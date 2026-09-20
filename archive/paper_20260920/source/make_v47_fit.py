#!/usr/bin/env python3
"""Sixth pass: the last twenty lines, so the conclusion lands on page nine.

Six places where the main text says something twice, or says at length what an
appendix table now says exactly.  Each is cut to the sentence that carries the
argument.  Nothing that a claim depends on leaves the main text.

Usage: python latex/make_v47_fit.py   (run after make_v47_evidence.py)
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


sub(r"""Selective prediction abstains on part of the input to trade coverage for lower
risk~\citep{chow1970optimum,vovk2005algorithmic,geifman2017selective,lei2018distribution}, and
learning to defer routes it to another decision maker~\citep{madras2018predict,
mozannar2020consistent}. Both change who or what produces the answer. Here the same frozen
forecaster answers every request and what is selected is whether the input is modified first.
Picking one of a fixed set of procedures from features of the instance is the shape of
per-instance algorithm selection~\citep{rice1976algorithm,xu2008satzilla}. What differs is the
supervision: the label here is the forecasting utility a repair actually produced on this
frozen model, not a property of the repair itself.
The decision layer is a supervised local estimation problem. Replay executes every action on
the same window against the same realised future, so the bank holds full action outcomes and no
propensity correction arises, which is what separates it from off-policy
evaluation~\citep{dudik2011doubly,swaminathan2015counterfactual}. Appendix~\ref{app:ope-positioning} states the positioning in
full.""",
    r"""Selective prediction abstains on part of the input to trade coverage for lower
risk~\citep{chow1970optimum,vovk2005algorithmic,geifman2017selective,lei2018distribution} and
learning to defer routes it to another decision maker~\citep{madras2018predict,
mozannar2020consistent}, and both change who produces the answer. Here the same frozen
forecaster answers every request and what is selected is whether the input is modified first.
Choosing one of a fixed set of procedures from features of the instance is the shape of
per-instance algorithm selection~\citep{rice1976algorithm,xu2008satzilla}, and what differs is
the label: the forecasting utility a repair produced on this frozen model. Replay executes
every action on the same window against the same realised future, so no propensity correction
arises and the setting is not off-policy
evaluation~\citep{dudik2011doubly,swaminathan2015counterfactual}.
Appendix~\ref{app:ope-positioning} sets the three side by side.""",
    tag="selective decision making, said once")

sub(r"""Each source is split chronologically at three quarters of its rows, the earlier part TRAIN and
the later part TEST, and the last TRAIN window of each source is dropped so the gap exceeds the
$L + H$ purge everywhere. TRAIN is split by origin time into the replay bank and a TRAIN-eval
block used once as an internal acceptance check. All design, hyperparameter selection, feature
normalisation and baseline fitting use TRAIN only, and every reported table is computed once on
TEST after the configuration is frozen. MASE~\citep{hyndman2006mase} is the primary metric and
RMSSE the secondary one, aggregated source-macro with the parent as the statistical unit and
paired cluster bootstrap intervals. Appendices \ref{app:splits},
\ref{app:metric-conventions} and \ref{app:diagnostic-conventions} hold the split boundaries,
the metric and statistics conventions, and the diagnostic counting rules.""",
    r"""Each source is split chronologically at three quarters of its rows with an $L + H$ purge, and
TRAIN is split again by origin time into the replay bank and a TRAIN-eval block used once as an
acceptance check. All design, hyperparameter selection, feature normalisation and baseline
fitting use TRAIN only, and every reported table is computed once on TEST after the
configuration is frozen. MASE~\citep{hyndman2006mase} is the primary metric and RMSSE the
secondary one, source-macro aggregated with the parent as the statistical unit and paired
cluster bootstrap intervals. Appendices \ref{app:splits}, \ref{app:metric-conventions} and
\ref{app:diagnostic-conventions} hold the boundaries, the conventions and the counting rules.""",
    tag="the split paragraph points at the appendix")

sub(r"""neighbourhood of its state. Appendix~\ref{app:transfer} measures it and finds that it holds at
the tail rather than throughout: the requests with the furthest neighbourhoods do carry the
largest estimation error, and distance orders that error only weakly in between. What the local
estimate supplies is therefore a ranking that moves with the request, which
\S\ref{sec:exp-ablation} shows a corpus average cannot supply. The assumption is not asserted
outside the registered grid either, and the paper makes no claim about behaviour beyond the
patterns and severities that were replayed.""",
    r"""neighbourhood of its state. Appendix~\ref{app:transfer} measures it: the furthest
neighbourhoods do carry the largest estimation error, and distance orders that error only
weakly in between, so what the local estimate supplies is a ranking that moves with the
request rather than a more accurate one. The assumption is not asserted outside the registered
grid, and the paper makes no claim about behaviour beyond the patterns and severities that
were replayed.""",
    tag="the assumption reports its measurement in one sentence")

sub(r"""A repair may write only values inside the range of the visible target widened by three robust
scales, and an action whose candidate leaves that range is recorded as unsupported on that
request instead of being executed. The bound is registered with the protocol and is applied
identically when the bank is built and when a request is served, so a diverging extrapolation
is caught where it is produced.""",
    r"""A repair may write only values inside the range of the visible target widened by three robust
