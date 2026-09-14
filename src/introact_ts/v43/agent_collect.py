"""Generate actual candidate/task/evidence caches before fitting any policy."""
from collections import defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import numpy as np
from .agent_inputs import POOL,TOOLS,training_origins,materialize_training,mask_views,history_views,context_scale
from .batch_executor import make_executor
from .candidates import prepare_model_input
from .cli import atomic_json,code_manifest
from .data_io import file_hash,read_rows
from .frozen_archive import FrozenP2Archive
from .p2_candidates import ridge_candidate
from .schemas import Candidate,array_hash,verify_impute,require,json_hash
from .task_labels import read_target,TaskTarget,evaluate_pair


class Collector:
    def __init__(self, config,out,code,status,model):
        self.config,self.out,self.status=config,out,status
        self.call,self.worker_costs=make_executor(config,out,code,atomic_json,status,model)
        self.invoices=[]
        self.forecast_aliases={}
        self.component_costs={}

    def model_call(self,key,task,mode,requests,shard):
        if not requests:return {},{}
        started=time.perf_counter();values=self.call(key,task,mode,requests,shard)
        response=json.loads((self.out/(shard+'.response.json')).read_text())
        total=time.perf_counter()-started
        inference=sum(r['runtime_seconds'] for r in response['rows'])
        overhead=max(0.,total-inference)/len(requests)
        predictions,costs={},{}
        for (e,arm,_),r,value in zip(requests,response['rows'],values):
            predictions[e.uid,arm]=value;costs[e.uid,arm]=r['runtime_seconds']+overhead
            self.invoices.append(dict(episode_uid=e.uid,arm=arm,shard=shard,inference_seconds=r['runtime_seconds'],
                                      allocated_shard_overhead_seconds=overhead,charged_seconds=costs[e.uid,arm]))
        atomic_json(self.out/'model_invoices.json',self.invoices)
        return predictions,costs

    def pools(self,episodes,prefix):
        output,costs,cpu={},{},{}
        for h in sorted({e.horizon for e in episodes}):
            group=[e for e in episodes if e.horizon==h]
            missing=[e for e in group if np.isnan(e.target).any()]
            mono,mc=self.model_call('tsicl','impute','none',[(e,'A2_SINGLE',e.target) for e in missing],f'{prefix}-h{h}-single')
            cov,cc=self.model_call('tsicl','impute','past_only',[(e,'A3_COV',e.target) for e in missing],f'{prefix}-h{h}-cov')
            for e in group:
                start=time.perf_counter();has_missing=np.isnan(e.target).any()
                ff_start=time.perf_counter();ff=prepare_model_input(e.target,native_nan=False);ff_cost=time.perf_counter()-ff_start
                ridge_start=time.perf_counter();ridge,_=ridge_candidate(e);ridge_cost=time.perf_counter()-ridge_start
                arms=[Candidate(e.uid,'A0_NATIVE',e.target),Candidate(e.uid,'A0_FFILL',ff),
                      Candidate(e.uid,'A2_SINGLE',mono[e.uid,'A2_SINGLE'] if has_missing else e.target),
                      Candidate(e.uid,'A3_COV',cov[e.uid,'A3_COV'] if has_missing else e.target),ridge]
                for c in arms:verify_impute(e,c)
                output[e.uid]={c.candidate_id:c.target for c in arms};cpu[e.uid]=time.perf_counter()-start
                costs[e.uid]=cpu[e.uid]+(mc[e.uid,'A2_SINGLE']+cc[e.uid,'A3_COV'] if has_missing else 0.)
                shared=max(0.,cpu[e.uid]-ff_cost-ridge_cost)/len(POOL)
                self.component_costs[e.uid]={'A0_NATIVE':shared,'A0_FFILL':ff_cost+shared,
                    'A2_SINGLE':shared+(mc[e.uid,'A2_SINGLE'] if has_missing else 0.),
                    'A3_COV':shared+(cc[e.uid,'A3_COV'] if has_missing else 0.),'A4_RIDGE_CONTEXT':ridge_cost+shared}
        return output,costs,cpu

    def forecasts(self,episodes,pools,prefix):
        output,costs={},{}
        for h in sorted({e.horizon for e in episodes}):
            requests=[];aliases={}
            for e in (e for e in episodes if e.horizon==h):
                seen={}
                for arm in POOL:
                    target=pools[e.uid][arm];digest=array_hash(target)
                    if digest not in seen:seen[digest]=arm;requests.append((e,arm,target))
                    aliases[e.uid,arm]=(e.uid,seen[digest])
            values,charged=self.model_call('bolt','forecast','none',requests,f'{prefix}-h{h}-bolt')
            for key,alias in aliases.items():
                output[key]=values[alias];costs[key]=charged[alias]
                self.forecast_aliases[prefix,*key]=alias
        return output,costs


