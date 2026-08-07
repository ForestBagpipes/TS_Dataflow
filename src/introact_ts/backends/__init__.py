"""Frozen backend registry.

Backends are named by ``family:checkpoint``, e.g. ``chronos:amazon/chronos-bolt-base``
or just ``surrogate``. Adapters import their dependency lazily, so a missing
package disables exactly one family instead of breaking the run.

``probe_report`` exists because the adapters cannot be verified without the
weights: it loads each requested backend, exercises the full probe surface, and
reports what actually worked. Run it once on the machine that has the GPU
before committing to a long experiment.
"""

import numpy as np

from .base import (
    ALL_CAPABILITIES,
    CAP_ENCODE,
    CAP_FORECAST,
    CAP_RECONSTRUCT,
    ForecastOnlyMixin,
    TSFMBackend,
    probe_signature,
)
from .surrogate import SurrogateTSFM, make_reference_corpus

#: family -> (module path, class name, default checkpoint)
FAMILIES = {
    "surrogate": ("introact_ts.backends.surrogate", "SurrogateTSFM", None),
    "chronos": ("introact_ts.backends.chronos", "ChronosTSFM", "amazon/chronos-bolt-base"),
    "moment": ("introact_ts.backends.moment", "MomentTSFM", "AutonLab/MOMENT-1-large"),
    "timesfm": ("introact_ts.backends.timesfm", "TimesFMTSFM", "google/timesfm-2.5-200m-pytorch"),
}

#: Suggested pools. The judge drives curation; the transfer pool never takes
#: part in it and exists only to test whether the benefit generalises.
PRESETS = {
    "offline": {
        "curation": ["surrogate:0", "surrogate:1", "surrogate:2"],
        "transfer": ["surrogate:7", "surrogate:11"],
    },
    "chronos-only": {
        "curation": [
            "chronos:amazon/chronos-bolt-base",
            "chronos:amazon/chronos-bolt-small",
            "chronos:amazon/chronos-t5-small",
        ],
        "transfer": ["chronos:amazon/chronos-t5-base", "surrogate:7"],
    },
    # Verified on an RTX 5090 against a seasonal-naive reference: bolt-base
    # 0.29x, bolt-small 0.27x, timesfm 0.27x, t5-small 0.91x. MOMENT is
    # deliberately excluded -- its zero-shot forecast is 20x naive (see
    # `backends/moment.py`), and the judge's forecast error dominates utility.
    "multi-family": {
        "curation": [
            "chronos:amazon/chronos-bolt-base",
            "timesfm:google/timesfm-2.5-200m-pytorch",
            "chronos:amazon/chronos-bolt-small",
        ],
        "transfer": ["chronos:amazon/chronos-t5-small", "surrogate:7"],
    },
    # MOMENT's genuine strengths, for the reconstruction/representation study.
    # Not for headline curation runs.
    "moment-recon": {
        "curation": ["moment:AutonLab/MOMENT-1-large"],
        "transfer": ["chronos:amazon/chronos-bolt-small"],
    },
}


def parse_spec(spec: str) -> tuple:
    """``family:checkpoint`` -> (family, checkpoint or None)."""
    if ":" not in spec:
        return spec, None
    family, rest = spec.split(":", 1)
    return family, rest


def make_backend(spec: str, device: str = "cuda", horizon: int = 32, **kw):
    """Build one backend from its spec string."""
    family, checkpoint = parse_spec(spec)
    if family not in FAMILIES:
        raise ValueError(f"unknown backend family {family!r}; have {sorted(FAMILIES)}")

    if family == "surrogate":
        seed = int(checkpoint) if checkpoint is not None else 0
        return SurrogateTSFM(seed=seed, horizon=horizon)

    import importlib

    module_path, class_name, default_ckpt = FAMILIES[family]
    cls = getattr(importlib.import_module(module_path), class_name)
    return cls(
        model_name=checkpoint or default_ckpt, device=device, horizon=horizon, **kw
    )


