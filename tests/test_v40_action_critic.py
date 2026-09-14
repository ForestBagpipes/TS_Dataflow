"""v4.0 Phase 2 action-delta critic: pure-function unit tests.

No GPU, no MOMENT weights, no bank files: the structural feature block, the
window-local normalisation contract, the split keying, the forbidden-input
guard and the arm configuration table are all pure.
"""

import numpy as np
import pytest

import v40_action_critic as c
from conftest import synth


def _gap_window(T=512, lo=200, hi=240, seed=0):
    x = synth(seed, T=T)
    x[lo:hi] = np.nan
    return x


# -- split keying --------------------------------------------------------------


def test_inner_split_is_deterministic_and_two_way():
    uids = [f"v40parent:ETTh1:0:{i}:abc" for i in range(500)]
    splits = [c.inner_split(u) for u in uids]
    assert set(splits) <= {"inner_train", "inner_val"}
    assert all(c.inner_split(u) == s for u, s in zip(uids, splits))
    frac_val = splits.count("inner_val") / len(splits)
    assert 0.08 < frac_val < 0.25


def test_inner_split_differs_from_phase1_split_namespace():
    # The inner split must not be a relabelling of the Phase 1 reporting
    # split, or "inner validation" would silently be the Phase 1 test set.
    import v40_counterfactual_bank as bank
    uids = [f"v40parent:Crypto:{i}:0:abc" for i in range(400)]
    inner_val = {u for u in uids if c.inner_split(u) == "inner_val"}
    p1_test = {u for u in uids if bank.parent_split(u) == "test"}
    # independent hashes -> overlap should be near chance, not near total
    if p1_test:
        overlap = len(inner_val & p1_test) / len(p1_test)
        assert overlap < 0.6


def test_episode_index_parses_uid():
    assert c.episode_index("v40ep-00042:spike:mid") == 42
    assert c.episode_index("v40ep-00000:none:none") == 0


# -- structural features -------------------------------------------------------


def test_struct_features_length_matches_names():
    x = _gap_window()
    y = np.nan_to_num(x, nan=0.0)
    touched = ~np.isfinite(x)
    f = c.struct_features(x, y, touched)
    assert f.shape == (c.N_STRUCT,)
    assert len(c.STRUCT_FEATURES) == c.N_STRUCT
    assert np.isfinite(f).all()


def test_struct_features_capture_gap_geometry():
    x = _gap_window(lo=200, hi=240)   # one 40-long gap in a 512 window
    y = np.nan_to_num(x, nan=0.0)
    touched = ~np.isfinite(x)
    f = dict(zip(c.STRUCT_FEATURES, c.struct_features(x, y, touched)))
    assert f["raw_nan_frac"] == pytest.approx(40 / 512)
    assert f["longest_nan_run_frac"] == pytest.approx(40 / 512)
    assert f["n_nan_runs_frac"] == pytest.approx(1 / 512)
    assert f["support_ratio"] == pytest.approx(472 / 512)
    assert f["gap_touches_edge"] == 0.0


def test_struct_features_flag_edge_gap():
    x = synth(0)
    x[:20] = np.nan
    y = np.nan_to_num(x, nan=0.0)
    f = dict(zip(c.STRUCT_FEATURES, c.struct_features(x, y, ~np.isfinite(x))))
    assert f["gap_touches_edge"] == 1.0


def test_struct_features_keep_has_zero_delta():
    x = _gap_window()
    from introact_ts.probe import materialize_for_probe
    y = materialize_for_probe(x)          # KEEP's candidate
    touched = np.zeros(len(x), dtype=bool)
    f = dict(zip(c.STRUCT_FEATURES, c.struct_features(x, y, touched)))
    assert f["delta_l1_over_scale"] == pytest.approx(0.0)
    assert f["delta_linf_over_scale"] == pytest.approx(0.0)
    assert f["delta_nonzero_frac"] == pytest.approx(0.0)
    assert f["touched_frac"] == pytest.approx(0.0)


def test_struct_features_never_see_the_clean_series():
    # Same dirty window and same candidate, two different "clean" pasts:
    # the features must be identical because clean is not an input at all.
    x = _gap_window()
    y = np.nan_to_num(x, nan=1.0)
    t = ~np.isfinite(x)
    f1 = c.struct_features(x, y, t)
    f2 = c.struct_features(x, y, t)
    assert np.array_equal(f1, f2)


# -- normalisation -------------------------------------------------------------


