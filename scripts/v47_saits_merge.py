#!/usr/bin/env python3
"""Join the imputer shards into one archive per block.

Each shard handled a disjoint set of sources and wrote its own archive, so the
join is a union with a check that no two shards claimed the same episode.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v47/replay/saits"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocks", required=True)
    args = parser.parse_args()

    began = time.perf_counter()
    report = {}
    for block in [b.strip() for b in args.blocks.split(",") if b.strip()]:
        shards = sorted(OUT.glob(f"{block}__*.npz"))
        if not shards:
            report[block] = {"status": "no shards"}
            continue
        merged: dict[str, np.ndarray] = {}
        owner: dict[str, str] = {}
        for path in shards:
            with np.load(path, allow_pickle=False) as store:
                for key in store.files:
                    if key in merged:
                        raise SystemExit(
                            f"{key} written by both {owner[key]} and {path.name}")
                    merged[key] = store[key]
                    owner[key] = path.name
        target = OUT / f"{block}.npz"
        with target.open("wb") as handle:
            np.savez(handle, **merged)
        report[block] = {"status": "ok", "shards": [p.name for p in shards],
                         "episodes": len(merged)}
        print(json.dumps({block: report[block]}), flush=True)

    (OUT / "merge_report.json").write_text(json.dumps({
        "stage": "v47-saits-merge", "blocks": report,
        "runtime_seconds": time.perf_counter() - began}, indent=1) + "\n")


if __name__ == "__main__":
    main()
