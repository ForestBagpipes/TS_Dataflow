#!/usr/bin/env python3
"""v4.4-r2 Batch 1 -- the TRAIN-Eval admission (criteria R1-R6).

The gate already froze one shared ``model config x tau``.  This script fits that
configuration on Replay-Fit, deploys it on TRAIN-Eval **once**, and evaluates
the six admission criteria against the frozen v4.4 ladder.

Nothing here may be re-run with a different configuration: the selection lives
in ``results/v44_r2/gate/gate_sweep.json`` and is only read.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import protocol as P
from introact_ts.v44 import statistics as ST
from introact_ts.v44_r2 import evaluate as EV
from introact_ts.v44_r2 import ranking as RK
from introact_ts.v44_r2.dataset import load_block, summarise

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "results/v44_r2/gate/gate_sweep.json"
V44_EVAL = ROOT / "results/v44/evaluation/train_eval.json"
OUT = ROOT / "results/v44_r2/evaluation"

CANDIDATE = "R2_DECISION_REGRET"

#: The v4.4 methods this candidate is admitted against.
CONTROLS = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART")
V44_REFERENCES = ("FULL_INTROACT", "A4_WO_GATE",
                  "A5_PARAMETRIC_RIDGE", "A5_PARAMETRIC_CART")
PARAMETRIC = ("A5_PARAMETRIC_RIDGE", "A5_PARAMETRIC_CART")

#: The average-rank field is the same one the v4.4 report used: every method
#: except the oracle diagnostic.  Dropping the three ablation variants here
#: would make the r2 rank incomparable with the v4.4 rank, which is the only
#: thing R4 is a statement about.
RANKED = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FULL_INTROACT",
          "A1_GLOBAL_REPLAY", "A2_WO_INTERVENTION", "A3_WO_FORECAST",
          "A4_WO_GATE", "A5_PARAMETRIC_RIDGE", "A5_PARAMETRIC_CART",
          CANDIDATE)


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--gate", default=str(GATE))
    parser.add_argument("--v44-eval", default=str(V44_EVAL))
    parser.add_argument("--output", default=str(OUT / "train_eval.json"))
    args = parser.parse_args()
    root = Path(args.root)
    began = time.perf_counter()

    selection = json.loads(Path(args.gate).read_text())
    frozen = selection["selected"]
    thresholds = selection["opportunity_thresholds"]

    v44_records = EV.load_v44_reference(args.v44_eval)
    from introact_ts.v44.splits import assign_splits
    from introact_ts.v44.registry import train_parents
    assignment = assign_splits(train_parents(root))

    records: list[dict] = []
    per_backbone: dict[str, dict] = {}
    for backbone in P.DEV_BACKBONES:
        fit = load_block(root, "replay_fit", backbone)
        block = load_block(root, "train_eval", backbone)
        ranker = RK.PairwiseRanker(learner=frozen["learner"],
                                   alpha=frozen["alpha"]).fit(fit)
        decisions = RK.apply_ranker(ranker, block, tau=frozen["tau"])
        block_records = EV.decision_records(block, decisions, backbone=backbone,
                                            method=CANDIDATE,
                                            thresholds=thresholds)
        records.extend(block_records)
        governance = EV.governance(block_records)
        per_backbone[backbone] = {
            "episodes": len(block),
            "macro_mase": EV.macro_mase(block_records, CANDIDATE, backbone),
            "macro_cells": EV.macro_cells(block_records, CANDIDATE, backbone),
            "governance": governance.get(CANDIDATE, {}),
            "keep_rate": EV.keep_rate(block_records, CANDIDATE),
            "high_opportunity_capture": EV.high_opportunity_capture(
                block_records, CANDIDATE),
            "opportunity_bands": EV.band_table(block_records, CANDIDATE),
            "dataset": summarise(block),
            "pair_summary": ranker.pair_summary,
            "ranker_notes": ranker.notes,
            "boundary_audit": EV.boundary_audit(block_records, block, assignment,
                                                method=CANDIDATE,
                                                backbone=backbone),
        }

    combined = records + v44_records
    ranks = ST.average_rank(combined, methods=[m for m in RANKED])
    wins = {b: ST.cell_win_counts([r for r in combined if r["backbone"] == b],
                                  method=CANDIDATE, baseline="NATIVE_KEEP")
            for b in P.DEV_BACKBONES}

    comparisons = {}
    for backbone in P.DEV_BACKBONES:
        comparisons[backbone] = {
            name: EV.paired(combined, backbone, CANDIDATE, name)
            for name in CONTROLS + V44_REFERENCES}

    # -- R1-R6 ------------------------------------------------------------
    verdicts = {}
    for backbone in P.DEV_BACKBONES:
        data = per_backbone[backbone]
        own = data["macro_mase"]
        reference = {name: EV.macro_mase(v44_records, name, backbone)
                     for name in V44_REFERENCES}
        verdicts[backbone] = {
            "candidate_macro_mase": own,
            "v44_reference": reference,
            "R1_beats_full_introact": bool(
                own is not None and reference["FULL_INTROACT"] is not None
                and own < reference["FULL_INTROACT"]),
            "R2_reaches_current_best_selector": bool(
                own is not None and reference["A5_PARAMETRIC_RIDGE"] is not None
                and reference["A5_PARAMETRIC_CART"] is not None
                and own <= min(reference["A5_PARAMETRIC_RIDGE"],
                               reference["A5_PARAMETRIC_CART"])),
            "R2_margin_vs_best_parametric": (
                None if own is None else
                own - min(reference["A5_PARAMETRIC_RIDGE"],
                          reference["A5_PARAMETRIC_CART"])),
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
    }

    payload = {
        "stage": "v44-r2-train-eval-admission",
        "frozen": frozen,
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
        "frozen": frozen,
        "candidate_macro_mase": {b: per_backbone[b]["macro_mase"]
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
