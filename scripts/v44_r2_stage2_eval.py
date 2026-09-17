#!/usr/bin/env python3
"""v4.4-r2 stage 2 -- TRAIN-Eval admission for the expected-regret ensemble.

Reads the frozen stage-2 selection, deploys it on TRAIN-Eval **once**, and
re-evaluates the same R1-R6 ladder, adding the stage-1 candidate as a control so
the enhancement is judged against what it replaced.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from introact_ts.v44 import protocol as P
from introact_ts.v44 import statistics as ST
from introact_ts.v44_r2 import evaluate as EV
from introact_ts.v44_r2 import regret as RG
from introact_ts.v44_r2.dataset import load_block, summarise

ROOT = Path(__file__).resolve().parent.parent
STAGE2 = ROOT / "results/v44_r2/gate/stage2_sweep.json"
STAGE1 = ROOT / "results/v44_r2/gate/gate_sweep.json"
STAGE1_EVAL = ROOT / "results/v44_r2/evaluation/train_eval.json"
V44_EVAL = ROOT / "results/v44/evaluation/train_eval.json"
OUT = ROOT / "results/v44_r2/evaluation/stage2_eval.json"

CANDIDATE = "R2_DECISION_REGRET_ENSEMBLE"
STAGE1_METHOD = "R2_DECISION_REGRET"

CONTROLS = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", STAGE1_METHOD)
V44_REFERENCES = ("FULL_INTROACT", "A4_WO_GATE",
                  "A5_PARAMETRIC_RIDGE", "A5_PARAMETRIC_CART")
PARAMETRIC = ("A5_PARAMETRIC_RIDGE", "A5_PARAMETRIC_CART")

#: Same rank field as the v4.4 report (every method except the oracle), so the
#: r2 rank and the v4.4 rank are the same statistic.
RANKED = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FULL_INTROACT",
          "A1_GLOBAL_REPLAY", "A2_WO_INTERVENTION", "A3_WO_FORECAST",
          "A4_WO_GATE", "A5_PARAMETRIC_RIDGE", "A5_PARAMETRIC_CART",
          STAGE1_METHOD, CANDIDATE)


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--stage2", default=str(STAGE2))
    parser.add_argument("--stage1", default=str(STAGE1))
    parser.add_argument("--stage1-eval", default=str(STAGE1_EVAL))
    parser.add_argument("--v44-eval", default=str(V44_EVAL))
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()
    root = Path(args.root)
    began = time.perf_counter()

    selection = json.loads(Path(args.stage2).read_text())
    lambdas = tuple(selection["selected"]["lambdas"])
    tau = float(selection["selected"]["tau"])
    frozen = json.loads(Path(args.stage1).read_text())["selected"]
    thresholds = selection["opportunity_thresholds"]

    v44_records = EV.load_v44_reference(args.v44_eval)
    stage1_records = [r for r in EV.load_v44_reference(args.stage1_eval)
                      if r["method"] == STAGE1_METHOD]

    from introact_ts.v44.splits import assign_splits
    from introact_ts.v44.registry import train_parents
    assignment = assign_splits(train_parents(root))

    records: list[dict] = []
    per_backbone: dict[str, dict] = {}
    for backbone in P.DEV_BACKBONES:
        fit = load_block(root, "replay_fit", backbone)
        block = load_block(root, "train_eval", backbone)
        ranker, ridge, tree = RG.fit_all(fit, frozen=frozen)
        prepared, probabilities, legals = RG.prepare(block, ranker, ridge, tree)
        decisions = RG.decisions_for(block, prepared, probabilities, legals,
                                     lambdas=lambdas, tau=tau)
        block_records = EV.decision_records(block, decisions, backbone=backbone,
                                            method=CANDIDATE,
                                            thresholds=thresholds)
        records.extend(block_records)
        per_backbone[backbone] = {
            "episodes": len(block),
            "macro_mase": EV.macro_mase(block_records, CANDIDATE, backbone),
            "macro_cells": EV.macro_cells(block_records, CANDIDATE, backbone),
            "governance": EV.governance(block_records).get(CANDIDATE, {}),
            "keep_rate": EV.keep_rate(block_records, CANDIDATE),
            "high_opportunity_capture": EV.high_opportunity_capture(
                block_records, CANDIDATE),
            "opportunity_bands": EV.band_table(block_records, CANDIDATE),
            "dataset": summarise(block),
            "ridge_notes": ridge.notes(),
            "tree_notes": tree.notes(),
            "pair_summary": ranker.pair_summary,
            "boundary_audit": EV.boundary_audit(block_records, block, assignment,
                                                method=CANDIDATE,
                                                backbone=backbone),
        }

    combined = records + stage1_records + v44_records
    ranks = ST.average_rank(combined, methods=list(RANKED))
    wins = {b: ST.cell_win_counts([r for r in combined if r["backbone"] == b],
                                  method=CANDIDATE, baseline="NATIVE_KEEP")
            for b in P.DEV_BACKBONES}

    comparisons = {}
    for backbone in P.DEV_BACKBONES:
        comparisons[backbone] = {
            name: EV.paired(combined, backbone, CANDIDATE, name)
            for name in CONTROLS + V44_REFERENCES}

    verdicts = {}
    for backbone in P.DEV_BACKBONES:
        data = per_backbone[backbone]
        own = data["macro_mase"]
        reference = {name: EV.macro_mase(v44_records, name, backbone)
                     for name in V44_REFERENCES}
        stage1_macro = EV.macro_mase(stage1_records, STAGE1_METHOD, backbone)
        best_parametric = min(reference["A5_PARAMETRIC_RIDGE"],
                              reference["A5_PARAMETRIC_CART"])
        verdicts[backbone] = {
            "candidate_macro_mase": own,
            "stage1_macro_mase": stage1_macro,
            "v44_reference": reference,
            "R1_beats_full_introact": bool(
                own is not None and reference["FULL_INTROACT"] is not None
                and own < reference["FULL_INTROACT"]),
            "R2_reaches_current_best_selector": bool(
                own is not None and own <= best_parametric),
            "R2_margin_vs_best_parametric": (
                None if own is None else own - best_parametric),
            "R3_not_worse_than_no_gate": bool(
                own is not None and reference["A4_WO_GATE"] is not None
                and own <= reference["A4_WO_GATE"]),
            "R3_significant_vs_no_gate": comparisons[backbone]["A4_WO_GATE"],
            "R5_keep_rate": data["keep_rate"],
            "R5_non_degenerate": bool(0.0 < data["keep_rate"] < 1.0),
            "R6_boundary_ok": bool(
                data["boundary_audit"]["block_boundary_ok"]
                and data["boundary_audit"]["records_match_episodes"]
                and data["boundary_audit"]["headline_equals_cell_mean"]),
        }
    verdicts["_global"] = {
        "R1_both_backbones": all(verdicts[b]["R1_beats_full_introact"]
                                 for b in P.DEV_BACKBONES),
        "R2_both_backbones": all(
            verdicts[b]["R2_reaches_current_best_selector"]
            for b in P.DEV_BACKBONES),
        "R3_both_backbones": all(verdicts[b]["R3_not_worse_than_no_gate"]
                                 for b in P.DEV_BACKBONES),
        "R4_average_rank": {m: ranks.get(m) for m in RANKED},
        "R4_better_than_parametric": all(
            ranks.get(CANDIDATE) is not None
            and ranks.get(CANDIDATE) < ranks.get(name)
            for name in PARAMETRIC),
        "R5_both_backbones": all(verdicts[b]["R5_non_degenerate"]
                                 for b in P.DEV_BACKBONES),
        "R6_both_backbones": all(verdicts[b]["R6_boundary_ok"]
                                 for b in P.DEV_BACKBONES),
        "all_six": False,
    }
    verdicts["_global"]["all_six"] = all([
        verdicts["_global"]["R1_both_backbones"],
        verdicts["_global"]["R2_both_backbones"],
        verdicts["_global"]["R3_both_backbones"],
        verdicts["_global"]["R4_better_than_parametric"],
        verdicts["_global"]["R5_both_backbones"],
        verdicts["_global"]["R6_both_backbones"],
    ])

    payload = {
        "stage": "v44-r2-stage2-train-eval-admission",
        "frozen": selection["selected"],
        "inherits_stage1": frozen,
        "objective": "paired cluster bootstrap of source-macro MASE, parent as unit",
        "bootstrap": {"resamples": P.BOOTSTRAP_RESAMPLES, "seed": P.BOOTSTRAP_SEED,
                      "level": P.CI_LEVEL},
        "opportunity_thresholds": thresholds,
        "per_backbone": per_backbone,
        "average_rank": ranks,
        "cell_wins_vs_keep": wins,
        "comparisons": comparisons,
        "verdicts": verdicts,
        "records": records,
        "runtime_seconds": time.perf_counter() - began,
        "heldout_labels_read": 0,
        "calibration_test_touched": False,
    }
    write(Path(args.output), payload)
    print(json.dumps({
        "frozen": payload["frozen"],
        "candidate_macro_mase": {b: per_backbone[b]["macro_mase"]
                                 for b in P.DEV_BACKBONES},
        "stage1_macro_mase": {b: verdicts[b]["stage1_macro_mase"]
                              for b in P.DEV_BACKBONES},
        "keep_rate": {b: per_backbone[b]["keep_rate"] for b in P.DEV_BACKBONES},
        "high_opportunity_capture": {
            b: per_backbone[b]["high_opportunity_capture"]
            for b in P.DEV_BACKBONES},
        "average_rank": ranks,
        "verdicts": verdicts["_global"],
        "runtime_seconds": payload["runtime_seconds"],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
