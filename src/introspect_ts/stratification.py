"""Quality-guided data stratification.

Pure method layer. Zero file IO.
"""

import numpy as np


def stratify_by_quality(
    quality_scores: np.ndarray,
    alpha: float = 0.25,
) -> dict:
    """Partition samples into top, middle, and bottom quality tiers.

    Args:
        quality_scores: numpy array of shape (N,). Higher = better quality.
        alpha: fraction for top and bottom tiers. Default 0.25 means
               top 25%, middle 50%, bottom 25%.

    Returns:
        strata: dict with keys:
            "top_indices": indices of top-alpha samples
            "mid_indices": indices of middle (1-2*alpha) samples
            "bottom_indices": indices of bottom-alpha samples
            "thresholds": (tau_high, tau_low) quantile thresholds
            "stratum_labels": numpy array of shape (N,) with values in {0,1,2}
               0=bottom, 1=middle, 2=top
    """
    N = len(quality_scores)
    alpha = max(0.0, min(alpha, 0.5))
    tau_high = float(np.quantile(quality_scores, 1.0 - alpha))
    tau_low = float(np.quantile(quality_scores, alpha))

    labels = np.zeros(N, dtype=np.int32)
    labels[quality_scores >= tau_high] = 2
    labels[(quality_scores >= tau_low) & (quality_scores < tau_high)] = 1

    top_indices = np.where(labels == 2)[0]
    mid_indices = np.where(labels == 1)[0]
    bottom_indices = np.where(labels == 0)[0]

    return {
        "top_indices": top_indices,
        "mid_indices": mid_indices,
        "bottom_indices": bottom_indices,
        "thresholds": (tau_high, tau_low),
        "stratum_labels": labels,
    }
