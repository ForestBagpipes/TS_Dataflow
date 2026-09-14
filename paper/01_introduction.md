# Introduction

## Background, and what it costs

Time series foundation models are pretrained on corpora assembled from many
sources, and those corpora carry defects. Sensors drop out, values are
duplicated by a faulty ingest, spikes arrive from transient faults, and
segments are spliced at a level that does not match. Removing these defects
before pretraining is what data curation is for.

The cost of getting it wrong is measurable and it is not symmetric. In our
experiments, a curation pipeline that repairs unconditionally raises the mean
squared error of a downstream forecaster trained on its output by a factor of
between two and eleven, from 7.56 to 25.20 in the single seed case and worse in
two of three seeds. The same pipeline, with an acceptance step added and
nothing else changed, returns to within a few percent of not curating at all.
The difference between the two is not which defects were found. It is whether
each edit was checked after the fact.

This asymmetry has a specific cause. Curation systems verify their edits by
asking whether a model does better on the result, and a model does better on
data that has been flattened as surely as on data that has been repaired. On
our corpus, edits that removed 82.3 percent of a window's variance were
rewarded with a utility gain of 25.81 on average, while edits that repaired
genuine contamination earned 0.54. Measured per unit of variance destroyed,
destroying signal in clean data pays seventeen times better than repairing a
defect. An objective that reads only model utility does not merely tolerate
this. It prefers it.

## Limitations of existing approaches

Existing work addresses parts of the problem and leaves the acceptance question
open.

**First**, established repair methods are effective at repairing and have no
mechanism for declining. We ran two of them, a speed constraint repair from
2015 and an iterative minimum repair from 2017, over our corpus and measured
where their proposed edits land. **More than half of what they propose falls on
data that should not be touched: 51.7 percent of the speed constraint method's
candidates land on a protected stratum**, where the window is already clean and
any edit increases error. On the windows that genuinely need repair the same
method is good, with 61.8 percent of its candidates beneficial and a harm rate
of 0.382.

Those two figures belong together. The first says these methods work. The
second says what they lack is not repair quality but the judgement of when to
leave data alone. The problem this paper addresses is the decision to
intervene, not the quality of the intervention.

Statistical outlier detection, which identifies defects from the data alone
without consulting any model, has the complementary limit. It works where a
defect leaves a local trace and fails where it does not. On our corpus a
duplicated segment is detected at 0.489 by a statistical profile, which is a
coin flip, and four standard outlier detectors could not separate contaminated
windows from clean ones at all, with contaminated lifts between 0.83 and 1.00.

**Second**, model based quality scoring ranks windows by how a model reacts to
them and curates the low scoring tail. This inherits the problem above. We
measure the behavioural signal from a frozen forecaster at a corpus AUROC of
0.468, with a bootstrap interval entirely below 0.5, meaning it is
systematically inverted rather than merely weak. The reason is that the signal
measures predictability rather than data quality, which we establish by a
controlled experiment rather than by inference: it decomposes into level
positioning uncertainty worth 0.203 and local shape unpredictability worth
0.141, and clean windows that are structurally unpredictable are ranked as more
suspicious than genuine contamination at an AUROC of 0.726.

**Third**, sequential curation systems that learn a repair policy fold
structural preservation into the reward as a weighted penalty. An edit that
damages structure is then still available whenever the utility gain outweighs
the penalty, so the safety property holds in expectation over training rather
than for any particular edit. Their own parameter studies show the cost of
raising that weight, since a penalty that restricts damage also restricts
repair.

## Why neither a rule nor a model suffices here

Gating an action before it takes effect is an established construction. It has
been proposed for code execution and driving agents, for mobile interface
automation, for locally deployed language models, for cross runtime action
certification and for tool call arguments, all within recent work. The closest
of these gives a language in which a safety rule is a trigger, a predicate and
an enforcement mechanism, and blocks any proposed action whose predicate
rejects it. That convergence is evidence the problem is real and that the shape
of the answer is agreed on.

The construction transfers to data curation. The predicate does not, and the
reason is the argument of this paper.

**A safety predicate cannot be written here.** In those settings unsafe is
expressible as a condition on the action itself. Do not delete outside this
directory. Do not exceed this speed. Do not let untrusted content set a
recipient. Whether an edit to a window is harmful is not a condition on the
edit. The same operator applied with the same parameters repairs one window and
destroys another, and which of the two occurred depends on what the window
contained. No rule over operators and parameters separates them.

