"""IntroAct-TS: the perceive - act - verify - rollback loop.

Perception is corpus-level, because peer calibration needs neighbours: every
window is profiled and probed once, then each behaviour signature is scored
against structurally similar windows. Curation is per-window and sequential:
the policy proposes candidates, each is applied to a sandbox copy, the frozen
TSFM is re-probed on that copy, and the candidate is committed only if it
passes the dual verification. A rejected candidate leaves the working copy
untouched and the agent falls through to the next proposal.

Two invariants hold throughout and are what make the trace auditable:

  * the working copy is only ever replaced by a candidate that was accepted,
    so any prefix of the trace can be replayed to reconstruct the data;
  * every probe of a given window uses the same fixed reference scale and the
    same frozen peer statistics, so utilities and risks are comparable across
    the whole episode rather than drifting with the edits.
"""

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from .actions import apply_action
from .calibration import RISK_WEIGHTS, calibrate, ood_scores, recalibrate_one
from .policy import PolicyConfig, propose_actions
from .probe import ProbeConfig, SIGNAL_NAMES, probe_window, reference_scale
from .profiling import extract_statistical_profile
from .risk import (
    CorpusReference,
    RiskState,
    build_risk_state,
    corpus_reference,
    infer_hypothesis,
    statistical_evidence,
)
from .structure import structure_distortion
from .types import (
    Action,
    ActionRecord,
    GovernanceTrace,
    TERMINAL_ACTIONS,
    Verdict,
)
from .verify import (VerifyConfig, action_risk, improvement_consistency,
                     improvement_depth, verify)

#: Repair switch, see experiments/fix_compare.py. True feeds action_risk the
#: improvement depth of the edit under test, False restores the class posterior
#: it used to consume. Only the comparison harness sets it to False.
USE_DEPTH = True


@dataclass
class AgentConfig:
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    verification: VerifyConfig = field(default_factory=VerifyConfig)
    K_peers: int = 40
    max_probe_calls: int = 10
    seed: int = 42
    #: Worker processes for the statistical half of perception. None means all
    #: cores but two. Set to 1 to disable, which tests rely on for determinism
    #: of failure messages rather than of results, since the computation itself
    #: is deterministic either way.
    n_jobs: int = None
    #: When False the peer group becomes the whole corpus, which is exactly the
    #: uncalibrated baseline: behaviour is then z-scored globally and a volatile
    #: window looks defective simply for being volatile.
    peer_calibration: bool = True


