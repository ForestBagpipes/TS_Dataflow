# -*- coding: utf-8 -*-
"""把 v4.4 附录重排为 v4.4-r2 的 A-M 结构（任务书 §29）。

只做结构与措辞重组，不新增结果数字（唯一例外：Development Negative Results 里
引用实验线已审核的 TRAIN-eval 规范 CSV 数值，并显式标注其不可与主表比较）。
"""
import io
import re
import sys

PATH = r'F:\work\Time-research\work2\latex\introact_ts_iclr27_v44.tex'

src = io.open(PATH, encoding='utf-8').read()

# ------------------------------------------------------------------ 切分
marker = '\n\\appendix\n'
i = src.index(marker)
head = src[:i + 1]
app = src[i + 1:]

lines = app.split('\n')
first_sec = next(k for k, l in enumerate(lines)
                 if l.startswith('\\section{Protocol Details}'))
prefix = '\n'.join(lines[:first_sec])
body = '\n'.join(lines[first_sec:])

parts = re.split(r'(?m)^\\section\{(?!\*)(.*?)\}\s*$', body)
sec, order = {}, []
for k in range(1, len(parts), 2):
    sec[parts[k]] = parts[k + 1]
    order.append(parts[k])

prot = sec['Protocol Details']
sp = re.split(r'(?m)^\\subsection\{(.*?)\}\s*$', prot)
sub, sub_order = {}, []
for k in range(1, len(sp), 2):
    sub[sp[k]] = sp[k + 1]
    sub_order.append(sp[k])

need = ['Splits, Purging, and Replay-Bank Construction',
        'Scope of Validity of the Replay Bank',
        'Governance Action Catalog',
        'Observable Task-State Features',
        'Missingness Patterns']
for n in need:
    assert n in sub, 'missing subsection: ' + n
for n in ['Full Per-Source Results', 'Full Missing-Severity Tables', 'Per-Pattern Results',
          'Reconstruction versus Utility: Full Paired Table', 'Governance Diagnostics Figure',
          'Robustness Figure', 'Replay Size', '$K$ and $\\beta$ Sensitivity',
          'Frozen-Model Call Accounting',
          'Negative Result from the Preceding Development Cycle', 'Complete Input Contract',
          'Finance Case Study', 'Ten Mask Seeds', 'Additional Horizons',
          'Reproducibility Details']:
    assert n in sec, 'missing section: ' + n


def fix(t):
    """在旧块内部做必要的措辞修正（selector 口径变化）。

    只用单行、无换行的简单替换，避免因为换行位置不匹配而静默失效。
    最关键的是把指向已删除 label 的引用改掉，否则编译会出现 undefined reference。
    """
    pairs = [
        ('\\S\\ref{sec:method-gate}', '\\S\\ref{sec:method-scoring}'),
        ('\\S\\ref{sec:exp-efficiency}', '\\S\\ref{sec:exp-main}'),
        ('\\S\\ref{sec:exp-recutility}', '\\S\\ref{sec:exp-opportunity}'),
        ('\\S\\ref{sec:exp-governance}', '\\S\\ref{sec:exp-opportunity}'),
        ('\\ref{tab:governance}', '\\ref{tab:opportunity}'),
        ('\\ref{tab:efficiency}', '\\ref{tab:app-efficiency}'),
        ('$K$, $\\beta$, baseline hyperparameters', 'selector and baseline hyperparameters'),
        ('$K$, $\\beta$, and any legal baseline hyperparameter',
         'the selector hyperparameters and any legal baseline hyperparameter'),
        ('$K$ and $\\beta$ sensitivity', 'selector hyperparameter sensitivity'),
        ('conservative gate', 'lower-confidence gate'),
    ]
    for a, b in pairs:
        t = t.replace(a, b)
    return t


