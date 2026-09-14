"""Shared fixtures. Puts ``src`` and ``experiments`` on the path."""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))


def synth(seed: int = 0, T: int = 512, noise: float = 0.3) -> np.ndarray:
    """A clean seasonal-plus-trend series; the base every fixture builds on."""
    rng = np.random.RandomState(seed)
    t = np.arange(T, dtype=np.float64)
    return (
        5.0 * np.sin(2.0 * np.pi * t / 24.0 + rng.rand() * 6.0)
        + 0.01 * rng.uniform(-1.0, 1.0) * t
        + rng.randn(T) * noise
    )


@pytest.fixture
def clean_series():
    return synth(0)


@pytest.fixture(scope="session")
def models():
    from introact_ts.tsfm import make_model_pool

    return make_model_pool((0, 1, 2))
