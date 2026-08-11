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

| stratum | edited | ΔU mean | ΔU median | ΔU vs contaminated | variance ratio mean | min | edits removing over half the variance |
|---|---|---|---|---|---|---|---|
| contaminated | 124 | 0.54 | 0.25 | 1.0x | 0.697 | 0.211 | 21 of 79 |
| **clean_ood** | **20** | **25.81** | **16.97** | **48.1x** | **0.177** | **0.032** | **19 of 20** |
| clean | 31 | 2.91 | 0.40 | 5.4x | 0.749 | 0.000 | 6 of 31 |
| hard | 26 | 0.22 | 0.09 | 0.4x | 0.962 | 0.853 | 0 of 26 |
| rare_valid | 10 | 0.38 | 0.11 | 0.7x | 0.906 | 0.285 | 1 of 10 |
| changepoint | 9 | 0.57 | 0.20 | 1.1x | 0.787 | 0.347 | 2 of 9 |
| **real_ood** | **0** | | | | | | **0** |

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
