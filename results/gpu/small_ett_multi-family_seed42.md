# IntroAct-TS results

Corpus: 95 windows, source `ett`, backend preset `multi-family`.

- Curation (judge + disagreement pool): `amazon/chronos-bolt-base`, `google/timesfm-2.5-200m-pytorch`, `amazon/chronos-bolt-small`
- Transfer (never consulted during curation): `amazon/chronos-t5-small`, `surrogate-s7`
- Capabilities: {'amazon/chronos-bolt-base': ['encode', 'forecast', 'reconstruct'], 'google/timesfm-2.5-200m-pytorch': ['forecast', 'reconstruct'], 'amazon/chronos-bolt-small': ['encode', 'forecast', 'reconstruct']}

## Headline

| method | detect F1 | action acc | repair NMSE red. | over-clean rate | damage to protected | rollbacks | abstain |
|---|---|---|---|---|---|---|---|
| no_action | 0.552 | 0.000 | 0.000 | 0.000 | 0.0000 | 0 | 0.000 |
| always_clean | 0.552 | 0.686 | -0.027 | 1.000 | 0.2071 | 0 | 0.000 |
| stat_only | 0.552 | 0.657 | 0.168 | 0.417 | 0.0888 | 0 | 0.000 |
| quality_rank | 0.552 | 0.171 | -0.003 | 0.250 | 0.0299 | 0 | 0.000 |
| introact_full | 0.552 | 0.314 | 0.367 | 0.083 | 0.0121 | 55 | 0.021 |
| ablate_no_structure | 0.552 | 0.343 | 0.141 | 0.167 | 0.0222 | 36 | 0.011 |
| ablate_no_reprobe | 0.552 | 0.429 | 0.391 | 0.200 | 0.0268 | 38 | 0.021 |
| ablate_no_verify | 0.552 | 0.571 | 0.382 | 0.283 | 0.0568 | 0 | 0.011 |
| ablate_no_peer_calibration | 0.568 | 0.343 | 0.383 | 0.083 | 0.0121 | 55 | 0.011 |
| ablate_no_protection | 0.552 | 0.371 | 0.381 | 0.150 | 0.0200 | 59 | 0.147 |

## Transfer to models that took no part in curation

| method | amazon/chronos-t5-small | surrogate-s7 |
|---|---|---|
| no_action | -0.0167 | +0.0000 |
| always_clean | +0.1017 | -0.0078 |
| stat_only | +0.0710 | +0.0831 |
| quality_rank | +0.1016 | +0.0097 |
| introact_full | +0.0137 | +0.0207 |
| ablate_no_structure | -0.0026 | +0.0157 |
| ablate_no_reprobe | -0.0139 | +0.0189 |
| ablate_no_verify | +0.0199 | +0.0327 |
| ablate_no_peer_calibration | +0.0002 | +0.0220 |
| ablate_no_protection | -0.0201 | +0.0910 |

## Repair by contamination type (IntroAct-TS full)

| contamination | NMSE before | NMSE after | reduction | action acc |
|---|---|---|---|---|
| duplicate | 0.2204 | 0.2215 | -0.005 | 0.200 |
| flatline | 0.0574 | 0.0533 | +0.072 | 0.200 |
| level_shift | 4.7604 | 2.5443 | +0.466 | 0.400 |
| missing_block | 0.0606 | 0.0401 | +0.338 | 0.600 |
| missing_scattered | 0.0199 | 0.0148 | +0.255 | 0.600 |
| noise | 0.8268 | 0.8268 | +0.000 | 0.000 |
| spike | 0.5253 | 0.3937 | +0.251 | 0.200 |

## Protection by stratum (IntroAct-TS full)

| stratum | n | modified | over-clean rate | mean damage |
|---|---|---|---|---|
| changepoint | 10 | 0 | 0.000 | 0.0000 |
| clean | 20 | 2 | 0.100 | 0.0230 |
| clean_ood | 10 | 0 | 0.000 | 0.0000 |
| hard | 10 | 2 | 0.200 | 0.0268 |
| rare_valid | 10 | 1 | 0.100 | 0.0000 |

## Rollback reasons (IntroAct-TS full)

- `ROLLED_BACK_STRUCTURE`: 17
- `ROLLED_BACK_UTILITY`: 38
- protected windows saved by a rollback: 17
- mean probe calls per window: 1.77
