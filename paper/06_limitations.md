# Limitations

Every entry carries the measurement that establishes it and the file it lives
in. Nothing here is a hedge without a number.

## On the method

**The predictability correction is partial and its cost is a symmetric error.**
Regressing a predictability proxy out of the behavioural signal raises corpus
AUROC from 0.468 to 0.551, a paired improvement of 0.083 with interval [0.060,
0.108]. It removes the false alarm on all four generator forms of clean
unpredictable data, from 0.705 to 0.760 down to 0.504 to 0.527, and it lowers
detection of level displacement from 0.495 to 0.375, of flatline from 0.576 to
0.463 and of duplication from 0.573 to 0.501. Both directions are one fact:
unpredictability from a displaced level and from the structure of the series are
the same quantity to this signal. Fully corrected the signal reaches 0.551,
which is not enough to carry an acceptance decision alone.
`docs/predictability_decorrelation.md`, `results/decorrelate.json`.

**Minimal interference is satisfied only partially.** Of 1154 replayable
vetoes, 304 would have improved the window, a forgone rate of 0.263. The
condition that consults the model misfires on 29.7 percent of what it blocks,
768 blocked and 228 helpful, and the structural condition on 19.7 percent, 386
blocked and 76 helpful. Reducing the first is future work.
`docs/shield_properties.md`, `results/shield_properties.json`.

**The structural distance weights are set by hand.** The invariant
specification module was not developed. The component weights inside the
structural distance are informed by the failure analysis in the experiments and
are not derived from a specification of what must be preserved. `docs/HANDOFF.md`.

**The reachable risk floor is 0.0088.** The most conservative threshold in the
grid, tau 0.005, already realises that damage rate on the reporting half, so
any target below it has no solution and the procedure returns the most
conservative threshold available. The floor is a joint property of the operator
set and the grid, not of the calibration. `docs/conformal_threshold.md`.

## The corpus dependence of calibration, and what it implies

Two of our limitations have one cause, and stating them together turns two
isolated defects into one understood property.

**Both calibrated quantities are relative to the corpus they were calibrated
on.** The behavioural risk is a peer calibrated z score, so the same window
placed among different neighbours receives a different value: the same staircase
generator scored a median of +0.535 in one corpus and -0.087 in another. The
conformal threshold is calibrated against an empirical risk curve, so a corpus
whose windows are harder to curate shifts that curve: calibrating on one corpus
and reporting on an independently sampled one held the guarantee at 2 of 9
target levels, with all seven violations underestimating and the two risk curves
offset by a consistent factor of 1.2 to 1.5 across the whole threshold grid,
worst absolute overshoot 0.0125. Under a same pool split the guarantee holds at
every reachable target, with one isolated violation at alpha 0.040 overshooting
by 0.0025 while both its neighbours hold.

**The common cause is that calibration reads the corpus composition.** Peer
calibration reads it through the neighbour set and conformal calibration reads
it through the risk curve. Neither quantity is a property of a window alone.

**The implicit assumption this makes explicit.** The method assumes curation is
performed on a corpus of stable composition, and a change of corpus requires
recalibration. That is a real operating condition and it is stated as one. Two
consequences follow and both are observed in this paper. No behavioural risk
value may be compared across corpora, which is why none is anywhere here. And
the guarantee degrades rather than collapses when the assumption is violated,
overshooting a small target by 20 to 50 percent relative rather than failing
outright, which bounds what a user loses by deploying on data from a different
source than the calibration set.

`docs/scope_and_comparability.md`, `docs/conformal_threshold.md`,
`results/conformal_crosscorpus.json`, `results/conformal_samepool_stage1.json`.

## On the evidence

**No positive downstream gain is demonstrated for conservative curation.**
Every effect for the statistical rule, its gated variant and our full method
sits at or below its own model's paired noise floor of 0.27 to 2.99 percent,
and on the deep model the signs are not stable across seeds. The cause is
mechanical: our method edits 71 of 800 windows, 8.9 percent of the corpus, and
leaves the remainder byte identical. Dilution was ruled out rather than assumed
by evaluating on the 515 edited windows only, which leaves the effect at -0.09,
+0.07 and +0.08 percent across three models. `docs/downstream.md`.

**No foundation model fine tuning is reported.** A frozen model is the verifier
in this method and not the object being curated, appearing in the behavioural
probe and the backend comparison. Whether continued training of a foundation
model on a curated corpus helps is a different question and is not evaluated.
The reason is the measurement above rather than cost: at under 9 percent of
windows modified, the downstream protocol cannot resolve a difference on models
far cheaper to train. `docs/downstream.md`.

**The statistical profile misfire is established only for our implementation.**
It assigns a defect to between 65 and 81 percent of clean windows that are
structurally unpredictable. An attempt to cross validate this against five
standard outlier detectors could not decide the question: four of them cannot
separate contaminated from clean windows on this corpus, with contaminated
lifts of 0.83 to 1.00, so they are not a valid control, and the fifth uses a
three sigma criterion at a rate scale three orders of magnitude below ours and
reports zero on the stratum in question, which is silence rather than a correct
judgement. Whether the misfire generalises to other multi defect classifiers is
untested. `docs/detector_crossval.md`.

**The downstream protocol conflates two sources of variation.** Changing the
seed changes both the corpus window sampling and the model initialisation, so
an unpaired aggregation charges corpus variation to method differences. The
unpaired noise floor on the reference row is 33 to 34 percent against 0.27 to
2.99 once paired. All reported downstream numbers are paired. This was found by
us rather than raised in review. `docs/downstream.md`.

## On the evaluation setting

**Multivariate blocks are not seven channels throughout.** Blocks carry 3 to 7
channels with a median of 4.5, 150 blocks and 684 channel series at the 800
window scale. The distribution follows from the corpus builder over sampling so
the hard stratum can be selected by difficulty and then drawing only what each
stratum needs, which leaves most positions contributing some channels and not
all. `docs/multivariate_downstream.md`.

**The clean out of distribution stratum is absent from the multivariate
evaluation.** Those windows are generated rather than drawn from data, so they
have no channel siblings, and placing them in a multivariate block would mean
inventing companion channels that never existed. They remain in the curation
stage evaluation where they carry the characterisation results.
`docs/multivariate_downstream.md`.

**The cross domain stratum is not verifiably out of distribution.** Exchange
rate and solar power are standard public benchmarks that appear in widely used
repositories, so they may sit inside the pretraining corpora of the frozen
backends, and membership could not be verified. Everything built on that
stratum is described as cross domain and is not offered as strict out of
distribution evidence. `experiments/datasets.py`.

## On the comparison

**End to end reproduction of the closest competing system was not achieved.**
Its published repository omits the module that loads data, which all four of
its core modules import, and its ignore file excludes that path. The authors
were contacted and replied that the module cannot be located and cannot be
supplied. A timeboxed reconstruction with an acceptance criterion fixed in
advance is reported separately, and the comparison in related work is at the
level of mechanism, drawn from that paper's own reported parameter study rather
than from any run of ours. `docs/aegists_reproduction.md`,
`researched_papers/aegists/ISSUE_TO_SEND.md`.

**No experimental comparison is run against the five execution time gating
systems.** Their corpora, action spaces and definitions of harm do not overlap
with a series curation corpus, so there is no shared platform, and constructing
one would mean inventing a benchmark whose numbers would measure the benchmark.
The separation is conceptual and the reason is stated rather than left as a
gap. `researched_papers/conformal_agents/README.md`.
