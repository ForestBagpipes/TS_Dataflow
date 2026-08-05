# Backend verification

| backend | loaded | layers | capabilities | forecast | batch | reconstruct | encode |
|---|---|---|---|---|---|---|---|
| `surrogate:0` | yes | 6 | encode,forecast,reconstruct | ok (0.921x naive) | ok | ok (mse 2.7709) | ok (6x64) |
| `surrogate:7` | yes | 6 | encode,forecast,reconstruct | ok (0.827x naive) | ok | ok (mse 2.3663) | ok (6x64) |
| `chronos:amazon/chronos-bolt-base` | NO | - | - | - | - | - | - |

## Problems

- `chronos:amazon/chronos-bolt-base` did not load: ImportError: ChronosTSFM needs `pip install chronos-forecasting`.

`forecast` is reported relative to a seasonal-naive baseline: below 1.0 means the model beats it. A value near or above 1.0 on a clean seasonal series usually means the adapter is mis-wiring the input, not that the checkpoint is weak.
