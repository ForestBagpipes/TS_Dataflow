# Offline audit, heavy, 67 percent contaminated, real TSFM

Source: `results/gpu/heavy_ett_multi-family_seed42_traces.json`

Replay self check, reconstructed repair against the recorded value:

| method | replay | reported | abs error |
|---|---|---|---|
| no_action | 0.0000 | 0.0000 | 0.0000 |
| always_clean | 0.0419 | 0.0419 | 0.0000 |
| stat_only | 0.7655 | 0.7655 | 0.0000 |
| quality_rank | 0.0190 | 0.0190 | 0.0000 |
| introact_full | 0.3202 | 0.3202 | 0.0000 |
| ablate_no_structure | 0.3038 | 0.3038 | 0.0000 |
| ablate_no_reprobe | 0.5157 | 0.5157 | 0.0000 |
| ablate_no_verify | 0.4843 | 0.4843 | 0.0000 |
| ablate_no_peer_calibration | 0.3233 | 0.3233 | 0.0000 |
| ablate_no_protection | 0.5031 | 0.5031 | 0.0000 |

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
| introact_full | 153 | 51 | 0.333 | 39.86 | 29.29 | -10.57 |
| ablate_no_structure | 92 | 35 | 0.380 | 38.59 | 17.94 | -20.65 |
| ablate_no_reprobe | 99 | 24 | 0.242 | 1.38 | 23.55 | +22.18 |
| ablate_no_peer_calibration | 152 | 51 | 0.336 | 39.86 | 29.29 | -10.57 |
| ablate_no_protection | 160 | 55 | 0.344 | 55.78 | 29.86 | -25.92 |

### introact_full, split by the reason for refusal

| verdict | n | wrongly refused | rate |
|---|---|---|---|
| ROLLED_BACK_STRUCTURE | 50 | 14 | 0.280 |
| ROLLED_BACK_UTILITY | 103 | 37 | 0.359 |

### introact_full, split by operator

| action | rejections | wrongly refused | rate | total forgone | total avoided | net | median forgone |
|---|---|---|---|---|---|---|---|
| DENOISE | 3 | 1 | 0.333 | 0.87 | 0.20 | -0.67 | 0.8725 |
| IMPUTE | 138 | 42 | 0.304 | 1.32 | 29.06 | +27.75 | 0.0242 |
| RESEGMENT | 12 | 8 | 0.667 | 37.67 | 0.03 | -37.64 | 5.9451 |

### introact_full, split by contamination

| contamination or stratum | rejections | wrongly refused | rate | total forgone | total avoided | net |
|---|---|---|---|---|---|---|
| duplicate | 13 | 0 | 0.000 | 0.00 | 9.56 | +9.56 |
| flatline | 31 | 17 | 0.548 | 0.37 | 0.75 | +0.38 |
| level_shift | 13 | 8 | 0.615 | 37.74 | 1.53 | -36.21 |
| missing_block | 31 | 13 | 0.419 | 0.32 | 4.58 | +4.26 |
| missing_scattered | 11 | 11 | 1.000 | 0.34 | 0.00 | -0.34 |
| noise | 1 | 1 | 1.000 | 0.87 | 0.00 | -0.87 |
| none | 39 | 0 | 0.000 | 0.00 | 11.15 | +11.15 |
| spike | 14 | 1 | 0.071 | 0.22 | 1.72 | +1.51 |

### the mirror question, were the commits right

Of 61 committed edits, 34 moved the window closer to truth, a precision of 0.557. Mean gain on a good commit 1.8937, mean loss on a bad one 0.1201.

Note, 58 of the audited rejections had their operator parameters inferred from the policy proposal order rather than read from the trace. The replay reproduces every recorded repair number exactly, so the inference is consistent with the run.

## B  ledger by contamination, not one mean

Absolute gain is the total normalised error removed across the stratum.
It is what the corpus mean is actually weighted by.

### no_action

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| clean | 20 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| clean_ood | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| duplicate | 20 | 0.2102 | 0.2102 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| flatline | 20 | 0.0617 | 0.0617 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| hard | 10 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| level_shift | 20 | 7.6788 | 7.6788 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| missing_block | 20 | 0.0929 | 0.0929 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| missing_scattered | 20 | 0.0250 | 0.0250 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| noise | 20 | 0.9366 | 0.9366 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| rare_valid | 20 | 0.0000 | 0.0000 | +1.000 | +0.00 | 0 | 0 | 0 | n/a |
| spike | 20 | 0.8186 | 0.8186 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |

### always_clean

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.1200 | -119951819047.599 | -1.20 | 10 | 0 | 10 | 0.00 |
| clean | 20 | 0.0000 | 0.1881 | -188117758588.659 | -3.76 | 20 | 0 | 20 | 0.00 |
| clean_ood | 10 | 0.0000 | 0.1464 | -146417556747.794 | -1.46 | 10 | 0 | 10 | 0.00 |
| duplicate | 20 | 0.2102 | 0.4163 | -0.981 | -4.12 | 20 | 0 | 20 | 0.00 |
| flatline | 20 | 0.0617 | 0.1528 | -1.476 | -1.82 | 20 | 3 | 17 | 0.15 |
| hard | 10 | 0.0000 | 0.5263 | -526309160593.546 | -5.26 | 10 | 0 | 10 | 0.00 |
| level_shift | 20 | 7.6788 | 7.9019 | -0.029 | -4.46 | 20 | 5 | 15 | 0.25 |
| missing_block | 20 | 0.0929 | 0.3628 | -2.904 | -5.40 | 20 | 3 | 17 | 0.15 |
| missing_scattered | 20 | 0.0250 | 0.0884 | -2.537 | -1.27 | 20 | 6 | 14 | 0.30 |
| noise | 20 | 0.9366 | 0.3299 | +0.648 | +12.13 | 20 | 20 | 0 | 1.00 |
| rare_valid | 20 | 0.0000 | 0.1452 | -145240645835.405 | -2.90 | 20 | 0 | 20 | 0.00 |
| spike | 20 | 0.8186 | 0.1598 | +0.805 | +13.18 | 20 | 20 | 0 | 1.00 |

### stat_only

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.0538 | -53819493741.437 | -0.54 | 6 | 0 | 3 | 0.00 |
| clean | 20 | 0.0000 | 0.0629 | -62855355552.245 | -1.26 | 8 | 0 | 6 | 0.00 |
| clean_ood | 10 | 0.0000 | 0.1242 | -124181334965.370 | -1.24 | 3 | 0 | 2 | 0.00 |
| duplicate | 20 | 0.2102 | 0.4167 | -0.983 | -4.13 | 11 | 2 | 9 | 0.18 |
| flatline | 20 | 0.0617 | 0.0716 | -0.160 | -0.20 | 19 | 11 | 8 | 0.58 |
| hard | 10 | 0.0000 | 0.2104 | -210360734870.743 | -2.10 | 8 | 0 | 7 | 0.00 |
| level_shift | 20 | 7.6788 | 0.4442 | +0.942 | +144.69 | 19 | 18 | 1 | 0.95 |
| missing_block | 20 | 0.0929 | 0.3038 | -2.268 | -4.22 | 20 | 7 | 13 | 0.35 |
| missing_scattered | 20 | 0.0250 | 0.0149 | +0.404 | +0.20 | 13 | 12 | 1 | 0.92 |
| noise | 20 | 0.9366 | 0.5627 | +0.399 | +7.48 | 16 | 15 | 1 | 0.94 |
| rare_valid | 20 | 0.0000 | 0.0793 | -79258606653.222 | -1.59 | 10 | 0 | 9 | 0.00 |
| spike | 20 | 0.8186 | 0.4895 | +0.402 | +6.58 | 19 | 11 | 8 | 0.58 |

### quality_rank

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.0085 | -8524874722.043 | -0.09 | 2 | 0 | 2 | 0.00 |
| clean | 20 | 0.0000 | 0.0265 | -26515695449.951 | -0.53 | 5 | 0 | 5 | 0.00 |
| clean_ood | 10 | 0.0000 | 0.1289 | -128868795410.643 | -1.29 | 6 | 0 | 6 | 0.00 |
| duplicate | 20 | 0.2102 | 0.2429 | -0.156 | -0.66 | 5 | 0 | 5 | 0.00 |
| flatline | 20 | 0.0617 | 0.0875 | -0.418 | -0.52 | 4 | 0 | 4 | 0.00 |
| hard | 10 | 0.0000 | 0.3606 | -360575791550.393 | -3.61 | 6 | 0 | 6 | 0.00 |
| level_shift | 20 | 7.6788 | 7.7399 | -0.008 | -1.22 | 3 | 0 | 3 | 0.00 |
| missing_block | 20 | 0.0929 | 0.1024 | -0.101 | -0.19 | 3 | 1 | 2 | 0.33 |
| missing_scattered | 20 | 0.0250 | 0.0287 | -0.149 | -0.07 | 2 | 1 | 1 | 0.50 |
| noise | 20 | 0.9366 | 0.9366 | +0.000 | +0.00 | 0 | 0 | 0 | n/a |
| rare_valid | 20 | 0.0000 | 0.0559 | -55871563138.228 | -1.12 | 9 | 0 | 9 | 0.00 |
| spike | 20 | 0.8186 | 0.4991 | +0.390 | +6.39 | 8 | 8 | 0 | 1.00 |

### introact_full

| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | 0.0053 | -5275572191.247 | -0.05 | 2 | 0 | 1 | 0.00 |
| clean | 20 | 0.0000 | 0.0142 | -14162241948.608 | -0.28 | 5 | 0 | 3 | 0.00 |
| clean_ood | 10 | 0.0000 | 0.1098 | -109795399871.555 | -1.10 | 1 | 0 | 1 | 0.00 |
| duplicate | 20 | 0.2102 | 0.2122 | -0.009 | -0.04 | 6 | 2 | 4 | 0.33 |
| flatline | 20 | 0.0617 | 0.0485 | +0.214 | +0.26 | 8 | 5 | 3 | 0.62 |
| hard | 10 | 0.0000 | 0.0197 | -19692220540.002 | -0.20 | 3 | 0 | 2 | 0.00 |
| level_shift | 20 | 7.6788 | 4.7041 | +0.387 | +59.49 | 8 | 8 | 0 | 1.00 |
| missing_block | 20 | 0.0929 | 0.0841 | +0.095 | +0.18 | 7 | 5 | 2 | 0.71 |
| missing_scattered | 20 | 0.0250 | 0.0180 | +0.280 | +0.14 | 6 | 6 | 0 | 1.00 |
| noise | 20 | 0.9366 | 0.8965 | +0.043 | +0.80 | 3 | 3 | 0 | 1.00 |
| rare_valid | 20 | 0.0000 | 0.0074 | -7351222942.266 | -0.15 | 3 | 0 | 3 | 0.00 |
| spike | 20 | 0.8186 | 0.7143 | +0.127 | +2.09 | 5 | 4 | 1 | 0.80 |

### which stratum drives the corpus mean

| stratum | n | nmse before | share of total corpus error |
|---|---|---|---|
| level_shift | 20 | 7.6788 | 78.2% |
| noise | 20 | 0.9366 | 9.5% |
| spike | 20 | 0.8186 | 8.3% |
| duplicate | 20 | 0.2102 | 2.1% |
| missing_block | 20 | 0.0929 | 0.9% |
| flatline | 20 | 0.0617 | 0.6% |
| missing_scattered | 20 | 0.0250 | 0.3% |
| changepoint | 10 | 0.0000 | 0.0% |
| clean | 20 | 0.0000 | 0.0% |
| clean_ood | 10 | 0.0000 | 0.0% |
| hard | 10 | 0.0000 | 0.0% |
| rare_valid | 20 | 0.0000 | 0.0% |

### pareto view, utility gained against collateral damage

| method | net corpus gain | windows worsened | over clean rate | damage to protected |
|---|---|---|---|---|
| stat_only | +0.731 | 68 | 0.500 | 0.0961 |
| ablate_no_reprobe | +0.495 | 35 | 0.257 | 0.0583 |
| ablate_no_protection | +0.493 | 25 | 0.271 | 0.0297 |
| ablate_no_verify | +0.442 | 59 | 0.400 | 0.1181 |
| ablate_no_peer_calibration | +0.314 | 20 | 0.200 | 0.0254 |
| introact_full | +0.311 | 20 | 0.200 | 0.0254 |
| ablate_no_structure | +0.294 | 35 | 0.257 | 0.0282 |
| no_action | +0.000 | 0 | 0.000 | 0.0000 |
| quality_rank | -0.015 | 43 | 0.400 | 0.0947 |
| always_clean | -0.032 | 153 | 1.000 | 0.2085 |

Pareto frontier on gain against windows worsened: ablate_no_peer_calibration, ablate_no_protection, ablate_no_reprobe, no_action, stat_only

## C  ablation ladder on real models

| rung | configuration | status | net corpus | repair | over clean | damage | worsened |
|---|---|---|---|---|---|---|---|
| a  score only, no action | no_action | done | +0.000 | 0.000 | 0.000 | 0.0000 | 0 |
| b  repair, no verification | ablate_no_verify | done | +0.442 | 0.484 | 0.400 | 0.1181 | 59 |
| c  repair plus structure, no utility recheck | ablate_no_reprobe | done | +0.495 | 0.516 | 0.257 | 0.0583 | 35 |
| d  full agent | introact_full | done | +0.311 | 0.320 | 0.200 | 0.0254 | 20 |

Additional single mechanism ablations already run on real models:

| ablation | key | net corpus | repair | over clean | damage |
|---|---|---|---|---|---|
| no structural veto | ablate_no_structure | +0.294 | 0.304 | 0.257 | 0.0282 |
| no peer calibration | ablate_no_peer_calibration | +0.314 | 0.323 | 0.200 | 0.0254 |
| no protection of hard, rare valid, OOD | ablate_no_protection | +0.493 | 0.503 | 0.271 | 0.0297 |

Gaps on the ladder, to be filled in the next GPU session:

- no ABSTAIN only ablation exists. The refusal path is currently
  entangled with the rest of the policy, so its separate contribution
  is not measured. Needs PolicyConfig with min_confidence set to zero.
- no rung isolates rollback from veto. c and d differ by the utility
  recheck, not by whether a rejected edit is retried with another
  operator, so the value of retrying is not separated.

## D  seed coverage

| run | seeds present | count |
|---|---|---|
| heavy_ett_multi-family | 42 | 1 |
| heavy_ett_offline | 42 | 1 |
| medium_ett | 42 | 1 |
| small_ett | 42 | 1 |
| small_ett_multi-family | 42 | 1 |
| small_ett_offline | 42 | 1 |

Every headline number in the paper so far rests on a single seed, 42.
That includes the three the argument leans on most:

- repair 0.367 on small with real TSFMs
- the 2.4x gap to stat_only at 67 percent contamination
- the collapse from 0.367 to 0.141 when the structural veto is removed

None of these has an error bar. All need at least three seeds before
they can be claimed. Not run this round by instruction.

