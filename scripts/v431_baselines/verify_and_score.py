#!/usr/bin/env python3
"""Independently replay frozen TATO choices, then score identical dev targets."""
from collections import defaultdict
import json
from pathlib import Path
import sys
import numpy as np
from tato_adapter import sha,predict_native
from worker import atom,array_sha


def grouped_mean(rows,field):
    groups=defaultdict(list)
    for row in rows:groups[(row['source'],row['horizon'],row['condition'])].append(row[field])
    return float(np.mean([np.mean(v) for v in groups.values()]))


def main(directory):
    out=Path(directory);request=json.loads((out/'request.json').read_text());status=json.loads((out/'status.json').read_text())
    if status['status']!='completed':raise RuntimeError('worker incomplete; do not read any evaluation target')
    if sha(out/'predictions.npz')!=status['prediction_file_sha256']:raise RuntimeError('prediction file identity changed')
    if sha(request['inputs'])!=request['inputs_sha256']:raise RuntimeError('input file identity changed')
    records=json.loads((out/'decisions.json').read_text());calls=json.loads((out/'calls.json').read_text())
    if len(records)!=len(request['rows']):raise RuntimeError('row denominator changed')
    model_outputs={};call_prices={};raw_count=0
    for call in calls:
        if call['cache_hit']:continue
        path=out/call['raw_file']
        if sha(path)!=call['raw_sha256']:raise RuntimeError('raw model file changed')
        with np.load(path,allow_pickle=False) as raw:
            if request['backend']=='tato' and request.get('backbone_family')!='timesfm':
                if not np.array_equal(raw['point'],raw['quantiles'][:,4,:,None]):raise AssertionError('Bolt point is not median')
                point=raw['point'].copy()
            else:point=raw['point'][:,:,None].copy()
            if call['cache_key']!=array_sha(raw['input'])+':'+str(call['horizon']):raise AssertionError('model input cache identity mismatch')
            if not np.isfinite(point).all() or not np.isfinite(raw['quantiles']).all():raise AssertionError('nonfinite raw output')
        model_outputs[call['cache_key']]=point;call_prices[call['cache_key']]=call['seconds'];raw_count+=1
    class Replay:
        def forecast(self,x,horizon):
            return model_outputs[array_sha(x)+':'+str(horizon)].copy()
    checked_trials=0;deploy_costs={}
    with np.load(request['inputs'],allow_pickle=False) as contexts, np.load(out/'predictions.npz',allow_pickle=False) as forecasts:
        for row in records:
            x=contexts[row['input_key']];p=forecasts[row['input_key']]
            if array_sha(x)!=row['input_sha256'] or array_sha(p)!=row['prediction_sha256']:raise AssertionError('row hash mismatch')
            if request['backend']=='tato':
                cutoff=len(x)-row['horizon'];observed=x[cutoff:];valid=np.isfinite(observed)
                successful=[]
                for trial in row['trials']:
                    if trial['status']!='completed':continue
                    actual,_=predict_native(trial['params'],Replay(),x[:cutoff],row['horizon'])
                    np.testing.assert_array_equal(actual,np.array(trial['prediction']))
                    loss=float(np.mean(np.abs(actual[valid]-observed[valid])))
                    if abs(loss-trial['validation_mae'])>1e-12:raise AssertionError('historical validation mismatch')
                    checked_trials+=1;successful.append(trial)
                chosen=min(successful,key=lambda t:(t['validation_mae'],t['trial']))
                if chosen['trial']!=row['selected_trial']:raise AssertionError('selection not derived from dirty-only validation')
                actual,_=predict_native(chosen['params'],Replay(),x,row['horizon'])
                np.testing.assert_array_equal(actual,p)
            else:
                actual=Replay().forecast(x[None,:,None],row['horizon'])[0,:,0]
                np.testing.assert_array_equal(actual,p)
            # Per-origin standalone inference cannot borrow an already computed
            # comparison arm or another origin for free. Within TATO origin,
            # identical trial/model input reuse is legitimately shared.
            local_seen=set();supplement=0.;standalone_inference=0.
            for call in row['model_calls']:
                key=call['cache_key']
                if key in local_seen:continue
                local_seen.add(key);standalone_inference+=call_prices[key]
                if call['cache_hit']:supplement+=call_prices[key]
            deploy_costs[row['input_key']]=dict(standalone_model_seconds=standalone_inference,
                experimental_cache_seconds_supplement=supplement,
                standalone_wall_estimate_seconds=row['wall_seconds']+supplement)
    audit=dict(status='passed',all_rows=len(records),raw_outputs=raw_count,successful_trial_replays=checked_trials,
        no_target_read_before_replay=True,future_access='next step opens only frozen dev targets',heldout_labels_read=0,
        verifier_sha256=sha(__file__),request_sha256=sha(out/'request.json'))
    atom(out/'independent_replay.json',audit)
    # Only after all predictions and their decisions are independently verified.
    source=Path(request['source_run']);meta=json.loads((source/'episode_manifest.json').read_text())
    scales=json.loads((source/'mase_scales.json').read_text());direct=json.loads((source/'direct_candidate_costs.json').read_text())
    scored=[]
    with np.load(source/'targets.npz',allow_pickle=False) as labels,np.load(out/'predictions.npz',allow_pickle=False) as forecasts:
        for row in records:
            uid=row['episode_uid']
            if meta[uid]['role']!='dev':raise RuntimeError('baseline evaluation may read only dev')
            target=labels[uid+'_values'];mask=labels[uid+'_mask'].astype(bool);prediction=forecasts[row['input_key']]
            if not mask.any() or not np.isfinite(target[mask]).all():raise AssertionError('invalid common scoring mask')
            loss=float(np.mean(np.abs(prediction[mask]-target[mask])));cost=deploy_costs[row['input_key']]
            inherited=0. if request['backend']=='tato' else direct[uid][row['arm']]
            scored.append({k:row[k] for k in ('episode_uid','arm','source','horizon','condition','parent_group')}|
                dict(mae=loss,mase=loss/scales[row['source']],scored_points=int(mask.sum()),actual_model_calls=row['actual_model_calls'],
                     experimental_row_wall_seconds=row['wall_seconds'],inherited_candidate_generation_seconds=inherited,
                     **cost,standalone_total_estimate_seconds=inherited+cost['standalone_wall_estimate_seconds']))
    native_losses={}
    if request['backend']=='tato' and request.get('backbone_family')!='timesfm':
        native_losses={r['episode_uid']:r['mae'] for r in json.loads((source/'task_labels.json').read_text()) if r['arm']=='A0_NATIVE'}
    elif request['backend']=='tato':
        # Same-backbone KEEP comes from the already completed frozen five-arm run.
        native_path=out.parent/'timesfm'/'scored_rows.json'
        native_losses={r['episode_uid']:r['mae'] for r in json.loads(native_path.read_text()) if r['arm']=='A0_NATIVE'}
    else:native_losses={r['episode_uid']:r['mae'] for r in scored if r['arm']=='A0_NATIVE'}
    budget_path=out.parent/'terminal_manifest.json'
    budgets=json.loads(budget_path.read_text())['budgets'] if budget_path.exists() else {}
    overhead=status.get('process_overhead_seconds',0.)/len(records)
    for row in scored:
        row['task_harm']=row['mae']>native_losses[row['episode_uid']]+1e-12
        row['total_seconds']=row['standalone_total_estimate_seconds']+overhead
        row['budget_overrun']={name:row['total_seconds']>value for name,value in budgets.items()}
    summary=[];common=[]
    for arm in sorted({x['arm'] for x in scored}):
        rows=[r for r in scored if r['arm']==arm]
        summary.append(dict(arm=arm,n=len(rows),parents=len({r['parent_group'] for r in rows}),source_macro_mase=grouped_mean(rows,'mase'),
            source_macro_deployment_seconds=grouped_mean(rows,'standalone_total_estimate_seconds'),
            source_macro_model_seconds=grouped_mean(rows,'standalone_model_seconds'),
            source_macro_actual_experiment_row_seconds=grouped_mean(rows,'experimental_row_wall_seconds'),
            by_source={s:grouped_mean([r for r in rows if r['source']==s],'mase') for s in sorted({r['source'] for r in rows})}))
        common.append(dict(policy=('TIMESFM_TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR' if request.get('backbone_family')=='timesfm' else 'TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR') if request['backend']=='tato' else 'TIMESFM_FIXED_'+arm,
            backbone='chronos-bolt-base' if request['backend']=='tato' and request.get('backbone_family')!='timesfm' else 'timesfm-2.5-200m-pytorch',
            episodes=len(rows),parents=len({r['parent_group'] for r in rows}),mase=grouped_mean(rows,'mase'),mae=grouped_mean(rows,'mae'),
            total_seconds=grouped_mean(rows,'total_seconds'),task_harm=grouped_mean(rows,'task_harm'),
            mean_tools=8. if request['backend']=='tato' else 0.,budget_overruns={k:sum(r['budget_overrun'][k] for r in rows) for k in budgets},
            budget_reference=budgets,budget_enforcement='retrospective audit; fixed 8 trials, no wall-clock early termination' if request['backend']=='tato' else 'fixed method; retrospective audit',
            status='completed_dev_not_confirmatory',raw_model_cost_reuse='cross-row cache inference repriced; same-origin shared compute deduplicated'))
    atom(out/'scored_rows.json',scored);atom(out/'summary.json',dict(status='completed',table=summary,
        full_process_wall_seconds=status['total_wall_seconds'],model_load_seconds=status['model_load_seconds'],
        experiment_overhead_seconds=status.get('process_overhead_seconds'),deployment_cost_scope='row wall plus repriced cross-origin cache inference; model startup separately; inherited fixed-arm governance included',
        actual_experiment_model_calls=status['actual_model_calls'],confirmation=False,incumbent='PICS_joint_relabel'))
    atom(out/'baseline_table.json',common)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main(sys.argv[1])
