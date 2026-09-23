#!/usr/bin/env python3
"""Audit completed PSW-I Traffic shards after a report permission failure.

The old failed report is archived intact. A recovery report is issued only if
all four existing archives exactly cover their frozen input episodes and every
repair matches observed values while filling hidden values finitely.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v54/replay/external/pswi"
TAG = "pswi-traffic-full"
BLOCKS = ("train_eval", "test", "test30", "test50")


def audit() -> dict[str, int]:
    coverage = {}
    for block in BLOCKS:
        manifest = json.loads((ROOT / f"results/v47/replay/inputs/{block}.json").read_text())
        expected = {f"{row['episode']}|PSW_I" for row in manifest["rows"]
                    if row["source"] == "Traffic"}
        archive = OUT / f"{block}__{TAG}.npz"
        with np.load(archive, allow_pickle=False) as repairs, \
                np.load(ROOT / f"results/v47/replay/inputs/{block}.npz",
                        allow_pickle=False) as inputs:
            if set(repairs.files) != expected:
                raise RuntimeError(f"{block}: archive coverage differs from registry")
            for key in repairs.files:
                episode = key.rsplit("|", 1)[0]
                repaired = repairs[key]
                reference = inputs[f"{episode}|reference"]
                if repaired.shape != reference.shape:
                    raise RuntimeError(f"{block}/{episode}: wrong shape")
                observed = np.isfinite(reference)
                if not np.allclose(repaired[observed], reference[observed],
                                   rtol=1e-5, atol=1e-4):
                    raise RuntimeError(f"{block}/{episode}: observed values changed")
                if not np.isfinite(repaired[~observed]).all():
                    raise RuntimeError(f"{block}/{episode}: hidden values not finite")
        coverage[block] = len(expected)
    return coverage


def main() -> None:
    coverage = audit()  # no mutation until every block is checked
    report = OUT / f"report_full-{TAG}.json"
    status = OUT / f"status_full-{TAG}.json"
    previous = json.loads(report.read_text())
    if previous.get("recovery"):
        raise SystemExit("recovery report already exists")
    if any(previous.get("arrays", {}).values()):
        raise SystemExit("prior report already recorded completed arrays")
    archive = OUT / "archive_failed_reports_20260923"
    archive.mkdir(exist_ok=True)
    for original in (report, status):
        target = archive / original.name
        if target.exists():
            raise SystemExit(f"refusing to overwrite {target}")
        shutil.copy2(original, target)
    previous["per_source"]["Traffic"] = {
        "status": "recovered: complete existing shards independently audited",
        "episodes": coverage,
    }
    previous["arrays"] = {f"{block}__{TAG}.npz": n
                          for block, n in coverage.items()}
    previous["failures"] = {}
    previous["recovery"] = {
        "reason": "original root-owned report prevented final vipuser write",
        "original_failed_reports": [str(archive / p.name) for p in (report, status)],
        "audit": "exact frozen episode coverage, observed values, finite hidden values",
    }
    payload = json.dumps(previous, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    for target in (report, status):
        target.write_text(payload)
    print(json.dumps({"status": "recovered", "coverage": coverage}))


if __name__ == "__main__":
    main()
