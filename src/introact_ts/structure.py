"""Temporal structure fidelity.

Model utility alone is a treacherous objective: aggressive smoothing lowers
forecast error while erasing the peaks, regime shifts and local periodicity
that made the data worth keeping. This module measures what an intervention
did to the *structure* of a window, independently of how the model felt about
it.

Seven components are compared before and after, each mapped to a bounded
distortion in [0, 1]:

  trend, period, spectrum, autocorrelation, changepoints, extremes, shape

The aggregate mixes the weighted mean with the worst single component, so a
single catastrophic change (all extreme events flattened) cannot be averaged
away by six well-behaved ones.

RESEGMENT changes the length of the window. Comparing a cut series against the
full original would report a huge distortion for what is, by construction, a
crop. ``align_for_action`` therefore slices the original down to the retained
span before comparison, so the metric answers the right question: was the
*kept* part damaged?
"""

from dataclasses import dataclass, field

import numpy as np

from .actions import changepoints, dominant_period, robust_scale
from .types import Action

#: Local operators (IMPUTE, DESPIKE, RESEGMENT) declare which points they
#: rewrite, and are judged on three questions: did everything they did *not*
#: claim survive intact, is what they wrote in its place statistically coherent
#: with its surroundings, and how much of the window did they rewrite.
#:
#: The global descriptors are deliberately absent here. Once point-wise
#: fidelity outside the footprint holds, trend / period / ACF are preserved by
#: construction, while the spectrum is actively misleading: an injected spike
#: is broadband energy, so removing it -- correctly -- shifts the normalised
#: power spectrum enormously, and a spectral term vetoes exactly the repairs
#: that should be accepted.
LOCAL_WEIGHTS = {
    "shape": 0.35,
    "extremes": 0.25,
    "patch": 0.25,
    "footprint": 0.15,
}

#: Global operators (DENOISE) rewrite every point by construction, so
#: point-wise fidelity is not the right question. What they must preserve is
#: the signal band of the spectrum, the trend, the seasonality, the memory and
#: above all the tails -- flattening the peaks is exactly the failure mode this
#: profile exists to catch.
GLOBAL_WEIGHTS = {
    "trend": 0.15,
    "period": 0.18,
    "spectrum": 0.22,
    "acf": 0.15,
    "changepoint": 0.10,
    "extremes": 0.20,
}

STRUCT_WEIGHTS = LOCAL_WEIGHTS

#: Operators that declare a footprint and are judged outside it.
LOCAL_ACTIONS = (Action.IMPUTE, Action.DESPIKE, Action.RESEGMENT)

#: Fraction of the spectrum a global smoother is allowed to alter. Denoising
#: necessarily removes high-frequency energy; the signal band must survive.
SIGNAL_BAND = 0.5


@dataclass
class StructureReport:
    distortion: float
    parts: dict = field(default_factory=dict)


