"""Count what the pre registered stratum criteria actually select.

The criteria and every threshold are fixed in
docs/stratum_selection_preregistration.md, which was committed before this
script ran. Nothing here may widen them. A layer that does not fill is reported
with its count and its cause.

Three unit conventions for the changepoint jump are measured side by side, not
because the criterion is undecided but because the pre registration promised to
report the jump distribution of the selected layer against the injected level
shift, and that comparison is only meaningful once both are expressed in the
same scale. The pre registered criterion is the channel IQR one. The other two
are diagnostics that say what the criterion is doing, and they are reported
whichever way they come out.

  channel     the pre registered unit, the channel's IQR over its whole history
  window      the window's own spread, which is what inject() scales by
  blockwise   the median of blockwise IQRs, which a level break does not inflate

Usage:
    python -u experiments/stratum_selection.py --n 800
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

import corpus as C  # noqa: E402
from datasets import (FINANCIAL, INDUSTRIAL, channel_columns,  # noqa: E402
                      sample_ett_windows, sample_time_windows)

from introact_ts.actions import robust_scale  # noqa: E402


def family_of(dataset: str) -> str:
    return "financial" if dataset in set(FINANCIAL) else "industrial"


def jump_in_units(series, ref_channel):
    """The best split's standardised jump under each of the three units."""
    x = np.asarray(series, dtype=np.float64)
    med = float(np.median(x))
    out = {}
    out["channel"] = C.best_split(x, ref_channel)[0]
    out["window"] = C.best_split(x, (med, C._spread(x), np.inf))[0]
    out["blockwise"] = C.best_split(x, (med, robust_scale(x), np.inf))[0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=800,
                    help="windows drawn per family")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "results" / "stratum_selection.json"))
    args = ap.parse_args()

    cols = channel_columns(tuple(INDUSTRIAL) + tuple(FINANCIAL))
    pool = (sample_ett_windows(args.n, seed=args.seed)
            + sample_time_windows(args.n, seed=args.seed))
    print(f"pool {len(pool)} windows, "
          f"{sum(1 for w in pool if family_of(w['dataset']) == 'industrial')} "
          f"industrial and "
          f"{sum(1 for w in pool if family_of(w['dataset']) == 'financial')} "
          f"financial", flush=True)

    rng = np.random.RandomState(args.seed)
    per_ds = defaultdict(lambda: {"n": 0, "rare": 0, "cp": 0})
    fails = Counter()
    jumps = defaultdict(lambda: defaultdict(list))
    rare_diag = []

    for w in pool:
        ref = C.channel_reference(cols[(w["dataset"], w["channel"])])
        fam = family_of(w["dataset"])
        d = per_ds[w["dataset"]]
        d["n"] += 1

        ok_r, dg_r = C.is_rare_valid(w["series"], ref)
        d["rare"] += int(ok_r)
        if dg_r:
            rare_diag.append(dg_r)
            if not ok_r:
                # Which of the three conditions stopped it. Reported so a zero
                # count has a cause attached rather than just a zero.
                if dg_r["peak_z"] < dg_r["tail_z"]:
                    fails[f"{fam}:rare:A1_no_tail"] += 1
                elif dg_r["tail_share"] > C.BRIEF_FRAC:
                    fails[f"{fam}:rare:A2_not_brief"] += 1
                else:
                    fails[f"{fam}:rare:A3_no_return"] += 1

        t, dg_c = C.jump_t(w["series"], ref)
        if dg_c and not dg_c["passes_gates"]:
            if not ((1 / C.SCALE_RATIO) <= dg_c["scale_ratio"] <= C.SCALE_RATIO):
                fails[f"{fam}:cp:C1_scale_moved"] += 1
            else:
                fails[f"{fam}:cp:C2_also_rare"] += 1

        for unit, val in jump_in_units(w["series"], ref).items():
            jumps[f"{fam}:real"][unit].append(val)
        shifted, _ = C.inject(w["series"], "level_shift", rng)
        for unit, val in jump_in_units(shifted, ref).items():
            jumps[f"{fam}:injected"][unit].append(val)

    # The changepoint layer is a within family rank, so it is selected over the
    # whole pool at once rather than window by window.
    refs = {i: C.channel_reference(cols[(w["dataset"], w["channel"])])
            for i, w in enumerate(pool)}
    fams = {i: family_of(w["dataset"]) for i, w in enumerate(pool)}
    n_cp = int(round(0.1125 * len(pool)))
    chosen, cp_report = C.select_changepoints(
        [(i, w["series"]) for i, w in enumerate(pool)], refs, fams, n_cp)
    for i in chosen:
        per_ds[pool[i]["dataset"]]["cp"] += 1

    def qs(a):
        a = np.asarray(a, dtype=np.float64)
        return {f"q{p:02d}": round(float(np.percentile(a, p)), 4)
                for p in (5, 50, 95, 99)}

    report = {
        "criteria": {
            "TAIL_PERCENTILE": C.TAIL_PERCENTILE, "BRIEF_FRAC": C.BRIEF_FRAC,
            "RETURN_TOL": C.RETURN_TOL, "JUMP_D": C.JUMP_D,
            "SCALE_RATIO": C.SCALE_RATIO, "SPLIT_MARGIN": C.SPLIT_MARGIN,
        },
        "per_dataset": {k: dict(v) for k, v in per_ds.items()},
        "failure_reasons": dict(fails),
        "changepoint_rank_selection": cp_report,
        "jump_distribution": {k: {u: qs(v) for u, v in d.items()}
                              for k, d in jumps.items()},
    }

    print()
    print(f"{'dataset':22s}{'n':>6s}{'rare_valid':>12s}{'changepoint':>13s}")
    for name in sorted(per_ds):
        v = per_ds[name]
        print(f"{name:22s}{v['n']:6d}{v['rare']:12d}{v['cp']:13d}")
    tot_r = sum(v["rare"] for v in per_ds.values())
    tot_c = sum(v["cp"] for v in per_ds.values())
    print(f"{'total':22s}{len(pool):6d}{tot_r:12d}{tot_c:13d}")

    print()
    print("changepoint layer, within family rank")
    for fam, v in cp_report.items():
        ts = v["t_selected"]
        print(f"  {fam:12s} pool {v['pool']:5d} quota {v['quota']:4d} "
              f"eligible {v['eligible']:5d} taken {v['taken']:4d} "
              f"shortfall {v['shortfall']:3d}  "
              f"t min {min(ts) if ts else float('nan'):.3f} "
              f"max {max(ts) if ts else float('nan'):.3f}")

    print()
    print("why a window was rejected")
    for k in sorted(fails):
        print(f"  {k:34s}{fails[k]:6d}")

    print()
    print("jump size, selected against injected, three units")
    for key in sorted(jumps):
        for unit in ("channel", "window", "blockwise"):
            q = qs(jumps[key][unit])
            print(f"  {key:22s}{unit:11s}"
                  f"q05={q['q05']:8.3f} q50={q['q50']:8.3f} "
                  f"q95={q['q95']:8.3f} q99={q['q99']:8.3f}")

    Path(args.out).write_text(json.dumps(report, indent=1, default=float),
                              encoding="utf-8")
    print("___STRATUM_SELECTION_DONE___", flush=True)


if __name__ == "__main__":
    main()
