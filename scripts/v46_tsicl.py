#!/usr/bin/env python3
"""v4.6 Stage B -- TS-ICL intervention stage (GPU).

Runs the frozen TS-ICL checkpoint through the *unmodified* v4.3 worker adapter,
so the intervention semantics (float32 normalisation, ``replace_by_gt``,
median point estimator, past-only covariate mode) are exactly the ones the
project already froze.

Produces the two TS-ICL candidate inputs of every episode:

* ``SINGLE_TSICL`` -- impute the target channel alone;
* ``MULTI_TSICL``  -- impute the target channel conditioned on the covariates.

Failures are recorded per episode with their reason; nothing is silently
dropped and nothing falls back to a different estimator.
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

from introact_ts.v43.workers import tsicl_worker
from introact_ts.v46 import grid as PL
from introact_ts.v44.hashing import array_hash

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v46/replay"
MANIFEST = ROOT / "configs/v43/model_manifest.bootstrap.json"


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


def verify_record(record: dict) -> dict:
    for name, item in record["files"].items():
        if sha(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"TS-ICL immutable model file changed: {name}")
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--block", default="bank", choices=["bank", "train_eval", "test", "test30", "test50"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only-source", default=None,
                        help="probe a single source before the full run")
    args = parser.parse_args()

    root = Path(args.root)
    out_dir = OUT / "tsicl"
    out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = out_dir / f"{args.block}.npz"
    status_path = out_dir / f"{args.block}.json"
    if npz_path.exists() or status_path.exists():
        raise SystemExit(f"refusing to overwrite existing TS-ICL output {npz_path}")

    manifest = json.loads(MANIFEST.read_text())
    record = verify_record(manifest["models"]["tsicl"])

    specs = PL.episode_specs(root, args.block)
    if args.only_source:
        specs = [s for s in specs if s.source == args.only_source]
    if args.limit:
        specs = specs[: args.limit]

    arrays: dict[str, np.ndarray] = {}
    rows: list[dict] = []
    failures: list[dict] = []
    began = time.perf_counter()
    load_seconds = 0.0

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
        model = tsicl_worker.load(record)
        torch.cuda.synchronize()
        load_seconds = time.perf_counter() - tick
        identity = {
            "repo_id": record["repo_id"],
            "revision": record["revision"],
            "checkpoint_path": record["checkpoint_path"],
            "weight_sha256": {k: v["sha256"] for k, v in record["files"].items()},
            "dtype": "float32",
            "environment_python": sys.executable,
            "adapter": "introact_ts.v43.workers.tsicl_worker.predict",
            "load_seconds": load_seconds,
            "load_peak_gpu_bytes": int(torch.cuda.max_memory_allocated()),
        }

        try:
            for spec, _raw, masked, _future in PL.iter_panels(root, specs):
                key = spec.episode_id
                target = masked[:, 0].copy()
                covariates = masked[:, 1:].copy()
                for action, mode in (("SINGLE_TSICL", "none"),
                                     ("MULTI_TSICL", "past_only")):
                    request = {"task": "impute", "covariate_mode": mode,
                               "horizon": spec.horizon, "dtype": "<f8"}
                    payload = {"target": target, "covariates": covariates}
                    row = {"output_length": target.shape[0]}
                    torch.cuda.reset_peak_memory_stats()
                    tick = time.perf_counter()
                    try:
                        point, _quantiles = tsicl_worker.predict(model, payload, request, row)
                        torch.cuda.synchronize()
                        runtime = time.perf_counter() - tick
                        value = np.asarray(point, dtype=np.float64)
                        if value.shape != target.shape:
                            raise RuntimeError(f"unexpected TS-ICL shape {value.shape}")
                        if not np.isfinite(value).all():
                            raise RuntimeError("TS-ICL produced non-finite output")
                        arrays[f"{key}|{action}"] = value
                        rows.append({"episode": key, "action": action,
                                     "applicable": True, "reason": None,
                                     "input_hash": array_hash(value),
                                     "runtime_seconds": runtime,
                                     "peak_gpu_bytes": int(torch.cuda.max_memory_allocated())})
                    except Exception as exc:  # noqa: BLE001 - recorded, never silent
                        failures.append({"episode": key, "action": action,
                                         "reason": f"{type(exc).__name__}: {exc}"})
                        rows.append({"episode": key, "action": action,
                                     "applicable": False,
                                     "reason": f"{type(exc).__name__}: {exc}",
                                     "input_hash": None, "runtime_seconds": None,
                                     "peak_gpu_bytes": None})
                if len(rows) % 100 == 0:
                    print(json.dumps({"rows": len(rows),
                                      "elapsed": time.perf_counter() - began}), flush=True)
        except BaseException:
            traceback.print_exc()
            write(status_path, {"status": "failed", "rows": rows,
                                "failures": failures})
            raise

    with npz_path.open("wb") as handle:
        np.savez(handle, **arrays)

    status = {
        "stage": "v44-replay-tsicl-B",
        "block": args.block,
        "status": "completed",
        "identity": identity,
        "episodes": len(specs),
        "rows": len(rows),
        "supported": sum(1 for r in rows if r["applicable"]),
        "failed": len(failures),
        "failures": failures,
        "per_action": dict(sorted(Counter(
            r["action"] for r in rows if r["applicable"]).items())),
        "runtime_seconds": time.perf_counter() - began,
        "load_seconds": load_seconds,
        "outputs_npz": str(npz_path.relative_to(root)),
        "outputs_sha256": sha(npz_path),
        "rows_detail": rows,
        "source_hashes": {
            "src/introact_ts/v43/workers/tsicl_worker.py":
                sha(root / "src/introact_ts/v43/workers/tsicl_worker.py"),
            "src/introact_ts/v44/pipeline.py":
                sha(root / "src/introact_ts/v44/pipeline.py"),
            "scripts/v44_replay_tsicl.py": sha(Path(__file__)),
        },
        "heldout_labels_read": 0,
    }
    write(status_path, status)
    print(json.dumps({k: v for k, v in status.items() if k not in ("rows_detail",)},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
