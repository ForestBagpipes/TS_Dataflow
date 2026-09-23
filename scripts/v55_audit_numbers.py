#!/usr/bin/env python3
"""Check the numbers the manuscript prints against the records they come from.

The paper quotes a few dozen figures in prose and a few hundred in tables, and
the only way a reader can trust either is if both trace to the same payload.
This script re-reads the payloads, rebuilds every value the main text quotes,
and reports any that the manuscript does not contain.  It checks presence of the
exact printed string rather than parsing LaTeX, which is crude but catches the
failure that matters: a number left behind by an earlier run.

usage: v55_audit_numbers.py [--tex latex/IntroActTS_20260923_v56.tex]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BACKBONES = ("bolt", "timesfm", "chronos2")
ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results/v55"


def load(block):
    return {bb: json.loads((RESULTS / "evaluation" / f"{block}_{bb}.json").read_text())
            for bb in BACKBONES}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", default="latex/IntroActTS_20260923_v56.tex")
    args = ap.parse_args()
    tex = (ROOT / args.tex).read_text(encoding="utf-8")

    test = load("test")
    checks = []

    def expect(label, value, fmt="%.3f"):
        text = fmt % value
        checks.append((label, text, text in tex))

    rows = ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED", "R2_CART", "FIXED_SAITS",
            "TATO", "TIMESNET", "PSW_I", "T1", "FULL_INTROACT", "CATALOG_ORACLE")
    for row in rows:
        overall = sum(test[bb]["rows"][row]["mase"] for bb in BACKBONES) / 3
        expect(f"{row} overall MASE", overall)
        for bb in BACKBONES:
            expect(f"{row} {bb} MASE", test[bb]["rows"][row]["mase"])

    full = "FULL_INTROACT"
    expect("FULL repair rate",
           100 * sum(test[bb]["rows"][full]["intervention_rate"] for bb in BACKBONES) / 3,
           "%.1f")
    expect("FULL harmful loss",
           sum(test[bb]["rows"][full]["harmful_loss"] for bb in BACKBONES) / 3, "%.4f")

    for control in ("NATIVE_KEEP", "BEST_FIXED", "SOURCE_FIXED"):
        for bb in BACKBONES:
            comp = test[bb]["comparisons"].get(f"FULL_INTROACT_vs_{control}")
            if comp is None:
                continue
            expect(f"diff {control} {bb}", abs(comp["difference"]), "%.4f")

    conf = {bb: json.loads((RESULTS / "confirmatory" / f"{bb}.json").read_text())
            for bb in BACKBONES}
    for row in ("NATIVE_KEEP", "BEST_FIXED", "FULL_INTROACT"):
        overall = sum(conf[bb]["blocks"]["test"]["rows"][row]["mase"]
                      for bb in BACKBONES) / 3
        expect(f"confirmatory {row}", overall)

    cost = json.loads((ROOT / "results/v54/cost/e2e_latency.json").read_text())
    for bb in BACKBONES:
        hot = cost["per_backbone"][bb]["hot_per_request"]
        expect(f"cost {bb} FULL median ms", hot["FULL_INTROACT"]["p50_ms"], "%.0f")
        expect(f"cost {bb} KEEP median ms", hot["NATIVE_KEEP"]["p50_ms"], "%.0f")

    missing = [c for c in checks if not c[2]]
    print(f"{len(checks) - len(missing)} of {len(checks)} recorded values appear in the manuscript")
    for label, text, _ in missing:
        print(f"  MISSING  {label:34s} {text}")
    legality = cost["legality_validation"]["mismatches"]
    print(f"E3 legality mismatches: {len(legality)} of {cost['requests']} requests")


if __name__ == "__main__":
    main()
