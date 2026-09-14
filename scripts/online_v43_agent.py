#!/usr/bin/env python3
"""Actual sequential evidence acquisition with two isolated resident models."""
import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import joblib
import numpy as np
import yaml
from introact_ts.v43.agent_collect import Collector
from types import SimpleNamespace
from introact_ts.v43.schemas import Episode
from introact_ts.v43.agent_inputs import POOL,TOOLS,mask_views,history_views,context_scale
from introact_ts.v43.agent_policy import execute_policy
from introact_ts.v43.cli import atomic_json,code_manifest
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import array_hash,json_hash,require
from introact_ts.v43.worker_protocol import verify_response


class Services:
    def __init__(self,out,model,code,status,collector):
        self.out,self.model,self.code,self.status,self.collector=out,model,code,status,collector
        self.processes={};self.logs={};self.startup=[]
        allowed=out/'allowed_services.json'
        for key in ('tsicl','bolt'):
            log=(out/(key+'-service.log')).open('x');self.logs[key]=log
            p=subprocess.Popen([model['models'][key]['environment_python'],str(Path(__file__).with_name('serve_v43_model.py')),
                                '--key',key,'--allowed',str(allowed)],stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True)
            self.processes[key]=p
        identities=[dict(model=k,pid=p.pid,start_ticks=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19]) for k,p in self.processes.items()]
        atomic_json(allowed,identities)

    def request(self,key,task,mode,candidates,shard):
        record=self.model['models'][key];rows=[];horizon=candidates[0][0].horizon
        for i,(e,arm,target) in enumerate(candidates):
            require(e.horizon==horizon,'mixed live horizons')
            path=self.out/'inputs'/f'{shard}-{i}.npz'
            with path.open('xb') as f:np.savez(f,target=target,raw_mask=e.observed_mask,covariates=e.covariates,timestamps=e.timestamps,availability=e.availability)
            rows.append(dict(episode_uid=e.uid,candidate_id=arm,input_hash=array_hash(target),raw_mask_hash=array_hash(e.observed_mask),
                covariate_hash=array_hash(e.covariates),availability_hash=array_hash(e.availability),timestamps_hash=array_hash(e.timestamps),
                cutoff=e.context_end,parameters={},parameters_hash=json_hash({}),array_path=str(path),output_length=e.horizon if task=='forecast' else len(e.target)))
        request=dict(schema_version=1,request_id=f'{self.out.parent.name}:{self.out.name}:{shard}',model_revision=record['revision'],model_key=key,
            model_manifest=str(self.out/'model_manifest.json'),code_hash=self.code['hash'],environment_hash=record['environment_lock_sha256'],task=task,
            horizon=horizon,dtype='float64',seed=101,covariate_mode=mode,batch_size=1,normalization='native',rows=rows,
            gpu_lock='/home/vipuser/work/work2/locks/gpu.lock')
        path=self.out/(shard+'.request.json');atomic_json(path,request)
        return request,path

    def command(self,key,command):
        p=self.processes[key];p.stdin.write(json.dumps(command)+'\n');p.stdin.flush()
        path=Path(command['response']);deadline=time.monotonic()+180
        while not path.exists():
            require(p.poll() is None,'live service exited; see its log')
            require(time.monotonic()<deadline,'live request timeout')
            time.sleep(.01)
        response=json.loads(path.read_text());require(response['status'] in ('loaded','completed'),f"live service failed: {response.get('error')}")
        return response

    def load(self,e):
        for key in ('tsicl','bolt'):
            task='impute' if key=='tsicl' else 'forecast';shard='load-'+key
            _,path=self.request(key,task,'none',[(e,'A0_NATIVE',e.target)],shard)
            start=time.perf_counter()
            response=self.command(key,dict(action='load',request=str(path),response=str(self.out/(shard+'.response.json'))))
            self.startup.append(dict(model=key,wall_seconds=time.perf_counter()-start,load_seconds=response['service_initial_load_seconds']))
        atomic_json(self.out/'service_startup.json',self.startup)

    def call(self,key,task,mode,candidates,shard):
        start=time.perf_counter();request,path=self.request(key,task,mode,candidates,shard)
        target=self.out/(shard+'.predictions.npz');response_path=self.out/(shard+'.response.json')
        self.status.update(active_shard=shard,active_service_pid=self.processes[key].pid);atomic_json(self.out/'status.json',self.status)
        response=self.command(key,dict(action='run',request=str(path),response=str(response_path),predictions=str(target)))
        with np.load(target,allow_pickle=False) as f:preds=[f[f'row_{i}'] for i in range(len(candidates))]
        verify_response(request,response,preds)
        self.collector.worker_costs.append(dict(shard=shard,model=key,task=task,n_requests=len(candidates),load_seconds=0.,
            worker_wall_seconds=time.perf_counter()-start,inference_seconds=sum(r['runtime_seconds'] for r in response['rows']),
            peak_gpu_bytes=max(response['load_peak_gpu_bytes'],*(r['peak_gpu_bytes'] for r in response['rows']))))
        atomic_json(self.out/'cost_ledger.json',self.collector.worker_costs)
        return preds

    def close(self):
        for p in self.processes.values():
            if p.poll() is None:
                try:p.stdin.write('{"action":"close"}\n');p.stdin.flush()
                except BrokenPipeError:pass
        for p in self.processes.values():
            try:p.wait(timeout=15)
            except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
        for log in self.logs.values():log.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path)
    parser.add_argument('--output-name',default='online-boundary-v2');args=parser.parse_args()
    root=args.run.resolve()
    # Deny the evaluator's current labels and precomputed evidence at the OS
    # file-open boundary until every selected final forecast has been saved.
    barrier=dict(open=False,denied_preflight=0,denied_unexpected=0)
    forbidden={str((root/p).resolve()) for p in ('task_labels.json','targets.npz','evidence.json','forecasts.npz','candidates.npz','agent/decisions.json')}
    def audit_open(event,arguments):
        if event=='open' and not barrier['open'] and isinstance(arguments[0],(str,bytes,os.PathLike)):
            if str(Path(os.fsdecode(arguments[0])).resolve()) in forbidden:
                raise PermissionError('online evaluator/evidence archive is sealed until final forecasts')
    sys.addaudithook(audit_open)
    for path in forbidden:
        try:
            with open(path,'rb'):raise AssertionError('sealed archive was opened')
        except PermissionError:barrier['denied_preflight']+=1
    read=lambda name:json.loads((root/(name+'.json')).read_text())
    meta=read('episode_manifest')
    with np.load(root/'contexts.npz',allow_pickle=False) as f:
        episodes={uid:Episode(uid,m['source'],m['source'],m['parent_group'],m['split'],0,m['raw_start'],m['context_end'],m['horizon'],
            f[uid+'_timestamps'],f[uid+'_target'],f[uid+'_covariates'],f[uid+'_availability']) for uid,m in meta.items()}
    data=SimpleNamespace(meta=meta,episodes=episodes,read=read)
    manifest=json.loads((root/'agent/model_manifest.json').read_text())
    require(file_hash(root/'agent/models.joblib')==manifest['model_sha256'],'policy checkpoint changed')
    models=joblib.load(root/'agent/models.joblib');code=code_manifest()
    require(code['hash']==data.read('code_manifest')['hash'],'online code differs from frozen collection')
    require('/' not in args.output_name and args.output_name not in ('.','..'),'invalid output directory')
    out=root/args.output_name;out.mkdir(exist_ok=False)
    chosen=[]
    for source in sorted({m['source'] for m in data.meta.values()}):
        uids=[u for u,m in data.meta.items() if m['role']=='dev' and m['source']==source and m['horizon']==96 and m['condition']=='target_block_10']
        chosen+=sorted(uids,key=lambda u:data.meta[u]['raw_start'])[:3]
    atomic_json(out/'protocol.json',dict(selection='first up to 3 dev parents per source, H96 target_block10; fixed before policy results',uids=chosen,
        policy='LEARNED_two_tools',budget=manifest['budgets']['two_tools'],array_tolerance=dict(rtol=1e-6,atol=1e-5),
        startup_cost='measured separately and allocated across these requests',service_computation='GPU lock serializes both isolated resident models'))
    config=yaml.safe_load((root/'resolved_config.yaml').read_text());model=data.read('model_manifest');atomic_json(out/'model_manifest.json',model);atomic_json(out/'code_manifest.json',code)
    status=dict(status='running',phase='online_replay',pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat(),new_heldout_labels_read=0)
    collector=Collector(config,out,code,status,model);services=Services(out,model,code,status,collector);collector.call=services.call
    outputs=[];predictions={};actual_pools={};started=time.perf_counter()
    try:
        services.load(data.episodes[chosen[0]])
        for i,uid in enumerate(chosen):
            e=data.episodes[uid];pools,base,_=collector.pools([e],f'case{i}-base');pool=pools[uid]
            actual_pools[uid]=pool
            acquired={};evidence_equal={}
            def fetch(tool):
                start=time.perf_counter()
                if tool=='strict_mask':
                    planned,reason=mask_views(e);views=[x for x,_ in planned]
                    p,cost,_=collector.pools(views,f'case{i}-mask') if views else ({},{},{})
                    values=defaultdict(list)
                    for view,b in planned:
                        for arm in POOL:
                            x=p[view.uid][arm][b]
                            if np.isfinite(x).all():values[arm].append(float(np.mean(abs(x-e.target[b])))/context_scale(e))
                    evidence={a:([float(np.mean(v)),float(np.std(v)),len(v)/3] if (v:=values[a]) else [None,None,0.]) for a in POOL}
                else:
                    views=history_views(e);hist=[v for v,_ in views];p,cost,_=collector.pools(hist,f'case{i}-history')
                    forecast,_=collector.forecasts(hist,p,f'case{i}-history');values=defaultdict(list);support=0
                    for view,r in views:
                        y=e.target[r:r+32];m=np.isfinite(y);support+=int(m.sum())
                        if m.any():
                            km=float(np.abs(forecast[view.uid,'A0_NATIVE'][m]-y[m]).mean())
                            for arm in POOL:values[arm].append((km-float(np.abs(forecast[view.uid,arm][m]-y[m]).mean()))/context_scale(e))
                    evidence={a:([float(np.mean(v)),float(np.std(v)),support/64] if (v:=values[a]) else [None,None,0.]) for a in POOL}
                actual=time.perf_counter()-start
                acquired[tool]=dict(evidence=evidence,actual_seconds=actual)
                return evidence,actual
            result=execute_policy(e,pool,models['utility'],models['acquisition'],fetch,manifest['estimated_tool_costs'],manifest['budgets']['two_tools'])
            req=[(e,result['arm'],pool[result['arm']])];pred,cost=collector.model_call('bolt','forecast','none',req,f'case{i}-selected-final')
            predictions[uid]=pred[uid,result['arm']]
            outputs.append(dict(episode_uid=uid,**data.meta[uid],**result,base_seconds=base[uid],acquired=acquired,
                                final_forecast_seconds=cost[uid,result['arm']]))
            atomic_json(out/'decisions.json',outputs)
        with (out/'forecasts.npz').open('xb') as f:np.savez(f,**predictions)
        # Open the evaluator only after all seven selected final forecasts exist.
        barrier['open']=True
        barrier['released_at']=datetime.now(timezone.utc).isoformat()
        barrier['final_forecasts_sha256']=file_hash(out/'forecasts.npz')
        atomic_json(out/'label_access_barrier.json',barrier)
        offline={r['episode_uid']:r for r in json.loads((root/'agent/decisions.json').read_text()) if r['policy']=='LEARNED_two_tools'}
        evidence=data.read('evidence')
        with np.load(root/'candidates.npz',allow_pickle=False) as candidates,np.load(root/'forecasts.npz',allow_pickle=False) as forecasts:
            for row in outputs:
                uid=row['episode_uid'];reference=offline[uid]
                row.update(offline_arm=reference['arm'],offline_history=reference['history'],
                    action_agreement=row['arm']==reference['arm'],history_agreement=row['history']==reference['history'],
                    decision_agreement=row['arm']==reference['arm'] and row['history']==reference['history'],
                    candidate_array_agreement=all(np.allclose(actual_pools[uid][a],candidates[uid+'_'+a],rtol=1e-6,atol=1e-5,equal_nan=True) for a in POOL),
                    final_forecast_agreement=bool(np.allclose(predictions[uid],forecasts[uid+'_'+row['arm']],rtol=1e-6,atol=1e-5,equal_nan=False)),
                    acquired_evidence_agreement={t:all(np.allclose(np.array(v['evidence'][a],dtype=float),np.array(evidence[uid][t][a],dtype=float),rtol=1e-6,atol=1e-5,equal_nan=True) for a in POOL) for t,v in row['acquired'].items()})
        with np.load(root/'targets.npz',allow_pickle=False) as targets:
            for row in outputs:
                uid=row['episode_uid'];y,m=targets[uid+'_values'],targets[uid+'_mask']
                row['mae']=float(np.abs(predictions[uid][m]-y[m]).mean())
                row['mase']=row['mae']/data.read('mase_scales')[row['source']]
                row['allocated_startup_seconds']=sum(x['wall_seconds'] for x in services.startup)/len(chosen)
                row['total_governance_seconds']=row['base_seconds']+row['tool_seconds']+row['selection_seconds']+row['allocated_startup_seconds']
        atomic_json(out/'decisions.json',outputs)
        status.update(status='completed',episodes=len(outputs),decision_agreements=sum(r['decision_agreement'] for r in outputs),
            candidate_array_agreements=sum(r['candidate_array_agreement'] for r in outputs),action_agreements=sum(r['action_agreement'] for r in outputs),
            final_forecast_agreements=sum(r['final_forecast_agreement'] for r in outputs),budget_overruns=sum(r['budget_overrun'] for r in outputs),label_access_barrier=barrier,
            online_equivalence_passed=all(r['decision_agreement'] and r['final_forecast_agreement'] and r['candidate_array_agreement'] and all(r['acquired_evidence_agreement'].values()) and not r['budget_overrun'] for r in outputs),
            promotion=False,runtime_seconds=time.perf_counter()-started)
    except Exception as exc:status.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:
        services.close();atomic_json(out/'status.json',status);print(json.dumps(dict(out=str(out),**status)),flush=True)


if __name__=='__main__':main()
