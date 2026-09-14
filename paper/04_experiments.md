# Experiments

Skeleton. Slots marked PENDING are waiting on queued runs and are filled from
the result files named beside them. Every number already present is committed
in this repository and traceable to the file cited.

## Setup

**Corpus.** Windows of fixed length drawn from four electricity transformer
temperature files, partitioned into a contaminated stratum with seven injected
defect types and five protected strata that must not be edited: clean, hard,
rare valid, changepoint, and clean out of distribution. A sixth stratum of real
cross domain windows is used where stated. Scale is 800 windows per point for
sweeps and 2000 for the characterisation runs.

**A naming caveat carried from the corpus.** The stratum identifier for cross
domain windows is retained from the code for traceability, and those windows
are described as cross domain rather than out of distribution throughout,
because they are drawn from public benchmarks whose presence in the backends'
pretraining corpora could not be verified.

**Backends.** Frozen forecasters used only as verifiers. Ablations over the
backend pool are reported in E4.

**Metrics.** Damage is normalised error introduced on protected strata. Repair
is the reduction in normalised error on contaminated windows. Protected stratum
edits counts windows in a protected stratum that were modified. Windows
worsened counts windows whose error against the pristine series increased.

**Protocol notes.** Downstream comparisons are paired within seed, because the
seed changes both corpus sampling and model initialisation and an unpaired
aggregation charges the former to the latter. Behavioural risk is a within
corpus quantity and is never compared across corpora.

## E1, does the acceptance layer work on proposers that are not ours

| method | damage | repair | edits | protected edits | edit precision | worsened |
|---|---|---|---|---|---|---|
| *reference bound, no_action* | *0.0000* | *+0.000* | *0* | *0* | | *0* |
| statistical rule | 0.0715 | +0.366 | 446 | 226 | 0.493 | 274 |
| statistical rule, gated | 0.0016 | +0.255 | 77 | 33 | 0.571 | 22 |
| unconditional cleaner | 0.1919 | -0.014 | 800 | 520 | 0.350 | 691 |
| unconditional cleaner, gated | 0.0057 | +0.044 | 198 | 125 | 0.369 | 146 |
| ours, full | 0.0020 | +0.181 | 71 | 26 | 0.634 | 29 |
| oracle upper bound | PENDING | | | | | |
| random proposer | PENDING | | | | | |

Source `results/gating.json`. Oracle and random rows PENDING.

**Conclusion.** The layer transfers. On a statistical rule it cuts damage by a
factor of 45 while retaining 70 percent of repair. On an unconditional cleaner
it moves the net effect from harmful to beneficial without modifying the
cleaner. The gated statistical rule reaches lower damage than our own complete
system, 0.0016 against 0.0020, which is why the claim is about the layer and
not about the search. Of 1398 proposals from the unconditional cleaner, 725
were rejected on structural distance against 452 on utility, so the structural
condition is the principal gatekeeper.

## E2, does the calibrated threshold deliver its target

| alpha | lambda star | realised | classification |
|---|---|---|---|
| 0.001 | 0.005 | 0.0088 | target unreachable |
| 0.002 | 0.005 | 0.0088 | target unreachable |
| 0.005 | 0.005 | 0.0088 | target unreachable |
| 0.010 | 0.005 | 0.0088 | holds |
| 0.015 | 0.005 | 0.0088 | holds |
| 0.020 | 0.015 | 0.0100 | holds |
| 0.030 | 0.020 | 0.0200 | holds |
| 0.040 | 0.030 | 0.0425 | violation |
| 0.050 | 0.040 | 0.0500 | holds |

Source `results/conformal_samepool_stage1.json`. Stability across six
contamination rates PENDING.

**Conclusion.** The guarantee holds at every reachable target. Three targets
lie below a floor of 0.0088 set jointly by the action space and the grid, where
no solution exists and the procedure correctly returns the most conservative
threshold. One isolated violation at 0.040 overshoots by 0.0025 with both
neighbours holding, which is finite sample fluctuation. Hand set thresholds on
the same data realise 0.0200, 0.1025 and 0.1562 with nothing stated about any
of them. Calibrating on one corpus and applying to an independently sampled one
overshoots by 20 to 50 percent relative, which is the cost of violating
exchangeability and is reported as the deployment caveat.

