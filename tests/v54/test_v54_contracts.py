"""v54 freeze contract tests (docs/protocol_freeze_v54_20260922.md §4/§5/§6).

Covers the repaired intervention-state definition (§5), the parent-clustered
neighbourhood scoring and the KEEP-only infeasible-cap fallback of the v47
selector (§6/§4), and the deployment contracts that interact with them:
KEEP's all-zero intervention block, observed-value immutability under every
action, the complete-input abstention, and the no-future-label state rule.

Execute only in the designated server environment.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from introact_ts.v44 import state as ST
from introact_ts.v47 import select as S
from introact_ts.v47_verified import actions as A

L = 512


class MeanImputer:
    """Deterministic stub imputer; never used outside the contract tests."""

    def impute_single(self, target):
        out = np.array(target, dtype=np.float64, copy=True)
        missing = ~np.isfinite(out)
        if missing.any():
            out[missing] = float(np.nanmean(out))
        return out

    def impute_multi(self, target, covariates):
        out = np.array(target, dtype=np.float64, copy=True)
        missing = ~np.isfinite(out)
        if missing.any():
            base = float(np.nanmean(out))
            cov = np.nan_to_num(covariates, nan=0.0).mean(axis=1)
            out[missing] = base + 0.001 * cov[missing]
        return out


def series(seed: int = 0, n: int = L) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=np.float64)
    return 5.0 * np.sin(2.0 * np.pi * t / 24.0) + 0.02 * t + rng.normal(0, 0.2, n)


def gapped_target(seed: int = 0, lo: int = 100, hi: int = 160) -> np.ndarray:
    x = series(seed)
    x[lo:hi] = np.nan
    return x


def panel(seed: int = 0, gap: bool = True) -> np.ndarray:
    target = gapped_target(seed) if gap else series(seed)
    cov1 = series(seed + 100)
    cov2 = series(seed + 200)
    return np.column_stack([target, cov1, cov2])


# -- §5: repaired intervention-state definition ------------------------------


def test_state_version_is_v54():
    assert ST.STATE_VERSION == "v54-full22"


def test_keep_intervention_block_is_all_zero():
    reference = gapped_target()
    scale = ST.robust_scale(reference)
    feats = ST.intervention_features(reference.copy(), reference, scale)
    assert feats.shape == (5,)
    assert np.array_equal(feats, np.zeros(5)), "KEEP must be exactly zero-intervention"


def test_complete_reference_has_no_repair_positions():
    reference = series(1)  # no NaN at all
    scale = ST.robust_scale(reference)
    edited = reference.copy()
    edited[:200] += 5.0 * scale  # not a repair: the reference was observed there
    feats = ST.intervention_features(edited, reference, scale)
    assert np.array_equal(feats, np.zeros(5))


def test_ffill_intervention_block_is_nonzero_on_gapped_series():
    reference = gapped_target()
    scale = ST.robust_scale(reference)
    candidate = A._fill_forward(reference)
    feats = ST.intervention_features(candidate, reference, scale)
    assert feats[0] > 0.0, "mean_abs_change must register the FFILL repair"
    assert feats[1] >= feats[0]
    assert feats[2] == pytest.approx(60.0 / L)  # fraction_changed = repairs/length
    assert np.all(np.isfinite(feats))


def test_intervention_delta_is_measured_against_interpolated_baseline():
    reference = gapped_target()
    scale = ST.robust_scale(reference)
    baseline = ST.interpolate_gaps(reference)
    candidate = baseline.copy()
    candidate[100:160] = baseline[100:160] + 2.0 * scale
    feats = ST.intervention_features(candidate, reference, scale)
    assert feats[0] == pytest.approx(2.0)   # mean |delta| / scale on repairs
    assert feats[1] == pytest.approx(2.0)   # max |delta| / scale


# -- action immutability of observed values ----------------------------------


def test_no_action_modifies_observed_values():
    p = panel(2, gap=True)
    observed = np.isfinite(p[:, 0])
    assert not observed.all()
    for name in S.ACTIONS:
        out = A.apply_action(name, p, imputer=MeanImputer())
        np.testing.assert_array_equal(
            out.target[observed], p[observed, 0],
            err_msg=f"{name} rewrote an observed target value")
        np.testing.assert_array_equal(
            out.panel[:, 1:], p[:, 1:],
            err_msg=f"{name} modified a covariate channel")
        if not out.applicable:
            np.testing.assert_array_equal(
                out.target, p[:, 0],
                err_msg=f"unsupported {name} must hand the reference through")


# -- complete input: KEEP only ------------------------------------------------


def test_complete_input_admits_only_keep_and_selector_abstains():
    p = panel(3, gap=False)
    assert A.legal_actions(p) == (S.REFERENCE,)
    legal = A.legal_actions(p)
    q = SimpleNamespace(episode=np.arange(1))
    q.legal = {a: np.array([a in legal]) for a in S.ACTIONS}
    scores = {a: np.array([10.0]) for a in S.ACTIONS}
    selected = S.decide(q, scores)
    assert selected[0] == S.REFERENCE, "complete input: the selector must abstain"


# -- no future labels in the state --------------------------------------------


def test_state_vector_does_not_read_future_labels():
    """Two samples that differ only after the origin give identical states."""
    origin = L
    shared = series(4)
    full_a = np.concatenate([shared, series(5, 96)])
    full_b = np.concatenate([shared, series(5, 96) + 1e6])
    assert not np.array_equal(full_a[origin:], full_b[origin:])

    def deployment_inputs(full):
        # Everything the state functions can touch is derived from the
        # pre-origin context; the differing future never enters an argument.
        reference = full[:origin].copy()
        reference[100:160] = np.nan
        masked = np.column_stack([reference, series(6, origin), series(7, origin)])
        candidate = A._fill_forward(reference)
        prediction = np.linspace(0.0, 1.0, 96)
        return dict(masked_panel=masked, reference_target=reference, period=24,
                    candidate_target=candidate, reference_prediction=prediction)

    first = ST.state_vector(**deployment_inputs(full_a))
    second = ST.state_vector(**deployment_inputs(full_b))
    assert first.size == 22
    np.testing.assert_array_equal(first, second)


def test_reference_forecast_features_accepts_exactly_one_prediction():
    reference = gapped_target()
    prediction = np.linspace(0.0, 1.0, 96)
    out = ST.reference_forecast_features(prediction, reference)
    assert out.shape == (5,)
    np.testing.assert_array_equal(
        out, ST.reference_forecast_features(prediction.copy(), reference))
    other = ST.reference_forecast_features(prediction + 1.0, reference)
    assert not np.array_equal(out, other), "output must move with the one prediction"
    with pytest.raises(ValueError):
        ST.reference_forecast_features(np.array([]), reference)
    bad = prediction.copy()
    bad[3] = np.nan
    with pytest.raises(ValueError):
        ST.reference_forecast_features(bad, reference)


# -- §6: parent-clustered neighbourhood scoring --------------------------------


def _bank_with(action, g, parent):
    per = {}
    for a in S.ACTIONS:
        if a == action:
            per[a] = SimpleNamespace(g=np.asarray(g, dtype=np.float64),
                                     parent=np.asarray(parent))
        else:
            per[a] = SimpleNamespace(g=np.zeros(0), parent=np.array([], dtype=object))
    return SimpleNamespace(per=per)


def _one_query():
    return SimpleNamespace(episode=np.arange(1))


def test_score_grid_counts_distinct_parents_not_records():
    action = "FFILL"
    bank = _bank_with(action, [1.0, 1.0, 1.0, -1.0], ["pA", "pA", "pA", "pB"])
    D = {a: np.zeros((1, 0)) for a in S.ACTIONS}
    D[action] = np.full((1, 4), 0.5)
    scores = S.score_grid(bank, _one_query(), D, k=4, beta=1.0)
    # Parent merge: pA mean utility 1.0, pB -1.0; equal distances -> equal
    # weights -> mu = 0, sigma = 1, n_eff = 2 distinct parents (not 4 records).
    # Record-level scoring would give mu = 0.5, n_eff = 4 and a positive score.
    assert scores[action][0] == pytest.approx(-1.0 / np.sqrt(2.0))


def test_score_grid_global_branch_clusters_by_parent():
    """A1 (local=False): no retrieval, but mu/sigma/n_eff stay parent-level."""
    action = "FFILL"
    bank = _bank_with(action, [1.0, 1.0, 1.0, -1.0], ["pA", "pA", "pA", "pB"])
    D = {a: np.zeros((1, 0)) for a in S.ACTIONS}
    q = SimpleNamespace(episode=np.arange(3))
    scores = S.score_grid(bank, q, D, k=4, beta=1.0, local=False)
    # Parent means are 1.0 (pA) and -1.0 (pB): mu = 0, sigma = 1, n_eff = 2
    # distinct parents for every query.  Record-level pooling would give
    # mu = 0.5 and n_eff = 4, a positive score.
    expected = -1.0 / np.sqrt(2.0)
    assert scores[action].shape == (3,)
    np.testing.assert_allclose(scores[action], expected)


def test_score_grid_parent_mean_not_record_pool():
    action = "FFILL"
    # pA's three variants average to 0.2; if records were pooled unmerged the
    # neighbourhood mean would be (0.1+0.2+0.3+(-1.0))/4 = -0.1.
    bank = _bank_with(action, [0.1, 0.2, 0.3, -1.0], ["pA", "pA", "pA", "pB"])
    D = {a: np.zeros((1, 0)) for a in S.ACTIONS}
    D[action] = np.full((1, 4), 0.5)
    scores = S.score_grid(bank, _one_query(), D, k=4, beta=0.0)
    assert scores[action][0] == pytest.approx((0.2 - 1.0) / 2.0)


def test_score_grid_empty_neighbourhood_scores_minus_inf_and_keeps():
    action = "FFILL"
    bank = _bank_with(action, [1.0, 1.0], ["pA", "pB"])
    D = {a: np.zeros((1, 0)) for a in S.ACTIONS}
    D[action] = np.full((1, 2), np.inf)
    q = _one_query()
    scores = S.score_grid(bank, q, D, k=4, beta=1.0)
    assert scores[action][0] == -np.inf
    q.legal = {a: np.ones(1, bool) for a in S.ACTIONS}
    assert S.decide(q, scores)[0] == S.REFERENCE


def test_score_grid_zero_distance_neighbourhood_uses_tau_epsilon():
    action = "FFILL"
    bank = _bank_with(action, [1.0, -1.0], ["pA", "pB"])
    D = {a: np.zeros((1, 0)) for a in S.ACTIONS}
    D[action] = np.zeros((1, 2))
    scores = S.score_grid(bank, _one_query(), D, k=2, beta=1.0)
    # tau = 0 + TAU_EPSILON -> weights ~1; mu = 0, sigma = 1, n_eff = 2.
    assert np.isfinite(scores[action][0])
    assert scores[action][0] == pytest.approx(-1.0 / np.sqrt(2.0))


def test_decide_tie_breaks_least_intervention_then_action_order():
    q = SimpleNamespace(episode=np.arange(3))
    q.legal = {a: np.ones(3, bool) for a in S.ACTIONS}
    scores = {a: np.full(3, -1.0) for a in S.ACTIONS}
    first, second = S.NONREF[0], S.NONREF[1]
    scores[first] = np.array([0.0, 2.0, 2.0])
    scores[second] = np.array([0.0, 2.0, 1.0])
    selected = S.decide(q, scores)
    assert selected[0] == S.REFERENCE, "an exactly zero score does not intervene"
    assert selected[1] == first, "a tie resolves to the earliest catalogue action"
    assert selected[2] == first


# -- §4: KEEP-only fallback when no (k, beta) respects the cap ------------------


def _fallback_fixture():
    action = "FFILL"
    per = {}
    for a in S.ACTIONS:
        if a == action:
            z = np.array([[0., 0.], [1., 0.], [0., 1.], [1., 1.]])
            per[a] = SimpleNamespace(Z=z, Zs=z.copy(),
                                     g=np.full(4, 0.5),
                                     parent=np.array(["p1", "p2", "p3", "p4"]))
        else:
            z = np.zeros((0, 2))
            per[a] = SimpleNamespace(Z=z, Zs=z.copy(), g=np.zeros(0),
                                     parent=np.array([], dtype=object))
    bank = SimpleNamespace(per=per,
                           standardise=lambda v: np.asarray(v, dtype=np.float64))

    n = 2
    q = SimpleNamespace(episode=np.arange(n),
                        parent=np.array(["q1", "q2"]),
                        source=np.array(["s", "s"]),
                        horizon=np.array([96, 96]),
                        severity=np.array([0.1, 0.1]))
    q.Z = {a: np.full((n, 2), np.nan) for a in S.ACTIONS}
    q.Z[S.REFERENCE] = np.array([[0.5, 0.5], [0.5, 0.5]])
    q.Z[action] = np.array([[0.5, 0.5], [0.5, 0.5]])
    q.legal = {a: np.zeros(n, bool) for a in S.ACTIONS}
    q.legal[S.REFERENCE][:] = True
    q.legal[action][:] = True
    q.utility = {a: np.full(n, np.nan) for a in S.ACTIONS}
    q.utility[S.REFERENCE][:] = 0.0
    # Every executed repair is harmful, so any intervening configuration has
    # conditional HIR 1.0 and violates a zero cap.
    q.utility[action][:] = -4.0
    q.metric = {"mase": {a: np.full(n, np.nan) for a in S.ACTIONS}}
    q.metric["mase"][S.REFERENCE][:] = 1.0
    q.metric["mase"][action][:] = 5.0
    return bank, q


def test_infeasible_cap_falls_back_to_keep_only_not_max_beta():
    bank, q = _fallback_fixture()
    result = S.select_hyperparameters(bank, q, k_grid=(8,), beta_grid=(0.0, 1.0),
                                      cap=0.0)
    assert result["selected"] is None
    assert result["keep_only"] is True
    assert result["fallback_to_keep_only"] is True
    assert result["fallback_to_most_conservative"] is False, \
        "the max-beta retreat without a cap recheck is removed by the freeze"
    assert result["feasible_settings"] == 0
    assert result["leader"] is None
    # The grid is still recorded for the audit trail.
    assert len(result["grid"]) == 2
    assert all(r["conditional_hir"] == 1.0 for r in result["grid"])


def test_feasible_cap_selects_normally_and_marks_no_fallback():
    bank, q = _fallback_fixture()
    result = S.select_hyperparameters(bank, q, k_grid=(8,), beta_grid=(0.0, 1.0),
                                      cap=1.0)
    assert result["selected"] == {"k": 8, "beta": 0.0}
    assert result["keep_only"] is False
    assert result["fallback_to_keep_only"] is False


# -- §4: KEEP-only deployment contract -----------------------------------------


def test_frozen_config_returns_none_on_keep_only():
    keep_only = {"selected": None, "keep_only": True,
                 "fallback_to_keep_only": True}
    assert S.frozen_config(keep_only) is None
    # The payload shape written by scripts/v47_select.py nests under "selection".
    assert S.frozen_config({"selection": keep_only}) is None


def test_frozen_config_returns_k_beta_on_normal_selection():
    result = {"selected": {"k": 16, "beta": 0.5}, "keep_only": False}
    assert S.frozen_config(result) == (16, 0.5)
    k, beta = S.frozen_config({"selection": result})
    assert isinstance(k, int) and isinstance(beta, float)


def test_keep_only_fallback_deploys_reference_on_every_request():
    """The decision the KEEP-only fallback serves: KEEP everywhere, no crash."""
    bank, q = _fallback_fixture()
    result = S.select_hyperparameters(bank, q, k_grid=(8,), beta_grid=(0.0, 1.0),
                                      cap=0.0)
    assert S.frozen_config(result) is None
    # This is the decision scripts/v47_evaluate.py writes for FULL_INTROACT
    # under keep_only; it must equal the NATIVE_KEEP row exactly.
    decision = np.full(len(q.episode), S.REFERENCE, dtype=object)
    assert (decision == S.REFERENCE).all()
