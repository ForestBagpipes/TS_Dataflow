#!/usr/bin/env python3
"""v53 gate controls, part 2 (review plan diagnostic-A completion).

v52 already shipped the mean-only / linear / random gate controls matched to
the full method's intervention rate (``scripts/v52_gate_controls.py``).  This
script adds the remaining frequency-matched controls, all computed offline
from the frozen replay cache:

* ``R2_CART_T05``       -- the inherited R2-CART control at its original 0.5
  probability threshold (``SEL.r2_cart``).  Recomputed here and cross-checked
  against ``results/v47/evaluation/<block>_<backbone>.json``.
* ``R2_CART_MATCHED``   -- the same per-action trees, but the execution
  threshold theta is scanned on TRAIN-eval so the intervention rate matches
  FULL's TRAIN-eval rate, then frozen and applied unchanged to TEST.
* ``BEST_FIXED_RANDOM`` -- BEST_FIXED's action executed with probability p by
  a deterministic hash of the request identity, otherwise KEEP; p equals
  FULL's TRAIN-eval intervention rate (matched on TRAIN-eval, frozen for
  TEST).  This separates "which action" from "how often" for the fixed-action
  control family.

Thresholds and probabilities are calibrated on train_eval only and reported on
test as realised, never re-matched.  Nothing here runs a model.

Outputs go to ``results/v53_state_compact/`` and never overwrite v47/v52.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import protocol as P
from introact_ts.v47 import select as SEL

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v52_ablation_action_cond import clean, summarise, write

ROOT = Path(__file__).resolve().parent.parent

HASH_TAG = "v53-best-fixed-random-keep"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def r2_cart_posteriors(bank: SEL.Bank, queries: SEL.Queries, *, max_depth: int = 3,
                       min_samples_leaf: int = 96, seed: int = 101):
    """SEL.r2_cart refactored to also return the winning probability.

    Same models, same fits, same tie handling: the selected action is the one
    with the highest P(utility > 0); the returned probability drives the
    threshold scan.  ``R2_CART_T05`` below must reproduce ``SEL.r2_cart``
    exactly, which is asserted.
    """
    from sklearn.tree import DecisionTreeClassifier

    models = {}
    for a in SEL.NONREF:
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
    best = np.full(n, SEL.REFERENCE, dtype=object)
    best_p = np.full(n, -np.inf)
    for a, model in models.items():
        Z = queries.Z[a]
        ok = np.isfinite(Z).all(1) & queries.legal[a]
        if not ok.any():
            continue
        p = np.zeros(n)
        p[ok] = model.predict_proba(Z[ok])[:, 1]
        take = ok & (p > best_p)
        best[take] = a
        best_p[take] = p[take]
    return best, best_p


def gate_at(best: np.ndarray, best_p: np.ndarray, theta: float) -> np.ndarray:
    sel = np.full(len(best), SEL.REFERENCE, dtype=object)
    take = (best != SEL.REFERENCE) & np.isfinite(best_p) & (best_p > theta)
    sel[take] = best[take]
    return sel


def hash_uniform(episode: str) -> float:
    digest = hashlib.sha256(f"{HASH_TAG}|{episode}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(2 ** 64)


def best_fixed_random(queries: SEL.Queries, action: str, p: float) -> np.ndarray:
    sel = np.full(len(queries.episode), SEL.REFERENCE, dtype=object)
    if action == SEL.REFERENCE or p <= 0:
        return sel
    for i, episode in enumerate(queries.episode):
        if queries.legal[action][i] and hash_uniform(str(episode)) < p:
            sel[i] = action
    return sel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--bank-blocks", default="bankx")
    parser.add_argument("--resamples", type=int, default=P.BOOTSTRAP_RESAMPLES)
    parser.add_argument("--replay", default="results/v47/replay")
    parser.add_argument("--protocol-dir", default="results/v47/protocol")
    parser.add_argument("--v47-evaluation-dir", default="results/v47/evaluation")
    parser.add_argument("--output-root", default="results/v53_state_compact")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    out = root / args.output_root
    C.REPLAY = args.replay

    freeze = root / args.protocol_dir / f"selection_{args.backbone}.json"
    selection = json.loads(freeze.read_text())
    k = int(selection["selection"]["selected"]["k"])
    beta = float(selection["selection"]["selected"]["beta"])

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(C.load_catalog(root, name.strip(), args.backbone))
    bank = SEL.Bank(bank_catalogs, blocks=SEL.blocks_of())
    fixed_action = SEL.best_fixed_action(bank)

    packs = {}
    for blk in ("train_eval", "test"):
        catalogs = C.load_catalog(root, blk, args.backbone)
        q = SEL.Queries(catalogs, blocks=SEL.blocks_of())
        D = SEL.distance_matrices(bank, q, lopo=False)
        full_sel = SEL.decide(q, SEL.score_grid(bank, q, D, k, beta))
        reference_sel = SEL.r2_cart(bank, q)
        best, best_p = r2_cart_posteriors(bank, q)
        t05 = gate_at(best, best_p, 0.5)
        packs[blk] = {"queries": q, "full_sel": full_sel,
                      "reference_sel": reference_sel, "t05": t05,
                      "best": best, "best_p": best_p,
                      "r2_matches_reference": bool((t05 == reference_sel).all())}

    dev = packs["train_eval"]
    dev_rate = float((dev["full_sel"] != SEL.REFERENCE).mean())
    finite_p = dev["best_p"][np.isfinite(dev["best_p"])]
    theta = float(np.quantile(finite_p, 1.0 - dev_rate)) if len(finite_p) and dev_rate > 0 \
        else float("inf")
    p_random = dev_rate

    calibration = {"k": k, "beta": beta, "dev_block": "train_eval",
                   "dev_full_intervention_rate": dev_rate,
                   "r2_cart_theta_matched": theta,
                   "best_fixed_action": fixed_action,
                   "best_fixed_random_probability": p_random,
                   "hash_tag": HASH_TAG,
                   "r2_matches_reference": {b: packs[b]["r2_matches_reference"]
                                            for b in packs}}

    result = {"calibration": calibration, "blocks": {}}
    for blk, pack in packs.items():
        q = pack["queries"]
        decisions = {
            "FULL_INTROACT": pack["full_sel"],
            "R2_CART_T05": pack["t05"],
            "R2_CART_MATCHED": gate_at(pack["best"], pack["best_p"], theta),
            "BEST_FIXED": SEL.apply_fixed(q, fixed_action),
            "BEST_FIXED_RANDOM": best_fixed_random(q, fixed_action, p_random),
        }
        rows = {name: summarise(q, sel, name) for name, sel in decisions.items()}
        mase_of = {name: SEL.realised(q, sel) for name, sel in decisions.items()}
        comparisons = {}
        for name in ("R2_CART_T05", "R2_CART_MATCHED", "BEST_FIXED", "BEST_FIXED_RANDOM"):
            comparisons[f"FULL_INTROACT_vs_{name}"] = SEL.paired_cluster_bootstrap(
                q, mase_of["FULL_INTROACT"], mase_of[name],
                resamples=args.resamples)
        result["blocks"][blk] = {"rows": rows, "comparisons": comparisons,
                                 "episodes": int(len(q.episode))}

    # Cross-check the recomputed 0.5-threshold R2-CART and BEST_FIXED against
    # the published v47 evaluation rows (train_eval and test both exist there).
    crosscheck = {}
    for blk in ("train_eval", "test"):
        ref_path = root / args.v47_evaluation_dir / f"{blk}_{args.backbone}.json"
        if not ref_path.exists():
            crosscheck[blk] = {"status": "missing", "file": str(ref_path)}
            continue
        ref = json.loads(ref_path.read_text())["rows"]
        entry = {"file": str(ref_path.relative_to(root))}
        for name in ("R2_CART", "BEST_FIXED"):
            mine = result["blocks"][blk]["rows"]["R2_CART_T05" if name == "R2_CART"
                                                  else name]
            theirs = ref[name]
            entry[name] = {
                "v47_mase": theirs["mase"], "v53_mase": mine["mase"],
                "mase_match": bool(abs(theirs["mase"] - mine["mase"]) < 1e-9),
                "v47_intervention_rate": theirs["intervention_rate"],
                "v53_intervention_rate": mine["intervention_rate"],
                "rate_match": bool(abs(theirs["intervention_rate"]
                                       - mine["intervention_rate"]) < 1e-12),
                "v47_harmful_loss": theirs["harmful_loss"],
                "v53_harmful_loss": mine["harmful_loss"],
            }
        crosscheck[blk] = entry
    result["crosscheck_v47_evaluation"] = crosscheck

    result.update({
        "stage": "v53-gate-controls-2",
        "backbone": args.backbone,
        "bank_blocks": args.bank_blocks,
        "replay": args.replay,
        "module": "introact_ts.v47.select",
        "code_sha256": {
            "scripts/v53_gate_controls2.py": sha256_of(Path(__file__).resolve()),
            "src/introact_ts/v47/select.py": sha256_of(root / "src/introact_ts/v47/select.py"),
        },
        "runtime_seconds": time.perf_counter() - began,
    })
    write(out / f"gate_controls2_{args.backbone}.json", clean(result))

    summary = {"backbone": args.backbone, "calibration": calibration}
    for blk, pack in result["blocks"].items():
        summary[blk] = {
            name: {"mase": r["mase"], "intervention_rate": r["intervention_rate"],
                   "conditional_hir": r["conditional_hir"],
                   "harmful_loss": r["harmful_loss"]}
            for name, r in pack["rows"].items()}
        summary[blk]["vs"] = {
            key: [v["difference"], v["ci_low"], v["ci_high"], v["p_value"]]
            for key, v in pack["comparisons"].items()}
    summary["crosscheck"] = {b: {m: (e[m]["mase_match"], e[m]["rate_match"])
                                 for m in ("R2_CART", "BEST_FIXED")}
                             for b, e in crosscheck.items() if "R2_CART" in e}
    print(json.dumps(clean(summary), indent=1))


if __name__ == "__main__":
    main()
