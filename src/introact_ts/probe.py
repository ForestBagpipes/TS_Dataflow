"""Behavioural probing of a frozen TSFM.

The probe is the agent's only window onto how a model actually reacts to a
piece of data. It is run twice per candidate intervention -- once before, once
after -- so that the resulting utility change is a measurement, not a guess.

Six families of signals are extracted:

  1. holdout forecast error and residual structure
  2. masked-reconstruction stability
  3. multi-view forecast consistency
  4. perturbation sensitivity of the output
  5. inter-layer representation dynamics
  6. cross-model disagreement

Every signal is scale-free with respect to a *fixed* reference scale supplied
by the caller, and the fixing is what makes a utility *difference* meaningful.
Were each measurement normalised by the spread of the series in front of it,
the ruler would move with the edit: a smoothing action shrinks the denominator
and inflates its own error, a scaling action does the reverse, and in neither
case does the change reflect anything about the data's quality. Pinning the
scale to the original window means before and after are measured with the same
instrument, so the sign of the difference can be trusted.

Guarding against over-smoothing is a separate job, and the utility term does
not do it -- a flattened series really is easier to forecast. That veto lives
in :mod:`introact_ts.structure`.
"""

from dataclasses import dataclass, field

import numpy as np

from .types import ProbeResult

#: Names of the behaviour vector dimensions, in fixed order.
SIGNAL_NAMES = (
    "forecast_nrmse",
    "resid_acf1",
    "resid_skew",
    "recon_nrmse_med",
    "recon_nrmse_iqr",
    "recon_nrmse_max",
    "multiview_disagree",
    "multiview_err_spread",
    "perturb_output_sens",
    "perturb_repr_sens",
    "repr_jump_mean",
    "repr_jump_max",
    "repr_norm_drift",
    "model_disagree",
)

#: Utility weights. All signals are "lower is better", so utility negates them.
DEFAULT_UTILITY_WEIGHTS = {
    "forecast_nrmse": 1.0,
    "resid_acf1": 0.3,
    "recon_nrmse_med": 1.0,
    "recon_nrmse_iqr": 0.3,
    "recon_nrmse_max": 0.6,
    "multiview_disagree": 0.5,
    "perturb_output_sens": 0.4,
    "repr_jump_mean": 0.3,
    "model_disagree": 0.5,
}


@dataclass
class ProbeConfig:
    """Knobs for the probe. Held fixed across a whole experiment."""

    horizon: int = 32
    n_masks: int = 8
    mask_len: int = 24
    view_fractions: tuple = (1.0, 0.7, 0.45)
    perturb_eps: float = 0.02
    n_perturb: int = 2
    weights: dict = field(default_factory=lambda: dict(DEFAULT_UTILITY_WEIGHTS))
    seed: int = 42


def reference_scale(series: np.ndarray) -> float:
    """Robust spread of a window, used to make every error scale-free."""
    series = np.asarray(series, dtype=np.float64)
    finite = series[np.isfinite(series)]
    if finite.size == 0:
        return 1.0
    q75, q25 = np.percentile(finite, [75, 25])
    scale = float(q75 - q25)
    if scale < 1e-8:
        scale = float(np.std(finite))
    return max(scale, 1e-6)


def _naive_fill(series: np.ndarray) -> np.ndarray:
    """Forward-fill NaNs so the model can be queried at all.

    The choice of filler is not incidental. Interpolating here would have the
    probe quietly perform the repair itself: IMPUTE would then produce a
    candidate the model cannot distinguish from the original, the measured
    utility change would be exactly zero, and every fill would be rolled back
    for failing to help. Forward-fill instead reproduces what a model actually
    meets when nobody curated the data -- a gap frozen at its last observation
    -- so a real imputation has something to improve on.
    """
    series = np.asarray(series, dtype=np.float64).copy()
    bad = ~np.isfinite(series)
    if not bad.any():
        return series
    if bad.all():
        return np.zeros_like(series)
    idx = np.arange(len(series))
    good = np.where(~bad)[0]
    # Carry the last valid observation forward; back-fill the leading gap.
    prev = np.maximum.accumulate(np.where(~bad, idx, -1))
    prev[prev < 0] = good[0]
    return series[prev]


#: Retained under the old name for callers that only need "queryable series".
_nan_safe = _naive_fill


def _acf1(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 3:
        return 0.0
    x = x - x.mean()
    denom = float(np.dot(x, x))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(x[:-1], x[1:]) / denom)


