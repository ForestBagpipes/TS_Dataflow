#!/usr/bin/env python3
"""Live one-decision r3 replay; evaluator archives remain sealed until prediction."""
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
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('results/v431-r3'))
    parser.add_argument('--family', required=True, choices=['bolt', 'timesfm'])
    parser.add_argument('--output-name')
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    args.root = args.root.resolve()
    name = args.output_name or 'online-' + args.family
    assert Path(name).name == name and name not in ('.', '..')
    out = args.root / name
    if args.worker:
        return worker(args, out)
    out.mkdir(exist_ok=False)
    begun = time.perf_counter()
    command = [sys.executable, str(Path(__file__).resolve()), '--root', str(args.root),
               '--family', args.family, '--output-name', name, '--worker']
    with (out / 'worker.log').open('x') as f:
        process = subprocess.Popen(command, stdout=f, stderr=subprocess.STDOUT)
        atom(out / 'process_accounting.json', dict(status='running', pid=process.pid, command=command))
        code = process.wait()
    wall = time.perf_counter() - begun
    accounting = dict(status='completed' if code == 0 else 'failed', exit_code=code, process_wall_seconds=wall,
                      scope='full validation worker spawn through exit including controlled cases')
    if (out / 'decisions.json').exists():
        rows = json.loads((out / 'decisions.json').read_text())
        hot = sum(r['hot_request_seconds'] for r in rows)
        startup = sum(r['wall_seconds'] for r in json.loads((out / 'service/service_startup.json').read_text()))
        assert wall >= hot + startup
        natural = [r for r in rows if not r['controlled']]
        accounting.update(requests=len(rows), natural_requests=len(natural), hot_request_seconds=hot,
                          model_startup_seconds=startup, remaining_overhead_seconds=wall-hot-startup,
                          natural_actual_tool_calls=sum(r['actual_tool_calls'] for r in natural),
                          natural_hot_seconds=sum(r['hot_request_seconds'] for r in natural),
                          natural_acquisition_decisions=sum(r['branch'] is not None for r in natural))
        for r in rows:
            r.update(allocated_startup_seconds=startup/len(rows),
                     allocated_other_process_seconds=(wall-hot-startup)/len(rows),
                     total_seconds=r['hot_request_seconds']+(wall-hot)/len(rows))
            r['complete_process_budget_overrun'] = r['total_seconds'] > r['budget']+1e-12
        atom(out / 'decisions.json', rows)
    atom(out / 'process_accounting.json', accounting)
    print(json.dumps(accounting), flush=True)
    if code:
        raise SystemExit(code)


