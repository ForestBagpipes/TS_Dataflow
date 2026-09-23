#!/usr/bin/env python3
"""Reject incomplete external forecasts before using their paper rows."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent.parent
BLOCKS = ("test", "test30", "test50")
BACKBONES = ("bolt", "timesfm", "chronos2")
METHODS = ("tato", "timesnet", "pswi", "t1")


def check(root: Path, methods: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    replay = root / "results/v47/replay/inputs"
    baselines = root / "results/v47/baselines"
    for block in BLOCKS:
        rows = json.loads((replay / f"{block}.json").read_text())["rows"]
        expected = {row["episode"] for row in rows}
        if len(expected) != len(rows):
            raise ValueError(f"{block}: repeated episode identifiers")
        for method in methods:
            for backbone in BACKBONES:
                label = f"{method}/{block}/{backbone}"
                run = baselines / f"{method}_{block}_{backbone}"
                payload = json.loads((run / "records.json").read_text())
                records = payload["records"]
                if payload.get("block") != block or payload.get("backbone") != backbone:
                    raise ValueError(f"{label}: metadata mismatch")
                if method != "tato" and payload.get("method") != method:
                    raise ValueError(f"{label}: method mismatch")
                if set(records) != expected:
                    raise ValueError(f"{label}: missing or extra forecast episodes")
                failures = payload.get("failed", payload.get("missing", 0))
                if failures != 0 or payload.get("scored") != len(expected):
                    raise ValueError(f"{label}: failed or unscored requests")
                if not all(item.get("mase") is not None and
                           math.isfinite(item["mase"]) for item in records.values()):
                    raise ValueError(f"{label}: nonfinite MASE")
                with np.load(run / "predictions.npz", allow_pickle=False) as archive:
                    if set(archive.files) != expected:
                        raise ValueError(f"{label}: prediction archive coverage mismatch")
                counts[label] = len(expected)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    args = parser.parse_args()
    counts = check(args.root, tuple(args.methods))
    print(json.dumps({"status": "passed", "counts": counts}, sort_keys=True))


if __name__ == "__main__":
    main()