# ------------------------------------------------------------------ 新附录导航表
MAP = r'''\section*{Appendix map}
\label{app:map}
Table~\ref{tab:app-map} lists what each appendix section contains, so that a reader looking
for a specific piece of evidence does not have to scan the whole appendix. Sections~A--D fix
the protocol and the method details, E--I report the evidence behind the main-text tables,
J records what was tried and rejected, and K--M cover the boundary regimes.

\begin{table}[h]
  \caption{Appendix map. Sections are lettered in order of appearance; this table is
  unnumbered and does not consume a section letter.}
  \label{tab:app-map}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lll}
    \toprule
    Section & Contents & Question it answers \\
    \midrule
    A. Scope and assumptions & replay-bank scope, closed catalog, determinism & what is out of scope, and which claims are therefore not made? \\
    B. Full method details & action catalog, observable state, relation to OPE and selective prediction & what exactly is the method, and how is it positioned? \\
    C. Replay construction & splits and purging, bank construction, bank size & how was the replay bank built, and how much of it is needed? \\
    D. Dataset and missingness protocol & the four frozen patterns and the mask derivation rule & what missingness is being simulated, and how is it made deterministic? \\
    E. Full main results & per-source tables, reconstruction-vs-utility, governance diagnostics, opportunity strata, extended comparison & does the aggregate hold source by source and stratum by stratum? \\
    F. Robustness breakdown & $10/30/50\%$ tables, per-pattern results, severity trend & does the frozen policy degrade slower than the baselines? \\
    G. Historical support results & every method re-fitted at $25/50/100\%$ support & how much history does each method need? \\
    H. Ablation details & full outcome vector and ordering stability & which component carries the gain? \\
    I. Runtime and failure audit & latency, call counts, failures, timeouts, cold start & what does a request actually cost? \\
    J. Development negative results & local gain averaging with lower-confidence gating, gain regression, the sealed v4.4 TRAIN-eval batch & what was tried and rejected, and why? \\
    K. Complete-input contract & required behaviour by input regime & what happens when nothing is missing? \\
    L. Financial case study & finance parents, QLIKE & what happens outside the benchmark sources? \\
    M. Additional seeds and sensitivity & mask-seed stability, extra horizons, record schema & is the conclusion an artefact of one mask, or of the chosen horizons? \\
    \bottomrule
  \end{tabular}}
\end{table}
'''

# ------------------------------------------------------------------ 新增内容
SEC_A = r'''
\section{Scope and Assumptions}
\label{app:scope}
This section states what the replay bank is, what it is not, and which claims the paper
therefore does and does not make.

The bank is a discrete grid (four patterns $\times$ three severities $\times$ registered
sources), not a continuous model of missingness. If a request falls outside that grid --- a
different missingness mechanism, a different missing-rate regime, or an unrepresented source
family --- the scorer still returns a ranking, but the retrieved historical losses need not
transfer. We therefore read \S\ref{sec:exp-robust} as a within-grid check rather than as
out-of-grid generalisation, and the finance case study (Appendix~\ref{app:finance}) is the
only contact with a non-synthetic gap in this paper.

Three further assumptions are worth stating explicitly. First, the action catalog is closed and
given: we do not search for new interventions, and a wider catalog would change every number
in this paper without changing the decision problem. Second, the deployment missingness
mechanism is assumed to be the one that the replay injects; a request produced by a different
mechanism is handled by the same scorer but is outside the scope of the reported results.
Third, the frozen forecaster is assumed deterministic and revision-pinned: every replay record
is tied to the exact model revision that produced it, and a model update invalidates the bank
rather than silently degrading it.
'''

SEC_B_HEAD = r'''
\section{Full Method Details}
\label{app:method-details}
This section expands \S\ref{sec:method}: the closed action catalog, the observable state used
by the scorer, and the relation of the decision layer to off-policy evaluation and selective
prediction. The learner that turns replay records into a ranking is frozen on the TRAIN gate
and reported in \S\ref{sec:exp-main}; its implementation is not restated here because it is
selected by the protocol rather than fixed by the paper's formulation.
'''

