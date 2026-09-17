"""Common forecasting metrics and the frozen aggregation ladder (task book §12–§14).

Every method is scored by the same functions on the same future positions with
the same denominators.  Two denominators are carried explicitly, never
recomputed per method:

* ``mase_scale``  -- mean absolute seasonal naive error of the raw TRAIN series
* ``rmsse_scale`` -- mean squared seasonal naive error of the same series

Both are computed from rows strictly before the forecast origin, so they cannot
leak a future value, and both are hashed into the record so a mismatched
denominator is detectable after the fact.

Aggregation is deliberately hierarchical: variants are *not* independent
samples, so a source's score is the mean of its parents' scores, and the macro
average weights the eight sources equally.
"""

from __future__ import annotations

import numpy as np

from .protocol import AGGREGATION_ORDER, CGC_EPSILON

#: Condition keys that identify one cell of the result table.  Aggregation
#: never mixes two different values of these.
CONDITION_KEYS = ("method", "backbone", "horizon", "pattern", "severity")

_LEVEL_KEYS = {
    "variant": ("source", "parent", "variant"),
    "parent": ("source", "parent"),
    "source": ("source",),
    "macro": (),
}


def seasonal_scale(raw_train: np.ndarray, period: int) -> tuple[float | None, float | None]:
    """``(mase_scale, rmsse_scale)`` from a raw training series.

    Both are ``None`` when the seasonal naive error is degenerate, in which
    case the corresponding metric is reported as missing rather than as zero.
    """
    x = np.asarray(raw_train, dtype=np.float64)
    if x.ndim != 1 or period <= 0 or period >= len(x):
        raise ValueError("invalid series or seasonal period")
    valid = np.isfinite(x[period:]) & np.isfinite(x[:-period])
    if not valid.any():
        return None, None
    diff = x[period:][valid] - x[:-period][valid]
    mae = float(np.mean(np.abs(diff)))
    mse = float(np.mean(diff ** 2))
    mase = mae if mae > 0 and np.isfinite(mae) else None
    rmsse = mse if mse > 0 and np.isfinite(mse) else None
    return mase, rmsse


def forecast_metrics(target: np.ndarray, prediction: np.ndarray, *,
                     mase_scale: float | None,
                     rmsse_scale: float | None,
                     mask: np.ndarray | None = None) -> dict:
    """MASE / MSE / MAE / RMSSE on the common future positions."""
    target = np.asarray(target, dtype=np.float64).reshape(-1)
    prediction = np.asarray(prediction, dtype=np.float64).reshape(-1)
    if target.shape != prediction.shape:
        raise ValueError("target/prediction shape mismatch")
    if not np.isfinite(prediction).all():
        raise ValueError("a failed prediction must not enter the denominator")
    if mask is None:
        mask = np.isfinite(target)
    mask = np.asarray(mask, dtype=bool)
    if mask.shape != target.shape:
        raise ValueError("scoring mask shape mismatch")
    n_scored = int(mask.sum())
    if n_scored == 0:
        return {"n_scored": 0, "mase": None, "mse": None, "mae": None, "rmsse": None}
    error = prediction[mask] - target[mask]
    mae = float(np.mean(np.abs(error)))
    mse = float(np.mean(error ** 2))
    return {
        "n_scored": n_scored,
        "mae": mae,
        "mse": mse,
        "mase": None if mase_scale is None else mae / float(mase_scale),
        "rmsse": None if rmsse_scale is None else float(np.sqrt(mse / float(rmsse_scale))),
    }


# -- governance diagnostics (§28) -------------------------------------------


def harmful_intervention_rate(loss_method: np.ndarray, loss_keep: np.ndarray) -> float:
    """Fraction of requests where the method is worse than the reference."""
    loss_method = np.asarray(loss_method, dtype=np.float64)
    loss_keep = np.asarray(loss_keep, dtype=np.float64)
    if loss_method.shape != loss_keep.shape or loss_method.size == 0:
        raise ValueError("loss vectors must be non-empty and aligned")
    return float(np.mean(loss_method > loss_keep))


def harmful_loss(loss_method: np.ndarray, loss_keep: np.ndarray) -> float:
    """Mean positive excess loss over the reference."""
    loss_method = np.asarray(loss_method, dtype=np.float64)
    loss_keep = np.asarray(loss_keep, dtype=np.float64)
    if loss_method.shape != loss_keep.shape or loss_method.size == 0:
        raise ValueError("loss vectors must be non-empty and aligned")
    return float(np.mean(np.maximum(0.0, loss_method - loss_keep)))


def catalog_gap_closed(loss_method: np.ndarray, loss_keep: np.ndarray,
                       loss_oracle: np.ndarray, *,
                       epsilon: float = CGC_EPSILON) -> dict:
    """Fraction of the achievable catalog gap that a method closes.

    Windows where the oracle does not beat the reference, or where the
    achievable gap is below the pre-registered epsilon, are excluded from the
    mean and reported as a count -- never deleted silently.
    """
    loss_method = np.asarray(loss_method, dtype=np.float64)
    loss_keep = np.asarray(loss_keep, dtype=np.float64)
    loss_oracle = np.asarray(loss_oracle, dtype=np.float64)
    if not (loss_method.shape == loss_keep.shape == loss_oracle.shape):
        raise ValueError("loss vectors must be aligned")
    gap = loss_keep - loss_oracle
    usable = (gap > epsilon) & np.isfinite(gap)
    if not usable.any():
        return {"cgc": None, "usable": 0, "excluded": int(loss_keep.size)}
    closed = (loss_keep[usable] - loss_method[usable]) / gap[usable]
    return {"cgc": float(np.mean(closed)), "usable": int(usable.sum()),
            "excluded": int(loss_keep.size - usable.sum())}


# -- aggregation (§13) ------------------------------------------------------


def _mean(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    return float(values.mean()) if values.size else None


def hierarchical_aggregate(records: list[dict], value_key: str, *,
                           levels=AGGREGATION_ORDER) -> dict[str, list[dict]]:
    """Aggregate ``value_key`` up the frozen ladder.

    ``records`` must each carry the condition keys, ``source``, ``parent`` and
    ``variant``.  Returns one row list per level; every row repeats its
    condition keys so downstream tables can be built without re-joining.
    """
    for level in levels:
        if level not in _LEVEL_KEYS:
            raise ValueError(f"unregistered aggregation level {level!r}")
    if not records:
        return {level: [] for level in levels}

    def group(items: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
        buckets: dict[tuple, list[dict]] = {}
        for item in items:
            key = tuple(item.get(k) for k in CONDITION_KEYS) + tuple(
                item.get(k) for k in keys)
            buckets.setdefault(key, []).append(item)
        return buckets

    current = records
    out: dict[str, list[dict]] = {}
    for level in levels:
        keys = _LEVEL_KEYS[level]
        buckets = group(current, keys)
        rows = []
        for key, items in buckets.items():
            condition = dict(zip(CONDITION_KEYS, key[:len(CONDITION_KEYS)]))
            identity = dict(zip(keys, key[len(CONDITION_KEYS):]))
            values = [item[value_key] for item in items
                      if item.get(value_key) is not None]
            rows.append({**condition, **identity,
                         value_key: _mean(values),
                         "n_units": len(items)})
        rows.sort(key=lambda r: tuple(str(r.get(k)) for k in
                                      CONDITION_KEYS + keys))
        out[level] = rows
        current = rows
    return out


def macro_summary(records: list[dict], value_key: str) -> list[dict]:
    """Convenience wrapper: the ``macro`` level of the ladder, one row per cell."""
    return hierarchical_aggregate(records, value_key)["macro"]
