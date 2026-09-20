#!/usr/bin/env python3
"""Produce the v4.7 manuscript template from the v4.6 one.

Two kinds of change.  The first are corrections that do not depend on any new
number: the claims about what a frozen forecaster rules out, the forward
reference that pointed at a section which did not carry it, the appendix that
described a bank sliced by source and horizon while the code never sliced it,
the comma splice in the problem setup, and the wording the project's own style
rules forbid.  The second follow the catalog gaining a trained imputer and the
selection rule losing its one standard error step.

Usage: python latex/make_v47.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "IntroActTS_20260919_v46.tex"
DST = HERE / "IntroActTS_20260919_v47.tex"

TEXT = SRC.read_text(encoding="utf-8")
APPLIED: list[str] = []


def sub(old: str, new: str, *, tag: str) -> None:
    global TEXT
    if TEXT.count(old) != 1:
        raise SystemExit(f"FAILED {tag}: anchor appears {TEXT.count(old)} times")
    TEXT = TEXT.replace(old, new)
    APPLIED.append(tag)


# ================================================================== abstract

sub("""Existing methods reconstruct the unavailable values or train an
architecture that tolerates missingness, and both options are closed once the forecaster is
frozen.""",
    """One line of work reconstructs the unavailable values, and what it
optimises is how closely they come back rather than what the forecast does with them. Another
trains an architecture that tolerates missingness, which a frozen forecaster rules out.""",
    tag="abstract: what a frozen forecaster actually rules out")

sub("""held out from method design, \\ph{ABSTRACT_RESULT}. \\ph{ABSTRACT_CLOSING}.""",
    """held out from method design, \\ph{ABSTRACT_RESULT}. \\ph{ABSTRACT_HARM}.
\\ph{ABSTRACT_CLOSING}.""",
    tag="abstract: report the governance result as well as the accuracy")


# ============================================================== introduction

sub("""The usual response is imputation, and it is scored on how accurately the missing entries come
back~\\citep{cao2018brits,tashiro2021csdi,du2023saits}. A second line handles missingness inside
the forecasting model instead~\\citep{chen2024bitgraph,peng2025s4m}. Both lines train or
redesign the predictor, which a frozen foundation model takes off the table. A third
line moves the objective from recovery to downstream utility, estimating how imputed values
affect the forecaster and combining strategies by the estimated
gain~\\citep{wang2024taskoriented,hao2025toivsf,xu2026srdi}, and TATO adapts a frozen \\tsfm{} to
a domain through transformation pipelines selected from historical task
performance~\\citep{qiu2026tato}. These methods decide at training time, over a corpus, which
strategy or transformation to use. The decision studied here is made at deployment time, for
one request.""",
    """The usual response is imputation, and it is scored on how accurately the missing entries come
back~\\citep{cao2018brits,tashiro2021csdi,du2023saits}. A second line handles missingness inside
the forecasting model instead~\\citep{chen2024bitgraph,peng2025s4m}, which trains a predictor and
is therefore closed to a deployment that must keep its forecaster fixed. Imputation stays open,
and what it optimises is the recovery of the hidden values rather than the effect they have on
the forecast. A third line moves the objective from recovery to downstream utility, estimating
how imputed values affect the forecaster and combining strategies by the estimated
gain~\\citep{wang2024taskoriented,hao2025toivsf,xu2026srdi}. TATO adapts a frozen \\tsfm{} to a
domain through transformation pipelines selected from historical task
performance~\\citep{qiu2026tato}. All of these decide at training time, over a corpus, which
strategy or transformation to use. The decision studied here is made at deployment time, for
one request.""",
    tag="intro: imputation is not closed by freezing the forecaster")

sub("""That decision is what remains once the model is in service. The forecaster is frozen, the""",
    """That decision is what a deployed system still controls. The forecaster is frozen, the""",
    tag="intro: plainer opening of the third paragraph")

sub("""conflict, and an action that looks favourable on average can still increase the loss of the
request at hand, so an action runs only when the local evidence says it will help and the
input is otherwise left alone.""",
    """conflict, and an action that looks favourable on average can still increase the loss of the
