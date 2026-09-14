"""The contract every frozen backend implements.

Only ``forecast_batch`` is mandatory. Everything else the probe needs is
derived from it by :class:`ForecastOnlyMixin`, so a model that exposes nothing
but a forecasting API is still fully usable -- it simply contributes fewer
signal families, which it declares through :attr:`capabilities` rather than by
silently returning zeros.

Batching is in the contract rather than bolted on afterwards because the probe
issues on the order of thirty forward passes per window. Served one at a time
on a GPU that is almost all launch overhead; served as a batch it is one call.
"""

from typing import Protocol, Sequence, runtime_checkable

import numpy as np

#: What a backend can do beyond forecasting.
CAP_FORECAST = "forecast"
CAP_ENCODE = "encode"          # per-layer hidden states
CAP_RECONSTRUCT = "reconstruct"  # native masked reconstruction / imputation

ALL_CAPABILITIES = frozenset({CAP_FORECAST, CAP_ENCODE, CAP_RECONSTRUCT})


@runtime_checkable
class TSFMBackend(Protocol):
    """Interface the probe programs against."""

    name: str
    n_layers: int
    capabilities: frozenset

    def forecast_batch(self, contexts: Sequence[np.ndarray], horizon: int) -> list:
        """Predict ``horizon`` steps beyond each context. One call, N results."""
        ...


def instance_norm(x: np.ndarray) -> tuple:
    """Instance normalisation, the standard TSFM input treatment."""
    mu = float(np.mean(x))
    sigma = float(np.std(x))
    if sigma < 1e-8:
        sigma = 1.0
    return (x - mu) / sigma, mu, sigma


def fit_context(series: np.ndarray, context_len: int) -> np.ndarray:
    """Crop or left-pad ``series`` to exactly ``context_len`` points."""
    series = np.asarray(series, dtype=np.float64)
    T = len(series)
    if T >= context_len:
        return series[-context_len:]
    pad = np.full(context_len - T, series[0] if T > 0 else 0.0, dtype=np.float64)
    return np.concatenate([pad, series])


class ForecastOnlyMixin:
    """Derives the rest of the probe surface from a batched forecaster.

    Backcasting runs the model on the reversed series. That is a real
    distribution shift for a causal forecaster, but it is applied identically
    before and after an intervention, so the *difference* the agent acts on
    stays valid even where the absolute reconstruction error does not.
    """

    def forecast(self, context: np.ndarray, horizon: int = None) -> np.ndarray:
        horizon = int(horizon or getattr(self, "horizon", 32))
        return self.forecast_batch([context], horizon)[0]

    def backcast(self, future: np.ndarray, horizon: int) -> np.ndarray:
        rev = np.asarray(future, dtype=np.float64)[::-1]
        return self.forecast_batch([rev], horizon)[0][::-1]

    def reconstruct(self, series: np.ndarray, lo: int, hi: int) -> np.ndarray:
        return self.reconstruct_batch(series, [(lo, hi)])[0]

    def reconstruct_batch(self, series: np.ndarray, spans: Sequence) -> list:
        """Reconstruct several masked spans of one series in a single batch.

        Each span is filled by blending a forward forecast from its left
        context with a backcast from its right, so the seam is smooth and the
        masked values themselves are never seen.
        """
        series = np.asarray(series, dtype=np.float64)
        spans = [(int(lo), int(hi)) for lo, hi in spans]

        requests, plan = [], []
        for lo, hi in spans:
            span = hi - lo
            if span <= 0:
                plan.append((span, None, None))
                continue
            left, right = series[:lo], series[hi:]
            have_left, have_right = len(left) >= 8, len(right) >= 8
            i_fwd = i_bwd = None
            if have_left:
                i_fwd = len(requests)
                requests.append(("f", left, span))
            if have_right:
                i_bwd = len(requests)
                requests.append(("b", right, span))
            plan.append((span, i_fwd, i_bwd))

        results = {}
        by_horizon = {}
        for idx, (kind, ctx, span) in enumerate(requests):
            by_horizon.setdefault(span, []).append((idx, kind, ctx))
        for span, group in by_horizon.items():
            contexts = [c[::-1] if k == "b" else c for _, k, c in group]
            preds = self.forecast_batch(contexts, span)
            for (idx, kind, _), p in zip(group, preds):
                results[idx] = np.asarray(p)[::-1] if kind == "b" else np.asarray(p)

        out = []
        for (lo, hi), (span, i_fwd, i_bwd) in zip(spans, plan):
            if span <= 0:
                out.append(np.zeros(0, dtype=np.float64))
                continue
            fwd = results.get(i_fwd)
            bwd = results.get(i_bwd)
            if fwd is not None and bwd is not None:
                w = np.linspace(1.0, 0.0, span)
                out.append(w * fwd + (1.0 - w) * bwd)
            elif fwd is not None:
                out.append(fwd)
            elif bwd is not None:
                out.append(bwd)
            else:
                fill = series[lo - 1] if lo > 0 else (series[hi] if hi < len(series) else 0.0)
                out.append(np.full(span, float(fill)))
        return out

    def encode(self, context: np.ndarray) -> list:
        """Per-layer states. Backends without CAP_ENCODE must not be asked."""
        raise NotImplementedError(
            f"{getattr(self, 'name', type(self).__name__)} does not expose hidden states"
        )


def probe_signature(backend) -> dict:
    """What a backend can contribute, for logging and for the report."""
    return {
        "name": getattr(backend, "name", type(backend).__name__),
        "n_layers": int(getattr(backend, "n_layers", 0)),
        "capabilities": sorted(getattr(backend, "capabilities", frozenset())),
    }
