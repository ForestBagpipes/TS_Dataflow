"""Tests for the v3.5 ACV shared core (experiments/v35_acv_common.py).

Pre-registered invariants of the frozen §2 data flow: anchor determinism,
anchor/support disjointness, anchor targets drawn only from original finite
observations, support-run decomposition edge cases, and horizon skip. All
synthetic; no corpus, no labels, no TSFM.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v35_acv_common as acv  # noqa: E402
from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.types import Action  # noqa: E402


def _series(T=256, seed=3):
    rng = np.random.RandomState(seed)
    t = np.arange(T, dtype=np.float64)
    return np.cumsum(rng.randn(T)) + 2.0 * np.sin(2 * np.pi * t / 24.0)


# -- support runs decomposition -----------------------------------------------


def test_support_runs_edge_cases():
    assert acv.support_runs(np.zeros(10, dtype=bool)) == []
    m = np.zeros(10, dtype=bool)
    m[0:3] = True  # support at the very start
    assert acv.support_runs(m) == [(0, 3)]
    m = np.zeros(10, dtype=bool)
    m[7:10] = True  # support at the very end
    assert acv.support_runs(m) == [(7, 10)]
    m = np.ones(10, dtype=bool)  # whole window
    assert acv.support_runs(m) == [(0, 10)]
    m = np.zeros(10, dtype=bool)
    m[[0, 2, 4, 9]] = True  # scattered singletons
    assert acv.support_runs(m) == [(0, 1), (2, 3), (4, 5), (9, 10)]


# -- anchor determinism ----------------------------------------------------------


def test_anchor_determinism_bit_identical():
    x = _series()
    x[100:120] = np.nan  # missing block -> IMPUTE support
    out = apply_action(x, Action.IMPUTE, method="linear", min_run=8)
    sup = acv.changed_support_mask(x, "IMPUTE", out)
    a1 = acv.select_anchors("uid:A", x, sup)
    a2 = acv.select_anchors("uid:A", x, sup)
    assert a1 == a2
    # A different uid may reorder the >3-run cap selection, never the value
    # set for a single run; here a single run must give identical anchors.
    a3 = acv.select_anchors("uid:B", x, sup)
    assert a1 == a3


def test_anchor_cap_deterministic_under_many_runs():
    x = _series()
    sup = np.zeros(len(x), dtype=bool)
    # Six separate single-point supports, each followed by >= 32 finite
    # points, so every run yields an anchor and the MAX_ANCHORS cap binds.
    for lo in range(0, 192, 32):
        sup[lo:lo + 1] = True
    a1 = acv.select_anchors("uid:cap", x, sup)
    a2 = acv.select_anchors("uid:cap", x, sup)
    assert len(a1) == acv.MAX_ANCHORS
    assert a1 == a2  # same uid -> same surviving anchors, bit for bit


# -- anchor / support invariants --------------------------------------------------


def test_anchor_support_disjoint_and_targets_finite():
    x = _series()
    x[40:60] = np.nan
    x[150:170] = np.nan
    out = apply_action(x, Action.IMPUTE, method="linear", min_run=8)
    sup = acv.changed_support_mask(x, "IMPUTE", out)
    anchors = acv.select_anchors("uid:inv", x, sup)
    assert anchors
    for a in anchors:
        assert not sup[a["start"]:a["end"]].any()
        assert np.isfinite(x[a["start"]:a["end"]]).all()
        assert a["start"] >= a["run_hi"]  # post-action
        assert a["end"] - a["start"] == a["horizon"]
        assert a["horizon"] in acv.HORIZONS


def test_anchor_never_uses_materialised_nan():
    # NaN block immediately after the support run: the anchor must skip it.
    x = _series()
    sup = np.zeros(len(x), dtype=bool)
    sup[50:60] = True
    x[60:80] = np.nan  # not support, but not finite either
    anchors = acv.select_anchors("uid:nan", x, sup)
    assert anchors
    for a in anchors:
        assert a["start"] >= 80
        assert np.isfinite(x[a["start"]:a["end"]]).all()


# -- horizon skip -----------------------------------------------------------------


def test_insufficient_horizon_skipped():
    x = _series()
    sup = np.zeros(len(x), dtype=bool)
    sup[-4:] = True  # support reaches window end: no post-action room
    assert acv.select_anchors("uid:end", x, sup) == []
    rec_reason = acv.anchor_failure_reason(x, sup, [])
    assert rec_reason == "support_reaches_window_end"


def test_multi_horizon_emits_one_anchor_per_feasible_horizon():
    # Adopted §2.3 reading: horizons 8, 16, 32 are tried in order and every
    # feasible one yields an anchor, all starting at the same block.
    x = _series()
    for tail, expected_Hs in ((8, [8]), (20, [8, 16]), (40, [8, 16, 32])):
        sup = np.zeros(len(x), dtype=bool)
        sup[len(x) - tail - 10:len(x) - tail] = True
        anchors = acv.select_anchors("uid:h", x, sup)
        assert [a["horizon"] for a in anchors] == expected_Hs
        assert len({a["start"] for a in anchors}) == 1  # overlapping starts
        for a in anchors:
            assert a["end"] - a["start"] == a["horizon"]


def test_legacy_per_run_rule_preserved():
    # The stricter Phase-0 reading stays available as a parameter: exactly
    # one anchor per run, at the largest feasible horizon.
    x = _series()
    for tail, expected_H in ((8, 8), (20, 16), (40, 32)):
        sup = np.zeros(len(x), dtype=bool)
        sup[len(x) - tail - 10:len(x) - tail] = True
        anchors = acv.select_anchors("uid:h", x, sup, multi_horizon=False)
        assert len(anchors) == 1
        assert anchors[0]["horizon"] == expected_H
    # Legacy anchors are a subset of the multi-horizon ones for the same run.
    sup = np.zeros(len(x), dtype=bool)
    sup[100:110] = True
    multi = acv.select_anchors("uid:sub", x, sup)
    legacy = acv.select_anchors("uid:sub", x, sup, multi_horizon=False)
    assert len(multi) == 3 and len(legacy) == 1
    assert legacy[0] in multi


def test_multi_horizon_cap_binds_within_single_run():
    # One run with a long tail emits exactly MAX_ANCHORS anchors (8/16/32);
    # the cap rule is deterministic across calls.
    x = _series()
    sup = np.zeros(len(x), dtype=bool)
    sup[100:110] = True
    a1 = acv.select_anchors("uid:cap1", x, sup)
    a2 = acv.select_anchors("uid:cap1", x, sup)
    assert len(a1) == acv.MAX_ANCHORS
    assert a1 == a2
    # Anchors are returned sorted by (start, horizon).
    assert a1 == sorted(a1, key=lambda a: (a["start"], a["horizon"]))


def test_fragmented_tail_reason():
    x = _series()
    sup = np.zeros(len(x), dtype=bool)
    sup[100:110] = True
    # Only 4 finite points after the run, then NaN to the end.
    x[114:] = np.nan
    anchors = acv.select_anchors("uid:frag", x, sup)
    assert anchors == []
    assert acv.anchor_failure_reason(x, sup, []) == "fragmented_tail"


# -- changed support semantics -----------------------------------------------------


def test_changed_support_impute_matches_filled_points():
    x = _series()
    x[100:120] = np.nan
    out = apply_action(x, Action.IMPUTE, method="linear", min_run=8)
    sup = acv.changed_support_mask(x, "IMPUTE", out)
    assert sup.sum() == 20
    lo, hi = acv.support_runs(sup)[0]
    assert (lo, hi) == (100, 120)
    # Value-consistency with the hash definition: changed points are exactly
    # where the rounded bytes differ or NaN status flips.
    assert (sup == acv.value_changed(x, out.series)).all()


def test_changed_support_keep_empty_and_unsupported():
    x = _series()
    rec = acv.audit_candidate("uid:keep", x, "KEEP", {})
    assert rec["support_n"] == 0
    assert rec["anchors"] == []
    assert rec["prequential_supported"] == 0
    assert rec["support_conformity_supported"] == 0
    assert rec["role"] == acv.KEEP_ROLE


def test_audit_candidate_impute_end_to_end():
    x = _series()
    x[100:120] = np.nan
    rec = acv.audit_candidate("uid:e2e", x, "IMPUTE",
                              {"method": "linear", "min_run": 8})
    from v33_labels import hash_array
    out = apply_action(x, Action.IMPUTE, method="linear", min_run=8)
    assert rec["output_hash"] == hash_array(out.series)
    assert rec["prequential_supported"] == 1
    assert rec["support_conformity_supported"] == 1
    assert rec["anchor_failure_reason"] is None
    # Determinism of the full record.
    rec2 = acv.audit_candidate("uid:e2e", x, "IMPUTE",
                               {"method": "linear", "min_run": 8})
    assert rec == rec2


def test_run_anchor_capacities_reports_feasible_horizons():
    x = _series()
    sup = np.zeros(len(x), dtype=bool)
    sup[100:110] = True  # long finite tail -> all horizons fit
    caps = acv.run_anchor_capacities(x, sup)
    assert caps == [{"run_lo": 100, "run_hi": 110, "block_start": 110,
                     "block_len": len(x) - 110,
                     "feasible_horizons": [8, 16, 32]}]
    sup2 = np.zeros(len(x), dtype=bool)
    sup2[len(x) - 20:len(x) - 10] = True  # 10-point tail -> only H=8
    caps2 = acv.run_anchor_capacities(x, sup2)
    assert caps2[0]["feasible_horizons"] == [8]
    sup3 = np.zeros(len(x), dtype=bool)
    sup3[-4:] = True
    assert acv.run_anchor_capacities(x, sup3)[0]["feasible_horizons"] == []


def test_resegment_prefix_discard_anchor_inside_retained_span():
    # A level shift at t=64: RESEGMENT discards [0, 64) and keeps the tail.
    x = _series(T=192)
    x[:64] += 50.0
    out = apply_action(x, Action.RESEGMENT, penalty=8.0, min_size=24,
                       min_keep_frac=0.4)
    if not out.applicable:
        return  # synthetic did not trigger the cut; nothing to assert
    rec = acv.audit_candidate("uid:reseg", x, "RESEGMENT",
                              {"penalty": 8.0, "min_size": 24,
                               "min_keep_frac": 0.4})
    lo, hi = rec["retain_span"]
    for a in rec["anchors"]:
        assert lo <= a["start"] and a["end"] <= hi
        assert not acv.changed_support_mask(
            x, "RESEGMENT", out)[a["start"]:a["end"]].any()