OPE = r'''
\subsection{Relation to Off-Policy Evaluation and Selective Prediction}
\label{app:ope-positioning}
Our decision layer is formally close to conservative policy selection in contextual
bandits~\citep{abbasiyadkori2011improved,lattimore2020bandit} and to off-policy
evaluation~\citep{strehl2010learning,dudik2011doubly,swaminathan2015counterfactual,
jiang2016doubly,thomas2016data}, but three differences matter here. First, an arm's value is
not a designed reward but the realised loss of a frozen, non-differentiable forecaster, so
there is no reward model to fit and no simulator to query: the only legal supervision is a
replayed historical window, tied to the exact model revision that produced it. Second, the
untouched input is one of the arms rather than a fallback, so a wrong decision is asymmetric
and directly measurable, which is why we report harmful loss and action-opportunity strata
rather than regret alone. Third, the exploration budget is zero: no action is ever executed at
deployment in order to learn, so the bank is a fixed historical artefact and the method has no
online update.

Selective prediction and learning to defer~\citep{chow1970optimum,vovk2005algorithmic,
geifman2017selective,madras2018predict,mozannar2020consistent} are the closest relatives, but
they decide whether to \emph{predict} or to hand the case to a human or a second model. We
decide whether to \emph{modify the input} of one fixed predictor, and our abstention returns
that predictor's own reference forecast. Work on sequential evidence acquisition and decision
value~\citep{he2024dime,kang2020forecastwithforecasts} formalises when information is worth
its cost; we make no information-theoretic optimality claim and report the full cost
accounting separately (Appendix~\ref{app:calls}).
'''

