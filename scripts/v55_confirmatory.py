#!/usr/bin/env python3
"""Freeze on confirmatory TRAIN, then score its TEST regions once.

The freeze stage loads only bankx and train_eval.  The evaluate stage requires
that freeze artifact and a completed input/forecast audit before it opens any
confirmatory TEST catalog.  Results are limited to catalog policies because
external imputer rows have not been run on these sources.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v47 import select as SEL
from introact_ts.v55 import select as V55

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import ROOT, clean, sha, write  # noqa: E402
from v55_select_1se import one_se_pick  # noqa: E402

REPLAY = "results/v55/confirmatory/replay"
OUT = ROOT / "results/v55/confirmatory"
BLOCKS = ("test", "test_m2", "test_m3")
ALPHAS = (0.01, 0.02, 0.03, 0.05)


def catalogs(root: Path, block: str, backbone: str):
    C.REPLAY = REPLAY
    rows = C.load_catalog(root, block, backbone)
    expected = json.loads((root / REPLAY / "inputs" / f"{block}.json").read_text())
    if len(rows) != expected["episodes"]:
        raise RuntimeError(f"{block}/{backbone}: {len(rows)} scored vs "
                           f"{expected['episodes']} expected episodes")
    return rows


def freeze(root: Path, backbone: str) -> None:
    path = OUT / f"freeze_{backbone}.json"
    if path.exists():
        raise SystemExit(f"freeze already exists: {path}")
    bank_rows = catalogs(root, "bankx", backbone)
    calibration_rows = catalogs(root, "train_eval", backbone)
    blocks = SEL.blocks_of()
    bank = SEL.Bank(bank_rows, blocks=blocks)
    train = SEL.Queries(bank_rows, blocks=blocks)
    cap = SEL.harm_cap(bank, train)
    selection = V55.select_hyperparameters(bank, train, cap=cap["cap"])
    if selection.get("selected") is not None:
        pick = one_se_pick(selection["grid"], cap["cap"])
        selection["min_rule_selected"] = selection["selected"]
        selection["selected"] = {k: pick[k] for k in
                                 ("k", "beta", "lam", "lam_is_inf")}
        selection["leader"] = {
            "k": pick["k"], "beta": pick["beta"], "lam": pick["lam"],
            "lam_is_inf": pick["lam_is_inf"],
            "lopo_mase": pick["lopo_mase"],
            "intervention_rate": pick["intervention_rate"],
            "conditional_hir": pick["conditional_hir"],
            "gap_to_min_rule": pick.get("gap_to_selected"),
            "gap_se": pick.get("gap_se"),
        }
        selection["rule"] = "one standard error, then least intervention"
        selection["one_se_band_size"] = sum(
            r["conditional_hir"] <= cap["cap"]
            and (r.get("gap_to_selected") or 0.0) <= (r.get("gap_se") or 0.0)
            for r in selection["grid"])
    config = V55.frozen_config(selection)
    levels = []
    if config is not None:
        queries = SEL.Queries(calibration_rows, blocks=blocks)
        D = SEL.distance_matrices(bank, queries, lopo=False)
        moments = V55.local_moments(bank, queries, D, config[0])
        means = V55.source_action_means(bank)
        scores = V55.scores_from_moments(moments, means, queries,
                                         config[1], config[2])
        for alpha in ALPHAS:
            level = V55.conformal_threshold(queries, scores, alpha)["selected"]
            levels.append({"alpha": alpha,
                           "threshold": ("inf" if np.isinf(level["threshold"])
                                         else level["threshold"]),
                           "calibration_harm": level["empirical_harm"],
                           "crc_bound": level["crc_bound"],
                           "note": level.get("note")})
    payload = {
        "status": "frozen", "backbone": backbone,
        "bank_episodes": len(bank_rows),
        "bank_parents": len({r.parent for r in bank_rows}),
        "calibration_episodes": len(calibration_rows),
        "calibration_parents": len({r.parent for r in calibration_rows}),
        "cap": cap, "selection_rule": "one-standard-error",
        "selection": selection, "conformal": levels,
        "test_records_read": 0,
        "code_sha256": {
            "src/introact_ts/v55/select.py": sha(root / "src/introact_ts/v55/select.py"),
            "scripts/v55_confirmatory.py": sha(Path(__file__)),
        },
    }
    write(path, clean(payload))
    print(json.dumps(clean({"backbone": backbone,
                            "selected": selection.get("selected"),
                            "conformal": levels,
                            "test_records_read": 0}), indent=1))


def source_fixed(bank: SEL.Bank, queries: SEL.Queries):
    means = V55.source_action_means(bank)
    policy = {}
    for source in sorted(set(map(str, queries.source))):
        usable = {a: means[a][source]["mean"] for a in SEL.NONREF
                  if source in means[a]}
        policy[source] = max(usable, key=usable.get) if usable else SEL.REFERENCE
    decision = np.full(len(queries.episode), SEL.REFERENCE, dtype=object)
    for i, source in enumerate(queries.source):
        action = policy[str(source)]
        if action != SEL.REFERENCE and queries.legal[action][i]:
            decision[i] = action
    return decision, policy


def score_block(root: Path, backbone: str, block: str, bank: SEL.Bank,
                config: tuple | None, levels: list):
    queries = SEL.Queries(catalogs(root, block, backbone), blocks=SEL.blocks_of())
    n = len(queries.episode)
    decisions = {
        "NATIVE_KEEP": np.full(n, SEL.REFERENCE, dtype=object),
        "BEST_FIXED": SEL.apply_fixed(queries, SEL.best_fixed_action(bank)),
        "FIXED_SAITS": SEL.apply_fixed(queries, "SAITS"),
        "R2_CART": SEL.r2_cart(bank, queries),
        "CATALOG_ORACLE": SEL.oracle(queries),
    }
    decisions["SOURCE_FIXED"], policy = source_fixed(bank, queries)
    if config is None:
        decisions["FULL_INTROACT"] = decisions["NATIVE_KEEP"].copy()
    else:
        D = SEL.distance_matrices(bank, queries, lopo=False)
        moments = V55.local_moments(bank, queries, D, config[0])
        means = V55.source_action_means(bank)
        scores = V55.scores_from_moments(moments, means, queries,
                                         config[1], config[2])
        decisions["FULL_INTROACT"] = V55.decide(queries, scores)
        for label, lam in (("E_LOCAL_ONLY", 0.0),
                           ("E_SOURCE_ONLY", float("inf"))):
            decisions[label] = V55.decide(
                queries, V55.scores_from_moments(moments, means, queries,
                                                  config[1], lam))
        for level in levels:
            label = "CONFORMAL_A%02d" % round(level["alpha"] * 100)
            decisions[label] = V55.decide(queries, scores,
                                           threshold=float(level["threshold"]))
    vectors = {name: SEL.realised(queries, selected)
               for name, selected in decisions.items()}
    rows = {}
    for name, selected in decisions.items():
        out = SEL.outcomes(queries, selected)
        rows[name] = {
            "mase": SEL.source_macro(queries, vectors[name]),
            "per_source_mase": SEL.macro_by_source(queries, vectors[name]),
            "intervention_rate": out["intervention_rate"],
            "conditional_hir": out["conditional_hir"],
            "harmful_loss": out["harmful_loss"],
            "harm_clipped": float(V55.harm_per_request(queries, selected).mean()),
        }
    comparisons = {}
    for ref in ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "FIXED_SAITS",
                "R2_CART"):
        comparisons[f"FULL_INTROACT_vs_{ref}"] = SEL.paired_cluster_bootstrap(
            queries, vectors["FULL_INTROACT"], vectors[ref],
            resamples=2000, seed=101)
    adjusted = SEL.holm({k: v["p_value"] for k, v in comparisons.items()})
    for key, value in comparisons.items():
        value["p_holm"] = adjusted[key]
    return {"episodes": n, "parents": len(set(queries.parent)),
            "sources": sorted(set(map(str, queries.source))),
            "source_fixed_policy": policy, "rows": rows,
            "comparisons": comparisons}


def evaluate(root: Path, backbone: str) -> None:
    path = OUT / f"evaluation_{backbone}.json"
    if path.exists():
        raise SystemExit(f"one-time evaluation already exists: {path}")
    check = OUT / "check_report.json"
    if not check.exists():
        raise SystemExit("confirmatory stage audit is missing")
    audit = json.loads(check.read_text())
    if audit.get("status") != "completed" and not audit.get("all_passed"):
        raise SystemExit("confirmatory stage audit did not pass")
    frozen = json.loads((OUT / f"freeze_{backbone}.json").read_text())
    if frozen.get("test_records_read") != 0:
        raise SystemExit("freeze artifact records TEST access")
    current_hashes = {
        "src/introact_ts/v55/select.py": sha(root / "src/introact_ts/v55/select.py"),
        "scripts/v55_confirmatory.py": sha(Path(__file__)),
    }
    if current_hashes != frozen["code_sha256"]:
        raise SystemExit("code changed after confirmation freeze; TEST remains closed")
    config = V55.frozen_config(frozen["selection"])
    bank = SEL.Bank(catalogs(root, "bankx", backbone), blocks=SEL.blocks_of())
    began = time.perf_counter()
    blocks = {name: score_block(root, backbone, name, bank, config,
                                frozen["conformal"]) for name in BLOCKS}
    payload = {
        "status": "completed", "backbone": backbone,
        "freeze_file": str(OUT / f"freeze_{backbone}.json"),
        "freeze_code_sha256": frozen["code_sha256"],
        "code_sha256": current_hashes,
        "blocks": blocks,
        "runtime_seconds": time.perf_counter() - began,
        "scope": "two previously used sources; heldout TEST periods; catalog policies only",
    }
    tmp = path.with_suffix(".json.tmp")
    write(tmp, clean(payload))
    os.replace(tmp, path)
    print(json.dumps(clean({"backbone": backbone,
                            "main_test": blocks["test"]["rows"]}), indent=1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("freeze", "evaluate"))
    parser.add_argument("--backbone", choices=("bolt", "timesfm", "chronos2"),
                        required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.stage == "freeze":
        freeze(args.root, args.backbone)
    else:
        evaluate(args.root, args.backbone)


if __name__ == "__main__":
    main()
