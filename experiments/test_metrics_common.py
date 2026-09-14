"""Tests for the canonical NMSE / repair RMSD definitions.

These run on the server, not locally, because they are part of the experiment
reproducibility pipeline. They cover the cases the P0 audit found ambiguous:
normal series, NaN handling, KEEP, level shift, unequal lengths, and the
robust_offset_local operator.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from metrics_common import canonical_nmse, repair_rmsd, ref_var  # noqa: E402


def test_normal_series():
    x = np.sin(np.linspace(0, 10, 512))
    c = x.copy()
    rv = ref_var(c)
    assert canonical_nmse(x, c, rv) == 0.0
    assert repair_rmsd(x, c) == 0.0

    # Additive noise: NMSE should be >0 and <1 for small noise.
    noisy = x + np.random.RandomState(0).randn(512) * 0.01
    nm = canonical_nmse(noisy, c, rv)
    assert 0.0 < nm < 1.0
    assert repair_rmsd(noisy, c) < 1.0


def test_nan_handling():
    c = np.sin(np.linspace(0, 10, 512))
    x = c.copy()
    x[100:120] = np.nan
    rv = ref_var(c)
    # Points where the difference is non-finite are masked out, so identical
    # remaining points give NMSE 0.
    assert canonical_nmse(x, c, rv) == 0.0
    # repair_rmsd does not mask and would be NaN; this is intentional.
    assert np.isnan(repair_rmsd(x, c))


def test_keep_baseline():
    c = np.linspace(0, 10, 512)
    x = c.copy()
    rv = ref_var(c)
    assert canonical_nmse(x, c, rv) == 0.0
    assert repair_rmsd(x, c) == 0.0


def test_level_shift():
    c = np.sin(np.linspace(0, 10, 512))
    x = c.copy()
    x[256:] += 5.0  # pure level shift
    rv = ref_var(c)
    before = canonical_nmse(x, c, rv)
    assert before > 0.0

    # A perfect repair removes the offset.
    y = x.copy()
    y[256:] -= 5.0
    after = canonical_nmse(y, c, rv)
    assert after < before
    assert repair_rmsd(y, c) < repair_rmsd(x, c)


def test_unequal_lengths():
    c = np.sin(np.linspace(0, 10, 512))
    x = c[:256]  # shorter window
    rv = ref_var(c)
    nm = canonical_nmse(x, c, rv)
    assert nm == 0.0
    assert repair_rmsd(x, c[:256]) == 0.0


def test_robust_offset_local():
    from route_conditioned_shift import op_robust_offset_local  # noqa: E402

    c = np.sin(np.linspace(0, 10, 512))
    x = c.copy()
    x[256:] += 5.0
    raw = op_robust_offset_local(x, penalty=12.0, min_size=24, local_width=24)
    assert raw is not None
    y = raw["series"]
    rv = ref_var(c)
    assert canonical_nmse(y, c, rv) < canonical_nmse(x, c, rv)
    assert repair_rmsd(y, c) < repair_rmsd(x, c)


if __name__ == "__main__":
    test_normal_series()
    test_nan_handling()
    test_keep_baseline()
    test_level_shift()
    test_unequal_lengths()
    test_robust_offset_local()
    print("all tests passed")
