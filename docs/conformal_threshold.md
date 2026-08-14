# Calibrating the structural threshold with a finite sample guarantee

The threshold was set by hand, then moved to a held out seed by a rule fixed in
code, and both give a number with no statement attached about what it
guarantees. This replaces the number with a procedure that carries one: given a
target level alpha, the expected fraction of windows the system damages is at
most alpha, assuming only exchangeability between the calibration data and the
deployment data.

## Pre registration of the split, written before the run

The first attempt used two corpora built from different seeds, 123 for
calibration and 42 for reporting. That violates exchangeability, and the
measured consequence is quantified in the last section. The corrected design
draws **one pool and splits it at random**, so exchangeability holds by
construction rather than by assumption.

Fixed here before any of it executes:

    pool         1600 windows, corpus seed 42, 35 percent contaminated
    split        random, 800 calibration and 800 reporting
    split seed   7
    loss         L_i = 1 if nmse_after > nmse_before + 1e-9, bounded in [0,1]
    alpha grid   0.001 0.002 0.005 0.01 0.015 0.02 0.03 0.04 0.05
    tau grid     0.005 0.01 0.015 0.02 0.03 0.04 0.06 0.08 0.10 0.12 0.16 0.20 0.25 0.30

The split is drawn once. It is not redrawn if the result is unfavourable, and
the loss threshold and the two grids carry over from the first attempt
unchanged so that nothing about the target moved when the design was fixed.

## Results, same pool split

Deferred until the run completes. This section is written by the run, not by
hand.

## Failure boundary, measured rather than assumed

The first attempt is retained, because a negative result about the assumption
is worth more than a discarded experiment. Its outputs are preserved at
`results/conformal_crosscorpus.json` and `logs/conformal_crosscorpus.log` so
the two designs can be read side by side.

One thing it does not contain. Its stability table across contamination rates
was still running when the design error was identified, and it was stopped
rather than allowed to finish, because it would have spent two and a half GPU
hours measuring stability under a protocol already known to be wrong. **The
cross corpus stability table is therefore not available and is marked
deferred.** The same pool version supersedes it and is produced by the rerun.

Calibrating on a corpus built from seed 123 and reporting on one built from
seed 42, the guarantee held at 2 of 9 alpha levels.

| alpha | lambda star | calibration risk | realised on reporting | holds |
|---|---|---|---|---|
| 0.001 | 0.005 | 0.0100 | 0.0100 | no |
| 0.005 | 0.005 | 0.0100 | 0.0100 | no |
| **0.010** | 0.005 | 0.0100 | 0.0100 | **yes** |
| 0.015 | 0.015 | 0.0125 | 0.0187 | no |
| **0.020** | 0.015 | 0.0125 | 0.0187 | **yes** |
| 0.030 | 0.030 | 0.0288 | 0.0413 | no |
| 0.040 | 0.040 | 0.0312 | 0.0462 | no |
| 0.050 | 0.060 | 0.0425 | 0.0625 | no |

The cause is not the calibration machinery and not a monotonicity failure.
Monotonicity holds on both corpora. The two risk curves are offset:

| tau | calibration | reporting | ratio |
|---|---|---|---|
| 0.005 | 0.0100 | 0.0100 | 1.00 |
| 0.020 | 0.0238 | 0.0300 | 1.26 |
| 0.060 | 0.0425 | 0.0625 | 1.47 |
| 0.120 | 0.0737 | 0.1075 | 1.46 |
| 0.300 | 0.1388 | 0.1625 | 1.17 |

**At the same threshold the reporting corpus is 20 to 50 percent more damageable
than the calibration corpus.** Two independent samples of ETT windows differ in
difficulty because window difficulty is heterogeneous in that data, so the two
sets are not exchangeable draws from one distribution. All seven violations
underestimate, never overestimate, which is the signature of a systematic
offset rather than sampling noise. The largest absolute overshoot is 0.0125.

This is the deployment statement the paper should make: **the guarantee is
conditional on exchangeability, and when it is violated by calibrating on one
corpus and deploying on an independently sampled one, the realised risk exceeds
the target by 20 to 50 percent relative.** Anyone applying this to data from a
different source than the calibration set should expect degradation of that
order.

## Two results that stand regardless

**Hand set thresholds carry no guarantee at all**, and their realised risks on
the reporting corpus are 0.0300 at tau 0.02, 0.1075 at 0.12 and 0.1537 at 0.20.
The comparison is not between a guaranteed procedure and a slightly worse one,
it is between a procedure that states what it delivers and three numbers that
state nothing.

**The failure mode is mild and conservative in direction.** Even under the
violated assumption the procedure held at alpha 0.01 and 0.02, and it selected
lambda values well below the hand set ones, 0.005 and 0.015 against 0.02. It
degrades by overshooting a small target rather than by collapsing.

## Sensitivity to the loss threshold

At alpha 0.02, on the first attempt's data:

| delta | lambda star | realised | holds |
|---|---|---|---|
| **1e-9, primary** | 0.015 | 0.0187 | **yes** |
| 1e-4 | 0.015 | 0.0187 | yes |
| 1e-2 | 0.020 | 0.0288 | no |
| 5e-2 | 0.040 | 0.0225 | no |

The primary criterion is the strictest and it is also the one that holds. It
was chosen before the run because it has no free parameter, being floating
point noise rather than a tuned magnitude, and that choice is not revisited
here.
