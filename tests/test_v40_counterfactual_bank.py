"""v4.0 Phase 0/1 counterfactual action bank: pure-function unit tests.

No corpus, no GPU, no model weights, no server-only public-data files: the
episode plan, the corruption injectors, the semantic action gate, the
TS-ICL fill-insertion contract, the record schema/digest, the isolation
report and the budget carry-over assertions are all pure or operate on
small synthetic inputs.
"""

import numpy as np
import pytest

import v40_counterfactual_bank as b
from conftest import synth


def _gap_window(T=512, lo=200, hi=240, seed=0):
    x = synth(seed, T=T)
    x[lo:hi] = np.nan
    return x


# -- uid / split helpers ------------------------------------------------------


def test_episode_seed_deterministic_and_distinct():
    assert b.episode_seed(3) == b.episode_seed(3)
    assert b.episode_seed(3) != b.episode_seed(4)
    assert 0 <= b.episode_seed(9999) < 2**31 - 1


def test_parent_uid_deterministic_and_content_sensitive():
    s = synth(0)
    u1 = b.parent_uid("ETTh1", "0", 10, s)
    u2 = b.parent_uid("ETTh1", "0", 10, s)
    assert u1 == u2
    assert u1.startswith("v40parent:ETTh1:0:10:")
    u3 = b.parent_uid("ETTh1", "0", 10, synth(1))
    assert u3 != u1


def test_episode_uid_format():
    assert b.episode_uid(7, "spike", "mid") == "v40ep-00007:spike:mid"


def test_parent_split_partitions_and_is_deterministic():
    uids = [f"v40parent:ETTh1:0:{i}:abc" for i in range(500)]
    splits = [b.parent_split(u) for u in uids]
    assert set(splits) <= {"train", "val", "test"}
    # same uid always maps to the same split
    assert all(b.parent_split(u) == s for u, s in zip(uids, splits))
    frac_train = splits.count("train") / len(splits)
    frac_val = splits.count("val") / len(splits)
    frac_test = splits.count("test") / len(splits)
    assert 0.70 < frac_train < 0.90
    assert 0.03 < frac_val < 0.17
    assert 0.03 < frac_test < 0.17


# -- episode plan --------------------------------------------------------------


def test_episode_plan_counts_and_reproducibility():
    plan = b.episode_plan()
    assert len(plan) == b.N_TOTAL == 4200
    by_mech = {}
    for e in plan:
        by_mech.setdefault(e["corruption"], 0)
        by_mech[e["corruption"]] += 1
    for mech in b.MECHANISMS:
        assert by_mech[mech] == 3 * b.N_PER_CELL  # 3 severities x 150
    assert by_mech["mixed"] == b.N_MIXED
    assert by_mech["none"] == b.N_CLEAN

    plan2 = b.episode_plan()
    assert [e["corruption"] for e in plan] == [e["corruption"] for e in plan2]
    assert [e["seed"] for e in plan] == [e["seed"] for e in plan2]


def test_episode_plan_mixed_components_two_distinct_mechanisms():
    plan = b.episode_plan()
    mixed = [e for e in plan if e["corruption"] == "mixed"]
    assert len(mixed) == b.N_MIXED
    for e in mixed:
        comps = e["components"]
        assert len(comps) == 2
        mechs = [c[0] for c in comps]
        assert mechs[0] != mechs[1]
        assert all(m in b.MECHANISMS for m in mechs)
        assert all(s in b.SEVERITIES for _m, s in comps)


def test_episode_plan_severity_ranges_cover_5_to_50_pct_for_missing_block():
    lo_all = min(v[0] for v in b.SEVERITY_RANGES["missing_block"].values())
    hi_all = max(v[1] for v in b.SEVERITY_RANGES["missing_block"].values())
    assert lo_all <= 0.06
    assert hi_all >= 0.49


# -- nan runs / semantic action gate ------------------------------------------


