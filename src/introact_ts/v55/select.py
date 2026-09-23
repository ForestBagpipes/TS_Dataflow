"""Partially pooled utility estimation and a conformal execution gate.

Two changes to the v54 decision layer, both registered in
``docs/v55_plan_20260923.md``.

The first is the estimator.  A neighbourhood of eight to thirty two bank
records gives a noisy mean, and a source level mean over the whole bank gives a
stable one that cannot see variation inside a source.  The v54 rule used the
first alone and the source fixed policy used the second alone, and on the
recorded evaluation each won on a different backbone.  The pooled estimator
shrinks the local mean towards the source level mean with a strength that the
same leave one parent out procedure selects,

    mu_tilde = (n_eff * mu_local + lam * m_source) / (n_eff + lam),
    S        = mu_tilde - beta * sigma / sqrt(n_eff + lam).

``lam = 0`` reproduces the v54 rule exactly and ``lam = inf`` reduces the score
to the source level mean, so the search contains both earlier rules and cannot
choose a setting that is worse than either on the training side.

The second is the gate.  v54 executed whenever the top score was positive,
which is a convention and carries no guarantee.  Here the threshold is
calibrated by conformal risk control on a block that took no part in selecting
``(k, beta, lam)``, so the harmful loss of the deployed rule has a finite
sample bound.

Nothing in this module reads a future target, a candidate's forecast or a TEST
record while a decision is being made.
"""

from __future__ import annotations

import numpy as np

from introact_ts.v44 import protocol as P
from introact_ts.v47 import select as SEL

ACTIONS = SEL.ACTIONS
NONREF = SEL.NONREF
REFERENCE = SEL.REFERENCE
TAU_EPSILON = SEL.TAU_EPSILON

K_GRID = P.K_GRID
BETA_GRID = P.BETA_GRID
#: Pooling strengths.  0 is the v54 local rule and inf is the source level
#: rule; the interior values are in units of distinct parents, so 16 means the
#: source level mean carries the weight of sixteen neighbourhood parents.
LAM_GRID = (0.0, 4.0, 16.0, 64.0, float("inf"))

#: Per request harmful loss is a MASE increase and has no natural bound, so
#: conformal risk control needs one.  A single request that loses more than one
#: MASE point counts as one; the clip is registered and reported.
HARM_CLIP = 1.0


# ---------------------------------------------------------------- source means

def source_action_means(bank: SEL.Bank) -> dict:
    """Replay-record mean utility used by the Source Fixed comparison.

    The registered v55 source term is the same quantity that Source Fixed
    maximises.  That policy averages the available replay records, so the
    source term keeps that weighting.  Leave-one-parent-out selection removes
    *all* of a parent's records from the sum and count.
    """
    out = {}
    for action in ACTIONS:
        b = bank.per[action]
        table: dict[str, dict] = {}
        if len(b.g):
            for source in np.unique(b.source):
                take = b.source == source
                values = b.g[take]
                parents = b.parent[take]
                uniq, inv = np.unique(parents, return_inverse=True)
                counts = np.bincount(inv, minlength=len(uniq))
                sums = np.bincount(inv, weights=values, minlength=len(uniq))
                table[str(source)] = {
                    "mean": float(values.mean()),
                    "records": int(values.size),
                    "sum": float(values.sum()),
                    "parent_sum": {str(p): float(v)
                                   for p, v in zip(uniq, sums)},
                    "parent_count": {str(p): int(v)
                                     for p, v in zip(uniq, counts)},
                }
        out[action] = table
    return out


def source_vector(means: dict, action: str, queries: SEL.Queries, *,
                  lopo: bool = False) -> np.ndarray:
    """The source level mean of ``action`` aligned to the query rows.

    With ``lopo`` the query's own parent is removed from its source mean, which
    is what the selection pass needs because there the bank and the queries are
    the same block.  A source the bank has never seen for this action, or a
    source whose only parent is the query's own, yields NaN and the caller
    treats the source term as unavailable for that request.
    """
    table = means.get(action, {})
    out = np.full(len(queries.episode), np.nan)
    for i, source in enumerate(queries.source):
        entry = table.get(str(source))
        if entry is None:
            continue
        if not lopo:
            out[i] = entry["mean"]
            continue
        parent = str(queries.parent[i])
        own = entry["parent_sum"].get(parent)
        if own is None:
            out[i] = entry["mean"]
        elif entry["records"] > entry["parent_count"][parent]:
            out[i] = ((entry["sum"] - own)
                      / (entry["records"] - entry["parent_count"][parent]))
    return out


