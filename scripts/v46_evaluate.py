#!/usr/bin/env python3
"""v4.6 evaluation: every table the paper reports, from one prediction cache.

The configuration must already be frozen: this script refuses to run unless the
selection file written by ``v46_select.py`` exists for the backbone, and it
reads (k, beta) from that file rather than searching anything.

One run produces, for one backbone and one block:

* the main comparison row of every method, in MASE and RMSSE;
* the governance diagnostics (intervention rate, conditional harmful rate,
  harmful loss, beneficial precision, missed opportunity);
* the ablation ladder A1-A5 with the always-act variant as A4;
* the action-heterogeneity statistics behind Figure 1(a);
* per-source, per-pattern and per-horizon breakdowns;
* paired cluster bootstrap differences against every deployable control.
"""

from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v46 import select as SEL

ROOT = Path(__file__).resolve().parent.parent
C.REPLAY = "results/v46/replay"
OUT = ROOT / "results/v46"

#: Rows that carry a claim, in table order.  The oracle is a diagnostic and is
#: excluded from every rank.
DEPLOYABLE = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FULL_INTROACT")

#: Published baselines, by the directory their records live in.  A method that
#: returns a repaired input or a transformed context intervenes on every
#: incomplete request by construction.
BASELINES = {"saits": "SAITS", "tato": "TATO"}
ABLATIONS = ("A1_GLOBAL_UTILITY", "A2_WO_INTERVENTION", "A3_WO_FORECAST",
             "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE")


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def heterogeneity(queries: SEL.Queries) -> dict:
    """The two premises of Section 4.2, computed on the evaluation episodes."""
    oracle_sel = SEL.oracle(queries)
    n = len(oracle_sel)
    share = collections.Counter(oracle_sel)
    per_action = {}
    for a in SEL.NONREF:
        u = queries.utility[a]
        ok = np.isfinite(u) & queries.legal[a]
        per_action[a] = {
            "applicable": int(ok.sum()),
            "p_positive": float((u[ok] > 0).mean()) if ok.any() else None,
            "p_negative": float((u[ok] < 0).mean()) if ok.any() else None,
            "p_zero": float((u[ok] == 0).mean()) if ok.any() else None,
            "mean_utility": float(u[ok].mean()) if ok.any() else None,
        }
    keep_mase = SEL.realised(queries, np.full(n, SEL.REFERENCE, dtype=object))
    oracle_mase = SEL.realised(queries, oracle_sel)
    opportunity = keep_mase - oracle_mase
    return {
        "oracle_best_share": {a: share.get(a, 0) / n for a in SEL.ACTIONS},
        "oracle_best_count": {a: int(share.get(a, 0)) for a in SEL.ACTIONS},
        "per_action_utility": per_action,
        "opportunity": {
            "mean": float(np.nanmean(opportunity)),
            "median": float(np.nanmedian(opportunity)),
            "p90": float(np.nanpercentile(opportunity, 90)),
            "share_zero": float(np.mean(opportunity <= 1e-9)),
        },
        "episodes": n,
    }


def per_source_horizon(queries: SEL.Queries, mase: np.ndarray) -> dict:
    """Source-macro MASE split by horizon, for the per-source appendix tables."""
    by_parent: dict[tuple, list[float]] = collections.defaultdict(list)
    for i in range(len(mase)):
        if np.isfinite(mase[i]):
            key = (int(queries.horizon[i]), queries.source[i], queries.parent[i])
            by_parent[key].append(float(mase[i]))
    by_source: dict[str, list[float]] = collections.defaultdict(list)
    for (horizon, source, _parent), values in by_parent.items():
        by_source[f"h{horizon}|{source}"].append(float(np.mean(values)))
    return {k: float(np.mean(v)) for k, v in sorted(by_source.items())}


def load_baseline(root: Path, method: str, block: str, backbone: str,
                  queries: SEL.Queries) -> dict | None:
    """A baseline's realised MASE and RMSSE, aligned to the evaluation episodes."""
    path = root / f"results/v46/baselines/{method}_{block}_{backbone}/records.json"
    if not path.exists():
        return None
    records = json.loads(path.read_text())["records"]
    n = len(queries.episode)
    mase = np.full(n, np.nan)
    rmsse = np.full(n, np.nan)
    for i, episode in enumerate(queries.episode):
        item = records.get(episode)
        if item is None:
            continue
        if item.get("mase") is not None:
            mase[i] = item["mase"]
        if item.get("rmsse") is not None:
            rmsse[i] = item["rmsse"]
    if not np.isfinite(mase).any():
        return None
    return {"mase": mase, "rmsse": rmsse, "scored": int(np.isfinite(mase).sum())}


