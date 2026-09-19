"""v4.6 selector: vectorised same-action retrieval, leave-one-parent-out
selection of (k, beta) under a harmful-intervention cap, and the ablations.

The decision rule is the one of v4.4 and is not changed here.  What changes is
how the neighbourhood is computed (as one distance matrix per action rather
than one Python scan per query, so leave-one-parent-out over the whole bank is
affordable) and how (k, beta) are chosen.

Every function in this module reads the per-action state vector and the
recorded realised utility.  None of them reads a future target, a candidate's
forecast, or a TEST record during selection.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

import numpy as np

from introact_ts.v44 import protocol as P
from introact_ts.v44.matching import STATE_SLICES

ACTIONS = P.ACTIONS
REFERENCE = P.REFERENCE_ACTION
NONREF = tuple(a for a in ACTIONS if a != REFERENCE)

#: Searched grids.  v4.4 searched 3 x 3 on a 48-parent gate; v4.6 searches
#: 4 x 4 by cross-validation on the bank itself.
# Cross-validation picked the largest neighbourhood in the earlier grid on two
# of the three backbones, so the grid runs further out.  The bank holds 1784
# episodes, and 256 neighbours is still a seventh of it.
K_GRID = (8, 16, 32, 64, 128, 256)
BETA_GRID = (0.0, 0.5, 1.0, 1.64)
TAU_EPSILON = 1e-12

#: Feature blocks a variant may drop.  "mask" and "context" describe the
#: request and are never dropped, otherwise the state carries no information
#: about which request is being served.
DROPPABLE = ("intervention", "forecast")


def blocks_of(*, use_intervention: bool = True, use_forecast: bool = True) -> tuple[str, ...]:
    out = ["mask", "context"]
    if use_intervention:
        out.append("intervention")
    if use_forecast:
        out.append("forecast")
    return tuple(out)


def project(vector: np.ndarray, blocks: tuple[str, ...]) -> np.ndarray:
    return np.concatenate([np.asarray(vector)[STATE_SLICES[b]] for b in blocks])


@dataclass
class ActionBank:
    Z: np.ndarray                 # raw state vectors, (n, d)
    g: np.ndarray                 # realised utility against the reference
    parent: np.ndarray            # parent id of each record
    source: np.ndarray
    horizon: np.ndarray
    severity: np.ndarray
    Zs: np.ndarray = field(default=None)


class Bank:
    """Per-action arrays built once from a block's episode catalogs."""

    def __init__(self, catalogs, *, blocks: tuple[str, ...]):
        self.blocks = blocks
        per: dict[str, ActionBank] = {}
        for action in ACTIONS:
            Z, g, par, src, hz, sev = [], [], [], [], [], []
            for c in catalogs:
                e = c.actions.get(action)
                if e is None or not e.scored or e.utility is None or e.state_vector is None:
                    continue
                Z.append(project(e.state_vector, blocks))
                g.append(e.utility)
                par.append(c.parent)
                src.append(c.source)
                hz.append(c.horizon)
                sev.append(c.severity)
            per[action] = ActionBank(np.asarray(Z, dtype=np.float64),
                                     np.asarray(g, dtype=np.float64),
                                     np.asarray(par), np.asarray(src),
                                     np.asarray(hz), np.asarray(sev))
        stacked = np.vstack([per[a].Z for a in ACTIONS if len(per[a].Z)])
        self.mean = stacked.mean(0)
        scale = stacked.std(0)
        self.scale = np.where(scale > 1e-12, scale, 1.0)
        for action in ACTIONS:
            b = per[action]
            b.Zs = (b.Z - self.mean) / self.scale if len(b.Z) else b.Z
        self.per = per

    def standardise(self, vectors: np.ndarray) -> np.ndarray:
        return (np.asarray(vectors, dtype=np.float64) - self.mean) / self.scale

    def support(self) -> dict:
        return {a: int(len(self.per[a].g)) for a in ACTIONS}

    def mean_utility(self) -> dict:
        return {a: (float(self.per[a].g.mean()) if len(self.per[a].g) else float("nan"))
                for a in ACTIONS}


