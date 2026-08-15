# Related work

## Statistical detection of defects in series data

One line identifies defects from the data alone. Filters based on rolling
medians and robust dispersion flag isolated excursions, decomposition into
trend and season isolates residual anomalies, and density or distance based
outlier detectors treat each point or window as an object in a feature space.
These methods do not consult any model, which is their strength when the
question is whether something in the data is wrong, and their limit when the
defect leaves no local trace.

We measure that limit rather than assert it. On our corpus a statistical
profile separates duplicated segments from clean windows at 0.489, which is
chance. Four widely used general purpose outlier detectors fail to separate
contaminated windows from clean ones at all, with the ratio of contaminated to
clean flagging rates between 0.83 and 1.00. A detector that cannot distinguish
the positive class from the negative class on this data is not a usable
component of a curation decision.

## Model based data quality scoring

A second line scores each training example by how a model reacts to it and
curates the tail. Loss based selection, gradient influence, and forgetting
statistics all read a model's behaviour as evidence about the data. Applied to
time series, the natural instrument is a pretrained forecaster, and the natural
score is some function of its error and the stability of its internal states.

The assumption underneath is that a model finds bad data hard. We test that
assumption directly and it does not hold in the form required. The behavioural
signal we compute reaches a corpus AUROC of 0.468 with a bootstrap interval
entirely below 0.5, which means it ranks contaminated data as less suspicious
than protected data, systematically. The mechanism is that the signal responds
to predictability, and clean data can be unpredictable. Removing the
predictability component raises it to 0.551 and no further, so the limitation
is not a matter of better estimation.

## Sequential curation with a learned policy

A third line treats curation as sequential decision making. A policy selects
which quality issue to address and which operator to apply, and is trained
against a reward that combines an upstream cleaning term with a downstream task
term. Hierarchical variants separate the choice of issue from the choice of
operator, and dense shaping terms are added for temporal smoothness, for the
size of the modification, for the reduction in the targeted issue rate, and for
the gain on a lightweight surrogate of the downstream task.

This is the closest work to ours in what it does and the furthest in how it
guarantees anything, and the difference is worth being precise about.

**Structural preservation as a reward term against structural preservation as a
condition.** In that design, a smoothness term and a modification size term
enter the objective with weights. An edit that damages structure remains
available whenever the utility gain outweighs the weighted penalty, so the
safety property holds in expectation over the training distribution and not for
any individual edit. In ours the same quantity is a condition evaluated at
execution time on a sandbox copy, and no utility gain admits an edit that fails
it.

**The evidence for the difference runs in opposite directions.** Their own
parameter study reports that raising the modification constraint weight
increases error and degrades downstream performance, because a penalty that
restricts damage also restricts genuine repair. Our threshold sweep reports the
opposite shape for a hard condition: between 0.02 and 0.12 loosening the
threshold buys no repair at all, only damage, so in that range the condition is
free. A soft penalty cannot reach the same damage level as a veto without
paying repair for it, and the frontier that this predicts is measured directly
in E3.

**What is verified, and when.** Their verification signal is a model trained on
the downstream task, consulted during policy learning. Ours is a frozen
forecaster consulted per edit, and crucially it is not the only condition,
because we establish that it cannot be. Their reward has no term that does not
ultimately reference a model.

**What is not measured there.** That work reports cleaning quality and
downstream gain and does not report a protected stratum, so the question of
whether clean data was damaged does not appear. It also does not characterise
what its verification signal responds to, and its ablation without quality rate
signals shows the policy degrades sharply, which indicates dependence on
exactly the class of signal we measure as unreliable on clean unpredictable
data. Its stated future direction is to incorporate time series foundation
models for generalisation to unseen domains.

**Reproduction status.** The published implementation cannot be run as
released, because the module that loads data is absent from the repository and
is imported by all four core modules. The authors were contacted and replied
that it cannot be located and cannot be supplied. A timeboxed reconstruction is
reported in the appendix with its acceptance criterion fixed in advance.

## Distribution free uncertainty quantification

Split conformal prediction converts any score into a set with a coverage
guarantee under exchangeability. Conformal risk control extends this from
coverage to the expectation of any bounded loss that is monotone in a single
parameter, and Learn Then Test removes the monotonicity requirement at the cost
of a multiplicity correction over a fixed grid.

We use these as the calibration mechanism for an acceptance threshold rather
than for prediction sets. The loss is the fraction of windows a curation run
damages, which is bounded by construction, and the parameter is the structural
threshold. Two points of contact with the assumptions matter here and are
reported rather than assumed. Monotonicity is verified per run and the fallback
is used when it fails. Exchangeability is what the guarantee rests on, and we
measure the cost of violating it by calibrating on one corpus and applying to
an independently sampled one, which overshoots the target by 20 to 50 percent
relative.

## Calibrated gating of agent actions at execution time

A recent and fast moving line places a calibrated gate between a proposer and
its effects. One system scores each proposed mobile interface action with a
separate risk model and calibrates an execute or abstain threshold so that the
rate of harmful executed actions respects a stated budget. Another wraps a
locally deployed language model with an anytime valid selective risk bound that
holds per deployment rather than in aggregate. A third defines a runtime
neutral certificate for each action, recording what was authorised and on what
basis, with checkpoints from pre action admissibility to outcome closure. A
fourth calibrates per argument role rather than per call, on the argument that
a single budget over a whole tool call hides the fields where consequences
concentrate.

Taken together these establish that a calibrated gate at execution time is
worth building, arrived at independently in four different settings. We take
that as support for the premise rather than as competition, and our design is
the same shape: a proposer, a scored candidate, a threshold with a distribution
free guarantee, and an option to decline. Two specific points of contact are
worth recording. The certificate line and our governance trace serve the same
auditing purpose, and we verified that replay from our trace reproduces every
method to zero absolute error. The per role line and our per stratum reporting
share a refusal of the aggregate, reached from unrelated starting points.

**The premise differs, and that is the contribution.** These works assume the
risk signal is a reasonable proxy for harm, and what they calibrate is a signal
taken to be reliable. That assumption is sound in their settings: a harmful
interface action is harmful whatever a model believes, a verifiable reward is
verifiable, and a recipient field is dangerous no matter what a detector says.
In data curation it fails. The most natural verifier is whether a model does
better on the edited data, and a model does better on data that has been
flattened as surely as on data that has been repaired. We measure that signal
at a corpus AUROC of 0.468 with a bootstrap interval entirely below 0.5, and we
characterise the region where it inverts. Calibrating a signal that is anti
correlated with harm over a characterisable region delivers the budget and not
the safety, which is why our calibration is applied to a condition that never
consults the model.

**No experimental comparison is run against these four, deliberately.** Their
corpora are mobile interface traces, training rounds, cross runtime execution
records and tool call arguments. Their action spaces and their definitions of
harm do not overlap with injected defects in a series corpus and an edit that
damages a window. There is no shared platform, and constructing one would mean
inventing a benchmark whose numbers would measure the benchmark. The comparison
that does require numbers is against the sequential curation system above,
which shares both the data and the task.

## Runtime enforcement of safety conditions

Work on constrained decision making distinguishes systems that learn to satisfy
a constraint from systems that are prevented from violating it. The second
places a filter outside the policy that observes proposed actions and blocks
those that would violate a specification, so the safety property does not
depend on the policy having learned anything. Our acceptance layer is that
construction applied to data curation, with the specification instantiated as
structural preservation and the recovery mechanism as rollback to the sandbox
copy. The property we can state is non blocking, since the identity action is
admissible in every state, and the property we can only quantify is minimal
interference, measured at a 26.3 percent forgone benefit rate.
