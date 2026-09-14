#!/usr/bin/env python3
"""Run seven pre-registered, context-only online v4.3.1 requests.

The outer process measures the complete worker lifetime, including imports,
model service creation and shutdown. GPU launch belongs to the root queue.
"""
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
    parser.add_argument('--old-run', type=Path,
                        default=Path('results/v43/20260914T141030.324186Z-agent'))
    parser.add_argument('--output-name', default='online-7')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.run, args.old_run = args.run.resolve(), args.old_run.resolve()
    if '/' in args.output_name or args.output_name in ('.', '..'):
        raise ValueError('Invalid online output directory')
    out = args.run / args.output_name
    if args.worker:
        return worker(args, out)
    out.mkdir(exist_ok=False)
    started = time.perf_counter()
    command = [sys.executable, str(Path(__file__).resolve()), str(args.run),
               '--old-run', str(args.old_run), '--output-name', args.output_name, '--worker']
    atom(out / 'process_accounting.json', {'status': 'running', 'launcher_pid': os.getpid(),
         'started_at': datetime.now(timezone.utc).isoformat(), 'scope': 'worker spawn through exit'})
    with (out / 'worker.log').open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        atom(out / 'worker_identity.json', {'pid': process.pid, 'launcher_pid': os.getpid()})
        returncode = process.wait()
    elapsed = time.perf_counter() - started
    accounting = {'status': 'completed' if returncode == 0 else 'failed', 'exit_code': returncode,
                  'worker_pid': process.pid, 'process_wall_seconds': elapsed,
                  'scope': 'complete worker spawn through exit, including model services',
                  'finished_at': datetime.now(timezone.utc).isoformat()}
    if (out / 'decisions.json').exists():
        rows = json.loads((out / 'decisions.json').read_text())
        hot = sum(row['hot_request_seconds'] for row in rows)
        startup = json.loads((out / 'service_startup.json').read_text()) if (out / 'service_startup.json').exists() else []
        loads = sum(row['wall_seconds'] for row in startup)
        residual = elapsed - hot - loads
        if residual < -1e-6:
            raise RuntimeError('Online accounting overlaps measured phases')
        accounting.update(requests=len(rows), hot_request_seconds=hot,
                          model_startup_seconds=loads,
                          remaining_process_overhead_seconds=max(0., residual))
        if rows:
            for row in rows:
                row['allocated_model_startup_seconds'] = loads / len(rows)
                row['allocated_other_process_seconds'] = max(0., residual) / len(rows)
                row['total_seconds'] = row['hot_request_seconds'] + (elapsed - hot) / len(rows)
                row['complete_process_budget_overrun'] = row['total_seconds'] > row['budget'] + 1e-12
            atom(out / 'decisions.json', rows)
            accounting['complete_process_budget_overruns'] = sum(r['complete_process_budget_overrun'] for r in rows)
            accounting['mean_complete_request_seconds'] = elapsed / len(rows)
    atom(out / 'process_accounting.json', accounting)
    print(json.dumps({'output': str(out), **accounting}), flush=True)
    if returncode:
        raise SystemExit(returncode)


