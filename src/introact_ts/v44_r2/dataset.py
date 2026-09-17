"""The r2 episode view: one TRAIN block, one backbone, streamed from v4.4 artifacts.

This loader reads exactly the artifacts the v4.4 replay bank was built from
(``results/v44/replay/{inputs,tsicl,forecast}``).  It deliberately does **not**
reuse the v4.4 replay bank, because the bank stores the v4.4 feature blocks and
the r2 feature set is different -- rebuilding the rows from the frozen inputs is
the only way to guarantee that the r2 features and the realised losses describe
the same execution.

Nothing here reads calibration or test rows; the loader is restricted to the
three TRAIN blocks by construction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..v44 import masking as M
from ..v44 import metrics as ME
from ..v44 import protocol as P
from ..v44 import state as ST
from ..v44.hashing import array_hash
from . import features as F

REPLAY = "results/v44/replay"
TRAIN_BLOCKS = P.SPLIT_NAMES


@dataclass
class ActionView:
    """One ``(episode, action)`` execution as r2 needs to see it."""

    action: str
    applicable: bool
    reason: str | None
    alias_of: str | None
    input_hash: str
    prediction_hash: str
    loss: float | None = None
    mse: float | None = None
    mae: float | None = None
    rmsse: float | None = None
    utility: float | None = None
    runtime: float = 0.0
    features: np.ndarray | None = None

    @property
    def executable(self) -> bool:
        """Has a realised loss *and* a feature row: usable for ranking."""
        return self.loss is not None and self.features is not None


@dataclass
class EpisodeView:
    """One request and every legal action's realised loss on it."""

    episode: str
    source: str
    parent: str
    origin: int
    horizon: int
    pattern: str
    severity: float
    block: str
    period: int
    n_channels: int
    mase_scale: float | None
    rmsse_scale: float | None
    mase_scale_id: str
    future: np.ndarray
    reference_target: np.ndarray
    actions: dict[str, ActionView] = field(default_factory=dict)

    @property
    def reference(self) -> ActionView:
        return self.actions[P.REFERENCE_ACTION]

    def legal(self) -> tuple[str, ...]:
        """Actions that actually executed, with KEEP required to be present."""
        usable = [a for a in P.ACTIONS if self.actions[a].executable]
        if P.REFERENCE_ACTION not in usable:
            return ()
        return tuple(usable)

    def oracle(self) -> tuple[str | None, float | None]:
        """Post-hoc best legal action; diagnostic only, never deployable."""
        scored = [(a, self.actions[a].loss) for a in self.legal()
                  if self.actions[a].loss is not None]
        if not scored:
            return None, None
        return min(scored, key=lambda item: item[1])

    def opportunity(self) -> float | None:
        """``Delta_i = L_keep - L*``: how much a perfect chooser could gain."""
        action, best = self.oracle()
        if action is None or best is None:
            return None
        return float(self.reference.loss - best)

    def losses(self) -> dict[str, float]:
        return {a: self.actions[a].loss for a in self.legal()}


def _candidate(store, tsicl, key: str, action: str) -> np.ndarray | None:
    name = f"{key}|{action}"
    for source in (store, tsicl):
        if name in source.files:
            return source[name]
    return None


