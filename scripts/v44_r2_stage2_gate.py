#!/usr/bin/env python3
"""v4.4-r2 stage 2 -- the expected-regret ensemble gate (plan §12).

Stage 1 did not reach A5, so the plan permits **exactly one** enhancement.  This
is it: keep the frozen stage-1 pairwise model, add two cross-fitted regret
regressors, and search only the simplex triple ``(l1, l2, l3)`` and the veto
``tau`` on TRAIN-Gate.

The grid contains ``(1, 0, 0)``, which is stage 1 itself, so the search is
guaranteed not to be a regression on the block it is selected on.  Nothing is
refitted after the winner is known, and the winner is written once.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from introact_ts.v44 import protocol as P
from introact_ts.v44_r2 import evaluate as EV
from introact_ts.v44_r2 import regret as RG
from introact_ts.v44_r2.dataset import load_block
from introact_ts.v44_r2.protocol_r2 import TAU_GRID, lambda_grid

ROOT = Path(__file__).resolve().parent.parent
STAGE1 = ROOT / "results/v44_r2/gate/gate_sweep.json"
OUT = ROOT / "results/v44_r2/gate/stage2_sweep.json"
METHOD = "R2_DECISION_REGRET_ENSEMBLE"


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--stage1", default=str(STAGE1))
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()
    root = Path(args.root)
    output = Path(args.output)
    if output.exists():
        raise SystemExit("stage-2 gate already frozen; preserve the first selection")
    began = time.perf_counter()

    frozen = json.loads(Path(args.stage1).read_text())["selected"]
    thresholds = json.loads(Path(args.stage1).read_text())["opportunity_thresholds"]

    fit = {b: load_block(root, "replay_fit", b) for b in P.DEV_BACKBONES}
    gate = {b: load_block(root, "gate", b) for b in P.DEV_BACKBONES}

    grid = lambda_grid()
    per_backbone: dict[str, dict] = {}
    for backbone in P.DEV_BACKBONES:
        ranker, ridge, tree = RG.fit_all(fit[backbone], frozen=frozen)
        prepared, probabilities, legals = RG.prepare(gate[backbone], ranker,
                                                     ridge, tree)
        per_lambda: dict[str, dict] = {}
        for lambdas in grid:
            per_tau = {}
            for tau in TAU_GRID:
                decisions = RG.decisions_for(gate[backbone], prepared,
                                             probabilities, legals,
                                             lambdas=lambdas, tau=tau)
                records = EV.decision_records(gate[backbone], decisions,
                                              backbone=backbone, method=METHOD,
                                              thresholds=thresholds)
                governance = EV.governance(records).get(METHOD)
                if governance is None:
                    raise SystemExit(
                        f"{lambdas} x tau={tau} produced no scorable TRAIN-Gate "
                        f"record on {backbone}")
                per_tau[str(tau)] = {
                    "source_macro_mase": EV.macro_mase(records, METHOD, backbone),
                    "source_macro_cells": EV.macro_cells(records, METHOD, backbone),
                    "governance": governance,
                }
            per_lambda[repr(lambdas)] = {"lambdas": list(lambdas),
                                         "per_tau": per_tau}
        per_backbone[backbone] = {
            "episodes": len(gate[backbone]),
            "ridge_notes": ridge.notes(),
            "tree_notes": tree.notes(),
            "pair_summary": ranker.pair_summary,
            "per_lambda": per_lambda,
        }

    joint = []
    for lambdas in grid:
        key = repr(lambdas)
        for tau in TAU_GRID:
            values, keeps, harms = [], [], []
            for backbone in P.DEV_BACKBONES:
                row = per_backbone[backbone]["per_lambda"][key]["per_tau"][str(tau)]
                values.append(row["source_macro_mase"])
                keeps.append(row["governance"]["keep_rate"])
                harms.append(row["governance"]["harmful_loss"])
            scorable = all(v is not None for v in values)
            joint.append({
                "lambdas": list(lambdas),
                "tau": float(tau),
                "joint_objective": (float(sum(values) / len(values))
                                    if scorable else None),
                "per_backbone": values,
                "keep_rate": keeps,
                "mean_harmful_loss": (float(sum(harms) / len(harms))
                                      if all(h is not None for h in harms)
                                      else None),
                "non_degenerate": all(0.0 < k < 1.0 for k in keeps),
                "scorable": scorable,
            })

    eligible = [row for row in joint if row["non_degenerate"] and row["scorable"]]
    if not eligible:
        raise SystemExit("no non-degenerate stage-2 candidate on TRAIN-Gate")
    eligible.sort(key=lambda r: (r["joint_objective"], r["mean_harmful_loss"]))
    winner = eligible[0]
    stage1_row = next(row for row in eligible if row["lambdas"] == [1.0, 0.0, 0.0]
                      and abs(row["tau"] - frozen["tau"]) < 1e-12)

    payload = {
        "stage": "v44-r2-stage2-gate-selection",
        "status": "frozen",
        "objective": "macro average of the two development backbones' source-macro MASE",
        "constraint": "R5 applied at selection time: KEEP rate strictly in (0, 1)",
        "tie_breaks": ["lower mean Harmful Loss"],
        "inherits": frozen,
        "lambda_grid": [list(item) for item in grid],
        "tau_grid": list(TAU_GRID),
        "candidate_grid": {"lambdas": len(grid), "taus": len(TAU_GRID),
                           "total": len(grid) * len(TAU_GRID)},
        "opportunity_thresholds": thresholds,
        "per_backbone": per_backbone,
        "joint": joint,
        "selected": {"lambdas": winner["lambdas"], "tau": winner["tau"],
                     **frozen},
        "stage1_reference": {
            "lambdas": stage1_row["lambdas"], "tau": stage1_row["tau"],
            "joint_objective": stage1_row["joint_objective"],
            "per_backbone": stage1_row["per_backbone"],
            "keep_rate": stage1_row["keep_rate"],
        },
        "improvement_over_stage1": (stage1_row["joint_objective"]
                                    - winner["joint_objective"]),
        "runtime_seconds": time.perf_counter() - began,
        "heldout_labels_read": 0,
        "calibration_test_touched": False,
    }
    write(output, payload)
    print(json.dumps({
        "selected": payload["selected"],
        "joint_objective": winner["joint_objective"],
        "per_backbone": winner["per_backbone"],
        "keep_rate": winner["keep_rate"],
        "stage1_reference": payload["stage1_reference"],
        "improvement_over_stage1": payload["improvement_over_stage1"],
        "top5": [{k: r[k] for k in ("lambdas", "tau", "joint_objective",
                                    "per_backbone", "keep_rate")}
                 for r in eligible[:5]],
        "runtime_seconds": payload["runtime_seconds"],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
