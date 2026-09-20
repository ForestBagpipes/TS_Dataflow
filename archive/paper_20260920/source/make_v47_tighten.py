#!/usr/bin/env python3
"""Fourth pass: recover the last page without dropping evidence.

Six tables and two figures now carry the main text, which is the right shape
for the argument and one page more than the limit allows.  The space comes from
form rather than content: captions state the convention once and leave the
reading to the text, three displays that are one short line each go inline, the
skips around the remaining displays and around floats come in a little, and the
two sections that restate a neighbouring one are cut back.

Usage: python latex/make_v47_tighten.py   (run after make_v47_pages.py)
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
TEX = HERE / "IntroActTS_20260919_v47.tex"

TEXT = TEX.read_text(encoding="utf-8")
APPLIED: list[str] = []


def sub(old: str, new: str, *, tag: str) -> None:
    global TEXT
    if TEXT.count(old) != 1:
        raise SystemExit(f"FAILED {tag}: anchor appears {TEXT.count(old)} times")
    TEXT = TEXT.replace(old, new, 1)
    APPLIED.append(tag)


# ------------------------------------------------- skips around displays and floats

sub(r"""\setlength{\textfloatsep}{7pt plus 2pt minus 2pt}
\setlength{\floatsep}{7pt plus 2pt minus 2pt}
\setlength{\intextsep}{7pt plus 2pt minus 2pt}""",
    r"""\setlength{\textfloatsep}{5pt plus 2pt minus 2pt}
