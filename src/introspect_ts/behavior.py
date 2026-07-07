"""Behavioral signal extraction from a TSFM's forward pass.

Pure method layer. Zero file IO. Accepts a TSFM object and a series,
returns a (2L+3)-dimensional behavior signature.

D_B = 3 (error stats) + L (entropy) + (L-1) (delta) + 1 (loss) = 2L+3.

DESIGN CONSTRAINT (enforced at interface level, not in this file):
  Real implementations MUST aggregate per-layer attention and hidden states
  into the (2L+3)-dim signature and return ONLY that vector. They MUST NOT
  cache or write raw hidden states or attention maps to disk. This method
  returns a flat numpy array by construction.
"""

import numpy as np
from scipy.stats import iqr as scipy_iqr


class FakeTSFM:
    """Fake TSFM stub for testing and development.

    Accepts the same interface as a real TSFM: forward(series, horizon).
    Internally generates behavior signals from hidden latent variables
    (quality and difficulty) so we can validate the calibration pipeline
    on synthetic data with known ground truth.

    The stub is NOT a neural network. It produces behavior signals that
    follow the additive model assumed in Proposition 1:
        B_{i,d} = g_d(Q_i) + h_d(D_i) + noise.

    Args:
        L: number of transformer layers (default 12, like MOMENT).
        noise_std: standard deviation of random noise added to each dimension.
    """

    def __init__(self, L: int = 12, noise_std: float = 0.05):
        self.L = L
        self.noise_std = noise_std

    def forward(self, series: np.ndarray, horizon: int = 96):
        """Simulate a TSFM forward pass.

        Args:
            series: 1D numpy array of length T.
            horizon: forecast horizon (unused in stub).

        Returns:
            predictions: numpy array of shape (horizon,).
            attn_maps: list of L arrays, each shape (T,), placeholder.
            hidden_states: list of L arrays, each shape (T,), placeholder.
        """
        T = len(series)
        series = np.asarray(series, dtype=np.float64)
        predictions = series[-1] * np.ones(horizon, dtype=np.float64)
        attn_maps = [np.ones(T, dtype=np.float64) for _ in range(self.L)]
        hidden_states = [np.ones(T, dtype=np.float64) for _ in range(self.L)]
        return predictions, attn_maps, hidden_states

    def extract_behavior_signature(
        self,
        series: np.ndarray,
        quality: float,
        difficulty: float,
        horizon: int = 96,
        seed: int = 42,
    ) -> np.ndarray:
        """Generate a behavior signature using the additive model.

        The signature is produced by:
          error_scale = base + quality_effect * quality + difficulty_effect * difficulty + noise
          attention_entropy = base + quality_effect + difficulty_effect (layer-dependent)
          representation_change = base + quality_effect + difficulty_effect (layer-dependent)

        Higher quality -> lower error, lower entropy, smoother representations.
        Higher difficulty -> higher error, higher entropy, larger changes.

        Args:
            series: 1D numpy array (used to derive signal baseline from data stats).
            quality: scalar in [-1, 1], lower means worse quality.
            difficulty: scalar in [-1, 1], lower means harder domain.
            horizon: forecast horizon.
            seed: random seed for reproducibility.

        Returns:
            behavior: numpy array of shape (2L+4,) = (3 + L + L-1 + 1).
        """
        rng = np.random.RandomState(seed)
        L = self.L
        T = len(series)
        series = np.asarray(series, dtype=np.float64)

        # Use series statistics as a baseline
        series_std = max(np.std(series), 1e-6)
        base_error = series_std

        # 1. Per-step prediction error trajectory: 3 dims (median, IQR, p90)
        #   quality: higher -> lower error
        #   difficulty: lower -> harder -> higher error
        quality_factor = 1.0 - 0.5 * quality  # maps quality in [-1,1] to [0.5, 1.5]
        difficulty_factor = 1.0 - 0.5 * difficulty  # maps difficulty in [-1,1] to [0.5, 1.5]
        scale = base_error * quality_factor * difficulty_factor
        errors = np.abs(rng.randn(T) * scale * 0.5 + scale * 0.5)
        error_median = float(np.median(errors))
        error_iqr = float(scipy_iqr(errors))
        error_p90 = float(np.percentile(errors, 90))
        E_bar = np.array([error_median, error_iqr, error_p90], dtype=np.float64)

        # 2. Layer-wise attention entropy: L dims
        #   quality: higher -> lower entropy
        #   difficulty: lower -> harder -> higher entropy
        base_entropy = 2.0
        q_effect_entropy = -0.3 * quality
        d_effect_entropy = -0.3 * difficulty
        H = np.full(L, base_entropy + q_effect_entropy + d_effect_entropy, dtype=np.float64)
        H += rng.randn(L) * self.noise_std * base_entropy

        # 3. Inter-layer representation change: L-1 dims
        #   quality: higher -> smoother -> smaller changes
        #   difficulty: lower -> harder -> larger changes
        base_delta = 0.15
        q_effect_delta = -0.05 * quality
        d_effect_delta = -0.05 * difficulty
        Delta = np.full(L - 1, base_delta + q_effect_delta + d_effect_delta, dtype=np.float64)
        Delta += rng.randn(L - 1) * self.noise_std * base_delta
        Delta = np.clip(Delta, 0.0, 1.0)

        # 4. Overall prediction loss: 1 dim
        L_i = float(np.mean(errors))

        # Concatenate: [E_bar(3), H(L), Delta(L-1), L_i(1)] = 2L+4
        behavior = np.concatenate([E_bar, H, Delta, np.array([L_i])]).astype(np.float64)
        return behavior


