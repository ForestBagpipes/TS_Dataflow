# Figures from cached runs

## heavy pareto, gain against damage

| method | net gain | windows worsened | over clean | damage | on frontier |
|---|---|---|---|---|---|
| stat_only | +0.731 | 68 | 0.500 | 0.0961 | yes |
| ablate_no_reprobe | +0.495 | 35 | 0.257 | 0.0583 | yes |
| ablate_no_protection | +0.493 | 25 | 0.271 | 0.0297 | yes |
| ablate_no_verify | +0.442 | 59 | 0.400 | 0.1181 |  |
| ablate_no_peer_calibration | +0.314 | 20 | 0.200 | 0.0254 | yes |
| introact_full | +0.311 | 20 | 0.200 | 0.0254 |  |
| ablate_no_structure | +0.294 | 35 | 0.257 | 0.0282 |  |
| no_action | +0.000 | 0 | 0.000 | 0.0000 | yes |
| quality_rank | -0.015 | 43 | 0.400 | 0.0947 |  |
| always_clean | -0.032 | 153 | 1.000 | 0.2085 |  |

## heavy risk coverage, introact_full

57 edited windows ordered by risk state confidence. Confidence spread across them 0.000.

| coverage | error rate among edits |
|---|---|
| 0.09 | 0.600 |
| 0.25 | 0.357 |
| 0.49 | 0.357 |
| 0.74 | 0.405 |
| 1.00 | 0.351 |

Confidence is constant across edited windows here, so the curve carries no information. Cached traces store the risk state only at window level and the field may be absent, which the next run fixes.

## small pareto, gain against damage

| method | net gain | windows worsened | over clean | damage | on frontier |
|---|---|---|---|---|---|
| no_action | +0.000 | 0 | 0.000 | 0.0000 | yes |
| always_clean | +0.000 | 0 | 1.000 | 0.2071 | yes |
| stat_only | +0.000 | 0 | 0.417 | 0.0888 | yes |
| quality_rank | +0.000 | 0 | 0.250 | 0.0299 | yes |
| introact_full | +0.000 | 0 | 0.083 | 0.0121 | yes |
| ablate_no_structure | +0.000 | 0 | 0.167 | 0.0222 | yes |
| ablate_no_reprobe | +0.000 | 0 | 0.200 | 0.0268 | yes |
| ablate_no_verify | +0.000 | 0 | 0.283 | 0.0568 | yes |
| ablate_no_peer_calibration | +0.000 | 0 | 0.083 | 0.0121 | yes |
| ablate_no_protection | +0.000 | 0 | 0.150 | 0.0200 | yes |

## small risk coverage, introact_full

17 edited windows ordered by risk state confidence. Confidence spread across them 0.000.

| coverage | error rate among edits |
|---|---|
| 0.06 | 1.000 |
| 0.24 | 0.500 |
| 0.47 | 0.500 |
| 0.71 | 0.333 |
| 1.00 | 0.471 |

Confidence is constant across edited windows here, so the curve carries no information. Cached traces store the risk state only at window level and the field may be absent, which the next run fixes.

