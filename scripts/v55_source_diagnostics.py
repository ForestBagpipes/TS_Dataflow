#!/usr/bin/env python3
"""Recompute exploratory leave-one-source-out margins from frozen v55 rows."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKBONES = ("bolt", "timesfm", "chronos2")
REFERENCES = ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "R2_CART", "TATO")


def main() -> None:
    results = {}
    sources = None
    for backbone in BACKBONES:
        path = ROOT / f"results/v55/evaluation/test_{backbone}.json"
        data = json.loads(path.read_text())
        rows = data["rows"]
        full = rows["FULL_INTROACT"]["per_source_mase"]
        if sources is None:
            sources = sorted(full)
        if sorted(full) != sources or len(sources) != 8:
            raise RuntimeError(f"{backbone}: source roster differs")
        per_ref = {}
        for reference in REFERENCES:
            control = rows[reference]["per_source_mase"]
            if sorted(control) != sources:
                raise RuntimeError(f"{backbone}/{reference}: source roster differs")
            per_ref[reference] = {
                "all_sources": sum(full[s] - control[s] for s in sources) / 8,
                "left_out": {
                    omitted: sum(full[s] - control[s] for s in sources
                                 if s != omitted) / 7
                    for omitted in sources
                },
            }
        results[backbone] = per_ref
    payload = {"stage": "v55-source-diagnostics", "scope": "exploratory TEST",
               "sources": sources, "backbones": results}
    target = ROOT / "results/v55/source_diagnostics.json"
    target.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    for backbone, per_ref in results.items():
        for reference, values in per_ref.items():
            worst = max(values["left_out"].items(), key=lambda item: item[1])
            print(backbone, reference, "all", round(values["all_sources"], 4),
                  "worst_leave_out", worst[0], round(worst[1], 4))


if __name__ == "__main__":
    main()
