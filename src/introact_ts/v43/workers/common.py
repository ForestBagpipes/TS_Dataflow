"""Shared strict real-worker lifecycle. No download or surrogate path."""
import argparse
from copy import deepcopy
import fcntl
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from ..schemas import array_hash, json_hash, require
from ..worker_protocol import validate_request, verify_response
from ..data_io import file_hash


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name+f".tmp.{os.getpid()}")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")
    temp.replace(path)


def verify_model(request, key):
    manifest = json.loads(Path(request["model_manifest"]).read_text())
    record = manifest["models"][key]
    require(record["status"] == "ready" and record["validation"]["status"] == "passed", "bootstrap model not ready")
    require(record["revision"] == request["model_revision"], "model revision mismatch")
    require(Path(sys.prefix).resolve() == Path(record["environment_python"]).parent.parent.resolve(), "wrong worker interpreter")
    require(file_hash(record["environment_lock"]) == request["environment_hash"] == record["environment_lock_sha256"], "environment lock mismatch")
    source = Path(record["official_code_path"])
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    require(commit == record["official_code_commit"], "official source revision mismatch")
    for item in record["files"].values():
        require(file_hash(item["path"]) == item["sha256"], "model file hash mismatch")
    require(Path(record["snapshot_path"]).name == record["revision"], "snapshot revision mismatch")
    root = Path(__file__).resolve().parents[4]
    hashes = {str(p.relative_to(root)): file_hash(p) for p in sorted((root / "src/introact_ts/v43").rglob("*.py"))}
    require(json_hash(hashes) == request["code_hash"], "worker code mismatch")
    package = "tsicl.pipeline" if key == "tsicl" else "chronos.base"
    relative = "src/tsicl/pipeline.py" if key == "tsicl" else "src/chronos/base.py"
    installed = inspect.getfile(importlib.import_module(package))
    require(file_hash(installed) == file_hash(source / relative), "installed model source mismatch")
    return record


def load_inputs(request):
    arrays = []
    for row in request["rows"]:
        with np.load(row["array_path"], allow_pickle=False) as archive:
            require(set(archive.files) == {"target", "raw_mask", "covariates", "availability", "timestamps"}, "payload keys mismatch")
            payload = {k: archive[k] for k in archive.files}
        for name, hash_key in (("target", "input_hash"), ("raw_mask", "raw_mask_hash"),
                               ("covariates", "covariate_hash"), ("availability", "availability_hash"),
                               ("timestamps", "timestamps_hash")):
            require(array_hash(payload[name]) == row[hash_key], f"payload {name} hash mismatch")
        x, z, t, a, m = (payload[n] for n in ("target", "covariates", "timestamps", "availability", "raw_mask"))
        require(x.ndim == 1 and len(x) > 0 and x.dtype == np.dtype(request["dtype"]), "target layout mismatch")
        require(z.ndim == 2 and len(z) == len(x), "covariate layout mismatch")
        require(t.shape == x.shape and t.dtype.kind in "iu" and np.all(t[1:] > t[:-1]), "time layout mismatch")
        require(m.dtype == bool and m.shape == x.shape, "raw mask layout mismatch")
        require(a.shape == (len(x), z.shape[1]+1), "availability layout mismatch")
        require(not np.isinf(x).any() and not np.isinf(z).any(), "infinite input")
        require(not np.any(np.isfinite(np.column_stack((x, z))) & (a > t[-1])), "late value exposed")
        require(json_hash(row["parameters"]) == row["parameters_hash"], "parameter mismatch")
        require(row["parameters"] == {}, "worker parameter overrides not implemented")
        arrays.append(payload)
    return arrays


def run_worker(key, loader, predict):
    parser = argparse.ArgumentParser()
    for arg in ("request", "response", "predictions"):
        parser.add_argument("--"+arg, required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text())
    validate_request(request)
    require(request["normalization"] == "native" and request["model_key"] == key, "unsupported model settings")
    require(not Path(args.response).exists() and not Path(args.predictions).exists(), "stale worker output")
    response = deepcopy(request)
    response.update(status="running", units="original", worker_pid=os.getpid(), worker_python=sys.executable)
    try:
        payloads = load_inputs(request)
        record = verify_model(request, key)
        import torch
        require(torch.cuda.is_available(), "CUDA unavailable")
        torch.manual_seed(request["seed"])
        np.random.seed(request["seed"])
        with Path(request["gpu_lock"]).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            processes = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"], text=True).strip()
            require(not processes, "GPU compute process already active; do not interfere")
            torch.cuda.reset_peak_memory_stats()
            start = time.perf_counter()
            model = loader(record)
            torch.cuda.synchronize()
            response["load_seconds"] = time.perf_counter()-start
            response["load_peak_gpu_bytes"] = torch.cuda.max_memory_allocated()
            predictions, raw_outputs = [], {}
            for i, (row, payload) in enumerate(zip(response["rows"], payloads)):
                torch.cuda.reset_peak_memory_stats()
                start = time.perf_counter()
                point, raw = predict(model, payload, request, row)
                require(np.isfinite(raw).all(), "nonfinite raw model output")
                torch.cuda.synchronize()
                runtime = time.perf_counter()-start
                p = np.asarray(point, dtype=request["dtype"])
                row.update(prediction_hash=array_hash(p), shape=list(p.shape), runtime_seconds=runtime,
                           peak_gpu_bytes=torch.cuda.max_memory_allocated(), actual_batch_size=1,
                           raw_shape=list(raw.shape), raw_hash=array_hash(raw))
                predictions.append(p)
                raw_outputs[f"row_{i}"] = raw
                print(json.dumps({"row": i, "episode_uid": row["episode_uid"], "runtime_seconds": runtime, "shape": list(p.shape)}), flush=True)
            response["status"] = "completed"
            verify_response(request, response, predictions)
            out = Path(args.predictions)
            temp = out.with_name(out.name+f".tmp.{os.getpid()}")
            with temp.open("wb") as f:
                np.savez(f, **{f"row_{i}": p for i, p in enumerate(predictions)})
            temp.replace(out)
            raw_path = out.with_name(out.stem+".raw.npz")
            with raw_path.open("xb") as f:
                np.savez(f, **raw_outputs)
            response["raw_predictions"] = dict(path=str(raw_path), sha256=file_hash(raw_path))
            atomic_json(args.response, response)
    except Exception as exc:
        response.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        atomic_json(args.response, response)
        raise
