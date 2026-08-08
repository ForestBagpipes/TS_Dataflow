# IntroAct-TS results

Corpus: 210 windows, source `ett`, backend preset `offline`.

- Curation (judge + disagreement pool): `surrogate-s0`, `surrogate-s1`, `surrogate-s2`
- Transfer (never consulted during curation): `surrogate-s7`, `surrogate-s11`
- Capabilities: {'surrogate-s0': ['encode', 'forecast', 'reconstruct'], 'surrogate-s1': ['encode', 'forecast', 'reconstruct'], 'surrogate-s2': ['encode', 'forecast', 'reconstruct']}

## Headline

| method | **net corpus** | repair (contaminated) | over-clean rate | damage to protected | detect F1 | action acc | rollbacks | abstain |
|---|---|---|---|---|---|---|---|---|
| no_action | **+0.000** | 0.000 | 0.000 | 0.0000 | 0.738 | 0.000 | 0 | 0.000 |
| always_clean | **-0.032** | 0.042 | 1.000 | 0.2085 | 0.738 | 0.707 | 0 | 0.000 |
| stat_only | **+0.731** | 0.766 | 0.500 | 0.0961 | 0.738 | 0.643 | 0 | 0.000 |
| quality_rank | **-0.010** | 0.012 | 0.329 | 0.0623 | 0.738 | 0.100 | 0 | 0.000 |
| introact_full | **+0.591** | 0.606 | 0.214 | 0.0430 | 0.738 | 0.314 | 141 | 0.014 |
| ablate_no_structure | **+0.588** | 0.603 | 0.286 | 0.0425 | 0.738 | 0.407 | 80 | 0.019 |
| ablate_no_reprobe | **+0.624** | 0.645 | 0.257 | 0.0583 | 0.738 | 0.457 | 99 | 0.019 |
| ablate_no_verify | **+0.571** | 0.613 | 0.400 | 0.1181 | 0.738 | 0.564 | 0 | 0.019 |
| ablate_no_peer_calibration | **+0.591** | 0.606 | 0.214 | 0.0430 | 0.729 | 0.314 | 141 | 0.033 |
| ablate_no_protection | **+0.729** | 0.746 | 0.271 | 0.0470 | 0.738 | 0.393 | 147 | 0.133 |

`net corpus` is the reduction in mean normalised distance-to-truth over *every* window with a pristine reference, contaminated and protected alike. Repair and damage are trade-offs against each other and neither column alone can say whether running the pipeline was worth it; this one can.

| method | windows improved | windows worsened |
|---|---|---|
| no_action | 0 | 0 |
| always_clean | 57 | 153 |
| stat_only | 76 | 68 |
| quality_rank | 11 | 42 |
| introact_full | 40 | 20 |
| ablate_no_structure | 47 | 37 |
| ablate_no_reprobe | 52 | 35 |
| ablate_no_verify | 58 | 59 |
| ablate_no_peer_calibration | 40 | 20 |
| ablate_no_protection | 51 | 24 |

## Transfer to models that took no part in curation

| method | surrogate-s7 | surrogate-s11 |
|---|---|---|
| no_action | +0.0000 | +0.0000 |
| always_clean | +0.0293 | +0.0205 |
| stat_only | +0.3025 | +0.2942 |
| quality_rank | +0.0242 | +0.0164 |
| introact_full | +0.2598 | +0.2579 |
| ablate_no_structure | +0.2668 | +0.2618 |
| ablate_no_reprobe | +0.2480 | +0.2492 |
| ablate_no_verify | +0.2546 | +0.2466 |
| ablate_no_peer_calibration | +0.2598 | +0.2579 |
| ablate_no_protection | +0.2983 | +0.3000 |

## Repair by contamination type (IntroAct-TS full)

| contamination | NMSE before | NMSE after | reduction | action acc |
|---|---|---|---|---|
| duplicate | 0.2102 | 0.2098 | +0.002 | 0.200 |
| flatline | 0.0617 | 0.0539 | +0.126 | 0.250 |
| level_shift | 7.6788 | 1.9526 | +0.746 | 0.700 |
| missing_block | 0.0929 | 0.0828 | +0.109 | 0.350 |
| missing_scattered | 0.0250 | 0.0161 | +0.355 | 0.350 |
| noise | 0.9366 | 0.9030 | +0.036 | 0.150 |
| spike | 0.8186 | 0.6491 | +0.207 | 0.200 |

## Protection by stratum (IntroAct-TS full)

| stratum | n | modified | over-clean rate | mean damage |
|---|---|---|---|---|
| changepoint | 10 | 3 | 0.300 | 0.0053 |
| clean | 20 | 5 | 0.250 | 0.0278 |
| clean_ood | 10 | 1 | 0.100 | 0.1098 |
| hard | 10 | 3 | 0.300 | 0.0448 |
| rare_valid | 20 | 3 | 0.150 | 0.0428 |

## Rollback reasons (IntroAct-TS full)

- `ROLLED_BACK_STRUCTURE`: 51
- `ROLLED_BACK_UTILITY`: 90
- protected windows saved by a rollback: 20
- mean probe calls per window: 2.03
