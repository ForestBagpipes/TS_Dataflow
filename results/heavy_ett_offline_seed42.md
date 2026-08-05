# IntroAct-TS results

Corpus: 210 windows, source `ett`, backend preset `offline`.

- Curation (judge + disagreement pool): `surrogate-s0`, `surrogate-s1`, `surrogate-s2`
- Transfer (never consulted during curation): `surrogate-s7`, `surrogate-s11`
- Capabilities: {'surrogate-s0': ['encode', 'forecast', 'reconstruct'], 'surrogate-s1': ['encode', 'forecast', 'reconstruct'], 'surrogate-s2': ['encode', 'forecast', 'reconstruct']}

## Headline

| method | detect F1 | action acc | repair NMSE red. | over-clean rate | damage to protected | rollbacks | abstain |
|---|---|---|---|---|---|---|---|
| no_action | 0.728 | 0.000 | 0.000 | 0.000 | 0.0000 | 0 | 0.000 |
| always_clean | 0.728 | 0.707 | 0.042 | 1.000 | 0.2085 | 0 | 0.000 |
| stat_only | 0.728 | 0.629 | 0.531 | 0.514 | 0.0901 | 0 | 0.000 |
| quality_rank | 0.728 | 0.157 | 0.047 | 0.386 | 0.1055 | 0 | 0.000 |
| introact_full | 0.728 | 0.264 | 0.389 | 0.200 | 0.0437 | 157 | 0.081 |
| ablate_no_structure | 0.728 | 0.371 | 0.358 | 0.286 | 0.0492 | 89 | 0.086 |
| ablate_no_reprobe | 0.728 | 0.400 | 0.435 | 0.257 | 0.0583 | 109 | 0.090 |
| ablate_no_verify | 0.728 | 0.507 | 0.279 | 0.400 | 0.0961 | 0 | 0.095 |
| ablate_no_peer_calibration | 0.731 | 0.250 | 0.256 | 0.200 | 0.0437 | 159 | 0.086 |
| ablate_no_protection | 0.728 | 0.314 | 0.612 | 0.243 | 0.0451 | 159 | 0.195 |

## Transfer to models that took no part in curation

| method | surrogate-s7 | surrogate-s11 |
|---|---|---|
| no_action | +0.0000 | +0.0000 |
| always_clean | +0.0388 | +0.0232 |
| stat_only | +0.0830 | +0.0705 |
| quality_rank | +0.0296 | +0.0195 |
| introact_full | +0.0604 | +0.0618 |
| ablate_no_structure | +0.0616 | +0.0583 |
| ablate_no_reprobe | +0.0451 | +0.0525 |
| ablate_no_verify | +0.0340 | +0.0268 |
| ablate_no_peer_calibration | +0.0430 | +0.0431 |
| ablate_no_protection | +0.0795 | +0.0809 |

## Downstream transfer: train on curated data, test on pristine data

Models are trained from scratch on each method's output (147 windows) and scored on the untouched reference series of 63 held-out windows. Values are test MSE; the arrow is the change against `no_action`.

Training-independent reference on the same test split: `seasonal_naive` MSE 5.2401.

| method | ridge_ar | dlinear |
|---|---|---|
| no_action | 4.3083 (+0.0%) | 4.3019 (+0.0%) |
| always_clean | 4.5082 (-4.6%) | 4.6787 (-8.8%) |
| stat_only | 4.3122 (-0.1%) | 4.3061 (-0.1%) |
| quality_rank | 4.3256 (-0.4%) | 4.3201 (-0.4%) |
| introact_full | 4.3046 (+0.1%) | 4.2982 (+0.1%) |
| ablate_no_structure | 4.3029 (+0.1%) | 4.2967 (+0.1%) |
| ablate_no_reprobe | 4.2966 (+0.3%) | 4.2906 (+0.3%) |
| ablate_no_verify | 4.3130 (-0.1%) | 4.3071 (-0.1%) |
| ablate_no_peer_calibration | 4.3026 (+0.1%) | 4.2963 (+0.1%) |
| ablate_no_protection | 4.3081 (+0.0%) | 4.3020 (-0.0%) |

## Repair by contamination type (IntroAct-TS full)

| contamination | NMSE before | NMSE after | reduction | action acc |
|---|---|---|---|---|
| duplicate | 0.2102 | 0.2094 | +0.004 | 0.150 |
| flatline | 0.0617 | 0.0535 | +0.133 | 0.150 |
| level_shift | 7.6788 | 4.1805 | +0.456 | 0.450 |
| missing_block | 0.0929 | 0.0834 | +0.103 | 0.300 |
| missing_scattered | 0.0250 | 0.0161 | +0.355 | 0.350 |
| noise | 0.9366 | 0.9084 | +0.030 | 0.100 |
| spike | 0.8186 | 0.5500 | +0.328 | 0.350 |

## Protection by stratum (IntroAct-TS full)

| stratum | n | modified | over-clean rate | mean damage |
|---|---|---|---|---|
| changepoint | 10 | 2 | 0.200 | 0.0053 |
| clean | 20 | 4 | 0.200 | 0.0277 |
| clean_ood | 10 | 2 | 0.200 | 0.1098 |
| hard | 10 | 3 | 0.300 | 0.0496 |
| rare_valid | 20 | 3 | 0.150 | 0.0428 |

## Rollback reasons (IntroAct-TS full)

- `ROLLED_BACK_STRUCTURE`: 57
- `ROLLED_BACK_UTILITY`: 100
- protected windows saved by a rollback: 21
- mean probe calls per window: 2.05
