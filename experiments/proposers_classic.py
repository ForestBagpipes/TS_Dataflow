"""Two published cleaning algorithms, used as proposers.

Every proposer compared so far is our own construction, which makes the
modularity claim vulnerable to the charge that the gate was only ever tested
against straw men. These two are published methods with complete algorithmic
descriptions, reimplemented here and fed into the same acceptance layer as
everything else.

Why these two and not the more recent systems. Both are univariate. Our
curation window is a one dimensional series of length 512, verified by
inspection of the corpus, and the recent alternatives are multivariate methods
whose cross variable constraints have no referent on such a window. Scoping
them down would raise exactly the faithfulness dispute already documented for
the sequential curation system, where a reconstructed component makes any
resulting number less trustworthy than no number. Recency is carried elsewhere:
by the verification strategy baselines, which include mechanism level stand ins
for two 2026 systems, and by the five execution time gating papers in related
work. At the proposer layer, classical methods reproduce with less dispute.

Both are implemented from their published descriptions. Neither sees a label,
neither sees the pristine series, and the audit notes in
`docs/classic_proposers.md` record what each was given and what it was denied.
"""

import numpy as np

# -- SCREEN, speed constraint based repair, SIGMOD 2015 ----------------------
#
# The method assumes a maximum and minimum rate of change between consecutive
# observations, and repairs each point to the median of three candidates: the
# tightest lower bound implied by preceding repaired points, the tightest upper
# bound implied by the same, and a candidate derived from the following window.
# The local variant is used, which is the one the paper gives in full and which
# processes a bounded window rather than solving a global program.


def estimate_speed_bounds(series_list, lo_q: float = 1.0, hi_q: float = 99.0):
    """Estimate the speed constraint from a set of series.

    The paper takes the constraint as given by a domain expert. We have no such
    expert, so it is estimated from quantiles of the observed first difference
    across the corpus the proposer is allowed to see. Using a quantile rather
    than the extremes matters: with the extremes the constraint admits every
    observed transition including the contaminated ones, and the method becomes
    the identity.
    """
    diffs = []
    for s in series_list:
        s = np.asarray(s, dtype=np.float64)
        s = s[np.isfinite(s)]
        if len(s) > 1:
            diffs.append(np.diff(s))
    if not diffs:
        return -1.0, 1.0
    d = np.concatenate(diffs)
    return float(np.percentile(d, lo_q)), float(np.percentile(d, hi_q))


def screen_repair(series, s_min: float, s_max: float, window: int = 5):
    """Local speed constraint repair.

    Returns the repaired series. NaN entries are left untouched, since this
    method repairs values rather than filling gaps, and pretending otherwise
    would credit it with an operation it does not perform.
    """
    x = np.asarray(series, dtype=np.float64).copy()
    n = len(x)
    if n < 3:
        return x
    known = np.isfinite(x)

    for k in range(n):
        if not known[k]:
            continue
        lo, hi = -np.inf, np.inf
        for i in range(max(0, k - window), k):
            if not known[i]:
                continue
            dt = k - i
            lo = max(lo, x[i] + s_min * dt)
            hi = min(hi, x[i] + s_max * dt)

        cands = [x[k]]
        for i in range(k + 1, min(n, k + window + 1)):
            if not known[i]:
                continue
            dt = i - k
            cands.append(x[i] - s_max * dt)
            cands.append(x[i] - s_min * dt)
        x_mid = float(np.median(cands))

        if np.isfinite(lo) and np.isfinite(hi):
            if lo > hi:
                lo, hi = hi, lo
            x[k] = float(np.median([lo, hi, x_mid]))
        else:
            x[k] = x_mid
    return x


# -- IMR, iterative minimum repair, VLDB 2017 --------------------------------
#
# The method fits an autoregressive model to the sequence, identifies the point
# whose observation departs most from the model prediction, repairs that single
# point, refits, and iterates until no candidate exceeds a threshold or a step
# budget is exhausted. Repairing one point at a time and refitting is the part
# that matters, since a batch repair lets one error distort the model that
# judges the next.
#
# The published method is semi supervised: it is given a set of positions whose
# values are known correct, and it propagates from them. **We give it no
# labels**, because none exist in the deployment setting this paper studies and
# supplying them from the pristine series would be handing it the answer. This
# is a deviation from the published setting and it is a deviation that makes
# the method weaker, which is recorded in the audit note rather than hidden.


