#!/usr/bin/env python3
"""Independent CPU audit of r2 worker cache, state policies and task decisions.

No GPU/model inference and no calibration/test reader. Each invocation records
its own success, partial result or failure; previous reports are never replaced.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

import joblib
import numpy as np

from introact_ts.v43.agent_inputs import POOL, mask_views, context_scale
from introact_ts.v43.schemas import array_hash
from introact_ts.v431.data import FEATURE_NAMES
from introact_ts.v431.decision_tree import canonical_hash
from introact_ts.v431_r2.policy import EvidenceState, STATE_TOOLS, StatePolicy, supported_rows, freeze_reference
from introact_ts.v431_r2.data import R2Data

ROOT = Path('results/v431-r2')
SPRINT = Path('results/v431/20260914-sprint')
OLD = Path('results/v43/20260914T141030.324186Z-agent')


def read(path):
    return json.loads(Path(path).read_text())


def check(value, reason):
    if not value:
        raise AssertionError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def native_input_hash(x):
    x = np.ascontiguousarray(x)
    return hashlib.sha256(x.dtype.str.encode() + str(x.shape).encode() + x.tobytes()).hexdigest()


def audit_timesfm_cache():
    root = ROOT / 'timesfm-cache'
    request, status = read(root / 'request.json'), read(root / 'status.json')
    check(status['status'] == 'completed', 'TimesFM cache is incomplete')
    check(sha(root / 'request.json') == status['request_sha256'], 'Worker request changed')
    check(sha(root / 'predictions.npz') == status['prediction_sha256'], 'Worker point archive changed')
    for path, expected in request['source_requests'].items():
        check(sha(path) == expected, 'Imported immutable source request changed')
    for path, key in [('scripts/v431_r2_predict.py', 'worker_sha256'),
                      ('scripts/v431_baselines/worker.py', 'backend_source_sha256'),
                      ('logs/v431/baselines/timesfm-preparation.json', 'model_record_sha256')]:
        check(sha(path) == request[key], f'Producer dependency changed: {path}')
    identity = read(root / 'identity.json')
    assets = read('scripts/v431_baselines/asset_manifest.json')['timesfm']
    check(identity['revision'] == assets['revision'], 'TimesFM model revision mismatch')
    check(identity['repo_id'] == assets['repo_id'], 'TimesFM model family mismatch')
    check(identity['weight_sha256'] == assets['verified_sha256'], 'TimesFM weight hash mismatch')
    check(identity['source_commit'] == assets['official_code_commit'], 'TimesFM source revision mismatch')
    actual_source = subprocess.check_output(['git', '-C', '.cache/v431-timesfm-source', 'rev-parse', 'HEAD'], text=True).strip()
    check(actual_source == identity['source_commit'], 'Local TimesFM source checkout changed')
    model_record = read('logs/v431/baselines/timesfm-preparation.json')
    check(sha(Path(model_record['snapshot_path']) / 'model.safetensors') == identity['weight_sha256'], 'Actual TimesFM weights changed')
    meta = read(OLD / 'episode_manifest.json')
    records, calls = read(root / 'records.json'), read(root / 'calls.json')
    check(len(request['rows']) == len(records) == len(calls) == status['rows_done'], 'Dropped/added worker rows')
    raw_points, unique_calls = {}, {}
    for call in calls:
        if call['cache_hit']:
            check(call['cache_key'] in unique_calls and call['seconds'] == 0, 'Invalid forward cache hit')
            continue
        check(call['cache_key'] not in unique_calls, 'Duplicate supposedly unique model call')
        path = root / call['raw_file']
        check(sha(path) == call['raw_sha256'], 'Raw model artifact changed')
        with np.load(path, allow_pickle=False) as raw:
            x, point, quantiles = raw['input'], raw['point'], raw['quantiles']
            check(call['cache_key'] == native_input_hash(x) + ':' + str(call['horizon']), 'Native input/cache identity mismatch')
            check(x.ndim == 3 and x.shape[0] == x.shape[2] == 1, 'Model input geometry changed')
            check(point.shape == (1, call['horizon']), 'Native TimesFM point geometry changed')
            check(quantiles.shape[:2] == point.shape and np.isfinite(quantiles).all() and np.isfinite(point).all(),
                  'Nonfinite or malformed native TimesFM output')
            raw_points[call['cache_key']] = point[0].copy()
        unique_calls[call['cache_key']] = call
    check(len(unique_calls) == status['actual_model_calls'], 'Unique model call count mismatch')
    scope = read(root / 'cost_scope.json')
    overhead = max(0., status['elapsed_seconds'] - sum(c['seconds'] for c in unique_calls.values())) / len(unique_calls)
    np.testing.assert_allclose(scope['allocated_overhead_per_unique_call'], overhead, atol=1e-12)
    indexed, phases, covered = {}, Counter(), defaultdict(set)
    with np.load(root / 'predictions.npz', allow_pickle=False) as points, \
         np.load(OLD / 'contexts.npz', allow_pickle=False) as contexts:
        check(set(points.files) == {r['key'] for r in records}, 'Unexpected point archive keys')
        for q, r, call in zip(request['rows'], records, calls):
            check(all(r[k] == v for k, v in q.items()), 'Record changed source request identity')
            check(r['model_call'] == call, 'Record/call ordering mismatch')
            uid = r['base_uid'];m = meta[uid]
            check(r['phase'] in ('current', 'history') and m['split'] in ('train', 'dev'), 'Unauthorized phase/split')
            check(r['phase'] != 'current' or m['split'] == 'train', 'Current DEV was redundantly regenerated')
            check((r['source'], r['parent_group'], r['horizon']) == (m['source'], m['parent_group'], m['horizon']), 'Source/parent/horizon changed')
            length = 512 if r['phase'] == 'current' else 512 - m['horizon']
            check(sha(r['array_path']) == r['array_sha256'], 'Immutable model input file changed')
            with np.load(r['array_path'], allow_pickle=False) as payload:
                for name, field in [('target', 'input_hash'), ('raw_mask', 'raw_mask_hash'),
                                    ('covariates', 'covariate_hash'), ('timestamps', 'timestamps_hash'),
                                    ('availability', 'availability_hash')]:
                    check(array_hash(payload[name]) == r[field], f'Input {name} hash mismatch')
                x = contexts[uid + '_target'][:length].copy()
                cov = contexts[uid + '_covariates'][:length].copy()
                t = contexts[uid + '_timestamps'][:length]
                available = contexts[uid + '_availability'][:length]
                x[available[:, 0] > t[-1]] = np.nan
                cov[available[:, 1:] > t[-1]] = np.nan
                check(payload['target'].shape == (length,), 'Input was padded/extended across origin')
                np.testing.assert_array_equal(payload['timestamps'], t)
                np.testing.assert_array_equal(payload['availability'], available)
                np.testing.assert_array_equal(payload['covariates'], cov)
                np.testing.assert_array_equal(payload['raw_mask'], np.isfinite(x))
                np.testing.assert_array_equal(payload['target'][np.isfinite(x)], x[np.isfinite(x)])
                check(r['cutoff'] == m['raw_start'] + length, 'Exclusive cutoff mismatch')
                expected_key = native_input_hash(payload['target'][None, :, None]) + ':' + str(m['horizon'])
                check(call['cache_key'] == expected_key, 'Raw model input differs from original request input')
            p = points[r['key']]
            np.testing.assert_array_equal(p, raw_points[call['cache_key']])
            check(array_hash(p) == r['prediction_hash'], 'Stored point prediction hash mismatch')
            price = unique_calls[call['cache_key']]['seconds'] + overhead
            np.testing.assert_allclose(r['charged_seconds'], price, atol=1e-12)
            key = r['phase'], uid, r['input_hash']
            check(key not in indexed, 'Duplicate phase/UID/input hash despite deduplicated source requests')
            indexed[key] = (p.copy(), price)
            phases[r['phase']] += 1;covered[r['phase']].add(m['parent_group'])
    return {'status': 'passed', 'requests': len(records), 'actual_raw_outputs': len(unique_calls),
            'phase_requests': dict(phases), 'phase_parents': {k: len(v) for k, v in covered.items()},
            'native_point_preserved': True, 'quantiles_hash_and_finiteness_verified': True,
            'raw_masks_and_asof_prefixes_verified': True, 'source_model_input_and_revision_verified': True,
            'cross_row_hits_repriced': True, 'offline_process_body_seconds': status['elapsed_seconds']}, indexed


def audit_partition(data):
    partition = read(ROOT / 'partition.json')
    check(partition['metadata'] == data.meta, 'R2 data membership/metadata changed')
    fields = ['fit_parent_ids', 'check_parent_ids', 'acq_parent_ids', 'dev_parent_ids']
    groups = {field: set(partition[field]) for field in fields}
    for a, field in enumerate(fields):
        for other in fields[a + 1:]:
            check(not groups[field] & groups[other], 'A parent appears in multiple train/dev roles')
    for role, field in [('fit', fields[0]), ('T_check', fields[1]), ('T_acq', fields[2]), ('dev', fields[3])]:
        check(groups[field] == set(data.parents[data.ids(role)]), f'Role membership mismatch {role}')
    check([len(groups[f]) for f in fields] == [75, 17, 18, 26], 'Registered role support changed')
    ranges = {}
    for m in data.meta.values():
        key = m['source'], m['parent_group']
        lo, hi = ranges.get(key, (m['raw_start'], m['context_end'] + m['horizon']))
        ranges[key] = min(lo, m['raw_start']), max(hi, m['context_end'] + m['horizon'])
    for source in {k[0] for k in ranges}:
        spans = sorted(v for k, v in ranges.items() if k[0] == source)
        check(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), 'Full 704-row parent intervals overlap')
    nested = {float(k): set(v) for k, v in partition['nested_fit_parent_ids'].items()}
    check(nested[.25] <= nested[.5] <= nested[1.] == groups[fields[0]], 'Learning subsets are not nested')
    check([len(nested[k]) for k in (.25, .5, 1.)] == [18, 37, 75], 'Registered learning-curve parent counts changed')
    check(all(not parents & (groups[fields[1]] | groups[fields[2]]) for parents in nested.values()), 'Check/acq entered a curve fit')
    for role in ('fit', 'T_check', 'T_acq', 'dev'):
        indices = data.ids(role);w = data.weights(indices)
        sources = {data.meta[data.uids[i]]['source'] for i in indices}
        for source in sources:
            loc = [k for k, i in enumerate(indices) if data.meta[data.uids[i]]['source'] == source]
            np.testing.assert_allclose(w[loc].sum(), 1 / len(sources), atol=1e-12)
        for parent in set(data.parents[indices]):
            loc = np.flatnonzero(data.parents[indices] == parent)
            check(len(loc) == 6 and np.allclose(w[loc], w[loc[0]]), 'Variants changed parent mass')
    return {'status': 'passed', 'parents': {k: len(v) for k, v in groups.items()},
            'nested_fit_parents': {str(k): len(v) for k, v in nested.items()},
            'full_raw_ranges_disjoint': True, 'source_parent_weights_verified': True}, nested


def audit_data(data, indexed):
    hist_hashes = read(SPRINT / 'history/candidate_hashes.json')
    views = read(SPRINT / 'history/view_manifest.json')
    old_hcost = read(SPRINT / 'history/tool_costs.json')['target_horizon']
    old_fcost = defaultdict(float)
    for row in read(SPRINT / 'history/model_invoices.json'):
        if row['shard'].startswith('targeth-'):
            old_fcost[row['episode_uid'].split(':asof:', 1)[0]] += row['charged_seconds']
    tf_cost = {(r['episode_uid'], r['arm']): r for r in read(SPRINT / 'timesfm/scored_rows.json')}
    check(sha(SPRINT / 'timesfm/predictions.npz') == read(SPRINT / 'timesfm/status.json')['prediction_file_sha256'], 'Reused DEV TimesFM output changed')
    task_count, alias_count = 0, 0
    with np.load(OLD / 'targets.npz', allow_pickle=False) as targets, \
         np.load(SPRINT / 'timesfm/predictions.npz', allow_pickle=False) as tfdev:
        for i, uid in enumerate(data.uids):
            e = data.episodes[uid]
            y, mask = targets[uid + '_values'], targets[uid + '_mask']
            np.testing.assert_array_equal(mask, np.isfinite(y))
            for arm in POOL:
                if data.meta[uid]['split'] == 'train':
                    pred, charge = indexed['current', uid, array_hash(data.old.pools[uid][arm])]
                else:
                    pred = tfdev[uid + '_' + arm]
                    charge = tf_cost[uid, arm]['total_seconds'] - data.old.direct_costs[uid][arm]
                np.testing.assert_array_equal(data.predictions['timesfm'][uid][arm], pred)
                np.testing.assert_allclose(data.forecast_costs['timesfm'][uid + '_' + arm], charge, atol=1e-12)
                alias_count += 1
                for family in ('bolt', 'timesfm'):
                    p = data.predictions[family][uid][arm]
                    check(np.isfinite(p).all() and mask.any(), 'Failed point or empty scoring mask')
                    mae = float(np.abs(p[mask] - y[mask]).mean())
                    a = POOL.index(arm)
                    np.testing.assert_allclose([data.MAE[family][i, a], data.L[family][i, a]],
                                               [mae, mae / data.scales[e.source]], rtol=1e-12, atol=1e-12)
                    task_count += 1
            r = 512 - e.horizon;hy = e.target[r:r + e.horizon];hm = np.isfinite(hy)
            predictions, fees = {}, {}
            for arm in POOL:
                digest = hist_hashes[views[uid]['full']][arm]
                predictions[arm], fees[digest] = indexed['history', uid, digest]
            if hm.any():
                before = np.abs(predictions['A0_NATIVE'][hm] - hy[hm]).mean()
                evidence = [value for arm in POOL for value in
                            ((before - np.abs(predictions[arm][hm] - hy[hm]).mean()) / context_scale(e), 0., float(hm.mean()))]
            else:
                evidence = [value for arm in POOL for value in (np.nan, np.nan, 0.)]
            np.testing.assert_allclose(data.history['timesfm'][i], evidence, rtol=1e-12, atol=1e-12, equal_nan=True)
            nonforecast = old_hcost[uid] - old_fcost[uid]
            check(nonforecast >= 0, 'History repricing removed more than actual Bolt forecast charges')
            np.testing.assert_allclose(data.tool_costs['timesfm'][uid]['history'], nonforecast + sum(fees.values()), atol=1e-12)
            if data.complete[i]:
                for arm in POOL:
                    np.testing.assert_array_equal(data.old.pools[uid][arm], e.target)
                    for family in ('bolt', 'timesfm'):
                        np.testing.assert_array_equal(data.predictions[family][uid][arm], data.predictions[family][uid]['A0_NATIVE'])
    return {'status': 'passed', 'actual_task_losses_recomputed': task_count,
            'timesfm_current_aliases_verified': alias_count, 'timesfm_history_evidence_rows': len(data.uids),
            'complete_contexts_all_five_inputs_and_predictions_equal_KEEP': int(data.complete.sum())}


def invoice_check(invoice, family, uid, data, diagnostic):
    charges = invoice['charges'];keys = [c['key'] for c in charges]
    check(len(keys) == len(set(keys)), 'A shared computation is double charged')
    for c in charges:
        key, value = c['key'], c['seconds'];parts = key.split(':')
        check(np.isfinite(value) and value >= 0, 'Invalid computation charge')
        if parts[0] == 'candidate':
            check(parts[1] == uid, 'Candidate charge uses another UID')
            expected = data.old.direct_costs[uid][parts[2]]
        elif parts[0] == 'forecast':
            check(parts[1:3] == [family, uid], 'Forecast charge changed family/UID')
            expected = data.forecast_costs[family][uid + '_' + parts[3]]
        elif parts[0] == 'tool':
            check(parts[1:3] == [family, uid], 'Tool charge changed family/UID')
            expected = data.tool_costs[family][uid][parts[3]]
        elif parts[0] == 'diagnostic':
            check(parts[1] == uid, 'Diagnostic charge uses another UID')
            if uid in diagnostic:
                np.testing.assert_allclose(value, diagnostic[uid], atol=0, rtol=0)
            diagnostic[uid] = value
            continue
        elif parts[0] in ('decision', 'initial-selection', 'post-evidence-selection'):
            check(parts[1:3] == [family, uid], 'Selection charge changed family/UID')
            if parts[0] == 'post-evidence-selection':
                check(len(parts) == 4 and parts[3] in STATE_TOOLS, 'Post-evidence selector branch identity changed')
            if parts[0] == 'initial-selection':
                # The same initial choice is shared by immediate STOP and
                # all counterfactual acquisition branches for one request.
                if key in diagnostic:
                    np.testing.assert_allclose(value, diagnostic[key], rtol=0, atol=0)
                diagnostic[key] = value
            continue
        else:
            raise AssertionError('Unknown offline charge identity: ' + key)
        np.testing.assert_allclose(value, expected, rtol=1e-12, atol=1e-12)
    total = float(sum(c['seconds'] for c in charges))
    np.testing.assert_allclose(invoice['total_seconds'], total, atol=1e-12)
    return total


def state_at(data, family, i, kind):
    state = EvidenceState()
    for tool in STATE_TOOLS[kind]:
        state = state.acquire(tool, data.mask[i] if tool == 'mask' else data.history[family][i])
    return state


def audit_models_and_labels(data, nested):
    mf = read(ROOT / 'models_frozen.json');tf = read(ROOT / 'terminal_freeze.json')
    manifest, labels = read(ROOT / 'terminal_manifest.json'), read(ROOT / 'value_labels.json')
    check(sha(ROOT / 'models.joblib') == mf['sha256'], 'Frozen all-model checkpoint changed')
    check(sha(ROOT / 'terminal_models.joblib') == tf['sha256'], 'Frozen terminal checkpoint changed')
    check(sha(ROOT / 'terminal_manifest.json') == mf['terminal_manifest_sha256'], 'Terminal manifest changed after freeze')
    check(sha(ROOT / 'value_labels.json') == mf['value_labels_sha256'], 'Value labels changed after model freeze')
    check(manifest['created_at'] <= tf['created_at'] <= mf['created_at'], 'Freeze timestamps have impossible ordering')
    check((ROOT / 'terminal_freeze.json').stat().st_mtime_ns < (ROOT / 'value_labels.json').stat().st_mtime_ns,
          'Terminal-set freeze did not precede value-label artifact')
    models = joblib.load(ROOT / 'models.joblib');terminal_models = joblib.load(ROOT / 'terminal_models.joblib')
    fit, check_ids, acq = data.ids('fit'), data.ids('T_check'), data.ids('T_acq')
    diagnostic, label_count, state_count = {}, 0, 0
    for family, policy in models['policies'].items():
        fm = manifest['families'][family]
        digest = policy.frozen_hash
        check(digest == tf['terminal_hashes'][family] == fm['terminal_hash'] == terminal_models['policies'][family].frozen_hash,
              'Terminal identity differs across models, freeze and manifest')
        check(canonical_hash(read(ROOT / (family + '.terminal.json'))) == digest, 'Terminal JSON does not describe actual model')
        check(set(policy.training_parent_ids) == set(policy.reference_parent_ids) == nested[1.], 'Terminal/reference fit parents changed')
        ref = freeze_reference(data.L[family][fit], data.weights(fit), data.parents[fit])
        check(ref == fm['reference'] and ref['action'] == policy.reference_action, 'Fixed reference was not chosen only on fit loss')
        identity = policy.training_identity_
        for key, value in [('dirty', data.X[fit]), ('losses', data.L[family][fit]), ('weights', data.weights(fit))]:
            check(array_hash(value) == identity[key], f'Terminal training {key} hash mismatch')
        check(identity['parents'] == canonical_hash(data.parents[fit].tolist()), 'Terminal row parent ordering changed')
        for kind in ('mask', 'history', 'both'):
            audit = policy.audit_[kind];tools = STATE_TOOLS[kind]
            check(audit['tools'] == list(tools), 'State schema contains an unacquired tool')
            E = data.state_evidence(family, fit)
            supported = np.logical_and.reduce([supported_rows(E[t]) for t in tools])
            check(audit['supported_parents'] == len(set(data.parents[fit][supported])), 'State parent support miscount')
            if audit['status'] == 'fitted':
                transform = policy.transforms_[kind]
                check(np.all(transform['columns'] < len(FEATURE_NAMES) + 15 * len(tools)), 'State transform reads another tool group')
                model = policy.models_[kind]
                check(model.max_depth == 3 and model.min_samples_leaf == 96, 'CART rule changed')
                z = np.c_[data.X[fit], *(E[t] for t in tools)][supported]
                v = z[:, transform['columns']]
                design = np.c_[np.where(np.isfinite(v), v, transform['median']), np.isfinite(v)]
                leaves = model.apply(design)
                supports = {str(int(leaf)): len(set(data.parents[fit][supported][leaves == leaf])) for leaf in set(leaves)}
                check(supports == audit['leaf_parent_counts'] and min(supports.values()) >= 16, 'Training leaf parent gate violated')
            state_count += 1
        # An empty state cannot read an unacquired result; each individual state
        # includes only its own 15-column group, not a zeroed second group.
        empty = EvidenceState()
        try:
            empty.result('history')
        except ValueError:
            pass
        else:
            raise AssertionError('Unacquired evidence lookup succeeded')
        aq = models['acquirers'][family]
        check(aq.terminal_hash == digest, 'Acquirer uses stale terminal policy')
        rows = labels[family]
        check(len(rows) == 324 and len({(r['uid'], r['tool']) for r in rows}) == 324, 'Expected 108 T_acq rows x 3 branches')
        for row in rows:
            uid, kind = row['uid'], row['tool'];i = data.uids.index(uid)
            check(data.meta[uid]['v431_role'] == row['role'] == 'T_acq', 'Value label crossed training roles')
            check(row['parent'] == data.parents[i] and row['terminal_hash'] == digest, 'Value label identity changed')
            before = policy.choose(data.X[i], EvidenceState(), fully_observed=data.complete[i])['action']
            after = policy.choose(data.X[i], state_at(data, family, i, kind), fully_observed=data.complete[i])['action']
            gain = data.L[family][i, before] - data.L[family][i, after]
            stop = invoice_check(row['stop_invoice'], family, uid, data, diagnostic)
            acquired = invoice_check(row['acquire_invoice'], family, uid, data, diagnostic)
            tool_cost = invoice_check(row['tool_invoice'], family, uid, data, diagnostic)
            check(row['tools'] == list(STATE_TOOLS[kind]) and row['tool_count'] == len(STATE_TOOLS[kind]) == len(row['tool_invoice']['charges']),
                  'Combined branch did not count every actual tool')
            check(row['acquisition_steps'] == 1, 'Combination incorrectly represented as multiple decisions')
            for name, arm in [('stop_invoice', POOL[before]), ('acquire_invoice', POOL[after])]:
                check(any(c['key'] == f'candidate:{uid}:{arm}' for c in row[name]['charges']), 'Branch cost belongs to another terminal action')
            np.testing.assert_allclose([row['task_gain'], row['delta_cost'], row['stop_cost'], row['acquire_cost'], row['value']],
                                      [gain, acquired - stop, stop, acquired, gain - row['lambda'] * (acquired - stop)],
                                      rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(row['lambda'], aq.lambda_value, rtol=0, atol=0)
            check(tool_cost >= 0, 'Negative tool cost')
            label_count += 1
        for row in aq.report.get('cv_records', []):
            check(row['held_parent'] not in row['train_parents'], 'Price CV parent entered own fit')
            check(set(row['train_parents']) < set(data.parents[acq]), 'Price CV uses another role')
    curves = read(ROOT / 'learning_curves.json')
    check(len(curves) == 24, 'Expected 2 families x 3 support levels x 4 states')
    # Repeat the fixed deterministic small CART rule to check discarded 25/50%
    # curve models too. No model/result is written or selected from check loss.
    for family in models['policies']:
        for fraction in (.25, .5, 1.):
            subset = np.array([i for i in fit if data.parents[i] in nested[fraction]])
            ref = freeze_reference(data.L[family][subset], data.weights(subset), data.parents[subset])
            p = models['policies'][family] if fraction == 1. else StatePolicy(ref['action'], ref['parent_ids'], FEATURE_NAMES).fit(
                data.X[subset], data.state_evidence(family, subset), data.L[family][subset], data.weights(subset), data.parents[subset])
            for kind in ('none', 'mask', 'history', 'both'):
                row = next(r for r in curves if r['family'] == family and r['fraction'] == fraction and r['state'] == kind)
                check(set(row['fit_parent_ids']) == nested[fraction] and row['check_parents'] == 17, 'Curve fit/check support changed')
                check(row['terminal_hash'] == p.frozen_hash, 'Curve model differs from registered deterministic rule')
                acts = np.array([p.choose(data.X[i], state_at(data, family, i, kind), fully_observed=data.complete[i])['action'] for i in check_ids])
                g = data.L[family][check_ids, ref['action']] - data.L[family][check_ids, acts]
                w = data.weights(check_ids)
                np.testing.assert_allclose([row['mase'], row['reference_mase'], row['correct_switch_gain'], row['wrong_switch_loss']],
                                          [w @ data.L[family][check_ids, acts], w @ data.L[family][check_ids, ref['action']],
                                           w @ np.maximum(g, 0), w @ np.maximum(-g, 0)], rtol=1e-12, atol=1e-12)
    return {'status': 'passed', 'families': len(models['policies']), 'visible_state_models_audited': state_count,
            'same_frozen_terminal_value_labels': label_count, 'learning_curve_rows_recomputed': len(curves),
            'terminal_freeze_before_value_labels': True, 'check_never_used_for_training_or_fraction_selection': True}, models, diagnostic


def audit_decisions(data, models, diagnostic):
    rows = read(ROOT / 'decisions.json');table = read(ROOT / 'table.json')
    manifest = read(ROOT / 'terminal_manifest.json')
    ids = defaultdict(list);by = {};stops = 0;agent_count = 0;natural_calls = 0
    for row in rows:
        uid, family = row['episode_uid'], row['family'];i = data.uids.index(uid)
        check(data.meta[uid]['v431_role'] == 'dev', 'Main decision row outside common DEV')
        for field in ('source', 'parent_group', 'horizon', 'condition'):
            check(row[field] == data.meta[uid][field], 'Decision changed frozen task metadata')
        ids[family, row['policy']].append(uid);by[family, row['policy'], uid] = row
        arm = row['arm'];a = POOL.index(arm)
        check(array_hash(data.old.pools[uid][arm]) == row['candidate_hash'], 'Chosen governance input hash mismatch')
        check(array_hash(data.predictions[family][uid][arm]) == row['forecast_hash'], 'Chosen forecast hash mismatch')
        np.testing.assert_allclose([row['mase'], row['mae']], [data.L[family][i, a], data.MAE[family][i, a]], rtol=1e-12, atol=1e-12)
        np.testing.assert_array_equal(row['dirty_features'], data.X[i])
        total = invoice_check(row['invoice'], family, uid, data, diagnostic)
        np.testing.assert_allclose(row['total_seconds'], total, atol=1e-12)
        policy = models['policies'][family];ref = policy.reference_action
        gain = data.L[family][i, ref] - data.L[family][i, a]
        np.testing.assert_allclose([row['net_gain'], row['switch_gain'], row['wrong_switch_loss']],
                                  [gain, max(gain, 0), max(-gain, 0)], atol=1e-12)
        if row.get('budget') is not None:
            check(row['budget_overrun'] == (total > row['budget']), 'Low-budget overrun was hidden')
        if row['policy'].startswith('R2_AGENT_'):
            agent_count += 1
            check(row['terminal_hash'] == policy.frozen_hash == models['acquirers'][family].terminal_hash, 'Deployed stale terminal/acquirer')
            expected_initial = policy.choose(data.X[i], EvidenceState(), fully_observed=data.complete[i])['action']
            if row['branch'] is None:
                stops += 1
                check(a == expected_initial, 'STOP differs from fixed reference/complete KEEP')
                check(row['history'] == [] and row['evidence_hash'] is None and row['tool_count'] == 0, 'STOP exposed a hidden tool')
                check(not any(c['key'].startswith('tool:') for c in row['invoice']['charges']), 'STOP was charged an uncalled tool')
            else:
                natural_calls += 1
                kind = row['branch'];tools = STATE_TOOLS[kind]
                check(row['history'] == list(tools) and row['tool_count'] == len(tools), 'Natural acquisition tool count mismatch')
                action = policy.choose(data.X[i], state_at(data, family, i, kind), fully_observed=data.complete[i])['action']
                check(a == action, 'Acquired branch used another visible-state policy')
            if not data.complete[i]:
                values = {}
                applicable = {'mask': len(mask_views(data.episodes[uid])[0]) == 3, 'history': data.episodes[uid].horizon < 512}
                applicable['both'] = all(applicable.values())
                for kind in ('mask', 'history', 'both'):
                    if applicable[kind] and row['estimated_branch_costs'][kind] <= row['budget'] + 1e-12:
                        value = models['acquirers'][family].predict(data.X[i], kind, policy.frozen_hash)
                        if value is not None:
                            values[kind] = value
                check(values == row['predicted_values'], 'Pre-acquisition value used another evidence/feature state')
                chosen = max(values, key=values.get) if values and max(values.values()) > 0 else None
                check(chosen == row['branch'], 'Positive-value/STOP rule changed')
            else:
                check(row['branch'] is None and a == 0, 'Complete observations triggered governance or evidence')
    dev = {data.uids[i] for i in data.ids('dev')}
    for key, uids in ids.items():
        check(len(uids) == 156 and len(set(uids)) == 156 and set(uids) == dev, f'Changed common policy denominator {key}')
    for row in rows:
        if not row['policy'].startswith('R2_AGENT_') or row['branch'] is not None:
            continue
        f, u = row['family'], row['episode_uid'];budget = row['policy'].removeprefix('R2_AGENT_')
        stop, fixed = by[f, 'FORCE_STOP_' + budget, u], by[f, 'FIXED_REFERENCE', u]
        check(row['candidate_hash'] == stop['candidate_hash'] == fixed['candidate_hash'], 'STOP/fixed-reference input equivalence failed')
        check(row['forecast_hash'] == stop['forecast_hash'] == fixed['forecast_hash'], 'STOP/fixed-reference real prediction equivalence failed')
        np.testing.assert_allclose([row['mase'], stop['mase']], [fixed['mase'], fixed['mase']], atol=1e-12)
    check(len(table) == len(ids), 'Table omitted or duplicated a method')
    for item in table:
        selected = [r for r in rows if (r['family'], r['policy']) == (item['family'], item['policy'])]
        for metric in ('mase', 'mae', 'total_seconds', 'tool_count', 'switch_gain', 'wrong_switch_loss', 'net_gain'):
            sources = {r['source'] for r in selected}
            value = np.mean([np.mean([np.mean([r[metric] for r in selected if r['source'] == s and r['parent_group'] == p])
                                      for p in {r['parent_group'] for r in selected if r['source'] == s}]) for s in sources])
            np.testing.assert_allclose(item[metric], value, rtol=1e-12, atol=1e-12)
    return {'status': 'passed', 'policies': len(ids), 'decision_rows': len(rows), 'common_dev_parents': 26,
            'common_dev_episodes': 156, 'agent_rows': agent_count, 'agent_STOP_rows': stops,
            'natural_acquisition_rows': natural_calls, 'all_agent_rows_STOP': stops == agent_count,
            'STOP_forced_STOP_fixed_reference_inputs_and_forecasts_equal': True,
            'complete_KEEP_equivalence_verified': True, 'recorded_invoice_sums_and_budget_overruns_verified': True,
            'cost_scope': {'status': 'recorded_components_verified_pending_derived_accounting',
                           'not_claimed': 'complete_end_to_end_cost_certification',
                           'pending_main_table_components': ['initial_policy_choose_and_mask_views_applicability',
                                                             'existing_same_evidence_CART_predict'],
                           'value_labels_before_after_selection': 'explicit_measured_charges_verified',
                           'original_models_and_value_labels_preserved': True}}


def audit_accounting():
    """Check the derived ledger only; never reload models/data or repeat raw IO."""
    audit = read(ROOT / 'accounting_audit.json')
    check(audit['status'] == 'passed', 'Producer accounting did not complete')
    original_files = ('models.joblib', 'models_frozen.json', 'terminal_manifest.json',
                      'terminal_freeze.json', 'value_labels.json', 'decisions.json', 'table.json')
    check(set(audit['original_frozen_sha256']) == set(original_files), 'Frozen-artifact preservation list changed')
    for name, digest in audit['original_frozen_sha256'].items():
        check(sha(ROOT / name) == digest, 'Accounting changed frozen artifact: ' + name)
    mf, tf = read(ROOT / 'models_frozen.json'), read(ROOT / 'terminal_freeze.json')
    check(sha(ROOT / 'models.joblib') == mf['sha256'], 'All-model frozen checkpoint changed')
    check(sha(ROOT / 'terminal_models.joblib') == tf['sha256'], 'Terminal-set frozen checkpoint changed')
    for name, key in [('terminal_manifest.json', 'terminal_manifest_sha256'), ('value_labels.json', 'value_labels_sha256')]:
        check(sha(ROOT / name) == mf[key], 'Original freeze does not match preserved ' + name)
    for family, digest in tf['terminal_hashes'].items():
        check(canonical_hash(read(ROOT / (family + '.terminal.json'))) == digest, 'Terminal JSON changed')

    samples = read(ROOT / 'planning_cost_samples.json')
    sample_by = {(r['family'], r['episode_uid']): r for r in samples}
    check(len(samples) == len(sample_by) == 312, 'Expected one timing per family/common DEV UID')
    timing_fields = ('initial_choice_and_admission_seconds', 'existing_cart_selection_seconds')
    for sample in samples:
        check(set(sample) == {'family', 'episode_uid', *timing_fields}, 'Timing sample schema changed')
        check(all(np.isfinite(sample[k]) and sample[k] >= 0 for k in timing_fields), 'Invalid measured planning sample')
    original, rows = read(ROOT / 'decisions.json'), read(ROOT / 'accounted_decisions.json')
    check(len(original) == len(rows) == 4992, 'Derived accounting changed decision denominator')
    keys = lambda r: (r['family'], r['policy'], r['episode_uid'])
    check(len({keys(r) for r in rows}) == len(rows), 'Duplicate derived decision')
    check(set(sample_by) == {(r['family'], r['episode_uid']) for r in rows}, 'Planning samples crossed request support')
    fixed = {'KEEP', 'FIXED_TSICL', 'FIXED_REFERENCE'}
    editable = {'invoice', 'total_seconds', 'budget_overrun'}
    high_budget = read(ROOT / 'terminal_manifest.json')['budgets']['high']
    count, fixed_count, added, transitions = 0, 0, 0., Counter()
    groups = defaultdict(list)
    for old, row in zip(original, rows):
        check(keys(old) == keys(row), 'Derived decisions reordered or substituted a task')
        check({k: v for k, v in old.items() if k not in editable} ==
              {k: v for k, v in row.items() if k not in editable}, 'Accounting changed policy, evidence, predictions or task loss')
        check(row['split'] == row['v431_role'] == 'dev', 'Accounting includes non-DEV request')
        old_charges = {r['key']: r['seconds'] for r in old['invoice']['charges']}
        charges = {r['key']: r['seconds'] for r in row['invoice']['charges']}
        check(len(charges) == len(row['invoice']['charges']), 'Derived invoice double charges an identity')
        check(all(np.isfinite(v) and v >= 0 for v in charges.values()), 'Invalid derived charge')
        check(all(charges.get(k) == v for k, v in old_charges.items()), 'Original charge was removed or modified')
        if row['policy'] in fixed:
            check(row == old, 'Fixed methods were charged unnecessary dirty diagnostics or planning')
            check(not any(k.startswith(('diagnostic:', 'initial-choice-', 'existing-cart-')) for k in charges),
                  'Fixed method acquired an unnecessary feature dependency')
            fixed_count += 1
        else:
            legacy = row['policy'] == 'EXISTING_SAME_EVIDENCE_CART'
            sample = sample_by[row['family'], row['episode_uid']]
            seconds = sample[timing_fields[int(legacy)]]
            prefix = 'existing-cart-selection' if legacy else 'initial-choice-and-admission-preparation'
            key = f"{prefix}:{row['family']}:{row['episode_uid']}"
            check(set(charges) - set(old_charges) == {key}, 'Derived invoice added the wrong planning component')
            check(charges[key] == seconds, 'Recharged planning does not exactly match the measured sample')
            np.testing.assert_allclose(row['total_seconds'] - old['total_seconds'], seconds, rtol=1e-10, atol=1e-12)
            check(row['budget_overrun'] == (row['total_seconds'] > row.get('budget', high_budget) + 1e-12),
                  'Derived actual-cost overrun flag was not recomputed')
            count += 1;added += seconds
        total = float(sum(charges.values()))
        np.testing.assert_allclose([row['total_seconds'], row['invoice']['total_seconds']], [total, total], rtol=1e-12, atol=1e-12)
        transitions[f"{bool(old['budget_overrun'])}->{bool(row['budget_overrun'])}"] += 1
        groups[row['family'], row['policy'], row['source']].append(row)
    check(count == audit['rows_supplemented'] == 4056 and fixed_count == 936, 'Wrong fixed/supplemented method support')
    np.testing.assert_allclose(added, audit['summed_recharged_planning_seconds'], rtol=1e-12, atol=1e-12)

    metrics = ('mase', 'mae', 'total_seconds', 'tool_count', 'switch_gain', 'wrong_switch_loss', 'net_gain')
    expected_detail = {}
    for key, group in groups.items():
        parents = {r['parent_group'] for r in group}
        parent_rows = [[r for r in group if r['parent_group'] == p] for p in parents]
        check(all(len(rs) == 6 for rs in parent_rows), 'Horizon/condition variants changed parent weight')
        item = {metric: float(np.mean([np.mean([r[metric] for r in rs]) for rs in parent_rows])) for metric in metrics}
        item.update(parents=len(parents), episodes=len(group), budget_overruns=sum(r['budget_overrun'] for r in group),
                    failed_tools=sum(r.get('failure') is not None for r in group))
        expected_detail[key] = item
    details = read(ROOT / 'accounted_metrics_by_source.json')
    check(len(details) == len(expected_detail) == 96, 'Derived source table omitted/duplicated groups')
    seen = set()
    for row in details:
        key = row['family'], row['policy'], row['source'];check(key not in seen, 'Duplicated source-summary row');seen.add(key)
        expected = expected_detail[key]
        for field, value in expected.items():
            np.testing.assert_allclose(row[field], value, rtol=1e-12, atol=1e-12)
    table = read(ROOT / 'accounted_table.json')
    check(len(table) == 32, 'Derived main table changed comparison count')
    old_table = {(r['family'], r['policy']): r for r in read(ROOT / 'table.json')}
    seen = set()
    for row in table:
        key = row['family'], row['policy'];check(key not in seen, 'Duplicated main-summary row');seen.add(key)
        detail = [r for k, r in expected_detail.items() if k[:2] == key]
        check((row['parents'], row['episodes'], row['sources']) == (26, 156, 3), 'Derived source-macro denominator changed')
        for metric in metrics:
            np.testing.assert_allclose(row[metric], np.mean([r[metric] for r in detail]), rtol=1e-12, atol=1e-12)
            if metric != 'total_seconds':
                check(row[metric] == old_table[key][metric], 'Accounting altered a reported task-effectiveness metric')
        check(row['budget_overruns'] == sum(r['budget_overruns'] for r in detail), 'Main-table overruns are stale')
        check(row['failures'] == sum(r['failed_tools'] for r in detail), 'Accounting dropped a failed method')

    previous = [(p, read(p)) for p in sorted((ROOT / 'verification').glob('*.json'))]
    passed = [(p, result) for p, result in previous if result.get('phase') == 'all' and result.get('status') == 'passed']
    check(bool(passed), 'Independent full raw/model/task audit must precede accounting-only certification')
    prior_path, prior = passed[-1]
    return {'status': 'passed', 'original_rows': len(original), 'derived_rows': len(rows),
            'fixed_rows_unchanged': fixed_count, 'rows_supplemented': count, 'timing_requests': len(samples),
            'measured_planning_seconds_once': sum(s[k] for s in samples for k in timing_fields),
            'summed_recharged_planning_seconds': added, 'budget_flag_transitions': dict(transitions),
            'source_rows_recomputed': len(details), 'main_rows_recomputed': len(table),
            'original_model_labels_predictions_actions_and_effectiveness_unchanged': True,
            'prior_full_audit': str(prior_path), 'prior_full_audit_sha256': sha(prior_path),
            'derived_artifact_sha256': {name: sha(ROOT / name) for name in
                ('accounted_decisions.json', 'accounted_table.json', 'accounted_metrics_by_source.json',
                 'planning_cost_samples.json', 'accounting_audit.json')},
            'cost_scope': {'status': 'prior_missing_batch_planning_components_resolved',
                           'deployment_cost': 'stored actual candidate/tool/forecast costs plus measured diagnostic, decision and planning components',
                           'measurement_limit': 'planning timings are a separate equivalent CPU replay, shared across comparison rows; not an original request wall-clock trace',
                           'online_latency': 'cold startup and complete worker process accounting remain separate online artifacts',
                           'offline_costs': 'training, dataset IO, verification and cache generation remain separate; no experiment cost erased'}}


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--phase', choices=('cache', 'all', 'accounting'), default='all')
    phase = parser.parse_args().phase
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    output = ROOT / 'verification' / (stamp + '.json');output.parent.mkdir(exist_ok=True)
    start = time.perf_counter()
    report = {'status': 'running', 'phase': phase, 'started_at': stamp,
              'verifier_sha256': sha(__file__), 'heldout_labels_read': 0,
              'evaluator_uses_archived_train_dev_targets': phase == 'all'}
    try:
        if phase == 'accounting':
            report['derived_accounting'] = audit_accounting()
        else:
            report['timesfm_cache'], indexed = audit_timesfm_cache()
        if phase == 'all':
            check(read(ROOT / 'status.json')['status'] == 'completed', 'R2 fit/evaluation is incomplete')
            data = R2Data()
            report['partition'], nested = audit_partition(data)
            report['data_and_actual_tasks'] = audit_data(data, indexed)
            report['models_and_labels'], models, diagnostic = audit_models_and_labels(data, nested)
            report['common_decisions'] = audit_decisions(data, models, diagnostic)
        report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['runtime_seconds'] = time.perf_counter() - start
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(json.dumps({'report': str(output), **report}), flush=True)


if __name__ == '__main__':
    main()
