"""v3.9 Phase 2 BRIDGE probe: pure-function unit tests.

No corpus, no GPU, no model weights: the eta mixing contract, the five risk
signals, the robust ECDF normalisation, the CP calibration bound, the grid
working-point selection and the AUROC/AUPRC arithmetic are all pure.
"""

import numpy as np
import pytest

import v39_bridge_probe as p2
import v39_longgap_probe as p1


def _gap_window(T=512, lo=200, hi=240, seed=0):
    rng = np.random.RandomState(seed)
    t = np.arange(T, dtype=np.float64)
    x = 3.0 * np.sin(2 * np.pi * t / 24.0) + 0.1 * rng.randn(T)
    x[lo:hi] = np.nan
    return x


# -- eta mixing -------------------------------------------------------------------


def test_mix_fill_endpoints_exact():
    rng = np.random.RandomState(0)
    b, m = rng.randn(40), rng.randn(40)
    assert np.array_equal(p2.mix_fill(b, m, 0.0), b)
    assert np.array_equal(p2.mix_fill(b, m, 1.0), m)
    z = p2.mix_fill(b, m, 0.25)
    assert np.allclose(z, b + 0.25 * (m - b))
    with pytest.raises(AssertionError):
        p2.mix_fill(b, m[:-1], 0.5)


def test_mix_inserted_has_zero_observed_drift():
    x = _gap_window()
    pos = np.flatnonzero(~np.isfinite(x))
    rng = np.random.RandomState(1)
    b, m = rng.randn(len(pos)), rng.randn(len(pos))
    for eta in p2.ETAS:
        y, filled = p1.insert_fill_at_raw_nan(x, p2.mix_fill(b, m, eta))
        obs = np.isfinite(x)
        assert np.array_equal(y[obs], x[obs])  # drift exactly 0
        assert filled.sum() == len(pos)


# -- signals ------------------------------------------------------------------------


def test_disagreement_and_deviation():
    a = np.array([0.0, 1.0, 2.0])
    assert p2.disagreement_abs(a, a) == 0.0
    assert p2.disagreement_abs(a, a + 2.0) == pytest.approx(2.0)
    b = np.zeros(4)
    m = np.ones(4) * 3.0
    assert p2.deviation_abs(p2.mix_fill(b, m, 0.5), b) == pytest.approx(1.5)
    assert p2.deviation_abs(p2.mix_fill(b, m, 1.0), b) == pytest.approx(3.0)


def test_seam_components_value_and_slope():
    T, lo, hi = 512, 200, 240
    t = np.arange(T, dtype=np.float64)
    x = 2.0 * t  # constant slope 2
    x[lo:hi] = np.nan
    import v38_explicit_impute_probe as v38p
    res = v38p.impute_explicit_linear(x, max_gap=2**31 - 1)
    y = res["series"]
    s = p2.seam_components(x, y, lo, hi, scale=1.0)
    assert s["left_value"] == pytest.approx(2.0)  # one step of the slope
    assert s["left_slope"] == pytest.approx(0.0)  # slopes match exactly
    assert s["right_slope"] == pytest.approx(0.0)
    assert s["max"] == pytest.approx(2.0)
    # kinked fill: flat inside the gap -> slope discontinuity
    y2 = y.copy()
    y2[lo:hi] = y[lo]
    s2 = p2.seam_components(x, y2, lo, hi, scale=1.0)
    assert s2["left_slope"] == pytest.approx(2.0)
    assert s2["max"] >= 2.0


def test_norm_by_mad_floor():
    assert p2.norm_by_mad(10.0, 2.0, 0.5) == pytest.approx(5.0)
    assert p2.norm_by_mad(10.0, 1e-13, 0.5) == pytest.approx(20.0)  # floored
    assert p2.mad_floor([1.0, 2.0, 3.0, 100.0], q=0.5) == pytest.approx(2.5)


# -- robust ECDF ---------------------------------------------------------------------


def test_robust_ecdf_monotone_and_bounded():
    fit = p2.robust_ecdf_fit([0.1, 0.2, 0.3, 0.4, 100.0])
    vals = [p2.robust_ecdf_eval(fit, v)
            for v in (-1e9, 0.05, 0.15, 0.5, 1e9)]
    assert all(0.0 <= v <= 1.0 for v in vals)
    assert all(a <= b for a, b in zip(vals, vals[1:]))
    assert vals[-1] == 1.0  # huge outlier winsorised to the top
    assert p2.robust_ecdf_eval(fit, None) == 1.0  # missing view = max risk
    assert p2.robust_ecdf_eval(fit, float("nan")) == 1.0
    with pytest.raises(AssertionError):
        p2.robust_ecdf_fit([])


