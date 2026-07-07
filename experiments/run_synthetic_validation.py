"""Synthetic validation of profile-conditioned calibration.

Generates a small synthetic corpus with known true_quality and true_difficulty
latent variables. Uses FakeTSFM to produce behavior signatures, then runs
the full IntroSpect-TS pipeline (profile -> calibrate -> stratify) and verifies
that the calibrated quality scores q_i correlate strongly with true_quality
and weakly with true_difficulty.

Also runs an ablation: calibration with raw behaviors (no peer normalization)
to show that domain confounding inflates the quality-difficulty correlation.
"""

import json
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.introspect_ts.profiling import extract_statistical_profile
from src.introspect_ts.behavior import FakeTSFM
from src.introspect_ts.calibration import profile_conditioned_calibration
from src.introspect_ts.stratification import stratify_by_quality


def generate_synthetic_corpus(
    N: int = 500,
    T: int = 512,
    seed: int = 42,
) -> list[dict]:
    """Generate N synthetic time series with known quality and difficulty.

    Each series is a combination of trend, seasonality, and noise components.
    difficulty controls the domain (trend slope + seasonal frequency).
    quality controls the noise level.
    """
    rng = np.random.RandomState(seed)
    records = []
    for i in range(N):
        t = np.arange(T, dtype=np.float64)

        # difficulty in [-1, 1]: controls domain characteristics
        difficulty = rng.uniform(-1.0, 1.0)

        # Trend: steeper slope for higher difficulty
        trend_slope = 0.01 + 0.05 * (difficulty + 1.0)
        trend = trend_slope * t

        # Seasonality: different frequencies per difficulty level
        freq1 = 7.0 + 5.0 * difficulty  # varies from 2 to 12
        freq2 = 24.0 + 12.0 * difficulty  # varies from 12 to 36
        seasonal = 5.0 * np.sin(2.0 * np.pi * t / max(freq1, 1.0)) + 3.0 * np.cos(2.0 * np.pi * t / max(freq2, 1.0))

        # quality in [-1, 1]: controls noise level
        quality = rng.uniform(-1.0, 1.0)
        noise_std = 0.5 + 4.5 * (1.0 - (quality + 1.0) / 2.0)  # maps quality to noise: high quality = low noise

        noise = rng.randn(T) * noise_std
        series = trend + seasonal + noise

        records.append({
            "window_id": i,
            "series": series.tolist(),
            "dataset": "synthetic",
            "split": "train",
            "freq": "H",
            "true_quality": float(quality),
            "true_difficulty": float(difficulty),
            "noise_label": None,
            "seed": seed + i,
        })
    return records


def run_validation(N: int = 500, K: int = 50, seed: int = 42) -> dict:
    """Run the full validation and return results."""
    records = generate_synthetic_corpus(N=N, seed=seed)
    tsfm = FakeTSFM(L=12, noise_std=0.02)

    profiles = np.zeros((N, 12), dtype=np.float64)
    behaviors = np.zeros((N, 2 * tsfm.L + 3), dtype=np.float64)
    true_q = np.zeros(N, dtype=np.float64)
    true_d = np.zeros(N, dtype=np.float64)

    for i, rec in enumerate(records):
        series = np.array(rec["series"], dtype=np.float64)
        true_q[i] = rec["true_quality"]
        true_d[i] = rec["true_difficulty"]

        # Profile from real profiling (not synthetic)
        profiles[i] = extract_statistical_profile(series)

        # Behavior from FakeTSFM with known latent variables
        behaviors[i] = tsfm.extract_behavior_signature(
            series,
            quality=float(rec["true_quality"]),
            difficulty=float(rec["true_difficulty"]),
            seed=seed + i,
        )

    # Calibrated: with peer normalization
    q_calibrated = profile_conditioned_calibration(behaviors, profiles, K=K, seed=seed)

    # Ablation: no peer calibration (use raw behavior, z-score across all samples)
    # This simulates "just use raw prediction error" approach
    behavior_means = behaviors.mean(axis=0)
    behavior_iqrs = np.percentile(behaviors, 75, axis=0) - np.percentile(behaviors, 25, axis=0)
    z_raw = (behaviors - behavior_means) / (behavior_iqrs + 1e-8)
    q_uncalibrated = -z_raw.mean(axis=1)

    # Correlations
    from scipy.stats import spearmanr

    r_q_cal, p_q_cal = spearmanr(q_calibrated, true_q)
    r_d_cal, p_d_cal = spearmanr(q_calibrated, true_d)
    r_q_raw, p_q_raw = spearmanr(q_uncalibrated, true_q)
    r_d_raw, p_d_raw = spearmanr(q_uncalibrated, true_d)

    # Stratify
    strata = stratify_by_quality(q_calibrated, alpha=0.25)

    return {
        "N": N,
        "K": K,
        "calibrated": {
            "spearman_quality": float(r_q_cal),
            "p_quality": float(p_q_cal),
            "spearman_difficulty": float(r_d_cal),
            "p_difficulty": float(p_d_cal),
        },
        "uncalibrated": {
            "spearman_quality": float(r_q_raw),
            "p_quality": float(p_q_raw),
            "spearman_difficulty": float(r_d_raw),
            "p_difficulty": float(p_d_raw),
        },
        "strata": {
            "top_count": int(len(strata["top_indices"])),
            "mid_count": int(len(strata["mid_indices"])),
            "bottom_count": int(len(strata["bottom_indices"])),
        },
    }


