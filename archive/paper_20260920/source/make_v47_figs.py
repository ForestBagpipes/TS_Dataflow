#!/usr/bin/env python3
"""Second pass over the v4.7 template: hold the artwork, tabulate the results.

Figures 1 and 2 are the two drawn figures, the concept panel and the
architecture.  They keep their float, their display size and their caption, and
their body becomes a reserved box, so the layout and the page budget are
already settled when the artwork arrives.

Figures 3, 4 and 5 carried results.  At the size they had, a reader took
numbers off them by eye, so each becomes a table over the same records.

Usage: python latex/make_v47_figs.py   (run after make_v47.py)
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
TEX = HERE / "IntroActTS_20260919_v47.tex"

TEXT = TEX.read_text(encoding="utf-8")
APPLIED: list[str] = []
BS = "\\" * 2
NL = " " + BS + "\n"


def sub(old: str, new: str, *, tag: str) -> None:
    global TEXT
    if TEXT.count(old) != 1:
        raise SystemExit(f"FAILED {tag}: anchor appears {TEXT.count(old)} times")
    TEXT = TEXT.replace(old, new)
    APPLIED.append(tag)


def row(cells: list[str], indent: str = "    ") -> str:
    return indent + " & ".join(cells) + NL


# ------------------------------------------------------- the reserved box macro

sub(r"""\newcommand{\ph}[1]{\textcolor{phgray}{\textsf{[\detokenize{#1}]}}}""",
    r"""\newcommand{\ph}[1]{\textcolor{phgray}{\textsf{[\detokenize{#1}]}}}
% Artwork supplied separately.  The box reserves the display size the figure
% will occupy, so neither the layout nor the page budget moves when the drawing
% arrives.  Arguments are the width, the height and the panel name.
\newcommand{\figph}[3]{%
  \fbox{\parbox[c][#2][c]{#1}{\centering
    \textcolor{phgray}{\textsf{[\detokenize{#3}]}}}}}""",
    tag="preamble: a reserved box for artwork")


# ------------------------------------------------------------ figures 1 and 2

sub(r"""  \includegraphics[width=0.64\textwidth]{figure/fig1_selective_governance.pdf}""",
    r"""  \figph{0.64\textwidth}{3.4cm}{FIGURE_1_SELECTIVE_GOVERNANCE}""",
    tag="figure 1: reserved box")

sub(r"""  \includegraphics[width=0.48\textwidth]{figure/fig2_introact_architecture.pdf}""",
    r"""  \figph{0.48\textwidth}{4.6cm}{FIGURE_2_ARCHITECTURE}""",
    tag="figure 2: reserved box")


# ----------------------------------- figure 3 becomes the rank agreement table

RANK_ROWS = "".join(
    row([label] + [f"\\ph{{RG_{i}_{j}}}" for j in range(1, 6)])
    for i, label in enumerate(
        ["1 (most accurate)", "2", "3", "4", "5 (least accurate)"], start=1))

RANKGRID = (r"""\begin{table}[t]
  \caption{Within-episode reconstruction rank against within-episode realised-utility rank,
  over the five catalog interventions and the held-out episodes of all three backbones. Each
  row is normalised, so a cell is the share of episodes at that reconstruction rank whose
  realised utility took the column's rank. A criterion that predicted the other would put every
  episode on the diagonal.}
  \label{tab:rankgrid}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\begin{tabular}{lccccc}
    \toprule
""" + row(["Reconstruction rank", "Utility 1", "Utility 2", "Utility 3", "Utility 4",
           "Utility 5"])
    + "    \\midrule\n" + RANK_ROWS + r"""    \bottomrule
  \end{tabular}
\end{table}""")

FIG3 = r"""\begin{figure}[t]
  \centering
  \includegraphics[width=0.62\textwidth]{figure/fig3_why_selective.pdf}
  \caption{\textbf{(a)}~Joint distribution of the within-episode reconstruction rank and the
  within-episode realised-utility rank over the five catalog interventions,
  row-normalised over
  the held-out episodes of all three backbones. Off-diagonal mass is episodes on which the more
  accurate reconstruction is not the more useful intervention. \textbf{(b)}~Cross-validated
  conditional harmful rate against intervention rate over the neighbourhood and penalty grid,
  one point per grid cell per backbone, with the selected point enlarged and the cap marked.}
  \label{fig:why-selective}
\end{figure}"""

sub(FIG3, RANKGRID, tag="figure 3 becomes the rank agreement table")

sub(r"""sources of different scale apart. \ph{RECON_READING}. Figure~\ref{fig:why-selective}(a) shows it and
Appendix~\ref{app:recutils} reports it per action.""",
    r"""sources of different scale apart. \ph{RECON_READING}. Table~\ref{tab:rankgrid} shows the two
rankings against each other and Appendix~\ref{app:recutils} reports them per action.""",
    tag="section 4.2: point at the rank table")

sub(r"""Figure~\ref{fig:why-selective}(b) traces the trade-off over the score grid by post-processing
the stored scores on TEST, with no threshold selected on TEST.
Appendix~\ref{app:governance-fig} reports the curve cell by cell. \ph{HARM_RISKCURVE}.""",
    r"""Table~\ref{tab:app-operating} traces the same trade-off over the penalty grid, by
post-processing the stored scores on TEST and selecting no threshold there.
\ph{HARM_RISKCURVE}.""",
    tag="section 4.4: point at the operating point table")


# ------------------------------- figure 4 becomes two tables in the appendix

OPERATING_ROWS = "".join(
    row([label]
        + [f"\\ph{{OPPT_{bb}_{tag}_{field}}}"
           for bb in ("BOLT", "TF", "CH2") for field in ("IR", "HIR")])
    for tag, label in (("B00", "$\\beta = 0$"), ("B05", "$\\beta = 0.5$"),
                       ("B10", "$\\beta = 1$"), ("B164", "$\\beta = 1.64$")))

SCORE_ROWS = "".join(
    row([label, f"\\ph{{SU_B{i}_N}}", f"\\ph{{SU_B{i}_MEAN}}", f"\\ph{{SU_B{i}_CI}}"])
    for i, label in enumerate(["1 (lowest score)", "2", "3", "4", "5 (highest score)"],
                              start=1))

GOVERNANCE_TABLES = (r"""\begin{table}[h]
  \caption{Operating points over the penalty grid, with the neighbourhood size frozen at the
  selected value on each backbone. Intervention rate is the share of requests on which a
  non-reference action ran, and conditional HIR is the share of those that raised the loss.
  Raising the penalty moves the rate and leaves the conditional rate close to where it was, so
  what the rule controls is how often it acts rather than how often an executed action hurts.}
  \label{tab:app-operating}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lcccccc}
    \toprule
""" + row(["", "\\multicolumn{2}{c}{Bolt}", "\\multicolumn{2}{c}{TimesFM}",
           "\\multicolumn{2}{c}{Chronos-2}"])
    + "    \\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(lr){6-7}\n"
    + row(["Penalty strength", "Int.\\ rate", "Cond.\\ HIR", "Int.\\ rate", "Cond.\\ HIR",
           "Int.\\ rate", "Cond.\\ HIR"])
    + "    \\midrule\n" + OPERATING_ROWS + r"""    \bottomrule
  \end{tabular}}
\end{table}

\begin{table}[h]
  \caption{Realised utility against the quantile bin of the conservative score, pooled over the
  three backbones and every admissible action. The score orders actions and its magnitude is
  not claimed to be calibrated, so what this table checks is whether the order it induces
  agrees with the sign of the utility. Intervals resample parents.}
  \label{tab:app-scorebins}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\begin{tabular}{lccc}
    \toprule
""" + row(["Score bin", "Pairs", "Mean realised utility", "95\\% interval"])
    + "    \\midrule\n" + SCORE_ROWS + r"""    \bottomrule
  \end{tabular}
\end{table}""")

FIG4 = r"""\begin{figure}[h]
  \centering
  \includegraphics[width=0.84\textwidth]{figure/fig4_governance_diagnostics.pdf}
  \caption{\textbf{(a)}~Harmful loss per method, averaged over the three backbones.
  \textbf{(b)}~Realised utility of every admissible action against the quantile bin of its
  conservative score, with 95\% intervals that resample parents. Panel~(b) reports sign
  agreement and makes no calibration claim.}
  \label{fig:governance}
\end{figure}"""

sub(FIG4, GOVERNANCE_TABLES, tag="figure 4 becomes the operating point and score bin tables")

sub(r"""Figure~\ref{fig:governance} visualises the diagnostics tabulated in
Table~\ref{tab:harm}. Panel~(b) checks sign agreement. The ranking score is used only to order
actions, and its magnitude is not claimed to be calibrated against the utility scale.
\ph{GOV_FIG_READING}.""",
    r"""Table~\ref{tab:app-operating} walks the operating point over the penalty grid and
Table~\ref{tab:app-scorebins} checks that the order the score induces agrees with the sign of
the realised utility. The score is used only to order actions, and its magnitude is not claimed
to be calibrated against the utility scale. \ph{GOV_FIG_READING}.""",
    tag="appendix D: point at the two tables")


# ------------------------------------ figure 5 gives way to the severity tables

FIG5 = r"""\subsubsection{Robustness Trend Figure}
\label{app:robust-fig}
Figure~\ref{fig:robust} shows the severity trend summarised by Table~\ref{tab:robust}. Each
panel is a different frozen backbone. The axes are identical across panels so that the
panels can be compared directly.

\begin{figure}[h]
  \centering
  \includegraphics[width=0.86\textwidth]{figure/fig5_robustness_missingness.pdf}
  \caption{Relative MASE improvement over \textsc{Native Keep} as missingness severity
  increases, one line per method, one panel per frozen backbone. All methods reuse the
  models and rules frozen on TRAIN, with no per-severity retuning.}
  \label{fig:robust}
\end{figure}"""

TREND_METHODS = [("\\textsc{Native Keep}", "KEEP"), ("\\textsc{Best Fixed}", "BF"),
                 ("R2-CART", "R2"), ("Fixed SAITS", "SAITS"), ("TATO", "TATO"),
                 ("\\introact{}", "OURS")]

TREND_ROWS = "".join(
    row([label] + [f"\\ph{{TREND_{bb}_{key}_{sev}}}"
                   for bb in ("BOLT", "TF", "CH2")
                   for sev in ("S10", "S30", "S50")])
    for label, key in TREND_METHODS)

TREND = (r"""\subsubsection{Severity Trend by Backbone}
\label{app:robust-fig}
Table~\ref{tab:robust} averages the severity sweep over the backbones, and
Table~\ref{tab:app-trend} separates them, because a configuration that holds on average may
still be carried by one family. Every row reuses the models and rules frozen on TRAIN and
nothing is retuned per severity.

\begin{table}[h]
  \caption{Source-macro MASE at each registered severity, one block of columns per frozen
  backbone. The evaluation set, the roster and the frozen configuration are the ones of
  Table~\ref{tab:main}.}
  \label{tab:app-trend}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lccccccccc}
    \toprule
""" + row(["", "\\multicolumn{3}{c}{Bolt}", "\\multicolumn{3}{c}{TimesFM}",
           "\\multicolumn{3}{c}{Chronos-2}"])
    + "    \\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\\cmidrule(lr){8-10}\n"
    + row(["Method"] + ["$10\\%$", "$30\\%$", "$50\\%$"] * 3)
    + "    \\midrule\n" + TREND_ROWS
    + r"""    \bottomrule
  \end{tabular}}
\end{table}""")

sub(FIG5, TREND, tag="figure 5 becomes the per-backbone severity table")


TEX.write_text(TEXT, encoding="utf-8")
print("APPLIED:")
for item in APPLIED:
    print("  +", item)
print(f"\nwrote {TEX.name}, {len(TEXT)} characters, {TEXT.count('ph{')} placeholders, "
      f"{TEXT.count('includegraphics')} graphics left")