def extract_behavior_signature(tsfm, series: np.ndarray, horizon: int = 96) -> np.ndarray:
    """Extract 2L+4 dimensional behavior signature from a TSFM forward pass.

    DESIGN CONSTRAINT: This function aggregates per-layer attention entropies
    and inter-layer representation changes into the final flat vector and returns
    ONLY that vector. Raw hidden states and attention maps MUST NOT be cached
    or written to disk.

    Args:
        tsfm: A TSFM object with a .forward(series, horizon) method that returns
              (predictions, attention_maps, hidden_states).
        series: 1D numpy array of length T.
        horizon: forecast horizon.

    Returns:
        behavior: numpy array of shape (2L+4,).
            [0:3]   per-step error median, IQR, p90
            [3:3+L] layer-wise attention entropies
            [3+L:3+2L-1] inter-layer cosine distances
            [-1]    overall MSE
    """
    series = np.asarray(series, dtype=np.float64)
    predictions, attn_maps, hidden_states = tsfm.forward(series, horizon)
    T = len(series)
    L = len(attn_maps)

    # 1. Per-step prediction error trajectory: 3 dims
    horizon_actual = min(len(predictions), T)
    targets = series[-horizon_actual:]
    preds = np.asarray(predictions[:horizon_actual], dtype=np.float64)
    errors = (targets - preds) ** 2
    error_median = float(np.median(errors))
    error_iqr = float(scipy_iqr(errors))
    error_p90 = float(np.percentile(errors, 90))
    E_bar = np.array([error_median, error_iqr, error_p90], dtype=np.float64)

    # 2. Layer-wise attention entropy: L dims
    H = np.zeros(L, dtype=np.float64)
    for l in range(L):
        attn = np.asarray(attn_maps[l], dtype=np.float64)
        attn = attn + 1e-12
        attn = attn / (attn.sum() + 1e-12)
        entropy = -np.sum(attn * np.log(attn + 1e-12))
        H[l] = entropy

    # 3. Inter-layer representation change: L-1 dims (cosine distance)
    Delta = np.zeros(L - 1, dtype=np.float64)
    for l in range(L - 1):
        z_l = np.asarray(hidden_states[l], dtype=np.float64).mean()
        z_l1 = np.asarray(hidden_states[l + 1], dtype=np.float64).mean()
        if abs(z_l) > 1e-10 and abs(z_l1) > 1e-10:
            cos_sim = (z_l * z_l1) / (abs(z_l) * abs(z_l1) + 1e-12)
        else:
            cos_sim = 1.0
        Delta[l] = 1.0 - cos_sim

    # 4. Overall prediction loss: 1 dim
    L_i = float(np.mean(errors))

    behavior = np.concatenate([E_bar, H, Delta, np.array([L_i])]).astype(np.float64)
    return behavior
