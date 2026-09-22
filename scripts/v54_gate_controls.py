#!/usr/bin/env python3
"""v54 gate controls: decision quality vs intervention frequency, matched coverage.

Same design as ``scripts/v52_gate_controls.py`` (review finding E-003): the
action scorer and candidate generation of the full method stay fixed (v54
frozen k, beta, parent-clustered score grid); only the act/KEEP gating
changes -- GATE_DISPERSION (the full method), GATE_MEAN_ONLY, GATE_LINEAR and
GATE_RANDOM.  Thresholds are matched on the v54 train_eval block so each
control's train_eval coverage equals the full method's train_eval intervention
rate, then applied unchanged to every TEST block; TEST coverage is realised,
not re-matched.

What differs from the v52 run: v54-full22 states, parent-clustered scoring,
the v54 selection files, and all six evaluation blocks.  Writes only under
``results/v54/gate_controls/``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import state as ST
from introact_ts.v47 import select as SEL

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v47_evaluate import missed_opportunity, summarise
from v52_gate_controls import (best_action_scores, gate_from_score,
                               match_threshold, ridge_scores)
from v54_common import (BACKBONES, EVAL_BLOCKS, OUT, ROOT, clean, code_hashes,
                        load_catalogs, sha, write)

GATE_OUT = OUT / "gate_controls"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
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
    if config is None:
        raise SystemExit(f"selection for {args.backbone} is KEEP-only; the gate "
                         "controls have no dispersion scorer to calibrate against")
    k, beta = config

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(load_catalogs(root, name.strip(), args.backbone))
    bank = SEL.Bank(bank_catalogs, blocks=SEL.blocks_of())

    blocks = {}
    for blk in EVAL_BLOCKS:
        catalogs = load_catalogs(root, blk, args.backbone)
        q = SEL.Queries(catalogs, blocks=SEL.blocks_of())
        D = SEL.distance_matrices(bank, q, lopo=False)
        full_scores = SEL.score_grid(bank, q, D, k, beta)
        mean_scores = SEL.score_grid(bank, q, D, k, 0.0)
        lin_scores = ridge_scores(bank, q)
        best_full, best_full_score = best_action_scores(full_scores, q)
        best_mean, best_mean_score = best_action_scores(mean_scores, q)
        best_lin, best_lin_score = best_action_scores(lin_scores, q)
        blocks[blk] = {"queries": q, "full_scores": full_scores,
                       "best_full": best_full, "best_full_score": best_full_score,
                       "best_mean": best_mean, "best_mean_score": best_mean_score,
                       "best_lin": best_lin, "best_lin_score": best_lin_score}

    dev = blocks["train_eval"]
    dev_full_sel = SEL.decide(dev["queries"], dev["full_scores"])
    dev_rate = float((dev_full_sel != SEL.REFERENCE).mean())

    theta_mean = match_threshold(dev["best_mean_score"], dev_rate)
    theta_lin = match_threshold(dev["best_lin_score"], dev_rate)
    dev_candidate = dev["best_full"] != SEL.REFERENCE
    cand_rate = float(dev_candidate.mean())
    p_act = min(1.0, dev_rate / cand_rate) if cand_rate > 0 else 0.0

    calibration = {"k": k, "beta": beta,
                   "dev_block": "train_eval",
                   "dev_full_intervention_rate": dev_rate,
                   "dev_candidate_rate": cand_rate,
                   "theta_mean": theta_mean, "theta_lin": theta_lin,
                   "random_act_probability": p_act,
                   "random_seed": 101}

    out = {"stage": "v54-gate-controls", "state_version": ST.STATE_VERSION,
           "backbone": args.backbone, "calibration": calibration, "blocks": {}}
    for blk, pack in blocks.items():
        q = pack["queries"]
        decisions = {
            "GATE_DISPERSION": SEL.decide(q, pack["full_scores"]),
            "GATE_MEAN_ONLY": gate_from_score(pack["best_mean"],
                                              pack["best_mean_score"], theta_mean),
            "GATE_LINEAR": gate_from_score(pack["best_lin"],
                                           pack["best_lin_score"], theta_lin),
        }
        rng = np.random.default_rng(101)
        random_sel = np.full(len(q.episode), SEL.REFERENCE, dtype=object)
        cand = pack["best_full"] != SEL.REFERENCE
        fire = cand & (rng.random(len(q.episode)) < p_act)
        random_sel[fire] = pack["best_full"][fire]
        decisions["GATE_RANDOM"] = random_sel

        rows = {name: summarise(q, sel, name) for name, sel in decisions.items()}
        for name, sel in decisions.items():
            rows[name]["missed_opportunity"] = missed_opportunity(q, sel, 1e-9)
        mase_of = {name: SEL.realised(q, sel) for name, sel in decisions.items()}
        comparisons = {}
        for name in ("GATE_MEAN_ONLY", "GATE_LINEAR", "GATE_RANDOM"):
            comparisons[f"GATE_DISPERSION_vs_{name}"] = SEL.paired_cluster_bootstrap(
                q, mase_of["GATE_DISPERSION"], mase_of[name],
                resamples=args.resamples)
        out["blocks"][blk] = {"rows": rows, "comparisons": comparisons,
                              "episodes": len(q.episode)}

    out["code_sha256"] = code_hashes(root) | {
        "scripts/v54_gate_controls.py": sha(Path(__file__).resolve())}
    out["runtime_seconds"] = time.perf_counter() - began
    write(GATE_OUT / f"{args.backbone}.json", clean(out))

    summary = {"backbone": args.backbone, "calibration": calibration}
    for blk, pack in out["blocks"].items():
        summary[blk] = {
            name: {"mase": r["mase"], "intervention_rate": r["intervention_rate"],
                   "conditional_hir": r["conditional_hir"]}
            for name, r in pack["rows"].items()}
    print(json.dumps(clean(summary), indent=1))


if __name__ == "__main__":
    main()
