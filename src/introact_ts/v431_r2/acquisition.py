"""One acquisition decision over mask/history/both, with fixed inherited price."""
from __future__ import annotations

import hashlib
import math
import time

import numpy as np

from introact_ts.v43.agent_inputs import POOL
from introact_ts.v431.acquisition import (
    Acquirer, AcquiredBranch, Charge, CostInvoice, ParentRegressionTree,
    ValueLabelRow, make_value_labels as _old_labels, _validate_feature_names,
    fit_acquirer as _registered_fit_acquirer,
)
from .policy import EvidenceState, STATE_TOOLS, require

BRANCH_TOOLS = {state: STATE_TOOLS[state] for state in ('mask', 'history', 'both')}


def build_value_row(*, uid, parent, policy, dirty_features, losses, after_state,
                    stop_invoice, acquire_invoice, tool_invoices, weight=1., fully_observed=False):
    """Evaluator-only counterfactual row from exactly one complete frozen pi."""
    require(isinstance(after_state, EvidenceState) and after_state.kind in BRANCH_TOOLS,
            'An acquisition label needs its actually acquired state')
    expected = set(BRANCH_TOOLS[after_state.kind])
    require(set(tool_invoices) == expected, 'Combination branch must account for both tools')
    require(str(parent) not in set(policy.training_parent_ids) | set(policy.reference_parent_ids),
            'T_acq parent entered terminal/reference fitting')
    L = np.asarray(losses, float)
    require(L.shape == (5,) and np.isfinite(L).all(), 'Need all five actual finite task losses')
    fingerprint = policy.frozen_hash
    before = policy.choose(dirty_features, EvidenceState(), fully_observed=fully_observed)
    after = policy.choose(dirty_features, after_state, fully_observed=fully_observed)
    require(policy.frozen_hash == fingerprint, 'Terminal policy changed while generating value label')
    tools = CostInvoice().merge(*(tool_invoices[t] for t in BRANCH_TOOLS[after_state.kind]))
    return ValueLabelRow(uid, str(parent), after_state.kind, fingerprint, tuple(dirty_features),
                         float(L[before['action']]), float(L[after['action']]), stop_invoice,
                         acquire_invoice, weight=weight, tool_invoice=tools)


def make_value_labels(rows, terminal_hash, lambda_value):
    require(all(row.tool in BRANCH_TOOLS for row in rows), 'Unknown r2 acquisition branch')
    output = _old_labels(rows, terminal_hash, lambda_value)
    for row in output:
        row['tools'] = list(BRANCH_TOOLS[row['tool']])
        row['tool_count'] = len(row['tools'])
        row['acquisition_steps'] = 1
    return output


