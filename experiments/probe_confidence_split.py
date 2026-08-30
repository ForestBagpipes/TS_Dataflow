"""Can the perception layer's own confidence separate its mistakes.

Forty percent of the calibration candidates sit on protected windows, where the
clean reference is the window itself, so any value rewriting candidate scores a
loss of exactly one by construction. Neither the structural nor the utility
condition can separate them: their distortions overlap with the contaminated
ones, and on the synthetic probe layer the utility gain is an order of magnitude
*higher* than on genuinely contaminated windows.

Those candidates exist because `infer_hypothesis` labelled a protected window
`contaminated`. That call returns a confidence, the posterior mass on the
winning hypothesis, and the question here is whether the mistakes are
concentrated where that number is low. If they are, the threshold can be
calibrated per family and per confidence band, which is Mondrian conformal
prediction and needs no ground truth at deployment: the band is computed from
the posterior, which the agent has.

If they are not, there is no split to make and the honest move is a conservative
v2 with the perception layer's confidence as the next version's work.

The criterion, fixed here before the numbers are seen: **some confidence
threshold must remove more than half of the protected candidates while keeping
more than 80 percent of the contaminated ones.**

Perception only, no candidate execution, so this is one pass over the
calibration corpus rather than the full scoring run.

Usage:
    python -u experiments/probe_confidence_split.py --device cuda
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.policy import PolicyConfig, propose_actions  # noqa: E402
from introact_ts.spo import ARMS  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--out", default=str(ROOT / "results" / "confidence_split.json"))
    args = ap.parse_args()

    windows, _ = build_calibration(n=args.n, seed=args.seed, source=args.source,
                                   verbose=True)
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    pcfg = PolicyConfig(enable_param_ladder=True)
    agent = IntroActAgent(models, AgentConfig(policy=pcfg, n_jobs=args.n_jobs))
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"perception {time.time() - t0:.0f}s on {len(windows)} windows",
          flush=True)

    rows = []
    for w, st in zip(windows, states):
        cands = [(a, p) for a, p in propose_actions(st, [], pcfg) if a in ARMS]
        rows.append({
            "window_id": int(w.window_id), "stratum": w.stratum,
            "protected": w.stratum in PROTECTED,
            "hypothesis": st.hypothesis, "confidence": float(st.confidence),
            "n_candidates": len(cands),
            "posterior": {k: float(v) for k, v in (st.posterior or {}).items()},
        })

    prot = [r for r in rows if r["protected"]]
    cont = [r for r in rows if not r["protected"]]
    print()
    print(f"{len(prot)} protected windows, {len(cont)} contaminated windows")

    # How often perception is wrong, and how many candidates that costs.
    mis = [r for r in prot if r["hypothesis"] == "contaminated"]
    print(f"protected windows labelled contaminated: {len(mis)} "
          f"({len(mis) / max(len(prot), 1):.4f}), "
          f"carrying {sum(r['n_candidates'] for r in mis)} candidates")
    ok = [r for r in cont if r["hypothesis"] == "contaminated"]
    print(f"contaminated windows labelled contaminated: {len(ok)} "
          f"({len(ok) / max(len(cont), 1):.4f}), "
          f"carrying {sum(r['n_candidates'] for r in ok)} candidates")

    print()
    print("confidence distribution, on windows that produced candidates")
    for name, sub in (("protected, mislabelled", mis),
                      ("contaminated, correctly labelled", ok)):
        c = np.asarray([r["confidence"] for r in sub if r["n_candidates"]])
        if not len(c):
            print(f"  {name:34s}none")
            continue
        q = {p: float(np.percentile(c, p)) for p in (5, 25, 50, 75, 95)}
        print(f"  {name:34s}n={len(c):5d}  " +
              "  ".join(f"q{p:02d}={v:.4f}" for p, v in q.items()))

    # The criterion. A cut keeps windows at or above the threshold.
    print()
    print("candidates surviving a confidence floor")
    print(f"{'floor':>8s}{'protected kept':>16s}{'share':>9s}"
          f"{'contaminated kept':>19s}{'share':>9s}{'meets criterion':>17s}")
    mis_total = sum(r["n_candidates"] for r in mis)
    ok_total = sum(r["n_candidates"] for r in ok)
    best = None
    table = []
    for floor in [0.0, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8,
                  0.85, 0.9, 0.95]:
        pk = sum(r["n_candidates"] for r in mis if r["confidence"] >= floor)
        ck = sum(r["n_candidates"] for r in ok if r["confidence"] >= floor)
        ps = pk / max(mis_total, 1)
        cs = ck / max(ok_total, 1)
        meets = ps < 0.5 and cs > 0.8
        table.append({"floor": floor, "protected_kept": pk,
                      "protected_share": ps, "contaminated_kept": ck,
                      "contaminated_share": cs, "meets": bool(meets)})
        if meets and best is None:
            best = floor
        print(f"{floor:8.2f}{pk:16d}{ps:9.4f}{ck:19d}{cs:9.4f}"
              f"{'yes' if meets else '':>17s}")

    print()
    if best is not None:
        print(f"criterion met at confidence floor {best:g}: it removes more "
              f"than half the protected candidates and keeps more than 80 "
              f"percent of the contaminated ones")
        print("so a per family per confidence band calibration has a signal to "
              "work with")
    else:
        print("no floor meets the criterion. Perception's own confidence does "
              "not separate its mistakes on this corpus, so there is no band "
              "to stratify on and the conservative path is the honest one")

    Path(args.out).write_text(json.dumps(
        {"n_protected": len(prot), "n_contaminated": len(cont),
         "n_mislabelled": len(mis), "mislabelled_candidates": mis_total,
         "correct_candidates": ok_total, "sweep": table,
         "criterion_met_at": best, "rows": rows}, indent=1, default=float),
        encoding="utf-8")
    print()
    print("___CONFIDENCE_SPLIT_DONE___", flush=True)


if __name__ == "__main__":
    main()