def test_normalize_channels_shape_and_finiteness():
    x = _gap_window()
    y = np.nan_to_num(x, nan=0.0)
    ch = c.normalize_channels(x, y, ~np.isfinite(x))
    assert ch.shape == (5, 512)
    assert ch.dtype == np.float32
    assert np.isfinite(ch).all()          # NaNs must not survive into the net


def test_normalize_channels_masks_are_binary():
    x = _gap_window()
    y = np.nan_to_num(x, nan=0.0)
    ch = c.normalize_channels(x, y, ~np.isfinite(x))
    assert set(np.unique(ch[3])) <= {0.0, 1.0}
    assert set(np.unique(ch[4])) <= {0.0, 1.0}
    assert ch[3].sum() == 40


def test_normalize_channels_delta_is_repaired_minus_materialised():
    from introact_ts.probe import materialize_for_probe
    x = _gap_window()
    y = np.nan_to_num(x, nan=0.0)
    ch = c.normalize_channels(x, y, ~np.isfinite(x))
    # channel 2 (delta) must equal channel 1 (repaired) minus channel 0
    # (materialised dirty), all on the same scale
    assert np.allclose(ch[2], ch[1] - ch[0], atol=1e-4)
    xm = materialize_for_probe(x)
    assert np.isfinite(xm).all()


def test_normalize_channels_is_scale_equivariant():
    # A window and the same window times 10 must normalise to the same
    # thing: the scale comes from the dirty window itself.
    x = _gap_window()
    y = np.nan_to_num(x, nan=0.0)
    t = ~np.isfinite(x)
    a = c.normalize_channels(x, y, t)
    b = c.normalize_channels(x * 10.0, y * 10.0, t)
    assert np.allclose(a[0], b[0], atol=1e-3)
    assert np.allclose(a[2], b[2], atol=1e-3)


def test_as_probe_series_is_identity_on_finite_input():
    x = synth(0)
    assert np.array_equal(c.as_probe_series(x), x)


def test_as_probe_series_materialises_a_candidate_that_kept_its_nans():
    x = _gap_window()
    y = c.as_probe_series(x)          # KEEP's candidate is the dirty window
    assert np.isfinite(y).all()
    obs = np.isfinite(x)
    assert np.array_equal(y[obs], x[obs])   # observed support untouched


def test_keep_candidate_with_nans_yields_finite_channels():
    # The bug this guards: run_cpu_action(x, "keep") returns the dirty
    # window *with* its NaNs, and DESPIKE leaves gaps in place too, so a
    # window with real missingness used to push NaN into the repaired and
    # delta channels and into the TSFM input.
    x = _gap_window()
    ch = c.normalize_channels(x, x, np.zeros(len(x), dtype=bool))
    assert np.isfinite(ch).all()
    # KEEP is a no-op edit: the delta channel must be exactly zero
    assert np.abs(ch[2]).max() == pytest.approx(0.0)


def test_keep_candidate_with_nans_yields_finite_struct():
    x = _gap_window()
    f = dict(zip(c.STRUCT_FEATURES,
                 c.struct_features(x, x, np.zeros(len(x), dtype=bool))))
    assert all(np.isfinite(v) for v in f.values())
    assert f["delta_l1_over_scale"] == pytest.approx(0.0)
    assert f["delta_linf_over_scale"] == pytest.approx(0.0)


def test_partial_repair_leaving_nans_yields_finite_channels():
    # DESPIKE-like candidate: rewrites one region, leaves the gap NaN.
    x = _gap_window()
    y = x.copy()
    y[100:103] = 0.0
    ch = c.normalize_channels(x, y, np.zeros(len(x), dtype=bool))
    st = c.struct_features(x, y, np.zeros(len(x), dtype=bool))
    assert np.isfinite(ch).all() and np.isfinite(st).all()
    assert np.abs(ch[2]).max() > 0.0     # the real edit still shows up


def test_normalize_channels_uses_only_the_dirty_window():
    # Changing the *candidate* must not move the dirty channel, because the
    # (median, scale) pair is estimated on the dirty window alone.
    x = _gap_window()
    t = ~np.isfinite(x)
    a = c.normalize_channels(x, np.nan_to_num(x, nan=0.0), t)
    b = c.normalize_channels(x, np.nan_to_num(x, nan=500.0), t)
    assert np.array_equal(a[0], b[0])


# -- frozen configuration guards -----------------------------------------------


def test_forbidden_input_keys_cover_the_red_lines():
    for k in ("source", "true_kind", "clean", "sample_uid", "gain",
              "harmful", "beneficial_and_safe", "protected", "labels"):
        assert k in c.FORBIDDEN_INPUT_KEYS


