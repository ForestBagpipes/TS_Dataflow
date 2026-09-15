#!/usr/bin/env python3
"""Frozen legacy controls and native baselines on the exact r4 common denominator."""
from pathlib import Path
import argparse,time
import joblib,numpy as np
from v431_r4_run import ROOT,BUDGETS,load_batch,row_record,summarize,read,write,sha
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.schemas import array_hash
from introact_ts.v431_r4.branch_cost import BranchCost
from introact_ts.v431_r4.legacy_retrain import build_legacy_evidence

TOOLS=('H32','H','control')

def setup():
    root=ROOT/'legacy-final';status=read(root/'status.json')
    assert sha(root/'models.joblib')==status['models_sha256']
    models=joblib.load(root/'models.joblib')
    manifest=read(ROOT/'legacy/terminal_freeze.json')
    for f,p in models['families'].items():
        assert p['staged_policy'].frozen_hash==manifest['families'][f]['staged_hash']
        for k,v in p['full_policies'].items():assert v.frozen_hash==manifest['families'][f]['full_hashes'][k]
    return models,manifest

def training_context(batch):
    f=batch.subset(batch.roles=='T_fit');cost=BranchCost.fit(f)
    order=sorted(range(5),key=lambda a:(float(np.dot(f.weights,f.losses[:,a])),float(np.dot(f.weights,f.action_costs[:,a])),a!=2,a))
    return cost,order

def legacy_trace(policy,acquirer,evidence,b,i,budget,cost,order,tool=None,*,learned=False,measure=True):
    start=time.perf_counter();features=dict(zip(b.free_names,b.visible[i]));initial=policy.reference_action
    def fallback(remaining):
        if b.fully_observed[i]:return 0
        for a in [initial]+[a for a in order if a!=initial]:
            if cost.action_estimate(a,features)<=remaining:return a
        return order[0]
    before=fallback(budget);action=before;selected=None;values={};reason='STOP';toolcost=0.;support=True
    if b.fully_observed[i]:reason='complete_KEEP'
    else:
        options=TOOLS if learned else (() if tool is None else (tool,))
        for t in options:
            if not b.rows[i]['tools'][t]['metadata_applicable']:continue
            # Ridge may select any arm; CART classes describe every possible leaf.
            model=policy.models_.get(t)
            arms=list(map(int,model.classes_)) if policy.estimator=='cart' and model is not None else list(range(5))
            if cost.reservation(t,features,arms=arms)>budget:continue
            v=acquirer.predict(b.visible[i],t,policy.frozen_hash) if learned and acquirer is not None else (1. if not learned else None)
            if v is not None and v>0:values[t]=float(v)
        if values:
            selected=min(values,key=lambda t:(-values[t],cost.reservation(t,features),t));toolcost=float(b.tool_costs[selected][i])
            support=bool(b.supported[selected][i]);remaining=max(0.,budget-toolcost)
            if support:
                action=policy.choose(b.visible[i],evidence[selected][i],fully_observed=False)['action'];reason='acquired_commit'
                if cost.action_estimate(action,features)>remaining:action=fallback(remaining);reason='post_evidence_budget_fallback'
            else:action=fallback(remaining);reason='unsupported_fallback'
        elif tool is not None:reason='fixed_tool_inapplicable_or_budget_fallback'
    elapsed=time.perf_counter()-start if measure else 0.
    total=float(b.action_costs[i,action])+toolcost+elapsed
    return {'action':int(action),'tool':selected,'tool_count':0 if selected is None else (2 if selected=='control' else 1),
      'tool_cost_seconds':toolcost,'decision_seconds':elapsed,'total_seconds':total,'supported':support,
      'reason':reason,'predicted_tool_values':values,'before_action':int(before),'after_action':int(action),
      'terminal_hash':policy.frozen_hash,'budget_overrun':total>budget,'evidence_hash':None if selected is None else evidence[selected][i].identity_hash}

