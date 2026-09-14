"""v3.8 Phase 1 IMPUTE_EXPLICIT_LINEAR contracts.

Pre-registration: docs/v3_8_fact_preregistration.md §2 (operator/certificate
layer) and §4 (gap tiers tight<=4 / medium<=8 / wide<=16, abstain defaults).
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
from conftest import synth

from introact_ts.probe import materialize_for_probe
from metrics_common import canonical_nmse, ref_var
from v33_labels import compute_action_labels
from v38_explicit_impute_probe import (
    GAP_CERT_TIERS,
    diagnostics,
    gap_certificate,
    impute_explicit_linear,
    label_candidate,
    synthetic_battery_digest,
)

ROOT = Path(__file__).resolve().parent.parent
T = 256


def _series_with_gaps(gaps, seed=3):
    x = synth(seed, T=T)
    for lo, hi in gaps:
        x[lo:hi] = np.nan
    return x


def _filled_positions(res):
    return res["filled"]


def test_touched_mask_equals_raw_nan_bitwise():
    """ touched = ~isfinite(raw), bit exact; flatlines never enter the mask."""
    x = _series_with_gaps([(30, 36), (100, 110)])
    x[150:180] = x[149]  # finite flatline run of 30 (>= MIN_FLATLINE_RUN)
    nm = ~np.isfinite(x)
    for cap in GAP_CERT_TIERS.values():
        res = impute_explicit_linear(x, cap)
        np.testing.assert_array_equal(res["touched"], nm)
        # the flatline is finite, so it is outside the mask and never filled
        assert not res["filled"][150:180].any()
        assert res["filled"].sum() <= nm.sum()
        np.testing.assert_array_equal(res["filled"], res["filled"] & nm)


def test_observed_finite_values_unchanged():
    """No originally finite value may move, checked value by value."""
    x = _series_with_gaps([(30, 36), (100, 110), (200, 201)])
    obs = np.isfinite(x)
    for cap in GAP_CERT_TIERS.values():
        y = impute_explicit_linear(x, cap)["series"]
        np.testing.assert_array_equal(y[obs], x[obs])


def test_observed_support_drift_exactly_zero():
    x = _series_with_gaps([(30, 36), (100, 110)])
    clean = synth(3, T=T)
    for cap in GAP_CERT_TIERS.values():
        res = impute_explicit_linear(x, cap)
        d = diagnostics(x, res["series"], clean, res)
        assert d["observed_support_drift"] == 0.0


def test_linear_fill_values_exact():
    x = np.array([0.0, np.nan, np.nan, 3.0, 4.0])
    res = impute_explicit_linear(x, 16)
    np.testing.assert_allclose(res["series"], [0.0, 1.0, 2.0, 3.0, 4.0])
    assert res["applicable"]


def test_boundary_gaps_abstain():
    """Gaps touching either window endpoint abstain and keep the KEEP value."""
    x = _series_with_gaps([(0, 5), (T - 4, T), (60, 64)])
    res = impute_explicit_linear(x, 16)
    keep = materialize_for_probe(x)
    np.testing.assert_array_equal(res["series"][:5], keep[:5])
    np.testing.assert_array_equal(res["series"][T - 4:], keep[T - 4:])
    assert res["filled"][60:64].all()  # the interior gap is filled
    reasons = {d["abstain_reason"] for d in res["gap_decisions"]
               if not d["certified"]}
    assert reasons == {"boundary_gap"}
    for d in res["gap_decisions"]:
        if d["lo"] == 0 or d["hi"] == T:
            assert not d["certified"]
            assert not (d["left_anchor"] and d["right_anchor"])


def test_no_anchor_abstain():
    """An all-NaN window has no anchor at all: everything abstains."""
    x = np.full(64, np.nan)
    res = impute_explicit_linear(x, 16)
    assert not res["applicable"]
    assert res["gap_decisions"][0]["abstain_reason"] == "no_anchor"
    # output = KEEP of an all-NaN window (zeros), still fully finite
    assert np.isfinite(res["series"]).all()


def test_tier_boundaries_4_8_16():
    """Tier edges: tight fills <=4, medium <=8, wide <=16, >16 abstains."""
    # gap lengths 4, 5, 8, 9, 16, 17 spaced well apart
    gaps = [(10, 14), (30, 35), (50, 58), (80, 89), (110, 126), (150, 167)]
    x = _series_with_gaps(gaps)
    res = {tier: impute_explicit_linear(x, cap)
           for tier, cap in GAP_CERT_TIERS.items()}

    def filled_lens(res):
        return sorted(d["length"] for d in res["gap_decisions"]
                      if d["certified"])

    assert filled_lens(res["tight"]) == [4]
    assert filled_lens(res["medium"]) == [4, 5, 8]
    assert filled_lens(res["wide"]) == [4, 5, 8, 9, 16]
    for tier, r in res.items():
        overlong = [d for d in r["gap_decisions"]
                    if d["abstain_reason"] == "overlong_gap"]
        cap = GAP_CERT_TIERS[tier]
        assert all(d["length"] > cap for d in overlong)
    # every >16 gap abstains even under wide
    assert any(d["length"] == 17 and not d["certified"]
               for d in res["wide"]["gap_decisions"])


def test_abstain_output_equals_materialized_keep():
    """When nothing is certified the output is exactly the KEEP series."""
    x = _series_with_gaps([(0, 8), (100, 130)])  # boundary + overlong
    res = impute_explicit_linear(x, 16)
    assert not res["applicable"]
    np.testing.assert_array_equal(res["series"], materialize_for_probe(x))
    assert np.isfinite(res["series"]).all()


def test_label_path_parity_with_v33(clean_series):
    """Same window, same output, two paths -> identical labels.

    Path 1: compute_action_labels called directly (the v3.3 table path).
    Path 2: the probe's label_candidate wrapper.
    """
    x = clean_series.copy()
    x[100:112] = np.nan
    y = impute_explicit_linear(x, 16)["series"]
    nm = ~np.isfinite(x)
    direct = compute_action_labels("IMPUTE", x, y, clean_series,
                                   touched=nm, params={})
    wrapped = label_candidate(x, y, clean_series, nm)
    assert direct.keys() == wrapped.keys()
    for k in direct:
        a, b = direct[k], wrapped[k]
        if isinstance(a, float) or isinstance(b, float):
            assert a == b, k
        else:
            assert a == b, k
    # the KEEP counterfactual must be the materialised series, not the raw
    rv = ref_var(clean_series)
    assert direct["before_nmse"] == canonical_nmse(
        materialize_for_probe(x), clean_series, rv)


def test_labels_gain_sign_matches_nmse(clean_series):
    """A perfect fill of an interior gap is beneficial and safe; a destructive
    one is harmful -- the label path reacts in the right direction."""
    x = clean_series.copy()
    x[100:112] = np.nan
    y = impute_explicit_linear(x, 16)["series"]
    lab = label_candidate(x, y, clean_series, ~np.isfinite(x))
    assert lab["true_repair_gain"] > 0.0
    assert lab["beneficial_and_safe"] == 1.0
    lab_bad = label_candidate(x, np.zeros_like(x), clean_series,
                              ~np.isfinite(x))
    assert lab_bad["true_loss"] == 1.0
    assert lab_bad["beneficial_and_safe"] == 0.0


def test_two_process_determinism():
    """The synthetic battery digest is identical across independent processes
    and matches the in-process computation."""
    code = (
        "import sys; "
        f"sys.path.insert(0, r'{ROOT / 'src'}'); "
        f"sys.path.insert(0, r'{ROOT / 'experiments'}'); "
        "import v38_explicit_impute_probe as m; "
        "print(m.synthetic_battery_digest())"
    )
    digests = []
    for _ in range(2):
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                             capture_output=True, text=True, check=True)
        digests.append(out.stdout.strip())
    assert digests[0] == digests[1]
    assert digests[0] == synthetic_battery_digest()
