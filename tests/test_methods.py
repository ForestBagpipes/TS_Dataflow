"""Smoke tests for IntroSpect-TS pure method layer.

Run with: pytest tests/ -v
"""

import numpy as np
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.introspect_ts.profiling import extract_statistical_profile
from src.introspect_ts.behavior import FakeTSFM, extract_behavior_signature
from src.introspect_ts.calibration import profile_conditioned_calibration
from src.introspect_ts.stratification import stratify_by_quality


def test_profiling_output_shape():
    series = np.sin(np.linspace(0, 20 * np.pi, 512)) + np.random.randn(512) * 0.1
    profile = extract_statistical_profile(series)
    assert profile.shape == (12,), f"Expected (12,), got {profile.shape}"
    assert np.all(np.isfinite(profile)), "Profile contains NaN or inf"


def test_profiling_deterministic():
    rng = np.random.RandomState(42)
    series = rng.randn(256)
    p1 = extract_statistical_profile(series)
    p2 = extract_statistical_profile(series)
    assert np.allclose(p1, p2), "Profile should be deterministic"


def test_fake_tsfm_behavior_shape():
    tsfm = FakeTSFM(L=12)
    series = np.random.randn(512)
    behavior = tsfm.extract_behavior_signature(series, quality=0.5, difficulty=0.3, seed=42)
    expected_D = 2 * tsfm.L + 3
    assert behavior.shape == (expected_D,), f"Expected ({expected_D},), got {behavior.shape}"


def test_fake_tsfm_quality_direction():
    tsfm = FakeTSFM(L=12, noise_std=0.0)
    series = np.sin(np.linspace(0, 20 * np.pi, 512))
    b_good = tsfm.extract_behavior_signature(series, quality=1.0, difficulty=0.0, seed=1)
    b_bad = tsfm.extract_behavior_signature(series, quality=-1.0, difficulty=0.0, seed=1)
    assert np.mean(b_good) < np.mean(b_bad), "Good quality should give lower behavior signal"


def test_calibration_output_shape():
    N, D_P, D_B = 100, 12, 27
    rng = np.random.RandomState(42)
    profiles = rng.randn(N, D_P)
    behaviors = rng.randn(N, D_B)
    scores = profile_conditioned_calibration(behaviors, profiles, K=10, seed=42)
    assert scores.shape == (N,), f"Expected ({N},), got {scores.shape}"
    assert np.all(np.isfinite(scores)), "Scores contain NaN or inf"


def test_calibration_recovery():
    """If behavior encodes quality strongly, calibrated q_i should correlate with it.

    The correlation direction is negative because q_i negates z-scores:
    higher raw behavior -> higher z -> lower (more negative) q_i.
    We check abs(r) > 0.3 to confirm correlation exists.
    """
    N, D_P, D_B = 200, 12, 27
    rng = np.random.RandomState(42)
    true_q = rng.uniform(-1, 1, N)
    profiles = rng.randn(N, D_P)
    behaviors = np.column_stack([true_q + rng.randn(N) * 0.01 for _ in range(D_B)])
    scores = profile_conditioned_calibration(behaviors, profiles, K=20, seed=42)
    from scipy.stats import spearmanr
    r, p = spearmanr(scores, true_q)
    assert abs(r) > 0.3, f"Expected |correlation| > 0.3, got r={r:.4f}"


def test_stratification():
    N = 100
    scores = np.arange(N, dtype=np.float64)
    result = stratify_by_quality(scores, alpha=0.25)
    assert len(result["top_indices"]) > 0
    assert len(result["mid_indices"]) > 0
    assert len(result["bottom_indices"]) > 0
    assert set(result["stratum_labels"]) == {0, 1, 2}


def test_stratification_empty_alpha():
    scores = np.arange(100, dtype=np.float64)
    result = stratify_by_quality(scores, alpha=0.001)
    top_ratio = len(result["top_indices"]) / 100.0
    assert top_ratio <= 0.01, f"Expected <=1% top at tiny alpha, got {top_ratio:.3f}"


def test_method_layer_zero_io():
    """Verify no file IO in method layer modules."""
    import ast
    modules = [
        "src.introspect_ts.profiling",
        "src.introspect_ts.behavior",
        "src.introspect_ts.calibration",
        "src.introspect_ts.stratification",
    ]
    io_keywords = {"open", "read_csv", "to_csv", "save", "load", "write", "Path("}
    base = Path(__file__).parent.parent
    for mod_name in modules:
        path = base / (mod_name.replace(".", "/") + ".py")
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                code = ast.get_source_segment(source, node)
                if code:
                    for kw in io_keywords:
                        if kw in code:
                            raise AssertionError(f"IO call '{kw}' found in {mod_name}: {code[:80]}")
    assert True


def test_behavior_signature_field_order():
    """Verify the (2L+3) signature field order is correct."""
    tsfm = FakeTSFM(L=12)
    series = np.sin(np.linspace(0, 10 * np.pi, 256))
    behavior = tsfm.extract_behavior_signature(series, quality=0.0, difficulty=0.0, seed=1)
    L = tsfm.L
    expected_D = 2 * L + 3
    assert len(behavior) == expected_D, f"Expected {expected_D}, got {len(behavior)}"
    assert behavior[0] >= 0
    assert behavior[1] >= 0
    assert behavior[2] >= 0
    for l_idx in range(L):
        assert behavior[3 + l_idx] >= 0
    for l_idx in range(L - 1):
        assert 0.0 <= behavior[3 + L + l_idx] <= 1.0
    assert behavior[-1] >= 0