def test_nan_run_lengths():
    x = synth(0)
    x[10:13] = np.nan
    x[100:108] = np.nan
    runs = sorted(b.nan_run_lengths(x))
    assert runs == [3, 8]


def test_action_gate_keep_always_true():
    x = synth(0)
    ok, _ = b.action_gate(x, "keep")
    assert ok is True


def test_action_gate_fact_short_only_for_1_to_3_runs():
    x = synth(0)
    x[10:12] = np.nan  # run length 2
    ok, reason = b.action_gate(x, "fact_short")
    assert ok and "1-3" in reason
    x2 = synth(0)
    x2[10:15] = np.nan  # run length 5
    ok2, _ = b.action_gate(x2, "fact_short")
    assert ok2 is False


def test_action_gate_tsicl_long_only_for_ge4_runs():
    x = synth(0)
    x[10:13] = np.nan  # length 3, too short
    ok, _ = b.action_gate(x, "tsicl_long")
    assert ok is False
    x2 = synth(0)
    x2[10:14] = np.nan  # length 4
    ok2, _ = b.action_gate(x2, "tsicl_long")
    assert ok2 is True


def test_action_gate_impute_requires_missing():
    x = synth(0)
    ok, _ = b.action_gate(x, "impute_linear_default")
    assert ok is False  # fully finite, nothing frozen/missing
    x2 = synth(0)
    x2[50:55] = np.nan
    ok2, _ = b.action_gate(x2, "impute_linear_default")
    assert ok2 is True


def test_action_gate_denoise_requires_fully_finite():
    x = synth(0)
    ok, _ = b.action_gate(x, "denoise")
    assert ok is True
    x2 = synth(0)
    x2[5] = np.nan
    ok2, _ = b.action_gate(x2, "denoise")
    assert ok2 is False


def test_action_gate_unknown_action_raises():
    with pytest.raises(ValueError):
        b.action_gate(synth(0), "not_a_real_action")


# -- corruption injectors ------------------------------------------------------


@pytest.mark.parametrize("mech", b.MECHANISMS)
def test_inject_bank_reproducible_given_same_rng_state(mech):
    x = synth(0)
    y1, m1 = b.inject_bank(x, mech, "mid", np.random.RandomState(123))
    y2, m2 = b.inject_bank(x, mech, "mid", np.random.RandomState(123))
    assert np.array_equal(y1, y2, equal_nan=True)
    assert np.array_equal(m1, m2)


@pytest.mark.parametrize("mech", b.MECHANISMS)
def test_inject_bank_does_not_mutate_input(mech):
    x = synth(0)
    x_before = x.copy()
    b.inject_bank(x, mech, "mid", np.random.RandomState(0))
    assert np.array_equal(x, x_before, equal_nan=True)


def test_inject_bank_missing_block_severity_monotonic_in_length():
    x = synth(0)
    lens = {}
    for sev in b.SEVERITIES:
        _y, m = b.inject_bank(x, "missing_block", sev, np.random.RandomState(1))
        lens[sev] = int(m.sum())
    assert lens["low"] < lens["mid"] < lens["high"]
    assert lens["high"] <= len(x) // 2 + 1


def test_inject_bank_missing_block_writes_only_nan_inside_run():
    x = synth(0)
    y, m = b.inject_bank(x, "missing_block", "high", np.random.RandomState(2))
    assert np.all(np.isnan(y[m]))
    assert np.array_equal(y[~m], x[~m])


def test_inject_bank_spike_touches_only_masked_points():
    x = synth(0)
    y, m = b.inject_bank(x, "spike", "high", np.random.RandomState(3))
    assert np.array_equal(y[~m], x[~m])
    assert m.sum() > 0
    assert np.isfinite(y).all()


def test_inject_bank_noise_marks_whole_window_and_changes_it():
    x = synth(0)
    y, m = b.inject_bank(x, "noise", "mid", np.random.RandomState(4))
    assert m.all()
    assert not np.array_equal(x, y)


