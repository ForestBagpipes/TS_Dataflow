"""Chronos and Chronos-Bolt adapters.

Chronos treats forecasting as language modelling over quantised series, so its
native surface is exactly one thing: sample futures given a context. Everything
else the probe needs is derived.

The two families differ in what they expose. The original T5 pipeline has an
``embed`` method returning encoder states, so it can serve the representation
signals; Bolt is a direct multi-step regressor with no documented embedding
API, so it declares fewer capabilities rather than pretending.
"""

import numpy as np

from .base import CAP_ENCODE, CAP_FORECAST, CAP_RECONSTRUCT, ForecastOnlyMixin

DEFAULT_MODEL = "amazon/chronos-bolt-base"


class ChronosTSFM(ForecastOnlyMixin):
    """Frozen Chronos / Chronos-Bolt checkpoint.

    Args:
        model_name: HuggingFace id, e.g. ``amazon/chronos-bolt-base`` or
            ``amazon/chronos-t5-small``.
        device: ``cuda`` or ``cpu``.
        num_samples: sample count for the probabilistic T5 variants; ignored by
            Bolt, which is deterministic.
        batch_size: forward-pass batch cap.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = "cuda",
        num_samples: int = 20,
        batch_size: int = 64,
        horizon: int = 32,
    ):
        try:
            import torch
            from chronos import BaseChronosPipeline
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "ChronosTSFM needs `pip install chronos-forecasting`."
            ) from exc

        self._torch = torch
        dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
        self.pipeline = BaseChronosPipeline.from_pretrained(
            model_name, device_map=device, torch_dtype=dtype
        )
        self.name = model_name
        self.device = device
        self.num_samples = int(num_samples)
        self.batch_size = int(batch_size)
        self.horizon = int(horizon)

        self.is_bolt = "bolt" in model_name.lower()
        caps = {CAP_FORECAST, CAP_RECONSTRUCT}
        if not self.is_bolt and hasattr(self.pipeline, "embed"):
            caps.add(CAP_ENCODE)
        self.capabilities = frozenset(caps)
        self.n_layers = self._count_layers()

    def _count_layers(self) -> int:
        for attr in ("model.model.config.num_layers", "model.config.num_layers"):
            obj = self.pipeline
            try:
                for part in attr.split("."):
                    obj = getattr(obj, part)
                return int(obj)
            except AttributeError:
                continue
        return 4

    def forecast_batch(self, contexts, horizon: int = None) -> list:  # pragma: no cover
        torch = self._torch
        horizon = int(horizon or self.horizon)
        tensors = [
            torch.tensor(np.asarray(c, dtype=np.float32)) for c in contexts
        ]
        out = []
        for i in range(0, len(tensors), self.batch_size):
            chunk = tensors[i : i + self.batch_size]
            with torch.no_grad():
                # Bolt returns quantiles, T5 returns samples; the median of the
                # sample axis is the point forecast in both layouts.
                preds = self.pipeline.predict(context=chunk, prediction_length=horizon)
            for p in preds:
                arr = p.float().cpu().numpy()
                if arr.ndim == 2:
                    arr = np.median(arr, axis=0)
                out.append(arr.astype(np.float64)[:horizon])
        return out

    def encode(self, context: np.ndarray) -> list:  # pragma: no cover
        if CAP_ENCODE not in self.capabilities:
            raise NotImplementedError(f"{self.name} does not expose embeddings")
        torch = self._torch
        ctx = torch.tensor(np.asarray(context, dtype=np.float32))
        with torch.no_grad():
            embeddings, _ = self.pipeline.embed(ctx)
        emb = embeddings[0].float().cpu().numpy().astype(np.float64)
        # Encoder states arrive as one tensor over tokens. Splitting the token
        # axis into n_layers blocks and mean-pooling each gives a depth-like
        # trajectory: not true per-layer states, but a stable, ordered summary
        # whose *changes* under perturbation carry the same information.
        return [b.mean(axis=0) for b in np.array_split(emb, self.n_layers, axis=0)]