scales, and a candidate that leaves that range is recorded as unsupported instead of executed.
The bound is registered with the protocol and holds identically for the bank and for a served
request.""",
    tag="the plausibility bound in three lines")

sub(r"""\textbf{(2)~Historical full-action
replay.} We build a replay bank by injecting the registered missingness protocol into TRAIN
history and executing every catalog action with the frozen forecaster, so the stored
supervision is a realised forecasting utility rather than a reconstruction score. A request is
then served by estimating that utility locally and executing an action only when a
conservative score is positive (\S\ref{sec:method}).""",
    r"""\textbf{(2)~Historical full-action
replay.} We inject the registered missingness protocol into TRAIN history and execute every
catalog action with the frozen forecaster, so the stored supervision is a realised forecasting
utility rather than a reconstruction score. A request is served by estimating that utility
locally and executing an action only when a conservative score is positive
(\S\ref{sec:method}).""",
    tag="contribution two in five lines")

sub(r"""Every ablation reuses the same catalog prediction cache, so the rows are recomputed selector
variants and not new forecasting runs. Every difference reported below is the MASE of the full
method minus the MASE of the variant, so a negative value favours the full method. A1 scores each action by its global mean utility
instead of by its neighbourhood, A2 and A3 drop the intervention and the reference-forecast
block of the state, A4 removes the reference option so that an action runs on every request,
and A5 replaces the local estimate with a per-action linear utility predictor over the same
features. Appendix~\ref{app:ablation-details} gives the exact definitions.""",
    r"""Every ablation reuses the same catalog prediction cache, so the rows are recomputed selector
variants and not new forecasting runs, and every difference below is the MASE of the full
method minus that of the variant. A1 scores each action by its global mean utility instead of
by its neighbourhood, A2 and A3 drop the intervention and the reference-forecast block of the
state, A4 removes the reference option, and A5 replaces the local estimate with a per-action
linear predictor over the same features (Appendix~\ref{app:ablation-details}).""",
    tag="the ablation definitions in six lines")



# ---- the rank grid joins the per-action table of the same experiment

start = TEXT.index(r"\begin{table}[t]" + "\n" + r"  \caption{Within-episode reconstruction rank")
end = TEXT.index(r"\end{table}", start) + len(r"\end{table}")
RANKGRID = TEXT[start:end].replace(r"\begin{table}[t]", r"\begin{table}[h]", 1)
TEXT = TEXT[:start] + TEXT[end:].lstrip("\n")
APPLIED.append("the rank grid leaves the main text")

sub(r"""sources of different scale apart. \ph{RECON_READING}. Table~\ref{tab:rankgrid} shows the two
rankings against each other and Appendix~\ref{app:recutils} reports them per action.""",
    r"""sources of different scale apart. \ph{RECON_READING}. Table~\ref{tab:heterogeneity} carries
the summary, and Appendix~\ref{app:recutils} reports both criteria per action with
Table~\ref{tab:rankgrid} giving the two rankings against each other.""",
    tag="section 4.2 points at the appendix for the grid")

sub(r"""\begin{table}[h]
  \caption{Reconstruction quality against realised forecasting utility, over the five catalog""",
    RANKGRID + r"""

\begin{table}[h]
  \caption{Reconstruction quality against realised forecasting utility, over the five catalog""",
    tag="the rank grid lands beside the per-action table")



sub(r"""The boundary is equally clear. All missingness here comes from controlled deletion under a
registered protocol, and the method cannot detect that a request lies outside that grid, so
generalisation to unseen mechanisms and to naturally incomplete streams remains open
(Appendix~\ref{app:scope}). \ph{CONCLUSION_CLOSING}.""",
    r"""The boundary is equally clear. All missingness here is controlled deletion under a registered
protocol and the method cannot tell that a request lies outside that grid, so naturally
incomplete streams remain open (Appendix~\ref{app:scope}). \ph{CONCLUSION_CLOSING}.""",
    tag="the conclusion boundary in two lines")

sub(r"""We studied incomplete-input handling for frozen \tsfm{}s as a per-request decision over a fixed
catalog of admissible interventions. The realised utility of an intervention is not observable
at forecast time, and reconstruction quality turns out to be close to uninformative about it,
so \introact{} reads the answer off history: it replays TRAIN windows as pseudo-deployments,
executes every catalog action with the frozen forecaster, and stores what each action did.""",
    r"""We studied incomplete-input handling for frozen \tsfm{}s as a per-request decision over a fixed
catalog of admissible interventions. The realised utility of an intervention is not observable
at forecast time and reconstruction quality is close to uninformative about it, so \introact{}
replays TRAIN windows as pseudo-deployments, executes every catalog action with the frozen
forecaster, and stores what each action did.""",
    tag="the conclusion opening in five lines")


TEX.write_text(TEXT, encoding="utf-8")
print("APPLIED:")
for item in APPLIED:
    print("  +", item)
print(f"\nwrote {TEX.name}, {len(TEXT)} characters, {TEXT.count('ph{')} placeholders")
