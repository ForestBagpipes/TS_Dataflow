"""Recompute the main table's headline columns from the per window traces.

Check four of the number discipline: every number that goes in the paper is
reconciled against a second, independent source. The main table's columns come
out of `score_rows`, which reads the live trace objects at the end of a run.
This file recomputes the same three columns from the JSONL the run flushed to
disk, and reports the difference. Agreement means the table is not an artefact
of how the run held its state, and the JSONL is a usable substrate for a future
metric change without a GPU.

The three columns and how each is rebuilt:

  protected mis edit rate   modified windows in the four protected strata over
                            the size of those strata. The probe layer is
                            excluded here as it is in the table
  damage rate               of the windows that were actually edited and carry
                            a clean reference, the share whose distance to that
                            reference grew. The table compares normalised mean
                            squared error, the JSONL stores root mean square
                            distance, and the two are monotone in each other on
                            a fixed window, so the comparison is the same one
  repair nRMSD              mean over contaminated windows of the final distance
                            divided by the window's own robust scale

The damage comparison is the one that can legitimately differ by a window or
two. The table's test is `a > b + 1e-9` on the normalised quantity, this one is
on the unnormalised distance, so a window sitting exactly on the boundary can
fall either side. A difference of more than a couple of windows is a real
disagreement and not a rounding artefact.

Usage:
    python experiments/reconcile_traces.py \
        --traces results/xl/seed_0_window_traces.jsonl \
        --table results/main_table_seed0.json
"""

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

PROTECTED = ("clean", "hard", "rare_valid", "changepoint")
PROBE_LAYER = "clean_ood"

#: Columns to reconcile, and how close counts as agreement. The rates are
#: computed from the same integers on both sides, so they should agree to
#: floating point. nRMSD averages the same floats in the same order.
TOL = 1e-6


def recompute(path, arm):
    """The three headline columns of one arm, from the JSONL alone."""
    n_protected = 0
    mis = 0
    committed = 0
    harmful = 0
    nrmsd = []
    n_rows = 0
    boundary = 0
    for line in Path(path).open(encoding="utf-8"):
        r = json.loads(line)
        if r["arm"] != arm:
            continue
        n_rows += 1
        stratum = r["stratum"]
        if stratum in PROTECTED:
            n_protected += 1
            if r["modified"]:
                mis += 1
        before, after = r["dist_before"], r["dist_after"]
        if before is None or after is None:
            continue
        if r["modified"]:
            committed += 1
            if after > before + 1e-9:
                harmful += 1
            elif abs(after - before) <= 1e-9:
                boundary += 1
        if stratum == "contaminated":
            v = r["nrmsd_after"]
            if v is not None:
                nrmsd.append(float(v))
    return {
        "rows": n_rows,
        "n_protected_windows": n_protected,
        "protected_mis_edits": mis,
        "protected_mis_edit_rate": (mis / n_protected) if n_protected else None,
        "committed_edits": committed,
        "damage_rate": (harmful / committed) if committed else 0.0,
        "n_injected_scored": len(nrmsd),
        "repair_nrmsd": float(np.mean(nrmsd)) if nrmsd else None,
        "repair_nrmsd_median": float(np.median(nrmsd)) if nrmsd else None,
        "at_boundary": boundary,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", required=True)
    ap.add_argument("--table", required=True)
    ap.add_argument("--arms", nargs="+",
                    default=["introact", "spec_veto", "utility_only",
                             "L1_screen", "L2_imr", "L3_mtcsc",
                             "L7_learn2clean", "oracle"])
    ap.add_argument("--out", default=str(ROOT / "results" / "trace_reconcile.json"))
    args = ap.parse_args()

    table = json.loads(Path(args.table).read_text(encoding="utf-8"))["rows"]
    cols = ("protected_mis_edit_rate", "damage_rate", "repair_nrmsd",
            "committed_edits", "n_protected_windows", "n_injected_scored")

    print(f"{'arm':16s}{'column':26s}{'table':>14s}{'traces':>14s}{'diff':>12s}")
    report, worst = {}, 0.0
    for arm in args.arms:
        if arm not in table:
            print(f"{arm:16s}not in the table, skipped")
            continue
        got = recompute(args.traces, arm)
        if got["rows"] == 0:
            print(f"{arm:16s}no rows in the traces, skipped")
            continue
        report[arm] = {"table": {c: table[arm].get(c) for c in cols},
                       "traces": got}
        for c in cols:
            t, g = table[arm].get(c), got.get(c)
            if t is None or g is None:
                print(f"{arm:16s}{c:26s}{str(t):>14s}{str(g):>14s}{'':>12s}")
                continue
            d = float(g) - float(t)
            worst = max(worst, abs(d))
            flag = "" if abs(d) <= TOL else "   <-- differs"
            print(f"{arm:16s}{c:26s}{float(t):14.6f}{float(g):14.6f}"
                  f"{d:+12.2e}{flag}")
        if got["at_boundary"]:
            print(f"{arm:16s}{'windows on the boundary':26s}"
                  f"{got['at_boundary']:>28d}")
        report[arm]["max_abs_diff"] = worst

    print()
    print(f"largest absolute difference across every arm and column {worst:.3e}")
    Path(args.out).write_text(json.dumps(
        {"traces": str(args.traces), "table": str(args.table),
         "tolerance": TOL, "max_abs_diff": worst, "arms": report}, indent=1),
        encoding="utf-8")
    print("___RECONCILE_DONE___")


if __name__ == "__main__":
    main()