def _ar_fit_predict(x, p: int = 3):
    """One step ahead AR(p) prediction for every position it can cover."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n <= p + 2:
        return None
    rows = np.lib.stride_tricks.sliding_window_view(x, p + 1)
    X, y = rows[:, :-1], rows[:, -1]
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y)
    if ok.sum() < p + 2:
        return None
    A = np.column_stack([X[ok], np.ones(ok.sum())])
    try:
        coef, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
    except np.linalg.LinAlgError:
        return None
    pred = np.full(n, np.nan)
    full = np.column_stack([X, np.ones(len(X))])
    valid = np.isfinite(full).all(axis=1)
    pred[p:][valid] = full[valid] @ coef
    return pred


def imr_repair(series, p: int = 3, max_iter: int = 20, tol_scale: float = 3.0):
    """Iterative minimum repair, unsupervised variant.

    At each step the point with the largest standardised residual against the
    autoregressive prediction is replaced by that prediction, and the model is
    refitted. The loop stops when no residual exceeds `tol_scale` robust
    deviations or the step budget runs out.
    """
    x = np.asarray(series, dtype=np.float64).copy()
    n = len(x)
    if n <= p + 2:
        return x
    repaired = 0
    for _ in range(max_iter):
        pred = _ar_fit_predict(x, p)
        if pred is None:
            break
        resid = x - pred
        finite = np.isfinite(resid)
        if finite.sum() < p + 2:
            break
        r = resid[finite]
        scale = 1.4826 * float(np.median(np.abs(r - np.median(r))))
        if scale <= 1e-12:
            break
        z = np.full(n, 0.0)
        z[finite] = np.abs(resid[finite]) / scale
        k = int(np.argmax(z))
        if z[k] <= tol_scale:
            break
        x[k] = float(pred[k])
        repaired += 1
    return x


def imr_repair_supervised(series, clean_prefix_frac: float = 0.1, **kw):
    """Variant that receives a prefix of known good values, as the paper assumes.

    Not used in the main comparison. It exists so the audit note can state what
    the published setting would give the method, and it takes the prefix from
    the series under repair rather than from any pristine reference, so it is
    still not being handed the answer.
    """
    x = np.asarray(series, dtype=np.float64).copy()
    n = len(x)
    seed = max(int(n * clean_prefix_frac), kw.get("p", 3) + 2)
    head, tail = x[:seed], x[seed:]
    if len(tail) == 0:
        return x
    joined = np.concatenate([head, tail])
    out = imr_repair(joined, **kw)
    out[:seed] = head
    return out


# -- MTCSC, univariate branch, speed constraint with a consistency anchor -----
#
# Multivariate Time Series Cleaning under Speed Constraints, arXiv 2411.01214,
# 2024. The reference implementation is `zaqthss/mtcsc`, class `MTCSC_Uni`, and
# it ships no license file, so this is reimplemented from the algorithm the
# class expresses rather than translated from it.
#
# The difference from SCREEN is what makes it worth measuring rather than
# assuming. SCREEN repairs each point to the median of three candidates derived
# from the speed bounds. MTCSC's univariate branch first looks for the longest
# run of consecutive points that are mutually speed consistent inside the
# window, treats the head of that run as a trustworthy anchor, and then repairs
# the key point by linear interpolation between the last repaired point and that
# anchor. So SCREEN asks what value the bounds allow, and MTCSC asks which
# neighbours agree with each other and pulls the point toward them.
#
# Both are given the same speed bounds from `estimate_speed_bounds`, so any
# difference in output is a difference in repair rule and not in calibration.


def mtcsc_uni_repair(series, s_min: float, s_max: float, window: int = 5):
    """Univariate MTCSC. Returns the repaired series.

    ``window`` is the number of subsequent points the anchor is searched over,
    matching the reference implementation's time window on an evenly sampled
    series where one timestamp step equals one index step.

    NaN entries are left untouched, the same convention `screen_repair` uses,
    since this method repairs values rather than filling gaps.
    """
    x = np.asarray(series, dtype=np.float64).copy()
    n = len(x)
    if n < 3:
        return x
    known = np.isfinite(x)
    idx = np.flatnonzero(known)
    if len(idx) < 3:
        return x

    prev = idx[0]
    for pos in range(1, len(idx)):
        k = idx[pos]
        tail = idx[pos:pos + window + 1]
        if len(tail) < 2:
            break

        lo = x[prev] + s_min * (k - prev)
        hi = x[prev] + s_max * (k - prev)

        # Longest run of mutually speed consistent points in the window. `run`
        # counts, for each start, how far the consistency extends.
        run = np.ones(len(tail), dtype=int)
        for i in range(len(tail) - 2, -1, -1):
            a, b = tail[i], tail[i + 1]
            d, dt = x[b] - x[a], b - a
            if s_min * dt <= d <= s_max * dt:
                run[i] = run[i + 1] + 1
        # The anchor is the head of the longest run, excluding the key point
        # itself, which is the candidate under repair.
        if len(tail) > 1:
            rel = int(np.argmax(run[1:])) + 1
        else:
            rel = 0
        anchor = tail[rel]

        # Bounds implied by the anchor, intersected with those from the last
        # repaired point. The reference intersects only when an anchor other
        # than the key point was found.
        if anchor != k:
            lo_a = x[anchor] + s_max * (k - anchor)
            hi_a = x[anchor] + s_min * (k - anchor)
            lo, hi = max(lo, lo_a), min(hi, hi_a)

        if x[k] < lo or x[k] > hi:
            span = anchor - prev
            if span != 0:
                rate = (k - prev) / span
                x[k] = (x[anchor] - x[prev]) * rate + x[prev]
            else:
                x[k] = x[prev]
        prev = k

    return x
