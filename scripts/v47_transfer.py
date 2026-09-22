#!/usr/bin/env python3
"""Does the local transfer assumption hold?

Section 3.2 rests on one empirical assumption: requests whose states are close
in the state space have similar action utilities, so the utility of an action on
a new request can be estimated from the same-action neighbourhood of its state.
Nothing in the paper tested it directly, and it is the assumption the whole
decision layer stands on.

The test is the one the assumption implies.  For every request and every
admissible non-reference action, record how far the retrieved neighbourhood
actually was, what the neighbourhood estimated, and what the action then did.
Bin the pairs by neighbourhood distance.  If the assumption holds, the bins
with the closer neighbourhoods carry the smaller estimation error and the
better sign agreement; if it does not, distance tells us nothing and the bins
look alike.

Nothing here selects anything.  The frozen configuration is read from the
selection file and the whole table is post-processing of the stored cache.
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
    k = int(frozen["selection"]["selected"]["k"])

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(C.load_catalog(ROOT, name.strip(), args.backbone))
    eval_catalogs = C.load_catalog(ROOT, args.block, args.backbone)
    blocks = SEL.blocks_of()
    bank = SEL.Bank(bank_catalogs, blocks=blocks)
    queries = SEL.Queries(eval_catalogs, blocks=blocks)
    D = SEL.distance_matrices(bank, queries, lopo=False)

    distance, estimate, realised, action_of = [], [], [], []
    for action in SEL.NONREF:
        b = bank.per[action]
        if len(b.g) == 0:
            continue
        d = D[action]
        ke = min(k, d.shape[1])
        idx = np.argpartition(d, ke - 1, axis=1)[:, :ke]
        dd = np.take_along_axis(d, idx, axis=1)
        gg = b.g[idx]
        finite = np.isfinite(dd).all(1)
        # The same weighting the decision uses, so the estimate in this table is
        # the estimate the rule acted on and not a different quantity.
        tau = np.median(np.where(np.isfinite(dd), dd, 0.0), axis=1)[:, None] + SEL.TAU_EPSILON
        w = np.exp(-np.where(np.isfinite(dd), dd, 0.0) / tau)
        mu = (w * gg).sum(1) / np.maximum(w.sum(1), 1e-12)
        ok = (finite & queries.legal[action] & np.isfinite(queries.utility[action]))
        if not ok.any():
            continue
        distance.append(dd[ok].mean(1))
        estimate.append(mu[ok])
        realised.append(queries.utility[action][ok])
        action_of.extend([action] * int(ok.sum()))

    distance = np.concatenate(distance)
    estimate = np.concatenate(estimate)
    realised = np.concatenate(realised)

    order = np.argsort(distance, kind="stable")
    chunks = np.array_split(order, args.bins)
    bins = []
    for i, part in enumerate(chunks, start=1):
        d = distance[part]
        err = np.abs(estimate[part] - realised[part])
        bins.append({
            "bin": i,
            "pairs": int(part.size),
            "distance_mean": float(d.mean()),
            "distance_low": float(d.min()),
            "distance_high": float(d.max()),
            "abs_error": float(err.mean()),
            "sign_agreement": float(np.mean((estimate[part] > 0) == (realised[part] > 0))),
            "realised_mean": float(realised[part].mean()),
        })

    # One number for the whole table: does distance rank the estimation error?
    rank_d = np.argsort(np.argsort(distance)).astype(float)
    rank_e = np.argsort(np.argsort(np.abs(estimate - realised))).astype(float)
    rank_d -= rank_d.mean()
    rank_e -= rank_e.mean()
    denom = float(np.sqrt((rank_d @ rank_d) * (rank_e @ rank_e)))
    spearman = float(rank_d @ rank_e / denom) if denom > 1e-12 else float("nan")

    payload = {
        "stage": "v47-local-transfer",
        "backbone": args.backbone, "block": args.block,
        "frozen": {"k": k},
        "note": "post-processing of the stored cache; the frozen configuration is "
                "reused and nothing is selected here",
        "pairs": int(distance.size),
        "bins": bins,
        "spearman_distance_vs_error": spearman,
        "runtime_seconds": time.perf_counter() - began,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"transfer_{args.block}_{args.backbone}.json").write_text(
        json.dumps(payload, indent=1) + "\n")
    print(json.dumps(payload, indent=1))


if __name__ == "__main__":
    main()
