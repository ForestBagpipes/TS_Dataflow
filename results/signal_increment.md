# Does the behavioural signal add information over the statistical profile

Measured on the 2000 window run with real TSFMs. This is the paper's first
claim, that a frozen model's behaviour carries risk information a statistical
profile does not, so it needs a direct answer rather than an inference from
downstream numbers.

## The headline answer is no, not as a detector

Separating the contaminated stratum from everything else:

| evidence | AUROC |
|---|---|
| statistical profile alone, `defect_strength` | **0.672** |
| behavioural signal alone, `behav_risk` | **0.468** |
| both, standardised and summed | 0.588 |

The behavioural signal alone is below chance. Adding it to the statistical
profile makes the combination worse than the profile by itself.

## Per contamination, against clean windows

| contamination | n | behaviour | statistics |
|---|---|---|---|
| spike | 106 | **0.669** | 0.562 |
| duplicate | 105 | **0.573** | 0.489 |
| flatline | 106 | 0.576 | **0.824** |
| missing_block | 106 | 0.558 | **0.917** |
| missing_scattered | 106 | 0.498 | 0.650 |
| level_shift | 105 | 0.495 | **0.816** |
| noise | 106 | 0.413 | 0.490 |

Behaviour wins on exactly two of seven. On spike it is clearly better, 0.669
against 0.562. On duplicate it is the only signal that works at all, 0.573
against a statistical 0.489 that is indistinguishable from chance, which makes
sense because a repeated segment leaves no local statistical trace.

Everywhere else the profile is better, and on the three defects with the
strongest statistical signature, missing_block, flatline and level_shift, it is
far better, 0.92, 0.82 and 0.82 against a behavioural signal hovering near 0.5.

## What this does and does not overturn

It does not contradict the method. Corruption in IntroAct-TS is the conjunction
of statistical and behavioural evidence, and the statistical half is doing the
detecting, which is what these numbers say it should do. The end to end
detection F1 of 0.581 comes from the joint posterior, not from either stream
alone.

It does contradict the claim as currently worded. Saying that behavioural
signals provide risk information beyond static profiles is not supported at
corpus level. Two narrower statements are supported and are worth more than
the broad one:

1. On defects that leave no local statistical trace, the behavioural signal is
   the only evidence available. Duplicate segments are the case in this corpus.
2. On isolated spikes the behavioural signal is genuinely stronger than the
   profile, which fits the mechanism, since a spike wrecks reconstruction at
   the point it sits.

The larger role the behavioural signal actually plays is not detection at all.
It is verification, the delta in utility that decides whether a proposed edit
is committed. Nothing here weakens that, and the ablation ladder measures it
separately.

## Why this only appeared now

The 210 window corpus had 20 windows per contamination type. An AUROC estimated
on 20 positives against 20 clean windows has a standard error wide enough to
hide a signal sitting at chance. At 105 per type the estimates are stable
enough to rank.

## Consequence for the paper

The first contribution has to be reworded to what the evidence supports, and
the per contamination table above belongs in the paper rather than a single
corpus level AUROC, since the corpus level number averages a signal that is
strong on one defect, uniquely available on another, and absent on five.
