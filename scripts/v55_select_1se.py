#!/usr/bin/env python3
"""v55 step 1b: apply the one standard error rule to the recorded grid.

The cross validated surface is flat.  Twelve to thirty five of the settings the
harm cap admits lie within one standard error of the lowest cross validated
error, so taking the strict minimum reads noise as signal and, because the
error of a setting falls slowly while its intervention rate rises quickly, it
systematically lands on a setting that acts far more often than it needs to.
The project used a one standard error rule for this reason before the v54
recompute, and v55 restores it: among the settings whose paired gap to the
leader is no larger than the standard error of that gap, take the one that
intervenes least, then the smaller neighbourhood.

The script only re-reads the grid that ``scripts/v55_select.py`` already wrote,
so it adds no model evaluation and cannot see a TEST record.  The minimum rule
choice stays in the payload as the registered sensitivity comparison.

Writes ``results/v55/protocol/selection_{backbone}.json`` in place, keeping the
original choice under ``selection.min_rule_selected``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import ROOT, clean, write

PROTOCOL = ROOT / "results/v55/protocol"


def one_se_pick(grid: list[dict], cap: float) -> dict:
    """The least intervening setting inside the one standard error band."""
    feasible = [r for r in grid if cap is None or r["conditional_hir"] <= cap]
    band = [r for r in feasible
            if (r.get("gap_to_selected") or 0.0) <= (r.get("gap_se") or 0.0)]
    pool = band or feasible
    return min(pool, key=lambda r: (round(r["intervention_rate"], 6), r["k"],
                                    round(r["lopo_mase"], 6)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", default="bolt")
    args = parser.parse_args()

    path = PROTOCOL / f"selection_{args.backbone}.json"
    payload = json.loads(path.read_text())
    chosen = payload["selection"]
    if chosen.get("keep_only") or chosen.get("selected") is None:
        print(json.dumps({"backbone": args.backbone,
                          "keep_only": True,
                          "note": "no configuration to re-pick"}, indent=1))
        return

    cap = payload["harm_cap"]["cap"]
    if "min_rule_selected" not in chosen:
        chosen["min_rule_selected"] = dict(chosen["selected"])
        chosen["min_rule_leader"] = dict(chosen["leader"])
    pick = one_se_pick(chosen["grid"], cap)
    chosen["selected"] = {"k": pick["k"], "beta": pick["beta"],
                          "lam": pick["lam"], "lam_is_inf": pick["lam_is_inf"]}
    chosen["leader"] = {"k": pick["k"], "beta": pick["beta"], "lam": pick["lam"],
                        "lam_is_inf": pick["lam_is_inf"],
                        "lopo_mase": pick["lopo_mase"],
                        "intervention_rate": pick["intervention_rate"],
                        "conditional_hir": pick["conditional_hir"],
                        "gap_to_min_rule": pick.get("gap_to_selected"),
                        "gap_se": pick.get("gap_se")}
    chosen["rule"] = ("among the settings whose conditional harmful rate "
                      "respects the cap and whose paired gap to the lowest "
                      "cross-validated source-macro MASE is no larger than the "
                      "standard error of that gap, the one that intervenes "
                      "least, then the smaller neighbourhood")
    chosen["one_se_band_size"] = sum(
        1 for r in chosen["grid"]
        if r["conditional_hir"] <= cap
        and (r.get("gap_to_selected") or 0.0) <= (r.get("gap_se") or 0.0))
    payload["selection_rule"] = "one-standard-error"
    write(path, clean(payload))
    print(json.dumps(clean({"backbone": args.backbone,
                            "one_se": chosen["selected"],
                            "min_rule": chosen["min_rule_selected"],
                            "band": chosen["one_se_band_size"],
                            "leader": chosen["leader"]}), indent=1))


if __name__ == "__main__":
    main()
