# Two rulers, model utility against fidelity

Model utility is the change a frozen TSFM registers, as recorded by
the run. Fidelity is the reduction in distance to the pristine
reference, recomputed offline. A positive fidelity gain with a flat
model utility is a repair the target model did not need.

## small, 37 percent contaminated

### introact_full

| stratum | n | nmse before | fidelity gain | damage introduced | model utility gain |
|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | n/a | 0.0000 | +0.0000 |
| clean | 20 | 0.0000 | n/a | 0.0230 | +0.0723 |
| clean_ood | 10 | 0.0000 | n/a | 0.0000 | +0.0000 |
| duplicate | 5 | 0.2204 | -0.005 | n/a | +0.0193 |
| flatline | 5 | 0.0574 | +0.072 | n/a | +0.0245 |
| hard | 10 | 0.0000 | n/a | 0.0268 | +0.0149 |
| level_shift | 5 | 4.7604 | +0.466 | n/a | +0.0917 |
| missing_block | 5 | 0.0606 | +0.338 | n/a | +0.3344 |
| missing_scattered | 5 | 0.0199 | +0.255 | n/a | +0.0299 |
| noise | 5 | 0.8268 | +0.000 | n/a | +0.0000 |
| rare_valid | 10 | 0.0000 | n/a | 0.0000 | +0.0169 |
| spike | 5 | 0.5253 | +0.251 | n/a | +0.2605 |

### stat_only

| stratum | n | nmse before | fidelity gain | damage introduced | model utility gain |
|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | n/a | 0.0000 | +0.0000 |
| clean | 20 | 0.0000 | n/a | 0.0862 | +0.0507 |
| clean_ood | 10 | 0.0000 | n/a | 0.0416 | +2.8098 |
| duplicate | 5 | 0.2204 | -0.005 | n/a | +0.0193 |
| flatline | 5 | 0.0574 | -2.158 | n/a | -0.1462 |
| hard | 10 | 0.0000 | n/a | 0.1647 | +0.0951 |
| level_shift | 5 | 4.7604 | +0.130 | n/a | +0.0628 |
| missing_block | 5 | 0.0606 | +0.230 | n/a | +0.2589 |
| missing_scattered | 5 | 0.0199 | -1.110 | n/a | -0.2004 |
| noise | 5 | 0.8268 | +0.313 | n/a | +0.2532 |
| rare_valid | 10 | 0.0000 | n/a | 0.1542 | -0.2600 |
| spike | 5 | 0.5253 | +0.644 | n/a | +0.6015 |

### always_clean

| stratum | n | nmse before | fidelity gain | damage introduced | model utility gain |
|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | n/a | 0.0642 | +0.2389 |
| clean | 20 | 0.0000 | n/a | 0.2088 | +0.2732 |
| clean_ood | 10 | 0.0000 | n/a | 0.0716 | +2.0796 |
| duplicate | 5 | 0.2204 | -0.350 | n/a | +0.4938 |
| flatline | 5 | 0.0574 | -3.470 | n/a | +0.3304 |
| hard | 10 | 0.0000 | n/a | 0.4897 | +0.5317 |
| level_shift | 5 | 4.7604 | -0.145 | n/a | +0.3414 |
| missing_block | 5 | 0.0606 | -0.571 | n/a | +0.3875 |
| missing_scattered | 5 | 0.0199 | -4.431 | n/a | +0.1965 |
| noise | 5 | 0.8268 | +0.632 | n/a | +0.4698 |
| rare_valid | 10 | 0.0000 | n/a | 0.1997 | +0.1364 |
| spike | 5 | 0.5253 | +0.756 | n/a | +0.9243 |

## heavy, 67 percent contaminated

### introact_full

| stratum | n | nmse before | fidelity gain | damage introduced | model utility gain |
|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | n/a | 0.0053 | +0.0218 |
| clean | 20 | 0.0000 | n/a | 0.0142 | +0.0486 |
| clean_ood | 10 | 0.0000 | n/a | 0.1098 | +6.3194 |
| duplicate | 20 | 0.2102 | -0.009 | n/a | +0.0764 |
| flatline | 20 | 0.0617 | +0.214 | n/a | +0.1349 |
| hard | 10 | 0.0000 | n/a | 0.0197 | +0.0339 |
| level_shift | 20 | 7.6788 | +0.387 | n/a | +0.1181 |
| missing_block | 20 | 0.0929 | +0.095 | n/a | +0.0681 |
| missing_scattered | 20 | 0.0250 | +0.280 | n/a | +0.0081 |
| noise | 20 | 0.9366 | +0.043 | n/a | +0.0281 |
| rare_valid | 20 | 0.0000 | n/a | 0.0074 | +0.0106 |
| spike | 20 | 0.8186 | +0.127 | n/a | +0.2239 |

### stat_only

| stratum | n | nmse before | fidelity gain | damage introduced | model utility gain |
|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | n/a | 0.0538 | -0.0216 |
| clean | 20 | 0.0000 | n/a | 0.0629 | +0.0181 |
| clean_ood | 10 | 0.0000 | n/a | 0.1242 | +10.7477 |
| duplicate | 20 | 0.2102 | -0.983 | n/a | +0.0361 |
| flatline | 20 | 0.0617 | -0.160 | n/a | +0.1502 |
| hard | 10 | 0.0000 | n/a | 0.2104 | +0.0475 |
| level_shift | 20 | 7.6788 | +0.942 | n/a | -0.1384 |
| missing_block | 20 | 0.0929 | -2.268 | n/a | -0.0970 |
| missing_scattered | 20 | 0.0250 | +0.404 | n/a | +0.0042 |
| noise | 20 | 0.9366 | +0.399 | n/a | +0.3024 |
| rare_valid | 20 | 0.0000 | n/a | 0.0793 | +0.0692 |
| spike | 20 | 0.8186 | +0.402 | n/a | +0.4358 |

### always_clean

| stratum | n | nmse before | fidelity gain | damage introduced | model utility gain |
|---|---|---|---|---|---|
| changepoint | 10 | 0.0000 | n/a | 0.1200 | +0.1997 |
| clean | 20 | 0.0000 | n/a | 0.1881 | +0.1448 |
| clean_ood | 10 | 0.0000 | n/a | 0.1464 | +10.6928 |
| duplicate | 20 | 0.2102 | -0.981 | n/a | +0.2816 |
| flatline | 20 | 0.0617 | -1.476 | n/a | +0.3407 |
| hard | 10 | 0.0000 | n/a | 0.5263 | +0.5523 |
| level_shift | 20 | 7.6788 | -0.029 | n/a | +0.2124 |
| missing_block | 20 | 0.0929 | -2.904 | n/a | +0.1004 |
| missing_scattered | 20 | 0.0250 | -2.537 | n/a | +0.1937 |
| noise | 20 | 0.9366 | +0.648 | n/a | +0.4878 |
| rare_valid | 20 | 0.0000 | n/a | 0.1452 | +0.3628 |
| spike | 20 | 0.8186 | +0.805 | n/a | +1.3454 |