def worker(args, out):
    import joblib
    import numpy as np
    from introact_ts.v43.schemas import Episode, array_hash, require
    from introact_ts.v43.agent_inputs import POOL
    from introact_ts.v43.data_io import file_hash
    from introact_ts.v431.data import dirty_features, PERIODS
    from introact_ts.v431_r3.runtime import LiveRuntime, OLD
    from introact_ts.v431_r3.probe import prepare_probe, registered_specs
    from introact_ts.v431_r3.response import state_from_results
    from introact_ts.v431_r3.acquisition import (
        BRANCH_TOOLS, ACTIVE_BRANCHES, CostInvoice, Charge, AcquiredBranch, AccountedToolError, execute_one_step)
    read = lambda p: json.loads(Path(p).read_text())
    barrier = dict(open=False, denied_preflight=0, unexpected=0)
    forbidden = {'targets.npz', 'task_labels.json', 'value_labels.json', 'decisions.json', 'evidence.json',
                 'forecasts.npz', 'predictions.npz', 'candidates.npz', 'records.json', 'scored_rows.json', 'proxy_target_pairs.json'}
    allowed_results = {args.root / name for name in ('terminal_manifest.json', 'models_frozen.json', 'models.joblib')}
    allowed_results.update(OLD / name for name in ('episode_manifest.json', 'contexts.npz', 'mase_scales.json', 'resolved_config.yaml', 'model_manifest.json', 'code_manifest.json'))
    results_root = OLD.parents[1]
    def blocked(path):
        return path.is_relative_to(results_root) and not path.is_relative_to(out) and path not in allowed_results
    def audit(event, arguments):
        if event == 'open' and not barrier['open'] and isinstance(arguments[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(arguments[0])).resolve()
            if blocked(path):
                if not barrier.get('preflight', False):
                    barrier['unexpected'] += 1
                raise PermissionError('r3 evaluator and unacquired probe archives sealed')
    sys.addaudithook(audit)
    barrier['preflight'] = True
    for name in forbidden:
        try:
            open(OLD / name, 'rb')
            raise AssertionError('Unsealed evaluator archive')
        except PermissionError:
            barrier['denied_preflight'] += 1
    barrier['preflight'] = False
    manifest = read(args.root / 'terminal_manifest.json')
    frozen = read(args.root / 'models_frozen.json')
    expected = frozen.get('sha256', frozen.get('model_sha256'))
    require(file_hash(args.root / 'models.joblib') == expected, 'Frozen complete models changed')
    models = joblib.load(args.root / 'models.joblib')
    policy = models['policies'][args.family]['residual']
    acquirer = models['acquirers'][args.family]
    settings = manifest['families'][args.family]
    require(policy.frozen_hash == acquirer.terminal_hash == settings['terminal_hash'], 'Acquirer references another terminal')
    high = float(manifest['budgets']['high'])
    meta, scales = read(OLD / 'episode_manifest.json'), read(OLD / 'mase_scales.json')
    uids = []
    for source in sorted({m['source'] for m in meta.values()}):
        candidates = [u for u, m in meta.items() if m['split'] == 'dev' and m['source'] == source
                      and m['horizon'] == 96 and m['condition'] == 'target_block_10']
        uids.extend(sorted(candidates, key=lambda u: meta[u]['raw_start'])[:3])
    require(len(uids) == 7, 'Original seven natural online cases changed')
    episodes = {}
    with np.load(OLD / 'contexts.npz', allow_pickle=False) as f:
        def load(uid):
            m = meta[uid]
            e = Episode(uid, m['source'], m['source'], m['parent_group'], m['split'], 0,
                        m['raw_start'], m['context_end'], m['horizon'],
                        **{k: f[uid+'_'+k] for k in ('target', 'covariates', 'timestamps', 'availability')})
            require(array_hash(e.target) == m['target_hash'], 'Current input changed')
            episodes[uid] = e
            return e
        for uid in uids:
            load(uid)
        raw = next(u for u, m in meta.items() if m['split'] == 'dev' and m['condition'] == 'raw'
                   and m['horizon'] == 96 and np.isfinite(load(u).target).all())
    plan = [dict(case_id='natural-'+str(i), episode_uid=u, controlled=False, mode='learned', budget=high) for i, u in enumerate(uids)]
    plan.extend([dict(case_id='complete-raw', episode_uid=raw, controlled=True, mode='learned', budget=high),
                 dict(case_id='budget-zero', episode_uid=uids[0], controlled=True, mode='learned', budget=0.),
                 dict(case_id='failed-after-real-long', episode_uid=uids[0], controlled=True, mode='fixed', branch='H',
                      budget=max(high, settings['branch_estimates']['H']), inject_failure=True),
                 dict(case_id='controlled-length-pair', episode_uid=uids[0], controlled=True, mode='fixed', branch='control',
                      budget=max(high, settings['branch_estimates']['control']))])
    atom(out / 'protocol.json', dict(family=args.family, plan=plan, terminal_hash=policy.frozen_hash,
         model_sha256=expected, source_sha256=file_hash(__file__), selection='original up-to-three H96 target-block parents per source',
         controlled_cases_not_method_results=True, hidden_archives=list(sorted(forbidden)),
         budget_rule='natural unchanged high; controlled branches use max(high, frozen estimate)', heldout_labels_read=0))
    runtime = LiveRuntime(out / 'service', args.family, episodes[uids[0]])
    rows, stored = [], {}
    try:
        for case in plan:
            e = episodes[case['episode_uid']]
            start = time.perf_counter()
            x = dirty_features(e, PERIODS[e.source])
            complete = bool(np.isfinite(e.target).all())
            before = policy.choose(x, None, fully_observed=complete)
            initial_seconds = time.perf_counter()-start
            stop_arm = before['arm']
            estimates = {k: CostInvoice((Charge('estimated-'+k, v),)) for k, v in settings['branch_estimates'].items() if k in ACTIVE_BRANCHES}
            stop_estimate = CostInvoice((Charge('estimated-final', settings['action_estimates'][stop_arm]),))
            available = {a: prepare_probe(e, registered_specs(e.horizon)[a], scales[e.source]).status == 'prepared'
                         for a in ('h32', 'long', 'short')}
            applicable = {k: all(available[a] for a in BRANCH_TOOLS[k]) for k in ACTIVE_BRANCHES}
            actual, final, after = [], {}, {}
            def run_final(arm):
                c, pred, invoice, detail = runtime.final(e, arm)
                stored[case['case_id']+'_candidate'] = c
                stored[case['case_id']+'_prediction'] = pred
                final.update(arm=arm, candidate_hash=array_hash(c), prediction_hash=array_hash(pred),
                             candidate_status=detail, invoice=invoice.as_dict())
                return invoice
            def fallback():
                return AcquiredBranch(stop_arm, run_final(stop_arm), 'actual-fixed-reference-fallback', policy.frozen_hash)
            def fetch(branch):
                records, spent = {}, CostInvoice()
                for primitive in BRANCH_TOOLS[branch]:
                    tick = time.perf_counter()
                    try:
                        record = runtime.probe(e, primitive, scales[e.source], POOL[policy.reference_action])
                    except Exception as exc:
                        cost = CostInvoice((Charge('failed-'+primitive, time.perf_counter()-tick),))
                        actual.append(dict(probe=primitive, status='failed', reason=repr(exc), invoice=cost.as_dict()))
                        raise AccountedToolError(repr(exc), spent.merge(cost), attempted_tools=tuple(r['probe'] for r in actual)) from exc
                    records[primitive] = record
                    actual.append(record)
                    spent = spent.merge(CostInvoice(tuple(Charge(**v) for v in record['invoice']['charges'])))
                    if case.get('inject_failure'):
                        raise AccountedToolError('controlled failure after real long measurement', spent, attempted_tools=(primitive,))
                state = state_from_results(branch, records, reference_arm=POOL[policy.reference_action])
                choice = policy.choose(x, state, fully_observed=complete)
                after.update(choice)
                return AcquiredBranch(choice['arm'], spent.merge(run_final(choice['arm'])), state.evidence_hash, policy.frozen_hash)
            result = execute_one_step(terminal_hash=policy.frozen_hash, visible_features=x, stop_arm=stop_arm,
                stop_invoice=stop_estimate, branch_estimates=estimates, budget=case['budget'], applicable=applicable,
                model=acquirer, fetch=fetch, fallback=fallback, fully_observed=complete,
                mode=case['mode'], tool_order=(case['branch'],) if case.get('branch') else None)
            if result['branch'] is None:
                require(result['arm'] == before['arm'], 'STOP changed the no-evidence terminal action')
            if not final:
                run_final(result['arm'])
            hot = time.perf_counter()-start
            component = {'initial-diagnostic-selection': initial_seconds,
                         'final-governance-and-forecast': final['invoice']['total_seconds']}
            for i, r in enumerate(actual):
                component[f'actual-probe-{i}-{r["probe"]}'] = r['invoice']['total_seconds']
            remainder = hot-sum(component.values())
            require(remainder >= -1e-6, 'Online phase cost double counted')
            component['planning-selection-logging-overhead'] = max(0., remainder)
            result.update(invoice=CostInvoice(tuple(Charge(k, v) for k, v in component.items())).as_dict(),
                          total_seconds=hot, hot_request_seconds=hot, budget_overrun=hot>case['budget']+1e-12,
                          delta_cost=None, counterfactual_stop_not_executed=True)
            row = dict(meta[e.uid], **case)
            row.update(result, family=args.family, final=final, before_decision=before, after_decision=after,
                       actual_probes=actual, actual_tool_calls=len(actual), visible_features=x.tolist(), fully_observed=complete)
            rows.append(row)
            atom(out / 'decisions.json', rows)
        with (out / 'live_arrays.npz').open('xb') as f:
            np.savez(f, **stored)
    finally:
        runtime.close()
    atom(out / 'visibility_barrier.json', dict(barrier, status='passed', predictions_saved=True,
         live_arrays_sha256=file_hash(out / 'live_arrays.npz'), before_evaluator_open=True))
    require(barrier['unexpected'] == 0, 'Unexpected hidden evidence access')
    barrier['open'] = True
    # Independent evaluation namespace begins only after every actual final output.
    from introact_ts.v431_r2.data import R2Data
    data = R2Data()
    for row in rows:
        i = data.uids.index(row['episode_uid'])
        arm = row['final']['arm']
        expected_pred = data.predictions[args.family][row['episode_uid']][arm]
        actual_pred = stored[row['case_id']+'_prediction']
        require(np.allclose(actual_pred, expected_pred, rtol=1e-6, atol=1e-5), 'Live final differs from actual frozen candidate prediction')
        expected_candidate = data.old.pools[row['episode_uid']][arm]
        actual_candidate = stored[row['case_id']+'_candidate']
        candidate_equal = bool(np.array_equal(actual_candidate, expected_candidate, equal_nan=True))
        require(np.allclose(actual_candidate, expected_candidate, equal_nan=True, rtol=1e-6, atol=1e-5), 'Live governance differs from frozen five-arm candidate')
        row.update(mase=float(data.L[args.family][i, POOL.index(arm)]), actual_prediction_matches_cache=True,
                   candidate_matches_cache=candidate_equal, candidate_hash_equal=array_hash(actual_candidate)==array_hash(expected_candidate),
                   prediction_hash_equal=array_hash(actual_pred)==array_hash(expected_pred))
    atom(out / 'decisions.json', rows)
    atom(out / 'status.json', dict(status='completed', cases=len(rows), heldout_labels_read=0,
         natural_actual_tool_calls=sum(r['actual_tool_calls'] for r in rows if not r['controlled']),
         all_final_predictions_match=True))


if __name__ == '__main__':
    main()