def _skew(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    sd = float(np.std(x))
    if sd < 1e-12 or len(x) < 3:
        return 0.0
    return float(np.mean(((x - x.mean()) / sd) ** 3))


def probe_window(
    series: np.ndarray,
    models: list,
    scale: float,
    cfg: ProbeConfig = None,
) -> ProbeResult:
    """Run the full behavioural probe on one window.

    Args:
        series: the window to probe. May contain NaNs.
        models: frozen backends. ``models[0]`` is the judge model that drives
            curation; the rest only contribute the disagreement signal and must
            never be used as a repair target.
        scale: fixed reference spread (see :func:`reference_scale`). Pass the
            scale of the *original* window for every probe of that window.
        cfg: probe configuration.

    Returns:
        A :class:`~introact_ts.types.ProbeResult` holding the 13-dim behaviour
        vector, the scalar utility, and the named parts.
    """
    cfg = cfg or ProbeConfig()
    judge = models[0]
    x = _naive_fill(series)
    T = len(x)
    scale = max(float(scale), 1e-6)
    rng = np.random.RandomState(cfg.seed)

    H = int(min(cfg.horizon, max(8, T // 4)))
    split = T - H
    parts = {}

    # 1. Holdout forecast error and residual structure -----------------------
    ctx, tgt = x[:split], x[split:]
    pred = judge.forecast(ctx, H)
    resid = tgt - pred
    parts["forecast_nrmse"] = float(np.sqrt(np.mean(resid**2)) / scale)
    parts["resid_acf1"] = abs(_acf1(resid))
    parts["resid_skew"] = abs(_skew(resid))

    # 2. Masked reconstruction stability -------------------------------------
    mask_len = int(min(cfg.mask_len, max(4, T // 10)))
    recon_errs = []
    lo_choices = np.linspace(T // 8, split - mask_len - 1, cfg.n_masks).astype(int)
    for lo in lo_choices:
        lo = int(max(mask_len, min(lo, T - mask_len - 1)))
        hi = lo + mask_len
        rec = judge.reconstruct(x, lo, hi)
        recon_errs.append(float(np.sqrt(np.mean((x[lo:hi] - rec) ** 2)) / scale))
    recon_errs = np.asarray(recon_errs, dtype=np.float64)
    parts["recon_nrmse_med"] = float(np.median(recon_errs))
    q75, q25 = np.percentile(recon_errs, [75, 25])
    parts["recon_nrmse_iqr"] = float(q75 - q25)
    # The worst-reconstructed region, kept separately from the median. A gap or
    # a stuck stretch is a local fault: it wrecks reconstruction exactly where
    # it sits and leaves the rest of the window alone, so a median over probe
    # positions averages it away and the repair that fixes it registers no
    # utility gain at all.
    parts["recon_nrmse_max"] = float(np.max(recon_errs))

    # 3. Multi-view forecast consistency -------------------------------------
    views, view_errs = [], []
    for frac in cfg.view_fractions:
        n_ctx = int(max(32, frac * split))
        v_pred = judge.forecast(ctx[-n_ctx:], H)
        views.append(v_pred)
        view_errs.append(float(np.sqrt(np.mean((tgt - v_pred) ** 2)) / scale))
    views = np.asarray(views, dtype=np.float64)
    parts["multiview_disagree"] = float(np.mean(np.std(views, axis=0)) / scale)
    parts["multiview_err_spread"] = float(np.std(view_errs))

    # 4. Perturbation sensitivity --------------------------------------------
    base_states = judge.encode(ctx)
    base_h = base_states[-1]
    out_sens, repr_sens = [], []
    for _ in range(cfg.n_perturb):
        delta = rng.randn(len(ctx)) * cfg.perturb_eps * scale
        p_ctx = ctx + delta
        d_in = float(np.linalg.norm(delta)) + 1e-12
        p_pred = judge.forecast(p_ctx, H)
        out_sens.append(float(np.linalg.norm(p_pred - pred) / d_in))
        p_h = judge.encode(p_ctx)[-1]
        repr_sens.append(
            float(np.linalg.norm(p_h - base_h) / (np.linalg.norm(base_h) + 1e-12))
        )
    parts["perturb_output_sens"] = float(np.mean(out_sens))
    parts["perturb_repr_sens"] = float(np.mean(repr_sens))

    # 5. Inter-layer representation dynamics ---------------------------------
    jumps = []
    for l in range(len(base_states) - 1):
        a, b = base_states[l], base_states[l + 1]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        cos = float(a @ b / (na * nb + 1e-12)) if na > 1e-12 and nb > 1e-12 else 1.0
        jumps.append(1.0 - cos)
    jumps = np.asarray(jumps, dtype=np.float64)
    parts["repr_jump_mean"] = float(np.mean(jumps))
    parts["repr_jump_max"] = float(np.max(jumps))
    n_first = float(np.linalg.norm(base_states[0]))
    parts["repr_norm_drift"] = float(
        abs(np.linalg.norm(base_states[-1]) - n_first) / (n_first + 1e-12)
    )

    # 6. Cross-model disagreement --------------------------------------------
    if len(models) > 1:
        peer_preds = [m.forecast(ctx, H) for m in models]
        peer_preds = np.asarray(peer_preds, dtype=np.float64)
        parts["model_disagree"] = float(np.mean(np.std(peer_preds, axis=0)) / scale)
    else:
        parts["model_disagree"] = 0.0

    vector = np.asarray([parts[k] for k in SIGNAL_NAMES], dtype=np.float64)
    vector = np.nan_to_num(vector, nan=0.0, posinf=1e6, neginf=-1e6)
    utility = -sum(w * parts.get(k, 0.0) for k, w in cfg.weights.items())
    if not np.isfinite(utility):
        utility = -1e6

    return ProbeResult(vector=vector, utility=float(utility), parts=parts)


def probe_corpus(
    windows: list,
    models: list,
    cfg: ProbeConfig = None,
) -> tuple:
    """Probe every window once, returning the behaviour matrix and utilities."""
    cfg = cfg or ProbeConfig()
    results = []
    for w in windows:
        scale = reference_scale(w.series)
        results.append(probe_window(w.series, models, scale, cfg))
    B = np.stack([r.vector for r in results])
    U = np.asarray([r.utility for r in results], dtype=np.float64)
    return B, U, results
