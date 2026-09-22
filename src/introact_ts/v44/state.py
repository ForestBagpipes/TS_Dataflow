"""Task-state features for local matching (task book §3, Module 2).

Four blocks, and the split between them is the whole point of the method:

* **mask state**      -- what is missing, where, and how far from the origin.
* **visible context** -- what the observed past looks like.
* **intervention state** -- how the candidate input repairs the reference
  input, measured against the interpolated baseline at the repair positions
  (v54 freeze §5).  This is a function of *inputs only*.
* **reference forecast state** -- five summaries of the single reference TSFM
  prediction.

The leakage rule (§35) is enforced structurally: ``reference_forecast_features``
accepts exactly one prediction array, and no function in this module ever sees
a candidate's forecast.  The only way to add a candidate forecast feature would
be to change this module's signature, which the frozen protocol forbids.
"""

from __future__ import annotations

import numpy as np

MASK_FEATURES = (
    "missing_ratio",
    "longest_run",
    "n_runs",
    "distance_to_origin",
    "target_shared",
    "tail_indicator",
)

CONTEXT_FEATURES = (
    "robust_scale",
    "linear_trend",
    "lag1_acf",
    "seasonal_acf",
    "recent_level_shift",
    "recent_volatility",
)

INTERVENTION_FEATURES = (
    "mean_abs_change",
    "max_abs_change",
    "fraction_changed",
    "change_trend",
    "near_origin_change",
)

REFERENCE_FORECAST_FEATURES = (
    "fc_mean",
    "fc_range",
    "fc_slope",
    "fc_first_jump",
    "fc_roughness",
)

#: State definition version.  "v54-full22" is the protocol freeze of
#: 2026-09-22 (docs/protocol_freeze_v54_20260922.md §5): the intervention
#: block measures the candidate against the interpolated baseline at the
#: repair positions only.  States built under "v44-full22" (which zeroed the
#: four magnitude features whenever the reference had gaps) must never be
#: mixed into the same replay bank as v54 states.
STATE_VERSION = "v54-full22"

#: Window used by the "recent" summaries, in context steps.
RECENT_WINDOW = 32

#: Floor for every scale-like denominator.
SCALE_FLOOR = 1e-8


def feature_names() -> tuple[str, ...]:
    """The frozen, ordered feature list written into the protocol freeze."""
    return (MASK_FEATURES + CONTEXT_FEATURES + INTERVENTION_FEATURES
            + REFERENCE_FORECAST_FEATURES)


