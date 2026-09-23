#!/usr/bin/env python3
"""One-shot confirmatory evaluation on Solar and US Term Structure.

Neither source took part in any design decision, so this is the only place in
the paper where a number is produced without the possibility of having been
tuned on it.  The procedure is the main-set procedure with nothing removed and
nothing added: build the replay bank from the confirmatory bankx block, choose
``(k, beta, lam)`` by leave one parent out under the same harm cap and the same
one standard error rule, calibrate the execution threshold on the confirmatory
internal block, then evaluate once on the confirmatory TEST block and stop.

The script refuses to run twice over an existing result unless ``--overwrite``
is given, because a confirmatory evaluation that can be repeated until it looks
right is not one.

usage: v55_confirmatory_evaluate.py --backbone bolt
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import state as ST
from introact_ts.v47 import select as SEL
from introact_ts.v55 import select as V55

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import ROOT, clean, code_hashes, sha, write
from v47_evaluate import missed_opportunity, summarise
from v53_source_fixed import apply_source_fixed
from v55_select_1se import one_se_pick

CONF_REPLAY = "results/v54/confirmatory/replay"
OUT = ROOT / "results/v55/confirmatory"
ALPHA_GRID = (0.01, 0.02, 0.03, 0.05)


def source_fixed_policy(bank: SEL.Bank) -> dict:
    """Per-source fixed action, over the sources this bank actually holds.

    The main-set helper reads the eight-source registry, which does not contain
    the confirmatory sources, so the policy is built from the bank itself.  The
    rule is unchanged: the non-reference action with the highest mean realised
    utility on that source's bank records, with the reference as the fallback
    when no action has support there.
    """
    sources = set()
    for action in SEL.ACTIONS:
        sources.update(str(s) for s in bank.per[action].source)
    policy = {}
    for source in sorted(sources):
        stats = {}
        for action in SEL.NONREF:
            b = bank.per[action]
            take = np.asarray([str(s) == source for s in b.source])
            if not take.any():
                stats[action] = {"support": 0, "mean_utility": None}
                continue
            stats[action] = {"support": int(take.sum()),
                             "mean_utility": float(b.g[take].mean())}
        usable = {a: v["mean_utility"] for a, v in stats.items()
                  if v["mean_utility"] is not None}
        chosen = max(usable, key=lambda a: usable[a]) if usable else SEL.REFERENCE
        policy[source] = {"action": chosen, "fallback": SEL.REFERENCE,
                          "candidates": stats}
    return policy


def load(root: Path, block: str, backbone: str):
    C.REPLAY = CONF_REPLAY
    return C.load_catalog(root, block, backbone)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--backbone", default="bolt")
    ap.add_argument("--bank-block", default="bankx")
    ap.add_argument("--calibration-block", default="train_eval")
    ap.add_argument("--blocks", default="test,test_m2,test_m3")
    ap.add_argument("--resamples", type=int, default=2000)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    target = OUT / f"{args.backbone}.json"
    if target.exists() and not args.overwrite:
        raise SystemExit(f"{target} already exists; a confirmatory evaluation is "
                         "run once, pass --overwrite only to repair a crash")

    blocks = SEL.blocks_of()
    bank_catalogs = load(root, args.bank_block, args.backbone)
    bank = SEL.Bank(bank_catalogs, blocks=blocks)
    bank_queries = SEL.Queries(bank_catalogs, blocks=blocks)

    cap = SEL.harm_cap(bank, bank_queries)
    chosen = V55.select_hyperparameters(bank, bank_queries, cap=cap["cap"])
    if chosen.get("selected") is not None:
        pick = one_se_pick(chosen["grid"], cap["cap"])
        chosen["min_rule_selected"] = dict(chosen["selected"])
        chosen["selected"] = {"k": pick["k"], "beta": pick["beta"],
                              "lam": pick["lam"], "lam_is_inf": pick["lam_is_inf"]}
        chosen["rule"] = "one standard error, least intervening, as on the main set"
    config = V55.frozen_config(chosen)

    payload = {
        "stage": "v55-confirmatory-evaluation",
        "state_version": ST.STATE_VERSION,
        "backbone": args.backbone,
        "replay": CONF_REPLAY,
        "sources": sorted({c.source for c in bank_catalogs}),
        "bank_episodes": len(bank_catalogs),
        "bank_parents": int(len({c.parent for c in bank_catalogs})),
        "harm_cap": cap,
        "selection": {k: v for k, v in chosen.items() if k != "grid"},
        "protocol_note": "same catalogue, same state, same harm cap, same "
                         "selection rule and same statistics as the main set; "
                         "the only change is the data, which took no part in any "
                         "design decision",
    }

    if config is None:
        payload["keep_only"] = True
        payload["blocks"] = {}
        write(target, clean(payload))
        print(json.dumps({"backbone": args.backbone, "keep_only": True}))
        return

    k, beta, lam = config
    means = V55.source_action_means(bank)

    cal_catalogs = load(root, args.calibration_block, args.backbone)
    cal_q = SEL.Queries(cal_catalogs, blocks=blocks)
    cal_D = SEL.distance_matrices(bank, cal_q, lopo=False)
    cal_scores = V55.scores_from_moments(
        V55.local_moments(bank, cal_q, cal_D, k), means, cal_q, beta, lam)
    levels = []
    for alpha in ALPHA_GRID:
        fit = V55.conformal_threshold(cal_q, cal_scores, alpha)["selected"]
        levels.append({"alpha": alpha, "threshold": fit["threshold"],
                       "calibration_harm": fit["empirical_harm"],
                       "crc_bound": fit["crc_bound"]})
    payload["conformal"] = {"calibration_block": args.calibration_block,
                            "calibration_episodes": len(cal_catalogs),
                            "levels": levels}

    policy = source_fixed_policy(bank)
    fixed = SEL.best_fixed_action(bank)
    payload["blocks"] = {}
    for block in args.blocks.split(","):
        block = block.strip()
        catalogs = load(root, block, args.backbone)
        q = SEL.Queries(catalogs, blocks=blocks)
        D = SEL.distance_matrices(bank, q, lopo=False)
        scores = V55.scores_from_moments(
            V55.local_moments(bank, q, D, k), means, q, beta, lam)
        n = len(catalogs)
        decisions = {
            "NATIVE_KEEP": np.full(n, SEL.REFERENCE, dtype=object),
            "BEST_FIXED": SEL.apply_fixed(q, fixed),
            "SOURCE_FIXED": apply_source_fixed(q, policy)[0],
            "FIXED_SAITS": SEL.apply_fixed(q, "SAITS"),
            "R2_CART": SEL.r2_cart(bank, q),
            "FULL_INTROACT": V55.decide(q, scores, threshold=0.0),
            "E_LOCAL_ONLY": V55.decide(
                q, V55.scores_from_moments(
                    V55.local_moments(bank, q, D, k), means, q, beta, 0.0)),
            "CATALOG_ORACLE": SEL.oracle(q),
        }
        for item in V55.crossfit_conformal(q, scores, ALPHA_GRID):
            label = "CROSSFIT_A%s" % ("%.3f" % item["alpha"]).replace("0.", "").rstrip("0")
            decisions[label] = V55.decide_with_mask(q, scores, item["applied"])
        rows = {name: summarise(q, sel, name) for name, sel in decisions.items()}
        for name, sel in decisions.items():
            rows[name]["missed_opportunity"] = missed_opportunity(q, sel, 1e-9)
            rows[name]["harm_clipped"] = float(V55.harm_per_request(q, sel).mean())
        mase_of = {name: SEL.realised(q, sel) for name, sel in decisions.items()}
        comparisons = {}
        for ref in ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "FIXED_SAITS",
                    "R2_CART", "E_LOCAL_ONLY"):
            comparisons[f"FULL_INTROACT_vs_{ref}"] = SEL.paired_cluster_bootstrap(
                q, mase_of["FULL_INTROACT"], mase_of[ref], resamples=args.resamples)
        family = {f"FULL_INTROACT_vs_{r}": comparisons[f"FULL_INTROACT_vs_{r}"]["p_value"]
                  for r in ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED",
                            "FIXED_SAITS", "R2_CART")}
        adjusted = SEL.holm(family)
        for key, value in adjusted.items():
            comparisons[key]["p_holm"] = value
            comparisons[key]["significant_holm"] = bool(value < 0.05)
        payload["blocks"][block] = {
            "episodes": n,
            "parents": int(len({c.parent for c in catalogs})),
            "sources": sorted({c.source for c in catalogs}),
            "rows": rows, "comparisons": comparisons}

    payload["frozen"] = {"k": k, "beta": beta,
                         "lam": (None if np.isinf(lam) else lam),
                         "lam_is_inf": bool(np.isinf(lam)),
                         "best_fixed_action": fixed,
                         "source_fixed_policy": {s: p["action"]
                                                 for s, p in policy.items()}}
    payload["code_sha256"] = code_hashes(root) | {
        "scripts/v55_confirmatory_evaluate.py": sha(Path(__file__).resolve()),
        "src/introact_ts/v55/select.py": sha(root / "src/introact_ts/v55/select.py")}
    payload["runtime_seconds"] = time.perf_counter() - began
    write(target, clean(payload))
    print(json.dumps(clean({
        "backbone": args.backbone, "frozen": payload["frozen"],
        "test": {name: row["mase"]
                 for name, row in payload["blocks"]["test"]["rows"].items()},
        "diffs": {key: {"difference": c["difference"], "ci_low": c["ci_low"],
                        "ci_high": c["ci_high"], "p_holm": c.get("p_holm")}
                  for key, c in payload["blocks"]["test"]["comparisons"].items()},
    }), indent=1))


if __name__ == "__main__":
    main()
