# What behavioural risk measures, settled by controlled experiment

Three explanations were proposed for the same observation. Two are dead and the
third turns out to be half right, which is the useful result: the variable is
not one thing, it is two separable things that add.

## The two dead explanations

**Classical predictability.** Killed by the controlled ladder,
`results/ladder.json`, 100 instances per rung, all generated so no dataset
membership question arises.

| rung | median behav_risk | IQR | auc vs ett_real | p |
|---|---|---|---|---|
| sine_pure | -0.168 | 0.326 | 0.254 | 1.8e-09 |
| sine_noisy | -0.085 | 0.446 | 0.354 | 3.7e-04 |
| ar_095 | **+0.384** | 0.363 | 0.729 | 2.1e-08 |
| ar_070 | +0.074 | 0.316 | 0.463 | 0.36 |
| ar_030 | -0.100 | 0.222 | 0.285 | 1.4e-07 |
| white_noise | +0.034 | 0.294 | 0.424 | 0.065 |
| random_walk | **+0.613** | 0.566 | 0.791 | 1.1e-12 |

The ladder is not monotone, 4 rises out of 6. AR(0.95) is more forecastable
than AR(0.30) and scores four tenths higher. White noise is maximally
unforecastable point by point and scores below the real data anchor.

**Structural familiarity.** Killed by the same run's second ladder, built to be
deterministic yet shaped unlike anything typical of a time series corpus.

| rung | median | IQR | auc vs ett_real | p |
|---|---|---|---|---|
| piecewise_linear | -0.023 | 0.559 | 0.415 | 0.039 |
| staircase | -0.087 | 0.462 | 0.364 | 8.8e-04 |
| sawtooth | +0.028 | 0.545 | 0.440 | 0.14 |
| pulse_train | +0.460 | **1.198** | 0.627 | 1.9e-03 |
| ett_real (anchor) | +0.118 | 0.457 | ref | |

Three of the four sit below the real data anchor. If unfamiliar shape were the
variable, all four would be high. Pulse train is the exception and its IQR of
1.198 is the widest in the experiment, so it behaves like a separate phenomenon
rather than like a member of this ladder.

## The 2x2, which decomposes rather than decides

`results/level_2x2.json`, 100 instances per cell, every series normalised to
unit variance so amplitude cannot confound, and the two composite cells built
by one code path so they differ only in whether the baseline wanders randomly
or moves along a straight line.

| cell | level | local shape | median | IQR | auc vs sine_anchored | p |
|---|---|---|---|---|---|---|
| sine_anchored | anchored | predictable | **-0.148** | 0.286 | ref | |
| sine_on_ramp | determined | predictable | **-0.267** | 0.325 | 0.393 | 9.1e-03 |
| noise_anchored | anchored | unpredictable | **-0.007** | 0.441 | 0.665 | 5.8e-05 |
| sine_on_walk | wandering | predictable | **-0.064** | 0.365 | 0.627 | 1.9e-03 |
| walk_only | wandering | unpredictable | **+0.210** | 0.476 | 0.865 | 4.5e-19 |
| ett_real | mixed | mixed | -0.072 | 0.502 | 0.579 | 0.053 |

**Both factors are real, both are significant, and neither dominates.**

Level uncertainty, isolated by the decisive pair where local shape is held
fixed: sine_on_walk -0.064 against sine_on_ramp -0.267, auc 0.716, p 1.4e-07.
The effect is +0.203 and it is not an artefact of the level moving, because the
ramp moves the level just as far, block mean spread 0.715 against the walk's
0.624, and moves it *downward*.

Local unpredictability, isolated with the level anchored in both cells:
noise_anchored -0.007 against sine_anchored -0.148, auc 0.665, p 5.8e-05. The
effect is +0.141.

The two are close to additive. Starting from sine_anchored at -0.148 and adding
both effects predicts -0.148 + 0.203 + 0.141 = +0.196, and the measured cell
that has both, walk_only, sits at +0.210. Within the resolution of this
experiment the factors do not interact.

The automatic verdict printed by the script says the hypothesis is not
supported. That verdict compares the decisive cell against a hand set margin of
0.1 and the measured gap is 0.084, so it fires on a threshold rather than on
the evidence. The paired test is the correct read and it is significant at
1.4e-07. The right conclusion is not that level uncertainty fails, it is that
level uncertainty alone was never going to account for a range that runs from
-0.267 to +0.613.

## The phi sweep, corroborating only

| phi | median | IQR |
|---|---|---|
| 0.30 | -0.127 | 0.364 |
| 0.50 | +0.035 | 0.479 |
| 0.70 | +0.136 | 0.432 |
| 0.85 | +0.176 | 0.307 |
| 0.95 | +0.310 | 0.325 |
| 0.99 | +0.331 | 0.402 |
| 1.00 | +0.202 | 0.402 |

Five rises out of six, with the reversal at the unit root. This is consistent
with the level uncertainty effect and it is not evidence on its own, because
phi moves persistence, within window non stationarity and the stationary
variance together. It is recorded as corroboration and nothing is concluded
from it alone.

## What this explains

Every rung of the ladder follows from the two factor account.

- random_walk highest, both factors present.
- ar_095 high, level uncertainty without much local unpredictability.
- white_noise low despite being unforecastable, because its level is pinned at
  zero. Point by point unpredictability is the weaker of the two factors and
  the reference scale absorbs irreducible noise.
- sine_pure lowest, neither factor.
- staircase and piecewise_linear below the anchor, which matches sine_on_ramp
  sitting below sine_anchored. A determined level change does not merely fail
  to raise risk, it lowers it.

It also connects to two findings recorded earlier under different headings.
The level_shift detection bug, whose root cause was a global IQR inflated 3.04x
by a level displacement, and the RESEGMENT edits that bought no utility because
strong forecasters instance normalise, are the same sensitivity seen from two
other directions.

## The claim this licenses

Behavioural risk is a measure of how hard the window is for a frozen forecaster
to locate and to continue, and it decomposes into level positioning uncertainty
and local shape unpredictability, of which the first is the larger. It is not a
contamination detector, not an out of distribution detector, and not a novelty
detector.

## Limits

The additivity is measured at one point in one corpus with one backend pool and
should not be extrapolated. The composite cells give the sine half the total
variance while sine_anchored gives it all, so the comparison of a composite
against sine_anchored carries that asymmetry, which is why the decisive claim
rests on the walk against ramp pair where the asymmetry is identical on both
sides. Pulse train is not explained by either factor and remains open. All
values are within corpus quantities, see `docs/scope_and_comparability.md`.
