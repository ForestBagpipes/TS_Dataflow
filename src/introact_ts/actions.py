"""The curation action space.

Every operator is a pure function of a series: it returns a *new* array and
never touches the input. That is what makes the agent's interventions
reversible -- the sandbox holds the candidate, the original stays intact until
verification passes.

Operators are deliberately conservative. DESPIKE only removes spikes that are
narrow *and* return to the local baseline, so a genuine regime shift or a real
sustained extreme event is left alone; RESEGMENT refuses to cut away more than
it keeps. Being unable to act is a valid outcome, reported through
``applicable=False`` rather than by silently returning the input.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import savgol_filter

from .types import Action

#: Real sensor series contain genuine constant stretches (a load sitting at
#: its floor overnight). A run has to be long enough that a stuck sensor is
#: the better explanation before it counts as missing.
MIN_FLATLINE_RUN = 16


@dataclass
class ActionOutcome:
    """Result of applying one operator in the sandbox.

    ``touched`` marks the points the operator claims to have rewritten. It is
    what lets verification ask the sharper question -- not "did anything
    change?" but "did anything change that this action did not claim?" -- and
    it is ``None`` for operators that rewrite the window as a whole.
    """

    series: np.ndarray
    params: dict = field(default_factory=dict)
    applicable: bool = True
    cost: float = 0.0
    note: str = ""
    touched: np.ndarray = None


# -- detection helpers ------------------------------------------------------


def robust_scale(series: np.ndarray, n_blocks: int = 8) -> float:
    """Typical local spread of a window, immune to level displacement.

    The median of per-block interquartile ranges, not the IQR of the whole
    window. The distinction is not cosmetic: a displaced segment inflates the
    global IQR roughly threefold on this corpus, and since that quantity is the
    denominator of every scale-free indicator here -- forecast error, jump
    magnitude, noise ratio -- the contamination ends up dividing away its own
    evidence and reads as an easier-than-average window. Blockwise, only the
    block spanning the break is affected and the median discards it.
    """
    series = np.asarray(series, dtype=np.float64)
    finite = series[np.isfinite(series)]
    if finite.size == 0:
        return 1e-8

    def iqr(x):
        q75, q25 = np.percentile(x, [75, 25])
        return float(q75 - q25)

    scale = 0.0
    if finite.size >= 4 * n_blocks:
        spreads = [iqr(b) for b in np.array_split(finite, n_blocks) if len(b) >= 4]
        positive = [v for v in spreads if v > 1e-12]
        if positive:
            scale = float(np.median(positive))
    if scale < 1e-8:
        scale = iqr(finite)
    if scale < 1e-8:
        scale = float(np.std(finite))
    return max(scale, 1e-8)


def missing_mask(
    series: np.ndarray,
    min_run: int = MIN_FLATLINE_RUN,
    context: int = 8,
    activity_ratio: float = 0.4,
) -> np.ndarray:
    """Points that are missing outright (NaN) or frozen by a stuck sensor.

    Length alone does not identify a stuck sensor. Real series sit still for
    long stretches on their own -- an overnight load at its floor, a quantised
    reading that stops resolving -- and flagging those as missing sends clean
    windows to the imputer. What distinguishes a fault is the *transition*: a
    stuck sensor freezes out of ordinary movement and thaws back into it, so
    the run is bracketed by activity, whereas a natural plateau is entered and
    left gradually and its neighbourhood is as quiet as it is.
    """
    series = np.asarray(series, dtype=np.float64)
    mask = ~np.isfinite(series)
    d = np.diff(series)
    frozen = np.isfinite(d) & (np.abs(d) < 1e-12)

    moving = np.abs(d[np.isfinite(d) & (np.abs(d) > 1e-12)])
    typical = float(np.median(moving)) if len(moving) else 0.0

    T = len(series)
    run_start = None
    for i in range(len(frozen) + 1):
        active = i < len(frozen) and frozen[i]
        if active and run_start is None:
            run_start = i
        elif not active and run_start is not None:
            lo, hi = run_start, i + 1
            if hi - lo >= min_run and _bracketed_by_activity(
                d, lo, hi, T, context, typical, activity_ratio
            ):
                mask[lo:hi] = True
            run_start = None
    return mask


def _bracketed_by_activity(
    d: np.ndarray, lo: int, hi: int, T: int, context: int,
    typical: float, ratio: float,
) -> bool:
    """Is this frozen run surrounded by movement typical of the series?"""
    if typical <= 0.0:
        return True
    before = np.abs(d[max(0, lo - context) : lo])
    after = np.abs(d[min(hi, len(d)) : min(hi + context, len(d))])
    edges = np.concatenate([before, after])
    edges = edges[np.isfinite(edges)]
    if len(edges) == 0:
        return True
    return float(np.median(edges)) >= ratio * typical


def hampel_outliers(
    series: np.ndarray, window: int = 11, n_sigma: float = 4.0
) -> np.ndarray:
    """Hampel filter: points far from the local median in robust units."""
    series = np.asarray(series, dtype=np.float64)
    T = len(series)
    half = max(1, window // 2)
    flags = np.zeros(T, dtype=bool)
    padded = np.pad(series, half, mode="reflect")
    for i in range(T):
        seg = padded[i : i + 2 * half + 1]
        seg = seg[np.isfinite(seg)]
        if len(seg) < 3:
            continue
        med = np.median(seg)
        mad = np.median(np.abs(seg - med))
        sigma = 1.4826 * mad
        if sigma < 1e-9:
            sigma = np.std(seg)
        if sigma < 1e-9:
            continue
        if np.isfinite(series[i]) and abs(series[i] - med) > n_sigma * sigma:
            flags[i] = True
    return flags


def isolated_spikes(
    series: np.ndarray,
    window: int = 11,
    n_sigma: float = 4.0,
    max_width: int = 3,
    min_prominence: float = 1.2,
) -> np.ndarray:
    """Outliers that form short runs, i.e. spikes rather than regime changes.

    Two filters, and both matter. A sustained excursion (a level shift, a
    multi-hour peak that is genuinely in the data) produces a long run of flags
    and is deliberately *not* returned: that is the main guard against
    over-cleaning rare-but-valid structure. A point must also clear
    ``min_prominence`` times the window's global spread, which stops a merely
    noisy series from registering as a field of spikes -- local MAD adapts to
    the noise floor, but a genuine spike towers over the whole window.
    """
    x = np.asarray(series, dtype=np.float64)
    flags = hampel_outliers(x, window=window, n_sigma=n_sigma)
    finite = x[np.isfinite(x)]
    if len(finite) >= 8:
        q75, q25 = np.percentile(finite, [75, 25])
        spread = max(float(q75 - q25), 1e-8)
        med = float(np.median(finite))
        prominent = np.zeros_like(flags)
        prominent[np.isfinite(x)] = (
            np.abs(finite - med) / spread >= min_prominence
        )
        flags = flags & prominent

    keep = np.zeros_like(flags)
    i = 0
    T = len(flags)
    while i < T:
        if not flags[i]:
            i += 1
            continue
        j = i
        while j < T and flags[j]:
            j += 1
        if j - i <= max_width:
            keep[i:j] = True
        i = j
    return keep


def dominant_period(series: np.ndarray, min_period: int = 4) -> int:
    """Dominant seasonal period from the periodogram, 0 if none stands out."""
    x = np.asarray(series, dtype=np.float64)
    x = x[np.isfinite(x)]
    T = len(x)
    if T < 4 * min_period:
        return 0
    spec = np.abs(np.fft.rfft(x - x.mean())) ** 2
    freqs = np.fft.rfftfreq(T)
    valid = (freqs > 1.0 / (T / 2.0)) & (freqs <= 1.0 / min_period)
    if not valid.any():
        return 0
    idx = np.argmax(spec[valid])
    peak_freq = freqs[valid][idx]
    if peak_freq <= 0:
        return 0
    energy = spec[valid][idx] / (spec[valid].sum() + 1e-12)
    if energy < 0.05:
        return 0
    return int(round(1.0 / peak_freq))


def changepoints(series: np.ndarray, penalty: float = 25.0, min_size: int = 24) -> list:
    """PELT changepoints on a robustly scaled series."""
    import ruptures as rpt

    x = np.asarray(series, dtype=np.float64)
    x = np.nan_to_num(x, nan=float(np.nanmedian(x)) if np.isfinite(x).any() else 0.0)
    sd = np.std(x)
    if sd < 1e-9 or len(x) < 3 * min_size:
        return []
    try:
        algo = rpt.Pelt(model="l2", min_size=min_size).fit((x - x.mean()) / sd)
        bkps = algo.predict(pen=penalty)
    except Exception:
        return []
    return [int(b) for b in bkps if 0 < b < len(x)]


# -- operators --------------------------------------------------------------


def op_keep(series: np.ndarray, **kw) -> ActionOutcome:
    return ActionOutcome(
        series=np.asarray(series, dtype=np.float64).copy(),
        params={},
        applicable=True,
        cost=0.0,
        note="unchanged",
    )


def op_impute(
    series: np.ndarray,
    min_run: int = MIN_FLATLINE_RUN,
    method: str = "seasonal",
    **kw,
) -> ActionOutcome:
    """Fill NaNs and frozen runs.

    ``linear`` interpolates between the gap's edges; ``seasonal`` additionally
    donates the shape from one period earlier for gaps long enough that a
    straight line would be conspicuous.

    Which is better is genuinely data-dependent -- seasonal filling helps when
    the periodicity is strong and actively hurts when it is not -- so the choice
    is left to the policy as two competing candidates rather than settled here.
    Verification decides.
    """
    x = np.asarray(series, dtype=np.float64).copy()
    mask = missing_mask(x, min_run=min_run)
    n_missing = int(mask.sum())
    if n_missing == 0 or n_missing >= len(x) - 4:
        return ActionOutcome(x, {"n_filled": 0}, applicable=False, note="nothing to fill")

    idx = np.arange(len(x))
    good = ~mask & np.isfinite(x)
    if good.sum() < 4:
        return ActionOutcome(x, {"n_filled": 0}, applicable=False, note="too few anchors")

    filled = x.copy()
    filled[mask] = np.interp(idx[mask], idx[good], x[good])

    period = dominant_period(x[good]) if method == "seasonal" else 0
    n_seasonal = 0
    if period >= 4:
        for lo, hi in _mask_runs(mask):
            if hi - lo < max(4, period // 2):
                continue
            # Level offset between the gap's left edge and the same phase one
            # period earlier, so the donated shape lands at the right level.
            here = filled[max(0, lo - period) : lo]
            there = x[max(0, lo - 2 * period) : max(0, lo - period)]
            offset = 0.0
            if len(here) >= 2 and len(there) >= 2:
                offset = float(np.median(here) - np.median(there))
            if not np.isfinite(offset):
                offset = 0.0
            for t in range(lo, hi):
                src = t - period
                while src >= 0 and (mask[src] or not np.isfinite(x[src])):
                    src -= period
                if src >= 0:
                    filled[t] = x[src] + offset
                    n_seasonal += 1

    return ActionOutcome(
        series=filled,
        touched=mask.copy(),
        params={
            "n_filled": n_missing,
            "n_seasonal": n_seasonal,
            "period": int(period),
            "method": method,
            "n_seasonal_used": n_seasonal,
        },
        applicable=True,
        cost=float(n_missing) / len(x),
        note=f"filled {n_missing} points",
    )


def _mask_runs(mask: np.ndarray) -> list:
    """Contiguous True runs of a boolean mask as (lo, hi) half-open pairs."""
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


def op_despike(
    series: np.ndarray,
    window: int = 11,
    n_sigma: float = 4.0,
    max_width: int = 3,
    **kw,
) -> ActionOutcome:
    """Replace narrow, isolated spikes with the local median."""
    x = np.asarray(series, dtype=np.float64).copy()
    flags = isolated_spikes(x, window=window, n_sigma=n_sigma, max_width=max_width)
    n_spikes = int(flags.sum())
    if n_spikes == 0:
        return ActionOutcome(x, {"n_replaced": 0}, applicable=False, note="no spikes")

    out = x.copy()
    half = max(1, window // 2)
    for lo, hi in _mask_runs(flags):
        left = x[max(0, lo - half) : lo]
        right = x[hi : hi + half]
        left = left[np.isfinite(left)]
        right = right[np.isfinite(right)]
        anchor_l = np.median(left) if len(left) else np.nan
        anchor_r = np.median(right) if len(right) else np.nan
        if np.isfinite(anchor_l) and np.isfinite(anchor_r):
            out[lo:hi] = np.linspace(anchor_l, anchor_r, hi - lo + 2)[1:-1]
        elif np.isfinite(anchor_l):
            out[lo:hi] = anchor_l
        elif np.isfinite(anchor_r):
            out[lo:hi] = anchor_r
    return ActionOutcome(
        series=out,
        touched=flags.copy(),
        params={"n_replaced": n_spikes, "n_sigma": n_sigma, "max_width": max_width},
        applicable=True,
        cost=float(n_spikes) / len(x),
        note=f"replaced {n_spikes} spike points",
    )


def op_denoise(
    series: np.ndarray, strength: str = "medium", **kw
) -> ActionOutcome:
    """Savitzky-Golay smoothing, which preserves peak shape better than an MA.

    Strength controls the window; the polynomial order stays at 2 so local
    curvature (peaks, troughs) survives.
    """
    x = np.asarray(series, dtype=np.float64).copy()
    T = len(x)
    if T < 15 or not np.isfinite(x).all():
        return ActionOutcome(x, {}, applicable=False, note="too short or has NaN")

    win_map = {"light": 5, "medium": 11, "heavy": 21}
    window = int(win_map.get(strength, 11))
    window = min(window, T - 1 if (T - 1) % 2 == 1 else T - 2)
    if window < 5:
        return ActionOutcome(x, {}, applicable=False, note="window too small")
    if window % 2 == 0:
        window += 1

    smoothed = savgol_filter(x, window_length=window, polyorder=2)
    removed = float(np.std(x - smoothed))
    return ActionOutcome(
        series=smoothed,
        params={"window": window, "polyorder": 2, "strength": strength,
                "removed_std": removed},
        applicable=True,
        cost=0.2,
        note=f"savgol w={window}",
    )


def op_resegment(
    series: np.ndarray,
    penalty: float = 12.0,
    min_size: int = 24,
    min_keep_frac: float = 0.5,
    **kw,
) -> ActionOutcome:
    """Cut at the strongest changepoint and keep the longer homogeneous piece.

    Refuses to act when the surviving piece would be shorter than
    ``min_keep_frac`` of the window: discarding most of a window is a deletion,
    not a resegmentation, and should go through QUARANTINE instead.
    """
    x = np.asarray(series, dtype=np.float64).copy()
    T = len(x)
    bkps = changepoints(x, penalty=penalty, min_size=min_size)
    if not bkps:
        return ActionOutcome(x, {}, applicable=False, note="no changepoint")

    edges = [0] + bkps + [T]
    segments = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    lo, hi = max(segments, key=lambda s: s[1] - s[0])
    keep_frac = (hi - lo) / T
    if keep_frac < min_keep_frac:
        return ActionOutcome(
            x, {"keep_frac": keep_frac}, applicable=False, note="would discard too much"
        )
    if hi - lo == T:
        return ActionOutcome(x, {}, applicable=False, note="no effective cut")

    return ActionOutcome(
        series=x[lo:hi].copy(),
        params={"lo": int(lo), "hi": int(hi), "keep_frac": float(keep_frac),
                "n_changepoints": len(bkps)},
        applicable=True,
        cost=1.0 - keep_frac,
        note=f"kept [{lo},{hi}) of {T}",
    )


def op_quarantine(series: np.ndarray, **kw) -> ActionOutcome:
    return ActionOutcome(
        series=np.asarray(series, dtype=np.float64).copy(),
        params={},
        applicable=True,
        cost=0.0,
        note="set aside, series untouched",
    )


def op_abstain(series: np.ndarray, **kw) -> ActionOutcome:
    return ActionOutcome(
        series=np.asarray(series, dtype=np.float64).copy(),
        params={},
        applicable=True,
        cost=0.0,
        note="refused to act",
    )


OPERATORS = {
    Action.KEEP: op_keep,
    Action.IMPUTE: op_impute,
    Action.DESPIKE: op_despike,
    Action.DENOISE: op_denoise,
    Action.RESEGMENT: op_resegment,
    Action.QUARANTINE: op_quarantine,
    Action.ABSTAIN: op_abstain,
}


def apply_action(series: np.ndarray, action: Action, **params) -> ActionOutcome:
    """Apply one operator in the sandbox. The input array is never modified."""
    op = OPERATORS[Action(action)]
    return op(series, **params)