def worker(args, out):
    # Heavy imports intentionally live inside the timed child.
    from collections import defaultdict
    import joblib
    import numpy as np
    import yaml
    from online_v43_agent import Services
    from introact_ts.v43.agent_collect import Collector
    from introact_ts.v43.agent_inputs import POOL, context_scale, history_views, mask_views
    from introact_ts.v43.candidates import prepare_model_input
    from introact_ts.v43.cli import atomic_json, code_manifest
    from introact_ts.v43.data_io import file_hash
    from introact_ts.v43.p2_candidates import ridge_candidate
    from introact_ts.v43.schemas import Candidate, Episode, array_hash, require, verify_impute
    from introact_ts.v431.acquisition import AcquiredBranch, Charge, CostInvoice, execute_one_step
    from introact_ts.v431.data import PERIODS, aligned_views, dirty_features

    root, old = args.run, args.old_run
    barrier = {'open': False, 'preflight': True, 'denied_preflight': 0, 'denied_unexpected': 0}
    forbidden = {str((old / path).resolve()) for path in
                 ('task_labels.json', 'targets.npz', 'evidence.json', 'forecasts.npz',
                  'candidates.npz', 'agent/decisions.json')}
    forbidden.update(str((root / path).resolve()) for path in
                     ('decisions.json', 'history/evidence.json', 'history/forecasts.npz'))

    def audit_open(event, arguments):
        if event == 'open' and not barrier['open'] and isinstance(arguments[0], (str, bytes, os.PathLike)):
            filename = str(Path(os.fsdecode(arguments[0])).resolve())
            if filename in forbidden:
                key = 'denied_preflight' if barrier['preflight'] else 'denied_unexpected'
                barrier[key] += 1
                raise PermissionError('Current evaluator/candidate/evidence archive remains sealed')

    sys.addaudithook(audit_open)
    for filename in sorted(forbidden):
        try:
            with open(filename, 'rb'):
                raise AssertionError('A sealed archive was opened')
        except PermissionError:
            pass
    barrier['preflight'] = False
    read = lambda path: json.loads(Path(path).read_text())
    manifest = read(root / 'terminal_manifest.json')
    model_path = root / 'models.joblib'
    frozen_models = read(root / 'models_frozen.json')
    expected_hash = frozen_models['sha256']
    require(expected_hash is not None and file_hash(model_path) == expected_hash,
            'Frozen policy model file identity missing or changed')
    models = joblib.load(model_path)
    name = manifest['selected'][0]
    policy, acquirer = models['terminal'][name], models['acquirers'][name]
    require(acquirer.terminal_hash == policy.frozen_hash, 'Acquirer terminal policy hash changed')
    budget = float(manifest['budgets']['high'])
    require(np.isfinite(budget) and budget >= 0, 'Invalid frozen online budget')
    # Exact configuration names and evidence conditions were registered before dev.
    registration = read(Path(__file__).resolve().parents[1] / 'configs/v431/sprint_manifest.json')
    configs = {c['name']: c for c in manifest['configs']}
    registered = {c['name']: c for c in registration['terminal_configs']}
    require(name in configs, 'Unregistered terminal configuration')
    condition = configs[name]['evidence']
    require(name in registered and condition == registered[name]['evidence'], 'Frozen evidence differs from registration')
    require(condition in ('old32', 'same_origin32', 'target_horizon'), 'Unknown historical evidence condition')
    metadata = read(old / 'episode_manifest.json')
    partition = read(root / 'partition.json')
    chosen = []
    for source in sorted({m['source'] for m in partition.values()}):
        uids = [u for u, m in partition.items() if m['v431_role'] == 'dev'
                and m['source'] == source and m['horizon'] == 96 and m['condition'] == 'target_block_10']
        chosen.extend(sorted(uids, key=lambda u: partition[u]['raw_start'])[:3])
    require(len(chosen) == 7, 'Pre-registered online set must contain all seven cases')
    episodes = {}
    with np.load(old / 'contexts.npz', allow_pickle=False) as archive:
        for uid in chosen:
            m = metadata[uid]
            episodes[uid] = Episode(uid, m['source'], m['source'], m['parent_group'], m['split'], 0,
                  m['raw_start'], m['context_end'], m['horizon'], archive[uid + '_timestamps'],
                  archive[uid + '_target'], archive[uid + '_covariates'], archive[uid + '_availability'])
            require(array_hash(episodes[uid].target) == m['target_hash'], 'Dirty context identity changed')
    code, model_manifest = code_manifest(), read(old / 'model_manifest.json')
    require(code['hash'] == read(old / 'code_manifest.json')['hash'], 'v43 model worker source identity changed')
    config = yaml.safe_load((old / 'resolved_config.yaml').read_text())
    atomic_json(out / 'model_manifest.json', model_manifest)
    atomic_json(out / 'code_manifest.json', code)
    atomic_json(out / 'protocol.json', {
        'selected_config': name, 'terminal_hash': policy.frozen_hash, 'models_sha256': expected_hash,
        'history_condition': condition, 'budget': budget, 'max_tool_steps': 1, 'uids': chosen,
        'selection': 'first up to three dev parents per source, H96 target_block_10, fixed before new results',
        'candidate_generation': 'only selected current candidate; tools regenerate their own historical views',
        'tool_feature_layout': '15 strict_mask then 15 history; unavailable entries are NaN',
        'online_script_sha256': file_hash(Path(__file__)), 'current_task_labels_read_before_forecasts': 0,
        'cost_scope': 'actual hot branch wall, separate startup, and full worker lifetime overhead',
        'budget_scope': 'report hot branch and complete cold-process allocation separately'})
    status = {'status': 'running', 'phase': 'online', 'pid': os.getpid(), 'episodes_completed': 0,
              'started_at': datetime.now(timezone.utc).isoformat(), 'heldout_labels_read': 0}
    atomic_json(out / 'status.json', status)
    collector = Collector(config, out, code, status, model_manifest)
    services = Services.__new__(Services)
    outputs, predictions, selected_arrays = [], {}, {}

    def bill(key, seconds):
        return CostInvoice((Charge(key, float(seconds)),))

    def selected_final(e, arm, prefix):
        begun = time.perf_counter()
        candidate_status = {'status': 'completed'}
        if arm == 'A0_NATIVE':
            candidate = e.target
        elif arm == 'A0_FFILL':
            candidate = prepare_model_input(e.target, native_nan=False)
        elif arm in ('A2_SINGLE', 'A3_COV'):
            if np.isnan(e.target).any():
                values, _ = collector.model_call('tsicl', 'impute',
                    'none' if arm == 'A2_SINGLE' else 'past_only', [(e, arm, e.target)], prefix + '-impute')
                candidate = values[e.uid, arm]
            else:
                candidate = e.target
                candidate_status = {'status': 'not_needed'}
        elif arm == 'A4_RIDGE_CONTEXT':
            governed, candidate_status = ridge_candidate(e)
            candidate = governed.target
        else:
            raise ValueError('Selected action outside frozen pool')
        verify_impute(e, Candidate(e.uid, arm, candidate))
        governance = time.perf_counter() - begun
        forecast_started = time.perf_counter()
        values, _ = collector.model_call('bolt', 'forecast', 'none', [(e, arm, candidate)], prefix + '-forecast')
        forecast_seconds = time.perf_counter() - forecast_started
        return candidate, values[e.uid, arm], governance, forecast_seconds, candidate_status

    def acquire_evidence(e, tool, prefix):
        begun = time.perf_counter()
        if tool == 'strict_mask':
            planned, reason = mask_views(e)
            views = [v for v, _ in planned]
            pools, _, _ = collector.pools(views, prefix + '-mask') if views else ({}, {}, {})
            errors = defaultdict(list)
            for view, indices in planned:
                for arm in POOL:
                    values = pools[view.uid][arm][indices]
                    if np.isfinite(values).all():
                        errors[arm].append(float(np.mean(abs(values - e.target[indices]))) / context_scale(e))
            evidence = {a: ([float(np.mean(v)), float(np.std(v)), len(v) / 3]
                            if (v := errors[a]) else [None, None, 0.]) for a in POOL}
            detail = {'blocks': [np.flatnonzero(indices).tolist() for _, indices in planned],
                      'unsupported_reason': reason}
        elif tool == 'history':
            if condition == 'old32':
                planned = history_views(e)
                generated = [v for v, _ in planned]
                predicted = generated
                cutoffs = [r for _, r in planned]
            else:
                full, short, cutoff = aligned_views(e)
                generated = [full]
                predicted = [short if condition == 'same_origin32' else full]
                cutoffs = [cutoff]
            pools, _, _ = collector.pools(generated, prefix + '-history')
            forecast_pools = {p.uid: pools[g.uid] for p, g in zip(predicted, generated)}
            forecasts, _ = collector.forecasts(predicted, forecast_pools, prefix + '-history')
            errors, support = defaultdict(list), 0
            for view, cutoff in zip(predicted, cutoffs):
                truth = e.target[cutoff:cutoff + view.horizon]
                mask = np.isfinite(truth)
                support += int(mask.sum())
                if mask.any():
                    keep_mae = float(np.mean(abs(forecasts[view.uid, 'A0_NATIVE'][mask] - truth[mask])))
                    for arm in POOL:
                        mae = float(np.mean(abs(forecasts[view.uid, arm][mask] - truth[mask])))
                        errors[arm].append((keep_mae - mae) / context_scale(e))
            denominator = sum(v.horizon for v in predicted)
            evidence = {a: ([float(np.mean(v)), float(np.std(v)), support / denominator]
                            if (v := errors[a]) else [None, None, 0.]) for a in POOL}
            detail = {'cutoffs': cutoffs, 'forecast_horizons': [v.horizon for v in predicted],
                      'input_lengths': [len(v.target) for v in generated],
                      'context_only_target_support': support, 'historical_clean_reads': 0}
        else:
            raise ValueError('Unregistered evidence tool')
        return evidence, time.perf_counter() - begun, detail

    try:
        Services.__init__(services, out, model_manifest, code, status, collector)
        collector.call = services.call
        services.load(episodes[chosen[0]])
        for index, uid in enumerate(chosen):
            e = episodes[uid]
            started = time.perf_counter()
            x = dirty_features(e, PERIODS[e.source])
            empty = np.full(30, np.nan)
            stop_arm = POOL[int(policy.predict(x[None], empty[None])[0])]
            initial_seconds = time.perf_counter() - started
            acquired = {}
            final_details = {}
            stop_estimates = manifest.get('action_cost_estimates', manifest.get('stop_estimates', {}))
            stop_estimate = stop_estimates.get(stop_arm)
            planning_stop = bill('estimated-stop', stop_estimate) if stop_estimate is not None else CostInvoice()
            estimates = {tool: bill('estimated-complete-' + tool, seconds)
                         for tool, seconds in manifest['estimates'][name].items()}
            applicable = {'strict_mask': len(mask_views(e)[0]) == 3,
                          'history': e.horizon < len(e.target)}

            def fetch(tool):
                evidence, tool_seconds, detail = acquire_evidence(e, tool, f'case{index}')
                vector = empty.copy()
                values = [np.nan if value is None else value for arm in POOL for value in evidence[arm]]
                vector[:15] = values if tool == 'strict_mask' else vector[:15]
                vector[15:] = values if tool == 'history' else vector[15:]
                select_start = time.perf_counter()
                arm = POOL[int(policy.predict(x[None], vector[None])[0])]
                post_selection = time.perf_counter() - select_start
                candidate, point, governance, forecast, state = selected_final(e, arm, f'case{index}-final')
                selected_arrays[uid], predictions[uid] = candidate, point
                final_details.update(arm=arm, governance_seconds=governance,
                                     final_forecast_seconds=forecast, candidate_status=state)
                acquired[tool] = {'evidence': evidence, 'actual_seconds': tool_seconds, **detail}
                invoice = bill('initial-dirty-selection', initial_seconds).merge(
                    bill('tool-' + tool, tool_seconds), bill('post-evidence-selection', post_selection),
                    bill('selected-governance', governance), bill('selected-forecast', forecast))
                return AcquiredBranch(arm, invoice, array_hash(vector), policy.frozen_hash)

            result = execute_one_step(terminal_hash=policy.frozen_hash, visible_features=x,
                stop_arm=stop_arm, stop_invoice=planning_stop, branch_estimates=estimates,
                budget=budget, applicable=applicable, model=acquirer, fetch=fetch)
            if result['tool'] is None:
                candidate, point, governance, forecast, state = selected_final(e, result['arm'], f'case{index}-final')
                selected_arrays[uid], predictions[uid] = candidate, point
                final_details.update(arm=result['arm'], governance_seconds=governance,
                                     final_forecast_seconds=forecast, candidate_status=state)
            hot_seconds = time.perf_counter() - started
            result.update(total_seconds=hot_seconds, hot_request_seconds=hot_seconds,
                          budget_overrun=hot_seconds > budget + 1e-12,
                          status='budget_overrun' if hot_seconds > budget + 1e-12 else
                                 'STOP' if result['tool'] is None else 'COMMIT',
                          stop_cost_estimate_seconds=stop_estimate,
                          delta_cost_estimate_seconds=None if stop_estimate is None else hot_seconds - stop_estimate,
                          delta_cost=None, stop_total_seconds=None,
                          counterfactual_stop_cost='not executed online; no claim of actual branch difference')
            # Replace provisional admission invoices with the entire measured hot request.
            component = {'initial-dirty-selection': initial_seconds,
                         'selected-governance': final_details['governance_seconds'],
                         'selected-forecast': final_details['final_forecast_seconds']}
            for tool, record in acquired.items():
                component['tool-' + tool] = record['actual_seconds']
            remaining = hot_seconds - sum(component.values())
            require(remaining >= -1e-6, 'Overlapping hot request phases')
            component['selection-and-request-overhead'] = max(0., remaining)
            result['invoice'] = CostInvoice(tuple(Charge(key, seconds) for key, seconds in component.items())).as_dict()
            require(result['arm'] == final_details['arm'], 'Forecast action differs from selected governance')
            row = {**partition[uid], **result, **final_details, 'episode_uid': uid,
                   'candidate_hash': array_hash(selected_arrays[uid]), 'acquired': acquired,
                   'dirty_feature_hash': array_hash(x), 'selected_candidate_only': True}
            outputs.append(row)
            atomic_json(out / 'decisions.json', outputs)
            status['episodes_completed'] = len(outputs)
            atomic_json(out / 'status.json', status)
        with (out / 'forecasts.npz').open('xb') as stream:
            np.savez(stream, **predictions)
        with (out / 'selected_candidates.npz').open('xb') as stream:
            np.savez(stream, **selected_arrays)
        barrier.update(open=True, released_at=datetime.now(timezone.utc).isoformat(),
                       final_forecasts_sha256=file_hash(out / 'forecasts.npz'))
        atomic_json(out / 'label_access_barrier.json', barrier)
        # Evaluation and cached-output comparisons are first opened after all forecasts.
        scales = read(old / 'mase_scales.json')
        old_evidence = read(old / 'evidence.json')
        history_evidence = None if condition == 'old32' else read(root / 'history/evidence.json')[condition]
        offline = [r for r in read(root / 'decisions.json') if r['policy'] == 'AGENT_' + name + '_high']
        reference = {r['episode_uid']: r for r in offline}
        with np.load(old / 'targets.npz', allow_pickle=False) as targets, \
             np.load(old / 'candidates.npz', allow_pickle=False) as candidates, \
             np.load(old / 'forecasts.npz', allow_pickle=False) as forecasts:
            for row in outputs:
                uid, arm = row['episode_uid'], row['arm']
                truth, mask = targets[uid + '_values'], targets[uid + '_mask']
                require(np.array_equal(mask, np.isfinite(truth)), 'Changed common scoring mask')
                row['mae'] = float(np.mean(abs(predictions[uid][mask] - truth[mask])))
                row['mase'] = row['mae'] / scales[row['source']]
                row['candidate_agreement'] = bool(np.allclose(selected_arrays[uid], candidates[uid + '_' + arm],
                                                  rtol=1e-6, atol=1e-5, equal_nan=True))
                row['forecast_agreement'] = bool(np.allclose(predictions[uid], forecasts[uid + '_' + arm],
                                                  rtol=1e-6, atol=1e-5))
                row['evidence_agreement'] = {}
                for tool, record in row['acquired'].items():
                    expected = old_evidence[uid]['strict_mask'] if tool == 'strict_mask' else (
                        old_evidence[uid]['history_probe'] if condition == 'old32' else history_evidence[uid])
                    row['evidence_agreement'][tool] = all(np.allclose(np.asarray(record['evidence'][a], float),
                          np.asarray(expected[a], float), rtol=1e-6, atol=1e-5, equal_nan=True) for a in POOL)
                row['offline_policy_match'] = reference[uid]['policy'] if uid in reference else None
                row['action_agreement'] = row['arm'] == reference[uid]['arm'] if uid in reference else None
                row['history_agreement'] = row['history'] == reference[uid]['history'] if uid in reference else None
        atomic_json(out / 'decisions.json', outputs)
        status.update(status='completed', cases=len(outputs),
                      current_target_archive_opened_after_final_forecasts=True,
                      action_agreements=sum(r['action_agreement'] is True for r in outputs),
                      history_agreements=sum(r['history_agreement'] is True for r in outputs),
                      raw_output_agreements=sum(r['candidate_agreement'] and r['forecast_agreement'] for r in outputs),
                      hot_budget_overruns=sum(r['budget_overrun'] for r in outputs),
                      online_equivalence_passed=all(r['candidate_agreement'] and r['forecast_agreement']
                          and r['action_agreement'] is True and r['history_agreement'] is True
                          and all(r['evidence_agreement'].values()) and not r['budget_overrun'] for r in outputs),
                      label_access_barrier=barrier, method_promotion=False)
    except Exception as exc:
        status.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        if hasattr(services, 'processes'):
            services.close()
        atomic_json(out / 'status.json', status)
        print(json.dumps(status), flush=True)


if __name__ == '__main__':
    main()