class Queries:
    """The per-action state vectors and realised losses of a block of requests."""

    def __init__(self, catalogs, *, blocks: tuple[str, ...]):
        self.catalogs = catalogs
        self.blocks = blocks
        self.episode = np.asarray([c.episode for c in catalogs])
        self.parent = np.asarray([c.parent for c in catalogs])
        self.source = np.asarray([c.source for c in catalogs])
        self.horizon = np.asarray([c.horizon for c in catalogs])
        self.severity = np.asarray([c.severity for c in catalogs])
        n, d = len(catalogs), len(blocks_slice_length(blocks))
        self.Z = {a: np.full((n, d), np.nan) for a in ACTIONS}
        self.legal = {a: np.zeros(n, bool) for a in ACTIONS}
        self.utility = {a: np.full(n, np.nan) for a in ACTIONS}
        self.metric = {m: {a: np.full(n, np.nan) for a in ACTIONS}
                       for m in ("mase", "rmsse", "mae", "mse")}
        self.pattern = np.asarray([c.pattern for c in catalogs])
        for i, c in enumerate(catalogs):
            usable = set(c.legal())
            for a in ACTIONS:
                e = c.actions.get(a)
                if e is None:
                    continue
                if e.state_vector is not None:
                    self.Z[a][i] = project(e.state_vector, blocks)
                self.legal[a][i] = a in usable and e.state_vector is not None
                if e.utility is not None:
                    self.utility[a][i] = e.utility
                for m in ("mase", "rmsse", "mae", "mse"):
                    value = getattr(e, m, None)
                    if value is not None:
                        self.metric[m][a][i] = value

    @property
    def mase(self):
        return self.metric["mase"]


def blocks_slice_length(blocks: tuple[str, ...]) -> np.ndarray:
    return np.concatenate([np.arange(STATE_SLICES[b].start, STATE_SLICES[b].stop)
                           for b in blocks])


def distance_matrices(bank: Bank, queries: Queries, *, lopo: bool,
                      same_horizon: bool = False) -> dict[str, np.ndarray]:
    """``(n_query, n_bank)`` standardised Euclidean distances, per action.

    With ``lopo`` the distance to every record of the query's own parent is set
    to infinity, which is what makes a cross-validated score on the bank itself
    a statement about a request the bank has not seen.
    """
    out = {}
    for action in ACTIONS:
        b = bank.per[action]
        if len(b.g) == 0:
            out[action] = np.zeros((len(queries.episode), 0))
            continue
        Q = bank.standardise(queries.Z[action])
        finite = np.isfinite(Q).all(1)
        Q = np.where(np.isfinite(Q), Q, 0.0)
        D = np.sqrt(np.maximum(
            (Q ** 2).sum(1)[:, None] + (b.Zs ** 2).sum(1)[None, :] - 2.0 * Q @ b.Zs.T, 0.0))
        D[~finite] = np.inf
        if lopo:
            D[queries.parent[:, None] == b.parent[None, :]] = np.inf
        if same_horizon:
            D[queries.horizon[:, None] != b.horizon[None, :]] = np.inf
        out[action] = D
    return out


