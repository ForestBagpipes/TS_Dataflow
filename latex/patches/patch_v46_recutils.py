"""Sixth v4.6 patch: the reconstruction-versus-utility appendix.

The comparison now runs on the catalog itself, where both rankings exist for
the same episode under one protocol, so the table lists the four interventions
rather than external methods that have no runnable implementation here.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"
START = "This subsection supports \\S\\ref{sec:exp-exists}. Reconstruction error is only defined for"
END = "\\subsubsection{Governance Diagnostics}"

BODY = r"""This subsection supports \S\ref{sec:exp-exists}. Reconstruction error is defined only where a
method emits an explicit estimate of the hidden positions, which the four interventions of the
catalog all do. Running the comparison on the catalog keeps both criteria on one protocol and
one set of episodes: the same window, the same mask, the same frozen backbone, and the same
realised future. \textsc{Keep} does not enter, because it estimates nothing, and \introact{}
does not enter, because it returns a forecast from an executed input rather than a
reconstruction.

Reconstruction error is measured on the artificially hidden positions of the target channel,
which are known because the mask is synthetic. Realised utility is the change in forecasting
loss the same action produced on the same episode. Both rankings are formed inside an episode
and then compared, because episodes differ in scale and in difficulty and pooling them would
let a few large-scale sources decide the answer. Table~\ref{tab:app-recutils} gives the
per-action averages and the two rank statistics.

\begin{table}[h]
  \caption{Reconstruction quality against realised forecasting utility, over the four catalog
  interventions on the held-out evaluation episodes. Reconstruction error is measured on the
  hidden positions and realised utility against \textsc{Keep} on the same backbone. Winner
  agreement is the share of episodes on which the most accurate reconstruction is also the most
  useful intervention, and the discordant rate is the share of ordered pairs whose two rankings
  disagree.}
  \label{tab:app-recutils}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lcccc}
    \toprule
    Intervention & Rec.\ MSE $\downarrow$ & Rec.\ MAE $\downarrow$
                 & Mean realised utility $\uparrow$ & Episodes \\
    \midrule
    \textsc{Ffill}         & \ph{REC_FFILL_MSE}  & \ph{REC_FFILL_MAE}  & \ph{REC_FFILL_UTIL}  & \ph{REC_FFILL_N} \\
    \textsc{Single TS-ICL} & \ph{REC_SINGLE_MSE} & \ph{REC_SINGLE_MAE} & \ph{REC_SINGLE_UTIL} & \ph{REC_SINGLE_N} \\
    \textsc{Multi TS-ICL}  & \ph{REC_MULTI_MSE}  & \ph{REC_MULTI_MAE}  & \ph{REC_MULTI_UTIL}  & \ph{REC_MULTI_N} \\
    \textsc{Context Ridge} & \ph{REC_RIDGE_MSE}  & \ph{REC_RIDGE_MAE}  & \ph{REC_RIDGE_UTIL}  & \ph{REC_RIDGE_N} \\
    \midrule
    \multicolumn{5}{l}{\footnotesize Winner agreement \ph{RECON_AGREE}, discordant rate
    \ph{DISCORDANT_RATE}, mean within-episode Spearman $\rho$ \ph{RECON_RHO}} \\
    \bottomrule
  \end{tabular}}
\end{table}

The averages in the table make the same point as the rank statistics. The intervention with the
lowest mean reconstruction error is not the one with the highest mean realised utility, so the
disagreement is not a property of a few unusual episodes. A deployment that picked its repair
by reconstruction accuracy would therefore be optimising a criterion that is close to
uninformative about the quantity it cares about.

"""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    i = text.find(START)
    j = text.find(END, i)
    assert i > 0 and j > i, "recutils section not found"
    text = text[:i] + BODY + text[j:]
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("recutils rewritten")


if __name__ == "__main__":
    main()
