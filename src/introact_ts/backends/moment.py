"""MOMENT adapter.

MOMENT contributes reconstruction and representations, not forecasts.

Its pretraining task *is* masked reconstruction, so reconstruction and
embeddings are genuinely zero-shot and both are strong. Forecasting is not:
the head ships randomly initialised and the paper obtains its forecasting
numbers by linear probing. Measured on this box against a seasonal-naive
reference, `short_forecast` scores **20x worse than naive** while Chronos-Bolt
and TimesFM score 0.27x -- and that gap is the model, not the adapter, since
the same call reconstructs at MSE 0.38.

The consequence is architectural, and it is why this backend is absent from
the default presets: a judge model's forecast error is the highest-weighted
term in the probe's utility, so putting MOMENT in that seat would have the
agent optimising against noise. Use it as a reconstruction/representation
source, or not at all.

The model takes a fixed 512-point input, which happens to be the window length
used throughout these experiments; other lengths are cropped or padded and the
padding is masked out.
"""

import numpy as np

from .base import ALL_CAPABILITIES, ForecastOnlyMixin

DEFAULT_MODEL = "AutonLab/MOMENT-1-large"
SEQ_LEN = 512


class MomentTSFM(ForecastOnlyMixin):
    """Frozen MOMENT checkpoint used through its reconstruction head."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = "cuda",
        batch_size: int = 16,
        horizon: int = 32,
    ):
        try:
            import torch
            from momentfm import MOMENTPipeline
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError("MomentTSFM needs `pip install momentfm`.") from exc

        self._torch = torch
        self.model = MOMENTPipeline.from_pretrained(
            model_name, model_kwargs={"task_name": "reconstruction"}
        )
        self.model.init()
        self.model.to(device).eval()
        self.name = model_name
        self.device = device
        self.batch_size = int(batch_size)
        self.horizon = int(horizon)
        self.capabilities = ALL_CAPABILITIES
        self.n_layers = int(
            getattr(getattr(self.model, "config", None), "t5_config", {}).get(
                "num_layers", 24
            )
            if isinstance(getattr(getattr(self.model, "config", None), "t5_config", None), dict)
            else 24
        )

    # -- input plumbing -----------------------------------------------------

    def _pack(self, series: np.ndarray) -> tuple:
        """Crop/pad one series to SEQ_LEN, returning values and an input mask."""
        x = np.asarray(series, dtype=np.float32)
        mask = np.ones(SEQ_LEN, dtype=np.float32)
        if len(x) >= SEQ_LEN:
            return x[-SEQ_LEN:], mask
        padded = np.zeros(SEQ_LEN, dtype=np.float32)
        padded[SEQ_LEN - len(x) :] = x
        mask[: SEQ_LEN - len(x)] = 0.0
        return padded, mask

    def _reconstruct_masked(self, packed: list) -> np.ndarray:  # pragma: no cover
        """Run the reconstruction head. ``packed`` holds (values, input_mask, mask)."""
        torch = self._torch
        outputs = []
        for i in range(0, len(packed), self.batch_size):
            chunk = packed[i : i + self.batch_size]
            x = torch.tensor(np.stack([c[0] for c in chunk])).unsqueeze(1)
            im = torch.tensor(np.stack([c[1] for c in chunk]))
            mk = torch.tensor(np.stack([c[2] for c in chunk]))
            with torch.no_grad():
                out = self.model(
                    x_enc=x.to(self.device),
                    input_mask=im.to(self.device),
                    mask=mk.to(self.device),
                )
            rec = out.reconstruction.squeeze(1).float().cpu().numpy()
            outputs.append(rec)
        return np.concatenate(outputs, axis=0).astype(np.float64)

    # -- probe surface ------------------------------------------------------
    #
    # Each of the three entry points below is MOMENT's own published method.
    # An earlier version of this adapter hand-rolled the forecast by appending
    # zeros to the context and masking the tail; it scored twenty times worse
    # than seasonal-naive, because the appended zeros pass through `input_mask`
    # as genuine observations and poison the encoding. `short_forecast` instead
    # rolls the series so the horizon lands in already-valid input slots.

    def _tensors(self, values, masks=None):
        torch = self._torch
        x = torch.tensor(np.stack([v for v, _ in values])).unsqueeze(1)
        im = torch.tensor(np.stack([m for _, m in values]))
        out = [x.to(self.device), im.to(self.device)]
        if masks is not None:
            out.append(self._torch.tensor(np.stack(masks)).to(self.device))
        return out

    def forecast_batch(self, contexts, horizon: int = None) -> list:  # pragma: no cover
        torch = self._torch
        horizon = int(horizon or self.horizon)
        packed = [self._pack(np.asarray(c, dtype=np.float64)) for c in contexts]
        out = []
        for i in range(0, len(packed), self.batch_size):
            chunk = packed[i : i + self.batch_size]
            x, im = self._tensors(chunk)
            with torch.no_grad():
                res = self.model.short_forecast(
                    x_enc=x, input_mask=im, forecast_horizon=horizon
                )
            fc = res.forecast.squeeze(1).float().cpu().numpy().astype(np.float64)
            out.extend(f[:horizon] for f in np.atleast_2d(fc))
        return out

    def reconstruct_batch(self, series: np.ndarray, spans) -> list:  # pragma: no cover
        """Native masked reconstruction -- this is MOMENT's pretraining task."""
        torch = self._torch
        x = np.asarray(series, dtype=np.float64)
        offset = max(0, len(x) - SEQ_LEN)
        packed, masks, keep = [], [], []
        for lo, hi in spans:
            lo, hi = int(lo), int(hi)
            packed.append(self._pack(x))
            mask = np.ones(SEQ_LEN, dtype=np.float32)
            m_lo, m_hi = max(0, lo - offset), max(0, hi - offset)
            mask[m_lo:m_hi] = 0.0  # 0 marks what MOMENT must reconstruct
            masks.append(mask)
            keep.append((m_lo, m_hi))

        out = []
        for i in range(0, len(packed), self.batch_size):
            chunk, mchunk = packed[i : i + self.batch_size], masks[i : i + self.batch_size]
            xt, im, mk = self._tensors(chunk, mchunk)
            with torch.no_grad():
                res = self.model.reconstruct(x_enc=xt, mask=mk, input_mask=im)
            rec = res.reconstruction.squeeze(1).float().cpu().numpy().astype(np.float64)
            out.extend(np.atleast_2d(rec))
        return [r[a:b] for r, (a, b) in zip(out, keep)]

    def encode(self, context: np.ndarray) -> list:  # pragma: no cover
        torch = self._torch
        values, input_mask = self._pack(np.asarray(context, dtype=np.float64))
        x = torch.tensor(values[None, None, :]).to(self.device)
        im = torch.tensor(input_mask[None, :]).to(self.device)
        with torch.no_grad():
            # reduction="none" keeps the patch axis, which is what gives the
            # representation signals something to vary along. The default
            # "mean" collapses it to a single vector and the inter-layer
            # dynamics become undefined.
            res = self.model.embed(x_enc=x, input_mask=im, reduction="none")
        emb = np.asarray(res.embeddings.squeeze().float().cpu().numpy(), dtype=np.float64)
        if emb.ndim == 1:
            emb = emb[None, :]
        n = min(self.n_layers, len(emb))
        return [b.mean(axis=0) for b in np.array_split(emb, max(n, 1))]