def score_grid(bank: Bank, queries: Queries, D: dict[str, np.ndarray], k: int,
               beta: float, *, local: bool = True) -> dict[str, np.ndarray]:
    """The conservative score of every action on every query."""
    n = len(queries.episode)
    scores = {}
    for action in ACTIONS:
        b = bank.per[action]
        if len(b.g) == 0:
            scores[action] = np.full(n, -np.inf)
            continue
        if not local:
            mu = np.full(n, float(b.g.mean()))
            sigma = np.full(n, float(b.g.std()))
            n_eff = np.full(n, float(len(b.g)))
            scores[action] = mu - beta * sigma / np.sqrt(np.maximum(n_eff, 1.0))
            continue
        d = D[action]
        ke = min(k, d.shape[1])
        idx = np.argpartition(d, ke - 1, axis=1)[:, :ke]
        dd = np.take_along_axis(d, idx, axis=1)
        order = np.argsort(dd, axis=1, kind="stable")
        idx = np.take_along_axis(idx, order, axis=1)
        dd = np.take_along_axis(dd, order, axis=1)
        gg = b.g[idx]
        bad = ~np.isfinite(dd)
        dd = np.where(bad, 0.0, dd)
        tau = np.median(dd, axis=1)[:, None] + TAU_EPSILON
        w = np.exp(-dd / tau)
        w = np.where(bad, 0.0, w)
        wsum = w.sum(1)
        degenerate = wsum <= 0
        w[degenerate] = 1.0
        wsum = w.sum(1)
        mu = (w * gg).sum(1) / wsum
        sigma = np.sqrt((w * (gg - mu[:, None]) ** 2).sum(1) / wsum)
        n_eff = np.clip(wsum ** 2 / (w ** 2).sum(1), 1.0, ke)
        s = mu - beta * sigma / np.sqrt(n_eff)
        s[np.all(bad, axis=1)] = -np.inf
        scores[action] = s
    return scores


def decide(queries: Queries, scores: dict[str, np.ndarray], *,
           act_or_keep: bool = True) -> np.ndarray:
    """Return the selected action of every request.

    ``act_or_keep`` False is the A4 ablation: the reference option is removed
    and the highest-scoring admissible action is always executed.
    """
    n = len(queries.episode)
    best = np.full(n, REFERENCE, dtype=object)
    best_score = np.full(n, 0.0 if act_or_keep else -np.inf)
    for action in NONREF:
        s = np.where(queries.legal[action], scores[action], -np.inf)
        take = s > best_score
        best[take] = action
        best_score[take] = s[take]
    return best


# ------------------------------------------------------------------ evaluation

def realised(queries: Queries, selected: np.ndarray, metric: str = "mase") -> np.ndarray:
    """The realised value of one metric under a decision."""
    out = np.full(len(selected), np.nan)
    table = queries.metric[metric]
    for i, a in enumerate(selected):
        out[i] = table[a][i]
    return out


def outcomes(queries: Queries, selected: np.ndarray) -> dict:
    """Realised MASE, intervention rate and the harm diagnostics of a decision."""
    n = len(selected)
    mase = realised(queries, selected, "mase")
    util = np.zeros(n)
    for i, a in enumerate(selected):
        if a != REFERENCE:
            util[i] = queries.utility[a][i]
    acted = selected != REFERENCE
    n_act = int(acted.sum())
    harmful = acted & (util < 0)
    benefit = acted & (util > 0)
    return {
        "mase": mase,
        "selected": selected,
        "intervention_rate": n_act / n,
        "conditional_hir": (float(harmful.sum()) / n_act) if n_act else 0.0,
        "harmful_loss": float((-util[harmful]).sum() / n) if n_act else 0.0,
        "beneficial_precision": (float(benefit.sum()) / n_act) if n_act else float("nan"),
        "n_acted": n_act,
        "n_zero_utility": int((acted & (util == 0)).sum()),
    }


