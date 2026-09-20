"""Keys that v4.7 adds: the tables that replaced the result figures, the
retrieval scope, the per-backbone severity trend, and the two sentences the
review asked the main text to carry.

Every value here comes from a file under ``results/v47`` and nothing is
estimated.  A key with no record stays a placeholder, which is what makes a
missing experiment visible in the rendered manuscript.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "results/v47/evaluation"
DIAG = ROOT / "results/v47/diagnostics"
PROTO = ROOT / "results/v47/protocol"

BACKBONES = [("bolt", "BOLT"), ("timesfm", "TF"), ("chronos2", "CH2")]
BACKBONE_NAME = {"bolt": "Bolt", "timesfm": "TimesFM", "chronos2": "Chronos-2"}
METHOD_TAG = {"NATIVE_KEEP": "KEEP", "BEST_FIXED": "BF", "R2_CART": "R2",
              "FIXED_SAITS": "SAITS", "TATO": "TATO", "FULL_INTROACT": "OURS"}
BETA_TAG = {0.0: "B00", 0.5: "B05", 1.0: "B10", 1.64: "B164"}
PCT = "\\%"


def read(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def build(num, pct) -> dict:
    out: dict[str, str] = {}

    # -- the rank grid that replaced Figure 3(a) ----------------------------
    grids, order = [], None
    for backbone, _tag in BACKBONES:
        recon = read(DIAG / f"reconstruction_test_{backbone}.json")
        if recon and recon.get("rank_grid"):
            grids.append(recon["rank_grid"])
            order = recon.get("rank_grid_order", order)
    if grids:
        size = len(grids[0])
        for i in range(size):
            totals = [sum(g[i]) for g in grids]
            for j in range(size):
                share = sum(g[i][j] for g in grids) / max(sum(totals), 1)
                out[f"RG_{i + 1}_{j + 1}"] = f"{share * 100:.1f}{PCT}"

    # -- the operating points and the score bins that replaced Figure 4 -----
    bins_pooled: dict[int, list] = {}
    for backbone, tag in BACKBONES:
        item = read(DIAG / f"operating_test_{backbone}.json")
        if not item:
            continue
        for key, point in item["points"].items():
            beta_tag = BETA_TAG.get(round(point["beta"], 2))
            if beta_tag is None:
                continue
            out[f"OPPT_{tag}_{beta_tag}_IR"] = pct(point["intervention_rate"])
            out[f"OPPT_{tag}_{beta_tag}_HIR"] = pct(point["conditional_hir"])
            out[f"OPPT_{tag}_{beta_tag}_MASE"] = num(point["mase"])
        for entry in item.get("score_bins", []):
            bins_pooled.setdefault(entry["bin"], []).append(entry)
    for index, entries in bins_pooled.items():
        pairs = sum(e["pairs"] for e in entries)
        mean = sum(e["mean_utility"] * e["pairs"] for e in entries
                   if e["mean_utility"] is not None) / max(pairs, 1)
        low = min(e["ci_low"] for e in entries)
        high = max(e["ci_high"] for e in entries)
        out[f"SU_B{index}_N"] = f"{pairs:,}"
        out[f"SU_B{index}_MEAN"] = f"{mean:+.3f}"
        out[f"SU_B{index}_CI"] = f"[{low:+.3f}, {high:+.3f}]"

    # -- the per-backbone severity trend that replaced Figure 5 -------------
    for backbone, tag in BACKBONES:
        for block, sev in (("test", "S10"), ("test30", "S30"), ("test50", "S50")):
            payload = read(EVAL / f"{block}_{backbone}.json")
            if not payload:
                continue
            for method, method_tag in METHOD_TAG.items():
                row = payload["rows"].get(method)
                if row and row.get("mase") is not None:
                    out[f"TREND_{tag}_{method_tag}_{sev}"] = num(row["mase"])

    # -- the table that establishes the decision problem --------------------
    TAG = {"KEEP": "KEEP", "FFILL": "FFILL", "SINGLE_TSICL": "SINGLE",
           "MULTI_TSICL": "MULTI", "CONTEXT_RIDGE": "RIDGE", "SAITS": "SAITS"}
    share, applic, positive, utility = {}, {}, {}, {}
    for backbone, _tag in BACKBONES:
        payload = read(EVAL / f"test_{backbone}.json")
        if not payload:
            continue
        het = payload["heterogeneity"]
        for action, tag in TAG.items():
            value = het["oracle_best_share"].get(action)
            if value is not None:
                share.setdefault(tag, []).append(value)
            item = het["per_action_utility"].get(action)
            if not item:
                continue
            applic.setdefault(tag, []).append(item["applicable"])
            if item.get("p_positive") is not None:
                positive.setdefault(tag, []).append(item["p_positive"])
            if item.get("mean_utility") is not None:
                utility.setdefault(tag, []).append(item["mean_utility"])
    episodes = None
    payload = read(EVAL / "test_bolt.json")
    if payload:
        episodes = payload["episodes"]
    for tag in TAG.values():
        if tag in share:
            out[f"HET_{tag}_BEST"] = pct(sum(share[tag]) / len(share[tag]))
        if tag in applic:
            out[f"HET_{tag}_N"] = f"{int(round(sum(applic[tag]) / len(applic[tag]))):,}"
        elif tag == "KEEP" and episodes:
            out["HET_KEEP_N"] = f"{episodes:,}"
        if tag in positive:
            out[f"HET_{tag}_POS"] = pct(sum(positive[tag]) / len(positive[tag]))
        elif tag == "KEEP":
            out["HET_KEEP_POS"] = "---"
        if tag in utility:
            value = sum(utility[tag]) / len(utility[tag])
            out[f"HET_{tag}_UTIL"] = f"{value:+.3f}"
        elif tag == "KEEP":
            out["HET_KEEP_UTIL"] = "0.000"

    # -- the local transfer assumption, measured ----------------------------
    for backbone, tag in BACKBONES:
        item = read(DIAG / f"transfer_test_{backbone}.json")
        if not item:
            continue
        out[f"TR_{tag}_RHO"] = num(item["spearman_distance_vs_error"], 3)
        for entry in item["bins"]:
            i = entry["bin"]
            out[f"TR_{tag}_B{i}_DIST"] = num(entry["distance_mean"], 2)
            out[f"TR_{tag}_B{i}_ERR"] = num(entry["abs_error"], 3)
            out[f"TR_{tag}_B{i}_SIGN"] = pct(entry["sign_agreement"])

    # -- what restricting retrieval costs -----------------------------------
    label = {"none": "NONE", "same_horizon": "HZ", "same_source": "SRC",
             "same_source_and_horizon": "BOTH"}
    for backbone, tag in BACKBONES:
        item = read(DIAG / f"retrieval_test_{backbone}.json")
        if not item:
            continue
        for key, short in label.items():
            row = item["rows"].get(key)
            if row:
                out[f"RETR_{short}_{tag}"] = num(row["mase"])

    # -- the two sentences the review asked the main text to carry ----------
    keeps, fixed_action = {}, {}
    for backbone, _tag in BACKBONES:
        payload = read(EVAL / f"test_{backbone}.json")
        if payload:
            keeps[backbone] = payload["rows"]["NATIVE_KEEP"]["mase"]
            fixed_action[backbone] = payload["frozen"]["best_fixed_action"]
    if len(keeps) >= 2:
        spread = ", ".join(f"{BACKBONE_NAME[b]} {keeps[b]:.3f}" for b in keeps)
        names = {b: fixed_action[b].replace("_", " ").title() for b in fixed_action}
        distinct = len(set(names.values()))
        tail = ("and the single action with the highest mean utility on the bank is not the "
                "same one on every backbone, " + ", ".join(
                    f"{names[b]} on {BACKBONE_NAME[b]}" for b in names)
                if distinct > 1 else
                "and the single action with the highest mean utility on the bank is the same "
                "one on every backbone")
        out["KEEP_SEMANTICS"] = (
            "What \\textsc{Keep} means differs between the backbone families, and so does what "
            f"it costs: the untouched input reaches {spread}, {tail}")

    primary = read(EVAL / "test_bolt.json")
    rates, losses = [], []
    for backbone, _tag in BACKBONES:
        payload = read(EVAL / f"test_{backbone}.json")
        if not payload:
            continue
        rates.append(payload["rows"]["FULL_INTROACT"]["intervention_rate"])
        losses.append((payload["rows"]["FULL_INTROACT"]["harmful_loss"],
                       payload["rows"]["BEST_FIXED"]["harmful_loss"]))
    if rates and losses:
        rate = sum(rates) / len(rates)
        ours = sum(x for x, _ in losses) / len(losses)
        fixed = sum(y for _, y in losses) / len(losses)
        out["ABSTRACT_HARM"] = (
            f"It executes an intervention on {rate * 100:.0f}{PCT} of the requests and the loss "
            f"its harmful interventions add is {ours:.4f} against {fixed:.4f} for the best fixed "
            f"intervention")
    return {k: v for k, v in out.items() if v is not None}
