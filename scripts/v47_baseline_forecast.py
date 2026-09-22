#!/usr/bin/env python3
"""Forecast a baseline's repaired inputs with a frozen backbone.

Takes a candidate archive keyed ``block|episode`` holding one repaired target
channel per evaluation episode, runs the frozen backbone on it, and scores the
forecast with the same denominators every other row in the paper uses.  A
method that returns a repaired input intervenes on every incomplete request by
construction, so its intervention rate is one and its harmful rate is measured
against the reference forecast of the same backbone.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BASELINES = ROOT / "scripts/v431_baselines"
REPLAY = ROOT / "results/v47/replay"
OUT = ROOT / "results/v47/baselines"


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", default="saits")
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--block", default="test")
    args = parser.parse_args()

    began = time.perf_counter()
    candidates = OUT / args.method / "candidates.npz"
    if not candidates.exists():
        raise SystemExit(f"missing candidate archive {candidates}")
    rows = json.loads((REPLAY / "inputs" / f"{args.block}.json").read_text())["rows"]
    run_dir = OUT / f"{args.method}_{args.block}_{args.backbone}"
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(BASELINES))
    import worker as baseline_worker

    records: dict[str, dict] = {}
    missing: list[str] = []
    predictions: dict[str, np.ndarray] = {}

    with (ROOT / "locks/gpu.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        active = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
            text=True).strip()
        if active:
            raise RuntimeError("GPU has active processes; refusing to interfere")
        import torch
        torch.manual_seed(101)
        np.random.seed(101)
        if args.backbone == "bolt":
            model = baseline_worker.Bolt(run_dir)
        elif args.backbone == "timesfm":
            model = baseline_worker.TimesFM(run_dir)
        else:
            sys.path.insert(0, str(ROOT / "scripts"))
            from v46_chronos2 import Chronos2
            model = Chronos2(run_dir)

        with np.load(candidates, allow_pickle=False) as store, \
                np.load(REPLAY / "inputs" / f"{args.block}.npz", allow_pickle=False) as inputs:
            for index, row in enumerate(rows):
                key = row["episode"]
                name = f"{args.block}|{key}"
                if name not in store.files:
                    missing.append(key)
                    continue
                value = np.asarray(store[name], dtype=np.float64)
                horizon = int(row["horizon"])
                prediction = model.forecast(value[None, :, None], horizon)[0, :, 0]
                if not np.isfinite(prediction).all():
                    missing.append(key)
                    continue
                future = inputs[f"{key}|future"]
                error = prediction - future
                mae = float(np.mean(np.abs(error)))
                mse = float(np.mean(error ** 2))
                records[key] = {
                    "mae": mae, "mse": mse,
                    "mase": mae / row["mase_scale"] if row["mase_scale"] else None,
                    "rmsse": (float(np.sqrt(mse / row["rmsse_scale"]))
                              if row["rmsse_scale"] else None),
                    "source": row["source"], "parent": row["parent"],
                    "horizon": row["horizon"], "pattern": row["pattern"],
                    "severity": row["severity"],
                }
                predictions[key] = prediction.astype(np.float64)
                if index % 200 == 0:
                    print(json.dumps({"done": index, "total": len(rows),
                                      "elapsed": time.perf_counter() - began}), flush=True)

    with (run_dir / "predictions.npz").open("wb") as handle:
        np.savez(handle, **predictions)
    raw_files = sorted((run_dir / "raw").glob("call_*.npz"))
    raw_calls = len(raw_files)
    for path in raw_files:
        path.unlink()
    (run_dir / "raw").rmdir()
    write(run_dir / "records.json", {
        "stage": "v46-baseline-forecast", "method": args.method,
        "backbone": args.backbone, "block": args.block,
        "scored": len(records), "missing": len(missing), "missing_episodes": missing[:50],
        "backbone_calls": raw_calls,
        "raw_call_dumps": "removed after the run; predictions.npz is the retained artefact",
        "records": records,
        "runtime_seconds": time.perf_counter() - began,
    })
    print(json.dumps({"method": args.method, "backbone": args.backbone,
                      "block": args.block, "scored": len(records),
                      "missing": len(missing),
                      "runtime_seconds": time.perf_counter() - began}, indent=1))


if __name__ == "__main__":
    main()