def freeze_fixed(models):
    path=ROOT/'common_fixed_freeze.json'
    if path.exists():return read(path)
    out={'selection_role':'T_fit only','dev_consulted':False,'unit':'MAE/request-origin-scale','families':{}}
    for family,fb in models['families'].items():
        b=load_batch('main',family).subset(load_batch('main',family).roles=='T_fit')
        cost,order=training_context(b);e,_=build_legacy_evidence(b,fb['full_reference']);fm={}
        for bn,budget in BUDGETS.items():
            choices=[]
            for a in range(5):
                actions=np.where(b.fully_observed,0,a);seconds=b.action_costs[np.arange(len(b.uids)),actions]
                feasible=all(cost.action_estimate(int(k),dict(zip(b.free_names,b.visible[i])))<=budget for i,k in enumerate(actions))
                if feasible:choices.append({'name':'FIXED_'+POOL[a],'kind':'fixed','action':a,'loss':float(np.dot(b.weights,b.losses[np.arange(len(actions)),actions])),'seconds':float(np.dot(b.weights,seconds))})
            for estimator,p in fb['full_policies'].items():
                for tool in TOOLS:
                    ts=[legacy_trace(p,None,e,b,i,budget,cost,order,tool,measure=False) for i in range(len(b.uids))]
                    a=np.array([t['action'] for t in ts]);s=np.array([t['total_seconds'] for t in ts])
                    if np.all(s<=budget):choices.append({'name':'LEGACY_'+estimator.upper()+'_'+tool,'kind':'legacy','estimator':estimator,'tool':tool,'loss':float(np.dot(b.weights,b.losses[np.arange(len(a)),a])),'seconds':float(np.dot(b.weights,s))})
            fm[bn]={'selected':min(choices,key=lambda r:(r['loss'],r['seconds'],r['name'])) if choices else None,'choices':choices}
        out['families'][family]=fm
    out['legacy_model_sha256']=sha(ROOT/'legacy-final/models.joblib');out['hot_cost_sha256']=sha(ROOT/'hot_costs.json')
    write(path,out);return out

def external_rows(suite,batches,reference_map,external):
    path=Path('results/v431-r3')/('common_decisions.json' if suite=='main' else 'common_financial_decisions.json')
    rows=read(path);result=[];missing=[]
    if suite=='financial':
        original=read('results/v431-r2/financial-observation-index-r1/common_financial_decisions.json')
        rows += [{**r,'policy':'R2_EXISTING_CART'} for r in original if r['policy']=='EXISTING_SAME_EVIDENCE_CART']
    policies=['R3_AGENT_high','R3_AGENT_low','R2_EXISTING_CART']
    selected=[r for r in rows if r['policy'] in policies or r['policy'].startswith('TATO')]
    tato={}
    for family in batches:
        directory=Path(external['tato'][suite+':'+family]['status_file']).parent
        status=read(directory/'status.json');assert sha(directory/'predictions.npz')==status['prediction_file_sha256']
        detail={r['episode_uid']:r for r in read(directory/'decisions.json')}
        with np.load(directory/'predictions.npz',allow_pickle=False) as f:
            tato[family]={u:{'forecast_hash':array_hash(f[u+'_TATO_NATIVE_SPACE']),'original_input_hash':r['input_sha256'],'selected_trial':r.get('selected_trial'),'selected_params':r.get('selected_params')} for u,r in detail.items()}

    for r in selected:
        family=r['family'];b=batches[family];u=r['episode_uid'];ix={str(u):i for i,u in enumerate(b.uids)}
        if u not in ix:continue
        i=ix[u];m=b.rows[i]['meta'];original=r['policy'];budgetnames=[original.rsplit('_',1)[-1]] if original.startswith('R3_AGENT_') else list(BUDGETS)
        fix=external.get('rows',{}).get(suite,{}).get(family,{}).get(original,{}).get(u)
        seconds=float(r['total_seconds']) if fix is None else float(fix['hot_seconds'])
        for bn in budgetnames:
            ref=reference_map[family];gain=float(b.report_losses[i,ref]-r['mase']);name=('R3_FROZEN_'+bn if original.startswith('R3_AGENT_') else ('TATO_NATIVE_8_'+bn if original.startswith('TATO') else 'R2_EXISTING_CART_'+bn))
            rr={**r,'policy':name,'original_policy':original,'role':str(b.roles[i]),'raw_start':m['raw_start'],'split':m['split'],
              'reference_arm':POOL[ref],'learning_loss':float(r['mae']/b.rows[i]['origin_scale']['value']),'learning_scale':b.rows[i]['origin_scale'],'report_scale':b.rows[i]['outer_report_scale'],
              'total_seconds':seconds,'budget':BUDGETS[bn],'budget_overrun':seconds>BUDGETS[bn],'switch_gain':max(gain,0.),'wrong_switch_loss':max(-gain,0.),'net_gain':gain,
              'origin':'frozen_historical_native_method','information':'r2_mask+history_different_from_r3' if 'R2' in name else ('official_native_8_trial_search' if 'TATO' in name else 'r3_frozen_response_history'),
              'trace':{'reason':'frozen_prediction_reuse','original_seconds':r['total_seconds'],'cost_reclassification':fix,'tool':r.get('actual_state'),'tool_count':r.get('tool_count',0)},'forecast_hash':r.get('forecast_hash'),'candidate_hash':r.get('candidate_hash')}
            if rr['arm'] in POOL:
                a=POOL.index(rr['arm']);assert np.isclose(rr['mase'],b.report_losses[i,a],rtol=1e-10,atol=1e-10)
                rr['forecast_hash']=b.rows[i]['actions'][rr['arm']]['prediction_hash'];rr['candidate_hash']=b.rows[i]['actions'][rr['arm']]['input_hash'];rr['action_identity']=b.rows[i]['actions'][rr['arm']]
            elif original.startswith('TATO'):
                rr['forecast_hash']=tato[family][u]['forecast_hash']
                rr['candidate_hash']=None
                rr['trace']['native_transform_identity']=tato[family][u]
                rr['trace']['candidate_hash_reason']='native transformation pipeline, not a five-arm governed candidate'
            result.append(rr)
    return result,missing

