"""Baselines that stand in for the families of prior work.

Each produces a ``GovernanceTrace`` so the same metrics apply to all of them.

  no_action      leave the corpus alone; the floor for repair and the ceiling
                 for protection
  always_clean   unconditional rule-based pipeline (impute, despike, denoise)
                 applied to every window -- the classical statistical cleaner
  stat_only      pick the operator the dominant statistical defect implies and
                 execute it directly: an action-selecting agent with no model
                 feedback, no re-probe and no rollback
  quality_rank   score windows by peer-calibrated behavioural risk and clean the
                 worst alpha of them wholesale -- the quality-assessment family,
                 which ranks but cannot verify

The point of the last two is that they choose *the same kinds of actions*
IntroAct-TS chooses. What they lack is the mechanism to find out whether the
action was worth committing.
"""

import numpy as np

from introact_ts.actions import apply_action
from introact_ts.probe import probe_window, reference_scale
from introact_ts.types import (
    Action,
    ActionRecord,
    GovernanceTrace,
    Verdict,
)

DEFECT_TO_ACTION = {
    "missing": Action.IMPUTE,
    "spike": Action.DESPIKE,
    "noise": Action.DENOISE,
    "shift": Action.RESEGMENT,
}


def _trace(window, state, series, records, final_state, initial_u, final_u, probes,
           crop_offset=0):
    return GovernanceTrace(
        window_id=window.window_id,
        stratum=window.stratum,
        contamination=window.contamination,
        initial_series=np.asarray(window.series, dtype=np.float64).copy(),
        final_series=np.asarray(series, dtype=np.float64).copy(),
        records=records,
        final_state=final_state,
        initial_utility=float(initial_u),
        final_utility=float(final_u),
        risk_state={
            "hypothesis": state.hypothesis,
            "confidence": state.confidence,
            "behav_risk": state.behav_risk,
            "ood": state.ood,
            "dominant_defect": state.dominant_defect,
            "defect_strength": state.defect_strength,
            "posterior": state.posterior,
        },
        probe_calls=probes,
        crop_offset=crop_offset,
    )


def _record(step, action, outcome, u_before, u_after):
    return ActionRecord(
        step=step,
        action=action,
        params=dict(outcome.params),
        verdict=Verdict.ACCEPTED,
        delta_utility=float(u_after - u_before),
        struct_distortion=0.0,
        risk=0.0,
        utility_before=float(u_before),
        utility_after=float(u_after),
        cost=float(outcome.cost),
        note="committed without verification",
    )


def run_no_action(windows: list, states: list, models: list) -> list:
    return [
        _trace(w, s, w.series, [], "KEEP", s.utility, s.utility, 1)
        for w, s in zip(windows, states)
    ]


def _pipeline(window, state, models, actions, probe_cfg, label):
    """Apply a fixed sequence of operators with no verification at all."""
    work = np.asarray(window.series, dtype=np.float64).copy()
    scale = reference_scale(window.series)
    records = []
    u = state.utility
    probes = 1
    crop_offset = 0
    for step, (action, params) in enumerate(actions):
        outcome = apply_action(work, action, **params)
        if not outcome.applicable:
            continue
        after = probe_window(outcome.series, models, scale, probe_cfg)
        probes += 1
        records.append(_record(step, action, outcome, u, after.utility))
        if action is Action.RESEGMENT:
            crop_offset += int(outcome.params.get("lo", 0))
        work = outcome.series
        u = after.utility
    final = "REPAIRED" if records else "KEEP"
    return _trace(window, state, work, records, final, state.utility, u, probes,
                  crop_offset=crop_offset)


def run_always_clean(windows: list, states: list, models: list, probe_cfg=None) -> list:
    from introact_ts.probe import ProbeConfig

    probe_cfg = probe_cfg or ProbeConfig()
    plan = [
        (Action.IMPUTE, {}),
        (Action.DESPIKE, {}),
        (Action.DENOISE, {"strength": "medium"}),
    ]
    return [
        _pipeline(w, s, models, plan, probe_cfg, "always_clean")
        for w, s in zip(windows, states)
    ]


def run_stat_only(windows: list, states: list, models: list, probe_cfg=None) -> list:
    """Route on the dominant statistical defect and commit immediately."""
    from introact_ts.probe import ProbeConfig

    probe_cfg = probe_cfg or ProbeConfig()
    traces = []
    for w, s in zip(windows, states):
        defect = s.dominant_defect
        if defect == "none":
            traces.append(_trace(w, s, w.series, [], "KEEP", s.utility, s.utility, 1))
            continue
        plan = [(DEFECT_TO_ACTION[defect], {})]
        traces.append(_pipeline(w, s, models, plan, probe_cfg, "stat_only"))
    return traces


def run_quality_rank(
    windows: list, states: list, models: list, alpha: float = 0.25, probe_cfg=None
) -> list:
    """Clean the worst alpha by behavioural risk, wholesale.

    This is the quality-assessment family taken to its logical conclusion: the
    ranking is informative, but acting on it means applying a fixed pipeline to
    whatever lands in the bottom tier, with no way to notice when that was a
    mistake.
    """
    from introact_ts.probe import ProbeConfig

    probe_cfg = probe_cfg or ProbeConfig()
    risks = np.asarray([s.behav_risk for s in states], dtype=np.float64)
    threshold = float(np.quantile(risks, 1.0 - alpha))
    plan = [
        (Action.IMPUTE, {}),
        (Action.DESPIKE, {}),
        (Action.DENOISE, {"strength": "medium"}),
    ]
    traces = []
    for w, s in zip(windows, states):
        if s.behav_risk >= threshold:
            traces.append(_pipeline(w, s, models, plan, probe_cfg, "quality_rank"))
        else:
            traces.append(_trace(w, s, w.series, [], "KEEP", s.utility, s.utility, 1))
    return traces


BASELINES = {
    "no_action": run_no_action,
    "always_clean": run_always_clean,
    "stat_only": run_stat_only,
    "quality_rank": run_quality_rank,
}
