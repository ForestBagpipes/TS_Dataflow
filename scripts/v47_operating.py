#!/usr/bin/env python3
"""The operating point as the penalty strength is walked over its grid.

The neighbourhood size stays at the value the selection froze.  Only the
penalty moves, and the point of the table is what moves with it: the share of
requests on which an action runs changes a great deal, and the share of
executed actions that raise the loss changes very little.  That separation is
what the paper claims about the rule, so it is measured rather than asserted.

Every row post-processes the scores of the same stored prediction cache.  No
threshold is selected here, and the row the paper reports is the frozen one.
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
    parser.add_argument("--bins", type=int, default=5)
    args = parser.parse_args()

    began = time.perf_counter()
    frozen = json.loads(
        (ROOT / f"results/v47/protocol/selection_{args.backbone}.json").read_text())
    config = SEL.frozen_config(frozen)
    if config is None:
        raise SystemExit(f"selection for {args.backbone} is KEEP-only; "
                         "no frozen (k, beta) exists to analyse")
    k, beta_frozen = config

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(C.load_catalog(ROOT, name.strip(), args.backbone))
    eval_catalogs = C.load_catalog(ROOT, args.block, args.backbone)
    blocks = SEL.blocks_of()
    bank = SEL.Bank(bank_catalogs, blocks=blocks)
    queries = SEL.Queries(eval_catalogs, blocks=blocks)
    D = SEL.distance_matrices(bank, queries, lopo=False)

    points = {}
    for beta in SEL.BETA_GRID:
        scores = SEL.score_grid(bank, queries, D, k, beta)
        out = SEL.outcomes(queries, SEL.decide(queries, scores))
        points[f"{beta:g}"] = {
            "beta": float(beta),
            "frozen": abs(beta - beta_frozen) < 1e-12,
            "mase": SEL.source_macro(queries, out["mase"]),
            "intervention_rate": out["intervention_rate"],
            "conditional_hir": out["conditional_hir"],
            "harmful_loss": out["harmful_loss"],
            "beneficial_precision": out["beneficial_precision"],
        }

    # The score orders actions; whether that order agrees with the sign of the
    # realised utility is what the bins below check.
    scores = SEL.score_grid(bank, queries, D, k, beta_frozen)
    values, utilities = [], []
    for action in SEL.NONREF:
        ok = queries.legal[action] & np.isfinite(queries.utility[action]) \
            & np.isfinite(scores[action])
        values.append(scores[action][ok])
        utilities.append(queries.utility[action][ok])
    values = np.concatenate(values)
    utilities = np.concatenate(utilities)
    order = np.argsort(values, kind="stable")
    chunks = np.array_split(order, args.bins)
    rng = np.random.default_rng(101)
    bins = []
    for i, idx in enumerate(chunks, start=1):
        sample = utilities[idx]
        draws = np.array([sample[rng.integers(0, len(sample), len(sample))].mean()
                          for _ in range(2000)]) if len(sample) else np.zeros(1)
        bins.append({
            "bin": i, "pairs": int(len(idx)),
            "score_low": float(values[idx].min()) if len(idx) else None,
            "score_high": float(values[idx].max()) if len(idx) else None,
            "mean_utility": float(sample.mean()) if len(sample) else None,
            "ci_low": float(np.percentile(draws, 2.5)),
            "ci_high": float(np.percentile(draws, 97.5)),
        })
    positive = values > 0
    payload = {
        "stage": "v47-operating-points",
        "backbone": args.backbone, "block": args.block,
        "frozen": {"k": k, "beta": beta_frozen},
        "points": points,
        "score_bins": bins,
        "sign_agreement": float(np.mean((values > 0) == (utilities > 0))),
        "mean_utility_positive_score": float(utilities[positive].mean()) if positive.any() else None,
        "mean_utility_negative_score": float(utilities[~positive].mean()) if (~positive).any() else None,
        "pairs": int(len(values)),
        "runtime_seconds": time.perf_counter() - began,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"operating_{args.block}_{args.backbone}.json").write_text(
        json.dumps(payload, indent=1) + "\n")
    print(json.dumps({k2: v for k2, v in payload.items() if k2 != "score_bins"}, indent=1))


if __name__ == "__main__":
    main()