def _clean(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if np.isfinite(x).all():
        return x
    idx = np.arange(len(x))
    good = np.isfinite(x)
    if not good.any():
        return np.zeros_like(x)
    out = x.copy()
    out[~good] = np.interp(idx[~good], idx[good], x[good])
    return out


def _scale(x: np.ndarray) -> float:
    """Local spread, robust to level displacement. See ``actions.robust_scale``."""
    return robust_scale(x)


def _bounded(v: float, k: float = 1.0) -> float:
    """Map a non-negative difference into [0, 1) with saturation at scale k."""
    v = abs(float(v))
    if not np.isfinite(v):
        return 1.0
    return float(v / (v + k))


def _trend_distortion(a: np.ndarray, b: np.ndarray) -> float:
    """Change in normalised slope and in how much of the variance it explains."""
    def feats(x):
        t = np.arange(len(x), dtype=np.float64)
        t = (t - t.mean()) / (t.std() + 1e-12)
        xc = (x - x.mean()) / (_scale(x) + 1e-12)
        slope = float(np.dot(t, xc) / (np.dot(t, t) + 1e-12))
        resid = xc - slope * t
        r2 = 1.0 - float(np.var(resid) / (np.var(xc) + 1e-12))
        return slope, max(0.0, min(1.0, r2))

    s_a, r_a = feats(a)
    s_b, r_b = feats(b)
    return 0.6 * _bounded(s_a - s_b, k=0.5) + 0.4 * abs(r_a - r_b)


def _period_distortion(a: np.ndarray, b: np.ndarray) -> float:
    """Whether the dominant period survived, and whether its energy did."""
    p_a, p_b = dominant_period(a), dominant_period(b)
    if p_a == 0 and p_b == 0:
        period_term = 0.0
    elif p_a == 0 or p_b == 0:
        period_term = 1.0
    else:
        period_term = _bounded(abs(p_a - p_b) / max(p_a, p_b), k=0.25)

    def seasonal_energy(x, period):
        if period < 2 or len(x) < 2 * period:
            return 0.0
        spec = np.abs(np.fft.rfft(x - x.mean())) ** 2
        freqs = np.fft.rfftfreq(len(x))
        target = 1.0 / period
        band = (freqs > target * 0.8) & (freqs < target * 1.25)
        if not band.any():
            return 0.0
        return float(spec[band].sum() / (spec[1:].sum() + 1e-12))

    ref_period = p_a if p_a >= 2 else p_b
    e_a = seasonal_energy(a, ref_period)
    e_b = seasonal_energy(b, ref_period)
    return 0.5 * period_term + 0.5 * abs(e_a - e_b)


def _spectrum_distortion(
    a: np.ndarray, b: np.ndarray, n_bins: int = 32, hi_frac: float = 1.0
) -> float:
    """L1 distance between normalised power spectra on a common frequency grid.

    Interpolating onto normalised frequencies makes this valid across the
    length change that RESEGMENT introduces. ``hi_frac`` restricts the
    comparison to the lower ``hi_frac`` of the band, which is how a denoiser is
    judged: it is allowed to strip high-frequency energy, not to reshape the
    signal band.
    """
    f_max = 0.5 * float(np.clip(hi_frac, 0.05, 1.0))

    def spec(x):
        p = np.abs(np.fft.rfft(x - x.mean())) ** 2
        f = np.fft.rfftfreq(len(x))
        if len(p) < 3:
            return np.ones(n_bins) / n_bins
        grid = np.linspace(f[1], f_max, n_bins)
        interp = np.interp(grid, f[1:], p[1:])
        total = interp.sum()
        return interp / total if total > 1e-12 else np.ones(n_bins) / n_bins

    return float(0.5 * np.abs(spec(a) - spec(b)).sum())


def _acf_distortion(a: np.ndarray, b: np.ndarray, n_lags: int = 24) -> float:
    def acf(x):
        x = x - x.mean()
        denom = float(np.dot(x, x)) + 1e-12
        lags = min(n_lags, len(x) // 3)
        return np.asarray(
            [np.dot(x[:-k], x[k:]) / denom for k in range(1, max(2, lags + 1))]
        )

    ac_a, ac_b = acf(a), acf(b)
    n = min(len(ac_a), len(ac_b))
    if n == 0:
        return 0.0
    return float(np.mean(np.abs(ac_a[:n] - ac_b[:n])) / 2.0)


def _changepoint_distortion(a: np.ndarray, b: np.ndarray) -> float:
    """Symmetric matching error between changepoint sets in relative position."""
    cp_a = np.asarray(changepoints(a), dtype=np.float64) / max(len(a), 1)
    cp_b = np.asarray(changepoints(b), dtype=np.float64) / max(len(b), 1)
    if len(cp_a) == 0 and len(cp_b) == 0:
        return 0.0
    if len(cp_a) == 0 or len(cp_b) == 0:
        return min(1.0, 0.5 + 0.1 * abs(len(cp_a) - len(cp_b)))
    d_ab = np.mean([np.min(np.abs(cp_b - c)) for c in cp_a])
    d_ba = np.mean([np.min(np.abs(cp_a - c)) for c in cp_b])
    pos_term = float(min(1.0, (d_ab + d_ba)))
    count_term = abs(len(cp_a) - len(cp_b)) / max(len(cp_a), len(cp_b))
    return float(0.6 * pos_term + 0.4 * min(1.0, count_term))


def _extreme_distortion(a: np.ndarray, b: np.ndarray) -> float:
    """Did the tails survive? Compares tail spread and exceedance counts.

    Both series are put on the *original* robust scale so that flattening the
    peaks registers as loss rather than being normalised away.
    """
    s = _scale(a)
    med = float(np.median(a))
    za = (a - med) / s
    zb = (b - med) / s

    def tails(z):
        hi = float(np.percentile(z, 99))
        lo = float(np.percentile(z, 1))
        n_hi = float(np.mean(z > 3.0))
        n_lo = float(np.mean(z < -3.0))
        return hi, lo, n_hi, n_lo

    hi_a, lo_a, nhi_a, nlo_a = tails(za)
    hi_b, lo_b, nhi_b, nlo_b = tails(zb)
    spread_term = 0.5 * (_bounded(hi_a - hi_b, k=1.0) + _bounded(lo_a - lo_b, k=1.0))
    count_term = min(1.0, abs(nhi_a - nhi_b) + abs(nlo_a - nlo_b))
    return float(0.6 * spread_term + 0.4 * count_term)


def _shape_distortion(a: np.ndarray, b: np.ndarray) -> float:
    """Point-wise deviation, on the original scale, plus loss of correlation."""
    n = min(len(a), len(b))
    if n < 2:
        return 1.0
    s = _scale(a)
    rmse = float(np.sqrt(np.mean((a[:n] - b[:n]) ** 2)) / s)
    sa, sb = np.std(a[:n]), np.std(b[:n])
    if sa < 1e-9 or sb < 1e-9:
        corr = 1.0 if abs(sa - sb) < 1e-9 else 0.0
    else:
        corr = float(np.corrcoef(a[:n], b[:n])[0, 1])
        if not np.isfinite(corr):
            corr = 0.0
    return float(0.5 * _bounded(rmse, k=0.3) + 0.5 * (1.0 - max(0.0, corr)))


def align_for_action(original: np.ndarray, candidate: np.ndarray,
                     action: Action, params: dict) -> tuple:
    """Slice the original down to the span an action retained, if it cropped."""
    if Action(action) is Action.RESEGMENT and "lo" in params and "hi" in params:
        lo, hi = int(params["lo"]), int(params["hi"])
        return np.asarray(original, dtype=np.float64)[lo:hi], candidate
    return original, candidate


def structure_distortion(
    original: np.ndarray,
    candidate: np.ndarray,
    action: Action = Action.KEEP,
    params: dict = None,
    touched: np.ndarray = None,
    weights: dict = None,
) -> StructureReport:
    """Bounded structural distortion caused by one intervention.

    Returns 0 for an identity edit and approaches 1 as the intervention
    destroys the trend, periodicity, spectrum, memory, changepoints, tails and
    point-wise shape of the window.

    Local operators are judged outside their declared footprint (see
    :data:`LOCAL_WEIGHTS`); global ones are judged on the signal band and the
    tails (see :data:`GLOBAL_WEIGHTS`).
    """
    params = params or {}
    action = Action(action)
    is_local = action in LOCAL_ACTIONS
    weights = weights or (LOCAL_WEIGHTS if is_local else GLOBAL_WEIGHTS)

    a_raw, b_raw = align_for_action(original, candidate, action, params)
    a, b = _clean(a_raw), _clean(b_raw)

    if len(a) < 8 or len(b) < 8:
        return StructureReport(distortion=1.0, parts={"error": "too short"})

    if is_local:
        keep = _untouched_mask(touched, len(a), len(b))
        a_keep, b_keep = a[keep], b[keep]
        if len(a_keep) >= 8:
            parts = {
                "shape": _shape_distortion(a_keep, b_keep),
                "extremes": _extreme_distortion(a_keep, b_keep),
            }
        else:
            parts = {
                "shape": _shape_distortion(a, b),
                "extremes": _extreme_distortion(a, b),
            }
        parts["patch"] = _patch_distortion(b, touched)
        parts["footprint"] = _footprint(touched, params, len(a))
    else:
        parts = {
            "trend": _trend_distortion(a, b),
            "period": _period_distortion(a, b),
            "spectrum": _spectrum_distortion(a, b, hi_frac=SIGNAL_BAND),
            "acf": _acf_distortion(a, b),
            "changepoint": _changepoint_distortion(a, b),
            "extremes": _extreme_distortion(a, b),
        }

    parts = {k: float(np.clip(v, 0.0, 1.0)) for k, v in parts.items()}
    total_w = sum(weights.get(k, 0.0) for k in parts)
    mean_term = sum(weights.get(k, 0.0) * v for k, v in parts.items()) / max(total_w, 1e-9)
    worst_term = max(parts.values())
    distortion = float(0.7 * mean_term + 0.3 * worst_term)
    return StructureReport(distortion=distortion, parts=parts)


def _patch_distortion(candidate: np.ndarray, touched: np.ndarray,
                      context: int = 32) -> float:
    """Is what the operator wrote coherent with the data around it?

    Point-wise fidelity says nothing about the repaired span itself -- the
    original values there were the defect. What can be checked is whether the
    replacement behaves like its neighbourhood: it should join at the seams
    without a jump, and it should have comparable local variability. Filling a
    forty-point gap with a straight line passes every global descriptor and
    fails here, which is the point.
    """
    if touched is None:
        return 0.0
    t = np.asarray(touched, dtype=bool)
    b = np.asarray(candidate, dtype=np.float64)
    n = min(len(t), len(b))
    t, b = t[:n], b[:n]
    runs = _runs(t)
    if not runs:
        return 0.0

    scores = []
    for lo, hi in runs:
        left = b[max(0, lo - context) : lo]
        right = b[hi : min(n, hi + context)]
        nbr = np.concatenate([left, right])
        if len(nbr) < 8:
            continue
        d_nbr = np.abs(np.diff(nbr))
        typ = float(np.median(d_nbr))
        if typ < 1e-9:
            typ = float(np.mean(d_nbr)) or 1e-9

        # Seam continuity: a jump many times the typical step is implausible.
        jumps = []
        if lo > 0:
            jumps.append(abs(b[lo] - b[lo - 1]))
        if hi < n:
            jumps.append(abs(b[hi] - b[hi - 1]))
        seam = _bounded(max(max(jumps) / typ - 3.0, 0.0), k=6.0) if jumps else 0.0

        # Variability match: the patch should neither be flat nor wilder than
        # its context. Compared in log-ratio so both failures are symmetric.
        patch = b[lo:hi]
        if len(patch) >= 3:
            d_patch = float(np.median(np.abs(np.diff(patch))))
            ratio = (d_patch + 1e-9) / (typ + 1e-9)
            # Local variability fluctuates on its own; a patch within a factor
            # of two of its context is unremarkable. Only what lies outside
            # that band counts -- a flat fill (ratio -> 0) still scores 1.
            excess = max(abs(np.log(max(ratio, 1e-6))) - 0.7, 0.0)
            spread = _bounded(excess, k=1.0)
        else:
            spread = 0.0

        scores.append(0.5 * seam + 0.5 * spread)

    return float(np.mean(scores)) if scores else 0.0


def _runs(mask: np.ndarray) -> list:
    """Contiguous True runs as (lo, hi) half-open pairs."""
    runs = []
    i, T = 0, len(mask)
    while i < T:
        if mask[i]:
            j = i
            while j < T and mask[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def _untouched_mask(touched: np.ndarray, len_a: int, len_b: int) -> np.ndarray:
    """Points present in both series that the operator did not claim."""
    n = min(len_a, len_b)
    keep = np.ones(n, dtype=bool)
    if touched is not None:
        t = np.asarray(touched, dtype=bool)
        if len(t) >= n:
            keep &= ~t[:n]
    return keep


def _footprint(touched: np.ndarray, params: dict, length: int) -> float:
    """How much of the window the operator *rewrote*, in [0, 1].

    Cropping is not rewriting. RESEGMENT declares no footprint because it
    leaves every point it keeps exactly as it found it -- what it discards is a
    cost, not a distortion, and is charged through R(a) instead. Folding it in
    here would mean any resegmentation deep enough to be worth doing is vetoed
    on structural grounds it never actually violated.
    """
    if touched is not None and len(touched) > 0:
        return float(np.mean(np.asarray(touched, dtype=bool)))
    return 0.0
