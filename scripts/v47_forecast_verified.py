#!/usr/bin/env python3
"""v4.6 Stage C -- frozen TSFM forecast stage (GPU).

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

from introact_ts.v47_verified import actions as A
from introact_ts.v47_verified import protocol as P
from introact_ts.v44.hashing import array_hash

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v47_verified/replay"
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


def load_candidate(store, tsicl_store, saits_store, key: str,
                   action: str) -> np.ndarray | None:
    name = f"{key}|{action}"
    if action in ("KEEP", "FFILL", "CONTEXT_RIDGE"):
        return store[name] if name in store.files else None
    if action == "SAITS":
        if saits_store is None or name not in saits_store.files:
            return None
        return saits_store[name]
    return tsicl_store[name] if name in tsicl_store.files else None


def configure_batching(model, backbone: str, batch_size: int) -> None:
    """Apply only batching settings that passed the TRAIN-only probe."""
    if backbone == "timesfm":
        import timesfm
        model.model.compile(timesfm.ForecastConfig(
            max_context=512, max_horizon=192, normalize_inputs=True,
            per_core_batch_size=batch_size,
            use_continuous_quantile_head=True, force_flip_invariance=True,
            infer_is_positive=True, fix_quantile_crossing=True))
    elif backbone == "chronos2":
        original = model.pipeline.predict

        def predict(*args, **kwargs):
            kwargs["batch_size"] = batch_size
            return original(*args, **kwargs)

        model.pipeline.predict = predict


def batch_input(values: list[np.ndarray]) -> np.ndarray:
    stacked = np.stack(values)
    if stacked.ndim == 2:
        stacked = stacked[:, :, None]
    if stacked.ndim != 3 or stacked.shape[2] != 1:
        raise ValueError(f"unexpected candidate batch shape {stacked.shape}")
    return stacked


def main() -> None:
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--block", default="bank",
                        choices=["bank", "bankx", "bankx2", "train_eval", "test", "test30", "test50", "test_m2", "test_m3"])
    parser.add_argument("--backbone", default="bolt",
                        choices=list(P.ALL_BACKBONES))
    parser.add_argument("--limit", type=int, default=0,
                        help="probe only the first N episodes (diagnostic runs)")
    parser.add_argument("--output-root", default="results/v47_verified")
    args = parser.parse_args()
    if args.block.startswith("test"):
        raise SystemExit("TEST disabled until TRAIN gate and protocol freeze")
    OUT = Path(args.root) / args.output_root / "replay"

    root = Path(args.root)
    run_dir = OUT / "forecast" / args.block / args.backbone
    run_dir.mkdir(parents=True, exist_ok=True)
    npz_path = run_dir / "predictions.npz"
    status_path = run_dir / "status.json"
    if npz_path.exists() or status_path.exists():
        raise SystemExit(f"refusing to overwrite existing forecast output {npz_path}")
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    write(status_path, {"stage": "v47-verified-forecast", "status": "running",
                        "block": args.block, "backbone": args.backbone,
                        "heldout_labels_read": 0})

    manifest = json.loads((OUT / "inputs" / f"{args.block}.json").read_text())
    if sha(OUT / "inputs" / f"{args.block}.npz") != manifest["inputs_sha256"]:
        raise RuntimeError("Input archive checksum mismatch")
    rows = manifest["rows"]
    if args.limit:
        rows = rows[: args.limit]
    tsicl_path = OUT / "tsicl" / f"{args.block}.npz"
    if not tsicl_path.exists():
        raise SystemExit("TS-ICL stage output missing; run stage B first")

    tsicl_status = json.loads((OUT / "tsicl" / f"{args.block}.json").read_text())
    if tsicl_status.get("status") != "completed" or sha(tsicl_path) != tsicl_status["outputs_sha256"]:
        raise RuntimeError("TS-ICL stage is incomplete or its archive changed")
    sys.path.insert(0, str(BASELINES))
    import worker as baseline_worker

    arrays: dict[str, np.ndarray] = {}
    calls: list[dict] = []
    batch_calls: list[dict] = []
    runtime_of: dict[tuple[str, int], float] = {}
    failures: list[dict] = []
    alias: list[dict] = []
    began = time.perf_counter()

    saits_path = OUT / "saits" / f"{args.block}.npz"
    if not saits_path.exists():
        raise RuntimeError("SAITS archive missing; model failure is not unsupported action")
    saits_store = np.load(saits_path, allow_pickle=False)

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
                    if not available:
                        raise RuntimeError(f"Missing generated candidate: {key}/{action}")
                    meta = {"applicable": available,
                            "reason": None if available else "tsicl stage produced no output"}
                if action == "SAITS":
                    available = (saits_store is not None
                                 and f"{key}|{action}" in saits_store.files)
                    if not available:
                        raise RuntimeError(f"Missing generated candidate: {key}/{action}")
                    meta = {"applicable": available,
                            "reason": None if available else "imputer stage produced no output"}
                if meta is None or not meta["applicable"]:
                    plan.append({"episode": key, "action": action,
                                 "applicable": False,
                                 "reason": (meta or {}).get("reason", "no candidate"),
                                 "input_hash": None})
                    continue
                value = load_candidate(store, tsicl_store, saits_store, key, action)
                if value is None:
                    raise RuntimeError(f"Missing candidate array for declared action: {key}/{action}")
                # Every candidate meets the registered plausibility bound
                # before it is executed, whichever stage produced it, so a
                # diverging repair is recorded here instead of entering the
                # bank as a legitimate execution.
                reference = store[f"{key}|reference"]
                observed = np.isfinite(reference)
                if value.shape != reference.shape or not np.array_equal(value[observed], reference[observed]):
                    raise RuntimeError(f"observed values changed: {key}/{action}")
                if action == "KEEP" and not np.array_equal(value, reference, equal_nan=True):
                    raise RuntimeError(f"KEEP changed reference: {key}")
                implausible = (None if action == "KEEP" else A.implausible_reason(value, reference))
                if implausible is not None:
                    plan.append({"episode": key, "action": action,
                                 "applicable": False, "reason": implausible,
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
            fcntl.flock(lock, fcntl.LOCK_EX)
            # All heavy GPU work shares the project lock.
            free_mib = int(subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                text=True).strip().splitlines()[0])
            if free_mib < 3072:
                raise RuntimeError(f"only {free_mib} MiB of GPU memory is free")
            import torch
            torch.manual_seed(101)
            np.random.seed(101)
            torch.cuda.reset_peak_memory_stats()
            tick = time.perf_counter()
            try:
                if args.backbone == "bolt":
                    model = baseline_worker.Bolt(run_dir)
                elif args.backbone == "timesfm":
                    model = baseline_worker.TimesFM(run_dir)
                else:
                    sys.path.insert(0, str(ROOT / "scripts"))
                    from v46_chronos2 import Chronos2
                    model = Chronos2(run_dir)
                torch.cuda.synchronize()
                load_seconds = time.perf_counter() - tick
                identity = dict(model.identity)
                identity["load_seconds"] = load_seconds
                identity["load_peak_gpu_bytes"] = int(torch.cuda.max_memory_allocated())
            except BaseException as exc:
                write(status_path, {"stage": "v47-verified-forecast",
                                    "status": "failed", "block": args.block,
                                    "backbone": args.backbone,
                                    "error": f"{type(exc).__name__}: {exc}",
                                    "heldout_labels_read": 0})
                raise

            try:
                decision_path = root / "configs/v47-verified/batch_probe_decision.json"
                decision = json.loads(decision_path.read_text())
                frozen = decision["backbones"][args.backbone]
                if identity.get("weight_sha256") != frozen["weight_sha256"]:
                    raise RuntimeError("backbone weight hash differs from batch probe")
                if (args.backbone == "timesfm" and
                        identity.get("source_commit") != frozen["source_commit"]):
                    raise RuntimeError("TimesFM source commit differs from batch probe")
                batch_size = P.INFERENCE_BATCH_SIZE[args.backbone]
                if decision["decision"][args.backbone] != batch_size:
                    raise RuntimeError("batch decision artifact and protocol disagree")
                configure_batching(model, args.backbone, batch_size)
                identity["inference_batch_size"] = batch_size
                if args.backbone == "chronos2":
                    identity["generation"] = dict(identity["generation"])
                    identity["generation"]["batch_size"] = batch_size
                jobs_by_horizon: dict[int, list[tuple[str, np.ndarray]]] = {}
                for digest in sorted(unique):
                    horizons = {p["horizon"] for p in plan
                                if p.get("input_hash") == digest}
                    for horizon in sorted(horizons):
                        jobs_by_horizon.setdefault(horizon, []).append(
                            (digest, unique[digest]))
                total_jobs = sum(len(jobs) for jobs in jobs_by_horizon.values())
                done = 0
                for horizon, jobs in sorted(jobs_by_horizon.items()):
                    for offset in range(0, len(jobs), batch_size):
                        chunk = jobs[offset:offset + batch_size]
                        tick = time.perf_counter()
                        try:
                            prediction = model.forecast(
                                batch_input([value for _, value in chunk]),
                                horizon)[:, :, 0]
                            batch_seconds = time.perf_counter() - tick
                            if prediction.shape != (len(chunk), horizon):
                                raise RuntimeError(
                                    f"unexpected shape {prediction.shape}")
                            if not np.isfinite(prediction).all():
                                raise RuntimeError("non-finite forecast")
                            amortized = batch_seconds / len(chunk)
                            batch_calls.append({"horizon": horizon,
                                                "offset": offset,
                                                "size": len(chunk),
                                                "seconds": batch_seconds})
                            for row_index, (digest, _) in enumerate(chunk):
                                arrays[f"{digest}|h{horizon}"] = np.asarray(
                                    prediction[row_index], dtype=np.float64)
                                runtime_of[(digest, horizon)] = amortized
                                calls.append({"input_hash": digest,
                                              "horizon": horizon,
                                              "runtime_seconds": amortized,
                                              "batch_size": len(chunk),
                                              "batch_seconds": batch_seconds,
                                              "batch_offset": offset})
                        except Exception as exc:  # noqa: BLE001 - recorded
                            for digest, _ in chunk:
                                failures.append({"input_hash": digest,
                                                 "horizon": horizon,
                                                 "reason": f"{type(exc).__name__}: {exc}"})
                        done += len(chunk)
                        if done == len(chunk) or done % 200 < len(chunk):
                            print(json.dumps({"done": done, "total": total_jobs,
                                          "elapsed": time.perf_counter() - began}),
                                  flush=True)
            except BaseException:
                traceback.print_exc()
                write(status_path, {"stage": "v47-verified-forecast",
                                    "status": "failed", "block": args.block,
                                    "backbone": args.backbone, "calls": calls,
                                    "batch_calls": batch_calls,
                                    "failures": failures,
                                    "heldout_labels_read": 0})
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
                matched = [f for f in failures
                           if f["input_hash"] == item["input_hash"] and
                           f["horizon"] == item["horizon"]]
                if not matched:
                    raise RuntimeError("prediction missing without a recorded model failure")
                item["execution_failure"] = matched[0]["reason"]

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
        "stage": "v47-verified-forecast",
        "block": args.block,
        "backbone": args.backbone,
        "status": "failed" if failures else "completed",
        "identity": identity,
        "unique_inputs": len(unique),
        "unique_predictions": len(arrays),
        "plan_rows": len(plan),
        "applicable_rows": sum(1 for p in plan if p["applicable"]),
        "unsupported_rows": sum(1 for p in plan if not p["applicable"]),
        "execution_failed_rows": sum(1 for p in plan if "execution_failure" in p),
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
        "inference_batch_size": P.INFERENCE_BATCH_SIZE[args.backbone],
        "batch_calls": batch_calls,
        "batch_call_seconds_total": float(sum(
            row["seconds"] for row in batch_calls)),
        "predictions_npz": str(npz_path.relative_to(root)),
        "predictions_sha256": sha(npz_path),
        "plan": plan,
        "source_hashes": {
            "scripts/v431_baselines/worker.py": sha(root / "scripts/v431_baselines/worker.py"),
            "scripts/v47_forecast_verified.py": sha(Path(__file__)),
            "src/introact_ts/v47_verified/actions.py": sha(Path(A.__file__)),
            "src/introact_ts/v47_verified/protocol.py": sha(Path(P.__file__)),
            "configs/v47-verified/batch_probe_decision.json": sha(
                root / "configs/v47-verified/batch_probe_decision.json"),
        },
        "input_dependencies": {"inputs": manifest["inputs_sha256"],
                               "tsicl": tsicl_status["outputs_sha256"],
                               "saits": sha(saits_path)},
        "heldout_labels_read": 0,
    }
    if args.backbone == "chronos2":
        status["source_hashes"]["scripts/v46_chronos2.py"] = sha(
            root / "scripts/v46_chronos2.py")
    write(status_path, status)
    if failures:
        raise SystemExit(f"forecast failures: {len(failures)}; inspect recorded status")
    print(json.dumps({k: v for k, v in status.items()
                      if k not in ("plan", "aliases")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
