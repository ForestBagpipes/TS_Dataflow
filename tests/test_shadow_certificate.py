"""Tests for the v3.4 Phase 2 shadow intervention certificate.

Covers the pre-registered integrity requirements of
``docs/v3_4_scrc_pics_preregistration.md`` §6: deterministic masks, masks
never touching real missing evidence, a certificate path that cannot read
ground truth, value-identical operator behaviour against the formal IMPUTE
implementation, abstain behaviour on unsupported windows, and bit-identical
results across independent processes.
"""

import inspect
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v34_shadow_certificate as sc  # noqa: E402
from introact_ts.actions import Action, apply_action, missing_mask  # noqa: E402
from v33_labels import hash_array  # noqa: E402


def _block_series(T=256, lo=120, hi=140, seed=7):
    rng = np.random.RandomState(seed)
    x = np.cumsum(rng.randn(T))
    x[lo:hi] = np.nan
    return x


def _scattered_series(T=256, seed=11):
    rng = np.random.RandomState(seed)
    t = np.arange(T, dtype=np.float64)
    x = 3.0 * np.sin(2 * np.pi * t / 24.0) + rng.randn(T) * 0.3
    x[np.linspace(20, 230, 10).astype(int)] = np.nan
    return x


def _flatline_series(T=256, lo=160, hi=200, seed=13):
    rng = np.random.RandomState(seed)
    x = np.cumsum(rng.randn(T))
    x[lo:hi] = x[lo - 1]
    return x


# -- mask determinism ----------------------------------------------------------


def test_masks_bit_deterministic():
    uid = "DS:contaminated:missing_block:aa:bb"
    x = _block_series()
    first = sc.shadow_masks(uid, x)
    second = sc.shadow_masks(uid, x)
    assert len(first) == sc.N_REPLICAS
    for a, b in zip(first, second):
        assert (a is None) == (b is None)
        if a is not None:
            assert np.array_equal(a, b)


def test_masks_depend_on_uid_and_replica():
    x = _block_series()
    a = sc.shadow_masks("uid-A", x)
    b = sc.shadow_masks("uid-B", x)
    assert any(not np.array_equal(x1, x2) for x1, x2 in zip(a, b))
    per_rep = [sc.make_shadow_mask("uid-A", x, r) for r in range(sc.N_REPLICAS)]
    assert any(not np.array_equal(per_rep[0], m) for m in per_rep[1:])


def test_masks_deterministic_on_scattered_geometry():
    uid = "DS:contaminated:missing_scattered:cc:dd"
    x = _scattered_series()
    assert sc.geometry_of(x) == "scattered"
    for a, b in zip(sc.shadow_masks(uid, x), sc.shadow_masks(uid, x)):
        assert (a is None) == (b is None)
        if a is not None:
            assert np.array_equal(a, b)


# -- masks never touch real missing --------------------------------------------


@pytest.mark.parametrize("series", [
    _block_series(), _scattered_series(), _flatline_series(),
])
def test_masks_avoid_real_missing(series):
    ev = missing_mask(series, min_run=sc.EVIDENCE_MIN_RUN)
    for r in range(sc.N_REPLICAS):
        mask = sc.make_shadow_mask("uid-X", series, r)
        if mask is None:
            continue
        assert not (mask & ev).any()
        assert not (mask & ~np.isfinite(series)).any()
        assert np.isfinite(series[mask]).all()


def test_geometry_from_nan_layout_only():
    assert sc.geometry_of(_block_series()) == "block"
    assert sc.geometry_of(_scattered_series()) == "scattered"
    rng = np.random.RandomState(3)
    assert sc.geometry_of(np.cumsum(rng.randn(128))) == "block"  # no evidence


# -- ground truth cannot enter the certificate path -----------------------------


def test_certificate_path_reads_no_ground_truth():
    forbidden = ("true_kind", "clean_series", "clean_hash", "clean_ref",
                 "w.clean", "eval_labels")
    for fn in (sc.shadow_seed, sc.evidence_mask, sc.geometry_of,
               sc.make_shadow_mask, sc.shadow_masks, sc.certificate_operator,
               sc.observed_ref_var, sc.run_trial, sc.certify_candidate,
               sc._certify_uid):
        src = inspect.getsource(fn)
        for tok in forbidden:
            assert tok not in src, f"{fn.__name__} references {tok}"


def test_certify_candidate_signature_takes_no_labels():
    params = list(inspect.signature(sc.certify_candidate).parameters)
    assert params == ["sample_uid", "series", "params", "masks", "rv"]


# -- operator path identical to the formal IMPUTE implementation ----------------


@pytest.mark.parametrize("params", [
    {"method": "linear", "min_run": 16},
    {"method": "seasonal", "min_run": 8},
    {"method": "linear", "min_run": 32},
])
def test_certificate_operator_value_identical_to_apply_action(params):
    x = _block_series()
    cert = sc.certificate_operator(x, params)
    formal = apply_action(x.copy(), Action.IMPUTE, **params)
    assert cert.applicable == formal.applicable
    np.testing.assert_array_equal(
        np.nan_to_num(cert.series, nan=-9.999e99),
        np.nan_to_num(formal.series, nan=-9.999e99))
    assert hash_array(cert.series) == hash_array(formal.series)
    real_missing = missing_mask(x, min_run=params["min_run"])
    np.testing.assert_array_equal(cert.series[real_missing],
                                  formal.series[real_missing])


# -- abstain behaviour ------------------------------------------------------------


def test_abstain_when_observation_span_insufficient():
    # 10 observed islands of 3 points inside a sea of NaN: no block of
    # 4 + 2*CLEARANCE observed points exists and scattered placement cannot
    # find enough eligible points either, so no valid trial can complete.
    x = np.full(256, np.nan)
    for start in range(0, 250, 25):
        x[start:start + 3] = np.arange(3, dtype=np.float64)
    rec = sc.certify_candidate("uid-sparse", x, {"method": "linear",
                                                 "min_run": 16})
    assert rec["features"]["shadow_valid_trials"] < sc.MIN_VALID_TRIALS
    assert rec["features"]["shadow_support"] == 0
    assert rec["features"]["shadow_gain_mean"] is None
    assert rec["features"]["shadow_stability"] is None


def test_support_one_on_healthy_window():
    rec = sc.certify_candidate("uid-ok", _block_series(),
                               {"method": "linear", "min_run": 16})
    f = rec["features"]
    assert f["shadow_valid_trials"] == sc.N_REPLICAS
    assert f["shadow_support"] == 1
    assert np.isfinite(f["shadow_gain_mean"])
    # A linear fill of a random-walk gap must beat forward-fill on average.
    assert f["shadow_gain_mean"] > 0


# -- multiprocess bit consistency -------------------------------------------------


def test_selftest_bit_identical_across_processes(tmp_path):
    outs = [tmp_path / f"run{i}.jsonl" for i in range(2)]
    for out in outs:
        proc = subprocess.run(
            [sys.executable,
             str(ROOT / "experiments" / "v34_shadow_certificate.py"),
             "--selftest", str(out)],
            capture_output=True, text=True, cwd=str(ROOT), timeout=300)
        assert proc.returncode == 0, proc.stderr[-2000:]
        assert "___V34_SHADOW_SELFTEST_DONE___" in proc.stdout
    assert outs[0].read_bytes() == outs[1].read_bytes()
    rows = [json.loads(l) for l in outs[0].read_text().splitlines()]
    assert len(rows) == 3 * 3  # 3 windows x 3 candidate param sets
    for r in rows:
        assert r["features"]["shadow_support"] == 1
