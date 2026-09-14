"""Tests for the v3.5 Phase 2 TSFM_RECONSTRUCT_IMPUTE operator probe.

Pre-registered invariants (§3/§6): the operator fills exactly the real NaN
runs, never modifies an observed finite value, never mutates its input, is
deterministic, stays a candidate action (no auto-commit path exists), and
the records stage reads no evaluation fields (source scan). All synthetic,
on the offline surrogate pool: no corpus, no GPU.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v35_tsfm_impute_probe as probe2  # noqa: E402
from introact_ts.backends import make_model_pool  # noqa: E402
from introact_ts.probe import materialize_for_probe  # noqa: E402
from v33_labels import hash_array  # noqa: E402


def _series(T=256, seed=3):
    rng = np.random.RandomState(seed)
    t = np.arange(T, dtype=np.float64)
    return np.cumsum(rng.randn(T)) + 2.0 * np.sin(2 * np.pi * t / 24.0)


def _model():
    return make_model_pool((0,))[0]


# -- observed finite values are untouchable (§3.3) ---------------------------------


def test_observed_finite_values_never_modified():
    x = _series()
    x[40:60] = np.nan
    x[150:155] = np.nan
    y, spans = probe2.tsfm_reconstruct_impute(_model(), x)
    observed = np.isfinite(x)
    assert np.array_equal(y[observed], x[observed])
    assert spans == [(40, 60), (150, 155)]


def test_all_nan_runs_filled_and_finite_output():
    x = _series()
    x[40:60] = np.nan
    x[150:155] = np.nan
    y, spans = probe2.tsfm_reconstruct_impute(_model(), x)
    assert np.isfinite(y).all()
    # The fill is NOT the forward-fill base (the model reconstructed it).
    base = materialize_for_probe(x)
    changed = [not np.array_equal(y[lo:hi], base[lo:hi])
               for lo, hi in spans]
    assert any(changed)


def test_no_nan_window_is_identity():
    x = _series()
    y, spans = probe2.tsfm_reconstruct_impute(_model(), x)
    assert spans == []
    assert np.array_equal(y, materialize_for_probe(x))
    assert np.array_equal(y, x)


def test_input_array_not_mutated():
    x = _series()
    x[40:60] = np.nan
    before = x.copy()
    probe2.tsfm_reconstruct_impute(_model(), x)
    assert np.array_equal(np.isfinite(before), np.isfinite(x))
    assert np.allclose(before[np.isfinite(before)], x[np.isfinite(x)])


def test_operator_deterministic():
    x = _series()
    x[40:60] = np.nan
    y1, s1 = probe2.tsfm_reconstruct_impute(_model(), x)
    y2, s2 = probe2.tsfm_reconstruct_impute(_model(), x)
    assert s1 == s2
    assert hash_array(y1) == hash_array(y2)
    assert np.array_equal(y1, y2)


# -- verifier disagreement plumbing ---------------------------------------------------


def test_verifier_disagreement_runs_without_seeing_fill():
    x = _series()
    x[40:60] = np.nan
    models = make_model_pool((0, 1))
    base = materialize_for_probe(x)
    y, spans = probe2.tsfm_reconstruct_impute(models[0], x)
    d = probe2.verifier_disagreement(models[1], base, spans, y,
                                     scale=1.0)
    assert d["n_spans_valid"] == len(spans)
    assert d["mean_abs_gap"] is not None and d["mean_abs_gap"] >= 0.0
    # A fill overwritten with absurd values changes nothing the verifier
    # reconstructs (the leak-freedom contract of flat_reconstruct).
    y_absurd = y.copy()
    y_absurd[40:60] = 1e9
    d2 = probe2.verifier_disagreement(models[1], base, spans, y_absurd,
                                      scale=1.0)
    assert d2["n_spans_valid"] == d["n_spans_valid"]


def test_verifier_disagreement_empty_spans():
    x = _series()
    d = probe2.verifier_disagreement(_model(), x, [], x, scale=1.0)
    assert d == {"mean_abs_gap": None, "n_spans_valid": 0}


# -- frozen configuration --------------------------------------------------------------


def test_default_rung_params_frozen():
    assert probe2.DEFAULT_IMPUTE_PARAMS == {"method": "linear",
                                            "min_run": 16}


def test_model_status_honest_about_single_native_backend():
    cfg = probe2.probe_config()
    assert cfg["proposer_native_reconstruct"] is True
    assert "ForecastOnlyMixin" in cfg["verifier_reconstruct"]


# -- source scan: records stage reads no evaluation fields ----------------------------


def test_probe_source_free_of_evaluation_fields():
    src = (ROOT / "experiments" / "v35_tsfm_impute_probe.py").read_text(
        encoding="utf-8")
    src = src.replace("from v33_labels import hash_array", "")
    forbidden = ["true_kind", "clean", "beneficial", "harmful", "true_loss",
                 "label", "before_nmse", "after_nmse", "clean_hash"]
    low = src.lower()
    for tok in forbidden:
        assert tok not in low, f"probe source references {tok!r}"
