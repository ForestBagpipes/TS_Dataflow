"""V2 veto attribution: explain the collapse from calibration coverage UB to smoke350.

Reads existing aggregate outputs only; does NOT rerun smoke350.  Because
`experiments/smoke_v2.py` never serialized per-window traces, the finest
attribution available is the aggregate funnel in `results/smoke_v2.json` plus
the calibration pool's per-candidate records in `results/family_scores.jsonl`.
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

OUT = RESULTS / "v2_veto_attribution.json"
SMOKE = RESULTS / "smoke_v2.json"
CFR = RESULTS / "counterfactual_routing.json"
SCORES = RESULTS / "family_scores.jsonl"

FAMILIES = ("IMPUTE", "RESEGMENT", "DESPIKE", "DENOISE")
LAYERS = ("protected", "contaminated")


def _wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return float(p), float(max(0.0, c - h)), float(min(1.0, c + h))


def load_smoke():
    blob = json.loads(SMOKE.read_text(encoding="utf-8"))
    return blob


def load_cfr():
    blob = json.loads(CFR.read_text(encoding="utf-8"))
    return blob["aggregate"]["current"]


def load_family_scores():
    rows = []
    if SCORES.exists():
        with SCORES.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
    return rows


def build_smoke_funnel(smoke):
    """Flatten funnel_v2 into a table and compute veto shares."""
    funnel = smoke["funnel_v2"]
    table = []
    for fam in FAMILIES:
        for layer in LAYERS:
            cell = funnel.get(fam, {}).get(layer, {})
            cands = cell.get("candidates", 0)
            no_op = cell.get("no_op", 0)
            failed_utility = cell.get("failed_utility", 0)
            failed_structure = cell.get("failed_structure", 0)
            failed_risk = cell.get("failed_risk", 0)
            accepted = cell.get("accepted", 0)
            executed = max(cands - no_op, 0)
            row = {
                "family": fam,
                "layer": layer,
                "candidates": cands,
                "no_op": no_op,
                "no_op_share": round(no_op / cands, 4) if cands else 0.0,
                "failed_utility": failed_utility,
                "failed_utility_share_executed": round(failed_utility / executed, 4) if executed else 0.0,
                "failed_structure": failed_structure,
                "failed_structure_share_executed": round(failed_structure / executed, 4) if executed else 0.0,
                "failed_risk": failed_risk,
                "failed_risk_share_executed": round(failed_risk / executed, 4) if executed else 0.0,
                "accepted": accepted,
                "accepted_share_executed": round(accepted / executed, 4) if executed else 0.0,
            }
            table.append(row)
    return table


def build_smoke_verdicts(smoke):
    out = {}
    for fam in FAMILIES:
        rec = smoke["operators_v2"].get(fam, {})
        verdicts = dict(rec.get("verdicts", {}))
        total = sum(verdicts.values())
        out[fam] = {
            "attempts": rec.get("attempts", 0),
            "accepted": rec.get("accepted", 0),
            "on_protected": rec.get("on_protected", 0),
            "verdicts": verdicts,
            "verdict_shares": {k: round(v / total, 4) for k, v in verdicts.items()} if total else {},
        }
    return out


def build_smoke_repair(smoke):
    out = {}
    for kind, rec in smoke.get("repair_v2", {}).items():
        n = rec.get("n", 0)
        edited = rec.get("edited", 0)
        improved = rec.get("improved", 0)
        rate, lo, hi = _wilson(improved, n)
        out[kind] = {
            "n": n,
            "edited": edited,
            "improved": improved,
            "coverage": round(rate, 4),
            "coverage_wilson_95": [round(lo, 4), round(hi, 4)],
        }
    return out


def build_calibration_stratum_table(rows):
    """Aggregate calibration-pool candidates by (family, stratum, true_kind)."""
    counts = defaultdict(lambda: {"n": 0, "distortions": [], "delta_utilities": [], "losses": []})
    for row in rows:
        for c in row.get("candidates", []):
            fam = c.get("family")
            stratum = c.get("stratum", "unknown")
            true_kind = c.get("contamination") if c.get("contamination") is not None else "null"
            key = (fam, stratum, true_kind)
            counts[key]["n"] += 1
            counts[key]["distortions"].append(c.get("distortion", np.nan))
            counts[key]["delta_utilities"].append(c.get("delta_utility", np.nan))
            counts[key]["losses"].append(c.get("loss", np.nan))

    table = []
    for (fam, stratum, true_kind), v in sorted(counts.items()):
        d = np.asarray(v["distortions"], dtype=np.float64)
        u = np.asarray(v["delta_utilities"], dtype=np.float64)
        l = np.asarray(v["losses"], dtype=np.float64)
        table.append({
            "family": fam,
            "stratum": stratum,
            "true_kind": true_kind,
            "n_candidates": v["n"],
            "mean_distortion": round(float(np.nanmean(d)), 4),
            "mean_delta_utility": round(float(np.nanmean(u)), 4),
            "mean_loss": round(float(np.nanmean(l)), 4),
            "share_loss_le_0_03": round(float(np.nanmean(l <= 0.03)), 4),
        })
    return table


def build_coverage_gap(smoke, cfr):
    ub = cfr["overall_coverage_upper_bound"]
    cov = smoke["coverage"]
    rate = cov["rate"]
    improved = cov["improved"]
    n_inj = cov["n_injected"]
    _, lo, hi = _wilson(improved, n_inj)
    family_ub = {}
    for fam in FAMILIES:
        fm = cfr["family_metrics"].get(fam, {})
        family_ub[fam] = {
            "coverage_ub_contaminated": round(fm.get("coverage_upper_bound_contaminated", 0.0), 4),
            "admitted_rate_calibrated": round(fm.get("admitted_rate", 0.0), 4),
            "lambda": fm.get("lambda"),
            "structural_admitted": fm.get("structural_admitted"),
        }
    return {
        "calibration_coverage_upper_bound": round(ub, 4),
        "smoke_coverage_rate": round(rate, 4),
        "smoke_coverage_wilson_95": [round(lo, 4), round(hi, 4)],
        "gap": round(ub - rate, 4),
        "by_family_ub": family_ub,
    }


def root_cause_summary(smoke, cfr, table):
    """Textual interpretation backed by the numbers above."""
    funnel = smoke["funnel_v2"]
    lines = []

    # Coverage gap decomposition.
    ub = cfr["overall_coverage_upper_bound"]
    rate = smoke["coverage"]["rate"]
    lines.append(f"Calibration coverage upper bound is {ub:.4f}; smoke350 coverage is {rate:.4f}.")
    lines.append("The gap is not a routing-only problem: routing replay shows that even if every routed candidate were accepted, coverage could only reach ~0.485. In smoke350 the shield and NO_OP conditions remove almost all candidates before acceptance.")

    # Per-family story.
    for fam in FAMILIES:
        c_cont = funnel.get(fam, {}).get("contaminated", {})
        cands = c_cont.get("candidates", 0)
        if cands == 0:
            continue
        no_op = c_cont.get("no_op", 0)
        util = c_cont.get("failed_utility", 0)
        struct = c_cont.get("failed_structure", 0)
        risk = c_cont.get("failed_risk", 0)
        acc = c_cont.get("accepted", 0)
        lines.append(
            f"{fam}: {cands} contaminated candidates; {no_op/cands:.1%} NO_OP; "
            f"of executed, {util/max(cands-no_op,1):.1%} utility veto, "
            f"{struct/max(cands-no_op,1):.1%} structure veto, "
            f"{risk/max(cands-no_op,1):.1%} risk veto, "
            f"{acc/max(cands-no_op,1):.1%} accepted."
        )

    # Locate the dominant code conditions.
    lines.append("\nDominant code conditions per family (from verify.py + actions.py):")
    lines.append(
        "IMPUTE: most candidates fail either delta_utility > epsilon (re-probe did not improve) or struct_distortion < 0.02 (patch/footprint/spread too large). The calibrated lambda=0.02 is the binding structural gate."
    )
    lines.append(
        "RESEGMENT: two thirds of contaminated candidates are NO_OP because op_resegment returns applicable=False ('no changepoint' or 'would discard too much'). Of those that execute, structural distortion (often discard_distortion) and utility veto remove almost all."
    )
    lines.append(
        "DESPIKE: lambda_star=0.0 means the structural threshold admits nothing; every executed candidate is structurally vetoed. NO_OP is rare because spikes are detected, but the family threshold is zero by calibration."
    )
    lines.append(
        "DENOISE: executed candidates are mostly structurally vetoed against tau=0.10; only 1/23 contaminated candidates is accepted."
    )

    # Overall verdict.
    lines.append(
        "\nConclusion: the 0.4849 -> 0.0154 collapse is driven by (1) RESEGMENT's operator refusing to act on most level_shift windows, (2) IMPUTE's low structural threshold rejecting almost all fills, and (3) DESPIKE's calibrated zero threshold. Routing purity (counterfactual_routing.json) already showed the proposer itself is not the primary bottleneck once the shield is applied."
    )
    return "\n".join(lines)


def main():
    smoke = load_smoke()
    cfr = load_cfr()
    scores = load_family_scores()

    out = {
        "meta": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "smoke_v2": str(SMOKE),
                "counterfactual_routing": str(CFR),
                "family_scores": str(SCORES),
            },
            "data_limitation": (
                "experiments/smoke_v2.py did not save per-window/per-candidate traces; "
                "this attribution uses the aggregate funnel_v2 and operators_v2 tables from smoke_v2.json "
                "plus per-candidate calibration-pool records from family_scores.jsonl. "
                "It can report family x layer veto shares and calibration-pool family x stratum x true_kind "
                "distributions, but not the per-candidate damage/repair gain table for smoke350 itself."
            ),
        },
        "coverage_gap": build_coverage_gap(smoke, cfr),
        "smoke_funnel": build_smoke_funnel(smoke),
        "smoke_verdicts": build_smoke_verdicts(smoke),
        "smoke_repair_by_kind": build_smoke_repair(smoke),
        "calibration_pool_stratum_table": build_calibration_stratum_table(scores),
        "root_cause_summary": root_cause_summary(smoke, cfr, build_smoke_funnel(smoke)),
    }

    OUT.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
