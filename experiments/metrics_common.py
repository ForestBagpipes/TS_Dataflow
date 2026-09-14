"""Canonical evaluation metrics shared by all experiment scripts.

The P0 audit found that two scripts computed "the same" NMSE with different
conventions: one median-centered both series and replaced NaN with the median,
the other did neither. They are not the same quantity. This module fixes the
convention once, and every evaluation script must import from here.

The canonical definition is the one the deployment shield sees: uncentered,
finite-mask NMSE against the clean reference.
"""

from typing import Optional

import numpy as np


def ref_var(clean: np.ndarray) -> float:
    """Variance of the clean reference after median-centering.

    This is the scale factor for NMSE. It is computed once from the clean
    series and reused for both before and after measurements.
    """
    c = np.asarray(clean, dtype=np.float64)
    c = c - np.median(c)
    return float(np.var(c))


def canonical_nmse(series: np.ndarray, clean: np.ndarray,
                   ref_var: Optional[float] = None) -> float:
    """Normalised distance between series and clean.

    Definition: mean squared error over the points where the difference is
    finite, divided by ``ref_var``. No median-centering of either argument is
    performed here; the caller decides whether the series should be compared
    in absolute level or in shape. For level-shift repair evaluation the
    level matters, so no centering is applied.

    If ``ref_var`` is None it is computed from ``clean``.
    """
    x = np.asarray(series, dtype=np.float64)
    c = np.asarray(clean, dtype=np.float64)
    n = min(len(x), len(c))
    if n == 0:
        return float("nan")
    x, c = x[:n], c[:n]
    d = x - c
    finite = np.isfinite(d)
    if not finite.any():
        return float("nan")
    if ref_var is None:
        ref_var = globals()["ref_var"](c)
    if ref_var < 1e-12:
        return float(np.mean(d[finite] ** 2))
    return float(np.mean(d[finite] ** 2) / ref_var)


def repair_rmsd(series: np.ndarray, clean: np.ndarray,
                scale: Optional[float] = None) -> float:
    """RMS distance to clean, normalised by the clean series' robust scale.

    ``robust_scale`` is imported lazily to avoid a circular import when this
    module is loaded early.
    """
    x = np.asarray(series, dtype=np.float64)
    c = np.asarray(clean, dtype=np.float64)
    n = min(len(x), len(c))
    if n == 0:
        return float("nan")
    x, c = x[:n], c[:n]
    if scale is None:
        from introact_ts.actions import robust_scale  # noqa: E402
        scale = robust_scale(c)
    if not scale > 0:
        return float("nan")
    return float(np.sqrt(np.mean((x - c) ** 2)) / scale)


def damage(worse_binary: float, discard_share: float) -> float:
    """Formal damage definition, `max(worse_binary, discard_share)`."""
    return float(max(worse_binary, discard_share))


def conditional_loss_metrics(losses, alpha: float = 0.03) -> dict:
    """Loss distribution over committed candidates.

    ``conditional_harm_rate`` (CHR) is the share of commits whose loss exceeds
    ``alpha`` -- this is what the v3.2 compare script misleadingly reported
    under the name ``n_harm / n_committed``. ``conditional_mean_loss`` and the
    p90/p95 quantiles are the actual loss magnitudes, which CHR alone hides.
    Returns NaNs for an empty commit set.
    """
    import numpy as np
    v = np.asarray(list(losses), dtype=np.float64)
    if len(v) == 0:
        return {"conditional_harm_rate": float("nan"),
                "conditional_mean_loss": float("nan"),
                "conditional_loss_p90": float("nan"),
                "conditional_loss_p95": float("nan"),
                "n_committed": 0}
    q90, q95 = np.percentile(v, [90, 95])
    return {"conditional_harm_rate": float(np.mean(v > alpha)),
            "conditional_mean_loss": float(np.mean(v)),
            "conditional_loss_p90": float(q90),
            "conditional_loss_p95": float(q95),
            "n_committed": int(len(v))}
