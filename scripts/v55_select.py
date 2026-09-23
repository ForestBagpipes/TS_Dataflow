#!/usr/bin/env python3
"""v55 step 1: choose ``(k, beta, lam)`` on the frozen v54 replay bank.

Same data, same harm cap and same leave one parent out procedure as
``scripts/v54_select.py``.  The only difference is the third axis: the score
shrinks the local mean towards the source level mean with strength ``lam``, and
``lam = 0`` recovers the v54 rule exactly, so the v54 configuration is inside
the search space and the outcome can be read as what cross validation prefers
when both earlier rules are available.

Writes ``results/v55/protocol/selection_{backbone}.json`` and reads nothing
outside ``results/v54/replay`` and ``results/v47/replay``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import state as ST
from introact_ts.v47 import select as SEL
from introact_ts.v55 import select as V55

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import ROOT, clean, code_hashes, load_catalogs, sha, write

OUT55 = ROOT / "results/v55"
PROTOCOL = OUT55 / "protocol"


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
    chosen = V55.select_hyperparameters(bank, queries, cap=cap["cap"])

    means = V55.source_action_means(bank)
    payload = {
        "stage": "v55-hyperparameter-selection",
        "state_version": ST.STATE_VERSION,
        "backbone": args.backbone,
        "block": args.bank_blocks,
        "episodes": len(catalogs),
        "parents": int(len({c.parent for c in catalogs})),
        "sources": int(len({c.source for c in catalogs})),
        "bank_support": bank.support(),
        "bank_mean_utility": {k: (None if not np.isfinite(v) else v)
                              for k, v in bank.mean_utility().items()},
        "source_action_mean_utility": {
            action: {source: entry["mean"] for source, entry in table.items()}
            for action, table in means.items()},
        "harm_cap": cap,
        "k_grid": list(V55.K_GRID),
        "beta_grid": list(V55.BETA_GRID),
        "lam_grid": [None if np.isinf(v) else v for v in V55.LAM_GRID],
        "selection": chosen,
        "code_sha256": code_hashes(root) | {
            "scripts/v55_select.py": sha(Path(__file__).resolve()),
            "src/introact_ts/v55/select.py": sha(
                root / "src/introact_ts/v55/select.py")},
        "runtime_seconds": time.perf_counter() - began,
        "test_records_read": 0,
    }
    write(PROTOCOL / f"selection_{args.backbone}.json", clean(payload))
    top = chosen["grid"][:5]
    print(json.dumps(clean({
        "backbone": args.backbone,
        "selected": chosen["selected"],
        "keep_only": chosen.get("keep_only"),
        "cap": cap["cap"], "anchor": cap["anchor"],
        "leader": chosen["leader"],
        "feasible_settings": chosen["feasible_settings"],
        "top5": [{"k": r["k"], "beta": r["beta"],
                  "lam": ("inf" if r["lam_is_inf"] else r["lam"]),
                  "lopo_mase": round(r["lopo_mase"], 5),
                  "hir": round(r["conditional_hir"], 4),
                  "ir": round(r["intervention_rate"], 4)} for r in top],
        "episodes": len(catalogs)}), indent=1))


if __name__ == "__main__":
    main()
