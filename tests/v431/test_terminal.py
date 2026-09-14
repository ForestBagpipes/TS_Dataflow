import json

import numpy as np
import pytest

from introact_ts.v431.decision_tree import LossTree, split_thresholds
from introact_ts.v431.terminal import RefinedPolicy, grouped_gain_interval


def sample(n=40, prefix="fit"):
    x = np.arange(n, dtype=float)[:, None]
    losses = np.full((n, 5), 5.0)
    losses[:, 2] = 1.0
    return x, losses, np.ones(n) / n, np.asarray([f"{prefix}-{i}" for i in range(n)])


def refinement_case(gate_benefit=True, gate_n=16, prune=True):
    x, loss, w, p = sample()
    # A2 is globally strongest. Evidence gives A3 a gain for just half the rows.
    loss[:20, 3] = 0.0
    base = LossTree(max_depth=0).fit(x, loss, w, p)
    gx, gl, gw, gp = sample(gate_n, "gate")
    ge = np.arange(gate_n, dtype=float)[:, None] * 40 / gate_n
    gl[ge[:, 0] <= 19.5, 3] = 0.0 if gate_benefit else 2.0
    policy = RefinedPolicy(base, prune=prune).fit(
        x, x, loss, w, p, gx, ge, gl, gw, gp)
    return policy, gx, ge


def test_task_loss_tree_uses_magnitude_instead_of_oracle_classification():
    x, loss, w, p = sample()
    loss[:] = 100.0
    loss[:, 2] = 1.0
    loss[:39, 0] = 0.9
    loss[39, 0] = 100.0
    tree = LossTree(max_depth=0).fit(x, loss, w, p)
    # 39/40 classification labels favor A0, but its total task loss is worse.
    assert np.all(tree.predict(x) == 2)


def test_ties_prefer_tsicl_and_weighted_losses_control_actions():
    x, loss, w, p = sample()
    loss[:] = 1.0
    assert np.all(LossTree(max_depth=0).fit(x, loss, w, p).predict(x) == 2)
    loss[:, 0] = 0.8
    loss[0, 0] = 10
    w[0] = 10
    assert np.all(LossTree(max_depth=0).fit(x, loss, w, p).predict(x) == 2)


def test_variants_do_not_create_parent_support_and_split_weight_is_invariant():
    x, loss, w, p = sample(32)
    loss[:16, 0] = 0.0
    tree = LossTree(max_depth=1).fit(x, loss, w, p)
    assert len(set(tree.predict(x))) == 2
    xx = np.repeat(x, 6, axis=0)
    ll = np.repeat(loss, 6, axis=0)
    ww = np.repeat(w / 6, 6)
    pp = np.repeat(p, 6)
    repeated = LossTree(max_depth=1).fit(xx, ll, ww, pp)
    np.testing.assert_array_equal(tree.predict(x), repeated.predict(x))
    # Deliberately 8 independent parents repeated five times cannot train a leaf.
    with pytest.raises(ValueError, match="independent parents"):
        LossTree().fit(x[:8].repeat(5, axis=0), loss[:8].repeat(5, axis=0),
                       np.ones(40), p[:8].repeat(5))


def test_missing_route_roundtrip_and_frozen_identity():
    x, loss, w, p = sample(48)
    x[:16, 0] = np.nan
    loss[:32, 0] = 0
    tree = LossTree(max_depth=1).fit(x, loss, w, p)
    assert "missing_left" in tree.root_
    state = json.loads(json.dumps(tree.to_dict(), allow_nan=False))
    restored = LossTree.from_dict(state)
    assert tree.frozen_hash == restored.frozen_hash
    np.testing.assert_array_equal(tree.predict(x), restored.predict(x))
    state["training_parent_ids"][0] = "changed"
    with pytest.raises(ValueError, match="identity hash"):
        LossTree.from_dict(state)


def test_refinement_gate_accepts_benefit_and_hidden_evidence_keeps_parent():
    policy, gx, ge = refinement_case()
    assert policy.audit_[0]["accepted"]
    assert policy.audit_[0]["gate"]["lower_90"] > 0
    assert np.any(policy.predict(gx, ge) == 3)
    assert np.all(policy.predict(gx, np.full_like(ge, np.nan)) == 2)
    restored = RefinedPolicy.from_dict(json.loads(json.dumps(policy.to_dict())))
    assert restored.frozen_hash == policy.frozen_hash
    np.testing.assert_array_equal(restored.predict(gx, ge), policy.predict(gx, ge))


def test_refinement_rejects_harm_or_low_support_but_unpruned_keeps_proposal():
    policy, gx, ge = refinement_case(gate_benefit=False)
    assert not policy.audit_[0]["accepted"]
    assert policy.audit_[0]["reason"] == "gate_not_positive"
    assert np.all(policy.predict(gx, ge) == 2)
    ablation, _, _ = refinement_case(gate_benefit=False, prune=False)
    assert ablation.audit_[0]["accepted"]
    assert np.any(ablation.predict(gx, ge) == 3)
    sparse, _, _ = refinement_case(gate_n=7)
    assert sparse.audit_[0]["reason"] == "insufficient_gate_parent_support"
    assert not sparse.audit_[0]["accepted"]


def test_refinement_rejects_parent_overlap_and_never_reads_hidden_feature_columns():
    x, loss, w, p = sample()
    base = LossTree(max_depth=0).fit(x, loss, w, p)
    with pytest.raises(ValueError, match="overlap"):
        RefinedPolicy(base).fit(x, x, loss, w, p, x, x, loss, w, p)
    policy, gx, ge = refinement_case()
    hidden = np.full_like(ge, np.nan)
    before = policy.frozen_hash
    np.testing.assert_array_equal(policy.predict(gx, hidden), policy.base_tree.predict(gx))
    assert policy.frozen_hash == before


def test_parent_bootstrap_preserves_variants_and_source_macro_weight():
    parents = np.array(["p0", "p1", "p2", "p3"])
    groups = np.array(["a", "a", "b", "b"])
    gains = np.array([1.0, 1.0, -0.5, -0.5])
    weights = np.ones(4) / 4
    result = grouped_gain_interval(gains, weights, parents, groups=groups)
    assert result["mean_gain"] == 0.25
    assert result["lower_90"] == result["upper_90"] == 0.25
    repeated = grouped_gain_interval(np.repeat(gains, 6), np.repeat(weights / 6, 6),
                                    np.repeat(parents, 6), groups=np.repeat(groups, 6))
    assert repeated["parent_count"] == 4
    assert repeated["mean_gain"] == pytest.approx(result["mean_gain"])
    assert repeated["lower_90"] == pytest.approx(result["lower_90"])


def test_threshold_search_is_bounded_and_failed_losses_are_rejected():
    assert len(split_thresholds(np.arange(1000))) <= 16
    x, loss, w, p = sample()
    loss[0, 0] = np.nan
    with pytest.raises(ValueError, match="failed/missing"):
        LossTree().fit(x, loss, w, p)
