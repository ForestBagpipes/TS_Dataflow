# Synthetic Validation Results

N=200, K=20

## With Peer Calibration (IntroSpect-TS)

| Metric | Value |
|--------|-------|
| Spearman r(q_i, true_quality) | 0.7593 (p=0.0000) |
| Spearman r(q_i, true_difficulty) | 0.2611 (p=0.0002) |

## Without Peer Calibration (Raw Behavior Only)

| Metric | Value |
|--------|-------|
| Spearman r(raw, true_quality) | 0.7916 (p=0.0000) |
| Spearman r(raw, true_difficulty) | 0.5949 (p=0.0000) |

## Interpretation

PASS: Calibrated q_i strongly correlates with true_quality and weakly with true_difficulty.
PASS: Peer calibration reduces difficulty contamination.

Strata: top=50, mid=100, bottom=50

## Caveat

This validation uses synthetic data and a FakeTSFM stub. It verifies that the calibration
mechanism and implementation are correct under the additive model assumptions of Proposition 1.
Whether real TSFM behavior follows the same separation pattern must be verified with real
TSFM forward passes on real data (requires GPU rental).
