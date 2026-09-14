"""Evaluation-only future access; never imported by candidate generators."""
from dataclasses import dataclass
import numpy as np
from .schemas import array_hash, frozen_array, require


@dataclass(frozen=True)
class TaskTarget:
    episode_uid: str
    split: str
    values: np.ndarray
    mask: np.ndarray

    def __post_init__(self):
        require(self.split in ("train", "dev"), "held-out label access not enabled")
        y, mask = np.asarray(self.values), np.asarray(self.mask)
        require(y.ndim == 1 and y.dtype.kind == "f", "invalid future")
        require(mask.dtype == bool and mask.shape == y.shape, "invalid common mask")
        require(np.array_equal(mask, np.isfinite(y)), "common mask must be frozen from raw future")
        object.__setattr__(self, "values", frozen_array(y))
        object.__setattr__(self, "mask", frozen_array(mask))


def read_target(reader, episode):
    """The split check happens before the supplied storage reader is called."""
    require(episode.split in ("train", "dev"), "held-out label access not enabled")
    y = np.asarray(reader(episode.context_end, episode.context_end+episode.horizon))
    require(y.shape == (episode.horizon,), "future length mismatch")
    return TaskTarget(episode.uid, episode.split, y, np.isfinite(y))


def mase_scale(raw_train, period):
    x = np.asarray(raw_train)
    require(x.ndim == 1 and 0 < period < len(x), "invalid seasonal period")
    valid = np.isfinite(x[period:]) & np.isfinite(x[:-period])
    if not valid.any():
        return None
    scale = float(np.mean(np.abs(x[period:][valid]-x[:-period][valid])))
    return scale if scale > 0 and np.isfinite(scale) else None


def evaluate_pair(target, keep, candidate, *, scale, tolerance=1e-9):
    keep, candidate = np.asarray(keep), np.asarray(candidate)
    require(keep.shape == candidate.shape == target.values.shape, "forecast/future shape mismatch")
    require(np.isfinite(keep).all() and np.isfinite(candidate).all(), "model failure cannot alter denominator")
    require(scale is None or (np.isfinite(scale) and scale > 0), "invalid MASE scale")
    require(tolerance >= 0 and np.isfinite(tolerance), "invalid tolerance")
    row = {"episode_uid": target.episode_uid, "future_hash": array_hash(target.values),
           "mask_hash": array_hash(target.mask), "n_scored": int(target.mask.sum()),
           "horizon": len(target.values), "repair_gain": None, "repair_harm": None}
    if not target.mask.any():
        return dict(row, status="unscorable_future", mae=None, mse=None, mase=None,
                    keep_mae=None, task_gain=None, task_harm=None)
    ek = keep[target.mask]-target.values[target.mask]
    ec = candidate[target.mask]-target.values[target.mask]
    km, cm = float(np.mean(abs(ek))), float(np.mean(abs(ec)))
    return dict(row, status="completed", mae=cm, mse=float(np.mean(ec**2)),
                mase=None if scale is None else cm/scale, keep_mae=km,
                task_gain=km-cm, task_harm=bool(cm > km+tolerance))
