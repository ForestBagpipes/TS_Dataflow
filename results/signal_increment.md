# What the behavioural signal can and cannot separate

Measured on the 2000 window run with real TSFMs. The first version of this
document reported a corpus level AUROC of 0.468 and read it as the behavioural
signal being useless. That reading was wrong, and the reason it was wrong is
the interesting part.

## The calibration question, settled

`behav_risk` in the traces is the peer calibrated quantity, not the raw signal.
The path is `calibrate()` computing `z = (behaviours - centers) / spreads` with
centres and spreads taken from the profile matched peer group, then
`risk = z @ w`, which reaches `RiskState.behav_risk` and the trace summary
unchanged. So 0.468 is already what the method uses.

Running the same measurement on the global standardisation ablation, which
replaces the peer group with the whole corpus, gives 0.467. The two are
indistinguishable, and they stay indistinguishable per contamination type, with
every pair within 0.03. **Peer calibration is not what is going on here.**

## What is going on: the negative class

The per type numbers are computed against clean windows. The corpus level
number is computed against every non contaminated stratum. Those are different
questions, and separating them locates the failure exactly.

| negative class | n | behaviour | statistics |
|---|---|---|---|
| clean | 420 | 0.540 | 0.678 |
| hard | 210 | 0.503 | 0.656 |
| changepoint | 210 | 0.485 | 0.762 |
| rare_valid | 210 | 0.466 | 0.737 |
| **clean_ood** | 210 | **0.274** | 0.518 |
| all protected | 1260 | 0.468 | 0.672 |

The mechanism is one column of medians:

| stratum | median behavioural risk |
|---|---|
| **clean_ood** | **+0.473** |
| rare_valid | +0.108 |
| changepoint | +0.071 |
| **contaminated** | **+0.063** |
| hard | +0.044 |
| clean | +0.020 |

**Clean out of distribution windows carry a behavioural risk seven times that
of the contaminated stratum.** A random walk, a staircase, a pulse train and a
sawtooth are internally consistent and undamaged, and a frozen forecaster is
far worse on them than on a window with an injected spike. Rare valid and
changepoint sit above contaminated too, by smaller margins.

So the behavioural signal separates dirty from clean at 0.540, which is weak
but real, and then inverts to 0.274 against clean but unfamiliar data. Pooling
the strata averages a weak positive against a strong negative and lands at
0.468.

## This is the paper's premise, measured

The problem statement says that trend turns, regime switches, extreme peaks and
out of distribution samples raise prediction error without being contamination,
and that separating those from real defects is the hard part. The table above is
that claim with numbers on it: ordered by how alarmed the model gets, the most
alarming windows in the corpus are the ones that are perfectly fine.

It also explains the clean_ood finding recorded separately. 96 of 210 clean_ood
windows were labelled contaminated, and now it is clear why: they have the
highest behavioural risk in the corpus, the statistical profile cannot separate
them either at 0.518, and the OOD hypothesis that exists to protect them never
fires because of a threshold bug. All three lines of defence are down at once
for that stratum.

## Where behaviour is the only evidence there is

Against clean windows, per contamination type:

| contamination | n | behaviour | statistics |
|---|---|---|---|
| spike | 106 | **0.669** | 0.562 |
| duplicate | 105 | **0.573** | 0.489 |
| flatline | 106 | 0.576 | **0.824** |
| missing_block | 106 | 0.558 | **0.917** |
| missing_scattered | 106 | 0.498 | 0.650 |
| level_shift | 105 | 0.495 | **0.816** |
| noise | 106 | 0.413 | 0.490 |

Duplicate is the case that matters most. A repeated segment leaves no local
statistical trace, the profile scores 0.489 which is a coin flip, and the
behavioural signal is the only thing that sees it at all. Spike is the case
where behaviour is simply stronger, which fits the mechanism, since a spike
wrecks reconstruction exactly where it sits.

## What the contribution should claim

Not that behavioural signals beat statistical profiles at detection. They do
not, and the honest division of labour is sharper anyway:

**Statistics detect, behaviour verifies.** Detecting whether a window is dirty
is something a statistical profile does better wherever the defect leaves a
local trace. What a profile cannot do is say whether an edit made the model
better off, and that question can only be put to the model. The behavioural
signal carries the acceptance decision, not the detection.

Two narrower detection claims survive and are worth more than the broad one.
On defects with no local statistical trace the behavioural signal is the only
evidence available. On isolated spikes it is genuinely stronger.

And one claim that is new, from the table above: **the behavioural signal is
actively misleading on clean out of distribution data, which is precisely the
case the method exists to protect.** That is an argument for the conjunction
rule rather than against it.

## A note on the combination

An earlier version compared a standardised sum of the two signals, 0.588,
against statistics alone, 0.672, and read the drop as evidence that adding
behaviour hurts. That combination is a strawman the system never uses. The
method combines the two through the hypothesis posterior, whose end to end
detection F1 is 0.581. The posterior probabilities are not currently exported
in the traces, so a like for like AUROC against the profile is deferred to the
next run, and the standardised sum should not appear in the paper.

## Why none of this was visible at 210 windows

Twenty positives per contamination type against twenty clean windows gives an
AUROC standard error wide enough to hide a signal sitting at chance, and the
protected strata had ten members each, which cannot support a per stratum
breakdown at all. Every number in this document needed the larger corpus.