def _finite(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return x[np.isfinite(x)]


def robust_scale(x: np.ndarray, n_blocks: int = 8) -> float:
    """Median per-block interquartile range; immune to level displacement."""
    finite = _finite(x)
    if finite.size == 0:
        return SCALE_FLOOR

    def iqr(values: np.ndarray) -> float:
        q75, q25 = np.percentile(values, [75, 25])
        return float(q75 - q25)

    scale = 0.0
    if finite.size >= 4 * n_blocks:
        spreads = [iqr(b) for b in np.array_split(finite, n_blocks) if len(b) >= 4]
        positive = [v for v in spreads if v > SCALE_FLOOR]
        if positive:
            scale = float(np.median(positive))
    if scale < SCALE_FLOOR:
        scale = iqr(finite)
    if scale < SCALE_FLOOR:
        scale = float(np.std(finite))
    return max(scale, SCALE_FLOOR)


def interpolate_gaps(x: np.ndarray) -> np.ndarray:
    """Linear interpolation over interior gaps; leading/trailing use nearest."""
    x = np.asarray(x, dtype=np.float64)
    out = x.copy()
    valid = np.flatnonzero(np.isfinite(out))
    if len(valid) == 0:
        return np.zeros_like(out)
    idx = np.arange(len(out))
    out = np.interp(idx, idx[valid], out[valid])
    return out


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def _autocorr(x: np.ndarray, lag: int) -> float:
    x = np.asarray(x, dtype=np.float64)
    if lag <= 0 or len(x) <= lag + 2:
        return 0.0
    a, b = x[lag:], x[:-lag]
    a, b = a - a.mean(), b - b.mean()
    denom = float(np.sqrt((a @ a) * (b @ b)))
    if denom < SCALE_FLOOR:
        return 0.0
    value = float((a @ b) / denom)
    return value if np.isfinite(value) else 0.0


def mask_features_from_mask(mask: np.ndarray) -> np.ndarray:
    """Mask state of the request, from the mask itself.

    The mask is the frozen object -- a pure function of the episode identity --
    so taking it directly avoids re-deriving it from a panel and guarantees the
    replay bank and the live path describe the same request.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or mask.shape[0] < 2:
        raise ValueError("mask must be a (length, channels) boolean array")
    length = mask.shape[0]
    target_missing = mask[:, 0]
    runs = _runs(target_missing)
    n_missing = int(target_missing.sum())

    missing_ratio = n_missing / length
    longest = max((hi - lo for lo, hi in runs), default=0) / length
    n_runs = len(runs) / length
    distance = 1.0 if not runs else (length - runs[-1][1]) / length
    shared = float(bool(mask[:, 1:].any())) if mask.shape[1] > 1 else 0.0
    tail = 1.0 if target_missing[-1] else 0.0
    return np.array([missing_ratio, longest, n_runs, distance, shared, tail],
                    dtype=np.float64)


def mask_features(masked_panel: np.ndarray, reference_target: np.ndarray) -> np.ndarray:
    """Convenience wrapper: recover the mask from a masked panel."""
    masked_panel = np.asarray(masked_panel, dtype=np.float64)
    mask = ~np.isfinite(masked_panel)
    return mask_features_from_mask(mask)


def context_features(reference_target: np.ndarray, period: int) -> np.ndarray:
    """Visible-context descriptors of the reference (unmodified) series."""
    reference_target = np.asarray(reference_target, dtype=np.float64)
    scale = robust_scale(reference_target)
    filled = interpolate_gaps(reference_target)
    n = len(filled)
    idx = np.arange(n, dtype=np.float64)

    if np.isfinite(reference_target).sum() >= 4:
        observed = np.isfinite(reference_target)
        slope = float(np.polyfit(idx[observed], reference_target[observed], 1)[0])
    else:
        slope = 0.0

    lag1 = _autocorr(filled, 1)
    seasonal = _autocorr(filled, int(period)) if period and period < n - 2 else 0.0

    window = min(RECENT_WINDOW, n // 2)
    recent = filled[-window:]
    previous = filled[-2 * window:-window] if n >= 2 * window else filled[:window]
    level_shift = abs(float(recent.mean() - previous.mean())) / scale
    diffs = np.diff(recent)
    volatility = float(np.std(diffs)) / scale if diffs.size else 0.0

    return np.array([scale, slope / scale, lag1, seasonal, level_shift, volatility],
                    dtype=np.float64)


def intervention_features(candidate_target: np.ndarray,
                          reference_target: np.ndarray,
                          scale: float) -> np.ndarray:
    """How the candidate input repairs the reference input.

    v54 definition (protocol freeze §5): the baseline is
    ``interpolate_gaps(reference_target)`` -- a pure function of the visible
    reference, no model, no future label.  A *repair position* is one where
    the reference is NaN and the candidate is finite, and ``delta =
    candidate - baseline`` is evaluated on the repair positions only, divided
    by ``scale``.  KEEP hands the reference through unchanged (gaps stay
    NaN), so its repair set is empty and all five features are exactly zero,
    including ``fraction_changed``; the same holds whenever nothing was
    repaired.  ``fraction_changed`` is the share of window positions that
    were repaired; ``near_origin_change`` averages |delta| over the repair
    positions inside the last ``RECENT_WINDOW`` steps and is zero when no
    repair lies there.

    Input-only by construction: no forecast of the candidate exists at this
    point, and none is passed in.
    """
    candidate = np.asarray(candidate_target, dtype=np.float64)
    reference = np.asarray(reference_target, dtype=np.float64)
    if candidate.shape != reference.shape:
        raise ValueError("candidate/reference shape mismatch")
    scale = max(float(scale), SCALE_FLOOR)

    n = len(reference)
    repaired = ~np.isfinite(reference) & np.isfinite(candidate)
    fraction = float(repaired.sum()) / n if n else 0.0
    if not repaired.any():
        return np.zeros(len(INTERVENTION_FEATURES), dtype=np.float64)

    baseline = interpolate_gaps(reference)
    idx = np.flatnonzero(repaired)
    delta = candidate[idx] - baseline[idx]

    mean_abs = float(np.mean(np.abs(delta))) / scale
    max_abs = float(np.max(np.abs(delta))) / scale

    if len(idx) >= 3:
        slope = float(np.polyfit(idx.astype(np.float64), delta, 1)[0])
    else:
        slope = 0.0
    change_trend = slope / scale

    near = idx >= n - min(RECENT_WINDOW, n)
    near_origin = float(np.mean(np.abs(delta[near]))) / scale if near.any() else 0.0
    return np.array([mean_abs, max_abs, fraction, change_trend, near_origin],
                    dtype=np.float64)


def reference_forecast_features(prediction: np.ndarray,
                                reference_target: np.ndarray) -> np.ndarray:
    """Five summaries of the *reference* forecast only.

    The signature takes exactly one forecast.  There is no code path that lets
    a candidate's prediction reach this function, which is what makes the
    "reference forecast feature only from reference" contract testable rather
    than merely documented.
    """
    prediction = np.asarray(prediction, dtype=np.float64).reshape(-1)
    reference_target = np.asarray(reference_target, dtype=np.float64)
    if prediction.size == 0 or not np.isfinite(prediction).all():
        raise ValueError("reference forecast must be finite and non-empty")
    scale = robust_scale(reference_target)

    idx = np.arange(len(prediction), dtype=np.float64)
    slope = float(np.polyfit(idx, prediction, 1)[0]) if len(prediction) >= 2 else 0.0
    last_observed = reference_target[np.isfinite(reference_target)]
    anchor = float(last_observed[-1]) if last_observed.size else float(prediction[0])
    roughness = float(np.mean(np.abs(np.diff(prediction)))) if len(prediction) >= 2 else 0.0

    return np.array([
        float(prediction.mean()) / scale,
        float(prediction.max() - prediction.min()) / scale,
        slope / scale,
        (float(prediction[0]) - anchor) / scale,
        roughness / scale,
    ], dtype=np.float64)


def state_vector(*, masked_panel: np.ndarray, reference_target: np.ndarray,
                 period: int, candidate_target: np.ndarray,
                 reference_prediction: np.ndarray) -> np.ndarray:
    """The full matching state for one (request, action) pair."""
    return np.concatenate([
        mask_features(masked_panel, reference_target),
        context_features(reference_target, period),
        intervention_features(candidate_target, reference_target,
                              robust_scale(reference_target)),
        reference_forecast_features(reference_prediction, reference_target),
    ])


def state_vector_from_mask(*, mask: np.ndarray, reference_target: np.ndarray,
                           period: int, candidate_target: np.ndarray,
                           reference_prediction: np.ndarray) -> np.ndarray:
    """Same state, built from the frozen mask instead of a masked panel.

    The replay builder only keeps the mask (the full panel is far too large to
    store for Traffic's 862 channels), and the mask is what actually defines
    the request, so this path is the canonical one.
    """
    return np.concatenate([
        mask_features_from_mask(mask),
        context_features(reference_target, period),
        intervention_features(candidate_target, reference_target,
                              robust_scale(reference_target)),
        reference_forecast_features(reference_prediction, reference_target),
    ])
