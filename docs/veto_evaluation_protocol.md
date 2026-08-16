# How a veto is evaluated, fixed before the results are read

Three ways of scoring the acceptance layer's decisions were available and they
answer different questions. Which one carries the conclusion is decided here,
before the join completes, so it cannot be chosen afterwards on the basis of
which is more favourable.

## Why more than one is needed

Candidates do not fall uniformly across the corpus. For the speed constraint
proposer, 51.7 percent of candidates land on a protected stratum, where the
window is already clean and any edit increases error by definition. On that
half the harm rate is exactly 1.000 and no scoring rule can separate a good
veto from a bad one, because every veto is correct.

That is why an aggregate precision figure is close to meaningless here. It is
diluted by a region with no discriminative content, and it looks worse the more
of the corpus is protected.

## The three protocols and their roles

### Contaminated stratum, precision. This is the discriminative test.

**Question.** Of the candidates the layer vetoed on contaminated windows, what
fraction would actually have hurt?

**Baseline.** The harm rate on that stratum, 0.382 for the speed constraint
proposer. Vetoing at random achieves that precision in expectation, so the
layer must significantly exceed it to be judged as discriminating rather than
blocking.

**Why this is the test.** The contaminated stratum is the only region with
genuine discriminative room: 61.8 percent of candidates there are beneficial
and 38.2 percent are harmful, so a decision procedure has something to get
right or wrong. **This protocol carries the conclusion about component three.**

### Protected strata, recall. This is the safety test.

**Question.** Of the 168 candidates landing on protected windows, how many did
the layer stop?

**Why recall and not precision.** The harm rate there is 1.000, so any veto is
by construction correct and precision is identically 1 for every possible
policy, including one that vetoes at random. Precision carries no information
on this stratum. Recall does, because it measures how much of a region that
should never be touched was in fact protected.

**Baseline.** The overall veto rate. A layer that vetoes a fixed fraction
regardless of content achieves that recall on any stratum, so the layer must
exceed it.

### Whole corpus, precision. Reference only.

Reported for completeness and **not used as the basis for any conclusion**. It
mixes the 51.7 percent with no discriminative content into the 48.3 percent
that has some, so it is compressed towards the corpus harm rate by
construction. A number that moves when the stratum proportions change is not a
measure of the decision procedure.

## Fixed

Discriminative power is judged on contaminated precision against 0.382. Safety
is judged on protected recall against the overall veto rate. The aggregate is
context. These roles are not revised after the join is read.
