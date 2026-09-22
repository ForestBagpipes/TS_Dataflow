#!/usr/bin/env python3
"""v54 parent manifest: the explicit parent-window list behind the freeze.

Emits ``configs/v54/parent_manifest.json``: ``grid.summary()`` block sizes and
purge audit plus, per block, the explicit parent list (source, parent id,
read_start, origin, max_target_end) and, for TRAIN, the bank/train_eval
assignment.  Pure function of the registered metadata; no data row is read.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from introact_ts.v46 import grid as G
from v54_common import ROOT, clean, sha, write

OUT = ROOT / "configs" / "v54"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    summary = G.summary(root)

    train = G.train_parents(root)
    assignment = G.assign_train(train)
    blocks = {}
    for block in G.BLOCKS:
        parents = G.parents_of(root, block)
        blocks[block] = {
            "parents": [{
                "source": p.source, "parent": p.parent,
                "read_start": int(p.read_start), "origin": int(p.origin),
                "max_target_end": int(p.max_target_end),
            } for p in sorted(parents, key=lambda p: (p.source, p.read_start))],
        }
    payload = {
        "stage": "v54-parent-manifest",
        "generated_by": "scripts/v54_parent_manifest.py",
        "summary": summary,
        "train_assignment": {p.parent: assignment[p.parent] for p in train},
        "blocks": blocks,
        "code_sha256": {
            "src/introact_ts/v46/grid.py": sha(root / "src/introact_ts/v46/grid.py"),
            "scripts/v54_parent_manifest.py": sha(Path(__file__).resolve()),
        },
        "runtime_seconds": time.perf_counter() - began,
    }
    write(OUT / "parent_manifest.json", clean(payload))
    print(json.dumps({b: {"parents": s["parents"], "episodes": s["episodes"]}
                      for b, s in summary.items() if b != "purge_audit"},
                     indent=1))


if __name__ == "__main__":
    main()
