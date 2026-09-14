"""Validated context-only views. No labels or arbitrary metadata in Episode."""
from dataclasses import dataclass
import hashlib
import json
import numpy as np


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def frozen_array(value):
    a = np.ascontiguousarray(value)
    require(a.dtype.kind in "biuf", "only numeric arrays are allowed")
    # Immutable bytes owner: setflags(write=True) cannot reopen the array.
    return np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape)


def array_hash(value):
    a = np.array(value, copy=True, order="C")
    require(a.dtype.kind in "biuf", "object/complex arrays forbidden")
    if a.dtype.kind == "f":
        a[np.isnan(a)] = np.nan  # canonical NaN payload; no rounding
    header = json.dumps([a.dtype.str, list(a.shape)], separators=(",", ":"))
    return hashlib.sha256(header.encode() + b"\0" + a.tobytes()).hexdigest()


def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Episode:
    uid: str
    source: str
    panel: str
    parent_group: str
    split: str
    target_channel: int
    raw_start: int
    context_end: int  # exclusive row offset in original panel
    horizon: int
    timestamps: np.ndarray  # int64 timestamps or declared common row index
    target: np.ndarray
    covariates: np.ndarray
    availability: np.ndarray  # [L, 1+C], same units as timestamps

    def __post_init__(self):
        for name in ("timestamps", "target", "covariates", "availability"):
            object.__setattr__(self, name, frozen_array(getattr(self, name)))
        t, x, z, a = self.timestamps, self.target, self.covariates, self.availability
        require(bool(self.uid and self.source and self.panel and self.parent_group), "missing identity")
        require(self.split in ("train", "dev", "calibration", "test"), "unknown split")
        require(x.ndim == 1 and len(x) > 0 and x.dtype.kind == "f", "invalid target")
        require(t.shape == x.shape and t.dtype.kind in "iu", "invalid timestamps")
        require(np.all(t[1:] > t[:-1]), "timestamps must strictly increase")
        require(z.ndim == 2 and len(z) == len(x) and z.dtype.kind == "f", "invalid covariates")
        require(a.shape == (len(x), z.shape[1]+1) and a.dtype.kind in "iu", "invalid availability")
        require(not np.isinf(x).any() and not np.isinf(z).any(), "infinity is not missing")
        require(self.raw_start >= 0 and self.context_end-self.raw_start == len(x), "raw interval mismatch")
        require(self.horizon > 0 and self.target_channel >= 0, "invalid horizon/channel")
        visible = np.column_stack((x, z))
        require(not np.any(np.isfinite(visible) & (a > t[-1])), "unavailable value exposed")

    @property
    def observed_mask(self):
        return frozen_array(np.isfinite(self.target))

    @property
    def covariate_mask(self):
        return frozen_array(np.isfinite(self.covariates))


@dataclass(frozen=True)
class Candidate:
    episode_uid: str
    candidate_id: str
    target: np.ndarray
    applicable: bool = True
    reason: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "target", frozen_array(self.target))
        require(self.target.ndim == 1 and self.target.dtype.kind == "f", "invalid candidate")
        require(not np.isinf(self.target).any(), "infinite candidate")
        require(self.applicable or bool(self.reason), "unsupported candidate requires reason")


def verify_impute(episode, candidate):
    require(candidate.episode_uid == episode.uid, "candidate episode mismatch")
    require(candidate.target.shape == episode.target.shape, "candidate changed time axis")
    m = episode.observed_mask
    require(candidate.target.dtype == episode.target.dtype, "candidate changed units/dtype")
    require(candidate.target[m].tobytes() == episode.target[m].tobytes(), "observed write")