# -------------------------------------------------------------- local moments

def local_moments(bank: SEL.Bank, queries: SEL.Queries,
                  D: dict, k: int) -> dict:
    """Parent clustered mu, sigma and n_eff of every action on every query.

    This is the expensive half of the v54 score and it depends on ``k`` alone,
    so it is computed once and reused for every ``(beta, lam)`` on the grid.
    The construction is the one the freeze fixes in section 6: the k nearest
    same action records collapse to one entity per distinct parent, the
    parent's utility is the plain mean of its variants and its distance is the
    nearest variant's distance, mu and sigma are the distance weighted moments
    over those entities, and n_eff counts distinct parents.  A query with no
    finite distance gets n_eff zero and the caller treats the local term as
    unavailable.
    """
    n = len(queries.episode)
    out = {}
    for action in ACTIONS:
        b = bank.per[action]
        mu = np.full(n, np.nan)
        sigma = np.full(n, np.nan)
        n_eff = np.zeros(n)
        if len(b.g) == 0:
            out[action] = {"mu": mu, "sigma": sigma, "n_eff": n_eff}
            continue
        d = D[action]
        ke = min(k, d.shape[1])
        idx = np.argpartition(d, ke - 1, axis=1)[:, :ke]
        dd = np.take_along_axis(d, idx, axis=1)
        order = np.argsort(dd, axis=1, kind="stable")
        idx = np.take_along_axis(idx, order, axis=1)
        dd = np.take_along_axis(dd, order, axis=1)
        gg = b.g[idx]
        pp = b.parent[idx]
        for i in range(n):
            finite = np.isfinite(dd[i])
            if not finite.any():
                continue
            dist = dd[i][finite]
            util = gg[i][finite]
            parents = pp[i][finite]
            tau = float(np.median(dist)) + TAU_EPSILON
            uniq, inv = np.unique(parents, return_inverse=True)
            d_parent = np.full(len(uniq), np.inf)
            np.minimum.at(d_parent, inv, dist)
            count = np.bincount(inv, minlength=len(uniq)).astype(np.float64)
            g_parent = np.bincount(inv, weights=util, minlength=len(uniq)) / count
            w = np.exp(-d_parent / tau)
            wsum = float(w.sum())
            if not np.isfinite(wsum) or wsum <= 0.0:
                w = np.ones(len(uniq))
                wsum = float(len(uniq))
            m = float((w * g_parent).sum() / wsum)
            mu[i] = m
            sigma[i] = float(np.sqrt((w * (g_parent - m) ** 2).sum() / wsum))
            n_eff[i] = float(len(uniq))
        out[action] = {"mu": mu, "sigma": sigma, "n_eff": n_eff}
    return out


