# Cross checking the profile misfire against independent detectors

Our statistical profile assigns a defect to 65 to 81 percent of clean_ood
windows. Whether that is a property of our implementation or of the class of
signal decides how the paper can state it. AegisTS would have settled it with
its FMMS selected detector, and its repository cannot be run, so five standard
detectors were substituted.

**The result is that this detector pool cannot decide the question. That is not
the same as deciding it in the negative, and the paper says so.**

## What was measured

Five detectors with no code in common with our profile: isolation forest, local
outlier factor, one class support vector machine, a Hampel filter, and three
sigma on a linearly detrended residual. Each was run per window on the 2000
window corpus. Point level rates are reported because the thresholded window
flag rates saturate, see below.

Median fraction of points called anomalous:

| detector | clean | hard | random_walk | pulse_train | staircase | sawtooth | contaminated |
|---|---|---|---|---|---|---|---|
| isolation_forest | 0.2812 | 0.2119 | 0.3496 | 0.3291 | 0.3203 | 0.3320 | 0.2637 |
| local_outlier_factor | 0.0410 | 0.0479 | 0.0176 | 0.0264 | 0.0332 | 0.0215 | 0.0411 |
| one_class_svm | 0.1035 | 0.1729 | 0.0527 | 0.0527 | 0.0527 | 0.0527 | 0.0943 |
| hampel | 0.0850 | 0.0498 | 0.0508 | 0.0371 | 0.0312 | 0.0400 | 0.0703 |
| zscore_detrended | 0.0010 | 0.0059 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0020 |
| *our profile* | | | *0.660* | *0.808* | *0.755* | *0.731* | |

## Why four of the five are not a valid control

Lift of the contaminated rate over the real clean rate:

| detector | contaminated lift | usable |
|---|---|---|
| isolation_forest | 0.94 | no |
| local_outlier_factor | 1.00 | no |
| one_class_svm | 0.91 | no |
| hampel | 0.83 | no |
| zscore_detrended | 2.00 | yes |

Four of them call real clean ETT windows anomalous at the same rate as windows
with injected defects, or higher. A detector that cannot separate the positive
class from the negative class is not measuring data quality on this corpus,
and its behaviour on a third class carries no information. Using one to check
our profile would be measuring our ruler with a broken ruler.

The window level flag rates make the same point more starkly. At a one percent
flag threshold, isolation forest fires on 100 percent of clean windows, one
class SVM on 99.8 percent and Hampel on 97.9 percent.

## Why the fifth does not settle it either

`zscore_detrended` does separate contaminated from clean, at a lift of 2.00,
and it is the only one that does. Its rate on random_walk and pulse_train is
0.0000.

That zero is not a correct judgement, it is silence. The detector reports
essentially nothing on any of the four OOD forms, and a detector that abstains
everywhere trivially has no false positives on clean data. It is also a three
sigma rule on a detrended residual, operating at a rate scale of 1e-3, which is
not the same task as our profile performs: deciding among missing, spike, noise
and level shift and naming a dominant defect.

## What the paper may say

> Our statistical profile assigns a defect to between 65 and 81 percent of
> windows that are structurally unpredictable and entirely clean. We attempted
> to cross validate this against five general purpose outlier detectors. Four
> cannot distinguish contaminated from clean windows on this corpus and so do
> not constitute a valid control, and the fifth uses a three sigma criterion at
> a rate scale three orders of magnitude below ours and is silent on the
> stratum in question. We therefore confirm the misfire only for the profile
> implementation used here, and whether it generalises to other multi defect
> classifiers remains to be tested.

## A positive reading, for the limitations section

The same table supports a claim we could previously only cite from others.
**Four widely used general purpose outlier detectors fail to separate
contaminated windows from clean ones on a realistic time series corpus**, with
contaminated lifts of 0.83 to 1.00. That is our own measurement of why generic
statistical outlier detection is insufficient for this task, and it does not
depend on any of the contested points above.

## Status

The generality question is deferred. It needs a multi defect classifier rather
than a generic outlier detector, which is what the AegisTS FMMS component would
have provided. The pre registered prediction in `docs/prediction_aegists.md`
stands unverified and is not withdrawn.