def test_inject_bank_level_shift_only_after_breakpoint():
    x = synth(0)
    y, m = b.inject_bank(x, "level_shift", "high", np.random.RandomState(5))
    lo = int(np.argmax(m))
    assert np.array_equal(y[:lo], x[:lo])
    assert m[lo:].all() and not m[:lo].any()


def test_inject_bank_duplicate_copies_a_finite_earlier_span():
    x = synth(0)
    y, m = b.inject_bank(x, "duplicate", "mid", np.random.RandomState(6))
    assert m.sum() > 0
    assert np.array_equal(y[~m], x[~m])


def test_inject_bank_unknown_mechanism_raises():
    # SEVERITY_RANGES[mechanism] is looked up before the mechanism dispatch,
    # so an unrecognised mechanism fails on the dict lookup (KeyError) rather
    # than reaching the explicit `raise ValueError` at the bottom of the
    # if/elif chain -- unreachable in the real pipeline since mechanisms are
    # always drawn from MECHANISMS by construction (episode_plan()).
    with pytest.raises(KeyError):
        b.inject_bank(synth(0), "not_a_mechanism", "mid", np.random.RandomState(0))


def test_apply_episode_corruption_none_is_clean_control():
    x = synth(0)
    dirty, mask = b.apply_episode_corruption(
        x, {"corruption": "none", "severity": "none", "components": None,
            "seed": 42})
    assert np.array_equal(dirty, x)
    assert not mask.any()


def test_apply_episode_corruption_mixed_unions_component_masks():
    x = synth(0)
    entry = {"corruption": "mixed", "severity": "mixed",
             "components": [["spike", "high"], ["noise", "mid"]], "seed": 7}
    dirty, mask = b.apply_episode_corruption(x, entry)
    # noise marks the whole window, so the union must be everywhere touched
    assert mask.all()
    assert not np.array_equal(dirty, x)


def test_apply_episode_corruption_reproducible_by_seed():
    x = synth(0)
    entry = {"corruption": "spike", "severity": "mid", "components": None,
             "seed": 99}
    d1, m1 = b.apply_episode_corruption(x, entry)
    d2, m2 = b.apply_episode_corruption(x, entry)
    assert np.array_equal(d1, d2, equal_nan=True)
    assert np.array_equal(m1, m2)


# -- CPU actions ----------------------------------------------------------------


def test_run_cpu_action_keep_is_identity_untouched():
    x = _gap_window()
    y, touched, applicable, params = b.run_cpu_action(x, "keep")
    assert np.array_equal(y, x, equal_nan=True)
    assert not touched.any()
    assert applicable is True
    assert params == {}


def test_run_cpu_action_fact_short_only_short_gaps():
    x = synth(0)
    x[10:12] = np.nan  # length 2, inside FACT_SHORT_MAX_GAP
    y, touched, applicable, params = b.run_cpu_action(x, "fact_short")
    assert applicable is True
    assert np.isfinite(y[10:12]).all()
    assert touched[10:12].all()
    obs = np.isfinite(x)
    assert np.array_equal(y[obs], x[obs])


def test_run_cpu_action_impute_linear_default_fills_gap():
    x = synth(0)
    x[100:120] = np.nan
    y, touched, applicable, params = b.run_cpu_action(x, "impute_linear_default")
    assert applicable is True
    assert np.isfinite(y).all()
    assert touched[100:120].all()


def test_run_cpu_action_unknown_action_raises():
    with pytest.raises(ValueError):
        b.run_cpu_action(synth(0), "not_a_real_action")


def test_rebuild_tsicl_output_drift_zero_and_only_raw_nan_written():
    x = _gap_window()
    pos = np.flatnonzero(~np.isfinite(x))
    fill = np.arange(len(pos), dtype=np.float64)
    y, touched = b.rebuild_tsicl_output(x, fill)
    obs = np.isfinite(x)
    assert np.array_equal(y[obs], x[obs])  # zero observed-support drift
    assert touched.sum() == len(pos)
    assert np.array_equal(y[~obs], fill)


