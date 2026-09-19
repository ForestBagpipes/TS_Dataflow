#!/usr/bin/env python3
"""Predicted score against realised utility, binned.

The conservative score orders actions.  This stage asks whether the order it
produces agrees in sign with what the action actually did to the forecast, which
is the only property the decision rule relies on.  It is not a calibration
check and no claim is made that the score is on the scale of the utility.

Every admissible non-reference action of every evaluation request contributes
one pair.  Bins are quantiles of the score, and the interval of each bin comes
from a bootstrap that resamples parents, because requests from one parent are
not independent.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v46 import select as SEL

ROOT = Path(__file__).resolve().parent.parent
C.REPLAY = "results/v46/replay"
OUT = ROOT / "results/v46/diagnostics"
BINS = 8
RESAMPLES = 1000


def clustered_interval(values: np.ndarray, parents: np.ndarray, *,
                       seed: int = 101) -> tuple[float, float, float]:
    """Mean of ``values`` with a 95% interval that resamples whole parents."""
    rng = np.random.default_rng(seed)
    keys = np.unique(parents)
    index = {key: np.where(parents == key)[0] for key in keys}
    point = float(values.mean())
    draws = np.empty(RESAMPLES)
    for r in range(RESAMPLES):
        pick = rng.integers(0, len(keys), len(keys))
        taken = np.concatenate([index[keys[j]] for j in pick])
        draws[r] = values[taken].mean()
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return point, float(lo), float(hi)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--block", default="test")
    args = parser.parse_args()

    began = time.perf_counter()
    frozen = json.loads(
        (ROOT / f"results/v46/protocol/selection_{args.backbone}.json").read_text())
    k = int(frozen["selection"]["selected"]["k"])
    beta = float(frozen["selection"]["selected"]["beta"])

    blocks = SEL.blocks_of()
    bank = SEL.Bank(C.load_catalog(ROOT, "bank", args.backbone), blocks=blocks)
    queries = SEL.Queries(C.load_catalog(ROOT, args.block, args.backbone), blocks=blocks)
    distances = SEL.distance_matrices(bank, queries, lopo=False)
    scores = SEL.score_grid(bank, queries, distances, k, beta)

    score_values, utility_values, parent_values, action_values = [], [], [], []
    for action in SEL.NONREF:
        legal = queries.legal[action]
        s = scores[action]
        u = queries.utility[action]
        take = legal & np.isfinite(s) & np.isfinite(u)
        score_values.append(s[take])
        utility_values.append(u[take])
        parent_values.append(queries.parent[take])
        action_values.extend([action] * int(take.sum()))
    s = np.concatenate(score_values)
    u = np.concatenate(utility_values)
    p = np.concatenate(parent_values)

    edges = np.quantile(s, np.linspace(0.0, 1.0, BINS + 1))
    edges[0] -= 1e-9
    edges[-1] += 1e-9
    rows = []
    for i in range(BINS):
        take = (s > edges[i]) & (s <= edges[i + 1])
        if take.sum() < 10:
            continue
        mean_u, lo, hi = clustered_interval(u[take], p[take])
        rows.append({"bin": i + 1,
                     "score_low": float(edges[i]), "score_high": float(edges[i + 1]),
                     "score_mid": float(np.median(s[take])),
                     "utility_mean": mean_u, "ci_low": lo, "ci_high": hi,
                     "n": int(take.sum()),
                     "positive_share": float((u[take] > 0).mean())})

    positive = s > 0
    payload = {
        "stage": "v46-score-utility", "backbone": args.backbone, "block": args.block,
        "frozen": {"k": k, "beta": beta},
        "pairs": int(s.size), "parents": int(len(np.unique(p))),
        "bins": rows,
        "sign_agreement": float(((s > 0) == (u > 0)).mean()),
        "mean_utility_positive_score": float(u[positive].mean()) if positive.any() else None,
        "mean_utility_negative_score": float(u[~positive].mean()) if (~positive).any() else None,
        "spearman": float(np.corrcoef(np.argsort(np.argsort(s)),
                                      np.argsort(np.argsort(u)))[0, 1]),
        "note": "sign agreement only; the score is not claimed to be on the utility scale",
        "runtime_seconds": time.perf_counter() - began,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"score_utility_{args.block}_{args.backbone}.json").write_text(
        json.dumps(payload, indent=1) + "\n")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in ("bins", "note")}, indent=1))


if __name__ == "__main__":
    main()
