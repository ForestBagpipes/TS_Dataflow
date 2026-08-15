# Calibrating the structural threshold with a finite sample guarantee

The threshold tau was set by hand, then moved to a held out seed by a rule
fixed in code, and both give a number with no statement attached about what it
guarantees. This replaces the number with a procedure that carries one: given a
target level alpha, the expected fraction of windows the system damages is at
most alpha, assuming only exchangeability between calibration and deployment
data.

## Pre registration of the split

Fixed in commit f563583 before the code that uses it was written:

    pool         1600 windows, corpus seed 42, 35 percent contaminated
    split        random, 800 calibration and 800 reporting
    split seed   7
    loss         L_i = 1 if nmse_after > nmse_before + 1e-9, bounded in [0,1]
    alpha grid   0.001 0.002 0.005 0.01 0.015 0.02 0.03 0.04 0.05
    tau grid     0.005 0.01 0.015 0.02 0.03 0.04 0.06 0.08 0.10 0.12 0.16 0.20 0.25 0.30

The split was drawn once and not redrawn. The loss threshold and both grids
carry over unchanged from the first attempt, so nothing about the target moved
when the design was corrected.

## The reachable floor, which the table cannot be read without

**The most conservative threshold in the grid, tau 0.005, already realises a
risk of 0.0088 on the reporting half.** No entry in the grid reaches below it,
so any target under 0.0088 has no solution: the procedure returns the most
conservative threshold available and the realised risk sits above the target
regardless.

That floor is a property of the action space and the grid together, not of the
calibration. It exists because the operators available are coarse, and because
the grid stops at 0.005 rather than continuing towards zero. Extending the grid
downward would lower it until the point where no edit is admitted at all, at
which the risk is zero and so is the repair.

## Main result, same pool split

| alpha | lambda star | calibration risk | corrected | realised | classification |
|---|---|---|---|---|---|
| 0.001 | 0.005 | 0.0112 | 0.0125 | 0.0088 | target unreachable |
| 0.002 | 0.005 | 0.0112 | 0.0125 | 0.0088 | target unreachable |
| 0.005 | 0.005 | 0.0112 | 0.0125 | 0.0088 | target unreachable |
| **0.010** | 0.005 | 0.0112 | 0.0125 | **0.0088** | holds |
| **0.015** | 0.005 | 0.0112 | 0.0125 | **0.0088** | holds |
| **0.020** | 0.015 | 0.0163 | 0.0175 | **0.0100** | holds |
| **0.030** | 0.020 | 0.0213 | 0.0225 | **0.0200** | holds |
| 0.040 | 0.030 | 0.0375 | 0.0387 | 0.0425 | **true violation** |
| **0.050** | 0.040 | 0.0450 | 0.0462 | **0.0500** | holds |

**Under the same pool split the guarantee holds everywhere it is reachable,
with one exception.** Three targets lie below the 0.0088 floor and have no
solution in this action space and grid, and the procedure behaves correctly
there by returning the most conservative threshold. Five hold. One genuine
violation remains, at alpha 0.040 where the realised risk is 0.0425, an
overshoot of 0.0025.

That single violation is bracketed by alpha 0.030 and alpha 0.050, both of
which hold. An isolated failure surrounded by successes is what finite sample
fluctuation looks like, and it is reported as such rather than explained away.

## The signature that separates the two designs

The first attempt calibrated on a corpus built from seed 123 and reported on
one built from seed 42. Both are retained,
`results/conformal_crosscorpus.json` and
`results/conformal_samepool_stage1.json`.

| | cross corpus | same pool |
|---|---|---|
| violations | 7 of 9 | 1 true, 3 unreachable |
| direction | all seven underestimate | isolated |
| ratio of risk curves | 1.2 to 1.5 across the grid | not applicable |
| worst overshoot | +0.0125 | +0.0025 |
| reading | systematic offset | finite sample fluctuation |

The distinguishing evidence is the direction, not the count. Seven violations
all in the same direction, with the two risk curves offset by a consistent 1.2
to 1.5 across the whole threshold grid, is a distribution shift: two
independent samples of ETT windows differ in difficulty, so they are not
exchangeable draws. One isolated violation with neighbours on both sides
holding has no such structure.

## What the alternative is

Hand set thresholds, realised risk on the same reporting half:

| tau | realised risk | guarantee |
|---|---|---|
| 0.02 | 0.0200 | none |
| 0.12 | 0.1025 | none |
| 0.20 | 0.1562 | none |

At alpha 0.02 the procedure selects lambda star 0.015 and realises 0.0100,
**half the target**. The comparison is not between a guaranteed procedure and a
marginally better one. It is between a procedure that states what it delivers
and three numbers that state nothing.

## Sensitivity to the loss threshold

At alpha 0.02, all four hold under the same pool split, against two of four
under the cross corpus design:

| delta | lambda star | realised | holds |
|---|---|---|---|
| **1e-9, primary** | 0.015 | 0.0100 | yes |
| 1e-4 | 0.015 | 0.0088 | yes |
| 1e-2 | 0.020 | 0.0138 | yes |
| 5e-2 | 0.030 | 0.0163 | yes |

Lambda star widens as delta grows, which is the expected direction: counting
only substantive damage admits more edits. The primary criterion at 1e-9 is the
strictest and was fixed before the run because it has no free parameter.

## Monotonicity and which route ran

Measured: **calibration half monotone, reporting half not.**

The selection rule reads only the calibration half, so the nested family
assumption is satisfied where it is used and the conformal route is licensed.
The reporting half is used only to check the realised risk and its monotonicity
does not enter the derivation.

The run prints a warning whenever either half is non monotone, which is stricter
than the condition that actually governs the route, `use_ltt = not mono_cal`.
The logic is right and the message is over broad. **Recorded as a wording defect
to fix; no number changes.**

A fixed sequence testing fallback with Bentkus p values is implemented in
`introact_ts.conformal` for the case where the calibration half is non monotone.
It was verified on a synthetic non monotone family and did not run here.

## Reproducibility

Per window losses at every threshold are written to
`results/conformal_losses.npz`, so any alpha, any selection rule and any future
correction can be evaluated on CPU without occupying the GPU again.
