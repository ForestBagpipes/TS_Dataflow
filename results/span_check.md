# RESEGMENT span alignment check

Offline surrogate. 69 windows where RESEGMENT applies, of which 31 would move the window toward truth.
Acceptance threshold epsilon 0.005.

| utility definition | accepts | agrees with truth | wrongly refused | wrongly accepted | gain forgone | corr with truth |
|---|---|---|---|---|---|---|
| current, free span | 0.84 | 0.52 | 3 | 30 | 7.64 | +0.778 |
| aligned span | 0.62 | 0.62 | 7 | 19 | 17.76 | +0.696 |

Per window, sorted by how much truth improvement was available.

| window | contamination | keep frac | delta nmse | delta u current | delta u aligned |
|---|---|---|---|---|---|
| 119 | level_shift | 0.60 | +24.975 | +15.9826 | +4.8532 |
| 107 | level_shift | 0.51 | +11.072 | +10.9293 | +3.4988 |
| 113 | level_shift | 0.66 | +9.483 | +1.3956 | +0.8323 |
| 120 | level_shift | 0.55 | +9.165 | +2.3326 | +0.2995 |
| 116 | level_shift | 0.57 | +8.992 | +4.5039 | +1.1980 |
| 104 | level_shift | 0.65 | +8.248 | +1.2970 | +0.6569 |
| 103 | level_shift | 0.54 | +7.550 | +2.8886 | +0.4895 |
| 110 | level_shift | 0.56 | +7.243 | -0.0717 | -0.1583 |
| 115 | level_shift | 0.59 | +7.152 | +2.0524 | +1.6110 |
| 106 | level_shift | 0.53 | +6.948 | +2.8050 | +0.6596 |
| 102 | level_shift | 0.54 | +6.817 | +0.4592 | +0.4425 |
| 111 | level_shift | 0.52 | +6.631 | +5.4778 | -0.1253 |
| 108 | level_shift | 0.66 | +6.617 | +1.6147 | +0.2399 |
| 114 | level_shift | 0.54 | +6.596 | +1.3775 | +0.5500 |
| 117 | level_shift | 0.62 | +5.914 | +2.1006 | +0.4748 |
| 118 | level_shift | 0.52 | +5.259 | +1.0218 | +0.2492 |
| 109 | level_shift | 0.55 | +3.399 | +0.0724 | -0.1249 |
| 112 | level_shift | 0.51 | +2.817 | +1.2179 | +0.4502 |
| 61 | spike | 0.71 | +0.405 | +1.9619 | +0.1300 |
| 94 | noise | 0.78 | +0.239 | +0.0152 | +0.0153 |