def scores_from_moments(moments: dict, source_means: dict, queries: SEL.Queries,
                        beta: float, lam: float, *, lopo: bool = False) -> dict:
    """Pooled conservative score of every action on every query.

    ``lam = 0`` returns the v54 score unchanged.  ``lam = inf`` returns the
    source level mean with no dispersion penalty, which is the score a per
    source fixed policy would use.  In between, a request whose neighbourhood
    holds few distinct parents leans on its source and one whose neighbourhood
    is large keeps its local estimate.  A request needs at least one of the two
    terms; with only one available the other drops out of both the numerator
    and the weight, so the penalty never divides by a weight that was not used.
    """
    n = len(queries.episode)
    scores = {}
    for action in ACTIONS:
        mom = moments[action]
        mu, sigma, n_eff = mom["mu"], mom["sigma"], mom["n_eff"]
        m_src = source_vector(source_means, action, queries, lopo=lopo)
        if np.isinf(lam):
            s = np.full(n, -np.inf)
            usable = np.isfinite(m_src)
            s[usable] = m_src[usable]
            scores[action] = s
            continue
        have_local = (n_eff > 0) & np.isfinite(mu)
        if lam == 0.0:
            usable = have_local
            pooled = np.where(usable, mu, np.nan)
            denom = np.where(usable, n_eff, np.nan)
        else:
            have_src = np.isfinite(m_src)
            usable = have_local | have_src
            local_w = np.where(have_local, n_eff, 0.0)
            src_w = np.where(have_src, lam, 0.0)
            total = local_w + src_w
            numer = (np.where(have_local, mu, 0.0) * local_w
                     + np.where(have_src, m_src, 0.0) * src_w)
            positive = total > 0
            with np.errstate(invalid="ignore", divide="ignore"):
                pooled = np.where(positive, numer / np.where(positive, total, 1.0),
                                  np.nan)
            denom = np.where(positive, total, np.nan)
        spread = np.where(np.isfinite(sigma), sigma, 0.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            value = pooled - beta * spread / np.sqrt(denom)
        scores[action] = np.where(usable & np.isfinite(value), value, -np.inf)
    return scores


def decide(queries: SEL.Queries, scores: dict, *, threshold: float = 0.0):
    """Select an action per request, executing only above ``threshold``.

    The reference is the default and wins every tie, exactly as in v54.  The
    only generalisation is that the bar a score has to clear is a parameter
    rather than the constant zero, which is what the conformal calibration
    below sets.
    """
    n = len(queries.episode)
    best = np.full(n, REFERENCE, dtype=object)
    best_score = np.full(n, float(threshold))
    for action in NONREF:
        s = np.where(queries.legal[action], scores[action], -np.inf)
        take = s > best_score
        best[take] = action
        best_score[take] = s[take]
    return best


# ------------------------------------------------------------- conformal gate

def harm_per_request(queries: SEL.Queries, selected, *, clip: float = HARM_CLIP):
    """Loss a decision added on each request, zero when it kept the input.

    The utility of an executed action is the reference loss minus the repaired
    loss, so a negative utility is the amount of MASE the repair added.  Only
    that amount counts, keeping the input contributes nothing, and a request
    that lost more than ``clip`` counts as ``clip`` so the risk has the bounded
    range conformal risk control needs.
    """
    out = np.zeros(len(selected))
    for i, action in enumerate(selected):
        if action == REFERENCE:
            continue
        g = queries.utility[action][i]
        if np.isfinite(g) and g < 0.0:
            out[i] = min(float(-g), float(clip))
    return out


def top_and_harm(queries: SEL.Queries, scores: dict, *, clip: float = HARM_CLIP):
    """Per request top legal score and the harm executing it would add.

    Raising the bar never changes which action wins, only whether the winner is
    executed, so the whole threshold sweep is a function of two vectors: the top
    score of each request and the harm that request would take on if its winner
    ran.  Computing them once turns the sweep into a comparison.
    """
    n = len(queries.episode)
    top = np.full(n, -np.inf)
    best = np.full(n, REFERENCE, dtype=object)
    for action in NONREF:
        s = np.where(queries.legal[action], scores[action], -np.inf)
        take = s > top
        best[take] = action
        top[take] = s[take]
    harm = np.zeros(n)
    for i in range(n):
        if best[i] == REFERENCE or not np.isfinite(top[i]):
            continue
        g = queries.utility[best[i]][i]
        if np.isfinite(g) and g < 0.0:
            harm[i] = min(float(-g), float(clip))
    return top, best, harm


def threshold_candidates(queries: SEL.Queries, scores: dict) -> np.ndarray:
    """Thresholds at which the decision of at least one request changes.

    Sweeping every real number is unnecessary.  The rule only changes when the
    bar passes the top legal score of some request, so those values, together
    with zero as the lower end, are the whole ladder.
    """
    top, _best, _harm = top_and_harm(queries, scores)
    finite = np.unique(top[np.isfinite(top)])
    return np.concatenate([[0.0], finite[finite > 0.0]])


def crc_threshold_from_arrays(top: np.ndarray, harm: np.ndarray, alpha: float,
                              *, clip: float = HARM_CLIP) -> dict:
    """Conformal risk control threshold from precomputed calibration arrays."""
    n = int(len(top))
    finite = np.unique(top[np.isfinite(top)])
    ladder = np.concatenate([[0.0], finite[finite > 0.0]])
    for t in ladder:
        acted = top > t
        risk = float((harm * acted).sum() / n) if n else 0.0
        bound = (n * risk + float(clip)) / (n + 1)
        if bound <= alpha:
            return {"threshold": float(t), "empirical_harm": risk,
                    "crc_bound": bound,
                    "intervention_rate": float(acted.mean()) if n else 0.0}
    # A threshold just above the largest calibration score would still allow
    # a larger future score to execute.  Infinity is the actual KEEP-only rule.
    return {"threshold": float("inf"),
            "empirical_harm": 0.0, "crc_bound": 0.0,
            "intervention_rate": 0.0,
            "note": "no finite threshold reached the level; unconditional "
                    "KEEP has zero harm"}


def crossfit_conformal(queries: SEL.Queries, scores: dict, alphas, *,
                       clip: float = HARM_CLIP) -> list:
    """Calibrate and apply inside one evaluation block by disjoint parent folds.

    A threshold fitted on the training period does not have to transfer to a
    later one, and a served system does not need it to: the target of a request
    becomes visible once its horizon has passed, so a deployment recalibrates on
    recently completed requests.  This routine imitates that.  Parents are
    split into two folds, each fold's threshold comes from the other fold alone,
    and the reported harm is the pooled realised harm of requests that were
    never part of their own calibration sample.
    """
    top, best, harm = top_and_harm(queries, scores, clip=clip)
    parents = [str(p) for p in queries.parent]
    order = sorted(set(parents))
    first = {p for i, p in enumerate(order) if i % 2 == 0}
    fold = np.asarray([p in first for p in parents])
    out = []
    for alpha in alphas:
        applied = np.zeros(len(top), bool)
        thresholds = []
        for cal, app in ((fold, ~fold), (~fold, fold)):
            fit = crc_threshold_from_arrays(top[cal], harm[cal], alpha, clip=clip)
            thresholds.append(fit)
            applied |= app & (top > fit["threshold"])
        realised = float((harm * applied).mean())
        out.append({"alpha": float(alpha),
                    "thresholds": ["inf" if np.isinf(f["threshold"])
                                   else f["threshold"] for f in thresholds],
                    "calibration_harm": [f["empirical_harm"] for f in thresholds],
                    "realised_harm": realised,
                    "respected": bool(realised <= alpha),
                    "intervention_rate": float(applied.mean()),
                    "acted": int(applied.sum()),
                    "folds": [int(fold.sum()), int((~fold).sum())],
                    "applied": applied})
    return out


def decide_with_mask(queries: SEL.Queries, scores: dict, applied: np.ndarray):
    """The decision of the winning action wherever ``applied`` says to execute."""
    top, best, _harm = top_and_harm(queries, scores)
    out = np.full(len(top), REFERENCE, dtype=object)
    take = applied & np.isfinite(top)
    out[take] = best[take]
    return out


def conformal_threshold(queries: SEL.Queries, scores: dict, alpha: float, *,
                        clip: float = HARM_CLIP) -> dict:
    """Smallest threshold whose calibrated harmful loss respects ``alpha``.

    Harmful loss falls as the threshold rises, because a higher bar only ever
    withdraws an execution, so conformal risk control applies directly.  With
    ``n`` calibration requests and a risk bounded by ``clip``, taking the
    smallest threshold that satisfies

        (n * empirical_harm(t) + clip) / (n + 1) <= alpha

    bounds the expected harmful loss of the same rule on an exchangeable
    request by ``alpha``.  If no threshold on the ladder reaches the level the
    rule keeps every input, which has zero harm and always satisfies it.
    """
    ladder = threshold_candidates(queries, scores)
    n = len(queries.episode)
    rows = []
    chosen = None
    for t in ladder:
        selected = decide(queries, scores, threshold=float(t))
        harm = float(harm_per_request(queries, selected, clip=clip).mean())
        bound = (n * harm + float(clip)) / (n + 1)
        acted = int((selected != REFERENCE).sum())
        rows.append({"threshold": float(t), "empirical_harm": harm,
                     "crc_bound": bound, "acted": acted,
                     "intervention_rate": acted / n if n else 0.0})
        if chosen is None and bound <= alpha:
            chosen = rows[-1]
    if chosen is None:
        chosen = {"threshold": float("inf"),
                  "empirical_harm": 0.0,
                  "crc_bound": 0.0,
                  "acted": 0, "intervention_rate": 0.0,
                  "note": "no finite threshold reached the level; unconditional "
                          "KEEP has zero harm"}
    return {"alpha": float(alpha), "clip": float(clip),
            "calibration_requests": int(n),
            "selected": chosen, "ladder": rows}


# ------------------------------------------------------------ hyperparameters

def select_hyperparameters(bank: SEL.Bank, queries: SEL.Queries, *,
                           k_grid=K_GRID, beta_grid=BETA_GRID,
                           lam_grid=LAM_GRID, cap=None) -> dict:
    """Leave one parent out choice of ``(k, beta, lam)`` under the harm cap.

    The rule is the v54 one with a third axis.  Every bank episode is scored
    against a bank with all records of its own parent removed, in the
    neighbourhood and in the source level mean alike, so the pooled estimate is
    as honest as the local one.  Among the settings whose cross validated
    conditional harmful rate respects the cap the lowest cross validated source
    macro MASE wins, a tie goes to the setting that intervenes least, and an
    empty feasible set falls back to KEEP only exactly as before.
    """
    D = SEL.distance_matrices(bank, queries, lopo=True)
    means = source_action_means(bank)
    rows = []
    for k in k_grid:
        moments = local_moments(bank, queries, D, int(k))
        for beta in beta_grid:
            for lam in lam_grid:
                scores = scores_from_moments(moments, means, queries,
                                             float(beta), float(lam), lopo=True)
                selected = decide(queries, scores)
                out = SEL.outcomes(queries, selected)
                rows.append({"k": int(k), "beta": float(beta),
                             "lam": (None if np.isinf(lam) else float(lam)),
                             "lam_is_inf": bool(np.isinf(lam)),
                             "mase": out["mase"],
                             "lopo_mase": SEL.source_macro(queries, out["mase"]),
                             "intervention_rate": out["intervention_rate"],
                             "conditional_hir": out["conditional_hir"],
                             "harmful_loss": out["harmful_loss"],
                             "beneficial_precision": out["beneficial_precision"]})
    feasible = [r for r in rows if cap is None or r["conditional_hir"] <= cap]
    if not feasible:
        for r in rows:
            r.pop("mase", None)
        return {"selected": None, "keep_only": True, "cap": cap,
                "fallback_to_keep_only": True,
                "rule": "no grid setting respects the harm cap; the selector "
                        "abstains to KEEP-only on every request",
                "leader": None, "feasible_settings": 0,
                "grid": sorted(rows, key=lambda r: r["lopo_mase"])}
    best = min(feasible, key=lambda r: (round(r["lopo_mase"], 6),
                                        r["intervention_rate"], r["k"]))
    for r in feasible:
        gap = SEL.macro_difference(queries, r["mase"], best["mase"])
        r["gap_to_selected"] = gap["difference"]
        r["gap_se"] = gap["standard_error"]
    for r in rows:
        r.pop("mase", None)
    return {"selected": {"k": best["k"], "beta": best["beta"],
                         "lam": best["lam"], "lam_is_inf": best["lam_is_inf"]},
            "keep_only": False, "cap": cap, "fallback_to_keep_only": False,
            "rule": "lowest leave-one-parent-out source-macro MASE among the "
                    "settings whose conditional harmful rate respects the cap",
            "leader": {"k": best["k"], "beta": best["beta"], "lam": best["lam"],
                       "lam_is_inf": best["lam_is_inf"],
                       "lopo_mase": best["lopo_mase"]},
            "feasible_settings": len(feasible),
            "grid": sorted(rows, key=lambda r: r["lopo_mase"])}


def frozen_config(selection: dict):
    """``(k, beta, lam)`` of a selection payload, or ``None`` on KEEP-only."""
    result = selection.get("selection", selection)
    if result.get("keep_only") or result.get("selected") is None:
        return None
    chosen = result["selected"]
    lam = float("inf") if chosen.get("lam_is_inf") else float(chosen["lam"])
    return int(chosen["k"]), float(chosen["beta"]), lam