SEC_E_TAIL = r'''
\subsection{Action-Opportunity Strata}
\label{app:opportunity}
The strata used in \S\ref{sec:exp-opportunity} are defined by thresholds on the oracle
opportunity $\Delta_i = L_{\textsc{Keep},i} - L_i^{\star}$ of \eqref{eq:opportunity}. The
thresholds are fitted on the gate split only and then applied unchanged to the evaluation
episodes, so no evaluation episode participates in choosing them. Table~\ref{tab:app-opp-sizes}
records the realised stratum sizes and the opportunity distribution, and
Table~\ref{tab:app-opp-sens} repeats the stratum-level MASE under alternative boundaries, so
that a reader can see how much of the effect depends on where the boundary was drawn.

\begin{table}[h]
  \caption{Action-opportunity strata on the evaluation episodes. Boundaries are the TRAIN-gate
  thresholds, applied unchanged. Counts are of legal parents, not of mask variants.}
  \label{tab:app-opp-sizes}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lcccc}
    \toprule
    Stratum & Parents & Share of episodes & Median $\Delta_i$ & 90th pct.\ $\Delta_i$ \\
    \midrule
    No-op             & \ph{STRATUM_NOOP_N}  & \ph{STRATUM_NOOP_SHARE}  & \ph{STRATUM_NOOP_MED}  & \ph{STRATUM_NOOP_P90} \\
    Low opportunity   & \ph{STRATUM_LOW_N}   & \ph{STRATUM_LOW_SHARE}   & \ph{STRATUM_LOW_MED}   & \ph{STRATUM_LOW_P90} \\
    High opportunity  & \ph{STRATUM_HIGH_N}  & \ph{STRATUM_HIGH_SHARE}  & \ph{STRATUM_HIGH_MED}  & \ph{STRATUM_HIGH_P90} \\
    \bottomrule
  \end{tabular}}
\end{table}

\begin{table}[h]
  \caption{Stratum-boundary sensitivity. The no-op tolerance and the low/high boundary are
  shifted by the indicated factor of the TRAIN-gate threshold; every other setting is
  unchanged. MASE is source-macro averaged within the resulting strata.}
  \label{tab:app-opp-sens}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lcccc}
    \toprule
    Boundary factor & No-op MASE $\downarrow$ & Low MASE $\downarrow$ & High MASE $\downarrow$ & Overall MASE $\downarrow$ \\
    \midrule
    $\times 0.5$ & \ph{OPPSENS_HALF_NOOP}  & \ph{OPPSENS_HALF_LOW}  & \ph{OPPSENS_HALF_HIGH}  & \ph{OPPSENS_HALF_OVR} \\
    $\times 1.0$ & \ph{OPPSENS_ONE_NOOP}   & \ph{OPPSENS_ONE_LOW}   & \ph{OPPSENS_ONE_HIGH}   & \ph{OPPSENS_ONE_OVR} \\
    $\times 2.0$ & \ph{OPPSENS_TWO_NOOP}   & \ph{OPPSENS_TWO_LOW}   & \ph{OPPSENS_TWO_HIGH}   & \ph{OPPSENS_TWO_OVR} \\
    \bottomrule
  \end{tabular}}
\end{table}

\subsection{Extended Comparison}
\label{app:extended}
VIDA~\citep{liang2025vida} is a closely related variable-subset-forecasting framework that
reframes the problem as cross-domain knowledge transfer. It is not part of the five core
baselines: the core set is fixed at five published methods before any result is seen, and
VIDA's adaptation procedure targets a training regime that differs from our frozen-backbone
contract. We therefore report it as an extended comparison rather than substituting it for a
core baseline. Table~\ref{tab:app-vida} gives the comparison on the main protocol.

If a core baseline turns out not to admit a legal adaptation to our protocol, we report that
to the reader instead of replacing it silently, and any change to the core set is an explicit
protocol revision rather than an editorial one.

\begin{table}[h]
  \caption{Extended comparison on the main protocol ($10\%$ severity, source-macro MASE,
  lower is better). VIDA is reported for completeness and is excluded from the core average
  ranks of Table~\ref{tab:main}.}
  \label{tab:app-vida}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
  \begin{tabular}{lccccc}
    \toprule
    Method & Bolt $\downarrow$ & TimesFM $\downarrow$ & Chronos-2 $\downarrow$ & Overall $\downarrow$ & Rank $\downarrow$ \\
    \midrule
    VIDA           & \ph{VIDA_BOLT} & \ph{VIDA_TF} & \ph{VIDA_CH2} & \ph{VIDA_OVR} & \ph{VIDA_RANK} \\
    \introact{}    & \ph{OURS_BOLT} & \ph{OURS_TF} & \ph{OURS_CH2} & \ph{OURS_OVR} & \ph{OURS_RANK} \\
    \bottomrule
  \end{tabular}
\end{table}
'''