**So the predicate must consult a model.** If harm cannot be read off the
action, it has to be read off the effect, and the only instrument that reports
on the effect is a model asked whether it does better on the result. That is
what every curation system does, ours included, and there is no alternative
instrument.

**And the model's opinion is anti correlated with harm over a region we can
characterise.** It rewards flattening as readily as repair, at seventeen times
the rate per unit of variance destroyed. The behavioural signal it yields
reaches a corpus AUROC of 0.468 with a bootstrap interval entirely below 0.5,
and the region where it inverts is not an edge case but precisely the clean
data that curation exists to protect.

**Therefore neither alone.** A declared rule cannot express the condition, and
the model that can express it is wrong where it matters most. The response is a
compound admission test, in which a condition that consults the model and a
condition that never does must both hold, and a calibration applied to that
compound rather than to either part.

## Technical challenges

**Challenge 1. The verification signal is the thing under suspicion.** The only
instrument that can say whether an edit helped a model is the model, and that
instrument is systematically wrong on precisely the data that must be
protected. Correcting it is not sufficient either. Removing the predictability
confound raises the corpus AUROC from 0.468 to 0.551, a paired improvement of
0.083 with a confidence interval of 0.060 to 0.108, and 0.551 is still too weak
to carry an acceptance decision.

**Challenge 2. The two available evidence sources fail together on the same
data.** A statistical profile assigns a defect to between 65 and 81 percent of
clean windows that are structurally unpredictable, and the behavioural signal
ranks those same windows above contaminated ones. Neither can act as a check on
the other where both are wrong in the same direction.

**Challenge 3. Correcting the signal trades one error for its opposite.**
Unpredictability arising from a displaced level and unpredictability arising
from the structure of the series are the same quantity to a frozen forecaster.
Removing that confound reduces the false alarm on clean unpredictable data from
an AUROC of 0.726 to 0.514, and simultaneously reduces detection of genuine
level displacement from 0.495 to 0.375. There is no operation on the signal
alone that removes both errors.

**Challenge 4. A threshold that is not calibrated states nothing.** The
structural preservation test needs a threshold, and a value chosen by hand
carries no statement about what it delivers. Three hand set values on our
corpus realise damage rates of 0.0200, 0.1025 and 0.1562, and none of them is
accompanied by any claim about the fourth corpus it might be applied to.

## Contributions

**We characterise what the model based verification signal measures.** It is
predictability, not data quality, established by a two by two design with unit
variance normalisation whose decisive pair holds local shape fixed at an AUROC
of 0.716 with p 1.4e-07. Two competing explanations are tested and refuted. The
characterisation replicates across four frozen backends, weakest at p 1.3e-04,
and survives removing the two generator forms whose structure resembles an
injected defect, leaving an AUROC of 0.715 at p 9.5e-13 over 105 windows.

**We move structural preservation from a term in an objective to a condition at
execution time.** Each proposed edit is applied to a sandbox copy, scored, and
committed only if it improves model utility and preserves structure and clears
a risk bound, with rollback otherwise. The layer is independent of what
proposes the edits, which we verify by placing it around two proposers that are
not ours: on a statistical rule it reduces damage from 0.0715 to 0.0016 while
retaining 70 percent of repair, and on an unconditional cleaner it moves the
net effect from harmful at -0.014 to beneficial at +0.044 without modifying the
cleaner. On one of them the gated result is better on damage than our own
complete system, 0.0016 against 0.0020, which is why the contribution is the
layer rather than the search.

**We calibrate the acceptance threshold with a finite sample guarantee.** Given
a target level, the procedure returns a threshold for which the expected
fraction of damaged windows is bounded, assuming only exchangeability. Under a
same pool split the bound holds at every reachable target, with a floor at
0.0088 imposed jointly by the action space and the threshold grid. We also
measure what happens when the assumption is violated, since that is the
deployment case: calibrating on one corpus and applying to an independently
sampled one overshoots by 20 to 50 percent relative.

**We report the cost of the layer as well as its benefit.** Of the edits it
vetoes, 26.3 percent would have improved the window. The condition that
consults the model is the less accurate of the two, misfiring on 29.7 percent
of what it blocks against 19.7 percent for the structural condition, which is a
fourth independent line of evidence that model utility cannot carry the
decision alone.
