#!/usr/bin/env python3
"""TRAIN-only numerical equivalence and throughput check before batching."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts/v431_baselines"))
import worker
sys.path.insert(0, str(ROOT / "scripts"))
from v46_chronos2 import Chronos2

def configure(model, name, batch):
    if name == "timesfm":
        import timesfm
        model.model.compile(timesfm.ForecastConfig(max_context=512, max_horizon=192,
            normalize_inputs=True, per_core_batch_size=batch,
            use_continuous_quantile_head=True, force_flip_invariance=True,
            infer_is_positive=True, fix_quantile_crossing=True))
    elif name == "chronos2":
        original = getattr(model, "_unbatched_predict", model.pipeline.predict)
        model._unbatched_predict = original
        def predict(*args, **kwargs):
            kwargs["batch_size"] = batch
            return original(*args, **kwargs)
        model.pipeline.predict = predict

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", required=True, choices=["bolt", "timesfm", "chronos2"])
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    directory = ROOT / "results/v47_batch_probe" / args.backbone
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "raw").mkdir()
    path = ROOT / "results/v47_verified_pilot/replay/inputs/bankx.npz"
    manifest = json.loads(path.with_suffix(".json").read_text())
    # A fixed source-balanced roster; no losses or future arrays are opened.
    selected = []
    counts = {}
    for row in manifest["rows"]:
        source = row["source"]
        if counts.get(source, 0) < 4:
            selected.append(row)
            counts[source] = counts.get(source, 0) + 1
    with np.load(path, allow_pickle=False) as archive:
        values = np.stack([archive[row["episode"] + "|reference"] for row in selected])
    # Tolerances fixed by inference dtype, before outputs are compared.
    tolerance = 0.01 if args.backbone == "bolt" else 0.0001
    with (ROOT / "locks/gpu.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        constructor = dict(bolt=worker.Bolt, timesfm=worker.TimesFM, chronos2=Chronos2)[args.backbone]
        model = constructor(directory)
        results = []
        for horizon in (96, 192):
            configure(model, args.backbone, 1)
            start = time.perf_counter()
            singles = np.stack([model.forecast(value[None, :, None], horizon)[0, :, 0] for value in values])
            single_seconds = time.perf_counter() - start
            model.cache.clear()
            configure(model, args.backbone, args.batch_size)
            start = time.perf_counter()
            batch = model.forecast(values[:, :, None], horizon)[:, :, 0]
            batch_seconds = time.perf_counter() - start
            scale = np.nanstd(values, axis=1)
            scale = np.maximum(scale, 1e-8)
            error = float(np.max(np.abs(batch - singles) / scale[:, None]))
            results.append(dict(horizon=horizon, max_context_scaled_error=error,
                                tolerance=tolerance, passed=error <= tolerance,
                                single_seconds=single_seconds, batch_seconds=batch_seconds))
        payload = dict(backbone=args.backbone, identity=model.identity, batch_size=args.batch_size,
                       episodes=[r["episode"] for r in selected], results=results,
                       status="passed" if all(r["passed"] for r in results) else "failed",
                       input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       future_arrays_read=0, test_records_read=0)
        (directory / "report.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        if payload["status"] != "passed":
            raise SystemExit(1)
if __name__ == "__main__":
    main()
