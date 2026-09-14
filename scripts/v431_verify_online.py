#!/usr/bin/env python3
"""Independent post-execution audit of seven real v4.3.1 online requests."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import joblib
import numpy as np

from introact_ts.v43.agent_inputs import POOL, mask_views
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import Candidate, Episode, array_hash, verify_impute
from introact_ts.v43.worker_protocol import validate_request, verify_response
from introact_ts.v431.acquisition import AcquiredBranch, Charge, CostInvoice, execute_one_step
from introact_ts.v431.data import PERIODS, dirty_features


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def read(path):
    return json.loads(Path(path).read_text())


def near(actual, expected, label):
    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-10, err_msg=label)


def invoice(record):
    charges = record['charges']
    check(len({r['key'] for r in charges}) == len(charges), 'Duplicate charge was billed twice')
    result = CostInvoice(tuple(Charge(**row) for row in charges))
    near(result.total_seconds, record['total_seconds'], 'Invoice arithmetic')
    return result


def audit(out, old):
    root = out.parent
    protocol, status = read(out / 'protocol.json'), read(out / 'status.json')
    barrier, accounting = read(out / 'label_access_barrier.json'), read(out / 'process_accounting.json')
    check(status['status'] == accounting['status'] == 'completed' and accounting['exit_code'] == 0,
          'Online process did not finish successfully')
    check(barrier['open'] and barrier['denied_preflight'] == 9 and barrier['denied_unexpected'] == 0,
          'Nine archive barriers were not demonstrated')
    check(barrier == status['label_access_barrier'], 'Conflicting barrier records')
    check(file_hash(out / 'forecasts.npz') == barrier['final_forecasts_sha256'], 'Final forecast file changed')
    release = datetime.fromisoformat(barrier['released_at']).timestamp()
    check((out / 'forecasts.npz').stat().st_mtime <= release,
          'Evaluator barrier opened before final forecast file was written')
    check((out / 'selected_candidates.npz').stat().st_mtime <= release,
          'Selected candidate archive was not complete before evaluator release')
    check(file_hash('scripts/v431_online.py') == protocol['online_script_sha256'], 'Executed online source changed')
    check(protocol['current_task_labels_read_before_forecasts'] == 0 and status['heldout_labels_read'] == 0,
          'Online label permissions changed')
    manifest, frozen = read(root / 'terminal_manifest.json'), read(root / 'models_frozen.json')
    check(file_hash(root / 'models.joblib') == frozen['sha256'] == protocol['models_sha256'],
          'Frozen checkpoint changed after online replay')
    models = joblib.load(root / 'models.joblib')
    name = manifest['selected'][0]
    check(name == protocol['selected_config'], 'Online selected configuration differs from frozen selection')
    terminal, acquirer = models['terminal'][name], models['acquirers'][name]
    check(terminal.frozen_hash == protocol['terminal_hash'] == acquirer.terminal_hash == manifest['terminal_hashes'][name],
          'Terminal/acquirer cache identity mismatch')
    check(protocol['max_tool_steps'] == 1, 'Unexpected acquisition depth')
    config = next(row for row in manifest['configs'] if row['name'] == name)
    check(config['evidence'] == protocol['history_condition'], 'Evidence condition changed')
    meta, partition = read(old / 'episode_manifest.json'), read(root / 'partition.json')
    chosen = []
    for source in sorted({m['source'] for m in partition.values()}):
        ids = [uid for uid, m in partition.items() if m['v431_role'] == 'dev' and m['source'] == source
               and m['horizon'] == 96 and m['condition'] == 'target_block_10']
        chosen.extend(sorted(ids, key=lambda uid: partition[uid]['raw_start'])[:3])
    rows = read(out / 'decisions.json')
    check(chosen == protocol['uids'] == [row['episode_uid'] for row in rows] and len(chosen) == 7,
          'Pre-registered seven-case denominator changed')
    episodes = {}
    with np.load(old / 'contexts.npz', allow_pickle=False) as contexts:
        for uid in chosen:
            m = meta[uid]
            check(m['split'] == 'dev', 'Online case outside dev')
            episodes[uid] = Episode(uid, m['source'], m['source'], m['parent_group'], m['split'], 0,
                  m['raw_start'], m['context_end'], m['horizon'], contexts[uid + '_timestamps'],
                  contexts[uid + '_target'], contexts[uid + '_covariates'], contexts[uid + '_availability'])
            check(array_hash(episodes[uid].target) == m['target_hash'], 'Context hash changed')
    offline = {row['episode_uid']: row for row in read(root / 'decisions.json')
               if row['policy'] == 'AGENT_' + name + '_high'}
    check(set(chosen) <= set(offline), 'Missing common offline policy decisions')
    final_raw = {}
    model_manifest, code_manifest = read(out / 'model_manifest.json'), read(out / 'code_manifest.json')
    allowed = {row['model']: row for row in read(out / 'allowed_services.json')}
    worker_rows, requests, raw_hashes = 0, [], {}
    for request_path in sorted(out.glob('case*.request.json')):
        stem = request_path.name.removesuffix('.request.json')
        request, response = read(request_path), read(out / (stem + '.response.json'))
        validate_request(request)
        record = model_manifest['models'][request['model_key']]
        check(request['model_revision'] == record['revision'] and
              request['environment_hash'] == record['environment_lock_sha256'], 'Model/environment identity changed')
        check(request['code_hash'] == code_manifest['hash'], 'Worker code identity changed')
        check(response['worker_pid'] == allowed[request['model_key']]['pid'], 'Unexpected model service PID')
        check(response['service_sha256'] == file_hash('scripts/serve_v43_model.py'), 'Model service source changed')
        check(response['status'] == 'completed', 'Incomplete model request')
        raw_path = Path(response['raw_predictions']['path'])
        check(raw_path.parent == out and file_hash(raw_path) == response['raw_predictions']['sha256'],
              'Raw quantile archive identity changed')
        check(request_path.stat().st_mtime <= release and raw_path.stat().st_mtime <= release,
              'Online raw computation appeared after evaluator release')
        raw_hashes[raw_path.name] = file_hash(raw_path)
        with np.load(out / (stem + '.predictions.npz'), allow_pickle=False) as points, \
             np.load(raw_path, allow_pickle=False) as quantiles:
            expected_keys = {f'row_{i}' for i in range(len(request['rows']))}
            check(set(points.files) == set(quantiles.files) == expected_keys, 'Missing or extra model output')
            predictions = [points[f'row_{i}'] for i in range(len(request['rows']))]
            verify_response(request, response, predictions)
            for i, (requested, returned, point) in enumerate(zip(request['rows'], response['rows'], predictions)):
                raw = quantiles[f'row_{i}']
                check(np.isfinite(raw).all() and array_hash(raw) == returned['raw_hash'], 'Raw quantile failure/hash mismatch')
                check(list(raw.shape) == returned['raw_shape'], 'Raw quantile shape changed')
                with np.load(requested['array_path'], allow_pickle=False) as payload:
                    for field, digest in (('target', 'input_hash'), ('raw_mask', 'raw_mask_hash'),
                                          ('covariates', 'covariate_hash'), ('timestamps', 'timestamps_hash'),
                                          ('availability', 'availability_hash')):
                        check(array_hash(payload[field]) == requested[digest], 'Worker input hash changed: ' + field)
                    check(len(payload['target']) == len(payload['timestamps']), 'Raw time axis changed')
                    visible = np.column_stack((payload['target'], payload['covariates']))
                    check(not np.any(np.isfinite(visible) & (payload['availability'] > payload['timestamps'][-1])),
                          'Historical/current payload exposed a value before publication')
                    if request['task'] == 'forecast':
                        np.testing.assert_array_equal(point, raw[0, 4])
                        if stem.endswith('-final-forecast'):
                            uid = requested['episode_uid']
                            check(uid not in final_raw, 'Duplicate final online forecast')
                            final_raw[uid] = (requested['candidate_id'], payload['target'].copy(), point.copy())
                    else:
                        x = payload['target']
                        observed = np.isfinite(x)
                        check(point[observed].tobytes() == x[observed].tobytes(), 'Imputation changed an observed value')
                        np.testing.assert_array_equal(point[~observed], raw[0, 0, ~observed, 1])
                worker_rows += 1
        requests.append(request)
    check(set(final_raw) == set(chosen), 'A final selected request was not backed by raw model output')
    for key in ('tsicl', 'bolt'):
        request, response = read(out / ('load-' + key + '.request.json')), read(out / ('load-' + key + '.response.json'))
        check(response['status'] == 'loaded' and response['worker_pid'] == allowed[key]['pid'], 'Model load identity failed')
        check(response['model_revision'] == request['model_revision'] == model_manifest['models'][key]['revision'],
              'Loaded checkpoint differs from inference checkpoint')
    budget = float(manifest['budgets']['high'])
    near(budget, protocol['budget'], 'Frozen budget')
    scales = read(old / 'mase_scales.json')
    tool_steps, online_replay_count = 0, 0
    with np.load(out / 'forecasts.npz', allow_pickle=False) as forecasts, \
         np.load(out / 'selected_candidates.npz', allow_pickle=False) as selected, \
         np.load(old / 'targets.npz', allow_pickle=False) as targets, \
         np.load(old / 'forecasts.npz', allow_pickle=False) as original_forecasts, \
         np.load(old / 'candidates.npz', allow_pickle=False) as original_candidates:
        check(set(forecasts.files) == set(selected.files) == set(chosen), 'Online output denominator differs')
        for row in rows:
            uid, arm = row['episode_uid'], row['arm']
            check(row['arm'] == offline[uid]['arm'] and row['history'] == offline[uid]['history'],
                  'Online/offline deployment decision differs')
            check(len(row['history']) <= 1 and set(row['history']) == set(row['acquired']), 'More than one actual acquired tool')
            e = episodes[uid]
            candidate = selected[uid]
            verify_impute(e, Candidate(uid, arm, candidate))
            check(array_hash(candidate) == row['candidate_hash'], 'Selected candidate hash changed')
            check(final_raw[uid][0] == arm, 'Raw final model call used a different governance action')
            np.testing.assert_array_equal(candidate, final_raw[uid][1])
            np.testing.assert_array_equal(forecasts[uid], final_raw[uid][2])
            np.testing.assert_allclose(candidate, original_candidates[uid + '_' + arm],
                                       rtol=1e-6, atol=1e-5, equal_nan=True)
            np.testing.assert_allclose(forecasts[uid], original_forecasts[uid + '_' + arm], rtol=1e-6, atol=1e-5)
            truth, mask = targets[uid + '_values'], targets[uid + '_mask']
            np.testing.assert_array_equal(mask, np.isfinite(truth))
            check(mask.any() and np.isfinite(forecasts[uid]).all(), 'Failure or missing scoring mask')
            mae = float(np.mean(abs(forecasts[uid][mask] - truth[mask])))
            near(mae, row['mae'], 'Online MAE')
            near(mae / scales[row['source']], row['mase'], 'Online MASE')
            x = dirty_features(e, PERIODS[e.source])
            check(array_hash(x) == row['dirty_feature_hash'], 'Pre-acquisition feature identity changed')
            empty = np.full((1, 30), np.nan)
            stop_arm = POOL[int(terminal.predict(x[None], empty)[0])]
            estimate = CostInvoice((Charge('stop', manifest['action_cost_estimates'][stop_arm]),))
            branch_estimates = {tool: CostInvoice((Charge('estimate', cost),))
                                for tool, cost in manifest['estimates'][name].items()}
            actual_invoice = invoice(row['invoice'])
            called = []

            def fetch(tool):
                called.append(tool)
                check(tool in row['acquired'], 'Replay requests evidence that was never acquired online')
                evidence = empty.copy()
                values = [np.nan if v is None else v for a in POOL for v in row['acquired'][tool]['evidence'][a]]
                evidence[0, :15] = values if tool == 'strict_mask' else evidence[0, :15]
                evidence[0, 15:] = values if tool == 'history' else evidence[0, 15:]
                action = POOL[int(terminal.predict(x[None], evidence)[0])]
                return AcquiredBranch(action, actual_invoice, array_hash(evidence.ravel()), terminal.frozen_hash)

            replay = execute_one_step(terminal_hash=terminal.frozen_hash, visible_features=x,
                stop_arm=stop_arm, stop_invoice=estimate, branch_estimates=branch_estimates, budget=budget,
                applicable={'strict_mask': len(mask_views(e)[0]) == 3, 'history': e.horizon < len(e.target)},
                model=acquirer, fetch=fetch)
            check(replay['arm'] == arm and replay['history'] == row['history'] == called,
                  'Frozen policy replay failed')
            check(replay['excluded'] == row['excluded'], 'Budget/applicability decision changed')
            check(set(replay['predicted_values']) == set(row['predicted_values']), 'Acquisition score support changed')
            for tool, value in replay['predicted_values'].items():
                near(value, row['predicted_values'][tool], 'Predicted acquisition net value')
            near(actual_invoice.total_seconds, row['hot_request_seconds'], 'Entire hot request invoice')
            check(row['budget_overrun'] == (row['hot_request_seconds'] > budget + 1e-12), 'Hot budget overrun hidden')
            check(row['complete_process_budget_overrun'] == (row['total_seconds'] > budget + 1e-12), 'Cold budget overrun hidden')
            near(row['total_seconds'], row['hot_request_seconds'] + row['allocated_model_startup_seconds']
                 + row['allocated_other_process_seconds'], 'Complete request cost')
            tool_steps += len(called)
            online_replay_count += 1
    startup = sum(r['wall_seconds'] for r in read(out / 'service_startup.json'))
    hot = sum(r['hot_request_seconds'] for r in rows)
    near(startup, accounting['model_startup_seconds'], 'Startup ledger')
    near(hot, accounting['hot_request_seconds'], 'Hot request ledger')
    near(sum(r['total_seconds'] for r in rows), accounting['process_wall_seconds'], 'Complete process total')
    near(accounting['process_wall_seconds'], hot + startup + accounting['remaining_process_overhead_seconds'],
         'Unallocated process overhead')
    for row in rows:
        near(row['allocated_model_startup_seconds'], startup / len(rows), 'Startup allocation')
        near(row['allocated_other_process_seconds'], accounting['remaining_process_overhead_seconds'] / len(rows),
             'Imports/shutdown allocation')
    check(sum(r['budget_overrun'] for r in rows) == status['hot_budget_overruns'], 'Hot overrun count changed')
    check(sum(r['complete_process_budget_overrun'] for r in rows) == accounting['complete_process_budget_overruns'],
          'Complete overrun count changed')
    check(status['worker_pid'] == accounting['worker_pid'] if 'worker_pid' in status
          else status['pid'] == accounting['worker_pid'], 'Process identity mismatch')
    return {'status': 'passed', 'episodes': len(rows), 'independent_parents': len({r['parent_group'] for r in rows}),
            'actual_model_rows_verified': worker_rows, 'model_requests': len(requests),
            'raw_quantile_sha256': raw_hashes, 'frozen_policy_replays': online_replay_count,
            'actual_online_tool_steps': tool_steps,
            'actual_online_tool_path_validated': tool_steps > 0,
            'path_limit': 'All seven actual requests STOP; online acquisition branch was not exercised'
                          if tool_steps == 0 else 'Only actually acquired tools are counted as online evidence',
            'barrier_files_denied': barrier['denied_preflight'], 'hot_seconds': hot,
            'whole_process_seconds': accounting['process_wall_seconds'],
            'hot_budget_overruns': status['hot_budget_overruns'],
            'complete_budget_overruns': accounting['complete_process_budget_overruns'],
            'models_sha256': frozen['sha256'], 'terminal_hash': terminal.frozen_hash,
            'heldout_labels_read': 0, 'existing_dev_targets_read_posthoc': len(rows),
            'method_promotion': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('online', type=Path)
    parser.add_argument('--old-run', type=Path, default=Path('results/v43/20260914T141030.324186Z-agent'))
    parser.add_argument('--output-name', default='independent_verification.json')
    args = parser.parse_args()
    out = args.online.resolve()
    check(Path(args.output_name).name == args.output_name, 'Invalid report name')
    destination = out / args.output_name
    check(not destination.exists(), 'Refuse to overwrite historical audit')
    started = time.perf_counter()
    report = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
              'verifier_sha256': file_hash(__file__)}
    try:
        report.update(audit(out, args.old_run.resolve()))
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['runtime_seconds'] = time.perf_counter() - started
        destination.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
