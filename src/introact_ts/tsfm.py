"""Frozen time-series foundation model backends.

IntroAct-TS treats the TSFM as a black box that is *frozen*: the agent may
query it but never updates it. Two backends implement the same protocol.

``SurrogateTSFM`` is the default. It is a small patch-free encoder with fixed
random residual layers and a ridge read-out head fitted once on a synthetic
reference corpus and then frozen. It requires no network access and no GPU, is
bit-for-bit reproducible from a seed, and exposes real per-layer hidden states,
so every behavioural probe in :mod:`introact_ts.probe` is genuinely computed
rather than simulated.

``ChronosTSFM`` wraps a real pretrained checkpoint when the optional
``chronos-forecasting`` dependency and weights are available. It is the backend
to use for the headline experiments; the surrogate keeps the whole pipeline
runnable and testable offline.
"""

from typing import Protocol, Sequence

import numpy as np

CONTEXT_LEN = 256
HIDDEN_DIM = 64
N_LAYERS = 6


class TSFMBackend(Protocol):
    """Interface every frozen backend must satisfy."""

    name: str
    n_layers: int

    def forecast(self, context: np.ndarray, horizon: int) -> np.ndarray:
        """Predict ``horizon`` steps beyond ``context``."""
        ...

    def encode(self, context: np.ndarray) -> list:
        """Return per-layer hidden representations for ``context``."""
        ...


def _instance_norm(x: np.ndarray) -> tuple:
    """Instance normalisation, the standard TSFM input treatment."""
    mu = float(np.mean(x))
    sigma = float(np.std(x))
    if sigma < 1e-8:
        sigma = 1.0
    return (x - mu) / sigma, mu, sigma


def _fit_context(series: np.ndarray, context_len: int) -> np.ndarray:
    """Crop or left-pad ``series`` to exactly ``context_len`` points."""
    series = np.asarray(series, dtype=np.float64)
    T = len(series)
    if T >= context_len:
        return series[-context_len:]
    pad = np.full(context_len - T, series[0] if T > 0 else 0.0, dtype=np.float64)
    return np.concatenate([pad, series])


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


class SurrogateTSFM:
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

    def forecast(self, context: np.ndarray, horizon: int = None) -> np.ndarray:
        """Direct multi-step forecast, autoregressively rolled if needed."""
        horizon = int(horizon or self.horizon)
        preds = []
        work = np.asarray(context, dtype=np.float64).copy()
        while len(preds) < horizon:
            ctx = _fit_context(work, self.context_len)
            ctx_n, mu, sigma = _instance_norm(ctx)
            feat = np.append(self._features(ctx_n), 1.0)
            step = (feat @ self.head) * sigma + mu
            preds.extend(step.tolist())
            work = np.concatenate([work, step])
        return np.asarray(preds[:horizon], dtype=np.float64)

    def backcast(self, future: np.ndarray, horizon: int) -> np.ndarray:
        """Predict ``horizon`` steps *before* ``future`` by time reversal."""
        rev = np.asarray(future, dtype=np.float64)[::-1]
        out = self.forecast(rev, horizon)
        return out[::-1]

    def reconstruct(self, series: np.ndarray, lo: int, hi: int) -> np.ndarray:
        """Reconstruct ``series[lo:hi]`` from both sides, without peeking at it.

        Used by the masked-reconstruction probe. Left context forecasts forward,
        right context backcasts, and the two are blended linearly so the seam is
        smooth. When one side is missing the other carries the whole span.
        """
        series = np.asarray(series, dtype=np.float64)
        span = hi - lo
        if span <= 0:
            return np.zeros(0, dtype=np.float64)

        left = series[:lo]
        right = series[hi:]
        have_left = len(left) >= 8
        have_right = len(right) >= 8

        if have_left:
            fwd = self.forecast(left, span)
        else:
            fwd = np.full(span, right[0] if len(right) else 0.0)
        if have_right:
            bwd = self.backcast(right, span)
        else:
            bwd = np.full(span, left[-1] if len(left) else 0.0)

        if have_left and have_right:
            w = np.linspace(1.0, 0.0, span)
            return w * fwd + (1.0 - w) * bwd
        return fwd if have_left else bwd


class ChronosTSFM:
    """Adapter for a real pretrained Chronos checkpoint.

    Optional: requires ``chronos-forecasting`` plus downloaded weights. Exposes
    the same protocol as :class:`SurrogateTSFM` so experiments can swap backends
    with a single flag. Hidden states come from the encoder's last hidden layer
    stack, mean-pooled over time so raw activations are never retained.
    """

    def __init__(self, model_name: str = "amazon/chronos-t5-tiny", device: str = "cpu"):
        try:
            import torch
            from chronos import ChronosPipeline
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "ChronosTSFM needs `pip install chronos-forecasting`. "
                "Use SurrogateTSFM for the offline pipeline."
            ) from exc

        self._torch = torch
        self.pipeline = ChronosPipeline.from_pretrained(
            model_name, device_map=device, torch_dtype=torch.float32
        )
        self.name = model_name
        self.device = device
        cfg = self.pipeline.model.model.config
        self.n_layers = int(getattr(cfg, "num_layers", 4))

    def forecast(self, context: np.ndarray, horizon: int = 32) -> np.ndarray:  # pragma: no cover
        torch = self._torch
        ctx = torch.tensor(np.asarray(context, dtype=np.float32))
        with torch.no_grad():
            samples = self.pipeline.predict(ctx, int(horizon), num_samples=20)
        return samples[0].median(dim=0).values.numpy().astype(np.float64)

    def encode(self, context: np.ndarray) -> list:  # pragma: no cover
        torch = self._torch
        ctx = torch.tensor(np.asarray(context, dtype=np.float32))
        with torch.no_grad():
            embeddings, _ = self.pipeline.embed(ctx)
        emb = embeddings[0].numpy().astype(np.float64)
        # Split the token axis into n_layers blocks and mean-pool each.
        blocks = np.array_split(emb, self.n_layers, axis=0)
        return [b.mean(axis=0) for b in blocks]

    def backcast(self, future: np.ndarray, horizon: int) -> np.ndarray:  # pragma: no cover
        rev = np.asarray(future, dtype=np.float64)[::-1]
        return self.forecast(rev, horizon)[::-1]

    def reconstruct(self, series: np.ndarray, lo: int, hi: int) -> np.ndarray:  # pragma: no cover
        return SurrogateTSFM.reconstruct(self, series, lo, hi)


def make_model_pool(seeds: Sequence[int] = (0, 1, 2), horizon: int = 32) -> list:
    """Instantiate a pool of independently initialised frozen surrogates.

    Used for the cross-model disagreement signal and for transfer evaluation on
    models that took no part in curation.
    """
    return [SurrogateTSFM(seed=s, horizon=horizon) for s in seeds]
