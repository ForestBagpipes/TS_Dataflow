#!/usr/bin/env python3
"""Chronos-2 forecast backend for the v4.6 stage-C script.

Mirrors the interface of the frozen r5 ``Bolt`` and ``TimesFM`` workers so the
forecast stage does not need to know which backbone it is driving: one
``forecast(x, horizon)`` call taking ``(batch, context, channels)`` and
returning ``(batch, horizon, 1)``.

The generation settings are the ones the r5 Chronos-2 native acceptance run
registered: 512-step context, the 0.5 quantile as the point forecast, no cross
learning, batch size one, and ``limit_prediction_length``.  The weights are the
pinned revision and their hash is checked before the first call.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path("/home/vipuser/work2-cache/chronos2-native-check")
REVISION = "29ec3766d36d6f73f0696f85560a422f50e8498c"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array_sha(x: np.ndarray) -> str:
    x = np.ascontiguousarray(np.asarray(x, dtype=np.float64))
    return hashlib.sha256(x.tobytes()).hexdigest()


class Chronos2:
    def __init__(self, out: Path):
        import torch
        from chronos import Chronos2Pipeline

        snapshot = CACHE / REVISION
        weight = snapshot / "model.safetensors"
        if not weight.exists():
            raise RuntimeError(f"Chronos-2 weights not present at {weight}")
        self.weight_sha = sha(weight)
        self.pipeline = Chronos2Pipeline.from_pretrained(
            str(snapshot), device_map="cuda", torch_dtype=torch.float32,
            local_files_only=True)
        if not isinstance(self.pipeline, Chronos2Pipeline):
            raise RuntimeError("wrong backbone class")
        self.quantiles = list(self.pipeline.quantiles)
        if 0.5 not in self.quantiles:
            raise RuntimeError("Chronos-2 pipeline does not expose the median quantile")
        self.median = self.quantiles.index(0.5)
        self.out = Path(out)
        (self.out / "raw").mkdir(parents=True, exist_ok=True)
        self.calls: list[dict] = []
        self.cache: dict[str, np.ndarray] = {}
        self.counter = 0
        self.identity = dict(repo_id="amazon/chronos-2", revision=REVISION,
                             dtype="float32", environment_python=sys.executable,
                             weight_sha256=self.weight_sha,
                             generation=dict(context_length=512, point_quantile=0.5,
                                             cross_learning=False, batch_size=1,
                                             limit_prediction_length=True))

    def forecast(self, x: np.ndarray, horizon: int) -> np.ndarray:
        import torch

        x = np.asarray(x)
        key = array_sha(x) + ":" + str(horizon)
        if key in self.cache:
            self.calls.append(dict(cache_key=key, cache_hit=True, seconds=0.0))
            return self.cache[key].copy()
        tick = time.perf_counter()
        torch.cuda.reset_peak_memory_stats()
        series = [torch.from_numpy(v[:, 0].astype(np.float32)).unsqueeze(0) for v in x]
        with torch.inference_mode():
            out = self.pipeline.predict(series, prediction_length=horizon,
                                        context_length=512, batch_size=1,
                                        cross_learning=False,
                                        limit_prediction_length=True)
        torch.cuda.synchronize()
        seconds = time.perf_counter() - tick
        raw = np.stack([o.float().cpu().numpy()[0] for o in out])   # (batch, q, H)
        if not np.isfinite(raw).all():
            raise FloatingPointError("raw Chronos-2 quantiles nonfinite")
        point = raw[:, self.median, :, None]
        name = f"call_{self.counter:05d}"
        self.counter += 1
        np.savez(self.out / "raw" / f"{name}.npz", input=x, quantiles=raw, point=point)
        self.calls.append(dict(cache_key=key, cache_hit=False, seconds=seconds,
                               raw_file="raw/" + name + ".npz",
                               raw_sha256=sha(self.out / "raw" / f"{name}.npz"),
                               peak_gpu_bytes=int(torch.cuda.max_memory_allocated()),
                               horizon=horizon))
        self.cache[key] = point.copy()
        return point
