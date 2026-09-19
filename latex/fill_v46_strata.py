"""Opportunity strata and the per-severity appendix tables."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKBONES = ("bolt", "timesfm", "chronos2")
METHOD_KEY = {"NATIVE_KEEP": "KEEP", "BEST_FIXED": "BF", "R2_CART": "R2",
              "SAITS": "SAITS", "TATO": "TATO", "FULL_INTROACT": "OURS",
              "CATALOG_ORACLE": "ORACLE"}
STRATUM = {"no-op": "NOOP", "low": "LOWOP", "high": "HIGHOP"}
SEV_BLOCK = {"test": "10", "test30": "30", "test50": "50"}


def build(num, pct) -> dict:
    out: dict[str, str] = {}

    payloads = {}
    for backbone in BACKBONES:
        path = ROOT / f"results/v46/evaluation/test_{backbone}.json"
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
            path = ROOT / f"results/v46/evaluation/{block}_{backbone}.json"
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
    return out
