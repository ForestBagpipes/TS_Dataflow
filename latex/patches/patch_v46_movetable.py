"""Move the severity table to the appendix and leave Section 4.5 as prose.

The severity sweep is a secondary claim and the appendix already holds the
complete per-severity tables, so the body keeps the reading and drops the
duplicate float.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"
START = "\\begin{table}[t]\n  \\caption{Within-grid robustness to missingness severity"
END = "\\end{table}"
ANCHOR = "\\subsubsection{Robustness Trend Figure}"


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    i = text.find(START)
    assert i > 0, "severity table"
    j = text.find(END, i) + len(END)
    table = text[i:j]
    text = text[:i].rstrip() + "\n" + text[j:].lstrip("\n")
    text = text.replace("Table~\\ref{tab:robust} reports the severity trend and the worst pattern cell",
                        "Table~\\ref{tab:robust} in Appendix~\\ref{app:severity-full} reports the "
                        "severity trend and the worst pattern cell")
    assert ANCHOR in text, "appendix anchor"
    text = text.replace(ANCHOR, table.replace("[t]", "[h]") + "\n\n" + ANCHOR, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("severity table moved to the appendix")


if __name__ == "__main__":
    main()
