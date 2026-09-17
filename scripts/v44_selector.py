#!/usr/bin/env python3
"""v4.4 Step 6-8 -- the K/beta gate and the TRAIN-Eval admission.

``--mode gate`` runs the nine allowed ``K x beta`` configurations on TRAIN-Gate
and selects **one** configuration shared by both development backbones, using
the joint objective required by the task book: the macro average of the two
source-macro MASE values, with the declared tie-breaks.

``--mode eval`` freezes that configuration and runs the admission ladder
(Native KEEP, Best Fixed, R2-CART, Full IntroAct and the five ablations) on
TRAIN-Eval, together with the governance and efficiency diagnostics.

Nothing here opens calibration or test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from introact_ts.v44 import methods as MT
from introact_ts.v44 import metrics as ME
from introact_ts.v44 import protocol as P
from introact_ts.v44 import statistics as ST
from introact_ts.v44.catalog import EpisodeCatalog, load_catalog, to_records
from introact_ts.v44.replay import ReplayBank
from introact_ts.v44.splits import ParentWindow, assign_splits
from introact_ts.v44.registry import train_parents

ROOT = Path(__file__).resolve().parent.parent
BANKS = ROOT / "results/v44/banks"
GATE_OUT = ROOT / "results/v44/gate"
EVAL_OUT = ROOT / "results/v44/evaluation"


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


def block_of(root: Path) -> dict[str, str]:
    return assign_splits(train_parents(root))


def load_bank(backbone: str, block: str = "replay_fit") -> ReplayBank:
    return ReplayBank.load(BANKS / block, name=f"replay_bank_{backbone}")


def run_methods(bank: ReplayBank, catalogs: list[EpisodeCatalog], *,
                mapping: dict[str, str], k: int, beta: float,
                gate_catalogs: list[EpisodeCatalog] | None = None) -> dict[str, MT.MethodRun]:
    """Every method of the ladder, all sharing one decision interface.

    The bank is always the Replay-Fit bank, so every retrieval and every
    control fit is guarded with ``MT.BANK_BLOCK``.  The block under evaluation
    is whatever ``catalogs`` holds -- it is deliberately *not* passed to the
    retrieval guard, which would empty the bank and make every method abstain.
    """
    runs: dict[str, MT.MethodRun] = {}
    runs["NATIVE_KEEP"] = MT.native_keep(catalogs)

    fixed_source = gate_catalogs if gate_catalogs is not None else catalogs
    fixed = MT.best_fixed(fixed_source)
    runs["BEST_FIXED"] = MT.apply_fixed(fixed, catalogs)

    runs["R2_CART"] = MT.r2_cart(bank, catalogs, block_of=mapping)

    runs["FULL_INTROACT"] = MT.select_with(
        MT.full_selector(bank, k=k, beta=beta, block_of=mapping), bank, catalogs,
        block_of=mapping)
    runs["A1_GLOBAL_REPLAY"] = MT.select_with(
        MT.full_selector(bank, k=k, beta=beta, block_of=mapping, local=False),
        bank, catalogs, block_of=mapping)
    runs["A2_WO_INTERVENTION"] = MT.select_with(
        MT.full_selector(bank, k=k, beta=beta, block_of=mapping,
                         use_intervention=False),
        bank, catalogs, block_of=mapping)
    runs["A3_WO_FORECAST"] = MT.select_with(
        MT.full_selector(bank, k=k, beta=beta, block_of=mapping,
                         use_forecast=False),
        bank, catalogs, block_of=mapping)
    runs["A4_WO_GATE"] = MT.select_with(
        MT.full_selector(bank, k=k, beta=beta, block_of=mapping,
                         conservative=False),
        bank, catalogs, block_of=mapping)
    runs["A5_PARAMETRIC_RIDGE"] = MT.parametric(
        bank, catalogs, k=k, beta=beta, block_of=mapping, kind="ridge")
    runs["A5_PARAMETRIC_CART"] = MT.parametric(
        bank, catalogs, k=k, beta=beta, block_of=mapping, kind="cart")
    runs["CATALOG_ORACLE"] = MT.oracle_run(catalogs)
    return runs


def method_table(runs: dict[str, MT.MethodRun], catalogs: list[EpisodeCatalog],
                 backbone: str) -> list[dict]:
    """One record per (method, variant) with the metrics of the chosen action."""
    records: list[dict] = []
    for method, run in runs.items():
        for catalog in catalogs:
            action = run.selected.get(catalog.episode, P.REFERENCE_ACTION)
            entry = catalog.actions.get(action) or catalog.reference
            reference = catalog.reference
            records.append({
                "method": method,
                "backbone": backbone,
                "source": catalog.source,
                "parent": catalog.parent,
                "variant": catalog.episode,
                "horizon": catalog.horizon,
                "pattern": catalog.pattern,
                "severity": catalog.severity,
                "selected_action": action,
                "intervened": action != P.REFERENCE_ACTION,
                "mase": entry.mase,
                "mse": entry.mse,
                "mae": entry.mae,
                "rmsse": entry.rmsse,
                "keep_mase": reference.mase,
                "keep_mse": reference.mse,
                "oracle_mase": catalog.oracle()[1],
                "runtime": entry.runtime,
                "applicable": entry.applicable,
                "failure": None if entry.applicable else entry.reason,
                "alias_of": entry.alias_of,
            })
    return records


def governance(records: list[dict]) -> dict:
    """HIR, Harmful Loss and Catalog Gap Closed, computed per method.

    A request only enters the diagnostics when its own loss, its reference loss
    and its oracle loss are all present.  The three are structurally coupled --
    the scoring mask and the MASE denominator are properties of the window, not
    of the action -- so a disagreement would mean the catalog and the metrics
    had drifted apart, and the count is reported rather than hidden.
    """
    out: dict[str, dict] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["method"]].append(record)
    for method, items in sorted(grouped.items()):
        usable = [r for r in items
                  if r["mase"] is not None and r["keep_mase"] is not None
                  and r["oracle_mase"] is not None]
        if not usable:
            continue
        loss = np.array([r["mase"] for r in usable], dtype=np.float64)
        keep = np.array([r["keep_mase"] for r in usable], dtype=np.float64)
        oracle = np.array([r["oracle_mase"] for r in usable], dtype=np.float64)
        intervened = np.array([r["intervened"] for r in usable], dtype=bool)
        harmful = loss > keep
        out[method] = {
            "n": int(loss.size),
            "excluded_missing_loss": int(len(items) - len(usable)),
            "intervention_rate": float(intervened.mean()),
            "hir": ME.harmful_intervention_rate(loss, keep),
            "conditional_hir": (float(harmful[intervened].mean())
                                if intervened.any() else None),
            "harmful_loss": ME.harmful_loss(loss, keep),
            **ME.catalog_gap_closed(loss, keep, oracle),
        }
    return out


def efficiency(records: list[dict]) -> dict:
    out: dict[str, dict] = {}
    grouped: dict[str, list[float]] = defaultdict(list)
    for record in records:
        grouped[record["method"]].append(float(record.get("runtime") or 0.0))
    for method, values in sorted(grouped.items()):
        array = np.asarray(values, dtype=np.float64)
        out[method] = {
            "n": int(array.size),
            "mean_latency": float(array.mean()),
            "p95_latency": float(np.percentile(array, 95)),
            "max_latency": float(array.max()),
            "calls_per_request": 1.0,
        }
    return out


def macro_mase(records: list[dict], method: str, backbone: str) -> float | None:
    """Headline source-macro MASE for one method, averaged over condition cells."""
    subset = [r for r in records if r["method"] == method and r["backbone"] == backbone]
    return ME.macro_headline(subset, "mase")


def mode_gate(root: Path) -> None:
    mapping = block_of(root)
    output = GATE_OUT / "gate_sweep.json"
    if output.exists():
        raise SystemExit("gate selection already frozen; preserve the first one")
    began = time.perf_counter()
    results: dict[str, dict] = {}
    for backbone in P.DEV_BACKBONES:
        bank = load_bank(backbone)
        catalogs = load_catalog(root, "gate", backbone)
        sweep = []
        for k in P.K_GRID:
            for beta in P.BETA_GRID:
                selector = MT.full_selector(bank, k=k, beta=beta,
                                            block_of=mapping)
                run = MT.select_with(selector, bank, catalogs, block_of=mapping)
                records = method_table({"FULL_INTROACT": run}, catalogs, backbone)
                sweep.append({
                    "k": k, "beta": beta,
                    "source_macro_mase": macro_mase(records, "FULL_INTROACT", backbone),
                    "source_macro_cells": {
                        f"h{cell['horizon']}|{cell['pattern']}": cell["mase"]
                        for cell in ME.macro_cells(records, "mase")},
                    "abstained": run.notes["abstained"],
                    "governance": governance(records).get("FULL_INTROACT", {}),
                })
        results[backbone] = {"episodes": len(catalogs), "sweep": sweep}

    joint = []
    for k in P.K_GRID:
        for beta in P.BETA_GRID:
            values, harm, hir, calls = [], [], [], []
            for backbone in P.DEV_BACKBONES:
                row = next(r for r in results[backbone]["sweep"]
                           if r["k"] == k and abs(r["beta"] - beta) < 1e-12)
                value = row["source_macro_mase"]
                if value is None:
                    raise SystemExit(
                        f"gate sweep produced no score for {backbone} at "
                        f"K={k}, beta={beta}")
                values.append(value)
                gov = row["governance"]
                harm.append(gov.get("harmful_loss", float("inf")))
                hir.append(gov.get("hir", float("inf")))
                calls.append(row["governance"].get("intervention_rate", 1.0))
            joint.append({
                "k": k, "beta": beta,
                "joint_objective": float(np.mean(values)),
                "per_backbone": values,
                "mean_harmful_loss": float(np.mean(harm)),
                "mean_hir": float(np.mean(hir)),
                "mean_intervention_rate": float(np.mean(calls)),
            })
    joint.sort(key=lambda r: (r["joint_objective"], r["mean_harmful_loss"],
                              r["mean_hir"], r["mean_intervention_rate"]))
    winner = joint[0]
    payload = {
        "stage": "v44-gate-selection",
        "status": "frozen",
        "objective": "macro average of the two development backbones' source-macro MASE",
        "tie_breaks": ["lower Harmful Loss", "lower HIR", "fewer interventions"],
        "per_backbone_sweep": results,
        "joint": joint,
        "selected": {"k": winner["k"], "beta": winner["beta"]},
        "block_of_sha256": hashlib.sha256(json.dumps(
            mapping, sort_keys=True).encode()).hexdigest(),
        "runtime_seconds": time.perf_counter() - began,
        "heldout_labels_read": 0,
    }
    write(output, payload)
    print(json.dumps({"selected": payload["selected"],
                      "joint": joint[:3],
                      "backbones": {b: min(r["sweep"],
                                           key=lambda x: x["source_macro_mase"])["source_macro_mase"]
                                    for b, r in results.items()}},
                     ensure_ascii=False, indent=1))


def mode_eval(root: Path) -> None:
    selection = json.loads((GATE_OUT / "gate_sweep.json").read_text())
    k, beta = selection["selected"]["k"], selection["selected"]["beta"]
    mapping = block_of(root)
    began = time.perf_counter()

    all_records: list[dict] = []
    per_backbone: dict[str, dict] = {}
    for backbone in P.DEV_BACKBONES:
        bank = load_bank(backbone)
        gate_catalogs = load_catalog(root, "gate", backbone)
        catalogs = load_catalog(root, "train_eval", backbone)
        runs = run_methods(bank, catalogs, mapping=mapping, k=k, beta=beta,
                           gate_catalogs=gate_catalogs)
        records = method_table(runs, catalogs, backbone)
        all_records.extend(records)
        per_backbone[backbone] = {
            "episodes": len(catalogs),
            "macro_mase": {method: macro_mase(records, method, backbone)
                           for method in runs},
            "macro_cells": {
                method: {f"h{cell['horizon']}|{cell['pattern']}": cell["mase"]
                         for cell in ME.macro_cells(
                             [r for r in records if r["method"] == method],
                             "mase")}
                for method in runs},
            "governance": governance(records),
            "efficiency": efficiency(records),
            "notes": {method: run.notes for method, run in runs.items()},
        }

    payload = {
        "stage": "v44-train-eval-admission",
        "frozen": {"k": k, "beta": beta},
        "per_backbone": per_backbone,
        "records": all_records,
        "runtime_seconds": time.perf_counter() - began,
        "heldout_labels_read": 0,
        "calibration_test_touched": False,
    }
    write(EVAL_OUT / "train_eval.json", payload)
    print(json.dumps({"frozen": payload["frozen"],
                      "macro_mase": {b: v["macro_mase"]
                                     for b, v in per_backbone.items()}},
                     ensure_ascii=False, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--mode", required=True, choices=["gate", "eval"])
    args = parser.parse_args()
    if args.mode == "gate":
        mode_gate(Path(args.root))
    else:
        mode_eval(Path(args.root))


if __name__ == "__main__":
    main()