def run_collect(config,out,code,status):
    from .agent_fit import PARAMS
    settings=config['agent']
    require(tuple(settings['pool'])==POOL and tuple(settings['tools'])==TOOLS,'unregistered agent pool/tools')
    require(settings['model']==PARAMS and settings['train_role_time_fraction']==.7
            and settings['value_cost_penalty_multiplier']==.1 and settings['max_rounds']==2,'unregistered learning settings')
    gate=json.loads(Path(config['runtime']['semantic_gate']).read_text())
    require(gate['status']=='completed' and gate['code_hash']==code['hash'] and gate['config_hash']==json_hash(config),'agent CPU gate stale')
    atomic_json(out/'semantic_gate.json',gate)
    archive=FrozenP2Archive(config['agent']['dev_archive'],config['agent']['dev_evidence'])
    atomic_json(out/'imported_dev_producer.json',archive.provenance)
    records=archive.read('data_manifest')
    for r in records:require(file_hash(r['path'])==r['file_sha256'],'underlying data changed')
    train_origins=training_origins(records,config['agent']['maximum_train_origins_per_source'])
    io_start=time.perf_counter();train,meta=materialize_training(records,train_origins,config)
    dev=list(archive.contexts.values());episodes=train+dev
    for uid,m in archive.meta.items():meta[uid]=dict(m,role='dev')
    io_seconds=time.perf_counter()-io_start
    atomic_json(out/'data_manifest.json',records);atomic_json(out/'train_origins.json',train_origins)
    atomic_json(out/'episode_manifest.json',meta)
    model=json.loads(Path(config['models']['manifest']).read_text());atomic_json(out/'model_manifest.json',model)
    collector=Collector(config,out,code,status,model)
    status.update(phase='base_candidates',episodes=len(episodes),future_labels_read=0,heldout_labels_read=0)
    atomic_json(out/'status.json',status)
    # Measure the same pool for both splits so original unused A4_FULL/A5 CPU
    # work cannot inflate a fixed baseline's bill. Historical dev inputs/labels
    # stay frozen; generation and forecast costs are freshly measured together.
    pools,base_costs,base_cpu=collector.pools(episodes,'base')
    direct_costs={e.uid:{a:collector.component_costs[e.uid][a]+io_seconds/len(episodes) for a in POOL} for e in episodes}
    atomic_json(out/'direct_candidate_costs.json',direct_costs)
    for uid in base_costs:base_costs[uid]+=io_seconds/len(episodes)
    evidence={e.uid:{} for e in episodes};tool_costs={e.uid:{} for e in episodes}
    mask_plan={};views=[];owners={}
    for e in episodes:
        start=time.perf_counter();planned,reason=mask_views(e)
        mask_plan[e.uid]=dict(reason=reason,blocks=[np.flatnonzero(b).tolist() for _,b in planned])
        tool_costs[e.uid]['strict_mask']=time.perf_counter()-start
        for view,mask in planned:views.append(view);owners[view.uid]=(e.uid,mask)
    atomic_json(out/'mask_plan.json',mask_plan)
    status['phase']='strict_mask';atomic_json(out/'status.json',status)
    masked,mask_cost,_=collector.pools(views,'mask')
    mask_errors=defaultdict(lambda:defaultdict(list))
    byuid={e.uid:e for e in episodes}
    for view in views:
        uid,b=owners[view.uid];e=byuid[uid];start=time.perf_counter()
        for arm in POOL:
            pred=masked[view.uid][arm][b]
            if np.isfinite(pred).all():mask_errors[uid][arm].append(float(np.mean(abs(pred-e.target[b])))/context_scale(e))
        tool_costs[uid]['strict_mask']+=mask_cost[view.uid]+time.perf_counter()-start
    del masked,views
    for e in episodes:
        evidence[e.uid]['strict_mask']={arm:([float(np.mean(v)),float(np.std(v)),len(v)/3] if (v:=mask_errors[e.uid][arm]) else [None,None,0.]) for arm in POOL}
    history=[];history_owner={}
    for e in episodes:
        for view,r in history_views(e):history.append(view);history_owner[view.uid]=(e.uid,r)
    status['phase']='history_probe';atomic_json(out/'status.json',status)
    hp,hcost,_=collector.pools(history,'history')
    predictions,predcost=collector.forecasts(history,hp,'history')
    del hp
    history_errors=defaultdict(lambda:defaultdict(list));support=defaultdict(int)
    for view in history:
        uid,r=history_owner[view.uid];e=byuid[uid];start=time.perf_counter()
        target=e.target[r:r+32];mask=np.isfinite(target);support[uid]+=int(mask.sum())
        if mask.any():
            km=float(np.mean(abs(predictions[view.uid,'A0_NATIVE'][mask]-target[mask])))
            for arm in POOL:
                mae=float(np.mean(abs(predictions[view.uid,arm][mask]-target[mask])))
                history_errors[uid][arm].append((km-mae)/context_scale(e))
        # Alias forecasts are billed once per distinct prediction actually used.
        distinct={collector.forecast_aliases['history',view.uid,arm]:predcost[view.uid,arm] for arm in POOL}
        tool_costs[uid]['history_probe']=tool_costs[uid].get('history_probe',0.)+hcost[view.uid]+sum(distinct.values())+time.perf_counter()-start
    for e in episodes:
        evidence[e.uid]['history_probe']={arm:([float(np.mean(v)),float(np.std(v)),support[e.uid]/64] if (v:=history_errors[e.uid][arm]) else [None,None,0.]) for arm in POOL}
    atomic_json(out/'evidence.json',evidence);atomic_json(out/'tool_costs.json',tool_costs)
    atomic_json(out/'base_costs.json',base_costs)
    atomic_json(out/'cost_scope.json',dict(base='fresh actual candidate pool cost for both train/dev',worker_overhead='allocated actual shard wall including load and IPC',
                                         offline_training_generation='all counterfactual invoices retained; deployed trace charges only acquired tools',data_io_seconds=io_seconds))
    with (out/'candidates.npz').open('xb') as f:np.savez(f,**{uid+'_'+arm:x for uid,pool in pools.items() for arm,x in pool.items()})
    with (out/'contexts.npz').open('xb') as f:np.savez(f,**{e.uid+'_'+name:getattr(e,name) for e in episodes for name in ('target','covariates','timestamps','availability')})
    status['phase']='final_forecasts';atomic_json(out/'status.json',status)
    forecasts,forecast_cost=collector.forecasts(episodes,pools,'final')
    with (out/'forecasts.npz').open('xb') as f:np.savez(f,**{uid+'_'+arm:x for (uid,arm),x in forecasts.items()})
    atomic_json(out/'forecast_costs.json',{uid+'_'+arm:x for (uid,arm),x in forecast_cost.items()})
    status['phase']='task_labels';status['forecast_status']='completed';atomic_json(out/'status.json',status)
    scales=archive.read('mase_scales');lookup={r['source']:r for r in records};cache={};targets={};labels=[]
    oldtargets=archive.arrays('targets.npz')
    for e in episodes:
        if e.split=='dev':target=TaskTarget(e.uid,'dev',oldtargets[e.uid+'_values'],oldtargets[e.uid+'_mask'])
        else:
            key=e.parent_group,e.horizon
            if key not in cache:
                record=lookup[e.source]
                target=read_target(lambda lo,hi:read_rows(record,lo,hi,'train')[1][:,0],e)
                cache[key]=target.values;status['future_labels_read']+=1
            target=TaskTarget(e.uid,'train',cache[key],np.isfinite(cache[key]))
        for arm in POOL:
            row=evaluate_pair(target,forecasts[e.uid,'A0_NATIVE'],forecasts[e.uid,arm],scale=scales[e.source])
            require(row['status']=='completed' and row['mase'] is not None,'minimal agent requires complete common task labels')
            labels.append(dict(row,arm=arm,**meta[e.uid],task_gain_mase=row['task_gain']/scales[e.source]))
        targets[e.uid+'_values'],targets[e.uid+'_mask']=target.values,target.mask
    with (out/'targets.npz').open('xb') as f:np.savez(f,**targets)
    atomic_json(out/'task_labels.json',labels);atomic_json(out/'mase_scales.json',scales)
    status.update(status='completed',phase='agent_collect',train_episodes=len(train),dev_episodes=len(dev),labels=len(labels),
                  governance_pool=list(POOL),tools=list(TOOLS),promotion=False)
