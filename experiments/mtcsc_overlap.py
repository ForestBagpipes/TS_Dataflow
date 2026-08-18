"""Does MTCSC's univariate branch edit the same points SCREEN does.

Both are speed constraint repairs and both take the same bounds, so the question
is whether the second one is a distinct method on this corpus or a variant that
lands in the same place. If the edits coincide, listing MTCSC as a separate
baseline row would present one method twice.

The decision this feeds is stated before the run so the number is not read to
fit a convenience. **If the overlap is high, MTCSC is not implemented as a
separate arm and the full baseline table marks it as substantially coincident
with SCREEN, citing this measurement. If it is low, it is a distinct method and
gets its own row.** The reason recorded is coincidence, not effort.

Three levels of agreement are reported, because they can disagree and only the
strictest supports a merge.

  window level   did both edit the same windows at all
  point level    did both change the same positions inside a window
  value level    did both move those positions to the same value

Usage:
    python -u experiments/mtcsc_overlap.py --scale xl
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))

from corpus import build_corpus  # noqa: E402
from monitor import Monitor  # noqa: E402
from proposers_classic import (estimate_speed_bounds, mtcsc_uni_repair,  # noqa: E402
                               screen_repair)
from run_agent import SCALES  # noqa: E402

#: Positions counted as changed. Matches the strict edit definition used
#: everywhere else, an exact byte comparison rather than a tolerance.
ATOL = 1e-12


def changed_mask(before, after):
    b = np.nan_to_num(np.asarray(before, dtype=np.float64))
    a = np.nan_to_num(np.asarray(after, dtype=np.float64))
    return ~np.isclose(a, b, rtol=0, atol=ATOL)


def jaccard(a, b):
    inter = int((a & b).sum())
    union = int((a | b).sum())
    return (inter / union) if union else 1.0, inter, union


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--window", type=int, default=5)
    ap.add_argument("--value-rtol", dest="value_rtol", type=float, default=1e-3)
    ap.add_argument("--out", default=str(ROOT / "results" / "mtcsc_overlap.json"))
    args = ap.parse_args()

    rel_out = str(Path(args.out).relative_to(ROOT)).replace("\\", "/")
    mon = Monitor("mtcsc_overlap", expects=[rel_out],
                  config={"scale": args.scale, "seed": args.seed,
                          "window": args.window},
                  require_clean_tree=False, beat_every=10.0)
    mon.start()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source="ett")
    s_min, s_max = estimate_speed_bounds([w.series for w in windows])
    print(f"{len(windows)} windows, speed bounds [{s_min:.4f}, {s_max:.4f}]",
          flush=True)

    n_win_screen = n_win_mtcsc = n_win_both = n_win_either = 0
    pt_inter = pt_union = 0
    val_same = val_total = 0
    rel_diffs = []
    per_stratum = {}
    jac_per_window = []

    for i, w in enumerate(windows):
        a = screen_repair(w.series, s_min, s_max, window=args.window)
        b = mtcsc_uni_repair(w.series, s_min, s_max, window=args.window)
        ma, mb = changed_mask(w.series, a), changed_mask(w.series, b)
        ea, eb = bool(ma.any()), bool(mb.any())
        n_win_screen += ea
        n_win_mtcsc += eb
        n_win_both += (ea and eb)
        n_win_either += (ea or eb)

        j, inter, union = jaccard(ma, mb)
        pt_inter += inter
        pt_union += union
        if union:
            jac_per_window.append(j)

        # Value agreement, only over positions both methods touched.
        both = ma & mb
        if both.any():
            va, vb = a[both], b[both]
            close = np.isclose(va, vb, rtol=args.value_rtol, atol=1e-9)
            val_same += int(close.sum())
            val_total += int(both.sum())
            # How far apart the two repairs are, scaled by the window's own
            # spread so windows of different amplitude contribute comparably.
            scale = max(float(np.nanstd(w.clean_series)), 1e-9)
            rel_diffs.append(np.abs(va - vb) / scale)

        d = per_stratum.setdefault(w.stratum, {"n": 0, "screen": 0, "mtcsc": 0,
                                               "both": 0, "either": 0})
        d["n"] += 1
        d["screen"] += ea
        d["mtcsc"] += eb
        d["both"] += (ea and eb)
        d["either"] += (ea or eb)

        if (i + 1) % 200 == 0:
            mon.beat("repairing", done=i + 1, total=len(windows))

    win_j = n_win_both / n_win_either if n_win_either else 1.0
    pt_j = pt_inter / pt_union if pt_union else 1.0
    val_agree = val_same / val_total if val_total else float("nan")

    print(f"\nwindow level")
    print(f"  SCREEN edited      {n_win_screen}")
    print(f"  MTCSC edited       {n_win_mtcsc}")
    print(f"  both               {n_win_both}")
    print(f"  either             {n_win_either}")
    print(f"  jaccard            {win_j:.4f}")
    print(f"\npoint level")
    print(f"  intersection       {pt_inter}")
    print(f"  union              {pt_union}")
    print(f"  jaccard            {pt_j:.4f}")
    print(f"  per window mean    {np.mean(jac_per_window):.4f}"
          f"  median {np.median(jac_per_window):.4f}")
    rd = np.concatenate(rel_diffs) if rel_diffs else np.array([0.0])
    print(f"\nvalue level, over the {val_total} positions both touched")
    print(f"  same value within rtol {args.value_rtol}: {val_same} "
          f"({val_agree:.4f})")
    print(f"  repair difference in units of the window's clean sd")
    for q in (25, 50, 75, 90, 99):
        print(f"    p{q:<3d} {np.percentile(rd, q):.4f}")
    print(f"    share below 0.01 sd {float((rd < 0.01).mean()):.4f}"
          f"   below 0.1 sd {float((rd < 0.1).mean()):.4f}")

    print(f"\n{'stratum':<14s}{'n':>6s}{'screen':>8s}{'mtcsc':>7s}{'both':>6s}"
          f"{'jaccard':>9s}")
    for s, d in sorted(per_stratum.items()):
        j = d["both"] / d["either"] if d["either"] else 1.0
        print(f"{s:<14s}{d['n']:6d}{d['screen']:8d}{d['mtcsc']:7d}"
              f"{d['both']:6d}{j:9.4f}")

    payload = {
        "scale": args.scale, "seed": args.seed, "window": args.window,
        "n_windows": len(windows), "speed_bounds": [s_min, s_max],
        "window_level": {"screen": n_win_screen, "mtcsc": n_win_mtcsc,
                         "both": n_win_both, "either": n_win_either,
                         "jaccard": win_j},
        "point_level": {"intersection": pt_inter, "union": pt_union,
                        "jaccard": pt_j,
                        "per_window_mean": float(np.mean(jac_per_window)),
                        "per_window_median": float(np.median(jac_per_window))},
        "value_level": {"same": val_same, "total": val_total,
                        "agreement": val_agree, "rtol": args.value_rtol,
                        "rel_diff_sd_units": {
                            str(q): float(np.percentile(rd, q))
                            for q in (25, 50, 75, 90, 99)},
                        "share_below_0.01sd": float((rd < 0.01).mean()),
                        "share_below_0.1sd": float((rd < 0.1).mean())},
        "per_stratum": per_stratum,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, default=float),
                              encoding="utf-8")
    mon.finish(git_add=False)
    print("___MTCSC_OVERLAP_DONE___", flush=True)


if __name__ == "__main__":
    main()
