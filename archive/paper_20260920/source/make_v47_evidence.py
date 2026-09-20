#!/usr/bin/env python3
"""Fifth pass: every analysis gets a table, and the assumption gets tested.

Section 3.2 rested on an assumption that nothing in the paper measured, so the
appendix now carries the measurement and the main text says what it found.
The answer is not the flattering one, and saying so is the point: distance in
the state space orders the estimation error only weakly, so what the local
estimate buys is an answer that moves with the request rather than an answer
that is more accurate.  The ablation against the global variant already showed
that this is worth having.

Five appendix sections argued from prose alone.  Each gets a table, because a
rule stated in a sentence is a rule a reader has to reconstruct.

Usage: python latex/make_v47_evidence.py   (run after make_v47_tighten.py)
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


BACKBONES = [("BOLT", "Bolt"), ("TF", "TimesFM"), ("CH2", "Chronos-2")]


# ============================================ 1. the assumption gets measured

TRANSFER_ROWS = "".join(
    row([label]
        + [f"\\ph{{TR_{tag}_B{i}_{field}}}"
           for tag, _name in BACKBONES for field in ("DIST", "ERR", "SIGN")])
    for i, label in enumerate(["1 (closest)", "2", "3", "4", "5 (furthest)"], start=1))

TRANSFER = (r"""\subsection{Does the Local Transfer Assumption Hold?}
\label{app:transfer}
The decision layer rests on one empirical assumption, stated in \S\ref{sec:method-replay}:
requests whose states are close in the state space have similar action utilities. The
assumption implies a test. For every evaluation request and every admissible non-reference
action, record how far the retrieved neighbourhood actually was, what that neighbourhood
estimated, and what the action then did. If the assumption holds, the requests whose
neighbourhoods were closer carry the smaller estimation error.

Table~\ref{tab:app-transfer} runs that test. The furthest fifth does carry the largest error on
every backbone, so the assumption is not empty. It is also not monotone in between, and the
rank correlation between neighbourhood distance and absolute estimation error is
\ph{TR_BOLT_RHO} on Bolt, \ph{TR_TF_RHO} on TimesFM and \ph{TR_CH2_RHO} on the held-out family.
Distance therefore orders the estimation error weakly, and the local estimate is not earning
its place by being more accurate where the neighbourhood is tight.

What it earns is an answer that moves with the request. The A1 variant of
\S\ref{sec:exp-ablation} scores each action by its global mean utility, which is the same
estimate for every request, and it is worse than the local estimate on all three backbones
while intervening on every request. So the evidence supports a weaker statement than the one
the assumption makes: retrieving by state produces a per-request ranking that a corpus average
cannot produce, and the conservative threshold is what turns that ranking into a decision. We
state the assumption where the method needs it and report here that it holds only at the tail.

\begin{table}[h]
  \caption{The local transfer assumption, measured. Pairs are every admissible non-reference
  action of every evaluation request, split into five bins by the mean distance of the
  neighbourhood the rule retrieved. Distance is in the standardised state space, error is
  $|\hat\mu_a - g_a|$ between the estimate the rule acted on and what the action did, and sign
  agreement is how often the two share a sign. The frozen configuration is reused and nothing
  is selected here.}
  \label{tab:app-transfer}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lccccccccc}
    \toprule
""" + row([""] + [f"\\multicolumn{{3}}{{c}}{{{name}}}" for _tag, name in BACKBONES])
    + "    \\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\\cmidrule(lr){8-10}\n"
    + row(["Distance bin"] + ["Dist.", "$|\\hat\\mu_a - g_a|$", "Sign agr."] * 3)
    + "    \\midrule\n" + TRANSFER_ROWS
    + "    \\midrule\n"
    + row(["Rank corr.\\ of distance with error",
           "\\multicolumn{3}{c}{\\ph{TR_BOLT_RHO}}",
           "\\multicolumn{3}{c}{\\ph{TR_TF_RHO}}",
           "\\multicolumn{3}{c}{\\ph{TR_CH2_RHO}}"])
    + r"""    \bottomrule
  \end{tabular}}
