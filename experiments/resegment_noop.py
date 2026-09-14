"""Why RESEGMENT declines to act on two thirds of the windows it is offered.

On the 350 window slice, 125 of 189 RESEGMENT candidates in the contaminated
layer returned NO_OP, and 209 of 291 in the protected layer. A NO_OP is not a
refusal by the shield; the operator itself decided there was nothing to do. That
distinction matters for the coverage number, because a candidate that never
executes cannot be admitted no matter how the threshold is set.

Four causes are separable from the operator's own return value:

  no changepoint          `changepoints` found nothing at this penalty
  would discard too much  a cut existed but the surviving piece was shorter
                          than `min_keep_frac` of the window
  too short               the window is below the operator's minimum length
  other                   anything else, reported rather than folded in

The sweep over the two parameters says whether the rate is a property of the
data or of the settings the ladder chose.

Usage:
    python experiments/resegment_noop.py --n 350 --seed 202
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402
from build_calibration import build_slice  # noqa: E402

from introact_ts.actions import changepoints, op_resegment  # noqa: E402
from introact_ts.policy import LADDER, RUNG_ORDER, _at_rung  # noqa: E402
from introact_ts.types import Action  # noqa: E402


def classify(note, applicable):
    if applicable:
        return "acted"
    n = (note or "").lower()
    if "no changepoint" in n:
        return "no changepoint"
    if "discard too much" in n:
        return "would discard too much"
    if "short" in n:
        return "too short"
    return f"other: {n[:40]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=350)
    ap.add_argument("--seed", type=int, default=202)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--out", default=str(ROOT / "results" / "resegment_noop.json"))
    args = ap.parse_args()

    cal, _ = build_calibration(n=1600, seed=101, source=args.source)
    windows, _, short = build_slice(args.n, args.seed, source=args.source,
                                    also_avoid=[cal], verbose=True)
    if short:
        raise SystemExit(f"slice short in {short}")

    print()
    print("at the three ladder rungs, over every window of the slice")
    print(f"{'rung':14s}{'penalty':>9s}{'min_keep':>10s}{'acted':>7s}"
          f"{'no cp':>7s}{'discard':>9s}{'other':>7s}{'act rate':>10s}")
    per_rung = {}
    for rung in RUNG_ORDER:
        params = _at_rung(Action.RESEGMENT, rung)
        c = Counter()
        for w in windows:
            x = np.asarray(w.series, dtype=np.float64)
            o = op_resegment(x, **params)
            c[classify(o.note, o.applicable)] += 1
        n = sum(c.values())
        per_rung[rung] = {"params": params, "counts": dict(c),
                          "act_rate": c["acted"] / max(n, 1)}
        print(f"{rung:14s}{params['penalty']:9.1f}{params['min_keep_frac']:10.2f}"
              f"{c['acted']:7d}{c['no changepoint']:7d}"
              f"{c['would discard too much']:9d}"
              f"{n - c['acted'] - c['no changepoint'] - c['would discard too much']:7d}"
              f"{c['acted'] / max(n, 1):10.4f}")

    print()
    print("penalty sweep at min_keep_frac 0.5, which separates detection from "
          "the keep rule")
    print(f"{'penalty':>9s}{'acted':>7s}{'no cp':>7s}{'discard':>9s}"
          f"{'act rate':>10s}{'mean cuts found':>17s}")
    sweep = {}
    for pen in (4.0, 6.0, 8.0, 12.0, 20.0, 30.0, 50.0):
        c = Counter()
        cuts = []
        for w in windows:
            x = np.asarray(w.series, dtype=np.float64)
            cuts.append(len(changepoints(x, penalty=pen, min_size=24)))
            o = op_resegment(x, penalty=pen, min_size=24, min_keep_frac=0.5)
            c[classify(o.note, o.applicable)] += 1
        n = sum(c.values())
        sweep[pen] = {"counts": dict(c), "act_rate": c["acted"] / max(n, 1),
                      "mean_cuts": float(np.mean(cuts))}
        print(f"{pen:9.1f}{c['acted']:7d}{c['no changepoint']:7d}"
              f"{c['would discard too much']:9d}{c['acted'] / max(n, 1):10.4f}"
              f"{np.mean(cuts):17.2f}")

    print()
    print("by stratum, at the default rung")
    params = _at_rung(Action.RESEGMENT, "default")
    by_st = defaultdict(Counter)
    for w in windows:
        x = np.asarray(w.series, dtype=np.float64)
        o = op_resegment(x, **params)
        by_st[w.stratum][classify(o.note, o.applicable)] += 1
    print(f"{'stratum':14s}{'n':>6s}{'acted':>7s}{'no cp':>7s}{'discard':>9s}"
          f"{'act rate':>10s}")
    strata = {}
    for st in sorted(by_st):
        c = by_st[st]
        n = sum(c.values())
        strata[st] = {"n": n, "counts": dict(c), "act_rate": c["acted"] / n}
        print(f"{st:14s}{n:6d}{c['acted']:7d}{c['no changepoint']:7d}"
              f"{c['would discard too much']:9d}{c['acted'] / n:10.4f}")

    print()
    d = per_rung["default"]["counts"]
    tot = sum(d.values())
    main_cause = max((k for k in d if k != "acted"), key=lambda k: d[k])
    print(f"dominant cause at the default rung: {main_cause}, "
          f"{d[main_cause]} of {tot}")
    print("a NO_OP is the operator declining, not the shield refusing, so it "
          "caps coverage before any threshold applies")

    Path(args.out).write_text(json.dumps(
        {"n_windows": len(windows), "slice_seed": args.seed,
         "per_rung": per_rung, "penalty_sweep": sweep, "by_stratum": strata,
         "dominant_cause": main_cause}, indent=1, default=float),
        encoding="utf-8")
    print()
    print("___RESEGMENT_NOOP_DONE___")


if __name__ == "__main__":
    main()
