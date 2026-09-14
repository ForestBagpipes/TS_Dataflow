#!/usr/bin/env python3
"""Freeze TRAIN-only references and fit/evaluate the r3 response strategy."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from types import SimpleNamespace

import joblib
import numpy as np

from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.cli import atomic_json
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import array_hash, Episode
from introact_ts.v431.acquisition import Charge, CostInvoice, AcquiredBranch
from introact_ts.v431.data import FEATURE_NAMES, dirty_features, PERIODS, source_parent_weights
from introact_ts.v431.decision_tree import canonical_hash
from introact_ts.v431_r2.data import R2Data
from introact_ts.v431_r2.policy import freeze_reference
from introact_ts.v431_r3.response import (ResponsePolicy, ResponseEvidence, PSI_NAMES, STATE_PRIMITIVES,
                                         state_from_results, historical_argmax)
from introact_ts.v431_r3.acquisition import (ACTIVE_BRANCHES, BRANCH_TOOLS, build_value_row,
                                            fit_acquirer, make_value_labels, execute_one_step)


def read(path):
    return json.loads(Path(path).read_text())


def invoice(payload):
    result = CostInvoice(tuple(Charge(**charge) for charge in payload['charges']))
    assert np.isclose(result.total_seconds, payload['total_seconds'], rtol=0, atol=1e-10), 'Probe invoice differs from charges'
    return result


def load_probe_ledger(root, family, required_uids, suite_name='main'):
    """Only complete producer sessions; metadata-unsupported probes remain explicit."""
    suite = root / 'probes' / suite_name
    prepared = read(suite / 'probe_manifest.json')
    required_uids = set(required_uids)
    specs = {(r['base_uid'], r['spec']['name']): r for r in prepared if r['base_uid'] in required_uids}
    assert len(specs) == len(required_uids)*4, 'Requested current contexts not in frozen probe metadata'
    index, sources = {}, {}
    for key, row in specs.items():
        if row['status'] == 'unsupported':
            charge = Charge('probe-prepare:'+row['input_hash'], row['preparation_seconds'])
            index[key] = {**row, 'probe': row['spec']['name'], 'family': family, 'metadata_status': row['status'],
                          'invoice': CostInvoice((charge,)).as_dict()}
    for status_path in sorted((suite / 'sessions').glob('*/status.json')):
        status = read(status_path)
        if status.get('status') != 'completed' or status.get('family') != family:
            continue
        path = status_path.with_name('records.json')
        assert file_hash(path) == status['records_sha256'], 'Completed probe session changed'
        sources[str(path)] = file_hash(path)
        for row in read(path):
            key = (row['base_uid'], row['probe'])
            if key not in specs:
                continue
            assert row['input_hash'] == specs[key]['input_hash'], 'Probe input differs from preregistered metadata'
            if key in index and index[key]['status'] == 'completed':
                assert row['status'] == 'completed' and row['mae'] == index[key]['mae'], 'Two completed probe values disagree'
                continue  # Retain first actual accounting; later reuse is a separate offline cost.
            index[key] = {**row, 'metadata_status': specs[key]['status']}
    missing = [key for key in specs if key not in index]
    if missing:
        raise RuntimeError(f'{family}: {len(missing)} required actual probes remain uncollected; first={missing[:3]}')
    return index, sources


class EvidenceBatches(dict):
    def __init__(self):
        super().__init__({state: [] for state in STATE_PRIMITIVES})
        self.projection_invoices = {}


def state_batches(data, indices, ledger, reference_arm, *, rebase_reference=False):
    output = EvidenceBatches()
    for i in indices:
        u = data.uids[i]
        atoms = {k: ledger[u, k] for k in ('h32', 'long', 'short', 'second')}
        if rebase_reference:
            atoms = {k: ({**a, 'reference_arm': reference_arm,
                        'gain': {arm: (a['mae'][reference_arm]-a['mae'][arm])/a['current_scale'] for arm in POOL}}
                         if a['status'] == 'completed' else a) for k, a in atoms.items()}
        for state in STATE_PRIMITIVES:
            tick = time.perf_counter()
            output[state].append(state_from_results(state, atoms, reference_arm=reference_arm))
            output.projection_invoices[u, state] = CostInvoice((Charge('state-projection:'+ledger[u, 'long']['family']+':'+u+':'+state,
                                                                       time.perf_counter()-tick),))
    return output


def tool_invoice(ledger, uid, state, projections=None):
    return CostInvoice().merge(*(invoice(ledger[uid, atom]['invoice']) for atom in STATE_PRIMITIVES[state]),
                               CostInvoice() if projections is None else projections[uid, state])


def metadata_applicable(ledger, uid, state):
    return all(ledger[uid, atom]['metadata_status'] == 'prepared' for atom in STATE_PRIMITIVES[state])


def exact_roles(data):
    result = {r: np.flatnonzero(data.roles == r) for r in ('T_fit', 'T_gate', 'T_check', 'T_acq', 'dev')}
    expected = {'T_fit': 54, 'T_gate': 21, 'T_check': 17, 'T_acq': 18, 'dev': 26}
    for role, indices in result.items():
        assert len(set(data.parents[indices])) == expected[role], 'Original parent partition changed'
    keys = list(result)
    for a, left in enumerate(keys):
        for right in keys[a+1:]:
            assert not set(data.parents[result[left]]) & set(data.parents[result[right]]), 'Parent isolation broken'
    assert all('position358' not in data.meta[u]['condition'] for u in data.uids), 'New check-only combination entered original fit data'
    return result


def freeze_references(root, data=None):
    path = root / 'reference_manifest.json'
    if path.exists():
        return json.loads(path.read_text())
    data = R2Data() if data is None else data
    selected = np.flatnonzero(np.isin(data.roles, ['T_fit', 'T_gate']))
    assert set(data.roles[selected]) == {'T_fit', 'T_gate'}
    assert not set(data.parents[selected]) & set(data.parents[np.isin(data.roles, ['T_check', 'T_acq', 'dev'])])
    result = {'version': 'v4.3.1-r3', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'reference_training_roles': ['T_fit', 'T_gate'],
              'state_model_fit_role': 'T_fit', 'alpha_selection_role': 'T_gate',
              'fitting_parent_count': len(set(data.parents[selected])),
              'feature_or_hyperparameter_selection_on_dev': False,
              'new_probe_results_consulted': False, 'families': {},
              'script_sha256': file_hash(__file__)}
    for family in ('bolt', 'timesfm'):
        result['families'][family] = freeze_reference(data.L[family][selected], data.weights(selected), data.parents[selected])
    result['reference_hash'] = canonical_hash(result['families'])
    root.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    return result


def fit_models(root):
    assert not (root/'terminal_manifest.json').exists(), 'Never overwrite a frozen r3 terminal set'
    begun = time.perf_counter()
    config_path = Path('configs/v431_r3/manifest.json')
    config = read(config_path)
    assert config['tools'] == list(ACTIVE_BRANCHES)
    assert config['ridge_alphas'] == [.1, 1, 10]
    data = R2Data(); roles = exact_roles(data)
    fit, gate, acq = (roles[r] for r in ('T_fit', 'T_gate', 'T_acq'))
    references = freeze_references(root, data)
    manifest = {'version': 'v4.3.1-r3', 'created_utc': datetime.now(timezone.utc).isoformat(),
                'reference_hash': references['reference_hash'], 'config_sha256': file_hash(config_path),
                'budgets': config['budgets'], 'families': {}, 'psi_names': list(PSI_NAMES),
                'state_primitives': STATE_PRIMITIVES, 'active_tools': list(ACTIVE_BRANCHES),
                'mechanism_controls': ['equal-cost', 'disagreement'],
                'disagreement': 'mean_time population std of actual same-family long/short raw forecasts / current S_t; no length factor; no validation label needed',
                'disagreement_registration_correction': 'source audit before response-model fitting and r3 DEV policy evaluation; train throughput probes may already exist',
                'fit_parent_ids': sorted(set(data.parents[fit])), 'gate_parent_ids': sorted(set(data.parents[gate])),
                'check_parent_ids': sorted(set(data.parents[roles['T_check']])), 'acq_parent_ids': sorted(set(data.parents[acq])),
                'source_hashes': {p: file_hash(p) for p in ('src/introact_ts/v431_r3/response.py',
                    'src/introact_ts/v431_r3/acquisition.py', 'src/introact_ts/v431_r3/probe.py', 'scripts/v431_r3_fit.py')},
                'new_check_combination': config['generalization'], 'heldout_labels_read': 0, 'dev_results_consulted_for_fit': False}
    policies, acquirers, ledgers, evidence_all, preparation_sources = {}, {}, {}, {}, {}
    pairs, projection_records = [], []
    # Fit/gate/acq loaded before new check or DEV probes are ever evaluated.
    relevant = np.r_[fit, gate, acq]
    for family in ('bolt', 'timesfm'):
        ledger, provenance = load_probe_ledger(root, family, [data.uids[i] for i in relevant])
        ledgers[family], preparation_sources[family] = ledger, provenance
        ref = references['families'][family]
        # Recheck the already frozen reference using only its original 75 parents.
        reference_indices = np.flatnonzero(np.isin(data.roles, ['T_fit', 'T_gate']))
        frozen_again = freeze_reference(data.L[family][reference_indices], data.weights(reference_indices), data.parents[reference_indices])
        assert canonical_hash(frozen_again) == canonical_hash(ref), 'Reference training data changed'
        E = {role: state_batches(data, roles[role], ledger, ref['arm']) for role in ('T_fit', 'T_gate', 'T_acq')}
        evidence_all[family] = E
        family_pairs = []
        for role, es in E.items():
            ids, weights = roles[role], data.weights(roles[role])
            for j, i in enumerate(ids):
                u = data.uids[i]
                assert data.meta[u]['split'] == 'train'
                for state in STATE_PRIMITIVES:
                    e = es[state][j]
                    record = {'family': family, 'uid': u, 'parent': str(data.parents[i]), 'role': role,
                        'split': 'train', 'state': state, 'status': e.status, 'reason': e.reason,
                        'evidence_hash': e.identity_hash, 'scale': data.scales[data.meta[u]['source']],
                        'raw_historical_mae': {a: ledger[u, a].get('mae') or None for a in STATE_PRIMITIVES[state]},
                        'd': e.d, 'extra': e.extra, 'psi': e.psi,
                        'current_actual_delta': (data.L[family][i, ref['action']]-data.L[family][i]).tolist(),
                        'current_five_losses': data.L[family][i].tolist(), 'reference_arm': ref['arm'],
                        'source_parent_weight': float(weights[j]), 'source': data.meta[u]['source'],
                        'target_hash': data.old.labels[u, POOL[0]]['future_hash'],
                        'scoring_mask_hash': data.old.labels[u, POOL[0]]['mask_hash']}
                    family_pairs.append(record)
                    projection_records.append({'family': family, 'uid': u, 'state': state,
                                               'invoice': es.projection_invoices[u, state].as_dict(), 'role': role})
        pairs.extend(family_pairs)
        policies[family] = {}
        for estimator in ('residual', 'direct', 'cart'):
            p = ResponsePolicy(ref['action'], ref['parent_ids'], FEATURE_NAMES, PSI_NAMES, estimator)
            p.fit(E['T_fit'], data.L[family][fit], data.weights(fit), data.parents[fit],
                  gate_evidence=E['T_gate'], gate_losses=data.L[family][gate],
                  gate_weights=data.weights(gate), gate_parents=data.parents[gate])
            p.training_identity_['proxy_target_pair_fit_gate_hash'] = canonical_hash([r for r in family_pairs if r['role'] in ('T_fit', 'T_gate')])
            policies[family][estimator] = p
        p = policies[family]['residual']
        estimates = {}
        for state in STATE_PRIMITIVES:
            values = []
            for ids, es in ((fit, E['T_fit']), (gate, E['T_gate'])):
                for j, i in enumerate(ids):
                    if es[state][j].status == 'completed':
                        values.append(tool_invoice(ledger, data.uids[i], state, es.projection_invoices).total_seconds+
                                      max(data.final_invoice(family, i, a, True).total_seconds for a in range(5)))
            if values:
                estimates[state] = float(np.quantile(values, .95))*1.1
        action_estimates = {a: float(np.quantile([data.final_invoice(family, i, k, True).total_seconds
                                                  for i in np.r_[fit, gate]], .95))*1.1 for k, a in enumerate(POOL)}
        fixed, fixed_risks = {}, {}
        for budget_name, budget in config['budgets'].items():
            risks = {}
            for state in ACTIVE_BRANCHES:
                if estimates.get(state, float('inf')) > budget:
                    continue
                acts = [p.choose(data.X[i], E['T_gate'][state][j], fully_observed=bool(data.complete[i]))['action'] for j, i in enumerate(gate)]
                risks[state] = float(np.dot(data.weights(gate), data.L[family][gate, acts]))
            fixed[budget_name] = min(risks, key=risks.get) if risks else None
            fixed_risks[budget_name] = risks
        manifest['families'][family] = {'terminal_hash': p.frozen_hash,
            'terminal_hashes': {k: v.frozen_hash for k, v in policies[family].items()}, 'reference': ref,
            'branch_estimates': estimates, 'action_estimates': action_estimates, 'fixed_state': fixed,
            'gate_fixed_tool_risks': fixed_risks, 'state_support': {k: v.audit_ for k, v in policies[family].items()}}
    atomic_json(root/'proxy_target_pairs.json', pairs)
    atomic_json(root/'training_projection_costs.json', projection_records)
    manifest['proxy_target_pairs_sha256'] = file_hash(root/'proxy_target_pairs.json')
    manifest['training_projection_costs_sha256'] = file_hash(root/'training_projection_costs.json')
    atomic_json(root/'terminal_manifest.json', manifest)
    atomic_json(root/'probe_training_sources.json', preparation_sources)
    joblib.dump({'policies': policies}, root/'terminal_models.joblib')
    atomic_json(root/'terminal_freeze.json', {'created_utc': datetime.now(timezone.utc).isoformat(),
        'sha256': file_hash(root/'terminal_models.joblib'), 'terminal_manifest_sha256': file_hash(root/'terminal_manifest.json'),
        'terminal_hashes': {f: {k: p.frozen_hash for k, p in ps.items()} for f, ps in policies.items()}})
    # Only after that immutable terminal-set freeze may independent T_acq labels be generated.
    all_labels, label_provenance = {}, {}
    for family in policies:
        p, E, ledger = policies[family]['residual'], evidence_all[family]['T_acq'], ledgers[family]
        items, skipped, provenance = [], [], []
        w = data.weights(acq)
        for j, i in enumerate(acq):
            u = data.uids[i]
            tick = time.perf_counter(); before = p.choose(data.X[i], fully_observed=bool(data.complete[i]))
            metadata_support = {s: metadata_applicable(ledger, u, s) for s in ACTIVE_BRANCHES}
            current_estimates = {s: CostInvoice((Charge('estimated-complete:'+s, v),)) for s, v in manifest['families'][family]['branch_estimates'].items() if s in ACTIVE_BRANCHES}
            initial = CostInvoice((Charge('initial-response:'+family+':'+u, time.perf_counter()-tick),))
            for state in ACTIVE_BRANCHES:
                e = E[state][j]
                if not metadata_support[state]:
                    skipped.append({'uid': u, 'tool': state, 'reason': e.reason, 'status': 'metadata_unsupported_not_an_acquisition_label'})
                    continue
                tick = time.perf_counter(); after = p.choose(data.X[i], e, fully_observed=bool(data.complete[i]))
                selection = CostInvoice((Charge('after-response:'+family+':'+u+':'+state, time.perf_counter()-tick),))
                tools = {a: invoice(ledger[u, a]['invoice']) for a in BRANCH_TOOLS[state]}
                tools[BRANCH_TOOLS[state][0]] = tools[BRANCH_TOOLS[state][0]].merge(E.projection_invoices[u, state])
                items.append(build_value_row(uid=u, parent=data.parents[i], policy=p, dirty_features=data.X[i], losses=data.L[family][i],
                    after_state=e, stop_invoice=data.final_invoice(family, i, before['action'], True).merge(initial),
                    acquire_invoice=data.final_invoice(family, i, after['action'], True).merge(initial, selection, *tools.values()),
                    tool_invoices=tools, weight=float(w[j]), fully_observed=bool(data.complete[i])))
                provenance.append({'uid': u, 'parent': str(data.parents[i]), 'role': 'T_acq', 'tool': state,
                    'stop_action': before['action'], 'acquire_action': after['action'],
                    'stop_loss': float(data.L[family][i, before['action']]), 'acquire_loss': float(data.L[family][i, after['action']]),
                    'five_losses': data.L[family][i].tolist(), 'dirty_features': [float(v) if np.isfinite(v) else None for v in data.X[i]],
                    'dirty_features_hash': array_hash(data.X[i]), 'after_state': asdict(e), 'source_parent_weight': float(w[j]),
                    'fully_observed': bool(data.complete[i]), 'terminal_freeze_sha256': file_hash(root/'terminal_freeze.json'),
                    'before_terminal_hash': p.frozen_hash, 'after_terminal_hash': p.frozen_hash,
                    'metadata_applicable': metadata_support, 'branch_estimates': {s: v.as_dict() for s, v in current_estimates.items()}})
        ref = manifest['families'][family]['reference']['action']
        aq = fit_acquirer(items, p.frozen_hash, FEATURE_NAMES,
            task_differences=(data.L[family][fit]-data.L[family][fit, ref, None]).ravel(),
            forbidden_parents=set(data.parents[np.r_[fit, gate, roles['T_check']]]))
        acquirers[family] = aq
        all_labels[family] = make_value_labels(items, p.frozen_hash, aq.lambda_value)
        label_provenance[family] = provenance
        atomic_json(root/(family+'.acquisition.json'), {'model': aq.report, 'unsupported_rows_skipped': skipped})
    atomic_json(root/'value_labels.json', all_labels)
    atomic_json(root/'label_provenance.json', label_provenance)
    joblib.dump({'policies': policies, 'acquirers': acquirers}, root/'models.joblib')
    atomic_json(root/'models_frozen.json', {'created_utc': datetime.now(timezone.utc).isoformat(),
        'sha256': file_hash(root/'models.joblib'), 'terminal_manifest_sha256': file_hash(root/'terminal_manifest.json'),
        'value_labels_sha256': file_hash(root/'value_labels.json'), 'label_provenance_sha256': file_hash(root/'label_provenance.json'),
        'proxy_target_pairs_sha256': file_hash(root/'proxy_target_pairs.json'), 'stage': 'frozen_before_r3_check_and_dev'})
    atomic_json(root/'fit_status.json', {'status': 'completed', 'elapsed_seconds': time.perf_counter()-begun,
                'heldout_labels_read': 0, 'new_check_or_dev_tuning': False,
                'parents': {r: len(set(data.parents[v])) for r, v in roles.items()}})
    print(json.dumps(read(root/'fit_status.json')), flush=True)


def summarize(rows):
    """Source macro, then independent parent, then its equally weighted variants."""
    groups = defaultdict(list)
    for r in rows:
        groups[r['family'], r['policy'], r['source'], r['parent_group']].append(r)
    columns = ('mase', 'mae', 'total_seconds', 'tool_count', 'switch_gain', 'wrong_switch_loss', 'net_gain')
    parents = []
    for (f, p, s, parent), group in groups.items():
        assert len({r['episode_uid'] for r in group}) == len(group), 'Repeated common episode changed denominator'
        parents.append({'family': f, 'policy': p, 'source': s, 'parent_group': parent,
                        'episodes': len(group), 'budget_overruns': sum(r['budget_overrun'] for r in group),
                        **{k: float(np.mean([r[k] for r in group])) for k in columns}})
    sources = []
    for f, p, s in sorted({(r['family'], r['policy'], r['source']) for r in parents}):
        group = [r for r in parents if (r['family'], r['policy'], r['source']) == (f, p, s)]
        sources.append({'family': f, 'policy': p, 'source': s, 'parents': len(group),
                        'episodes': sum(r['episodes'] for r in group), 'budget_overruns': sum(r['budget_overruns'] for r in group),
                        **{k: float(np.mean([r[k] for r in group])) for k in columns}})
    table = []
    for f, p in sorted({(r['family'], r['policy']) for r in sources}):
        group = [r for r in sources if (r['family'], r['policy']) == (f, p)]
        table.append({'family': f, 'policy': p, 'sources': len(group), 'parents': sum(r['parents'] for r in group),
                      'episodes': sum(r['episodes'] for r in group), 'budget_overruns': sum(r['budget_overruns'] for r in group),
                      **{k: float(np.mean([r[k] for r in group])) for k in columns}})
    return table, sources


def frozen_models(root):
    frozen = read(root/'models_frozen.json')
    assert file_hash(root/'models.joblib') == frozen['sha256'], 'Frozen models changed'
    assert file_hash(root/'terminal_manifest.json') == frozen['terminal_manifest_sha256'], 'Terminal manifest changed'
    assert file_hash(root/'value_labels.json') == frozen['value_labels_sha256'], 'Acquisition labels changed'
    assert file_hash(root/'label_provenance.json') == frozen['label_provenance_sha256'], 'Acquisition replay provenance changed'
    assert file_hash(root/'proxy_target_pairs.json') == frozen['proxy_target_pairs_sha256'], 'Training pair binding changed'
    manifest = read(root/'terminal_manifest.json')
    for path, digest in manifest['source_hashes'].items():
        assert file_hash(path) == digest, 'Executed source differs from terminal freeze: '+path
    models = joblib.load(root/'models.joblib')
    for f, family in models['policies'].items():
        for name, policy in family.items():
            assert policy.frozen_hash == manifest['families'][f]['terminal_hashes'][name], 'Terminal state hash changed'
    return models, manifest


def evaluate_data(root, data, indices, *, prefix='', ledger_root=None, probe_suite='main'):
    """Frozen evaluation for original DEV/check or an audited check-only adapter.

    The adapter exposes R2Data's uid/meta/X/complete/L/MAE/final_invoice contract.
    New-combination adapters must use only the predeclared T_check parent IDs.
    They never enter fit_models, references, alpha selection or acquisition fit.
    """
    assert not (root/(prefix+'decisions.json')).exists(), 'Keep existing evaluation immutable'
    models, manifest = frozen_models(root)
    begun = time.perf_counter(); rows, mechanism, support, provenance, projection_records = [], [], [], {}, []
    for family in ('bolt', 'timesfm'):
        ps = models['policies'][family]; policy, acquirer = ps['residual'], models['acquirers'][family]
        fm = manifest['families'][family]; reference = fm['reference']['action']
        assert set(data.parents[indices]) <= set(manifest['check_parent_ids']) if prefix.startswith('new_combination') else True
        ledger, provenance[family] = load_probe_ledger(root if ledger_root is None else ledger_root, family,
                                                      [data.uids[i] for i in indices], probe_suite)
        E = state_batches(data, indices, ledger, POOL[reference])
        projection_records.extend({'family': family, 'uid': uid, 'state': state, 'invoice': inv.as_dict()}
                                  for (uid, state), inv in E.projection_invoices.items())
        for state in STATE_PRIMITIVES:
            supported = [j for j in range(len(indices)) if E[state][j].status == 'completed']
            support.append({'family': family, 'state': state, 'rows': len(indices), 'supported_rows': len(supported),
                            'supported_parents': len({data.parents[indices[j]] for j in supported}),
                            'unsupported_rows': [{'uid': data.uids[indices[j]], 'reason': E[state][j].reason}
                                                 for j in range(len(indices)) if j not in supported]})
        for j, i in enumerate(indices):
            uid = data.uids[i]; complete = bool(data.complete[i])
            base_start = time.perf_counter(); initial = policy.choose(data.X[i], fully_observed=complete)
            applicable = {state: metadata_applicable(ledger, uid, state) and not complete for state in STATE_PRIMITIVES}
            estimates = {s: CostInvoice((Charge('estimated-complete:'+s, v),)) for s, v in fm['branch_estimates'].items() if s in ACTIVE_BRANCHES}
            initial_invoice = CostInvoice((Charge('initial-response:'+family+':'+uid, time.perf_counter()-base_start),))
            stop = initial['action']
            def final(a, with_diagnostic=True):
                return data.final_invoice(family, i, int(a), with_diagnostic)
            def save(name, a, cost, *, tool_count=0, requested_state=None, actual_state=None,
                     budget=None, status='COMMIT', excluded=None, estimated_gains=None, **extra):
                gain = float(data.L[family][i, reference]-data.L[family][i, a])
                meta = data.meta[uid]
                row = {'family': family, 'policy': name, 'episode_uid': uid,
                       **{k: meta[k] for k in ('source', 'parent_group', 'horizon', 'condition', 'split')},
                       'arm': POOL[a], 'reference_arm': POOL[reference],
                       'mase': float(data.L[family][i, a]), 'mae': float(data.MAE[family][i, a]),
                       'total_seconds': cost.total_seconds, 'invoice': cost.as_dict(), 'tool_count': tool_count,
                       'switch_gain': max(gain, 0.), 'wrong_switch_loss': max(-gain, 0.), 'net_gain': gain,
                       'requested_state': requested_state, 'actual_state': actual_state, 'budget': budget,
                       'budget_overrun': budget is not None and cost.total_seconds > budget,
                       'status': status, 'excluded': excluded, 'estimated_gains': estimated_gains,
                       'fully_observed': complete, 'terminal_hash': policy.frozen_hash, **extra}
                if hasattr(data, 'predictions'):
                    row['forecast_hash'] = array_hash(data.predictions[family][uid][POOL[a]])
                if hasattr(data, 'old'):
                    row['candidate_hash'] = array_hash(data.old.pools[uid][POOL[a]])
                rows.append(row)
            for a in range(5):
                save('KEEP' if a == 0 else 'FIXED_TSICL' if a == 2 else 'FIXED_'+POOL[a], a, final(a, False))
            save('FIXED_REFERENCE', reference if not complete else 0, final(reference if not complete else 0, False))
            save('FORCE_STOP', stop, final(stop).merge(initial_invoice), actual_state='none', status='STOP')
            # All full-coverage methods include unsupported/failure fallback windows.
            for state in STATE_PRIMITIVES:
                e = E[state][j]
                for estimator, p in ps.items():
                    for bn, budget in manifest['budgets'].items():
                        valid = applicable[state] and fm['branch_estimates'].get(state, float('inf')) <= budget
                        tick = time.perf_counter()
                        result = p.choose(data.X[i], e if valid else None, fully_observed=complete)
                        selection = CostInvoice((Charge('selection:'+family+':'+uid+':'+estimator+':'+state, time.perf_counter()-tick),))
                        cost = final(result['action']).merge(selection, initial_invoice,
                            tool_invoice(ledger, uid, state, E.projection_invoices) if valid else CostInvoice())
                        save(estimator.upper()+'_'+state+'_'+bn, result['action'], cost,
                             tool_count=len(STATE_PRIMITIVES[state]) if valid else 0, requested_state=state,
                             actual_state=state if valid else 'none', budget=budget,
                             status=result['status'] if valid else 'metadata_or_budget_STOP',
                             excluded=None if valid else 'fully_observed' if complete else e.reason if not applicable[state] else 'complete_branch_budget',
                             estimated_gains=result['estimated_gains'], policy_terminal_hash=p.frozen_hash)
                if e.status == 'completed':
                    current_gain = data.L[family][i, reference]-data.L[family][i]
                    measured = np.asarray(e.d)
                    mapped = ps['residual'].choose(data.X[i], e, fully_observed=complete)
                    mechanism.append({'family': family, 'episode_uid': uid, 'source': data.meta[uid]['source'],
                        'parent_group': data.parents[i], 'horizon': data.meta[uid]['horizon'], 'condition': data.meta[uid]['condition'],
                        'state': state, 'measured_gain': measured.tolist(), 'current_task_gain': current_gain.tolist(),
                        'extra': e.extra, 'psi': e.psi, 'mapped_gain': mapped['estimated_gains'],
                        'zero_measured_arms': int(np.sum(measured == 0)), 'zero_current_arms': int(np.sum(current_gain == 0)),
                        'nonreference_sign_agreement': [bool(np.sign(measured[a]) == np.sign(current_gain[a])) for a in range(5) if a != reference],
                        'reference_arm': POOL[reference], 'actual_evidence_hash': e.evidence_hash,
                        'joint_control_equalcost_support': E['control'][j].status == E['equal-cost'][j].status == 'completed'})
            for state in ('H32', 'H'):
                for bn, budget in manifest['budgets'].items():
                    valid = applicable[state] and fm['branch_estimates'].get(state, float('inf')) <= budget
                    tick = time.perf_counter(); action = historical_argmax(reference, E[state][j] if valid else None, fully_observed=complete)
                    cost = final(action).merge(initial_invoice, CostInvoice((Charge('raw-history-rule:'+family+':'+uid+':'+state, time.perf_counter()-tick),)),
                                               tool_invoice(ledger, uid, state, E.projection_invoices) if valid else CostInvoice())
                    save('HISTORICAL_ARGMAX_'+state+'_'+bn, action, cost, budget=budget,
                         tool_count=int(valid), requested_state=state, actual_state=state if valid else 'none')
            fetch_elapsed = [0.]
            def fetch(state):
                tick = time.perf_counter(); result = policy.choose(data.X[i], E[state][j], fully_observed=complete)
                cost = final(result['action']).merge(initial_invoice, tool_invoice(ledger, uid, state, E.projection_invoices))
                cost = cost.merge(CostInvoice((Charge('post-response:'+family+':'+uid+':'+state, time.perf_counter()-tick),)))
                fetch_elapsed[0] += time.perf_counter()-tick
                return AcquiredBranch(result['arm'], cost, E[state][j].evidence_hash, policy.frozen_hash)
            for bn, budget in manifest['budgets'].items():
                fixed = fm['fixed_state'][bn]
                for name, mode, order in (('R3_AGENT', 'learned', None), ('R3_RANDOM', 'random', None),
                                           ('R3_FIXED_TOOL', 'fixed' if fixed else 'stop', None if fixed is None else (fixed,))):
                    tick = time.perf_counter()
                    fetch_elapsed[0] = 0.
                    result = execute_one_step(terminal_hash=policy.frozen_hash, visible_features=data.X[i],
                        stop_arm=POOL[stop], stop_invoice=final(stop).merge(initial_invoice), branch_estimates=estimates,
                        budget=budget, applicable={s: applicable[s] for s in ACTIVE_BRANCHES}, model=acquirer,
                        fetch=fetch, fully_observed=complete, mode=mode, tool_order=order, random_key=uid)
                    cost = invoice(result['invoice']).merge(CostInvoice((Charge('acquisition-decision:'+family+':'+uid,
                                                        max(0., time.perf_counter()-tick-fetch_elapsed[0])),)))
                    save(name+'_'+bn, POOL.index(result['arm']), cost, tool_count=result['tool_count'],
                         requested_state=result['tool'], actual_state=result['tool'] or 'none', budget=budget,
                         status=result['status'], excluded=result['excluded'], predicted_tool_values=result['predicted_values'],
                         acquisition_steps=result['acquisition_steps'], actual_primitives=result['primitives'])
    atomic_json(root/(prefix+'decisions.json'), rows)
    table, source_metrics = summarize(rows)
    atomic_json(root/(prefix+'table.json'), table)
    atomic_json(root/(prefix+'metrics_by_source.json'), source_metrics)
    atomic_json(root/(prefix+'mechanism_rows.json'), mechanism)
    atomic_json(root/(prefix+'support.json'), support)
    atomic_json(root/(prefix+'evaluation_sources.json'), provenance)
    atomic_json(root/(prefix+'state_projection_costs.json'), projection_records)
    atomic_json(root/(prefix+'evaluation_status.json'), {'status': 'completed', 'elapsed_seconds': time.perf_counter()-begun,
        'rows': len(rows), 'groups': len(table), 'common_episodes_per_family': len(indices),
        'independent_parents': len(set(data.parents[indices])), 'method_promoted': False, 'heldout_labels_read': 0})
    print(json.dumps(read(root/(prefix+'evaluation_status.json'))), flush=True)
    return rows, table


class ExternalEvaluationData:
    """Frozen-policy-only access to registered check or previously used finance."""
    def __init__(self, root, suite):
        _, manifest = frozen_models(root)  # Before any current target archive is opened.
        self.input_provenance = {}
        if suite == 'generalization':
            source = root/'probes/main'
            self.meta = read(source/'generalization_metadata.json')
            assert len(self.meta) == 17
            assert all(m['generalization_only'] and m['v431_role'] == 'T_check'
                       and m['horizon'] == 192 and m['gap'] == [358, 409] for m in self.meta.values())
            assert {m['parent_group'] for m in self.meta.values()} <= set(manifest['check_parent_ids'])
            contexts = source/'generalization_contexts.npz'
            target_path = Path('results/v43/20260914T141030.324186Z-agent/targets.npz')
            scales = read(source/'mase_scales.json')
        else:
            assert suite == 'financial'
            source = Path('results/v431-r2/financial-observation-index-r1')
            self.meta = read(source/'episode_manifest.json')
            assert len(self.meta) == 12 and len({m['parent_group'] for m in self.meta.values()}) == 2
            assert read(source/'collector_independent_replay.json')['status'] == 'passed'
            contexts, target_path = source/'contexts.npz', source/'targets.npz'
            scales = read(source/'mase_scales.json')
            target_freeze = read(source/'target_read_ledger.json')
            assert file_hash(target_path) == target_freeze['targets_sha256'], 'Previously evaluated financial target changed'
        self.uids = list(self.meta)
        self.parents = np.array([self.meta[u]['parent_group'] for u in self.uids])
        self.roles = np.array(['T_check' if suite == 'generalization' else 'dev']*len(self.uids))
        self.episodes, X, diagnostic, complete = {}, [], [], []
        with np.load(contexts, allow_pickle=False) as f:
            for u in self.uids:
                m = self.meta[u]
                fields = {k: f[u+'_'+k].copy() for k in ('target', 'covariates', 'timestamps', 'availability')}
                assert array_hash(fields['target']) == m['target_hash'], 'Current context changed'
                e = Episode(u, m['source'], m.get('panel', m['source']), m['parent_group'], m['split'], 0,
                            m['raw_start'], m['context_end'], m['horizon'], **fields)
                self.episodes[u] = e
                tick = time.perf_counter(); X.append(dirty_features(e, PERIODS.get(m['source'], 5)))
                diagnostic.append(time.perf_counter()-tick); complete.append(np.isfinite(e.target).all())
        self.X, self.diagnostic_costs, self.complete = np.asarray(X), np.asarray(diagnostic), np.asarray(complete)
        self.predictions, self.forecast_costs, self.direct, self.L, self.MAE = {}, {}, {}, {}, {}
        pools = None
        # All current predictions are checked before the target cache is decoded.
        for family in ('bolt', 'timesfm'):
            if suite == 'generalization':
                current = root/('generalization-current-'+family)
                assert read(current/'status.json')['status'] == 'completed', 'Registered check predictions incomplete'
                current_manifest = read(current/'manifest.json')
                assert current_manifest['input_sha256'] == file_hash(contexts), 'New-combination forecast input changed'
                for name, digest in current_manifest['files'].items():
                    assert file_hash(current/name) == digest, 'New-combination cached output changed'
                candidate_path, forecast_path = current/'candidates.npz', current/'predictions.npz'
                self.direct[family] = read(current/'direct_candidate_costs.json')
                self.forecast_costs[family] = read(current/'forecast_costs.json')
            else:
                candidate_path = source/'candidates.npz'
                forecast_path = source/('forecasts.npz' if family == 'bolt' else 'timesfm/predictions.npz')
                self.direct[family] = read(source/'direct_candidate_costs.json')
                if family == 'bolt':
                    self.forecast_costs[family] = read(source/'forecast_costs.json')
                else:
                    status = read(source/'timesfm/status.json')
                    assert status['status'] == 'completed' and status['prediction_file_sha256'] == file_hash(forecast_path)
                    assert read(source/'timesfm/independent_replay.json')['status'] == 'passed'
                    self.forecast_costs[family] = {r['episode_uid']+'_'+r['arm']: r['total_seconds']-self.direct[family][r['episode_uid']][r['arm']]
                                                 for r in read(source/'timesfm/scored_rows.json')}
            with np.load(candidate_path, allow_pickle=False) as f:
                current_pools = {u: {a: f[u+'_'+a].copy() for a in POOL} for u in self.uids}
            if pools is not None:
                assert all(np.array_equal(pools[u][a], current_pools[u][a], equal_nan=True) for u in self.uids for a in POOL), 'Backbones changed governance candidates'
            pools = current_pools
            with np.load(forecast_path, allow_pickle=False) as f:
                self.predictions[family] = {u: {a: f[u+'_'+a].copy() for a in POOL} for u in self.uids}
            self.input_provenance[str(candidate_path)] = file_hash(candidate_path)
            self.input_provenance[str(forecast_path)] = file_hash(forecast_path)
        self.old = SimpleNamespace(pools=pools)
        with np.load(target_path, allow_pickle=False) as f:
            targets = {}
            for u in self.uids:
                base = self.meta[u]['base_uid'] if suite == 'generalization' else u
                y, m = f[base+'_values'], f[base+'_mask']
                assert y.shape == m.shape == (self.meta[u]['horizon'],) and m.any()
                targets[u] = y.copy(), m.copy()
        for family in self.predictions:
            mae = []
            for u in self.uids:
                y, m = targets[u]
                prediction = self.predictions[family][u]
                assert all(p.shape == y.shape and np.isfinite(p).all() for p in prediction.values())
                mae.append([float(np.abs(prediction[a][m]-y[m]).mean()) for a in POOL])
            self.MAE[family] = np.array(mae)
            self.L[family] = self.MAE[family]/np.array([scales[self.meta[u]['source']] for u in self.uids])[:, None]
        self.input_provenance[str(contexts)] = file_hash(contexts)
        self.input_provenance[str(target_path)] = file_hash(target_path)

    def final_invoice(self, family, i, a, diagnostic=False):
        u, arm = self.uids[i], POOL[int(a)]
        result = CostInvoice((Charge('candidate:'+u+':'+arm, self.direct[family][u][arm]),
                              Charge('forecast:'+family+':'+u+':'+arm, self.forecast_costs[family][u+'_'+arm])))
        if diagnostic:
            result = result.merge(CostInvoice((Charge('diagnostic:'+u, float(self.diagnostic_costs[i])),)))
        return result

    def weights(self, indices):
        return source_parent_weights([self.uids[i] for i in indices], self.meta)


def curve_subsets(data, fit):
    groups = {}
    for source in sorted({data.meta[data.uids[i]]['source'] for i in fit}):
        groups[source] = sorted({data.parents[i] for i in fit if data.meta[data.uids[i]]['source'] == source},
            key=lambda parent: min(data.meta[data.uids[i]]['raw_start'] for i in fit if data.parents[i] == parent))
    def quotas(total):
        raw = {s: total*len(p)/54 for s, p in groups.items()}
        q = {s: max(1, int(v)) for s, v in raw.items()}
        while sum(q.values()) < total:
            s = max(groups, key=lambda s: (raw[s]-q[s], s)); q[s] += 1
        assert sum(q.values()) == total
        return q
    half, quarter = {}, {}
    hq, qq = quotas(27), quotas(13)
    for source, parents in groups.items():
        half[source] = [parents[i] for i in np.linspace(0, len(parents)-1, hq[source], dtype=int)]
        quarter[source] = [half[source][i] for i in np.linspace(0, len(half[source])-1, qq[source], dtype=int)]
    chosen = {13: {p for ps in quarter.values() for p in ps}, 27: {p for ps in half.values() for p in ps}, 54: set(data.parents[fit])}
    assert chosen[13] <= chosen[27] <= chosen[54]
    return {n: np.array([i for i in fit if data.parents[i] in parents]) for n, parents in chosen.items()}


def learning_curves(root):
    assert not (root/'learning_curves.json').exists(), 'Keep previous support curve immutable'
    begun = time.perf_counter(); full_models, full_manifest = frozen_models(root)
    data = R2Data(); roles = exact_roles(data); fit, gate, check = (roles[r] for r in ('T_fit', 'T_gate', 'T_check'))
    subsets = curve_subsets(data, fit); records, artifacts, curve_models = [], {}, {}
    for family in ('bolt', 'timesfm'):
        ledger, sources = load_probe_ledger(root, family, [data.uids[i] for i in np.r_[fit, gate, check]])
        artifacts[family], curve_models[family] = sources, {}
        for parent_count, subset in subsets.items():
            ref_ids = np.r_[subset, gate]
            ref = freeze_reference(data.L[family][ref_ids], data.weights(ref_ids), data.parents[ref_ids])
            E = {role: state_batches(data, ids, ledger, ref['arm'], rebase_reference=True)
                 for role, ids in (('fit', subset), ('gate', gate), ('check', check))}
            if parent_count == 54:
                p = full_models['policies'][family]['residual']
                assert p.reference_action == ref['action'], 'Full curve changed the main fixed reference'
            else:
                p = ResponsePolicy(ref['action'], ref['parent_ids'], FEATURE_NAMES, PSI_NAMES, 'residual')
                p.fit(E['fit'], data.L[family][subset], data.weights(subset), data.parents[subset],
                    gate_evidence=E['gate'], gate_losses=data.L[family][gate], gate_weights=data.weights(gate), gate_parents=data.parents[gate])
            curve_models[family][parent_count] = p
            for state in ('H32', 'H', 'control'):
                actions = [p.choose(data.X[i], E['check'][state][j], fully_observed=bool(data.complete[i]))['action'] for j, i in enumerate(check)]
                records.append({'family': family, 'fit_parents': parent_count, 'gate_parents': 21,
                    'total_supervised_parents': parent_count+21, 'check_parents': 17, 'state': state,
                    'mase': float(np.dot(data.weights(check), data.L[family][check, actions])),
                    'reference_mase': float(np.dot(data.weights(check), data.L[family][check, ref['action']])),
                    'reference_arm': ref['arm'], 'fit_parent_ids': sorted(set(data.parents[subset])),
                    'gate_parent_ids': sorted(set(data.parents[gate])), 'terminal_hash': p.frozen_hash,
                    'alpha': p.audit_[state].get('alpha'), 'support': p.audit_[state],
                    'check_episodes': [{'uid': data.uids[i], 'parent': str(data.parents[i]), 'action': int(actions[j]),
                                       'loss': float(data.L[family][i, actions[j]]), 'source_parent_weight': float(data.weights(check)[j])}
                                      for j, i in enumerate(check)],
                    'scope': 'fixed-evidence terminal support curve; no acquisition fitting or budget claim',
                    'selected_using_check': False, 'main_training_fraction_changed': False})
    joblib.dump(curve_models, root/'learning_curve_models.joblib')
    atomic_json(root/'learning_curves.json', records)
    atomic_json(root/'learning_curve_manifest.json', {'status': 'completed', 'source_sessions': artifacts,
        'main_models_sha256': file_hash(root/'models.joblib'), 'curve_models_sha256': file_hash(root/'learning_curve_models.joblib'),
        'curve_sha256': file_hash(root/'learning_curves.json'), 'elapsed_seconds': time.perf_counter()-begun,
        'subset_rule': 'source-proportional quotas; evenly spaced original time; 13 nested in 27 nested in 54',
        'gate_parents_extra': 21, 'check_parent_count': 17, 'selection_on_check': False})
    print(json.dumps(read(root/'learning_curve_manifest.json')), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('results/v431-r3'))
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--freeze-reference', action='store_true')
    modes.add_argument('--fit', action='store_true')
    modes.add_argument('--evaluate', action='store_true')
    modes.add_argument('--learning-curves', action='store_true')
    parser.add_argument('--role', choices=['dev', 'T_check'], default='dev')
    parser.add_argument('--suite', choices=['main', 'generalization', 'financial'], default='main')
    args = parser.parse_args()
    if args.learning_curves:
        learning_curves(args.root)
        return
    if args.fit:
        fit_models(args.root)
        return
    if args.evaluate:
        if args.suite == 'main':
            data = R2Data(); roles = exact_roles(data)
            evaluate_data(args.root, data, roles[args.role], prefix='' if args.role == 'dev' else 'check_')
        else:
            data = ExternalEvaluationData(args.root, args.suite)
            prefix = 'new_combination_' if args.suite == 'generalization' else 'financial_'
            evaluate_data(args.root, data, np.arange(len(data.uids)), prefix=prefix,
                          probe_suite='main' if args.suite == 'generalization' else 'financial')
            atomic_json(args.root/(prefix+'current_sources.json'), data.input_provenance)
        return
    result = freeze_references(args.root)
    print(json.dumps({'reference_hash': result['reference_hash'],
                      'families': {f: v['arm'] for f, v in result['families'].items()},
                      'parents': result['fitting_parent_count']}, indent=2))


if __name__ == '__main__':
    main()
