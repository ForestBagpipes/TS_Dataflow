# Offline audit, small, 37 percent contaminated, real TSFM

Source: `results/gpu/small_ett_multi-family_seed42_traces.json`

Replay self check, reconstructed repair against the recorded value:

| method | replay | reported | abs error |
|---|---|---|---|
| no_action | 0.0000 | 0.0000 | 0.0000 |
| always_clean | -0.0266 | -0.0266 | 0.0000 |
| stat_only | 0.1676 | 0.1676 | 0.0000 |
| quality_rank | -0.0025 | -0.0025 | 0.0000 |
| introact_full | 0.3672 | 0.3672 | 0.0000 |
| ablate_no_structure | 0.1407 | 0.1407 | 0.0000 |
| ablate_no_reprobe | 0.3914 | 0.3914 | 0.0000 |
| ablate_no_verify | 0.3817 | 0.3817 | 0.0000 |
| ablate_no_peer_calibration | 0.3829 | 0.3829 | 0.0000 |
| ablate_no_protection | 0.3810 | 0.3810 | 0.0000 |

Worst absolute error 0.0000. The replay is exact, so the
counterfactuals below rest on the same series the run produced.

## A  rollback audit, was the refusal right

Every rejected edit is re applied offline and scored against the
pristine reference. An edit that would have reduced the distance to
truth was wrongly refused and its gain was thrown away. An edit that
would not have is a rejection that protected the data.

Totals are the number that settles it. If refusing costs more in
forgone gain than it saves in avoided harm, the rule is too strict
whatever the rate looks like.

| method | rejections | wrongly refused | rate | total gain forgone | total harm avoided | net of refusing |
|---|---|---|---|---|---|---|
| introact_full | 55 | 14 | 0.255 | 0.54 | 10.71 | +10.17 |
| ablate_no_structure | 36 | 10 | 0.278 | 7.62 | 6.76 | -0.86 |
| ablate_no_reprobe | 38 | 7 | 0.184 | 0.41 | 9.74 | +9.33 |
| ablate_no_peer_calibration | 55 | 14 | 0.255 | 0.54 | 10.71 | +10.17 |
| ablate_no_protection | 59 | 14 | 0.237 | 0.54 | 11.28 | +10.74 |

### introact_full, split by the reason for refusal

| verdict | n | wrongly refused | rate |
|---|---|---|---|
| ROLLED_BACK_STRUCTURE | 17 | 5 | 0.294 |
| ROLLED_BACK_UTILITY | 38 | 9 | 0.237 |

### introact_full, split by operator

| action | rejections | wrongly refused | rate | total forgone | total avoided | net | median forgone |
|---|---|---|---|---|---|---|---|
| DESPIKE | 1 | 0 | 0.000 | 0.00 | 0.04 | +0.04 | 0.0000 |
| IMPUTE | 51 | 13 | 0.255 | 0.47 | 10.67 | +10.20 | 0.0124 |
| RESEGMENT | 3 | 1 | 0.333 | 0.07 | 0.00 | -0.07 | 0.0719 |

### introact_full, split by contamination

| contamination or stratum | rejections | wrongly refused | rate | total forgone | total avoided | net |
|---|---|---|---|---|---|---|
| flatline | 8 | 4 | 0.500 | 0.34 | 1.29 | +0.94 |
| level_shift | 2 | 0 | 0.000 | 0.00 | 2.48 | +2.48 |
| missing_block | 6 | 5 | 0.833 | 0.08 | 0.02 | -0.06 |
| missing_scattered | 4 | 4 | 1.000 | 0.04 | 0.00 | -0.04 |
| noise | 1 | 1 | 1.000 | 0.07 | 0.00 | -0.07 |
| none | 33 | 0 | 0.000 | 0.00 | 6.92 | +6.92 |
| spike | 1 | 0 | 0.000 | 0.00 | 0.00 | +0.00 |

### the mirror question, were the commits right

Of 18 committed edits, 8 moved the window closer to truth, a precision of 0.444. Mean gain on a good commit 1.8600, mean loss on a bad one 0.3726.

Note, 22 of the audited rejections had their operator parameters inferred from the policy proposal order rather than read from the trace. The replay reproduces every recorded repair number exactly, so the inference is consistent with the run.

## B  ledger by contamination, not one mean

Absolute gain is the total normalised error removed across the stratum.
It is what the corpus mean is actually weighted by.

### no_action

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| clean | 20 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| clean_ood | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| duplicate | 5 | 0.2204 | 0.2204 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| flatline | 5 | 0.0574 | 0.0574 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| hard | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| level_shift | 5 | 4.7604 | 4.7604 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| missing_block | 5 | 0.0606 | 0.0606 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| missing_scattered | 5 | 0.0199 | 0.0199 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| noise | 5 | 0.8268 | 0.8268 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| rare_valid | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| spike | 5 | 0.5253 | 0.5253 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |

### always_clean

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.0642 | -64245360447.192 | -0.64 | 10 | 0 | 10 | 0.00 |
| clean | 20 | 0.0000 | 0.2088 | -208778062863.741 | -4.18 | 20 | 0 | 20 | 0.00 |
| clean_ood | 10 | 0.0000 | 0.0716 | -71595671411.951 | -0.72 | 10 | 0 | 10 | 0.00 |
| duplicate | 5 | 0.2204 | 0.2975 | -0.350 | -0.39 | 5 | 0 | 5 | 0.00 |
| flatline | 5 | 0.0574 | 0.2567 | -3.470 | -1.00 | 5 | 1 | 4 | 0.20 |
| hard | 10 | 0.0000 | 0.4897 | -489668420326.831 | -4.90 | 10 | 0 | 10 | 0.00 |
| level_shift | 5 | 4.7604 | 5.4530 | -0.145 | -3.46 | 5 | 2 | 3 | 0.40 |
| missing_block | 5 | 0.0606 | 0.0952 | -0.571 | -0.17 | 5 | 3 | 2 | 0.60 |
| missing_scattered | 5 | 0.0199 | 0.1081 | -4.431 | -0.44 | 5 | 1 | 4 | 0.20 |
| noise | 5 | 0.8268 | 0.3046 | +0.632 | +2.61 | 5 | 5 | 0 | 1.00 |
| rare_valid | 10 | 0.0000 | 0.1997 | -199745559353.981 | -2.00 | 10 | 0 | 10 | 0.00 |
| spike | 5 | 0.5253 | 0.1280 | +0.756 | +1.99 | 5 | 5 | 0 | 1.00 |

### stat_only

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| clean | 20 | 0.0000 | 0.0862 | -86207954929.971 | -1.72 | 11 | 0 | 11 | 0.00 |
| clean_ood | 10 | 0.0000 | 0.0416 | -41624587112.828 | -0.42 | 4 | 0 | 2 | 0.00 |
| duplicate | 5 | 0.2204 | 0.2215 | -0.005 | -0.01 | 1 | 0 | 1 | 0.00 |
| flatline | 5 | 0.0574 | 0.1814 | -2.158 | -0.62 | 5 | 3 | 2 | 0.60 |
| hard | 10 | 0.0000 | 0.1647 | -164701480516.382 | -1.65 | 8 | 0 | 7 | 0.00 |
| level_shift | 5 | 4.7604 | 4.1398 | +0.130 | +3.10 | 3 | 1 | 2 | 0.33 |
| missing_block | 5 | 0.0606 | 0.0467 | +0.230 | +0.07 | 5 | 4 | 1 | 0.80 |
| missing_scattered | 5 | 0.0199 | 0.0420 | -1.110 | -0.11 | 4 | 3 | 1 | 0.75 |
| noise | 5 | 0.8268 | 0.5678 | +0.313 | +1.29 | 5 | 5 | 0 | 1.00 |
| rare_valid | 10 | 0.0000 | 0.1542 | -154194310708.971 | -1.54 | 2 | 0 | 2 | 0.00 |
| spike | 5 | 0.5253 | 0.1871 | +0.644 | +1.69 | 5 | 3 | 2 | 0.60 |

### quality_rank

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.0158 | -15809503517.393 | -0.16 | 3 | 0 | 3 | 0.00 |
| clean | 20 | 0.0000 | 0.0208 | -20832370723.178 | -0.42 | 3 | 0 | 3 | 0.00 |
| clean_ood | 10 | 0.0000 | 0.0441 | -44135254469.457 | -0.44 | 5 | 0 | 5 | 0.00 |
| duplicate | 5 | 0.2204 | 0.2278 | -0.034 | -0.04 | 1 | 0 | 1 | 0.00 |
| flatline | 5 | 0.0574 | 0.0474 | +0.175 | +0.05 | 1 | 1 | 0 | 1.00 |
| hard | 10 | 0.0000 | 0.0741 | -74065555343.732 | -0.74 | 2 | 0 | 2 | 0.00 |
| level_shift | 5 | 4.7604 | 4.7812 | -0.004 | -0.10 | 2 | 1 | 1 | 0.50 |
| missing_block | 5 | 0.0606 | 0.0458 | +0.245 | +0.07 | 2 | 2 | 0 | 1.00 |
| missing_scattered | 5 | 0.0199 | 0.0339 | -0.702 | -0.07 | 2 | 0 | 2 | 0.00 |
| noise | 5 | 0.8268 | 0.8268 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| rare_valid | 10 | 0.0000 | 0.0038 | -3800407623.718 | -0.04 | 2 | 0 | 2 | 0.00 |
| spike | 5 | 0.5253 | 0.5242 | +0.002 | +0.01 | 1 | 1 | 0 | 1.00 |

