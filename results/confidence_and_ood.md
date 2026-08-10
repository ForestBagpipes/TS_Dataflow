# Two negative findings from the 2000 window run

Both are properties of the method rather than of the corpus, both were only
visible at this scale, and both bear directly on claims the paper makes.

## 1. Confidence is anti correlated with edit quality

Ordering edited windows by the confidence of the risk state and measuring the
error rate among the most confident fraction gives a curve that runs the wrong
way.

| coverage | error rate among edits |
|---|---|
| 0.10 | 0.595 |
| 0.25 | 0.649 |
| 0.50 | 0.608 |
| 0.75 | 0.583 |
| 1.00 | 0.484 |

The most confident tenth of edits is wrong 59.5 percent of the time against
48.4 percent across all of them. Selective execution on this signal would make
the pipeline worse, not better.

The mechanism is visible in one table:

| defect routed | edits | median confidence |
|---|---|---|
| missing | 232 | 0.642 |
| noise | 8 | 0.600 |
| spike | 39 | 0.578 |
| shift | 99 | 0.509 |

Confidence is highest exactly where the agent edits most, on missingness, and
the rollback audit already established that refusing an IMPUTE saves twenty
times what it costs. So the windows the agent is most sure about are the ones
whose repairs most need vetoing.

That is not a contradiction, it is a conflation. The posterior measures **how
sure the agent is about what kind of window this is**. It says nothing about
**how likely this particular edit is to succeed**. The acceptance rule treats
them as the same quantity: `action_risk` gives the confidence term a weight of
0.45, so a high posterior lowers the decision risk and makes a commit easier
precisely in the regime where commits go wrong most often.

The risk term therefore does not currently do the job it exists for. Fixing it
means finding a signal that predicts edit success rather than defect identity.
The obvious candidate is already computed and currently weighted at 0.30,
improvement consistency, the fraction of behaviour dimensions that moved the
right way. Whether it separates good edits from bad ones is measurable offline
from the traces now on disk, and that measurement should come before any
reweighting.

## 2. The clean out of distribution hypothesis never fires

Of 210 clean_ood windows, the posterior assigned:

| assigned hypothesis | n |
|---|---|
| contaminated | 96 |
| rare_valid | 63 |
| clean | 45 |
| hard | 6 |
| clean_ood | **0** |

Not one window in the entire corpus was labelled clean_ood, and 46 percent of
the stratum was labelled contaminated. The hypothesis exists in the posterior
and contributes nothing.

The cause is in `corpus_reference`, which sets `ood_scale` to zero unless the
85th percentile of the OOD score exceeds 1e-3. OOD scores are mean cosine
distances between L2 normalised statistical profiles, and on this corpus they
do not clear that floor, so the OOD evidence term is switched off and the
hypothesis can never win.

Two consequences. The protection numbers reported for the clean_ood stratum
are real, since those windows were still mostly left alone, but they are the
result of other hypotheses winning rather than of OOD reasoning working. And
one of the six evaluation strata currently tests nothing about the mechanism
it was built for.

The floor was added for a reason. It stops a degenerate OOD distribution,
where every window is equally typical, from producing a 0.5 sigmoid and
inventing OOD evidence everywhere. The fix is to make the switch depend on the
spread of the distribution rather than on an absolute distance, since what
matters is whether windows differ from each other in profile space, not
whether the raw cosine number is large.

## Status

Both are recorded, neither is fixed. Fixing them changes the acceptance rule
and the risk state, which would invalidate the sweep currently running, so
they belong in the round after it.