SEC_G = r'''
\section{Historical Support Results}
\label{app:support-details}
This section supports \S\ref{sec:exp-support}. Every method is re-fitted from scratch under
$25\%$, $50\%$, and $100\%$ of the replay-fit portion of TRAIN, using the identical split rule
and purge of Appendix~\ref{app:splits}. Table~\ref{tab:app-support-full} reports all four
metrics at each support level, and Table~\ref{tab:app-support-cost} separates the one-off
offline fitting cost from the per-request online cost at each level.

The bank-size check in Appendix~\ref{app:replaysize} is the corresponding internal ablation: it
subsamples the replay bank while holding the baseline training set fixed, whereas this section
restricts the available history for every method at the same time. The two are not
interchangeable, and a disagreement between them is informative rather than contradictory.

\begin{table}[h]
  \caption{Historical support efficiency, all four metrics, source-macro averaged. Every
  method is re-fitted under the same restriction. Lower is better in every metric column.}
  \label{tab:app-support-full}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{llcccc}
    \toprule
    Method & Support & MASE $\downarrow$ & MAE $\downarrow$ & RMSE $\downarrow$ & MSE $\downarrow$ \\
    \midrule
    TOI                & 25\% / 50\% / 100\% & \ph{TOI_S25_MASE} & \ph{TOI_S25_MAE} & \ph{TOI_S25_RMSE} & \ph{TOI_S25_MSE} \\
    TOI-VSF            & 25\% / 50\% / 100\% & \ph{TOIVSF_S25_MASE} & \ph{TOIVSF_S25_MAE} & \ph{TOIVSF_S25_RMSE} & \ph{TOIVSF_S25_MSE} \\
    GIMCC              & 25\% / 50\% / 100\% & \ph{GIMCC_S25_MASE} & \ph{GIMCC_S25_MAE} & \ph{GIMCC_S25_RMSE} & \ph{GIMCC_S25_MSE} \\
    SRDI               & 25\% / 50\% / 100\% & \ph{SRDI_S25_MASE} & \ph{SRDI_S25_MAE} & \ph{SRDI_S25_RMSE} & \ph{SRDI_S25_MSE} \\
    ChannelTokenFormer & 25\% / 50\% / 100\% & \ph{CTF_S25_MASE} & \ph{CTF_S25_MAE} & \ph{CTF_S25_RMSE} & \ph{CTF_S25_MSE} \\
    \introact{}        & 25\% / 50\% / 100\% & \ph{OURS_S25_MASE} & \ph{OURS_S25_MAE} & \ph{OURS_S25_RMSE} & \ph{OURS_S25_MSE} \\
    \bottomrule
  \end{tabular}}
\end{table}

\begin{table}[h]
  \caption{Offline and online cost by support level. Offline cost is the one-off fitting cost;
  online cost is per request and excludes cold start. The two are never summed into a single
  number, because they are paid on different schedules.}
  \label{tab:app-support-cost}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lcccccc}
    \toprule
    Method & Offline 25\% & Offline 50\% & Offline 100\% & Online 25\% & Online 50\% & Online 100\% \\
    \midrule
    TOI                & \ph{TOI_OFF25} & \ph{TOI_OFF50} & \ph{TOI_OFF100} & \ph{TOI_ON25} & \ph{TOI_ON50} & \ph{TOI_ON100} \\
    TOI-VSF            & \ph{TOIVSF_OFF25} & \ph{TOIVSF_OFF50} & \ph{TOIVSF_OFF100} & \ph{TOIVSF_ON25} & \ph{TOIVSF_ON50} & \ph{TOIVSF_ON100} \\
    GIMCC              & \ph{GIMCC_OFF25} & \ph{GIMCC_OFF50} & \ph{GIMCC_OFF100} & \ph{GIMCC_ON25} & \ph{GIMCC_ON50} & \ph{GIMCC_ON100} \\
    SRDI               & \ph{SRDI_OFF25} & \ph{SRDI_OFF50} & \ph{SRDI_OFF100} & \ph{SRDI_ON25} & \ph{SRDI_ON50} & \ph{SRDI_ON100} \\
    ChannelTokenFormer & \ph{CTF_OFF25} & \ph{CTF_OFF50} & \ph{CTF_OFF100} & \ph{CTF_ON25} & \ph{CTF_ON50} & \ph{CTF_ON100} \\
    \introact{}        & \ph{OURS_OFF25} & \ph{OURS_OFF50} & \ph{OURS_OFF100} & \ph{OURS_ON25} & \ph{OURS_ON50} & \ph{OURS_ON100} \\
    \bottomrule
  \end{tabular}}
\end{table}
'''