request at hand, so an action runs only when the lower end of the local evidence is still
positive, and the input is left alone otherwise.""",
    tag="intro: the third property matches the rule the method implements")

sub("""\\textbf{(3)~Evidence on accuracy, harm
and cost.} Against a no-op control, the best fixed intervention, a simple learned selector, a
published reconstruction baseline and a published data-side adaptation baseline, on eight
sources, three frozen \\tsfm{} families, four missingness patterns and three severity levels,
\\ph{CONTRIB_RESULT} (\\S\\ref{sec:exp-main}, \\S\\ref{sec:exp-harm}, \\S\\ref{sec:exp-robust}).""",
    """\\textbf{(3)~Evidence on accuracy, harm
and cost.} The comparison covers eight sources, three frozen \\tsfm{} families, four missingness
patterns and three severity levels. Its controls are a no-op, the best fixed intervention, a
simple learned selector, a trained imputer applied to every incomplete request, and a published
data-side adaptation baseline. \\ph{CONTRIB_RESULT}
(\\S\\ref{sec:exp-main}, \\S\\ref{sec:exp-harm}, \\S\\ref{sec:exp-robust}).""",
    tag="intro: contribution three names the roster in short sentences")


# ============================================================= related work

sub("""So the three routes recover the hidden values, train a predictor that tolerates them, or pick
an imputation strategy from corpus-level task performance. \\introact{} keeps the predictor fixed
and works at the deployment stage, where the request has arrived, the backbone is frozen, the
future target is unavailable, and the system selects one input version from a finite catalog or
keeps the reference input.""",
    """\\introact{} keeps the predictor fixed and works at the deployment stage, where the request has
arrived, the backbone is frozen, the future target is unavailable, and the system selects one
input version from a finite catalog or keeps the reference input. The first route supplies
members of that catalog: a trained imputer enters this paper both as one of the available
repairs and as the policy that applies it to every incomplete request.""",
    tag="related: drop the recap and place the reconstruction route inside the catalog")

sub("""mozannar2020consistent}. Both change who or what produces the answer. Here the same frozen
forecaster answers every request and what is selected is whether the input is modified first.
The decision layer is a supervised local estimation problem.""",
    """mozannar2020consistent}. Both change who or what produces the answer. Here the same frozen
forecaster answers every request and what is selected is whether the input is modified first.
Picking one of a fixed set of procedures from features of the instance is the shape of
per-instance algorithm selection~\\citep{rice1976algorithm,xu2008satzilla}. What differs is the
supervision: the label here is the forecasting utility a repair actually produced on this
frozen model, not a property of the repair itself.
The decision layer is a supervised local estimation problem.""",
    tag="related: name per-instance algorithm selection")


# ==================================================================== method

sub("""Three constraints define the deployment protocol. No observation that has arrived and is valid
may be overwritten, so every $X^{a}$ differs from $X^{a_0}$ only at positions where $M = 0$.
The future target is unavailable, so no realised loss is observable at deployment time. The
reference forecast is the only forecast that may be computed before the decision, This is a
call budget, not a claim about what is knowable: a request may spend one
forecasting-backbone call to obtain $p_0 = F(X^{a_0})$, and the forecasts of the remaining
candidates must not be inspected when the action is chosen.""",
    """Four constraints define the deployment protocol. No observation that has arrived and is valid
