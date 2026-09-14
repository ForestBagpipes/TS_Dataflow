"""TimesFM adapter.

A decoder-only patched forecaster. Its API takes a list of arrays and returns a
point forecast per array, so batching is native. It exposes no hidden states,
which it declares rather than fabricating.

Two generations are in the wild with incompatible entry points -- 2.5 uses
``TimesFM_2p5_200M_torch.from_pretrained`` plus an explicit ``compile``, while
1.x uses ``TimesFm(hparams, checkpoint)``. Both are handled; whichever is
installed wins.
"""

import numpy as np

from .base import CAP_FORECAST, CAP_RECONSTRUCT, ForecastOnlyMixin

DEFAULT_MODEL = "google/timesfm-2.5-200m-pytorch"


class TimesFMTSFM(ForecastOnlyMixin):
    """Frozen TimesFM checkpoint."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = "cuda",
        batch_size: int = 32,
        horizon: int = 32,
        context_len: int = 512,
    ):
        try:
            import timesfm
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError("TimesFMTSFM needs `pip install timesfm[torch]`.") from exc

        self._timesfm = timesfm
        self.name = model_name
        self.device = device
        self.batch_size = int(batch_size)
        self.horizon = int(horizon)
        self.context_len = int(context_len)
        self.capabilities = frozenset({CAP_FORECAST, CAP_RECONSTRUCT})
        self.n_layers = 20
        self._api = None
        self.model = self._load(model_name)

    def _load(self, model_name: str):  # pragma: no cover
        timesfm = self._timesfm
        if hasattr(timesfm, "TimesFM_2p5_200M_torch"):
            model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(model_name)
            cfg = timesfm.ForecastConfig(
                max_context=self.context_len,
                max_horizon=max(64, self.horizon),
                normalize_inputs=True,
            )
            model.compile(cfg)
            self._api = "2.5"
            return model
        # 1.x fallback
        hparams = timesfm.TimesFmHparams(
            backend="gpu" if self.device.startswith("cuda") else "cpu",
            per_core_batch_size=self.batch_size,
            horizon_len=max(128, self.horizon),
            context_len=self.context_len,
        )
        model = timesfm.TimesFm(
            hparams=hparams,
            checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id=model_name),
        )
        self._api = "1.x"
        return model

    def forecast_batch(self, contexts, horizon: int = None) -> list:  # pragma: no cover
        horizon = int(horizon or self.horizon)
        inputs = [
            np.asarray(c, dtype=np.float32)[-self.context_len :] for c in contexts
        ]
        out = []
        for i in range(0, len(inputs), self.batch_size):
            chunk = inputs[i : i + self.batch_size]
            if self._api == "2.5":
                point, _ = self.model.forecast(horizon=horizon, inputs=chunk)
            else:
                point, _ = self.model.forecast(chunk, freq=[0] * len(chunk))
            for p in np.asarray(point):
                out.append(np.asarray(p, dtype=np.float64)[:horizon])
        return out
