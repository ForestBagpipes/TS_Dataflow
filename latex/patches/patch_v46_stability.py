"""Report how much of the result rests on the exact configuration the bank chose.

The cross-validated surface is rough, so the natural question is whether the
selected pair is a property of the rule or of this particular bank.  The answer
is that the pair moves and the outcome does not, and the appendix now says so
with the measurements behind it.
"""
import io

TEX = "latex/IntroActTS_20260919_v46.tex"
EXTRA = "latex/fill_v46_extra.py"

ANCHOR_TEX = r"""\subsection{Mask-Realisation Stability}"""

NEW_SECTION = r"""\subsection{Selection Stability}
\label{app:selstability}
The cross-validated surface over the grid is rough, so the pair the bank selects is worth
questioning directly. This subsection repeats the whole selection procedure on parent-level
subsamples of the replay bank, at half and at three quarters of its parents with three draws
each, and records what the rule picks and what that pick produces on the evaluation block. The
evaluation figures are diagnostics. Nothing in the paper is selected from them, and the
reported configuration stays the one the full bank chooses.

\ph{SELSTAB_READING}.

\begin{table}[h]
  \caption{Selection stability. Each row is one subsample of the replay bank, with the pair the
  rule selected on it and the evaluation outcome that pair produces. The first row of each
  backbone is the configuration the paper reports.}
  \label{tab:app-selstab}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lccccc}
    \toprule
    Backbone & Bank share & Selected $k$ & Selected $\beta$ & MASE $\downarrow$ & Intervention rate \\
    \midrule
\ph{SELSTAB_ROWS}
    \bottomrule
  \end{tabular}}
\end{table}

\subsection{Mask-Realisation Stability}"""

ANCHOR_PY = '''    # The governance figure reading, from the score-against-utility records.'''

BLOCK_PY = '''    # Selection stability over parent-level subsamples of the replay bank.
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
            share = "full bank" if row["seed"] is None else f"{row['fraction'] * 100:.0f}\\\\%"
            stab_rows.append("    %s & %s & %d & %s & %.3f & %.1f\\\\%% %s" % (
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
            f"The rule reproduces the frozen pair on {share:.0f}\\\\% of the subsamples, so the "
            f"pair itself is not a stable point of the grid. The outcome is steadier than the "
            f"pair: the worst subsample choice costs {max(worst):.3f} MASE against the frozen "
            f"one")
        if all_better:
            out["SELSTAB_READING"] += (
                ", and every subsample choice still improves on the untouched input. This is "
                "what the standard-error rule is for, because on a bank of this size the "
                "settings inside one standard error of the leader cannot be told apart")

    # The governance figure reading, from the score-against-utility records.'''


def main() -> None:
    text = io.open(TEX, encoding="utf-8").read()
    assert ANCHOR_TEX in text, "stability anchor"
    io.open(TEX, "w", encoding="utf-8").write(text.replace(ANCHOR_TEX, NEW_SECTION, 1))

    code = io.open(EXTRA, encoding="utf-8").read()
    assert ANCHOR_PY in code, "extra anchor"
    io.open(EXTRA, "w", encoding="utf-8").write(code.replace(ANCHOR_PY, BLOCK_PY, 1))
    print("selection stability appendix added")


if __name__ == "__main__":
    main()
