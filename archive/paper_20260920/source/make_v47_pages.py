#!/usr/bin/env python3
"""Third pass: every experiment gets a table, and the main text stays at nine pages.

Two sections argued from prose alone, the one that establishes the decision
problem and the one that sweeps severity.  Each gets a table here, so every
experimental question in the main text is answered by something a reader can
read numbers off.

The space comes from three places.  Heading and paragraph spacing is tightened
once per level in the preamble, so every heading of a level moves by the same
amount.  Evidence the main text summarises in a sentence and the appendix
carries in full moves to the appendix.  Prose that the appendix already repeats
almost word for word is cut back to a pointer.  No claim and no measurement is
dropped.

Usage: python latex/make_v47_pages.py   (run after make_v47_figs.py)
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
TEX = HERE / "IntroActTS_20260919_v47.tex"

TEXT = TEX.read_text(encoding="utf-8")
APPLIED: list[str] = []
BS = "\\" * 2


def row(cells: list[str], indent: str = "    ") -> str:
    return indent + " & ".join(cells) + " " + BS + "\n"


def sub(old: str, new: str, *, tag: str) -> None:
    global TEXT
    if TEXT.count(old) != 1:
        raise SystemExit(f"FAILED {tag}: anchor appears {TEXT.count(old)} times")
    TEXT = TEXT.replace(old, new, 1)
    APPLIED.append(tag)


def lift(start_marker: str, *, tag: str) -> str:
    """Remove a float that begins at ``start_marker`` and return it."""
    global TEXT
    start = TEXT.index(start_marker)
    end = TEXT.index(r"\end{table}", start) + len(r"\end{table}")
    block = TEXT[start:end]
    TEXT = TEXT[:start] + TEXT[end:].lstrip("\n")
    APPLIED.append(tag)
    return block


# ===================================================== 1. spacing, per level

sub(r"""% ICLR 正文硬上限 9 页，浮动体间距默认偏松，这里收紧以腾出正文空间。""",
    r"""% 正文硬上限 9 页。标题与段间距在这里按层级各收紧一次，所以同级标题的
% 调整完全一致，不是逐处手改。模板文件本身不动。
\makeatletter
\def\section{\@startsection{section}{1}{\z@}{-1.6ex plus -0.5ex minus -.2ex}%
  {1.1ex plus 0.2ex minus 0.1ex}{\large\sc\raggedright}}
\def\subsection{\@startsection{subsection}{2}{\z@}{-1.4ex plus -0.4ex minus -.2ex}%
  {0.6ex plus .1ex}{\normalsize\sc\raggedright}}
\def\subsubsection{\@startsection{subsubsection}{3}{\z@}{-1.2ex plus -0.4ex minus -.2ex}%
  {0.4ex plus .1ex}{\normalsize\sc\raggedright}}
\def\paragraph{\@startsection{paragraph}{4}{\z@}{1.1ex plus 0.3ex minus .2ex}%
  {-1em}{\normalsize\bf}}
\makeatother
\setlength{\parskip}{3.8pt plus 1pt minus 0.5pt}

% ICLR 正文硬上限 9 页，浮动体间距默认偏松，这里收紧以腾出正文空间。""",
    tag="preamble: heading and paragraph spacing tightened once per level")


# ============================ 2. the decision problem gets a table of its own

HET_ROWS = "".join(
    row([label, f"\\ph{{HET_{tag}_BEST}}", f"\\ph{{HET_{tag}_N}}",
         f"\\ph{{HET_{tag}_POS}}", f"\\ph{{HET_{tag}_UTIL}}"])
    for label, tag in [(r"\textsc{Keep} $a_0$", "KEEP"),
                       (r"\textsc{Ffill}", "FFILL"),
                       (r"\textsc{Single TS-ICL}", "SINGLE"),
                       (r"\textsc{Multi TS-ICL}", "MULTI"),
                       (r"\textsc{Context Ridge}", "RIDGE"),
                       (r"\textsc{SAITS}", "SAITS")])

HETERO = (r"""\begin{table}[t]
  \caption{Why the choice has to be made per request, over the held-out episodes of all three
  backbones. Oracle-best share is how often an action attains the lowest realised loss of the
  catalog, and the shares sum to one. Improves the forecast is the share of the episodes where
  the action applies on which it lowered the loss against \textsc{Keep}, and mean utility is
  that change averaged over the same episodes. No action holds the first column often enough to
  serve every request, and every intervention both helps and hurts.}
  \label{tab:heterogeneity}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lcccc}
    \toprule
""" + row(["Action", "Oracle-best share", "Episodes where it applies",
           "Improves the forecast", "Mean realised utility"])
    + "    \\midrule\n" + HET_ROWS + r"""    \bottomrule
  \end{tabular}}
  \vspace{-2pt}
  {\footnotesize Reconstruction accuracy does not order the repairs the way realised utility
  does. The most accurate reconstruction is the most useful repair on \ph{RECON_AGREE} of the
  episodes, \ph{DISCORDANT_RATE} of the ordered pairs disagree, and the mean within-episode
  rank correlation is \ph{RECON_RHO}. Appendix~\ref{app:recutils} reports both criteria per
  action.}