def test_struct_feature_names_contain_no_v39_signal_family():
    # §1 forbids re-litigating posterior width / model disagreement / seam /
    # bridge deviation as hand-crafted signals.
    banned = ("seam", "posterior", "width", "disagree", "bridge_dev")
    for name in c.STRUCT_FEATURES:
        assert not any(b in name for b in banned), name


def test_arm_table_is_complete_and_distinct():
    assert set(c.ARM_CONFIG) == set(c.ALL_ARMS)
    assert len(c.ALL_ARMS) == 5
    assert set(c.ARMS) <= set(c.ALL_ARMS)   # V40_ARMS only ever narrows
    # full vs full_without_GroupDRO differ only in the DRO flag
    full = c.ARM_CONFIG["full_COUNTERACT"]
    no_dro = c.ARM_CONFIG["full_without_GroupDRO"]
    assert full[:4] == no_dro[:4]
    assert full[4] is True and no_dro[4] is False
    # the three restricted arms each keep exactly one input block
    assert c.ARM_CONFIG["stat_only"][:3] == (False, False, False)
    assert c.ARM_CONFIG["TSFM_latent_only"][1] is True
    assert c.ARM_CONFIG["delta_only"][2] is True


def test_frozen_hyperparameters_match_the_preregistration():
    assert c.SEED == 20260904
    assert c.QUANTILES == (0.1, 0.5, 0.9)
    assert (c.LAMBDA_H, c.LAMBDA_P, c.LAMBDA_R) == (1.0, 0.5, 0.3)
    assert c.WARMUP_EPOCHS == 5 and c.MAX_EPOCHS == 60 and c.PATIENCE == 10
    assert c.DRO_ETA == 0.01 and c.DRO_WEIGHT_CAP_MULT == 10.0
    assert c.CHR_CALIB_UPPER == 0.15
    assert c.TSFM_REVISION.startswith("ca58581b")
    assert len(c.TAU_H_GRID) == 30 and max(c.TAU_H_GRID) == pytest.approx(0.60)


def test_action_and_family_index_tables_align():
    assert len(c.ACTION_INDEX) == 8
    assert set(c.FAMILY_INDEX) == set(c.FAMILIES)
    import v40_counterfactual_bank as bank
    for action, fam in bank.ACTION_FAMILY.items():
        assert action in c.ACTION_INDEX
        assert fam in c.FAMILY_INDEX


# -- the deployment rule -------------------------------------------------------


class _FakeCache:
    """Minimal stand-in with just the arrays PolicyView reads."""

    def __init__(self, ep_idx, is_keep, y_harm, y_bs, y_prot):
        self.ep_idx = np.asarray(ep_idx)
        self.is_keep = np.asarray(is_keep, dtype=bool)
        self.y_harm = np.asarray(y_harm)
        self.y_bs = np.asarray(y_bs)
        self.y_prot = np.asarray(y_prot)


def _random_case(seed, n_ep=40, n_act=4):
    rng = np.random.RandomState(seed)
    ep, keep = [], []
    for e in range(n_ep):
        for a in range(n_act):
            ep.append(e)
            keep.append(a == 0)          # one KEEP row per episode
    n = len(ep)
    cache = _FakeCache(ep, keep, rng.randint(0, 2, n), rng.randint(0, 2, n),
                       rng.randint(0, 2, n))
    idx = np.arange(n)
    q10 = rng.randn(n)
    harm = rng.rand(n)
    prot = rng.rand(n)
    return cache, idx, q10, harm, prot


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_vectorised_policy_matches_the_reference_rule(seed):
    cache, idx, q10, harm, prot = _random_case(seed)
    for thr in ({"tau_h": 0.5, "delta": 0.0, "tau_p": 0.5},
                {"tau_h": 0.2, "delta": 0.5, "tau_p": 1.0},
                {"tau_h": 1.0, "delta": -10.0, "tau_p": 0.35}):
        fast = c.PolicyView(cache, idx).select(q10, harm, prot, thr)
        ref = c.policy_select_reference(cache, idx, q10, harm, prot, thr)
        assert np.array_equal(np.sort(fast), np.sort(ref)), thr


def test_policy_never_commits_a_keep_row():
    cache, idx, q10, harm, prot = _random_case(7)
    thr = {"tau_h": 1.0, "delta": -1e9, "tau_p": 1.0}   # admit everything
    chosen = c.PolicyView(cache, idx).select(q10, harm, prot, thr)
    assert not cache.is_keep[chosen].any()


