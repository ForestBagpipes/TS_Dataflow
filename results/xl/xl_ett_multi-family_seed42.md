# IntroAct-TS results

Corpus: 2000 windows, source `ett`, backend preset `multi-family`.

- Curation (judge + disagreement pool): `amazon/chronos-bolt-base`, `google/timesfm-2.5-200m-pytorch`, `amazon/chronos-bolt-small`
- Transfer (never consulted during curation): `amazon/chronos-t5-small`, `surrogate-s7`
- Capabilities: {'amazon/chronos-bolt-base': ['encode', 'forecast', 'reconstruct'], 'google/timesfm-2.5-200m-pytorch': ['forecast', 'reconstruct'], 'amazon/chronos-bolt-small': ['encode', 'forecast', 'reconstruct']}

## Headline

| method | **net corpus** | repair (contaminated) | over-clean rate | damage to protected | detect F1 | action acc | rollbacks | abstain |
|---|---|---|---|---|---|---|---|---|
| no_action | **+0.000** | 0.000 | 0.000 | 0.0000 | 0.581 | 0.000 | 0 | 0.000 |
| always_clean | **-0.216** | 0.078 | 1.000 | 0.2015 | 0.581 | 0.693 | 0 | 0.000 |
| stat_only | **+0.449** | 0.585 | 0.451 | 0.0931 | 0.581 | 0.638 | 0 | 0.000 |
| quality_rank | **-0.042** | 0.022 | 0.267 | 0.0442 | 0.581 | 0.151 | 0 | 0.000 |
| introact_full | **+0.242** | 0.272 | 0.132 | 0.0205 | 0.581 | 0.224 | 1157 | 0.033 |
| ablate_no_structure | **+0.215** | 0.269 | 0.212 | 0.0370 | 0.581 | 0.305 | 709 | 0.035 |
| ablate_no_reprobe | **+0.345** | 0.388 | 0.196 | 0.0295 | 0.581 | 0.397 | 783 | 0.043 |
| ablate_no_verify | **+0.292** | 0.387 | 0.308 | 0.0655 | 0.581 | 0.532 | 0 | 0.047 |
| ablate_no_peer_calibration | **+0.242** | 0.272 | 0.129 | 0.0203 | 0.581 | 0.220 | 1154 | 0.029 |
| ablate_no_protection | **+0.340** | 0.379 | 0.198 | 0.0268 | 0.581 | 0.291 | 1282 | 0.162 |

`net corpus` is the reduction in mean normalised distance-to-truth over *every* window with a pristine reference, contaminated and protected alike. Repair and damage are trade-offs against each other and neither column alone can say whether running the pipeline was worth it; this one can.

| method | windows improved | windows worsened |
|---|---|---|
| no_action | 0 | 0 |
| always_clean | 299 | 1701 |
| stat_only | 374 | 653 |
| quality_rank | 70 | 430 |
| introact_full | 141 | 183 |
| ablate_no_structure | 183 | 318 |
| ablate_no_reprobe | 241 | 295 |
| ablate_no_verify | 314 | 479 |
| ablate_no_peer_calibration | 137 | 181 |
| ablate_no_protection | 190 | 258 |

## Transfer to models that took no part in curation

| method | amazon/chronos-t5-small | surrogate-s7 |
|---|---|---|
| no_action | -0.0000 | +0.0000 |
| always_clean | +0.0583 | +0.0322 |
| stat_only | +0.1044 | +0.1107 |
| quality_rank | +0.0671 | +0.0161 |
| introact_full | +0.0371 | +0.0679 |
| ablate_no_structure | +0.0642 | +0.0752 |
| ablate_no_reprobe | +0.0491 | +0.0841 |
| ablate_no_verify | +0.0765 | +0.0866 |
| ablate_no_peer_calibration | +0.0477 | +0.0682 |
| ablate_no_protection | +0.0644 | +0.0780 |

## Downstream transfer: train on curated data, test on pristine data

Models are trained from scratch on each method's output (1400 windows) and scored on the untouched reference series of 600 held-out windows. Values are test MSE; the arrow is the change against `no_action`.

Training-independent reference on the same test split: `seasonal_naive` MSE 15.1414.

| method | ridge_ar | dlinear |
|---|---|---|
| no_action | 14.2265 (+0.0%) | 14.2257 (+0.0%) |
| always_clean | 15.0319 (-5.7%) | 15.2240 (-7.0%) |
| stat_only | 14.2059 (+0.1%) | 14.2054 (+0.1%) |
| quality_rank | 14.2167 (+0.1%) | 14.2169 (+0.1%) |
| introact_full | 14.2262 (+0.0%) | 14.2256 (+0.0%) |
| ablate_no_structure | 14.2268 (-0.0%) | 14.2261 (-0.0%) |
| ablate_no_reprobe | 14.2130 (+0.1%) | 14.2119 (+0.1%) |
| ablate_no_verify | 14.2142 (+0.1%) | 14.2137 (+0.1%) |
| ablate_no_peer_calibration | 14.2265 (+0.0%) | 14.2258 (-0.0%) |
| ablate_no_protection | 14.2218 (+0.0%) | 14.2211 (+0.0%) |

## Repair by contamination type (IntroAct-TS full)

| contamination | NMSE before | NMSE after | reduction | action acc |
|---|---|---|---|---|
| duplicate | 0.2601 | 0.2679 | -0.030 | 0.048 |
| flatline | 0.0979 | 0.0866 | +0.115 | 0.255 |
| level_shift | 5.9692 | 4.0098 | +0.328 | 0.286 |
| missing_block | 0.1087 | 0.1058 | +0.027 | 0.226 |
| missing_scattered | 0.0274 | 0.0231 | +0.157 | 0.443 |
| noise | 0.9478 | 0.9268 | +0.022 | 0.028 |
| spike | 0.7966 | 0.5563 | +0.302 | 0.283 |

## Protection by stratum (IntroAct-TS full)

| stratum | n | modified | over-clean rate | mean damage |
|---|---|---|---|---|
| changepoint | 210 | 21 | 0.100 | 0.0132 |
| clean | 420 | 58 | 0.138 | 0.0120 |
| clean_ood | 210 | 20 | 0.095 | 0.0522 |
| hard | 210 | 48 | 0.229 | 0.0309 |
| rare_valid | 210 | 19 | 0.090 | 0.0028 |

## Rollback reasons (IntroAct-TS full)

- `ROLLED_BACK_STRUCTURE`: 387
- `ROLLED_BACK_UTILITY`: 770
- protected windows saved by a rollback: 330
- mean probe calls per window: 1.78
