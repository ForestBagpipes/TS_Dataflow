#!/usr/bin/env python3
"""Is the selected configuration a property of the rule or of this bank?

The neighbourhood size and the penalty strength are chosen once on the replay
bank.  This stage repeats that choice on parent-level subsamples of the same
bank and records what the rule picks each time, together with what the pick
would have produced on the evaluation block.

The evaluation figures here are diagnostics.  Nothing in the paper is selected
from them, and the reported configuration stays the one the full bank chooses.
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
OUT = ROOT / "results/v47/ablations"
FRACTIONS = (0.5, 0.75)
SEEDS = (1, 2, 3)


def subsample(catalogs, fraction: float, seed: int):
    parents = sorted({c.parent for c in catalogs})
    rng = np.random.default_rng(seed)
    keep = set(rng.choice(parents, max(2, int(round(len(parents) * fraction))),
                          replace=False).tolist())
    return [c for c in catalogs if c.parent in keep]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--block", default="test")
    args = parser.parse_args()

    began = time.perf_counter()
    blocks = SEL.blocks_of()
    bank_catalogs = C.load_catalog(ROOT, "bankx", args.backbone)
    eval_catalogs = C.load_catalog(ROOT, args.block, args.backbone)
    queries = SEL.Queries(eval_catalogs, blocks=blocks)

    frozen = json.loads(
        (ROOT / f"results/v47/protocol/selection_{args.backbone}.json").read_text())
    reference = frozen["selection"]["selected"]

    full_bank = SEL.Bank(bank_catalogs, blocks=blocks)
    eval_distance = SEL.distance_matrices(full_bank, queries, lopo=False)

    def evaluate(k: int, beta: float) -> dict:
        scores = SEL.score_grid(full_bank, queries, eval_distance, k, beta)
        out = SEL.outcomes(queries, SEL.decide(queries, scores))
        return {"mase": SEL.source_macro(queries, out["mase"]),
                "intervention_rate": out["intervention_rate"],
                "conditional_hir": out["conditional_hir"]}

    rows = [{"fraction": 1.0, "seed": None, "k": int(reference["k"]),
             "beta": float(reference["beta"]),
             **evaluate(int(reference["k"]), float(reference["beta"]))}]
    for fraction in FRACTIONS:
        for seed in SEEDS:
            subset = subsample(bank_catalogs, fraction, seed)
            bank = SEL.Bank(subset, blocks=blocks)
            bank_queries = SEL.Queries(subset, blocks=blocks)
            cap = SEL.harm_cap(bank, bank_queries)
            chosen = SEL.select_hyperparameters(bank, bank_queries, cap=cap["cap"])
            k = int(chosen["selected"]["k"])
            beta = float(chosen["selected"]["beta"])
            rows.append({"fraction": fraction, "seed": seed, "k": k, "beta": beta,
                         "parents": int(len({c.parent for c in subset})),
                         "same_as_frozen": bool(k == int(reference["k"])
                                                and beta == float(reference["beta"])),
                         **evaluate(k, beta)})

    frozen_mase = rows[0]["mase"]
    resampled = [r for r in rows if r["seed"] is not None]
    payload = {
        "stage": "v46-selection-stability", "backbone": args.backbone, "block": args.block,
        "frozen": reference, "rows": rows,
        "same_choice_share": float(np.mean([r["same_as_frozen"] for r in resampled])),
        "mase_spread": float(max(r["mase"] for r in resampled)
                             - min(r["mase"] for r in resampled)),
        "worst_gap_to_frozen": float(max(r["mase"] - frozen_mase for r in resampled)),
        "note": "the evaluation figures are diagnostics and select nothing",
        "runtime_seconds": time.perf_counter() - began,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"selection_stability_{args.block}_{args.backbone}.json").write_text(
        json.dumps(payload, indent=1) + "\n")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in ("rows", "note")}, indent=1))


if __name__ == "__main__":
    main()
