#!/usr/bin/env python3
"""v53 state compaction: Full-22 vs Compact-17, one train-side comparison.

Task 1 of the v53 plan (2026-09-22).  For each backbone:

* Re-runs the complete ``select_hyperparameters`` (same k x beta grid, same
  leave-one-parent-out, same harm cap) on the replay bank with the Compact-17
  state (``blocks_of(use_intervention=False)``: mask + context + forecast, the
  five intervention features dropped).
* Re-runs the same selection with the Full-22 state and checks the outcome
  against the frozen ``results/v47/protocol/selection_<backbone>.json``.
* Evaluates each variant with its OWN selected (k, beta) on train_eval
  (decision block) and on test / test30 / test50 / test_m2 / test_m3
  (recorded only; nothing is tuned on them).
* Computes the parent-clustered paired bootstrap of FULL - COMPACT on
  train_eval and on test (2000 resamples, seed 101, the module default).

Module choice (audited 2026-09-22): the frozen selections were produced by
``scripts/v47_select.py`` with ``introact_ts.v47.select`` +
``introact_ts.v44.catalog`` on the ``bankx`` block (its harm-cap anchor is the
action with the highest bank mean utility, and its infeasible branch falls
back to ``beta == max(beta_grid)``).  ``introact_ts.v47_verified.select`` is a
later, stricter rewrite (fold-refit standardisation, MASE-anchored cap, raises
on infeasibility) and would NOT reproduce the frozen JSONs.  This script
therefore uses the operational ``v47`` module, exactly as the v52 scripts do,
so the Full-22 rerun is a genuine consistency check of the freeze.

Selection reads the bank block only; the payload records
``test_records_read == 0`` guarded by a load log.

Outputs go to ``results/v53_state_compact/`` and never overwrite v47/v52.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import protocol as P
from introact_ts.v47 import select as SEL

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v52_ablation_action_cond import clean, summarise, write

ROOT = Path(__file__).resolve().parent.parent

EVAL_BLOCKS = ("train_eval", "test", "test30", "test50", "test_m2", "test_m3")
VARIANTS = {
    "FULL22": {},
    "COMPACT17": {"use_intervention": False},
}

#: Blocks loaded through the tracked loader, in order.  The selection phase
#: must contain no test* entry; that is the development-gate guard.
LOAD_LOG: list[str] = []
_ORIG_LOAD = C.load_catalog


def load_catalog(root, block, backbone):
    LOAD_LOG.append(block)
    return _ORIG_LOAD(root, block, backbone)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_selection(root: Path, backbone: str, bank_catalogs, blocks) -> dict:
    bank = SEL.Bank(bank_catalogs, blocks=blocks)
    queries = SEL.Queries(bank_catalogs, blocks=blocks)
    cap = SEL.harm_cap(bank, queries)
    started = len(LOAD_LOG)
    selection = SEL.select_hyperparameters(bank, queries, cap=cap["cap"])
    assert not any(b.startswith("test") for b in LOAD_LOG[started:]), \
        "selection read a TEST block"
    return {"bank": bank, "harm_cap": cap, "selection": selection}


def evaluate(root: Path, backbone: str, bank, blocks, k: int, beta: float,
             block: str):
    catalogs = load_catalog(root, block, backbone)
    queries = SEL.Queries(catalogs, blocks=blocks)
    D = SEL.distance_matrices(bank, queries, lopo=False)
    selected = SEL.decide(queries, SEL.score_grid(bank, queries, D, k, beta))
    return queries, selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--bank-blocks", default="bankx")
    parser.add_argument("--blocks", default=",".join(EVAL_BLOCKS))
    parser.add_argument("--resamples", type=int, default=P.BOOTSTRAP_RESAMPLES)
    parser.add_argument("--replay", default="results/v47/replay")
    parser.add_argument("--protocol-dir", default="results/v47/protocol")
    parser.add_argument("--output-root", default="results/v53_state_compact")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    out = root / args.output_root
    C.REPLAY = args.replay

    code_hashes = {
        "scripts/v53_state_compact.py": sha256_of(Path(__file__).resolve()),
        "src/introact_ts/v47/select.py": sha256_of(
            root / "src/introact_ts/v47/select.py"),
        "src/introact_ts/v44/catalog.py": sha256_of(
            root / "src/introact_ts/v44/catalog.py"),
    }

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(load_catalog(root, name.strip(), args.backbone))

    # ---------------- selection phase (bank only, no test block) ----------
    mark = len(LOAD_LOG)
    selections = {}
    for variant, kwargs in VARIANTS.items():
        blocks = SEL.blocks_of(**kwargs)
        t0 = time.perf_counter()
        pack = run_selection(root, args.backbone, bank_catalogs, blocks)
        pack["blocks"] = blocks
        pack["runtime_seconds"] = time.perf_counter() - t0
        selections[variant] = pack
    test_reads_in_selection = sum(1 for b in LOAD_LOG[mark:] if b.startswith("test"))

    frozen_path = root / args.protocol_dir / f"selection_{args.backbone}.json"
    frozen = json.loads(frozen_path.read_text())
    full = selections["FULL22"]
    consistency = {
        "frozen_file": str(frozen_path.relative_to(root)),
        "frozen_selected": frozen["selection"]["selected"],
        "rerun_selected": full["selection"]["selected"],
        "k_match": bool(full["selection"]["selected"]["k"]
                        == frozen["selection"]["selected"]["k"]),
        "beta_match": bool(full["selection"]["selected"]["beta"]
                           == frozen["selection"]["selected"]["beta"]),
        "cap_match": bool(abs(full["selection"]["cap"] - frozen["selection"]["cap"]) < 1e-12),
        "anchor_match": bool(full["harm_cap"]["anchor"] == frozen["harm_cap"]["anchor"]),
        "lopo_mase_match": bool(abs(full["selection"]["leader"]["lopo_mase"]
                                    - frozen["selection"]["leader"]["lopo_mase"]) < 1e-9),
        "fallback_to_most_conservative": full["selection"]["fallback_to_most_conservative"],
    }
    consistency["consistent"] = all(consistency[k] for k in (
        "k_match", "beta_match", "cap_match", "anchor_match", "lopo_mase_match"))

    selection_payload = {
        "stage": "v53-state-compact-selection",
        "backbone": args.backbone,
        "bank_blocks": args.bank_blocks,
        "replay": args.replay,
        "module": "introact_ts.v47.select",
        "code_sha256": code_hashes,
        "episodes": len(bank_catalogs),
        "parents": int(len({c.parent for c in bank_catalogs})),
        "sources": int(len({c.source for c in bank_catalogs})),
        "test_records_read": test_reads_in_selection,
        "consistency_with_frozen_full22": consistency,
        "variants": {},
    }
    for variant, pack in selections.items():
        selection_payload["variants"][variant] = {
            "blocks": list(pack["blocks"]),
            "state_dim": int(len(SEL.blocks_slice_length(pack["blocks"]))),
            "harm_cap": pack["harm_cap"],
            "selection": pack["selection"],
            "runtime_seconds": pack["runtime_seconds"],
        }
    write(out / f"selection_{args.backbone}.json", clean(selection_payload))

    # ---------------- evaluation phase (frozen per-variant k, beta) -------
    blocks_wanted = [b.strip() for b in args.blocks.split(",")]
    evaluation: dict[str, dict] = {v: {} for v in VARIANTS}
    realised_mase: dict[str, dict[str, np.ndarray]] = {v: {} for v in VARIANTS}
    eval_queries: dict[str, SEL.Queries] = {}
    for variant, pack in selections.items():
        k = int(pack["selection"]["selected"]["k"])
        beta = float(pack["selection"]["selected"]["beta"])
        blocks = pack["blocks"]
        for block in blocks_wanted:
            queries, selected = evaluate(root, args.backbone, pack["bank"],
                                         blocks, k, beta, block)
            if variant == "FULL22":
                eval_queries[block] = queries
            row = summarise(queries, selected, variant)
            row["k"] = k
            row["beta"] = beta
            evaluation[variant][block] = row
            realised_mase[variant][block] = SEL.realised(queries, selected)

    comparisons = {}
    for block in ("train_eval", "test"):
        if block not in eval_queries:
            continue
        comparisons[f"FULL22_minus_COMPACT17@{block}"] = SEL.paired_cluster_bootstrap(
            eval_queries[block], realised_mase["FULL22"][block],
            realised_mase["COMPACT17"][block], resamples=args.resamples)

    evaluation_payload = {
        "stage": "v53-state-compact-evaluation",
        "backbone": args.backbone,
        "bank_blocks": args.bank_blocks,
        "replay": args.replay,
        "module": "introact_ts.v47.select",
        "code_sha256": code_hashes,
        "blocks": blocks_wanted,
        "episodes": {b: int(len(eval_queries[b].episode)) for b in eval_queries},
        "selected": {v: selections[v]["selection"]["selected"] for v in VARIANTS},
        "rows": evaluation,
        "comparisons": comparisons,
        "runtime_seconds": time.perf_counter() - began,
    }
    write(out / f"evaluation_{args.backbone}.json", clean(evaluation_payload))

    print(json.dumps(clean({
        "backbone": args.backbone,
        "consistency": consistency,
        "selected": {v: selections[v]["selection"]["selected"] for v in VARIANTS},
        "cap": {v: selections[v]["selection"]["cap"] for v in VARIANTS},
        "fallback": {v: selections[v]["selection"]["fallback_to_most_conservative"]
                     for v in VARIANTS},
        "feasible": {v: selections[v]["selection"]["feasible_settings"]
                     for v in VARIANTS},
        "mase": {v: {b: evaluation[v][b]["mase"] for b in evaluation[v]}
                 for v in VARIANTS},
        "intervention_rate": {v: {b: evaluation[v][b]["intervention_rate"]
                                  for b in evaluation[v]} for v in VARIANTS},
        "harmful_loss": {v: {b: evaluation[v][b]["harmful_loss"]
                             for b in evaluation[v]} for v in VARIANTS},
        "comparisons": {k2: [v2["difference"], v2["ci_low"], v2["ci_high"],
                             v2["p_value"], v2["excludes_zero"]]
                        for k2, v2 in comparisons.items()},
    }), indent=1))


if __name__ == "__main__":
    main()
