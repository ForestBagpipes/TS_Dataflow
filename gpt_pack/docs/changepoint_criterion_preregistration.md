# The changepoint layer's criterion, second pre registration

Written 2026-08-23, **before any selection under this criterion was run**. The
first attempt is recorded in `docs/stratum_selection_preregistration.md` and it
failed, returning four windows out of 1600 with four of six datasets giving
none. This document replaces criterion B only. Criterion A, the rare valid
layer, is unchanged and its 115 of 1600 stands.

## Why the first criterion failed, stated before the replacement

The threshold was expressed in channel IQR units and justified as sitting at the
bottom of the injected level shift range. The measurement that pre registration
itself mandated showed the justification was wrong: the injection scales by the
**window's** spread while the criterion measured in the **channel's** IQR, and
the two differ by a factor of two to three. At 2.5 channel IQR the threshold sat
near the top of the injected distribution rather than the bottom, so criterion B1
rejected 792 of 800 industrial and 799 of 800 financial windows.

That was an error in the criterion's expression, and the reason it is being
replaced rather than retuned is set out below.

## Why no absolute threshold can work, measured

The jump statistic was measured in three units on 400 windows per family. No
unit puts the two families on one scale.

| unit | industrial | financial |
|---|---|---|
| channel IQR, median | 0.312 | 0.325 |
| channel IQR, 99th | 2.468 | 1.450 |
| blockwise robust scale, median | 0.639 | 3.257 |
| pooled within segment SD, median | 0.725 | 2.487 |
| pooled within segment SD, 90th | 1.848 | 4.284 |

The financial median under the last two units sits above the industrial 90th
percentile. A single threshold either takes almost nothing from industry or
almost everything from finance. This is not a tuning problem, it is a property
of the data: a parallel shift of a rate curve is an ordinary weekly event while
a transformer changing regime is not.

## The criterion, a within family rank

**The changepoint layer is the windows with the largest jump statistic among
those that preserve scale, ranked within their own family, taken to the
requested layer size split between the two families in proportion to the pool.**

Statistic, computed on the window alone.

    split k    the point in the middle half maximising the absolute difference
               of segment means, the same search criterion A already uses
    pooled     sqrt( (var(x[:k]) + var(x[k:])) / 2 )
    t          abs(mean(x[:k]) - mean(x[k:])) / pooled

Admission, in order.

| # | condition | form |
|---|---|---|
| C1 | scale is preserved, `std(left)/std(right)` lies in `[1/1.5, 1.5]` | unchanged from B2 |
| C2 | it is not also a rare valid window, criterion A fails | unchanged from B3 |
| C3 | it is not in the pool any defect is injected into | unchanged from B4 |
| C4 | among the survivors, it is in the top `n_family` by `t`, ranked within its own family | **new, replaces B1** |

`n_family` is the requested layer size split in proportion to each family's
share of the pool, so neither family can be absent and neither can dominate by
pool size alone.

## Against the three criteria that were set

**Not dependent on anything only the injector knows.** `t`, the scale ratio and
criterion A all read the window's own values. No injection parameter, no
contamination label, no pristine reference enters. The circularity the first
pre registration set out to remove stays removed.

**Selects in both families by construction.** A rank within a family always
fills that family's quota as long as the pool holds enough windows passing C1 to
C3. The measured pass rate for C1 alone is 0.725 industrial and 0.417 financial,
so both have room. If a family cannot fill its quota the shortfall is reported
with its count, never repaired by relaxing C1.

**Scale free.** A rank is invariant to any monotone rescaling of `t`, which is
the same reason the window sampler compares a window's spread against its own
channel's typical local spread rather than an absolute floor.

## What is given up, said plainly

A rank always returns something. It cannot report that a family has no
legitimate changepoints, only that its top `n` are the least unlike one. The
absolute threshold could have said that and this cannot.

The compensation is fixed here: **the distribution of `t` in the selected layer
is reported per family, beside the distribution of `t` on injected level shift
windows.** If the selected windows turn out to have jumps far smaller than the
injected ones, the layer is a weaker test than it claims and that is reported,
whichever way it comes out. This is the same read out the first pre registration
promised and it survives the change of criterion.

## Rejected alternatives, with reasons

**Per family absolute thresholds set from each family's injected distribution.**
Rejected because the numbers would have been chosen after seeing the counts that
disqualified the first attempt, which is what a pre registration exists to
prevent, and because it keeps two thresholds where a rank needs none.

**Industrial only, and record that finance provides no such layer.** Rejected
against criterion two. It is also false to the data: finance has more large mean
shifts, not fewer, so declaring it empty would misdescribe it.

**Keeping the synthetic construction for this layer alone.** Rejected. It is the
circularity that section 4.1.2 claims to avoid, and leaving one of four
protected layers synthetic would leave the claim untrue by a quarter.

## Assignment order, unchanged

rare_valid by criterion A, then changepoint by the criterion above, then hard by
difficulty, then the remainder. No window enters two layers.