def source_macro(queries: Queries, mase: np.ndarray) -> float:
    """variant -> parent -> source -> equal-weight over sources, per condition cell,
    then an equal-weight mean over the cells, matching the v4.4 headline."""
    cells: dict[tuple, dict[tuple, list[float]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for i in range(len(mase)):
        if not np.isfinite(mase[i]):
            continue
        cell = (int(queries.horizon[i]), float(queries.severity[i]))
        cells[cell][(queries.source[i], queries.parent[i])].append(float(mase[i]))
    values = []
    for cell, parents in cells.items():
        by_source: dict[str, list[float]] = collections.defaultdict(list)
        for (source, _parent), items in parents.items():
            by_source[source].append(float(np.mean(items)))
        values.append(float(np.mean([np.mean(v) for v in by_source.values()])))
    return float(np.mean(values)) if values else float("nan")


def macro_by_cell(queries: Queries, mase: np.ndarray) -> dict:
    """Source-macro MASE of every (horizon, pattern, severity) cell."""
    cells: dict[str, dict[tuple, list[float]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for i in range(len(mase)):
        if not np.isfinite(mase[i]):
            continue
        key = (f"h{int(queries.horizon[i])}|{queries.pattern[i]}"
               f"|s{int(round(queries.severity[i] * 100)):02d}")
        cells[key][(queries.source[i], queries.parent[i])].append(float(mase[i]))
    out = {}
    for key, parents in cells.items():
        by_source: dict[str, list[float]] = collections.defaultdict(list)
        for (source, _parent), items in parents.items():
            by_source[source].append(float(np.mean(items)))
        out[key] = float(np.mean([np.mean(v) for v in by_source.values()]))
    return dict(sorted(out.items()))


def macro_by_source(queries: Queries, mase: np.ndarray) -> dict:
    out: dict[str, list[float]] = collections.defaultdict(list)
    by_parent: dict[tuple, list[float]] = collections.defaultdict(list)
    for i in range(len(mase)):
        if np.isfinite(mase[i]):
            by_parent[(queries.source[i], queries.parent[i])].append(float(mase[i]))
    for (source, _parent), items in by_parent.items():
        out[source].append(float(np.mean(items)))
    return {s: float(np.mean(v)) for s, v in sorted(out.items())}


def paired_cluster_bootstrap(queries: Queries, mase_a: np.ndarray, mase_b: np.ndarray,
                             *, resamples: int = 2000, seed: int = 101) -> dict:
    """Parent-clustered paired bootstrap of the source-macro MASE difference."""
    rng = np.random.default_rng(seed)
    diff = mase_a - mase_b
    by_parent: dict[tuple, list[int]] = collections.defaultdict(list)
    for i in range(len(diff)):
        if np.isfinite(diff[i]):
            by_parent[(queries.source[i], queries.parent[i])].append(i)
    parents_by_source: dict[str, list[tuple]] = collections.defaultdict(list)
    for key in by_parent:
        parents_by_source[key[0]].append(key)

    def macro(sample: list[tuple[tuple, int]]) -> float:
        by_source: dict[str, list[float]] = collections.defaultdict(list)
        for key, _tag in sample:
            by_source[key[0]].append(float(np.mean(diff[by_parent[key]])))
        return float(np.mean([np.mean(v) for v in by_source.values()]))

    point = macro([(k, 0) for k in by_parent])
    draws = np.empty(resamples)
    for r in range(resamples):
        sample = []
        for source, keys in parents_by_source.items():
            pick = rng.integers(0, len(keys), len(keys))
            sample.extend((keys[j], t) for t, j in enumerate(pick))
        draws[r] = macro(sample)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"difference": point, "ci_low": float(lo), "ci_high": float(hi),
            "excludes_zero": bool(lo > 0 or hi < 0),
            "parents": len(by_parent), "resamples": resamples, "seed": seed}


def holm(pairs: dict[str, float]) -> dict[str, float]:
    """Holm step-down on a dict of raw p-values."""
    ordered = sorted(pairs.items(), key=lambda kv: kv[1])
    m = len(ordered)
    out, running = {}, 0.0
    for i, (name, p) in enumerate(ordered):
        adjusted = min(1.0, (m - i) * p)
        running = max(running, adjusted)
        out[name] = running
    return out


# --------------------------------------------------------------- hyperparameters

def harm_cap(bank: Bank, queries: Queries) -> dict:
    """The cap the selected configuration must respect.

    The anchor is the best fixed intervention: the non-reference action with the
    highest mean realised utility on the bank.  Its conditional harmful rate is
    the rate a deployment would already accept by applying that one action to
    every request, so requiring the selector not to exceed it states that
    choosing per request may not be more harmful than the best fixed choice.
    """
    means = {a: float(np.nanmean(queries.utility[a])) for a in NONREF
             if np.isfinite(queries.utility[a]).any()}
    anchor = max(means, key=means.get)
    u = queries.utility[anchor]
    usable = np.isfinite(u) & queries.legal[anchor]
    cap = float((u[usable] < 0).mean())
    return {"anchor": anchor, "cap": cap, "anchor_mean_utility": means[anchor],
            "anchor_applicable": int(usable.sum()), "action_mean_utility": means}


def macro_difference(queries: Queries, mase_a: np.ndarray,
                     mase_b: np.ndarray) -> dict:
    """Source-macro of a paired difference and its parent-clustered standard error.

    The parent is the resampling unit everywhere else in this paper, so it is
    the unit here too.  Sources are equally weighted, which makes the variance
    of the macro the equally weighted sum of the within-source variances of the
    parent means.
    """
    diff = mase_a - mase_b
    by_parent: dict[tuple, list[float]] = collections.defaultdict(list)
    for i in range(len(diff)):
        if np.isfinite(diff[i]):
            by_parent[(queries.source[i], queries.parent[i])].append(float(diff[i]))
    by_source: dict[str, list[float]] = collections.defaultdict(list)
    for (source, _parent), items in by_parent.items():
        by_source[source].append(float(np.mean(items)))
    if not by_source:
        return {"difference": float("nan"), "standard_error": float("nan")}
    means = [float(np.mean(v)) for v in by_source.values()]
    n_source = len(by_source)
    variance = 0.0
    for values in by_source.values():
        n = len(values)
        if n > 1:
            variance += float(np.var(values, ddof=1)) / n
    return {"difference": float(np.mean(means)),
            "standard_error": float(np.sqrt(variance)) / n_source,
            "sources": n_source, "parents": len(by_parent)}


def select_hyperparameters(bank: Bank, queries: Queries, *, k_grid=K_GRID,
                           beta_grid=BETA_GRID, cap: float | None = None,
                           same_horizon: bool = False) -> dict:
    """Leave-one-parent-out choice of (k, beta) under the harm cap."""
    D = distance_matrices(bank, queries, lopo=True, same_horizon=same_horizon)
    rows = []
    for k in k_grid:
        for beta in beta_grid:
            scores = score_grid(bank, queries, D, k, beta)
            selected = decide(queries, scores)
            out = outcomes(queries, selected)
            rows.append({"k": int(k), "beta": float(beta),
                         "mase": out["mase"],
                         "lopo_mase": source_macro(queries, out["mase"]),
                         "intervention_rate": out["intervention_rate"],
                         "conditional_hir": out["conditional_hir"],
                         "harmful_loss": out["harmful_loss"],
                         "beneficial_precision": out["beneficial_precision"]})
    feasible = [r for r in rows if cap is None or r["conditional_hir"] <= cap]
    fallback = not feasible
    if fallback:
        feasible = [r for r in rows if r["beta"] == max(beta_grid)]
    leader = min(feasible, key=lambda r: (r["lopo_mase"], r["k"]))
    # A paired comparison against the leader, clustered on the parent, says
    # which of the remaining settings the bank cannot separate from it.
    for r in feasible:
        gap = macro_difference(queries, r["mase"], leader["mase"])
        r["gap_to_leader"] = gap["difference"]
        r["gap_se"] = gap["standard_error"]
        r["tied_with_leader"] = bool(gap["difference"] <= gap["standard_error"])
    tied = [r for r in feasible if r["tied_with_leader"]]
    # Among settings the bank cannot separate, the one that intervenes least
    # carries the least exposure to harm.
    best = min(tied, key=lambda r: (r["intervention_rate"], -r["beta"], r["k"]))
    for r in rows:
        r.pop("mase", None)
    return {"selected": {"k": best["k"], "beta": best["beta"]},
            "cap": cap, "fallback_to_most_conservative": fallback,
            "rule": "one clustered standard error of the leave-one-parent-out "
                    "leader, then the least intervening setting",
            "leader": {"k": leader["k"], "beta": leader["beta"],
                       "lopo_mase": leader["lopo_mase"]},
            "tied_settings": len(tied), "feasible_settings": len(feasible),
            "grid": sorted(rows, key=lambda r: r["lopo_mase"])}


# -------------------------------------------------------------------- baselines

def best_fixed_action(bank: Bank) -> str:
    means = bank.mean_utility()
    return max(ACTIONS, key=lambda a: (means[a] if np.isfinite(means[a]) else -np.inf))


def apply_fixed(queries: Queries, action: str) -> np.ndarray:
    sel = np.full(len(queries.episode), REFERENCE, dtype=object)
    if action != REFERENCE:
        sel[queries.legal[action]] = action
    return sel


def oracle(queries: Queries) -> np.ndarray:
    n = len(queries.episode)
    sel = np.full(n, REFERENCE, dtype=object)
    best = np.full(n, np.inf)
    for a in ACTIONS:
        m = np.where(queries.legal[a] & np.isfinite(queries.mase[a]),
                     queries.mase[a], np.inf)
        take = m < best
        sel[take] = a
        best[take] = m[take]
    return sel


def r2_cart(bank: Bank, queries: Queries, *, max_depth: int = 3,
            min_samples_leaf: int = 96, seed: int = 101) -> np.ndarray:
    """The inherited simple control: one shallow tree per action, asking whether
    that action beats the reference on this state."""
    from sklearn.tree import DecisionTreeClassifier

    models = {}
    for a in NONREF:
        b = bank.per[a]
        if len(b.g) < 8:
            continue
        label = (b.g > 0).astype(int)
        if len(np.unique(label)) < 2:
            continue
        models[a] = DecisionTreeClassifier(max_depth=max_depth,
                                           min_samples_leaf=min_samples_leaf,
                                           random_state=seed).fit(b.Z, label)
    n = len(queries.episode)
    sel = np.full(n, REFERENCE, dtype=object)
    best_p = np.full(n, 0.5)
    for a, model in models.items():
        Z = queries.Z[a]
        ok = np.isfinite(Z).all(1) & queries.legal[a]
        if not ok.any():
            continue
        p = np.zeros(n)
        p[ok] = model.predict_proba(Z[ok])[:, 1]
        take = ok & (p > best_p)
        sel[take] = a
        best_p[take] = p[take]
    return sel


def parametric(bank: Bank, queries: Queries, *, kind: str = "ridge",
               beta: float = 0.0) -> np.ndarray:
    """A5: replace retrieval by a per-action parametric utility predictor."""
    from sklearn.linear_model import Ridge
    from sklearn.tree import DecisionTreeRegressor

    n = len(queries.episode)
    sel = np.full(n, REFERENCE, dtype=object)
    best = np.zeros(n)
    for a in NONREF:
        b = bank.per[a]
        if len(b.g) < 8:
            continue
        model = (Ridge(alpha=1.0) if kind == "ridge"
                 else DecisionTreeRegressor(max_depth=3, min_samples_leaf=96,
                                            random_state=101))
        model.fit(b.Zs, b.g)
        residual = float(np.std(b.g - model.predict(b.Zs)))
        Z = queries.Z[a]
        ok = np.isfinite(Z).all(1) & queries.legal[a]
        if not ok.any():
            continue
        s = np.full(n, -np.inf)
        s[ok] = model.predict(bank.standardise(Z[ok])) - beta * residual / np.sqrt(len(b.g))
        take = s > best
        sel[take] = a
        best[take] = s[take]
    return sel
