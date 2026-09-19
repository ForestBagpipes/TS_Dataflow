"""Per-pattern cells, the penalty grid, and the severity sweep.

All three come from records the main evaluation already wrote, so nothing here
re-runs a forecast.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN_KEY = {"P1_point": "P1", "P2_target_block": "P2",
               "P3_shared_block": "P3", "P4_tail": "P4"}
METHOD_KEY = {"NATIVE_KEEP": "KEEP", "BEST_FIXED": "BF", "R2_CART": "R2",
              "SAITS": "SAITS", "TATO": "TATO", "FULL_INTROACT": "OURS"}
SEV_KEY = {"test": "10", "test30": "30", "test50": "50"}


def build(evals: dict, selections: dict, num, pct) -> dict:
    out: dict[str, str] = {}

    # Per-pattern MASE, averaged over the backbones that finished.
    for method, key in METHOD_KEY.items():
        per_pattern: dict[str, list[float]] = {p: [] for p in PATTERN_KEY}
        ranks: list[float] = []
        for e in evals.values():
            row = e["rows"].get(method)
            if not row:
                continue
            for cell, value in row["per_cell_mase"].items():
                pattern = cell.split("|")[1]
                if pattern in per_pattern and value is not None:
                    per_pattern[pattern].append(value)
            if e["average_rank"].get(method) is not None:
                ranks.append(e["average_rank"][method])
        for pattern, tag in PATTERN_KEY.items():
            values = per_pattern[pattern]
            if values:
                out[f"{tag}_{key}"] = num(sum(values) / len(values))
        if ranks:
            out[f"PR_{key}"] = num(sum(ranks) / len(ranks), 2)

    # The penalty and neighbourhood grid, from the cross-validated selection.
    if selections:
        first = next(iter(selections.values()))
        for row in first["selection"]["grid"]:
            tag = f"K{row['k']}B{str(row['beta']).replace('.', '')}"
            out[f"GRID_{tag}_MASE"] = num(row["lopo_mase"])
            out[f"GRID_{tag}_IR"] = pct(row["intervention_rate"])
            out[f"GRID_{tag}_HIR"] = pct(row["conditional_hir"])

    # Severity sweep: one row per method per level.
    severity: dict[str, dict[str, list[float]]] = {}
    for block, level in SEV_KEY.items():
        for backbone in ("bolt", "timesfm", "chronos2"):
            path = ROOT / f"results/v46/evaluation/{block}_{backbone}.json"
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            for method, key in METHOD_KEY.items():
                row = payload["rows"].get(method)
                if row and row.get("mase") is not None:
                    severity.setdefault(level, {}).setdefault(key, []).append(row["mase"])
    for level, methods in severity.items():
        for key, values in methods.items():
            out[f"RB_{key}_{level}"] = num(sum(values) / len(values))
            out[f"SEV{level}-{key}-MASE"] = num(sum(values) / len(values))
    # Replay-bank size, averaged over the backbones that ran it.
    sizes: dict[str, list[dict]] = {}
    for backbone in ("bolt", "timesfm", "chronos2"):
        path = ROOT / f"results/v46/ablations/banksize_test_{backbone}.json"
        if path.exists():
            for row in json.loads(path.read_text())["rows"]:
                sizes.setdefault(f"{int(row['fraction'] * 100)}", []).append(row)
    for tag, rows in sizes.items():
        n = len(rows)
        out[f"RS{tag}_MASE"] = num(sum(r["mase"] for r in rows) / n)
        out[f"RS{tag}_IR"] = pct(sum(r["intervention_rate"] for r in rows) / n)
        out[f"RS{tag}_HIR"] = pct(sum(r["conditional_hir"] for r in rows) / n)
        out[f"RS{tag}_HL"] = num(sum(r["harmful_loss"] for r in rows) / n, 4)
        out[f"RS{tag}_CALLS"] = num(1.0 + sum(r["intervention_rate"] for r in rows) / n, 2)

    # Per-backbone bank-size anchors.  The averaged rows above hide the
    # direction, and the appendix sentence is about the direction.
    for backbone, tag in (("bolt", "BOLT"), ("timesfm", "TF"), ("chronos2", "CH2")):
        path = ROOT / f"results/v46/ablations/banksize_test_{backbone}.json"
        if not path.exists():
            continue
        rows = sorted(json.loads(path.read_text())["rows"], key=lambda r: r["fraction"])
        values = [r["mase"] for r in rows if r.get("mase") is not None]
        if not values:
            continue
        out[f"BANK_Q_{tag}"] = num(values[0])
        out[f"BANK_F_{tag}"] = num(values[-1])
        out[f"BANK_SPREAD_{tag}"] = num(max(values) - min(values), 3)

    # Holm across the pre-declared baseline comparisons, reported in full.
    names = {"NATIVE_KEEP": "the untouched input", "BEST_FIXED": "the best fixed intervention",
             "R2_CART": "the simple selector", "SAITS": "SAITS", "TATO": "TATO"}
    titles = {"bolt": "Bolt", "timesfm": "TimesFM", "chronos2": "Chronos-2"}
    rows, survived, against_fixed = [], {}, []
    for backbone in ("bolt", "timesfm", "chronos2"):
        payload = evals.get(backbone)
        if not payload:
            continue
        for key, label in names.items():
            entry = payload["comparisons"].get(f"FULL_INTROACT_vs_{key}")
            if not entry or "p_holm" not in entry:
                continue
            rows.append("    %s & %s & %+.4f & [%+.4f, %+.4f] & %.4f & %.4f %s" % (
                titles.get(backbone, backbone), label, entry["difference"],
                entry["ci_low"], entry["ci_high"], entry["p_value"], entry["p_holm"],
                chr(92) * 2))
            if entry["significant_holm"]:
                survived.setdefault(key, []).append(titles.get(backbone, backbone))
            if key == "BEST_FIXED" and entry["significant_holm"]:
                against_fixed.append(titles.get(backbone, backbone))
    if rows:
        out["HOLM_ROWS"] = chr(10).join(rows)
        keep_where = survived.get("NATIVE_KEEP", [])
        sentence = "Holm correction over the five baseline comparisons leaves the difference"
        if len(keep_where) == 3:
            sentence += " against the untouched input below $0.05$ on every backbone"
        elif keep_where:
            sentence += (" against the untouched input below $0.05$ on "
                         + " and ".join(keep_where))
        if against_fixed:
            sentence += (" and the one against the best fixed intervention below $0.05$ on "
                         + " and ".join(against_fixed))
        out["MAIN_HOLM"] = sentence

    # Selection stability over parent-level subsamples of the replay bank.
    titles = {"bolt": "Bolt", "timesfm": "TimesFM", "chronos2": "Chronos-2"}
    stab_rows, same, worst, all_better = [], [], [], True
    for backbone in ("bolt", "timesfm", "chronos2"):
        path = ROOT / f"results/v46/ablations/selection_stability_test_{backbone}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        keep = None
        eval_path = ROOT / f"results/v46/evaluation/test_{backbone}.json"
        if eval_path.exists():
            keep = json.loads(eval_path.read_text())["rows"]["NATIVE_KEEP"]["mase"]
        for row in payload["rows"]:
            share = "full bank" if row["seed"] is None else f"{row['fraction'] * 100:.0f}\\%"
            stab_rows.append("    %s & %s & %d & %s & %.3f & %.1f\\%% %s" % (
                titles.get(backbone, backbone), share, row["k"],
                ("%.2f" % row["beta"]).rstrip("0").rstrip("."),
                row["mase"], row["intervention_rate"] * 100, chr(92) * 2))
            if keep is not None and row["mase"] >= keep:
                all_better = False
        same.append(payload["same_choice_share"])
        worst.append(payload["worst_gap_to_frozen"])
    if stab_rows:
        out["SELSTAB_ROWS"] = chr(10).join(stab_rows)
        share = sum(same) / len(same) * 100.0
        out["SELSTAB_READING"] = (
            f"The rule reproduces the frozen pair on {share:.0f}\\% of the subsamples, so the "
            f"pair itself is not a stable point of the grid. The outcome is steadier than the "
            f"pair: the worst subsample choice costs {max(worst):.3f} MASE against the frozen "
            f"one")
        if all_better:
            out["SELSTAB_READING"] += (
                ", and every subsample choice still improves on the untouched input. This is "
                "what the standard-error rule is for, because on a bank of this size the "
                "settings inside one standard error of the leader cannot be told apart")

    # The governance figure reading, from the score-against-utility records.
    agree, positive, negative, pairs = [], [], [], 0
    for backbone in ("bolt", "timesfm", "chronos2"):
        path = ROOT / f"results/v46/diagnostics/score_utility_test_{backbone}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        agree.append(payload["sign_agreement"])
        if payload.get("mean_utility_positive_score") is not None:
            positive.append(payload["mean_utility_positive_score"])
        if payload.get("mean_utility_negative_score") is not None:
            negative.append(payload["mean_utility_negative_score"])
        pairs += payload["pairs"]
    if agree and positive and negative:
        out["GOV_FIG_READING"] = (
            f"Over {pairs} admissible pairs the sign of the score and the sign of the realised "
            f"utility agree on {sum(agree) / len(agree) * 100:.0f}\\% of them, and the mean "
            f"realised utility is {sum(positive) / len(positive):+.3f} where the score is "
            f"positive against {sum(negative) / len(negative):+.3f} where it is negative, so the "
            f"score carries the direction the decision needs without carrying the level")

    # The severity reading, written from the sweep itself.
    levels = [lv for lv in ("10", "30", "50") if lv in severity]
    if len(levels) >= 2:
        def row(level, key):
            values = severity[level].get(key)
            return sum(values) / len(values) if values else None

        parts = []
        for level in levels:
            keep, ours = row(level, "KEEP"), row(level, "OURS")
            if keep is not None and ours is not None:
                parts.append(f"{level}\\% {ours:.3f} against {keep:.3f}")
        out["ROBUST_READING"] = (
            "Against the untouched input the frozen configuration holds at every level: "
            + ", ".join(parts))
        beaten = []
        for level in levels:
            ours = row(level, "OURS")
            rivals = {k: row(level, k) for k in ("BF", "R2") if row(level, k) is not None}
            better = [k for k, v in rivals.items() if v < ours]
            if better:
                beaten.append((level, better, min(rivals.values())))
        name = {"BF": "the best fixed intervention", "R2": "the simple selector"}
        if beaten:
            worst = ", ".join(
                f"at {lv}\\% {' and '.join(name[b] for b in bs)} reaches {v:.3f}"
                for lv, bs, v in beaten)
            out["ROBUST_30"] = (
                "The ordering between the deployable rows does change with severity: " + worst)
            out["ROBUST_50"] = (
                "The configuration is frozen on a bank that mixes the three levels, so the sweep "
                "shows how far one operating point carries rather than what a per-level tuning "
                "could reach")
        else:
            # We lead at every level.  Whether the rows below keep their order is
            # a separate question, and the answer does not have to be yes.
            orders = []
            for level in levels:
                values = {k: row(level, k) for k in ("KEEP", "BF", "R2", "SAITS", "TATO")
                          if row(level, k) is not None}
                orders.append(tuple(sorted(values, key=values.get)))
            stable = len(set(orders)) == 1
            out["ROBUST_30"] = (
                "The method holds the lowest macro average at every level"
                + (", and the rows below it hold their order too" if stable else
                   ", and the rows below it change order between levels, so the sweep separates "
                   "the method from the roster rather than reproducing one ranking"))
            out["ROBUST_50"] = (
                "The configuration is frozen on a bank that mixes the three levels and is not "
                "retuned per level")
    return out