\end{table}""")

sub(r"""Appendix~\ref{app:opportunity} breaks the same episodes down by how much improvement was
available.""",
    HETERO + r"""

Appendix~\ref{app:opportunity} breaks the same episodes down by how much improvement was
available.""",
    tag="section 4.2 gets its table")


# ================================ 3. the severity sweep gets its table back

ROBUST = lift(r"""\begin{table}[h]
  \caption{Within-grid robustness to missingness severity, with no method retuned between""",
              tag="the severity table leaves the appendix")
ROBUST = ROBUST.replace(r"\begin{table}[h]", r"\begin{table}[t]", 1)

sub(r"""Table~\ref{tab:robust} in Appendix~\ref{app:severity-full} reports the severity trend and the worst pattern cell, and the
held-out backbone is the Chronos-2 column of Table~\ref{tab:main}.""",
    r"""Table~\ref{tab:robust} reports the severity trend and the worst pattern cell, and the
held-out backbone is the Chronos-2 column of Table~\ref{tab:main}.""",
    tag="section 4.5 points at its own table")

sub(r"""Appendix~\ref{app:severity-full} holds the complete per-severity tables and
Appendix~\ref{app:pattern} holds the per-pattern tables.""",
    ROBUST + r"""

Appendix~\ref{app:severity-full} holds the complete per-severity tables and
Appendix~\ref{app:pattern} holds the per-pattern tables.""",
    tag="section 4.5 gets its table")


# ======================================= 4. prose the appendix already carries

sub(r"""Three routes handle an incomplete input, and they differ in what they optimise. The first
reconstructs the hidden values and is scored on how close the reconstruction
is~\citep{cao2018brits,tashiro2021csdi,yoon2018gain,du2023saits,park2026t1}. The second builds
a forecaster that reads the missing pattern directly, on the argument that imputing first and
forecasting afterwards accumulates error~\citep{chen2024bitgraph,peng2025s4m,
jang2026channeltokenformer}. These are complete models whose parameters are part of the
contribution. The third replaces the recovery objective with a downstream
one~\citep{wang2024taskoriented,hao2025toivsf,hao2025gimcc,liang2025vida,xu2026srdi}, mostly in
\emph{variable subset forecasting}, where whole variables are absent at inference and not
positions inside the context.""",
    r"""Three routes handle an incomplete input and they differ in what they optimise. The first
reconstructs the hidden values and is scored on how close the reconstruction
is~\citep{cao2018brits,tashiro2021csdi,yoon2018gain,du2023saits,park2026t1}. The second builds
a forecaster that reads the missing pattern directly~\citep{chen2024bitgraph,peng2025s4m,
jang2026channeltokenformer}, and those are complete models whose parameters are part of the
contribution. The third replaces the recovery objective with a downstream
one~\citep{wang2024taskoriented,hao2025toivsf,hao2025gimcc,liang2025vida,xu2026srdi}, mostly in
\emph{variable subset forecasting}, where whole variables are absent at inference and not
positions inside the context.""",
    tag="related work 2.1 drops a restated motivation")

sub(r"""The estimator is a weighted average of the recorded utilities of the same action on nearby
states, in a fixed standardised feature space. The state $z_a$ of \eqref{eq:state} carries
four groups of features, twenty-two numbers in total. Mask state describes how the request is
incomplete, through the missing fraction, the run structure of the gaps, the distance from the
nearest gap to the forecast origin, and whether other channels are affected. Visible-context
state summarises the observed part of the target channel. Intervention state describes how
$X^{a}$ differs from $X^{a_0}$. Reference-forecast state summarises $p_0 = F(X^{a_0})$.
Appendix~\ref{app:features} is the canonical list, with the window lengths and the
normalisation, which is fitted on the replay bank only.""",
    r"""The estimator is a weighted average of the recorded utilities of the same action on nearby
states, in a fixed standardised feature space. The state $z_a$ of \eqref{eq:state} carries
twenty-two numbers in four groups: how the request is incomplete, what the observed part of the
target channel looks like, how $X^{a}$ differs from $X^{a_0}$, and what the reference forecast
$p_0 = F(X^{a_0})$ looks like. Appendix~\ref{app:features} is the canonical list, with the
window lengths and the normalisation, which is fitted on the replay bank only.""",
    tag="the state description points at its canonical list")

sub(r"""A request is served in two stages. The first reads the visible context and the mask, executes
the reference action to obtain $p_0$ and the reference-forecast state, materialises the
candidate input versions, and forms the action-conditioned states $z_a$. The second retrieves
the same-action neighbourhoods from the frozen bank, evaluates $S_a$ for every
$a \in \calA^{+}$, executes $a^{\star}$, and returns the resulting forecast, which is the
reference forecast when $a^{\star} = a_0$.""",
    r"""A request is served in two stages. The first executes the reference action to obtain $p_0$,
materialises the candidate input versions and forms the states $z_a$. The second retrieves the
same-action neighbourhoods from the frozen bank, evaluates $S_a$ for every $a \in \calA^{+}$,
executes $a^{\star}$ and returns its forecast, which is the reference forecast when
$a^{\star} = a_0$.""",
    tag="the deployment procedure drops what Figure 2 shows")



# ============================== 5. the roster definitions become a table

ROSTER_ROWS = "".join(
    row([label, what])
    for label, what in [
        (r"\textsc{Native Keep}", "hands the incomplete context to the frozen backbone and "
         "never intervenes. Every other row is measured against it"),
        (r"\textsc{Best Fixed}", "applies to every request the single catalog action with the "
         "highest mean realised utility on the replay bank, which makes it the strongest "
         "policy that ignores the request"),
        ("R2-CART", "one depth-three classification tree per action over the same state "
         "features, each asking whether that action beats the reference. The most confident "
         "action runs when its probability exceeds one half"),
        ("Fixed SAITS", "applies the trained imputer to every incomplete request. The imputer "
         "is one of the six catalog actions and its bank records are cross-fitted by parent, "
         "so the stored utility is out of sample"),
        ("TATO", "searches one transformation pipeline per source against the realised futures "
         "of the same TRAIN windows the replay bank is built from"),
        (r"\emph{Catalog Oracle}", "reads the future target and takes the best catalog action "
         "in hindsight. Diagnostic only, excluded from every rank and every claim"),
    ])

ROSTER = (r"""\begin{table}[h]
  \caption{The comparison, fixed before any evaluation record was read. Every row composes with
  the same frozen backbone and is given the same evidence, which is the TRAIN region under the
  registered missingness protocol including the realised futures of those windows. No row sees
  a TEST window before its numbers are computed.}
  \label{tab:app-roster}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}l p{0.76\textwidth}@{}}
    \toprule