def load_block(root: str | Path, block: str, backbone: str,
               *, horizons=P.HORIZONS) -> list[EpisodeView]:
    """Load one TRAIN block for one backbone."""
    if block not in TRAIN_BLOCKS:
        raise ValueError(f"{block!r} is not a TRAIN block; refusing to load it")
    root = Path(root)
    replay = root / REPLAY
    manifest = json.loads((replay / "inputs" / f"{block}.json").read_text())
    forecast_dir = replay / "forecast" / block / backbone
    status = json.loads((forecast_dir / "status.json").read_text())
    if status.get("status") != "completed":
        raise SystemExit(f"forecast stage for {block}/{backbone} is not complete")
    plan = {(p["episode"], p["action"]): p for p in status["plan"]}

    episodes: list[EpisodeView] = []
    with np.load(replay / "inputs" / f"{block}.npz", allow_pickle=False) as store, \
            np.load(replay / "tsicl" / f"{block}.npz", allow_pickle=False) as tsicl, \
            np.load(forecast_dir / "predictions.npz", allow_pickle=False) as predictions:

        for row in manifest["rows"]:
            if row["horizon"] not in horizons:
                continue
            key = row["episode"]
            horizon = int(row["horizon"])
            reference_target = store[f"{key}|reference"]
            future = store[f"{key}|future"]
            mask = M.build_mask(row["source"], row["parent"], row["origin"],
                                horizon, row["pattern"], row["severity"],
                                length=len(reference_target),
                                n_channels=row["n_channels"])
            episode_state = F.episode_state(mask, reference_target, row["period"])
            scale = ST.robust_scale(reference_target)

            episode = EpisodeView(
                episode=key, source=row["source"], parent=row["parent"],
                origin=int(row["origin"]), horizon=horizon,
                pattern=row["pattern"], severity=float(row["severity"]),
                block=block, period=int(row["period"]),
                n_channels=int(row["n_channels"]),
                mase_scale=row["mase_scale"], rmsse_scale=row["rmsse_scale"],
                mase_scale_id=row["mase_scale_id"], future=future,
                reference_target=reference_target,
            )

            reference_loss = None
            for action in P.ACTIONS:
                item = plan.get((key, action))
                candidate = _candidate(store, tsicl, key, action)
                applicable = bool(item and item.get("applicable")
                                  and candidate is not None)
                prediction = None
                if applicable:
                    name = f"{item['input_hash']}|h{horizon}"
                    if name in predictions.files:
                        prediction = predictions[name]
                    else:
                        applicable = False

                view = ActionView(
                    action=action, applicable=applicable,
                    reason=(item or {}).get("reason"),
                    alias_of=(item or {}).get("alias_of"),
                    input_hash=(item or {}).get("input_hash") or "",
                    prediction_hash=(array_hash(prediction)
                                     if prediction is not None else ""),
                    runtime=float((item or {}).get("runtime_seconds") or 0.0),
                )
                if applicable:
                    view.features = F.assert_dimension(F.action_features(
                        action=action, episode_state_vector=episode_state,
                        candidate_target=candidate,
                        reference_target=reference_target, scale=scale))
                    try:
                        values = ME.forecast_metrics(
                            future, prediction, mase_scale=row["mase_scale"],
                            rmsse_scale=row["rmsse_scale"])
                    except ValueError:
                        view.features = None
                    else:
                        view.loss = values["mase"]
                        view.mse = values["mse"]
                        view.mae = values["mae"]
                        view.rmsse = values["rmsse"]
                if action == P.REFERENCE_ACTION:
                    reference_loss = view.loss
                episode.actions[action] = view

            for view in episode.actions.values():
                if view.loss is not None and reference_loss is not None:
                    view.utility = float(reference_loss - view.loss)
            episodes.append(episode)
    return episodes


def summarise(episodes: list[EpisodeView]) -> dict:
    """Block-level diagnostics: support, degeneracy and opportunity spread."""
    from collections import Counter

    support = Counter()
    unsupported = Counter()
    legal_sizes = Counter()
    degenerate = 0
    opportunities = []
    for episode in episodes:
        legal = episode.legal()
        legal_sizes[len(legal)] += 1
        for action in P.ACTIONS:
            view = episode.actions[action]
            if view.executable:
                support[action] += 1
            elif view.reason:
                unsupported[view.reason] += 1
        value = episode.opportunity()
        if value is None:
            continue
        opportunities.append(value)
        if value <= 1e-9:
            degenerate += 1
    array = np.asarray(opportunities, dtype=np.float64)
    return {
        "episodes": len(episodes),
        "per_action_support": dict(sorted(support.items())),
        "unsupported_reasons": dict(sorted(unsupported.items())),
        "legal_size_histogram": {str(k): v for k, v in sorted(legal_sizes.items())},
        "oracle_degenerate": degenerate,
        "oracle_degenerate_ratio": (degenerate / len(episodes)) if episodes else None,
        "opportunity_quantiles": (
            {q: float(np.quantile(array, q)) for q in (0.25, 0.5, 0.75, 0.9)}
            if array.size else {}),
    }
