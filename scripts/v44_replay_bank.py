#!/usr/bin/env python3
"""v4.4 Stage D -- score the counterfactuals and build the replay bank (CPU).

Joins the three GPU/CPU stages, scores every ``(episode, action)`` against the
episode's future, and writes one replay record per pair with its full identity,
its metrics, its utility against the reference, and its task-state vector.

The future is read here and only here: this is the historical replay bank, which
is explicitly allowed to see TRAIN futures because it is the method's training
memory.  The deployment selector never touches this file's outputs beyond the
bank's utilities and state vectors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from introact_ts.v44 import masking as M
from introact_ts.v44 import metrics as ME
from introact_ts.v44 import protocol as P
from introact_ts.v44 import state as ST
from introact_ts.v44.hashing import array_hash, json_hash
from introact_ts.v44.replay import ReplayBank, ReplayRecord

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v44/replay"
BANKS = ROOT / "results/v44/banks"

V44_SOURCES = (
    "src/introact_ts/v44/protocol.py",
    "src/introact_ts/v44/masking.py",
    "src/introact_ts/v44/actions.py",
    "src/introact_ts/v44/state.py",
    "src/introact_ts/v44/matching.py",
    "src/introact_ts/v44/metrics.py",
    "src/introact_ts/v44/splits.py",
    "src/introact_ts/v44/replay.py",
    "src/introact_ts/v44/registry.py",
    "src/introact_ts/v44/pipeline.py",
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_sha(root: Path) -> str:
    return json_hash({name: sha(root / name) for name in V44_SOURCES
                      if (root / name).exists()})


def resolved_config_hash() -> str:
    return json_hash({
        "context": P.CONTEXT,
        "horizons": list(P.HORIZONS),
        "patterns": list(P.PATTERNS),
        "severities": list(P.SEVERITIES),
        "main_severity": P.MAIN_SEVERITY,
        "actions": list(P.ACTIONS),
        "reference_action": P.REFERENCE_ACTION,
        "k_grid": list(P.K_GRID),
        "beta_grid": list(P.BETA_GRID),
        "protocol_seed": P.PROTOCOL_SEED,
        "split_ratios": list(P.SPLIT_RATIOS),
        "purge": P.PURGE,
        "seasonal_periods": P.SEASONAL_PERIODS,
    })


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def build(root: Path, block: str, backbone: str) -> dict:
    manifest = json.loads((OUT / "inputs" / f"{block}.json").read_text())
    rows = manifest["rows"]
    forecast_dir = OUT / "forecast" / block / backbone
    status = json.loads((forecast_dir / "status.json").read_text())
    if status.get("status") != "completed":
        raise SystemExit("forecast stage did not complete")
    plan = {(p["episode"], p["action"]): p for p in status["plan"]}

    bank = ReplayBank(backbone, code_sha=code_sha(root),
                      resolved_config_hash=resolved_config_hash())
    code = bank.code_sha
    config = bank.resolved_config_hash
    model = status["identity"]

    unscorable: list[dict] = []
    began = time.perf_counter()

    with np.load(OUT / "inputs" / f"{block}.npz", allow_pickle=False) as store, \
            np.load(OUT / "tsicl" / f"{block}.npz", allow_pickle=False) as tsicl_store, \
            np.load(forecast_dir / "predictions.npz", allow_pickle=False) as predictions:

        def candidate(key: str, action: str) -> np.ndarray | None:
            name = f"{key}|{action}"
            for source in (store, tsicl_store):
                if name in source.files:
                    return source[name]
            return None

        for row in rows:
            key = row["episode"]
            horizon = row["horizon"]
            period = row["period"]
            reference = store[f"{key}|reference"]
            future = store[f"{key}|future"]
            mask = M.build_mask(row["source"], row["parent"], row["origin"],
                                horizon, row["pattern"], row["severity"],
                                length=len(reference), n_channels=row["n_channels"])
            mask_hash = array_hash(mask)

            reference_plan = plan.get((key, P.REFERENCE_ACTION))
            if reference_plan is None or not reference_plan.get("applicable"):
                unscorable.append({"episode": key,
                                   "reason": "reference forecast unavailable"})
                continue
            reference_prediction = predictions[
                f"{reference_plan['input_hash']}|h{horizon}"]

            mask_features = ST.mask_features_from_mask(mask)
            context_features = ST.context_features(reference, period)
            reference_features = ST.reference_forecast_features(
                reference_prediction, reference)
            scale = ST.robust_scale(reference)
            reference_metrics = ME.forecast_metrics(
                future, reference_prediction, mase_scale=row["mase_scale"],
                rmsse_scale=row["rmsse_scale"])
            reference_loss = reference_metrics["mase"]

            for action in P.ACTIONS:
                item = plan.get((key, action))
                target = candidate(key, action)
                failure = None
                unsupported = None
                if item is None:
                    unsupported = "no plan entry"
                elif not item.get("applicable"):
                    unsupported = item.get("reason") or "unsupported"
                if target is None and unsupported is None:
                    unsupported = "candidate array missing"

                record_metrics = {"mase": None, "mse": None, "mae": None,
                                  "rmsse": None}
                prediction = None
                if unsupported is None:
                    name = f"{item['input_hash']}|h{horizon}"
                    if name not in predictions.files:
                        failure = item.get("reason") or "backbone produced no prediction"
                    else:
                        prediction = predictions[name]
                        try:
                            record_metrics = ME.forecast_metrics(
                                future, prediction, mase_scale=row["mase_scale"],
                                rmsse_scale=row["rmsse_scale"])
                        except ValueError as exc:
                            failure = f"{type(exc).__name__}: {exc}"

                utility = None
                if (failure is None and unsupported is None
                        and record_metrics["mase"] is not None
                        and reference_loss is not None):
                    utility = float(reference_loss - record_metrics["mase"])

                intervention = (ST.intervention_features(target, reference, scale)
                                if target is not None
                                else np.zeros(len(ST.INTERVENTION_FEATURES)))

                record = ReplayRecord(
                    source=row["source"],
                    parent=row["parent"],
                    origin=row["origin"],
                    horizon=horizon,
                    pattern=row["pattern"],
                    severity=row["severity"],
                    mask_hash=mask_hash,
                    backbone=backbone,
                    backbone_revision=model.get("revision", ""),
                    action=action,
                    input_hash=(item or {}).get("input_hash") or "",
                    prediction_hash=(array_hash(prediction)
                                     if prediction is not None else ""),
                    mask_features=mask_features,
                    context_features=context_features,
                    intervention_features=intervention,
                    reference_forecast_features=reference_features,
                    mase_scale=row["mase_scale"],
                    mase_scale_id=row["mase_scale_id"],
                    mase=record_metrics["mase"],
                    mse=record_metrics["mse"],
                    mae=record_metrics["mae"],
                    rmsse=record_metrics["rmsse"],
                    utility_vs_reference=utility,
                    runtime=float(item.get("runtime_seconds") or 0.0) if item else 0.0,
                    failure=failure,
                    alias=(item or {}).get("alias_of"),
                    unsupported=unsupported,
                    code_sha=code,
                    resolved_config_hash=config,
                    variant=key,
                    context_length=P.CONTEXT,
                    model_family=backbone,
                    checkpoint=str(model.get("repo_id", "")),
                    revision=str(model.get("revision", "")),
                    dtype=str(model.get("dtype", "")),
                    generation_config_hash=json_hash({
                        "backbone": backbone,
                        "horizon": horizon,
                        "point_rule": model.get("native_settings",
                                                {}).get("point", "native median"),
                    }),
                    forecast=(np.asarray(prediction, dtype=np.float64)
                              if prediction is not None else np.zeros(horizon)),
                    target=np.asarray(future, dtype=np.float64),
                )
                bank.add(record)

    banks_dir = BANKS / block
    info = bank.save(banks_dir, name=f"replay_bank_{backbone}")
    support = bank.support()
    summary = {
        "stage": "v44-replay-bank-D",
        "block": block,
        "backbone": backbone,
        "records": len(bank),
        "episodes": len({r.episode_uid for r in bank.records}),
        "unscorable_episodes": unscorable,
        "support": support,
        "per_source_support": dict(sorted(Counter(
            r.source for r in bank.records if r.scored).items())),
        "per_pattern_support": dict(sorted(Counter(
            r.pattern for r in bank.records if r.scored).items())),
        "per_severity_support": {str(k): v for k, v in sorted(Counter(
            r.severity for r in bank.records if r.scored).items())},
        "utility_mean_per_action": {
            action: float(np.mean([r.utility_vs_reference for r in bank.records
                                   if r.scored and r.action == action]))
            for action in P.ACTIONS
            if any(r.scored and r.action == action for r in bank.records)},
        "code_sha": code,
        "resolved_config_hash": config,
        "runtime_seconds": time.perf_counter() - began,
        "bank": info,
        "heldout_labels_read": 0,
    }
    write(banks_dir / f"replay_bank_{backbone}.summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--block", default="replay_fit",
                        choices=["replay_fit", "gate", "train_eval"])
    parser.add_argument("--backbone", default="bolt",
                        choices=list(P.DEV_BACKBONES))
    args = parser.parse_args()
    summary = build(Path(args.root), args.block, args.backbone)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
