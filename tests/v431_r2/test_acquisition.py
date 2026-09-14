import numpy as np
import pytest

from introact_ts.v431_r2.acquisition import (
    AccountedToolError, AcquiredBranch, Charge, CostInvoice, ValueLabelRow,
    execute_one_step, fit_acquirer, make_value_labels,
)

HASH = 'full-state-policy-frozen-hash'
NAMES = ('missing_fraction', 'horizon_ratio')


def invoice(**values):
    return CostInvoice(tuple(Charge(key, value) for key, value in values.items()))


def rows(gains=None):
    gains = gains or {'mask': 1., 'history': 1., 'both': 2.}
    output = []
    for parent in range(18):
        for branch in ('mask', 'history', 'both'):
            tools = invoice(mask=1., history=1.) if branch == 'both' else invoice(**{branch: 1.})
            output.append(ValueLabelRow(f'u{parent}', f'p{parent}', branch, HASH, (.1, .5),
                3., 3. - gains[branch], invoice(shared=1., final=2.),
                invoice(shared=1., final=2.).merge(tools), weight=1./18, tool_invoice=tools))
    return output


def model(gains=None):
    return fit_acquirer(rows(gains), HASH, NAMES, lambda_value=.1)


def arguments(acquirer, fetch):
    return dict(terminal_hash=HASH, visible_features=(.1, .5), stop_arm='A2_SINGLE',
        stop_invoice=invoice(shared=1., final=2.),
        branch_estimates={'mask': invoice(branch=4.), 'history': invoice(branch=4.), 'both': invoice(branch=5.)},
        budget=6., applicable={'mask': True, 'history': True, 'both': True}, model=acquirer, fetch=fetch)


def test_combination_is_one_decision_and_two_charged_tools():
    called = []
    def fetch(branch):
        called.append(branch)
        return AcquiredBranch('A3_COV', invoice(mask=1., history=1., final=2.), 'both-evidence-hash', HASH)
    result = execute_one_step(**arguments(model(), fetch))
    assert called == ['both']
    assert result['acquisition_steps'] == 1 and result['tool_count'] == 2
    assert result['history'] == ['mask', 'history'] and result['total_seconds'] == 4.
    labels = make_value_labels(rows(), HASH, .1)
    assert next(r for r in labels if r['tool'] == 'both')['tool_count'] == 2


def test_hidden_evidence_not_fetched_on_stop_or_full_observation():
    def forbidden(_):
        raise AssertionError('No hidden evidence may be opened')
    kwargs = arguments(model({'mask': -1., 'history': 0., 'both': -2.}), forbidden)
    result = execute_one_step(**kwargs)
    assert result['history'] == [] and result['arm'] == 'A2_SINGLE' and result['status'] == 'STOP'
    kwargs.update(stop_arm='A0_NATIVE', fully_observed=True)
    result = execute_one_step(**kwargs)
    assert result['arm'] == 'A0_NATIVE' and result['acquisition_steps'] == 0


def test_low_budget_uses_complete_branch_and_retains_actual_overrun():
    called = []
    def fetch(branch):
        called.append(branch)
        return AcquiredBranch('A3_COV', invoice(tool=5., final=3.), 'real-evidence', HASH)
    kwargs = arguments(model(), fetch)
    kwargs['budget'] = 3.
    result = execute_one_step(**kwargs)
    assert not called and result['status'] == 'STOP'
    assert all(reason == 'estimated_complete_branch_exceeds_budget' for reason in result['excluded'].values())
    kwargs['budget'] = 6.
    result = execute_one_step(**kwargs)
    assert result['budget_overrun'] and result['total_seconds'] == 8. and result['arm'] == 'A3_COV'


def test_exact_spent_cost_and_actual_fixed_fallback_are_preserved_on_failure():
    calls = []
    def fetch(branch):
        calls.append(branch)
        raise AccountedToolError('history worker failed after mask', invoice(mask=2., failed_history=4.),
                                 attempted_tools=('mask', 'history'))
    def fallback():
        calls.append('fallback')
        return AcquiredBranch('A2_SINGLE', invoice(final=2.), 'fallback-real-prediction', HASH)
    result = execute_one_step(**arguments(model(), fetch), fallback=fallback)
    assert calls == ['both', 'fallback']
    assert result['status'] == 'failed_fallback' and result['arm'] == 'A2_SINGLE'
    assert result['total_seconds'] == 8. and result['budget_overrun']
    assert result['failure']['spent_invoice']['total_seconds'] == 6.
    assert result['history'] == [] and result['failure']['no_failed_output_filled']


def test_unaccounted_tool_exception_records_elapsed_time_not_a_zero_failure():
    def fetch(branch):
        raise RuntimeError('explicit failure')
    result = execute_one_step(**arguments(model(), fetch))
    assert result['status'] == 'failed_fallback'
    assert result['failure']['spent_cost_source'] == 'measured_fetch_wall_unaccounted_exception'
    assert result['failure']['spent_invoice']['total_seconds'] > 0
    assert result['total_seconds'] > 3.


def test_complete_state_hash_invalidates_labels_models_and_returned_branch():
    with pytest.raises(ValueError, match='hash'):
        fit_acquirer(rows(), 'updated-hash', NAMES, lambda_value=.1)
    with pytest.raises(ValueError, match='hash'):
        make_value_labels(rows(), 'updated-hash', .1)
    kwargs = arguments(model(), lambda _: AcquiredBranch('A3_COV', invoice(total=4.), 'evidence', 'wrong'))
    with pytest.raises(ValueError, match='hash'):
        execute_one_step(**kwargs)
    kwargs['terminal_hash'] = 'updated'
    with pytest.raises(ValueError, match='hash'):
        execute_one_step(**kwargs)


def test_price_rule_and_parent_isolation_are_reused_without_lowering_threshold():
    trained = fit_acquirer(rows(), HASH, NAMES, task_differences=[1.])
    assert trained.report['lambda_candidates'] == [0., .1]
    assert trained.report['positive_value_threshold'] == 0.
    assert all(record['held_parent'] not in record['train_parents'] for record in trained.report['cv_records'])
    assert all(tree.root_.feature is None for tree in trained.models.values())
    with pytest.raises(ValueError, match='overlap'):
        fit_acquirer(rows(), HASH, NAMES, forbidden_parents=['p0'])
    with pytest.raises(ValueError, match='unavailable'):
        fit_acquirer(rows(), HASH, ('missing_fraction', 'candidate_value'))
