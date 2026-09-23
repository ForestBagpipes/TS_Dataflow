#!/usr/bin/env python3
"""Regenerate manuscript figure tables from the checked v55 TEST records."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "latex/figure/data"
BACKBONES = ("bolt", "timesfm", "chronos2")
BLOCKS = ("test", "test30", "test50")
METHODS = (
    ("Native KEEP", "NATIVE_KEEP"),
    ("Best Fixed", "BEST_FIXED"),
    ("R2-CART", "R2_CART"),
    ("Fixed SAITS", "FIXED_SAITS"),
    ("TATO", "TATO"),
    ("IntroAct-TS", "FULL_INTROACT"),
)


def loaded():
    return {
        (block, backbone): json.loads((ROOT / f"results/v55/evaluation/"
                                       f"{block}_{backbone}.json").read_text())
        for block in BLOCKS for backbone in BACKBONES
    }


def avg(records, key):
    return sum(row[key] for row in records) / len(records)


def main() -> None:
    data = loaded()
    DEST.mkdir(parents=True, exist_ok=True)
    harm = []
    severity = []
    for display, method in METHODS:
        rows = [data[("test", bb)]["rows"][method] for bb in BACKBONES]
        harm.append({
            "method": display, "mase": avg(rows, "mase"),
            "intervention_rate": 100 * avg(rows, "intervention_rate"),
            "conditional_hir": 100 * avg(rows, "conditional_hir"),
            "harmful_loss": avg(rows, "harmful_loss"),
            "beneficial_precision": ("" if any(r["beneficial_precision"] is None
                                          for r in rows) else
                                     100 * avg(rows, "beneficial_precision")),
            "missed_opportunity": 100 * avg(rows, "missed_opportunity"),
        })
        by_block = {
            block: avg([data[(block, bb)]["rows"][method]
                        for bb in BACKBONES], "mase")
            for block in BLOCKS
        }
        worst = max(
            data[(block, bb)]["rows"][method]["per_cell_mase"][cell]
            - data[(block, bb)]["rows"]["NATIVE_KEEP"]["per_cell_mase"][cell]
            for block in BLOCKS for bb in BACKBONES
            for cell in data[(block, bb)]["rows"][method]["per_cell_mase"]
        )
        severity.append({"method": display, "s10": by_block["test"],
                         "s30": by_block["test30"], "s50": by_block["test50"],
                         "worst_cell": worst})
    for name, rows in (("harm.csv", harm), ("severity.csv", severity)):
        with (DEST / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]),
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    evidence = {}
    for bb in BACKBONES:
        source = json.loads((ROOT / f"results/v55/gate_controls/{bb}.json").read_text())
        result = source["blocks"]["test"]
        evidence[bb] = {
            "rows": {name: {key: row[key] for key in
                             ("mase", "intervention_rate", "harmful_loss")}
                     for name, row in result["rows"].items()},
            "comparisons": result["comparisons"],
        }
    (DEST / "v55_gate_evidence.json").write_text(
        json.dumps(evidence, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"harm": harm, "severity": severity}, indent=1))


if __name__ == "__main__":
    main()