if __name__ == "__main__":
    results = run_validation(N=200, K=20, seed=42)
    output_path = Path(__file__).parent.parent / "docs" / "synthetic_validation.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    # Write readable summary
    md_path = Path(__file__).parent.parent / "docs" / "synthetic_validation.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Synthetic Validation Results\n\n")
        f.write(f"N={results['N']}, K={results['K']}\n\n")
        f.write("## With Peer Calibration (IntroSpect-TS)\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Spearman r(q_i, true_quality) | {results['calibrated']['spearman_quality']:.4f} (p={results['calibrated']['p_quality']:.4f}) |\n")
        f.write(f"| Spearman r(q_i, true_difficulty) | {results['calibrated']['spearman_difficulty']:.4f} (p={results['calibrated']['p_difficulty']:.4f}) |\n\n")
        f.write("## Without Peer Calibration (Raw Behavior Only)\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Spearman r(raw, true_quality) | {results['uncalibrated']['spearman_quality']:.4f} (p={results['uncalibrated']['p_quality']:.4f}) |\n")
        f.write(f"| Spearman r(raw, true_difficulty) | {results['uncalibrated']['spearman_difficulty']:.4f} (p={results['uncalibrated']['p_difficulty']:.4f}) |\n\n")
        f.write("## Interpretation\n\n")
        if results['calibrated']['spearman_quality'] > 0.5 and abs(results['calibrated']['spearman_difficulty']) < 0.3:
            f.write("PASS: Calibrated q_i strongly correlates with true_quality and weakly with true_difficulty.\n")
        else:
            f.write("CHECK: Correlation pattern not as strong as expected.\n")
        if abs(results['uncalibrated']['spearman_difficulty']) > results['calibrated']['spearman_difficulty']:
            f.write("PASS: Peer calibration reduces difficulty contamination.\n")
        else:
            f.write("CHECK: Peer calibration did not reduce difficulty correlation.\n")
        f.write(f"\nStrata: top={results['strata']['top_count']}, mid={results['strata']['mid_count']}, bottom={results['strata']['bottom_count']}\n")
        f.write("\n## Caveat\n\n")
        f.write("This validation uses synthetic data and a FakeTSFM stub. It verifies that the calibration\n")
        f.write("mechanism and implementation are correct under the additive model assumptions of Proposition 1.\n")
        f.write("Whether real TSFM behavior follows the same separation pattern must be verified with real\n")
        f.write("TSFM forward passes on real data (requires GPU rental).\n")

    print(f"Results written to {output_path} and {md_path}")
    print(f"Calibrated:   r_q={results['calibrated']['spearman_quality']:.4f}, r_d={results['calibrated']['spearman_difficulty']:.4f}")
    print(f"Uncalibrated: r_q={results['uncalibrated']['spearman_quality']:.4f}, r_d={results['uncalibrated']['spearman_difficulty']:.4f}")
