#!/usr/bin/env python3
"""Wait for existing bootstrap; run one frozen pilot, never install/retry models."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import yaml
from introact_ts.v43.cli import ROOT, atomic_json, code_manifest, readiness
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import json_hash, require


def main():
    config_path = ROOT / "configs/v43/bootstrap.yaml"
    config = yaml.safe_load(config_path.read_text())
    created = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    queue_dir = ROOT / "logs/v43" / (created+"-pilot-queue")
    queue_dir.mkdir(parents=True, exist_ok=False)
    lock = (ROOT / "locks/v43-pilot-queue.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    code_hash, config_hash = code_manifest()["hash"], json_hash(config)
    queue_script_hash = file_hash(__file__)
    status = dict(status="waiting_for_models", pid=os.getpid(), created_at=created, code_hash=code_hash,
                  config_hash=config_hash, script_sha256=queue_script_hash, queue_directory=str(queue_dir),
                  config=str(config_path), owner=os.environ.get("USER", "vipuser"),
                  program=str(Path(__file__).resolve()), pilot_status="not_run")
    def save():
        status["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(queue_dir / "status.json", status)
        atomic_json(ROOT / "results/v43/pilot_queue_status.json", status)
    save()
    start = time.monotonic()
    stage = Path("/home/vipuser/work2-staging/bootstrap-20260914")
    try:
        while True:
            require(code_manifest()["hash"] == code_hash and json_hash(yaml.safe_load(config_path.read_text())) == config_hash,
                    "code/config changed while queued; review and launch a new queue")
            ready = readiness(config)
            status["reasons"] = ready["reasons"]
            if ready["status"] == "completed":
                processes = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"], text=True).strip()
                if not processes:
                    break
                status["status"] = "waiting_for_gpu"
            else:
                for name in ("status.json", "continuation-status.json"):
                    path = stage / name
                    report = json.loads(path.read_text()) if path.exists() else {}
                    require(report.get("status") not in ("failed", "blocked", "blocked_dependency"), f"bootstrap {name} failed/blocked; preserve logs")
                    if report.get("status") in ("running", "waiting_for_environments"):
                        require(Path(f"/proc/{report.get('pid')}").exists(), f"bootstrap {name} PID absent on host")
                manifest_path = Path(config["models"]["manifest"])
                manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
                require(manifest.get("status") not in ("failed", "gpu_validation_deferred"), "model preparation stopped before ready")
                for record in manifest.get("models", {}).values():
                    require(record.get("status") != "failed", "model failure must be repaired before pilot")
            require(time.monotonic()-start < 24*3600, "24 hour dependency wait expired")
            save()
            time.sleep(30)
        # Gate is bound to this code/config and run afresh immediately before GPU.
        status.update(status="validating_cpu_gate")
        save()
        with (queue_dir / "contracts.log").open("x") as log:
            subprocess.run([sys.executable, str(ROOT / "scripts/run_v43_contracts.py"), "--config", str(config_path)],
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        out = ROOT / "results/v43" / (created+"-pilot")
        status.update(status="running_pilot", pilot_directory=str(out))
        save()
        with (queue_dir / "pilot.log").open("x") as log:
            process = subprocess.Popen([sys.executable, "-m", "introact_ts.v43.cli", "pilot", "--config", str(config_path), "--out", str(out)],
                                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            status.update(pilot_pid=process.pid)
            save()
            while process.poll() is None:
                save()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
            pilot = json.loads((out / "status.json").read_text())
            status.update(pilot_status=pilot["status"], pilot_exit_code=process.returncode)
            require(process.returncode == 0 and pilot["status"] == "completed", "pilot failed/blocked; preserve raw run and repair")
        status.update(status="completed", scope="interface_pilot_only_A0_A5_still_pending")
    except Exception as exc:
        status.update(status="blocked_dependency" if status["pilot_status"] == "not_run" else "failed",
                      error=f"{type(exc).__name__}: {exc}")
        save()
        raise
    save()


if __name__ == "__main__":
    main()
