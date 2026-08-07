# Backend verification

| backend | loaded | layers | capabilities | forecast | batch | reconstruct | encode |
|---|---|---|---|---|---|---|---|
| `moment:AutonLab/MOMENT-1-large` | yes | 24 | encode,forecast,reconstruct | ok (20.265x naive) | ok | ok (mse 0.3776) | ok (24x1024) |

All requested backends loaded and passed every check.

`forecast` is reported relative to a seasonal-naive baseline: below 1.0 means the model beats it. A value near or above 1.0 on a clean seasonal series usually means the adapter is mis-wiring the input, not that the checkpoint is weak.
