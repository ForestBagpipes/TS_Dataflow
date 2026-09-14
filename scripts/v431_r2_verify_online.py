#!/usr/bin/env python3
"""Post-execution audit of actual r2 natural and controlled online branches."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import joblib
import numpy as np

from introact_ts.v43.agent_inputs import POOL, mask_views
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import Candidate, array_hash, verify_impute
from introact_ts.v43.worker_protocol import validate_request, verify_response
from introact_ts.v431_r2.data import R2Data
from introact_ts.v431_r2.policy import EvidenceState
from introact_ts.v431_r2.acquisition import (
    AccountedToolError, AcquiredBranch, BRANCH_TOOLS, Charge, CostInvoice, execute_one_step)


def check(value, message):
    if not value:
        raise AssertionError(message)


def read(path):
    return json.loads(Path(path).read_text())


def near(a, b, label):
    np.testing.assert_allclose(a, b, rtol=1e-10, atol=1e-10, err_msg=label)


def bill(record):
    check(len({q['key'] for q in record['charges']}) == len(record['charges']), 'Duplicate cost charge')
    result = CostInvoice(tuple(Charge(**row) for row in record['charges']))
    near(result.total_seconds, record['total_seconds'], 'Invoice arithmetic')
    return result


def audit(out):
    root = out.parent
    status, protocol = read(out / 'status.json'), read(out / 'protocol.json')
    check(status['status'] == 'completed', 'Online producer failed/incomplete')
    family = protocol['family']
    check(family in ('bolt', 'timesfm'), 'Unknown online target family')
    barrier, accounting = read(out / 'label_access_barrier.json'), read(out / 'process_accounting.json')
    check(accounting['status'] == 'completed' and accounting['exit_code'] == 0, 'Whole worker did not succeed')
    check(barrier['open'] and barrier['denied_preflight'] == len(protocol['label_barrier_paths'])
          and barrier['denied_unexpected'] == 0, 'Online archive barrier incomplete')
    check(barrier == status['label_access_barrier'], 'Conflicting barrier records')
    check(file_hash(out / 'forecasts.npz') == barrier['final_forecasts_sha256'], 'Forecast archive changed')
    released = datetime.fromisoformat(barrier['released_at']).timestamp()
    for filename in ('forecasts.npz', 'selected_candidates.npz'):
        check((out / filename).stat().st_mtime <= released, 'Evaluator opened before selected outputs were final')
    check(file_hash('scripts/v431_r2_online.py') == protocol['script_sha256'], 'Executed online source changed')
    frozen, manifest = read(root / 'models_frozen.json'), read(root / 'terminal_manifest.json')
    check(file_hash(root / 'models.joblib') == frozen['sha256'] == protocol['models_sha256'], 'Checkpoint changed')
    check(file_hash(root / 'terminal_manifest.json') == frozen['terminal_manifest_sha256'], 'Terminal manifest changed')
    models = joblib.load(root / 'models.joblib')
    policy, acquirer = models['policies'][family], models['acquirers'][family]
    setting = manifest['families'][family]
    check(policy.frozen_hash == acquirer.terminal_hash == protocol['terminal_hash'] == setting['terminal_hash'],
          'Complete evidence-state policy hash differs')
    check(protocol['collector_forecast_key_mapping'] == {'bolt': family}, 'Target routing is not explicit')
    if family == 'timesfm':
        routing = read(out / 'backbone_routing.json')
        check(routing['actual_target_backbone'] == routing['request_model_key'] == family,
              'Logical collector slot was silently interpreted as Bolt')
    rows = read(out / 'decisions.json')
    natural = [r for r in rows if not r['controlled']]
    check(len(natural) == 7 and [r['episode_uid'] for r in natural] == protocol['natural_uids'], 'Natural case set changed')
    check(len({r['case_id'] for r in rows}) == len(rows), 'Duplicate case identifier')
    data = R2Data(require_timesfm=family == 'timesfm')  # Explicit post-run evaluator only.
    ids = {uid: i for i, uid in enumerate(data.uids)}
    expected = []
    for source in sorted({m['source'] for m in data.meta.values()}):
        uids = [u for u, m in data.meta.items() if m['v431_role'] == 'dev' and m['source'] == source
                and m['horizon'] == 96 and m['condition'] == 'target_block_10']
        expected.extend(sorted(uids, key=lambda u: data.meta[u]['raw_start'])[:3])
    check(expected == protocol['natural_uids'], 'Natural origins were selected after seeing online outputs')
    offline = {r['episode_uid']: r for r in read(root / 'decisions.json')
               if r['family'] == family and r['policy'] == 'R2_AGENT_high'}
    model_manifest = read(out / 'model_manifest.json')
    code = read(out / 'code_manifest.json')
    allowed = {r['model']: r for r in read(out / 'allowed_services.json')}
    raw_rows, native_cache_hits, unique_native_files = 0, 0, set()
    finals, request_ids, raw_files = {}, set(), {}
    for path in sorted(out.glob('*.request.json')):
        stem = path.name.removesuffix('.request.json')
        request, response = read(path), read(out / (stem + '.response.json'))
        validate_request(request)
        check(request['request_id'] not in request_ids, 'Repeated service request identity')
        request_ids.add(request['request_id'])
        key = request['model_key']
        check(key == ('tsicl' if request['task'] == 'impute' else family), 'Actual forecast family differs from declared family')
        record = model_manifest['models'][key]
        check(request['model_revision'] == record['revision'] and request['environment_hash'] == record['environment_lock_sha256'],
              'Immutable model/environment changed')
        check(request['code_hash'] == code['hash'] and response['worker_pid'] == allowed[key]['pid'], 'Worker code/process identity differs')
        service = 'scripts/serve_v431_r2_timesfm.py' if key == 'timesfm' else 'scripts/serve_v43_model.py'
        check(response['service_sha256'] == file_hash(service), 'Resident service source changed')
        if stem.startswith('load-'):
            check(response['status'] == 'loaded', 'Model load failed')
            continue
        check(response['status'] == 'completed', 'Model request failed instead of returning actual outputs')
        raw_path = Path(response['raw_predictions']['path'])
        check(raw_path.parent == out and file_hash(raw_path) == response['raw_predictions']['sha256'], 'Raw quantile file changed')
        check(path.stat().st_mtime <= released and raw_path.stat().st_mtime <= released, 'Raw inference followed evaluator release')
        raw_files[raw_path.name] = file_hash(raw_path)
        with np.load(out / (stem + '.predictions.npz'), allow_pickle=False) as points, \
             np.load(raw_path, allow_pickle=False) as raw:
            expected_keys = {f'row_{i}' for i in range(len(request['rows']))}
            check(set(points.files) == set(raw.files) == expected_keys, 'Missing or extra model output')
            predictions = [points[f'row_{i}'] for i in range(len(request['rows']))]
            verify_response(request, response, predictions)
            for i, (asked, returned, point) in enumerate(zip(request['rows'], response['rows'], predictions)):
                quantile = raw[f'row_{i}']
                check(np.isfinite(quantile).all() and array_hash(quantile) == returned['raw_hash'], 'Raw quantile invalid/hash mismatch')
                check(list(quantile.shape) == returned['raw_shape'], 'Raw quantile shape changed')
                with np.load(asked['array_path'], allow_pickle=False) as inputs:
                    for name, digest in (('target', 'input_hash'), ('raw_mask', 'raw_mask_hash'),
                            ('covariates', 'covariate_hash'), ('timestamps', 'timestamps_hash'), ('availability', 'availability_hash')):
                        check(array_hash(inputs[name]) == asked[digest], 'Worker payload identity changed: ' + name)
                    combined = np.column_stack((inputs['target'], inputs['covariates']))
                    check(not np.any(np.isfinite(combined) & (inputs['availability'] > inputs['timestamps'][-1])),
                          'Payload exposed unpublished values')
                    if key == 'tsicl':
                        x = inputs['target']
                        observed = np.isfinite(x)
                        check(point[observed].tobytes() == x[observed].tobytes(), 'Imputation overwrote observed target')
                        np.testing.assert_array_equal(point[~observed], quantile[0, 0, ~observed, 1])
                    elif key == 'bolt':
                        np.testing.assert_array_equal(point, quantile[0, 4])
                    else:
                        native_path = Path(returned['raw_native_file'])
                        check(native_path.is_relative_to(out / 'timesfm-native'), 'TimesFM native result escapes run')
                        with np.load(native_path, allow_pickle=False) as native:
                            np.testing.assert_array_equal(native['input'], inputs['target'][None, :, None])
                            np.testing.assert_array_equal(native['quantiles'], quantile)
                            np.testing.assert_array_equal(native['point'][0].astype(point.dtype), point)
                        native_cache_hits += int(returned['cache_hit'])
                        unique_native_files.add(str(native_path))
                    for suffix in ('-selected-final-forecast', '-fallback-final-forecast'):
                        if stem.endswith(suffix):
                            case_id = stem.removesuffix(suffix)
                            check(case_id not in finals, 'Repeated final forecast for one case')
                            finals[case_id] = (asked['episode_uid'], asked['candidate_id'], inputs['target'].copy(), point.copy())
                    raw_rows += 1
    check(set(finals) == {row['case_id'] for row in rows}, 'Selected forecasts are not all backed by model raw output')
    replayed, natural_steps, controlled_steps = 0, 0, 0
    with np.load(out / 'forecasts.npz', allow_pickle=False) as forecasts, \
         np.load(out / 'selected_candidates.npz', allow_pickle=False) as candidates, \
         np.load(data.old.root / 'targets.npz', allow_pickle=False) as targets:
        check(set(forecasts.files) == set(candidates.files) == set(finals), 'Case denominator changed')
        for row in rows:
            case, uid, arm = row['case_id'], row['episode_uid'], row['arm']
            i, e = ids[uid], data.episodes[uid]
            check(row['family'] == family and row['split'] == 'dev', 'Case family/split changed')
            c, point = candidates[case], forecasts[case]
            verify_impute(e, Candidate(uid, arm, c))
            check(array_hash(c) == row['candidate_hash'], 'Selected governance hash changed')
            check(finals[case][:2] == (uid, arm), 'Raw selected action differs from trace')
            np.testing.assert_array_equal(c, finals[case][2])
            np.testing.assert_array_equal(point, finals[case][3])
            np.testing.assert_allclose(c, data.old.pools[uid][arm], rtol=1e-6, atol=1e-5, equal_nan=True)
            np.testing.assert_allclose(point, data.predictions[family][uid][arm], rtol=1e-6, atol=1e-5)
            y, mask = targets[uid + '_values'], targets[uid + '_mask']
            np.testing.assert_array_equal(mask, np.isfinite(y))
            mae = float(np.mean(abs(point[mask] - y[mask])))
            near(mae, row['mae'], 'Common-mask MAE')
            near(mae / data.scales[row['source']], row['mase'], 'Source MASE')
            x = data.X[i]
            check(array_hash(x) == row['dirty_feature_hash'], 'Dirty pre-acquisition feature changed')
            complete = bool(np.isfinite(e.target).all())
            before = policy.choose(x, EvidenceState(), fully_observed=complete)
            check(before == row['before_decision'], 'No-evidence state differs from frozen reference')
            for record in row['actual_tools']:
                check(record['actual_seconds'] >= 0, 'Invalid actual tool cost')
                if record['status'] != 'completed':
                    check(record.get('evidence') is None and record.get('error'), 'Failed tool got fabricated values')
                    continue
                vector = np.asarray([np.nan if v is None else v for a in POOL for v in record['evidence'][a]])
                check(array_hash(vector) == record['evidence_hash'], 'Acquired evidence hash changed')
                expected_e = data.mask[i] if record['tool'] == 'mask' else data.history[family][i]
                np.testing.assert_allclose(vector, expected_e, rtol=1e-6, atol=1e-5, equal_nan=True)
                check(record['real_model_rows'] > 0, 'Tool was declared real without model requests')
                if record['tool'] == 'history':
                    check(record['input_lengths'] == [512 - e.horizon] and record['cutoffs'] == [512 - e.horizon],
                          'Historical tool used the current full context')
            actual_invoice = bill(row['invoice'])
            estimates = {b: CostInvoice((Charge('estimate', v),)) for b, v in setting['branch_estimates'].items()}
            stop_invoice = CostInvoice((Charge('stop-estimate', setting['action_estimates'][before['arm']]),))
            callbacks = []

            def fetch(branch):
                callbacks.append(branch)
                if row['failure'] is not None:
                    failure = row['failure']
                    raise AccountedToolError(failure['message'], bill(failure['spent_invoice']),
                                             attempted_tools=failure['attempted_tools'] or ())
                state = EvidenceState()
                for tool in BRANCH_TOOLS[branch]:
                    records = [r for r in row['actual_tools'] if r['tool'] == tool and r['status'] == 'completed']
                    check(len(records) == 1, 'Replay requested unavailable evidence')
                    state = state.acquire(tool, [np.nan if v is None else v for a in POOL for v in records[0]['evidence'][a]])
                decision = policy.choose(x, state, fully_observed=complete)
                check(decision == row['after_decision'], 'Acquired state executed a different terminal CART')
                return AcquiredBranch(decision['arm'], actual_invoice, 'verified-acquired-state', policy.frozen_hash)

            def fallback():
                return AcquiredBranch(before['arm'], actual_invoice, 'verified-real-fallback', policy.frozen_hash)

            mask_ok = len(mask_views(e)[0]) == 3
            replay = execute_one_step(terminal_hash=policy.frozen_hash, visible_features=x, stop_arm=before['arm'],
                stop_invoice=stop_invoice, branch_estimates=estimates, budget=row['budget'],
                applicable={'mask': mask_ok, 'history': e.horizon < 512, 'both': mask_ok and e.horizon < 512},
                model=acquirer, fetch=fetch, fallback=fallback, fully_observed=complete, mode=row['mode'],
                tool_order=(row['branch'],) if row['mode'] == 'fixed' else None)
            check(replay['arm'] == arm and replay['branch'] == row['branch'] and replay['history'] == row['history'],
                  'Frozen policy/STOP/controlled replay changed')
            check(replay['excluded'] == row['excluded'], 'Eligibility or complete budget decision changed')
            check(set(replay['predicted_values']) == set(row['predicted_values']), 'Acquisition branch support changed')
            for branch, value in replay['predicted_values'].items():
                near(value, row['predicted_values'][branch], 'Acquisition predicted net value')
            if not row['controlled']:
                check(row['arm'] == offline[uid]['arm'] and row['history'] == offline[uid]['history'], 'Natural offline/online decision differs')
                near(row['budget'], manifest['budgets']['high'], 'Natural policy budget changed')
                natural_steps += len(row['actual_tools'])
            else:
                controlled_steps += len(row['actual_tools'])
            if row.get('inject_failure'):
                check(row['failure'] is not None and row['actual_tools'][0]['tool'] == 'mask'
                      and row['actual_tools'][0]['status'] == 'completed', 'Failure fixture did not first run real mask')
                check(arm == before['arm'], 'Failure did not return fixed reference')
            if complete:
                check(arm == 'A0_NATIVE' and not row['actual_tools'], 'Complete observations incurred unneeded governance')
            near(actual_invoice.total_seconds, row['hot_request_seconds'], 'Hot complete invoice')
            near(row['total_seconds'], row['hot_request_seconds'] + row['allocated_startup_seconds']
                 + row['allocated_process_overhead_seconds'], 'Complete cold allocation')
            check(row['budget_overrun'] == (row['hot_request_seconds'] > row['budget'] + 1e-12), 'Actual hot overrun hidden')
            check(row['complete_process_budget_overrun'] == (row['total_seconds'] > row['budget'] + 1e-12), 'Actual whole-process overrun hidden')
            replayed += 1
    hot = sum(r['hot_request_seconds'] for r in rows)
    startup = sum(r['wall_seconds'] for r in read(out / 'service_startup.json'))
    near(hot, accounting['hot_request_seconds'], 'Whole hot ledger')
    near(startup, accounting['model_startup_seconds'], 'Actual service startup ledger')
    near(sum(r['total_seconds'] for r in rows), accounting['process_wall_seconds'], 'Whole-process invoice sum')
    near(hot + startup + accounting['remaining_process_overhead_seconds'], accounting['process_wall_seconds'], 'Process phases')
    near(natural_steps, accounting['natural_actual_tool_calls'], 'Natural tools counted separately')
    near(controlled_steps, accounting['controlled_actual_tool_calls'], 'Controlled tools counted separately')
    check(all(r['mode'] == 'learned' for r in natural), 'Forced branches appeared in natural results')
    return {'status': 'passed', 'family': family, 'cases': len(rows), 'natural_cases': len(natural),
            'controlled_cases': len(rows) - len(natural), 'raw_model_response_rows': raw_rows,
            'timesfm_native_cache_hits': native_cache_hits, 'timesfm_unique_native_forecasts': len(unique_native_files),
            'raw_quantile_files': raw_files, 'frozen_policy_replays': replayed,
            'natural_actual_tool_calls': natural_steps, 'controlled_actual_tool_calls': controlled_steps,
            'natural_acquisition_exercised': natural_steps > 0,
            'failure_after_actual_tool_exercised': any(r.get('controlled_failure_exercised') for r in rows),
            'hot_seconds': hot, 'complete_validation_process_seconds': accounting['process_wall_seconds'],
            'natural_hot_budget_overruns': sum(r['budget_overrun'] for r in natural),
            'controlled_hot_budget_overruns': sum(r['budget_overrun'] for r in rows if r['controlled']),
            'budget_zero_limit': 'Final prediction at B=0 is recorded as an infeasible complete-budget branch, not hard-budget success',
            'heldout_labels_read': 0, 'evaluator_targets': 'existing dev only, post-execution', 'method_promotion': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('online', type=Path)
    parser.add_argument('--output-name', default='independent_verification.json')
    args = parser.parse_args()
    check(Path(args.output_name).name == args.output_name, 'Invalid report filename')
    out = args.online.resolve()
    destination = out / args.output_name
    check(not destination.exists(), 'Never overwrite previous audit evidence')
    started = time.perf_counter()
    report = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(), 'verifier_sha256': file_hash(__file__)}
    try:
        report.update(audit(out))
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}:{exc}')
        raise
    finally:
        report['runtime_seconds'] = time.perf_counter() - started
        destination.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