\end{table}

""")

sub(r"""\subsection{Dataset and Missingness Protocol}
\label{app:data-protocol}""",
    TRANSFER + r"""\subsection{Dataset and Missingness Protocol}
\label{app:data-protocol}""",
    tag="the local transfer test enters the appendix")

sub(r"""The step from the bank to a decision rests on one empirical assumption, stated explicitly.
Requests whose action-conditioned states are close in the state space have similar action
utilities, so the utility of an action on a new request can be estimated from the same-action
neighbourhood of its state in the bank. This local transfer assumption is not asserted outside
the registered grid, and the paper makes no claim about behaviour beyond the patterns and
severities that were replayed.""",
    r"""The step from the bank to a decision rests on one empirical assumption, stated explicitly.
Requests whose action-conditioned states are close in the state space have similar action
utilities, so the utility of an action on a new request can be estimated from the same-action
neighbourhood of its state. Appendix~\ref{app:transfer} measures it and finds that it holds at
the tail rather than throughout: the requests with the furthest neighbourhoods do carry the
largest estimation error, and distance orders that error only weakly in between. What the local
estimate supplies is therefore a ranking that moves with the request, which
\S\ref{sec:exp-ablation} shows a corpus average cannot supply. The assumption is not asserted
outside the registered grid either, and the paper makes no claim about behaviour beyond the
patterns and severities that were replayed.""",
    tag="section 3.2 states what the measurement found")


# ================================= 2. the counting rules become a table

COUNTING = (r"""\begin{table}[h]
  \caption{The four counting rules, fixed before any evaluation record was read. Each one is a
  convention rather than a metric, and a different convention would change a reported number
  without changing a single forecast.}
  \label{tab:app-counting}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}p{0.17\textwidth} p{0.40\textwidth} p{0.33\textwidth}@{}}
    \toprule
""" + row(["Quantity", "Rule", "Boundary case"])
    + "    \\midrule\n"
    + row(["Oracle-best action",
           "the admissible action with the smallest realised loss",
           "ties go to the first action in the frozen catalog order, so the shares sum to "
           "one. Unsupported, aliased and failed actions leave the argmin rather than "
           "counting as a loss"])
    + row(["Utility sign",
           "harmful when $g_{i,a} < 0$ strictly, beneficial when $g_{i,a} > 0$ strictly",
           "$g_{i,a} = 0$ enters neither rate and is reported as its own count"])
    + row(["Beneficial precision",
           "executed interventions with strictly positive utility, over executed interventions",
           "undefined when nothing was executed, and reported as missing rather than as zero"])
    + row(["Opportunity strata",
           "two pre-declared quantiles of $\\Delta_i$ on the replay bank, applied unchanged "
           "to TEST",
           "the same two values partition every method and no boundary is recomputed per "
           "method"])
    + r"""    \bottomrule
  \end{tabular}
\end{table}""")

sub(r"""Four quantities in the diagnostics are counting rules rather than metrics, and each one is
fixed before any evaluation record is read, because a different convention would change the
reported numbers without changing a single forecast.""",
    r"""Four quantities in the diagnostics are counting rules rather than metrics, and
Table~\ref{tab:app-counting} fixes each one before any evaluation record is read.

""" + COUNTING,
    tag="the counting rules become a table")


# ================================ 3. the baseline configuration becomes a table

BASELINECFG = (r"""\begin{table}[h]
  \caption{What each fitted row was given. Both read the TRAIN region under the registered
  missingness protocol, including the realised futures of those windows, and neither sees a
  TEST window before its numbers are computed.}
  \label{tab:app-baselinecfg}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}p{0.17\textwidth} p{0.26\textwidth} p{0.47\textwidth}@{}}
    \toprule
