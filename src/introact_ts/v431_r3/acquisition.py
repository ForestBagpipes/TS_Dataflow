"""One frozen-policy probe decision with complete branch costs and explicit STOP."""
from __future__ import annotations

import time
import numpy as np

from introact_ts.v43.agent_inputs import POOL
from introact_ts.v431.acquisition import (
    AcquiredBranch, Charge, CostInvoice, ValueLabelRow,
    fit_acquirer as _fit, make_value_labels as _labels,
    execute_one_step as _execute, _validate_feature_names,
)
from .response import require


BRANCH_TOOLS = {'H32': ('h32',), 'H': ('long',),
                'control': ('long', 'short'), 'equal-cost': ('long', 'second')}
ACTIVE_BRANCHES = ('H32', 'H', 'control')


class AccountedToolError(RuntimeError):
    def __init__(self, message, spent_invoice, *, attempted_tools=()):
        require(isinstance(spent_invoice, CostInvoice), 'Failed tool actual invoice required')
        require(set(attempted_tools) <= {'h32', 'long', 'short', 'second'}, 'Unknown primitive')
        super().__init__(message)
        self.spent_invoice = spent_invoice
        self.attempted_tools = tuple(attempted_tools)


def build_value_row(*, uid, parent, policy, dirty_features, losses, after_state,
                    stop_invoice, acquire_invoice, tool_invoices, weight=1., fully_observed=False):
    branch = after_state.kind
    require(branch in ACTIVE_BRANCHES, 'Only registered active probes produce acquisition labels')
    require(set(tool_invoices) == set(BRANCH_TOOLS[branch]), 'Primitive cost missing from acquired state')
    require(str(parent) not in set(policy.training_parent_ids) | set(policy.reference_parent_ids),
            'Acquisition parent entered response fitting/gate/reference')
    L = np.asarray(losses, float)
    require(L.shape == (5,) and np.isfinite(L).all(), 'Need five real finite task losses')
    fingerprint = policy.frozen_hash
    before = policy.choose(dirty_features, None, fully_observed=fully_observed)
    after = policy.choose(dirty_features, after_state, fully_observed=fully_observed)
    require(fingerprint == policy.frozen_hash, 'Policy changed while generating value label')
    return ValueLabelRow(uid, str(parent), branch, fingerprint, tuple(dirty_features),
                         float(L[before['action']]), float(L[after['action']]),
                         stop_invoice, acquire_invoice, weight=weight,
                         tool_invoice=CostInvoice().merge(*tool_invoices.values()))


def fit_acquirer(rows, terminal_hash, feature_names, *, task_differences=None, forbidden_parents=()):
    rows = tuple(rows)
    require(rows and all(r.tool in ACTIVE_BRANCHES for r in rows), 'Unknown or absent r3 acquisition rows')
    model = _fit(rows, terminal_hash, feature_names, task_differences=task_differences, forbidden_parents=forbidden_parents)
    model.report.update(version='v4.3.1-r3', max_acquisition_steps=1, positive_value_threshold=0.,
                        primitive_tools={k: list(v) for k, v in BRANCH_TOOLS.items()},
                        lambda_rule='unchanged_zero_or_formula_T_acq_parent_LOPO')
    return model


def make_value_labels(rows, terminal_hash, lambda_value):
    require(all(r.tool in ACTIVE_BRANCHES for r in rows), 'Unknown r3 acquisition branch')
    result = _labels(rows, terminal_hash, lambda_value)
    for row in result:
        row.update(primitives=list(BRANCH_TOOLS[row['tool']]),
                   tool_count=len(BRANCH_TOOLS[row['tool']]), acquisition_steps=1)
    return result


def execute_one_step(*, terminal_hash, visible_features, stop_arm, stop_invoice,
                     branch_estimates, budget, applicable, model, fetch, fallback=None,
                     fully_observed=False, mode='learned', tool_order=None,
                     condition=False, random_key='', seed=101):
    require(stop_arm in POOL, 'Unknown STOP action')
    require(set(branch_estimates) <= set(BRANCH_TOOLS), 'Unknown branch estimate')
    if mode in ('learned', 'random'):
        require(tool_order is None or set(tool_order) <= set(ACTIVE_BRANCHES), 'Mechanism controls are not active acquisition candidates')
    if model is not None:
        _validate_feature_names(model.feature_names)
        if 'missing_fraction' in model.feature_names:
            fully_observed = bool(fully_observed or np.asarray(visible_features)[model.feature_names.index('missing_fraction')] == 0.)
    require(not fully_observed or stop_arm == POOL[0], 'Complete observation requires KEEP')
    failures = []
    def guarded_fetch(branch):
        begun = time.perf_counter()
        try:
            result = fetch(branch)
        except Exception as exc:
            if isinstance(exc, AccountedToolError):
                spent, attempted = exc.spent_invoice, list(exc.attempted_tools)
                scope = 'actual_primitive_invoice'
            else:
                spent = CostInvoice((Charge('failed-probe-wall', time.perf_counter()-begun),))
                attempted, scope = None, 'measured_fetch_wall_unknown_completed_primitives'
            failure = {'type': type(exc).__name__, 'message': str(exc), 'attempted_primitives': attempted,
                       'spent_invoice': spent.as_dict(), 'cost_scope': scope,
                       'fallback': 'frozen_fixed_reference', 'failed_values_filled': False}
            if fallback is None:
                invoice = stop_invoice
                failure['fallback_cost_source'] = 'caller_audited_actual_STOP_invoice'
            else:
                actual = fallback()
                require(isinstance(actual, AcquiredBranch) and actual.terminal_hash == terminal_hash
                        and actual.arm == stop_arm, 'Fallback identity or fixed action changed')
                invoice = actual.invoice
                failure['fallback_cost_source'] = 'actual_fallback_callback'
            failures.append(failure)
            return AcquiredBranch(stop_arm, spent.merge(invoice), 'failed-no-evidence-consumed', terminal_hash)
        require(isinstance(result, AcquiredBranch) and result.arm in POOL, 'Invalid actual response output')
        return result
    result = _execute(terminal_hash=terminal_hash, visible_features=visible_features,
                      stop_arm=stop_arm, stop_invoice=stop_invoice, branch_estimates=branch_estimates,
                      budget=budget, applicable={k: v and not fully_observed for k, v in applicable.items()},
                      model=model, fetch=guarded_fetch, mode='stop' if fully_observed else mode,
                      tool_order=tuple(k for k in ACTIVE_BRANCHES if k in branch_estimates) if mode in ('learned', 'random') and tool_order is None else tool_order,
                      condition=condition, random_key=random_key, seed=seed)
    result.update(branch=result['tool'], acquisition_steps=int(result['tool'] is not None),
                  primitives=[] if result['tool'] is None or failures else list(BRANCH_TOOLS[result['tool']]),
                  requested_primitives=[] if result['tool'] is None else list(BRANCH_TOOLS[result['tool']]),
                  failure=failures[0] if failures else None)
    result['tool_count'] = len(result['primitives'])
    result['evidence_tool_count'] = len(result['primitives'])
    result['attempted_primitives'] = list(result['primitives'])
    if failures:
        result.update(status='failed_fallback', history=[], evidence_hash=None)
        attempted = failures[0]['attempted_primitives']
        result['attempted_primitives'] = attempted
        result['tool_count'] = None if attempted is None else len(attempted)
    return result