def fit_acquirer(rows, terminal_hash, feature_names, *, lambda_value=None,
                 task_differences=None, forbidden_parents=()):
    """Reuse registered zero/formula prices and T_acq parent leave-one-out.

    A caller may instead pass an already frozen lambda. This never introduces
    another threshold, price grid, or dev-based selection.
    """
    rows, names = tuple(rows), tuple(feature_names)
    _validate_feature_names(names)
    require(rows and (lambda_value is None or math.isfinite(lambda_value) and lambda_value >= 0),
            'Missing labels or invalid frozen lambda')
    require(all(row.terminal_hash == terminal_hash and row.role == 'T_acq' for row in rows),
            'Stale policy hash or non-T_acq label')
    require(not ({row.parent for row in rows} & set(forbidden_parents)), 'Terminal/acquisition parent overlap')
    require(all(row.tool in BRANCH_TOOLS and len(row.features) == len(names) for row in rows),
            'Acquisition feature or branch schema changed')
    seen, snapshots = set(), {}
    for row in rows:
        require((row.uid, row.tool) not in seen, 'Duplicate acquisition value label')
        seen.add((row.uid, row.tool))
        if row.uid in snapshots:
            require(np.array_equal(snapshots[row.uid], row.features, equal_nan=True),
                    'Pre-acquisition features depend on hidden target tool')
        snapshots[row.uid] = row.features
    if lambda_value is None:
        result = _registered_fit_acquirer(rows, terminal_hash, names,
                    task_differences=task_differences, forbidden_parents=forbidden_parents)
        result.report.update(version='v4.3.1-r2', max_acquisition_steps=1,
                             branch_tools={k: list(v) for k, v in BRANCH_TOOLS.items()},
                             combination_is_two_tools=True, positive_value_threshold=0.,
                             lambda_rule='unchanged_registered_zero_or_formula_T_acq_parent_LOPO')
        return result
    models, support = {}, {}
    for branch in BRANCH_TOOLS:
        subset = [row for row in rows if row.tool == branch]
        count = len({row.parent for row in subset})
        support[branch] = {'parents': count, 'rows': len(subset),
                           'status': 'fitted' if count >= 16 else 'unsupported_parent_count',
                           'tools': list(BRANCH_TOOLS[branch]), 'tool_count': len(BRANCH_TOOLS[branch])}
        if count >= 16:
            models[branch] = ParentRegressionTree(max_depth=2, min_parents=16).fit(
                [row.features for row in subset], [row.task_gain - lambda_value * row.delta_cost for row in subset],
                [row.parent for row in subset], [row.weight for row in subset])
    report = {'terminal_hash': terminal_hash, 'feature_names': list(names), 'lambda': lambda_value,
              'lambda_selection': 'inherited_frozen_price_no_r2_search', 'positive_value_threshold': 0.,
              'parents': len({row.parent for row in rows}), 'rows': len(rows), 'tool_support': support,
              'max_depth': 2, 'min_leaf_independent_parents': 16, 'max_acquisition_steps': 1,
              'combination_is_two_tools': True, 'model_family': 'one parent-constrained regression tree per branch',
              'unsupported_behavior': 'explicit STOP; no synthetic zero model'}
    return Acquirer(terminal_hash, names, models, float(lambda_value), report)


class AccountedToolError(RuntimeError):
    """A tool runner records already incurred computation before raising."""
    def __init__(self, message, spent_invoice, *, attempted_tools=()):
        require(isinstance(spent_invoice, CostInvoice), 'Failed tool cost invoice required')
        require(set(attempted_tools) <= set(('mask', 'history')), 'Unknown failed tool identity')
        super().__init__(message)
        self.spent_invoice = spent_invoice
        self.attempted_tools = tuple(attempted_tools)