""" + row(["Row", "Unit of fitting", "Configuration"])
    + "    \\midrule\n"
    + row(["Fixed SAITS, deployment model",
           "one per source, on every bank parent",
           "the packaged implementation, two layers, model width 128, four heads, "
           "feed-forward width 128, dropout $0.1$, batch size 16, at most "
           "\\ph{SAITS_EPOCHS} epochs with early stopping. Sources with more than "
           "\\ph{SAITS_MAXCH} channels use the target channel plus the covariates most "
           "correlated with it on TRAIN"])
    + row(["Fixed SAITS, bank records",
           "two per source, each on half the bank parents by origin time",
           "the same configuration. A window is repaired only by the model that never saw "
           "its own parent, so the utility stored for this action is out of sample"])
    + row(["TATO",
           "one pipeline per source and backbone",
           "the official implementation over its eight transformation slots, "
           "\\ph{TATO_TRIALS} trials seeded with the identity pipeline, each scored by the "
           "mean absolute error against the realised futures of \\ph{TATO_WINDOWS} TRAIN "
           "windows. Gaps are filled by linear interpolation first, which the official "
           "pipeline requires, and that step is part of what the row measures"])
    + r"""    \bottomrule
  \end{tabular}
\end{table}""")

sub(r"""\paragraph{The trained imputer.}""",
    BASELINECFG + r"""

\paragraph{The trained imputer.}""",
    tag="the baseline configuration becomes a table")


# ============================== 4. the scope statement becomes a table

CLAIMS = (r"""\begin{table}[h]
  \caption{What the evidence supports and what it does not. The right column is not a list of
  weaknesses to be fixed later; it marks the statements this protocol cannot make, whatever the
  numbers had been.}
  \label{tab:app-claims}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}p{0.46\textwidth} p{0.46\textwidth}@{}}
    \toprule
""" + row(["Supported by the reported evidence", "Not claimed anywhere"])
    + "    \\midrule\n"
    + row(["Selective intervention inside the registered missingness grid, on the four "
           "patterns and three severities that were replayed",
           "out-of-grid or out-of-distribution missingness generalisation"])
    + row(["Transfer of the frozen procedure to a backbone family that took no part in "
           "method design, with its bank rebuilt by that family",
           "that the method can detect that its historical evidence is insufficient for "
           "the request in front of it"])
    + row(["A conservative score that orders actions and a threshold that decides whether "
           "any of them runs",
           "any coverage or risk-control guarantee for that score"])
    + row(["Behaviour under controlled deletion from complete series",
           "that the results extend to naturally incomplete deployment streams"])
    + r"""    \bottomrule
  \end{tabular}
\end{table}""")

sub(r"""Four claims are therefore not made anywhere in this paper.""",
    CLAIMS + r"""

Table~\ref{tab:app-claims} states the two sides together. Four claims are therefore not made
anywhere in this paper.""",
    tag="the scope statement becomes a table")


# ========================= 5. the positioning becomes a table

POSITIONING = (r"""\begin{table}[h]
  \caption{Where the decision layer sits. The row that matters is the third column: what has to
  be corrected for before the recorded outcomes can be used.}
  \label{tab:app-positioning}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}p{0.19\textwidth} p{0.33\textwidth} p{0.38\textwidth}@{}}
    \toprule
""" + row(["Setting", "What the record holds", "What it needs"])
    + "    \\midrule\n"
    + row(["Off-policy evaluation",
           "the outcome of the logged action alone",
           "a propensity correction, because the logging policy chose which outcome exists"])
    + row(["Selective prediction and learning to defer",
           "the outcome of the answer that was produced",
           "a second answerer, or an abstention, since what changes is who answers"])
    + row(["Historical full-action replay",
           "the outcome of every catalog action on the same window against the same "
           "realised future",
           "nothing of the kind. There is no partial feedback to correct and no online "
           "exploration, because no action is ever executed at deployment in order to learn"])
    + r"""    \bottomrule
  \end{tabular}