\setlength{\floatsep}{5pt plus 2pt minus 2pt}
\setlength{\intextsep}{5pt plus 2pt minus 2pt}
% Display skips, set once so every equation in the paper carries the same one.
\setlength{\abovedisplayskip}{5pt plus 2pt minus 2pt}
\setlength{\belowdisplayskip}{5pt plus 2pt minus 2pt}
\setlength{\abovedisplayshortskip}{3pt plus 1pt minus 1pt}
\setlength{\belowdisplayshortskip}{3pt plus 1pt minus 1pt}""",
    tag="float and display skips set once")


# ---------------------------------------------------------- the reserved boxes

sub(r"""  \figph{0.64\textwidth}{3.4cm}{FIGURE_1_SELECTIVE_GOVERNANCE}""",
    r"""  \figph{0.64\textwidth}{2.9cm}{FIGURE_1_SELECTIVE_GOVERNANCE}""",
    tag="figure 1 reserves a little less height")

sub(r"""  \figph{0.48\textwidth}{4.6cm}{FIGURE_2_ARCHITECTURE}""",
    r"""  \figph{0.48\textwidth}{4.0cm}{FIGURE_2_ARCHITECTURE}""",
    tag="figure 2 reserves a little less height")


# ------------------------------------------- captions state the convention once

for old, new, tag in [
    (r"""  \caption{Why the choice has to be made per request, over the held-out episodes of all three
  backbones. Oracle-best share is how often an action attains the lowest realised loss of the
  catalog, and the shares sum to one. Improves the forecast is the share of the episodes where
  the action applies on which it lowered the loss against \textsc{Keep}, and mean utility is
  that change averaged over the same episodes. No action holds the first column often enough to
  serve every request, and every intervention both helps and hurts.}""",
     r"""  \caption{Why the choice has to be made per request, over the held-out episodes of all three
  backbones. Oracle-best share is how often an action attains the lowest realised loss of the
  catalog and the shares sum to one. The last two columns cover the episodes where the action
  applies and are measured against \textsc{Keep}.}""",
     "caption: heterogeneity"),

    (r"""  \caption{Main comparison on TEST at $10\%$ missingness. MASE and RMSSE are source-macro
  averaged and lower is better everywhere. Every row composes with the same frozen backbone and
  therefore shares one reference contract. \best{Bold} marks the best value of a column
  and \second{underline} the second best. Average rank is computed cell by cell over the
  rows of this table, so it says how often a method wins and not how large its average is. The oracle row reads the future target for diagnosis only
  and is excluded from the ranks. Chronos-2 is a held-out backbone whose configuration is
  selected by the same frozen procedure on its own replay bank and is not retuned.}""",
     r"""  \caption{Main comparison on TEST at $10\%$ missingness, source-macro averaged, lower is
  better everywhere. \best{Bold} is the best value of a column and \second{underline} the
  second. Average rank is over the deployable rows of this table, cell by cell. The oracle
  reads the future target and is excluded from every rank. Chronos-2 is held out and is not
  retuned. Table~\ref{tab:app-roster} defines the rows.}""",
     "caption: main comparison"),

    (r"""  \caption{Selective-governance diagnostics at the default operating point, $10\%$ severity.
  Intervention rate is the share of requests on which a non-reference action was executed.
  Conditional harmful rate is the share of executed interventions that increased the realised
  loss relative to \textsc{Keep}, and harmful loss is the mean increase over those requests.
  Beneficial precision is the share of executed interventions that reduced the loss, and missed
  opportunity is the share of positive-opportunity episodes on which nothing was executed.}""",
     r"""  \caption{Selective-governance diagnostics at the default operating point, $10\%$ severity.
  Intervention rate is the share of requests on which a non-reference action ran. The next three
  columns cover those requests and are measured against \textsc{Keep}. Missed opportunity is the
  share of positive-opportunity episodes on which nothing ran.
  Appendix~\ref{app:diagnostic-conventions} fixes the counting rules.}""",
     "caption: harm diagnostics"),

    (r"""  \caption{Within-grid robustness to missingness severity, with no method retuned between
  levels. The rows are the roster of Table~\ref{tab:main} and cover every control type. Values
  are source-macro MASE averaged over the backbones, both horizons and the four patterns. The
  worst-pattern column is the largest degradation relative to \textsc{Native Keep} over all
  pattern and backbone cells at that severity.}""",
     r"""  \caption{Within-grid robustness to missingness severity, with nothing retuned between levels.
  Values are source-macro MASE over the three backbones, both horizons and the four patterns.
  The worst-cell column is the largest degradation against \textsc{Native Keep} over every
  pattern, backbone and severity of the sweep, so it is one number for the whole table.}""",
     "caption: robustness"),

    (r"""  \caption{Core ablation and cost at $10\%$ severity, on the held-out evaluation set. Every
  row reads the same catalog prediction cache, so the rows differ only in how the stored
  utilities are summarised and thresholded. Calls counts forecasting-backbone calls per
  request and equals one plus the intervention rate. Candidate materialisation is reported
  separately in Appendix~\ref{app:calls}.}""",
     r"""  \caption{Core ablation and cost at $10\%$ severity. Every row reads the same catalog
  prediction cache, so the rows differ only in how the stored utilities are summarised and
  thresholded. Calls counts forecasting-backbone calls per request. Candidate materialisation
  is reported separately in Appendix~\ref{app:calls}.}""",
     "caption: ablation"),

    (r"""  \caption{Architecture of \introact{}. \textbf{Offline}: TRAIN windows become incomplete
  contexts under the registered missingness protocol, every catalog action is executed with the
  frozen forecaster, and the realised utilities populate the replay bank. This is the only place
  a future is read. \textbf{Online}: the reference forecast is computed, an action-conditioned
  state $z_a$ is formed per action and scored against the frozen bank, and one action is
  executed with the same frozen forecaster.}""",
     r"""  \caption{Architecture of \introact{}. \textbf{Offline}: TRAIN windows become incomplete
  contexts under the registered protocol, every catalog action is executed with the frozen
  forecaster, and the realised utilities populate the replay bank. This is the only place a
  future is read. \textbf{Online}: the reference forecast is computed, a state is formed per
  action and scored against the frozen bank, and one action is executed.}""",
     "caption: architecture"),
]:
    sub(old, new, tag=tag)


# ------------------------------------------- three one-line displays go inline

sub(r"""replay bank is
\begin{equation}
  \calB \;=\; \bigl\{\, (z_{i,a},\, a,\, g_{i,a}) \,\bigr\},
  \label{eq:replay-bank}
