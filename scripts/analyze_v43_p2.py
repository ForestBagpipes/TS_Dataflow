#!/usr/bin/env python3
"""Post-hoc dev attribution; reveal synthetic context truth only to this report."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from introact_ts.v43.data_io import read_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    root = parser.parse_args().run
    out = root/'posthoc_attribution'
    out.mkdir(exist_ok=False)
    def read(name): return json.loads((root/(name+'.json')).read_text())
    assert read('independent_verification')['status'] == 'completed'
    settings = dict(scope='posthoc_dev_only_not_method_selection',new_future_labels_read=0,heldout_labels_read=0,
                    repair_scope='synthetically_hidden_finite_target_positions_only_no_keep_repair_gain',
                    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'config.json').write_text(json.dumps(settings,indent=2)+'\n')
    records = {r['source']:r for r in read('data_manifest')}
    meta, evidence = read('episode_manifest'), read('candidate_evidence')
    arms = read('arm_manifest')['executed']
    labels = defaultdict(dict)
    for row in read('task_labels'): labels[row['episode_uid']][row['arm']] = row
    scopes = {'target_only':['A0_NATIVE','A0_FFILL','A2_SINGLE'],
              'plus_simple_cross_channel':['A0_NATIVE','A0_FFILL','A2_SINGLE','A3_COV','A4_RIDGE_CONTEXT'],
              'plus_residual':['A0_NATIVE','A0_FFILL','A2_SINGLE','A3_COV','A4_RIDGE_CONTEXT','A5_STATIC'],
              'plus_full_history':arms}
    grouped, selected, repair, changes = defaultdict(list), [], [], []
    truth_cache = {}
    with np.load(root/'candidates.npz',allow_pickle=False) as candidates:
        for uid, rows in labels.items():
            e = meta[uid]
            assert all(r['status']=='completed' for r in rows.values())
            for scope,names in scopes.items():
                choice = min((rows[a] for a in names),key=lambda r:r['mae'])
                grouped[scope,e['source'],e['horizon'],e['condition']].append(choice['mase'])
                selected.append(dict(episode_uid=uid,scope=scope,chosen_arm=choice['arm'],mase=choice['mase']))
            if e['condition']=='raw': continue
            key = e['source'],e['raw_start'],e['context_end']
            if key not in truth_cache:
                truth_cache[key] = read_rows(records[e['source']],e['raw_start'],e['context_end'],'dev')[1][:,0]
            truth = truth_cache[key]
            dirty = candidates[uid+'_A0_NATIVE']
            hidden = np.isfinite(truth)&np.isnan(dirty)
            assert hidden.any()
            errors={}
            for arm in arms:
                x=candidates[uid+'_'+arm]
                filled=np.isfinite(x[hidden])
                mae=float(np.abs(x[hidden]-truth[hidden]).mean()) if filled.all() else None
                errors[arm]=mae
                repair.append(dict(episode_uid=uid,source=e['source'],condition=e['condition'],horizon=e['horizon'],arm=arm,
                                   synthetic_positions=int(hidden.sum()),filled_positions=int(filled.sum()),repair_mae=mae,
                                   status='completed' if mae is not None else 'unfilled_no_numeric_repair_error'))
            residual=evidence[uid]['A5_STATIC']
            if residual.get('eta',0)>0:
                loss=np.mean(residual['outer_mae'],axis=0);eta=residual['eta']
                changes.append(dict(episode_uid=uid,source=e['source'],parent_group=e['parent_group'],horizon=e['horizon'],eta=eta,
                                    pseudo_mae_gain=float(loss[0]-loss[(0.,.5,1.).index(eta)]),
                                    actual_gap_mae_gain=errors['A2_SINGLE']-errors['A5_STATIC'],
                                    future_mae_gain=rows['A2_SINGLE']['mae']-rows['A5_STATIC']['mae']))
    summaries={}
    for source in records:
        summaries[source]={scope:float(np.mean([np.mean(v) for k,v in grouped.items() if k[:2]==(scope,source)])) for scope in scopes}
    summary=dict(settings,source_macro_oracles={s:float(np.mean([x[s] for x in summaries.values()])) for s in scopes},
                 oracles_by_source=summaries,residual_changed_episodes=len(changes),residual_changed_parents=len({r['parent_group'] for r in changes}),
                 changed_future_better=sum(r['future_mae_gain']>1e-9 for r in changes),changed_future_worse=sum(r['future_mae_gain']<-1e-9 for r in changes),
                 changed_gap_better=sum(r['actual_gap_mae_gain']>1e-9 for r in changes),changed_gap_worse=sum(r['actual_gap_mae_gain']<-1e-9 for r in changes),
                 promotion=False,confidence_interval=None)
    for name,value in [('summary',summary),('oracle_selections',selected),('synthetic_repair',repair),('residual_changed_cases',changes)]:
        (out/(name+'.json')).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary))


if __name__=='__main__': main()
