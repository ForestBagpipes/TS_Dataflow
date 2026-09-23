#!/usr/bin/env python3
"""Emit every headline number the manuscript quotes, straight out of results/v55.

One producer for the main comparison table, the estimator and gate ablation
table, the paired differences the prose quotes, and the calibrated gate
operating points.  A row the evaluation does not carry is printed as missing and
never invented.

usage: v55_paper_tables.py [--block test] [--results results/v55]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BACKBONES = ("bolt", "timesfm", "chronos2")
LABEL = {"bolt": "Bolt", "timesfm": "TimesFM", "chronos2": "Chronos-2"}

ROSTER = [
    ("NATIVE_KEEP", r"Native KEEP"),
    ("BEST_FIXED", r"Best Fixed"),
    ("SOURCE_FIXED", r"Source Fixed"),
    ("FIXED_SAITS", r"Fixed SAITS"),
    ("R2_CART", r"R2-CART"),
    ("TATO", r"TATO"),
    ("TIMESNET", r"TimesNet"),
    ("PSW_I", r"PSW-I"),
    ("T1", r"T1"),
]
OURS = ("FULL_INTROACT", r"\introact{}")
ORACLE = ("CATALOG_ORACLE", r"Catalog Oracle")

ABLATION = [
    ("FULL_INTROACT", r"Full \introact{}"),
    ("E_LOCAL_ONLY", r"Neighbourhood only ($\lambda=0$)"),
    ("E_SOURCE_ONLY", r"Source mean only ($\lambda=\infty$)"),
    ("A1_GLOBAL_UTILITY", r"No retrieval"),
    ("A5_PARAMETRIC_RIDGE", r"Linear utility model"),
    ("A4_ALWAYS_ACT", r"No execution gate"),
    ("A2_WO_ACTION_COND", r"No action conditioning"),
]

CONTROLS = ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "R2_CART",
            "FIXED_SAITS", "TATO", "TIMESNET", "PSW_I", "T1",
            "E_LOCAL_ONLY", "E_SOURCE_ONLY", "A1_GLOBAL_UTILITY",
            "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE", "A2_WO_ACTION_COND")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", default="test")
    ap.add_argument("--results", default="results/v55")
    args = ap.parse_args()
    root = Path(args.results)
    pay = {bb: json.loads((root / "evaluation" / f"{args.block}_{bb}.json").read_text())
           for bb in BACKBONES}

    def has(key):
        return all(key in pay[bb]["rows"] for bb in BACKBONES)

    def mase(key, bb):
        return pay[bb]["rows"][key]["mase"]

    def overall(key):
        return sum(mase(key, bb) for bb in BACKBONES) / len(BACKBONES)

    def field(key, bb, name):
        return pay[bb]["rows"][key].get(name)

    def overall_field(key, name):
        vals = [field(key, bb, name) for bb in BACKBONES]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    print(f"% block={args.block}  frozen=" + json.dumps(
        {bb: {k: pay[bb]["frozen"][k] for k in ("k", "beta", "lam")}
         for bb in BACKBONES}))
    missing = [k for k, _ in ROSTER if not has(k)]
    print(f"% rows absent from the evaluation: {missing if missing else 'none'}")

    present = [(k, lab) for k, lab in ROSTER if has(k)]
    order = present + [OURS]
    best, second = {}, {}
    for col in list(BACKBONES) + ["overall"]:
        vals = ({k: overall(k) for k, _ in order} if col == "overall"
                else {k: mase(k, col) for k, _ in order})
        rank = sorted(vals, key=lambda k: vals[k])
        best[col], second[col] = rank[0], (rank[1] if len(rank) > 1 else None)

    def cell(key, col, value):
        text = f"{value:.3f}"
        if key == best[col]:
            return rf"\best{{{text}}}"
        if key == second[col]:
            return rf"\second{{{text}}}"
        return text

    print("\n%%% MAIN TABLE BODY")
    for key, lab in order:
        if key == OURS[0]:
            print(r"    \midrule")
        cells = [cell(key, bb, mase(key, bb)) for bb in BACKBONES]
        cells.append(cell(key, "overall", overall(key)))
        cells.append(f"{overall_field(key, 'intervention_rate'):.3f}")
        prefix = r"\rowcolor{bestgray}" if key == OURS[0] else ""
        print(f"{prefix}{lab} & " + " & ".join(cells) + r" \\")
    print(r"    \midrule")
    oc = [rf"\oracle{{{mase(ORACLE[0], bb):.3f}}}" for bb in BACKBONES]
    oc.append(rf"\oracle{{{overall(ORACLE[0]):.3f}}}")
    oc.append(rf"\oracle{{{overall_field(ORACLE[0], 'intervention_rate'):.3f}}}")
    print(f"{ORACLE[1]} & " + " & ".join(oc) + r" \\")

    print("\n%%% ABLATION TABLE BODY (aggregate over the three backbones)")
    for key, lab in ABLATION:
        if not has(key):
            print(f"% {key} missing")
            continue
        print("%s & %.3f & %.1f\\%% & %.1f\\%% & %.4f \\\\" % (
            lab, overall(key),
            100 * overall_field(key, "intervention_rate"),
            100 * overall_field(key, "conditional_hir"),
            overall_field(key, "harmful_loss")))

    print("\n%%% PAIRED DIFFERENCES (FULL minus control)")
    for c in CONTROLS:
        if not has(c):
            continue
        parts = []
        for bb in BACKBONES:
            d = pay[bb]["comparisons"].get(f"FULL_INTROACT_vs_{c}")
            if d is None:
                parts.append(f"{LABEL[bb]}: --")
                continue
            star = "*" if d.get("significant_holm") else ""
            parts.append("%s %+.4f [%+.4f,%+.4f] p=%.4f%s"
                         % (LABEL[bb], d["difference"], d["ci_low"],
                            d["ci_high"], d["p_value"], star))
        print(f"{c:20s} " + " | ".join(parts))

    print("\n%%% CALIBRATED GATE, thresholds fitted on the internal block")
    for bb in BACKBONES:
        for r in pay[bb].get("conformal_rows", []):
            print("%-9s alpha=%.2f thr=%.4f realised=%.4f respected=%s ir=%.3f"
                  % (bb, r["alpha"], r["threshold"], r["realised_harm"],
                     r["respected"], r["realised_intervention_rate"]))

    print("\n%%% CALIBRATED GATE, thresholds refitted on completed requests")
    for bb in BACKBONES:
        for r in pay[bb].get("crossfit_conformal_rows", []):
            print("%-9s alpha=%.2f realised=%.4f respected=%s ir=%.3f mase=%.4f"
                  % (bb, r["alpha"], r["realised_harm"], r["respected"],
                     r["intervention_rate"], r["realised_mase"]))

    print("\n%%% OVERALL SOURCE-MACRO MASE")
    for key, _ in order + [ORACLE] + [(k, None) for k, _ in ABLATION
                                      if has(k) and k != OURS[0]]:
        print(f"{key:22s} {overall(key):.4f}")


if __name__ == "__main__":
    main()
