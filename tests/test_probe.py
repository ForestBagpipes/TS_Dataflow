"""Probe and calibration invariants."""

import numpy as np
import pytest
from conftest import synth

from introact_ts.calibration import calibrate, ood_scores, recalibrate_one
from introact_ts.probe import (
    SIGNAL_NAMES,
    ProbeConfig,
    probe_window,
    reference_scale,
)
from introact_ts.profiling import extract_statistical_profile
from introact_ts.tsfm import SurrogateTSFM


def test_probe_is_deterministic(models, clean_series):
    scale = reference_scale(clean_series)
    a = probe_window(clean_series, models, scale)
    b = probe_window(clean_series, models, scale)
    assert np.allclose(a.vector, b.vector)
    assert a.utility == b.utility


def test_probe_vector_matches_signal_names(models, clean_series):
    r = probe_window(clean_series, models, reference_scale(clean_series))
    assert r.dim == len(SIGNAL_NAMES)
    assert np.isfinite(r.vector).all()
    assert np.isfinite(r.utility)


def test_utility_is_scale_free_under_a_fixed_reference(models):
    """Rescaling the data must not, by itself, change the measured utility."""
    x = synth(1)
    a = probe_window(x, models, reference_scale(x))
    b = probe_window(10.0 * x, models, reference_scale(10.0 * x))
    assert abs(a.utility - b.utility) < 0.05 * max(abs(a.utility), 1.0)


def test_the_ruler_must_be_fixed_for_a_difference_to_mean_anything(models):
    """An edit that moves the spread also moves a self-scaled denominator.

    Measured against its own spread, a smoothed series is judged with a
    different instrument than the original was -- so the utility difference
    would partly report the change of ruler rather than the change of data.
    """
    from introact_ts.actions import apply_action
    from introact_ts.types import Action

    x = synth(2, noise=1.0)
    scale = reference_scale(x)
    smoothed = apply_action(x, Action.DENOISE, strength="heavy").series
    own_scale = reference_scale(smoothed)

    assert own_scale != pytest.approx(scale, rel=1e-3)
    pinned = probe_window(smoothed, models, scale).utility
    self_scaled = probe_window(smoothed, models, own_scale).utility
    assert pinned != pytest.approx(self_scaled, rel=1e-6)


def test_corruption_lowers_utility(models):
    clean = synth(3)
    spiked = clean.copy()
    spiked[[80, 200, 350]] += 30.0
    scale = reference_scale(clean)
    assert probe_window(spiked, models, scale).utility < probe_window(
        clean, models, scale
    ).utility


def test_probe_handles_nan_without_repairing_them(models):
    """Forward-fill, not interpolation: a fill must have something to improve."""
    x = synth(4)
    gapped = x.copy()
    gapped[200:260] = np.nan
    scale = reference_scale(x)
    r = probe_window(gapped, models, scale)
    assert np.isfinite(r.utility)
    assert r.utility < probe_window(x, models, scale).utility


def test_calibration_shapes_and_recalibration_consistency(models):
    xs = [synth(i) for i in range(30)]
    P = np.stack([extract_statistical_profile(x) for x in xs])
    B = np.stack([probe_window(x, models, reference_scale(x)).vector for x in xs])
    cal = calibrate(B, P, SIGNAL_NAMES, K=8)
    assert cal.z.shape == B.shape
    assert cal.risk.shape == (len(xs),)

    z, risk = recalibrate_one(
        B[0], cal.centers[0], cal.spreads[0], SIGNAL_NAMES
    )
    assert np.allclose(z, cal.z[0])
    assert abs(risk - cal.risk[0]) < 1e-9


def test_ood_score_flags_a_structurally_alien_window(models):
    xs = [synth(i) for i in range(20)]
    alien = np.cumsum(np.random.RandomState(0).randn(512)) * 5.0
    P = np.stack([extract_statistical_profile(x) for x in xs + [alien]])
    scores = ood_scores(P, K=8)
    assert scores[-1] > np.median(scores[:-1])


def test_surrogate_beats_a_naive_forecast():
    model = SurrogateTSFM(seed=0)
    errs_model, errs_naive = [], []
    for i in range(10):
        x = synth(100 + i)
        ctx, tgt = x[:480], x[480:]
        errs_model.append(np.mean((model.forecast(ctx, 32) - tgt) ** 2))
        errs_naive.append(np.mean((ctx[-1] - tgt) ** 2))
    assert np.mean(errs_model) < 0.5 * np.mean(errs_naive)


def test_surrogate_is_reproducible_from_its_seed():
    a = SurrogateTSFM(seed=3).forecast(synth(0)[:480], 32)
    b = SurrogateTSFM(seed=3).forecast(synth(0)[:480], 32)
    assert np.allclose(a, b)
    c = SurrogateTSFM(seed=4).forecast(synth(0)[:480], 32)
    assert not np.allclose(a, c)
