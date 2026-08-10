# How clean out of distribution windows defeat every check in turn

Pre fix baseline. Every number here comes from the 2000 window run with real
TSFMs, `results/xl/xl_ett_multi-family_seed42_traces.json`, and describes the
system as it stands before the two repairs listed at the end. None of the
repairs have been applied, so these numbers stay valid as the before column.

The headline is that 96 of 210 clean out of distribution windows are labelled
contaminated. That number by itself suggests one broken component. It is not
one. Three independent checks fail on this stratum, each for its own reason,
and the failures compose into a specific and severe outcome: ten clean windows
were flattened into near constants with the full approval of the acceptance
rule.

## Failure one, perception has no evidence that says clean

The hypothesis is chosen from two sources of evidence, and on this stratum one
of them is inverted and the other is silent.

| stratum | median behavioural risk | vs contaminated |
|---|---|---|
| **clean_ood** | **+0.473** | auc 0.726, p 1.3e-23 |
| rare_valid | +0.108 | auc 0.534, p 0.13 |
| changepoint | +0.071 | auc 0.515, p 0.51 |
| contaminated | +0.063 | reference |
| hard | +0.044 | auc 0.497, p 0.89 |
| clean | +0.020 | auc 0.460, p 0.023 |

Behavioural risk is inverted. Clean out of distribution windows alarm a frozen
forecaster more than injected contamination does, by a factor of seven at the
median, and it is the only stratum where that inversion is significant. The
mechanism is not subtle: a random walk or a staircase is unlike anything in the
pretraining mixture, so reconstruction is bad everywhere, whereas a spike in an
ETT window is bad in one place.

The statistical profile, which exists to catch exactly this, is silent. Against
contaminated windows it scores auc 0.482 with p 0.42, indistinguishable from a
coin flip, while on every other protected stratum it works normally at 0.24 to
0.34 with p below 1e-11. So there is no second opinion available here.

The third source, the out of distribution hypothesis that exists to protect this
stratum, fired 0 times out of 210. `corpus_reference` requires the 85th
percentile of the OOD score to exceed 1e-3 before the hypothesis is admitted,
and the score is a cosine distance between normalised profiles, which does not
reach that threshold on this corpus. The protection is unreachable by
construction, not merely mistuned.

Result: 96 contaminated, 63 rare valid, 45 clean, 6 hard. The correct label is
not in the top slot for 165 of 210 windows.

## Failure two, the utility ruler pays for destruction

Twenty windows were edited. Ten of them share a signature that is not visible
in any aggregate:

| shape | delta utility | utility before | utility after | points changed | std before | std after |
|---|---|---|---|---|---|---|
| sawtooth | +65.2 | -67.15 | -1.91 | 10.7% | 1.409 | 0.046 |
| sawtooth | +64.6 | -66.57 | -1.98 | 9.8% | 1.351 | 0.044 |
| staircase | +64.2 | -66.46 | -2.24 | 9.4% | 1.369 | 0.048 |
| sawtooth | +55.3 | -57.35 | -2.03 | 9.8% | 1.281 | 0.047 |
| random_walk | +55.0 | -57.09 | -2.11 | 9.0% | 1.266 | 0.046 |
| staircase | +52.4 | -54.50 | -2.11 | 9.6% | 1.261 | 0.045 |
| staircase | +48.8 | -50.77 | -2.02 | 8.6% | 1.256 | 0.049 |
| random_walk | +48.5 | -50.33 | -1.85 | 8.8% | 1.354 | 0.047 |
| random_walk | +42.5 | -44.51 | -2.03 | 9.0% | 1.284 | 0.049 |
| random_walk | +42.0 | -44.07 | -2.10 | 9.0% | 1.168 | 0.047 |

Every one of them lands on the same final utility, close to -2.0, from starting
points spread between -44 and -67. That common endpoint is the tell. DESPIKE is
not removing an anomaly from these windows, it is removing the window. Nine
percent of the points are edited and ninety six percent of the variance
disappears with them. What is left is close to a constant, and a constant is
the easiest thing in the world for a forecaster to predict, which is exactly
why the utility rises by sixty five.

This is the two rulers problem in its sharpest form. Measured by model utility
the edit is the best edit in the entire corpus. Measured against the data it
destroyed the signal. An acceptance rule that reads only the first ruler cannot
tell the two apart, and no amount of tightening epsilon helps, because the
effect is not marginal, it is a factor of thirty.

The other three shapes matter for what they rule out. Pulse train, the shape a
spike remover would obviously wreck, was edited 0 times out of 52. My first
reading of this table was that pulse trains were being shaved, and the data
says otherwise. The vulnerable shapes are the ones whose structure lives in
sharp transitions spread across the window rather than in isolated events.

## Failure three, the structural guard is exempted from looking

The guard is not broken. On this same stratum it vetoed 64 proposals, at a
median structural distance of 0.248 against a threshold of 0.12. It works.

It did not see these ten:

| | structural distance | threshold |
|---|---|---|
| the ten flattening edits | median **0.0373** | 0.12 |
| what the guard did veto | median 0.2480 | 0.12 |

The ten edits score at a third of the budget. The reason is a design decision
that is correct for most cases and wrong for this one. DESPIKE is a local
operator, so it is judged with the local weight profile, which evaluates
distortion *outside the footprint the operator declares*. The declared
footprint is the nine percent of points being removed. Outside it, the other
ninety one percent of points are untouched, so the distance is genuinely small.

The guard is checking outside the circle the operator drew, and the damage is
inside the circle. The variance collapse is precisely the quantity the
footprint exemption hides.

## What the composition produced

Failure one supplies a contaminated label with no dissenting evidence. Failure
two turns the most destructive available edit into the highest scoring one.
Failure three lets it through the last gate. All three are needed: any single
one of them alone would have stopped it.

It is worth stating what did work, because it bounds the damage and it is the
reason the failure is measurable at all. Only 20 of 210 clean out of
distribution windows were modified, a rate of 9.5 percent, which is *lower*
than the 13.8 percent on the clean stratum, and 73 proposals were rolled back.
The post hoc verification layer caught most of what perception got wrong. It is
the one gap in that layer, the footprint exemption, that the ten flattenings
went through.

That is also the honest way to present this in the paper. The method's own
governance trace is what makes this diagnosable, down to which operator, which
windows and which threshold. A pipeline that scored windows and dropped the low
scoring ones would have destroyed the same ten windows and produced no record
that it had.

## The two repairs, specified but not applied

**A variance preservation term in the structural distance for local operators.**
The footprint exemption should not exempt the operator from accounting for what
it removed. A ratio of post edit spread to pre edit spread, measured on the
whole window and vetoing below some floor, would have stopped all ten at a
distance of 0.03 while leaving the three benign DESPIKE edits, whose ratios are
0.99 to 1.00, untouched. This is one cheap scalar and it separates the two
populations completely in this run.

**A reachable out of distribution threshold.** The 1e-3 floor on the 85th
percentile of a normalised profile cosine distance admits nothing. The
threshold has to be set from the corpus distribution of that score rather than
from an absolute constant.

Both change the acceptance rule, so both invalidate the runs that use it. What
would need rerunning is listed in `docs/rerun_after_fixes.md`. The current
numbers are kept as the pre fix baseline and this document is the record of
what they were.
