#!/usr/bin/env python3
"""v55 step 3: full-roster evaluation under the pooled estimator.

Everything outside the decision layer is the v54 pipeline, imported rather than
copied: the same catalogs, the same prediction cache, the same summaries, the
same parent clustered paired bootstrap and the same external baseline loader.
What this script adds is the row set the pooled rule needs.

``FULL_INTROACT`` is the pooled rule at the frozen ``(k, beta, lam)`` with the
zero threshold, so its accuracy is directly comparable with the v54 number.
``E_LOCAL_ONLY`` is the same rule with ``lam = 0``, which is the v54 rule
exactly, and ``E_SOURCE_ONLY`` is ``lam = inf``, which scores by the source
level mean alone.  Those two bracket the estimator and make the pooling the
single changed variable.  ``CONFORMAL_A*`` applies the thresholds calibrated by
``scripts/v55_conformal.py`` on the internal evaluation block, and the payload
records the harmful loss each one actually produced here so the promised level
can be checked against the realised one.

Writes only under ``results/v55/evaluation/``.
"""

from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import state as ST
from introact_ts.v47 import select as SEL
from introact_ts.v55 import select as V55

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import (BACKBONES, EVAL_BLOCKS, OUT, ROOT, clean, code_hashes,
                        load_catalogs, sha, write)
from v47_evaluate import (heterogeneity, load_baseline, missed_opportunity,
                          opportunity_strata, summarise, summarise_vectors)
from v54_evaluate import (BASELINES, apply_source_fixed, score_grid_action_pooled,
                          source_fixed_policy)

OUT55 = ROOT / "results/v55"
EVAL_OUT = OUT55 / "evaluation"

DEPLOYABLE = ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "R2_CART",
              "FIXED_SAITS", "FULL_INTROACT")
ABLATIONS = ("E_LOCAL_ONLY", "E_SOURCE_ONLY", "A1_GLOBAL_UTILITY",
             "A2_WO_INTERVENTION", "A2_WO_ACTION_COND", "A3_WO_FORECAST",
             "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE")
CONFIG_DEPENDENT = ("E_LOCAL_ONLY", "E_SOURCE_ONLY", "A1_GLOBAL_UTILITY",
                    "A4_ALWAYS_ACT", "A2_WO_INTERVENTION", "A3_WO_FORECAST",
                    "A2_WO_ACTION_COND")


def alpha_label(alpha: float) -> str:
    return "CONFORMAL_A%s" % ("%.3f" % alpha).replace("0.", "").rstrip("0")


