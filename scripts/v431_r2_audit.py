#!/usr/bin/env python3
"""Read-only r2 diagnosis of v4.3.1 STOP, real task outputs and train support."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np

from introact_ts.v43.agent_inputs import POOL, mask_views
from introact_ts.v43.schemas import array_hash
from introact_ts.v43.worker_protocol import verify_response
from introact_ts.v431.data import SprintData, FEATURE_NAMES
from introact_ts.v431.acquisition import CostInvoice, Charge, execute_one_step

OLD = Path('results/v43/20260914T141030.324186Z-agent')
RUN = Path('results/v431/20260914-sprint')
OUT = Path('results/v431-r2/audit') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def write(name, value):
    with (OUT / name).open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def finite_or_none(x):
    return float(x) if np.isfinite(x) else None


def macro(rows, field):
    buckets = defaultdict(list)
    for row in rows:
        buckets[row['source'], row['parent_group']].append(row[field])
    return float(np.mean([np.mean([np.mean(v) for (s, _), v in buckets.items() if s == source])
                          for source in sorted({k[0] for k in buckets})]))


def path_for(tree, x):
    node, path = tree.root_, []
    while 'feature' in node:
        f, v = node['feature'], x[node['feature']]
        left = node['missing_left'] if np.isnan(v) else v <= node['threshold']
        path.append({'node': node['id'], 'feature': FEATURE_NAMES[f], 'index': f,
                     'value': finite_or_none(v), 'threshold': node['threshold'], 'left': bool(left)})
        node = node['left'] if left else node['right']
    return {'path': path, 'leaf': node['id'], 'action': POOL[node['action']],
            'fit_parent_count': node['parent_count']}


def support_inventory(data):
    records = read(OLD / 'data_manifest.json')
    rows, intervals = [], []
    for record in records:
        lo, hi = record['split_bounds']['train']
        ends = list(range(lo + 512, hi - 192 + 1, 704))
        seen = {m['raw_start'] for m in data.meta.values()
                if m['source'] == record['source'] and m['split'] == 'train'}
        roles = {role: len({m['parent_group'] for m in data.meta.values()
                           if m['source'] == record['source'] and m['v431_role'] == role})
                 for role in ('T_fit', 'T_gate', 'T_check', 'T_acq', 'dev')}
        rows.append({'source': record['source'], 'train_bounds': [lo, hi],
                     'existing_train_parents': len(seen), 'max_nonoverlapping_704_parents': len(ends),
                     'maximum_64_removed': max(0, len(ends) - 64),
                     'unused_legal_independent_parents': sum(e - 512 not in seen for e in ends),
                     'roles': roles})
        intervals.extend({'source': record['source'], 'raw_start': e - 512, 'context_end': e,
                          'full_read_stop': e + 192, 'already_cached_bolt': e - 512 in seen}
                         for e in ends)
    timesfm_request = read(RUN / 'timesfm' / 'request.json')
    timesfm_uids = {r['episode_uid'] for r in timesfm_request['rows']}
    tf_roles = {role: len({data.meta[u]['parent_group'] for u in timesfm_uids
                          if data.meta[u]['v431_role'] == role})
                for role in ('T_fit', 'T_gate', 'T_check', 'T_acq', 'dev')}
    candidates = []
    for record in read(Path('results/v43/20260914T125500.992800Z-pilot/data_manifest.json')):
        if record['source'] in {r['source'] for r in records}:
            continue
        lo, hi = record['split_bounds']['train']
        candidates.append({'source': record['source'], 'nominal_train_parents_704': (hi - lo) // 704,
                           'status': 'metadata_known_not_in_current_three_source_protocol',
                           'constraint': ('synchronize_with_ETTm1_before_independent_count' if record['source'] == 'ETTh1'
                                          else 'synchronize_with_ETTm2_if_both_added' if record['source'] == 'ETTh2'
                                          else 'dev_has_no_complete_704_parent' if record['source'] == 'Crypto'
                                          else 'new_source_requires_prefreeze_protocol_and_baseline_expansion')})
    with Path('data/ETT-small_ETTm2.csv').open() as f:
        reader = csv.reader(f);header = next(reader);dates = [r[0] for r in reader]
    candidates.append({'source': 'ETTm2', 'raw_rows': len(dates), 'channels': len(header) - 1,
                       'nominal_train_parents_704': int(.6 * len(dates)) // 704,
                       'status': 'not_in_current_inventory_adapter',
                       'constraint': 'original timestamp grid and synchronization with ETTh2 must be audited; not additive to ETTh2'})
    with gzip.open('data/exchange.txt.gz', 'rb') as f:
        widths = [line.count(b',') + 1 for line in f]
    candidates.append({'source': 'Exchange', 'raw_rows': len(widths), 'channel_widths': sorted(set(widths)),
                       'nominal_train_parents_704': int(.6 * len(widths)) // 704,
                       'status': 'not_in_current_inventory_adapter',
                       'constraint': 'missing original time/provenance contract; requires preregistration, not ready independent support'})
    inventory = {'geometry': {'context': 512, 'max_horizon': 192, 'stride': 704, 'target_channel': 0},
                 'sources': rows, 'current_protocol_maximum': sum(r['max_nonoverlapping_704_parents'] for r in rows),
                 'current_protocol_unused': sum(r['unused_legal_independent_parents'] for r in rows),
                 'timesfm_actual_forecast_parent_roles': tf_roles,
                 'timesfm_has_train_task_labels': False, 'timesfm_has_train_evidence': False,
                 'second_family_missing_train_parent_count': 110,
                 'additional_source_candidates': candidates,
                 'metadata_only_inventory': True, 'calibration_test_numeric_values_read': 0,
                 'not_valid_expansions': ['raising max_origins=64 on current three sources',
                                          'more seeds/horizons/target siblings counted as independent parents',
                                          'overlapping contexts counted as new independent support'],
                 'available_without_new_sources': 'predeclared nested purged parent cross-fitting over the existing 110 train parents; refit all dependent policies outside each outer holdout'}
    write('support_inventory.json', inventory)
    write('legal_train_interval_candidates.json', intervals)
    return inventory


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    status = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
              'calibration_test_values_read': 0, 'scope': 'posthoc_development_audit_not_new_method_result',
              'output': str(OUT)}
    try:
        data = SprintData()
        support = support_inventory(data)
        frozen, manifest = read(RUN / 'models_frozen.json'), read(RUN / 'terminal_manifest.json')
        assert sha(RUN / 'models.joblib') == frozen['sha256']
        models = joblib.load(RUN / 'models.joblib')
        decisions = read(RUN / 'accounted_decisions.json')
        records = {(r['policy'], r['episode_uid']): r for r in decisions}
        labels = read(RUN / 'value_labels.json')
        raw_points, raw_count = {}, 0
        for path in sorted(OLD.glob('final-*.request.json')):
            shard = path.name.removesuffix('.request.json')
            request, response = read(path), read(OLD / (shard + '.response.json'))
            with np.load(OLD / (shard + '.predictions.npz'), allow_pickle=False) as points, \
                 np.load(OLD / (shard + '.predictions.raw.npz'), allow_pickle=False) as raw:
                predictions = [points[f'row_{i}'] for i in range(len(request['rows']))]
                verify_response(request, response, predictions)
                for i, (q, r, p) in enumerate(zip(request['rows'], response['rows'], predictions)):
                    quantiles = raw[f'row_{i}']
                    assert array_hash(quantiles) == r['raw_hash']
                    np.testing.assert_array_equal(p, quantiles[0, 4])
                    raw_points[q['episode_uid'], q['input_hash']] = p
                    raw_count += 1
        with np.load(OLD / 'forecasts.npz', allow_pickle=False) as predictions, \
             np.load(OLD / 'targets.npz', allow_pickle=False) as targets:
            task = {}
            for uid in data.uids:
                y, mask = targets[uid + '_values'], targets[uid + '_mask']
                np.testing.assert_array_equal(mask, np.isfinite(y))
                for arm in POOL:
                    p = predictions[uid + '_' + arm]
                    digest = array_hash(data.old.pools[uid][arm])
                    np.testing.assert_array_equal(p, raw_points[uid, digest])
                    mae = float(np.abs(p[mask] - y[mask]).mean())
                    task[uid, arm] = {'mae': mae, 'mase': mae / data.old.read('mase_scales')[data.meta[uid]['source']],
                                      'prediction_hash': array_hash(p), 'candidate_hash': digest}
        windows, train_diagnostics, replay = [], {}, {}
        dev = data.ids('dev')
        for name in manifest['selected']:
            model, aq = models['terminal'][name], models['acquirers'][name]
            assert model.frozen_hash == aq.terminal_hash == manifest['terminal_hashes'][name]
            condition = next(r['evidence'] for r in manifest['configs'] if r['name'] == name)
            E = data.evidence(condition)
            gain_rows = labels[name]
            tool_labels = {}
            for tool in ('strict_mask', 'history'):
                items = [r for r in gain_rows if r['tool'] == tool]
                w = np.array([r['weight'] for r in items]);g = np.array([r['task_gain'] for r in items])
                v = np.array([r['value'] for r in items])
                for item in items:
                    assert item['terminal_hash'] == model.frozen_hash and item['role'] == 'T_acq'
                    np.testing.assert_allclose(item['value'], item['task_gain'] - item['lambda'] * item['delta_cost'])
                tree = aq.models[tool]
                tool_labels[tool] = {'rows': len(items), 'parents': len({r['parent'] for r in items}),
                                     'positive': int((g > 1e-12).sum()), 'zero': int((abs(g) <= 1e-12).sum()),
                                     'negative': int((g < -1e-12).sum()), 'weighted_gain': float(w @ g / w.sum()),
                                     'weighted_net_value': float(w @ v / w.sum()),
                                     'actual_tree_root_is_leaf': tree.root_.feature is None,
                                     'actual_constant_value': tree.root_.value, 'lambda': aq.lambda_value}
                np.testing.assert_allclose(tree.root_.value, w @ v / w.sum(), atol=1e-12)
            train_diagnostics[name] = {'tools': tool_labels, 'price_cv': aq.report['cv_summary'],
                                      'retained_refinements': model.refinements_, 'gate_audit': model.audit_}
            fetched = 0
            def forbidden_fetch(tool):
                nonlocal fetched
                fetched += 1
                raise AssertionError('STOP replay exposed unacquired evidence')
            stale_rejected = False
            try:
                aq.predict(data.X[dev[0]], 'history', '0' * 64)
            except ValueError:
                stale_rejected = True
            assert stale_rejected
            for bname in ('low', 'high'):
                for i in dev:
                    uid, x = data.uids[i], data.X[i]
                    row = records[f'AGENT_{name}_{bname}', uid]
                    before = int(model.base_tree.predict(x[None])[0])
                    empty = int(model.predict(x[None], np.full((1, 30), np.nan))[0])
                    assert before == empty and row['arm'] == POOL[before]
                    estimates = {t: CostInvoice((Charge('estimate:' + t, c),))
                                 for t, c in row['estimated_branch_costs'].items()}
                    invoice = CostInvoice(tuple(Charge(**r) for r in row['invoice']['charges']))
                    options = dict(terminal_hash=model.frozen_hash, visible_features=x,
                                   stop_arm=POOL[before], stop_invoice=invoice, branch_estimates=estimates,
                                   budget=row['budget'], applicable={'history': data.old.episodes[uid].horizon < len(data.old.episodes[uid].target),
                                                                    'strict_mask': len(mask_views(data.old.episodes[uid])[0]) == 3},
                                   model=aq, fetch=forbidden_fetch)
                    forced = execute_one_step(**options, mode='stop')
                    actual = execute_one_step(**options, mode='learned')
                    assert forced['arm'] == actual['arm'] == row['arm']
                    assert actual['history'] == row['history'] == [] and row['evidence_hash'] is None
                    assert actual['predicted_values'] == row['predicted_values']
                    assert not any(c['key'].startswith('tool:') for c in row['invoice']['charges'])
                    assert len({c['key'] for c in row['invoice']['charges']}) == len(row['invoice']['charges'])
                    cart, median, ok, _ = models['cart'][condition]
                    z = np.r_[x, E[i]];zz = np.r_[np.where(np.isfinite(z), z, median), np.isfinite(z)]
                    assert ok
                    cart_action = int(cart.predict(zz[None])[0])
                    assert records['CART_' + condition, uid]['arm'] == POOL[cart_action]
                    arms = {'agent': row['arm'], 'forced_stop': forced['arm'], 'fixed_A2': 'A2_SINGLE',
                            'CART': POOL[cart_action], 'full_evidence_terminal': POOL[int(model.predict(x[None], E[i:i+1])[0])]}
                    values = {key: {'arm': arm, **task[uid, arm]} for key, arm in arms.items()}
                    np.testing.assert_allclose(values['agent']['mase'], row['mase'], atol=1e-12)
                    values['agent']['invoice'] = row['invoice']
                    values['agent']['status'] = row['status']
                    values['agent']['predicted_values'] = row['predicted_values']
                    windows.append({'episode_uid': uid, 'terminal': name, 'budget_name': bname,
                                    **{k: data.meta[uid][k] for k in ('source', 'parent_group', 'horizon', 'condition')},
                                    'features': {n: finite_or_none(v) for n, v in zip(FEATURE_NAMES, x)},
                                    'base_path': path_for(model.base_tree, x), 'policies': values,
                                    'stop_reason': 'no_strictly_positive_predicted_net_value',
                                    'excluded': row['excluded'], 'tool_fetch_calls': 0,
                                    'agent_minus_A2_mase': values['agent']['mase'] - values['fixed_A2']['mase'],
                                    'agent_minus_CART_mase': values['agent']['mase'] - values['CART']['mase']})
            replay[name] = {'unacquired_evidence_fetch_calls': fetched, 'stale_hash_rejected': stale_rejected,
                            'forced_stop_matches_agent_all_rows': True, 'policy_runtime_subtracts_price_again': False,
                            'selected_lambda': aq.lambda_value, 'double_cost_penalty_explains_STOP': False}
        summary = []
        focus = [r for r in windows if r['terminal'] == 'd2_target_horizon_gated' and r['budget_name'] == 'high']
        for source in ('ALL', *sorted({r['source'] for r in focus})):
            items = focus if source == 'ALL' else [r for r in focus if r['source'] == source]
            summary.append({'source': source, 'episodes': len(items), 'parents': len({r['parent_group'] for r in items}),
                            'agent_vs_A2_action_changes': sum(r['policies']['agent']['arm'] != r['policies']['fixed_A2']['arm'] for r in items),
                            'agent_vs_A2_candidate_changes': sum(r['policies']['agent']['candidate_hash'] != r['policies']['fixed_A2']['candidate_hash'] for r in items),
                            'agent_vs_A2_prediction_changes': sum(r['policies']['agent']['prediction_hash'] != r['policies']['fixed_A2']['prediction_hash'] for r in items),
                            'better': sum(r['agent_minus_A2_mase'] < -1e-12 for r in items),
                            'same': sum(abs(r['agent_minus_A2_mase']) <= 1e-12 for r in items),
                            'worse': sum(r['agent_minus_A2_mase'] > 1e-12 for r in items),
                            'mean_agent_minus_A2_mase': macro(items, 'agent_minus_A2_mase'),
                            'mean_agent_minus_CART_mase': macro(items, 'agent_minus_CART_mase')})
        role_table = []
        for role in ('T_fit', 'T_gate', 'T_check', 'T_acq', 'dev'):
            ids = data.ids(role);w = data.weights(ids)
            for policy, actions in [('FIXED_A2', np.repeat(2, len(ids))),
                                    ('DIRTY_D1', models['base'][1].predict(data.X[ids])),
                                    ('DIRTY_D2', models['base'][2].predict(data.X[ids]))]:
                role_table.append({'role': role, 'policy': policy,
                                   'mase': float(w @ np.array([task[data.uids[i], POOL[a]]['mase'] for i, a in zip(ids, actions)])),
                                   'parents': len(set(data.parents[ids]))})
        write('stop_window_audit.json', windows)
        write('stop_comparison.json', summary)
        write('acquisition_training_audit.json', train_diagnostics)
        write('forced_stop_and_contracts.json', replay)
        write('base_policy_role_losses.json', role_table)
        source_files = ['src/introact_ts/v43/agent_inputs.py', 'src/introact_ts/v431/data.py',
                        'src/introact_ts/v431/decision_tree.py', 'src/introact_ts/v431/terminal.py',
                        'src/introact_ts/v431/acquisition.py', 'scripts/v431_fit_evaluate.py',
                        'scripts/v431_baselines/worker.py', __file__]
        write('source_identity.json', {p: sha(p) for p in source_files})
        status.update(status='completed', raw_current_outputs_verified=raw_count,
                      current_task_labels_independently_recomputed=len(task), audited_agent_rows=len(windows),
                      dev_common_episodes=156, support_maximum=support['current_protocol_maximum'],
                      actual_unused_independent_train_parents=support['current_protocol_unused'],
                      counterfactual_evaluator_reads='archived train/dev only; no raw calibration/test numeric decoder invoked',
                      method_promotion=False)
    except Exception as exc:
        status.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        status['runtime_seconds'] = time.perf_counter() - started
        write('status.json', status)
        print(json.dumps(status), flush=True)


if __name__ == '__main__':
    main()