def summarise_vectors(queries: SEL.Queries, mase: np.ndarray, rmsse: np.ndarray,
                      name: str, *, keep_mase: np.ndarray) -> dict:
    """The same row a catalog method gets, for a method that returns a forecast.

    A baseline modifies the input of every incomplete request, so its
    intervention rate is one and its harmful rate is unconditional: it counts
    the requests where its forecast is worse than the reference forecast of the
    same backbone.
    """
    usable = np.isfinite(mase) & np.isfinite(keep_mase)
    harmful = usable & (mase > keep_mase)
    benefit = usable & (mase < keep_mase)
    n = int(usable.sum())
    return {
        "method": name,
        "mase": SEL.source_macro(queries, mase),
        "rmsse": SEL.source_macro(queries, rmsse),
        "intervention_rate": 1.0,
        "conditional_hir": (float(harmful.sum()) / n) if n else 0.0,
        "harmful_loss": (float((mase[harmful] - keep_mase[harmful]).sum()) / n) if n else 0.0,
        "beneficial_precision": (float(benefit.sum()) / n) if n else float("nan"),
        "n_acted": n,
        "n_zero_utility": int(usable.sum() - harmful.sum() - benefit.sum()),
        "per_source_mase": SEL.macro_by_source(queries, mase),
        "per_source_horizon_mase": per_source_horizon(queries, mase),
        "per_cell_mase": SEL.macro_by_cell(queries, mase),
        "action_counts": {},
    }


def summarise(queries: SEL.Queries, selected: np.ndarray, name: str) -> dict:
    out = SEL.outcomes(queries, selected)
    row = {
        "method": name,
        "mase": SEL.source_macro(queries, out["mase"]),
        "rmsse": SEL.source_macro(queries, SEL.realised(queries, selected, "rmsse")),
        "intervention_rate": out["intervention_rate"],
        "conditional_hir": out["conditional_hir"],
        "harmful_loss": out["harmful_loss"],
        "beneficial_precision": out["beneficial_precision"],
        "n_acted": out["n_acted"],
        "n_zero_utility": out["n_zero_utility"],
        "per_source_mase": SEL.macro_by_source(queries, out["mase"]),
        "per_source_horizon_mase": per_source_horizon(queries, out["mase"]),
        "per_cell_mase": SEL.macro_by_cell(queries, out["mase"]),
        "action_counts": {a: int((selected == a).sum()) for a in SEL.ACTIONS},
    }
    return row


def opportunity_strata(bank_queries: SEL.Queries, queries: SEL.Queries,
                       rows: dict, mase_of: dict,
                       quantiles=(0.50, 0.85)) -> dict:
    """Stratum sizes and per-stratum MASE, under boundaries fixed on the bank."""
    def opportunity(q: SEL.Queries) -> np.ndarray:
        keep = SEL.realised(q, np.full(len(q.episode), SEL.REFERENCE, dtype=object))
        best = SEL.realised(q, SEL.oracle(q))
        return keep - best

    bank_gap = opportunity(bank_queries)
    usable = bank_gap[np.isfinite(bank_gap)]
    positive = usable[usable > 1e-9]
    if positive.size < 10:
        return {}
    low, high = (float(np.quantile(positive, quantiles[0])),
                 float(np.quantile(positive, quantiles[1])))

    gap = opportunity(queries)
    strata = np.full(len(gap), "no-op", dtype=object)
    strata[np.isfinite(gap) & (gap > 1e-9) & (gap <= low)] = "low"
    strata[np.isfinite(gap) & (gap > low)] = "high"
    strata[np.isfinite(gap) & (gap > high)] = "high"

    out = {"boundaries": {"no_op": 1e-9, "low_to_high": low, "upper_reference": high,
                          "quantiles": list(quantiles), "fitted_on": "replay bank"},
           "sizes": {}, "per_method": {}}
    for name in ("no-op", "low", "high"):
        mask = strata == name
        values = gap[mask & np.isfinite(gap)]
        out["sizes"][name] = {
            "episodes": int(mask.sum()),
            "share": float(mask.mean()),
            "parents": int(len({queries.parent[i] for i in np.flatnonzero(mask)})),
            "median": float(np.median(values)) if values.size else None,
            "p90": float(np.percentile(values, 90)) if values.size else None,
        }
    for method, vector in mase_of.items():
        row = {}
        for name in ("no-op", "low", "high"):
            mask = (strata == name) & np.isfinite(vector)
            if not mask.any():
                row[name] = None
                continue
            sub = SEL.Queries.__new__(SEL.Queries)
            sub.episode = queries.episode[mask]
            sub.parent = queries.parent[mask]
            sub.source = queries.source[mask]
            sub.horizon = queries.horizon[mask]
            sub.severity = queries.severity[mask]
            sub.pattern = queries.pattern[mask]
            row[name] = SEL.source_macro(sub, vector[mask])
        row["overall"] = SEL.source_macro(queries, vector)
        out["per_method"][method] = row
    return out


