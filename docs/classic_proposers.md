# Two published proposers, and what each was given

Every proposer compared so far is our own construction. These two are published
methods, reimplemented from their algorithmic descriptions and fed into the same
acceptance layer as everything else, so the modularity claim is tested against
something we did not design.

## Parameter selection rule, fixed before the runs

**For each proposer, the parameter setting that maximises its repair is
selected. Damage is not considered in the selection.**

The reason this is the right rule and not the convenient one. Our claim is that
the acceptance layer reduces damage without giving up most of the repair.
Selecting a proposer's parameters to minimise its damage would be doing the
layer's job on its behalf before the comparison starts, which would make the
comparison meaningless and would flatter us. Giving each proposer its strongest
repair setting puts the layer under the harder test.

This rule is recorded before the selection is applied and is not revisited.

### What it selects, with the discarded settings

| proposer | setting | damage | repair | selected |
|---|---|---|---|---|
| SCREEN | window 5 | 0.0044 | **+0.070** | **yes** |
| SCREEN | window 10 | 0.0045 | +0.069 | no |
| IMR unsupervised | p 3, 20 iterations | 0.1869 | +0.023 | no |
| IMR unsupervised | p 5, 40 iterations | 0.2888 | **+0.029** | **yes** |

Measured on a 190 window corpus at seed 42, before any gating.

For SCREEN the two settings are within 0.0001 damage and 0.001 repair of each
other, so the choice is immaterial and either would give the same conclusion.

**For IMR the choice matters and it goes against us.** The selected setting has
0.2888 damage against 0.1869 for the discarded one, so the rule hands the
comparison a proposer that does more damage than it needed to. That follows
from the rule, which was fixed for the reason above, and the discarded row is
printed here so the effect of the rule is visible rather than implied.

## SCREEN, speed constraint repair

**Given:** the distribution of first differences across the corpus it may see,
used to estimate the speed constraint.

**Denied:** any label, and the pristine series.

**One judgement call, and it favours SCREEN.** The paper takes the speed
constraint as supplied by a domain expert. We have none, so it is estimated
from quantiles of the observed first difference, at the 1st and 99th percentile
rather than at the extremes. With the extremes the constraint admits every
transition present in the data including those produced by contamination, and
the method degenerates to the identity. The quantile choice is what allows it
to act at all, and it is a choice we made in its favour.

**Not weakened:** the local variant is used, which is the one the paper
describes in full and which processes a bounded window rather than solving a
global program.

## IMR, iterative minimum repair

**Given:** the series under repair, and nothing else.

**Denied:** labels.

**This is a real deviation from the published setting and it disadvantages the
method.** IMR as published is semi supervised: it receives a set of positions
whose values are known correct and propagates from them. No such labels exist
in the deployment setting this paper studies, and taking them from the pristine
series would be handing the method the answer to the question being asked. So
the unsupervised variant is what enters the comparison.

**The deviation is bounded and we measured it.** A seeded variant was also
implemented, treating the first ten percent of the series as trustworthy, taken
from the series under repair rather than from any pristine reference. It scores
0.1748 damage against 0.1869 for the unsupervised variant at the same
parameters, a difference of 0.0121.

**That difference is small, and it settles the question a reviewer will ask.**
IMR's high damage is a property of the method being aggressive on this data,
not an artefact of having withheld its labels. Both variants appear in the main
table so a reader can see this rather than take it on trust.

**Not weakened:** the algorithm repairs one point per iteration and refits the
model afterwards, which is the part that matters, since a batch repair lets one
error distort the model that judges the next.

## Why these two and not the recent systems

Both are univariate. Our curation window is a one dimensional series of length
512, confirmed by inspection of the corpus, and the recent alternatives are
multivariate methods whose cross variable constraints have no referent on such
a window. Scoping them down would raise the same faithfulness dispute already
documented for the sequential curation system, where a reconstructed component
makes any resulting number less trustworthy than no number at all.

Recency is carried elsewhere. The verification strategy comparison includes
mechanism level stand ins for two 2026 systems, a soft penalty arm and a
utility only calibrated arm, both implemented by us as controlled contrasts.
The related work section covers five execution time gating papers. At the
proposer layer, classical methods reproduce with less dispute, which is the
whole point of adding them.
