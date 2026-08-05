"""Profile-conditioned peer calibration.

A raw behaviour signature cannot be read as a quality signal on its own: a
volatile, high-entropy window will always look worse to a model than a smooth
one, whether or not anything is wrong with it. Calibration removes that
confound by scoring each window against the peers that look structurally like
it -- its nearest neighbours in profile space -- rather than against the corpus
as a whole.

The same peer group is reused after an intervention (see
:func:`recalibrate_one`), so the post-action risk is measured on exactly the
scale the pre-action risk was.
"""

from dataclasses import dataclass, field

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import normalize as sk_normalize

#: Behaviour dimensions that count towards the scalar risk, and how much.
#: Keys are indices into :data:`introact_ts.probe.SIGNAL_NAMES`.
RISK_WEIGHTS = {
    "forecast_nrmse": 1.0,
    "resid_acf1": 0.4,
    "resid_skew": 0.2,
    "recon_nrmse_med": 1.0,
    "recon_nrmse_iqr": 0.4,
    "recon_nrmse_max": 0.5,
    "multiview_disagree": 0.6,
    "multiview_err_spread": 0.3,
    "perturb_output_sens": 0.5,
    "perturb_repr_sens": 0.3,
    "repr_jump_mean": 0.4,
    "repr_jump_max": 0.3,
    "repr_norm_drift": 0.2,
    "model_disagree": 0.6,
}


@dataclass
class PeerCalibration:
    """Per-dimension robust z-scores against profile-matched peers."""

    z: np.ndarray
    risk: np.ndarray
    peer_indices: np.ndarray
    centers: np.ndarray = field(repr=False, default=None)
    spreads: np.ndarray = field(repr=False, default=None)
    signal_names: tuple = ()

    def dim_z(self, i: int, name: str) -> float:
        """z-score of window ``i`` on the named behaviour dimension."""
        if name not in self.signal_names:
            return 0.0
        return float(self.z[i, self.signal_names.index(name)])


def _weight_vector(signal_names, weights: dict) -> np.ndarray:
    w = np.asarray([weights.get(n, 0.0) for n in signal_names], dtype=np.float64)
    total = w.sum()
    return w / total if total > 1e-12 else np.ones(len(w)) / max(len(w), 1)


def calibrate(
    behaviors: np.ndarray,
    profiles: np.ndarray,
    signal_names: tuple,
    K: int = 40,
    weights: dict = None,
    eps: float = 1e-8,
) -> PeerCalibration:
    """Robustly z-score every behaviour dimension within its peer group.

    Args:
        behaviors: (N, D_B) raw behaviour signatures.
        profiles: (N, D_P) statistical profiles defining structural similarity.
        signal_names: names of the behaviour dimensions, in column order.
        K: peer group size.
        weights: per-signal weights for the scalar risk; defaults to
            :data:`RISK_WEIGHTS`.

    Returns:
        A :class:`PeerCalibration`. Higher ``risk`` means the window behaves
        worse than structurally similar windows do.
    """
    behaviors = np.asarray(behaviors, dtype=np.float64)
    profiles = np.nan_to_num(np.asarray(profiles, dtype=np.float64))
    N, D_B = behaviors.shape

    profiles_n = sk_normalize(profiles, norm="l2")
    n_neighbors = int(min(K + 1, N))
    knn = NearestNeighbors(n_neighbors=n_neighbors, metric="cosine").fit(profiles_n)
    _, indices = knn.kneighbors(profiles_n)
    peer_indices = indices[:, 1:] if n_neighbors > 1 else indices

    centers = np.zeros((N, D_B), dtype=np.float64)
    spreads = np.zeros((N, D_B), dtype=np.float64)
    for i in range(N):
        peers = behaviors[peer_indices[i], :]
        centers[i] = np.median(peers, axis=0)
        q75, q25 = np.percentile(peers, [75, 25], axis=0)
        spreads[i] = q75 - q25

    z = (behaviors - centers) / (spreads + eps)
    z = np.clip(np.nan_to_num(z), -20.0, 20.0)

    w = _weight_vector(signal_names, weights or RISK_WEIGHTS)
    risk = z @ w
    return PeerCalibration(
        z=z,
        risk=risk.astype(np.float64),
        peer_indices=peer_indices,
        centers=centers,
        spreads=spreads,
        signal_names=tuple(signal_names),
    )


def recalibrate_one(
    behavior: np.ndarray,
    center: np.ndarray,
    spread: np.ndarray,
    signal_names: tuple,
    weights: dict = None,
    eps: float = 1e-8,
) -> tuple:
    """Re-score a post-intervention behaviour against the *original* peer group.

    Keeping the centre and spread fixed is what makes the before/after risks
    comparable: the candidate is judged on the scale its own peers defined, not
    on a scale the edit itself moved.
    """
    behavior = np.asarray(behavior, dtype=np.float64)
    z = np.clip(np.nan_to_num((behavior - center) / (spread + eps)), -20.0, 20.0)
    w = _weight_vector(signal_names, weights or RISK_WEIGHTS)
    return z, float(z @ w)


def ood_scores(profiles: np.ndarray, K: int = 20) -> np.ndarray:
    """How far each window sits from the bulk of the corpus in profile space.

    A high score means "structurally unlike anything else here". On its own
    that is not a defect -- clean out-of-distribution data scores high too --
    which is exactly why the risk state combines it with behavioural evidence
    instead of acting on it directly.
    """
    profiles = np.nan_to_num(np.asarray(profiles, dtype=np.float64))
    N = len(profiles)
    profiles_n = sk_normalize(profiles, norm="l2")
    k = int(min(K + 1, N))
    knn = NearestNeighbors(n_neighbors=k, metric="cosine").fit(profiles_n)
    distances, _ = knn.kneighbors(profiles_n)
    return distances[:, 1:].mean(axis=1) if k > 1 else np.zeros(N)
