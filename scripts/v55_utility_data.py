#!/usr/bin/env python3
"""Rewrite the action-utility figure table from the v55 records.

Panel (a,b) of the diagnostics figure reports, for each catalog action, how
often it is the best choice of its episode, how often it improves on the
unchanged input, and its mean realised utility.  All three come from the
heterogeneity block of the evaluation payloads and are averaged over the three
backbones with equal weight, which is the convention the caption states.

usage: v55_utility_data.py [--results results/v55] [--out latex/figure/data]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

BACKBONES = ("bolt", "timesfm", "chronos2")
LABEL = {"KEEP": "KEEP", "FFILL": "Ffill", "SINGLE_TSICL": "Single TS-ICL",
         "MULTI_TSICL": "Multi TS-ICL", "CONTEXT_RIDGE": "Context Ridge",
         "SAITS": "SAITS"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results/v55")
    ap.add_argument("--out", default="latex/figure/data")
    args = ap.parse_args()
    root, out = Path(args.results), Path(args.out)
    het = {bb: json.loads((root / "evaluation" / f"test_{bb}.json").read_text())["heterogeneity"]
           for bb in BACKBONES}

    rows = []
    for action, label in LABEL.items():
        best = [het[bb]["oracle_best_share"][action] for bb in BACKBONES]
        per = [het[bb]["per_action_utility"].get(action) for bb in BACKBONES]
        applicable = [p["applicable"] for p in per if p]
        positive = [p["p_positive"] for p in per if p]
        utility = [p["mean_utility"] for p in per if p]
        rows.append([
            label,
            round(100 * sum(best) / len(best), 1),
            int(sum(applicable) / len(applicable)) if applicable
            else het["bolt"]["episodes"],
            "" if action == "KEEP" else round(100 * sum(positive) / len(positive), 1),
            "%+.3f" % (sum(utility) / len(utility)) if utility else "+0.000",
        ])

    path = out / "utility.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["action", "best_share", "episodes", "beneficial_share",
                    "mean_utility"])
        w.writerows(rows)
    print(f"wrote {path}")
    for row in rows:
        print(row)
    span = [r[1] for r in rows]
    print("best-share range: %.1f to %.1f, KEEP %.1f"
          % (min(span), max(span), rows[0][1]))


if __name__ == "__main__":
    main()
