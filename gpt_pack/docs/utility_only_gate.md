# The single signal calibrated gate, and why its calibrated operating point is unusable

Source `results/utility_only_gate.json`, produced by `experiments/utility_only_gate.py`.
Proposer `stat_only`, seed 42, alpha 0.02, 800 windows.

## What this arm is

The recent gating literature scores each proposed action with one risk model and
calibrates a single threshold on that score so the rate of harmful executions
meets a stated budget. Transposed to this setting the score is the change in
model utility and the threshold is epsilon. Everything else is shared with our
own arm, the same proposer, the same candidates, the same probe, the same
corpus, the same conformal machinery, the same loss. One variable is isolated,
whether the acceptance test consults anything other than the model.

## The full grid, which is the evidence

| eps | damage | repair | edits | protected edits | protected share |
|---|---|---|---|---|---|
| 0 | 0.0394 | +0.309 | 274 | 135 | 0.493 |
| 0.005 | 0.0394 | +0.309 | 265 | 134 | 0.506 |
| 0.01 | 0.0383 | +0.309 | 251 | 121 | 0.482 |
| 0.02 | 0.0358 | +0.310 | 231 | 110 | 0.476 |
| 0.05 | 0.0320 | +0.309 | 190 | 90 | 0.474 |
| 0.1 | 0.0301 | +0.309 | 160 | 74 | 0.463 |
| 0.25 | 0.0221 | +0.225 | 108 | 48 | 0.444 |
| 0.5 | 0.0184 | +0.135 | 76 | 35 | 0.461 |
| 1 | 0.0170 | +0.034 | 41 | 27 | 0.659 |
| 2 | 0.0144 | +0.003 | 23 | 21 | 0.913 |
| **5** | **0.0144** | **+0.000** | **19** | **19** | **1.000** |

The last row is the operating point the conformal procedure selects at alpha
0.02. Realised risk 0.0200, the guarantee holds.

**The whole grid goes in the paper.** Reporting only the calibrated row would
hide that repair collapses from +0.225 to 0.000 while damage moves only from
0.0221 to 0.0144. The shape of that trade is the finding.

## The comparison, at each side's own calibrated point

| arm | operating point | damage | repair | protected edits |
|---|---|---|---|---|
| single signal, utility only | eps star 5 | 0.0144 | +0.000 | 19 of 19 edits |
| structural condition, ours | tau 0.02 | 0.0017 | substantive | 37 |

Both points are what the same conformal procedure returns at the same alpha on
the same corpus. Neither is chosen by hand.

## What this is not

**It is not an efficiency difference.** The single signal arm does not reach a
worse point on the same frontier, it reaches a point where the method has
stopped doing anything. The only way that gate meets alpha 0.02 is by almost
never repairing.

**It is a usability difference.** A gate that satisfies its risk budget by
declining to act has satisfied it vacuously. The budget is met and the method
is gone.

## The part that connects to E4

The protected share column is not incidental. If edits fell at random across the
corpus that share would be 520 of 800, namely 0.650. Under a loose gate it sits
at 0.44 to 0.51, meaning edits concentrate on the contaminated stratum, which is
correct behaviour. As the utility threshold tightens the share rises to 0.659,
then 0.913, then 1.000. At the calibrated point every surviving edit is on a
stratum that must not be edited.

Tests on that concentration:

| comparison | test | result |
|---|---|---|
| 19 of 19 against the 0.650 random baseline | binomial | p 2.8e-04 |
| 19 of 19 against 135 of 274 at eps 0 | Fisher | p 3.2e-06 |
| 21 of 23 at eps 2 against 135 of 274 | Fisher | OR 10.81, p 5.5e-05 |

The binomial test assumes each edit lands independently on a protected stratum
with probability 0.650. These are post selection counts so that assumption does
not hold exactly and the number is an order of magnitude reference, not an exact
level. The two Fisher comparisons do not need it.

This is the consequence E4 predicts. The utility signal measures predictability
rather than data quality, and on protected strata it runs against harm rather
than with it. Selecting by that signal therefore keeps the edits it should drop.
The direction was recorded in `docs/predictability_decorrelation.md` before this
arm was run, and this arm is the operational cost of it.

## Limitation, stated whether or not the result is favourable

**Single seed.** The `seed` field in `results/utility_only_gate.json` is 42, one
value. Our own arm has three seeds on the corresponding audit. This arm does
not, and no spread is available for any row in the grid above. The conclusion is
reported at that strength and not above it.

## Methodological record, a withdrawn reading

An earlier report of this arm stated that our own arm reached damage roughly 11
times lower at comparable protection, citing 35 protected edits against 37 and
damage 0.0184 against 0.0017.

**That reading is withdrawn.** It took the eps 0.5 row, which is a row of the
grid and not the point the calibration selects. Comparing a hand picked row of
one arm against the calibrated point of the other is selective reporting, and
the fact that it favoured us is exactly why it needed to be caught rather than
kept.

The corrected comparison is the calibrated point of each arm, which is the table
above. It happens to be more favourable to us than the withdrawn one, for a
different and stronger reason. The withdrawn number is left in this record
rather than deleted, because the error was in the selection rule and a reader
checking the grid would otherwise wonder why eps 0.5 was ever quoted.

The error surfaced from reading `logs/utility_only.log`, which prints the
calibrated epsilon star on its own line. The result file carried the same value
in its `epsilon_star` field the whole time and it was not read.
