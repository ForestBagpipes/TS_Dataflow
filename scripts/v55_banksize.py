#!/usr/bin/env python3
"""v55 replay bank size ablation.

The bank is subsampled by parent, keeping every action and severity of each
parent that survives, so the only thing that changes is how much history the
pooled estimate can draw on.  The frozen ``(k, beta, lam)`` is held fixed,
which is what makes the row a sensitivity check on support rather than a
second selection.  Writes only under ``results/v55/ablations/``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v47 import select as SEL
from introact_ts.v55 import select as V55

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v47_banksize import subsample
from v54_common import OUT, ROOT, load_catalogs, write

ABL_OUT = ROOT / "results/v55" / "ablations"
FRACTIONS = (0.25, 0.50, 1.00)
SEEDS = (1, 2, 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--block", default="test")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    freeze = ROOT / "results/v55/protocol" / f"selection_{args.backbone}.json"
    if not freeze.exists():
        raise SystemExit(f"v55 configuration is not frozen for {args.backbone}: "
                         f"{freeze} missing; run scripts/v55_select.py first")
    frozen = json.loads(freeze.read_text())
    config = V55.frozen_config(frozen)
    if config is None:
        raise SystemExit(f"selection for {args.backbone} is KEEP-only; "
                         "no frozen (k, beta) exists to evaluate")
    k, beta, lam = config

    bank_catalogs = load_catalogs(root, "bankx", args.backbone)
    eval_catalogs = load_catalogs(root, args.block, args.backbone)
    blocks = SEL.blocks_of()
    queries = SEL.Queries(eval_catalogs, blocks=blocks)

    rows = []
    for fraction in FRACTIONS:
        seeds = SEEDS if fraction < 1.0 else (SEEDS[0],)
        runs = []
        for seed in seeds:
            subset = subsample(bank_catalogs, fraction, seed)
            bank = SEL.Bank(subset, blocks=blocks)
            D = SEL.distance_matrices(bank, queries, lopo=False)
            moments = V55.local_moments(bank, queries, D, k)
            means = V55.source_action_means(bank)
            selected = V55.decide(queries, V55.scores_from_moments(
                moments, means, queries, beta, lam))
            out = SEL.outcomes(queries, selected)
            runs.append({
                "seed": seed,
                "parents": len({c.parent for c in subset}),
                "episodes": len(subset),
                "mase": SEL.source_macro(queries, out["mase"]),
                "intervention_rate": out["intervention_rate"],
                "conditional_hir": out["conditional_hir"],
                "harmful_loss": out["harmful_loss"],
            })
        rows.append({
            "fraction": fraction,
            "runs": runs,
            "mase": float(np.mean([r["mase"] for r in runs])),
            "intervention_rate": float(np.mean([r["intervention_rate"] for r in runs])),
            "conditional_hir": float(np.mean([r["conditional_hir"] for r in runs])),
            "harmful_loss": float(np.mean([r["harmful_loss"] for r in runs])),
            "parents": int(np.mean([r["parents"] for r in runs])),
        })
        print(json.dumps(rows[-1] | {"runs": len(runs)}), flush=True)

    payload = {"stage": "v55-bank-size", "backbone": args.backbone,
               "block": args.block,
               "frozen": {"k": k, "beta": beta, "lam": (None if lam == float("inf") else lam)}, "rows": rows,
               "runtime_seconds": time.perf_counter() - began}
    ABL_OUT.mkdir(parents=True, exist_ok=True)
    (ABL_OUT / f"banksize_{args.block}_{args.backbone}.json").write_text(
        json.dumps(payload, indent=1) + "\n")


if __name__ == "__main__":
    main()
