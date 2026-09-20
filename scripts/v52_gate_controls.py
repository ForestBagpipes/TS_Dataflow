#!/usr/bin/env python3
"""v52 gate controls (review finding E-003 / plan E3): decision quality vs
intervention frequency, at matched coverage.

The action scorer and the candidate generation of the full method stay fixed
(frozen k, beta, same score grid).  Only the act/KEEP gating changes:

* ``GATE_DISPERSION``   -- the full method itself (mu - beta*sigma/sqrt(n_eff) > 0).
* ``GATE_MEAN_ONLY``    -- same neighbourhood mean, no uncertainty penalty;
  act when the best mean exceeds a threshold theta.
* ``GATE_LINEAR``       -- per-action ridge utility predictor (the A5 scorer);
  act when the best prediction exceeds a threshold theta_r.
* ``GATE_RANDOM``       -- the full method's recommended action (the always-act
  candidate), kept or dropped by an independent coin, so action selection and
  intervention frequency are separated.

Every threshold / probability is fixed on the TRAIN-eval block so that each
control's TRAIN-eval coverage matches the full method's TRAIN-eval
intervention rate, then applied unchanged to TEST.  TEST coverage is reported
as realised, not re-matched.  Nothing is tuned on TEST.

Outputs go to ``results/v52_ablation/gate_controls/`` and never overwrite v47.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import protocol as P
from introact_ts.v47 import select as SEL

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v52_ablation_action_cond import clean, missed_opportunity, summarise, write

ROOT = Path(__file__).resolve().parent.parent


def best_action_scores(scores: dict[str, np.ndarray],
                       queries: SEL.Queries) -> tuple[np.ndarray, np.ndarray]:
    """Per request: best admissible non-reference action and its score."""
    n = len(queries.episode)
    best = np.full(n, SEL.REFERENCE, dtype=object)
    best_score = np.full(n, -np.inf)
    for action in SEL.NONREF:
        s = np.where(queries.legal[action], scores[action], -np.inf)
        take = s > best_score
        best[take] = action
        best_score[take] = s[take]
    return best, best_score


def ridge_scores(bank: SEL.Bank, queries: SEL.Queries) -> dict[str, np.ndarray]:
    """The A5 scorer as raw predictions (no threshold applied)."""
    from sklearn.linear_model import Ridge

    n = len(queries.episode)
    out = {}
    for a in SEL.NONREF:
        b = bank.per[a]
        s = np.full(n, -np.inf)
        if len(b.g) >= 8:
            model = Ridge(alpha=1.0)
            model.fit(b.Zs, b.g)
            Z = queries.Z[a]
            ok = np.isfinite(Z).all(1)
            if ok.any():
                s[ok] = model.predict(bank.standardise(Z[ok]))
        out[a] = s
    return out


def gate_from_score(best: np.ndarray, best_score: np.ndarray,
                    theta: float) -> np.ndarray:
    sel = np.full(len(best), SEL.REFERENCE, dtype=object)
    take = (best != SEL.REFERENCE) & np.isfinite(best_score) & (best_score > theta)
    sel[take] = best[take]
    return sel


def match_threshold(best_score: np.ndarray, target_rate: float) -> float:
    finite = best_score[np.isfinite(best_score)]
    if not len(finite) or target_rate <= 0:
        return float("inf")
    return float(np.quantile(finite, 1.0 - target_rate))


def evaluate(backbone: str, args) -> dict:
    root = Path(args.root)
    freeze = root / args.protocol_dir / f"selection_{backbone}.json"
    selection = json.loads(freeze.read_text())
    k = int(selection["selection"]["selected"]["k"])
    beta = float(selection["selection"]["selected"]["beta"])

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(C.load_catalog(root, name.strip(), backbone))
    bank = SEL.Bank(bank_catalogs, blocks=SEL.blocks_of())

    blocks = {}
    for blk in ("train_eval", "test"):
        catalogs = C.load_catalog(root, blk, backbone)
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

    out = {"calibration": calibration, "blocks": {}}
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
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--resamples", type=int, default=P.BOOTSTRAP_RESAMPLES)
    parser.add_argument("--bank-blocks", default="bankx")
    parser.add_argument("--replay", default="results/v47/replay")
    parser.add_argument("--protocol-dir", default="results/v47/protocol")
    parser.add_argument("--output-root", default="results/v52_ablation")
    args = parser.parse_args()

    began = time.perf_counter()
    C.REPLAY = args.replay
    result = evaluate(args.backbone, args)
    result["stage"] = "v52-gate-controls"
    result["backbone"] = args.backbone
    result["replay"] = args.replay
    result["runtime_seconds"] = time.perf_counter() - began
    out = Path(args.root) / args.output_root
    write(out / f"gate_controls/{args.backbone}.json", clean(result))

    summary = {"backbone": args.backbone, "calibration": result["calibration"]}
    for blk, pack in result["blocks"].items():
        summary[blk] = {
            name: {"mase": r["mase"], "intervention_rate": r["intervention_rate"],
                   "conditional_hir": r["conditional_hir"],
                   "harmful_loss": r["harmful_loss"]}
            for name, r in pack["rows"].items()}
        summary[blk]["vs"] = {
            key: [v["difference"], v["ci_low"], v["ci_high"], v["excludes_zero"]]
            for key, v in pack["comparisons"].items()}
    print(json.dumps(clean(summary), indent=1))


if __name__ == "__main__":
    main()
