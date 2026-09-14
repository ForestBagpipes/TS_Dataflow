# What an edit is worth, and what it costs

Source `results/ood_curate.json`, one run of the full curation loop over 1150
windows with real TSFM backends, seed 42. This is the pre fix baseline: tau is
at 0.12, which the holdout selection later revises, and the footprint exemption
in the structural distance is still in place.

## The table

Variance ratio is the standard deviation of the curated series over the
standard deviation of the input. It is undefined where the input held NaN,
which is the case for `missing_block` and `missing_scattered`, so 45 of the 124
contaminated edits are excluded from the variance columns and none of the
protected ones are.

Quartiles rather than means. The mean is reported in the last column and it
should not be the headline for this stratum: the 20 clean_ood edits run from
+0.14 to +64.61, two orders of magnitude, and a mean over that is not a
description of anything.

| stratum | edits | ΔU p25 | ΔU median | ΔU p75 | IQR | (mean) | variance ratio mean | min | over half the variance |
|---|---|---|---|---|---|---|---|---|---|
| contaminated | 124 | 0.04 | **0.25** | 0.80 | 0.76 | 0.54 | 0.697 | 0.211 | 21 of 79 |
| **clean_ood** | **20** | 3.45 | **16.97** | 48.02 | 44.57 | 25.81 | **0.177** | **0.032** | **19 of 20** |
| clean | 31 | 0.20 | 0.40 | 0.76 | 0.55 | 2.91 | 0.749 | 0.000 | 6 of 31 |
| hard | 26 | 0.04 | 0.09 | 0.20 | 0.17 | 0.22 | 0.962 | 0.853 | 0 of 26 |
| rare_valid | 10 | 0.06 | 0.11 | 0.39 | 0.33 | 0.38 | 0.906 | 0.285 | 1 of 10 |
| changepoint | 9 | 0.04 | 0.20 | 0.21 | 0.17 | 0.57 | 0.787 | 0.347 | 2 of 9 |
| **real_ood** | **0** | | | | | | | | **0** |

All twenty clean_ood edits, sorted:

    0.14  0.15  0.53  0.96  1.88  3.97  6.81  6.88  8.21  14.89
    19.04 42.14 46.20 46.44 47.30 50.17 50.96 52.18 52.81 64.61

The distribution is bimodal. Ten edits under +20 and ten above +42, with a gap
between 19.04 and 42.14 containing nothing. The upper cluster is the flattening
population documented in `docs/triple_failure_analysis.md`, which lands at a
common post edit utility near -2.0 regardless of where it started. Reporting a
median of 16.97 lands inside the empty gap and describes neither cluster, so
the honest summary of this stratum is that it holds two populations and the
figure should show both.

On the comparison that matters, the median clean_ood edit still collects 68
times the median contaminated edit, 16.97 against 0.25, and the upper cluster
collects around 200 times.

## The exchange rate

Averaged over the edits each stratum received:

| | variance removed | utility gained | utility per percent of variance destroyed |
|---|---|---|---|
| contaminated | 30.3 percent | +0.54 | 0.018 |
| **clean_ood** | **82.3 percent** | **+25.81** | **0.314** |

**Destroying signal in clean unpredictable data pays seventeen times better
than repairing actual contamination.** That ratio is the finding. A rule that
reads only model utility is not merely permissive about destructive edits, it
prefers them, and prefers them by a wide margin over the edits it exists to
make.

Nineteen of the twenty edits on this stratum removed more than half the
variance, against twenty one of seventy nine on contaminated windows. The
destruction is not a tail, it is what almost every edit on this stratum did.

## Why the mechanism is not an accident

A frozen forecaster's reconstruction error on a series it cannot locate is
enormous. Flattening the series towards a constant makes it trivially
predictable, so the error collapses and the utility difference is huge. The
utility ruler is behaving exactly as defined. The definition is what admits
this, and no adjustment to epsilon helps, because the effect is a factor of
thirty rather than a marginal crossing of a threshold.

This is the argument for the conjunction rule stated as a measurement. Utility
alone selects for destruction on precisely the data a curation tool must not
touch. The structural term is what is supposed to stop it, and at tau 0.12 it
stopped 73 proposals on this stratum and let 20 through.

## The two controls in the same table

`hard` is the control that shows the ruler is not simply broken. Those windows
received 26 edits at a mean variance ratio of 0.962 and a mean utility gain of
0.22, and not one of them removed half the variance. Where the data is
genuinely difficult rather than unlocatable, the same rule produces small,
conservative edits.

`real_ood` is the control that bounds the scope. One hundred and fifty real
cross domain windows received zero edits. Whatever drives the flattening, it
does not arise from data being merely unfamiliar, and it did not fire once on
data drawn from real recordings.

## What has to be rerun

Both repairs listed in `docs/triple_failure_analysis.md` change these numbers.
The variance preservation term is aimed directly at the 19 destructive edits,
whose ratios run from 0.032 to below 0.5, and would leave the `hard` edits at
0.962 untouched. The holdout tau selection in `results/tau_holdout.json` also
moves the structural threshold. This table is the before column for both and
should be regenerated with the same script once either lands.
