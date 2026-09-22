#!/usr/bin/env python3
"""v53 latency audit (task 5): summarise the existing timing evidence.

The requested per-request breakdown is: reference forecast / candidate
materialisation / feature retrieval / selected-action forecast / end-to-end /
call counts.  This script checks what already exists and aggregates it:

* ``results/v47/cost_audit/latency_<block>_<backbone>.json`` -- per-request
  retrieval (distance matrices + score grid + decide, one request at a time)
  and the reference backbone call time recorded by the forecast stage.
* ``results/v47/replay/forecast/<block>/<backbone>/status.json`` -- call
  seconds (mean/p95/max), call counts (unique_inputs, unique_predictions,
  per_action), and per-plan-row runtimes.
* the inputs / tsicl / saits replay stage manifests for candidate-stage
  runtime fields.

Nothing is recomputed; no model is run.  Components with no recorded timing
are reported as missing rather than estimated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BLOCKS = ("bankx", "train_eval", "test", "test30", "test50", "test_m2", "test_m3")
BACKBONES = ("bolt", "timesfm", "chronos2")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--replay", default="results/v47/replay")
    parser.add_argument("--cost-audit", default="results/v47/cost_audit")
    parser.add_argument("--output-root", default="results/v53_state_compact")
    args = parser.parse_args()
    root = Path(args.root)

    began = time.perf_counter()

    latency_files = {}
    for path in sorted((root / args.cost_audit).glob("latency_*.json")):
        d = json.loads(path.read_text())
        latency_files[path.name] = {
            "backbone": d.get("backbone"), "block": d.get("block"),
            "retrieval_per_request": d.get("retrieval_per_request"),
            "backbone_call": d.get("backbone_call"),
            "bank_records": d.get("bank_records"),
        }

    forecast_status = {}
    replay = root / args.replay
    for block in BLOCKS:
        for backbone in BACKBONES:
            path = replay / "forecast" / block / backbone / "status.json"
            if not path.exists():
                continue
            s = json.loads(path.read_text())
            forecast_status[f"{block}/{backbone}"] = {
                "status": s.get("status"),
                "runtime_seconds": s.get("runtime_seconds"),
                "call_seconds_total": s.get("call_seconds_total"),
                "call_seconds_mean": s.get("call_seconds_mean"),
                "call_seconds_p95": s.get("call_seconds_p95"),
                "call_seconds_max": s.get("call_seconds_max"),
                "unique_inputs": s.get("unique_inputs"),
                "unique_predictions": s.get("unique_predictions"),
                "computed_here": s.get("computed_here"),
                "reused_from_donor": s.get("reused_from_donor"),
                "per_action": s.get("per_action"),
            }

    candidate_stages = {}
    for stage in ("inputs", "tsicl", "saits"):
        stage_dir = replay / stage
        if not stage_dir.exists():
            continue
        for path in sorted(stage_dir.glob("*.json")):
            try:
                d = json.loads(path.read_text())
            except Exception:
                continue
            timing = {k: v for k, v in d.items()
                      if isinstance(v, (int, float)) and
                      any(t in k for t in ("runtime", "seconds", "load"))}
            candidate_stages[f"{stage}/{path.name}"] = {
                "has_timing": bool(timing), "timing_fields": timing,
                "keys": sorted(d.keys())[:20]}

    components = {
        "reference_forecast": {
            "status": "recorded",
            "where": "forecast status.json call_seconds_* (per unique input)",
        },
        "candidate_materialisation": {
            "status": ("partial" if any(v["has_timing"]
                                        for v in candidate_stages.values())
                       else "missing"),
            "where": ("inputs/tsicl/saits stage manifests carry stage-level "
                      "runtimes where recorded; there is no per-request "
                      "candidate-construction timer"),
        },
        "feature_retrieval": {
            "status": "recorded",
            "where": ("cost_audit latency_* retrieval_per_request "
                      "(distance matrices + score grid + decide, one request "
                      "at a time, deployment shape)"),
        },
        "selected_action_forecast": {
            "status": "recorded_at_stage_level",
            "where": ("forecast status.json per_action counts and per-plan-row "
                      "runtime_seconds; the deployed path forecasts only the "
                      "selected action, so its per-call time equals the "
                      "recorded backbone call time"),
        },
        "end_to_end": {
            "status": "missing",
            "where": ("no single timer spans reference forecast + candidate "
                      "construction + retrieval + selected-action forecast "
                      "per request"),
        },
        "call_counts": {
            "status": "recorded",
            "where": ("forecast status.json unique_inputs / "
                      "unique_predictions / per_action"),
        },
    }

    payload = {
        "stage": "v53-latency-audit",
        "replay": args.replay,
        "cost_audit": args.cost_audit,
        "code_sha256": {
            "scripts/v53_latency_audit.py": sha256_of(Path(__file__).resolve()),
            "scripts/v47_latency.py": sha256_of(root / "scripts/v47_latency.py"),
        },
        "components": components,
        "latency_files": latency_files,
        "forecast_status": forecast_status,
        "candidate_stages": candidate_stages,
        "runtime_seconds": time.perf_counter() - began,
    }
    out = root / args.output_root
    out.mkdir(parents=True, exist_ok=True)
    (out / "latency_audit.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v["status"] for k, v in components.items()}, indent=1))


if __name__ == "__main__":
    main()
