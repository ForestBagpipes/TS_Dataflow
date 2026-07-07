"""Thin IO shell for calibration and stratification.

Reads manifest with profiles and behavior signatures, runs calibration,
stratification, writes updated manifest.
"""

import json
import numpy as np
import argparse
from src.introspect_ts.calibration import profile_conditioned_calibration
from src.introspect_ts.stratification import stratify_by_quality


def run_calibrate_from_manifest(
    input_path: str,
    output_path: str,
    K: int = 50,
    alpha: float = 0.25,
    seed: int = 42,
):
    """Read manifest JSON, compute q_i from profiles and behaviors, stratify, write back."""
    with open(input_path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    N = len(rows)

    # Extract profile and behavior matrices
    D_P = 12
    profiles = np.zeros((N, D_P), dtype=np.float64)
    for i, row in enumerate(rows):
        for d in range(D_P):
            profiles[i, d] = row.get(f"profile_{d}", 0.0)

    # Find D_B from first row's behavior fields
    behavior_keys = [k for k in rows[0].keys() if k.startswith("behavior_")]
    D_B = len(behavior_keys)
    behaviors = np.zeros((N, D_B), dtype=np.float64)
    for i, row in enumerate(rows):
        for d in range(D_B):
            behaviors[i, d] = row.get(f"behavior_{d}", 0.0)

    # Calibrate
    q_scores = profile_conditioned_calibration(behaviors, profiles, K=K, seed=seed)

    # Stratify
    strata = stratify_by_quality(q_scores, alpha=alpha)

    # Write back
    for i, row in enumerate(rows):
        row["q_i"] = float(q_scores[i])
        row["stratum"] = int(strata["stratum_labels"][i])

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print(f"Calibration done. {N} windows. tau_high={strata['thresholds'][0]:.4f}, tau_low={strata['thresholds'][1]:.4f}")
    print(f"  top: {len(strata['top_indices'])}, mid: {len(strata['mid_indices'])}, bottom: {len(strata['bottom_indices'])}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--K", type=int, default=50)
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run_calibrate_from_manifest(args.input, args.output, K=args.K, alpha=args.alpha, seed=args.seed)
