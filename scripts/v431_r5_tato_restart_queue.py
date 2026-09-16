#!/usr/bin/env python3
"""Prepare and run deterministic fresh restarts for deadline-partial TATO scenes.

The original partial directories are immutable evidence.  Each selected scene is
restarted from trial zero in a new directory with the same research identity and
an explicitly registered wall-clock cap.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "results/v431-r5/tato-scene-extra-cached"
DEFAULT_OUTPUT = ROOT / "results/v431-r5/tato-scene-restart-20260916"
DEFAULT_WORKER = ROOT / "scripts/v431_r5_tato_cached_scene.py"
DEFAULT_CACHE_MODULE = ROOT / "scripts/v431_r5_tato_parent_cache.py"
MAX_REGISTERED_SECONDS = 1200.0

# These fields define the research/data/code identity.  Only output, status, and
# the explicitly registered wall-clock allowance may differ from the source.
IDENTITY_KEYS = (
    "family",
    "horizon",
    "source",
    "target_channel",
    "target_field",
    "condition",
    "context",
    "train_parents",
    "dev_parents",
    "rows",
    "trials",
    "inputs",
    "inputs_sha256",
    "seed",
    "worker_sha256",
    "cache_module_sha256",
    "adapter_sha256",
    "reference_frozen_sha256",
    "supervision",
    "heldout_labels_read",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path: Path | str):
    return json.loads(Path(path).read_text())


def atomic_write(path: Path | str, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def source_request_path(scene: Path) -> Path:
    frozen_path = scene / "run/frozen_scene.json"
    assert frozen_path.exists(), f"Missing source frozen scene: {scene}"
    expected = read(frozen_path)["request_sha256"]
    matches = [path for path in sorted(scene.glob("request*.json")) if sha(path) == expected]
    assert matches, f"No source request matches frozen hash: {scene}"
    return next((path for path in matches if path.name == "request.resolved.json"), matches[0])


def prepare_restart_queue(
    source_root: Path | str,
    output_root: Path | str,
    max_seconds: float,
    worker: Path | str,
    cache_module: Path | str,
):
    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    worker = Path(worker).resolve()
    cache_module = Path(cache_module).resolve()
    if output_root.exists():
        raise FileExistsError(f"Restart output already exists: {output_root}")
    assert source_root.is_dir(), source_root
    assert worker.is_file() and cache_module.is_file()
    assert 0 < float(max_seconds) <= MAX_REGISTERED_SECONDS

    selected = []
    for status_path in sorted(source_root.glob("*/run/status.json")):
        scene = status_path.parent.parent
        status = read(status_path)
        if status.get("status") != "partial":
            continue
        frozen_path = scene / "run/frozen_scene.json"
        frozen = read(frozen_path)
        requested = int(frozen["requested_trials"])
        actual = int(frozen["actual_trials"])
        assert actual < requested, f"Partial scene has no missing trials: {scene.name}"
        request_path = source_request_path(scene)
        source_request = read(request_path)
        assert int(source_request["trials"]) == requested == 500
        assert source_request["heldout_labels_read"] == 0
        assert float(max_seconds) > float(source_request["max_seconds"])
        assert sha(source_request["inputs"]) == source_request["inputs_sha256"]
        assert sha(worker) == source_request["worker_sha256"]
        assert sha(cache_module) == source_request["cache_module_sha256"]

        selected.append(
            (scene, status_path, frozen_path, request_path, source_request, actual, requested)
        )

    assert selected, "No deadline-partial scenes found"
    output_root.mkdir(parents=True, exist_ok=False)
    jobs = []
    for scene, status_path, frozen_path, request_path, source_request, actual, requested in selected:
        frozen = read(frozen_path)

        destination = output_root / scene.name
        destination.mkdir()
        request = dict(source_request)
        request.update(
            status="preregistered_not_run",
            output=str(destination),
            max_seconds=float(max_seconds),
            restart_amendment={
                "mode": "fresh_deterministic_from_trial_zero",
                "reason": "source run was interrupted only by the registered shutdown deadline",
                "source_scene": str(scene.resolve()),
                "source_request": str(request_path.resolve()),
                "source_request_sha256": sha(request_path),
                "source_status": str(status_path.resolve()),
                "source_status_sha256": sha(status_path),
                "source_frozen": str(frozen_path.resolve()),
                "source_frozen_sha256": sha(frozen_path),
                "source_max_seconds": float(source_request["max_seconds"]),
                "registered_max_seconds": float(max_seconds),
                "created_utc": utc_now(),
                "old_partial_preserved": True,
            },
        )
        for key in IDENTITY_KEYS:
            assert request[key] == source_request[key]
        new_request_path = destination / "request.preregistered.json"
        atomic_write(new_request_path, request)
        jobs.append(
            {
                "scene": scene.name,
                "request": str(new_request_path),
                "request_sha256": sha(new_request_path),
                "source_actual_trials": actual,
                "source_completed_trials": int(frozen["completed_trials"]),
                "requested_trials": requested,
                "status": "preregistered_not_run",
            }
        )

    queue = {
        "status": "preregistered_not_run",
        "created_utc": utc_now(),
        "source_root": str(source_root),
        "output_root": str(output_root),
        "worker": str(worker),
        "worker_sha256": sha(worker),
        "cache_module": str(cache_module),
        "cache_module_sha256": sha(cache_module),
        "max_seconds": float(max_seconds),
        "mode": "fresh_deterministic_from_trial_zero",
        "server_shutdown_invoked": False,
        "queue": jobs,
    }
    atomic_write(output_root / "queue.preregistered.json", queue)
    return queue


def run_restart_queue(queue_path: Path | str, queue_lock: Path | str):
    queue_path = Path(queue_path).resolve()
    queue = read(queue_path)
    execution_path = queue_path.with_name("queue.execution.json")
    if execution_path.exists():
        raise FileExistsError(f"Queue execution already exists: {execution_path}")
    assert queue["status"] == "preregistered_not_run"
    assert queue["server_shutdown_invoked"] is False
    worker = Path(queue["worker"])
    assert sha(worker) == queue["worker_sha256"]
    queue_lock = Path(queue_lock)
    queue_lock.parent.mkdir(parents=True, exist_ok=True)
    with queue_lock.open("a") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.perf_counter()
        execution = {
            "status": "running",
            "started_utc": utc_now(),
            "queue_preregistered": str(queue_path),
            "queue_preregistered_sha256": sha(queue_path),
            "mode": queue["mode"],
            "server_shutdown_invoked": False,
            "jobs": [],
        }
        atomic_write(execution_path, execution)
        for registered in queue["queue"]:
            request_path = Path(registered["request"])
            job = {
                "scene": registered["scene"],
                "request": str(request_path),
                "status": "running",
                "started_utc": utc_now(),
            }
            execution["jobs"].append(job)
            atomic_write(execution_path, execution)
            job_started = time.perf_counter()
            log_path = request_path.parent / "worker.stdout.log"
            command = [sys.executable, str(worker), "--request", str(request_path)]
            try:
                assert sha(request_path) == registered["request_sha256"]
                request = read(request_path)
                assert request["restart_amendment"]["mode"] == queue["mode"]
                assert sha(worker) == request["worker_sha256"]
                with log_path.open("w") as log_handle:
                    completed = subprocess.run(
                        command,
                        cwd=ROOT,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        text=True,
                        check=False,
                    )
                job["returncode"] = completed.returncode
                terminal_path = request_path.parent / "run/status.json"
                if terminal_path.exists():
                    job["worker_terminal"] = read(terminal_path)
                worker_status = job.get("worker_terminal", {}).get("status")
                if completed.returncode != 0:
                    job["status"] = "failed"
                elif worker_status == "completed":
                    job["status"] = "completed"
                elif worker_status in ("partial", "failed"):
                    job["status"] = "worker_" + worker_status
                else:
                    job["status"] = "missing_terminal_status"
            except Exception as exc:
                job.update(status="failed_to_launch", returncode=None, error=repr(exc))
            job.update(
                finished_utc=utc_now(),
                wall_seconds=time.perf_counter() - job_started,
                wall_scope="full child process after queue lock; queue wait excluded",
                log=str(log_path),
            )
            atomic_write(execution_path, execution)

    execution.update(
        status=(
            "completed"
            if all(job["status"] == "completed" for job in execution["jobs"])
            else "finished_with_failures"
        ),
        finished_utc=utc_now(),
        wall_seconds=time.perf_counter() - started,
        server_shutdown_invoked=False,
    )
    atomic_write(execution_path, execution)
    return execution


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    prepare_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    prepare_parser.add_argument("--max-seconds", type=float, default=MAX_REGISTERED_SECONDS)
    prepare_parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    prepare_parser.add_argument("--cache-module", type=Path, default=DEFAULT_CACHE_MODULE)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--queue", type=Path, default=DEFAULT_OUTPUT / "queue.preregistered.json")
    run_parser.add_argument(
        "--queue-lock", type=Path, default=ROOT / "locks/v431_r5_tato_restart_queue.lock"
    )
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_restart_queue(
            args.source_root, args.output_root, args.max_seconds, args.worker, args.cache_module
        )
        print(json.dumps({"status": result["status"], "jobs": len(result["queue"])}))
    else:
        result = run_restart_queue(args.queue, args.queue_lock)
        print(json.dumps({"status": result["status"], "jobs": len(result["jobs"])}))
        if result["status"] != "completed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