def test_rebuild_tsicl_output_rejects_fill_count_mismatch():
    x = _gap_window()
    pos = np.flatnonzero(~np.isfinite(x))
    with pytest.raises(AssertionError):
        b.rebuild_tsicl_output(x, np.zeros(len(pos) + 1))


# -- record schema / digest ------------------------------------------------------


def _min_evaluated_record(**overrides):
    """A record shaped like stage_evaluate's output: every REQUIRED_RECORD_FIELDS
    key present -- this is the only shape validate_record is ever actually
    called with in the pipeline (always labeled=True, see stage_evaluate)."""
    rec = {
        "episode_uid": "v40ep-00000:spike:mid", "clean_parent_uid": "p",
        "source": "ETTh1", "corruption": "spike", "severity": "mid",
        "family": "DESPIKE", "action": "despike", "candidate_hash": "h",
        "input_hash": "i", "mask_hash": "m", "before_nmse": 0.5,
        "after_nmse": 0.3, "gain": 0.2, "true_loss": 0.0,
        "harmful": False, "beneficial_and_safe": True, "protected": False,
        "provenance": {}, "applicable": True, "labels": {"true_loss": 0.0},
    }
    rec.update(overrides)
    return rec


def test_validate_record_flags_missing_required_field():
    rec = _min_evaluated_record()
    del rec["gain"]
    problems = b.validate_record(rec, labeled=True)
    assert any("missing field gain" in p for p in problems)


def test_validate_record_labeled_applicable_requires_labels():
    rec = _min_evaluated_record(applicable=True, labels=None)
    problems = b.validate_record(rec, labeled=True)
    assert any("applicable record without joined labels" in p for p in problems)


def test_validate_record_labeled_full_record_passes():
    rec = _min_evaluated_record()
    assert b.validate_record(rec, labeled=True) == []


def test_validate_record_not_applicable_record_needs_no_labels():
    rec = _min_evaluated_record(applicable=False, labels=None)
    assert b.validate_record(rec, labeled=True) == []


def test_candidate_forbidden_keys_cover_leakage_and_eval_fields():
    # Static contract check on the module constant (§2 red line): the keys
    # that must never leak into a pre-freeze candidate record.
    assert {"true_kind", "clean", "clean_series", "clean_hash",
            "sample_uid"} <= b.CANDIDATE_FORBIDDEN_KEYS
    assert b.EVAL_NAMESPACE <= b.CANDIDATE_FORBIDDEN_KEYS


def test_raw_candidate_record_shape_has_no_forbidden_keys():
    # _candidate_record() is what the "candidates" stage actually writes,
    # before compute_action_labels ever runs (§2 freeze-before-labels rule).
    entry = {"idx": 0, "corruption": "spike", "severity": "mid",
             "components": None, "seed": 1}
    meta = {"clean_parent_uid": "p1", "source": "ETTh1", "channel": "0",
             "start": 0, "split": "train"}
    rec = b._candidate_record(entry, meta, "despike")
    assert not (b.CANDIDATE_FORBIDDEN_KEYS & set(rec))


def _digest_row(episode_uid, action, candidate_hash="h"):
    return {"episode_uid": episode_uid, "action": action, "supported": True,
            "applicable": True, "candidate_hash": candidate_hash,
            "input_hash": "i", "mask_hash": "m"}


def test_digest_records_order_independent_and_deterministic():
    r1 = _digest_row("e1", "a")
    r2 = _digest_row("e2", "a")
    d1 = b.digest_records([r1, r2])
    d2 = b.digest_records([r2, r1])
    assert d1 == d2
    r2_changed = _digest_row("e2", "a", candidate_hash="different")
    d3 = b.digest_records([r1, r2_changed])
    assert d3 != d1


# -- isolation report -----------------------------------------------------------


