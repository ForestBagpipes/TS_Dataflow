#!/usr/bin/env python3
"""v52 ablation correction: mechanism-level A2 variant, from the frozen cache.

Motivation (review findings E-002 / L-002 of 2026-09-20): the published A2 row
(``use_intervention=False``) only drops five intervention features from the
retrieval key while keeping same-action local utility estimation, so it does
not ablate the mechanism the paper claims as its contribution -- per-request,
per-action local utility retrieval.  This script recomputes the full ablation
ladder unchanged AND adds a mechanism-level variant:

* ``A2_WO_ACTION_COND`` -- action-blind retrieval.  The neighbourhood is
  retrieved from the pooled bank of all non-reference actions using the
  action-independent 17-dimensional state (mask + context + forecast), so the
  local utility estimate no longer conditions on the candidate action.  Actions
  remain distinguishable only through the bank-global mean utility of each
  action, added as a prior:  s_i(a) = mu_w(i) + (g_bar_a - g_bar_all)
  - beta * sigma_w(i) / sqrt(n_eff(i)).

The frozen (k, beta) of the backbone are reused unchanged; nothing is searched
or tuned for the new variant.  The original A2 row is recomputed with identical
semantics so both numbers stand side by side.

Outputs go to ``--output-root`` (default ``results/v52_ablation``) and never
overwrite ``results/v47`` or ``results/v47_verified``.
"""

from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import protocol as P
from introact_ts.v47 import select as SEL

ROOT = Path(__file__).resolve().parent.parent

NEW_VARIANT = "A2_WO_ACTION_COND"


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


def per_source_horizon(queries: SEL.Queries, mase: np.ndarray) -> dict:
    by_parent: dict[tuple, list[float]] = collections.defaultdict(list)
    for i in range(len(mase)):
        if np.isfinite(mase[i]):
            key = (int(queries.horizon[i]), queries.source[i], queries.parent[i])
            by_parent[key].append(float(mase[i]))
    by_source: dict[str, list[float]] = collections.defaultdict(list)
    for (horizon, source, _parent), values in by_parent.items():
        by_source[f"h{horizon}|{source}"].append(float(np.mean(values)))
    return {k: float(np.mean(v)) for k, v in sorted(by_source.items())}


