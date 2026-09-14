"""Fit on disjoint temporal train roles, then evaluate deployed decisions on dev."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from .agent_inputs import POOL,TOOLS
from .agent_policy import EvidenceState,features,choose,acquisition_features,execute_policy,FEATURE_NAMES
from .cli import atomic_json
from .data_io import file_hash
from .schemas import Episode,array_hash,json_hash,require

STATES=((),('strict_mask',),('history_probe',),TOOLS)
PARAMS=dict(max_iter=100,max_leaf_nodes=7,learning_rate=.05,min_samples_leaf=20,l2_regularization=1.,early_stopping=False,random_state=101)


def audit_partitions(meta):
    parents={};intervals={}
    for m in meta.values():
        key=m['source'],m['parent_group'];role=m['role']
        require(role in ('scorer_fit','acquisition_fit','dev'),'unknown learning role')
        require(key not in parents or parents[key]==role,'parent leaks across learning roles')
        parents[key]=role
        lo,hi=intervals.get(key,(m['raw_start'],m['context_end']+m['horizon']))
        intervals[key]=(min(lo,m['raw_start']),max(hi,m['context_end']+m['horizon']))
    for source in {k[0] for k in parents}:
        spans=sorted((lo,hi,parents[key]) for key,(lo,hi) in intervals.items() if key[0]==source)
        require(all(a[1]<=b[0] for a,b in zip(spans,spans[1:])),'overlapping raw parent intervals')
    return dict(Counter(parents.values()))


def weights(uids,meta):
    rows=Counter(meta[u]['parent_group'] for u in uids)
    source_parents=defaultdict(set)
    for u in uids:source_parents[meta[u]['source']].add(meta[u]['parent_group'])
    w=np.array([1/(rows[meta[u]['parent_group']]*len(source_parents[meta[u]['source']])) for u in uids])
    return w*len(w)/w.sum()


class AgentDataset:
    def __init__(self,root):
        self.root=Path(root)
        self.meta=self.read('episode_manifest');self.partition_counts=audit_partitions(self.meta)
        self.labels={(r['episode_uid'],r['arm']):r for r in self.read('task_labels')}
        self.evidence=self.read('evidence');self.tool_costs=self.read('tool_costs');self.base_costs=self.read('base_costs')
        self.direct_costs=self.read('direct_candidate_costs');self.forecast_costs=self.read('forecast_costs')
        with np.load(self.root/'candidates.npz',allow_pickle=False) as f:self.pools={uid:{a:f[uid+'_'+a] for a in POOL} for uid in self.meta}
        with np.load(self.root/'contexts.npz',allow_pickle=False) as f:
            self.episodes={uid:Episode(uid,m['source'],m['source'],m['parent_group'],m['split'],0,m['raw_start'],m['context_end'],m['horizon'],
                f[uid+'_timestamps'],f[uid+'_target'],f[uid+'_covariates'],f[uid+'_availability']) for uid,m in self.meta.items()}

    def read(self,name):return json.loads((self.root/(name+'.json')).read_text())

    def state(self,uid,path):
        state=EvidenceState()
        for tool in path:state=state.acquire(tool,self.evidence[uid][tool])
        return state


def fit_utility(data,paths):
    x,y,uids=[],[],[]
    for uid,m in data.meta.items():
        if m['role']!='scorer_fit':continue
        for path in paths:
            state=data.state(uid,path)
            for arm in POOL[1:]:
                x.append(features(data.episodes[uid],data.pools[uid],arm,state))
                y.append(data.labels[uid,arm]['task_gain_mase']);uids.append(uid)
    model=HistGradientBoostingRegressor(**PARAMS).fit(np.stack(x),y,sample_weight=weights(uids,data.meta))
    return model,dict(rows=len(y),parents=len({data.meta[u]['parent_group'] for u in uids}),feature_names=list(FEATURE_NAMES),target='task_gain_mase',role='scorer_fit')


def macro_for_fixed(data,uids,arm):
    grouped=defaultdict(list)
    for uid in uids:
        m=data.meta[uid];grouped[m['source'],m['horizon'],m['condition']].append(data.labels[uid,arm]['mase'])
    return float(np.mean([np.mean(v) for v in grouped.values()]))


def fit_and_evaluate(root):
    data=AgentDataset(root);out=Path(root)/'agent';out.mkdir(exist_ok=False)
    require(data.read('status')['status']=='completed','incomplete model/evidence collection')
    started=time.perf_counter()
    train=[u for u,m in data.meta.items() if m['role']!='dev'];dev=[u for u,m in data.meta.items() if m['role']=='dev']
    utility,utility_meta=fit_utility(data,STATES);simple,simple_meta=fit_utility(data,((),))
    fixed_metrics={a:macro_for_fixed(data,train,a) for a in POOL};fixed=min(POOL,key=lambda a:fixed_metrics[a])
    tool_samples={t:[data.tool_costs[u][t] for u in train] for t in TOOLS}
    estimated={t:float(np.quantile(v,.95)) for t,v in tool_samples.items()}
    absolute=[abs(data.labels[u,a]['task_gain_mase']) for u in train for a in POOL[1:]]
    scale=float(np.median(absolute));scale_rule='median_absolute_task_gain_mase'
    if scale==0:scale=float(np.subtract(*np.quantile(absolute,[.75,.25])));scale_rule='predeclared_iqr_fallback'
    cost_scale=float(np.median([c for v in tool_samples.values() for c in v]))
    require(cost_scale>0,'no measured tool costs')
    penalty=.1*scale/cost_scale
    low=max(estimated.values())*1.1;high=sum(max(v) for v in tool_samples.values())*1.1
    budgets={'zero':0.,'one_tool':low,'two_tools':high}
    x,y,uids,ledger=[],[],[],[]
    for uid,m in data.meta.items():
        if m['role']!='acquisition_fit':continue
        e,pool=data.episodes[uid],data.pools[uid]
        for path in STATES[:3]:
            state=data.state(uid,path);before,_=choose(e,pool,state,utility)
            for tool in TOOLS:
                if tool in path:continue
                after,_=choose(e,pool,state.acquire(tool,data.evidence[uid][tool]),utility)
                gain=data.labels[uid,before]['mase']-data.labels[uid,after]['mase']
                cost=data.tool_costs[uid][tool];value=gain-penalty*cost
                x.append(acquisition_features(e,pool,state,utility,tool));y.append(value);uids.append(uid)
                ledger.append(dict(episode_uid=uid,parent_group=m['parent_group'],history=list(path),tool=tool,before=before,after=after,
                                   task_gain_mase=gain,cost_seconds=cost,penalty=penalty,value_label=value))
    acquisition=HistGradientBoostingRegressor(**PARAMS).fit(np.stack(x),y,sample_weight=weights(uids,data.meta))
    model_path=out/'models.joblib';joblib.dump(dict(utility=utility,simple=simple,acquisition=acquisition),model_path)
    manifest=dict(status='frozen_before_dev_policy_evaluation',created_at=datetime.now(timezone.utc).isoformat(),model_sha256=file_hash(model_path),
                  pool=list(POOL),tools=list(TOOLS),model_parameters=PARAMS,partition_counts=data.partition_counts,utility=utility_meta,simple=simple_meta,
                  acquisition_rows=len(y),acquisition_parents=len({data.meta[u]['parent_group'] for u in uids}),
                  train_best_fixed=fixed,train_fixed_metrics=fixed_metrics,estimated_tool_costs=estimated,budgets=budgets,penalty=penalty,
                  penalty_scale_rule=scale_rule,penalty_multiplier=.1,policy_scope='max_two_step_greedy_predicted_net_task_value',
                  repair_risk_classifier='not_fitted_no_repair_safety_claim',incumbent='PICS_joint_relabel',promotion=False)
    atomic_json(out/'model_manifest.json',manifest);atomic_json(out/'tool_value_training_ledger.json',ledger)
    with (out/'acquisition_training.npz').open('xb') as f:np.savez(f,x=np.stack(x),y=np.array(y),weights=weights(uids,data.meta))
    decisions=[]
    for uid in dev:
        e,pool=data.episodes[uid],data.pools[uid]
        fetch=lambda tool,u=uid:(data.evidence[u][tool],data.tool_costs[u][tool])
        policies={}
        for arm in POOL:
            policies['FIXED_'+arm]=dict(arm=arm,history=[],tool_seconds=0.,selection_seconds=0.,budget=None,budget_overrun=False,trace=[],direct_cost=True)
        policies['TRAIN_BEST_FIXED']=dict(policies['FIXED_'+fixed])
        policies['DIRTY_SELECTOR']=execute_policy(e,pool,simple,None,fetch,estimated,0.,mode='simple')
        policies['ALL_EVIDENCE']=execute_policy(e,pool,utility,None,fetch,estimated,None,mode='all')
        for name,tool in [('MASK_RULE','strict_mask'),('HISTORY_RULE','history_probe')]:
            start=time.perf_counter();values=data.evidence[uid][tool]
            eligible=[a for a in POOL[1:] if values[a][0] is not None and array_hash(pool[a])!=array_hash(pool['A0_NATIVE'])]
            if name=='MASK_RULE':arm=min(eligible,key=lambda a:values[a][0]) if eligible else 'A0_NATIVE'
            else:
                arm=max(eligible,key=lambda a:values[a][0]) if eligible else 'A0_NATIVE'
                if values[arm][0] is None or values[arm][0]<=0:arm='A0_NATIVE'
            policies[name]=dict(arm=arm,history=[tool],tool_seconds=data.tool_costs[uid][tool],selection_seconds=time.perf_counter()-start,
                                budget=None,budget_overrun=False,trace=[])
        for bname,budget in budgets.items():
            policies['LEARNED_'+bname]=execute_policy(e,pool,utility,acquisition,fetch,estimated,budget)
            policies['FIXED_MASK_HISTORY_'+bname]=execute_policy(e,pool,utility,None,fetch,estimated,budget,mode='fixed')
            policies['FIXED_HISTORY_MASK_'+bname]=execute_policy(e,pool,utility,None,fetch,estimated,budget,mode='fixed',fixed_order=TOOLS[::-1])
        for name,decision in policies.items():
            arm=decision['arm'];row=data.labels[uid,arm]
            base=data.direct_costs[uid][arm] if decision.get('direct_cost') else data.base_costs[uid]
            decisions.append(dict(episode_uid=uid,policy=name,**data.meta[uid],**decision,mae=row['mae'],mase=row['mase'],mse=row['mse'],
                                  task_harm=row['task_harm'],task_gain_mase=row['task_gain_mase'],candidate_hash=array_hash(pool[arm]),
                                  base_seconds=base,total_governance_seconds=base+decision['tool_seconds']+decision['selection_seconds'],
                                  final_forecast_seconds=data.forecast_costs[uid+'_'+arm]))
    atomic_json(out/'decisions.json',decisions)
    grouped=defaultdict(list)
    for d in decisions:grouped[d['policy'],d['source'],d['horizon'],d['condition']].append(d)
    detail=[]
    for (name,source,horizon,condition),rows in grouped.items():
        detail.append(dict(policy=name,source=source,horizon=horizon,condition=condition,n=len(rows),
            **{k:float(np.mean([r[k] for r in rows])) for k in ('mae','mase','task_harm','base_seconds','tool_seconds','selection_seconds','total_governance_seconds','final_forecast_seconds')},
            overrun_count=sum(r['budget_overrun'] for r in rows),mean_tools=float(np.mean([len(r['history']) for r in rows]))))
    comparison={}
    for name in sorted({d['policy'] for d in decisions}):
        rows=[r for r in detail if r['policy']==name];require(len(rows)==18,'dev policy denominator mismatch')
        comparison[name]={k:float(np.mean([r[k] for r in rows])) for k in ('mae','mase','task_harm','base_seconds','tool_seconds','selection_seconds','total_governance_seconds','final_forecast_seconds','mean_tools')}
        comparison[name].update(overrun_count=sum(r['overrun_count'] for r in rows),budget_claim_valid=all(r['overrun_count']==0 for r in rows))
    atomic_json(out/'metrics_by_source.json',detail)
    atomic_json(out/'comparison.json',dict(scope='train_fitted_dev_evaluation_not_confirmatory',policies=comparison,confidence_interval=None,promotion=False,
        dev_best_fixed_diagnostic=min(('FIXED_'+a for a in POOL),key=lambda k:comparison[k]['mase']),
        limitation='3 sources, USTS 1 dev parent; no independent confirmation; costs are measured batch-amortized invoices, cold online replay pending'))
    atomic_json(out/'status.json',dict(status='completed',dev_episodes=len(dev),n_policies=len(comparison),decision_rows=len(decisions),runtime_seconds=time.perf_counter()-started,
                                      new_heldout_labels_read=0,promotion=False,online_replay='pending'))
    return comparison
