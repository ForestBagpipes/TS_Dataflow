# The hard layer's criterion, pre registration

Written 2026-08-23, **before any count under the new criterion was produced**.
The distributions below were measured while designing it, which is what the
instruction asked for. No selection has been run.

## Why the old statistic is wrong, independently of any count

    old difficulty = 1 - 0.5 * seasonal - 0.5 * memory

with `seasonal` the largest spectral component's share and `memory` the mean
absolute autocorrelation at lags 1 to 3.

A series near a random walk has short lag autocorrelation close to one and its
spectral power concentrated at the lowest frequency. Both terms therefore
subtract and the window reads as easy. A random walk is the canonical hard case
in forecasting. **The statistic and the concept it names point in opposite
directions on a case that matters.**

This is a definitional error and it stands on its own. It would stand if both
families filled the layer, and it would stand on a corpus with no financial data
at all. The fact that the hard layer came out entirely industrial is what made
the error visible, it is not the reason for fixing it. Nothing in this document
or in the paper may present the change as having been made so that the financial
half would contribute windows.

## The consistency requirement this also settles

The paper already establishes, and section 2.2 states, that the behavioural
signal measures how predictable a window is rather than how good it is. The old
hard layer statistic called a window easy precisely when it was hard to predict.
The two treatments of predictability contradicted each other. The new criterion
defines difficulty by predictability directly, so the two agree.

## The new criterion

**Difficulty is one minus the share of the differenced series' variance that a
linear autoregression on that differenced series can explain.**

    d      = diff(x), mean removed
    AR(p)  fitted on d by least squares, p = 16
    R2     = 1 - residual sum of squares / total sum of squares, floored at 0
    difficulty = clip(1 - R2, 0, 1)

Differencing is what makes the random walk case come out right. A random walk's
level is highly autocorrelated and its increments are not, so measuring the
increments asks the question forecasting actually asks.

`R2` is a ratio of variances, so the statistic is invariant to rescaling the
window. That is the same requirement the window sampler and the changepoint
criterion already carry.

It uses no model from the judged pool. That is not only about cost. Experiment
one asks whether the behavioural signal misreads clean but complex data as low
quality. If the hard layer were defined by that same signal the experiment would
be circular, and the finding would be built into the corpus rather than measured
on it.

## Control cases, measured before the criterion was fixed

Fifty draws each, difficulty on the same scale where larger means harder.

| case | difficulty | expected |
|---|---|---|
| random walk | **0.9684** | hardest, this is the case the old statistic got backwards |
| pure sine | **0.0000** | easiest |
| sine plus noise | 0.5567 | middle |
| white noise | 0.5113 | middle, see the note |

**The white noise note, recorded rather than hidden.** White noise is
unpredictable in level yet scores 0.51 rather than 1.0. Differencing white noise
produces a moving average with lag one autocorrelation of minus one half, which
the autoregression partly predicts. This is a property of the statistic and it
is stated here. It does not affect the corpus, whose base pool is real data, and
it does not affect the case the criterion was rebuilt for.

## Distribution on the two families, measured

400 windows per family.

| quantile | industrial | financial |
|---|---|---|
| 5 | 0.5865 | 0.8398 |
| 25 | 0.7580 | 0.8888 |
| 50 | **0.8338** | **0.9151** |
| 75 | 0.8828 | 0.9381 |
| 95 | 0.9542 | 0.9691 |

Under the old statistic the two medians were 0.1905 and 0.0105, a factor of
eighteen and in the wrong direction. They are now within ten percent of each
other and in the same direction.

**They are still not identical, and the shift is probably real.** Financial
price series are closer to random walks than transformer telemetry is, so a
statistic that correctly identifies random walks as hard should place them
higher. The shift is signal, unlike the old inversion which was error.

## Selection, and the degradation path taken

Because the financial fifth percentile, 0.8398, sits above the industrial
twenty fifth, 0.7580, a single global rank would fill the hard layer mostly from
the financial half. That mirrors the old problem with the sign reversed.

**The hard layer is therefore selected by within family rank**, quota split in
proportion to each family's share of the pool, exactly as the changepoint layer
already is under `docs/changepoint_criterion_preregistration.md`.

This is the degradation path the instruction asked to be written down in
advance, and the condition that triggered it is stated above with its
measurement. What it gives up is the same thing a rank always gives up: it
cannot report that a family contains no hard windows, only that its top `n` are
the hardest it has. The compensation is the same one the changepoint layer
carries, the difficulty distribution of the selected layer is reported per
family beside the pool's.

## Assignment order, unchanged

rare_valid by criterion A, changepoint by the rank criterion, hard by the
criterion above, then the remainder. No window enters two layers. Hard is third,
so it draws from what the first two leave.

## What invalidates what

Changing this criterion changes which windows are protected, so every result
reported per stratum is void and is regenerated with the corpus switch already
under way. This is not an additional cost, it is inside the rerun that the move
to selected layers already required.