\end{equation}
built once from TRAIN history and then frozen. Deployment reads it and never writes to it.""",
    r"""replay bank is $\calB = \{(z_{i,a}, a, g_{i,a})\}$, built once from TRAIN history and then
frozen. Deployment reads it and never writes to it.""",
    tag="the bank definition goes inline")

sub(r"""where $\beta$ is a penalty strength, and
\begin{equation}
  \max_{a \in \calA^{+}} S_a > 0
  \;\Rightarrow\;
  a^{\star} = \arg\max_{a \in \calA^{+}} S_a ,
  \qquad\text{otherwise}\qquad
  a^{\star} = a_0 .
  \label{eq:decision}
\end{equation}""",
    r"""where $\beta$ is a penalty strength. The action taken is
$a^{\star} = \arg\max_{a \in \calA^{+}} S_a$ when $\max_{a \in \calA^{+}} S_a > 0$, and
$a^{\star} = a_0$ otherwise.""",
    tag="the decision rule goes inline")

sub(r"""The state recorded with each outcome is action conditioned. For window $i$ and action $a$,
\begin{equation}
  z_{i,a} \;=\; \phi\!\left(X_i,\, M_i,\, X_i^{a},\, p_i^{0}\right),
  \qquad
  p_i^{0} = F(X_i^{a_0}),
  \label{eq:state}
\end{equation}
where $X_i^{a} = T_a(X_i, M_i)$. The state may use the reference forecast $p_i^0$, which the
protocol already permits, and it never uses the forecast of a non-selected candidate.""",
    r"""The state recorded with each outcome is action conditioned:
$z_{i,a} = \phi(X_i, M_i, X_i^{a}, p_i^{0})$ with $p_i^{0} = F(X_i^{a_0})$ and
$X_i^{a} = T_a(X_i, M_i)$.\label{eq:state} It may use the reference forecast $p_i^0$, which the
protocol already permits, and it never uses the forecast of a non-selected candidate.""",
    tag="the state definition goes inline")


# --------------------------------------- the data-side subsection stops repeating

sub(r"""TATO~\citep{qiu2026tato} shows that a frozen \tsfm{} can be adapted to heterogeneous domains
without parameter updates. It searches a transformation pipeline, including context slicing,
scale normalisation, and outlier correction, and selects the pipeline from historical task
performance. The unit of adaptation is a target domain. TS-ICL~\citep{tsicl2026} is a
foundation model that natively supports imputation, irregular observations, and partially
observed look-back windows. It appears here only as the in-context regression backend of two
catalog actions, so two of the five actions cost one call to a frozen imputation model on top
of the forecasting call (\S\ref{sec:method-deploy}).""",
    r"""TATO~\citep{qiu2026tato} shows that a frozen \tsfm{} can be adapted to heterogeneous domains
without parameter updates, by searching a transformation pipeline and selecting it from
historical task performance. Its unit of adaptation is a target domain.
TS-ICL~\citep{tsicl2026} is a foundation model that natively supports imputation and partially
observed look-back windows, and it appears here only as the in-context regression backend of
two catalog actions.""",
    tag="the data-side subsection stops listing what the appendix lists")



sub(r"""    Method & 10\% MASE $\downarrow$ & 30\% MASE $\downarrow$ & 50\% MASE $\downarrow$ & Worst pattern $\downarrow$""",
    r"""    Method & 10\% MASE $\downarrow$ & 30\% MASE $\downarrow$ & 50\% MASE $\downarrow$ & Worst cell $\downarrow$""",
    tag="the worst column says what it is")


TEX.write_text(TEXT, encoding="utf-8")
print("APPLIED:")
for item in APPLIED:
    print("  +", item)
print(f"\nwrote {TEX.name}, {len(TEXT)} characters, {TEXT.count('ph{')} placeholders")
