"""Appendix diagnostic: how an action's realised utility depends on the backbone
and on how much of the context is missing.
"""
import io

PATH = "latex/IntroActTS_20260919_v46.tex"
ANCHOR = "\\subsubsection{Governance Diagnostics}"

SECTION = r"""\subsubsection{Where an Action's Utility Comes From}
\label{app:utility-by-severity}
Table~\ref{tab:app-utility-severity} reports the mean realised utility of each catalog action
on the replay bank, once over the whole bank and once within each registered severity. It
selects nothing and is computed after the configuration was frozen. Two things in it matter for
reading the main tables.

The first is that how much a repair is worth depends on the backbone and on how much of the
context is missing, and the two dependencies are not the same shape. On TimesFM every
non-trivial repair grows more valuable as the context empties, so a rule tuned at one severity
is looking at a moving target. On Chronos-2 the same repairs sit at roughly the same value
across severities. That is the premise of \S\ref{sec:exp-exists} restated as a table, and it is
why the decision cannot be a single policy learned once.

The second is a data-quality fact that has to travel with the numbers. On Bolt the mean utility
of \textsc{Context Ridge} over the whole bank is \ph{RIDGE_BOLT_ALL}, while within the $10\%$
episodes alone it is \ph{RIDGE_BOLT_S10}. The gap is one replay episode on which the ridge
extrapolation diverged, and a single such record moves a mean over a few hundred. It was not
winsorised, because silently transforming a recorded execution is exactly what the protocol
forbids, and it is one reason the neighbourhood size matters: a local estimate over eight
neighbours is exposed to an outlier that an estimate over sixty-four dilutes.

\begin{table}[h]
  \caption{Mean realised utility of each action on the replay bank, overall and within each
  registered severity. Positive means the action lowered the forecasting loss relative to
  leaving the input unchanged. Utility is measured per episode, so it is not on the same
  aggregation as the source-macro MASE of the main tables and the two are not directly
  comparable in magnitude.}
  \label{tab:app-utility-severity}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{llcccc}
    \toprule
    Backbone & Action & All severities & $10\%$ & $30\%$ & $50\%$ \\
    \midrule
    \multirow{4}{*}{Bolt}
      & \textsc{Ffill}         & \ph{UB_BOLT_FFILL_ALL}  & \ph{UB_BOLT_FFILL_S10}  & \ph{UB_BOLT_FFILL_S30}  & \ph{UB_BOLT_FFILL_S50} \\
      & \textsc{Single TS-ICL} & \ph{UB_BOLT_SINGLE_ALL} & \ph{UB_BOLT_SINGLE_S10} & \ph{UB_BOLT_SINGLE_S30} & \ph{UB_BOLT_SINGLE_S50} \\
      & \textsc{Multi TS-ICL}  & \ph{UB_BOLT_MULTI_ALL}  & \ph{UB_BOLT_MULTI_S10}  & \ph{UB_BOLT_MULTI_S30}  & \ph{UB_BOLT_MULTI_S50} \\
      & \textsc{Context Ridge} & \ph{UB_BOLT_RIDGE_ALL}  & \ph{UB_BOLT_RIDGE_S10}  & \ph{UB_BOLT_RIDGE_S30}  & \ph{UB_BOLT_RIDGE_S50} \\
    \midrule
    \multirow{4}{*}{TimesFM}
      & \textsc{Ffill}         & \ph{UB_TF_FFILL_ALL}  & \ph{UB_TF_FFILL_S10}  & \ph{UB_TF_FFILL_S30}  & \ph{UB_TF_FFILL_S50} \\
      & \textsc{Single TS-ICL} & \ph{UB_TF_SINGLE_ALL} & \ph{UB_TF_SINGLE_S10} & \ph{UB_TF_SINGLE_S30} & \ph{UB_TF_SINGLE_S50} \\
      & \textsc{Multi TS-ICL}  & \ph{UB_TF_MULTI_ALL}  & \ph{UB_TF_MULTI_S10}  & \ph{UB_TF_MULTI_S30}  & \ph{UB_TF_MULTI_S50} \\
      & \textsc{Context Ridge} & \ph{UB_TF_RIDGE_ALL}  & \ph{UB_TF_RIDGE_S10}  & \ph{UB_TF_RIDGE_S30}  & \ph{UB_TF_RIDGE_S50} \\
    \midrule
    \multirow{4}{*}{Chronos-2}
      & \textsc{Ffill}         & \ph{UB_CH2_FFILL_ALL}  & \ph{UB_CH2_FFILL_S10}  & \ph{UB_CH2_FFILL_S30}  & \ph{UB_CH2_FFILL_S50} \\
      & \textsc{Single TS-ICL} & \ph{UB_CH2_SINGLE_ALL} & \ph{UB_CH2_SINGLE_S10} & \ph{UB_CH2_SINGLE_S30} & \ph{UB_CH2_SINGLE_S50} \\
      & \textsc{Multi TS-ICL}  & \ph{UB_CH2_MULTI_ALL}  & \ph{UB_CH2_MULTI_S10}  & \ph{UB_CH2_MULTI_S30}  & \ph{UB_CH2_MULTI_S50} \\
      & \textsc{Context Ridge} & \ph{UB_CH2_RIDGE_ALL}  & \ph{UB_CH2_RIDGE_S10}  & \ph{UB_CH2_RIDGE_S30}  & \ph{UB_CH2_RIDGE_S50} \\
    \bottomrule
  \end{tabular}}
\end{table}

"""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert ANCHOR in text, "anchor"
    text = text.replace(ANCHOR, SECTION + ANCHOR, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("severity diagnostic appendix added")


if __name__ == "__main__":
    main()