def summarise(queries: SEL.Queries, selected: np.ndarray, name: str) -> dict:
    out = SEL.outcomes(queries, selected)
    return {
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


def missed_opportunity(queries: SEL.Queries, selected: np.ndarray,
                       threshold: float) -> float:
    keep_mase = SEL.realised(queries, np.full(len(selected), SEL.REFERENCE, dtype=object))
    oracle_mase = SEL.realised(queries, SEL.oracle(queries))
    opportunity = keep_mase - oracle_mase
    has = np.isfinite(opportunity) & (opportunity > threshold)
    if not has.any():
        return float("nan")
    return float((selected[has] == SEL.REFERENCE).mean())


def score_grid_action_pooled(bank: SEL.Bank, queries: SEL.Queries, k: int,
                             beta: float) -> dict[str, np.ndarray]:
    """A2 mechanism variant: action-blind neighbourhood + global action prior.

    ``bank`` and ``queries`` must have been built with the action-independent
    blocks (mask, context, forecast).  The neighbourhood of a request is its
    k nearest records in the union of every non-reference action's bank, so
    the local utility estimate carries no action conditioning.  The candidate
    actions are ranked by the shared local estimate shifted by the bank-global
    mean utility of each action.
    """
    n = len(queries.episode)
    zs, gs = [], []
    for a in SEL.NONREF:
        b = bank.per[a]
        if len(b.g):
            zs.append(b.Z)
            gs.append(b.g)
    if not zs:
        return {a: np.full(n, -np.inf) for a in SEL.ACTIONS}
    zp = np.vstack(zs)
    gp = np.concatenate(gs)
    mean = zp.mean(0)
    scale = zp.std(0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    B = (zp - mean) / scale
    g_all = float(gp.mean())
    g_action = {a: (float(bank.per[a].g.mean()) if len(bank.per[a].g) else None)
                for a in SEL.NONREF}

    # The 17-dimensional state is action-independent, but entries can be
    # missing per action; take the first finite row available.
    Q = np.full((n, zp.shape[1]), np.nan)
    for a in SEL.NONREF:
        take = ~np.isfinite(Q).all(1) & np.isfinite(queries.Z[a]).all(1)
        Q[take] = queries.Z[a][take]
    finite = np.isfinite(Q).all(1)
    Qs = np.where(np.isfinite(Q), Q, 0.0)
    Qs = (Qs - mean) / scale

    d = np.sqrt(np.maximum(
        (Qs ** 2).sum(1)[:, None] + (B ** 2).sum(1)[None, :] - 2.0 * Qs @ B.T,
        0.0))
    d[~finite] = np.inf

    ke = min(k, d.shape[1])
    idx = np.argpartition(d, ke - 1, axis=1)[:, :ke]
    dd = np.take_along_axis(d, idx, axis=1)
    order = np.argsort(dd, axis=1, kind="stable")
    idx = np.take_along_axis(idx, order, axis=1)
    dd = np.take_along_axis(dd, order, axis=1)
    gg = gp[idx]
    bad = ~np.isfinite(dd)
    dd = np.where(bad, 0.0, dd)
    tau = np.median(dd, axis=1)[:, None] + SEL.TAU_EPSILON
    w = np.exp(-dd / tau)
    w = np.where(bad, 0.0, w)
    wsum = w.sum(1)
    degenerate = wsum <= 0
    w[degenerate] = 1.0
    wsum = w.sum(1)
    mu = (w * gg).sum(1) / wsum
    sigma = np.sqrt((w * (gg - mu[:, None]) ** 2).sum(1) / wsum)
    n_eff = np.clip(wsum ** 2 / (w ** 2).sum(1), 1.0, ke)
    local = mu - beta * sigma / np.sqrt(n_eff)
    local[np.all(bad, axis=1)] = -np.inf

    scores = {SEL.REFERENCE: np.full(n, -np.inf)}
    for a in SEL.NONREF:
        if g_action[a] is None:
            scores[a] = np.full(n, -np.inf)
            continue
        s = local + (g_action[a] - g_all)
        scores[a] = np.where(np.isfinite(local), s, -np.inf)
    return scores


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--block", default="train_eval",
                        choices=["train_eval", "test", "test30", "test50",
                                 "test_m2", "test_m3"])
    parser.add_argument("--resamples", type=int, default=P.BOOTSTRAP_RESAMPLES)
    parser.add_argument("--bank-blocks", default="bankx")
    parser.add_argument("--replay", default="results/v47/replay")
    parser.add_argument("--protocol-dir", default="results/v47/protocol")
    parser.add_argument("--output-root", default="results/v52_ablation")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    out = root / args.output_root
    C.REPLAY = args.replay

    freeze = root / args.protocol_dir / f"selection_{args.backbone}.json"
    if not freeze.exists():
        raise SystemExit(f"configuration is not frozen for {args.backbone}: {freeze} missing")
    selection = json.loads(freeze.read_text())
    k = int(selection["selection"]["selected"]["k"])
    beta = float(selection["selection"]["selected"]["beta"])

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(C.load_catalog(root, name.strip(), args.backbone))
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
    decisions["FIXED_SAITS"] = SEL.apply_fixed(queries, "SAITS")
    scores = SEL.score_grid(bank, queries, D, k, beta)
    decisions["FULL_INTROACT"] = SEL.decide(queries, scores)
    decisions["A1_GLOBAL_UTILITY"] = SEL.decide(
        queries, SEL.score_grid(bank, queries, D, k, beta, local=False))
    decisions["A4_ALWAYS_ACT"] = SEL.decide(queries, scores, act_or_keep=False)
    decisions["A5_PARAMETRIC_RIDGE"] = SEL.parametric(bank, queries, kind="ridge")
    decisions["CATALOG_ORACLE"] = SEL.oracle(queries)

    # Original A2 / A3, semantics unchanged from the v47 evaluation.
    reduced = {}
    for label, kwargs in (("A2_WO_INTERVENTION", {"use_intervention": False}),
                          ("A3_WO_FORECAST", {"use_forecast": False})):
        blocks = SEL.blocks_of(**kwargs)
        b2 = SEL.Bank(bank_catalogs, blocks=blocks)
        q2 = SEL.Queries(eval_catalogs, blocks=blocks)
        D2 = SEL.distance_matrices(b2, q2, lopo=False)
        decisions[label] = SEL.decide(q2, SEL.score_grid(b2, q2, D2, k, beta))
        reduced[label] = (b2, q2)

    # New mechanism-level A2: action-blind neighbourhood on the same reduced
    # blocks as the original A2, with the same frozen (k, beta).
    b17, q17 = reduced["A2_WO_INTERVENTION"]
    decisions[NEW_VARIANT] = SEL.decide(
        q17, score_grid_action_pooled(b17, q17, k, beta))

    rows = {name: summarise(queries, sel, name) for name, sel in decisions.items()}
    for name, sel in decisions.items():
        rows[name]["missed_opportunity"] = missed_opportunity(queries, sel, 1e-9)

    mase_of = {name: SEL.realised(queries, sel) for name, sel in decisions.items()}

    comparisons = {}
    for reference in ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FIXED_SAITS",
                      "A1_GLOBAL_UTILITY", "A2_WO_INTERVENTION", NEW_VARIANT,
                      "A3_WO_FORECAST", "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE"):
        comparisons[f"FULL_INTROACT_vs_{reference}"] = SEL.paired_cluster_bootstrap(
            queries, mase_of["FULL_INTROACT"], mase_of[reference],
            resamples=args.resamples)

    payload = {
        "stage": "v52-ablation-action-cond",
        "note": ("Recomputes the v47 ablation ladder unchanged and adds "
                 "A2_WO_ACTION_COND: action-blind pooled neighbourhood with a "
                 "bank-global per-action utility prior, same frozen (k, beta). "
                 "No tuning of the new variant on any block."),
        "backbone": args.backbone,
        "block": args.block,
        "replay": args.replay,
        "frozen": {"k": k, "beta": beta, "best_fixed_action": fixed,
                   "selection_file": str(freeze.relative_to(root))},
        "episodes": n,
        "parents": int(len({c.parent for c in eval_catalogs})),
        "sources": sorted({c.source for c in eval_catalogs}),
        "rows": rows,
        "comparisons": comparisons,
        "bank": {"episodes": len(bank_catalogs), "support": bank.support(),
                 "mean_utility": bank.mean_utility()},
        "runtime_seconds": time.perf_counter() - began,
    }
    write(out / f"evaluation/{args.block}_{args.backbone}.json", clean(payload))

    print(json.dumps(clean({
        "backbone": args.backbone, "block": args.block, "k": k, "beta": beta,
        "mase": {name: rows[name]["mase"] for name in rows},
        "rmsse": {name: rows[name]["rmsse"] for name in rows},
        "intervention_rate": {name: rows[name]["intervention_rate"] for name in rows},
        "conditional_hir": {name: rows[name]["conditional_hir"] for name in rows},
        "harmful_loss": {name: rows[name]["harmful_loss"] for name in rows},
        "vs": {key: [v["difference"], v["ci_low"], v["ci_high"], v["excludes_zero"]]
               for key, v in comparisons.items()},
    }), indent=1))


if __name__ == "__main__":
    main()
