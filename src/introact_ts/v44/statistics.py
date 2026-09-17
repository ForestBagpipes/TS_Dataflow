"""Statistics for the v4.4 result tables (task book §14).

The primary unit is the **parent**, never the variant: variants of one parent
share a future and are therefore one observation.  Comparisons are paired (the
same parents on both sides) and clustered (resampling happens at the parent
level, inside each source), then macro-averaged with the eight sources weighted
equally.  That is the same ladder the tables use, so a confidence interval and
a table cell are always computed from the same quantity.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from .protocol import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, CI_LEVEL, SOURCES


def parent_means(records: list[dict], *, method: str, value_key: str = "mase",
                 backbone: str | None = None, horizon: int | None = None,
                 pattern: str | None = None,
                 severity: float | None = None) -> dict[tuple[str, str], float]:
    """``(source, parent) -> mean value`` after variant aggregation."""
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for record in records:
        if record.get("method") != method:
            continue
        if backbone is not None and record.get("backbone") != backbone:
            continue
        if horizon is not None and record.get("horizon") != horizon:
            continue
        if pattern is not None and record.get("pattern") != pattern:
            continue
        if severity is not None and abs(float(record.get("severity", -1))
                                        - float(severity)) > 1e-12:
            continue
        value = record.get(value_key)
        if value is None:
            continue
        buckets[(record["source"], record["parent"])].append(float(value))
    return {key: float(np.mean(values)) for key, values in buckets.items()}


def _source_index(values: dict[tuple[str, str], float]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for (source, parent), value in values.items():
        out[source][parent] = value
    return out


def source_macro(values: dict[tuple[str, str], float], *,
                 sources=SOURCES) -> float:
    """Equal-weight macro average of per-source parent means."""
    index = _source_index(values)
    means = [float(np.mean(list(index[s].values()))) for s in sources if index.get(s)]
    if not means:
        return float("nan")
    return float(np.mean(means))


def paired_cluster_bootstrap(left: dict[tuple[str, str], float],
                             right: dict[tuple[str, str], float], *,
                             resamples: int = BOOTSTRAP_RESAMPLES,
                             seed: int = BOOTSTRAP_SEED,
                             level: float = CI_LEVEL,
                             sources=SOURCES) -> dict:
    """Paired cluster bootstrap of the source-macro difference ``left - right``.

    Parents present in only one side are dropped from the paired comparison and
    counted, never silently averaged in.
    """
    left_index, right_index = _source_index(left), _source_index(right)
    shared: dict[str, list[str]] = {}
    dropped = 0
    for source in sources:
        a, b = left_index.get(source, {}), right_index.get(source, {})
        common = sorted(set(a) & set(b))
        dropped += len(set(a) ^ set(b))
        if common:
            shared[source] = common
    if not shared:
        return {"status": "no_common_parents", "resamples": 0}

    observed_terms = []
    for source, parents in shared.items():
        diffs = [left_index[source][p] - right_index[source][p] for p in parents]
        observed_terms.append(float(np.mean(diffs)))
    observed = float(np.mean(observed_terms))

    rng = np.random.default_rng(seed)
    draws = np.empty(resamples, dtype=np.float64)
    source_list = list(shared)
    for i in range(resamples):
        terms = []
        for source in source_list:
            parents = shared[source]
            picks = rng.integers(0, len(parents), size=len(parents))
            diffs = np.array([left_index[source][parents[j]] - right_index[source][parents[j]]
                              for j in picks], dtype=np.float64)
            terms.append(float(diffs.mean()))
        draws[i] = float(np.mean(terms))

    alpha = (1.0 - level) / 2.0
    lo, hi = np.percentile(draws, [100 * alpha, 100 * (1 - alpha)])
    return {
        "status": "computed",
        "difference": observed,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "level": level,
        "resamples": int(resamples),
        "seed": int(seed),
        "sources": len(source_list),
        "parents": int(sum(len(v) for v in shared.values())),
        "unpaired_dropped": int(dropped),
    }


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni step-down adjustment over a family of comparisons."""
    items = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(items)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, p) in enumerate(items):
        value = min(1.0, (m - rank) * float(p))
        running = max(running, value)
        adjusted[name] = running
    return adjusted


def average_rank(records: list[dict], *, methods: list[str],
                 value_key: str = "mase", backbone: str | None = None,
                 horizon: int | None = None, pattern: str | None = None,
                 severity: float | None = None) -> dict[str, float]:
    """Mean rank of each method, ranked inside every fully-specified cell.

    A "cell" is one ``(source, parent, horizon, pattern, severity)`` -- a single
    comparison in which every method is scored on the same window.  Ranking
    inside the cell and averaging the ranks per method is what stops a source
    with many parents from dominating by sheer count, and what stops a record
    from one condition silently overwriting a record from another.
    """
    per_cell: dict[tuple, dict[str, float]] = defaultdict(dict)
    for record in records:
        if backbone is not None and record.get("backbone") != backbone:
            continue
        if horizon is not None and record.get("horizon") != horizon:
            continue
        if pattern is not None and record.get("pattern") != pattern:
            continue
        if severity is not None and abs(float(record.get("severity", -1))
                                        - float(severity)) > 1e-12:
            continue
        if record.get("method") not in methods:
            continue
        value = record.get(value_key)
        if value is None:
            continue
        key = (record["source"], record["parent"], record["horizon"],
               record["pattern"], float(record["severity"]))
        per_cell[key][record["method"]] = float(value)

    totals: dict[str, list[float]] = {method: [] for method in methods}
    for values in per_cell.values():
        present = [m for m in methods if m in values]
        if len(present) < 2:
            continue
        ordered = sorted(present, key=lambda m: values[m])
        for position, method in enumerate(ordered, start=1):
            totals[method].append(float(position))
    return {method: (float(np.mean(v)) if v else float("nan"))
            for method, v in totals.items()}


def cell_win_counts(records: list[dict], *, method: str, baseline: str,
                    value_key: str = "mase") -> dict:
    """Win/tie/loss counts over ``source x backbone x horizon x pattern x severity``.

    The severity is part of the cell key so the 30% and 50% robustness
    conditions can never be folded into -- or overwrite -- the 10% main one.
    """
    cells: dict[tuple, dict[str, float]] = defaultdict(dict)
    for record in records:
        if record.get("method") not in (method, baseline):
            continue
        value = record.get(value_key)
        if value is None:
            continue
        key = (record["source"], record["backbone"], record["horizon"],
               record["pattern"], float(record["severity"]))
        cells[key][record["method"]] = float(value)
    wins = ties = losses = 0
    for values in cells.values():
        if method not in values or baseline not in values:
            continue
        if values[method] < values[baseline]:
            wins += 1
        elif values[method] > values[baseline]:
            losses += 1
        else:
            ties += 1
    return {"cells": wins + ties + losses, "wins": wins, "ties": ties,
            "losses": losses}
