"""Real-model interface pilot. No method selection/calibration/test access."""
from collections import defaultdict
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from .schemas import Candidate, array_hash, json_hash, require, verify_impute
from .data_io import inventory, select_pilot, load_context, read_rows, file_hash
from .task_labels import read_target, evaluate_pair, mase_scale
from .worker_protocol import verify_response


def run_pilot(config, out, code, atomic, status):
    """Caller records any exception as failed; all raw worker output survives."""
    from .cli import readiness
    ready = readiness(config)
    if ready["status"] != "completed":
        status.update(status="blocked_dependency", reasons=ready["reasons"], forecast_status="not_run")
        return
    gate_path = Path(config["runtime"]["semantic_gate"])
    require(gate_path.is_file(), "CPU semantic gate missing")
    gate = json.loads(gate_path.read_text())
    require(gate["status"] == "completed" and gate["code_hash"] == code["hash"]
            and gate["config_hash"] == json_hash(config), "CPU semantic gate stale/failed")
    root = Path(__file__).resolve().parents[3]
    require(gate["test_hashes"] == {str(p.relative_to(root)): file_hash(p) for p in sorted((root / "tests/v43").rglob("*.py"))},
            "CPU test tree changed since gate")
    atomic(out / "semantic_gate.json", gate)
    require(config["runtime"]["inference_batch_size"] == 1, "pilot currently uses batch one")
    require(config["data"]["context"] == 512 and config["data"]["pilot_horizon"] == 32,
            "interface pilot requires L512/H32")
    model_manifest = json.loads(Path(config["models"]["manifest"]).read_text())
    atomic(out / "model_manifest.json", model_manifest)
    records = inventory(config["data"]["root"])
    origins = select_pilot(records, 32)
    atomic(out / "data_manifest.json", records)
    atomic(out / "origin_manifest.json", origins)
    lookup = {r["source"]: r for r in records}
    contexts = []
    for origin in origins:
        raw = load_context(lookup[origin["source"]], origin)
        x = raw.target.copy()
        lo, hi = config["data"]["pilot_block"]
        require(0 <= lo < hi <= len(x), "invalid pilot block")
        x[lo:hi] = np.nan
        uid = json_hash(dict(origin_uid=raw.uid, corruption="target_block", block=[lo, hi], seed=config["seed"]))
        contexts.append(replace(raw, uid=uid, target=x))
    inputs = out / "inputs"
    inputs.mkdir()
    for e in contexts:
        with (inputs / f"{e.uid}.npz").open("xb") as f:
            np.savez(f, target=e.target, raw_mask=e.observed_mask, covariates=e.covariates,
                     timestamps=e.timestamps, availability=e.availability)
    costs = []

    def call(key, task, mode, candidates, shard):
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
                       environment_hash=model["environment_lock_sha256"], task=task, horizon=32, dtype="float64",
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

    raw_requests = [(e, "KEEP", e.target) for e in contexts]
    singles = call("tsicl", "impute", "none", raw_requests, "tsicl_single")
    covs = call("tsicl", "impute", "past_only", raw_requests, "tsicl_cov")
    forecast_requests = []
    for e, mono, cov in zip(contexts, singles, covs):
        for name, target in (("KEEP", e.target), ("TSICL_SINGLE", mono), ("TSICL_COV", cov)):
            verify_impute(e, Candidate(e.uid, name, target))
            forecast_requests.append((e, name, target))
    forecasts = call("bolt", "forecast", "none", forecast_requests, "bolt")
    # Labels are opened only after all candidate/forecast outputs passed identity.
    targets, scales = {}, {}
    for e in contexts:
        record = lookup[e.source]
        reader = lambda lo, hi, r=record, s=e.split, c=e.target_channel: read_rows(r, lo, hi, s)[1][:, c]
        targets[e.uid] = read_target(reader, e)
        if e.source not in scales:
            lo, hi = record["split_bounds"]["train"]
            train = read_rows(record, lo, hi, "train")[1][:, e.target_channel]
            scales[e.source] = mase_scale(train, config["data"]["seasonal_periods"][e.source])
    labels = []
    with (out / "targets.npz").open("xb") as f:
        np.savez(f, **{f"{uid}_{name}": getattr(target, name) for uid, target in targets.items() for name in ("values", "mask")})
    for i, (e, arm, _) in enumerate(forecast_requests):
        label = evaluate_pair(targets[e.uid], forecasts[(i//3)*3], forecasts[i], scale=scales[e.source])
        labels.append(dict(label, source=e.source, candidate_id=arm))
    atomic(out / "task_labels.json", labels)
    atomic(out / "mase_scales.json", scales)
    grouped = defaultdict(list)
    for row in labels:
        grouped[(row["candidate_id"], row["source"])].append(row)
    metrics = []
    for (arm, source), values in grouped.items():
        valid = [r for r in values if r["status"] == "completed"]
        metrics.append(dict(arm=arm, source=source, n_origins=len(values), n_scored=len(valid),
                            mae=float(np.mean([r["mae"] for r in valid])) if valid else None,
                            mase=float(np.mean([r["mase"] for r in valid])) if valid and all(r["mase"] is not None for r in valid) else None,
                            task_gain=float(np.mean([r["task_gain"] for r in valid])) if valid else None))
    atomic(out / "metrics_by_source.json", metrics)
    comparison = {}
    for arm in ("KEEP", "TSICL_SINGLE", "TSICL_COV"):
        values = [m for m in metrics if m["arm"] == arm]
        require(len(values) == len(records), "pilot source denominator changed")
        comparison[arm] = {"n_origins": sum(m["n_origins"] for m in values), "n_sources": len(values)}
        for name in ("mae", "mase", "task_gain"):
            comparison[arm][f"source_macro_{name}"] = (float(np.mean([m[name] for m in values]))
                                                       if all(m[name] is not None for m in values) else None)
    atomic(out / "comparison.json", dict(scope="H32_interface_pilot_only", arms=comparison,
                                          confidence_interval=None, promotion=False,
                                          information_track="governance_with_historical_siblings_into_univariate_Bolt",
                                          limitation="Not a strict univariate method comparison; native multivariate target and A0-A5 pending"))
    atomic(out / "harmful_cases.json", [r for r in labels if r["task_harm"]])
    total = sum(r["worker_wall_seconds"] for r in costs)
    atomic(out / "cost_projection.json", dict(pilot_origins=32, pilot_wall_seconds=total,
                same_pilot_workload_seconds_per_1000_origins_with_20pct_margin=total/32*1000*1.2,
                limitation="H32 fixed three arms only; excludes A5 nested residual and formal H96/H192; not rental quote"))
    status.update(status="completed", scope="real_model_interface_pilot_only", n_origins=32,
                  future_labels_read=32, forecast_status="completed", incumbent="PICS_joint_relabel")
