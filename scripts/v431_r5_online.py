#!/usr/bin/env python3
"""Label-sealed real r5 trials; final output reuses an executed version.

Parent owns the single GPU lock. --prepare-only never starts a model.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def atom(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n');tmp.replace(path)


def json_safe(value):
    import numpy as np
    if isinstance(value,dict):return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [json_safe(v) for v in value]
    if isinstance(value,np.ndarray):return json_safe(value.tolist())
    if isinstance(value,(float,np.floating)) and not np.isfinite(value):return None
    if isinstance(value,np.generic):return value.item()
    return value


def features(episode):
    import numpy as np
    from introact_ts.v431.data import PERIODS
    from introact_ts.v431_r4.origin_scale import origin_scale,visible_features,FREE_NAMES
    from introact_ts.v431_r3.probe import prepare_probe,registered_specs,visible_descriptor
    scale=origin_scale(episode.target,PERIODS.get(episode.source,5))
    x=visible_features(episode,PERIODS.get(episode.source,5),scale)
    p=prepare_probe(episode,registered_specs(episode.horizon)['long'],scale.value)
    coverage=visible_descriptor(p.view)['covariate_coverage'] if p.status=='prepared' else np.nan
    return np.r_[x,coverage],scale,tuple(FREE_NAMES)+('known_history_covariate_coverage',)


def runtime_class():
    import numpy as np
    from introact_ts.v431_r3.runtime import LiveRuntime
    from introact_ts.v43.schemas import Candidate,array_hash,verify_impute,json_hash
    from introact_ts.v43.agent_inputs import POOL
    from introact_ts.v43.candidates import prepare_model_input
    from introact_ts.v43.p2_candidates import ridge_candidate
    from introact_ts.v431_r5.controller import TrialResult

    class CurrentTrials(LiveRuntime):
        def start_request(self):
            self.prediction_memo={};self.results={};self.executions=[]

        def trial(self,e,action):
            arm=POOL[action];prefix=self.prefix('r5-current');started=time.perf_counter();detail={'status':'completed'}
            if action==0:candidate=e.target.copy()
            elif action==1:candidate=prepare_model_input(e.target,native_nan=False)
            elif action in (2,3):
                if np.isnan(e.target).any():
                    values,_=self.collector.model_call('tsicl','impute','none' if action==2 else 'past_only',
                        [(e,arm,e.target)],prefix+'-impute');candidate=values[e.uid,arm]
                else:candidate=e.target.copy();detail['status']='not_needed'
            elif action==4:
                result,detail=ridge_candidate(e);candidate=result.target
            else:raise ValueError('Unregistered arm')
            verify_impute(e,Candidate(e.uid,arm,candidate));governance=time.perf_counter()-started
            key=(array_hash(candidate),e.horizon,self.identity)
            tick=time.perf_counter();reused=key in self.prediction_memo
            if reused:prediction=self.prediction_memo[key].copy()
            else:
                values,_=self.collector.model_call('bolt','forecast','none',[(e,arm,candidate)],prefix+'-forecast')
                prediction=values[e.uid,arm];self.prediction_memo[key]=prediction.copy()
            forecast=time.perf_counter()-tick
            actual=0 if action==4 and detail.get('status')=='unsupported' else action
            identity=dict(source=e.source,parent=e.parent_group,origin=e.context_end,raw_start=e.raw_start,
                L=len(e.target),H=e.horizon,target_mask_hash=array_hash(e.observed_mask),
                auxiliary_mask_hash=array_hash(np.isfinite(e.covariates)),timestamps_hash=array_hash(e.timestamps),
                availability_hash=array_hash(e.availability),input_version_hash=key[0],
                checkpoint_record=self.services.model['models'][self.family],checkpoint_record_hash=self.identity,
                model_settings='unchanged real service manifest and request protocol',prediction_dtype=str(prediction.dtype),
                candidate_dtype=str(candidate.dtype),prediction_hash=array_hash(prediction),
                arm=arm,actual_arm=POOL[actual],candidate_status=detail,
                numeric_protocol='native selected point; no averaging/correction',within_request_prediction_reuse=reused)
            identity['cache_key']=json_hash(identity)
            result=TrialResult(action=action,prediction=prediction.copy(),input_hash=key[0],identity=identity,
                governance_seconds=governance,forecast_seconds=forecast,status='alias' if actual!=action else 'completed',
                actual_action=actual,alias_reason=detail.get('reason') if actual!=action else None)
            self.results[action]=(candidate.copy(),prediction.copy(),result)
            self.executions.append(result.summary())
            return result
    return CurrentTrials


def main():
    p=argparse.ArgumentParser();p.add_argument('--family',choices=['bolt','timesfm'],required=True)
    p.add_argument('--root',type=Path,default=Path('results/v431-r5'));p.add_argument('--output-name')
    p.add_argument('--worker',action='store_true');p.add_argument('--prepare-only',action='store_true');args=p.parse_args()
    args.root=args.root.resolve();name=args.output_name or ('preflight-' if args.prepare_only else 'online-')+args.family
    if Path(name).name!=name:raise ValueError('Invalid output name')
    out=args.root/name
    if args.worker:return worker(args,out)
    out.mkdir(exist_ok=False);start=time.perf_counter()
    command=[sys.executable,str(Path(__file__).resolve()),'--family',args.family,'--root',str(args.root),
             '--output-name',name,'--worker']+(['--prepare-only'] if args.prepare_only else [])
    with (out/'worker.log').open('x') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        atom(out/'process_accounting.json',dict(status='running',pid=process.pid,command=command))
        code=process.wait()
    wall=time.perf_counter()-start
    account=dict(status='completed' if code==0 else 'failed',exit_code=code,process_wall_seconds=wall,
                 command=command,prepare_only=args.prepare_only)
    if (out/'decisions.json').exists():
        rows=json.loads((out/'decisions.json').read_text());hot=sum(r['hot_request_seconds'] for r in rows)
        startup=sum(r['wall_seconds'] for r in json.loads((out/'service/service_startup.json').read_text()))
        account.update(requests=len(rows),hot_request_seconds=hot,model_startup_seconds=startup,
                       remaining_overhead_seconds=wall-hot-startup)
        if wall+1e-5<hot+startup:raise AssertionError('Double-counted live phases')
    atom(out/'process_accounting.json',account);print(json.dumps(account),flush=True)
    if code:raise SystemExit(code)


def worker(args,out):
    import joblib
    import numpy as np
    from introact_ts.v43.schemas import Episode,array_hash,require
    from introact_ts.v43.data_io import file_hash
    from introact_ts.v43.agent_inputs import POOL
    from introact_ts.v431_r3.runtime import OLD
    from introact_ts.v431_r5.controller import run
    project=Path(__file__).resolve().parents[1];financial=project/'results/v431-r2/financial-observation-index-r1'
    read=lambda p:json.loads(Path(p).read_text())
    barrier=dict(open=False,denied_preflight=0,unexpected=0,preflight=False)
    allowed={args.root/'fit'/n for n in ('manifest.json','models_frozen.json','models.joblib')}
    allowed.update(OLD/n for n in ('episode_manifest.json','contexts.npz','model_manifest.json','code_manifest.json','resolved_config.yaml'))
    allowed.update(financial/n for n in ('episode_manifest.json','contexts.npz'))
    def audit(event,arguments):
        if event=='open' and not barrier['open'] and isinstance(arguments[0],(str,bytes,os.PathLike)):
            q=Path(os.fsdecode(arguments[0])).resolve()
            if q.is_relative_to(project/'results') and not q.is_relative_to(out) and q not in allowed:
                if not barrier['preflight']:barrier['unexpected']+=1
                raise PermissionError('r5 future labels and unqueried prediction archives sealed')
    sys.addaudithook(audit);barrier['preflight']=True
    for path in (OLD/'targets.npz',OLD/'task_labels.json',project/'results/v431-r4/trajectory-final/main/bolt.joblib',
                 project/'results/v431-r3/probes/main/probe_manifest.json',financial/'targets.npz'):
        try:open(path,'rb');raise AssertionError('Hidden archive readable')
        except PermissionError:barrier['denied_preflight']+=1
    barrier['preflight']=False
    freeze=read(args.root/'fit/models_frozen.json');digest=freeze.get('sha256',freeze.get('models_sha256'))
    require(digest is not None and file_hash(args.root/'fit/models.joblib')==digest,'Frozen model bytes changed')
    manifest_path=args.root/'fit/manifest.json'
    if manifest_path.exists():
        manifest=read(manifest_path)
        if freeze.get('manifest_sha256'):require(file_hash(manifest_path)==freeze['manifest_sha256'],'Manifest changed')
        for path,value in manifest.get('source_sha256',{}).items():require(file_hash(path)==value,'Frozen source changed: '+path)
    model=joblib.load(args.root/'fit/models.joblib')['families'][args.family]
    allmeta={'main':read(OLD/'episode_manifest.json'),'financial':read(financial/'episode_manifest.json')};meta=allmeta['main']
    chosen=[];training=[]
    for source in sorted({m['source'] for m in meta.values()}):
        for split,holder,limit in [('dev',chosen,3),('train',training,1)]:
            us=[u for u,m in meta.items() if m['split']==split and m['source']==source and m['horizon']==96 and m['condition']=='target_block_10']
            holder.extend(sorted(us,key=lambda u:meta[u]['raw_start'])[:limit])
    require(len(chosen)==7,'Original metadata-only seven changed');require(len(training)==3,'Expected three TRAIN sources')
    fm=allmeta['financial'];require(len(fm)==12,'Financial metadata changed')
    episodes={}
    for suite,source in [('main',OLD),('financial',financial)]:
        with np.load(source/'contexts.npz',allow_pickle=False) as values:
            wanted=chosen+training if suite=='main' else sorted(fm)
            if suite=='main':wanted += [u for u,m in meta.items() if m['split']=='dev' and m['condition']=='raw' and m['horizon']==96]
            for uid in wanted:
                m=allmeta[suite][uid];fields={k:values[uid+'_'+k] for k in ('target','covariates','timestamps','availability')}
                require(array_hash(fields['target'])==m['target_hash'],'Current dirty input changed')
                episodes[suite,uid]=Episode(uid,m['source'],m.get('panel',m['source']),m['parent_group'],m['split'],0,
                    m['raw_start'],m['context_end'],m['horizon'],**fields)
    raw=next(u for (suite,u),e in episodes.items() if suite=='main' and meta[u]['condition']=='raw' and np.isfinite(e.target).all())
    budgets={'low':.8140623268639832,'high':3.5}
    plan=[dict(case_id=f'train-timing-{i}',suite='main',episode_uid=u,controlled=True,pilot=True,budget=3.5,budget_name='high',schedule='fixed') for i,u in enumerate(training)]
    for budget_name,budget in budgets.items():
        plan += [dict(case_id=f'main-natural-{budget_name}-{i}',suite='main',episode_uid=u,controlled=False,pilot=False,budget=budget,budget_name=budget_name,schedule='selective') for i,u in enumerate(chosen)]
        plan += [dict(case_id=f'financial-natural-{budget_name}-{i}',suite='financial',episode_uid=u,controlled=False,pilot=False,budget=budget,budget_name=budget_name,schedule='selective') for i,u in enumerate(sorted(fm))]
    plan += [dict(case_id='controlled-complete',suite='main',episode_uid=raw,controlled=True,pilot=False,budget=3.5,budget_name='high',schedule='selective'),
             dict(case_id='controlled-budget-zero',suite='main',episode_uid=chosen[0],controlled=True,pilot=False,budget=0.,budget_name='high',schedule='selective'),
             dict(case_id='controlled-failure-after-trial',suite='main',episode_uid=chosen[0],controlled=True,pilot=False,budget=3.5,budget_name='high',schedule='fixed',inject_failure=True)]
    atom(out/'protocol.json',dict(family=args.family,plan=plan,model_sha256=digest,online_code_sha256=file_hash(__file__),
        costs='actual complete resident requests; startup separately; no historical timing sidecar accessed',
        cache='per-request same-input/model/H only; no cross-request predictions',
        pilot='three legal TRAIN parents, fixed order only for throughput; never select algorithm from pilot losses',
        hidden_labels_read=0,controlled_cases_not_method_results=True))
    if args.prepare_only:
        preliminary=[]
        for c in plan:
            e=episodes[c['suite'],c['episode_uid']];x,S,names=features(e)
            require(tuple(model['reference'].free_names)==names,'Online free-feature order differs from fit')
            preliminary.append(dict(**c,reference_action=0 if np.isfinite(e.target).all() else int(model['reference'].predict(x,False)),
                scale=S.to_dict(),feature_names=names,visible=json_safe(x)))
        atom(out/'preflight.json',dict(status='passed',cases=preliminary,barrier=barrier,GPU_started=False))
        atom(out/'status.json',dict(status='prepared_only',cases=len(plan)));return
    if args.family=='timesfm':
        from v431_r4_online import install_timesfm_service
        install_timesfm_service()
    runtime=runtime_class()(out/'service',args.family,episodes['main',training[0]])
    rows=[];arrays={}
    try:
        for case in plan:
            e=episodes[case['suite'],case['episode_uid']];runtime.start_request();begun=time.perf_counter()
            x,S,names=features(e);initial=time.perf_counter()-begun
            require(tuple(model['reference'].free_names)==names,'Online free-feature order differs from fit')
            def execute(action):
                trial=runtime.trial(e,action)
                if case.get('inject_failure') and len(runtime.executions)==2:
                    raise RuntimeError('controlled failure after a real candidate trial; keep previous valid decision')
                return trial
            cost_features=dict(zip(names,x));estimate=lambda a:float(model['cost'].action_estimate(a,cost_features))+.051
            result=run(x,S.value,bool(np.isfinite(e.target).all()),case['budget'],model['reference'],model['critics']['current'],
                       model['prior'],estimate,execute,mode='full',schedule=case['schedule'],
                       lambda_value=float(model['lambda'][case['budget_name']]),max_versions=3,
                       initial_seconds=initial,simulate_costs=False)
            prediction=result.pop('final_prediction');action=result['action'];candidate,original,trial=runtime.results[action]
            require(array_hash(prediction)==array_hash(original),'Final output is not the executed prediction')
            arrays[case['case_id']+'_candidate']=candidate;arrays[case['case_id']+'_prediction']=prediction
            # Serialize one actual response before stopping the hot clock.
            response=dict(action=action,arm=POOL[action],input_hash=trial.input_hash,prediction=prediction.tolist(),dtype=str(prediction.dtype))
            atom(out/(case['case_id']+'.response.json'),response)
            hot=time.perf_counter()-begun
            row=dict(allmeta[case['suite']][e.uid],**case)
            row.update(family=args.family,controller=result,origin_scale=S.to_dict(),visible_features=json_safe(dict(zip(names,x))),
                       executed_trials=runtime.executions,actual_versions=len(runtime.executions),
                       unique_input_versions=len({v['input_hash'] for v in runtime.executions}),
                       actual_forecast_calls=sum(not v['identity']['within_request_prediction_reuse'] for v in runtime.executions),
                       hot_request_seconds=hot,total_seconds=hot,budget_overrun=hot>case['budget'],
                       response_output_measured=True,controller_reserved_seconds=result['total_seconds'],
                       final=dict(arm=POOL[action],actual_arm=POOL[trial.actual_action],input_hash=trial.input_hash,
                                  prediction_hash=array_hash(prediction),dtype=str(prediction.dtype),identity=trial.identity),
                       failure=result['failure'])
            rows.append(json_safe(row));atom(out/'decisions.json',rows)
            if case['pilot']:
                atom(out/'train_timing.json',dict(status='running' if len(rows)<3 else 'completed',cases=[r for r in rows if r['pilot']],
                    scope='throughput only; no labels evaluated; model frozen before timing',peak_memory_source='real service raw responses'))
        with (out/'live_arrays.npz').open('xb') as f:np.savez(f,**arrays)
    finally:runtime.close()
    require(barrier['unexpected']==0,'Unexpected hidden archive access')
    atom(out/'visibility_barrier.json',dict(barrier,status='passed',all_final_predictions_saved=True,before_evaluator_open=True))
    barrier['open']=True
    from introact_ts.v431_r4.trajectory_dataset import load_data
    evaluation={suite:load_data(suite) for suite in ('main','financial')}
    for row in rows:
        d=evaluation[row['suite']];u=row['episode_uid'];a=row['controller']['action'];arm=POOL[a];i=d.uids.index(u)
        actual=arrays[row['case_id']+'_prediction'];expected=d.predictions[args.family][u][arm]
        got=arrays[row['case_id']+'_candidate'];wanted=d.old.pools[u][arm]
        require(np.allclose(actual,expected,rtol=1e-6,atol=1e-5),'Same-version live forecast differs')
        require(np.allclose(got,wanted,rtol=1e-6,atol=1e-5,equal_nan=True),'Live governed input differs')
        row.update(candidate_hash_equal=array_hash(got)==array_hash(wanted),prediction_hash_equal=array_hash(actual)==array_hash(expected),
                   actual_prediction_matches_cache=True)
        if not row['pilot']:
            row.update(mae=float(d.MAE[args.family][i,a]),mase=float(d.L[args.family][i,a]),
                       reference_mase=float(d.L[args.family][i,row['controller']['reference_action']]))
    atom(out/'decisions.json',rows)
    natural=[r for r in rows if not r['controlled']]
    atom(out/'status.json',dict(status='completed',cases=len(rows),natural_cases=len(natural),
        natural_nonstop=sum(r['actual_versions']>1 for r in natural),natural_overruns=sum(r['budget_overrun'] for r in natural),
        natural_failures=sum(bool(r['failure']) for r in natural),all_final_predictions_match=True,
        heldout_labels_read=0,financial_natural_gaps_not_claimed=True))


if __name__=='__main__':main()
