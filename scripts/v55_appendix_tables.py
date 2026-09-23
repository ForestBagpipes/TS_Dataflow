#!/usr/bin/env python3
"""Generate v55 source and pattern tables from the frozen evaluation JSONs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from v55_forecast_coverage import METHODS as EXTERNAL, check as check_external
from v55_paper_tables import BACKBONES, ORACLE, OURS, ROSTER


ROOT = Path(__file__).resolve().parent.parent
SOURCES = ("ETTh1", "ETTh2", "ETTm1", "ETTm2", "Electricity", "Exchange",
           "Traffic", "Weather")
PATTERNS = (("P1_point", "P1 Point"),
            ("P2_target_block", "P2 Target Block"),
            ("P3_shared_block", "P3 Shared Block"),
            ("P4_tail", "P4 Tail"))
LABEL = {"bolt": "Bolt", "timesfm": "TimesFM", "chronos2": "Chronos-2"}
ROWS = ROSTER + [OURS, ORACLE]


def formatted(label: str, values: list[float], macro: float) -> str:
    cells = [f"{value:.3f}" for value in values] + [f"{macro:.3f}"]
    prefix = r"\rowcolor{bestgray}" if label == OURS[1] else ""
    return f"    {prefix}{label} & " + " & ".join(cells) + r" \\"


def make_tables(root: Path, *, partial: bool = False) -> str:
    if not partial:
        check_external(root, EXTERNAL)
    data = {bb: json.loads((root / "results/v55/evaluation" /
                            f"test_{bb}.json").read_text()) for bb in BACKBONES}
    for bb, payload in data.items():
        if payload.get("episodes") != 760 or payload.get("block") != "test":
            raise ValueError(f"{bb}: incomplete main TEST evaluation")
    available = [(key, label) for key, label in ROWS
                 if all(key in data[bb]["rows"] for bb in BACKBONES)]
    missing = [key for key, _ in ROWS if key not in {k for k, _ in available}]
    if missing and not partial:
        raise ValueError(f"missing paper rows: {missing}")
    lines = ["% Generated from results/v55/evaluation/test_{bolt,timesfm,chronos2}.json",
             "% Do not edit numeric cells by hand."]
    for bb in BACKBONES:
        for horizon in (96, 192):
            lines.extend([
                r"\begin{table}[htbp]",
                (f"  \\caption{{Per-source MASE on {LABEL[bb]} at 10\\% missingness, "
                 f"$H={horizon}$. Macro equally weights the eight sources.}}"),
                f"  \\label{{tab:app-src-{bb}-{horizon}}}",
                r"  \centering", r"  \small", r"  \setlength{\tabcolsep}{3pt}",
                r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}",
                r"    \toprule",
                ("    Method & " + " & ".join(SOURCES) + r" & Macro $\downarrow$ \\"),
                r"    \midrule",
            ])
            for key, label in available:
                row = data[bb]["rows"][key]
                values = [row["per_source_horizon_mase"][f"h{horizon}|{source}"]
                          for source in SOURCES]
                lines.append(formatted(label, values, sum(values) / len(values)))
                if key == OURS[0]:
                    lines.insert(len(lines) - 1, r"    \midrule")
            lines.extend([r"    \bottomrule", r"  \end{tabular*}",
                          r"\end{table}", ""])
    lines.extend([
        r"\begin{table}[htbp]",
        (r"  \caption{Per-pattern MASE at 10\% missingness, source-macro "
         r"averaged over three backbones and both horizons. Overall is the "
         r"equal-weight mean of the four patterns and matches the main table.}"),
        r"  \label{tab:app-pattern-res}", r"  \centering", r"  \small",
        r"  \setlength{\tabcolsep}{4pt}",
        r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrr@{}}",
        r"    \toprule",
        ("    Method & " + " & ".join(label for _, label in PATTERNS) +
         r" & Overall $\downarrow$ \\"),
        r"    \midrule",
    ])
    for key, label in available:
        values = []
        for pattern, _ in PATTERNS:
            cells = [data[bb]["rows"][key]["per_cell_mase"]
                     [f"h{horizon}|{pattern}|s10"]
                     for bb in BACKBONES for horizon in (96, 192)]
            values.append(sum(cells) / len(cells))
        overall = sum(values) / len(values)
        expected = sum(data[bb]["rows"][key]["mase"] for bb in BACKBONES) / 3
        if abs(overall - expected) > 1e-6:
            raise ValueError(f"{key}: pattern average differs from main table")
        if key == OURS[0]:
            lines.append(r"    \midrule")
        lines.append(formatted(label, values, overall))
    lines.extend([r"    \bottomrule", r"  \end{tabular*}", r"\end{table}", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "latex/tables/v55_appendix_tables.tex")
    parser.add_argument("--partial", action="store_true",
                        help="preview with currently available rows only")
    args = parser.parse_args()
    result = make_tables(args.root, partial=args.partial)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result)
    print(json.dumps({"output": str(args.output),
                      "tables": 7, "partial": args.partial}))


if __name__ == "__main__":
    main()
