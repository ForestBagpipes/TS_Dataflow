# IntroAct-TS results

Corpus: 95 windows, source `ett`, backend preset `offline`.

- Curation (judge + disagreement pool): `surrogate-s0`, `surrogate-s1`, `surrogate-s2`
- Transfer (never consulted during curation): `surrogate-s7`, `surrogate-s11`
- Capabilities: {'surrogate-s0': ['encode', 'forecast', 'reconstruct'], 'surrogate-s1': ['encode', 'forecast', 'reconstruct'], 'surrogate-s2': ['encode', 'forecast', 'reconstruct']}

## Headline

| method | detect F1 | action acc | repair NMSE red. | over-clean rate | damage to protected | rollbacks | abstain |
|---|---|---|---|---|---|---|---|
| no_action | 0.562 | 0.000 | 0.000 | 0.000 | 0.0000 | 0 | 0.000 |
| always_clean | 0.562 | 0.686 | -0.027 | 1.000 | 0.2071 | 0 | 0.000 |
| stat_only | 0.562 | 0.657 | 0.168 | 0.417 | 0.0888 | 0 | 0.000 |
| quality_rank | 0.562 | 0.086 | 0.010 | 0.300 | 0.0531 | 0 | 0.000 |
| introact_full | 0.562 | 0.343 | 0.403 | 0.117 | 0.0192 | 53 | 0.021 |
| ablate_no_structure | 0.562 | 0.429 | 0.395 | 0.200 | 0.0218 | 29 | 0.021 |
| ablate_no_reprobe | 0.562 | 0.457 | 0.410 | 0.200 | 0.0268 | 38 | 0.021 |
| ablate_no_verify | 0.562 | 0.600 | 0.400 | 0.283 | 0.0568 | 0 | 0.032 |
| ablate_no_peer_calibration | 0.562 | 0.343 | 0.403 | 0.117 | 0.0192 | 53 | 0.011 |
| ablate_no_protection | 0.562 | 0.400 | 0.417 | 0.167 | 0.0224 | 60 | 0.147 |

## Transfer to models that took no part in curation

| method | surrogate-s7 | surrogate-s11 |
|---|---|---|
| no_action | +0.0000 | +0.0000 |
| always_clean | -0.0078 | +0.0153 |
| stat_only | +0.0831 | +0.0865 |
| quality_rank | +0.0004 | +0.0130 |
| introact_full | +0.0268 | +0.0250 |
| ablate_no_structure | +0.0317 | +0.0281 |
| ablate_no_reprobe | +0.0195 | +0.0161 |
| ablate_no_verify | +0.0334 | +0.0284 |
| ablate_no_peer_calibration | +0.0268 | +0.0250 |
| ablate_no_protection | +0.0983 | +0.0806 |

## Repair by contamination type (IntroAct-TS full)

| contamination | NMSE before | NMSE after | reduction | action acc |
|---|---|---|---|---|
| duplicate | 0.2204 | 0.2215 | -0.005 | 0.200 |
| flatline | 0.0574 | 0.0533 | +0.072 | 0.200 |
| level_shift | 4.7604 | 2.5443 | +0.466 | 0.400 |
| missing_block | 0.0606 | 0.0731 | -0.206 | 0.400 |
| missing_scattered | 0.0199 | 0.0186 | +0.067 | 0.600 |
| noise | 0.8268 | 0.6761 | +0.182 | 0.200 |
| spike | 0.5253 | 0.2764 | +0.474 | 0.400 |

## Protection by stratum (IntroAct-TS full)

| stratum | n | modified | over-clean rate | mean damage |
|---|---|---|---|---|
| changepoint | 10 | 0 | 0.000 | 0.0000 |
| clean | 20 | 4 | 0.200 | 0.0378 |
| clean_ood | 10 | 0 | 0.000 | 0.0000 |
| hard | 10 | 2 | 0.200 | 0.0395 |
| rare_valid | 10 | 1 | 0.100 | 0.0000 |

## Rollback reasons (IntroAct-TS full)

- `ROLLED_BACK_STRUCTURE`: 19
- `ROLLED_BACK_UTILITY`: 34
- protected windows saved by a rollback: 17
- mean probe calls per window: 1.79
