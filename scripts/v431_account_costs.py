#!/usr/bin/env python3
"""Add measured dirty-diagnostic cost without changing frozen policy outcomes.

The original decisions, model files and value labels remain byte-for-byte
unchanged. Derived accounting files distinguish marginal hot computation from
actual measured input materialization/model initialization and offline work.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np

from introact_ts.v43.schemas import Episode, array_hash
from introact_ts.v431.data import dirty_features, PERIODS


OLD = Path('results/v43/20260914T141030.324186Z-agent')
PREFIXES = ('DIRTY_LOSS_TREE_', 'CART_', 'FLAT_LOSS_TREE_', 'ALL_', 'AGENT_',
            'FIXED_HISTORY_', 'FIXED_MASK_', 'VISIBLE_CONDITION_', 'RANDOM_')


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check(value, message):
    if not value:
        raise AssertionError(message)


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def add_charge(invoice, uid, seconds):
    charges = [dict(c) for c in invoice['charges']]
    key = 'shared-diagnostic:' + uid
    check(key not in {c['key'] for c in charges}, 'Dirty diagnosis already charged')
    charges.append({'key': key, 'seconds': seconds})
    charges.sort(key=lambda c: c['key'])
    return {'charges': charges, 'total_seconds': float(sum(c['seconds'] for c in charges))}


def sum_invoice(invoice):
    charges = invoice['charges']
    check(len(charges) == len({c['key'] for c in charges}), 'Duplicated shared cost identity')
    check(all(np.isfinite(c['seconds']) and c['seconds'] >= 0 for c in charges), 'Invalid measured cost')
    total = float(sum(c['seconds'] for c in charges))
    np.testing.assert_allclose(total, invoice['total_seconds'], rtol=1e-12, atol=1e-12)
    return total


def table_from_rows(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['policy'], row['source'], row['horizon'], row['condition']].append(row)
    detail = []
    for (policy, source, horizon, condition), items in groups.items():
        detail.append({'policy': policy, 'source': source, 'horizon': horizon, 'condition': condition,
                       'episodes': len(items),
                       **{field: float(np.mean([r[field] for r in items]))
                          for field in ('mase', 'mae', 'total_seconds', 'task_harm')},
                       'mean_tools': float(np.mean([len(r.get('history', [])) for r in items])),
                       'budget_overruns': sum(r['budget_overrun'] for r in items)})
    table = []
    for policy in sorted({r['policy'] for r in rows}):
        items = [g for g in detail if g['policy'] == policy]
        check(len(items) == 18, f'{policy} changed the 3 source x 2 horizon x 3 condition denominator')
        policy_rows = [r for r in rows if r['policy'] == policy]
        check(len(policy_rows) == 156 and len({r['episode_uid'] for r in policy_rows}) == 156,
              'Missing/duplicated development rows')
        table.append({'policy': policy, 'episodes': len(policy_rows),
                      'parents': len({r['parent_group'] for r in policy_rows}),
                      **{field: float(np.mean([g[field] for g in items]))
                         for field in ('mase', 'mae', 'total_seconds', 'task_harm', 'mean_tools')},
                      'budget_overruns': sum(g['budget_overruns'] for g in items),
                      'status': 'completed_dev_not_confirmatory',
                      'cost_scope': 'cached measured candidate/tool/forecast plus actual selection and dirty diagnosis; initialization separate'})
    return table, detail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', nargs='?', type=Path, default=Path('results/v431/20260914-sprint'))
    root = parser.parse_args().root
    start = time.perf_counter()
    report = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
              'source': 'single actual dirty_features measurement per frozen episode on server CPU',
              'new_future_labels_read': 0, 'new_heldout_labels_read': 0,
              'verifier_sha256': digest(__file__)}
    destination = root / 'cost_accounting_verification.json'
    check(not destination.exists(), 'Accounting report exists; preserve original run')
    inputs = ['decisions.json', 'table.json', 'value_labels.json', 'models.joblib',
              'models_frozen.json', 'terminal_manifest.json', 'partition.json']
    old_hashes = {name: digest(root / name) for name in inputs}
    try:
        io_start = time.perf_counter()
        partition = read(root / 'partition.json')
        original = read(root / 'decisions.json')
        original_table = {r['policy']: r for r in read(root / 'table.json')}
        labels = read(root / 'value_labels.json')
        manifest = read(root / 'terminal_manifest.json')
        frozen = read(root / 'models_frozen.json')
        bookkeeping_io_seconds = time.perf_counter() - io_start
        check(digest(root / 'models.joblib') == frozen['sha256'], 'Frozen model SHA mismatch')
        model_start = time.perf_counter()
        model = joblib.load(root / 'models.joblib')
        model_load_seconds = time.perf_counter() - model_start
        del model

        metadata = read(OLD / 'episode_manifest.json')
        check(set(partition) == set(metadata) and len(partition) == 816, 'Frozen episode manifest changed')
        for uid, m in partition.items():
            check(m['split'] in ('train', 'dev'), 'Heldout input forbidden')
            check(m['v431_role'] in ('T_fit', 'T_gate', 'T_check', 'T_acq', 'dev'), 'Unknown train role')
            check(m['parent_group'] == metadata[uid]['parent_group'], 'Parent identity changed')
        parent_roles = defaultdict(set)
        for m in partition.values():
            parent_roles[m['source'], m['parent_group']].add(m['v431_role'])
        check(all(len(roles) == 1 for roles in parent_roles.values()), 'Parent spans roles')

        diagnostics, values, materialization_seconds = {}, {}, 0.0
        measurement_start = time.perf_counter()
        with np.load(OLD / 'contexts.npz', allow_pickle=False) as contexts:
            for uid, m in partition.items():
                materialize = time.perf_counter()
                e = Episode(uid, m['source'], m['source'], m['parent_group'], m['split'], 0,
                            m['raw_start'], m['context_end'], m['horizon'],
                            contexts[uid + '_timestamps'], contexts[uid + '_target'],
                            contexts[uid + '_covariates'], contexts[uid + '_availability'])
                materialization_seconds += time.perf_counter() - materialize
                diagnostic_start = time.perf_counter()
                x = dirty_features(e, PERIODS[m['source']])
                seconds = time.perf_counter() - diagnostic_start
                check(np.isfinite(seconds) and seconds >= 0 and not np.isinf(x).any(),
                      'Failed dirty feature extraction')
                diagnostics[uid] = {'seconds': seconds, 'feature_hash': array_hash(x),
                                    'source': m['source'], 'parent_group': m['parent_group'],
                                    'role': m['v431_role'], 'calls': 1}
                values[uid] = x
        measurement_wall = time.perf_counter() - measurement_start
        diagnostic_sum = sum(r['seconds'] for r in diagnostics.values())
        write_new(root / 'dirty_diagnostic_costs.json', diagnostics)
        with (root / 'dirty_features_measured.npz').open('xb') as stream:
            np.savez(stream, **values)

        accounted, additions = [], Counter()
        high = manifest['budgets']['high']
        for row in original:
            uid = row['episode_uid']
            check(partition[uid]['v431_role'] == 'dev', 'Main table uses training/heldout data')
            item = dict(row)
            needs_diagnostic = row['policy'].startswith(PREFIXES)
            if needs_diagnostic:
                item['invoice'] = add_charge(row['invoice'], uid, diagnostics[uid]['seconds'])
                item['total_seconds'] = item['invoice']['total_seconds']
                item['dirty_diagnostic_seconds'] = diagnostics[uid]['seconds']
                additions[row['policy']] += 1
            else:
                item['dirty_diagnostic_seconds'] = 0.0
            if item['policy'] == 'OLD_LEARNED_HGB_COMMON_BUDGET':
                item['budget'] = high
            # The original unbudgeted controls' budget_overrun field referred to
            # the common high-budget reference; preserve that scope explicitly.
            bound = item.get('budget', high)
            if bound is None:
                bound = high
            item['budget_overrun'] = item['total_seconds'] > bound
            item['budget_accounting_scope'] = 'explicit_budget' if item.get('budget') is not None else 'common_high_budget_reference'
            total = sum_invoice(item['invoice'])
            np.testing.assert_allclose(total, item['total_seconds'], rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(item['total_seconds'] - row['total_seconds'],
                                       diagnostics[uid]['seconds'] if needs_diagnostic else 0.,
                                       rtol=1e-10, atol=1e-12)
            for field in ('episode_uid', 'policy', 'arm', 'mae', 'mase', 'candidate_hash', 'source', 'horizon', 'condition'):
                check(item[field] == row[field], f'Accounting changed a frozen decision {field}')
            accounted.append(item)

        accounted_labels, label_count = {}, 0
        for name, rows in labels.items():
            check(name in manifest['selected'], 'Unregistered acquisition model')
            accounted_labels[name] = []
            for row in rows:
                uid = row['uid'];item = dict(row)
                check(partition[uid]['v431_role'] == row['role'] == 'T_acq', 'Value label outside T_acq')
                check(row['terminal_hash'] == manifest['terminal_hashes'][name], 'Stale terminal value label')
                seconds = diagnostics[uid]['seconds']
                item['stop_invoice'] = add_charge(row['stop_invoice'], uid, seconds)
                item['acquire_invoice'] = add_charge(row['acquire_invoice'], uid, seconds)
                item['stop_cost'] = sum_invoice(item['stop_invoice'])
                item['acquire_cost'] = sum_invoice(item['acquire_invoice'])
                item['shared_diagnostic_seconds'] = seconds
                item['accounting_derivation'] = 'same known dirty diagnosis in STOP and acquire; original model/value label unchanged'
                np.testing.assert_allclose(item['acquire_cost'] - item['stop_cost'], row['delta_cost'],
                                           rtol=1e-10, atol=1e-12)
                for field in ('task_gain', 'delta_cost', 'lambda', 'value', 'terminal_hash', 'role', 'parent', 'weight'):
                    check(item[field] == row[field], f'Accounting changed frozen acquisition supervision {field}')
                accounted_labels[name].append(item)
                label_count += 1

        table, groups = table_from_rows(accounted)
        # Independently recompute source -> parent aggregation, which must equal
        # the common 18-cell source/horizon/defect mean for this balanced matrix.
        grouped_parents = defaultdict(list)
        for row in accounted:
            grouped_parents[row['policy'], row['source'], row['parent_group']].append(row)
        for row in table:
            policy = row['policy'];sources = {s for p, s, _ in grouped_parents if p == policy}
            for field in ('mae', 'mase', 'total_seconds'):
                independent = np.mean([np.mean([np.mean([r[field] for r in items])
                    for (p, s, _), items in grouped_parents.items() if p == policy and s == source]) for source in sources])
                np.testing.assert_allclose(row[field], independent, rtol=1e-12, atol=1e-12)
            for field in ('mae', 'mase', 'task_harm', 'mean_tools'):
                np.testing.assert_allclose(row[field], original_table[policy][field], rtol=1e-12, atol=1e-12)
        write_new(root / 'accounted_decisions.json', accounted)
        write_new(root / 'accounted_table.json', table)
        write_new(root / 'accounted_metrics_by_group.json', groups)
        write_new(root / 'value_labels_accounted.json', accounted_labels)
        scope = {'dirty_diagnostic': {'single_pass_calls': len(diagnostics),
                                     'total_measured_function_seconds': diagnostic_sum,
                                     'measurement_loop_wall_seconds': measurement_wall,
                                     'input_materialization_seconds': materialization_seconds,
                                     'vector_and_accounting_overhead_seconds': measurement_wall - diagnostic_sum - materialization_seconds},
                 'initialization_measured_here': {'model_joblib_load_seconds': model_load_seconds,
                                                 'accounting_manifest_io_seconds': bookkeeping_io_seconds,
                                                 'context_materialization_seconds': materialization_seconds},
                 'offline_cost_references': {'historical_generation': str(root / 'history' / 'cost_ledger.json'),
                                             'old_full_counterfactual_generation': str(OLD / 'cost_ledger.json'),
                                             'current_fit_search_wall': read(root / 'status.json')['runtime_seconds']},
                 'limitations': ['Initialization timings are this accounting process on a warm filesystem, not a cold storage benchmark.',
                                 'Per-request dirty-feature cost is added only to methods that use the dirty feature vector.',
                                 'Old HGB selection already includes its feature computation; fixed five-arm methods do not require the new diagnostic vector.',
                                 'Counterfactual cache reuse does not erase original offline generation/training cost.',
                                 'True online end-to-end timings remain the separate online replay artifact.'],
                 'diagnostic_source_sha256': digest('src/introact_ts/v431/data.py')}
        write_new(root / 'accounted_cost_scope.json', scope)
        check(all(digest(root / name) == h for name, h in old_hashes.items()), 'Original frozen artifact was modified')
        report.update(status='passed', diagnostic_episodes=len(diagnostics), diagnostic_calls=len(diagnostics),
                      policies=len(table), decision_rows=len(accounted), added_diagnostic_rows=sum(additions.values()),
                      policies_charged=dict(additions), acquisition_value_rows=label_count,
                      delta_cost_and_value_unchanged=True, predictions_and_task_metrics_unchanged=True,
                      source_parent_weighting_verified=True, original_artifacts_unchanged=old_hashes,
                      measured_diagnostic_seconds=diagnostic_sum,
                      measured_initialization_and_input_seconds=model_load_seconds + bookkeeping_io_seconds + materialization_seconds,
                      heldout_labels_read=0, promotion=False)
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['complete_process_wall_seconds'] = time.perf_counter() - start
        write_new(destination, report)
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
