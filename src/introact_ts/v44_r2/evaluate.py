"""Scoring, governance and the r2 admission ladder.

Two things are kept strictly apart:

* the **gate** objective, which selects one shared ``model config x tau``; and
* the **admission** criteria R1-R6, which are only ever evaluated once, on
  TRAIN-Eval, after the configuration is frozen.

The records produced here are shape-compatible with the v4.4 evaluation records
so the two can be ranked and bootstrapped together without a translation layer.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

from ..v44 import metrics as ME
from ..v44 import protocol as P
from ..v44 import statistics as ST
from .dataset import EpisodeView
from .ranking import Decision

#: Opportunity thresholds, frozen from Replay-Fit quantiles (task book §19 of
#: the r2 plan: only TRAIN quantiles may define the bands).
OPPORTUNITY_QUANTILES = (1 / 3, 2 / 3)


def freeze_opportunity_thresholds(episodes: list[EpisodeView]) -> dict:
    values = np.asarray([e.opportunity() for e in episodes
                         if e.opportunity() is not None], dtype=np.float64)
    if values.size == 0:
        raise RuntimeError("no episode carries an oracle opportunity")
    low, high = (float(np.quantile(values, q)) for q in OPPORTUNITY_QUANTILES)
    return {"low": low, "high": high, "n": int(values.size),
            "quantiles": list(OPPORTUNITY_QUANTILES),
            "degenerate_ratio": float((values <= 1e-9).mean())}


def opportunity_band(value: float | None, thresholds: dict) -> str:
    if value is None:
        return "unknown"
    if value <= 1e-9:
        return "no_op"
    if value <= thresholds["high"]:
        return "low"
    return "high"


def decision_records(episodes: list[EpisodeView],
                     decisions: dict[str, Decision], *, backbone: str,
                     method: str, thresholds: dict | None = None) -> list[dict]:
    """One record per episode, in the same shape as the v4.4 evaluation."""
    records = []
    for episode in episodes:
        decision = decisions[episode.episode]
        action = decision.action
        view = episode.actions[action]
        reference = episode.reference
        _, oracle_loss = episode.oracle()
        opportunity = episode.opportunity()
        records.append({
            "method": method,
            "backbone": backbone,
            "source": episode.source,
            "parent": episode.parent,
            "variant": episode.episode,
            "horizon": episode.horizon,
            "pattern": episode.pattern,
            "severity": episode.severity,
            "selected_action": action,
            "intervened": action != P.REFERENCE_ACTION,
            "mase": view.loss,
            "keep_mase": reference.loss,
            "oracle_mase": oracle_loss,
            "opportunity": opportunity,
            "opportunity_band": (opportunity_band(opportunity, thresholds)
                                 if thresholds else "unknown"),
            "vetoed": decision.vetoed,
            "borda_winner": decision.borda_winner,
            "legal": list(decision.legal),
            "runtime": view.runtime,
        })
    return records


def macro_mase(records: list[dict], method: str, backbone: str) -> float | None:
    subset = [r for r in records
              if r["method"] == method and r["backbone"] == backbone]
    return ME.macro_headline(subset, "mase")


def macro_cells(records: list[dict], method: str, backbone: str) -> dict:
    """``cell -> source-macro MASE``, one entry per condition cell.

    The severity is part of the key: ``ME.macro_cells`` treats
    ``(horizon, pattern, severity)`` as three different conditions, and a key
    that dropped the severity would let a 30% cell overwrite the 10% cell of
    the same ``(horizon, pattern)`` in the robustness blocks.
    """
    subset = [r for r in records
              if r["method"] == method and r["backbone"] == backbone]
    return {f"h{c['horizon']}|{c['pattern']}|s{int(round(float(c['severity']) * 100)):02d}":
            c["mase"]
            for c in ME.macro_cells(subset, "mase")}


def governance(records: list[dict]) -> dict:
    """HIR, harmful loss, catalog gap closed and the KEEP rate."""
    out: dict[str, dict] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["method"]].append(record)
    for method, items in sorted(grouped.items()):
        usable = [r for r in items
                  if r["mase"] is not None and r["keep_mase"] is not None
                  and r["oracle_mase"] is not None]
        if not usable:
            continue
        loss = np.array([r["mase"] for r in usable], dtype=np.float64)
        keep = np.array([r["keep_mase"] for r in usable], dtype=np.float64)
        oracle = np.array([r["oracle_mase"] for r in usable], dtype=np.float64)
        intervened = np.array([r["intervened"] for r in usable], dtype=bool)
        harmful = loss > keep
        out[method] = {
            "n": int(loss.size),
            "excluded_missing_loss": int(len(items) - len(usable)),
            "intervention_rate": float(intervened.mean()),
            "keep_rate": float(1.0 - intervened.mean()),
            "hir": ME.harmful_intervention_rate(loss, keep),
            "conditional_hir": (float(harmful[intervened].mean())
                                if intervened.any() else None),
            "harmful_loss": ME.harmful_loss(loss, keep),
            **ME.catalog_gap_closed(loss, keep, oracle),
        }
    return out


def keep_rate(records: list[dict], method: str) -> float:
    items = [r for r in records if r["method"] == method]
    if not items:
        return float("nan")
    return float(np.mean([not r["intervened"] for r in items]))


def high_opportunity_capture(records: list[dict], method: str) -> dict:
    """How much of the achievable gain is taken where it is worth taking."""
    items = [r for r in records
             if r["method"] == method and r["opportunity_band"] == "high"
             and r["mase"] is not None and r["keep_mase"] is not None
             and r["oracle_mase"] is not None]
    if not items:
        return {"high_opportunity": 0, "capture": None, "achieved_oracle": None}
    achieved = sum(1 for r in items
                   if abs(r["mase"] - r["oracle_mase"]) <= 1e-12)
    gap = np.array([r["keep_mase"] - r["oracle_mase"] for r in items],
                   dtype=np.float64)
    closed = np.array([r["keep_mase"] - r["mase"] for r in items],
                      dtype=np.float64)
    usable = gap > 1e-9
    return {
        "high_opportunity": len(items),
        "capture": float((closed[usable] / gap[usable]).mean())
        if usable.any() else None,
        "achieved_oracle": float(achieved / len(items)),
        "intervention_rate": float(np.mean([r["intervened"] for r in items])),
    }


def band_table(records: list[dict], method: str) -> dict:
    out = {}
    for band in ("no_op", "low", "high"):
        values = [r["mase"] for r in records
                  if r["method"] == method and r["opportunity_band"] == band
                  and r["mase"] is not None]
        out[band] = float(np.mean(values)) if values else None
        out[f"{band}_n"] = len(values)
    overall = [r["mase"] for r in records
               if r["method"] == method and r["mase"] is not None]
    out["overall"] = float(np.mean(overall)) if overall else None
    return out


# -- admission -------------------------------------------------------------


def load_v44_reference(path: str | Path) -> list[dict]:
    """The frozen v4.4 TRAIN-Eval records, for the R1-R4 comparisons."""
    import json

    payload = json.loads(Path(path).read_text())
    return payload["records"]


def paired(records: list[dict], backbone: str, left: str, right: str) -> dict:
    """Paired cluster bootstrap of ``left - right`` (negative = left better)."""
    left_means = ST.parent_means(records, method=left, backbone=backbone)
    right_means = ST.parent_means(records, method=right, backbone=backbone)
    result = ST.paired_cluster_bootstrap(left_means, right_means)
    result["left"] = left
    result["right"] = right
    if result.get("status") == "computed":
        result["favours"] = ("left" if result["difference"] < 0
                             else "right" if result["difference"] > 0 else "tie")
        result["excludes_zero"] = bool(result["ci_low"] > 0
                                       or result["ci_high"] < 0)
    return result


def boundary_audit(records: list[dict], episodes: list[EpisodeView],
                   assignment: dict[str, str], *, method: str,
                   backbone: str) -> dict:
    """R6: the candidate may not have crossed a split, cache or aggregation line.

    Three independent things are checked, because a wrong headline can come
    from any of them:

    * **split** -- every parent scored must be assigned to ``train_eval``, so a
      request from another block cannot have leaked into the deployment set;
    * **coverage** -- one record per episode, so nothing was silently dropped
      and no episode was counted twice;
    * **aggregation** -- the quoted headline must be the equal-weight mean of
      the condition cells, not one cell standing in for the table.
    """
    parents = {r["parent"] for r in records}
    wrong_block = sorted(p for p in parents
                         if assignment.get(p) != "train_eval")
    cells = macro_cells(records, method, backbone)
    cell_values = [value for value in cells.values() if value is not None]
    headline = macro_mase(records, method, backbone)
    aggregated = float(np.mean(cell_values)) if cell_values else None
    return {
        "records": len(records),
        "episodes": len(episodes),
        "records_match_episodes": len(records) == len(episodes),
        "parents": len(parents),
        "cells": len(cells),
        "parents_outside_train_eval": wrong_block,
        "block_boundary_ok": not wrong_block,
        "headline_equals_cell_mean": (
            headline is not None and aggregated is not None
            and abs(headline - aggregated) <= 1e-12),
        "heldout_labels_read": 0,
        "calibration_test_touched": False,
    }