class IntroActAgent:
    """A curation agent that must justify every edit it commits."""

    def __init__(self, models: list, cfg: AgentConfig = None):
        if not models:
            raise ValueError("at least one frozen backend is required")
        self.models = models
        self.judge = models[0]
        self.cfg = cfg or AgentConfig()
        self._calib = None
        self._ood = None
        self._reference = CorpusReference()

    # -- perception ---------------------------------------------------------

    def perceive(self, windows: list) -> list:
        """Profile, probe and peer-calibrate the whole corpus once.

        The statistical half of perception, the 12 dimensional profile and the
        defect evidence, is pure numpy and by far the slower half: STL, PELT,
        ADF and a sample entropy per window add up to roughly half a second
        each, against a few milliseconds for a batched GPU probe. Run serially
        it pins one core at 100 percent while the accelerator idles. It is also
        embarrassingly parallel, so it is farmed out to processes when the
        corpus is large enough to pay for the fork.
        """
        series_list = [np.asarray(w.series, dtype=np.float64) for w in windows]
        finite_list = [_finite(s) for s in series_list]

        n_jobs = self.cfg.n_jobs
        if n_jobs is None:
            n_jobs = max(1, (os.cpu_count() or 2) - 2)
        use_pool = n_jobs > 1 and len(windows) >= 64

        if use_pool:
            # Workers touch numpy only. The parent holds the CUDA context and
            # the children never enter it, which is what makes a fork safe here.
            chunk = max(1, len(windows) // (n_jobs * 4))
            with ProcessPoolExecutor(max_workers=n_jobs) as pool:
                profiles = list(
                    pool.map(extract_statistical_profile, finite_list, chunksize=chunk)
                )
                evidences = list(
                    pool.map(statistical_evidence, series_list, chunksize=chunk)
                )
        else:
            profiles = [extract_statistical_profile(x) for x in finite_list]
            evidences = [statistical_evidence(x) for x in series_list]

        behaviors, probes = [], []
        for series in series_list:
            pr = probe_window(series, self.models, reference_scale(series), self.cfg.probe)
            probes.append(pr)
            behaviors.append(pr.vector)

        P = np.stack(profiles)
        B = np.stack(behaviors)
        K = self.cfg.K_peers if self.cfg.peer_calibration else len(windows) - 1
        self._calib = calibrate(B, P, SIGNAL_NAMES, K=max(K, 2))
        self._ood = ood_scores(P, K=min(20, max(2, len(windows) - 1)))
        self._reference = corpus_reference(evidences, self._calib.risk, self._ood)
        #: Read only cache of the perception inputs. Nothing in the loop reads
        #: these; they exist so an experiment can rebuild the risk states with a
        #: substituted behavioural score without re running the probe, which is
        #: the expensive part. Adding them changes no computation.
        self._evidences = evidences
        self._probes = probes
        self._profiles = P

        states = []
        for i, w in enumerate(windows):
            states.append(
                build_risk_state(
                    window_id=w.window_id,
                    series=w.series,
                    profile=P[i],
                    probe_result=probes[i],
                    z_row=self._calib.z[i],
                    behav_risk=float(self._calib.risk[i]),
                    ood=float(self._ood[i]),
                    reference=self._reference,
                    signal_names=SIGNAL_NAMES,
                    evidence=evidences[i],
                )
            )
        return states

    # -- curation -----------------------------------------------------------

    def curate_window(self, window, state: RiskState, peer_idx: int,
                      policy=None, cluster: int = None,
                      budget: int = None) -> GovernanceTrace:
        """Run the closed loop on one window and return its governance trace.

        ``policy`` is optional. Without it the proposer's own ordering is used,
        which is the fixed rule every earlier result was produced with. With it
        the candidate list is reordered by the upper confidence bound before
        anything is tried, and every adjudicated candidate is fed back. The
        shield is untouched either way, so a learned policy cannot admit
        anything the fixed rule could not.

        ``budget`` caps the probe calls for this window, which is how the
        corpus level allocation reaches a single episode. None means the
        configured global cap applies.
        """
        cfg = self.cfg
        original = np.asarray(window.series, dtype=np.float64).copy()
        scale = reference_scale(original)
        center = self._calib.centers[peer_idx]
        spread = self._calib.spreads[peer_idx]

        work = original.copy()
        utility = state.utility
        z_now = state.z
        live = state
        records = []
        probe_calls = 1
        final_state = "KEEP"
        step = 0
        crop_offset = 0

        cap = cfg.max_probe_calls if budget is None else min(cfg.max_probe_calls,
                                                            max(int(budget), 1))
        while step < cfg.policy.max_steps and probe_calls < cap:
            candidates = propose_actions(live, records, cfg.policy)
            if policy is not None and cluster is not None:
                candidates = policy.order(candidates, cluster, records)
            committed = False

            for action, params in candidates:
                if action in TERMINAL_ACTIONS:
                    records.append(
                        ActionRecord(
                            step=step, action=action, params=dict(params),
                            verdict=Verdict.NO_OP, delta_utility=0.0,
                            struct_distortion=0.0, risk=0.0,
                            utility_before=utility, utility_after=utility,
                            note="terminal",
                        )
                    )
                    final_state = _terminal_label(action, records)
                    step = cfg.policy.max_steps
                    committed = True
                    break

                outcome = apply_action(work, action, **params)
                if not outcome.applicable:
                    records.append(
                        ActionRecord(
                            step=step, action=action, params=dict(params),
                            verdict=Verdict.NO_OP, delta_utility=0.0,
                            struct_distortion=0.0, risk=0.0,
                            utility_before=utility, utility_after=utility,
                            cost=outcome.cost, note=outcome.note,
                        )
                    )
                    continue

                # Post-intervention re-probe on the sandbox copy.
                after = probe_window(outcome.series, self.models, scale, cfg.probe)
                probe_calls += 1
                delta_u = after.utility - utility
                z_after, _ = recalibrate_one(
                    after.vector, center, spread, SIGNAL_NAMES, RISK_WEIGHTS
                )
                report = structure_distortion(
                    work, outcome.series, action, outcome.params, touched=outcome.touched
                )
                consistency = improvement_consistency(z_now, z_after)
                depth = improvement_depth(z_now, z_after)
                risk = action_risk(
                    depth if USE_DEPTH else live.confidence,
                    outcome.cost, consistency,
                )
                verdict = verify(delta_u, report.distortion, risk, cfg.verification)

                records.append(
                    ActionRecord(
                        step=step, action=action, params=dict(outcome.params),
                        verdict=verdict, delta_utility=float(delta_u),
                        struct_distortion=float(report.distortion), risk=float(risk),
                        utility_before=float(utility), utility_after=float(after.utility),
                        struct_parts=report.parts, cost=float(outcome.cost),
                        note=outcome.note,
                    )
                )

                if policy is not None and cluster is not None:
                    policy.observe(cluster, action, verdict, float(delta_u),
                                   1, records)

                if verdict is Verdict.ACCEPTED:
                    if action is Action.RESEGMENT:
                        crop_offset += int(outcome.params.get("lo", 0))
                    work = outcome.series
                    utility = after.utility
                    z_now = z_after
                    live = self._refresh(live, work, after, z_after, center, spread)
                    final_state = "REPAIRED"
                    committed = True
                    break
                # Rejected: the sandbox copy is discarded, `work` is untouched.

            if not committed:
                # Without the ladder a refused list ends the episode, which is
                # what every result before this was produced under. With it,
                # the refusal is information rather than a stop: the next round
                # proposes the same operators at the rung the verdict selected,
                # `fresh` keeps it from retrying a setting already judged, and
                # `max_steps` still bounds the whole thing. When the rungs run
                # out `propose_actions` returns a terminal action and the loop
                # leaves through the branch above.
                if not getattr(cfg.policy, "enable_param_ladder", False):
                    break
            step += 1

        return GovernanceTrace(
            window_id=window.window_id,
            stratum=window.stratum,
            contamination=window.contamination,
            initial_series=original,
            final_series=work,
            records=records,
            final_state=final_state,
            initial_utility=float(state.utility),
            final_utility=float(utility),
            risk_state={
                "hypothesis": state.hypothesis,
                "confidence": state.confidence,
                "behav_risk": state.behav_risk,
                "ood": state.ood,
                "dominant_defect": state.dominant_defect,
                "defect_strength": state.defect_strength,
                "posterior": state.posterior,
            },
            probe_calls=probe_calls,
            crop_offset=crop_offset,
        )

    def _refresh(self, state, series, probe_result, z_after, center, spread) -> RiskState:
        """Re-derive the risk state after a committed edit."""
        _, risk_after = recalibrate_one(
            probe_result.vector, center, spread, SIGNAL_NAMES, RISK_WEIGHTS
        )
        evidence = statistical_evidence(series)
        z_named = {n: float(z_after[i]) for i, n in enumerate(SIGNAL_NAMES)}
        label, conf, posterior = infer_hypothesis(
            evidence, risk_after, state.ood, self._reference, z_named
        )
        evidence["z"] = z_named
        return RiskState(
            window_id=state.window_id,
            profile=state.profile,
            behavior=probe_result.vector,
            z=z_after,
            utility=probe_result.utility,
            behav_risk=risk_after,
            ood=state.ood,
            evidence=evidence,
            posterior=posterior,
            hypothesis=label,
            confidence=conf,
            reference=self._reference,
        )

    # -- driver -------------------------------------------------------------

    def run(self, windows: list, verbose: bool = False) -> list:
        """Perceive the corpus, then curate every window."""
        states = self.perceive(windows)
        traces = []
        for i, (w, s) in enumerate(zip(windows, states)):
            traces.append(self.curate_window(w, s, peer_idx=i))
            if verbose and (i + 1) % 50 == 0:
                print(f"  curated {i + 1}/{len(windows)}")
        return traces


def _terminal_label(action: Action, records: list) -> str:
    if action is Action.QUARANTINE:
        return "QUARANTINE"
    if action is Action.ABSTAIN:
        return "ABSTAIN"
    return "REPAIRED" if any(r.accepted for r in records) else "KEEP"


def _finite(series: np.ndarray) -> np.ndarray:
    """Profiling needs finite input; the agent still sees the raw NaNs."""
    x = np.asarray(series, dtype=np.float64)
    if np.isfinite(x).all():
        return x
    good = np.isfinite(x)
    if not good.any():
        return np.zeros_like(x)
    idx = np.arange(len(x))
    out = x.copy()
    out[~good] = np.interp(idx[~good], idx[good], x[good])
    return out