may be overwritten, so every $X^{a}$ differs from $X^{a_0}$ only at positions where $M = 0$.
A repair may write only values inside the range of the visible target widened by three robust
scales, and an action whose candidate leaves that range is recorded as unsupported on that
request instead of being executed. The bound is registered with the protocol and is applied
identically when the bank is built and when a request is served, so a diverging extrapolation
is caught where it is produced. The future target is unavailable, so no realised loss is
observable at deployment time. The reference forecast is the only forecast that may be computed
before the decision. That is a call budget rather than a claim about what is knowable: a
request may spend one forecasting-backbone call to obtain $p_0 = F(X^{a_0})$, and the forecasts
of the remaining candidates must not be inspected when the action is chosen.""",
    tag="method: the plausibility bound is part of the protocol, and the comma splice is gone")

sub("""Let $\\loss$ be the forecasting loss, defined on the same
normalised scale as the primary evaluation metric so that replay utilities and reported errors
are directly comparable.""",
    """Let $\\loss$ be the episode-level MASE of a forecast, which is also the primary evaluation
metric, so replay utilities and reported errors carry one scale.""",
    tag="method: the loss is named rather than described")

sub("""We measure it, and \\S\\ref{sec:exp-exists} reports how far the two development backbones diverge
on this point.""",
    """We measure it, and \\S\\ref{sec:exp-exists} reports how far the backbones diverge on this point.""",
    tag="method: keep the forward reference and make the target section carry it")

sub("""severities rather than a model of missingness. Retrieval itself is not restricted to a source
or a horizon: the state carries the mask geometry, the visible context and the reference
forecast, which is what the neighbourhood is meant to match on, and restricting retrieval to
the request's own source or horizon costs accuracy on one development backbone while gaining
little on the other (Appendix~\\ref{app:replay}).""",
    """severities rather than a model of missingness. Retrieval itself is not restricted to a source
or a horizon. The state carries the mask geometry, the visible context and the reference
forecast, which is what the neighbourhood is meant to match on, and
Appendix~\\ref{app:replay} reports what each restriction costs.""",
    tag="method: the retrieval scope points at a table that exists")

sub("""conditional harmful rate stays at or below a cap. The cap is not a free number: it is the conditional harmful rate of the action
with the highest mean realised utility on the same bank, so the constraint says that choosing
per request may not be more harmful, given that it intervenes, than always applying the
strongest single intervention. If no setting satisfies it the configuration falls back to the
largest penalty strength. A few requests on which an intervention fails badly move the source
macro further than the spread between neighbouring settings, so the cross-validated surface is
rough and its minimum carries noise. Each admissible setting is therefore compared against the
leading one by a paired difference clustered on the parent, and among those whose gap falls
inside one standard error the rule takes the setting that intervenes least, on the same
reasoning as the cap. The anchor, the cap, the retained settings and the selected pair are
recorded before any evaluation record is scored.""",
    """conditional harmful rate stays at or below a cap. The cap is read off the bank: it is the
conditional harmful rate of the action with the highest mean realised utility there, so the
constraint says that choosing per request may not be more harmful, given that it intervenes,
than always applying the strongest single intervention. Among the admissible settings the rule
takes the lowest cross-validated source-macro MASE, and a tie on that value goes to the setting
that intervenes least. If no setting satisfies the cap the configuration falls back to the
largest penalty strength. The anchor, the cap, the admissible settings and the selected pair
are recorded before any evaluation record is scored.""",
    tag="method: selection is a constrained minimisation")

sub("""A request costs one forecasting-backbone call for the reference action plus one more if an
intervention is executed, and the returned forecast is always one call of the unchanged $F$ on
one executed input version. Two of the four interventions build their candidate by calling a
frozen in-context imputation model, which is paid before the decision.""",
    """A request costs one forecasting-backbone call for the reference action plus one more if an
intervention is executed, and the returned forecast is always one call of the unchanged $F$ on
one executed input version. Three of the five interventions build their candidate with a model
of their own, two by calling a frozen in-context imputation model and one by calling the
trained imputer, and all of that is paid before the decision.""",
    tag="method: the cost sentence counts six actions")


# =============================================================== experiments

sub("""The catalog is fixed at five admissible actions with \\textsc{Keep} as the reference $a_0$, and
a complete and valid input is always mapped to \\textsc{Keep}.""",
    """The catalog is fixed at six admissible actions with \\textsc{Keep} as the reference $a_0$, and
