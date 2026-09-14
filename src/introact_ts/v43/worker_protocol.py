"""Strict batch identity and content-addressed file protocol (no fallback)."""
from pathlib import Path
import json
import re
import subprocess
import numpy as np
from .schemas import array_hash, json_hash, require

IDENTITY = ("schema_version", "request_id", "model_revision", "code_hash", "environment_hash",
            "task", "horizon", "dtype", "seed", "covariate_mode", "batch_size", "normalization")
ROW_IDENTITY = ("episode_uid", "candidate_id", "input_hash", "raw_mask_hash",
                "covariate_hash", "availability_hash", "timestamps_hash", "cutoff", "parameters_hash")


def validate_request(request):
    require(all(k in request for k in IDENTITY), "missing request identity")
    require(request["schema_version"] == 1, "unsupported schema")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", request["model_revision"])), "revision must be immutable SHA")
    require(request["task"] in ("forecast", "impute"), "unsupported task")
    require(isinstance(request["horizon"], int) and request["horizon"] > 0, "invalid horizon")
    require(request["dtype"] in ("float32", "float64"), "unsupported dtype")
    require(request["covariate_mode"] in ("none", "past_only"), "future covariates forbidden")
    require(request["normalization"] == "native", "unimplemented normalization")
    for name in ("code_hash", "environment_hash"):
        require(isinstance(request[name], str) and bool(re.fullmatch(r"[0-9a-f]{64}", request[name])), "invalid code/environment hash")
    rows = request.get("rows", [])
    require(len(rows) > 0 and request["batch_size"] > 0, "empty batch")
    for row in rows:
        require(all(k in row for k in ROW_IDENTITY), "missing row identity")
        for name in ("input_hash", "raw_mask_hash", "covariate_hash", "availability_hash", "timestamps_hash", "parameters_hash"):
            require(isinstance(row[name], str) and bool(re.fullmatch(r"[0-9a-f]{64}", row[name])), "invalid row hash")
        require(isinstance(row.get("output_length"), int) and row["output_length"] > 0, "output length required")
        if request["task"] == "forecast":
            require(row["output_length"] == request["horizon"], "forecast length mismatch")
    keys = [(r["episode_uid"], r["candidate_id"]) for r in rows]
    require(len(keys) == len(set(keys)), "duplicate batch identity")


def cache_key(request):
    validate_request(request)
    return json_hash({k: v for k, v in request.items() if k != "request_id"})


def verify_response(request, response, predictions):
    """Validate the whole shard before exposing even one prediction."""
    validate_request(request)
    require(response.get("status") == "completed", "worker failure")
    require(all(response.get(k) == request[k] for k in IDENTITY), "worker identity mismatch")
    require(response.get("units") == "original", "worker unit mismatch")
    rows = response.get("rows", [])
    require(len(rows) == len(request["rows"]) == len(predictions), "worker dropped/added rows")
    for expected, actual, pred in zip(request["rows"], rows, predictions):
        require(all(actual.get(k) == expected[k] for k in ROW_IDENTITY), "worker row mismatch")
        p = np.asarray(pred)
        require(p.shape == (expected["output_length"],), "worker output shape mismatch")
        require(p.dtype == np.dtype(request["dtype"]), "worker output dtype mismatch")
        require(np.isfinite(p).all(), "nonfinite prediction is a failure")
        require(actual.get("prediction_hash") == array_hash(p), "worker output hash mismatch")
        require(actual.get("shape") == list(p.shape), "declared output shape mismatch")
        for name in ("runtime_seconds", "peak_gpu_bytes"):
            value = actual.get(name)
            require(isinstance(value, (int, float)) and np.isfinite(value) and value >= 0, "missing/invalid cost")
    return tuple(predictions)


def submit_batch(interpreter, module, request_path, response_path, prediction_path, timeout):
    """Worker must exclusively create outputs; stale files are never reused."""
    response_path, prediction_path = Path(response_path), Path(prediction_path)
    require(not response_path.exists() and not prediction_path.exists(), "output already exists")
    request = json.loads(Path(request_path).read_text())
    validate_request(request)
    subprocess.run([str(interpreter), "-m", module, "--request", str(request_path),
                    "--response", str(response_path), "--predictions", str(prediction_path)],
                   check=True, timeout=timeout)
    response = json.loads(response_path.read_text())
    with np.load(prediction_path, allow_pickle=False) as archive:
        require(set(archive.files) == {f"row_{i}" for i in range(len(request["rows"]))}, "array keys mismatch")
        predictions = [archive[f"row_{i}"] for i in range(len(request["rows"]))]
    return verify_response(request, response, predictions)
