#!/usr/bin/env python3
"""v55 gate controls: decision quality against intervention frequency.

The action scorer of the full method stays fixed at the v55 frozen
``(k, beta, lam)`` and only the act or keep gating changes, so a control that
acts as often as the full method while deciding differently isolates the gate.
GATE_DISPERSION is the full method, GATE_MEAN_ONLY drops the dispersion penalty
and recovers its coverage with a matched threshold, GATE_LINEAR replaces the
estimator with a ridge fit on the same labels, and GATE_RANDOM keeps the full
method's recommendation and randomises only whether it runs.  Thresholds are
matched on the internal evaluation block and applied unchanged elsewhere.
Writes only under ``results/v55/gate_controls/``.
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
from introact_ts.v55 import select as V55

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v47_evaluate import missed_opportunity, summarise
from v52_gate_controls import (best_action_scores, gate_from_score,
                               match_threshold, ridge_scores)
from v54_common import (BACKBONES, EVAL_BLOCKS, OUT, ROOT, clean, code_hashes,
                        load_catalogs, sha, write)

GATE_OUT = ROOT / "results/v55" / "gate_controls"
V55_PROTOCOL = ROOT / "results/v55" / "protocol"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--bank-blocks", default="bankx")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    freeze = V55_PROTOCOL / f"selection_{args.backbone}.json"
    if not freeze.exists():
        raise SystemExit(f"v55 configuration is not frozen for {args.backbone}: "
                         f"{freeze} missing; run scripts/v55_select.py first")
    selection = json.loads(freeze.read_text())
    config = V55.frozen_config(selection)
    if config is None:
        raise SystemExit(f"selection for {args.backbone} is KEEP-only; the gate "
                         "controls have no dispersion scorer to calibrate against")
    k, beta, lam = config
    means = None

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(load_catalogs(root, name.strip(), args.backbone))
    bank = SEL.Bank(bank_catalogs, blocks=SEL.blocks_of())

    blocks = {}
    for blk in EVAL_BLOCKS:
        catalogs = load_catalogs(root, blk, args.backbone)
        q = SEL.Queries(catalogs, blocks=SEL.blocks_of())
        D = SEL.distance_matrices(bank, q, lopo=False)
        if means is None:
            means = V55.source_action_means(bank)
        moments = V55.local_moments(bank, q, D, k)
        full_scores = V55.scores_from_moments(moments, means, q, beta, lam)
        mean_scores = V55.scores_from_moments(moments, means, q, 0.0, lam)
        lin_scores = ridge_scores(bank, q)
        best_full, best_full_score = best_action_scores(full_scores, q)
        best_mean, best_mean_score = best_action_scores(mean_scores, q)
        best_lin, best_lin_score = best_action_scores(lin_scores, q)
        blocks[blk] = {"queries": q, "full_scores": full_scores,
                       "best_full": best_full, "best_full_score": best_full_score,
                       "best_mean": best_mean, "best_mean_score": best_mean_score,
                       "best_lin": best_lin, "best_lin_score": best_lin_score}

    dev = blocks["train_eval"]
    dev_full_sel = V55.decide(dev["queries"], dev["full_scores"])
    dev_rate = float((dev_full_sel != SEL.REFERENCE).mean())

    theta_mean = match_threshold(dev["best_mean_score"], dev_rate)
    theta_lin = match_threshold(dev["best_lin_score"], dev_rate)
    dev_candidate = dev["best_full"] != SEL.REFERENCE
    cand_rate = float(dev_candidate.mean())
    p_act = min(1.0, dev_rate / cand_rate) if cand_rate > 0 else 0.0

    calibration = {"k": k, "beta": beta,
                   "lam": (None if lam == float("inf") else lam),
                   "dev_block": "train_eval",
                   "dev_full_intervention_rate": dev_rate,
                   "dev_candidate_rate": cand_rate,
                   "theta_mean": theta_mean, "theta_lin": theta_lin,
                   "random_act_probability": p_act,
                   "random_seed": 101}

    out = {"stage": "v55-gate-controls", "state_version": ST.STATE_VERSION,
           "backbone": args.backbone, "calibration": calibration, "blocks": {}}
    for blk, pack in blocks.items():
        q = pack["queries"]
        decisions = {
            "GATE_DISPERSION": V55.decide(q, pack["full_scores"]),
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
        "scripts/v55_gate_controls.py": sha(Path(__file__).resolve())}
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