def test_risk_modes():
    ns = {"width": 0.9, "disagreement": 0.4, "seam": 0.2, "deviation": 0.7}
    assert p2.risk_of(ns, "max_w_d_s") == pytest.approx(0.9)
    assert p2.risk_of(ns, "width_only") == pytest.approx(0.9)
    assert p2.risk_of(ns, "seam_only") == pytest.approx(0.2)
    assert p2.risk_of(ns, "drop_width") == pytest.approx(0.4)
    assert p2.risk_of(ns, "drop_seam") == pytest.approx(0.9)


# -- calibration bound and working-point selection -------------------------------------


def test_clopper_pearson_upper():
    assert p2.clopper_pearson_upper(0, 10) < 0.3
    assert p2.clopper_pearson_upper(0, 10) > 0.2
    assert p2.clopper_pearson_upper(5, 10) > 0.5
    assert p2.clopper_pearson_upper(0, 0) == 1.0
    assert p2.clopper_pearson_upper(3, 3) == 1.0
    # monotone in h
    ups = [p2.clopper_pearson_upper(h, 50) for h in range(6)]
    assert all(a < b for a, b in zip(ups, ups[1:]))


def _grid_row(tau, eta, n, bs, harm):
    return {"tau": tau, "eta": eta, "n_commits": n, "n_bs": bs,
            "n_harmful": harm,
            "chr": harm / n if n else None,
            "cp_upper": p2.clopper_pearson_upper(harm, n)}


def test_select_working_point_max_coverage_under_chr_bound():
    rows = [
        _grid_row(0.2, 1.0, 60, 55, 3),   # cp upper ~0.115 ok
        _grid_row(0.4, 1.0, 70, 60, 10),  # cp upper too high
        _grid_row(0.2, 0.5, 60, 52, 3),   # same coverage, fewer bs
        _grid_row(0.2, 1.0, 50, 50, 0),   # safe but less coverage
    ]
    sel = p2.select_working_point(rows)
    assert not sel["no_calibrated_point"]
    assert sel["selected"]["n_commits"] == 60
    assert sel["selected"]["n_bs"] == 55  # tie-break: more train B&S


def test_select_working_point_fallback_when_none_satisfy():
    rows = [_grid_row(0.2, 1.0, 5, 0, 5), _grid_row(0.4, 0.0, 8, 0, 8)]
    sel = p2.select_working_point(rows)
    assert sel["no_calibrated_point"]
    assert sel["selected"]["n_commits"] == 5  # lowest cp upper


# -- discrimination metrics ---------------------------------------------------------------


def test_auroc_perfect_and_chance():
    labels = [0, 0, 1, 1]
    assert p2.auroc([0.1, 0.2, 0.8, 0.9], labels) == pytest.approx(1.0)
    assert p2.auroc([0.9, 0.8, 0.2, 0.1], labels) == pytest.approx(0.0)
    assert p2.auroc([0.5, 0.5, 0.5, 0.5], labels) == pytest.approx(0.5)
    assert p2.auroc([0.1, 0.2], [1, 1]) is None  # no negatives


def test_average_precision():
    labels = [0, 0, 1, 1]
    assert p2.average_precision([0.1, 0.2, 0.8, 0.9],
                                labels) == pytest.approx(1.0)
    # positives ranked last: AP = (1/3 + 2/4) / 2
    assert p2.average_precision([0.9, 0.8, 0.2, 0.1],
                                labels) == pytest.approx((1 / 3 + 2 / 4) / 2)
    assert p2.average_precision([0.1], [0]) is None


# -- frozen grid / gate constants --------------------------------------------------------


def test_frozen_grid_and_gates_match_preregistration():
    assert p2.ETAS == (0.0, 0.25, 0.5, 0.75, 1.0)
    assert p2.RISK_QUANTILES == (0.2, 0.4, 0.6, 0.8)
    assert p2.BASE_PROPOSERS == ("tsicl", "openfim", "fm_mean", "moment")
    assert p2.PRIMARY_BASE == "fm_mean"
    assert p2.CHR_CALIB_UPPER == 0.15
    assert p2.GATE_AUROC == 0.70 and p2.GATE_AUPRC_LIFT == 0.10
    assert p2.GATE_MIN_COMMITS == 15 and p2.GATE_HELDOUT_CHR == 0.15
    assert p2.GATE_SOURCES_NONINFERIOR == 4
