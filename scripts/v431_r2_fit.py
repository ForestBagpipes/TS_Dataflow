#!/usr/bin/env python3
"""One frozen r2 rule, independent support curves and joint two-family DEV table."""
from collections import defaultdict
from datetime import datetime,timezone
import hashlib,json,time
from pathlib import Path
import joblib,numpy as np
from sklearn.tree import DecisionTreeClassifier
from introact_ts.v43.agent_inputs import POOL,mask_views
from introact_ts.v43.cli import atomic_json
from introact_ts.v43.schemas import array_hash
from introact_ts.v431.data import FEATURE_NAMES
from introact_ts.v431.acquisition import Charge,CostInvoice,AcquiredBranch
from introact_ts.v431_r2.data import R2Data,ROOT,SPRINT,OLD,read,sha
from introact_ts.v431_r2.policy import StatePolicy,EvidenceState,freeze_reference
from introact_ts.v431_r2.acquisition import build_value_row,fit_acquirer,make_value_labels,execute_one_step,BRANCH_TOOLS

def state_at(data,family,i,kind):
    state=EvidenceState()
    for tool in BRANCH_TOOLS[kind]:state=state.acquire(tool,data.mask[i] if tool=='mask' else data.history[family][i])
    return state

def nested_indices(data,fit):
    subsets={.25:set(),.5:set(),1.:set(data.parents[fit])}
    for source in sorted({data.meta[data.uids[i]]['source'] for i in fit}):
        parents=sorted({data.parents[i] for i in fit if data.meta[data.uids[i]]['source']==source},key=lambda p:min(data.meta[data.uids[i]]['raw_start'] for i in fit if data.parents[i]==p))
        half=[parents[j] for j in np.linspace(0,len(parents)-1,max(1,int(len(parents)*.5)),dtype=int)]
        quarter=[half[j] for j in np.linspace(0,len(half)-1,max(1,int(len(parents)*.25)),dtype=int)]
        subsets[.5].update(half);subsets[.25].update(quarter)
    assert subsets[.25]<=subsets[.5]<=subsets[1.]
    return {p:np.array([i for i in fit if data.parents[i] in names]) for p,names in subsets.items()}

def grouped_summary(rows):
    by=defaultdict(list)
    for r in rows:by[r['family'],r['policy'],r['source'],r['parent_group'],r['horizon'],r['condition']].append(r)
    parent_rows=[]
    for key,group in by.items():
        assert len(group)==1,'duplicate common episode'
        parent_rows.append(group[0])
    sources=defaultdict(list)
    for r in parent_rows:sources[r['family'],r['policy'],r['source']].append(r)
    detail=[]
    for (f,p,s),rs in sources.items():
        detail.append(dict(family=f,policy=p,source=s,parents=len({r['parent_group'] for r in rs}),episodes=len(rs),
            **{k:float(np.mean([r[k] for r in rs])) for k in ('mase','mae','total_seconds','tool_count','switch_gain','wrong_switch_loss','net_gain')},
            budget_overruns=sum(r['budget_overrun'] for r in rs),failed_tools=sum(r.get('failure') is not None for r in rs)))
    table=[]
    for f,p in sorted({(r['family'],r['policy']) for r in rows}):
        ds=[r for r in detail if r['family']==f and r['policy']==p];rs=[r for r in rows if r['family']==f and r['policy']==p]
        table.append(dict(family=f,policy=p,parents=len({r['parent_group'] for r in rs}),episodes=len(rs),sources=len(ds),
            **{k:float(np.mean([r[k] for r in ds])) for k in ('mase','mae','total_seconds','tool_count','switch_gain','wrong_switch_loss','net_gain')},
            budget_overruns=sum(r['budget_overruns'] for r in ds),failures=sum(r['failed_tools'] for r in ds)))
    return table,detail

