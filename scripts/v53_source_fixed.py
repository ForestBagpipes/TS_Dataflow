#!/usr/bin/env python3
"""v53 source-level diagnostics (review plan diagnostic-B).

* Part A -- source-level fixed policy.  For each of the eight sources, one
  fixed action is chosen using TRAIN-side (replay bank) data only: the action
  with the highest mean realised utility on that source's bank records.  The
  pre-registered fallback for a request where the chosen action is not
  available is KEEP, and the fallback count is recorded per source.  The
  policy is then applied unchanged on TEST (no test-side adjustment) and its
  source-macro MASE is compared with FULL_INTROACT and BEST_FIXED.

* Part B -- leave-one-source-out sensitivity.  On the existing TEST results,
  each of the eight sources is left out in turn and the source-macro MASE of
  FULL_INTROACT and of every main control (NATIVE_KEEP, BEST_FIXED, R2_CART,
  FIXED_SAITS, TATO) is recomputed on the remaining seven sources, so the
  table shows whether FULL's advantage concentrates in a few sources.

Everything is computed offline from the frozen replay cache and the published
TATO records; no model is run.  Outputs go to ``results/v53_state_compact/``.
"""

from __future__ import annotations

import argparse
import collections
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


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_fixed_policy(bank: SEL.Bank) -> dict:
    """Per-source action choice on TRAIN-side bank utility, KEEP fallback."""
    policy = {}
    for source in P.SOURCES:
        stats = {}
        for action in SEL.NONREF:
            b = bank.per[action]
            take = b.source == source
            if not take.any():
                stats[action] = {"support": 0, "mean_utility": None}
                continue
            g = b.g[take]
            stats[action] = {"support": int(take.sum()),
                             "mean_utility": float(g.mean())}
        usable = {a: s["mean_utility"] for a, s in stats.items()
                  if s["mean_utility"] is not None}
        chosen = max(usable, key=lambda a: usable[a]) if usable else SEL.REFERENCE
        policy[source] = {"action": chosen, "fallback": SEL.REFERENCE,
                          "candidates": stats}
    return policy


def apply_source_fixed(queries: SEL.Queries, policy: dict):
    sel = np.full(len(queries.episode), SEL.REFERENCE, dtype=object)
    fallback_counts = collections.Counter()
    for i in range(len(queries.episode)):
        action = policy[queries.source[i]]["action"]
        if action != SEL.REFERENCE and queries.legal[action][i]:
            sel[i] = action
        elif action != SEL.REFERENCE:
            fallback_counts[queries.source[i]] += 1
    return sel, dict(fallback_counts)