""" + row(["Row", "What it does"])
    + "    \midrule\n" + ROSTER_ROWS + r"""    \bottomrule
  \end{tabular}
\end{table}""")

sub(r"""The comparison is fixed in advance. Three controls establish what a per-request decision has to
beat. \textsc{Native Keep} never intervenes and is the reference every other row is measured
against. \textsc{Best Fixed} applies to every request the single catalog action with the
highest mean realised utility on the replay bank, which makes it the strongest policy that
ignores the request. \textbf{R2-CART} is the simple learned selector inherited from the
previous development cycle: one depth-three classification tree per action over the same state
features, each asking whether that action beats the reference, executing the most confident
action when its probability exceeds one half. \textbf{Fixed SAITS} applies the trained
imputer~\citep{du2023saits,du2023pypots} to every incomplete request. That imputer is one of
the six catalog actions, fitted per source on the same TRAIN windows under the same missingness
protocol, so this row is the policy that always executes the strongest trained repair. Its bank
records are cross-fitted by parent, because a window the model was fitted on would otherwise
report a utility that same model does not reach on a new request.
\textbf{TATO}~\citep{qiu2026tato} is the data-side adaptation baseline, whose
transformation pipeline is searched per source against the realised futures of the same TRAIN
windows the replay bank is built from, so no row is given evidence another one lacks. A
\emph{Catalog Oracle} that reads the future target is reported as a diagnostic and excluded
from all ranks.""",
    r"""The comparison is fixed in advance and Table~\ref{tab:app-roster} defines every row. Three
controls establish what a per-request decision has to beat: never intervening, applying the
single strongest catalog action to every request, and a simple learned selector over the same
state features. Two further rows always repair, one with the trained
imputer~\citep{du2023saits,du2023pypots} that is also a catalog action and one with the
data-side adaptation baseline~\citep{qiu2026tato}. A catalog oracle that reads the future
target is reported as a diagnostic and is excluded from every rank.""",
    tag="the roster definitions move to a table in the appendix")

sub(r"""\subsection{Baseline Configuration}
\label{app:baseline-config}""",
    ROSTER + r"""

\subsection{Baseline Configuration}
\label{app:baseline-config}""",
    tag="the roster table lands in the appendix")


# ============================= 6. the selection paragraph stops restating itself

sub(r"""The two hyperparameters are selected once per backbone, on the replay bank, by
leave-one-parent-out cross-validation: every bank episode is scored against a bank from which
all records of its own parent have been removed, which makes the cross-validated score a
statement about a request the bank has not seen. The grid is""",
    r"""The two hyperparameters are selected once per backbone on the replay bank by
leave-one-parent-out cross-validation, so every bank episode is scored against a bank with all
records of its own parent removed. The grid is""",
    tag="the selection paragraph drops a restatement")


TEX.write_text(TEXT, encoding="utf-8")
print("APPLIED:")
for item in APPLIED:
    print("  +", item)
print(f"\nwrote {TEX.name}, {len(TEXT)} characters, {TEXT.count('ph{')} placeholders")
