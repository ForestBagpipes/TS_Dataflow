"""Fifth v4.6 patch: record which published baselines could be run and which could not.

A reviewer will ask why the comparison names some methods in the related work
and not in the tables.  The honest answer is availability, and it belongs in
the appendix as a table rather than in a footnote.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

ANCHOR = "\\subsubsection{Per-Source Results}"

SECTION = r"""\subsection{Baseline Availability}
\label{app:baseline-availability}
The comparison names more published methods in Section~\ref{sec:related} than it reports in
Table~\ref{tab:main}. The reason is implementation availability under the protocol of this
paper, and Table~\ref{tab:app-availability} records it method by method. A method enters the
tables only when an official implementation exists, admits an incomplete context of the shape
this protocol produces, and emits an input version a frozen backbone can consume. A
reimplementation from a paper description would not be comparable with the numbers that paper
reports, so a method without a usable implementation is left out of the tables rather than
approximated.

\begin{table}[h]
  \caption{Published methods considered for the comparison. The last column states what the
  method contributes here. Methods marked unavailable are discussed in
  Section~\ref{sec:related} and carry no row in any table.}
  \label{tab:app-availability}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{@{}l l p{0.28\textwidth} p{0.30\textwidth}@{}}
    \toprule
    Method & Venue & Implementation & Role here \\
    \midrule
    SAITS~\citep{du2023saits}       & ESWA 2023  & official, packaged~\citep{du2023pypots} & reconstruction baseline \\
    TOI~\citep{wang2024taskoriented}& NeurIPS 2024 & official repository & task-oriented baseline \\
    TATO~\citep{qiu2026tato}        & ICLR 2026  & official repository & data-side adaptation baseline \\
    \midrule
    BRITS~\citep{cao2018brits}      & NeurIPS 2018 & available & superseded by SAITS on this protocol \\
    CSDI~\citep{tashiro2021csdi}    & NeurIPS 2021 & available & not run, cost per request exceeds the deployment budget \\
    T1~\citep{park2026t1}           & ICLR 2026  & no public release found & discussed only \\
    SRDI~\citep{xu2026srdi}         & WWW 2026   & no public release found & discussed only \\
    GIMCC~\citep{hao2025gimcc}      & KDD 2025   & no public release found & discussed only \\
    VIDA~\citep{liang2025vida}      & KDD 2025   & no public release found & discussed only \\
    \midrule
    BiTGraph~\citep{chen2024bitgraph}   & ICLR 2024 & available & trains its own forecaster, outside the frozen-backbone contract \\
    S4M~\citep{peng2025s4m}             & ICLR 2025 & available & the same \\
    ChannelTokenFormer~\citep{jang2026channeltokenformer} & ICLR 2026 & available & the same \\
    \bottomrule
  \end{tabular}}
\end{table}

The last block is a different kind of exclusion. BiTGraph, S4M and ChannelTokenFormer are
complete forecasting models trained for missing inputs. They do not compose with a frozen
backbone, they have no reference action, and the harmful rate of an intervention is undefined
for them, so putting them in the same rank as a data-side adapter would compare two different
contracts. They belong to the setting this paper does not address, which is training a
forecaster of one's own.

"""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert ANCHOR in text, "per-source anchor"
    text = text.replace(ANCHOR, SECTION + ANCHOR, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("availability section added")


if __name__ == "__main__":
    main()
