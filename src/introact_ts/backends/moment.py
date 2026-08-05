"""MOMENT adapter.

MOMENT is the most natural fit for this probe and also the one whose API most
needs care. Its pretraining task *is* masked reconstruction, so reconstruction
and embeddings are genuinely zero-shot. Its forecasting head, by contrast, is
randomly initialised and expects fine-tuning -- calling it zero-shot would
measure noise. So forecasting here is derived the honest way: mask the horizon
and let the pretrained reconstruction head fill it in.

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

    def forecast_batch(self, contexts, horizon: int = None) -> list:  # pragma: no cover
        """Mask the horizon onto the end of the context and reconstruct it."""
        horizon = int(horizon or self.horizon)
        packed = []
        for c in contexts:
            x = np.asarray(c, dtype=np.float64)
            extended = np.concatenate([x, np.zeros(horizon)])
            values, input_mask = self._pack(extended)
            mask = np.ones(SEQ_LEN, dtype=np.float32)
            mask[-horizon:] = 0.0  # 0 marks the points MOMENT must invent
            packed.append((values, input_mask, mask))
        rec = self._reconstruct_masked(packed)
        return [r[-horizon:] for r in rec]

    def reconstruct_batch(self, series: np.ndarray, spans) -> list:  # pragma: no cover
        """Native masked reconstruction -- this is MOMENT's pretraining task."""
        x = np.asarray(series, dtype=np.float64)
        offset = max(0, len(x) - SEQ_LEN)
        packed, keep = [], []
        for lo, hi in spans:
            lo, hi = int(lo), int(hi)
            values, input_mask = self._pack(x)
            mask = np.ones(SEQ_LEN, dtype=np.float32)
            m_lo, m_hi = max(0, lo - offset), max(0, hi - offset)
            mask[m_lo:m_hi] = 0.0
            packed.append((values, input_mask, mask))
            keep.append((m_lo, m_hi))
        rec = self._reconstruct_masked(packed)
        return [r[a:b] for r, (a, b) in zip(rec, keep)]

    def encode(self, context: np.ndarray) -> list:  # pragma: no cover
        torch = self._torch
        values, input_mask = self._pack(context)
        x = torch.tensor(values[None, None, :]).to(self.device)
        im = torch.tensor(input_mask[None, :]).to(self.device)
        with torch.no_grad():
            out = self.model(x_enc=x, input_mask=im)
        emb = out.embeddings if hasattr(out, "embeddings") else out.reconstruction
        emb = emb.squeeze().float().cpu().numpy().astype(np.float64)
        if emb.ndim == 1:
            emb = emb[None, :]
        return [b.mean(axis=0) for b in np.array_split(emb, min(self.n_layers, len(emb)))]
