"""Do the whole series rewriters discriminate once they travel the local path?

The three seed audit found the structural condition has discriminative power on
the local operator path, odds ratio 2.971 with p 1.0e-20, and none on the
global path, odds ratio 0.954. The interaction is significant, log odds
difference +1.136 with CI [+0.711, +1.562]. That points at an implementation
defect rather than a property of the method: the global path was never
calibrated, and the whole series rewriters were routed to it only because they
do not declare a footprint.

This tests the repair. A rewriter's footprint is not unknown, it is simply not
declared: the changed point set can be read off by comparing before and after.
Declaring it sends the candidate down the calibrated local path, which includes
the spread term that was added after the flattening failure.

Nothing is fabricated. The footprint is the actual set of points the proposer
altered.

Prediction, recorded before the run: if the defect account is right, the odds
ratio for these two proposers moves from about 0.95 towards the local path's
3.0. If it does not move, the account is wrong and the global path failure is
not about routing.

Usage:
    python -u experiments/global_path_fix.py --device cuda --seeds 42 1 2
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
from corpus import CorpusSpec, build_corpus  # noqa: E402
from gating_classic import build_proposers  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.probe import (SIGNAL_NAMES, ProbeConfig,  # noqa: E402
                               probe_window, reference_scale)
from introact_ts.structure import (GLOBAL_WEIGHTS, LOCAL_WEIGHTS,  # noqa: E402
                                   structure_distortion)
from introact_ts.types import Action, Verdict  # noqa: E402
from introact_ts.verify import (VerifyConfig, action_risk,  # noqa: E402
                                improvement_consistency, improvement_depth,
                                verify)


def judge(window, state, models, cand, agent, idx, cfg, route):
    """Score a whole series candidate down either structural path."""
    work = np.asarray(window.series, dtype=np.float64)
    cand = np.asarray(cand, dtype=np.float64)
    scale = reference_scale(window.series)
    after = probe_window(cand, models, scale, ProbeConfig())
    delta_u = after.utility - state.utility
    z_after, _ = recalibrate_one(after.vector, agent._calib.centers[idx],
                                 agent._calib.spreads[idx], SIGNAL_NAMES,
                                 RISK_WEIGHTS)
    if route == "global":
        report = structure_distortion(work, cand, Action.DENOISE, {},
                                      weights=GLOBAL_WEIGHTS)
    else:
        # The footprint the proposer did not declare, read off directly.
        touched = ~np.isclose(np.nan_to_num(cand), np.nan_to_num(work),
                              rtol=0, atol=1e-12)
        report = structure_distortion(work, cand, Action.DESPIKE, {},
                                      touched=touched, weights=LOCAL_WEIGHTS)
    consistency = improvement_consistency(agent._calib.z[idx], z_after)
    depth = improvement_depth(agent._calib.z[idx], z_after)
    changed = float(np.mean(~np.isclose(np.nan_to_num(cand),
                                        np.nan_to_num(work), atol=1e-12)))
    risk = action_risk(depth, changed, consistency)
    verdict = verify(delta_u, report.distortion, risk, cfg)
    return verdict is Verdict.ACCEPTED, float(report.distortion)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 1, 2])
    args = ap.parse_args()

    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    cfg = VerifyConfig(tau=args.tau)
    out = {f"{p}_{r}": [] for p in ("screen", "imr") for r in ("global", "local")}

    for seed in args.seeds:
        n = args.n
        spec = CorpusSpec(
            n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
            n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
            n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=seed)
        windows = build_corpus(spec, source="ett")
        agent = IntroActAgent(models, AgentConfig(verification=cfg))
        t0 = time.time()
        states = agent.perceive(windows)
        print(f"[seed {seed}] perceive {time.time() - t0:.0f}s", flush=True)
        props, _ = build_proposers(windows)

        for name in ("screen", "imr"):
            t0 = time.time()
            fn = props[name]
            for i, (w, s) in enumerate(zip(windows, states)):
                cand = fn(w.series)
                if np.allclose(np.nan_to_num(cand), np.nan_to_num(w.series),
                               atol=1e-12):
                    continue
                ref = np.asarray(w.clean_series, dtype=np.float64)
                rv = float(np.var(ref - np.median(ref)))
                harmful = bool(_nmse(cand, ref, rv) > _nmse(w.series, ref, rv) + 1e-9)
                for route in ("global", "local"):
                    acc, dist = judge(w, s, models, cand, agent, i, cfg, route)
                    out[f"{name}_{route}"].append(
                        {"stratum": w.stratum, "vetoed": not acc,
                         "harmful": harmful, "distortion": dist})
            print(f"  {name:8s} {time.time() - t0:.0f}s", flush=True)

        (ROOT / "results" / "global_path_fix.json").write_text(
            json.dumps({"seeds": args.seeds, "records": out}, indent=1),
            encoding="utf-8")

    print(f"\n{'arm':16s}{'n':>6s}{'odds ratio':>12s}{'accept harm':>13s}"
          f"{'reject harm':>13s}")
    from scipy.stats import fisher_exact
    for k, rows in out.items():
        rs = [r for r in rows if r["stratum"] == "contaminated"]
        vh = sum(1 for r in rs if r["vetoed"] and r["harmful"])
        vn = sum(1 for r in rs if r["vetoed"] and not r["harmful"])
        ah = sum(1 for r in rs if not r["vetoed"] and r["harmful"])
        an = sum(1 for r in rs if not r["vetoed"] and not r["harmful"])
        odds, _ = fisher_exact([[vh, vn], [ah, an]], alternative="greater")
        print(f"{k:16s}{len(rs):6d}{float(odds):12.3f}"
              f"{ah / max(ah + an, 1):13.3f}{vh / max(vh + vn, 1):13.3f}")
    print("___GLOBAL_PATH_FIX_DONE___", flush=True)


if __name__ == "__main__":
    main()