def execute_one_step(*, terminal_hash, visible_features, stop_arm, stop_invoice,
                     branch_estimates, budget, applicable, model, fetch, fallback=None,
                     fully_observed=False, mode='learned', tool_order=None,
                     condition=False, random_key='', seed=101):
    """STOP or one branch; `both` means two real tools and a single decision.

    In real online use fallback() must return the actually generated fixed
    reference and its actual final-forecast invoice. Offline cache replay may
    supply the already audited actual stop_invoice directly. Unexpected tool
    exceptions record elapsed fetch wall; accounted exceptions retain their
    exact measured invoices. Contract/hash violations are never swallowed.
    """
    require(stop_arm in POOL and isinstance(stop_invoice, CostInvoice), 'Invalid fixed STOP branch')
    require(budget is None or math.isfinite(budget) and budget >= 0, 'Invalid frozen complete-branch budget')
    require(mode in ('learned', 'fixed', 'simple', 'random', 'stop'), 'Unregistered acquisition mode')
    require(set(branch_estimates) <= set(BRANCH_TOOLS), 'Unregistered branch estimate')
    if model is not None:
        require(model.terminal_hash == terminal_hash, 'Terminal hash invalidates trained acquirer')
        if 'missing_fraction' in model.feature_names:
            fully_observed = bool(fully_observed or
                np.asarray(visible_features)[model.feature_names.index('missing_fraction')] == 0.)
    if fully_observed:
        require(stop_arm == 'A0_NATIVE', 'Fully observed input must already select KEEP')
    order = tuple(BRANCH_TOOLS) if tool_order is None else tuple(tool_order)
    require(len(order) == len(set(order)) and set(order) <= set(BRANCH_TOOLS), 'Invalid branch order')
    values, excluded, eligible = {}, {}, []
    for branch in order:
        if branch not in branch_estimates:
            excluded[branch] = 'estimate_unavailable'
            continue
        estimate = branch_estimates[branch]
        require(isinstance(estimate, CostInvoice), 'Full branch invoice required; marginal cost is insufficient')
        if fully_observed:
            excluded[branch] = 'fully_observed_no_op'
        elif not applicable.get(branch, False):
            excluded[branch] = 'unsupported'
        elif budget is not None and estimate.total_seconds > budget + 1e-12:
            excluded[branch] = 'estimated_complete_branch_exceeds_budget'
        else:
            eligible.append(branch)
    selected = None
    if mode == 'learned' and not fully_observed:
        require(model is not None, 'Learned acquisition needs a frozen model')
        for branch in eligible:
            value = model.predict(visible_features, branch, terminal_hash)
            if value is None:
                excluded[branch] = 'unsupported_train_parent_count'
            else:
                values[branch] = value
        if values and max(values.values()) > 0:
            selected = max(values, key=values.get)
    elif mode == 'fixed' or mode == 'simple' and condition:
        selected = eligible[0] if eligible else None
    elif mode == 'random' and eligible:
        require(seed == 101, 'Random control seed remains 101')
        digest = hashlib.sha256(f'{seed}:{random_key}'.encode()).digest()
        options = [None, *eligible]
        selected = options[int.from_bytes(digest[:8], 'big') % len(options)]
    arm, actual_invoice, evidence_hash = stop_arm, stop_invoice, None
    failure, actual_tools = None, []
    if selected is not None:
        started = time.perf_counter()
        try:
            result = fetch(selected)
        except Exception as exc:
            elapsed = time.perf_counter() - started
            if isinstance(exc, AccountedToolError):
                spent, attempted = exc.spent_invoice, list(exc.attempted_tools)
                source = 'tool_runner_actual_invoice'
            else:
                spent, attempted = CostInvoice((Charge('failed-fetch-wall', elapsed),)), None
                source = 'measured_fetch_wall_unaccounted_exception'
            failure = {'type': type(exc).__name__, 'message': str(exc), 'spent_invoice': spent.as_dict(),
                       'attempted_tools': attempted, 'spent_cost_source': source,
                       'fallback': 'frozen_fixed_reference', 'no_failed_output_filled': True}
            if fallback is None:
                actual_invoice = spent.merge(stop_invoice)
                failure['fallback_invoice_source'] = 'caller_supplied_audited_actual_STOP_invoice'
            else:
                result = fallback()
                require(isinstance(result, AcquiredBranch) and result.terminal_hash == terminal_hash,
                        'Fallback changed frozen terminal identity')
                require(result.arm == stop_arm, 'Failure fallback must use the fixed STOP reference')
                actual_invoice = spent.merge(result.invoice)
                failure['fallback_invoice_source'] = 'actual_fallback_callback'
        else:
            require(isinstance(result, AcquiredBranch), 'Tool branch lacks complete actual invoice')
            require(result.terminal_hash == terminal_hash, 'Acquired branch changed frozen terminal hash')
            require(result.arm in POOL and isinstance(result.invoice, CostInvoice) and bool(result.evidence_hash),
                    'Invalid completed acquisition output')
            arm, actual_invoice, evidence_hash = result.arm, result.invoice, result.evidence_hash
            actual_tools = list(BRANCH_TOOLS[selected])
    overrun = budget is not None and actual_invoice.total_seconds > budget + 1e-12
    return {'terminal_hash': terminal_hash, 'mode': mode, 'arm': arm, 'tool': selected,
            'branch': selected, 'history': actual_tools, 'tool_count': len(actual_tools),
            'requested_tools': [] if selected is None else list(BRANCH_TOOLS[selected]),
            'acquisition_steps': int(selected is not None), 'failure': failure,
            'status': 'failed_fallback' if failure is not None else 'budget_overrun' if overrun
                      else 'STOP' if selected is None else 'COMMIT',
            'budget': budget, 'budget_overrun': overrun, 'total_seconds': actual_invoice.total_seconds,
            'invoice': actual_invoice.as_dict(), 'stop_total_seconds': stop_invoice.total_seconds,
            'delta_cost': actual_invoice.total_seconds - stop_invoice.total_seconds,
            'evidence_hash': evidence_hash, 'predicted_values': values, 'excluded': excluded,
            'estimated_branch_costs': {b: i.total_seconds for b, i in branch_estimates.items()}}
