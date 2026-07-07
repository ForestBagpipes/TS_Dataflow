"""Profile-conditioned behavior calibration.

Core algorithm of IntroSpect-TS. Transforms raw behavior signatures into
calibrated quality scores by normalizing within profile-matched peer groups.

Pure method layer. Zero file IO.
"""

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import normalize as sk_normalize


def profile_conditioned_calibration(
    behavior_signatures: np.ndarray,
    profiles: np.ndarray,
    K: int = 50,
    weights: np.ndarray = None,
    eps: float = 1e-8,
    seed: int = 42,
) -> np.ndarray:
    """Compute calibrated quality scores via profile-conditioned peer normalization.

    For each sample i:
      1. Find K nearest neighbors in L2-normalized profile space (cosine sim).
      2. For each behavior dimension d, compute:
           z_{i,d} = (B_{i,d} - median_{j in N(i)}(B_{j,d})) / (IQR_{j in N(i)}(B_{j,d}) + eps)
      3. Quality score: q_i = -sum_d w_d * z_{i,d}

    Args:
        behavior_signatures: numpy array of shape (N, D_B). Raw behavior vectors.
        profiles: numpy array of shape (N, D_P). Statistical profiles.
        K: number of nearest neighbors for peer group.
        weights: numpy array of shape (D_B,) or None. Fusion weights.
                 If None, uniform weights (1/D_B) are used.
        eps: small constant for numerical stability.
        seed: random seed (unused, kept for interface consistency).

    Returns:
        quality_scores: numpy array of shape (N,). Higher = better quality.
    """
    N, D_B = behavior_signatures.shape
    profiles = np.asarray(profiles, dtype=np.float64)

    # Normalize profiles to L2 unit norm for cosine similarity
    profiles_norm = sk_normalize(profiles, norm="l2")

    # Build KNN graph (K+1 because the query point itself is a neighbor)
    knn = NearestNeighbors(n_neighbors=min(K + 1, N), metric="cosine")
    knn.fit(profiles_norm)
    distances, indices = knn.kneighbors(profiles_norm)

    # Exclude self (index 0)
    peer_indices = indices[:, 1:]

    # Compute z-scores
    z_scores = np.zeros((N, D_B), dtype=np.float64)
    for i in range(N):
        peers = behavior_signatures[peer_indices[i], :]
        for d in range(D_B):
            peer_vals = peers[:, d]
            median_val = np.median(peer_vals)
            q75, q25 = np.percentile(peer_vals, [75, 25])
            iqr_val = q75 - q25
            z_scores[i, d] = (behavior_signatures[i, d] - median_val) / (iqr_val + eps)

    # Fusion
    if weights is None:
        weights = np.ones(D_B, dtype=np.float64) / D_B
    else:
        weights = np.asarray(weights, dtype=np.float64)
        weights = weights / weights.sum()

    quality_scores = -np.sum(z_scores * weights, axis=1)
    return quality_scores.astype(np.float64)