def missed_opportunity(queries: SEL.Queries, selected: np.ndarray,
                       threshold: float) -> float:
    """Share of episodes with a positive oracle opportunity where nothing ran."""
    keep_mase = SEL.realised(queries, np.full(len(selected), SEL.REFERENCE, dtype=object))
    oracle_mase = SEL.realised(queries, SEL.oracle(queries))
    opportunity = keep_mase - oracle_mase
    has = np.isfinite(opportunity) & (opportunity > threshold)
    if not has.any():
        return float("nan")
    return float((selected[has] == SEL.REFERENCE).mean())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--block", default="test", choices=["train_eval", "test", "test30", "test50"])
    parser.add_argument("--resamples", type=int, default=2000)
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    freeze = root / f"results/v46/protocol/selection_{args.backbone}.json"
    if not freeze.exists():
        raise SystemExit(f"configuration is not frozen for {args.backbone}: {freeze} missing")
    selection = json.loads(freeze.read_text())
    k = int(selection["selection"]["selected"]["k"])
    beta = float(selection["selection"]["selected"]["beta"])

    bank_catalogs = C.load_catalog(root, "bank", args.backbone)
    eval_catalogs = C.load_catalog(root, args.block, args.backbone)

    full_blocks = SEL.blocks_of()
    bank = SEL.Bank(bank_catalogs, blocks=full_blocks)
    queries = SEL.Queries(eval_catalogs, blocks=full_blocks)
    D = SEL.distance_matrices(bank, queries, lopo=False)

    decisions: dict[str, np.ndarray] = {}
    n = len(eval_catalogs)
    decisions["NATIVE_KEEP"] = np.full(n, SEL.REFERENCE, dtype=object)
    fixed = SEL.best_fixed_action(bank)
    decisions["BEST_FIXED"] = SEL.apply_fixed(queries, fixed)
    decisions["R2_CART"] = SEL.r2_cart(bank, queries)
    scores = SEL.score_grid(bank, queries, D, k, beta)
    decisions["FULL_INTROACT"] = SEL.decide(queries, scores)
    decisions["A1_GLOBAL_UTILITY"] = SEL.decide(
        queries, SEL.score_grid(bank, queries, D, k, beta, local=False))
    decisions["A4_ALWAYS_ACT"] = SEL.decide(queries, scores, act_or_keep=False)
    decisions["A5_PARAMETRIC_RIDGE"] = SEL.parametric(bank, queries, kind="ridge")
    decisions["CATALOG_ORACLE"] = SEL.oracle(queries)

    for label, kwargs in (("A2_WO_INTERVENTION", {"use_intervention": False}),
                          ("A3_WO_FORECAST", {"use_forecast": False})):
        blocks = SEL.blocks_of(**kwargs)
        b2 = SEL.Bank(bank_catalogs, blocks=blocks)
        q2 = SEL.Queries(eval_catalogs, blocks=blocks)
        D2 = SEL.distance_matrices(b2, q2, lopo=False)
        decisions[label] = SEL.decide(q2, SEL.score_grid(b2, q2, D2, k, beta))

    rows = {name: summarise(queries, sel, name) for name, sel in decisions.items()}
    threshold = 1e-9
    for name, sel in decisions.items():
        rows[name]["missed_opportunity"] = missed_opportunity(queries, sel, threshold)

    mase_of = {name: SEL.realised(queries, sel) for name, sel in decisions.items()}

    # Published baselines enter as realised forecasts rather than as a choice
    # over the catalog, and are ranked and tested exactly like the other rows.
    keep_mase = mase_of["NATIVE_KEEP"]
    external = {}
    for method, label in BASELINES.items():
        loaded = load_baseline(root, method, args.block, args.backbone, queries)
        if loaded is None:
            continue
        rows[label] = summarise_vectors(queries, loaded["mase"], loaded["rmsse"],
                                        label, keep_mase=keep_mase)
        rows[label]["missed_opportunity"] = 0.0
        rows[label]["scored_episodes"] = loaded["scored"]
        mase_of[label] = loaded["mase"]
        external[label] = loaded["scored"]
    comparisons = {}
    for reference in (("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "A1_GLOBAL_UTILITY",
                       "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE", "A2_WO_INTERVENTION",
                       "A3_WO_FORECAST") + tuple(external)):
        comparisons[f"FULL_INTROACT_vs_{reference}"] = SEL.paired_cluster_bootstrap(
            queries, mase_of["FULL_INTROACT"], mase_of[reference],
            resamples=args.resamples)

    ranked = [name for name in list(DEPLOYABLE) + list(external) + list(ABLATIONS)]
    cell_rank = collections.defaultdict(list)
    for i in range(n):
        values = [(name, mase_of[name][i]) for name in ranked
                  if np.isfinite(mase_of[name][i])]
        if len(values) < 2:
            continue
        order = sorted(values, key=lambda kv: kv[1])
        rank, previous, tie = 0, None, 0
        for j, (name, value) in enumerate(order):
            if previous is not None and abs(value - previous) < 1e-12:
                tie += 1
            else:
                rank = j + 1
                tie = 0
            cell_rank[name].append(rank)
            previous = value
    average_rank = {name: float(np.mean(v)) for name, v in cell_rank.items()}

    payload = {
        "stage": "v46-evaluation",
        "backbone": args.backbone,
        "block": args.block,
        "frozen": {"k": k, "beta": beta, "best_fixed_action": fixed,
                   "selection_file": str(freeze.relative_to(root))},
        "episodes": n,
        "external_baselines": external,
        "parents": int(len({c.parent for c in eval_catalogs})),
        "sources": sorted({c.source for c in eval_catalogs}),
        "rows": rows,
        "average_rank": average_rank,
        "comparisons": comparisons,
        "heterogeneity": heterogeneity(queries),
        "opportunity_strata": opportunity_strata(
            SEL.Queries(bank_catalogs, blocks=full_blocks), queries, rows, mase_of),
        "opportunity_strata_sensitivity": {
            f"x{factor}": opportunity_strata(
                SEL.Queries(bank_catalogs, blocks=full_blocks), queries, rows, mase_of,
                quantiles=(min(0.95, 0.50 * factor), min(0.98, 0.85 * factor)))
            for factor in (0.5, 1.0, 2.0)},
        "bank": {"episodes": len(bank_catalogs), "support": bank.support(),
                 "mean_utility": bank.mean_utility()},
        "runtime_seconds": time.perf_counter() - began,
    }
    write(OUT / f"evaluation/{args.block}_{args.backbone}.json", clean(payload))

    print(json.dumps(clean({
        "backbone": args.backbone, "block": args.block, "k": k, "beta": beta,
        "best_fixed": fixed,
        "mase": {name: rows[name]["mase"] for name in rows},
        "intervention_rate": {name: rows[name]["intervention_rate"] for name in rows},
        "conditional_hir": {name: rows[name]["conditional_hir"] for name in rows},
        "vs": {key: [v["difference"], v["ci_low"], v["ci_high"], v["excludes_zero"]]
               for key, v in comparisons.items()},
        "oracle_best_share": payload["heterogeneity"]["oracle_best_share"],
    }), indent=1))


if __name__ == "__main__":
    main()
