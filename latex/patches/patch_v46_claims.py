"""Bring the abstract and the third contribution in line with the measured result.

What holds on all three backbones is the improvement over the untouched input
and the average rank.  The lowest macro average holds on two of them.  The
earlier wording claimed both uniformly.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

OLD_ABS = ("held out from method design, \\introact{} lowers source-macro MASE by "
           "\\ph{ABS_DELTA_KEEP}\nrelative to leaving the input unchanged and by "
           "\\ph{ABS_DELTA_BF} relative to the best fixed\nintervention, with paired "
           "confidence intervals that exclude zero. \\ph{ABSTRACT_CLOSING}.")
NEW_ABS = "held out from method design, \\ph{ABSTRACT_RESULT}. \\ph{ABSTRACT_CLOSING}."

OLD_CON = ("and cost.} Against a no-op control, the best fixed intervention, a simple learned "
           "selector and\npublished reconstruction, task-oriented and data-side adaptation "
           "baselines, on eight sources,\nthree frozen \\tsfm{} families, four missingness "
           "patterns and three severity levels,\n\\introact{} is the best deployable method on "
           "every backbone and executes fewer harmful\ninterventions than any fixed "
           "intervention at one to two backbone calls per request\n"
           "(\\S\\ref{sec:exp-main}, \\S\\ref{sec:exp-harm}, \\S\\ref{sec:exp-robust}).")
NEW_CON = ("and cost.} Against a no-op control, the best fixed intervention and a simple learned\n"
           "selector, on eight sources, three frozen \\tsfm{} families, four missingness patterns\n"
           "and three severity levels, \\introact{} improves on the untouched input on every\n"
           "backbone with paired intervals that exclude zero and has the best average rank of the\n"
           "deployable rows on every backbone, at one to two backbone calls per request. We also\n"
           "report where it does not win, which is the held-out backbone on which one fixed repair\n"
           "reaches a lower macro average (\\S\\ref{sec:exp-main}, \\S\\ref{sec:exp-harm},\n"
           "\\S\\ref{sec:exp-robust}).")


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD_ABS in text, "abstract"
    text = text.replace(OLD_ABS, NEW_ABS)
    assert OLD_CON in text, "contribution"
    text = text.replace(OLD_CON, NEW_CON)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("claims aligned")


if __name__ == "__main__":
    main()