def load_tato_mase(root: Path, block: str, backbone: str,
                   queries: SEL.Queries) -> np.ndarray | None:
    path = root / f"results/v47/baselines/tato_{block}_{backbone}/records.json"
    if not path.exists():
        return None
    records = json.loads(path.read_text())["records"]
    mase = np.full(len(queries.episode), np.nan)
    for i, episode in enumerate(queries.episode):
        item = records.get(episode)
        if item is not None and item.get("mase") is not None:
            mase[i] = item["mase"]
    return mase if np.isfinite(mase).any() else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--bank-blocks", default="bankx")
    parser.add_argument("--block", default="test")
    parser.add_argument("--resamples", type=int, default=P.BOOTSTRAP_RESAMPLES)
    parser.add_argument("--replay", default="results/v47/replay")
    parser.add_argument("--protocol-dir", default="results/v47/protocol")
    parser.add_argument("--output-root", default="results/v53_state_compact")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    out = root / args.output_root
    C.REPLAY = args.replay

    freeze = root / args.protocol_dir / f"selection_{args.backbone}.json"
    selection = json.loads(freeze.read_text())
    k = int(selection["selection"]["selected"]["k"])
    beta = float(selection["selection"]["selected"]["beta"])

    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(C.load_catalog(root, name.strip(), args.backbone))
    bank = SEL.Bank(bank_catalogs, blocks=SEL.blocks_of())

    catalogs = C.load_catalog(root, args.block, args.backbone)
    queries = SEL.Queries(catalogs, blocks=SEL.blocks_of())
    sources = sorted({c.source for c in catalogs})

    # ---------------- part A: source-level fixed policy -------------------
    policy = source_fixed_policy(bank)
    source_sel, fallback_counts = apply_source_fixed(queries, policy)

    D = SEL.distance_matrices(bank, queries, lopo=False)
    full_sel = SEL.decide(queries, SEL.score_grid(bank, queries, D, k, beta))
    fixed_action = SEL.best_fixed_action(bank)
    decisions = {
        "FULL_INTROACT": full_sel,
        "SOURCE_FIXED": source_sel,
        "BEST_FIXED": SEL.apply_fixed(queries, fixed_action),
        "NATIVE_KEEP": np.full(len(queries.episode), SEL.REFERENCE, dtype=object),
        "R2_CART": SEL.r2_cart(bank, queries),
        "FIXED_SAITS": SEL.apply_fixed(queries, "SAITS"),
    }
    rows = {name: summarise(queries, sel, name) for name, sel in decisions.items()}
    mase_of = {name: SEL.realised(queries, sel) for name, sel in decisions.items()}

    tato_mase = load_tato_mase(root, args.block, args.backbone, queries)
    if tato_mase is not None:
        rows["TATO"] = {
            "method": "TATO",
            "mase": SEL.source_macro(queries, tato_mase),
            "rmsse": float("nan"),
            "intervention_rate": 1.0,
            "scored": int(np.isfinite(tato_mase).sum()),
        }
        mase_of["TATO"] = tato_mase

    comparisons = {}
    for name in ("SOURCE_FIXED", "BEST_FIXED", "NATIVE_KEEP", "R2_CART", "FIXED_SAITS"):
        comparisons[f"FULL_INTROACT_vs_{name}"] = SEL.paired_cluster_bootstrap(
            queries, mase_of["FULL_INTROACT"], mase_of[name],
            resamples=args.resamples)
    if tato_mase is not None:
        both = np.isfinite(mase_of["FULL_INTROACT"]) & np.isfinite(tato_mase)
        comparisons["FULL_INTROACT_vs_TATO"] = {
            "note": "TATO is forecast-returning; unpaired macro difference",
            "difference": float(SEL.source_macro(queries, mase_of["FULL_INTROACT"])
                                - SEL.source_macro(queries, tato_mase)),
            "paired_episodes": int(both.sum())}

    # ---------------- part B: leave-one-source-out ------------------------
    loo_rows = []
    controls = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FIXED_SAITS")
    if tato_mase is not None:
        controls = controls + ("TATO",)
    for left_out in sources:
        mask = queries.source != left_out
        entry = {"left_out": left_out}
        macros = {}
        for name in ("FULL_INTROACT",) + controls:
            m = np.where(mask, mase_of[name], np.nan)
            macros[name] = SEL.source_macro(queries, m)
        entry["macro_mase"] = macros
        entry["full_minus_control"] = {
            name: (macros["FULL_INTROACT"] - macros[name]
                   if np.isfinite(macros[name]) else None)
            for name in controls}
        loo_rows.append(entry)

    full_range = {}
    for name in controls:
        diffs = [r["full_minus_control"][name] for r in loo_rows
                 if r["full_minus_control"][name] is not None]
        full_range[name] = {"min": float(min(diffs)), "max": float(max(diffs)),
                            "n_negative": int(sum(1 for d in diffs if d < 0))}

    payload = {
        "stage": "v53-source-fixed-and-leaveout",
        "backbone": args.backbone,
        "block": args.block,
        "bank_blocks": args.bank_blocks,
        "replay": args.replay,
        "module": "introact_ts.v47.select",
        "code_sha256": {
            "scripts/v53_source_fixed.py": sha256_of(Path(__file__).resolve()),
            "src/introact_ts/v47/select.py": sha256_of(root / "src/introact_ts/v47/select.py"),
        },
        "frozen": {"k": k, "beta": beta, "best_fixed_action": fixed_action},
        "episodes": int(len(queries.episode)),
        "sources": sources,
        "part_a": {
            "policy_rule": ("per-source argmax of mean realised utility on the "
                            "replay bank (TRAIN side only); pre-registered "
                            "fallback KEEP when the action is unavailable"),
            "policy": policy,
            "fallback_counts_on_eval": fallback_counts,
            "rows": rows,
            "comparisons": comparisons,
        },
        "part_b": {
            "rule": ("source-macro MASE recomputed on the remaining seven "
                     "sources per left-out source; entries are "
                     "FULL_INTROACT macro minus control macro"),
            "rows": loo_rows,
            "difference_range": full_range,
        },
        "runtime_seconds": time.perf_counter() - began,
    }
    write(out / f"source_fixed_{args.backbone}.json", clean(payload))

    print(json.dumps(clean({
        "backbone": args.backbone, "block": args.block,
        "policy": {s: p["action"] for s, p in policy.items()},
        "fallback_counts": fallback_counts,
        "mase": {name: rows[name]["mase"] for name in rows},
        "vs": {key: [v.get("difference"), v.get("ci_low"), v.get("ci_high")]
               for key, v in comparisons.items()},
        "loo": [{"left_out": r["left_out"], **r["full_minus_control"]}
                for r in loo_rows],
    }), indent=1))


if __name__ == "__main__":
    main()
