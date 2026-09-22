#!/usr/bin/env python3
"""Assemble the plan's six-ablation machine-readable summary (2026-09-22).

Reads the frozen v54 evaluation payloads and the new A5/A6 ablation payloads
and writes ``results/v54/ablations/ablation_six_rows.json``: every plan
ablation x backbone x block with MASE, IR, conditional HIR, harmful loss,
beneficial precision and missed_opportunity, each row tagged as reused from
``results/v54/evaluation/`` or newly computed by ``v54_ablate_a5a6.py``.

Plan mapping (verified in docs/v54_ablations_a5a6_20260922.md):

* plan A1 Source Fixed            <- evaluation row SOURCE_FIXED
* plan A2 Linear utility          <- evaluation row A5_PARAMETRIC_RIDGE
* plan A3 drop intervention state <- evaluation row A2_WO_INTERVENTION
* plan A4 drop forecast state     <- evaluation row A3_WO_FORECAST
* plan A5 beta=0                  <- new row A5_BETA0 (a5a6 payloads)
* plan A6 no positive gate        <- new row A6_NO_POSITIVE_GATE (a5a6
                                     payloads; identical by construction to
                                     the existing A4_ALWAYS_ACT row)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import BACKBONES, OUT, ROOT, clean, write

BLOCKS = ("test", "test30", "test50")
METRICS = ("mase", "intervention_rate", "conditional_hir", "harmful_loss",
           "beneficial_precision", "missed_opportunity", "n_acted")

PLAN = {
    "A1_SOURCE_FIXED": {"provenance": "reused", "evaluation_row": "SOURCE_FIXED"},
    "A2_LINEAR_UTILITY": {"provenance": "reused",
                          "evaluation_row": "A5_PARAMETRIC_RIDGE"},
    "A3_WO_INTERVENTION_STATE": {"provenance": "reused",
                                 "evaluation_row": "A2_WO_INTERVENTION"},
    "A4_WO_FORECAST_STATE": {"provenance": "reused",
                             "evaluation_row": "A3_WO_FORECAST"},
    "A5_BETA0": {"provenance": "new", "a5a6_row": "A5_BETA0"},
    "A6_NO_POSITIVE_GATE": {"provenance": "new",
                            "a5a6_row": "A6_NO_POSITIVE_GATE"},
}


def pick(row: dict) -> dict:
    return {k: row.get(k) for k in METRICS}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root)

    cells: dict = {}
    missing = []
    for backbone in BACKBONES:
        cells[backbone] = {}
        for block in BLOCKS:
            eval_path = root / f"results/v54/evaluation/{block}_{backbone}.json"
            a5a6_path = root / f"results/v54/ablations/a5a6_{block}_{backbone}.json"
            eval_rows = json.loads(eval_path.read_text())["rows"]
            a5a6 = json.loads(a5a6_path.read_text())
            cell = {
                "FULL_INTROACT": pick(eval_rows["FULL_INTROACT"])
                | {"provenance": "reused",
                   "source_file": f"results/v54/evaluation/{block}_{backbone}.json"},
            }
            for plan_name, spec in PLAN.items():
                if spec["provenance"] == "reused":
                    row = eval_rows.get(spec["evaluation_row"])
                    if row is None:
                        missing.append((backbone, block, plan_name,
                                        "row absent (KEEP-only fallback?)"))
                        continue
                    cell[plan_name] = pick(row) | {
                        "provenance": "reused",
                        "evaluation_row": spec["evaluation_row"],
                        "source_file":
                            f"results/v54/evaluation/{block}_{backbone}.json"}
                else:
                    if a5a6.get("frozen", {}).get("keep_only"):
                        missing.append((backbone, block, plan_name,
                                        "skipped under KEEP-only fallback"))
                        continue
                    row = a5a6["rows"].get(spec["a5a6_row"])
                    if row is None:
                        missing.append((backbone, block, plan_name,
                                        "row absent in a5a6 payload"))
                        continue
                    cell[plan_name] = pick(row) | {
                        "provenance": "new",
                        "source_file":
                            f"results/v54/ablations/a5a6_{block}_{backbone}.json"}
                    if plan_name == "A5_BETA0":
                        cell[plan_name]["equals_full_by_construction"] = \
                            a5a6["a5_equals_full_by_construction"]
                    if plan_name == "A6_NO_POSITIVE_GATE":
                        cell[plan_name]["identical_to_existing_A4_ALWAYS_ACT"] = \
                            a5a6["a6_equals_existing_a4_always_act"].get("identical")
            cells[backbone][block] = cell

    payload = {
        "stage": "v54-ablation-six-rows",
        "plan_date": "2026-09-22",
        "blocks": list(BLOCKS),
        "backbones": list(BACKBONES),
        "note": ("blocks train_eval/test_m2/test_m3 also exist in the frozen "
                 "evaluation payloads for the reused rows; the new A5/A6 rows "
                 "were computed on test/test30/test50 only"),
        "plan_mapping": PLAN,
        "reference_row": "FULL_INTROACT",
        "metrics": list(METRICS),
        "cells": cells,
        "missing": [list(m) for m in missing],
    }
    out = root / "results/v54/ablations/ablation_six_rows.json"
    write(out, clean(payload))
    print(f"wrote {out}")
    if missing:
        print(json.dumps({"missing": missing}, indent=1))


if __name__ == "__main__":
    main()
