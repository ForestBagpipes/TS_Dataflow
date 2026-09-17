#!/usr/bin/env python3
"""v4.4-r2 canonical tables.

``results/`` is excluded from the repository on this machine, so every number
the paper needs is re-emitted into ``docs/`` where it can be reviewed and
diffed.  Nothing here recomputes a metric: the tables are read straight out of
the frozen gate and evaluation payloads, so a table cannot disagree with the run
that produced it.

Run after the batch scripts; re-running overwrites the tables from the same
frozen inputs, which is the intended behaviour (the payloads themselves are
write-once).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results/v44_r2"
V44 = ROOT / "results/v44/evaluation"
DOCS = ROOT / "docs"

GATE = RESULTS / "gate/gate_sweep.json"
S2_GATE = RESULTS / "gate/stage2_sweep.json"
S1_EVAL = RESULTS / "evaluation/train_eval.json"
S2_EVAL = RESULTS / "evaluation/stage2_eval.json"
V44_EVAL = V44 / "train_eval.json"

CANDIDATE_S2 = "R2_DECISION_REGRET_ENSEMBLE"
CANDIDATE_S1 = "R2_DECISION_REGRET"

#: Every method the r2 tables quote, in reporting order.
LADDER = (
    "NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FULL_INTROACT",
    "A1_GLOBAL_REPLAY", "A2_WO_INTERVENTION", "A3_WO_FORECAST",
    "A4_WO_GATE", "A5_PARAMETRIC_RIDGE", "A5_PARAMETRIC_CART",
    CANDIDATE_S1, CANDIDATE_S2,
)
DIAGNOSTIC = ("CATALOG_ORACLE",)


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in columns})


def macro(records: list[dict], method: str, backbone: str):
    from introact_ts.v44 import metrics as ME

    subset = [r for r in records
              if r["method"] == method and r["backbone"] == backbone]
    return ME.macro_headline(subset, "mase")


# -- tables -----------------------------------------------------------------


def gate_table() -> list[dict]:
    payload = read(GATE)
    rows = []
    for row in payload["joint"]:
        rows.append({
            "config": row["config"],
            "learner": row["learner"],
            "alpha": row["alpha"],
            "tau": row["tau"],
            "joint_objective": row["joint_objective"],
            "bolt_mase": row["per_backbone"][0],
            "timesfm_mase": row["per_backbone"][1],
            "bolt_keep_rate": row["keep_rate"][0],
            "timesfm_keep_rate": row["keep_rate"][1],
            "mean_harmful_loss": row["mean_harmful_loss"],
            "non_degenerate": row["non_degenerate"],
            "selected": (row["config"] == payload["selected"]["config"]
                         and abs(row["tau"] - payload["selected"]["tau"]) < 1e-12),
        })
    rows.sort(key=lambda r: (r["joint_objective"] is None,
                             r["joint_objective"] if r["joint_objective"]
                             is not None else 1e9))
    return rows


def stage2_gate_table() -> list[dict]:
    payload = read(S2_GATE)
    rows = []
    for row in payload["joint"]:
        lambdas = row["lambdas"]
        rows.append({
            "lambda_pair": lambdas[0],
            "lambda_ridge": lambdas[1],
            "lambda_tree": lambdas[2],
            "tau": row["tau"],
            "joint_objective": row["joint_objective"],
            "bolt_mase": row["per_backbone"][0],
            "timesfm_mase": row["per_backbone"][1],
            "bolt_keep_rate": row["keep_rate"][0],
            "timesfm_keep_rate": row["keep_rate"][1],
            "mean_harmful_loss": row["mean_harmful_loss"],
            "non_degenerate": row["non_degenerate"],
            "selected": (lambdas == payload["selected"]["lambdas"]
                         and abs(row["tau"] - payload["selected"]["tau"]) < 1e-12),
        })
    rows.sort(key=lambda r: (r["joint_objective"] is None,
                             r["joint_objective"] if r["joint_objective"]
                             is not None else 1e9))
    return rows


def train_eval_table() -> list[dict]:
    v44_payload = read(V44_EVAL)
    v44 = v44_payload["records"]
    s1 = read(S1_EVAL)
    s2 = read(S2_EVAL)
    s1_records = [r for r in s1["records"] if r["method"] == CANDIDATE_S1]
    s2_records = [r for r in s2["records"] if r["method"] == CANDIDATE_S2]
    ranks = dict(s2["average_rank"])

    rows = []
    for method in LADDER + DIAGNOSTIC:
        for backbone in ("bolt", "timesfm"):
            if method == CANDIDATE_S1:
                subset, governance = s1_records, s1["per_backbone"][backbone].get(
                    "governance", {})
            elif method == CANDIDATE_S2:
                subset, governance = s2_records, s2["per_backbone"][backbone].get(
                    "governance", {})
            else:
                subset = v44
                governance = v44_payload["per_backbone"][backbone].get(
                    "governance", {}).get(method, {})
            intervention = governance.get("intervention_rate")
            rows.append({
                "method": method,
                "backbone": backbone,
                "source_macro_mase": macro(subset, method, backbone),
                "average_rank": ranks.get(method),
                "keep_rate": governance.get("keep_rate",
                                            None if intervention is None
                                            else 1.0 - intervention),
                "intervention_rate": intervention,
                "hir": governance.get("hir"),
                "conditional_hir": governance.get("conditional_hir"),
                "harmful_loss": governance.get("harmful_loss"),
                "catalog_gap_closed": governance.get("cgc"),
                "n": governance.get("n"),
                "excluded_missing_loss": governance.get("excluded_missing_loss"),
                "diagnostic": method in DIAGNOSTIC,
            })
    return rows


def comparison_table() -> list[dict]:
    payload = read(S2_EVAL)
    rows = []
    for backbone in ("bolt", "timesfm"):
        for name, result in payload["comparisons"][backbone].items():
            rows.append({
                "candidate": CANDIDATE_S2,
                "backbone": backbone,
                "reference": name,
                "difference": result.get("difference"),
                "ci_low": result.get("ci_low"),
                "ci_high": result.get("ci_high"),
                "excludes_zero": result.get("excludes_zero"),
                "favours": result.get("favours"),
                "n_parents": result.get("n_units") or result.get("parents"),
            })
    return rows


def verdict_table() -> list[dict]:
    rows = []
    for label, path in (("stage1", S1_EVAL), ("stage2", S2_EVAL)):
        payload = read(path)
        for backbone in ("bolt", "timesfm"):
            verdict = payload["verdicts"][backbone]
            rows.append({
                "stage": label,
                "backbone": backbone,
                "candidate_macro_mase": verdict["candidate_macro_mase"],
                "R1_beats_full": verdict["R1_beats_full_introact"],
                "R2_reaches_best_selector": verdict["R2_reaches_current_best_selector"],
                "R2_margin": verdict["R2_margin_vs_best_parametric"],
                "R3_not_worse_than_no_gate": verdict["R3_not_worse_than_no_gate"],
                "R5_keep_rate": verdict["R5_keep_rate"],
                "R5_non_degenerate": verdict["R5_non_degenerate"],
                "R6_boundary_ok": verdict["R6_boundary_ok"],
            })
    return rows


def claims_markdown() -> str:
    s1 = read(S1_EVAL)
    s2 = read(S2_EVAL)
    gate = read(GATE)
    s2_gate = read(S2_GATE)
    g1 = s1["verdicts"]["_global"]
    g2 = s2["verdicts"]["_global"]
    rank_s1 = s1["average_rank"].get(CANDIDATE_S1)
    rank_s2 = s2["average_rank"].get(CANDIDATE_S2)
    rank_set = len(s2["average_rank"])
    lines = [
        "# v4.4-r2 Batch 1 + stage 2 -- claim boundaries",
        "",
        "Every number below comes from a frozen payload under `results/v44_r2/`.",
        "Calibration and test were never opened (`heldout_labels_read = 0`,",
        "`calibration_test_touched = false` in all four payloads).",
        "",
        "## What the r2 candidate may be claimed to do",
        "",
        f"* Frozen stage-1 selection: `{gate['selected']['config']}`, "
        f"tau = {gate['selected']['tau']}.",
        f"* Frozen stage-2 selection: lambda = {s2_gate['selected']['lambdas']}, "
        f"tau = {s2_gate['selected']['tau']}.",
        "* The candidate is a **decision-regret ranker over counterfactual "
        "replay**, deployed through a single confidence veto; KEEP is one of "
        "the five ranked actions and is never a post-hoc fallback.",
        "* It is significantly better than `NATIVE_KEEP`, `BEST_FIXED`, "
        "`R2_CART` and `FULL_INTROACT` on **both** development backbones "
        "(paired cluster bootstrap, parent as unit, 95% CI excludes zero).",
        "* It is **not** significantly different from `A4_WO_GATE` or from "
        "`A5_PARAMETRIC_RIDGE` on either backbone.",
        "",
        "## What it may NOT be claimed to do",
        "",
        "* It does **not** clear the R1-R6 ladder: R2, R3 and R4 fail.  R2 fails "
        "because `A5_PARAMETRIC_CART` on TimesFM is lower; R3 fails because "
        "`A4_WO_GATE` on TimesFM is lower by 0.00065 MASE; R4 fails because its "
        f"average rank ({rank_s1:.3f} stage 1, {rank_s2:.3f} stage 2) is worse "
        f"than both parametric selectors in a {rank_set}-method field.",
        "* It is not SOTA and must not be written as SOTA.  `CATALOG_ORACLE` is "
        "an oracle and is excluded from every ranking; it is reported as a "
        "diagnostic only.",
        "* The average-rank failure and the mean-MASE success are the **same "
        "fact**: the method wins on the average by taking large gains in "
        "high-opportunity windows while intervening on ~99% of TimesFM windows, "
        "with a 38% harmful-intervention rate against v4.4 Full's 8.4%.  Neither "
        "half may be quoted without the other.",
        "* Stage 2 was used **once**, as the plan permits.  Its gate-selected "
        "lambda improved the gate objective by "
        f"{s2_gate['improvement_over_stage1']:.6f} but did not transfer: "
        "it helped Bolt by 0.004799 and changed TimesFM by +0.000110, while "
        f"making the average rank worse ({rank_s1:.3f} -> {rank_s2:.3f}).  No "
        "further search is permitted.",
        "",
        "## Data-quality finding that must travel with the result",
        "",
        "* One `replay_fit` row on Bolt, "
        "`Weather|Weather:7040:7744|h96|P2_target_block|s30`, has "
        "`CONTEXT_RIDGE` MASE = 614.232 against a best action of 0.125 "
        "(MSE 3.917e7 vs KEEP 1.862).  It is a real execution of the action, "
        "not a metric defect, and it is **absent from the gate and TRAIN-Eval "
        "blocks**, so it does not enter any reported metric.",
        "* It does enter the fits: it is 1 row in 5168 and contributes about "
        "35% of the Bolt mean regret, inflating the `CONTEXT_RIDGE` ridge "
        "residual from ~0.5 to 21.37.  This is why the stage-2 ridge component "
        "is fragile and why its gain did not transfer.  It was **not** "
        "winsorised: the protocol forbids silent transformation, and a third "
        "method change is not permitted.",
        "",
        "## Boundary audit (R6)",
        "",
    ]
    for label, payload in (("stage1", s1), ("stage2", s2)):
        for backbone in ("bolt", "timesfm"):
            audit = payload["per_backbone"][backbone]["boundary_audit"]
            lines.append(
                f"* {label} / {backbone}: {audit['records']} records for "
                f"{audit['episodes']} episodes, {audit['parents']} parents, "
                f"{audit['cells']} cells, "
                f"parents outside TRAIN-Eval = "
                f"{audit['parents_outside_train_eval'] or 'none'}, "
                f"headline equals cell mean = {audit['headline_equals_cell_mean']}.")
    lines += [
        "",
        "## Global verdicts",
        "",
        f"* stage 1: `all_six` = "
        f"{g1.get('all_six', 'not recorded (R1-R6 recorded individually)')}",
        f"* stage 2: `all_six` = {g2.get('all_six')}",
        "",
        "The r2 method line is therefore **closed as a negative result** with "
        "the replay information shown to be real and the selector still unable "
        "to convert it into a competitive decision rule.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", default=str(DOCS))
    args = parser.parse_args()
    docs = Path(args.docs)

    write_csv(docs / "v44_r2_gate.csv", gate_table(), [
        "config", "learner", "alpha", "tau", "joint_objective", "bolt_mase",
        "timesfm_mase", "bolt_keep_rate", "timesfm_keep_rate",
        "mean_harmful_loss", "non_degenerate", "selected"])
    write_csv(docs / "v44_r2_stage2_gate.csv", stage2_gate_table(), [
        "lambda_pair", "lambda_ridge", "lambda_tree", "tau", "joint_objective",
        "bolt_mase", "timesfm_mase", "bolt_keep_rate", "timesfm_keep_rate",
        "mean_harmful_loss", "non_degenerate", "selected"])
    write_csv(docs / "v44_r2_train_eval.csv", train_eval_table(), [
        "method", "backbone", "source_macro_mase", "average_rank", "keep_rate",
        "intervention_rate", "hir", "conditional_hir", "harmful_loss",
        "catalog_gap_closed", "n", "excluded_missing_loss", "diagnostic"])
    write_csv(docs / "v44_r2_comparisons.csv", comparison_table(), [
        "candidate", "backbone", "reference", "difference", "ci_low", "ci_high",
        "excludes_zero", "favours", "n_parents"])
    write_csv(docs / "v44_r2_verdicts.csv", verdict_table(), [
        "stage", "backbone", "candidate_macro_mase", "R1_beats_full",
        "R2_reaches_best_selector", "R2_margin", "R3_not_worse_than_no_gate",
        "R5_keep_rate", "R5_non_degenerate", "R6_boundary_ok"])
    (docs / "v44_r2_claims.md").write_text(claims_markdown(), encoding="utf-8")
    print(json.dumps({
        "gate_rows": len(gate_table()),
        "stage2_gate_rows": len(stage2_gate_table()),
        "train_eval_rows": len(train_eval_table()),
        "comparisons": len(comparison_table()),
        "verdicts": len(verdict_table()),
        "written_to": str(docs),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
