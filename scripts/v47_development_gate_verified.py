#!/usr/bin/env python3
"""Apply the predeclared TRAIN-side gate; this script never reads TEST."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKBONES = ("bolt", "timesfm", "chronos2")
DEVELOPMENT = ("bolt", "timesfm")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="results/v47_verified")
    args = parser.parse_args()
    root = ROOT / args.output_root
    checks = []
    for backbone in BACKBONES:
        selected = json.loads((root / "protocol" / f"selection_{backbone}.json").read_text())
        evaluated = json.loads((root / "evaluation" / f"train_eval_{backbone}.json").read_text())
        if selected.get("test_records_read") != 0 or evaluated.get("test_records_read") != 0:
            raise RuntimeError("Development gate received TEST evidence")
        anchor = selected["harm_cap"]["anchor"]
        fixed = selected["harm_cap"]["action_source_macro_mase"][anchor]
        lopo = selected["selection"]["leader"]["lopo_mase"]
        checks.append(dict(name=f"{backbone}:lopo_below_best_fixed", passed=lopo < fixed,
                           observed=lopo, boundary=fixed))
        a4 = evaluated["comparisons"]["FULL_INTROACT_vs_A4_ALWAYS_ACT"]
        checks.append(dict(name=f"{backbone}:not_worse_than_A4", passed=a4["ci_low"] <= 0,
                           difference=a4["difference"], interval=[a4["ci_low"], a4["ci_high"]]))
        if backbone in DEVELOPMENT:
            a5 = evaluated["comparisons"]["FULL_INTROACT_vs_A5_PARAMETRIC_RIDGE"]
            checks.append(dict(name=f"{backbone}:better_than_A5", passed=a5["ci_high"] < 0,
                               difference=a5["difference"], interval=[a5["ci_low"], a5["ci_high"]]))
    payload = {"stage": "v47-verified-development-gate", "status": "passed" if all(c["passed"] for c in checks) else "failed",
               "checks": checks, "test_records_read": 0,
               "consequence": "freeze eligible" if all(c["passed"] for c in checks)
                              else "do not open TEST; retain as negative development result"}
    target = root / "development_gate.json"
    target.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    # A failed scientific gate is a completed negative result, not an
    # execution failure.  The durable driver records the distinction and
    # leaves TEST sealed in both cases.


if __name__ == "__main__":
    main()