## E3, a condition at execution time against a term in the objective

PENDING, from `results/soft_vs_hard.json`. A soft penalty sweep over mu against
a hard condition sweep over tau, same proposer and same operators, presented as
the repair achievable at or below each damage budget.

**Conclusion.** PENDING.

## E4, what the verification signal measures

| variant | corpus AUROC | 95 percent CI |
|---|---|---|
| behavioural risk, as used | 0.468 | [0.442, 0.494] |
| peer calibrated | 0.468 | |
| global standardised | 0.467 | |
| predictability residual | 0.551 | [0.524, 0.577] |

Source `results/decorrelate.json`.

Level uncertainty and local unpredictability, isolated by a two by two with
unit variance normalisation, contribute 0.203 and 0.141 and are roughly
additive: predicted 0.196 for a cell with both, measured 0.210. Source
`results/level_2x2.json`.

Four generator forms of clean unpredictable data are elevated at 0.705 to
0.760. Dropping the two whose structure resembles an injected defect leaves
0.715 at p 9.5e-13 over 105 windows. Source `results/ladder.json` and
`docs/ood_form_split.md`.

Four frozen backends reproduce the level effect, weakest at p 1.3e-04. Source
`results/cross_model.json`.

**Conclusion.** The signal measures predictability and not data quality. The
correction is real and insufficient: it removes the false alarm on all four
generator forms, from 0.705 to 0.760 down to 0.504 to 0.527, and it reduces
detection of level displacement from 0.495 to 0.375, because both are the same
quantity to this signal. Fully corrected the signal reaches 0.551, which is why
a condition that never consults the model is required rather than helpful.

## E5, downstream effect

| model | unconditional cleaner | same, gated |
|---|---|---|
| patchtst | -569.10% | -3.26% |
| dlinear | -102.03% | -0.18% |
| ridge_ar | -95.89% | -0.15% |

Paired within seed, three seeds. Source `results/downstream_gated.json`.

**Conclusion.** The evidence here is defensive. Without the acceptance step an
aggressive pipeline degrades downstream error by two to eleven fold, and with
it the same pipeline returns to within a few percent of not curating. Three
independently trained models agree in direction at one to two orders of
magnitude above any noise floor in the experiment. For the conservative
methods no measurable difference is observed: every effect sits at or below its
own model's paired noise floor of 0.27 to 2.99 percent. The cause is
mechanical, since our method edits 62 of 800 windows and leaves 92 percent of
the corpus byte identical, and dilution is ruled out by evaluating on the 515
edited windows only, which leaves the effect unchanged.

## E6, ablation

| rung | damage | repair | edits |
|---|---|---|---|
| no action | 0.0000 | +0.000 | 0 |
| no verification | 0.1181 | +0.484 | 119 |
| no utility recheck | 0.0583 | +0.516 | 89 |
| no structural condition | 0.0282 | +0.304 | 76 |
| no peer calibration | 0.0254 | +0.323 | 57 |
| single step | 0.0182 | +0.312 | 34 |
| no abstain | 0.0254 | +0.327 | 58 |
| full | 0.0254 | +0.320 | 57 |

Source `results/ablations/ablations.json`, at the heavy scale of 210 windows,
so this table supports the ordering of rungs and not per stratum conclusions.

**Conclusion.** Verification is the component. Removing it multiplies damage by
4.6 and doubles the edits for fifty percent more repair. Within verification the
utility recheck matters more than the structural condition on this axis, 0.0583
against 0.0282. Peer calibration and abstention show no measurable effect and
are reported as such rather than defended.

## E7, the cost of the layer

| veto reason | blocked | would have helped | forgone rate |
|---|---|---|---|
| utility condition | 768 | 228 | 0.297 |
| structural condition | 386 | 76 | 0.197 |
| all | 1157 | 304 of 1154 replayable | 0.263 |

Source `results/shield_properties.json`.

**Conclusion.** About a quarter of vetoes sacrifice a beneficial edit, and the
condition that consults the model is the less accurate of the two. This is
reported as partial satisfaction of minimal interference with the number
attached. It is a different measurement from the threshold sweep, which finds
that loosening the threshold buys no aggregate repair, and neither corroborates
the other: individually beneficial blocked edits have their aggregate
contribution cancelled by damage from edits admitted at the same threshold.
