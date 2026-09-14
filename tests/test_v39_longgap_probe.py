"""v3.9 Phase 1 long-gap probe: pure-function unit tests.

No corpus, no GPU, no model weights: the population selector, the fill
insertion contract, the seam/uncertainty diagnostics, the oracle pool
discipline and the per-proposer five-quantity arithmetic are all pure.
"""

import numpy as np
import pytest

import v38_explicit_impute_probe as v38p
import v39_longgap_probe as p1
from introact_ts.probe import materialize_for_probe


def _gap_window(T=512, lo=200, hi=240, seed=0):
    rng = np.random.RandomState(seed)
    t = np.arange(T, dtype=np.float64)
    x = 3.0 * np.sin(2 * np.pi * t / 24.0) + 0.1 * rng.randn(T)
    x[lo:hi] = np.nan
    return x


def _explicit_record(uid, n_filled, n_raw_nan, length=40, lo=200, hi=240):
    return {
        "variant": "wide", "sample_uid": uid, "dataset": "ETTh1",
        "stratum": "contaminated", "true_kind": "missing_block",
        "layer": "actual_nan_only", "corrupted_hash": "h" + uid,
        "n_raw_nan": n_raw_nan, "n_filled": n_filled,
        "gap_decisions": [{
            "lo": lo, "hi": hi, "length": length,
            "left_anchor": True, "right_anchor": True,
            "certified": n_filled > 0,
            "abstain_reason": None if n_filled > 0 else "overlong_gap",
        }],
    }


# -- population selection --------------------------------------------------------


def test_population_selects_only_fully_abstained_windows():
    recs = [_explicit_record(f"u{i}", 0, 40) for i in range(89)]
    recs.append(_explicit_record("filled", 40, 40))
    recs.append(_explicit_record("no_nan", 0, 0))
    pop = p1.longgap_population_uids(recs)
    assert len(pop) == 89
    assert "filled" not in pop and "no_nan" not in pop


def test_population_asserts_frozen_facts():
    recs = [_explicit_record(f"u{i}", 0, 40) for i in range(88)]
    with pytest.raises(AssertionError):
        p1.longgap_population_uids(recs)
    bad = [_explicit_record(f"u{i}", 0, 40) for i in range(89)]
    bad[0]["gap_decisions"][0]["length"] = 10
    with pytest.raises(AssertionError):
        p1.longgap_population_uids(bad)
    bad2 = [_explicit_record(f"u{i}", 0, 40) for i in range(89)]
    bad2[0]["gap_decisions"][0]["left_anchor"] = False
    with pytest.raises(AssertionError):
        p1.longgap_population_uids(bad2)


# -- the fill-insertion contract ---------------------------------------------------


def test_insert_fill_writes_only_raw_nan():
    x = _gap_window()
    pos = np.flatnonzero(~np.isfinite(x))
    fill = np.arange(len(pos), dtype=np.float64)
    y, filled = p1.insert_fill_at_raw_nan(x, fill)
    obs = np.isfinite(x)
    assert np.array_equal(y[obs], x[obs])
    assert filled.sum() == len(pos) and np.isfinite(y).all()
    assert len(y) == len(x)


def test_insert_fill_rejects_count_mismatch_and_nonfinite():
    x = _gap_window()
    pos = np.flatnonzero(~np.isfinite(x))
    with pytest.raises(AssertionError):
        p1.insert_fill_at_raw_nan(x, np.zeros(len(pos) + 1))
    bad = np.zeros(len(pos))
    bad[3] = np.nan
    with pytest.raises(AssertionError):
        p1.insert_fill_at_raw_nan(x, bad)


def test_linear_bridge_fills_overlong_gap_with_zero_drift():
    x = _gap_window()
    capped = v38p.impute_explicit_linear(x, max_gap=16)
    assert capped["n_filled"] == 0  # v3.8 behaviour: 40 > 16 abstains
    res = v38p.impute_explicit_linear(x, max_gap=2**31 - 1)
    assert res["n_filled"] == 40
    obs = np.isfinite(x)
    assert np.array_equal(res["series"][obs], x[obs])
    # exact linear interpolation between the anchors
    a, b = x[199], x[240]
    frac = np.arange(1, 41) / 41.0
    assert np.allclose(res["series"][200:240], a + (b - a) * frac)


def test_keep_is_materialized_forward_fill():
    x = _gap_window()
    meta = {"sample_uid": "u", "dataset": "d", "stratum": "contaminated",
            "true_kind": "missing_block", "layer": "actual_nan_only",
            "corrupted_hash": "h", "n_raw_nan": 40,
            "gap_decisions": []}
    rec = p1.gen_keep(x, meta)
    assert np.array_equal(np.array(rec["fill_values"]),
                          materialize_for_probe(x)[~np.isfinite(x)])
    assert not rec["applicable"] and rec["n_filled"] == 0
    assert rec["observed_support_drift"] == 0.0