def evaluate(suite,models,fixed):
    out=ROOT/'evaluation'/('dev' if suite=='main' else suite)
    if (out/'common_status.json').exists():raise RuntimeError('Preserve original common evaluation')
    rows=read(out/'decisions.json');batches={};references={};started=time.perf_counter()
    for family,fb in models['families'].items():
        full=load_batch('main',family);cost,order=training_context(full)
        b=full.subset(full.roles=='dev') if suite=='main' else load_batch(suite,family)
        batches[family]=b;ref=fb['full_reference'];references[family]=ref
        e,_=build_legacy_evidence(b,ref,suite=suite);se=e if fb['staged_reference']==ref else build_legacy_evidence(b,fb['staged_reference'],suite=suite)[0]
        for bn,budget in BUDGETS.items():
            for estimator,p in fb['full_policies'].items():
                for tool in TOOLS:
                    name='LEGACY_'+estimator.upper()+'_'+tool+'_'+bn
                    for i in range(len(b.uids)):
                        t=legacy_trace(p,None,e,b,i,budget,cost,order,tool)
                        rows.append(row_record(b,i,name,t,ref,budget,origin='r4_scale_retrained_r3',information='fixed_'+tool+'_same_legacy_terminal'))
            p=fb['staged_policy'];aq=fb['staged_acquirer']
            for i in range(len(b.uids)):
                t=legacy_trace(p,aq,se,b,i,budget,cost,order,learned=True)
                rows.append(row_record(b,i,'R3_RETRAINED_STAGED_'+bn,t,ref,budget,origin='r4_scale_retrained_r3',information='split_fit_staged_response_acquisition'))
            chosen=fixed['families'][family][bn]['selected']
            if chosen is not None:
                for i in range(len(b.uids)):
                    if chosen['kind']=='fixed':
                        a=0 if b.fully_observed[i] else chosen['action'];t={'action':a,'tool':None,'tool_count':0,'total_seconds':float(b.action_costs[i,a]),'reason':'frozen_train_fixed_action'}
                    else:t=legacy_trace(fb['full_policies'][chosen['estimator']],None,e,b,i,budget,cost,order,chosen['tool'])
                    rows.append(row_record(b,i,'TRAIN_BEST_FIXED_FLOW_'+bn,t,ref,budget,origin='train_selected_fixed_flow',information=chosen['name']))
    external=read(ROOT/'baseline_audit/external_hot_costs.json');assert external['status']=='completed'
    rr,missing=external_rows(suite,batches,references,external);rows+=rr
    table,sources=summarize(rows);write(out/'common_decisions.json',rows);write(out/'common_table.json',table);write(out/'common_sources.json',sources)
    write(out/'common_status.json',{'status':'completed','rows':len(rows),'groups':len(table),'seconds':time.perf_counter()-started,'missing':missing,'fixed_selection_sha256':sha(ROOT/'common_fixed_freeze.json'),'external_cost_sha256':sha(ROOT/'baseline_audit/external_hot_costs.json'),'source_sha256':sha(__file__)})
    print(suite,len(rows),len(table),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze-only',action='store_true');p.add_argument('--suite',choices=['main','financial','both'],default='both');a=p.parse_args()
    models,_=setup();fixed=freeze_fixed(models)
    if not a.freeze_only:
        for suite in (('main','financial') if a.suite=='both' else (a.suite,)):evaluate(suite,models,fixed)
