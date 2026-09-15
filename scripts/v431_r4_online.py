#!/usr/bin/env python3
"""Real typed r4 requests; all evaluator archives sealed until final predictions.

No GPU task is launched by importing this module. --prepare-only is CPU-only.
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


def timesfm_service():
    """Same official model and service; discard cross-request prediction cache.

    Collector already deduplicates identical arm inputs within a probe. Model
    weights stay resident. Clearing only the memoized forecast does not change
    weights, transforms, point estimator, quantiles or input shapes.
    """
    import serve_v431_r2_timesfm as original
    base=original.TimesFM
    class IndependentTimesFM(base):
        def forecast(self,x,horizon):
            self.cache.clear()
            # Original service locates its raw file via the first matching call.
            # Keep only this forecast's in-memory call list; all raw files and
            # request/response ledgers remain persisted with monotone counter.
            self.calls.clear()
            return super().forecast(x,horizon)
    original.TimesFM=IndependentTimesFM
    sys.argv.remove('--timesfm-service')
    original.main()


def install_timesfm_service():
    import v431_r2_services as module
    from introact_ts.v43.cli import atomic_json
    class IndependentServices(module.R2Services):
        def __init__(self,out,model,code,status,collector,family='timesfm'):
            assert family=='timesfm'
            self.out,self.model,self.code,self.status,self.collector=out,module.with_timesfm(model),code,status,collector
            atomic_json(out/'model_manifest.json',self.model)
            self.processes={};self.logs={};self.startup=[];allowed=out/'allowed_services.json'
            for key in ('tsicl','timesfm'):
                log=(out/(key+'-service.log')).open('x');self.logs[key]=log
                command=[self.model['models'][key]['environment_python']]
                if key=='tsicl':
                    command += [str(Path(__file__).with_name('serve_v43_model.py')),'--key',key,'--allowed',str(allowed)]
                else:
                    (out/'timesfm-native').mkdir()
                    command += [str(Path(__file__).resolve()),'--timesfm-service','--allowed',str(allowed),'--output',str(out/'timesfm-native')]
                self.processes[key]=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True)
            atomic_json(allowed,[dict(model=k,pid=p.pid,start_ticks=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19]) for k,p in self.processes.items()])
            atomic_json(out/'backbone_routing.json',dict(actual_target_backbone='timesfm',
                explicit_routing=True,prediction_cache='cleared before each actual forecast; model resident',
                within_request_deduplication='unchanged Collector.forecasts input hash aliases',
                worker_source=str(Path(__file__).resolve())))
    module.R2Services=IndependentServices


def main():
    p=argparse.ArgumentParser();p.add_argument('--family',choices=['bolt','timesfm'],required=True)
    p.add_argument('--root',type=Path,default=Path('results/v431-r4'));p.add_argument('--output-name')
    p.add_argument('--worker',action='store_true');p.add_argument('--prepare-only',action='store_true');args=p.parse_args()
    args.root=args.root.resolve();name=args.output_name or ('preflight-' if args.prepare_only else 'online-')+args.family
    assert Path(name).name==name and name not in ('.','..');out=args.root/name
    if args.worker:return worker(args,out)
    out.mkdir(exist_ok=False);begin=time.perf_counter()
    command=[sys.executable,str(Path(__file__).resolve()),'--family',args.family,'--root',str(args.root),
        '--output-name',name,'--worker']+(['--prepare-only'] if args.prepare_only else [])
    with (out/'worker.log').open('x') as f:
        process=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT)
        atom(out/'process_accounting.json',dict(status='running',pid=process.pid,command=command))
        code=process.wait()
    wall=time.perf_counter()-begin
    account=dict(status='completed' if code==0 else 'failed',exit_code=code,process_wall_seconds=wall,
        command=command,scope='full worker including natural and controlled cases; CPU prepare-only separately marked',prepare_only=args.prepare_only)
    if (out/'decisions.json').exists():
        rows=json.loads((out/'decisions.json').read_text());hot=sum(r['hot_request_seconds'] for r in rows)
        starts=json.loads((out/'service/service_startup.json').read_text());startup=sum(r['wall_seconds'] for r in starts)
        assert wall+1e-6>=hot+startup
        natural=[r for r in rows if not r['controlled']]
        account.update(requests=len(rows),natural_requests=len(natural),hot_request_seconds=hot,
            model_startup_seconds=startup,remaining_overhead_seconds=wall-hot-startup,
            natural_actual_probe_calls=sum(r['actual_tool_calls'] for r in natural),
            natural_acquisition_decisions=sum(r['branch'] is not None for r in natural),
            natural_hot_overruns=sum(r['budget_overrun'] for r in natural))
        for r in rows:
            r.update(allocated_startup_seconds=startup/len(rows),allocated_other_process_seconds=(wall-hot-startup)/len(rows),
                complete_process_amortized_seconds=r['hot_request_seconds']+(wall-hot)/len(rows))
        atom(out/'decisions.json',rows)
    atom(out/'process_accounting.json',account);print(json.dumps(account),flush=True)
    if code:raise SystemExit(code)


def worker(args,out):
    import joblib
    import numpy as np
    from introact_ts.v43.schemas import Episode,array_hash,require
    from introact_ts.v43.data_io import file_hash
    from introact_ts.v43.agent_inputs import POOL
    from introact_ts.v431.data import PERIODS
    from introact_ts.v431_r4.joint_policy import VisibleState,AcquiredEvidence
    from introact_ts.v431_r4.origin_scale import origin_scale,visible_features,FREE_NAMES
    from introact_ts.v431_r4.trajectory_dataset import evidence_features,TOOLS
    from introact_ts.v431_r3.runtime import LiveRuntime,OLD
    from introact_ts.v431_r3.probe import prepare_probe,registered_specs,visible_descriptor
    project=Path(__file__).resolve().parents[1];financial=project/'results/v431-r2/financial-observation-index-r1'
    read=lambda p:json.loads(Path(p).read_text())
    barrier=dict(open=False,denied_preflight=0,unexpected=0,preflight=False)
    allowed={args.root/'fit'/n for n in ('manifest.json','models_frozen.json','models.joblib')}
    allowed.update(OLD/n for n in ('episode_manifest.json','contexts.npz','model_manifest.json','code_manifest.json','resolved_config.yaml'))
    allowed.update(financial/n for n in ('episode_manifest.json','contexts.npz'))
    results=project/'results'
    def audit(event,arguments):
        if event=='open' and not barrier['open'] and isinstance(arguments[0],(str,bytes,os.PathLike)):
            q=Path(os.fsdecode(arguments[0])).resolve()
            if q.is_relative_to(results) and not q.is_relative_to(out) and q not in allowed:
                if not barrier['preflight']:barrier['unexpected']+=1
                raise PermissionError('r4 labels and unpurchased evidence sealed')
    sys.addaudithook(audit);barrier['preflight']=True
    for path in (OLD/'targets.npz',OLD/'task_labels.json',args.root/'trajectory-final/main/bolt.joblib',
        project/'results/v431-r3/probes/main/probe_manifest.json',project/'results/v431-r3/value_labels.json',financial/'targets.npz'):
        try:open(path,'rb');raise AssertionError('Unsealed archive')
        except PermissionError:barrier['denied_preflight']+=1
    barrier['preflight']=False
    frozen=read(args.root/'fit/models_frozen.json');manifest=read(args.root/'fit/manifest.json')
    require(file_hash(args.root/'fit/models.joblib')==frozen['sha256'],'Frozen model bytes changed')
    require(file_hash(args.root/'fit/manifest.json')==frozen['manifest_sha256'],'Frozen manifest changed')
    for path,digest in manifest['source_sha256'].items():require(file_hash(path)==digest,'Frozen source changed: '+path)
    models=joblib.load(args.root/'fit/models.joblib');policy=models[args.family]['JOINT_high']
    expected=manifest['families'][args.family]['selected']['JOINT_high']
    require(json.dumps(policy.to_dict(),sort_keys=True)==json.dumps(expected,sort_keys=True),'Selected joint policy differs')
    high=float(manifest['budgets']['high']);allmeta={'main':read(OLD/'episode_manifest.json'),'financial':read(financial/'episode_manifest.json')}
    chosen=[];meta=allmeta['main']
    for source in sorted({m['source'] for m in meta.values()}):
        us=[u for u,m in meta.items() if m['split']=='dev' and m['source']==source and m['horizon']==96 and m['condition']=='target_block_10']
        chosen.extend(sorted(us,key=lambda u:meta[u]['raw_start'])[:3])
    require(len(chosen)==7,'Original seven metadata-selected cases changed')
    fm=allmeta['financial'];require(len(fm)==12 and len({m['parent_group'] for m in fm.values()})==2,'Financial metadata changed')
    episodes={}
    for suite,source in [('main',OLD),('financial',financial)]:
        with np.load(source/'contexts.npz',allow_pickle=False) as values:
            wanted=chosen if suite=='main' else sorted(fm)
            raw_candidates=[u for u,m in meta.items() if m['split']=='dev' and m['horizon']==96 and m['condition']=='raw'] if suite=='main' else []
            for uid in wanted+raw_candidates:
                m=allmeta[suite][uid];fields={k:values[uid+'_'+k] for k in ('target','covariates','timestamps','availability')}
                require(array_hash(fields['target'])==m['target_hash'],'Current context hash changed')
                e=Episode(uid,m['source'],m.get('panel',m['source']),m['parent_group'],m['split'],0,m['raw_start'],m['context_end'],m['horizon'],**fields)
                episodes[suite,uid]=e
    raw=next(u for (suite,u),e in episodes.items() if suite=='main' and meta[u]['condition']=='raw' and np.isfinite(e.target).all())
    plan=[dict(case_id='main-natural-'+str(i),suite='main',episode_uid=u,controlled=False,budget=high) for i,u in enumerate(chosen)]
    plan += [dict(case_id='financial-natural-'+str(i),suite='financial',episode_uid=u,controlled=False,budget=high) for i,u in enumerate(sorted(fm))]
    plan += [dict(case_id='controlled-complete',suite='main',episode_uid=raw,controlled=True,budget=high),
             dict(case_id='controlled-budget-zero',suite='main',episode_uid=chosen[0],controlled=True,budget=0.),
             dict(case_id='controlled-failure-after-real-probe',suite='main',episode_uid=chosen[0],controlled=True,budget=high,inject_failure=True)]
    atom(out/'protocol.json',dict(family=args.family,plan=plan,policy_hash=policy.frozen_hash,model_sha256=frozen['sha256'],
        source_sha256=file_hash(__file__),selection='original three-per-source H96 target-block plus all 12 financial, metadata only',
        candidate_cache_policy='no prior-request prediction reuse; Collector deduplicates same-request arm inputs',
        cost_scope='actual resident hot request; startup and process separate; no evaluation cold-sidecar used online',
        budget_accounting='decide admission subtracts all measured elapsed from request start, including diagnostics, prior decisions and probes',
        controlled_cases_not_method_results=True,heldout_labels_read=0))
    def visible(e):
        period=PERIODS.get(e.source,5);scale=origin_scale(e.target,period);x=visible_features(e,period,scale)
        prepared={a:prepare_probe(e,registered_specs(e.horizon)[a],scale.value) for a in ('h32','long','short')}
        applicable={t:all(prepared[a].status=='prepared' for a in atoms) for t,atoms in TOOLS.items()}
        return VisibleState(dict(zip(FREE_NAMES,x.tolist())),bool(np.isfinite(e.target).all()),applicable),scale,prepared
    if args.prepare_only:
        preliminary=[]
        for c in plan:
            state,scale,_=visible(episodes[c['suite'],c['episode_uid']]);decision=policy.decide(state,None,c['budget'])
            preliminary.append(dict(**c,decision=decision,origin_scale=scale.to_dict()))
        # A poisoned offline row must be rejected rather than coerced into state.
        try:policy.decide({'future':[1.]},None,high);raise AssertionError('Untyped state accepted')
        except TypeError:pass
        atom(out/'preflight.json',dict(status='passed',cases=preliminary,barrier=barrier,
             method_performance_evaluated=False,GPU_started=False))
        atom(out/'status.json',dict(status='prepared_only',cases=len(plan),GPU_started=False));return
    if args.family=='timesfm':install_timesfm_service()
    runtime=LiveRuntime(out/'service',args.family,episodes['main',chosen[0]])
    rows=[];arrays={}
    try:
        for case in plan:
            e=episodes[case['suite'],case['episode_uid']];begun=time.perf_counter();state,scale,prepared=visible(e)
            before_elapsed=time.perf_counter()-begun
            before_remaining=max(0.,case['budget']-before_elapsed)
            before=policy.decide(state,None,before_remaining);initial=time.perf_counter()-begun
            branch=before['tool'] if before['kind']=='acquire' else None;actual=[];ev=None;after=before;failure=None
            after_elapsed=None;after_remaining=None
            if branch is not None:
                records={};tool_start=time.perf_counter()
                try:
                    for primitive in TOOLS[branch]:
                        tick=time.perf_counter()
                        try:record=runtime.probe(e,primitive,scale.value,POOL[policy.reference_arm])
                        except Exception as exc:
                            failed_seconds=time.perf_counter()-tick
                            actual.append(dict(probe=primitive,status='failed',error=repr(exc),invoice=dict(charges=[dict(key='failed-'+primitive,seconds=failed_seconds)],total_seconds=failed_seconds)))
                            raise
                        record['probe_descriptor']=visible_descriptor(prepared[primitive].view)
                        actual.append(record);records[primitive]=record
                        if case.get('inject_failure'):raise RuntimeError('controlled failure after real completed probe')
                    names,features=evidence_features(records,branch,scale.value)
                    require(names==tuple(policy.evidence_names[branch]),'Evidence whitelist/order differs from fit')
                    ev=AcquiredEvidence(branch,dict(zip(names,features.tolist())),'completed')
                except Exception as exc:
                    failure=repr(exc);ev=AcquiredEvidence(branch,{},'failed')
                spent=time.perf_counter()-tool_start
                after_elapsed=time.perf_counter()-begun
                after_remaining=max(0.,case['budget']-after_elapsed)
                after=policy.decide(state,ev,after_remaining)
                require(after['kind']=='submit','Second acquisition prohibited')
            elif case.get('inject_failure'):
                # The frozen candidate may legitimately STOP; do not force a
                # different policy and call it natural acquisition coverage.
                failure='controlled failure branch unsupported: frozen policy did not acquire'
            arm=after['arm'];c,pred,invoice,detail=runtime.final(e,arm)
            hot=time.perf_counter()-begun
            arrays[case['case_id']+'_candidate']=c;arrays[case['case_id']+'_prediction']=pred
            if state.fully_observed:require(arm=='A0_NATIVE','Complete input not KEEP')
            if branch is None:require(after==before,'STOP changed terminal decision')
            final=dict(arm=arm,candidate_hash=array_hash(c),prediction_hash=array_hash(pred),invoice=invoice.as_dict(),candidate_status=detail,
                       actual_action='A0_NATIVE' if arm=='A4_RIDGE_CONTEXT' and detail.get('status')=='unsupported' else arm)
            component=dict(initial_visible_and_decision=initial,final_governance_and_forecast=invoice.total_seconds)
            for j,r in enumerate(actual):component['probe-'+str(j)]=r['invoice']['total_seconds']
            remainder=hot-sum(component.values());require(remainder>=-1e-5,'Online phases double counted')
            component['other_planning_logging_and_selection']=max(0.,remainder)
            row=dict(allmeta[case['suite']][e.uid],**case)
            row.update(family=args.family,policy='JOINT_high',policy_hash=policy.frozen_hash,origin_scale=scale.to_dict(),
                before_decision=before,after_decision=after,branch=branch,actual_probes=actual,actual_tool_calls=len(actual),
                before_elapsed_seconds=before_elapsed,before_remaining_budget=before_remaining,
                after_elapsed_seconds=after_elapsed,after_remaining_budget=after_remaining,
                visible_features=state.features,purchased_evidence=None if ev is None else dict(tool=ev.tool,status=ev.status,features=ev.features),
                final=final,failure=failure,hot_request_seconds=hot,total_seconds=hot,budget_overrun=hot>case['budget'],
                component_seconds=component,fully_observed=state.fully_observed)
            rows.append(row);atom(out/'decisions.json',rows)
        with (out/'live_arrays.npz').open('xb') as f:np.savez(f,**arrays)
    finally:runtime.close()
    require(barrier['unexpected']==0,'Unexpected hidden archive access')
    atom(out/'visibility_barrier.json',dict(barrier,status='passed',all_final_predictions_saved=True,before_evaluator_open=True))
    barrier['open']=True
    # Offline evaluator starts only now. Uses already inspected labels, no new set.
    from introact_ts.v431_r4.trajectory_dataset import load_data
    evaluation={suite:load_data(suite) for suite in ('main','financial')}
    for row in rows:
        d=evaluation[row['suite']];u=row['episode_uid'];arm=row['final']['arm'];i=d.uids.index(u)
        actual=arrays[row['case_id']+'_prediction'];expected=d.predictions[args.family][u][arm]
        require(np.allclose(actual,expected,rtol=1e-6,atol=1e-5),'Same-input online model prediction differs')
        got=arrays[row['case_id']+'_candidate'];wanted=d.old.pools[u][arm]
        require(np.allclose(got,wanted,rtol=1e-6,atol=1e-5,equal_nan=True),'Online candidate differs')
        row.update(mae=float(d.MAE[args.family][i,POOL.index(arm)]),mase=float(d.L[args.family][i,POOL.index(arm)]),
            reference_mase=float(d.L[args.family][i,policy.reference_arm]),candidate_hash_equal=array_hash(got)==array_hash(wanted),
            prediction_hash_equal=array_hash(actual)==array_hash(expected),actual_prediction_matches_cache=True)
    atom(out/'decisions.json',rows)
    atom(out/'status.json',dict(status='completed',cases=len(rows),natural_cases=sum(not r['controlled'] for r in rows),
        natural_actual_tool_calls=sum(r['actual_tool_calls'] for r in rows if not r['controlled']),
        all_final_predictions_match=True,heldout_labels_read=0,financial_natural_requests=True,
        natural_failed_tool_requests=sum(bool(r['failure']) for r in rows if not r['controlled']),
        controlled_failed_tool_requests=sum(bool(r['failure']) for r in rows if r['controlled'])))


if __name__=='__main__':
    if '--timesfm-service' in sys.argv:timesfm_service()
    else:main()