# -- diagnostics -------------------------------------------------------------------


def test_seam_jump_zero_for_perfect_linear_fill():
    t = np.arange(512, dtype=np.float64)
    x = 2.0 * t
    x[200:240] = np.nan
    res = v38p.impute_explicit_linear(x, max_gap=2**31 - 1)
    s = p1.seam_jump_stats(x, res["series"], scale=1.0)
    assert s["seam_jump_max"] == pytest.approx(2.0)  # one step of the slope


def test_seam_jump_detects_discontinuity():
    x = _gap_window()
    pos = np.flatnonzero(~np.isfinite(x))
    y, _ = p1.insert_fill_at_raw_nan(x, np.full(len(pos), 1e6))
    s = p1.seam_jump_stats(x, y)
    assert s["seam_jump_max"] > 10.0


def test_uncertainty_width_normalisation():
    x = _gap_window()
    q10 = np.zeros(40)
    q90 = np.ones(40)
    u = p1.uncertainty_width(q10, q90, x)
    assert u["q10_q90_width_mean"] == pytest.approx(1.0)
    assert u["width_over_observed_mad_mean"] == pytest.approx(
        1.0 / u["observed_mad"])
    assert u["observed_mad"] > 0


# -- oracle pool discipline ----------------------------------------------------------


def _pool_row(uid, family, gain, loss=0.0, bs=True):
    return {"sample_uid": uid, "dataset": "ETTh1", "stratum": "contaminated",
            "true_kind": "missing_block", "corrupted_hash": "h",
            "family": family, "rung": "r", "params": {},
            "true_loss": loss, "true_repair_gain": gain,
            "beneficial": float(gain > 1e-9), "beneficial_and_safe": float(bs)}


def test_oracle_picks_max_gain_allowed_only():
    rows = [
        _pool_row("a", "DENOISE", 0.1),
        _pool_row("a", "BRIDGE_LONG", 0.2),
        _pool_row("a", "IMPUTE", 0.9),       # not allowed
        _pool_row("b", "BRIDGE_LONG", 0.3, loss=0.5, bs=False),  # harmful
    ]
    committed = p1.unrestricted_oracle_rows(rows, p1.ORACLE_ALLOWED)
    assert committed["a"][0]["family"] == "BRIDGE_LONG"
    assert committed["b"] is None  # harmful rows never picked -> CHR 0


def test_keep_placeholders_hold_the_frame():
    meta = {u: {"dataset": "d", "stratum": "contaminated",
                "true_kind": "missing_block", "corrupted_hash": "h"}
            for u in ("a", "b", "c")}
    ph = p1.keep_placeholders(["a", "b", "c"], {"a"}, meta)
    assert len(ph) == 2 and {r["sample_uid"] for r in ph} == {"b", "c"}
    assert all(r["family"] == "KEEP" for r in ph)


# -- five-quantity arithmetic ---------------------------------------------------------


def _labeled(uid, gain, loss, supported=True, applicable=True, ds="ETTh1"):
    return {"sample_uid": uid, "dataset": ds, "supported": supported,
            "applicable": applicable,
            "observed_support_drift": 0.0,
            "seam_jump_max": 0.0, "seam_jump_mean": 0.0,
            "labels": {"true_repair_gain": gain, "true_loss": loss,
                       "beneficial_and_safe": float(
                           gain > 1e-9 and loss <= 0.03),
                       "target_mask_nrmse_after": 0.1,
                       "target_mask_gain": 0.05}}


def test_proposer_stats_five_quantities():
    rows = [_labeled("a", 0.2, 0.0), _labeled("b", 0.0, 0.5),
            _labeled("c", 0.0, 0.0),
            _labeled("d", 0.0, 0.0, supported=False, applicable=False)]
    s = p1.proposer_stats(rows, 4)
    assert s["n_applicable"] == 3
    assert s["applicability_coverage"] == pytest.approx(0.75)
    assert s["action_conditional_bs_precision"] == pytest.approx(1 / 3)
    assert s["action_conditional_chr"] == pytest.approx(1 / 3)
    assert s["bcov_population"] == pytest.approx(0.25)
    assert s["abstention_rate"] == pytest.approx(0.25)
    assert s["n_neutral"] == 1
    assert s["mean_gain_all_windows"] == pytest.approx(0.05)


# -- freeze discipline ------------------------------------------------------------------


def test_evaluate_refuses_without_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr(p1, "OUT_FREEZE", tmp_path / "missing.json")
    with pytest.raises(SystemExit):
        p1.run_evaluate()
