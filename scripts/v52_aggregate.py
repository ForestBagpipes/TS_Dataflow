#!/usr/bin/env python3
"""Aggregate the v52 ablation-correction results against the v47 paper numbers.

Reads ``results/v52_ablation/evaluation/*.json`` and
``results/v52_ablation/gate_controls/*.json`` (never writes outside
``results/v52_ablation/``), and prints:

* the ablation ladder per backbone and the three-backbone mean, old A2 vs the
  new mechanism variant A2_WO_ACTION_COND vs FULL;
* paired bootstrap intervals FULL vs both A2 variants;
* the matched-coverage gate controls (E-003 / plan E3);
* the H=96-only realisation MASE for the seeds table (R-002), recomputed from
  the stored v47 per-source-horizon breakdowns (no rerun needed).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEW = ROOT / "results/v52_ablation"
OLD = ROOT / "results/v47/evaluation"
BACKBONES = ("bolt", "timesfm", "chronos2")
LADDER = ("FULL_INTROACT", "A1_GLOBAL_UTILITY", "A2_WO_INTERVENTION",
          "A2_WO_ACTION_COND", "A3_WO_FORECAST", "A4_ALWAYS_ACT",
          "A5_PARAMETRIC_RIDGE", "NATIVE_KEEP", "BEST_FIXED", "R2_CART",
          "FIXED_SAITS", "CATALOG_ORACLE")


def mean3(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def main() -> None:
    print("== ablation ladder, block=test (source-macro MASE) ==")
    header = ["method", *BACKBONES, "mean3", "v47_mean3"]
    print(("{:24s}" + "{:>10s}" * (len(header) - 1)).format(*header))
    means = {}
    for m in LADDER:
        row, old_row = [], []
        for bb in BACKBONES:
            new_path = NEW / f"evaluation/test_{bb}.json"
            old_path = OLD / f"test_{bb}.json"
            new = json.loads(new_path.read_text())["rows"] if new_path.exists() else {}
            old = json.loads(old_path.read_text())["rows"] if old_path.exists() else {}
            row.append(new.get(m, {}).get("mase"))
            old_row.append(old.get(m, {}).get("mase"))
        means[m] = mean3(row)
        cells = [f"{v:.4f}" if v is not None else "-" for v in row]
        cells.append(f"{means[m]:.4f}" if means[m] is not None else "-")
        om = mean3(old_row)
        cells.append(f"{om:.4f}" if om is not None else "-")
        print("{:24s}".format(m) + "".join(f"{c:>10s}" for c in cells))

    print("\n== intervention rate / conditional HIR, block=test, mean of 3 ==")
    for m in ("FULL_INTROACT", "A2_WO_INTERVENTION", "A2_WO_ACTION_COND",
              "A5_PARAMETRIC_RIDGE"):
        irs, hirs, hls = [], [], []
        for bb in BACKBONES:
            p = NEW / f"evaluation/test_{bb}.json"
            if not p.exists():
                continue
            r = json.loads(p.read_text())["rows"][m]
            irs.append(r["intervention_rate"])
            hirs.append(r["conditional_hir"])
            hls.append(r["harmful_loss"])
        print(f"{m:24s} IR={mean3(irs):.4f} HIR={mean3(hirs):.4f} "
              f"harmful_loss={mean3(hls):.5f}")

    print("\n== paired bootstrap FULL vs A2 variants, block=test ==")
    for bb in BACKBONES:
        p = NEW / f"evaluation/test_{bb}.json"
        if not p.exists():
            continue
        comps = json.loads(p.read_text())["comparisons"]
        for ref in ("A2_WO_INTERVENTION", "A2_WO_ACTION_COND", "A5_PARAMETRIC_RIDGE"):
            c = comps.get(f"FULL_INTROACT_vs_{ref}")
            if c:
                print(f"{bb:9s} FULL-{ref:22s} diff={c['difference']:+.4f} "
                      f"CI=[{c['ci_low']:+.4f},{c['ci_high']:+.4f}] "
                      f"excl0={c['excludes_zero']} p={c['p_value']:.4f}")

    print("\n== train_eval (dev) ladder mean of 3 ==")
    for m in ("FULL_INTROACT", "A2_WO_INTERVENTION", "A2_WO_ACTION_COND",
              "A5_PARAMETRIC_RIDGE"):
        vals = []
        for bb in BACKBONES:
            p = NEW / f"evaluation/train_eval_{bb}.json"
            if p.exists():
                vals.append(json.loads(p.read_text())["rows"][m]["mase"])
        if vals:
            print(f"{m:24s} dev_mase_mean={mean3(vals):.4f}")

    print("\n== gate controls (E-003), block=test ==")
    for bb in BACKBONES:
        p = NEW / f"gate_controls/{bb}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        cal = d["calibration"]
        print(f"-- {bb}: dev_rate={cal['dev_full_intervention_rate']:.4f} "
              f"theta_mean={cal['theta_mean']:.4f} theta_lin={cal['theta_lin']:.4f} "
              f"p_act={cal['random_act_probability']:.4f}")
        for name, r in d["blocks"]["test"]["rows"].items():
            print(f"   {name:16s} mase={r['mase']:.4f} IR={r['intervention_rate']:.4f} "
                  f"HIR={r['conditional_hir']:.4f} harm={r['harmful_loss']:.5f}")
        for key, c in d["blocks"]["test"]["comparisons"].items():
            print(f"   {key:38s} diff={c['difference']:+.4f} "
                  f"CI=[{c['ci_low']:+.4f},{c['ci_high']:+.4f}] excl0={c['excludes_zero']}")

    print("\n== R-002 correction: H=96-only FULL_INTROACT MASE by realisation ==")
    for blk, tag in (("test", "primary"), ("test_m2", "second"), ("test_m3", "third")):
        for bb in ("bolt", "chronos2"):
            p = OLD / f"{blk}_{bb}.json"
            if not p.exists():
                continue
            rows = json.loads(p.read_text())["rows"]["FULL_INTROACT"]
            psh = rows.get("per_source_horizon_mase", {})
            h96 = [v for k, v in psh.items() if k.startswith("h96|")]
            print(f"{tag:8s} {bb:9s} H96-only={mean3(h96):.4f} "
                  f"(dual-horizon macro printed in v51 seeds table: {rows['mase']:.4f})")


if __name__ == "__main__":
    main()
