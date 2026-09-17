#!/usr/bin/env python3
"""v4.4-r2 Batch 1 -- the decision-regret gate.

Fits the seven frozen model configurations on each backbone's Replay-Fit block,
sweeps the four veto thresholds on TRAIN-Gate, and freezes **one** shared
``model config x tau`` for both development backbones.

Nothing is refitted after the winner is known, and the winner is written once:
a second invocation refuses to overwrite it.  All CPU, no TSFM calls, no new
replay -- it consumes the v4.4 artifacts read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from introact_ts.v44 import protocol as P
from introact_ts.v44_r2 import evaluate as EV
from introact_ts.v44_r2 import ranking as RK
from introact_ts.v44_r2.dataset import load_block
from introact_ts.v44_r2.protocol_r2 import TAU_GRID, candidate_grid

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v44_r2/gate"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output", default=str(OUT / "gate_sweep.json"))
    args = parser.parse_args()
    root = Path(args.root)
    output = Path(args.output)
    if output.exists():
        raise SystemExit("r2 gate already frozen; preserve the first selection")
    began = time.perf_counter()

    fit = {b: load_block(root, "replay_fit", b) for b in P.DEV_BACKBONES}
    gate = {b: load_block(root, "gate", b) for b in P.DEV_BACKBONES}

    pooled = [e for b in P.DEV_BACKBONES for e in fit[b]]
    thresholds = EV.freeze_opportunity_thresholds(pooled)

    per_backbone: dict[str, dict] = {}
    for backbone in P.DEV_BACKBONES:
        block = gate[backbone]
        per_config: dict[str, dict] = {}
        for config in [c for c in candidate_grid() if c["tau"] == TAU_GRID[0]]:
            name = config["config"]
            ranker = RK.PairwiseRanker(learner=config["learner"],
                                       alpha=config["alpha"]).fit(fit[backbone])
            pairs = {e.episode: ranker.pair_probabilities(e) for e in block}
            legal = {e.episode: e.legal() for e in block}
            per_tau = {}
            for tau in TAU_GRID:
                decisions = {e.episode: RK.decide_from(pairs[e.episode],
                                                       legal[e.episode], tau=tau)
                             for e in block}
                records = EV.decision_records(block, decisions, backbone=backbone,
                                              method=name, thresholds=thresholds)
                governance = EV.governance(records).get(name)
                if governance is None:
                    raise SystemExit(
                        f"{name} produced no scorable TRAIN-Gate record on "
                        f"{backbone}; the sweep cannot rank a config that "
                        f"never executed")
                per_tau[str(tau)] = {
                    "source_macro_mase": EV.macro_mase(records, name, backbone),
                    "source_macro_cells": EV.macro_cells(records, name, backbone),
                    "governance": governance,
                }
            per_config[name] = {
                "learner": config["learner"],
                "alpha": config["alpha"],
                "pair_summary": ranker.pair_summary,
                "notes": ranker.notes,
                "per_tau": per_tau,
            }
        per_backbone[backbone] = {"episodes": len(block), "configs": per_config}

    joint = []
    for config in [c for c in candidate_grid() if c["tau"] == TAU_GRID[0]]:
        name = config["config"]
        for tau in TAU_GRID:
            values, keeps, harms = [], [], []
            for backbone in P.DEV_BACKBONES:
                row = per_backbone[backbone]["configs"][name]["per_tau"][str(tau)]
                values.append(row["source_macro_mase"])
                keeps.append(row["governance"]["keep_rate"])
                harms.append(row["governance"]["harmful_loss"])
            non_degenerate = all(0.0 < k < 1.0 for k in keeps)
            scorable = all(v is not None for v in values)
            joint.append({
                "config": name,
                "learner": config["learner"],
                "alpha": config["alpha"],
                "tau": float(tau),
                "joint_objective": (float(sum(values) / len(values))
                                    if scorable else None),
                "per_backbone": values,
                "keep_rate": keeps,
                "mean_harmful_loss": (float(sum(harms) / len(harms))
                                      if all(h is not None for h in harms)
                                      else None),
                "non_degenerate": non_degenerate,
                "scorable": scorable,
            })

    eligible = [row for row in joint if row["non_degenerate"] and row["scorable"]]
    if not eligible:
        raise SystemExit("no non-degenerate r2 candidate on TRAIN-Gate")
    eligible.sort(key=lambda r: (r["joint_objective"], r["mean_harmful_loss"]))
    winner = eligible[0]

    payload = {
        "stage": "v44-r2-gate-selection",
        "status": "frozen",
        "objective": "macro average of the two development backbones' source-macro MASE",
        "constraint": ("admission criterion R5 applied at selection time: the KEEP "
                       "rate must be strictly between 0 and 1 on both backbones"),
        "tie_breaks": ["lower mean Harmful Loss"],
        "candidate_grid": {"configs": 7, "taus": list(TAU_GRID), "total": 28},
        "opportunity_thresholds": thresholds,
        "per_backbone": per_backbone,
        "joint": joint,
        "selected": {"config": winner["config"], "learner": winner["learner"],
                     "alpha": winner["alpha"], "tau": winner["tau"]},
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
        "top5": [{k: r[k] for k in ("config", "tau", "joint_objective",
                                    "per_backbone", "keep_rate")}
                 for r in eligible[:5]],
        "runtime_seconds": payload["runtime_seconds"],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
