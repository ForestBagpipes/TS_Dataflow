#!/usr/bin/env python3
"""v4.4 Step 7-8 -- the TRAIN-Eval admission report.

Reads ``results/v44/evaluation/train_eval.json`` (produced by
``scripts/v44_selector.py --mode eval``) and turns the frozen ladder into an
admission verdict.

The verdict is deliberately split into two halves that must not be confused:

* **Control comparison** -- is the frozen method better than the controls it
  must beat (Native KEEP, Best Fixed, the R2 CART control)?
* **Component contribution** -- does removing each module make the method
  *worse*?  A component whose removal improves the metric does not contribute,
  whatever the headline comparison says.

Every comparison is a paired cluster bootstrap at the parent level, macro
averaged over the eight sources, so the interval and the table cell are the
same quantity.  Nothing here opens calibration or test.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from introact_ts.v44 import protocol as P
from introact_ts.v44 import statistics as ST

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "results/v44/evaluation"

#: Methods of the frozen ladder, in reporting order.
CONTROLS = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART")
COMPONENTS = {
    "A1_GLOBAL_REPLAY": "Module 2 (task-state matching): retrieval replaced by global replay",
    "A2_WO_INTERVENTION": "Module 2 (task-state matching): intervention block removed",
    "A3_WO_FORECAST": "Module 2 (task-state matching): reference-forecast block removed",
    "A4_WO_GATE": "Module 3 (conservative intervention): gate removed",
    "A5_PARAMETRIC_RIDGE": "Module 2 replaced by a ridge gain predictor",
    "A5_PARAMETRIC_CART": "Module 2 replaced by a depth-3 CART gain predictor",
}
FULL = "FULL_INTROACT"
DIAGNOSTIC = ("CATALOG_ORACLE",)


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def compare(records: list[dict], backbone: str, left: str, right: str) -> dict:
    """Paired cluster bootstrap of ``left - right`` (negative = left is better)."""
    left_means = ST.parent_means(records, method=left, backbone=backbone)
    right_means = ST.parent_means(records, method=right, backbone=backbone)
    result = ST.paired_cluster_bootstrap(left_means, right_means)
    result["left"] = left
    result["right"] = right
    # MASE is a loss, so a negative difference means the left method wins.
    if result.get("status") == "computed":
        result["favours"] = ("left" if result["difference"] < 0
                             else "right" if result["difference"] > 0 else "tie")
        result["excludes_zero"] = bool(result["ci_low"] > 0
                                       or result["ci_high"] < 0)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(EVAL / "train_eval.json"))
    parser.add_argument("--output", default=str(EVAL / "admission.json"))
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text())
    records = payload["records"]
    report: dict = {
        "stage": "v44-train-eval-admission-report",
        "frozen": payload["frozen"],
        "objective": "paired cluster bootstrap of source-macro MASE, parent as unit",
        "bootstrap": {"resamples": P.BOOTSTRAP_RESAMPLES, "seed": P.BOOTSTRAP_SEED,
                      "level": P.CI_LEVEL},
        "per_backbone": {},
        "heldout_labels_read": 0,
        "calibration_test_touched": False,
    }

    for backbone in P.DEV_BACKBONES:
        subset = [r for r in records if r["backbone"] == backbone]
        methods = sorted({r["method"] for r in subset})
        table = {}
        for method in methods:
            means = ST.parent_means(subset, method=method, backbone=backbone)
            table[method] = {
                "source_macro_mase": ST.source_macro(means),
                "parents": len(means),
                "cells": payload["per_backbone"][backbone]["macro_cells"].get(method, {}),
                "governance": payload["per_backbone"][backbone]["governance"].get(method, {}),
            }

        controls = {name: compare(subset, backbone, FULL, name)
                    for name in CONTROLS if name in methods}
        components = {name: compare(subset, backbone, FULL, name)
                      for name in COMPONENTS if name in methods}

        # A component contributes only if removing it makes the method worse,
        # i.e. only if FULL is better (lower MASE) than the ablated variant.
        contributions = {
            name: {
                "removes": COMPONENTS[name],
                "difference_full_minus_ablation": result.get("difference"),
                "ci_low": result.get("ci_low"),
                "ci_high": result.get("ci_high"),
                "excludes_zero": result.get("excludes_zero"),
                "contributes": bool(result.get("difference") is not None
                                    and result["difference"] < 0),
                "contributes_significantly": bool(result.get("excludes_zero")
                                                  and result["difference"] < 0),
            }
            for name, result in components.items()
        }

        wins = ST.cell_win_counts(subset, method=FULL, baseline="NATIVE_KEEP")
        report["per_backbone"][backbone] = {
            "table": table,
            "vs_controls": controls,
            "component_contribution": contributions,
            "average_rank": ST.average_rank(
                subset, methods=[m for m in methods if m != DIAGNOSTIC[0]]),
            "vs_native_keep_cells": wins,
        }

    # -- verdicts ----------------------------------------------------------
    verdicts = {}
    for backbone, data in report["per_backbone"].items():
        table = data["table"]
        full = table[FULL]["source_macro_mase"]
        row = {}
        for name in CONTROLS:
            if name not in table:
                continue
            other = table[name]["source_macro_mase"]
            row[f"beats_{name}"] = bool(full is not None and other is not None
                                        and full < other)
        verdicts[backbone] = {
            "full_source_macro_mase": full,
            "beats_controls": row,
            "all_components_contribute": all(
                item["contributes"]
                for item in data["component_contribution"].values()),
            "components_not_contributing": sorted(
                name for name, item in data["component_contribution"].items()
                if not item["contributes"]),
        }
    report["verdicts"] = verdicts

    write(Path(args.output), report)
    print(json.dumps(verdicts, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
