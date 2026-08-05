# IntroAct-TS results

Corpus: 190 windows, source `ett`. Curation models [0, 1, 2], transfer models [7, 11] (never consulted during curation).

## Headline

| method | detect F1 | action acc | repair NMSE red. | over-clean rate | damage to protected | rollbacks | abstain |
|---|---|---|---|---|---|---|---|
| no_action | 0.519 | 0.000 | 0.000 | 0.000 | 0.0000 | 0 | 0.000 |
| always_clean | 0.519 | 0.700 | 0.123 | 1.000 | 0.1893 | 0 | 0.000 |
| stat_only | 0.519 | 0.657 | 0.378 | 0.475 | 0.0784 | 0 | 0.000 |
| quality_rank | 0.519 | 0.214 | 0.065 | 0.250 | 0.0724 | 0 | 0.000 |
| introact_full | 0.519 | 0.257 | 0.298 | 0.142 | 0.0285 | 101 | 0.053 |
| ablate_no_structure | 0.519 | 0.300 | 0.146 | 0.217 | 0.0392 | 58 | 0.053 |
| ablate_no_reprobe | 0.519 | 0.343 | 0.299 | 0.200 | 0.0311 | 83 | 0.063 |
| ablate_no_verify | 0.519 | 0.471 | 0.060 | 0.308 | 0.0820 | 0 | 0.068 |
| ablate_no_peer_calibration | 0.509 | 0.257 | 0.298 | 0.142 | 0.0285 | 103 | 0.063 |
| ablate_no_protection | 0.519 | 0.343 | 0.441 | 0.200 | 0.0325 | 112 | 0.168 |

## Transfer to models that took no part in curation

| method | surrogate-s7 | surrogate-s11 |
|---|---|---|
| no_action | +0.0000 | +0.0000 |
| always_clean | +0.0441 | +0.0426 |
| stat_only | +0.0401 | +0.0307 |
| quality_rank | +0.0311 | +0.0234 |
| introact_full | +0.0398 | +0.0350 |
| ablate_no_structure | +0.0396 | +0.0365 |
| ablate_no_reprobe | +0.0374 | +0.0343 |
| ablate_no_verify | +0.0314 | +0.0229 |
| ablate_no_peer_calibration | +0.0398 | +0.0350 |
| ablate_no_protection | +0.0492 | +0.0452 |

## Repair by contamination type (IntroAct-TS full)

| contamination | NMSE before | NMSE after | reduction | action acc |
|---|---|---|---|---|
| duplicate | 0.1959 | 0.2828 | -0.443 | 0.000 |
| flatline | 0.1437 | 0.1110 | +0.227 | 0.300 |
| level_shift | 5.5426 | 3.4786 | +0.372 | 0.200 |
| missing_block | 0.1140 | 0.1104 | +0.031 | 0.400 |
| missing_scattered | 0.0261 | 0.0107 | +0.593 | 0.600 |
| noise | 0.8974 | 0.8974 | +0.000 | 0.000 |
| spike | 0.7340 | 0.4805 | +0.345 | 0.300 |

## Protection by stratum (IntroAct-TS full)

| stratum | n | modified | over-clean rate | mean damage |
|---|---|---|---|---|
| changepoint | 20 | 2 | 0.100 | 0.0000 |
| clean | 40 | 8 | 0.200 | 0.0339 |
| clean_ood | 20 | 1 | 0.050 | 0.0550 |
| hard | 20 | 6 | 0.300 | 0.0481 |
| rare_valid | 20 | 0 | 0.000 | 0.0000 |

## Rollback reasons (IntroAct-TS full)

- `ROLLED_BACK_STRUCTURE`: 38
- `ROLLED_BACK_UTILITY`: 63
- protected windows saved by a rollback: 32
- mean probe calls per window: 1.76
