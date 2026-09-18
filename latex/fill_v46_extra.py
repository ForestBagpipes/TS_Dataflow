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
              "FULL_INTROACT": "OURS"}
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
            out["ROBUST_30"] = "The ordering between the deployable rows is unchanged by severity"
            out["ROBUST_50"] = (
                "The configuration is frozen on a bank that mixes the three levels and is not "
                "retuned per level")
    return out
