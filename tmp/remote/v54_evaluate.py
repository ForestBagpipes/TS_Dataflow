#!/usr/bin/env python3
"""v54 stage 4a step 3: full-roster evaluation on the v54 semantics.

Same aggregation code path as ``scripts/v47_evaluate.py`` (imported, not
copied), on catalogs whose state vectors carry the v54-full22 intervention
block, scored by the parent-clustered v54 selector with the frozen
``results/v54/protocol/selection_{backbone}.json``.

Roster additions relative to the v47 run (freeze section 3):

* ``SOURCE_FIXED`` -- per-source fixed action chosen on TRAIN-side bank
  utility, KEEP fallback (the ``v53_source_fixed`` policy functions, reused);
* ``A2_WO_ACTION_COND`` (A2_M) -- action-blind pooled neighbourhood with a
  bank-global per-action utility prior, recomputed under parent clustering so
  FULL vs A2_M isolates action conditioning as the single changed variable;
* ``A2_WO_INTERVENTION`` (A2_F) -- meaningful again under v54-full22 states;
* ``TATO`` on every block, read from the published ``results/v47/baselines``
  records (forecast cache; nothing is re-run).

The Holm family gains SOURCE_FIXED relative to v47 (it is a catalogue-policy
comparison row, not an ablation); this is recorded in the payload.

KEEP-only fallback (freeze section 4): when the backbone's selection is
KEEP-only, FULL_INTROACT is the all-KEEP decision and the ablations that need
a frozen (k, beta) are skipped and recorded, never filled with a default.

One invocation runs all six evaluation blocks for one backbone, loading the
bank catalog once.  Writes only under ``results/v54/evaluation/``.
"""

from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import state as ST
from introact_ts.v47 import select as SEL

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v47_evaluate import (clean, heterogeneity, load_baseline,
                          missed_opportunity, opportunity_strata,
                          per_source_horizon, summarise, summarise_vectors,
                          write)
from v53_source_fixed import apply_source_fixed, source_fixed_policy
from v54_common import (BACKBONES, EVAL_BLOCKS, OUT, ROOT, code_hashes,
                        load_catalogs, sha)

EVAL_OUT = OUT / "evaluation"

#: Rows that carry a claim, in table order.  SOURCE_FIXED joins the v47 pool;
#: the oracle is a diagnostic and is excluded from every rank.
DEPLOYABLE = ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "R2_CART",
              "FIXED_SAITS", "FULL_INTROACT")

BASELINES = {"tato": "TATO", "timesnet": "TIMESNET", "pswi": "PSW_I", "t1": "T1"}
ABLATIONS = ("A1_GLOBAL_UTILITY", "A2_WO_INTERVENTION", "A2_WO_ACTION_COND",
             "A3_WO_FORECAST", "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE")

#: Ablations that need a frozen (k, beta) and therefore have no configuration
#: under the KEEP-only fallback.
CONFIG_DEPENDENT = ("A1_GLOBAL_UTILITY", "A4_ALWAYS_ACT", "A2_WO_INTERVENTION",
                    "A3_WO_FORECAST", "A2_WO_ACTION_COND")


