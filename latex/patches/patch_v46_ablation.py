"""Seventh v4.6 patch: the ablation ladder, its table, and the Figure 3 caption.

A4 is redefined from "remove the dispersion penalty" to "remove the reference
option", which is the component the section is actually about.  The latency
column is dropped because this run records per-call runtime but not end-to-end
request latency.
"""
import io
import re

PATH = "latex/IntroActTS_20260918_v45_review.tex"


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()

    old = ("variants rather than new forecasting runs. A1 removes the dependence on the request, A2 the\n"
           "intervention state, A3 the reference-forecast state, A4 the conservative penalty, and A5\n"
           "replaces the non-parametric estimate with a parametric utility predictor, with the exact\n"
           "definitions in Appendix~\\ref{app:ablation-details}. Table~\\ref{tab:ablation} reports accuracy,\n"
           "harm, and cost together.")
    new = ("variants rather than new forecasting runs. A1 scores each action by its global mean utility\n"
           "instead of by its neighbourhood, A2 and A3 drop the intervention and the reference-forecast\n"
           "block of the state, A4 removes the reference option so that an action runs on every request,\n"
           "and A5 replaces the local estimate with a per-action linear utility predictor over the same\n"
           "features. Appendix~\\ref{app:ablation-details} gives the exact definitions.\n"
           "Table~\\ref{tab:ablation} reports accuracy, harm, and cost together.")
    assert old in text, "ablation intro"
    text = text.replace(old, new)

    text = text.replace("A4 w/o conservative gate   &", "A4 Always act              &")
    text = text.replace("A4 w/o conservative gate    &", "A4 Always act               &")

    old_cap = ("  \\caption{Core ablation and cost at $10\\%$ severity. All rows read the same catalog\n"
               "  prediction cache. Latency is end-to-end request latency and calls counts forecasting-backbone\n"
               "  calls per request, with candidate materialisation reported in Appendix~\\ref{app:calls}. The\n"
               "  Reconstruction Oracle reads the hidden values and is excluded from every rank.}")
    new_cap = ("  \\caption{Core ablation and cost at $10\\%$ severity, on the held-out evaluation set. Every\n"
               "  row reads the same catalog prediction cache, so the rows differ only in how the stored\n"
               "  utilities are summarised and thresholded. Calls counts forecasting-backbone calls per\n"
               "  request and equals one plus the intervention rate; candidate materialisation is reported\n"
               "  separately in Appendix~\\ref{app:calls}.}")
    assert old_cap in text, "ablation caption"
    text = text.replace(old_cap, new_cap)

    old_fig = ("  \\caption{Why the decision needs forecasting utility and why it has to be selective.\n"
               "  \\textbf{(a)}~Within-parent reconstruction rank against forecasting-utility rank. A lower\n"
               "  reconstruction error does not imply a higher realised utility, so a reconstruction criterion\n"
               "  is not a substitute for the utility the deployment decision is about. \\textbf{(b)}~Risk\n"
               "  against intervention rate. A low harmful rate is only meaningful together with the\n"
               "  intervention rate at which it was obtained, because a method that almost never intervenes\n"
               "  reaches a low harmful rate without being useful.}")
    new_fig = ("  \\caption{\\textbf{(a)}~Within-episode reconstruction rank against realised-utility rank\n"
               "  over the four catalog interventions on the held-out episodes. Points off the diagonal are\n"
               "  episodes where the more accurate reconstruction is not the more useful intervention.\n"
               "  \\textbf{(b)}~Conditional harmful rate against intervention rate along the penalty grid,\n"
               "  with the selected operating point marked.}")
    assert old_fig in text, "figure 3 caption"
    text = text.replace(old_fig, new_fig)

    # The latency column has no measurement behind it in this run.
    text = text.replace(" & Calls $\\downarrow$ & Latency (ms) $\\downarrow$ \\\\",
                        " & Calls $\\downarrow$ \\\\")
    text = re.sub(r"\s*&\s*\\\\ph\{ABL_(?:FULL|A[1-5]|ORACLE)_LAT\}", "", text)
    text = re.sub(r"\s*&\s*\\ph\{ABL_(?:FULL|A[1-5]|ORACLE)_LAT\}", "", text)
    text = re.sub(r"\s*&\s*\\oracle\{\\ph\{ABL_ORACLE_LAT\}\}", "", text)
    text = text.replace("\\resizebox{\\textwidth}{!}{\\begin{tabular}{lcccccc}\n    \\toprule\n    Variant & MASE",
                        "\\resizebox{\\textwidth}{!}{\\begin{tabular}{lccccc}\n    \\toprule\n    Variant & MASE")
    text = text.replace("\\ph{COST_CALLS}. \\ph{COST_LATENCY}.", "\\ph{COST_CALLS}.")

    io.open(PATH, "w", encoding="utf-8").write(text)
    print("ablation patched")


if __name__ == "__main__":
    main()
