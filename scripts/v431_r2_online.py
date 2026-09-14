#!/usr/bin/env python3
"""Real r2 Bolt online decisions and separately labelled controlled branches."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def atom(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--family', choices=['bolt', 'timesfm'], default='bolt')
    parser.add_argument('--old-run', type=Path, default=Path('results/v43/20260914T141030.324186Z-agent'))
    parser.add_argument('--output-name')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.run, args.old_run = args.run.resolve(), args.old_run.resolve()
    args.output_name = args.output_name or 'online-' + args.family
    if Path(args.output_name).name != args.output_name or args.output_name in ('.', '..'):
        raise ValueError('Invalid output directory')
    out = args.run / args.output_name
    if args.worker:
        return worker(args, out)
    out.mkdir(exist_ok=False)
    started = time.perf_counter()
    command = [sys.executable, str(Path(__file__).resolve()), str(args.run), '--family', args.family,
               '--old-run', str(args.old_run), '--output-name', args.output_name, '--worker']
    atom(out / 'process_accounting.json', {'status': 'running', 'launcher_pid': os.getpid(),
         'started_at': datetime.now(timezone.utc).isoformat(), 'scope': 'complete validation worker spawn through exit'})
    with (out / 'worker.log').open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        atom(out / 'worker_identity.json', {'pid': process.pid, 'launcher_pid': os.getpid()})
        returncode = process.wait()
    elapsed = time.perf_counter() - started
    accounting = {'status': 'completed' if returncode == 0 else 'failed', 'exit_code': returncode,
                  'worker_pid': process.pid, 'process_wall_seconds': elapsed,
                  'scope': 'entire validation worker, including natural and controlled cases, startup and exit',
                  'finished_at': datetime.now(timezone.utc).isoformat()}
    if (out / 'decisions.json').exists():
        rows = json.loads((out / 'decisions.json').read_text())
        hot = sum(row['hot_request_seconds'] for row in rows)
        startup = json.loads((out / 'service_startup.json').read_text()) if (out / 'service_startup.json').exists() else []
        loads = sum(row['wall_seconds'] for row in startup)
        remaining = elapsed - hot - loads
        if remaining < -1e-6:
            raise RuntimeError('Online accounting has overlapping phases')
        accounting.update(requests=len(rows), hot_request_seconds=hot, model_startup_seconds=loads,
                          remaining_process_overhead_seconds=max(0., remaining))
        if rows:
            for row in rows:
                row['allocated_startup_seconds'] = loads / len(rows)
                row['allocated_process_overhead_seconds'] = max(0., remaining) / len(rows)
                row['total_seconds'] = row['hot_request_seconds'] + (elapsed - hot) / len(rows)
                row['complete_process_budget_overrun'] = row['total_seconds'] > row['budget'] + 1e-12
            natural = [row for row in rows if not row['controlled']]
            accounting.update(natural_requests=len(natural), controlled_requests=len(rows) - len(natural),
                natural_hot_seconds=sum(r['hot_request_seconds'] for r in natural),
                natural_actual_tool_calls=sum(r['actual_tool_calls'] for r in natural),
                controlled_actual_tool_calls=sum(r['actual_tool_calls'] for r in rows if r['controlled']),
                natural_complete_budget_overruns=sum(r['complete_process_budget_overrun'] for r in natural),
                controlled_complete_budget_overruns=sum(r['complete_process_budget_overrun'] for r in rows if r['controlled']),
                allocation_limit='Complete per-case allocation includes this controlled validation workload; not standalone natural-only cold latency')
            atom(out / 'decisions.json', rows)
    atom(out / 'process_accounting.json', accounting)
    print(json.dumps({'output': str(out), **accounting}), flush=True)
    if returncode:
        raise SystemExit(returncode)


def worker(args, out):
    from collections import defaultdict
    import joblib
    import numpy as np
    import yaml
    from online_v43_agent import Services
    if args.family == 'timesfm':
        from v431_r2_services import R2Services
        service_class = R2Services
    else:
        service_class = Services
    from introact_ts.v43.agent_collect import Collector
    from introact_ts.v43.agent_inputs import POOL, context_scale, history_views, mask_views
    from introact_ts.v43.candidates import prepare_model_input
    from introact_ts.v43.cli import atomic_json, code_manifest
    from introact_ts.v43.data_io import file_hash
    from introact_ts.v43.p2_candidates import ridge_candidate
    from introact_ts.v43.schemas import Candidate, Episode, array_hash, require, verify_impute
    from introact_ts.v431.data import PERIODS, aligned_views, dirty_features
    from introact_ts.v431_r2.policy import EvidenceState
    from introact_ts.v431_r2.acquisition import (
        AccountedToolError, AcquiredBranch, BRANCH_TOOLS, Charge, CostInvoice, execute_one_step)

    root, old = args.run, args.old_run
    read = lambda path: json.loads(Path(path).read_text())
    barrier = {'open': False, 'preflight': True, 'denied_preflight': 0, 'denied_unexpected': 0}
    explicit = {str((old / p).resolve()) for p in ('task_labels.json', 'targets.npz', 'evidence.json',
                 'forecasts.npz', 'candidates.npz', 'agent/decisions.json')}
    explicit.update(str((root / p).resolve()) for p in ('decisions.json', 'value_labels.json',
                      'evidence.json', 'labels.json', 'forecasts.npz', 'candidates.npz'))
    previous = Path('results/v431/20260914-sprint').resolve()
    explicit.update(str((previous / p).resolve()) for p in ('decisions.json', 'history/evidence.json',
                      'history/forecasts.npz', 'timesfm/predictions.npz', 'timesfm/scored_rows.json',
                      'history/candidate_hashes.json'))

    def sealed_path(filename):
        if filename in explicit:
            return True
        path = Path(filename)
        if path.is_relative_to(root) and not path.is_relative_to(out):
            lowered = path.name.lower()
            return any(word in lowered for word in ('evidence', 'labels', 'decisions', 'forecasts', 'candidates'))
        return False

    def audit_open(event, arguments):
        if event == 'open' and not barrier['open'] and isinstance(arguments[0], (str, bytes, os.PathLike)):
            if sealed_path(str(Path(os.fsdecode(arguments[0])).resolve())):
                key = 'denied_preflight' if barrier['preflight'] else 'denied_unexpected'
                barrier[key] += 1
                raise PermissionError('Current evidence/candidate/evaluator archive sealed until every final forecast')

    sys.addaudithook(audit_open)
    for path in sorted(explicit):
        try:
            with open(path, 'rb'):
                raise AssertionError('Sealed archive was opened')
        except PermissionError:
            pass
    barrier['preflight'] = False
    manifest, frozen = read(root / 'terminal_manifest.json'), read(root / 'models_frozen.json')
    require(file_hash(root / 'models.joblib') == frozen['sha256'], 'Frozen r2 model identity changed')
    models = joblib.load(root / 'models.joblib')
    policy, acquirer = models['policies'][args.family], models['acquirers'][args.family]
    setting = manifest['families'][args.family]
    require(policy.frozen_hash == setting['terminal_hash'] == acquirer.terminal_hash, 'Complete state policy hash changed')
    history_condition = setting.get('evidence_condition', manifest.get('evidence_condition'))
    require(history_condition in ('old32', 'same_origin32', 'target_horizon'), 'Explicit historical evidence condition required')
    high = float(manifest['budgets']['high'])
    require(np.isfinite(high) and high >= 0, 'Invalid inherited high budget')
    meta = read(old / 'episode_manifest.json')
    natural_ids = []
    for source in sorted({m['source'] for m in meta.values()}):
        ids = [u for u, m in meta.items() if m['role'] == 'dev' and m['source'] == source
               and m['horizon'] == 96 and m['condition'] == 'target_block_10']
        natural_ids.extend(sorted(ids, key=lambda u: meta[u]['raw_start'])[:3])
    require(len(natural_ids) == 7, 'Natural online protocol needs the original seven cases')
    raw_ids = sorted([u for u, m in meta.items() if m['role'] == 'dev' and m['horizon'] == 96
                      and m['condition'] == 'raw'], key=lambda u: (meta[u]['source'], meta[u]['raw_start']))
    episodes = {}
    with np.load(old / 'contexts.npz', allow_pickle=False) as archive:
        def load_episode(uid):
            if uid not in episodes:
                m = meta[uid]
                e = Episode(uid, m['source'], m['source'], m['parent_group'], m['split'], 0,
                    m['raw_start'], m['context_end'], m['horizon'], archive[uid + '_timestamps'],
                    archive[uid + '_target'], archive[uid + '_covariates'], archive[uid + '_availability'])
                require(array_hash(e.target) == m['target_hash'], 'Context input hash changed')
                episodes[uid] = e
            return episodes[uid]
        for uid in natural_ids:
            load_episode(uid)
        complete_id = next((uid for uid in raw_ids if np.isfinite(load_episode(uid).target).all()), None)
    require(complete_id is not None, 'No registered complete raw context is available')
    config = yaml.safe_load((old / 'resolved_config.yaml').read_text())
    code, model_manifest = code_manifest(), read(old / 'model_manifest.json')
    require(code['hash'] == read(old / 'code_manifest.json')['hash'], 'Frozen legacy worker source changed')
    atomic_json(out / 'model_manifest.json', model_manifest)
    atomic_json(out / 'code_manifest.json', code)
    natural_plan = [{'case_id': f'natural-{i}', 'episode_uid': uid, 'controlled': False,
                     'mode': 'learned', 'budget': high} for i, uid in enumerate(natural_ids)]
    control_plan = [
        {'case_id': 'complete-raw', 'episode_uid': complete_id, 'controlled': True, 'mode': 'learned',
         'budget': high, 'purpose': 'complete observation KEEP, no governance edit'},
        {'case_id': 'budget-zero', 'episode_uid': natural_ids[0], 'controlled': True, 'mode': 'learned',
         'budget': 0., 'purpose': 'reject unaffordable evidence; unavoidable final request spend remains an overrun'},
        {'case_id': 'tool-failure', 'episode_uid': natural_ids[0], 'controlled': True, 'mode': 'fixed',
         'branch': 'both', 'inject_failure': True,
         'budget': max(high, float(setting['branch_estimates']['both'])),
         'purpose': 'raise after real mask computation, before history; actual fixed fallback'},
    ]
    forced_plan = [{'case_id': 'forced-' + branch, 'episode_uid': natural_ids[0], 'controlled': True,
                    'mode': 'fixed', 'branch': branch,
                    'budget': max(high, float(setting['branch_estimates'][branch])),
                    'purpose': 'controlled tool wiring only; never counted as natural acquisition gain'}
                   for branch in ('mask', 'both')]
    protocol = {'family': args.family, 'terminal_hash': policy.frozen_hash, 'models_sha256': frozen['sha256'],
                'reference_arm': POOL[policy.reference_action], 'history_condition': history_condition,
                'natural_uids': natural_ids, 'natural_plan': natural_plan, 'controlled_plan': control_plan,
                'if_all_natural_STOP': forced_plan, 'natural_selection': 'original first up to three dev parents per source, H96 target-block',
                'script_sha256': file_hash(__file__), 'max_acquisition_steps': 1, 'both_is_two_tools': True,
                'new_heldout_reads': 0, 'label_barrier_paths': sorted(explicit),
                'controlled_trials_are_not_method_results': True,
                'controlled_branch_budget_rule': 'max(frozen high, frozen train branch estimate); never used for natural policy results',
                'collector_forecast_key_mapping': {'bolt': args.family},
                'worker_cost_scope': 'natural plus controlled validation workload, with full startup and exit'}
    atomic_json(out / 'protocol.json', protocol)
    status = {'status': 'running', 'phase': 'online', 'pid': os.getpid(), 'family': args.family,
              'started_at': datetime.now(timezone.utc).isoformat(), 'completed_cases': 0, 'heldout_labels_read': 0}
    atomic_json(out / 'status.json', status)
    collector = Collector(config, out, code, status, model_manifest)
    services = service_class.__new__(service_class)
    outputs, predictions, candidates = [], {}, {}

    def bill(key, seconds):
        return CostInvoice((Charge(key, float(seconds)),))

    def final(e, arm, prefix):
        started = time.perf_counter()
        state = {'status': 'completed'}
        if arm == 'A0_NATIVE':
            candidate = e.target
        elif arm == 'A0_FFILL':
            candidate = prepare_model_input(e.target, native_nan=False)
        elif arm in ('A2_SINGLE', 'A3_COV'):
            if np.isnan(e.target).any():
                values, _ = collector.model_call('tsicl', 'impute', 'none' if arm == 'A2_SINGLE' else 'past_only',
                                                [(e, arm, e.target)], prefix + '-impute')
                candidate = values[e.uid, arm]
            else:
                candidate, state = e.target, {'status': 'not_needed'}
        elif arm == 'A4_RIDGE_CONTEXT':
            result, state = ridge_candidate(e)
            candidate = result.target
        else:
            raise ValueError('Action outside frozen five-arm catalog')
        verify_impute(e, Candidate(e.uid, arm, candidate))
        governance_seconds = time.perf_counter() - started
        started = time.perf_counter()
        values, _ = collector.model_call('bolt', 'forecast', 'none', [(e, arm, candidate)], prefix + '-forecast')
        forecast_seconds = time.perf_counter() - started
        return candidate, values[e.uid, arm], governance_seconds, forecast_seconds, state

    def evidence_tool(e, tool, prefix):
        started = time.perf_counter()
        before_rows = len(collector.invoices)
        if tool == 'mask':
            planned, reason = mask_views(e)
            require(len(planned) == 3, 'Strict mask has insufficient visible support: ' + str(reason))
            views = [view for view, _ in planned]
            pools, _, _ = collector.pools(views, prefix + '-mask')
            values = defaultdict(list)
            for view, indices in planned:
                for arm in POOL:
                    x = pools[view.uid][arm][indices]
                    if np.isfinite(x).all():
                        values[arm].append(float(np.mean(abs(x - e.target[indices]))) / context_scale(e))
            evidence = {arm: ([float(np.mean(v)), float(np.std(v)), len(v) / 3]
                       if (v := values[arm]) else [None, None, 0.]) for arm in POOL}
            detail = {'blocks': [np.flatnonzero(indices).tolist() for _, indices in planned],
                      'input_lengths': [len(view.target) for view in views], 'cutoffs': [len(e.target)] * len(views)}
        elif tool == 'history':
            if history_condition == 'old32':
                plan = history_views(e)
                generated, predicted = [v for v, _ in plan], [v for v, _ in plan]
                cutoffs = [cutoff for _, cutoff in plan]
            else:
                full, short, cutoff = aligned_views(e)
                generated = [full]
                predicted = [short if history_condition == 'same_origin32' else full]
                cutoffs = [cutoff]
            pools, _, _ = collector.pools(generated, prefix + '-history')
            prediction_pools = {p.uid: pools[g.uid] for p, g in zip(predicted, generated)}
            forecasts, _ = collector.forecasts(predicted, prediction_pools, prefix + '-history')
            values, support = defaultdict(list), 0
            for view, cutoff in zip(predicted, cutoffs):
                truth = e.target[cutoff:cutoff + view.horizon]
                visible = np.isfinite(truth)
                support += int(visible.sum())
                if visible.any():
                    keep = float(np.mean(abs(forecasts[view.uid, 'A0_NATIVE'][visible] - truth[visible])))
                    for arm in POOL:
                        error = float(np.mean(abs(forecasts[view.uid, arm][visible] - truth[visible])))
                        values[arm].append((keep - error) / context_scale(e))
            denominator = sum(view.horizon for view in predicted)
            evidence = {arm: ([float(np.mean(v)), float(np.std(v)), support / denominator]
                       if (v := values[arm]) else [None, None, 0.]) for arm in POOL}
            detail = {'cutoffs': cutoffs, 'input_lengths': [len(view.target) for view in generated],
                      'forecast_horizons': [view.horizon for view in predicted], 'support': support}
        else:
            raise ValueError('Unknown actual tool')
        vector = np.asarray([np.nan if value is None else value for arm in POOL for value in evidence[arm]])
        return vector, {'tool': tool, 'status': 'completed', 'evidence': evidence,
                        'evidence_hash': array_hash(vector), 'actual_seconds': time.perf_counter() - started,
                        'real_model_rows': len(collector.invoices) - before_rows,
                        'context_only': True, 'clean_reads': 0, **detail}

    def one_case(case):
        case_id, uid = case['case_id'], case['episode_uid']
        e = episodes[uid]
        started = time.perf_counter()
        x = dirty_features(e, PERIODS[e.source])
        observed = bool(np.isfinite(e.target).all())
        before = policy.choose(x, EvidenceState(), fully_observed=observed)
        stop_arm = before['arm']
        initial_seconds = time.perf_counter() - started
        actual_records, final_record, state_record = [], {}, {}
        estimates = {branch: bill('estimated-complete-' + branch, value)
                     for branch, value in setting['branch_estimates'].items()}
        stop_estimate = bill('estimated-stop', setting['action_estimates'][stop_arm])
        mask_ok = len(mask_views(e)[0]) == 3
        applicable = {'mask': mask_ok, 'history': len(e.target) > e.horizon,
                      'both': mask_ok and len(e.target) > e.horizon}

        def generate_final(arm, suffix):
            c, p, governance, forecast, state = final(e, arm, case_id + suffix)
            candidates[case_id], predictions[case_id] = c, p
            final_record.update(arm=arm, governance_seconds=governance, forecast_seconds=forecast,
                                candidate_status=state, candidate_hash=array_hash(c))
            return bill('selected-governance', governance).merge(bill('selected-forecast', forecast))

        def fallback():
            actual = generate_final(stop_arm, '-fallback-final')
            return AcquiredBranch(stop_arm, actual, 'actual-fixed-reference-fallback', policy.frozen_hash)

        def fetch(branch):
            state = EvidenceState()
            spent = CostInvoice()
            for tool in BRANCH_TOOLS[branch]:
                step_started = time.perf_counter()
                try:
                    values, record = evidence_tool(e, tool, case_id)
                except Exception as exc:
                    failed = bill('failed-' + tool, time.perf_counter() - step_started)
                    actual_records.append({'tool': tool, 'status': 'failed', 'actual_seconds': failed.total_seconds,
                                           'error': f'{type(exc).__name__}:{exc}', 'evidence': None})
                    raise AccountedToolError(f'{tool}:{type(exc).__name__}:{exc}', spent.merge(failed),
                                             attempted_tools=tuple(r['tool'] for r in actual_records)) from exc
                actual_records.append(record)
                state = state.acquire(tool, values)
                spent = spent.merge(bill('tool-' + tool, record['actual_seconds']))
                if case.get('inject_failure') and tool == 'mask':
                    raise AccountedToolError('controlled failure after real mask; history was not started', spent,
                                             attempted_tools=('mask',))
            choice = policy.choose(x, state, fully_observed=observed)
            state_record.update(choice)
            actual = spent.merge(generate_final(choice['arm'], '-selected-final'))
            vector = np.asarray([value for tool in state.tools for value in state.result(tool)[1]])
            return AcquiredBranch(choice['arm'], actual, array_hash(vector), policy.frozen_hash)

        result = execute_one_step(terminal_hash=policy.frozen_hash, visible_features=x, stop_arm=stop_arm,
            stop_invoice=stop_estimate, branch_estimates=estimates, budget=case['budget'], applicable=applicable,
            model=acquirer, fetch=fetch, fallback=fallback, fully_observed=observed, mode=case['mode'],
            tool_order=(case['branch'],) if case.get('branch') else None)
        if not final_record:
            generate_final(result['arm'], '-selected-final')
        hot = time.perf_counter() - started
        component = {'initial-dirty-selection': initial_seconds,
                     'selected-governance': final_record['governance_seconds'],
                     'selected-forecast': final_record['forecast_seconds']}
        for record in actual_records:
            component['tool-' + record['tool']] = record['actual_seconds']
        remaining = hot - sum(component.values())
        require(remaining >= -1e-6, 'Hot request accounting overlaps')
        component['selection-request-overhead'] = max(0., remaining)
        invoice = CostInvoice(tuple(Charge(key, value) for key, value in component.items()))
        result.update(invoice=invoice.as_dict(), total_seconds=hot, hot_request_seconds=hot,
                      budget_overrun=hot > case['budget'] + 1e-12, delta_cost=None, stop_total_seconds=None,
                      stop_cost_estimate_seconds=stop_estimate.total_seconds,
                      counterfactual_stop_not_executed=True)
        if result['failure'] is None and result['budget_overrun']:
            result['status'] = 'budget_overrun'
        row = {**meta[uid], **case, **result, **final_record, 'family': args.family,
               'before_decision': before, 'after_decision': state_record,
               'fully_observed': observed, 'actual_tools': actual_records,
               'actual_tool_calls': len(actual_records),
               'completed_tool_calls': sum(r['status'] == 'completed' for r in actual_records),
               'natural_acquisition': not case['controlled'] and bool(actual_records),
               'dirty_feature_hash': array_hash(x)}
        if case.get('inject_failure'):
            row['controlled_failure_exercised'] = result['failure'] is not None and bool(actual_records)
        outputs.append(row)
        atomic_json(out / 'decisions.json', outputs)
        status['completed_cases'] = len(outputs)
        atomic_json(out / 'status.json', status)

    try:
        if args.family == 'timesfm':
            service_class.__init__(services, out, model_manifest, code, status, collector, family='timesfm')
        else:
            service_class.__init__(services, out, model_manifest, code, status, collector)
        collector.call = services.call
        services.load(episodes[natural_ids[0]])
        for case in natural_plan:
            one_case(case)
        natural_steps = sum(row['actual_tool_calls'] for row in outputs)
        for case in control_plan:
            one_case(case)
        if natural_steps == 0:
            for case in forced_plan:
                one_case(case)
        with (out / 'forecasts.npz').open('xb') as stream:
            np.savez(stream, **predictions)
        with (out / 'selected_candidates.npz').open('xb') as stream:
            np.savez(stream, **candidates)
        barrier.update(open=True, released_at=datetime.now(timezone.utc).isoformat(),
                       final_forecasts_sha256=file_hash(out / 'forecasts.npz'))
        atomic_json(out / 'label_access_barrier.json', barrier)
        scales = read(old / 'mase_scales.json')
        offline_name = setting.get('agent_policy', 'R2_AGENT_high')
        offline = [r for r in read(root / 'decisions.json')
                   if r.get('family', r.get('backbone')) == args.family and r['policy'] == offline_name]
        reference = {r['episode_uid']: r for r in offline}
        original_evidence = read(old / 'evidence.json')
        aligned = None if history_condition == 'old32' else read(previous / 'history/evidence.json')[history_condition]
        if args.family == 'timesfm':
            require(history_condition == 'target_horizon', 'TimesFM online comparison requires its frozen target-horizon evidence')
            histories = read(root / 'timesfm-cache/records.json')
            input_hashes = read(previous / 'history/candidate_hashes.json')
            views = read(previous / 'history/view_manifest.json')
            indexed = {(r['base_uid'], r['input_hash']): r for r in histories if r['phase'] == 'history'}
            aligned = {}
            with np.load(root / 'timesfm-cache/predictions.npz', allow_pickle=False) as reference_predictions:
                for uid in {r['episode_uid'] for r in outputs}:
                    e = episodes[uid]
                    cutoff = len(e.target) - e.horizon
                    truth = e.target[cutoff:cutoff + e.horizon]
                    mask = np.isfinite(truth)
                    forecast = {arm: reference_predictions[indexed[uid, input_hashes[views[uid]['full']][arm]]['key']]
                                for arm in POOL}
                    keep = float(np.mean(abs(forecast['A0_NATIVE'][mask] - truth[mask]))) if mask.any() else None
                    aligned[uid] = {arm: [(keep - float(np.mean(abs(forecast[arm][mask] - truth[mask])))) / context_scale(e)
                                         if mask.any() else None, 0. if mask.any() else None, float(mask.mean())]
                                    for arm in POOL}
        forecast_archive = old / 'forecasts.npz' if args.family == 'bolt' else previous / 'timesfm/predictions.npz'
        with np.load(old / 'targets.npz', allow_pickle=False) as targets, \
             np.load(old / 'candidates.npz', allow_pickle=False) as frozen_candidates, \
             np.load(forecast_archive, allow_pickle=False) as frozen_forecasts:
            for row in outputs:
                case_id, uid, arm = row['case_id'], row['episode_uid'], row['arm']
                truth, mask = targets[uid + '_values'], targets[uid + '_mask']
                require(np.array_equal(mask, np.isfinite(truth)), 'Common finite scoring mask changed')
                row['mae'] = float(np.mean(abs(predictions[case_id][mask] - truth[mask])))
                row['mase'] = row['mae'] / scales[row['source']]
                row['candidate_agreement'] = bool(np.allclose(candidates[case_id], frozen_candidates[uid + '_' + arm],
                                                    rtol=1e-6, atol=1e-5, equal_nan=True))
                row['forecast_agreement'] = bool(np.allclose(predictions[case_id], frozen_forecasts[uid + '_' + arm],
                                                   rtol=1e-6, atol=1e-5))
                row['evidence_agreement'] = {}
                for record in row['actual_tools']:
                    if record['status'] != 'completed':
                        continue
                    expected = original_evidence[uid]['strict_mask'] if record['tool'] == 'mask' else (
                        original_evidence[uid]['history_probe'] if history_condition == 'old32' else aligned[uid])
                    row['evidence_agreement'][record['tool']] = all(np.allclose(np.asarray(record['evidence'][a], float),
                        np.asarray(expected[a], float), rtol=1e-6, atol=1e-5, equal_nan=True) for a in POOL)
                if not row['controlled']:
                    row['offline_action_agreement'] = row['arm'] == reference[uid]['arm'] if uid in reference else None
                    expected_history = reference[uid].get('history') if uid in reference else None
                    row['offline_history_agreement'] = row['history'] == expected_history if expected_history is not None else None
        atomic_json(out / 'decisions.json', outputs)
        natural = [row for row in outputs if not row['controlled']]
        status.update(status='completed', cases=len(outputs), natural_cases=len(natural),
            natural_actual_tool_calls=sum(r['actual_tool_calls'] for r in natural),
            natural_action_agreements=sum(r.get('offline_action_agreement') is True for r in natural),
            natural_history_agreements=sum(r.get('offline_history_agreement') is True for r in natural),
            natural_hot_budget_overruns=sum(r['budget_overrun'] for r in natural),
            controlled_cases=len(outputs) - len(natural),
            controlled_failure_exercised=any(r.get('controlled_failure_exercised') for r in outputs),
            all_real_outputs_agree=all(r['candidate_agreement'] and r['forecast_agreement'] and
                                      all(r['evidence_agreement'].values()) for r in outputs),
            label_access_barrier=barrier, method_promotion=False)
    except Exception as exc:
        status.update(status='failed', error=f'{type(exc).__name__}:{exc}')
        raise
    finally:
        if hasattr(services, 'processes'):
            services.close()
        atomic_json(out / 'status.json', status)
        print(json.dumps(status), flush=True)


if __name__ == '__main__':
    main()