a complete and valid input is always mapped to \\textsc{Keep}.""",
    tag="setup: the catalog holds six actions")

sub("""Two published methods compose with a frozen
backbone and are reported in full: SAITS~\\citep{du2023saits,du2023pypots} is the
reconstruction baseline, trained per source on the same TRAIN windows under the same
missingness protocol, and TATO~\\citep{qiu2026tato} is the data-side adaptation baseline, whose
transformation pipeline is searched per source against the realised futures of the same TRAIN
windows the replay bank is built from, so neither method is given evidence the other lacks.""",
    """\\textbf{Fixed SAITS} applies the trained
imputer~\\citep{du2023saits,du2023pypots} to every incomplete request. That imputer is one of
the six catalog actions, fitted per source on the same TRAIN windows under the same missingness
protocol, so this row is the policy that always executes the strongest trained repair. Its bank
records are cross-fitted by parent, because a window the model was fitted on would otherwise
report a utility that same model does not reach on a new request.
\\textbf{TATO}~\\citep{qiu2026tato} is the data-side adaptation baseline, whose
transformation pipeline is searched per source against the realised futures of the same TRAIN
windows the replay bank is built from, so no row is given evidence another one lacks.""",
    tag="setup: the imputer is a catalog action and a fixed policy")

sub("""Both statistics below are diagnostics computed on TEST after the configuration is frozen and
are used for no selection. The first premise is that the best action varies across requests.""",
    """The statistics below are diagnostics computed on TEST after the configuration is frozen and
are used for no selection. \\ph{KEEP_SEMANTICS}. The first premise is that the best action
varies across requests.""",
    tag="experiments: the section carries the backbone difference it was said to carry")

sub("""run. The four catalog interventions and the published reconstruction baseline all estimate the
hidden positions explicitly and the mask is synthetic, so both rankings exist for the same
episode, and ranking inside an episode keeps sources of
different scale apart.""",
    """run. All five catalog interventions estimate the hidden positions explicitly and the mask is
synthetic, so both rankings exist for the same episode, and ranking inside an episode keeps
sources of different scale apart.""",
    tag="experiments: the reconstruction comparison runs on the catalog")

sub("""Every ablation reuses the same catalog prediction cache, so the rows are recomputed selector
variants rather than new forecasting runs. A1""",
    """Every ablation reuses the same catalog prediction cache, so the rows are recomputed selector
variants and not new forecasting runs. Every difference reported below is the MASE of the full
method minus the MASE of the variant, so a negative value favours the full method. A1""",
    tag="ablation: the sign convention is stated once")


# ================================================================== appendix

sub("""Two properties of the bank carry the scope of the method. It is indexed by the frozen backbone
revision and by the source, since a utility measured with one revision of one model does not
describe another and the state distribution differs across sources. The method therefore
requires labelled in-source history for the backbone it serves, which places it in the
frozen-backbone and history-supervised regime rather than in a zero-shot regime.""",
    """Two properties of the bank carry the scope of the method. It is indexed by the frozen backbone
revision, since a utility measured with one revision of one model does not describe another.
The method therefore requires labelled history for the backbone it serves, which places it in
the frozen-backbone and history-supervised regime rather than in a zero-shot regime.""",
    tag="appendix: the bank is indexed by backbone, as the code has it")

sub("""Because a utility measured with one model revision does not
describe another, because the state distribution differs across sources, and because $g_{i,a}$
is a loss over the forecast horizon and therefore a different quantity at $H=96$ and at
$H=192$, the bank is built per frozen backbone revision, per source, and per horizon. A request
is scored only against the slice that matches its own horizon, and no horizon indicator is
needed in the state because the horizon is fixed by the slice. Pseudo-deployment severities are drawn from
$\\{10\\%, 30\\%, 50\\%\\}$ by deterministic hash of the same key that defines the mask, so the
bank covers the registered severity range without the method being retuned per severity.""",
    """Because a utility measured with one model revision does not describe another, the bank is
