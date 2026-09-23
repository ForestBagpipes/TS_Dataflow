#!/usr/bin/env python3
"""Emit the appendix tables from the v55 records.

The appendix carries the breakdowns the main text points at, and every one of
them has to come from the same evaluation payloads as the main table.  This
script is the only producer.  It prints each table body under a banner so the
patcher can find it, and a row the evaluation does not carry is reported as
missing rather than filled in.

usage: v55_appendix_tables.py [--results results/v55]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BACKBONES = ("bolt", "timesfm", "chronos2")
BLOCKS = {"test": r"$10\%$", "test30": r"$30\%$", "test50": r"$50\%$"}
SEEDS = ("test", "test_m2", "test_m3")

ROSTER = [
    ("NATIVE_KEEP", r"\textsc{Native Keep}"),
    ("BEST_FIXED", r"\textsc{Best Fixed}"),
    ("SOURCE_FIXED", r"Source Fixed"),
    ("R2_CART", r"R2-CART"),
    ("FIXED_SAITS", r"Fixed SAITS"),
    ("TATO", r"TATO"),
    ("TIMESNET", r"TimesNet"),
    ("PSW_I", r"PSW-I"),
    ("T1", r"T1"),
]
OURS = ("FULL_INTROACT", r"\introact{}")

ABLATION = [
    ("FULL_INTROACT", r"Full \introact{}"),
    ("E_LOCAL_ONLY", r"Neighbourhood only ($\lambda=0$)"),
    ("E_SOURCE_ONLY", r"Source mean only ($\lambda=\infty$)"),
    ("A1_GLOBAL_UTILITY", r"No retrieval"),
    ("A5_PARAMETRIC_RIDGE", r"Linear utility model"),
    ("A2_WO_ACTION_COND", r"No action conditioning"),
    ("A2_WO_INTERVENTION", r"No candidate-difference features"),
    ("A3_WO_FORECAST", r"No reference-forecast features"),
    ("A4_ALWAYS_ACT", r"No execution gate"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results/v55")
    args = ap.parse_args()
    root = Path(args.results)

    def pay(block):
        return {bb: json.loads((root / "evaluation" / f"{block}_{bb}.json").read_text())
                for bb in BACKBONES}

    data = {b: pay(b) for b in list(BLOCKS) + ["test_m2", "test_m3"]}

    def has(block, key):
        return all(key in data[block][bb]["rows"] for bb in BACKBONES)

    def val(block, key, field="mase"):
        vals = [data[block][bb]["rows"][key][field] for bb in BACKBONES]
        return sum(vals) / len(vals)

    present = [(k, lab) for k, lab in ROSTER if has("test", k)] + [OURS]

    for block, label in BLOCKS.items():
        print(f"%%% SEVERITY_TABLE {block}")
        for key, lab in present:
            if not has(block, key):
                print(f"% {key} missing in {block}")
                continue
            prefix = r"\rowcolor{bestgray}" if key == OURS[0] else ""
            if key == OURS[0]:
                print(r"    \midrule")
            print("    %s%s & %.3f & %.3f \\\\" % (
                prefix, lab, val(block, key), val(block, key, "rmsse")))

    print("%%% SEVERITY_TREND")
    for key, lab in present:
        cells = []
        ok = True
        for bb in BACKBONES:
            for block in BLOCKS:
                row = data[block][bb]["rows"].get(key)
                if row is None:
                    ok = False
                    break
                cells.append("%.3f" % row["mase"])
        if not ok:
            print(f"% {key} missing")
            continue
        print("    %s & %s \\\\" % (lab, " & ".join(cells)))

    print("%%% MASK_SEEDS")
    for key, lab in present:
        cells = [("%.3f" % val(block, key)) if has(block, key) else "--"
                 for block in SEEDS]
        finite = [val(block, key) for block in SEEDS if has(block, key)]
        span = ("%.3f [%.3f, %.3f]" % (sum(finite) / len(finite), min(finite),
                                       max(finite))) if finite else "--"
        print("    %s & %s & %s \\\\" % (lab, " & ".join(cells), span))

    print("%%% ABLATION_DETAIL")
    for key, lab in ABLATION:
        if not has("test", key):
            print(f"% {key} missing")
            continue
        diffs = []
        for bb in BACKBONES:
            c = data["test"][bb]["comparisons"].get(f"FULL_INTROACT_vs_{key}")
            diffs.append("--" if c is None else
                         "$%+.3f$ [$%+.3f$, $%+.3f$]" % (c["difference"],
                                                        c["ci_low"], c["ci_high"]))
        print("    %s & %.3f & %.1f\\%% & %.4f & %s \\\\" % (
            lab, val("test", key), 100 * val("test", key, "intervention_rate"),
            val("test", key, "harmful_loss"), " & ".join(diffs)))

    print("%%% BANKSIZE")
    rows = {}
    for bb in BACKBONES:
        path = root / "ablations" / f"banksize_test_{bb}.json"
        if not path.exists():
            print(f"% banksize missing for {bb}")
            continue
        for item in json.loads(path.read_text())["rows"]:
            rows.setdefault(item["fraction"], []).append(item)
    for fraction in sorted(rows):
        items = rows[fraction]
        if len(items) != len(BACKBONES):
            continue
        mean = lambda f: sum(i[f] for i in items) / len(items)
        print("    $%d\\%%$ & %.3f & %.1f\\%% & %.1f\\%% & %.4f \\\\" % (
            round(100 * fraction), mean("mase"), 100 * mean("intervention_rate"),
            100 * mean("conditional_hir"), mean("harmful_loss")))

    print("%%% GATE_CONTROLS")
    label = {"GATE_DISPERSION": r"Full rule", "GATE_MEAN_ONLY": r"Mean only",
             "GATE_LINEAR": r"Linear score", "GATE_RANDOM": r"Random execution"}
    for bb in BACKBONES:
        path = root / "gate_controls" / f"{bb}.json"
        if not path.exists():
            print(f"% gate controls missing for {bb}")
            continue
        block = json.loads(path.read_text())["blocks"]["test"]
        for name in ("GATE_DISPERSION", "GATE_MEAN_ONLY", "GATE_LINEAR",
                     "GATE_RANDOM"):
            row = block["rows"][name]
            comp = block["comparisons"].get(f"GATE_DISPERSION_vs_{name}")
            diff = ("--" if comp is None else
                    "$%+.4f$ [$%+.4f$, $%+.4f$]" % (comp["difference"],
                                                    comp["ci_low"], comp["ci_high"]))
            print("    %s & %s & %.3f & %.1f\\%% & %.4f & %s \\\\" % (
                bb, label[name], row["mase"], 100 * row["intervention_rate"],
                row["harmful_loss"], diff))

    print("%%% CALLS")
    for key, lab in present:
        if not has("test", key):
            continue
        rate = val("test", key, "intervention_rate")
        print("    %s & %.2f & %.1f\\%% \\\\" % (lab, 1.0 + rate, 100 * rate))


if __name__ == "__main__":
    main()
