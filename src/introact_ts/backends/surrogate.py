"""The offline surrogate foundation model.

A fixed random residual encoder with a ridge read-out head fitted once on a
synthetic reference corpus and frozen thereafter. It needs no network and no
GPU, is bit-for-bit reproducible from a seed, and exposes real per-layer hidden
states -- so every probe signal is genuinely computed rather than simulated.

It is *not* a pretrained foundation model, and no claim about how real TSFM
behaviour looks should rest on it. Its job is to make the mechanism runnable,
testable and reproducible offline while the headline numbers come from the
checkpoints in the sibling modules.
"""

import numpy as np

from .base import (
    ALL_CAPABILITIES,
    ForecastOnlyMixin,
    fit_context as _fit_context,
    instance_norm as _instance_norm,
)

CONTEXT_LEN = 256
HIDDEN_DIM = 64
N_LAYERS = 6


def make_reference_corpus(
    n_series: int = 1200,
    length: int = 512,
    seed: int = 1234,
) -> np.ndarray:
    """Synthetic multi-source corpus used to fit the frozen read-out head.

    Mixes trends, multiple seasonal periods, AR(1) memory and heteroscedastic
    noise so the head is not tuned to any evaluation dataset. Generated from a
    fixed seed that is deliberately disjoint from every experiment seed.
    """
    rng = np.random.RandomState(seed)
    t = np.arange(length, dtype=np.float64)
    corpus = np.zeros((n_series, length), dtype=np.float64)

    for i in range(n_series):
        trend = rng.uniform(-0.02, 0.02) * t
        if rng.rand() < 0.3:
            trend += rng.uniform(-1.0, 1.0) * np.sqrt(t + 1.0)

        signal = np.zeros(length, dtype=np.float64)
        for _ in range(rng.randint(1, 4)):
            period = rng.choice([6.0, 12.0, 24.0, 48.0, 96.0, 168.0])
            amp = rng.uniform(0.2, 3.0)
            phase = rng.uniform(0.0, 2.0 * np.pi)
            signal += amp * np.sin(2.0 * np.pi * t / period + phase)

        ar = np.zeros(length, dtype=np.float64)
        phi = rng.uniform(0.0, 0.95)
        innov = rng.randn(length) * rng.uniform(0.1, 1.0)
        for k in range(1, length):
            ar[k] = phi * ar[k - 1] + innov[k]

        noise = rng.randn(length) * rng.uniform(0.05, 0.8)
        corpus[i] = trend + signal + ar + noise

    return corpus


class SurrogateTSFM(ForecastOnlyMixin):
    """Frozen surrogate foundation model: fixed encoder + fitted ridge head.

    The encoder is a residual stack of ``n_layers`` fixed random projections
    with tanh nonlinearities, which gives meaningful inter-layer representation
    dynamics: in-distribution inputs traverse the residual stream smoothly while
    corrupted inputs saturate the nonlinearity and produce large layer jumps.
    Only the linear read-out head is fitted, once, on
    :func:`make_reference_corpus`, and is frozen thereafter.
    """

    def __init__(
        self,
        seed: int = 0,
        horizon: int = 32,
        context_len: int = CONTEXT_LEN,
        hidden_dim: int = HIDDEN_DIM,
        n_layers: int = N_LAYERS,
        ridge_lambda: float = 1.0,
        name: str = None,
    ):
        self.seed = seed
        self.horizon = horizon
        self.context_len = context_len
        self.hidden_dim = hidden_dim
        self.n_layers = n_layers
        self.ridge_lambda = ridge_lambda
        self.name = name or f"surrogate-s{seed}"

        rng = np.random.RandomState(1000 + seed)
        self.W_in = rng.randn(hidden_dim, context_len) / np.sqrt(context_len)
        self.b_in = rng.randn(hidden_dim) * 0.01
        self.W = [
            rng.randn(hidden_dim, hidden_dim) / np.sqrt(hidden_dim)
            for _ in range(n_layers - 1)
        ]
        self.b = [rng.randn(hidden_dim) * 0.01 for _ in range(n_layers - 1)]
        self.capabilities = ALL_CAPABILITIES
        self.head = None
        self._fit_head()

    # -- frozen pretraining -------------------------------------------------

    def _fit_head(self):
        """Fit the ridge read-out on the reference corpus, then freeze."""
        corpus = make_reference_corpus(seed=1234)
        rng = np.random.RandomState(2000 + self.seed)
        feats, targets = [], []

        for row in corpus:
            T = len(row)
            n_cuts = 2
            for _ in range(n_cuts):
                lo = self.context_len
                hi = T - self.horizon
                if hi <= lo:
                    continue
                cut = rng.randint(lo, hi)
                ctx = row[cut - self.context_len : cut]
                tgt = row[cut : cut + self.horizon]
                ctx_n, mu, sigma = _instance_norm(ctx)
                feats.append(self._features(ctx_n))
                targets.append((tgt - mu) / sigma)

        X = np.asarray(feats, dtype=np.float64)
        Y = np.asarray(targets, dtype=np.float64)
        X = np.column_stack([X, np.ones(len(X))])
        gram = X.T @ X + self.ridge_lambda * np.eye(X.shape[1])
        self.head = np.linalg.solve(gram, X.T @ Y)

    # -- forward ------------------------------------------------------------

    def _layers(self, ctx_norm: np.ndarray) -> list:
        """Residual-stream hidden states for a normalised context."""
        h = np.tanh(self.W_in @ ctx_norm + self.b_in)
        states = [h]
        scale = 1.0 / np.sqrt(self.n_layers)
        for W_l, b_l in zip(self.W, self.b):
            h = h + scale * np.tanh(W_l @ h + b_l)
            states.append(h)
        return states

    def _features(self, ctx_norm: np.ndarray) -> np.ndarray:
        return self._layers(ctx_norm)[-1]

    def encode(self, context: np.ndarray) -> list:
        """Per-layer hidden states, aggregated. No raw states are retained."""
        ctx = _fit_context(context, self.context_len)
        ctx_n, _, _ = _instance_norm(ctx)
        return self._layers(ctx_n)

    def forecast_batch(self, contexts, horizon: int = None) -> list:
        """Direct multi-step forecast per context, rolled autoregressively."""
        horizon = int(horizon or self.horizon)
        out = []
        for context in contexts:
            preds = []
            work = np.asarray(context, dtype=np.float64).copy()
            while len(preds) < horizon:
                ctx = _fit_context(work, self.context_len)
                ctx_n, mu, sigma = _instance_norm(ctx)
                feat = np.append(self._features(ctx_n), 1.0)
                step = (feat @ self.head) * sigma + mu
                preds.extend(step.tolist())
                work = np.concatenate([work, step])
            out.append(np.asarray(preds[:horizon], dtype=np.float64))
        return out
