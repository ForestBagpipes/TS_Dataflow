# Manifest Schema

The manifest is a JSON array of flat records, one per time series window.
All downstream consumers (calibration, stratification, baseline scoring)
read this format. Every field present in the manifest is documented below.

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| window_id | int | Unique identifier within the corpus |
| dataset | str | Source dataset name |
| split | str | "train", "val", or "test" |
| freq | str | Frequency label ("H", "D", "10T", etc.) |
| series | list[float] | Raw time series values (length T) |
| seed | int | Random seed used during generation |

## Profile Fields (12 dims, filled by run_profile.py)

| Field | Index | Description |
|-------|-------|-------------|
| profile_0 | 0 | Trend strength (OLS R^2) |
| profile_1 | 1 | Trend linearity (linear vs quadratic R^2 ratio) |
| profile_2 | 2 | Seasonality strength (dominant FFT energy ratio) |
| profile_3 | 3 | Seasonality stability (std of sliding-window correlations) |
| profile_4 | 4 | Stationarity (ADF test p-value) |
| profile_5 | 5 | Sample entropy |
| profile_6 | 6 | Changepoint density (PELT) |
| profile_7 | 7 | Changepoint magnitude (mean absolute change) |
| profile_8 | 8 | Residual autocorrelation lag 1 (Ljung-Box Q) |
| profile_9 | 9 | Residual autocorrelation lag 7 (Ljung-Box Q) |
| profile_10 | 10 | Signal-to-noise ratio |
| profile_11 | 11 | Anomaly density (fraction outside 3*IQR) |

## Behavior Fields (2L+3 dims, filled by run_behavior.py)

| Field | Indices | Description |
|-------|---------|-------------|
| behavior_0 to behavior_2 | [0:3] | Per-step error: median, IQR, p90 |
| behavior_3 to behavior_{2+L} | [3:3+L] | Layer-wise attention entropy (L dims) |
| behavior_{3+L} to behavior_{2+2L} | [3+L:3+2L-1] | Inter-layer cosine distance (L-1 dims) |
| behavior_{2+2L+1} | [-1] | Overall prediction MSE |

## Quality Fields (filled by run_calibrate.py)

| Field | Type | Description |
|-------|------|-------------|
| q_i | float | Calibrated quality score (higher = better) |
| stratum | int | 0=bottom, 1=middle, 2=top |

## Optional Ground Truth Fields (synthetic experiments only)

| Field | Type | Description |
|-------|------|-------------|
| true_quality | float | True quality label (synthetic data) |
| true_difficulty | float | True difficulty label (synthetic data) |
| noise_label | str | Injected noise type description |

## Split Convention

- train: used for behavior signal extraction (Phase 1)
- val: held-out reference set for calibration validation
- test: only used for final downstream validation, never seen during scoring