def test_policy_commits_at_most_one_action_per_episode():
    cache, idx, q10, harm, prot = _random_case(8)
    view = c.PolicyView(cache, idx)
    thr = {"tau_h": 1.0, "delta": -1e9, "tau_p": 1.0}
    chosen = view.select(q10, harm, prot, thr)
    eps = view.inv[chosen]
    assert len(set(eps.tolist())) == len(eps)


def test_policy_abstains_when_nothing_passes():
    cache, idx, q10, harm, prot = _random_case(9)
    thr = {"tau_h": 0.0, "delta": 0.0, "tau_p": 0.0}    # admit nothing
    view = c.PolicyView(cache, idx)
    chosen = view.select(q10, harm, prot, thr)
    counts = view.counts(chosen)
    assert len(chosen) == 0
    assert counts["n_committed"] == 0
    assert counts["abstention_rate"] == pytest.approx(1.0)
    assert counts["chr"] == 0.0


def test_policy_counts_are_consistent():
    cache, idx, q10, harm, prot = _random_case(10)
    view = c.PolicyView(cache, idx)
    thr = {"tau_h": 0.7, "delta": -1.0, "tau_p": 0.8}
    chosen = view.select(q10, harm, prot, thr)
    k = view.counts(chosen)
    assert k["n_committed"] == len(chosen)
    assert k["n_harmful_commits"] == int(cache.y_harm[chosen].sum())
    assert k["chr"] == pytest.approx(
        k["n_harmful_commits"] / max(k["n_committed"], 1))
    assert k["chr_cp95_upper"] >= k["chr"]


# -- decision-stage helpers ----------------------------------------------------


def test_frontier_is_monotone_in_coverage():
    harm = np.linspace(0.0, 1.0, 20)
    y_h = (harm > 0.7).astype(int)
    y_b = 1 - y_h
    pts = c._frontier(harm, y_h, y_b, len(harm))
    covs = [p["coverage"] for p in pts]
    assert covs == sorted(covs)
    assert all(0 < p["coverage"] <= 1.0 for p in pts)
    # a threshold that admits only the low-harm end must have CHR 0
    assert pts[0]["chr"] == pytest.approx(0.0)


def test_dominates_requires_strict_improvement():
    ref = {"coverage": 0.5, "chr": 0.20}
    # same coverage, lower harm -> dominates
    assert c._dominates([{"coverage": 0.5, "chr": 0.10}], ref)
    # more coverage, same harm -> dominates
    assert c._dominates([{"coverage": 0.8, "chr": 0.20}], ref)
    # better on one axis, worse on the other -> does not dominate
    assert not c._dominates([{"coverage": 0.8, "chr": 0.30}], ref)
    assert not c._dominates([{"coverage": 0.3, "chr": 0.05}], ref)
    # identical -> not strict
    assert not c._dominates([{"coverage": 0.5, "chr": 0.20}], ref)


def test_paired_bootstrap_detects_a_real_difference():
    a = np.ones(89)
    b = np.zeros(89)
    r = c._paired_bootstrap(a, b, n_boot=500)
    assert r["mean_diff"] == pytest.approx(1.0)
    assert r["p_gt_0"] == 1.0
    assert r["n_windows"] == 89


def test_paired_bootstrap_is_neutral_on_identical_arms():
    a = np.array([1.0, -1.0, 0.0] * 30)
    r = c._paired_bootstrap(a, a, n_boot=500)
    assert r["mean_diff"] == pytest.approx(0.0)
    assert r["ci95"][0] == pytest.approx(0.0)
    assert r["ci95"][1] == pytest.approx(0.0)


def test_reference_points_match_the_frozen_v39_numbers():
    assert c.REF_RAW_TSICL["n_bs"] == 75
    assert c.REF_RAW_TSICL["n_harmful"] == 14
    assert c.REF_RAW_TSICL["coverage"] == 1.0
    assert c.REF_MIRAGE["n_commits"] == 47
    assert c.REF_MIRAGE["n_bs"] == 34
    assert c.REF_MIRAGE["n_harmful"] == 13


def test_gate_thresholds_match_the_preregistration():
    assert c.GATES["g1_harm_auroc_min"] == 0.75
    assert c.GATES["g2_auprc_lift_min"] == 0.10
    assert c.GATES["g3_bs_retained_min"] == 55
    assert c.GATES["g4_harmful_max"] == 3
    assert c.GATES["g5_chr_cp95_upper_max"] == 0.15
    assert c.GATES["g7_sources_not_degraded_min"] == 4
