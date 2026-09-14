"""Three seed audit of every veto, for all four proposers.

Produces one record per candidate edit: which proposer made it, which stratum
it landed on, whether the acceptance layer vetoed it, and whether committing it
would have made the window worse judged offline against the pristine series.

That is everything the two analyses need. The evaluation protocol is fixed in
`docs/veto_evaluation_protocol.md` and the readings in
`docs/component3_verdict_criteria.md`, both committed before this ran.

Usage:
    python -u experiments/audit_seeds.py --device cuda --seeds 42 1 2
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from baselines import BASELINES  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from gating import proposals_of  # noqa: E402
from gating_classic import build_proposers, gate_whole_series  # noqa: E402

from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.probe import (SIGNAL_NAMES, ProbeConfig,  # noqa: E402
                               probe_window, reference_scale)
from introact_ts.structure import structure_distortion  # noqa: E402
from introact_ts.types import Action, Verdict  # noqa: E402
from introact_ts.verify import (VerifyConfig, action_risk,  # noqa: E402
                                improvement_consistency, improvement_depth,
                                verify)

#: Which structural path each proposer travels. This is the variable the
#: stratified test isolates.
PATH = {"stat_only": "local", "always_clean": "local",
        "screen": "global", "imr": "global"}


def audit_local(window, state, models, plan, agent, peer_idx, cfg, out):
    """Walk an operator sequence, recording the verdict and the truth for each."""
    work = np.asarray(window.series, dtype=np.float64).copy()
    scale = reference_scale(window.series)
    center = agent._calib.centers[peer_idx]
    spread = agent._calib.spreads[peer_idx]
    z_now = agent._calib.z[peer_idx]
    u = state.utility
    crop = 0
    ref = np.asarray(window.clean_series, dtype=np.float64)
    rv = float(np.var(ref - np.median(ref)))

    for action, params in plan:
        outcome = apply_action(work, action, **params)
        if not outcome.applicable:
            continue
        after = probe_window(outcome.series, models, scale, ProbeConfig())
        delta_u = after.utility - u
        z_after, _ = recalibrate_one(after.vector, center, spread,
                                     SIGNAL_NAMES, RISK_WEIGHTS)
        report = structure_distortion(work, outcome.series, action,
                                      outcome.params, touched=outcome.touched)
        consistency = improvement_consistency(z_now, z_after)
        depth = improvement_depth(z_now, z_after)
        risk = action_risk(depth, outcome.cost, consistency)
        verdict = verify(delta_u, report.distortion, risk, cfg)

        lo = int(outcome.params.get("lo", 0)) if action is Action.RESEGMENT else 0
        nb = _nmse(work, ref[crop:crop + len(work)], rv)
        na = _nmse(outcome.series,
                   ref[crop + lo:crop + lo + len(outcome.series)], rv)
        out.append({"stratum": window.stratum,
                    "contamination": window.contamination,
                    "vetoed": bool(verdict is not Verdict.ACCEPTED),
                    "harmful": bool(na > nb + 1e-9)})

        if verdict is Verdict.ACCEPTED:
            crop += lo
            work = outcome.series
            u = after.utility
            z_now = z_after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 1, 2])
    args = ap.parse_args()

    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    cfg = VerifyConfig(tau=args.tau)
    records = {k: [] for k in PATH}

    for seed in args.seeds:
        n = args.n
        spec = CorpusSpec(
            n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
            n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
            n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125),
            seed=seed)
        windows = build_corpus(spec, source="ett")
        agent = IntroActAgent(models, AgentConfig(verification=cfg))
        t0 = time.time()
        states = agent.perceive(windows)
        print(f"[seed {seed}] perceive {time.time() - t0:.0f}s", flush=True)

        for name in ["stat_only", "always_clean"]:
            t0 = time.time()
            traces = BASELINES[name](windows, states, models)
            byid = {t.window_id: t for t in traces}
            for i, (w, s) in enumerate(zip(windows, states)):
                plan = proposals_of(byid[w.window_id])
                if plan:
                    audit_local(w, s, models, plan, agent, i, cfg, records[name])
            print(f"  {name:14s} {time.time() - t0:.0f}s  "
                  f"{len(records[name])} records", flush=True)

        props, _ = build_proposers(windows)
        for name in ["screen", "imr"]:
            t0 = time.time()
            fn = props[name]
            for i, (w, s) in enumerate(zip(windows, states)):
                cand = fn(w.series)
                if np.allclose(np.nan_to_num(cand), np.nan_to_num(w.series),
                               atol=1e-12):
                    continue
                _, acc, rec = gate_whole_series(w, s, models, cand, agent, i, cfg)
                ref = np.asarray(w.clean_series, dtype=np.float64)
                rv = float(np.var(ref - np.median(ref)))
                nb = _nmse(w.series, ref, rv)
                na = _nmse(cand, ref, rv)
                records[name].append({"stratum": w.stratum,
                                      "contamination": w.contamination,
                                      "vetoed": bool(not acc),
                                      "harmful": bool(na > nb + 1e-9)})
            print(f"  {name:14s} {time.time() - t0:.0f}s  "
                  f"{len(records[name])} records", flush=True)

        (ROOT / "results" / "audit_seeds.json").write_text(
            json.dumps({"path": PATH, "seeds": args.seeds,
                        "records": records}, indent=1), encoding="utf-8")
    print("___AUDIT_SEEDS_DONE___", flush=True)


if __name__ == "__main__":
    main()
