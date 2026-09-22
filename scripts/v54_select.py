#!/usr/bin/env python3
"""v54 stage 4a step 2: hyperparameter selection on the rebuilt v54 bank.

Identical rule to v47 (``scripts/v47_select.py``): leave-one-parent-out over
K_GRID x BETA_GRID on the bankx block under the harm cap.  What changed is the
input semantics: the catalog now carries v54-full22 states and the scoring is
parent-clustered (freeze SS6), and an infeasible cap falls back to KEEP-only
with the refusal recorded (freeze SS4) instead of the old max-beta retreat.

Writes ``results/v54/protocol/selection_{backbone}.json``; reads nothing from
and writes nothing to ``results/v47/``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import state as ST
from introact_ts.v47 import select as SEL

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import BACKBONES, OUT, ROOT, clean, code_hashes, load_catalogs, sha, write

PROTOCOL = OUT / "protocol"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--bank-blocks", default="bankx")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    catalogs = []
    for name in args.bank_blocks.split(","):
        catalogs.extend(load_catalogs(root, name.strip(), args.backbone))
    blocks = SEL.blocks_of()
    bank = SEL.Bank(catalogs, blocks=blocks)
    queries = SEL.Queries(catalogs, blocks=blocks)

    cap = SEL.harm_cap(bank, queries)
    chosen = SEL.select_hyperparameters(bank, queries, cap=cap["cap"])

    snapshot = OUT / "replay" / "bank" / f"{args.bank_blocks}_{args.backbone}.npz"
    payload = {
        "stage": "v54-hyperparameter-selection",
        "state_version": ST.STATE_VERSION,
        "backbone": args.backbone,
        "block": args.bank_blocks,
        "episodes": len(catalogs),
        "parents": int(len({c.parent for c in catalogs})),
        "sources": int(len({c.source for c in catalogs})),
        "bank_support": bank.support(),
        "bank_mean_utility": {k: (None if not np.isfinite(v) else v)
                              for k, v in bank.mean_utility().items()},
        "harm_cap": cap,
        "k_grid": list(SEL.K_GRID),
        "beta_grid": list(SEL.BETA_GRID),
        "selection": chosen,
        "state_snapshot": (str(snapshot.relative_to(ROOT))
                           if snapshot.exists() else None),
        "code_sha256": code_hashes(root) | {
            "scripts/v54_select.py": sha(Path(__file__).resolve())},
        "runtime_seconds": time.perf_counter() - began,
        "test_records_read": 0,
    }
    write(PROTOCOL / f"selection_{args.backbone}.json", clean(payload))
    print(json.dumps(clean({"backbone": args.backbone,
                            "selected": chosen["selected"],
                            "keep_only": chosen.get("keep_only"),
                            "cap": cap["cap"], "anchor": cap["anchor"],
                            "leader": chosen["leader"],
                            "feasible_settings": chosen["feasible_settings"],
                            "episodes": len(catalogs)}), indent=1))


if __name__ == "__main__":
    main()