def main():
    start=time.perf_counter();assert not (ROOT/'terminal_manifest.json').exists(),'do not overwrite frozen r2'
    cfg=read('configs/v431_r2/manifest.json');data=R2Data();fit,check,acq,dev=[data.ids(x) for x in ('fit','T_check','T_acq','dev')]
    subsets=nested_indices(data,fit);atomic_json(ROOT/'partition.json',dict(metadata=data.meta,nested_fit_parent_ids={str(k):sorted(set(data.parents[v])) for k,v in subsets.items()},
        fit_parent_ids=sorted(set(data.parents[fit])),check_parent_ids=sorted(set(data.parents[check])),acq_parent_ids=sorted(set(data.parents[acq])),dev_parent_ids=sorted(set(data.parents[dev]))))
    models={'policies':{},'acquirers':{},'legacy_carts':{}};manifest=dict(version='v4.3.1-r2',created_at=datetime.now(timezone.utc).isoformat(),config_sha256=sha('configs/v431_r2/manifest.json'),budgets=cfg['budgets'],families={},evidence_condition='target_horizon',heldout_labels_read=0)
    curves=[];fitpredictions={}
    for family in cfg['families']:
        L=data.L[family];reference=freeze_reference(L[fit],data.weights(fit),data.parents[fit])
        policy=StatePolicy(reference['action'],reference['parent_ids'],FEATURE_NAMES).fit(data.X[fit],data.state_evidence(family,fit),L[fit],data.weights(fit),data.parents[fit]);models['policies'][family]=policy
        hashes={kind:[policy.choose(data.X[i],state_at(data,family,i,kind),fully_observed=bool(data.complete[i]))['action'] for i in fit] for kind in BRANCH_TOOLS}
        branch_estimates={kind:float(np.quantile([data.tool_invoice(family,i,kind).total_seconds+max(data.final_invoice(family,i,a,True).total_seconds for a in range(5)) for i in fit],.95))*1.1 for kind in BRANCH_TOOLS}
        action_estimates={a:float(np.quantile([data.final_invoice(family,i,k,True).total_seconds for i in fit],.95))*1.1 for k,a in enumerate(POOL)}
        state_risks={kind:float(np.dot(data.weights(fit),L[fit,np.array(acts)])) for kind,acts in hashes.items()}
        fixed={b:min([k for k in BRANCH_TOOLS if branch_estimates[k]<=budget],key=lambda k:(state_risks[k],len(BRANCH_TOOLS[k]),k),default=None) for b,budget in cfg['budgets'].items()}
        manifest['families'][family]=dict(terminal_hash=policy.frozen_hash,reference=reference,branch_estimates=branch_estimates,action_estimates=action_estimates,fixed_state=fixed,fit_state_risks=state_risks,state_support=policy.audit_,fit_parents=len(reference['parent_ids']))
        atomic_json(ROOT/(family+'.terminal.json'),policy.to_dict())
        # The old same-evidence comparator keeps original T_fit54 and depth3.
        original=data.ids('T_fit');Z=np.c_[data.X,data.mask,data.history[family]];med=np.nanmedian(Z[original],axis=0);med=np.where(np.isfinite(med),med,0.)
        design=np.c_[np.where(np.isfinite(Z),Z,med),np.isfinite(Z)]
        oldcart=DecisionTreeClassifier(max_depth=3,min_samples_leaf=96,random_state=101).fit(design[original],np.argmin(L[original],axis=1),sample_weight=data.weights(original))
        support={int(leaf):len(set(data.parents[original][oldcart.apply(design[original])==leaf])) for leaf in set(oldcart.apply(design[original]))};assert min(support.values())>=16
        models['legacy_carts'][family]=(oldcart,med,support)
        for fraction,subset in subsets.items():
            ref=freeze_reference(L[subset],data.weights(subset),data.parents[subset])
            subpolicy=policy if fraction==1. else StatePolicy(ref['action'],ref['parent_ids'],FEATURE_NAMES).fit(data.X[subset],data.state_evidence(family,subset),L[subset],data.weights(subset),data.parents[subset])
            for kind in ('none',*BRANCH_TOOLS):
                acts=np.array([subpolicy.choose(data.X[i],EvidenceState() if kind=='none' else state_at(data,family,i,kind),fully_observed=bool(data.complete[i]))['action'] for i in check]);gain=L[check,ref['action']]-L[check,acts]
                curves.append(dict(family=family,fraction=fraction,state=kind,fit_parents=len(set(data.parents[subset])),check_parents=len(set(data.parents[check])),mase=float(np.dot(data.weights(check),L[check,acts])),reference=ref['arm'],reference_mase=float(np.dot(data.weights(check),L[check,ref['action']])),correct_switch_gain=float(np.dot(data.weights(check),np.maximum(gain,0))),wrong_switch_loss=float(np.dot(data.weights(check),np.maximum(-gain,0))),terminal_hash=subpolicy.frozen_hash,state_support=subpolicy.audit_.get(kind),fit_parent_ids=sorted(set(data.parents[subset]))))
    # Exact terminal-set freeze precedes every tool-value label.
    atomic_json(ROOT/'terminal_manifest.json',manifest);atomic_json(ROOT/'learning_curves.json',curves)
    joblib.dump({'policies':models['policies']},ROOT/'terminal_models.joblib');atomic_json(ROOT/'terminal_freeze.json',dict(created_at=datetime.now(timezone.utc).isoformat(),sha256=sha(ROOT/'terminal_models.joblib'),terminal_hashes={f:m.frozen_hash for f,m in models['policies'].items()}))
    labels={}
    for family,policy in models['policies'].items():
        items=[];weights=data.weights(acq)
        for j,i in enumerate(acq):
            tick=time.perf_counter();before=policy.choose(data.X[i],EvidenceState(),fully_observed=bool(data.complete[i]));before_cost=time.perf_counter()-tick
            shared_before=CostInvoice((Charge('initial-selection:'+family+':'+data.uids[i],before_cost),))
            for kind,tools in BRANCH_TOOLS.items():
                tick=time.perf_counter();state=state_at(data,family,i,kind);after=policy.choose(data.X[i],state,fully_observed=bool(data.complete[i]));after_cost=time.perf_counter()-tick;tool_invoices={t:data.tool_invoice(family,i,t) for t in tools}
                items.append(build_value_row(uid=data.uids[i],parent=data.parents[i],policy=policy,dirty_features=data.X[i],losses=data.L[family][i],after_state=state,
                    stop_invoice=data.final_invoice(family,i,before['action'],True).merge(shared_before),acquire_invoice=data.final_invoice(family,i,after['action'],True).merge(shared_before,*tool_invoices.values(),CostInvoice((Charge('post-evidence-selection:'+family+':'+data.uids[i]+':'+kind,after_cost),))),tool_invoices=tool_invoices,weight=float(weights[j]),fully_observed=bool(data.complete[i])))
        reference=manifest['families'][family]['reference']['action']
        aq=fit_acquirer(items,policy.frozen_hash,FEATURE_NAMES,task_differences=(data.L[family][fit]-data.L[family][fit,reference,None]).ravel(),forbidden_parents=set(data.parents[np.r_[fit,check]]));models['acquirers'][family]=aq
        labels[family]=make_value_labels(items,policy.frozen_hash,aq.lambda_value);atomic_json(ROOT/(family+'.acquisition.json'),aq.report)
    atomic_json(ROOT/'value_labels.json',labels);joblib.dump(models,ROOT/'models.joblib');atomic_json(ROOT/'models_frozen.json',dict(created_at=datetime.now(timezone.utc).isoformat(),sha256=sha(ROOT/'models.joblib'),terminal_manifest_sha256=sha(ROOT/'terminal_manifest.json'),value_labels_sha256=sha(ROOT/'value_labels.json'),stage='frozen_before_r2_dev_evaluation'))
    rows=[]
    for family,policy in models['policies'].items():
        fm=manifest['families'][family];aq=models['acquirers'][family];ref=fm['reference']['action']
        def save(i,name,a,invoice,**extra):
            u=data.uids[i];arm=POOL[int(a)];gain=data.L[family][i,ref]-data.L[family][i,int(a)]
            rows.append(dict(family=family,policy=name,episode_uid=u,**data.meta[u],arm=arm,reference_arm=POOL[ref],mase=float(data.L[family][i,int(a)]),mae=float(data.MAE[family][i,int(a)]),candidate_hash=array_hash(data.old.pools[u][arm]),forecast_hash=array_hash(data.predictions[family][u][arm]),dirty_features=data.X[i].tolist(),fully_observed=bool(data.complete[i]),total_seconds=invoice.total_seconds,invoice=invoice.as_dict(),tool_count=0,budget_overrun=False,switch_gain=max(float(gain),0.),wrong_switch_loss=max(float(-gain),0.),net_gain=float(gain),**extra))
        for i in dev:
            u=data.uids[i]
            for name,a in [('KEEP',0),('FIXED_TSICL',2),('FIXED_REFERENCE',ref)]:save(i,name,a,data.final_invoice(family,i,a))
            cart,med,_=models['legacy_carts'][family];z=np.r_[data.X[i],data.mask[i],data.history[family][i]];a=int(cart.predict(np.r_[np.where(np.isfinite(z),z,med),np.isfinite(z)][None])[0]);save(i,'EXISTING_SAME_EVIDENCE_CART',a,data.final_invoice(family,i,a,True).merge(data.tool_invoice(family,i,'both')));rows[-1].update(tool_count=2,history=['mask','history'])
            initial=policy.choose(data.X[i],EvidenceState(),fully_observed=bool(data.complete[i]));stop=initial['action']
            applicable={'mask':len(mask_views(data.episodes[u])[0])==3,'history':data.episodes[u].horizon<512};applicable['both']=all(applicable.values())
            estimates={k:CostInvoice((Charge('estimated-complete-'+k,v),)) for k,v in fm['branch_estimates'].items()}
            def fetch(kind):
                state=state_at(data,family,i,kind);a=policy.choose(data.X[i],state,fully_observed=bool(data.complete[i]))['action']
                return AcquiredBranch(POOL[a],data.final_invoice(family,i,a,True).merge(data.tool_invoice(family,i,kind)),array_hash(np.r_[*(state.result(t)[1] for t in BRANCH_TOOLS[kind])]),policy.frozen_hash)
            for b,B in cfg['budgets'].items():
                fixed=fm['fixed_state'][b]
                for name,mode,order in [('R2_AGENT','learned',None),('FIXED_ACQUIRE_CART','fixed',None if fixed is None else (fixed,)),('FORCE_STOP','stop',None),('FIXED_MASK_CART','fixed',('mask',)),('FIXED_HISTORY_CART','fixed',('history',)),('FIXED_BOTH_CART','fixed',('both',))]:
                    begun=time.perf_counter();result=execute_one_step(terminal_hash=policy.frozen_hash,visible_features=data.X[i],stop_arm=POOL[stop],stop_invoice=data.final_invoice(family,i,stop,True),branch_estimates=estimates,budget=B,applicable=applicable,model=aq,fetch=fetch,fully_observed=bool(data.complete[i]),mode='stop' if name=='FIXED_ACQUIRE_CART' and fixed is None else mode,tool_order=order)
                    invoice=CostInvoice(tuple(Charge(**v) for v in result['invoice']['charges'])).merge(CostInvoice((Charge('decision:'+family+':'+u,time.perf_counter()-begun),)))
                    save(i,name+'_'+b,POOL.index(result['arm']),invoice)
                    rows[-1].update({k:v for k,v in result.items() if k not in ('arm','invoice','total_seconds','budget_overrun')});rows[-1]['budget_overrun']=invoice.total_seconds>B
    atomic_json(ROOT/'decisions.json',rows);table,detail=grouped_summary(rows);atomic_json(ROOT/'table.json',table);atomic_json(ROOT/'metrics_by_source.json',detail)
    atomic_json(ROOT/'offline_costs.json',dict(fit_evaluate_process_body_seconds=time.perf_counter()-start,dataset_initialization_seconds=data.initialization_seconds,dirty_diagnostics_seconds=float(data.diagnostic_costs.sum()),generation='old Bolt and mask costs reused; new TimesFM cache cost_scope.json separately',per_window_selection='measured and included in invoices',heldout_labels_read=0))
    atomic_json(ROOT/'status.json',dict(status='completed',families=cfg['families'],policies=len(table),decisions=len(rows),runtime_seconds=time.perf_counter()-start,heldout_labels_read=0,promotion=False));print(json.dumps(read(ROOT/'status.json')),flush=True)

if __name__=='__main__':main()
