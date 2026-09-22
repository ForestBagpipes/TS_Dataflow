"""Episode catalogs: everything a selector needs about one block (task book §17–§22).

An episode catalog holds, for one episode and one backbone, the per-action state
vector, the per-action prediction and the per-action metrics.  It is built by
re-reading the three replay stages, which means the evaluation path and the
replay-bank path cannot disagree about what an action's input was.

The catalog is used two ways:

* by the **gate**, which needs the state vectors and the realised losses to
  choose ``K`` and ``beta``;
* by the **evaluation**, which needs, in addition, the prediction of whichever
  action the selector picks, plus the reference prediction.

Note the direction of information flow: the selector sees only the state vector
of each action (which is built from inputs and the *reference* forecast), and
the realised loss is attached afterwards for scoring.  Pre-computing the whole
catalog therefore does not leak anything into the decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import masking as M
from . import metrics as ME
from . import protocol as P
from . import state as ST
from .hashing import array_hash

REPLAY = "results/v44/replay"


@dataclass
class ActionEntry:
    action: str
    applicable: bool
    reason: str | None
    alias_of: str | None
    input_hash: str
    prediction_hash: str
    prediction: np.ndarray | None
    state_vector: np.ndarray | None
    mase: float | None = None
    mse: float | None = None
    mae: float | None = None
    rmsse: float | None = None
    utility: float | None = None
    runtime: float = 0.0

    @property
    def scored(self) -> bool:
        return self.applicable and self.prediction is not None


@dataclass
class EpisodeCatalog:
    episode: str
    source: str
    parent: str
    origin: int
    horizon: int
    pattern: str
    severity: float
    block: str
    period: int
    mase_scale: float | None
    rmsse_scale: float | None
    mase_scale_id: str
    future: np.ndarray
    reference_target: np.ndarray
    actions: dict[str, ActionEntry] = field(default_factory=dict)

    @property
    def reference(self) -> ActionEntry:
        return self.actions[P.REFERENCE_ACTION]

    @property
    def reference_prediction(self) -> np.ndarray:
        return self.reference.prediction

    @property
    def reference_mase(self) -> float | None:
        return self.reference.mase

    def legal(self) -> tuple[str, ...]:
        """Actions with a usable execution; KEEP is always the reference."""
        usable = [a for a in P.ACTIONS
                  if self.actions[a].applicable and self.actions[a].prediction is not None]
        if P.REFERENCE_ACTION not in usable:
            return ()
        return tuple(usable)

    def oracle(self) -> tuple[str | None, float | None]:
        """The post-hoc best legal action; diagnostic only (§17 C4)."""
        scored = [(a, self.actions[a].mase) for a in self.legal()
                  if self.actions[a].mase is not None]
        if not scored:
            return None, None
        best = min(scored, key=lambda kv: kv[1])
        return best[0], best[1]


def load_catalog(root: str | Path, block: str, backbone: str) -> list[EpisodeCatalog]:
    root = Path(root)
    replay = root / REPLAY
    manifest = json.loads((replay / "inputs" / f"{block}.json").read_text())
    forecast_dir = replay / "forecast" / block / backbone
    status = json.loads((forecast_dir / "status.json").read_text())
    if status.get("status") != "completed":
        raise SystemExit(f"forecast stage for {block}/{backbone} is not complete")
    plan = {(p["episode"], p["action"]): p for p in status["plan"]}

    catalogs: list[EpisodeCatalog] = []
    saits_path = replay / "saits" / f"{block}.npz"
    saits_store = (np.load(saits_path, allow_pickle=False)
                   if saits_path.exists() else None)

    with np.load(replay / "inputs" / f"{block}.npz", allow_pickle=False) as store, \
            np.load(replay / "tsicl" / f"{block}.npz", allow_pickle=False) as tsicl, \
            np.load(forecast_dir / "predictions.npz", allow_pickle=False) as predictions:

        stores = ((store, tsicl) if saits_store is None
                  else (store, tsicl, saits_store))

        def candidate(key: str, action: str) -> np.ndarray | None:
            name = f"{key}|{action}"
            for source in stores:
                if name in source.files:
                    return source[name]
            return None

        for row in manifest["rows"]:
            key = row["episode"]
            horizon = row["horizon"]
            reference_target = store[f"{key}|reference"]
            future = store[f"{key}|future"]
            mask = M.build_mask(row["source"], row["parent"], row["origin"],
                                horizon, row["pattern"], row["severity"],
                                length=len(reference_target),
                                n_channels=row["n_channels"])
            mask_features = ST.mask_features_from_mask(mask)
            context_features = ST.context_features(reference_target, row["period"])

            reference_plan = plan.get((key, P.REFERENCE_ACTION))
            reference_prediction = None
            if reference_plan and reference_plan.get("applicable"):
                name = f"{reference_plan['input_hash']}|h{horizon}"
                if name in predictions.files:
                    reference_prediction = predictions[name]
            if reference_prediction is None:
                continue
            reference_features = ST.reference_forecast_features(
                reference_prediction, reference_target)
            scale = ST.robust_scale(reference_target)

            catalog = EpisodeCatalog(
                episode=key, source=row["source"], parent=row["parent"],
                origin=row["origin"], horizon=horizon, pattern=row["pattern"],
                severity=row["severity"], block=block, period=row["period"],
                mase_scale=row["mase_scale"], rmsse_scale=row["rmsse_scale"],
                mase_scale_id=row["mase_scale_id"], future=future,
                reference_target=reference_target,
            )

            reference_loss = None
            for action in P.ACTIONS:
                item = plan.get((key, action))
                target = candidate(key, action)
                applicable = bool(item and item.get("applicable") and target is not None)
                prediction = None
                if applicable:
                    name = f"{item['input_hash']}|h{horizon}"
                    if name in predictions.files:
                        prediction = predictions[name]
                    else:
                        applicable = False
                entry = ActionEntry(
                    action=action, applicable=applicable,
                    reason=(item or {}).get("reason"),
                    alias_of=(item or {}).get("alias_of"),
                    input_hash=(item or {}).get("input_hash") or "",
                    prediction_hash=(array_hash(prediction)
                                     if prediction is not None else ""),
                    prediction=prediction,
                    state_vector=(np.concatenate([
                        mask_features, context_features,
                        ST.intervention_features(target, reference_target, scale),
                        reference_features]) if target is not None else None),
                    runtime=float((item or {}).get("runtime_seconds") or 0.0),
                )
                if prediction is not None:
                    try:
                        metrics = ME.forecast_metrics(
                            future, prediction, mase_scale=row["mase_scale"],
                            rmsse_scale=row["rmsse_scale"])
                        entry.mase = metrics["mase"]
                        entry.mse = metrics["mse"]
                        entry.mae = metrics["mae"]
                        entry.rmsse = metrics["rmsse"]
                    except ValueError:
                        entry.applicable = False
                if action == P.REFERENCE_ACTION:
                    reference_loss = entry.mase
                catalog.actions[action] = entry

            for entry in catalog.actions.values():
                if entry.mase is not None and reference_loss is not None:
                    entry.utility = float(reference_loss - entry.mase)
            catalogs.append(catalog)
    return catalogs


def catalog_losses(catalogs: list[EpisodeCatalog]) -> dict[tuple[str, str], float]:
    """``(source, parent) -> mean reference MASE`` over the block's variants."""
    from collections import defaultdict

    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for catalog in catalogs:
        if catalog.reference_mase is not None:
            buckets[(catalog.source, catalog.parent)].append(catalog.reference_mase)
    return {key: float(np.mean(values)) for key, values in buckets.items()}


def to_records(catalogs: list[EpisodeCatalog], *, method: str, backbone: str,
               selected: dict[str, str] | None = None) -> list[dict]:
    """Flatten catalogs into metric records for the aggregation ladder."""
    records = []
    for catalog in catalogs:
        action = (selected or {}).get(catalog.episode, P.REFERENCE_ACTION)
        entry = catalog.actions.get(action) or catalog.reference
        records.append({
            "method": method,
            "backbone": backbone,
            "source": catalog.source,
            "parent": catalog.parent,
            "variant": catalog.episode,
            "horizon": catalog.horizon,
            "pattern": catalog.pattern,
            "severity": catalog.severity,
            "mase": entry.mase,
            "mse": entry.mse,
            "mae": entry.mae,
            "rmsse": entry.rmsse,
            "selected_action": action,
            "applicable": entry.applicable,
        })
    return records
