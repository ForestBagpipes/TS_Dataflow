#!/usr/bin/env python3
"""v54 confirmatory Stage C -- frozen TSFM forecast stage (GPU).

A mirror of ``scripts/v47_forecast.py`` bound to the confirmatory grid and
writing only under ``results/v54/confirmatory/``.  It takes the candidate
inputs produced by stage A (CPU actions), stage B (TS-ICL actions), the SAITS
stage and the external BRITS/CSDI stage, and runs the frozen backbone on every
*distinct* candidate input.  Identical inputs are deduplicated by array hash
and forecast once; the alias is recorded rather than hidden.

BRITS and CSDI enter as additional catalog actions read from the confirmatory
external-imputer archives, mirroring how SAITS is read from its own stage
archive; every non-KEEP candidate passes the same registered plausibility
guard before execution.  The model classes are imported from the frozen r5
baseline worker, unchanged.
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

from introact_ts.v44 import actions as A
from introact_ts.v44 import protocol as P
from introact_ts.v54 import confirmatory as PL
from introact_ts.v44.hashing import array_hash

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v54/confirmatory/replay"
BASELINES = ROOT / "scripts/v431_baselines"

#: External imputer actions, read from the confirmatory external archives.
# BRITS/CSDI dropped by decision 2026-09-22 (training cost at the frozen
#: equal-capacity config exceeds the remaining budget); tuple kept empty so
#: forecast/check treat them as absent.
EXT_ACTIONS: tuple[str, ...] = ()
STAGE_ACTIONS = tuple(P.ACTIONS) + EXT_ACTIONS


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


def load_candidate(store, tsicl_store, saits_store, ext_stores, key: str,
                   action: str) -> np.ndarray | None:
    name = f"{key}|{action}"
    if action in ("KEEP", "FFILL", "CONTEXT_RIDGE"):
        return store[name] if name in store.files else None
    if action == "SAITS":
        if saits_store is None or name not in saits_store.files:
            return None
        return saits_store[name]
    if action in EXT_ACTIONS:
        ext = ext_stores.get(action)
        if ext is None or name not in ext.files:
            return None
        return ext[name]
    return tsicl_store[name] if name in tsicl_store.files else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--block", default="test", choices=list(PL.BLOCKS))
    parser.add_argument("--backbone", default="bolt",
                        choices=list(P.ALL_BACKBONES))
    parser.add_argument("--limit", type=int, default=0,
                        help="probe only the first N episodes (diagnostic runs)")
    parser.add_argument("--donor", default="",
                        help="an earlier predictions archive of the same block and "
                             "backbone; entries whose input hash and horizon match "
                             "are read from it instead of being recomputed")
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

    saits_path = OUT / "saits" / f"{args.block}.npz"
    saits_store = (np.load(saits_path, allow_pickle=False)
                   if saits_path.exists() else None)
    ext_stores = {}
    for action in EXT_ACTIONS:
        ext_path = OUT / "external" / action.lower() / f"{args.block}.npz"
        if ext_path.exists():
            ext_stores[action] = np.load(ext_path, allow_pickle=False)

    with np.load(OUT / "inputs" / f"{args.block}.npz", allow_pickle=False) as store, \
            np.load(tsicl_path, allow_pickle=False) as tsicl_store:
        # Deduplicate every candidate input across the whole block.
        unique: dict[str, np.ndarray] = {}
        plan: list[dict] = []
        for row in rows:
            key = row["episode"]
            horizon = row["horizon"]
            for action in STAGE_ACTIONS:
                meta = row["candidates"].get(action)
                if action in ("SINGLE_TSICL", "MULTI_TSICL"):
                    available = f"{key}|{action}" in tsicl_store.files
                    meta = {"applicable": available,
                            "reason": None if available else "tsicl stage produced no output"}
                if action == "SAITS":
                    available = (saits_store is not None
                                 and f"{key}|{action}" in saits_store.files)
                    meta = {"applicable": available,
                            "reason": None if available else "imputer stage produced no output"}
                if action in EXT_ACTIONS:
                    available = (action in ext_stores
                                 and f"{key}|{action}" in ext_stores[action].files)
                    meta = {"applicable": available,
                            "reason": None if available else "external imputer stage produced no output"}
                if meta is None or not meta["applicable"]:
                    plan.append({"episode": key, "action": action,
                                 "applicable": False,
                                 "reason": (meta or {}).get("reason", "no candidate"),
                                 "input_hash": None})
                    continue
                value = load_candidate(store, tsicl_store, saits_store,
                                       ext_stores, key, action)
                if value is None:
                    plan.append({"episode": key, "action": action,
                                 "applicable": False,
                                 "reason": "candidate array missing",
                                 "input_hash": None})
                    continue
                # Every repair meets the registered plausibility bound before
                # it is executed, whichever stage produced it.  The reference
                # action repairs nothing and is exempt.
                implausible = (None if action == P.REFERENCE_ACTION else
                               A.implausible_reason(value, store[f"{key}|reference"]))
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

        with (root / f"locks/gpu-{args.backbone}.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
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

            donor_hits = 0
            if args.donor:
                with np.load(args.donor, allow_pickle=False) as old:
                    for name in old.files:
                        if name not in arrays:
                            arrays[name] = old[name]
                            donor_hits += 1
            try:
                order = sorted(unique)
                for index, digest in enumerate(order):
                    value = unique[digest]
                    horizons = sorted({p["horizon"] for p in plan
                                       if p.get("input_hash") == digest})
                    for horizon in horizons:
                        if f"{digest}|h{horizon}" in arrays:
                            continue
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

    for ext in ext_stores.values():
        ext.close()
    if saits_store is not None:
        saits_store.close()

    with npz_path.open("wb") as handle:
        np.savez(handle, **arrays)

    status = {
        "stage": "v54-confirmatory-forecast-C",
        "block": args.block,
        "backbone": args.backbone,
        "status": "completed",
        "identity": identity,
        "unique_inputs": len(unique),
        "unique_predictions": len(arrays),
        "donor": args.donor or None,
        "reused_from_donor": donor_hits,
        "computed_here": len(calls),
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
        "plan": plan,
        "outputs_npz": str(npz_path.relative_to(root)),
        "outputs_sha256": sha(npz_path),
        "heldout_labels_read": 0,
    }
    write(status_path, status)
    print(json.dumps({k: v for k, v in status.items() if k != "plan"},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