SEC_H = r'''
\section{Ablation Details}
\label{app:ablation-details}
This section supports \S\ref{sec:exp-ablation}. Table~\ref{tab:app-ablation-full} reports the
full outcome vector for the six variants, and Table~\ref{tab:app-ablation-stab} repeats the
ablation under a different deterministic ordering of the replay records, so that a reader can
see whether a variant's position is an artefact of the order in which records were consumed.
The variant definitions follow \S\ref{sec:exp-ablation} exactly.

\begin{table}[h]
  \caption{Ablation, full outcome vector. Harmful loss is measured relative to
  \textsc{Native Keep} and is reported both unconditionally and conditional on an intervention
  having been executed. Calls is the mean number of frozen-model forecasts per request.}
  \label{tab:app-ablation-full}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
\resizebox{\textwidth}{!}{\begin{tabular}{lccccccc}
    \toprule
    Variant & MASE $\downarrow$ & MAE $\downarrow$ & RMSE $\downarrow$ & MSE $\downarrow$ & Harmful loss $\downarrow$ & Conditional HIR $\downarrow$ & Calls $\downarrow$ \\
    \midrule
    Full \introact{}          & \ph{AF_FULL_MASE} & \ph{AF_FULL_MAE} & \ph{AF_FULL_RMSE} & \ph{AF_FULL_MSE} & \ph{AF_FULL_HL} & \ph{AF_FULL_CHIR} & \ph{AF_FULL_CALLS} \\
    A1 Gain regression        & \ph{AF_A1_MASE}   & \ph{AF_A1_MAE}   & \ph{AF_A1_RMSE}   & \ph{AF_A1_MSE}   & \ph{AF_A1_HL}   & \ph{AF_A1_CHIR}   & \ph{AF_A1_CALLS} \\
    A2 Unweighted ranking     & \ph{AF_A2_MASE}   & \ph{AF_A2_MAE}   & \ph{AF_A2_RMSE}   & \ph{AF_A2_MSE}   & \ph{AF_A2_HL}   & \ph{AF_A2_CHIR}   & \ph{AF_A2_CALLS} \\
    A3 w/o intervention state & \ph{AF_A3_MASE}   & \ph{AF_A3_MAE}   & \ph{AF_A3_RMSE}   & \ph{AF_A3_MSE}   & \ph{AF_A3_HL}   & \ph{AF_A3_CHIR}   & \ph{AF_A3_CALLS} \\
    A4 w/o context state      & \ph{AF_A4_MASE}   & \ph{AF_A4_MAE}   & \ph{AF_A4_RMSE}   & \ph{AF_A4_MSE}   & \ph{AF_A4_HL}   & \ph{AF_A4_CHIR}   & \ph{AF_A4_CALLS} \\
    A5 Forced intervention    & \ph{AF_A5_MASE}   & \ph{AF_A5_MAE}   & \ph{AF_A5_RMSE}   & \ph{AF_A5_MSE}   & \ph{AF_A5_HL}   & \ph{AF_A5_CHIR}   & \ph{AF_A5_CALLS} \\
    \bottomrule
  \end{tabular}}
\end{table}

\begin{table}[h]
  \caption{Ordering stability of the ablation. The whole ablation is repeated after a
  deterministic reshuffle of the replay records; the column reports the Spearman correlation
  between the two rankings of the six variants, per backbone. A high value means the variant
  ordering is not an artefact of record order.}
  \label{tab:app-ablation-stab}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
  \begin{tabular}{lcc}
    \toprule
    Backbone & Spearman $\rho$ between orderings $\uparrow$ & Rank of Full variant \\
    \midrule
    Bolt      & \ph{ABL_STAB_BOLT} & \ph{ABL_RANKFULL_BOLT} \\
    TimesFM   & \ph{ABL_STAB_TF}   & \ph{ABL_RANKFULL_TF} \\
    Chronos-2 & \ph{ABL_STAB_CH2}  & \ph{ABL_RANKFULL_CH2} \\
    \bottomrule
  \end{tabular}
\end{table}
'''

SEC_J_HEAD = r'''
\section{Development Negative Results}
\label{app:development}
This section records what was tried in the development of this line of work and rejected, and
why. It exists because the final formulation is easier to read against the alternatives it
replaced, and because omitting it would misrepresent how the method was reached. Nothing in
this section is an independent confirmation of any method, and no number here is comparable
with any table in the main text.
'''

