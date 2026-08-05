# IntroAct-TS results

Corpus: 95 windows, source `ett`. Curation models [0, 1, 2], transfer models [7, 11] (never consulted during curation).

## Headline

| method | detect F1 | action acc | repair NMSE red. | over-clean rate | damage to protected | rollbacks | abstain |
|---|---|---|---|---|---|---|---|
| no_action | 0.598 | 0.000 | 0.000 | 0.000 | 0.0000 | 0 | 0.000 |
| always_clean | 0.598 | 0.686 | -0.027 | 1.000 | 0.2071 | 0 | 0.000 |
| stat_only | 0.598 | 0.657 | 0.168 | 0.433 | 0.0839 | 0 | 0.000 |
| quality_rank | 0.598 | 0.200 | 0.040 | 0.250 | 0.0619 | 0 | 0.000 |
| introact_full | 0.598 | 0.343 | 0.248 | 0.100 | 0.0192 | 56 | 0.053 |
| ablate_no_structure | 0.598 | 0.457 | 0.398 | 0.217 | 0.0276 | 30 | 0.042 |
| ablate_no_reprobe | 0.598 | 0.486 | 0.412 | 0.200 | 0.0286 | 39 | 0.053 |
| ablate_no_verify | 0.598 | 0.629 | 0.403 | 0.300 | 0.0309 | 0 | 0.042 |
| ablate_no_peer_calibration | 0.598 | 0.343 | 0.248 | 0.100 | 0.0192 | 56 | 0.063 |
| ablate_no_protection | 0.598 | 0.371 | 0.246 | 0.150 | 0.0224 | 61 | 0.137 |

## Transfer to models that took no part in curation

| method | surrogate-s7 | surrogate-s11 |
|---|---|---|
| no_action | +0.0000 | +0.0000 |
| always_clean | +0.0147 | +0.0567 |
| stat_only | +0.0286 | +0.0462 |
| quality_rank | +0.0327 | +0.0613 |
| introact_full | +0.0144 | +0.0152 |
| ablate_no_structure | +0.0252 | +0.0240 |
| ablate_no_reprobe | +0.0096 | +0.0092 |
| ablate_no_verify | +0.0240 | +0.0240 |
| ablate_no_peer_calibration | +0.0144 | +0.0152 |
| ablate_no_protection | +0.0192 | +0.0157 |

## Repair by contamination type (IntroAct-TS full)

| contamination | NMSE before | NMSE after | reduction | action acc |
|---|---|---|---|---|
| duplicate | 0.2204 | 0.2215 | -0.005 | 0.200 |
| flatline | 0.0574 | 0.0533 | +0.072 | 0.200 |
| level_shift | 4.7604 | 3.5640 | +0.251 | 0.200 |
| missing_block | 0.0606 | 0.0731 | -0.206 | 0.400 |
| missing_scattered | 0.0199 | 0.0186 | +0.067 | 0.600 |
| noise | 0.8268 | 0.7592 | +0.082 | 0.200 |
| spike | 0.5253 | 0.1751 | +0.667 | 0.600 |

## Protection by stratum (IntroAct-TS full)

| stratum | n | modified | over-clean rate | mean damage |
|---|---|---|---|---|
| changepoint | 10 | 0 | 0.000 | 0.0000 |
| clean | 20 | 3 | 0.150 | 0.0378 |
| clean_ood | 10 | 0 | 0.000 | 0.0000 |
| hard | 10 | 2 | 0.200 | 0.0395 |
| rare_valid | 10 | 1 | 0.100 | 0.0000 |

## Rollback reasons (IntroAct-TS full)

- `ROLLED_BACK_STRUCTURE`: 21
- `ROLLED_BACK_UTILITY`: 35
- protected windows saved by a rollback: 18
- mean probe calls per window: 1.80
