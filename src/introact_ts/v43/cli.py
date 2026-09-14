"""Implemented CPU commands only; model pilot is gated separately."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import numpy as np
import yaml
from .schemas import array_hash, json_hash, require
from .data_io import file_hash, inventory, select_pilot, load_context

ROOT = Path(__file__).resolve().parents[3]


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+f".tmp.{os.getpid()}")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n")
    temp.replace(path)


def code_manifest():
    files = [ROOT / "src/introact_ts/__init__.py", ROOT / "src/introact_ts/types.py",
             ROOT / "src/introact_ts/verify.py", *sorted((ROOT / "src/introact_ts/v43").rglob("*.py"))]
    hashes = {str(p.relative_to(ROOT)): file_hash(p) for p in files}
    return {"files": hashes, "hash": json_hash(hashes),
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}


def readiness(config):
    path = Path(config["models"]["manifest"])
    manifest = json.loads(path.read_text()) if path.exists() else {}
    reasons = []
    for key in config["models"]["required"]:
        record = manifest.get("models", {}).get(key, {})
        if record.get("status") != "ready" or record.get("validation", {}).get("status") != "passed":
            reasons.append(f"{key}: bootstrap model interface not ready")
    return {"status": "blocked_dependency" if reasons else "completed", "reasons": reasons,
            "scope": "bootstrap_readiness_only", "manifest": str(path)}


def main():
    parser = argparse.ArgumentParser(description="v4.3 CPU contract and input preparation; no method promotion")
    parser.add_argument("command", choices=("preflight", "inventory", "data", "pilot", "p2", "agent-collect"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", help="new run directory; existing directory is rejected")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    require(config["mode"] == "development" and config["runtime"]["label_access"] == "train_dev_only", "unsupported label mode")
    require(config["data"]["split_ratio"] == [.6, .15, .1, .15], "unimplemented split ratios")
    require(config["data"]["pilot_target_channel"] == 0, "unimplemented target selection")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")+"-"+args.command
    out = Path(args.out) if args.out else ROOT / "results/v43" / run_id
    out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    status = dict(run_id=run_id, phase=args.command, status="running", pid=os.getpid(),
                  started_at=datetime.now(timezone.utc).isoformat(), label_access="train_dev_only")
    atomic_json(out / "status.json", status)
    (out / "resolved_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
    code = code_manifest()
    atomic_json(out / "code_manifest.json", code)
    atomic_json(out / "environment_manifest.json", {"python": sys.executable, "version": platform.python_version(),
                                                   "numpy": np.__version__, "threads": os.environ.get("OPENBLAS_NUM_THREADS")})
    try:
        ready = readiness(config)
        atomic_json(out / "model_readiness.json", ready)
        if args.command == "agent-collect":
            from .agent_collect import run_collect
            run_collect(config, out, code, status)
        elif args.command == "p2":
            from .p2 import run_p2
            run_p2(config, out, code, atomic_json, status)
        elif args.command == "pilot":
            from .pilot import run_pilot
            run_pilot(config, out, code, atomic_json, status)
        elif args.command == "preflight":
            status.update(status=ready["status"], reasons=ready["reasons"])
        else:
            records = inventory(config["data"]["root"])
            atomic_json(out / "data_manifest.json", records)
            if args.command == "data":
                origins = select_pilot(records, config["data"]["pilot_origins"], config["data"]["context"], config["data"]["pilot_horizon"])
                atomic_json(out / "origin_manifest.json", origins)
                by_source = {r["source"]: r for r in records}
                audit = []
                for origin in origins:
                    e = load_context(by_source[origin["source"]], origin)
                    audit.append(dict(uid=e.uid, source=e.source, split=e.split, context_shape=list(e.target.shape),
                                      covariate_shape=list(e.covariates.shape), raw_start=e.raw_start, context_end=e.context_end,
                                      target_hash=array_hash(e.target), timestamp_hash=array_hash(e.timestamps),
                                      raw_mask_hash=array_hash(e.observed_mask), covariate_hash=array_hash(e.covariates),
                                      missing_context=int(np.isnan(e.target).sum())))
                atomic_json(out / "context_audit.json", audit)
                status.update(n_origins=len(origins), source_counts=dict(Counter(r["source"] for r in origins)),
                              split_counts=dict(Counter(r["split"] for r in origins)),
                              forecast_status="not_run", future_labels_read=0)
            status.update(status="completed", scope="CPU_input_preparation_only")
    except Exception as exc:
        status.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        status.update(runtime_seconds=time.perf_counter()-start)
        atomic_json(out / "status.json", status)
        print(json.dumps(dict(out=str(out), **status), ensure_ascii=False), flush=True)
    return 2 if status["status"] == "blocked_dependency" else 0


if __name__ == "__main__":
    raise SystemExit(main())
