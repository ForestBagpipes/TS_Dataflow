#!/usr/bin/env python3
"""Persistent single P2 task with external process/resource monitoring."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil
from introact_ts.v43.cli import atomic_json


def main():
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run = root/"results/v43"/(stamp+"-p2")
    logs = root/"logs/v43"/(stamp+"-p2")
    logs.mkdir(parents=True, exist_ok=False)
    state = dict(status="running", wrapper_pid=os.getpid(), owner=psutil.Process().username(), started_at=stamp, run=str(run), logs=str(logs))
    status_path = root/"results/v43/p2_queue_status.json"
    atomic_json(logs/"launch.json", dict(state, config="configs/v43/p2_first_dev.yaml", launcher_sha256=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest()))
    with (logs/"runner.log").open("x") as log, (logs/"resources.jsonl").open("x") as resources:
        process = subprocess.Popen([sys.executable, "-m", "introact_ts.v43.cli", "p2", "--config", str(root/"configs/v43/p2_first_dev.yaml"), "--out", str(run)], cwd=root, stdout=log, stderr=subprocess.STDOUT)
        state.update(pid=process.pid)
        atomic_json(status_path, state)
        while process.poll() is None:
            sample = dict(at=datetime.now(timezone.utc).isoformat(), pid=process.pid)
            try:
                parent = psutil.Process(process.pid)
                sample["processes"] = [dict(pid=p.pid, rss_bytes=p.memory_info().rss) for p in [parent, *parent.children(recursive=True)] if p.is_running()]
                sample["available_memory_bytes"] = psutil.virtual_memory().available
                sample["gpu"] = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True).strip()
            except (psutil.Error, OSError, subprocess.SubprocessError) as exc:
                sample["resource_error"] = str(exc)
            resources.write(json.dumps(sample)+"\n"); resources.flush()
            state.update(last_resource_sample=sample)
            atomic_json(status_path, state)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
    terminal = json.loads((run/"status.json").read_text()) if (run/"status.json").exists() else {}
    state.update(status="completed" if process.returncode == 0 and terminal.get("status") == "completed" else "failed", exit_code=process.returncode, finished_at=datetime.now(timezone.utc).isoformat(), run_status=terminal)
    atomic_json(status_path, state)
    atomic_json(logs/"terminal.json", state)
    print(json.dumps(state), flush=True)
    return process.returncode or (0 if state["status"] == "completed" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
