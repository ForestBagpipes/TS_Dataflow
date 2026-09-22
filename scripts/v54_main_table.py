#!/usr/bin/env python3
"""v54 main table: three mask-seed blocks paired, per backbone.

Reads ``results/v54/evaluation/{test,test_m2,test_m3}_{backbone}.json`` and
aggregates:

* per method: source-macro MASE on each seed block, the three-seed mean and
  the [min, max] seed range;
* FULL_INTROACT vs every pre-declared comparison row (BEST_FIXED,
  SOURCE_FIXED, R2_CART, FIXED_SAITS, TATO, NATIVE_KEEP): the paired
  difference with its parent-clustered bootstrap CI and Holm-adjusted p on
  each seed block, the mean difference across seeds, and whether all three
  seed CIs exclude zero.

Writes ``results/v54/main_table.json`` and a human-readable
``results/v54/main_table.md``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import BACKBONES, OUT, ROOT, clean, write

SEED_BLOCKS = ("test", "test_m2", "test_m3")
CONTROLS = ("BEST_FIXED", "SOURCE_FIXED", "R2_CART", "FIXED_SAITS", "TATO",
            "NATIVE_KEEP")

#: Table order for the human-readable rendering.
ROW_ORDER = ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "R2_CART",
             "FIXED_SAITS", "TATO", "FULL_INTROACT", "CATALOG_ORACLE",
             "A1_GLOBAL_UTILITY", "A2_WO_INTERVENTION", "A2_WO_ACTION_COND",
             "A3_WO_FORECAST", "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE")


def fmt(value, digits=4):
    return f"{value:.{digits}f}" if value is not None else "--"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()

    began = time.perf_counter()
    table = {}
    for backbone in BACKBONES:
        blocks = {}
        for block in SEED_BLOCKS:
            path = OUT / "evaluation" / f"{block}_{backbone}.json"
            if not path.exists():
                raise SystemExit(f"missing evaluation {path}; run v54_evaluate.py")
            blocks[block] = json.loads(path.read_text())

        methods = sorted({m for b in blocks.values() for m in b["rows"]})
        rows = {}
        for method in methods:
            per_seed = {}
            for block in SEED_BLOCKS:
                row = blocks[block]["rows"].get(method)
                per_seed[block] = row["mase"] if row else None
            values = [v for v in per_seed.values() if v is not None]
            rows[method] = {
                "per_seed_mase": per_seed,
                "seed_mean_mase": (float(sum(values) / len(values))
                                   if values else None),
                "seed_min": min(values) if values else None,
                "seed_max": max(values) if values else None,
                "intervention_rate": {
                    block: (blocks[block]["rows"][method]["intervention_rate"]
                            if method in blocks[block]["rows"] else None)
                    for block in SEED_BLOCKS},
            }

        comparisons = {}
        for control in CONTROLS:
            key = f"FULL_INTROACT_vs_{control}"
            per_seed = {}
            for block in SEED_BLOCKS:
                comp = blocks[block]["comparisons"].get(key)
                if comp is None:
                    continue
                per_seed[block] = {
                    "difference": comp["difference"],
                    "ci_low": comp["ci_low"],
                    "ci_high": comp["ci_high"],
                    "excludes_zero": comp["excludes_zero"],
                    "p_value": comp["p_value"],
                    "p_holm": comp.get("p_holm"),
                }
            diffs = [v["difference"] for v in per_seed.values()]
            comparisons[control] = {
                "per_seed": per_seed,
                "mean_difference": (float(sum(diffs) / len(diffs))
                                    if diffs else None),
                "all_seed_cis_exclude_zero": bool(
                    per_seed) and all(v["excludes_zero"]
                                      for v in per_seed.values()),
                "holm_significant_seeds": [b for b, v in per_seed.items()
                                           if v.get("p_holm") is not None
                                           and v["p_holm"] < 0.05],
            }

        table[backbone] = {
            "keep_only": blocks["test"]["frozen"]["keep_only"],
            "frozen": {"k": blocks["test"]["frozen"]["k"],
                       "beta": blocks["test"]["frozen"]["beta"]},
            "rows": rows,
            "full_introact_vs": comparisons,
            "average_rank": {block: blocks[block]["average_rank"]
                             for block in SEED_BLOCKS},
        }

    payload = {
        "stage": "v54-main-table",
        "state_version": "v54-full22",
        "seed_blocks": list(SEED_BLOCKS),
        "aggregation": ("per-block source-macro MASE from the paired evaluation "
                        "files; three-seed mean and [min, max] range; paired "
                        "differences are parent-clustered bootstrap (2000, seed "
                        "101) per block with Holm correction inside each block"),
        "backbones": table,
        "runtime_seconds": time.perf_counter() - began,
    }
    write(OUT / "main_table.json", clean(payload))

    # ---------------------------------------------------- human-readable md
    lines = ["# v54 main table (test / test_m2 / test_m3 paired seed blocks)",
             "",
             "Source-macro MASE; lower is better. FULL = FULL_INTROACT.",
             "Seed columns give the per-block value; mean [min, max] over the "
             "three mask seeds.", ""]
    for backbone in BACKBONES:
        info = table[backbone]
        frozen = info["frozen"]
        lines.append(f"## {backbone} "
                     f"(k={frozen['k']}, beta={frozen['beta']}, "
                     f"keep_only={info['keep_only']})")
        lines.append("")
        lines.append("| method | test | test_m2 | test_m3 | mean [min, max] | IR |")
        lines.append("|---|---|---|---|---|---|")
        ordered = [m for m in ROW_ORDER if m in info["rows"]]
        ordered += sorted(set(info["rows"]) - set(ordered))
        for method in ordered:
            r = info["rows"][method]
            ir = r["intervention_rate"]["test"]
            lines.append(
                f"| {method} | {fmt(r['per_seed_mase']['test'])} "
                f"| {fmt(r['per_seed_mase']['test_m2'])} "
                f"| {fmt(r['per_seed_mase']['test_m3'])} "
                f"| {fmt(r['seed_mean_mase'])} "
                f"[{fmt(r['seed_min'])}, {fmt(r['seed_max'])}] "
                f"| {fmt(ir, 3)} |")
        lines.append("")
        lines.append("FULL_INTROACT paired differences (parent-clustered "
                     "bootstrap 2000/seed 101, Holm within block):")
        lines.append("")
        lines.append("| control | mean diff | per-seed 95% CI | all CIs excl. 0 | Holm sig. seeds |")
        lines.append("|---|---|---|---|---|")
        for control, comp in info["full_introact_vs"].items():
            cis = "; ".join(
                f"{b}: [{fmt(v['ci_low'])}, {fmt(v['ci_high'])}]"
                for b, v in comp["per_seed"].items())
            lines.append(f"| {control} | {fmt(comp['mean_difference'])} "
                         f"| {cis} | {comp['all_seed_cis_exclude_zero']} "
                         f"| {', '.join(comp['holm_significant_seeds']) or '--'} |")
        lines.append("")
    (OUT / "main_table.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(clean({
        backbone: {
            "keep_only": info["keep_only"],
            "full_mase_mean": info["rows"].get("FULL_INTROACT", {})
            .get("seed_mean_mase"),
            "vs": {c: {"mean_difference": comp["mean_difference"],
                       "all_seed_cis_exclude_zero": comp["all_seed_cis_exclude_zero"]}
                   for c, comp in info["full_introact_vs"].items()},
        } for backbone, info in table.items()}), indent=1))


if __name__ == "__main__":
    main()
