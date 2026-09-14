"""v3.3 action-semantic label contracts (docs/v3_3_mast_pics_design.md §1)."""

import numpy as np
import pytest
from conftest import synth

from introact_ts.probe import (
    _naive_fill,
    materialize_for_probe,
    probe_window,
    reference_scale,
)
from metrics_common import (
    canonical_nmse,
    conditional_loss_metrics,
    ref_var,
)
from v33_labels import compute_action_labels, hash_array


def _gapped(clean, lo=200, hi=260):
    x = clean.copy()
    x[lo:hi] = np.nan
    return x


def test_materialize_is_public_and_aliased():
    x = np.array([1.0, np.nan, np.nan, 4.0])
    assert materialize_for_probe is _naive_fill
    np.testing.assert_allclose(materialize_for_probe(x), [1.0, 1.0, 1.0, 4.0])


def test_materialize_is_identity_on_finite_input(clean_series):
    np.testing.assert_array_equal(
        materialize_for_probe(clean_series), clean_series)


def test_probe_reads_the_materialised_series(models, clean_series):
    """The label counterfactual must be the exact input the probe queries."""
    x = _gapped(clean_series)
    scale = reference_scale(clean_series)
    a = probe_window(x, models, scale)
    b = probe_window(materialize_for_probe(x), models, scale)
    np.testing.assert_allclose(a.vector, b.vector)
    assert a.utility == b.utility


def test_nan_keep_before_nmse_is_not_zero(clean_series):
    """The v3.2 blind spot: a hole made before_nmse 0. It must not any more."""
    x = _gapped(clean_series)
    rv = ref_var(clean_series)
    assert canonical_nmse(x, clean_series, rv) == 0.0  # the old blind spot
    lab = compute_action_labels("IMPUTE", x, x, clean_series)
    assert lab["before_nmse"] > 0.0


def test_correct_interpolation_is_beneficial(clean_series):
    lo, hi = 200, 260
    x = _gapped(clean_series, lo, hi)
    y = x.copy()
    y[lo:hi] = clean_series[lo:hi]  # perfect repair of the hole
    lab = compute_action_labels(
        "IMPUTE", x, y, clean_series,
        touched=np.arange(lo, hi))
    assert lab["beneficial"] == 1.0
    assert lab["beneficial_and_safe"] == 1.0
    assert lab["true_repair_gain"] > 0.0


def test_fill_worse_than_forward_fill_is_harmful(clean_series):
    lo, hi = 200, 260
    x = _gapped(clean_series, lo, hi)
    ff = materialize_for_probe(x)
    y = x.copy()
    y[lo:hi] = ff[lo:hi] + 3.0 * np.std(clean_series)  # biased fill
    lab = compute_action_labels(
        "IMPUTE", x, y, clean_series, touched=np.arange(lo, hi))
    assert lab["beneficial"] == 0.0
    assert lab["harmful"] == 1.0
    assert lab["true_loss"] > 0.03


def test_impute_must_not_move_observed_support(clean_series):
    lo, hi = 200, 260
    x = _gapped(clean_series, lo, hi)
    y = x.copy()
    y[lo:hi] = clean_series[lo:hi]
    lab = compute_action_labels(
        "IMPUTE", x, y, clean_series, touched=np.arange(lo, hi))
    assert lab["observed_support_drift"] == pytest.approx(0.0, abs=1e-12)
    assert lab["target_mask_n"] == hi - lo
    assert lab["target_mask_gain"] > 0.0


def test_frozen_run_labels_reduce_to_old_definition(clean_series):
    """Finite frozen run: materialisation is the identity, x_keep == original."""
    x = clean_series.copy()
    x[300:340] = x[299]  # a finite stuck stretch, no NaN
    y = x.copy()
    y[300:340] = clean_series[300:340]
    lab = compute_action_labels(
        "IMPUTE", x, y, clean_series, touched=np.arange(300, 340))
    assert lab["missing_fraction"] == 0.0
    assert lab["missing_recovery_rate"] is None
    assert lab["keep_input_hash"] == hash_array(x)
    assert lab["beneficial"] == 1.0


def test_non_impute_labels_match_the_v32_code_path(clean_series):
    """DENOISE/DESPIKE labels must be the old inline formula, bit for bit."""
    rng = np.random.RandomState(7)
    x = clean_series + rng.randn(len(clean_series)) * 2.0
    y = clean_series + rng.randn(len(clean_series)) * 0.1
    rv = ref_var(clean_series)
    for fam in ("DENOISE", "DESPIKE"):
        lab = compute_action_labels(fam, x, y, clean_series)
        old_before = canonical_nmse(x, clean_series, rv)
        old_after = canonical_nmse(y, clean_series, rv)
        assert lab["before_nmse"] == old_before
        assert lab["after_nmse"] == old_after
        assert lab["keep_input_hash"] == hash_array(x)


def test_conditional_metrics_separate_rate_from_magnitude():
    losses = [0.0, 0.0, 0.5, 0.9]
    m = conditional_loss_metrics(losses)
    assert m["conditional_harm_rate"] == pytest.approx(0.5)
    assert m["conditional_mean_loss"] == pytest.approx(0.35)
    assert m["conditional_loss_p90"] > m["conditional_mean_loss"]
    assert m["n_committed"] == 4
    empty = conditional_loss_metrics([])
    assert empty["n_committed"] == 0
    assert np.isnan(empty["conditional_harm_rate"])