\end{table}""")

sub(r"""Selective prediction abstains on part of the input in order to trade coverage for lower
risk~\citep{chow1970optimum,vovk2005algorithmic,geifman2017selective,lei2018distribution}, and
learning to defer routes part of the input to a human or to another decision
maker~\citep{madras2018predict,mozannar2020consistent}.""",
    POSITIONING + r"""

Selective prediction abstains on part of the input in order to trade coverage for lower
risk~\citep{chow1970optimum,vovk2005algorithmic,geifman2017selective,lei2018distribution}, and
learning to defer routes part of the input to a human or to another decision
maker~\citep{madras2018predict,mozannar2020consistent}.""",
    tag="the positioning becomes a table")


# ==================== 6. the development record becomes a table

DEVELOPMENT = (r"""\begin{table}[h]
  \caption{What was tried before the present formulation and why it was dropped. The
  measurements behind these decisions come from an earlier protocol with a smaller development
  split and different budget accounting, so they are recorded in the released ledger and are
  not comparable with any table in this paper.}
  \label{tab:app-development}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}p{0.19\textwidth} p{0.35\textwidth} p{0.36\textwidth}@{}}
    \toprule
""" + row(["Tried", "What happened", "What it changed here"])
    + "    \\midrule\n"
    + row(["Projecting the estimated utility vector onto a convex feasible set before "
           "thresholding",
           "the squared error of the estimated vector fell and the forecasting metric did "
           "not follow, and on one backbone it got worse",
           "actions are ranked by a local mean and a dispersion penalty and a single "
           "threshold is applied, instead of calibrating a continuous score"])
    + row(["Treating the simple selector as a stepping stone rather than a control",
           "it was competitive with the more elaborate candidate of that cycle and better "
           "than it on one backbone",
           "R2-CART is a mandatory control in every main-text table"])
    + row(["Judging the gate by forecasting accuracy alone",
           "reducing estimation error on a continuous score did not improve the discrete "
           "selection",
           "the gate is evaluated on harmful intervention rate and harmful loss as well as "
           "on MASE"])
    + r"""    \bottomrule
  \end{tabular}
\end{table}""")

sub(r"""An earlier configuration tried to improve the action ranking by projecting estimated utility
vectors onto a convex feasible set before thresholding them.""",
    DEVELOPMENT + r"""

An earlier configuration tried to improve the action ranking by projecting estimated utility
vectors onto a convex feasible set before thresholding them.""",
    tag="the development record becomes a table")


# ============================= 7. the last lines the main text can spare

sub(r"""The evidence also has a clear boundary. All missingness here comes from controlled deletion
under a registered protocol, the replay bank covers only the patterns and severities that were
replayed, and the method cannot detect that a request lies outside that grid. The results
therefore support selective intervention under the evaluated controlled-missingness protocols
and frozen backbones, and generalisation to unseen mechanisms and to naturally incomplete
streams remains open. \ph{CONCLUSION_CLOSING}.""",
    r"""The boundary is equally clear. All missingness here comes from controlled deletion under a
registered protocol, and the method cannot detect that a request lies outside that grid, so
generalisation to unseen mechanisms and to naturally incomplete streams remains open
(Appendix~\ref{app:scope}). \ph{CONCLUSION_CLOSING}.""",
    tag="the conclusion stops restating the scope appendix")

sub(r"""The catalog is fixed at six admissible actions with \textsc{Keep} as the reference $a_0$, and
a complete and valid input is always mapped to \textsc{Keep}. Appendix~\ref{app:catalog}
defines each action and the status rules for unsupported, aliased, or failed executions.""",
    r"""The catalog is fixed at six admissible actions with \textsc{Keep} as the reference $a_0$, and
Appendix~\ref{app:catalog} defines each one.""",
    tag="the catalog sentence points at its table")


TEX.write_text(TEXT, encoding="utf-8")
print("APPLIED:")
for item in APPLIED:
    print("  +", item)
print(f"\nwrote {TEX.name}, {len(TEXT)} characters, {TEXT.count('ph{')} placeholders")