built per frozen backbone revision, and one bank serves every source and both horizons.
Table~\\ref{tab:app-retrieval} reports what restricting retrieval to the request's own source
or to its own horizon costs. Pseudo-deployment severities enumerate
$\\{10\\%, 30\\%, 50\\%\\}$ on every parent, pattern and horizon, so a request at any registered
severity has same-severity support and the method is not retuned per severity.

\\begin{table}[h]
  \\caption{What restricting retrieval costs. Each row keeps the frozen configuration and
  narrows the neighbourhood a request may draw on. Values are source-macro MASE on the
  held-out evaluation set. The reported method is the first row.}
  \\label{tab:app-retrieval}
  \\centering
  \\small
  \\setlength{\\tabcolsep}{4pt}
\\begin{tabular}{lccc}
    \\toprule
    Retrieval restriction & Bolt MASE $\\downarrow$ & TimesFM MASE $\\downarrow$ & Chronos-2 MASE $\\downarrow$ \\\\
    \\midrule
    none, the reported configuration & \\ph{RETR_NONE_BOLT} & \\ph{RETR_NONE_TF} & \\ph{RETR_NONE_CH2} \\\\
    same horizon only                & \\ph{RETR_HZ_BOLT}   & \\ph{RETR_HZ_TF}   & \\ph{RETR_HZ_CH2} \\\\
    same source only                 & \\ph{RETR_SRC_BOLT}  & \\ph{RETR_SRC_TF}  & \\ph{RETR_SRC_CH2} \\\\
    same source and horizon          & \\ph{RETR_BOTH_BOLT} & \\ph{RETR_BOTH_TF} & \\ph{RETR_BOTH_CH2} \\\\
    \\bottomrule
  \\end{tabular}
