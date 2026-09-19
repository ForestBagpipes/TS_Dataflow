"""Report the Holm adjustment the statistics appendix promises.

The evaluation stage now adjusts the five pre-declared baseline comparisons, so
the main paragraph says which of them survive and the appendix carries the raw
and adjusted values in full.
"""
import io

TEX = "latex/IntroActTS_20260919_v46.tex"
EXTRA = "latex/fill_v46_extra.py"

OLD_TEX = r"""\ph{MAIN_RANK}. Per-source MASE, MAE, and RMSE are in Appendix~\ref{app:datasets}, and"""
NEW_TEX = r"""\ph{MAIN_RANK}. \ph{MAIN_HOLM}.
Per-source MASE, MAE, and RMSE are in Appendix~\ref{app:datasets}, and"""

OLD_APP = r"""correction~\citep{holm1979simple} is applied across the pre-declared baseline comparisons.
Average rank and won cells are descriptive summaries only, and the headline claim rests on
paired differences with confidence intervals."""

NEW_APP = r"""correction~\citep{holm1979simple} is applied across the pre-declared baseline comparisons.
The family is the five comparisons of \introact{} against the deployable baselines on one
backbone, and the ablations stay outside it because they are variants of this method rather
than competing claims. Table~\ref{tab:app-holm} lists every raw and adjusted value.
Average rank and won cells are descriptive summaries only, and the headline claim rests on
paired differences with confidence intervals.

\begin{table}[h]
  \caption{Paired differences against the deployable baselines with the Holm adjustment.
  A negative difference favours \introact{}. The p-value is two sided and read off the same
  bootstrap draws as the interval, so it cannot fall below one over the number of resamples.}
  \label{tab:app-holm}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{llcccc}
    \toprule
    Backbone & Comparison & Difference & 95\% interval & $p$ & $p$ after Holm \\
    \midrule
\ph{HOLM_ROWS}
    \bottomrule
  \end{tabular}}
\end{table}"""

ANCHOR = '''    # The governance figure reading, from the score-against-utility records.'''

BLOCK = '''    # Holm across the pre-declared baseline comparisons, reported in full.
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
        sentence = "After Holm correction across the five baseline comparisons"
        if len(keep_where) == 3:
            sentence += (", the difference against the untouched input stays below $0.05$ on "
                         "every backbone")
        elif keep_where:
            sentence += (", the difference against the untouched input stays below $0.05$ on "
                         + " and ".join(keep_where))
        if against_fixed:
            sentence += (", and the difference against the best fixed intervention stays below "
                         "$0.05$ on " + " and ".join(against_fixed))
        out["MAIN_HOLM"] = sentence

    # The governance figure reading, from the score-against-utility records.'''


def main() -> None:
    text = io.open(TEX, encoding="utf-8").read()
    assert OLD_TEX in text, "main rank line"
    assert OLD_APP in text, "statistics appendix"
    text = text.replace(OLD_TEX, NEW_TEX, 1)
    text = text.replace(OLD_APP, NEW_APP, 1)
    io.open(TEX, "w", encoding="utf-8").write(text)

    code = io.open(EXTRA, encoding="utf-8").read()
    assert ANCHOR in code, "extra anchor"
    io.open(EXTRA, "w", encoding="utf-8").write(code.replace(ANCHOR, BLOCK, 1))
    print("Holm table and sentence added")


if __name__ == "__main__":
    main()