def evaluate_block(backbone: str, block: str, *, bank, bank_catalogs, config,
                   keep_only: bool, conformal: dict, root: Path,
                   resamples: int, began: float) -> dict:
    full_blocks = SEL.blocks_of()
    eval_catalogs = load_catalogs(root, block, backbone)
    queries = SEL.Queries(eval_catalogs, blocks=full_blocks)
    D = SEL.distance_matrices(bank, queries, lopo=False)
    means = V55.source_action_means(bank)
    n = len(eval_catalogs)

    decisions: dict[str, np.ndarray] = {}
    decisions["NATIVE_KEEP"] = np.full(n, SEL.REFERENCE, dtype=object)
    fixed = SEL.best_fixed_action(bank)
    decisions["BEST_FIXED"] = SEL.apply_fixed(queries, fixed)
    policy = source_fixed_policy(bank)
    source_sel, source_fallback = apply_source_fixed(queries, policy)
    decisions["SOURCE_FIXED"] = source_sel
    decisions["R2_CART"] = SEL.r2_cart(bank, queries)
    decisions["FIXED_SAITS"] = SEL.apply_fixed(queries, "SAITS")

    conformal_applied = []
    crossfit_applied = []
    if keep_only:
        decisions["FULL_INTROACT"] = np.full(n, SEL.REFERENCE, dtype=object)
        skipped = list(CONFIG_DEPENDENT)
    else:
        k, beta, lam = config
        moments = V55.local_moments(bank, queries, D, k)
        scores = V55.scores_from_moments(moments, means, queries, beta, lam)
        decisions["FULL_INTROACT"] = V55.decide(queries, scores, threshold=0.0)
        decisions["E_LOCAL_ONLY"] = V55.decide(
            queries,
            V55.scores_from_moments(moments, means, queries, beta, 0.0))
        decisions["E_SOURCE_ONLY"] = V55.decide(
            queries,
            V55.scores_from_moments(moments, means, queries, beta,
                                    float("inf")))
        decisions["A1_GLOBAL_UTILITY"] = SEL.decide(
            queries, SEL.score_grid(bank, queries, D, k, beta, local=False))
        decisions["A4_ALWAYS_ACT"] = V55.decide(queries, scores,
                                                threshold=-np.inf)
        for level in conformal.get("levels", []):
            label = alpha_label(level["alpha"])
            decisions[label] = V55.decide(queries, scores,
                                          threshold=float(level["threshold"]))
            conformal_applied.append({"row": label, "alpha": level["alpha"],
                                      "threshold": level["threshold"],
                                      "calibration_harm": level["calibration_harm"],
                                      "crc_bound": level["crc_bound"]})
        # Deployment style calibration: the threshold of each parent fold comes
        # from the other fold of this same block, which is what a served system
        # can do once a horizon has passed and the outcome is visible.
        alphas = conformal.get("alpha_grid") or [0.01, 0.02, 0.03, 0.05]
        for item in V55.crossfit_conformal(queries, scores, alphas):
            label = "CROSSFIT_A%s" % ("%.3f" % item["alpha"]).replace("0.", "").rstrip("0")
            decisions[label] = V55.decide_with_mask(queries, scores,
                                                    item["applied"])
            crossfit_applied.append({k: v for k, v in item.items()
                                     if k != "applied"} | {"row": label})
        skipped = []
    decisions["A5_PARAMETRIC_RIDGE"] = SEL.parametric(bank, queries, kind="ridge")
    decisions["CATALOG_ORACLE"] = SEL.oracle(queries)

    if not keep_only:
        k, beta, lam = config
        for label, kwargs in (("A2_WO_INTERVENTION", {"use_intervention": False}),
                              ("A3_WO_FORECAST", {"use_forecast": False})):
            blocks = SEL.blocks_of(**kwargs)
            b2 = SEL.Bank(bank_catalogs, blocks=blocks)
            q2 = SEL.Queries(eval_catalogs, blocks=blocks)
            D2 = SEL.distance_matrices(b2, q2, lopo=False)
            m2 = V55.local_moments(b2, q2, D2, k)
            means2 = V55.source_action_means(b2)
            decisions[label] = V55.decide(
                q2, V55.scores_from_moments(m2, means2, q2, beta, lam))
            if label == "A2_WO_INTERVENTION":
                decisions["A2_WO_ACTION_COND"] = SEL.decide(
                    q2, score_grid_action_pooled(b2, q2, k, beta))

    rows = {name: summarise(queries, sel, name) for name, sel in decisions.items()}
    for name, sel in decisions.items():
        rows[name]["missed_opportunity"] = missed_opportunity(queries, sel, 1e-9)
        rows[name]["harm_clipped"] = float(
            V55.harm_per_request(queries, sel).mean())

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
    controls = (("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "R2_CART",
                 "FIXED_SAITS") + tuple(external) + ABLATIONS
                + tuple(item["row"] for item in conformal_applied)
                + tuple(item["row"] for item in crossfit_applied))
    for reference in controls:
        if reference not in mase_of or reference == "FULL_INTROACT":
            continue
        comparisons[f"FULL_INTROACT_vs_{reference}"] = SEL.paired_cluster_bootstrap(
            queries, mase_of["FULL_INTROACT"], mase_of[reference],
            resamples=resamples)

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

    ablation_pool = ["FULL_INTROACT"] + [a for a in ABLATIONS if a in mase_of]
    ablation_cells = collections.defaultdict(list)
    for i in range(n):
        values = [(name, mase_of[name][i]) for name in ablation_pool
                  if np.isfinite(mase_of[name][i])]
        if len(values) < 2:
            continue
        for j, (name, _v) in enumerate(sorted(values, key=lambda kv: kv[1])):
            ablation_cells[name].append(j + 1)
    ablation_rank = {name: float(np.mean(v)) for name, v in ablation_cells.items()}

    k, beta, lam = config if config is not None else (None, None, None)
    payload = {
        "stage": "v55-evaluation",
        "state_version": ST.STATE_VERSION,
        "backbone": backbone,
        "block": block,
        "frozen": {"k": k, "beta": beta,
                   "lam": (None if lam is None or np.isinf(lam) else lam),
                   "lam_is_inf": bool(lam is not None and np.isinf(lam)),
                   "keep_only": keep_only,
                   "skipped_ablations": skipped,
                   "best_fixed_action": fixed,
                   "source_fixed_policy": {s: p["action"] for s, p in policy.items()},
                   "source_fixed_fallback_counts": source_fallback,
                   "selection_file": f"results/v55/protocol/selection_{backbone}.json",
                   "conformal_file": f"results/v55/protocol/conformal_{backbone}.json"},
        "crossfit_conformal_rows": [
            dict(item, realised_mase=float(SEL.source_macro(
                queries, mase_of[item["row"]])),
                 realised_harmful_loss=rows[item["row"]]["harmful_loss"])
            for item in crossfit_applied],
        "conformal_rows": [
            dict(item, realised_harm=rows[item["row"]]["harm_clipped"],
                 realised_harmful_loss=rows[item["row"]]["harmful_loss"],
                 realised_intervention_rate=rows[item["row"]]["intervention_rate"],
                 respected=bool(rows[item["row"]]["harm_clipped"] <= item["alpha"]))
            for item in conformal_applied],
        "holm_family_note": ("the Holm family holds the pre-declared comparison "
                             "rows only; the estimator and gate ablations are "
                             "variants of this method"),
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
        "bank": {"episodes": len(bank_catalogs), "support": bank.support(),
                 "mean_utility": bank.mean_utility()},
        "code_sha256": code_hashes(root) | {
            "scripts/v55_evaluate.py": sha(Path(__file__).resolve()),
            "src/introact_ts/v55/select.py": sha(
                root / "src/introact_ts/v55/select.py")},
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
    freeze = OUT55 / "protocol" / f"selection_{args.backbone}.json"
    if not freeze.exists():
        raise SystemExit(f"v55 configuration is not frozen for {args.backbone}: "
                         f"{freeze} missing; run scripts/v55_select.py first")
    selection = json.loads(freeze.read_text())
    config = V55.frozen_config(selection)
    keep_only = config is None
    calib = OUT55 / "protocol" / f"conformal_{args.backbone}.json"
    conformal = json.loads(calib.read_text()) if calib.exists() else {"levels": []}

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(load_catalogs(root, name.strip(), args.backbone))
    bank = SEL.Bank(bank_catalogs, blocks=SEL.blocks_of())

    for block in args.blocks.split(","):
        payload = evaluate_block(args.backbone, block.strip(),
                                 bank=bank, bank_catalogs=bank_catalogs,
                                 config=config, keep_only=keep_only,
                                 conformal=conformal, root=root,
                                 resamples=args.resamples, began=began)
        print(json.dumps(clean({
            "backbone": args.backbone, "block": block,
            "frozen": payload["frozen"]["k"] and {
                "k": payload["frozen"]["k"], "beta": payload["frozen"]["beta"],
                "lam": payload["frozen"]["lam"],
                "lam_is_inf": payload["frozen"]["lam_is_inf"]},
            "mase": {name: payload["rows"][name]["mase"] for name in payload["rows"]},
            "intervention_rate": {name: payload["rows"][name]["intervention_rate"]
                                  for name in payload["rows"]},
        }), indent=1), flush=True)


if __name__ == "__main__":
    main()
