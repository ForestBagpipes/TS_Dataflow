"""Replace the \\ph{KEY} placeholders with the numbers the v4.6 run produced.

Reads ``results/v46/evaluation/test_<backbone>.json`` for whatever backbones
have finished and ``results/v46/protocol/selection_<backbone>.json`` for the
frozen hyperparameters.  A key with no number stays a placeholder, so the
output always shows what is still missing rather than guessing.

Usage:  python latex/fill_v46.py <source.tex> <target.tex>
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "results/v46/evaluation"
PROTO = ROOT / "results/v46/protocol"

BACKBONES = [("bolt", "BOLT"), ("timesfm", "TF"), ("chronos2", "CH2")]
METHOD_KEY = {
    "NATIVE_KEEP": "KEEP", "BEST_FIXED": "BF", "R2_CART": "R2",
    "SAITS": "SAITS", "TATO": "TATO",
    "FULL_INTROACT": "OURS", "CATALOG_ORACLE": "ORACLE",
}
ABL_KEY = {
    "FULL_INTROACT": "FULL", "A1_GLOBAL_UTILITY": "A1", "A2_WO_INTERVENTION": "A2",
    "A3_WO_FORECAST": "A3", "A4_ALWAYS_ACT": "A4", "A5_PARAMETRIC_RIDGE": "A5",
}
HARM_KEY = {
    "NATIVE_KEEP": "KEEP", "BEST_FIXED": "BF", "R2_CART": "R2",
    "SAITS": "SAITS", "TATO": "TATO", "FULL_INTROACT": "OURS",
}
SOURCE_KEY = {"ETTh1": "ETTH1", "ETTh2": "ETTH2", "ETTm1": "ETTM1", "ETTm2": "ETTM2",
              "Electricity": "ELEC", "Exchange": "EXCH", "Traffic": "TRAF", "Weather": "WEA"}
ACTION_NAME = {"KEEP": "Keep", "FFILL": "Ffill", "SINGLE_TSICL": "Single TS-ICL",
               "MULTI_TSICL": "Multi TS-ICL", "CONTEXT_RIDGE": "Context Ridge"}


def num(value, digits=3):
    if value is None:
        return None
    return f"{float(value):.{digits}f}"


def pct(value, digits=1):
    if value is None:
        return None
    return f"{float(value) * 100:.{digits}f}\\%"


def signed(value, digits=3):
    if value is None:
        return None
    value = float(value)
    # A value that rounds to zero should not carry a sign that suggests a
    # direction the measurement does not support.
    if abs(round(value, digits)) < 10 ** -digits:
        return f"{0.0:.{digits}f}"
    return f"{value:+.{digits}f}"


def ci(entry, digits=4):
    if entry is None:
        return None
    return (f"{entry['difference']:+.{digits}f} "
            f"[{entry['ci_low']:+.{digits}f}, {entry['ci_high']:+.{digits}f}]")


def load() -> tuple[dict, dict]:
    evals, selections = {}, {}
    for backbone, _tag in BACKBONES:
        path = EVAL / f"test_{backbone}.json"
        if path.exists():
            evals[backbone] = json.loads(path.read_text())
        path = PROTO / f"selection_{backbone}.json"
        if path.exists():
            selections[backbone] = json.loads(path.read_text())
        path = ROOT / f"results/v46/diagnostics/reconstruction_test_{backbone}.json"
        if path.exists() and backbone in evals:
            evals[backbone]["reconstruction"] = json.loads(path.read_text())
    return evals, selections


def mean_over(evals: dict, method: str, field: str):
    values = [e["rows"][method][field] for e in evals.values()
              if method in e["rows"] and e["rows"][method].get(field) is not None]
    return sum(values) / len(values) if values else None


def build(evals: dict, selections: dict) -> dict:
    out: dict[str, str] = {}
    if not evals:
        return out
    primary = evals.get("bolt") or next(iter(evals.values()))

    # Main comparison.
    for method, key in METHOD_KEY.items():
        for backbone, tag in BACKBONES:
            e = evals.get(backbone)
            if e and method in e["rows"]:
                out[f"{key}_{tag}"] = num(e["rows"][method]["mase"])
        out[f"{key}_OVR"] = num(mean_over(evals, method, "mase"))
        out[f"{key}_RMSSE"] = num(mean_over(evals, method, "rmsse"))
        ranks = [e["average_rank"].get(method) for e in evals.values()
                 if e["average_rank"].get(method) is not None]
        if ranks and key != "ORACLE":
            out[f"{key}_RANK"] = num(sum(ranks) / len(ranks), 2)

    # Governance diagnostics.
    for method, key in HARM_KEY.items():
        row = primary["rows"].get(method)
        if not row:
            continue
        out[f"HARM_MASE_{key}"] = num(mean_over(evals, method, "mase"))
        out[f"HARM_IR_{key}"] = pct(mean_over(evals, method, "intervention_rate"))
        out[f"HARM_HIR_{key}"] = pct(mean_over(evals, method, "conditional_hir"))
        out[f"HARM_HL_{key}"] = num(mean_over(evals, method, "harmful_loss"), 4)
        value = mean_over(evals, method, "beneficial_precision")
        out[f"HARM_BP_{key}"] = pct(value) if value is not None else "---"
        out[f"HARM_MO_{key}"] = pct(mean_over(evals, method, "missed_opportunity"))

    # Ablation and cost.
    for method, key in ABL_KEY.items():
        if method not in primary["rows"]:
            continue
        out[f"ABL_{key}_MASE"] = num(mean_over(evals, method, "mase"))
        out[f"ABL_{key}_IR"] = pct(mean_over(evals, method, "intervention_rate"))
        out[f"ABL_{key}_HIR"] = pct(mean_over(evals, method, "conditional_hir"))
        out[f"ABL_{key}_HL"] = num(mean_over(evals, method, "harmful_loss"), 4)
        rate = mean_over(evals, method, "intervention_rate")
        out[f"ABL_{key}_CALLS"] = num(1.0 + rate, 2) if rate is not None else None
        out[f"AF_{key}_MASE"] = out[f"ABL_{key}_MASE"]
        out[f"AF_{key}_RMSSE"] = num(mean_over(evals, method, "rmsse"))
        out[f"AF_{key}_IR"] = out[f"ABL_{key}_IR"]
        out[f"AF_{key}_CHIR"] = out[f"ABL_{key}_HIR"]
        out[f"AF_{key}_HL"] = out[f"ABL_{key}_HL"]
        out[f"AF_{key}_CALLS"] = out[f"ABL_{key}_CALLS"]

    # Per-source tables.
    for backbone, tag in BACKBONES:
        e = evals.get(backbone)
        if not e:
            continue
        for method, key in METHOD_KEY.items():
            row = e["rows"].get(method)
            if not row:
                continue
            split = row.get("per_source_horizon_mase", {})
            for horizon in (96, 192):
                values = []
                for source, skey in SOURCE_KEY.items():
                    value = split.get(f"h{horizon}|{source}",
                                      row["per_source_mase"].get(source))
                    out[f"SRC_{tag}_{key}_{horizon}_{skey}"] = num(value)
                    if value is not None:
                        values.append(value)
                if values:
                    out[f"SRC_{tag}_{key}_{horizon}_MACRO"] = num(sum(values) / len(values))

    # Heterogeneity and the two premises of Section 4.2.
    het = primary["heterogeneity"]
    shares = het["oracle_best_share"]
    ordered = sorted(shares.items(), key=lambda kv: -kv[1])
    out["MAIN_HET_SHARES"] = (
        "No catalog action is oracle-best on more than "
        + pct(ordered[0][1], 0) + " of the episodes, and every action is best on at least "
        + pct(ordered[-1][1], 0) + " of them, so the best action is a property of the request "
        "rather than of the dataset")
    keep_mase = primary["rows"]["NATIVE_KEEP"]["mase"]
    oracle_mase = primary["rows"]["CATALOG_ORACLE"]["mase"]
    fixed_mase = primary["rows"]["BEST_FIXED"]["mase"]
    out["MAIN_HET_GAP"] = (
        f"The catalog oracle reaches {oracle_mase:.3f} source-macro MASE against "
        f"{keep_mase:.3f} for the untouched input, so the catalog does carry room to improve")
    out["MAIN_FIXED_ORACLE_GAP"] = (
        f"The best fixed intervention closes only "
        f"{(keep_mase - fixed_mase) / (keep_mase - oracle_mase) * 100:.0f}\\% of that room, "
        f"which is what a per-request decision has to recover")

    # Splits.
    out["TEST_PARENTS"] = str(primary["parents"])
    out["TEST_ORIGINS"] = str(primary["episodes"])
    out["TEST_SOURCES"] = str(len(primary["sources"]))
    out["N_DATASETS"] = "eight"
    if selections:
        first = next(iter(selections.values()))
        out["FIT_PARENTS"] = str(first["parents"])
        out["FIT_ORIGINS"] = str(first["episodes"])
        out["FIT_SOURCES"] = str(first["sources"])
        out["GATE_HARM_CAP"] = pct(first["harm_cap"]["cap"])
    for backbone in ("bolt", "timesfm", "chronos2"):
        path = EVAL / f"train_eval_{backbone}.json"
        if path.exists():
            payload = json.loads(path.read_text())
            out["EVAL_PARENTS"] = str(payload["parents"])
            out["EVAL_ORIGINS"] = str(payload["episodes"])
            out["EVAL_SOURCES"] = str(len(payload["sources"]))
            break

    # Headline differences.
    comp = primary["comparisons"]
    out["ABS_DELTA_KEEP"] = num(-comp["FULL_INTROACT_vs_NATIVE_KEEP"]["difference"])
    out["ABS_DELTA_BF"] = num(-comp["FULL_INTROACT_vs_BEST_FIXED"]["difference"])
    names = {"bolt": "Bolt", "timesfm": "TimesFM", "chronos2": "Chronos-2"}
    keep_parts, fixed_parts = [], []
    for backbone in ("bolt", "timesfm", "chronos2"):
        e = evals.get(backbone)
        if not e:
            continue
        keep_parts.append(f"{names[backbone]} {ci(e['comparisons']['FULL_INTROACT_vs_NATIVE_KEEP'])}")
        fixed_parts.append(f"{names[backbone]} {ci(e['comparisons']['FULL_INTROACT_vs_BEST_FIXED'])}")
    sig_keep = [names[b] for b in evals
                if evals[b]["comparisons"]["FULL_INTROACT_vs_NATIVE_KEEP"]["excludes_zero"]]
    sig_fixed = [names[b] for b in evals
                 if evals[b]["comparisons"]["FULL_INTROACT_vs_BEST_FIXED"]["excludes_zero"]]
    tail_keep = ("and every interval excludes zero" if len(sig_keep) == len(evals)
                 else "and the interval excludes zero on " + ", ".join(sorted(sig_keep)))
    if not sig_fixed:
        tail_fixed = "no interval excludes zero"
    elif len(sig_fixed) == len(evals):
        tail_fixed = "every interval excludes zero"
    else:
        tail_fixed = "the interval excludes zero on " + ", ".join(sorted(sig_fixed))
    out["MAIN_DELTA_CI"] = (
        "Against the untouched input the paired difference is "
        + ", ".join(keep_parts) + ", " + tail_keep
        + ". Against the best fixed intervention " + tail_fixed)
    out["MAIN_INTERVENTION_RATE"] = pct(mean_over(evals, "FULL_INTROACT", "intervention_rate"))
    out["HARM_HIR_OURS"] = pct(mean_over(evals, "FULL_INTROACT", "conditional_hir"))
    out["STRONG_BASELINE"] = "the best fixed intervention"
    out["N_BOOTSTRAP"] = "2,000"

    import fill_v46_reading
    recon = primary.get("reconstruction")
    if recon:
        tags = {"FFILL": "FFILL", "SINGLE_TSICL": "SINGLE", "MULTI_TSICL": "MULTI",
                "CONTEXT_RIDGE": "RIDGE", "SAITS": "SAITS"}
        for action, tag in tags.items():
            item = recon["per_action"].get(action)
            if not item:
                continue
            out[f"REC_{tag}_MSE"] = num(item["rec_mse"], 2)
            out[f"REC_{tag}_MAE"] = num(item["rec_mae"], 2)
            out[f"REC_{tag}_UTIL"] = signed(item["mean_utility"])
            out[f"REC_{tag}_N"] = str(item["n"])
        out["RECON_AGREE"] = pct(recon["winner_agreement"])
        out["DISCORDANT_RATE"] = pct(recon["discordant_rate"])
        out["RECON_RHO"] = num(recon["mean_within_episode_spearman"], 2)

    # The caption promises that the best deployable value in each column is
    # bold and the second best underlined, so mark them here rather than
    # leaving the promise unkept.
    deployable = ("KEEP", "BF", "R2", "SAITS", "TATO", "OURS")
    for column in [f"_{tag}" for tag in ("BOLT", "TF", "CH2", "OVR", "RMSSE")]:
        values = {}
        for key in deployable:
            text = out.get(f"{key}{column}")
            if text is None:
                continue
            try:
                values[key] = float(text)
            except ValueError:
                continue
        if len(values) < 2:
            continue
        order = sorted(values, key=lambda k: values[k])
        out[f"{order[0]}{column}"] = chr(92) + "best{" + out[f"{order[0]}{column}"] + "}"
        out[f"{order[1]}{column}"] = chr(92) + "second{" + out[f"{order[1]}{column}"] + "}"
    ranks = {}
    for key in deployable:
        text = out.get(f"{key}_RANK")
        if text is None:
            continue
        try:
            ranks[key] = float(text)
        except ValueError:
            continue
    if len(ranks) >= 2:
        order = sorted(ranks, key=lambda k: ranks[k])
        out[f"{order[0]}_RANK"] = chr(92) + "best{" + out[f"{order[0]}_RANK"] + "}"
        out[f"{order[1]}_RANK"] = chr(92) + "second{" + out[f"{order[1]}_RANK"] + "}"

    out.update(fill_v46_reading.build(evals, primary, mean_over, ci, selections))
    import fill_v46_extra
    out.update(fill_v46_extra.build(evals, selections, num, pct))
    import fill_v46_cost
    out.update(fill_v46_cost.build(num, pct))
    import fill_v46_strata
    out.update(fill_v46_strata.build(num, pct))
    import fill_v46_env
    out.update(fill_v46_env.build())
    return {k: v for k, v in out.items() if v is not None}


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "latex/IntroActTS_20260919_v46.tex"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "latex/IntroActTS_20260919_v46_filled.tex"
    evals, selections = load()
    table = build(evals, selections)
    text = io.open(src, encoding="utf-8").read()
    before = len(re.findall(r"\\ph\{", text))

    def repl(match):
        key = match.group(1)
        return table.get(key, match.group(0))

    text = re.sub(r"\\ph\{([A-Za-z0-9_\-]+)\}", repl, text)
    after = len(re.findall(r"\\ph\{", text))
    io.open(dst, "w", encoding="utf-8").write(text)
    missing = sorted({m for m in re.findall(r"\\ph\{([A-Za-z0-9_\-]+)\}", text)})
    print(json.dumps({"backbones": sorted(evals), "filled": before - after,
                      "remaining": after, "distinct_remaining": len(missing),
                      "target": str(dst)}, indent=1))
    (ROOT / "results/v46/evaluation/placeholder_status.json").write_text(
        json.dumps({"filled_keys": sorted(table), "remaining_keys": missing}, indent=1))


if __name__ == "__main__":
    main()
