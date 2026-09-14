"""Action-semantic labels for v3.3 (MAST-PICS).

Pre-registered in ``docs/v3_3_mast_pics_design.md`` §1. The v3.2 audit found
the binding label defect: the canonical uncentered finite-mask NMSE ignores
missing points in ``before_nmse`` but counts them once IMPUTE fills them, so a
genuine repair of a hole can be labelled harmful. The frozen TSFM never reads
NaN -- ``probe.py`` materialises the series with forward-fill before querying
-- so the KEEP counterfactual for IMPUTE is the materialised series, not the
raw array.

Label rules, fixed in advance:

- DENOISE / DESPIKE / RESEGMENT: unchanged from v3.2 (raw ``original`` against
  clean, RESEGMENT against the cropped clean span). A hard integrity gate
  requires these labels to be bit-identical to the v3.2 table.
- IMPUTE (NaN gaps and finite frozen runs alike):

    x_keep   = materialize_for_probe(original)   # identity when no NaN
    x_action = outcome.series
    before   = canonical_nmse(x_keep,   clean, ref_var)
    after    = canonical_nmse(x_action, clean, ref_var)

Labels and the clean series are evaluation-namespace only; nothing here may
enter a deployment feature.
"""

import hashlib
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from metrics_common import canonical_nmse, damage, ref_var  # noqa: E402
from introact_ts.contextual_shield import _touched_mask  # noqa: E402
from introact_ts.probe import materialize_for_probe  # noqa: E402

#: Families whose KEEP counterfactual is the probe-materialised series.
MATERIALISED_KEEP_FAMILIES = ("IMPUTE",)

#: Damage safety level, the project's standing definition.
ALPHA = 0.03


def hash_array(a: np.ndarray) -> str:
    """SHA-256 of the series rounded to 6 decimals, NaN preserved."""
    x = np.asarray(a, dtype=np.float64).copy()
    x[~np.isfinite(x)] = np.nan
    return hashlib.sha256(np.round(x, 6).tobytes()).hexdigest()


def _masked_nmse(x: np.ndarray, c: np.ndarray, mask: np.ndarray,
                 rv: float) -> float:
    """canonical_nmse restricted to mask positions; NaN when the mask is empty."""
    if mask is None or not mask.any():
        return float("nan")
    n = min(len(x), len(c), len(mask))
    m = mask[:n]
    d = x[:n][m] - c[:n][m]
    finite = np.isfinite(d)
    if not finite.any():
        return float("nan")
    v = float(np.mean(d[finite] ** 2))
    return v / rv if rv >= 1e-12 else v


def compute_action_labels(family, original: np.ndarray, outcome_series,
                          clean: np.ndarray, touched=None,
                          params: dict = None) -> dict:
    """Labels and action-semantic metrics for one executed candidate.

    Args:
        family: action family name (``Action.value`` string or enum).
        original: the corrupted window as routed (may contain NaN).
        outcome_series: the operator output.
        clean: pristine reference (evaluation namespace only).
        touched: the operator's touched declaration (mask or indices).
        params: operator params (``lo`` is read for RESEGMENT).
    """
    fam = family.value if hasattr(family, "value") else str(family)
    original = np.asarray(original, dtype=np.float64)
    y = np.asarray(outcome_series, dtype=np.float64)
    c = np.asarray(clean, dtype=np.float64)
    params = params or {}
    rv = ref_var(c)

    lo = int(params.get("lo", 0)) if fam == "RESEGMENT" else 0
    hi = lo + len(y)
    c_ref = c[lo:hi]

    x_keep = (materialize_for_probe(original)
              if fam in MATERIALISED_KEEP_FAMILIES else original.copy())
    before = canonical_nmse(x_keep, c, rv)
    after = canonical_nmse(y, c_ref, rv)
    worse = 1.0 if after > before + 1e-9 else 0.0
    discard = 1.0 - (hi - lo) / len(original)
    loss = damage(worse, discard)
    gain = before - after
    beneficial = float(gain > 1e-9)
    safe = float(loss <= ALPHA)

    T = len(original)
    same_len = len(y) == T
    mask = _touched_mask(touched, T) if same_len else None

    t_before = _masked_nmse(x_keep, c, mask, rv)
    t_after = _masked_nmse(y, c, mask, rv)
    support = None if mask is None else ~mask
    s_before = _masked_nmse(x_keep, c, support, rv)
    s_after = _masked_nmse(y, c, support, rv)

    missing = ~np.isfinite(original)
    missing_fraction = float(missing.mean())
    if missing.any() and same_len:
        filled = np.isfinite(y[missing])
        closer = np.abs(y[missing] - c[missing]) < np.abs(x_keep[missing] - c[missing]) - 1e-12
        recovery = float(np.mean(filled & closer))
    else:
        recovery = None

    return {
        "before_nmse": float(before),
        "after_nmse": float(after),
        "true_loss": float(loss),
        "true_repair_gain": float(gain),
        "beneficial": float(beneficial),
        "safe": float(safe),
        "harmful": float(1.0 - safe),
        "beneficial_and_safe": float(beneficial and safe),
        "discard_share": float(discard),
        # action-semantic fields (evaluation namespace)
        "target_mask_n": int(mask.sum()) if mask is not None else None,
        "target_mask_nrmse_before": t_before,
        "target_mask_nrmse_after": t_after,
        "target_mask_gain": (t_before - t_after)
        if np.isfinite(t_before) and np.isfinite(t_after) else None,
        "observed_support_nrmse_before": s_before,
        "observed_support_nrmse_after": s_after,
        "observed_support_drift": (s_after - s_before)
        if np.isfinite(s_before) and np.isfinite(s_after) else None,
        "missing_fraction": missing_fraction,
        "missing_recovery_rate": recovery,
        "forward_fill_baseline_hash": hash_array(materialize_for_probe(original)),
        "output_hash": hash_array(y),
        "keep_input_hash": hash_array(x_keep),
    }
