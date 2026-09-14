# Pre registered prediction, written before AegisTS is run

This document is committed before any AegisTS code executes on our corpus. Its
purpose is to state a falsifiable prediction in advance, so that a confirmation
counts as evidence rather than as a story assembled after the fact. The commit
timestamp is the record.

## What is being predicted

AegisTS will propose edits on a large fraction of our clean_ood windows, and it
will do so on random_walk and pulse_train in particular, the two forms that
share no structure with any injected defect.

## Why this follows from what is already known

AegisTS selects the issue type to work on from a high level state
`sH = [idom, aprevH, plite, l]`, in which `idom` is a one hot encoding of the
most severe issue determined from quality rates: missing rate, outlier rate and
violation rate. Its own ablation confirms the dependence, since the `w/o
Metrics` variant, which removes those rates, suffers NMSE spikes.

We have measured what a quality rate signal does on these windows. Our
statistical profile assigns a defect to between 65 and 81 percent of them, and
the misassignment does not depend on structural collision with an injected
defect:

| form | assigned a defect | of which level shift | none |
|---|---|---|---|
| random_walk | 35 of 53, 66 percent | 18 | 18 |
| pulse_train | 42 of 52, 81 percent | 28 | 10 |
| staircase | 40 of 53, 75 percent | 26 | 13 |
| sawtooth | 38 of 52, 73 percent | 25 | 14 |

Source `docs/ood_form_split.md`, from the 2000 window run.

AegisTS derives its rates from a detector selected by FMMS, which is a
different implementation from ours. That independence is what makes the
prediction worth registering: if a separately built detection stack fires on
the same windows, the weakness belongs to the class of signal rather than to
our implementation of it.

## The falsifiable criteria, fixed now

Measured on the clean_ood stratum of our corpus, with AegisTS as proposer and
before our acceptance rule filters anything.

**Primary.** More than 50 percent of random_walk windows and more than 50
percent of pulse_train windows receive at least one proposed edit.

**Secondary.** The proposal rate on clean_ood is at least 0.7 times the
proposal rate on the contaminated stratum. These windows are clean, so a
detector that works should propose far less often on them than on windows with
injected defects, and a ratio near or above 1 would mean it cannot tell them
apart at all.

**Tertiary.** Among proposals on random_walk windows, level shift repair
operators are the most frequent category, matching the 18 of 53 level shift
assignments our own profile makes on that form.

## What each outcome means

**All three hold.** The weakness is confirmed as a property of quality rate
signals rather than of our profile, verified by an independently implemented
detection stack. This goes into the paper as external validation and
strengthens the argument that neither statistical rates nor model utility can
carry the acceptance decision alone.

**Primary holds, secondary fails.** AegisTS fires on these windows but still
distinguishes them from contaminated ones better than we do. The weakness is
real but partly specific to our profile, and the claim narrows accordingly.

**Primary fails.** AegisTS does not fire on clean unpredictable windows. Its
detector stack has something ours lacks, the prediction is wrong, and it is
reported as wrong. In that case the interesting question becomes what its
detector does differently, and that becomes a limitation of our profile rather
than a shared weakness.

## What this document does not predict

Nothing about whether our acceptance rule improves AegisTS. That is measured
separately in the gating experiment and is not prejudged here.

## Status

Written and committed before the AegisTS environment was built. No AegisTS code
has been run on our corpus at the time of this commit.
