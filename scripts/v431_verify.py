#!/usr/bin/env python3
"""Independent v4.3.1 audit of frozen rows, raw outputs and reading boundaries.

This evaluator opens the already generated train/dev target cache to recompute
metrics. It is not an online policy input. No calibration/test reader is used.
Each invocation preserves its own report, including failed/partial attempts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import joblib

from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.schemas import array_hash
from introact_ts.v43.worker_protocol import verify_response


OLD = Path('results/v43/20260914T141030.324186Z-agent')


def read(path):
    return json.loads(Path(path).read_text())


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cost_references(root):
    return {'direct': read(OLD / 'direct_candidate_costs.json'),
            'forecast': read(OLD / 'forecast_costs.json'),
            'old_tools': read(OLD / 'tool_costs.json'),
            'new_tools': read(root / 'history' / 'tool_costs.json'),
            'old_base': read(OLD / 'base_costs.json'),
            'old_decisions': {(r['episode_uid'], r['policy']): r
                              for r in read(OLD / 'agent' / 'decisions.json')}}


def audit_invoice(invoice, uid, refs, *, row=None):
    charges = invoice['charges']
    check(len({c['key'] for c in charges}) == len(charges), 'Duplicate shared computation was charged twice')
    for charge in charges:
        key, value = charge['key'], charge['seconds']
        check(np.isfinite(value) and value >= 0, 'Nonfinite/negative cost')
        parts = key.split(':')
        check(len(parts) >= 2 and parts[1] == uid, 'Charge uses another episode identity')
        if parts[0] == 'candidate':
            expected = refs['direct'][uid][parts[2]]
        elif parts[0] == 'forecast':
            expected = refs['forecast'][uid + '_' + parts[2]]
        elif parts[0] == 'tool':
            condition, tool = parts[2:]
            if tool == 'strict_mask' or condition == 'old32':
                expected = refs['old_tools'][uid]['strict_mask' if tool == 'strict_mask' else 'history_probe']
            else:
                expected = refs['new_tools'][condition][uid]
        elif parts[0] in ('selection', 'stop-selection', 'acquired-selection'):
            continue  # A new actual timer is nonnegative; it is not a cache value.
        elif parts[0] == 'old-whole':
            check(row is not None, 'Unidentified old whole-invoice charge')
            if row['policy'] == 'OLD_DIRTY_HGB':
                old = refs['old_decisions'][uid, 'DIRTY_SELECTOR']
                expected = old['total_governance_seconds'] + old['final_forecast_seconds']
            else:
                old_selection = row.get('selection_seconds', row.get('old_selection_seconds'))
                check(old_selection is not None and np.isfinite(old_selection) and old_selection >= 0,
                      'Old HGB rerun did not record its actual selection time')
                expected = (refs['old_base'][uid] + old_selection +
                            sum(refs['old_tools'][uid][tool] for tool in row['history']) +
                            refs['forecast'][uid + '_' + row['arm']])
        else:
            raise AssertionError(f'Unregistered deployment charge {key}')
        np.testing.assert_allclose(value, expected, rtol=1e-12, atol=1e-12)
    total = float(sum(c['seconds'] for c in charges))
    np.testing.assert_allclose(invoice['total_seconds'], total, rtol=1e-12, atol=1e-12)
    return total


def audit_frozen_models(root, partition, contexts):
    from introact_ts.v43.schemas import Episode
    from introact_ts.v431.data import dirty_features, PERIODS, FEATURE_NAMES
    from introact_ts.v431.decision_tree import canonical_hash
    from introact_ts.v431.terminal import RefinedPolicy
    frozen = read(root / 'models_frozen.json')
    manifest = read(root / 'terminal_manifest.json')
    check(sha(root / 'models.joblib') == frozen['sha256'], 'Frozen model checkpoint hash mismatch')
    check(frozen['terminal_hashes'] == manifest['terminal_hashes'], 'Final freeze changed a terminal hash')
    check(manifest['created_at'] <= frozen['created_at'], 'Terminal freeze is later than all-model freeze')
    check(manifest['feature_names'] == list(FEATURE_NAMES), 'Unregistered dirty feature schema')
    models = joblib.load(root / 'models.joblib')  # Just-generated local file, hash checked first.
    terminals = {}
    fit_parents = {m['parent_group'] for m in partition.values() if m['v431_role'] == 'T_fit'}
    gate_parents = {m['parent_group'] for m in partition.values() if m['v431_role'] == 'T_gate'}
    acq_parents = {m['parent_group'] for m in partition.values() if m['v431_role'] == 'T_acq'}
    for name, digest in manifest['terminal_hashes'].items():
        terminal = RefinedPolicy.from_dict(read(root / (name + '.terminal.json')))
        check(terminal.frozen_hash == digest == models['terminal'][name].frozen_hash,
              'Terminal JSON/checkpoint/manifest identity mismatch')
        check(set(terminal.base_tree.training_parent_ids) == fit_parents, 'Base policy fitted outside T_fit')
        check(terminal.gate_parent_hash == canonical_hash(sorted(gate_parents)), 'Gate policy parent hash mismatch')
        terminals[name] = terminal
    refs = cost_references(root)
    old_evidence = read(OLD / 'evidence.json')
    new_evidence = read(root / 'history' / 'evidence.json')
    labels = read(root / 'value_labels.json')
    scales = read(OLD / 'mase_scales.json')
    task_losses = {}
    # Derive acquisition supervision from actual saved current-task predictions
    # and the sealed-to-policy evaluator target cache, not from a copied gain.
    with np.load(OLD / 'forecasts.npz', allow_pickle=False) as forecasts, \
         np.load(OLD / 'targets.npz', allow_pickle=False) as targets:
        for uid in {r['uid'] for rows in labels.values() for r in rows}:
            y, mask = targets[uid + '_values'], targets[uid + '_mask']
            np.testing.assert_array_equal(mask, np.isfinite(y))
            check(mask.any(), 'Empty acquisition supervision scoring mask')
            for arm in POOL:
                prediction = forecasts[uid + '_' + arm]
                check(np.isfinite(prediction).all(), 'Failed acquisition supervision forecast')
                task_losses[uid, arm] = float(np.abs(prediction[mask] - y[mask]).mean()) / scales[partition[uid]['source']]
    verified = 0
    for name, rows in labels.items():
        check(name in manifest['selected'] and len(manifest['selected']) <= 2, 'Unregistered additional acquirer')
        policy = terminals[name]
        condition = next(s['evidence'] for s in manifest['configs'] if s['name'] == name)
        aq = models['acquirers'][name]
        check(aq.terminal_hash == policy.frozen_hash, 'Acquirer trained for a different terminal')
        check(len({(r['uid'], r['tool']) for r in rows}) == len(rows), 'Duplicated acquisition label')
        for item in rows:
            uid = item['uid'];m = partition[uid]
            check(m['v431_role'] == item['role'] == 'T_acq' and item['parent'] == m['parent_group'],
                  'Acquisition label leaks across train roles')
            check(item['terminal_hash'] == policy.frozen_hash, 'Stale acquisition value label')
            same_source_parents = {m['parent_group'] for m in partition.values()
                                   if m['v431_role'] == 'T_acq' and m['source'] == partition[uid]['source']}
            source_count = len({m['source'] for m in partition.values() if m['v431_role'] == 'T_acq'})
            variant_count = sum(m['parent_group'] == item['parent'] for m in partition.values())
            np.testing.assert_allclose(item['weight'], 1 / (source_count * len(same_source_parents) * variant_count),
                                       rtol=1e-12, atol=1e-12)
            episode = Episode(uid, m['source'], m['source'], m['parent_group'], m['split'], 0,
                              m['raw_start'], m['context_end'], m['horizon'],
                              contexts[uid + '_timestamps'], contexts[uid + '_target'],
                              contexts[uid + '_covariates'], contexts[uid + '_availability'])
            X = dirty_features(episode, PERIODS[m['source']])[None]
            E = np.full((1, 30), np.nan)
            if item['tool'] == 'strict_mask':
                evidence = old_evidence[uid]['strict_mask']
                E[0, :15] = [np.nan if v is None else v for arm in POOL for v in evidence[arm]]
            else:
                check(item['tool'] == 'history', 'Unknown acquisition tool')
                evidence = (old_evidence[uid]['history_probe'] if condition == 'old32'
                            else new_evidence[condition][uid])
                E[0, 15:] = [np.nan if v is None else v for arm in POOL for v in evidence[arm]]
            before = int(policy.predict(X, np.full_like(E, np.nan))[0])
            after = int(policy.predict(X, E)[0])
            # Both endpoints are recomputed with exactly the same frozen pi,
            # using only one acquired tool at the second endpoint.
            gain = task_losses[uid, POOL[before]] - task_losses[uid, POOL[after]]
            stop = audit_invoice(item['stop_invoice'], uid, refs)
            acquire = audit_invoice(item['acquire_invoice'], uid, refs)
            audit_invoice(item['tool_invoice'], uid, refs)
            check(any(c['key'] == 'candidate:' + uid + ':' + POOL[before]
                      for c in item['stop_invoice']['charges']), 'STOP invoice uses another action')
            check(any(c['key'] == 'candidate:' + uid + ':' + POOL[after]
                      for c in item['acquire_invoice']['charges']), 'Acquire invoice uses another action')
            np.testing.assert_allclose([item['task_gain'], item['delta_cost'], item['stop_cost'],
                                       item['acquire_cost'], item['value']],
                                      [gain, acquire - stop, stop, acquire,
                                       gain - item['lambda'] * (acquire - stop)], rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(item['lambda'], aq.lambda_value, rtol=1e-12, atol=1e-12)
            verified += 1
        for record in aq.report['cv_records']:
            check(record['held_parent'] in acq_parents, 'Price chosen outside T_acq')
            check(record['held_parent'] not in record['train_parents'], 'Acquisition price CV parent leakage')
            check(set(record['train_parents']).issubset(acq_parents), 'Price CV used another role')
    return {'status': 'passed', 'terminal_models': len(terminals),
            'acquirers': len(labels), 'value_labels': verified,
            'same_frozen_policy_endpoints': True, 'T_acq_parent_cv_isolated': True,
            'T_acq_losses_recomputed_from_actual_predictions_and_targets': True,
            'T_acq_source_parent_weights_verified': True}


def audit_partition(root, meta):
    partition = read(root / 'partition.json')
    check(set(partition) == set(meta), 'Partition changed the archived episode denominator')
    spans, roles, strata = {}, {}, {}
    for uid, row in partition.items():
        original = meta[uid]
        for field in ('source', 'parent_group', 'split', 'raw_start', 'context_end',
                      'horizon', 'condition', 'target_hash', 'covariate_hash'):
            check(row[field] == original[field], f'Changed archived metadata {uid} {field}')
        check(row['split'] in ('train', 'dev'), 'Heldout row found')
        role = row['v431_role']
        check(role in ('T_fit', 'T_gate', 'T_check', 'T_acq', 'dev'), 'Unknown role')
        check((role == 'dev') == (row['split'] == 'dev'), 'Train/dev role mismatch')
        key = row['source'], row['parent_group']
        check(key not in roles or roles[key] == role, 'Parent crosses fitting roles')
        roles[key] = role
        strata[key] = row['source']
        lo, hi = spans.get(key, (row['raw_start'], row['context_end'] + row['horizon']))
        spans[key] = min(lo, row['raw_start']), max(hi, row['context_end'] + row['horizon'])
    for source in {s for s, _ in spans}:
        intervals = sorted((lo, hi, roles[key]) for key, (lo, hi) in spans.items() if key[0] == source)
        check(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])),
              f'Full context/future ranges overlap in {source}')
    # Recompute weights independently. Every source has equal mass; each parent
    # divides its own mass among its six correlated task variants.
    weight_audit = {}
    for role in sorted(set(roles.values())):
        uids = [u for u, m in partition.items() if m['v431_role'] == role]
        counts = Counter((partition[u]['source'], partition[u]['parent_group']) for u in uids)
        source_counts = Counter(source for source, _ in counts)
        weights = {u: 1 / (len(source_counts) * source_counts[partition[u]['source']] *
                            counts[partition[u]['source'], partition[u]['parent_group']]) for u in uids}
        check(np.isclose(sum(weights.values()), 1), 'Source macro weights do not sum to one')
        for source in source_counts:
            check(np.isclose(sum(weights[u] for u in uids if partition[u]['source'] == source),
                             1 / len(source_counts)), 'Source weight changed by variants')
        weight_audit[role] = {'parents': len(counts), 'episodes': len(uids),
                              'source_parents': dict(source_counts), 'weight_sum': sum(weights.values())}
    return partition, {'roles': weight_audit, 'raw_ranges_disjoint': True,
                       'same_parent_one_role': True, 'new_heldout_labels_read': 0}


def raw_worker_audit(directory, contexts, meta, *, historical=False, candidates=None):
    """Verify raw quantiles -> points, identity and exact original-row prefixes."""
    directory = Path(directory)
    model = read(directory / 'model_manifest.json')['models']
    code_hash = read(directory / 'code_manifest.json')['hash']
    requests = sorted(directory.glob('*.request.json')) if historical else sorted(directory.glob('final-*.request.json'))
    check(bool(requests), f'No worker requests in {directory}')
    checked_rows, checked_shards = 0, 0
    points, input_hashes, declared_costs = {}, {}, {}
    pending = []
    for path in requests:
        shard = path.name.removesuffix('.request.json')
        response_path = directory / (shard + '.response.json')
        if not response_path.exists():
            pending.append(shard)
            continue
        request, response = read(path), read(response_path)
        check(request['code_hash'] == code_hash, 'Producer code identity mismatch')
        model_record = model[request['model_key']]
        check(request['model_revision'] == model_record['revision'], 'Changed model revision')
        check(request['environment_hash'] == model_record['environment_lock_sha256'], 'Changed worker environment')
        check(request['normalization'] == 'native', 'Changed raw output normalization')
        with np.load(directory / (shard + '.predictions.npz'), allow_pickle=False) as archive, \
             np.load(directory / (shard + '.predictions.raw.npz'), allow_pickle=False) as raw:
            values = [archive[f'row_{i}'] for i in range(len(request['rows']))]
            verify_response(request, response, values)
            for i, (q, r, point) in enumerate(zip(request['rows'], response['rows'], values)):
                raw_value = raw[f'row_{i}']
                check(array_hash(raw_value) == r['raw_hash'], 'Raw quantile hash mismatch')
                check(np.isfinite(raw_value).all(), 'Nonfinite raw quantile output')
                uid = q['episode_uid'].split(':asof:', 1)[0] if historical else q['episode_uid']
                check(uid in meta, 'Worker input is outside frozen episode manifest')
                m = meta[uid]
                expected_length = 512 - m['horizon'] if historical else 512
                target = contexts[uid + '_target'][:expected_length].copy()
                covariates = contexts[uid + '_covariates'][:expected_length].copy()
                timestamps = contexts[uid + '_timestamps'][:expected_length]
                availability = contexts[uid + '_availability'][:expected_length]
                # Apply the publication boundary independently of as_of().
                target[availability[:, 0] > timestamps[-1]] = np.nan
                covariates[availability[:, 1:] > timestamps[-1]] = np.nan
                observed = np.isfinite(target)
                with np.load(q['array_path'], allow_pickle=False) as payload:
                    for key, hash_key in (('target', 'input_hash'), ('raw_mask', 'raw_mask_hash'),
                                          ('covariates', 'covariate_hash'), ('timestamps', 'timestamps_hash'),
                                          ('availability', 'availability_hash')):
                        check(array_hash(payload[key]) == q[hash_key], f'Worker payload hash mismatch {key}')
                    check(payload['target'].shape == target.shape, 'Historical context was padded or extended')
                    np.testing.assert_array_equal(payload['raw_mask'], observed)
                    np.testing.assert_array_equal(payload['timestamps'], timestamps)
                    np.testing.assert_array_equal(payload['availability'], availability)
                    np.testing.assert_array_equal(payload['covariates'], covariates)
                    check(q['cutoff'] == m['raw_start'] + expected_length, 'Exclusive origin cutoff mismatch')
                    np.testing.assert_array_equal(payload['target'][observed], target[observed])
                    if request['task'] == 'impute':
                        np.testing.assert_array_equal(payload['target'], target)
                        check(point[observed].tobytes() == target[observed].tobytes(), 'Imputation overwrote an observation')
                        np.testing.assert_array_equal(point[~observed], raw_value[0, 0, ~observed, 1])
                    else:
                        np.testing.assert_array_equal(point, raw_value[0, 4])
                        if not historical and candidates is not None:
                            np.testing.assert_array_equal(payload['target'], candidates[uid + '_' + q['candidate_id']])
                key = shard, q['episode_uid'], q['candidate_id']
                points[key] = point.copy()
                input_hashes[key] = q['input_hash']
                declared_costs[key] = r['runtime_seconds']
                checked_rows += 1
        checked_shards += 1
    return {'worker_shards': checked_shards, 'raw_quantile_rows': checked_rows,
            'pending_shards': pending, 'asof_prefix_checked': historical,
            'point_is_actual_raw_median': True}, points, input_hashes, declared_costs


def audit_history(root, contexts, meta):
    hroot = root / 'history'
    status = read(hroot / 'status.json')
    result, points, input_hashes, runtimes = raw_worker_audit(hroot, contexts, meta, historical=True)
    result['producer_status'] = status['status']
    if status['status'] != 'completed' or result['pending_shards']:
        result['status'] = 'partial_not_accepted'
        return result
    views = read(hroot / 'view_manifest.json')
    hashes = read(hroot / 'candidate_hashes.json')
    invoices = read(hroot / 'model_invoices.json')
    evidence = read(hroot / 'evidence.json')
    tool_costs = read(hroot / 'tool_costs.json')
    for item in invoices:
        key = item['shard'], item['episode_uid'], item['arm']
        check(key in runtimes, 'Invoice without a verified raw output')
        np.testing.assert_allclose(item['inference_seconds'], runtimes[key], rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(item['charged_seconds'], item['inference_seconds'] +
                                   item['allocated_shard_overhead_seconds'], rtol=1e-12, atol=1e-12)
        check(item['allocated_shard_overhead_seconds'] >= 0, 'Negative shard overhead')
    check(len(invoices) == len(runtimes), 'Missing/duplicated model invoice')
    distinct_forecast = {}
    for key, point in points.items():
        shard, uid, arm = key
        if 'bolt' in shard:
            distinct_forecast[shard, uid, input_hashes[key]] = point
    with np.load(hroot / 'forecasts.npz', allow_pickle=False) as forecasts:
        for uid, m in meta.items():
            x = contexts[uid + '_target']
            cutoff = 512 - m['horizon']
            check(views[uid]['cutoff'] == cutoff, 'Historical view manifest cutoff mismatch')
            # Repeat the observable robust scale formula, without calling the
            # production evidence function or looking at the true dirty gap.
            observed = x[np.isfinite(x)]
            median = float(np.median(observed))
            scale = float(np.median(np.abs(observed - median)))
            scale = max(scale, abs(median) * 1e-6, 1e-6)
            for condition, viewkey, horizon, prefix in (
                    ('same_origin32', 'short', 32, 'same32'),
                    ('target_horizon', 'full', m['horizon'], 'targeth')):
                view = views[uid][viewkey]
                shard = f'{prefix}-h{horizon}-bolt'
                y = x[cutoff:cutoff + horizon]
                mask = np.isfinite(y)
                predictions = {}
                for arm in POOL:
                    forecast = forecasts[condition + '_' + uid + '_' + arm]
                    digest = hashes[views[uid]['full']][arm]
                    key = shard, view, digest
                    check(key in distinct_forecast, 'No real hash-matched forecast for history alias')
                    np.testing.assert_array_equal(forecast, distinct_forecast[key])
                    predictions[arm] = forecast
                for arm in POOL:
                    e = evidence[condition][uid][arm]
                    if mask.any():
                        base = float(np.mean(np.abs(predictions['A0_NATIVE'][mask] - y[mask])))
                        err = float(np.mean(np.abs(predictions[arm][mask] - y[mask])))
                        np.testing.assert_allclose(e, [(base - err) / scale, 0., mask.mean()],
                                                   rtol=1e-12, atol=1e-12)
                    else:
                        check(e == [None, None, 0.], 'Unsupported history became numeric evidence')
                check(np.isfinite(tool_costs[condition][uid]) and tool_costs[condition][uid] > 0,
                      'Missing/invalid complete history tool invoice')
    result.update(status='passed',verified_model_invoices=len(invoices),
                  evidence_rows=2 * len(meta), no_current_future_used_in_evidence_formula=True,
                  limitation='Producer initially opened archived evaluator caches; no online isolation claim from this run')
    return result


def audit_decisions(root, meta, partition, contexts):
    decisions = read(root / 'decisions.json')
    check(isinstance(decisions, list) and decisions, 'No common decision rows')
    scales = read(OLD / 'mase_scales.json')
    dev = {u for u, m in partition.items() if m['v431_role'] == 'dev'}
    policy_ids = defaultdict(list)
    grouped = defaultdict(list)
    refs = cost_references(root)
    with np.load(OLD / 'forecasts.npz', allow_pickle=False) as forecasts, \
         np.load(OLD / 'targets.npz', allow_pickle=False) as targets, \
         np.load(OLD / 'candidates.npz', allow_pickle=False) as candidates:
        raw_result, points, input_hashes, _ = raw_worker_audit(OLD, contexts, meta, candidates=candidates)
        check(not raw_result['pending_shards'], 'Original current-task forecasts are incomplete')
        real_forecasts = {(uid, input_hashes[key]): value for key, value in points.items()
                          for _, uid, _ in [key]}
        for row in decisions:
            uid, arm = row['episode_uid'], row['arm']
            check(uid in dev and arm in POOL, 'Decision outside common dev/five-arm matrix')
            for field in ('source', 'horizon', 'condition'):
                check(row[field] == meta[uid][field], f'Decision metadata changed: {field}')
            policy_ids[row['policy']].append(uid)
            y, mask = targets[uid + '_values'], targets[uid + '_mask']
            point = forecasts[uid + '_' + arm]
            digest = array_hash(candidates[uid + '_' + arm])
            check((uid, digest) in real_forecasts, 'Selected action has no actual current-task raw forecast')
            np.testing.assert_array_equal(point, real_forecasts[uid, digest])
            np.testing.assert_array_equal(mask, np.isfinite(y))
            check(mask.any() and np.isfinite(point).all(), 'Empty scoring mask or failed forecast')
            mae = float(np.mean(np.abs(point[mask] - y[mask])))
            mase = mae / scales[row['source']]
            np.testing.assert_allclose([mae, mase], [row['mae'], row['mase']], rtol=1e-12, atol=1e-12)
            check(np.isfinite(row['total_seconds']) and row['total_seconds'] >= 0, 'Invalid declared deployment cost')
            billed = audit_invoice(row['invoice'], uid, refs, row=row)
            np.testing.assert_allclose(row['total_seconds'], billed, rtol=1e-12, atol=1e-12)
            if row.get('budget') is not None:
                check(row['budget_overrun'] == (billed > row['budget']), 'Budget overrun was hidden or misreported')
            grouped[row['policy'], row['source'], meta[uid]['parent_group']].append(row)
    for policy, uids in policy_ids.items():
        check(len(uids) == len(set(uids)) and set(uids) == dev,
              f'{policy} changed or duplicated the common denominator')
    summaries = {}
    for policy in sorted(policy_ids):
        sources = sorted({source for p, source, _ in grouped if p == policy})
        metrics = {}
        for metric in ('mae', 'mase', 'total_seconds'):
            metrics[metric] = float(np.mean([
                np.mean([np.mean([r[metric] for r in rows])
                         for (p, s, _), rows in grouped.items() if p == policy and s == source])
                for source in sources]))
        summaries[policy] = metrics
    return {'status': 'passed', 'policies': len(policy_ids), 'decisions': len(decisions),
            'dev_episodes_each_policy': len(dev),
            'dev_parents': len({(meta[u]['source'], meta[u]['parent_group']) for u in dev}),
            'common_denominator': True, 'current_task_raw_audit': raw_result,
            'independently_recomputed_source_parent_macro': summaries,
            'cost_scope': 'all invoice sums and cached candidate/forecast/tool charges independently checked'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', nargs='?', type=Path, default=Path('results/v431/20260914-sprint'))
    parser.add_argument('--phase', choices=('history', 'decisions', 'all'), default='all')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    destination = args.root / 'verifications' / (stamp + '.json')
    destination.parent.mkdir(exist_ok=True)
    report = {'status': 'running', 'phase': args.phase, 'started_at': stamp,
              'verifier_sha256': sha(__file__), 'new_heldout_labels_read': 0,
              'archived_train_dev_targets_opened': args.phase in ('decisions', 'all')}
    start = time.perf_counter()
    try:
        meta = read(OLD / 'episode_manifest.json')
        partition, report['partition'] = audit_partition(args.root, meta)
        with np.load(OLD / 'contexts.npz', allow_pickle=False) as contexts:
            if args.phase in ('history', 'all'):
                report['history'] = audit_history(args.root, contexts, meta)
            if args.phase in ('decisions', 'all'):
                report['frozen_models'] = audit_frozen_models(args.root, partition, contexts)
                report['decisions'] = audit_decisions(args.root, meta, partition, contexts)
        report['status'] = ('partial_not_accepted' if report.get('history', {}).get('status') == 'partial_not_accepted'
                            else 'passed')
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['runtime_seconds'] = time.perf_counter() - start
        destination.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(json.dumps({'report': str(destination), **report}), flush=True)


if __name__ == '__main__':
    main()
