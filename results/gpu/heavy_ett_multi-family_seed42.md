# IntroAct-TS results

Corpus: 210 windows, source `ett`, backend preset `multi-family`.

- Curation (judge + disagreement pool): `amazon/chronos-bolt-base`, `google/timesfm-2.5-200m-pytorch`, `amazon/chronos-bolt-small`
- Transfer (never consulted during curation): `amazon/chronos-t5-small`, `surrogate-s7`
- Capabilities: {'amazon/chronos-bolt-base': ['encode', 'forecast', 'reconstruct'], 'google/timesfm-2.5-200m-pytorch': ['forecast', 'reconstruct'], 'amazon/chronos-bolt-small': ['encode', 'forecast', 'reconstruct']}

## Headline

| method | **net corpus** | repair (contaminated) | over-clean rate | damage to protected | detect F1 | action acc | rollbacks | abstain |
|---|---|---|---|---|---|---|---|---|
| no_action | **+0.000** | 0.000 | 0.000 | 0.0000 | 0.729 | 0.000 | 0 | 0.000 |
| always_clean | **-0.032** | 0.042 | 1.000 | 0.2085 | 0.729 | 0.707 | 0 | 0.000 |
| stat_only | **+0.731** | 0.766 | 0.500 | 0.0961 | 0.729 | 0.643 | 0 | 0.000 |
| quality_rank | **-0.015** | 0.019 | 0.400 | 0.0947 | 0.729 | 0.114 | 0 | 0.000 |
| introact_full | **+0.311** | 0.320 | 0.200 | 0.0254 | 0.729 | 0.257 | 153 | 0.033 |
| ablate_no_structure | **+0.294** | 0.304 | 0.257 | 0.0282 | 0.729 | 0.343 | 92 | 0.033 |
| ablate_no_reprobe | **+0.495** | 0.516 | 0.257 | 0.0583 | 0.729 | 0.443 | 99 | 0.048 |
| ablate_no_verify | **+0.442** | 0.484 | 0.400 | 0.1181 | 0.729 | 0.550 | 0 | 0.052 |
| ablate_no_peer_calibration | **+0.314** | 0.323 | 0.200 | 0.0254 | 0.738 | 0.250 | 152 | 0.043 |
| ablate_no_protection | **+0.493** | 0.503 | 0.271 | 0.0297 | 0.729 | 0.314 | 160 | 0.119 |

`net corpus` is the reduction in mean normalised distance-to-truth over *every* window with a pristine reference, contaminated and protected alike. Repair and damage are trade-offs against each other and neither column alone can say whether running the pipeline was worth it; this one can.

| method | windows improved | windows worsened |
|---|---|---|
| no_action | 0 | 0 |
| always_clean | 57 | 153 |
| stat_only | 76 | 68 |
| quality_rank | 10 | 43 |
| introact_full | 33 | 20 |
| ablate_no_structure | 37 | 35 |
| ablate_no_reprobe | 50 | 35 |
| ablate_no_verify | 56 | 59 |
| ablate_no_peer_calibration | 33 | 20 |
| ablate_no_protection | 41 | 25 |

## Transfer to models that took no part in curation

| method | amazon/chronos-t5-small | surrogate-s7 |
|---|---|---|
| no_action | +0.0105 | +0.0000 |
| always_clean | +0.0700 | +0.0293 |
| stat_only | +0.2724 | +0.3025 |
| quality_rank | +0.0687 | +0.0130 |
| introact_full | +0.0723 | +0.0882 |
| ablate_no_structure | +0.0697 | +0.0936 |
| ablate_no_reprobe | +0.1476 | +0.1834 |
| ablate_no_verify | +0.1360 | +0.1899 |
| ablate_no_peer_calibration | +0.0705 | +0.0887 |
| ablate_no_protection | +0.1304 | +0.1600 |

## Downstream transfer: train on curated data, test on pristine data

Models are trained from scratch on each method's output (147 windows) and scored on the untouched reference series of 63 held-out windows. Values are test MSE; the arrow is the change against `no_action`.

Training-independent reference on the same test split: `seasonal_naive` MSE 5.2759.

| method | ridge_ar | dlinear |
|---|---|---|
| no_action | 4.3376 (+0.0%) | 4.3311 (+0.0%) |
| always_clean | 4.5389 (-4.6%) | 4.7106 (-8.8%) |
| stat_only | 4.3499 (-0.3%) | 4.3440 (-0.3%) |
| quality_rank | 4.3901 (-1.2%) | 4.3915 (-1.4%) |
| introact_full | 4.3359 (+0.0%) | 4.3299 (+0.0%) |
| ablate_no_structure | 4.3343 (+0.1%) | 4.3283 (+0.1%) |
| ablate_no_reprobe | 4.3305 (+0.2%) | 4.3245 (+0.2%) |
| ablate_no_verify | 4.3457 (-0.2%) | 4.3398 (-0.2%) |
| ablate_no_peer_calibration | 4.3358 (+0.0%) | 4.3298 (+0.0%) |
| ablate_no_protection | 4.3397 (-0.0%) | 4.3338 (-0.1%) |

## Repair by contamination type (IntroAct-TS full)

| contamination | NMSE before | NMSE after | reduction | action acc |
|---|---|---|---|---|
| duplicate | 0.2102 | 0.2122 | -0.009 | 0.200 |
| flatline | 0.0617 | 0.0485 | +0.214 | 0.300 |
| level_shift | 7.6788 | 4.7041 | +0.387 | 0.400 |
| missing_block | 0.0929 | 0.0841 | +0.095 | 0.300 |
| missing_scattered | 0.0250 | 0.0180 | +0.280 | 0.300 |
| noise | 0.9366 | 0.8965 | +0.043 | 0.100 |
| spike | 0.8186 | 0.7143 | +0.127 | 0.200 |

## Protection by stratum (IntroAct-TS full)

| stratum | n | modified | over-clean rate | mean damage |
|---|---|---|---|---|
| changepoint | 10 | 2 | 0.200 | 0.0053 |
| clean | 20 | 5 | 0.250 | 0.0142 |
| clean_ood | 10 | 1 | 0.100 | 0.1098 |
| hard | 10 | 3 | 0.300 | 0.0197 |
| rare_valid | 20 | 3 | 0.150 | 0.0074 |

## Rollback reasons (IntroAct-TS full)

- `ROLLED_BACK_STRUCTURE`: 50
- `ROLLED_BACK_UTILITY`: 103
- protected windows saved by a rollback: 23
- mean probe calls per window: 2.02