def test_isolation_report_passes_on_disjoint_input():
    metas = [{"clean_parent_uid": "p1", "series_sha256": "s1", "split": "train"},
             {"clean_parent_uid": "p2", "series_sha256": "s2", "split": "val"},
             {"clean_parent_uid": "p3", "series_sha256": "s3", "split": "test"}]
    manifest = {"records": [{"sample_uid": "u_other", "clean_hash": "z1",
                              "corrupted_hash": "z2"}]}
    rep = b.isolation_report(metas, manifest, eval_uids=["u_eval"])
    assert rep["pass"] is True
    assert rep["parent_uid_unique"] is True
    assert rep["n_parent_series_hash_in_manifest"] == 0


def test_isolation_report_fails_on_manifest_hash_collision():
    metas = [{"clean_parent_uid": "p1", "series_sha256": "z1", "split": "train"}]
    manifest = {"records": [{"sample_uid": "u_other", "clean_hash": "z1",
                              "corrupted_hash": "z2"}]}
    rep = b.isolation_report(metas, manifest, eval_uids=[])
    assert rep["pass"] is False
    assert rep["n_parent_series_hash_in_manifest"] == 1


def test_isolation_report_fails_on_duplicate_parent_uid():
    metas = [{"clean_parent_uid": "p1", "series_sha256": "s1", "split": "train"},
             {"clean_parent_uid": "p1", "series_sha256": "s2", "split": "val"}]
    manifest = {"records": []}
    rep = b.isolation_report(metas, manifest, eval_uids=[])
    assert rep["pass"] is False
    assert rep["parent_uid_unique"] is False


def test_isolation_report_fails_on_eval_frame_intersection():
    metas = [{"clean_parent_uid": "u_eval", "series_sha256": "s1",
              "split": "train"}]
    manifest = {"records": []}
    rep = b.isolation_report(metas, manifest, eval_uids=["u_eval"])
    assert rep["pass"] is False
    assert rep["intersect_eval_771_uids"] == ["u_eval"]


def test_isolation_report_fails_on_split_crossing():
    # same clean_parent_uid recorded under two different splits
    metas = [{"clean_parent_uid": "p1", "series_sha256": "s1", "split": "train"},
             {"clean_parent_uid": "p1", "series_sha256": "s1", "split": "val"}]
    manifest = {"records": []}
    rep = b.isolation_report(metas, manifest, eval_uids=[])
    assert rep["pass"] is False
    assert rep["split_disjoint_violations"]["train_val"] == ["p1"]


# -- budget carry-over -----------------------------------------------------------


def _v39_budget_stub(**overrides):
    stub = {
        "baseline_arm": "D_fact_short_first",
        "new_beneficial_commits_needed_for_bcov": 15,
        "gain_deficit_sum": 5.6318868545896805,
        "max_new_harmful_commits_at_required_beneficial": -1,
        "pme_headroom_edits": -1,
        "baseline": {"prot_edit": 2, "harmful": 15, "improved": 10,
                     "gain_sum": 1.0, "committed": 20},
        "n_contaminated": 100, "n_frame": 771, "n_protected": 50,
        "targets": {"chr": 0.10},
    }
    stub.update(overrides)
    return stub


def test_carry_over_budget_matches_frozen_v39_numbers(tmp_path, monkeypatch):
    v39 = _v39_budget_stub()
    fake = tmp_path / "v39_target_budget.json"
    fake.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(b, "V39_BUDGET", fake)
    out = b.carry_over_budget(v39)
    assert out["v40_targets"]["new_beneficial_and_safe_windows_min"] == 15
    assert out["v40_targets"]["gain_sum_increase_min"] == pytest.approx(
        5.6318868545896805)
    assert out["v40_targets"]["harmful_commits_must_decrease_below"] == 15


def test_carry_over_budget_raises_on_drifted_v39_numbers():
    v39 = _v39_budget_stub(new_beneficial_commits_needed_for_bcov=99)
    with pytest.raises(AssertionError):
        b.carry_over_budget(v39)

    v39b = _v39_budget_stub(gain_deficit_sum=1.0)
    with pytest.raises(AssertionError):
        b.carry_over_budget(v39b)
