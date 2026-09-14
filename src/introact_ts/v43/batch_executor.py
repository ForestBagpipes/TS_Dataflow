"""Logged real worker shards shared by the formal development runner."""
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from .schemas import array_hash, json_hash, require
from .worker_protocol import verify_response


def make_executor(config, out, code, atomic, status, model_manifest):
    inputs = out / "inputs"
    inputs.mkdir()
    costs = []
    def call(key, task, mode, candidates, shard):
        horizon = candidates[0][0].horizon
        require(all(e.horizon == horizon for e, _, _ in candidates), "mixed worker horizons")
        model = model_manifest["models"][key]
        rows = []
        for i, (e, candidate_id, target) in enumerate(candidates):
            path = inputs / f"{shard}-{i}.npz"
            with path.open("xb") as f:
                np.savez(f, target=target, raw_mask=e.observed_mask, covariates=e.covariates,
                         timestamps=e.timestamps, availability=e.availability)
            rows.append(dict(episode_uid=e.uid, candidate_id=candidate_id, input_hash=array_hash(target),
                             raw_mask_hash=array_hash(e.observed_mask), covariate_hash=array_hash(e.covariates),
                             availability_hash=array_hash(e.availability), timestamps_hash=array_hash(e.timestamps),
                             cutoff=e.context_end, parameters={}, parameters_hash=json_hash({}), array_path=str(path),
                             output_length=e.horizon if task == "forecast" else len(e.target)))
        request = dict(schema_version=1, request_id=f"{out.name}:{shard}", model_revision=model["revision"],
                       model_key=key, model_manifest=str(out / "model_manifest.json"), code_hash=code["hash"],
                       environment_hash=model["environment_lock_sha256"], task=task, horizon=horizon, dtype="float64",
                       seed=config["seed"], covariate_mode=mode, batch_size=1, normalization="native", rows=rows,
                       gpu_lock=str(Path(__file__).resolve().parents[3] / "locks/gpu.lock"))
        request_path, response_path, prediction_path = (out / f"{shard}.{suffix}" for suffix in ("request.json", "response.json", "predictions.npz"))
        atomic(request_path, request)
        module = "introact_ts.v43.workers.tsicl_worker" if key == "tsicl" else "introact_ts.v43.workers.chronos_worker"
        start = time.perf_counter()
        with (out / f"{shard}.log").open("x") as log:
            process = subprocess.Popen([model["environment_python"], "-m", module, "--request", str(request_path),
                                        "--response", str(response_path), "--predictions", str(prediction_path)],
                                       stdout=log, stderr=subprocess.STDOUT)
            status.update(active_worker_pid=process.pid, active_shard=shard)
            atomic(out / "status.json", status)
            # Every sample is timestamped; never collect other users' command lines.
            with (out / f"{shard}.resources.jsonl").open("x") as resource:
                while process.poll() is None:
                    try:
                        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True).strip()
                        proc = Path(f"/proc/{process.pid}/status")
                        rss = [line for line in proc.read_text().splitlines() if line.startswith("VmRSS:")]
                        resource.write(json.dumps(dict(wall_seconds=time.time(), pid=process.pid, gpu=gpu, rss=rss))+"\n")
                        resource.flush()
                    except (OSError, subprocess.SubprocessError) as exc:
                        resource.write(json.dumps(dict(resource_error=str(exc)))+"\n")
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        pass
            require(process.returncode == 0, f"worker {shard} failed; see raw log")
        response = json.loads(response_path.read_text())
        with np.load(prediction_path, allow_pickle=False) as archive:
            require(set(archive.files) == {f"row_{i}" for i in range(len(rows))}, "prediction keys mismatch")
            predictions = [archive[f"row_{i}"] for i in range(len(rows))]
        verify_response(request, response, predictions)
        costs.append(dict(shard=shard, model=key, task=task, n_requests=len(rows), load_seconds=response["load_seconds"],
                          worker_wall_seconds=time.perf_counter()-start,
                          inference_seconds=sum(r["runtime_seconds"] for r in response["rows"]),
                          load_peak_gpu_bytes=response["load_peak_gpu_bytes"],
                          peak_gpu_bytes=max(response["load_peak_gpu_bytes"], max(r["peak_gpu_bytes"] for r in response["rows"]))))
        atomic(out / "cost_ledger.json", costs)
        return predictions

    return call, costs
