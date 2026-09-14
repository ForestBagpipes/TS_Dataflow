import numpy as np
import pytest

from introact_ts.v431.acquisition import AcquiredBranch, Charge, CostInvoice, ValueLabelRow
from introact_ts.v431_r3.acquisition import AccountedToolError, execute_one_step, make_value_labels
from introact_ts.v431_r3.response import PriorRidge, ResponseEvidence, ResponsePolicy, historical_argmax, state_from_results, PSI_NAMES
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.schemas import array_hash


def evidence(kind='H', d=(0.1, -.2, 0., .3, -.1), extra=None, identity='e'):
    tools = {'H': ('long',), 'control': ('long', 'short'), 'H32': ('h32',)}[kind]
    return ResponseEvidence(kind, d, (.25, -.5), extra,
                            evidence_hash=identity, primitive_hashes=tuple((p, identity+p) for p in tools))


def fixture(estimator='residual', fit_parents=32):
    n, g = fit_parents*3, 16*3
    X = [evidence(d=(.1+i%3*.1, -.2, 0., .3, -.1), identity=f'f{i}') for i in range(n)]
    G = [evidence(d=(.1+i%3*.1, -.2, 0., .3, -.1), identity=f'g{i}') for i in range(g)]
    L = np.array([3.-np.asarray(e.d) for e in X])
    GL = np.array([3.-np.asarray(e.d) for e in G])
    p = np.array([f'f{i//3}' for i in range(n)])
    gp = np.array([f'g{i//3}' for i in range(g)])
    policy = ResponsePolicy(2, np.r_[p,gp], ('missing_fraction',), ('lag_difference', 'coverage_difference'), estimator, ('H',))
    return policy.fit({'H': X}, L, np.ones(n)/n, p, gate_evidence={'H': G}, gate_losses=GL,
                      gate_weights=np.ones(g)/g, gate_parents=gp)


def test_residual_ridge_identity_prior_in_original_units():
    x = np.arange(20, dtype=float).reshape(10, 2)
    for alpha in (.1, 1., 10.):
        model = PriorRidge(alpha).fit(x, x[:, 0], np.ones(10)/10)
        np.testing.assert_array_equal(model.coef_, [1., 0.])
        np.testing.assert_array_equal(model.predict(x), x[:, 0])
        assert model.intercept_ == 0


def test_response_signed_values_not_clipped_or_filled():
    e = evidence('control', extra=(-100., 20., 0., -3., 5.))
    assert e.extra[0] == -100.
    with pytest.raises(ValueError, match='No-kappa'):
        evidence('H', extra=(0.,)*5)
    with pytest.raises(ValueError, match='No-kappa'):
        evidence('control')
    with pytest.raises(ValueError, match='fabricated'):
        ResponseEvidence('H', (0.,)*5, status='unsupported', reason='absent')


def test_response_snapshots_are_immutable_and_bound():
    d = np.array([.1, -.2, 0., .3, -.1])
    e = evidence(d=d)
    before = e.identity_hash
    d[0] = 100.
    assert e.d[0] == .1 and e.identity_hash == before
    assert evidence(d=(.2, -.2, 0., .3, -.1)).identity_hash != before


def test_reference_stop_complete_keep_and_missing_state_fallback():
    p = fixture()
    assert p.choose([.1])['action'] == 2
    assert p.choose([0.])['action'] == 0
    absent = ResponseEvidence('H', status='unsupported', reason='history_boundary')
    assert p.choose([.1], absent)['action'] == 2
    r = p.choose([.1], evidence())
    assert r['estimated_gains'][2] == 0.
    np.testing.assert_allclose(r['estimated_gains'], evidence().d, atol=1e-12)


def test_same_capacity_direct_and_residual_and_gate_grid():
    r, d = fixture(), fixture('direct')
    assert r.audit_['H']['input_width'] == d.audit_['H']['input_width'] == 7
    assert r.models_['H'].coef_.shape == d.models_['H'].coef_.shape
    assert r.audit_['H']['alpha_candidates'] == [.1, 1., 10.]
    assert r.fit_parent_ids_ != r.gate_parent_ids_
    assert r.frozen_hash != d.frozen_hash


def test_parent_support_is_not_variant_count():
    p = fixture(fit_parents=15)
    assert p.audit_['H']['status'] == 'unsupported'
    assert p.choose([.1], evidence())['action'] == 2


def test_same_evidence_cart_parent_leaf_support():
    p = fixture('cart')
    assert p.audit_['H']['cart_config']['max_depth'] == 3
    assert min(p.audit_['H']['leaf_parent_counts'].values()) >= 16
    assert p.choose([.1], evidence())['action'] in range(5)


def test_historical_argmax_reference_ties():
    assert historical_argmax(2, evidence(d=(0., 0., 0., 0., 0.))) == 2
    assert historical_argmax(2, evidence()) == 3
    assert historical_argmax(2, evidence(), fully_observed=True) == 0


def test_negative_value_labels_and_policy_hash_invalidation():
    stop = CostInvoice((Charge('stop-final', .1),))
    tool = CostInvoice((Charge('long', .4),))
    after = tool.merge(CostInvoice((Charge('after-final', .2),)))
    row = ValueLabelRow('u', 'p', 'H', 'frozen', (.1,), 1., 1.2, stop, after, tool_invoice=tool)
    r = make_value_labels([row], 'frozen', 1.)[0]
    assert np.isclose(r['value'], -.7)
    with pytest.raises(ValueError, match='invalidates'):
        make_value_labels([row], 'changed', 0.)


