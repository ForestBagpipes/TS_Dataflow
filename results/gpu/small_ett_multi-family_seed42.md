# IntroAct-TS results

Corpus: 95 windows, source `ett`, backend preset `multi-family`.

- Curation (judge + disagreement pool): `amazon/chronos-bolt-base`, `google/timesfm-2.5-200m-pytorch`, `amazon/chronos-bolt-small`
- Transfer (never consulted during curation): `amazon/chronos-t5-small`, `surrogate-s7`
- Capabilities: {'amazon/chronos-bolt-base': ['encode', 'forecast', 'reconstruct'], 'google/timesfm-2.5-200m-pytorch': ['forecast', 'reconstruct'], 'amazon/chronos-bolt-small': ['encode', 'forecast', 'reconstruct']}

## Headline

| method | detect F1 | action acc | repair NMSE red. | over-clean rate | damage to protected | rollbacks | abstain |
|---|---|---|---|---|---|---|---|
| no_action | 0.541 | 0.000 | 0.000 | 0.000 | 0.0000 | 0 | 0.000 |
| always_clean | 0.541 | 0.686 | -0.027 | 1.000 | 0.2071 | 0 | 0.000 |
| stat_only | 0.541 | 0.657 | 0.168 | 0.433 | 0.0839 | 0 | 0.000 |
| quality_rank | 0.541 | 0.257 | 0.031 | 0.217 | 0.0537 | 0 | 0.000 |
| introact_full | 0.541 | 0.257 | -0.050 | 0.100 | 0.0121 | 56 | 0.032 |
| ablate_no_structure | 0.541 | 0.314 | -0.030 | 0.183 | 0.0273 | 35 | 0.032 |
| ablate_no_reprobe | 0.541 | 0.371 | -0.046 | 0.200 | 0.0286 | 39 | 0.042 |
| ablate_no_verify | 0.541 | 0.514 | -0.041 | 0.300 | 0.0309 | 0 | 0.042 |
| ablate_no_peer_calibration | 0.558 | 0.286 | -0.032 | 0.100 | 0.0121 | 55 | 0.032 |
| ablate_no_protection | 0.541 | 0.286 | -0.052 | 0.150 | 0.0171 | 60 | 0.105 |

## Transfer to models that took no part in curation

| method | amazon/chronos-t5-small | surrogate-s7 |
|---|---|---|
| no_action | -0.0037 | +0.0000 |
| always_clean | +0.1165 | +0.0147 |
| stat_only | +0.1115 | +0.0286 |
| quality_rank | +0.1379 | +0.0327 |
| introact_full | +0.0020 | -0.0038 |
| ablate_no_structure | -0.0012 | -0.0037 |
| ablate_no_reprobe | -0.0256 | -0.0073 |
| ablate_no_verify | -0.0059 | +0.0070 |
| ablate_no_peer_calibration | -0.0125 | -0.0027 |
| ablate_no_protection | +0.0012 | -0.0005 |

## Downstream transfer: train on curated data, test on pristine data

Models are trained from scratch on each method's output (66 windows) and scored on the untouched reference series of 29 held-out windows. Values are test MSE; the arrow is the change against `no_action`.

Training-independent reference on the same test split: `seasonal_naive` MSE 2.3997.

| method | ridge_ar | dlinear |
|---|---|---|
| no_action | 1.6176 (+0.0%) | 1.6243 (+0.0%) |
| always_clean | 2.4199 (-49.6%) | 2.5020 (-54.0%) |
| stat_only | 1.6153 (+0.1%) | 1.6282 (-0.2%) |
| quality_rank | 1.6438 (-1.6%) | 1.6596 (-2.2%) |
| introact_full | 1.6080 (+0.6%) | 1.6168 (+0.5%) |
| ablate_no_structure | 1.6089 (+0.5%) | 1.6191 (+0.3%) |
| ablate_no_reprobe | 1.6093 (+0.5%) | 1.6169 (+0.5%) |
| ablate_no_verify | 1.6187 (-0.1%) | 1.6280 (-0.2%) |
| ablate_no_peer_calibration | 1.6110 (+0.4%) | 1.6200 (+0.3%) |
| ablate_no_protection | 1.6099 (+0.5%) | 1.6188 (+0.3%) |

## Repair by contamination type (IntroAct-TS full)

| contamination | NMSE before | NMSE after | reduction | action acc |
|---|---|---|---|---|
| duplicate | 0.2204 | 0.2215 | -0.005 | 0.200 |
| flatline | 0.0574 | 0.0533 | +0.072 | 0.200 |
| level_shift | 4.7604 | 5.3400 | -0.122 | 0.000 |
| missing_block | 0.0606 | 0.0401 | +0.338 | 0.600 |
| missing_scattered | 0.0199 | 0.0195 | +0.022 | 0.400 |
| noise | 0.8268 | 0.8268 | +0.000 | 0.000 |
| spike | 0.5253 | 0.2925 | +0.443 | 0.400 |

## Protection by stratum (IntroAct-TS full)

| stratum | n | modified | over-clean rate | mean damage |
|---|---|---|---|---|
| changepoint | 10 | 0 | 0.000 | 0.0000 |
| clean | 20 | 3 | 0.150 | 0.0231 |
| clean_ood | 10 | 0 | 0.000 | 0.0000 |
| hard | 10 | 2 | 0.200 | 0.0268 |
| rare_valid | 10 | 1 | 0.100 | 0.0000 |

## Rollback reasons (IntroAct-TS full)

- `ROLLED_BACK_STRUCTURE`: 18
- `ROLLED_BACK_UTILITY`: 38
- protected windows saved by a rollback: 17
- mean probe calls per window: 1.77
