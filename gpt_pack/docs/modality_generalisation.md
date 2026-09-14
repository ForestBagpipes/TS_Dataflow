# What is modality specific and what is not

Draft for the method chapter's generalisation section. The split is not a claim
that the framework transfers; it is a statement of which parts would have to be
rebuilt if it were carried to another modality, and which would not. A reader
who works on text data curation should be able to read the first list and
recognise machinery they could use, and read the second and know exactly what
they would have to supply.

## The modality independent core

Five things, none of which mentions a time series.

**Sandbox trial execution.** A candidate edit is executed on a copy and the
working corpus is untouched until a verdict is reached. What this requires of a
modality is only that an edit be reversible by not committing it, which is true
of any curation operation on stored data.

**Adjudication after execution rather than before.** The decision is made on the
edit's measured effect, not on a prediction of it. This requires that the effect
be measurable, which means a readout the modality supplies. It does not require
the readout to be a forecast error.

**A conjunction, not a weighted sum.** Acceptance requires a utility gain and a
structural bound and a risk bound, all three. The architectural claim is that
structural preservation must not be tradeable against utility gain, and theorem
2 says why: with a weighted sum, on any class of windows where a harmful action's
utility gain scales with its structural damage, no choice of weight removes those
actions from the acceptance set.

**Per family calibration of the structural bound.** One threshold per operator
family, each calibrated on its own score distribution at the same target risk.
This came out of a failure that is not specific to time series: a threshold
calibrated on operators that rewrite a handful of points was applied to an
operator that rewrites all of them, and the second could never pass. A text
pipeline has exactly this shape. Deduplication removes whole documents,
truncation removes spans, boilerplate stripping rewrites within a document, and
field completion adds. Asking one tolerance to govern all four would fail the
same way and for the same reason.

**The CMDP formulation.** State, action, cost, and a constraint the policy
cannot buy its way out of.

## The modality specific parts

Three, and each is an interface rather than a component.

**The operator set.** Seven here. Another modality supplies its own.

**The structural distortion measure.** Here it is trend, periodicity, spectrum,
memory, changepoints and tails, weighted differently for local and global
operators. A modality supplies whatever "the thing that must survive an edit"
means for it.

**The utility probe.** Here a pool of pretrained time series models and their
forecast and reconstruction error. A modality supplies whatever readout says
"the model finds this data easier to use than before".

## The correspondence, for text

| here | text curation |
|---|---|
| DESPIKE, remove isolated outliers | drop anomalous samples inside a document |
| IMPUTE, fill gaps | complete missing fields or truncated records |
| RESEGMENT, cut at a changepoint and keep one side | truncate to a span, split a concatenated document |
| DENOISE, smooth every point | strip boilerplate, normalise formatting, rewrite in place |
| QUARANTINE, set aside | route to manual review |
| the utility readout, forecast and reconstruction error | perplexity or loss change under a reference model |
| the structural measure, point wise and spectral fidelity | semantic preservation and format validity |
| the protected strata, rare but valid windows | rare but valid documents, low resource languages, minority dialects, specialist registers |
| the injected layer, windows with known defects | held out documents with known corruptions |

## The two failures that are the strongest argument for the generalisation

Both were found here and neither is about time series.

**A distortion measure can be blind to the operator it is meant to govern.** The
alignment step compared the original to the candidate over the span the crop
retained, and a crop rewrites nothing inside that span, so every crop scored
exactly zero distortion and the structural condition refused none of 2766
attempts. The text analogue is immediate: a semantic similarity score computed
over the surviving text after a truncation is near perfect by construction,
because the removed part is not in the comparison. Any curation system that
measures fidelity on what survives an operation will have this hole for every
operation that removes.

**Damage that removes data is not damage that corrupts data, and one metric
usually only sees the second.** Because a crop leaves the surviving span
correct, the distance to the reference did not move and the damage rate read
zero. Measured here, that made the reported damage rate five times better than
the corrected one. In text, dropping a document scores nothing on any per
document quality metric, because the document is gone.

Neither of these needed a time series to happen. They needed a curation
operation that removes, and a measurement that only looks at what is left.

## What a small text transfer would and would not show

If one is run, it should be scoped honestly. A few hundred documents with
injected corruptions, the same five core mechanisms, a text operator set and a
perplexity readout, reporting the damage rate and the protected mis edit rate.
That would show the machinery runs on another modality and that the two failure
modes above appear there too. It would not show the method is competitive with
text specific curation pipelines, and the text should not imply it does.


## Training dynamics diagnosis, the part that is already standard elsewhere

The section above argues from mechanism. This one argues from precedent: the
signal v3 turns to is the standard toolbox of LLM data curation, and what is new
here is where it sits rather than what it measures.

| the text side | what it measures | our operationalisation |
|---|---|---|
| forgetting events, Toneva et al. 2019 | how often a learned example is unlearned | flips from below to above a per window learning threshold across epochs |
| EL2N and GraNd, Paul et al. 2021 | error norm early in training as a difficulty proxy | the error at ten percent of the training run |
| dataset cartography, Swayamdipta et al. 2020 | confidence and variability place a sample in easy, hard or ambiguous | mean and cross seed variance of the per window loss |
| data pruning at scale, Sorscher et al. 2022 | which examples can be removed without loss | which windows should be left alone, the same question inverted |
| TracIn, Pruthi et al. 2020 | influence of a training example along the trajectory | complementary rather than the same; it needs gradients, these need only the loss |

**What is different here, and it is the whole claim.** Every one of those is an
offline scoring pass: train a model, read the trajectory, rank the corpus, prune
once. In an agent loop the trajectory becomes a state signal read while the
decision is being made, and the decision is not keep or drop but leave this
window alone or offer it to the repair operators. None of them was built to
answer that, because none of them has an operator to gate.

The second difference is the modality. All five are stated for classification
over discrete examples. The operationalisation here is regression over
overlapping windows, where an example is not a natural unit and a window's loss
has to be assembled from the training samples that cover it. That mapping is in
`docs/v3_triage_design.md` and it is a contribution of the transfer rather than
a detail of it.

**Why it should transfer back.** The failure driving v3 is that a static readout
prefers unfamiliar clean data: the utility gain on the synthetic probe layer is
sixteen times the gain on genuinely contaminated windows. The text analogue is
already known in another guise, that a language model's perplexity improves most
on templated low entropy text, so a pipeline scoring documents by perplexity
change will systematically prefer to rewrite the documents that least need it.
Any pipeline whose quality signal is a model's own readout has this problem, and
training dynamics is one of the few signals that does not, because it measures
the data's relationship with the learner rather than the learner's comfort with
the data.

## A caveat this section must carry

The trajectory signal is unproven here. It is a hypothesis with a pre registered
test and a stated failure threshold. If the test fails, this section reduces to
the correspondence table and the negative result. Writing it as established
before the probe returns would repeat the error that produced the five fold
damage advantage, which turned out to be a measurement blind spot.
