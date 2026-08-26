"""Aggregate the main table over seeds and report mean and standard deviation.

Reads the per seed result files written by `run_main.py` and reports, per arm,
the mean and the sample standard deviation of every numeric column across the
seeds. Nothing is recomputed here, the numbers are the ones the runs wrote.

Two guards, because a mean over seeds is only meaningful if the seeds ran the
same experiment:

  the column set of every seed must match, otherwise a column is silently
  averaged over a subset of the seeds

  the arm set of every seed must match, for the same reason

The spread is the sample standard deviation, ddof 1, since three seeds are a
sample of the seed distribution rather than the whole of it. With three seeds
that estimate is itself noisy, so the per seed values are printed beside it.

Usage:
    python experiments/aggregate_seeds.py \
        --files results/main_table_seed0.json results/main_table_seed1.json \
                results/main_table_seed2.json
"""

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

#: The columns the paper's main table carries, in the order it carries them.
HEADLINE = ("committed_edits", "protected_mis_edit_rate", "damage_rate",
            "repair_nrmsd", "repair_nrmsd_median")

#: Arms in the order the frozen matrix lists them.
ARM_ORDER = ("L0_no_action", "L1_screen", "L2_imr", "L3_mtcsc", "L4_data_oob",
             "L5_timeinf", "L6_ltsv", "L7_learn2clean", "L8_tsrating",
             "soft_penalty", "utility_only", "spec_veto", "introact", "oracle")


def load(paths):
    blobs = []
    for p in paths:
        b = json.loads(Path(p).read_text(encoding="utf-8"))
        b["_path"] = str(p)
        blobs.append(b)
    arms = [set(b["rows"]) for b in blobs]
    if len({frozenset(a) for a in arms}) != 1:
        raise SystemExit(f"the seeds do not carry the same arms: {arms}")
    return blobs


def numeric(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def aggregate(blobs, arm):
    """Mean, sample std and the per seed values, for every numeric column."""
    rows = [b["rows"][arm] for b in blobs]
    keys = [set(r) for r in rows]
    common = set.intersection(*keys)
    out = {}
    for k in sorted(common):
        vals = [r[k] for r in rows]
        if not all(numeric(v) for v in vals):
            continue
        a = np.asarray(vals, dtype=np.float64)
        out[k] = {"mean": float(a.mean()),
                  "std": float(a.std(ddof=1)) if len(a) > 1 else 0.0,
                  "values": [float(x) for x in a]}
    dropped = sorted(set().union(*keys) - common)
    return out, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--out", default=str(ROOT / "results" / "main_table_agg.json"))
    args = ap.parse_args()

    blobs = load(args.files)
    seeds = [b.get("seed") for b in blobs]
    print(f"{len(blobs)} seeds {seeds}, "
          f"windows {[b.get('n_windows') for b in blobs]}, "
          f"tau {[b.get('tau') for b in blobs]}")
    for b in blobs:
        if b.get("warnings"):
            print(f"  warning in {b['_path']}: {b['warnings']}")

    agg = {}
    for arm in ARM_ORDER:
        if arm not in blobs[0]["rows"]:
            continue
        agg[arm], dropped = aggregate(blobs, arm)
        if dropped:
            print(f"  {arm}: columns present in only some seeds, skipped "
                  f"{dropped}")

    print()
    head = f"{'arm':16s}{'edits':>16s}{'mis edit rate':>20s}{'damage rate':>20s}{'nRMSD':>20s}"
    print(head)
    for arm, d in agg.items():
        cells = []
        for col in ("committed_edits", "protected_mis_edit_rate",
                    "damage_rate", "repair_nrmsd"):
            if col not in d:
                cells.append(f"{'n/a':>20s}")
                continue
            fmt = "{:.0f}+-{:.0f}" if col == "committed_edits" else "{:.4f}+-{:.4f}"
            cells.append(f"{fmt.format(d[col]['mean'], d[col]['std']):>20s}")
        print(f"{arm:16s}" + "".join(cells))

    print()
    print("per seed values, the three headline columns of the shielded arms")
    for arm in ("utility_only", "spec_veto", "introact"):
        if arm not in agg:
            continue
        for col in ("damage_rate", "protected_mis_edit_rate", "repair_nrmsd"):
            v = agg[arm][col]
            per = " ".join(f"{x:.4f}" for x in v["values"])
            print(f"  {arm:14s}{col:26s}{per}   mean {v['mean']:.4f} "
                  f"std {v['std']:.4f}")

    # The pre agreed check. A damage rate that moves more than this across seeds
    # would mean the seed, not the method, decides the headline number.
    THRESHOLD = 0.05
    verdict = None
    if "introact" in agg:
        s = agg["introact"]["damage_rate"]["std"]
        verdict = {"introact_damage_rate_std": s, "threshold": THRESHOLD,
                   "exceeds": bool(s > THRESHOLD)}
        print()
        print(f"introact damage rate std {s:.4f} against threshold {THRESHOLD}: "
              f"{'EXCEEDS' if s > THRESHOLD else 'within'}")

    if "introact" in agg and "spec_veto" in agg:
        print()
        print("introact against spec_veto, per seed difference")
        for col in ("damage_rate", "protected_mis_edit_rate", "repair_nrmsd"):
            a = np.asarray(agg["introact"][col]["values"])
            b = np.asarray(agg["spec_veto"][col]["values"])
            d = a - b
            per = " ".join(f"{x:+.4f}" for x in d)
            sign = "all negative" if (d < 0).all() else (
                "all positive" if (d > 0).all() else "mixed sign")
            print(f"  {col:26s}{per}   mean {d.mean():+.4f}  {sign}")

    Path(args.out).write_text(json.dumps(
        {"seeds": seeds, "files": [b["_path"] for b in blobs],
         "n_windows": [b.get("n_windows") for b in blobs],
         "rows": agg, "damage_std_check": verdict}, indent=1),
        encoding="utf-8")
    print()
    print("___AGGREGATE_DONE___")


if __name__ == "__main__":
    main()