TRAIN_EVAL = r'''
\subsection{The Sealed v4.4 TRAIN-Eval Batch}
\label{app:train-eval}
The preceding v4.4 cycle was run to completion on the TRAIN-only splits with the confirmation
set left sealed, in order to decide whether local gain averaging with a lower-confidence gate
should be promoted to the main experiment. It was not promoted. We report the batch because
the decision it motivated is part of the final method's justification.

Table~\ref{tab:app-train-eval} gives the source-macro MASE of the frozen v4.4 configuration and
of its own ablations, on the two development backbones. Four observations are load-bearing.
\textbf{(i)}~Counterfactual replay does carry downstream decision signal: the full
configuration is below \textsc{Native Keep} on both backbones. \textbf{(ii)}~The
lower-confidence gate lowers the harmful-intervention rate but pays for it in average accuracy:
removing it (\textsc{A4}) improves MASE on both backbones, so the gate is a governance
trade-off rather than an accuracy gain. \textbf{(iii)}~The local-matching component does not
carry independent evidence: the parametric gain regressors are at least as good as, and
usually better than, the full configuration. \textbf{(iv)}~Gain-estimation accuracy and action
ordering are not the same objective, which is why the final formulation optimises the ordering
directly rather than the point-wise error of a gain vector.

The batch is development evidence on TRAIN-only splits with the confirmation set unread. It is
not a promotion, it is not independent confirmation, and its numbers are not comparable with
Tables~\ref{tab:main}--\ref{tab:ablation}.

\begin{table}[h]
  \caption{Sealed v4.4 TRAIN-eval batch, retained as development evidence. Values are
  source-macro MASE from the development protocol; the confirmation set was not read. HIR is
  the harmful-intervention rate relative to \textsc{Native Keep}. These numbers belong to a
  different configuration and protocol and are \emph{not} comparable with any table in the main
  text.}
  \label{tab:app-train-eval}
  \centering
  \small
  \setlength{\tabcolsep}{4pt}
  \begin{tabular}{llcc}
    \toprule
    Backbone & Configuration & MASE $\downarrow$ & HIR $\downarrow$ \\
    \midrule
    Bolt     & Native KEEP            & 1.179735 & 0.000000 \\
    Bolt     & Best Fixed             & 1.179735 & 0.000000 \\
    Bolt     & R2-CART                & 1.178209 & 0.048913 \\
    Bolt     & Full v4.4              & 1.165800 & 0.084239 \\
    Bolt     & A4 (no gate)           & 1.142909 & 0.274457 \\
    Bolt     & A5 gain regression (ridge) & 1.140129 & 0.290761 \\
    Bolt     & A5 gain regression (CART)  & 1.153831 & 0.296196 \\
    \midrule
    TimesFM  & Native KEEP            & 1.242208 & 0.000000 \\
    TimesFM  & Best Fixed             & 1.103034 & 0.282609 \\
    TimesFM  & R2-CART                & 1.146845 & 0.078804 \\
    TimesFM  & Full v4.4              & 1.101261 & 0.187500 \\
    TimesFM  & A4 (no gate)           & 1.085381 & 0.339674 \\
    TimesFM  & A5 gain regression (ridge) & 1.088242 & 0.290761 \\
    TimesFM  & A5 gain regression (CART)  & 1.080967 & 0.334239 \\
    \bottomrule
  \end{tabular}
\end{table}
'''

# ------------------------------------------------------------------ 组装
out = []
out.append(head.rstrip('\n'))
out.append('')
out.append('\\appendix')
out.append('\\newpage')
out.append('')
out.append(MAP.rstrip('\n'))
out.append(SEC_A.rstrip('\n'))

out.append(SEC_B_HEAD.rstrip('\n'))
out.append('\\subsection{Governance Action Catalog}' + sub['Governance Action Catalog'].rstrip('\n'))
out.append('\\subsection{Observable Task-State Features}' + sub['Observable Task-State Features'].rstrip('\n'))
out.append(OPE.rstrip('\n'))