### introact_full

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| clean | 20 | 0.0000 | 0.0230 | -23000620748.341 | -0.46 | 2 | 0 | 2 | 0.00 |
| clean_ood | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| duplicate | 5 | 0.2204 | 0.2215 | -0.005 | -0.01 | 1 | 0 | 1 | 0.00 |
| flatline | 5 | 0.0574 | 0.0533 | +0.072 | +0.02 | 1 | 1 | 0 | 1.00 |
| hard | 10 | 0.0000 | 0.0268 | -26791692703.550 | -0.27 | 2 | 0 | 2 | 0.00 |
| level_shift | 5 | 4.7604 | 2.5443 | +0.466 | +11.08 | 3 | 2 | 1 | 0.67 |
| missing_block | 5 | 0.0606 | 0.0401 | +0.338 | +0.10 | 3 | 2 | 1 | 0.67 |
| missing_scattered | 5 | 0.0199 | 0.0148 | +0.255 | +0.03 | 3 | 2 | 1 | 0.67 |
| noise | 5 | 0.8268 | 0.8268 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| rare_valid | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 1 | 0 | 0 | n/a |
| spike | 5 | 0.5253 | 0.3937 | +0.251 | +0.66 | 1 | 1 | 0 | 1.00 |

### which stratum drives the corpus mean

| stratum | n | nmse before | share of total corpus error |
|---|---|---|---|
| level_shift | 5 | 4.7604 | 73.6% |
| noise | 5 | 0.8268 | 12.8% |
| spike | 5 | 0.5253 | 8.1% |
| duplicate | 5 | 0.2204 | 3.4% |
| missing_block | 5 | 0.0606 | 0.9% |
| flatline | 5 | 0.0574 | 0.9% |
| missing_scattered | 5 | 0.0199 | 0.3% |
| changepoint | 10 | 0.0000 | 0.0% |
| clean | 20 | 0.0000 | 0.0% |
| clean_ood | 10 | 0.0000 | 0.0% |
| hard | 10 | 0.0000 | 0.0% |
| rare_valid | 10 | 0.0000 | 0.0% |

### pareto view, utility gained against collateral damage

| method | net corpus gain | windows worsened | over clean rate | damage to protected |
|---|---|---|---|---|
| no_action | +0.000 | 0 | 0.000 | 0.0000 |
| always_clean | +0.000 | 0 | 1.000 | 0.2071 |
| stat_only | +0.000 | 0 | 0.417 | 0.0888 |
| quality_rank | +0.000 | 0 | 0.250 | 0.0299 |
| introact_full | +0.000 | 0 | 0.083 | 0.0121 |
| ablate_no_structure | +0.000 | 0 | 0.167 | 0.0222 |
| ablate_no_reprobe | +0.000 | 0 | 0.200 | 0.0268 |
| ablate_no_verify | +0.000 | 0 | 0.283 | 0.0568 |
| ablate_no_peer_calibration | +0.000 | 0 | 0.083 | 0.0121 |
| ablate_no_protection | +0.000 | 0 | 0.150 | 0.0200 |

Pareto frontier on gain against windows worsened: ablate_no_peer_calibration, ablate_no_protection, ablate_no_reprobe, ablate_no_structure, ablate_no_verify, always_clean, introact_full, no_action, quality_rank, stat_only

## C  ablation ladder on real models

| rung | configuration | status | net corpus | repair | over clean | damage | worsened |
|---|---|---|---|---|---|---|---|
| a  score only, no action | no_action | done | +0.000 | 0.000 | 0.000 | 0.0000 | 0 |
| b  repair, no verification | ablate_no_verify | done | +0.000 | 0.382 | 0.283 | 0.0568 | 0 |
| c  repair plus structure, no utility recheck | ablate_no_reprobe | done | +0.000 | 0.391 | 0.200 | 0.0268 | 0 |
| d  full agent | introact_full | done | +0.000 | 0.367 | 0.083 | 0.0121 | 0 |

Additional single mechanism ablations already run on real models:

| ablation | key | net corpus | repair | over clean | damage |
|---|---|---|---|---|---|
| no structural veto | ablate_no_structure | +0.000 | 0.141 | 0.167 | 0.0222 |
| no peer calibration | ablate_no_peer_calibration | +0.000 | 0.383 | 0.083 | 0.0121 |
| no protection of hard, rare valid, OOD | ablate_no_protection | +0.000 | 0.381 | 0.150 | 0.0200 |

Gaps on the ladder, to be filled in the next GPU session:

- no ABSTAIN only ablation exists. The refusal path is currently
  entangled with the rest of the policy, so its separate contribution
  is not measured. Needs PolicyConfig with min_confidence set to zero.
- no rung isolates rollback from veto. c and d differ by the utility
  recheck, not by whether a rejected edit is retried with another
  operator, so the value of retrying is not separated.