def score_grid_action_pooled(bank: SEL.Bank, queries: SEL.Queries, k: int,
                             beta: float) -> dict[str, np.ndarray]:
    """A2 mechanism variant: action-blind neighbourhood + global action prior.

    Same construction as the v52 correction (``v52_ablation_action_cond``) --
    the neighbourhood is retrieved from the pooled bank of all non-reference
    actions on the action-independent blocks, and actions are ranked by the
    shared local estimate shifted by the bank-global per-action mean utility --
    but with the v54 parent clustering applied to the pooled neighbourhood, so
    FULL vs A2_WO_ACTION_COND isolates action conditioning alone.
    """
    n = len(queries.episode)
    zs, gs, ps = [], [], []
    for a in SEL.NONREF:
        b = bank.per[a]
        if len(b.g):
            zs.append(b.Z)
            gs.append(b.g)
            ps.append(b.parent)
    if not zs:
        return {a: np.full(n, -np.inf) for a in SEL.ACTIONS}
    zp = np.vstack(zs)
    gp = np.concatenate(gs)
    pp = np.concatenate(ps)
    mean = zp.mean(0)
    scale = zp.std(0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    B = (zp - mean) / scale
    g_all = float(gp.mean())
    g_action = {a: (float(bank.per[a].g.mean()) if len(bank.per[a].g) else None)
                for a in SEL.NONREF}

    # The reduced state is action-independent, but entries can be missing per
    # action; take the first finite row available.
    Q = np.full((n, zp.shape[1]), np.nan)
    for a in SEL.NONREF:
        take = ~np.isfinite(Q).all(1) & np.isfinite(queries.Z[a]).all(1)
        Q[take] = queries.Z[a][take]
    finite = np.isfinite(Q).all(1)
    Qs = (np.where(np.isfinite(Q), Q, 0.0) - mean) / scale

    d = np.sqrt(np.maximum(
        (Qs ** 2).sum(1)[:, None] + (B ** 2).sum(1)[None, :] - 2.0 * Qs @ B.T, 0.0))
    d[~finite] = np.inf

    ke = min(k, d.shape[1])
    idx = np.argpartition(d, ke - 1, axis=1)[:, :ke]
    dd = np.take_along_axis(d, idx, axis=1)
    order = np.argsort(dd, axis=1, kind="stable")
    idx = np.take_along_axis(idx, order, axis=1)
    dd = np.take_along_axis(dd, order, axis=1)
    gg = gp[idx]
    parents = pp[idx]

    local = np.full(n, -np.inf)
    for i in range(n):
        ok = np.isfinite(dd[i])
        if not ok.any():
            continue
        dist = dd[i][ok]
        util = gg[i][ok]
        par = parents[i][ok]
        tau = float(np.median(dist)) + SEL.TAU_EPSILON
        uniq, inv = np.unique(par, return_inverse=True)
        d_parent = np.full(len(uniq), np.inf)
        np.minimum.at(d_parent, inv, dist)
        count = np.bincount(inv, minlength=len(uniq)).astype(np.float64)
        g_parent = np.bincount(inv, weights=util, minlength=len(uniq)) / count
        w = np.exp(-d_parent / tau)
        wsum = float(w.sum())
        if not np.isfinite(wsum) or wsum <= 0.0:
            w = np.ones(len(uniq))
            wsum = float(len(uniq))
        mu = float((w * g_parent).sum() / wsum)
        sigma = float(np.sqrt((w * (g_parent - mu) ** 2).sum() / wsum))
        local[i] = mu - beta * sigma / np.sqrt(float(len(uniq)))

    scores = {SEL.REFERENCE: np.full(n, -np.inf)}
    for a in SEL.NONREF:
        if g_action[a] is None:
            scores[a] = np.full(n, -np.inf)
            continue
        s = local + (g_action[a] - g_all)
        scores[a] = np.where(np.isfinite(local), s, -np.inf)
    return scores


def evaluate_block(backbone: str, block: str, *, bank, bank_catalogs,
                   config, keep_only: bool, root: Path,
                   resamples: int, began: float) -> dict:
    full_blocks = SEL.blocks_of()
    eval_catalogs = load_catalogs(root, block, backbone)
    queries = SEL.Queries(eval_catalogs, blocks=full_blocks)
    D = SEL.distance_matrices(bank, queries, lopo=False)

    decisions: dict[str, np.ndarray] = {}
    n = len(eval_catalogs)
    decisions["NATIVE_KEEP"] = np.full(n, SEL.REFERENCE, dtype=object)
    fixed = SEL.best_fixed_action(bank)
    decisions["BEST_FIXED"] = SEL.apply_fixed(queries, fixed)
    policy = source_fixed_policy(bank)
    source_sel, source_fallback = apply_source_fixed(queries, policy)
    decisions["SOURCE_FIXED"] = source_sel
    decisions["R2_CART"] = SEL.r2_cart(bank, queries)
    decisions["FIXED_SAITS"] = SEL.apply_fixed(queries, "SAITS")
    if keep_only:
        decisions["FULL_INTROACT"] = np.full(n, SEL.REFERENCE, dtype=object)
        skipped = list(CONFIG_DEPENDENT)
    else:
        k, beta = config
        scores = SEL.score_grid(bank, queries, D, k, beta)
        decisions["FULL_INTROACT"] = SEL.decide(queries, scores)
        decisions["A1_GLOBAL_UTILITY"] = SEL.decide(
            queries, SEL.score_grid(bank, queries, D, k, beta, local=False))
        decisions["A4_ALWAYS_ACT"] = SEL.decide(queries, scores, act_or_keep=False)
        skipped = []
    decisions["A5_PARAMETRIC_RIDGE"] = SEL.parametric(bank, queries, kind="ridge")
    decisions["CATALOG_ORACLE"] = SEL.oracle(queries)

    if not keep_only:
        k, beta = config
        for label, kwargs in (("A2_WO_INTERVENTION", {"use_intervention": False}),
                              ("A3_WO_FORECAST", {"use_forecast": False})):
            blocks = SEL.blocks_of(**kwargs)
            b2 = SEL.Bank(bank_catalogs, blocks=blocks)
            q2 = SEL.Queries(eval_catalogs, blocks=blocks)
            D2 = SEL.distance_matrices(b2, q2, lopo=False)
            decisions[label] = SEL.decide(q2, SEL.score_grid(b2, q2, D2, k, beta))
            if label == "A2_WO_INTERVENTION":
                # A2_M shares A2_F's action-independent blocks and the frozen
                # (k, beta); only the action conditioning is removed.
                decisions["A2_WO_ACTION_COND"] = SEL.decide(
                    q2, score_grid_action_pooled(b2, q2, k, beta))

    rows = {name: summarise(queries, sel, name) for name, sel in decisions.items()}
    for name, sel in decisions.items():
        rows[name]["missed_opportunity"] = missed_opportunity(queries, sel, 1e-9)

    mase_of = {name: SEL.realised(queries, sel) for name, sel in decisions.items()}

    keep_mase = mase_of["NATIVE_KEEP"]
    external = {}
    for method, label in BASELINES.items():
        loaded = load_baseline(root, method, block, backbone, queries)
        if loaded is None:
            continue
        rows[label] = summarise_vectors(queries, loaded["mase"], loaded["rmsse"],
                                        label, keep_mase=keep_mase)
        rows[label]["missed_opportunity"] = 0.0
        rows[label]["scored_episodes"] = loaded["scored"]
        mase_of[label] = loaded["mase"]
        external[label] = loaded["scored"]

    comparisons = {}
    for reference in (("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "R2_CART",
                       "FIXED_SAITS", "A1_GLOBAL_UTILITY", "A2_WO_INTERVENTION",
                       "A2_WO_ACTION_COND", "A3_WO_FORECAST", "A4_ALWAYS_ACT",
                       "A5_PARAMETRIC_RIDGE") + tuple(external)):
        if reference not in mase_of:
            continue  # ablation skipped under the KEEP-only fallback
        comparisons[f"FULL_INTROACT_vs_{reference}"] = SEL.paired_cluster_bootstrap(
            queries, mase_of["FULL_INTROACT"], mase_of[reference],
            resamples=resamples)

    # Holm across the pre-declared comparison rows only; the ablations are
    # variants of this method rather than competing claims.  SOURCE_FIXED is a
    # catalogue-policy row and joins the family in v54.
    family = [f"FULL_INTROACT_vs_{name}" for name
              in ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "R2_CART",
                  "FIXED_SAITS") + tuple(external)
              if f"FULL_INTROACT_vs_{name}" in comparisons]
    adjusted = SEL.holm({key: comparisons[key]["p_value"] for key in family})
    for key in family:
        comparisons[key]["p_holm"] = adjusted[key]
        comparisons[key]["significant_holm"] = bool(adjusted[key] < 0.05)
        comparisons[key]["in_holm_family"] = True

    ranked = [name for name in list(DEPLOYABLE) + list(external)]
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

    ablation_pool = ["FULL_INTROACT"] + list(ABLATIONS)
    ablation_rank_cells = collections.defaultdict(list)
    for i in range(n):
        values = [(name, mase_of[name][i]) for name in ablation_pool
                  if name in mase_of and np.isfinite(mase_of[name][i])]
        if len(values) < 2:
            continue
        for j, (name, _value) in enumerate(sorted(values, key=lambda kv: kv[1])):
            ablation_rank_cells[name].append(j + 1)
    ablation_rank = {name: float(np.mean(v))
                     for name, v in ablation_rank_cells.items()}

    k, beta = config if config is not None else (None, None)
    payload = {
        "stage": "v54-evaluation",
        "state_version": ST.STATE_VERSION,
        "backbone": backbone,
        "block": block,
        "frozen": {"k": k, "beta": beta, "keep_only": keep_only,
                   "skipped_ablations": skipped,
                   "best_fixed_action": fixed,
                   "source_fixed_policy": {s: p["action"] for s, p in policy.items()},
                   "source_fixed_fallback_counts": source_fallback,
                   "selection_file": f"results/v54/protocol/selection_{backbone}.json"},
        "holm_family_note": ("SOURCE_FIXED joins the v47 Holm family "
                             "(NATIVE_KEEP, BEST_FIXED, R2_CART, FIXED_SAITS, "
                             "external) as a catalogue-policy comparison row"),
        "episodes": n,
        "external_baselines": external,
        "parents": int(len({c.parent for c in eval_catalogs})),
        "sources": sorted({c.source for c in eval_catalogs}),
        "rows": rows,
        "average_rank": average_rank,
        "average_rank_pool": ranked,
        "ablation_rank": ablation_rank,
        "comparisons": comparisons,
        "heterogeneity": heterogeneity(queries),
        "opportunity_strata": opportunity_strata(
            SEL.Queries(bank_catalogs, blocks=full_blocks), queries, rows, mase_of),
        "opportunity_strata_sensitivity": {
            f"x{factor}": opportunity_strata(
                SEL.Queries(bank_catalogs, blocks=full_blocks), queries, rows,
                mase_of,
                quantiles=(min(0.95, 0.50 * factor), min(0.98, 0.85 * factor)))
            for factor in (0.5, 1.0, 2.0)},
        "bank": {"episodes": len(bank_catalogs), "support": bank.support(),
                 "mean_utility": bank.mean_utility()},
        "code_sha256": code_hashes(root) | {
            "scripts/v54_evaluate.py": sha(Path(__file__).resolve())},
        "runtime_seconds": time.perf_counter() - began,
    }
    write(EVAL_OUT / f"{block}_{backbone}.json", clean(payload))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--blocks", default=",".join(EVAL_BLOCKS))
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--bank-blocks", default="bankx")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    freeze = OUT / "protocol" / f"selection_{args.backbone}.json"
    if not freeze.exists():
        raise SystemExit(f"v54 configuration is not frozen for {args.backbone}: "
                         f"{freeze} missing; run scripts/v54_select.py first")
    selection = json.loads(freeze.read_text())
    config = SEL.frozen_config(selection)
    keep_only = config is None

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(load_catalogs(root, name.strip(), args.backbone))
    bank = SEL.Bank(bank_catalogs, blocks=SEL.blocks_of())

    for block in args.blocks.split(","):
        payload = evaluate_block(args.backbone, block.strip(),
                                 bank=bank, bank_catalogs=bank_catalogs,
                                 config=config, keep_only=keep_only,
                                 root=root, resamples=args.resamples,
                                 began=began)
        print(json.dumps(clean({
            "backbone": args.backbone, "block": block,
            "k": payload["frozen"]["k"], "beta": payload["frozen"]["beta"],
            "keep_only": keep_only,
            "mase": {name: payload["rows"][name]["mase"]
                     for name in payload["rows"]},
            "intervention_rate": {name: payload["rows"][name]["intervention_rate"]
                                  for name in payload["rows"]},
        }), indent=1), flush=True)


if __name__ == "__main__":
    main()
