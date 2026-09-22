#!/usr/bin/env python3
"""Join per-source imputer shards into one archive per block.

Each shard handled a disjoint set of sources and wrote its own archive, so the
join is a union with a check that no two shards claimed the same episode.
Same contract as scripts/v47_saits_merge.py, parameterised by method.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True)
    parser.add_argument("--blocks", required=True)
    args = parser.parse_args()

    out = ROOT / f"results/v54/replay/external/{args.method.lower()}"
    began = time.perf_counter()
    report = {}
    for block in [b.strip() for b in args.blocks.split(",") if b.strip()]:
        shards = sorted(out.glob(f"{block}__*.npz"))
        shards = [p for p in shards if "__smoke" not in p.name]
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
        target = out / f"{block}.npz"
        with target.open("wb") as handle:
            np.savez(handle, **merged)
        report[block] = {"status": "ok", "shards": [p.name for p in shards],
                         "episodes": len(merged)}
        print(json.dumps({block: report[block]}), flush=True)

    (out / "merge_report.json").write_text(json.dumps({
        "stage": "v54-external-merge", "method": args.method.upper(),
        "blocks": report,
        "runtime_seconds": time.perf_counter() - began}, indent=1) + "\n")


if __name__ == "__main__":
    main()