def make_pool(specs, device: str = "cuda", horizon: int = 32) -> list:
    """Build a list of backends, skipping any that fail to load."""
    pool, failures = [], []
    for spec in specs:
        try:
            pool.append(make_backend(spec, device=device, horizon=horizon))
        except Exception as exc:
            failures.append((spec, f"{type(exc).__name__}: {exc}"))
    if failures and not pool:
        detail = "; ".join(f"{s} ({e})" for s, e in failures)
        raise RuntimeError(f"no backend could be loaded: {detail}")
    for spec, err in failures:
        print(f"  [skip] {spec}: {err}")
    return pool


def make_model_pool(seeds=(0, 1, 2), horizon: int = 32) -> list:
    """Offline surrogate pool. Kept as the default for tests and local runs."""
    return [SurrogateTSFM(seed=s, horizon=horizon) for s in seeds]


def probe_report(specs, device: str = "cuda", horizon: int = 32) -> list:
    """Load each backend and exercise the probe surface it claims to support.

    Returns one record per spec describing what loaded, what ran, and what the
    forecast quality looked like against a seasonal-naive reference. This is
    the check to run before a long experiment: an adapter that imports fine can
    still return the wrong shape or a degenerate forecast.
    """
    rng = np.random.RandomState(0)
    t = np.arange(512, dtype=np.float64)
    series = 5.0 * np.sin(2.0 * np.pi * t / 24.0) + 0.01 * t + rng.randn(512) * 0.3
    ctx, tgt = series[:480], series[480:]
    naive = np.tile(ctx[-24:], 2)[: len(tgt)]
    naive_mse = float(np.mean((naive - tgt) ** 2))

    records = []
    for spec in specs:
        rec = {"spec": spec, "loaded": False, "checks": {}, "error": None}
        try:
            backend = make_backend(spec, device=device, horizon=horizon)
            rec["loaded"] = True
            rec.update(probe_signature(backend))
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
            records.append(rec)
            continue

        def check(name, fn):
            try:
                rec["checks"][name] = fn()
            except Exception as exc:
                rec["checks"][name] = f"FAIL {type(exc).__name__}: {exc}"

        def _forecast():
            p = backend.forecast_batch([ctx], 32)[0]
            assert len(p) == 32, f"expected 32 steps, got {len(p)}"
            assert np.isfinite(p).all(), "forecast contains non-finite values"
            mse = float(np.mean((p - tgt[:32]) ** 2))
            return {
                "ok": True,
                "mse": round(mse, 4),
                "vs_seasonal_naive": round(mse / max(naive_mse, 1e-9), 3),
            }

        def _batch():
            out = backend.forecast_batch([ctx, ctx[:400], ctx[:300]], 32)
            assert len(out) == 3, f"batch of 3 returned {len(out)}"
            return {"ok": True}

        def _reconstruct():
            spans = [(100, 124), (200, 224), (300, 324)]
            recs = backend.reconstruct_batch(series, spans)
            assert len(recs) == 3
            errs = [
                float(np.mean((r - series[a:b]) ** 2)) for r, (a, b) in zip(recs, spans)
            ]
            return {"ok": True, "mse": round(float(np.mean(errs)), 4)}

        def _encode():
            states = backend.encode(ctx)
            assert len(states) >= 2, f"expected >=2 layers, got {len(states)}"
            return {"ok": True, "n_layers": len(states), "dim": int(np.size(states[0]))}

        check("forecast", _forecast)
        check("forecast_batch", _batch)
        check("reconstruct", _reconstruct)
        if CAP_ENCODE in getattr(backend, "capabilities", frozenset()):
            check("encode", _encode)
        records.append(rec)
        del backend
    return records


__all__ = [
    "ALL_CAPABILITIES",
    "CAP_ENCODE",
    "CAP_FORECAST",
    "CAP_RECONSTRUCT",
    "FAMILIES",
    "PRESETS",
    "ForecastOnlyMixin",
    "SurrogateTSFM",
    "TSFMBackend",
    "make_backend",
    "make_model_pool",
    "make_pool",
    "make_reference_corpus",
    "parse_spec",
    "probe_report",
    "probe_signature",
]
