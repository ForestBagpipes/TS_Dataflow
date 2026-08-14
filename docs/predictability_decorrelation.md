# Removing the confound from the behavioural signal

Peer calibration buys nothing. Corpus AUROC is 0.468 against 0.467 for plain
global standardisation, and every per type pair is within 0.03. The established
reason is that the signal measures predictability rather than data quality, and
peers matched on a statistical profile are not matched on predictability.

This tests whether estimating predictability and regressing it out repairs the
signal. **It partially does, and the way it fails is more informative than the
way it succeeds.**

Source `results/decorrelate.json`, 2000 window run, no TSFM re run. Six proxies
computed from the series alone: spectral entropy, spectral flatness, out of
sample AR R squared, persistence NMSE, first difference autocorrelation, and
sample entropy. The regression uses no labels, so the AUROC that follows is
scored against labels it never saw.

## The headline, with intervals

Paired bootstrap, 2000 resamples, 740 contaminated against 1260 protected.

| variant | AUROC | 95 percent CI |
|---|---|---|
| behavioural risk, as used | 0.468 | [0.442, 0.494] |
| peer calibrated, recorded | 0.468 | |
| global standardised, recorded | 0.467 | |
| **predictability residual** | **0.551** | **[0.524, 0.577]** |

Paired difference **+0.083, CI [+0.060, +0.108]**, with 0 of 2000 resamples at
or below zero. The residual's interval excludes 0.5, which the original does
not: the original interval lies entirely below 0.5, meaning the raw signal is
systematically inverted rather than merely uninformative.

## The confound is precisely located, not diffusely correlated

**The regression explains 9.4 percent of the variance in behavioural risk, and
removing that 9.4 percent produces every structural change reported below.**

That combination is the point. A confound that accounted for most of the
variance would be unsurprising and would leave nothing behind. One that
accounts for a tenth of it while controlling the entire failure mode is a
specific, identifiable component rather than a vague correlation, which is what
makes it worth naming in the method.

Coefficients: spectral entropy +1.7643, spectral flatness -4.0828, AR R squared
-0.6926, sample entropy -0.6734, first difference autocorrelation -0.5046,
persistence NMSE -0.0000.

## What it fixes

Clean out of distribution windows, by generator form, against contaminated:

| form | behavioural median | residual median | auc, behavioural | auc, residual |
|---|---|---|---|---|
| random_walk | +0.389 | -0.220 | 0.725 | **0.504** |
| staircase | +0.535 | -0.173 | 0.716 | **0.518** |
| pulse_train | +0.326 | -0.145 | 0.705 | **0.527** |
| sawtooth | +0.492 | -0.237 | 0.760 | **0.514** |

All four move from 0.705 to 0.760 down to 0.504 to 0.527. Clean unpredictable
data is no longer ranked as more suspicious than genuine contamination, and the
correction is uniform across four generators that share nothing but being
unpredictable.

## What it breaks, and why it is the same root cause

Per contamination type, against clean windows:

| type | behavioural | residual | delta |
|---|---|---|---|
| noise | 0.413 | **0.814** | +0.401 |
| missing_scattered | 0.498 | 0.687 | +0.189 |
| missing_block | 0.558 | 0.720 | +0.162 |
| spike | 0.669 | 0.704 | +0.035 |
| duplicate | 0.573 | 0.501 | -0.072 |
| flatline | 0.576 | 0.463 | -0.113 |
| **level_shift** | 0.495 | **0.375** | -0.119 |

This is not a price paid for the fix. It is the same fact seen from the other
side.

The behavioural signal's sensitivity to level positioning uncertainty was
measured independently at +0.203 in the 2x2 experiment. Unpredictability
arising from a displaced level and unpredictability arising from the structure
of the series itself are **the same quantity as far as the signal is
concerned**, and no operation on the signal alone can separate them. So before
removing the confound, clean unpredictable data is scored as dirty. After
removing it, genuine level displacement is scored as clean. **Two errors in
opposite directions from one root cause.**

The design conclusion follows directly and is the reason this belongs in the
method rather than in an appendix. Any acceptance procedure that reads only
model behaviour will make opposite errors on these two classes of data, whether
or not it corrects for predictability, because the correction trades one for the
other. A second evidence source that does not consult the model is not a
robustness addition, it is required.

## Status of the module

**Diagnostic, and only integrated if it earns it.** Whether the residual score
is wired into the acceptance path is decided by measurement, in
`results/gating_m4.json`: it goes in only if protected stratum edits fall
without repair degrading materially. The criterion was fixed before that
experiment ran.

What this module establishes regardless of that outcome is that predictability
is a separable and locatable confound in the behavioural signal, quantified at
9.4 percent of its variance, and that removing it does not make the signal a
usable detector. **Even fully corrected the signal reaches only 0.551**, which
is the measurement behind the claim that model behaviour cannot carry the
acceptance decision on its own.
