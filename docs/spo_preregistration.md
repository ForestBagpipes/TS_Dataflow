# SPO pre registration

Written 2026-08-18, before any SPO code was run. Everything below is fixed here
so that no choice among these can be made after seeing which choice is more
favourable. Stage zero has run and its results are cited, nothing else has.

## The cluster count k

**k is 12.**

Criterion, stated so it can be checked: **the largest k whose cell occupancy is
at least 0.75.** Occupancy is the fraction of cluster crossed with operator
cells that the fixed policy actually visited, which is what warm starting can
fill from history.

From `results/spo_feasibility.json`:

| k | occupied | total | occupancy |
|---|---|---|---|
| 10 | 30 | 40 | 0.750 |
| 12 | 36 | 48 | **0.750** |
| 15 | 39 | 60 | 0.650 |
| 20 | 49 | 80 | 0.613 |

10 and 12 tie at 0.750, so the larger is taken, which is 12.

**This criterion is independent of any significance result.** It reads only the
occupancy column. It does not read the chi square or the permutation p, and it
would return the same k if every one of those tests had come back flat.

**When it was formed, stated plainly.** After the stage zero coverage table
existed and before any SPO run. It is not a blind pre registration. The reason
it is still worth recording is that occupancy and significance are separate
columns, and the tie break rule takes the larger k, which is the one where
IMPUTE's permutation p is *worse* than at k equal to 10, namely 0.0043 against
0.0031. Choosing on significance would have picked k equal to 10.

All four values of k are retained as a sensitivity analysis. Every stage zero
number for k in 10, 15 and 20 stays in the result file and in the paper's
appendix. No k is dropped.

## Corpus split for policy learning

Training and evaluation corpora do not overlap. The split is by window, drawn
once, and its seed is fixed here.

| item | value |
|---|---|
| split seed | 20260818 |
| training fraction | 0.40 |
| evaluation fraction | 0.60 |
| split unit | window |
| stratification | by stratum, so both halves carry all six layers in proportion |

The seed is written here rather than chosen at run time so that a rerun cannot
quietly land on a friendlier partition. Evaluation is the larger half because
every headline number is reported on it.

## Pre registered read outs

These three are fixed before their experiments run. Each names the outcome that
costs us the claim, at the same level of detail as the outcome that supports it.

**Experiment four, policy learning gain.** The improvement of the learned policy
over the fixed rule counts as established only if it exceeds the seed to seed
spread. That spread is measured first, on the fixed rule alone across multiple
seeds, and it is measured before the learned policy is run. If the improvement
falls inside the spread it is reported as not established, not as a trend.

**Experiment two, reward shaping.** If the flattening action proposal frequency
curves of the two policies do not differ significantly, the reward shaping claim
does not hold, and it is rewritten as no effect of this mechanism was observed
under the present setting. It is not rewritten as a smaller effect or as
directionally consistent.

**Experiment three, exploration safety.** If cumulative damage under the sandbox
arm grows with interaction count, that indicates an implementation fault rather
than a fault in theorem three. The implementation is checked first and the
finding is not reported as evidence against the theorem until the implementation
has been cleared.

## Expected shape of the result, recorded so it can be wrong

Stage zero found IMPUTE's admission rate ranges from 0.000 to 0.222 across
clusters at k equal to 12. Even the best cluster admits about two in nine.

The consequence for experiment four is that **the main gain available to policy
learning is suppressing hopeless proposals rather than raising repair volume.**
Damage and repair should improve only modestly. The larger separation should
appear in experiment five, on budget efficiency, because avoided proposals are
avoided probe calls.

This is written down now so that a modest damage and repair result is read as
the predicted outcome rather than as a disappointment, and equally so that a
large one is read as contradicting the stated expectation.

## What stage zero does and does not license

Licensed. There is cluster level structure in admission for IMPUTE, which
carries 1215 of 1561 adjudicated candidates. Its permutation p is below 0.05 at
all four k and below the Bonferroni threshold of 0.0125 at k equal to 10, 12 and
15.

Not licensed. **RESEGMENT has no cluster level structure**, permutation p from
0.81 to 0.96 at every k. DESPIKE loses significance as k rises, 0.0202 at k
equal to 10 up to 0.2226 at k equal to 20, which reads as insufficient
resolution rather than as structure. DENOISE is below 0.05 at every k but
carries only 71 candidates with 8 to 10 cells below the expected count rule, so
it is not treated as independent evidence.

The clustering is not a restatement of the stratum label. Adjusted mutual
information between cluster and stratum is 0.1502, 0.1473, 0.1417 and 0.1384 at
k equal to 10, 12, 15 and 20.
