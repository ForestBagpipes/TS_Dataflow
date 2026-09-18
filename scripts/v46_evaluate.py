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
        "per_cell_mase": SEL.macro_by_cell(queries, out["mase"]),
        "action_counts": {a: int((selected == a).sum()) for a in SEL.ACTIONS},
    }
    return row


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
    parser.add_argument("--block", default="test", choices=["train_eval", "test"])
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
    comparisons = {}
    for reference in ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "A1_GLOBAL_UTILITY",
                      "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE", "A2_WO_INTERVENTION",
                      "A3_WO_FORECAST"):
        comparisons[f"FULL_INTROACT_vs_{reference}"] = SEL.paired_cluster_bootstrap(
            queries, mase_of["FULL_INTROACT"], mase_of[reference],
            resamples=args.resamples)

    ranked = [name for name in list(DEPLOYABLE) + list(ABLATIONS)]
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
        "parents": int(len({c.parent for c in eval_catalogs})),
        "sources": sorted({c.source for c in eval_catalogs}),
        "rows": rows,
        "average_rank": average_rank,
        "comparisons": comparisons,
        "heterogeneity": heterogeneity(queries),
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
