#!/usr/bin/env python3
"""v4.6 hyperparameter selection: leave-one-parent-out on the replay bank.

This runs before any TEST record is scored.  It reads the bank block only,
chooses (k, beta) per backbone under a harmful-intervention cap anchored on the
best fixed intervention, and writes the freeze note that the evaluation script
requires.  Running the evaluation without this file is refused.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v47_verified import catalog as C
from introact_ts.v47_verified import select as SEL

ROOT = Path(__file__).resolve().parent.parent
C.REPLAY = "results/v47_verified/replay"
OUT = ROOT / "results/v47_verified/protocol"


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--bank-blocks", default="bankx",
                        help="comma separated blocks that make up the replay bank")
    global OUT
    parser.add_argument("--output-root", default="results/v47_verified")
    args = parser.parse_args()
    OUT = Path(args.root) / args.output_root / "protocol"
    C.REPLAY = args.output_root + "/replay"
    if any(b.strip().startswith("test") for b in args.bank_blocks.split(",")):
        raise SystemExit("cannot select on TEST")

    began = time.perf_counter()
    root = Path(args.root)
    catalogs = []
    for name in args.bank_blocks.split(","):
        catalogs.extend(C.load_catalog(root, name.strip(), args.backbone))
    blocks = SEL.blocks_of()
    bank = SEL.Bank(catalogs, blocks=blocks)
    queries = SEL.Queries(catalogs, blocks=blocks)

    cap = SEL.harm_cap(bank, queries)
    chosen = SEL.select_hyperparameters(bank, queries, cap=cap["cap"])

    payload = {
        "stage": "v47-hyperparameter-selection",
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
        "runtime_seconds": time.perf_counter() - began,
        "test_records_read": 0,
    }
    write(OUT / f"selection_{args.backbone}.json", payload)
    print(json.dumps({"backbone": args.backbone,
                      "selected": chosen["selected"],
                      "cap": cap["cap"], "anchor": cap["anchor"],
                      "fallback": chosen["fallback_to_most_conservative"],
                      "best_lopo": chosen["grid"][0],
                      "episodes": len(catalogs)}, indent=1))


if __name__ == "__main__":
    main()
