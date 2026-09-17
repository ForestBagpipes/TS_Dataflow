"""Counterfactual replay records and their cache identity (task book §11, §34).

A replay record is the complete, auditable description of one historical
``(episode, action)`` execution: what went in, what came out, how it was
scored, and which frozen identities it was produced under.  Nothing about it
may be inferred later -- if a field is not here, it does not exist.

Cache identity deliberately binds far more than the action name and the window
id.  Two predictions may only be reused when *every* identity field agrees,
including the model revision, the dtype and the resolved generation config.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .hashing import array_hash, json_hash
from .protocol import ACTIONS

#: The minimum record schema required by the task book (§11).  Kept as an
#: explicit tuple so a missing field is a test failure rather than a shrug.
REQUIRED_FIELDS = (
    "source", "parent", "origin", "horizon", "pattern", "severity",
    "mask_hash", "backbone", "backbone_revision", "action",
    "input_hash", "prediction_hash",
    "mask_features", "context_features", "intervention_features",
    "reference_forecast_features",
    "mase_scale", "mase_scale_id",
    "mase", "mse", "mae", "rmsse", "utility_vs_reference",
    "runtime", "failure", "alias", "unsupported",
    "code_sha", "resolved_config_hash",
)

#: Identity fields that participate in a cache key (§34).  ``prediction_hash``
#: is excluded because it is the *result* being cached, and ``runtime`` is
#: excluded because it is a measurement rather than an input.
CACHE_IDENTITY_FIELDS = (
    "source", "parent", "origin", "context_length", "horizon", "pattern",
    "severity", "mask_hash", "input_hash", "action", "model_family",
    "checkpoint", "revision", "dtype", "generation_config_hash",
)


@dataclass
class ReplayRecord:
    """One historical ``(episode, action)`` counterfactual execution."""

    source: str
    parent: str
    origin: int
    horizon: int
    pattern: str
    severity: float
    mask_hash: str
    backbone: str
    backbone_revision: str
    action: str
    input_hash: str
    prediction_hash: str
    mask_features: np.ndarray
    context_features: np.ndarray
    intervention_features: np.ndarray
    reference_forecast_features: np.ndarray
    mase_scale: float | None
    mase_scale_id: str
    mase: float | None
    mse: float | None
    mae: float | None
    rmsse: float | None
    utility_vs_reference: float | None
    runtime: float = 0.0
    failure: str | None = None
    alias: str | None = None
    unsupported: str | None = None
    code_sha: str = ""
    resolved_config_hash: str = ""
    variant: str = ""
    context_length: int = 512
    model_family: str = ""
    checkpoint: str = ""
    revision: str = ""
    dtype: str = ""
    generation_config_hash: str = ""
    forecast: np.ndarray = field(default_factory=lambda: np.zeros(0))
    target: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"unregistered action {self.action!r}")
        if not self.model_family:
            object.__setattr__(self, "model_family", self.backbone)
        if not self.revision:
            object.__setattr__(self, "revision", self.backbone_revision)
        for name in ("mask_features", "context_features",
                     "intervention_features", "reference_forecast_features"):
            value = np.asarray(getattr(self, name), dtype=np.float64)
            if value.ndim != 1 or not np.isfinite(value).all():
                raise ValueError(f"{name} must be a finite 1-D vector")
            object.__setattr__(self, name, value)
        if not self.variant:
            object.__setattr__(self, "variant", self.episode_uid)

    @property
    def episode_uid(self) -> str:
        return (f"{self.source}-{self.parent}-o{self.origin}-h{self.horizon}"
                f"-{self.pattern}-s{int(round(self.severity * 100)):02d}")

    @property
    def state_vector(self) -> np.ndarray:
        return np.concatenate([self.mask_features, self.context_features,
                               self.intervention_features,
                               self.reference_forecast_features])

    @property
    def scored(self) -> bool:
        return (self.failure is None and self.utility_vs_reference is not None
                and self.mase is not None)

    def cache_identity(self) -> dict:
        identity = {name: getattr(self, name) for name in CACHE_IDENTITY_FIELDS}
        identity["severity"] = float(self.severity)
        return identity

    def cache_key(self) -> str:
        return json_hash(self.cache_identity())

    def missing_fields(self) -> list[str]:
        return [name for name in REQUIRED_FIELDS if not hasattr(self, name)]

    def meta(self) -> dict:
        """JSON-safe view; the two array payloads are stored separately."""
        payload = asdict(self)
        for key in ("forecast", "target", "mask_features", "context_features",
                    "intervention_features", "reference_forecast_features"):
            payload.pop(key, None)
        payload.update({
            "mask_features": self.mask_features.tolist(),
            "context_features": self.context_features.tolist(),
            "intervention_features": self.intervention_features.tolist(),
            "reference_forecast_features": self.reference_forecast_features.tolist(),
            "cache_key": self.cache_key(),
            "state_vector_length": int(self.state_vector.size),
        })
        return payload


def make_cache_key(*, source: str, parent: str, origin: int, context_length: int,
                   horizon: int, pattern: str, severity: float, mask_hash: str,
                   input_hash: str, action: str, model_family: str,
                   checkpoint: str, revision: str, dtype: str,
                   generation_config: dict) -> str:
    """Cache key from the frozen identity tuple (§34).

    Deliberately not keyed on the action name alone, nor on the window id: two
    requests that differ only in their mask, their severity or the model dtype
    must never share a cached prediction.
    """
    return json_hash({
        "source": source,
        "parent": parent,
        "origin": int(origin),
        "context_length": int(context_length),
        "horizon": int(horizon),
        "pattern": pattern,
        "severity": float(severity),
        "mask_hash": mask_hash,
        "input_hash": input_hash,
        "action": action,
        "model_family": model_family,
        "checkpoint": checkpoint,
        "revision": revision,
        "dtype": dtype,
        "generation_config_hash": json_hash(generation_config),
    })


class ReplayBank:
    """The TRAIN-only counterfactual memory of one backbone."""

    def __init__(self, backbone: str, *, code_sha: str = "",
                 resolved_config_hash: str = ""):
        self.backbone = backbone
        self.code_sha = code_sha
        self.resolved_config_hash = resolved_config_hash
        self.records: list[ReplayRecord] = []
        self._keys: dict[str, int] = {}

    def __len__(self) -> int:
        return len(self.records)

    def add(self, record: ReplayRecord) -> bool:
        """Insert one record; returns ``False`` if the cache key already exists."""
        key = record.cache_key()
        if key in self._keys:
            existing = self.records[self._keys[key]]
            if existing.prediction_hash != record.prediction_hash:
                raise RuntimeError("cache identity collision with a different prediction")
            return False
        self._keys[key] = len(self.records)
        self.records.append(record)
        return True

    # -- retrieval ----------------------------------------------------------

    def by_action(self, action: str, *, exclude_parent: str | None = None,
                  block: str | None = None,
                  block_of: dict[str, str] | None = None) -> list[ReplayRecord]:
        """Records for one action, optionally restricted to a block.

        ``exclude_parent`` supports leave-one-parent-out retrieval; ``block``
        with ``block_of`` enforces that a lookup never crosses into an illegal
        split (§18 test 7).
        """
        out = []
        for record in self.records:
            if record.action != action or not record.scored:
                continue
            if exclude_parent is not None and record.parent == exclude_parent:
                continue
            if block is not None:
                if block_of is None:
                    raise ValueError("block filtering requires block_of")
                if block_of.get(record.parent) != block:
                    continue
            out.append(record)
        return out

    def actions(self) -> list[str]:
        return sorted({record.action for record in self.records})

    def support(self) -> dict:
        """Per-action / per-source / per-pattern support and alias statistics."""
        def tally(key_fn) -> dict:
            out: dict[str, int] = {}
            for record in self.records:
                out[key_fn(record)] = out.get(key_fn(record), 0) + 1
            return dict(sorted(out.items()))

        total = len(self.records)
        aliased = sum(1 for r in self.records if r.alias)
        unsupported = sum(1 for r in self.records if r.unsupported)
        failed = sum(1 for r in self.records if r.failure)
        scored = sum(1 for r in self.records if r.scored)
        by_episode: dict[str, set[str]] = {}
        for record in self.records:
            if record.scored:
                by_episode.setdefault(record.episode_uid, set()).add(
                    record.prediction_hash)
        distinct = list(by_episode.values())
        return {
            "backbone": self.backbone,
            "records": total,
            "scored": scored,
            "per_action": tally(lambda r: r.action),
            "per_source": tally(lambda r: r.source),
            "per_pattern": tally(lambda r: r.pattern),
            "alias_ratio": 0.0 if total == 0 else aliased / total,
            "unsupported_ratio": 0.0 if total == 0 else unsupported / total,
            "failure_ratio": 0.0 if total == 0 else failed / total,
            "episodes": len(by_episode),
            "distinct_prediction_ratio": (
                0.0 if not distinct else float(np.mean(
                    [len(v) / max(1, len(ACTIONS)) for v in distinct]))),
        }

    # -- persistence --------------------------------------------------------

    def save(self, directory: str | Path, *, name: str | None = None) -> dict:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stem = name or f"replay_bank_{self.backbone}"
        arrays: dict[str, np.ndarray] = {}
        for i, record in enumerate(self.records):
            arrays[f"{i:07d}|forecast"] = np.asarray(record.forecast, dtype=np.float64)
            arrays[f"{i:07d}|target"] = np.asarray(record.target, dtype=np.float64)
        npz_path = directory / f"{stem}.npz"
        with npz_path.open("wb") as handle:
            np.savez(handle, **arrays)
        meta_path = directory / f"{stem}.json"
        meta = {
            "backbone": self.backbone,
            "code_sha": self.code_sha,
            "resolved_config_hash": self.resolved_config_hash,
            "records": [record.meta() for record in self.records],
            "support": self.support(),
            "arrays": str(npz_path.name),
            "arrays_sha256": _file_sha(npz_path),
        }
        meta_path.write_text(json.dumps(meta, indent=1, allow_nan=False))
        return {"meta": str(meta_path), "arrays": str(npz_path),
                "records": len(self.records)}

    @classmethod
    def load(cls, directory: str | Path, *, name: str) -> "ReplayBank":
        directory = Path(directory)
        meta = json.loads((directory / f"{name}.json").read_text())
        bank = cls(meta["backbone"], code_sha=meta.get("code_sha", ""),
                   resolved_config_hash=meta.get("resolved_config_hash", ""))
        with np.load(directory / meta["arrays"], allow_pickle=False) as arrays:
            for i, payload in enumerate(meta["records"]):
                payload = dict(payload)
                forecast = arrays[f"{i:07d}|forecast"]
                target = arrays[f"{i:07d}|target"]
                payload.pop("cache_key", None)
                payload.pop("state_vector_length", None)
                for key in ("mask_features", "context_features",
                            "intervention_features", "reference_forecast_features"):
                    payload[key] = np.asarray(payload[key], dtype=np.float64)
                bank.records.append(ReplayRecord(forecast=forecast, target=target,
                                                 **payload))
        bank._keys = {record.cache_key(): i for i, record in enumerate(bank.records)}
        return bank


def _file_sha(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prediction_hash(prediction: np.ndarray) -> str:
    return array_hash(np.asarray(prediction, dtype=np.float64))
