#!/usr/bin/env python3
"""Per-request cost, measured rather than asserted.

Three components are timed separately because they are paid at different
points and by different hardware.  Candidate materialisation and the retrieval
that scores them are CPU work done before the decision; the forecasting call is
the GPU work the deployed system already pays for the reference forecast.  The
call times come from the runtimes the forecast stage recorded, and the
retrieval time is measured here on the same requests.
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
OUT = ROOT / "results/v46/cost_audit"


def percentiles(values: list[float]) -> dict:
    if not values:
        return {}
    array = np.asarray(values, dtype=np.float64) * 1000.0
    return {"mean_ms": float(array.mean()),
            "p95_ms": float(np.percentile(array, 95)),
            "max_ms": float(array.max()), "n": int(array.size)}


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

    bank_catalogs = C.load_catalog(ROOT, "bank", args.backbone)
    eval_catalogs = C.load_catalog(ROOT, args.block, args.backbone)
    blocks = SEL.blocks_of()
    bank = SEL.Bank(bank_catalogs, blocks=blocks)

    # One request at a time, which is the deployment shape; batching would
    # report a throughput number and call it a latency.
    retrieval = []
    for catalog in eval_catalogs:
        queries = SEL.Queries([catalog], blocks=blocks)
        tick = time.perf_counter()
        distances = SEL.distance_matrices(bank, queries, lopo=False)
        scores = SEL.score_grid(bank, queries, distances, k, beta)
        SEL.decide(queries, scores)
        retrieval.append(time.perf_counter() - tick)

    # The backbone call time comes from the stage that made the calls.
    status = json.loads(
        (ROOT / f"results/v46/replay/forecast/{args.block}/{args.backbone}/status.json").read_text())
    call = {}
    if status.get("call_seconds_mean") is not None:
        call = {"mean_ms": status["call_seconds_mean"] * 1000.0,
                "p95_ms": status["call_seconds_p95"] * 1000.0,
                "max_ms": status["call_seconds_max"] * 1000.0,
                "n": status.get("unique_predictions", status.get("unique_inputs"))}

    payload = {
        "stage": "v46-latency", "backbone": args.backbone, "block": args.block,
        "frozen": {"k": k, "beta": beta},
        "bank_records": sum(bank.support().values()),
        "retrieval_per_request": percentiles(retrieval),
        "backbone_call": call,
        "note": "retrieval is measured one request at a time on this machine; the "
                "backbone call time is the runtime the forecast stage recorded for "
                "the same block",
        "runtime_seconds": time.perf_counter() - began,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"latency_{args.block}_{args.backbone}.json").write_text(
        json.dumps(payload, indent=1) + "\n")
    print(json.dumps({k2: v for k2, v in payload.items() if k2 != "note"}, indent=1))


if __name__ == "__main__":
    main()