\\end{table}""",
    tag="appendix: the retrieval scope table the main text cites")



# ============================================ the catalog gains a sixth action

sub(r"""  \caption{The five admissible interventions. Observed entries are the entries that are""",
    r"""  \caption{The six admissible interventions. Observed entries are the entries that are""",
    tag="catalog table: six actions")

BS = "\\" * 2
sub("    " + r"\textsc{Context Ridge}& ridge reconstruction from the visible context & no & 1 "
    + BS + "\n    " + r"\bottomrule",
    "    " + r"\textsc{Context Ridge}& ridge reconstruction from the visible context & no & 1 "
    + BS + "\n    "
    + r"\textsc{SAITS}        & reconstruction by the trained imputer of the source & no & 1 "
    + BS + "\n    " + r"\bottomrule",
    tag="catalog table: the trained imputer row")

sub(r"""Table~\ref{tab:app-catalog} defines the five admissible actions. The catalog is closed, so no
action outside this set is ever executed, and no action may overwrite an observation that has
arrived and is valid.""",
    r"""Table~\ref{tab:app-catalog} defines the six admissible actions. The catalog is closed, so no
action outside this set is ever executed, and no action may overwrite an observation that has
arrived and is valid. Five of the six are pure functions of the request. The sixth calls a
trained imputer, so its records in the replay bank are cross-fitted: the parents of a source
are split into four folds and a window is repaired only by a model that never saw its own
parent, which is what keeps its stored utility out of sample. A request at deployment is
repaired by the model fitted on the whole bank.""",
    tag="catalog text: six actions and the cross-fitting rule")

# ------------------------------------------------- roster labels in the tables

for old, new, tag in [
    (r"""    SAITS              & Reconstruction          & \ph{SAITS_BOLT}""",
     r"""    Fixed SAITS        & Trained imputer         & \ph{SAITS_BOLT}""",
     "main table: the row is a fixed policy over a catalog action"),
    (r"""    SAITS              & \ph{HARM_MASE_SAITS}""",
     r"""    Fixed SAITS        & \ph{HARM_MASE_SAITS}""",
     "harm table label"),
    (r"""    SAITS                 & \ph{NOOP_SAITS}""",
     r"""    Fixed SAITS           & \ph{NOOP_SAITS}""",
     "opportunity strata label"),
    (r"""    SAITS & \ph{P1_SAITS}""",
     r"""    Fixed SAITS & \ph{P1_SAITS}""",
     "per-pattern label"),
    (r"""    SAITS & \ph{SEV10-SAITS-MASE}""",
     r"""    Fixed SAITS & \ph{SEV10-SAITS-MASE}""",
     "severity 10 label"),
    (r"""    SAITS & \ph{SEV30-SAITS-MASE}""",
     r"""    Fixed SAITS & \ph{SEV30-SAITS-MASE}""",
     "severity 30 label"),
    (r"""    SAITS & \ph{SEV50-SAITS-MASE}""",
     r"""    Fixed SAITS & \ph{SEV50-SAITS-MASE}""",
     "severity 50 label"),
    (r"""    SAITS              & \ph{RB_SAITS_10}""",
     r"""    Fixed SAITS        & \ph{RB_SAITS_10}""",
     "robustness label"),
    (r"""    SAITS                 & \ph{SAITS_OFF}""",
     r"""    Fixed SAITS           & \ph{SAITS_OFF}""",
     "cost table label"),
    (r"""    SAITS                  & \ph{REC_SAITS_MSE}""",
     r"""    \textsc{SAITS}         & \ph{REC_SAITS_MSE}""",
     "reconstruction table: SAITS is an action here"),
    (r"""    SAITS~\citep{du2023saits}       & ESWA 2023  & official, packaged~\citep{du2023pypots} & reconstruction baseline \\""",
     r"""    SAITS~\citep{du2023saits}       & ESWA 2023  & official, packaged~\citep{du2023pypots} & catalog action and fixed policy \\""",
     "availability table: the role of the imputer"),
]:
    sub(old, new, tag=tag)

for tag_backbone in ("BOLT", "TF", "CH2"):
    for horizon in ("96", "192"):
        sub(f"    SAITS & \ph{{SRC_{tag_backbone}_SAITS_{horizon}_ETTH1}}",
            f"    Fixed SAITS & \ph{{SRC_{tag_backbone}_SAITS_{horizon}_ETTH1}}",
            tag=f"per-source label {tag_backbone} h{horizon}")

# ----------------------------------------- the reconstruction comparison roster

sub(r"""  \caption{Reconstruction quality against realised forecasting utility, over the four catalog
  interventions and SAITS on the held-out evaluation episodes.""",
    r"""  \caption{Reconstruction quality against realised forecasting utility, over the five catalog
  interventions on the held-out evaluation episodes.""",
    tag="reconstruction table caption: five interventions")

sub(r"""  \caption{\textbf{(a)}~Joint distribution of the within-episode reconstruction rank and the
  within-episode realised-utility rank over the four catalog interventions and SAITS,
  row-normalised over""",
    r"""  \caption{\textbf{(a)}~Joint distribution of the within-episode reconstruction rank and the
  within-episode realised-utility rank over the five catalog interventions,
  row-normalised over""",
    tag="figure 3 caption: five interventions")

sub(r"""Reconstruction error is defined only where a
method emits an explicit estimate of the hidden positions, which the four catalog interventions
and the published reconstruction baseline all do.""",
    r"""Reconstruction error is defined only where a
method emits an explicit estimate of the hidden positions, which all five catalog interventions
do.""",
    tag="reconstruction appendix: five interventions")



# ============================================== the appendix follows the roster

sub(r"""Both published baselines are given the same evidence \introact{} is given, which is the TRAIN
region under the registered missingness protocol, including the realised futures of those
windows. Neither sees a TEST window or a TEST label before its numbers are computed.""",
    r"""Every row is given the same evidence \introact{} is given, which is the TRAIN region under
the registered missingness protocol, including the realised futures of those windows. No row
sees a TEST window or a TEST label before its numbers are computed.""",
    tag="appendix B.2: the roster is no longer two published baselines")

sub(r"""\paragraph{SAITS.} One imputer per source, trained on that source's TRAIN bank windows after
the missingness protocol has been injected, so the training distribution is the one the
evaluation produces.""",
    r"""\paragraph{The trained imputer.} One imputer per source, trained on that source's TRAIN bank
windows after the missingness protocol has been injected, so the training distribution is the
one the evaluation produces. Two models are fitted per source. The deployment model reads every
bank parent and repairs every evaluation request, and it is what the \textsc{Fixed SAITS} row
and the catalog action both call at serving time. The bank records come from a cross-fitted
pair: the parents of the source are split in two by origin time, each half trains a model, and
that model repairs only the windows of the other half. Without that split the utility stored
for this action would be the utility of repairing a window the model had already seen, and the
selector would learn to execute it more often than the evidence supports.""",
    tag="appendix B.2: the imputer is fitted twice and only one of them writes the bank")

sub(r"""Fourth, the neighbourhood size and the
penalty strength are read off one bank. Appendix~\ref{app:selstability} measures how far that
choice travels, and the pair a subsample selects is usually a different one, so the reported
configuration should be read as one admissible point rather than as the only one the rule
would ever pick.""",
    r"""Fourth, the neighbourhood size and the
penalty strength are chosen on one bank. Appendix~\ref{app:selstability} repeats the whole
selection on subsamples of that bank and reports both how often the same pair returns and what
the pairs a subsample picks produce on the evaluation block.""",
    tag="appendix A.1: the stability assumption points at what is measured")



# ============================================================== a style pass

for old, new, tag in [
    ("""One line of work reconstructs the unavailable values, and what it
optimises is how closely they come back rather than what the forecast does with them. Another
trains an architecture that tolerates missingness, which a frozen forecaster rules out.""",
     """One line of work reconstructs the unavailable values and is scored on how closely they come
back, which leaves open what the forecast then does with them. Another trains an architecture
that tolerates missingness, and a frozen forecaster rules that out.""",
     "style: the abstract states the two lines without a pivot"),

    ("""Imputation stays open,
and what it optimises is the recovery of the hidden values rather than the effect they have on
the forecast.""",
     """Imputation stays open, and it
optimises the recovery of the hidden values. Whether that recovery helps the forecast is a
separate question.""",
     "style: the introduction says the same in two sentences"),

    (r"""The best action
changes with the request and with the backbone (\S\ref{sec:exp-exists}), so evidence has to be
retrieved locally rather than averaged over a corpus.""",
     r"""The best action
changes with the request and with the backbone (\S\ref{sec:exp-exists}), so the evidence a
decision rests on has to be local.""",
     "style: local evidence without a pivot"),

    ("""where whole variables are absent at inference rather than
positions inside the context.""",
     """where whole variables are absent at inference and not
positions inside the context.""",
     "style: variable subset forecasting"),

    ("""That is a call budget rather than a claim about what is knowable: a""",
     """That is a call budget and not a claim about what is knowable: a""",
     "style: the call budget"),

    ("""grid rather than read off a sampling distribution. The threshold of zero is not tuned either.""",
     """grid and is not derived from a sampling distribution. The threshold of zero is not tuned
either.""",
     "style: the penalty strength is searched"),

    ("""conditional harmful rate stays at or below a cap. The cap is read off the bank: it is the""",
     """conditional harmful rate stays at or below a cap. The cap comes from the bank itself: it is
the""",
     "style: where the cap comes from"),

    ("""  rows of this table, so it says how often a method wins rather than how large its average is.""",
     """  rows of this table, so it says how often a method wins and not how large its average is.""",
     "style: the rank caption"),
]:
    sub(old, new, tag=tag)


print("APPLIED:")
for item in APPLIED:
    print("  +", item)
DST.write_text(TEXT, encoding="utf-8")
print(f"\nwrote {DST.name}, {len(TEXT)} characters, "
      f"{TEXT.count('ph{')} placeholders")
