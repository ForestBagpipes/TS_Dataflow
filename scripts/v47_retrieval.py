#!/usr/bin/env python3
"""What restricting retrieval costs.

The method scores a request against the whole bank of its backbone, without
asking that a neighbour share the request's source or its horizon.  The state
already carries the mask geometry, the visible context and the reference
forecast, which is what the neighbourhood is meant to match on, so the question
is empirical: does narrowing the pool to the request's own source or its own
horizon help or hurt.

Nothing here selects anything.  The frozen configuration is read from the
selection file and reused unchanged in all four rows.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v47 import select as SEL

ROOT = Path(__file__).resolve().parent.parent
C.REPLAY = "results/v47/replay"
OUT = ROOT / "results/v47/diagnostics"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--block", default="test")
    parser.add_argument("--bank-blocks", default="bankx")
    args = parser.parse_args()

    began = time.perf_counter()
    frozen = json.loads(
        (ROOT / f"results/v47/protocol/selection_{args.backbone}.json").read_text())
    k = int(frozen["selection"]["selected"]["k"])
    beta = float(frozen["selection"]["selected"]["beta"])

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(C.load_catalog(ROOT, name.strip(), args.backbone))
    eval_catalogs = C.load_catalog(ROOT, args.block, args.backbone)
    blocks = SEL.blocks_of()
    bank = SEL.Bank(bank_catalogs, blocks=blocks)
    queries = SEL.Queries(eval_catalogs, blocks=blocks)

    rows = {}
    for label, same_horizon, same_source in (("none", False, False),
                                             ("same_horizon", True, False),
                                             ("same_source", False, True),
                                             ("same_source_and_horizon", True, True)):
        D = SEL.distance_matrices(bank, queries, lopo=False,
                                  same_horizon=same_horizon,
                                  same_source=same_source)
        selected = SEL.decide(queries, SEL.score_grid(bank, queries, D, k, beta))
        out = SEL.outcomes(queries, selected)
        rows[label] = {
            "mase": SEL.source_macro(queries, out["mase"]),
            "intervention_rate": out["intervention_rate"],
            "conditional_hir": out["conditional_hir"],
            "harmful_loss": out["harmful_loss"],
        }
        print(json.dumps({label: rows[label]}), flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"retrieval_{args.block}_{args.backbone}.json").write_text(json.dumps({
        "stage": "v47-retrieval-scope",
        "backbone": args.backbone, "block": args.block,
        "frozen": {"k": k, "beta": beta},
        "note": "the frozen configuration is reused in every row and nothing is selected here",
        "rows": rows,
        "runtime_seconds": time.perf_counter() - began,
    }, indent=1) + "\n")


if __name__ == "__main__":
    main()
