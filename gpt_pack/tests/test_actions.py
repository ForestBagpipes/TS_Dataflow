"""Operator contracts: purity, footprints, and refusal to over-reach."""

import numpy as np
import pytest
from conftest import synth

from introact_ts.actions import (
    apply_action,
    dominant_period,
    isolated_spikes,
    missing_mask,
    op_denoise,
    op_despike,
    op_impute,
    op_resegment,
)
from introact_ts.types import Action, MUTATING_ACTIONS


@pytest.mark.parametrize("action", list(Action))
def test_operators_never_mutate_their_input(action, clean_series):
    """The sandbox guarantee: an operator may not touch the array it was given."""
    x = clean_series.copy()
    x[100:140] = np.nan
    x[300] += 40.0
    before = x.copy()
    apply_action(x, action)
    assert np.array_equal(before, x, equal_nan=True)


def test_keep_is_identity(clean_series):
    out = apply_action(clean_series, Action.KEEP)
    assert out.applicable
    assert np.allclose(out.series, clean_series)


def test_impute_fills_every_gap():
    x = synth(1)
    x[150:190] = np.nan
    out = op_impute(x)
    assert out.applicable
    assert np.isfinite(out.series).all()
    assert out.params["n_filled"] == 40
    assert out.touched.sum() == 40


def test_impute_not_applicable_without_gaps(clean_series):
    assert not op_impute(clean_series).applicable


def test_impute_methods_differ_on_seasonal_data():
    x = synth(2)
    x[150:200] = np.nan
    lin = op_impute(x, method="linear")
    sea = op_impute(x, method="seasonal")
    assert lin.params["method"] == "linear"
    assert sea.params["n_seasonal_used"] > 0
    assert not np.allclose(lin.series, sea.series)


def test_despike_removes_spikes_and_reports_them():
    clean = synth(3)
    x = clean.copy()
    x[[80, 200, 350]] += 30.0
    out = op_despike(x)
    assert out.applicable
    assert out.params["n_replaced"] == 3
    assert out.touched.sum() == 3
    # The repair should land far closer to the truth than the corruption did.
    assert np.mean((out.series - clean) ** 2) < 0.05 * np.mean((x - clean) ** 2)


def test_despike_leaves_a_wide_real_excursion_alone():
    """A sustained event is not a spike, and the width filter must say so."""
    x = synth(4)
    x[220:260] += 25.0
    flags = isolated_spikes(x)
    assert flags[220:260].sum() == 0


def test_despike_ignores_a_merely_noisy_series():
    """Local MAD adapts to noise; the prominence filter stops false spikes."""
    x = synth(5, noise=3.0)
    frac = isolated_spikes(x).mean()
    assert frac < 0.01


def test_denoise_reduces_high_frequency_content():
    x = synth(6, noise=2.0)
    out = op_denoise(x, strength="medium")
    assert out.applicable
    assert np.std(np.diff(out.series)) < np.std(np.diff(x))


def test_denoise_declares_no_footprint():
    """It rewrites everything, so it is judged globally, not on a footprint."""
    out = op_denoise(synth(7), strength="light")
    assert out.touched is None
    assert Action.DENOISE in MUTATING_ACTIONS


def test_resegment_cuts_at_a_level_shift():
    x = synth(8)
    x[300:] += 25.0
    out = op_resegment(x)
    assert out.applicable
    assert len(out.series) < len(x)
    assert out.params["keep_frac"] >= 0.5


def test_resegment_refuses_to_discard_most_of_the_window():
    x = synth(9)
    x[60:] += 25.0  # the break sits so early that keeping the rest is a deletion
    out = op_resegment(x, min_keep_frac=0.95)
    assert not out.applicable


def test_flatline_detected_only_when_bracketed_by_activity():
    """A stuck sensor freezes out of movement; a quiet plateau does not."""
    x = synth(10)
    x[200:240] = x[200]
    assert missing_mask(x)[200:240].sum() > 0

    # A slow signal read at coarse resolution sits flat across its crest. The
    # neighbourhood there is as quiet as the plateau, so it is not a fault.
    t = np.arange(512, dtype=np.float64)
    quantised = np.round(5.0 * np.sin(2.0 * np.pi * t / 512.0), 1)
    assert missing_mask(quantised).sum() == 0


def test_dominant_period_recovers_a_known_period():
    t = np.arange(512, dtype=np.float64)
    x = np.sin(2.0 * np.pi * t / 24.0)
    assert abs(dominant_period(x) - 24) <= 2
