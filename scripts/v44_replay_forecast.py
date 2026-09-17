#!/usr/bin/env python3
"""v4.4 Stage C -- frozen TSFM forecast stage (GPU).

Takes the candidate inputs produced by stage A (CPU actions) and stage B
(TS-ICL actions) and runs the frozen backbone on every *distinct* candidate
input.  Identical inputs are deduplicated by array hash and are forecast once;
the alias is recorded rather than hidden, so the bank can tell "this action
changed nothing" apart from "this action was never run".

The model classes are imported from the frozen r5 baseline worker, so the
weight hashes, dtype, quantile rule and TimesFM ``ForecastConfig`` are exactly
the ones the project already validated.  No parameter of the backbone is
touched.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

import numpy as np

from introact_ts.v44 import protocol as P
from introact_ts.v44.hashing import array_hash

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v44/replay"
BASELINES = ROOT / "scripts/v431_baselines"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                              allow_nan=False) + "\n")
    tmp.replace(path)


def load_candidate(store, tsicl_store, key: str, action: str) -> np.ndarray | None:
    if action in ("KEEP", "FFILL", "CONTEXT_RIDGE"):
        name = f"{key}|{action}"
        return store[name] if name in store.files else None
    name = f"{key}|{action}"
    return tsicl_store[name] if name in tsicl_store.files else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--block", default="replay_fit",
                        choices=["replay_fit", "gate", "train_eval"])
    parser.add_argument("--backbone", default="bolt",
                        choices=list(P.DEV_BACKBONES))
    parser.add_argument("--limit", type=int, default=0,
                        help="probe only the first N episodes (diagnostic runs)")
    args = parser.parse_args()

    root = Path(args.root)
    run_dir = OUT / "forecast" / args.block / args.backbone
    run_dir.mkdir(parents=True, exist_ok=True)
    npz_path = run_dir / "predictions.npz"
    status_path = run_dir / "status.json"
    if npz_path.exists() or status_path.exists():
        raise SystemExit(f"refusing to overwrite existing forecast output {npz_path}")
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)

    manifest = json.loads((OUT / "inputs" / f"{args.block}.json").read_text())
    rows = manifest["rows"]
    if args.limit:
        rows = rows[: args.limit]
    tsicl_path = OUT / "tsicl" / f"{args.block}.npz"
    if not tsicl_path.exists():
        raise SystemExit("TS-ICL stage output missing; run stage B first")

    sys.path.insert(0, str(BASELINES))
    import worker as baseline_worker

    arrays: dict[str, np.ndarray] = {}
    calls: list[dict] = []
    runtime_of: dict[tuple[str, int], float] = {}
    failures: list[dict] = []
    alias: list[dict] = []
    began = time.perf_counter()

    with np.load(OUT / "inputs" / f"{args.block}.npz", allow_pickle=False) as store, \
            np.load(tsicl_path, allow_pickle=False) as tsicl_store:
        # Deduplicate every candidate input across the whole block.
        unique: dict[str, np.ndarray] = {}
        plan: list[dict] = []
        for row in rows:
            key = row["episode"]
            horizon = row["horizon"]
            for action in P.ACTIONS:
                meta = row["candidates"].get(action)
                if action in ("SINGLE_TSICL", "MULTI_TSICL"):
                    available = f"{key}|{action}" in tsicl_store.files
                    meta = {"applicable": available,
                            "reason": None if available else "tsicl stage produced no output"}
                if meta is None or not meta["applicable"]:
                    plan.append({"episode": key, "action": action,
                                 "applicable": False,
                                 "reason": (meta or {}).get("reason", "no candidate"),
                                 "input_hash": None})
                    continue
                value = load_candidate(store, tsicl_store, key, action)
                if value is None:
                    plan.append({"episode": key, "action": action,
                                 "applicable": False,
                                 "reason": "candidate array missing",
                                 "input_hash": None})
                    continue
                digest = array_hash(value)
                unique.setdefault(digest, value)
                plan.append({"episode": key, "action": action, "applicable": True,
                             "reason": None, "input_hash": digest,
                             "horizon": horizon})

        print(json.dumps({"unique_inputs": len(unique), "plan_rows": len(plan)}),
              flush=True)

        with (root / "locks/gpu.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            active = subprocess.check_output(
                ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
                text=True).strip()
            if active:
                raise RuntimeError("GPU has active processes; refusing to interfere")
            import torch
            torch.manual_seed(101)
            np.random.seed(101)
            torch.cuda.reset_peak_memory_stats()
            tick = time.perf_counter()
            model = (baseline_worker.Bolt(run_dir) if args.backbone == "bolt"
                     else baseline_worker.TimesFM(run_dir))
            torch.cuda.synchronize()
            load_seconds = time.perf_counter() - tick
            identity = dict(model.identity)
            identity["load_seconds"] = load_seconds
            identity["load_peak_gpu_bytes"] = int(torch.cuda.max_memory_allocated())

            try:
                order = sorted(unique)
                for index, digest in enumerate(order):
                    value = unique[digest]
                    # Every candidate needs a horizon; the same input string can
                    # only appear at one horizon because the mask hash binds it.
                    horizons = sorted({p["horizon"] for p in plan
                                       if p.get("input_hash") == digest})
                    for horizon in horizons:
                        tick = time.perf_counter()
                        try:
                            prediction = model.forecast(value[None, :, None], horizon)[0, :, 0]
                            runtime = time.perf_counter() - tick
                            if prediction.shape != (horizon,):
                                raise RuntimeError(f"unexpected shape {prediction.shape}")
                            if not np.isfinite(prediction).all():
                                raise RuntimeError("non-finite forecast")
                            arrays[f"{digest}|h{horizon}"] = np.asarray(
                                prediction, dtype=np.float64)
                            runtime_of[(digest, horizon)] = runtime
                            calls.append({"input_hash": digest, "horizon": horizon,
                                          "runtime_seconds": runtime})
                        except Exception as exc:  # noqa: BLE001 - recorded
                            failures.append({"input_hash": digest, "horizon": horizon,
                                             "reason": f"{type(exc).__name__}: {exc}"})
                    if index % 200 == 0:
                        print(json.dumps({"done": index, "total": len(order),
                                          "elapsed": time.perf_counter() - began}),
                              flush=True)
            except BaseException:
                traceback.print_exc()
                write(status_path, {"status": "failed", "calls": calls,
                                    "failures": failures})
                raise

        for item in plan:
            if not item["applicable"]:
                continue
            name = f"{item['input_hash']}|h{item['horizon']}"
            if name in arrays:
                item["prediction_hash"] = array_hash(arrays[name])
                item["runtime_seconds"] = runtime_of.get(
                    (item["input_hash"], item["horizon"]))
            else:
                item["applicable"] = False
                item["reason"] = "backbone produced no prediction"

        # Aliases: two actions of one episode that share a model input.
        grouped: dict[tuple[str, int], dict[str, str]] = {}
        for item in plan:
            if not item["applicable"]:
                continue
            bucket = grouped.setdefault((item["episode"], item["horizon"]), {})
            bucket.setdefault(item["input_hash"], item["action"])
        for item in plan:
            if not item["applicable"]:
                continue
            owner = grouped[(item["episode"], item["horizon"])][item["input_hash"]]
            item["alias_of"] = None if owner == item["action"] else owner
            if item["alias_of"]:
                alias.append({"episode": item["episode"], "action": item["action"],
                              "alias_of": owner})

    with npz_path.open("wb") as handle:
        np.savez(handle, **arrays)

    status = {
        "stage": "v44-replay-forecast-C",
        "block": args.block,
        "backbone": args.backbone,
        "status": "completed",
        "identity": identity,
        "unique_inputs": len(unique),
        "unique_predictions": len(arrays),
        "plan_rows": len(plan),
        "applicable_rows": sum(1 for p in plan if p["applicable"]),
        "failed_rows": sum(1 for p in plan if not p["applicable"]),
        "failures": failures,
        "alias_count": len(alias),
        "aliases": alias,
        "per_action": dict(sorted(Counter(
            p["action"] for p in plan if p["applicable"]).items())),
        "unsupported_reasons": dict(sorted(Counter(
            p["reason"] for p in plan if not p["applicable"]).items())),
        "runtime_seconds": time.perf_counter() - began,
        "load_seconds": load_seconds,
        "call_seconds_total": float(sum(c["runtime_seconds"] for c in calls)),
        "call_seconds_mean": float(np.mean([c["runtime_seconds"] for c in calls]))
        if calls else None,
        "call_seconds_p95": float(np.percentile(
            [c["runtime_seconds"] for c in calls], 95)) if calls else None,
        "call_seconds_max": float(max((c["runtime_seconds"] for c in calls),
                                      default=0.0)),
        "predictions_npz": str(npz_path.relative_to(root)),
        "predictions_sha256": sha(npz_path),
        "plan": plan,
        "source_hashes": {
            "scripts/v431_baselines/worker.py": sha(root / "scripts/v431_baselines/worker.py"),
            "scripts/v44_replay_forecast.py": sha(Path(__file__)),
        },
        "heldout_labels_read": 0,
    }
    write(status_path, status)
    print(json.dumps({k: v for k, v in status.items()
                      if k not in ("plan", "aliases")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