out.append(r'''
\section{Replay Construction}
\label{app:replay}
This section records how the replay bank is built and how much of it is needed. Nothing here
is a result; it is the construction that the result tables are read against.'''.lstrip('\n'))
out.append('\\subsection{Splits, Purging, and Replay-Bank Construction}'
           + fix(sub['Splits, Purging, and Replay-Bank Construction']).rstrip('\n'))
out.append('\\subsection{Replay Bank Size}'
           + fix(sec['Replay Size']).rstrip('\n'))

out.append(r'''
\section{Dataset and Missingness Protocol}
\label{app:data-protocol}
The missingness mechanism is frozen before any method is run, and every mask is derived
deterministically from a key that identifies the parent and the pattern. This section fixes
the four patterns and the derivation rule.'''.lstrip('\n'))
out.append('\\subsection{Missingness Patterns}' + sub['Missingness Patterns'].rstrip('\n'))

out.append(r'''
\section{Full Main Results}
\label{app:main-full}
This section expands \S\ref{sec:exp-main} and \S\ref{sec:exp-opportunity}: per-source tables,
the paired reconstruction-versus-utility table, the governance diagnostics figure, the
opportunity strata, and the extended comparison.'''.lstrip('\n'))
out.append('\\subsection{Per-Source Results}' + fix(sec['Full Per-Source Results']).rstrip('\n'))
out.append('\\subsection{Reconstruction versus Forecasting Utility}'
           + fix(sec['Reconstruction versus Utility: Full Paired Table']).rstrip('\n'))
out.append('\\subsection{Governance Diagnostics}'
           + fix(sec['Governance Diagnostics Figure']).rstrip('\n'))
out.append(SEC_E_TAIL.rstrip('\n'))

out.append(r'''
\section{Robustness Breakdown}
\label{app:robustness}
This section expands \S\ref{sec:exp-robust}: the complete severity tables, the per-pattern
results, and the severity trend.'''.lstrip('\n'))
out.append('\\subsection{Severity Tables}' + fix(sec['Full Missing-Severity Tables']).rstrip('\n'))
out.append('\\subsection{Per-Pattern Results}' + fix(sec['Per-Pattern Results']).rstrip('\n'))
out.append('\\subsection{Robustness Trend Figure}' + fix(sec['Robustness Figure']).rstrip('\n'))

out.append(SEC_G.rstrip('\n'))
out.append(SEC_H.rstrip('\n'))

out.append(r'''
\section{Runtime and Failure Audit}
\label{app:calls}'''.lstrip('\n')
           + fix(sec['Frozen-Model Call Accounting']).split('\n', 1)[1].rstrip('\n'))

out.append(SEC_J_HEAD.rstrip('\n'))
out.append('\\subsection{Local Gain Averaging with Lower-Confidence Gating}'
           + fix(sec['Negative Result from the Preceding Development Cycle']).rstrip('\n'))
out.append('\\subsection{Sensitivity of the Selector Hyperparameters}'
           + fix(sec['$K$ and $\\beta$ Sensitivity']).rstrip('\n'))
out.append(TRAIN_EVAL.rstrip('\n'))

out.append(r'''
\section{Complete-Input Contract}'''.lstrip('\n')
           + sec['Complete Input Contract'].rstrip('\n'))
out.append(r'''
\section{Financial Case Study}'''.lstrip('\n')
           + sec['Finance Case Study'].rstrip('\n'))
out.append(r'''
\section{Additional Seeds and Sensitivity}
\label{app:seeds}'''.lstrip('\n')
           + sec['Ten Mask Seeds'].rstrip('\n')
           + '\n' + '\\subsection{Additional Horizons}' + sec['Additional Horizons'].rstrip('\n')
           + '\n' + '\\subsection{Reproducibility Details}' + sec['Reproducibility Details'].rstrip('\n'))

new = '\n\n'.join(out) + '\n'
io.open(PATH, 'w', encoding='utf-8', newline='\n').write(new)
print('OK  old lines=%d  new lines=%d' % (len(src.split('\n')), len(new.split('\n'))))
