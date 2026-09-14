import numpy as np
import pytest

from introact_ts.v431_r2.policy import EvidenceState, StatePolicy, freeze_reference

NAMES = ('missing_fraction', 'horizon_ratio')


def data(parents=40, repeats=6):
    n = parents * repeats
    X = np.tile([.1, .5], (n, 1))
    ids = np.repeat([f'p{i}' for i in range(parents)], repeats)
    signal = np.repeat(np.arange(parents) >= parents // 2, repeats).astype(float)
    E = np.tile([0., 0., 1.], (n, 5))
    E[:, 0] = signal
    L = np.ones((n, 5)) * 3
    L[:, 2] = 1.
    L[:, 3] = np.where(signal == 0, 0., 2.)
    return X, {'mask': E.copy(), 'history': E.copy()}, L, np.ones(n) / n, ids


def fitted():
    X, E, L, w, p = data()
    return StatePolicy(2, sorted(set(p)), NAMES).fit(X, E, L, w, p), (X, E, L, w, p)


def test_no_evidence_uses_fixed_reference_without_touching_other_models():
    policy, (X, E, *_rest) = fitted()
    state = EvidenceState()
    before = policy.choose(X[0], state)
    assert before['arm'] == 'A2_SINGLE' and before['status'] == 'fixed_reference'
    assert policy.choose(X[0], state, fully_observed=True)['arm'] == 'A0_NATIVE'
    assert policy.choose(np.array([0., .5]), state)['arm'] == 'A0_NATIVE'
    with pytest.raises(ValueError, match='Unacquired'):
        state.result('history')


def test_state_specific_cart_never_uses_unacquired_history_and_snapshot_is_immutable():
    policy, (X, E, *_rest) = fitted()
    supplied = E['mask'][0].copy()
    state = EvidenceState().acquire('mask', supplied)
    expected = policy.choose(X[0], state)
    supplied[:] = 1e10
    E['history'][:] = 1e10
    assert policy.choose(X[0], state) == expected
    assert expected['arm'] == 'A3_COV'
    assert expected['history'] == ['mask']
    assert policy.audit_['mask']['tools'] == ['mask']
    assert policy.transforms_['mask']['columns'].max() < len(NAMES) + 15
    full = state.acquire('history', np.tile([0., 0., 1.], 5))
    assert policy.choose(X[0], full)['history'] == ['mask', 'history']


def test_empty_support_or_tool_failure_is_explicit_fixed_fallback():
    policy, (X, *_rest) = fitted()
    unsupported = EvidenceState().acquire('mask', np.full(15, np.nan))
    failed = EvidenceState().acquire('mask', status='failed', reason='model_error')
    for state in (unsupported, failed):
        result = policy.choose(X[0], state)
        assert result['arm'] == 'A2_SINGLE' and result['status'] == 'fallback'
        assert result['reason']
    with pytest.raises(ValueError, match='fabricated'):
        EvidenceState().acquire('mask', np.zeros(15), status='failed', reason='bad')


def test_repeated_variants_do_not_supply_independent_training_parents():
    X, E, L, w, p = data(parents=15, repeats=100)
    policy = StatePolicy(2, sorted(set(p)), NAMES).fit(X, E, L, w, p)
    assert policy.models_ == {}
    assert all(r['supported_parents'] == 15 and r['status'] == 'unsupported' for r in policy.audit_.values())
    result = policy.choose(X[0], EvidenceState().acquire('mask', E['mask'][0]))
    assert result['status'] == 'fallback'


def test_every_used_leaf_has_parent_support_and_entire_state_hash_is_frozen():
    policy, (X, E, L, w, p) = fitted()
    assert policy.models_ and all(min(r['leaf_parent_counts'].values()) >= 16 for r in policy.audit_.values())
    assert all(r['cart_config']['max_depth'] == 3 and r['cart_config']['min_samples_leaf'] == 96
               for r in policy.audit_.values())
    digest = policy.frozen_hash
    policy.transforms_['history']['median'][0] += .01
    assert policy.frozen_hash != digest
    with pytest.raises(ValueError, match='again'):
        policy.fit(X, E, L, w, p)


def test_reference_respects_supplied_source_parent_weights_and_task_failures_are_rejected():
    L = np.array([[0., 10., 2., 3., 4.], [10., 0., 2., 3., 4.]])
    reference = freeze_reference(L, [.99, .01], ['rare', 'common'])
    assert reference['action'] == 0
    other = freeze_reference(L, [.01, .99], ['rare', 'common'])
    assert other['action'] == 1
    X, E, losses, w, p = data()
    losses[0, 1] = np.nan
    with pytest.raises(ValueError, match='task losses'):
        StatePolicy(2, sorted(set(p)), NAMES).fit(X, E, losses, w, p)
