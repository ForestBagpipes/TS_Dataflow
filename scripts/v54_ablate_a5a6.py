#!/usr/bin/env python3
"""v54 plan ablations A5 (beta=0) and A6 (positive gate removed), 2026-09-22.

Plan semantics (user plan of 2026-09-22, mapped onto the frozen v54 protocol):

* ``A5_BETA0`` -- the FULL scoring pipeline with the frozen ``k`` and ``beta``
  forced to 0.  The conservative penalty ``beta * sigma / sqrt(n_eff)`` is the
  single changed variable; retrieval, parent clustering and the positive-score
  gate are unchanged.  When a backbone's frozen FULL configuration already has
  ``beta == 0`` the ablation coincides with FULL by construction; that is a
  valid result and is recorded as-is (no parameter is moved to manufacture a
  difference).
* ``A6_NO_POSITIVE_GATE`` -- the FULL recommendation ranking is kept exactly;
  only the execution condition "the top score must be strictly positive" is
  removed.  This is the decision branch ``decide(..., act_or_keep=False)``
  already present in ``introact_ts.v47.select`` (default behaviour unchanged):
  the highest-scoring admissible action runs whenever at least one action has
  a finite score, and a request whose legal set is KEEP alone (complete input)
  or whose scores are all ``-inf`` (no support) still keeps the reference.
  This is semantically identical to the existing ``A4_ALWAYS_ACT`` evaluation
  row; the identity is verified numerically against the frozen evaluation
  payload and recorded under ``a6_equals_existing_a4_always_act``.

The script reuses the v54 catalogue loading and distance matrices of
``scripts/v54_evaluate.py`` (via ``v54_common`` and ``introact_ts.v47.select``)
and the same ``SEL.realised`` / ``summarise`` / ``missed_opportunity`` metric
path.  FULL_INTROACT semantics and the frozen selection JSONs are not touched.

KEEP-only fallback (freeze section 4): if a backbone's frozen selection is
KEEP-only there is no (k, beta) to ablate; both ablations are skipped and the
skip is recorded, never filled with a default.

Writes only new files under ``results/v54/ablations/``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import state as ST
from introact_ts.v47 import select as SEL

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v47_evaluate import missed_opportunity, summarise
from v54_common import BACKBONES, OUT, ROOT, code_hashes, load_catalogs, sha

ABLATION_OUT = OUT / "ablations"
EVAL_OUT = OUT / "evaluation"
BLOCKS = ("test", "test30", "test50")

A5 = "A5_BETA0"
A6 = "A6_NO_POSITIVE_GATE"


def source_fixed_keep_pool_check(bank: SEL.Bank) -> dict:
    """Mapping check for plan A1: does adding KEEP to the argmax pool change
    the per-source fixed action?

    ``scripts/v53_source_fixed.source_fixed_policy`` takes the argmax over the
    non-reference actions only, with KEEP as the unavailability fallback; the
    plan wording ("same pool of all actions including KEEP") would let KEEP
    win on any source whose non-reference mean utilities are all negative
    (KEEP's realised utility is 0 by definition).  This reports, per source,
    the chosen action under both pools.  It changes nothing.
    """
    from v53_source_fixed import source_fixed_policy
    from introact_ts.v44 import protocol as P

    policy = source_fixed_policy(bank)
    out = {}
    for source in P.SOURCES:
        means = {a: s["mean_utility"]
                 for a, s in policy[source]["candidates"].items()}
        usable = {a: m for a, m in means.items() if m is not None}
        with_keep = dict(usable)
        with_keep[SEL.REFERENCE] = 0.0
        chosen_with_keep = (max(with_keep, key=lambda a: with_keep[a])
                            if with_keep else SEL.REFERENCE)
        out[source] = {
            "chosen_nonref_pool": policy[source]["action"],
            "chosen_pool_including_keep": chosen_with_keep,
            "differs": chosen_with_keep != policy[source]["action"],
            "nonref_mean_utility": means,
        }
    return out


def evaluate_block(backbone: str, block: str, *, bank, config, root: Path,
                   resamples: int, began: float) -> dict:
    eval_catalogs = load_catalogs(root, block, backbone)
    queries = SEL.Queries(eval_catalogs, blocks=SEL.blocks_of())
    D = SEL.distance_matrices(bank, queries, lopo=False)
    k, beta = config

    scores_full = SEL.score_grid(bank, queries, D, k, beta)
    decisions = {
        "FULL_INTROACT": SEL.decide(queries, scores_full),
        A5: SEL.decide(queries, SEL.score_grid(bank, queries, D, k, 0.0)),
        A6: SEL.decide(queries, scores_full, act_or_keep=False),
    }

    rows = {name: summarise(queries, sel, name) for name, sel in decisions.items()}
    for name, sel in decisions.items():
        rows[name]["missed_opportunity"] = missed_opportunity(queries, sel, 1e-9)
    mase_of = {name: SEL.realised(queries, sel) for name, sel in decisions.items()}

    comparisons = {}
    for name in (A5, A6):
        comparisons[f"FULL_INTROACT_vs_{name}"] = SEL.paired_cluster_bootstrap(
            queries, mase_of["FULL_INTROACT"], mase_of[name],
            resamples=resamples)

    # Numerical cross-check of the A6 == A4_ALWAYS_ACT mapping against the
    # frozen evaluation payload (same scores, same decision branch).
    a6_check = {"available": False}
    eval_path = EVAL_OUT / f"{block}_{backbone}.json"
    if eval_path.exists():
        existing = json.loads(eval_path.read_text())["rows"].get("A4_ALWAYS_ACT")
        if existing is not None:
            keys = ("mase", "intervention_rate", "conditional_hir",
                    "harmful_loss", "beneficial_precision",
                    "missed_opportunity")
            diff = {key: (None if existing.get(key) is None
                          else abs(rows[A6][key] - existing[key]))
                    for key in keys}
            a6_check = {
                "available": True,
                "evaluation_file": f"results/v54/evaluation/{block}_{backbone}.json",
                "max_abs_metric_diff": max(v for v in diff.values()
                                           if v is not None),
                "per_metric_abs_diff": diff,
                "identical": all(v is None or v <= 1e-12 for v in diff.values()),
            }

    payload = {
        "stage": "v54-ablation-a5a6",
        "state_version": ST.STATE_VERSION,
        "backbone": backbone,
        "block": block,
        "plan_date": "2026-09-22",
        "frozen": {"k": k, "beta": beta, "keep_only": False,
                   "selection_file": f"results/v54/protocol/selection_{backbone}.json"},
        "ablation_semantics": {
            A5: ("FULL scoring with the frozen k and beta forced to 0; the "
                 "conservative penalty is the single changed variable.  When "
                 "the frozen FULL beta is already 0 this row equals FULL by "
                 "construction and is recorded as-is."),
            A6: ("FULL recommendation ranking unchanged; only the "
                 "strictly-positive-top-score execution gate is removed "
                 "(decide(..., act_or_keep=False)).  Complete input or "
                 "all-unsupported requests still KEEP.  Semantically "
                 "identical to the existing A4_ALWAYS_ACT row."),
        },
        "a5_equals_full_by_construction": bool(beta == 0.0),
        "a6_equals_existing_a4_always_act": a6_check,
        "episodes": len(eval_catalogs),
        "rows": rows,
        "comparisons": comparisons,
        "code_sha256": code_hashes(root) | {
            "scripts/v54_ablate_a5a6.py": sha(Path(__file__).resolve())},
        "runtime_seconds": time.perf_counter() - began,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbones", default=",".join(BACKBONES))
    parser.add_argument("--blocks", default=",".join(BLOCKS))
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--bank-blocks", default="bankx")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    blocks = [b.strip() for b in args.blocks.split(",")]

    for backbone in [b.strip() for b in args.backbones.split(",")]:
        freeze = OUT / "protocol" / f"selection_{backbone}.json"
        if not freeze.exists():
            raise SystemExit(f"v54 configuration is not frozen for {backbone}: "
                             f"{freeze} missing")
        selection = json.loads(freeze.read_text())
        config = SEL.frozen_config(selection)

        bank_catalogs = []
        for name in args.bank_blocks.split(","):
            bank_catalogs.extend(load_catalogs(root, name.strip(), backbone))
        bank = SEL.Bank(bank_catalogs, blocks=SEL.blocks_of())
        keep_pool = source_fixed_keep_pool_check(bank)

        if config is None:
            # KEEP-only fallback (freeze section 4): no frozen (k, beta)
            # exists, so neither ablation has a configuration; record the
            # skip, never fill a default.
            for block in blocks:
                payload = {
                    "stage": "v54-ablation-a5a6",
                    "state_version": ST.STATE_VERSION,
                    "backbone": backbone,
                    "block": block,
                    "plan_date": "2026-09-22",
                    "frozen": {"k": None, "beta": None, "keep_only": True,
                               "selection_file":
                               f"results/v54/protocol/selection_{backbone}.json"},
                    "skipped_ablations": [A5, A6],
                    "skip_reason": ("frozen selection is KEEP-only; no (k, "
                                    "beta) configuration exists to ablate"),
                    "source_fixed_keep_pool_check": keep_pool,
                    "code_sha256": code_hashes(root) | {
                        "scripts/v54_ablate_a5a6.py":
                            sha(Path(__file__).resolve())},
                    "runtime_seconds": time.perf_counter() - began,
                }
                path = ABLATION_OUT / f"a5a6_{block}_{backbone}.json"
                from v54_common import clean, write
                write(path, clean(payload))
                print(json.dumps({"backbone": backbone, "block": block,
                                  "keep_only": True, "skipped": [A5, A6]}),
                      flush=True)
            continue

        for block in blocks:
            t0 = time.perf_counter()
            payload = evaluate_block(backbone, block, bank=bank, config=config,
                                     root=root, resamples=args.resamples,
                                     began=began)
            payload["source_fixed_keep_pool_check"] = keep_pool
            from v54_common import clean, write
            path = ABLATION_OUT / f"a5a6_{block}_{backbone}.json"
            write(path, clean(payload))
            print(json.dumps(clean({
                "backbone": backbone, "block": block,
                "k": config[0], "beta": config[1],
                "a5_equals_full": payload["a5_equals_full_by_construction"],
                "a6_identical_to_a4_always_act":
                    payload["a6_equals_existing_a4_always_act"].get("identical"),
                "mase": {n: payload["rows"][n]["mase"] for n in payload["rows"]},
                "intervention_rate": {n: payload["rows"][n]["intervention_rate"]
                                      for n in payload["rows"]},
                "block_seconds": time.perf_counter() - t0,
            }), indent=1), flush=True)


if __name__ == "__main__":
    main()