def test_full_branch_budget_and_measured_failure_costs():
    stop = CostInvoice((Charge('stop-final', .1),))
    branch = CostInvoice((Charge('long', .4), Charge('after-final', .2)))
    calls = []
    def fetch(tool):
        calls.append(tool)
        raise AccountedToolError('actual long failed', CostInvoice((Charge('spent-long', .15),)), attempted_tools=('long',))
    r = execute_one_step(terminal_hash='p', visible_features=[.1], stop_arm='A2_SINGLE', stop_invoice=stop,
                         branch_estimates={'H': branch}, budget=.5, applicable={'H': True}, model=None, fetch=fetch, mode='fixed')
    assert not calls and r['status'] == 'STOP'  # delta .5 cannot admit the actual .6 branch
    r = execute_one_step(terminal_hash='p', visible_features=[.1], stop_arm='A2_SINGLE', stop_invoice=stop,
                         branch_estimates={'H': branch}, budget=.6, applicable={'H': True}, model=None, fetch=fetch, mode='fixed')
    assert calls == ['H'] and r['status'] == 'failed_fallback'
    assert np.isclose(r['total_seconds'], .25) and r['tool_count'] == 1 and r['evidence_tool_count'] == 0
    assert r['failure']['attempted_primitives'] == ['long']


def test_same_cost_control_not_added_to_active_search():
    with pytest.raises(ValueError, match='not active'):
        execute_one_step(terminal_hash='p', visible_features=[.1], stop_arm='A2_SINGLE', stop_invoice=CostInvoice(),
                         branch_estimates={}, budget=1., applicable={}, model=None, fetch=lambda _: None,
                         mode='learned', tool_order=('equal-cost',))


def atom(name, offset=0.):
    predictions = {a: np.full(96, j+offset, dtype=float) for j, a in enumerate(POOL)}
    return {'status': 'completed', 'probe': name, 'base_uid': 'u', 'family': 'bolt',
            'input_hash': name, 'model_identity_hash': 'real-model', 'reference_arm': 'A2_SINGLE',
            'current_scale': 2., 'scoring_mask_hash': 'mask',
            'spec': {'start': 64 if name == 'short' else 0, 'origin': 352 if name == 'second' else 416,
                     'horizon': 96, 'current_origin': 512},
            'mae': {a: j+1.+offset for j, a in enumerate(POOL)},
            'raw_predictions': {a: p.tolist() for a, p in predictions.items()},
            'prediction_hashes': {a: array_hash(p) for a, p in predictions.items()},
            'psi': {n: 0. for n in PSI_NAMES}}


def test_shared_factory_hidden_short_and_strict_signed_pair():
    class Hidden(dict):
        def __getitem__(self, key):
            if key != 'long':
                raise AssertionError('hidden short read')
            return super().__getitem__(key)
    e = state_from_results('H', Hidden(long=atom('long')), reference_arm='A2_SINGLE')
    assert e.kind == 'H' and e.extra is None
    wrong = atom('short'); wrong['scoring_mask_hash'] = 'different'
    with pytest.raises(ValueError, match='scoring masks'):
        state_from_results('control', {'long': atom('long'), 'short': wrong}, reference_arm='A2_SINGLE')


def test_raw_forecast_disagreement_not_absolute_error_gain_response():
    atoms = {'long': atom('long'), 'short': atom('short', 4.)}
    response = state_from_results('control', atoms, reference_arm='A2_SINGLE')
    dispersion = state_from_results('disagreement', atoms, reference_arm='A2_SINGLE')
    np.testing.assert_array_equal(response.extra, np.zeros(5))
    # Both historical gain vectors are identical, but real forecast views differ.
    np.testing.assert_array_equal(dispersion.extra, np.ones(5))


def test_known_unsupported_does_not_silently_become_H():
    atoms = {'long': atom('long'), 'short': {'status': 'unsupported', 'reason': 'gap_outside_short'}}
    absent = state_from_results('control', atoms, reference_arm='A2_SINGLE')
    assert absent.kind == 'control' and absent.status == 'unsupported' and absent.d is None
    actual = state_from_results('control', atoms, reference_arm='A2_SINGLE', allow_degrade_to_H=True)
    assert actual.kind == 'H' and actual.requested_kind == 'control' and actual.extra is None


def test_same_input_equal_cost_uses_actual_second_origin():
    e = state_from_results('equal-cost', {'long': atom('long'), 'second': atom('second')}, reference_arm='A2_SINGLE')
    assert e.tools == ('long', 'second') and e.extra is not None
    with pytest.raises(ValueError, match='another frozen reference'):
        state_from_results('H', {'long': atom('long')}, reference_arm=POOL[1])


def test_json_state_primitives_are_frozen_copies():
    pairs = [['long', 'original']]
    e = ResponseEvidence('H', (1., -.2, 0., 2., -.1), (.1,), evidence_hash='e', primitive_hashes=pairs)
    before = e.identity_hash
    pairs[0][1] = 'changed'
    assert e.primitive_hashes == (('long', 'original'),) and e.identity_hash == before


def test_fitting_parent_may_not_be_used_as_gate():
    p = ResponsePolicy(2, ['shared'], ('missing_fraction',), ('gap_difference',), states=('H',))
    with pytest.raises(ValueError, match='Fit/gate parent overlap'):
        p.fit({'H': [evidence()]}, [[1.]*5], [1.], ['shared'],
              gate_evidence={'H': [evidence()]}, gate_losses=[[1.]*5], gate_weights=[1.], gate_parents=['shared'])
