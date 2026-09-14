#!/usr/bin/env python3
"""Post-hoc mechanism diagnostics on the frozen train/dev cache; no fitting."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import time
import joblib
import numpy as np
from introact_ts.v43.agent_fit import AgentDataset, STATES
from introact_ts.v43.agent_inputs import POOL, TOOLS
from introact_ts.v43.agent_policy import choose, acquisition_features
from introact_ts.v43.cli import atomic_json
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import array_hash, require


def macro(rows, field):
    groups = defaultdict(list)
    for row in rows:
        groups[row['source'], row['horizon'], row['condition']].append(row[field])
    return float(np.mean([np.mean(v) for v in groups.values()]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    root = parser.parse_args().run
    out = root / 'agent' / 'mechanism_diagnostic'
    out.mkdir(exist_ok=False)
    data = AgentDataset(root)
    manifest = json.loads((root / 'agent/model_manifest.json').read_text())
    require(file_hash(root / 'agent/models.joblib') == manifest['model_sha256'], 'model changed')
    models = joblib.load(root / 'agent/models.joblib')
    started = time.perf_counter()
    rows, transitions, protection = [], [], []
    path_names = ['empty', 'mask', 'history', 'both']
    for uid, meta in data.meta.items():
        episode, pool = data.episodes[uid], data.pools[uid]
        losses = {a: data.labels[uid, a]['mase'] for a in POOL}
        choices = {}
        for name, path in zip(path_names, STATES):
            choices[name], _ = choose(episode, pool, data.state(uid, path), models['utility'])
        simple, _ = choose(episode, pool, data.state(uid, ()), models['simple'])
        oracle = min(POOL, key=losses.get)
        row = dict(episode_uid=uid, **meta, oracle_arm=oracle, fixed_arm=manifest['train_best_fixed'],
                   fixed=losses[manifest['train_best_fixed']], oracle=losses[oracle],
                   oracle_space=losses[manifest['train_best_fixed']]-losses[oracle],
                   choices=choices, simple=losses[simple],
                   **{n: losses[a] for n, a in choices.items()})
        rows.append(row)
        if meta['role'] == 'dev':
            for arm in POOL:
                observed = np.isfinite(episode.target)
                require(pool[arm][observed].tobytes() == episode.target[observed].tobytes(), 'observed changed')
            protection.append(dict(episode_uid=uid, **meta, natural_missing=int(np.isnan(episode.target).sum()),
                all_candidates_identical_to_keep=all(array_hash(v)==array_hash(pool['A0_NATIVE']) for v in pool.values())))
        for name, path in zip(path_names[:3], STATES[:3]):
            state = data.state(uid, path)
            before = choices[name]
            for tool in TOOLS:
                if tool in path:
                    continue
                after, _ = choose(episode, pool, state.acquire(tool, data.evidence[uid][tool]), models['utility'])
                predicted = float(models['acquisition'].predict(acquisition_features(episode, pool, state, models['utility'], tool)[None])[0])
                gain = losses[before]-losses[after]
                value = gain-manifest['penalty']*data.tool_costs[uid][tool]
                transitions.append(dict(episode_uid=uid, **meta, history=list(path), tool=tool,
                    before=before, after=after, action_changed=before!=after,
                    actual_gain_mase=gain, actual_net_value=value, predicted_net_value=predicted,
                    predicted_positive=predicted>0, actual_positive=value>0))
    role_summary = {}
    for role in ('scorer_fit', 'acquisition_fit', 'dev'):
        subset = [r for r in rows if r['role']==role]
        trs = [r for r in transitions if r['role']==role]
        positives = [r for r in trs if r['predicted_positive']]
        role_summary[role] = dict(parents=len({r['parent_group'] for r in subset}), episodes=len(subset),
            mase={k:macro(subset,k) for k in ('fixed','oracle','simple',*path_names)},
            oracle_space=macro(subset,'oracle_space'),
            oracle_beats_fixed_episodes=sum(r['oracle_space']>1e-10 for r in subset),
            oracle_winners=dict(Counter(r['oracle_arm'] for r in subset)),
            tool_transitions=dict(n=len(trs), changed=sum(r['action_changed'] for r in trs),
                beneficial=sum(r['actual_gain_mase']>1e-10 for r in trs), harmful=sum(r['actual_gain_mase']< -1e-10 for r in trs),
                predicted_positive=len(positives), actual_positive=sum(r['actual_positive'] for r in trs),
                precision_on_predicted_positive=sum(r['actual_positive'] for r in positives)/len(positives) if positives else None))
    dev = [r for r in rows if r['role']=='dev']
    by_source = {s:{k:macro([r for r in dev if r['source']==s],k) for k in ('fixed','oracle','simple',*path_names)} for s in sorted({r['source'] for r in dev})}
    delta_rows = []
    for row in dev:
        delta_rows.append(dict(episode_uid=row['episode_uid'],source=row['source'],parent_group=row['parent_group'],
            horizon=row['horizon'],condition=row['condition'],before=row['choices']['empty'],after=row['choices']['both'],
            gain_mase=row['empty']-row['both']))
    decisions = json.loads((root/'agent/decisions.json').read_text())
    selected = [r for r in decisions if r['policy']=='LEARNED_two_tools']
    actual_steps=[]
    for row in selected:
        uid=row['episode_uid']
        for step in row['trace']:
            if step['tool'] is not None:
                match=[r for r in transitions if r['episode_uid']==uid and r['history']==step['history'] and r['tool']==step['tool']]
                require(len(match)==1,'transition mismatch')
                actual_steps.append(match[0])
    acquired=dict(n=len(actual_steps), beneficial=sum(r['actual_gain_mase']>1e-10 for r in actual_steps),
        harmful=sum(r['actual_gain_mase']< -1e-10 for r in actual_steps),
        task_unchanged=sum(abs(r['actual_gain_mase'])<=1e-10 for r in actual_steps))
    raw=[r for r in protection if r['condition']=='raw']
    report=dict(scope='posthoc_frozen_model_mechanism_diagnostic_no_refit',role_summary=role_summary,
        dev_by_source=by_source,learned_high_budget_acquired_transitions=acquired,
        dev_raw_protection=dict(episodes=len(raw),no_missing_identical_pool=sum(r['all_candidates_identical_to_keep'] for r in raw),
            natural_missing_episodes=sum(r['natural_missing']>0 for r in raw),observed_write_violations=0,
            valid_event_labels='not_available_no_event_preservation_claim'),
        label_scope='existing_train_dev_only',new_heldout_labels_read=0,
        caveat='fit-role metrics are apparent/in-sample; acquisition-fit is unseen only by utility, dev is repeatedly used development data',
        runtime_seconds=time.perf_counter()-started,promotion=False)
    for name, value in [('episode_diagnostics',rows),('tool_transitions',transitions),('dev_evidence_switches',delta_rows),('raw_protection',protection),('summary',report)]:
        atomic_json(out/(name+'.json'),value)
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
