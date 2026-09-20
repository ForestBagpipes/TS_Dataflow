"""Opportunity strata and the per-severity appendix tables."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKBONES = ("bolt", "timesfm", "chronos2")
METHOD_KEY = {"NATIVE_KEEP": "KEEP", "BEST_FIXED": "BF", "R2_CART": "R2",
              "FIXED_SAITS": "SAITS", "TATO": "TATO", "FULL_INTROACT": "OURS",
              "CATALOG_ORACLE": "ORACLE"}
STRATUM = {"no-op": "NOOP", "low": "LOWOP", "high": "HIGHOP"}
SEV_BLOCK = {"test": "10", "test30": "30", "test50": "50"}


def build(num, pct) -> dict:
    out: dict[str, str] = {}

    payloads = {}
    for backbone in BACKBONES:
        path = ROOT / f"results/v47/evaluation/test_{backbone}.json"
        if path.exists():
            payloads[backbone] = json.loads(path.read_text())
    strata = [p["opportunity_strata"] for p in payloads.values()
              if p.get("opportunity_strata")]
    if strata:
        for name, tag in STRATUM.items():
            sizes = [s["sizes"][name] for s in strata if name in s["sizes"]]
            if not sizes:
                continue
            short = {"NOOP": "NOOP", "LOWOP": "LOW", "HIGHOP": "HIGH"}[tag]
            out[f"STRATUM_{short}_N"] = str(int(
                sum(x["parents"] for x in sizes) / len(sizes)))
            out[f"STRATUM_{short}_SHARE"] = pct(
                sum(x["share"] for x in sizes) / len(sizes))
            med = [x["median"] for x in sizes if x["median"] is not None]
            p90 = [x["p90"] for x in sizes if x["p90"] is not None]
            if med:
                out[f"STRATUM_{short}_MED"] = num(sum(med) / len(med))
            if p90:
                out[f"STRATUM_{short}_P90"] = num(sum(p90) / len(p90))
        for method, key in METHOD_KEY.items():
            for name, tag in STRATUM.items():
                values = [s["per_method"][method][name] for s in strata
                          if method in s["per_method"]
                          and s["per_method"][method].get(name) is not None]
                if values:
                    out[f"{tag}_{key}"] = num(sum(values) / len(values))
            overall = [s["per_method"][method]["overall"] for s in strata
                       if method in s["per_method"]
                       and s["per_method"][method].get("overall") is not None]
            if overall:
                out[f"OVR_{key}"] = num(sum(overall) / len(overall))
        boundaries = strata[0]["boundaries"]
        out["OPPSENS_ONE_NOOP"] = num(boundaries["no_op"], 6)
        out["OPPSENS_ONE_LOW"] = num(boundaries["low_to_high"])
        out["OPPSENS_ONE_HIGH"] = num(boundaries["upper_reference"])

    # Per-severity appendix tables, in every metric the records carry.
    for block, level in SEV_BLOCK.items():
        rows: dict[str, dict[str, list[float]]] = {}
        ranks: dict[str, list[float]] = {}
        for backbone in BACKBONES:
            path = ROOT / f"results/v47/evaluation/{block}_{backbone}.json"
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            for method, key in METHOD_KEY.items():
                row = payload["rows"].get(method)
                if not row:
                    continue
                store = rows.setdefault(key, {"mase": [], "rmsse": []})
                if row.get("mase") is not None:
                    store["mase"].append(row["mase"])
                if row.get("rmsse") is not None:
                    store["rmsse"].append(row["rmsse"])
                if payload["average_rank"].get(method) is not None:
                    ranks.setdefault(key, []).append(payload["average_rank"][method])
        for key, store in rows.items():
            if store["mase"]:
                out[f"SEV{level}-{key}-MASE"] = num(sum(store["mase"]) / len(store["mase"]))
            if store["rmsse"]:
                out[f"SEV{level}-{key}-RMSSE"] = num(sum(store["rmsse"]) / len(store["rmsse"]))
            if ranks.get(key):
                out[f"SEV{level}-{key}-RANK"] = num(sum(ranks[key]) / len(ranks[key]), 2)
    # Boundary sensitivity: the same partition under a half and a double
    # threshold, so a reader can see how much the stratum reading depends on
    # where the line was drawn.
    factors = {"x0.5": "HALF", "x1.0": "ONE", "x2.0": "TWO"}
    for factor, tag in factors.items():
        rows_f = [p["opportunity_strata_sensitivity"][factor] for p in payloads.values()
                  if p.get("opportunity_strata_sensitivity", {}).get(factor)]
        if not rows_f:
            continue
        for name, column in (("no-op", "NOOP"), ("low", "LOW"), ("high", "HIGH"),
                             ("overall", "OVR")):
            values = [r["per_method"]["FULL_INTROACT"][name] for r in rows_f
                      if r["per_method"].get("FULL_INTROACT", {}).get(name) is not None]
            if values:
                out[f"OPPSENS_{tag}_{column}"] = num(sum(values) / len(values))

    # Worst cell of the whole sweep: the largest degradation relative to the
    # untouched input over every pattern, backbone and severity.  One column
    # covers three severities, so the maximum has to run over all of them;
    # taking it per severity and writing it to one key would put numbers from
    # different severities in the same column.
    worst: dict[str, float] = {}
    for block, level in SEV_BLOCK.items():
        for backbone in BACKBONES:
            path = ROOT / f"results/v47/evaluation/{block}_{backbone}.json"
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            keep = payload["rows"].get("NATIVE_KEEP")
            if not keep:
                continue
            for method, key in METHOD_KEY.items():
                row = payload["rows"].get(method)
                if not row:
                    continue
                for cell, value in row["per_cell_mase"].items():
                    reference = keep["per_cell_mase"].get(cell)
                    if reference is None or value is None:
                        continue
                    gap = value - reference
                    if key not in worst or gap > worst[key]:
                        worst[key] = gap
    for key, gap in worst.items():
        out[f"RB_{key}_WORST"] = f"{gap:+.3f}"

    # Mask-realisation stability: the same TEST parents under three deterministic
    # deletion patterns.  The spread is a stability diagnostic and is never
    # treated as a third sample of parents.
    plan = [("bolt", ("test", "test_m2", "test_m3"), (1, 2, 3), "BOLT"),
            ("chronos2", ("test", "test_m2", "test_m3"), (4, 5, 6), "CH2")]
    for backbone, blocks, indices, tag in plan:
        mases, rates = [], []
        for block, index in zip(blocks, indices):
            path = ROOT / f"results/v47/evaluation/{block}_{backbone}.json"
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            ours = payload["rows"].get("FULL_INTROACT")
            keep = payload["rows"].get("NATIVE_KEEP")
            if not ours or not keep:
                continue
            out[f"SEED{index}_MASE"] = num(ours["mase"])
            out[f"SEED{index}_DELTA"] = f"{ours['mase'] - keep['mase']:+.3f}"
            out[f"SEED{index}_IR"] = pct(ours["intervention_rate"])
            mases.append(ours["mase"])
            rates.append(ours["intervention_rate"])
        if len(mases) >= 2:
            out[f"SEED_SPREAD_{tag}"] = num(max(mases) - min(mases))
            out[f"SEED_IR_SPREAD_{tag}"] = pct(max(rates) - min(rates))
        # The rival on the same realisations, so the stability claim covers the
        # comparison rather than one row of it.
        rival = []
        for block in blocks:
            path = ROOT / f"results/v47/evaluation/{block}_{backbone}.json"
            if not path.exists():
                continue
            row = json.loads(path.read_text())["rows"].get("R2_CART")
            if row and row.get("mase") is not None:
                rival.append(row["mase"])
        if len(rival) >= 2:
            out[f"SEED_SPREAD_CART_{tag}"] = num(max(rival) - min(rival))
    return out
