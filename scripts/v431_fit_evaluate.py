#!/usr/bin/env python3
"""Freeze eight terminal candidates, fit at most two one-step agents, one dev table."""
from collections import defaultdict
from datetime import datetime,timezone
import json,time
from pathlib import Path
import joblib
import numpy as np
from sklearn.tree import DecisionTreeClassifier
from introact_ts.v43.agent_inputs import POOL,mask_views
from introact_ts.v43.cli import atomic_json
from introact_ts.v43.schemas import json_hash,array_hash
from introact_ts.v43.agent_policy import execute_policy as old_execute
from introact_ts.v431.data import SprintData,FEATURE_NAMES
from introact_ts.v431.decision_tree import LossTree
from introact_ts.v431.terminal import RefinedPolicy
from introact_ts.v431.acquisition import Charge,CostInvoice,ValueLabelRow,fit_acquirer,make_value_labels,AcquiredBranch,execute_one_step

def main():
    start=time.perf_counter();data=SprintData();root=data.root
    config=json.loads(Path('configs/v431/sprint_manifest.json').read_text());old=data.old
    assert json.loads((root/'history/status.json').read_text())['status']=='completed'
    assert not (root/'terminal_manifest.json').exists(),'refuse to overwrite frozen terminal'
    fit,gate,check,acq,dev=[data.ids(r) for r in ('T_fit','T_gate','T_check','T_acq','dev')]
    evidence={c:data.evidence(c) for c in config['history_conditions']}
    toolcost=json.loads((root/'history/tool_costs.json').read_text())
    def cost(i,condition,tool):
        uid=data.uids[i]
        return old.tool_costs[uid]['strict_mask' if tool=='strict_mask' else 'history_probe'] if tool=='strict_mask' or condition=='old32' else toolcost[condition][uid]
    def final_invoice(i,a):
        uid=data.uids[i];arm=POOL[a]
        return CostInvoice((Charge('candidate:'+uid+':'+arm,old.direct_costs[uid][arm]),Charge('forecast:'+uid+':'+arm,old.forecast_costs[uid+'_'+arm])))
    def tool_invoice(i,condition,tool):return CostInvoice((Charge('tool:'+data.uids[i]+':'+condition+':'+tool,cost(i,condition,tool)),))
    def visible(E,tool):
        out=np.full_like(E,np.nan)
        if tool=='strict_mask':out[:,:15]=E[:,:15]
        elif tool=='history':out[:,15:]=E[:,15:]
        elif tool=='all':out[:]=E
        return out
    base={d:LossTree(max_depth=d).fit(data.X[fit],data.L[fit],data.weights(fit),data.parents[fit]) for d in (1,2)}
    terminals={};selection=[]
    for setting in config['terminal_configs']:
        name,d,condition=setting['name'],setting['depth'],setting['evidence'];E=evidence[condition]
        model=RefinedPolicy(base[d],prune=setting['prune']).fit(data.X[fit],E[fit],data.L[fit],data.weights(fit),data.parents[fit],
            data.X[gate],E[gate],data.L[gate],data.weights(gate),data.parents[gate],gate_groups=[data.meta[data.uids[i]]['source'] for i in gate])
        terminals[name]=model;pred=model.predict(data.X[gate],E[gate]);score=float(np.dot(data.weights(gate),data.L[gate,pred]))
        selection.append(dict(**setting,terminal_hash=model.frozen_hash,gate_mase=score,retained_refinements=len(model.refinements_),audit=model.audit_))
    eligible=[r for r in selection if r['prune']]
    selected=[r['name'] for r in sorted(eligible,key=lambda r:(r['gate_mase'],r['evidence']!='target_horizon',r['depth'],r['name']))[:2]]
    estimates={};training=np.r_[fit,gate]
    for setting in selection:
        c=setting['evidence'];estimates[setting['name']]={t:float(np.quantile([cost(i,c,t)+max(final_invoice(i,a).total_seconds for a in range(5)) for i in training],.95))*1.1 for t in ('strict_mask','history')}
    # Same registered complete budget for all deployed controls. Derived only
    # from fit/gate invoices; no dev runtime or outcome chooses it.
    low=max(v for d in estimates.values() for v in d.values());high=max(3.5,low)
    budgets={'low':low,'high':high}
    manifest=dict(status='terminal_frozen_before_acquisition_labels',created_at=datetime.now(timezone.utc).isoformat(),
        selected=selected,configs=selection,budgets=budgets,estimates=estimates,feature_names=FEATURE_NAMES,
        partition_counts={r:len(set(data.parents[data.ids(r)])) for r in ('T_fit','T_gate','T_check','T_acq','dev')},
        terminal_hashes={k:v.frozen_hash for k,v in terminals.items()},budget_rule='max fit/gate 95% complete branch costs x1.1; high max(low,3.5s)',
        action_cost_estimates={POOL[a]:float(np.quantile([final_invoice(i,a).total_seconds for i in training],.95))*1.1 for a in range(5)},
        sources=config['sources'],max_acquisitions=1,heldout_labels_read=0,promotion=False)
    atomic_json(root/'terminal_manifest.json',manifest)
    for name,model in terminals.items():atomic_json(root/(name+'.terminal.json'),model.to_dict())
    atomic_json(root/'T_check.json',{name:dict(mase=float(np.dot(data.weights(check),data.L[check,model.predict(data.X[check],evidence[next(s['evidence'] for s in selection if s['name']==name)][check])])),role='T_check_not_used_for_selection') for name,model in terminals.items()})
    acquirers={};labels={};checkpoints={'base':base,'terminal':terminals,'acquirers':acquirers,'cart':{},'flat':{}}
    forbidden=data.parents[np.r_[fit,gate,check]]
    for name in selected:
        model=terminals[name];c=next(s['evidence'] for s in selection if s['name']==name);E=evidence[c];items=[];w=data.weights(acq)
        stop=model.base_tree.predict(data.X)
        for k,i in enumerate(acq):
            st=time.perf_counter();model.base_tree.predict(data.X[i:i+1]);stop_selection=time.perf_counter()-st
            si=final_invoice(i,int(stop[i])).merge(CostInvoice((Charge('stop-selection:'+data.uids[i],stop_selection),)))
            for t in ('strict_mask','history'):
                st=time.perf_counter();a=int(model.predict(data.X[i:i+1],visible(E[i:i+1],t))[0]);elapsed=time.perf_counter()-st;ti=tool_invoice(i,c,t)
                ai=ti.merge(final_invoice(i,a),CostInvoice((Charge('acquired-selection:'+data.uids[i]+':'+t,elapsed),)))
                items.append(ValueLabelRow(data.uids[i],data.parents[i],t,model.frozen_hash,tuple(data.X[i]),data.L[i,stop[i]],data.L[i,a],
                    si,ai,weight=float(w[k]),tool_invoice=ti))
        aq=fit_acquirer(items,model.frozen_hash,FEATURE_NAMES,task_differences=(data.L[fit]-data.L[fit,2,None]).ravel(),forbidden_parents=forbidden)
        acquirers[name]=aq;labels[name]=make_value_labels(items,model.frozen_hash,aq.lambda_value)
        atomic_json(root/(name+'.acquisition.json'),aq.report)
    atomic_json(root/'value_labels.json',labels)
    # Same-information controls fit on T_fit only; no dev label is used here.
    for c,E in evidence.items():
        Z=np.c_[data.X,E];Zfit=Z[fit];median=np.nanmedian(Zfit,axis=0);median=np.where(np.isfinite(median),median,0.)
        # Missing evidence in training has explicit flags; 0 here is an imputer
        # for CART features only, never a task label or failed model prediction.
        ZZ=np.c_[np.where(np.isfinite(Z),Z,median),np.isfinite(Z)]
        cart=DecisionTreeClassifier(max_depth=3,min_samples_leaf=16*6,random_state=101).fit(ZZ[fit],np.argmin(data.L[fit],axis=1),sample_weight=data.weights(fit))
        # Assert independent supports; prune the entire unsupported CART to its
        # source-macro best fixed action, explicitly recorded, never inflate N.
        support={int(leaf):len(set(data.parents[fit][cart.apply(ZZ[fit])==leaf])) for leaf in set(cart.apply(ZZ[fit]))}
        cart_ok=all(n>=16 for n in support.values())
        assert cart_ok, 'ordinary CART has insufficient parent support; do not silently substitute'
        checkpoints['cart'][c]=(cart,median,cart_ok,support)
        checkpoints['flat'][c]=LossTree(max_depth=3).fit(Zfit,data.L[fit],data.weights(fit),data.parents[fit])
    joblib.dump(checkpoints,root/'models.joblib')
    atomic_json(root/'models_frozen.json',dict(created_at=datetime.now(timezone.utc).isoformat(),sha256=__import__('hashlib').sha256((root/'models.joblib').read_bytes()).hexdigest(),terminal_hashes=manifest['terminal_hashes'],stage='all_models_frozen_before_dev'))
    decisions=[]
    def save(i,name,a,invoice,**extra):
        uid=data.uids[i];arm=POOL[int(a)];label=old.labels[uid,arm]
        decisions.append(dict(episode_uid=uid,policy=name,arm=arm,**data.meta[uid],mae=label['mae'],mase=label['mase'],task_harm=label['task_harm'],
            candidate_hash=array_hash(old.pools[uid][arm]),total_seconds=invoice.total_seconds,invoice=invoice.as_dict(),budget_overrun=invoice.total_seconds>high,**extra))
    previous={r['episode_uid']:{} for r in json.loads((old.root/'agent/decisions.json').read_text())}
    for r in json.loads((old.root/'agent/decisions.json').read_text()):previous[r['episode_uid']][r['policy']]=r
    oldmodels=joblib.load(old.root/'agent/models.joblib');oldmanifest=json.loads((old.root/'agent/model_manifest.json').read_text())
    for i in dev:
        uid=data.uids[i]
        for a in range(5):save(i,'FIXED_'+POOL[a],a,final_invoice(i,a),history=[])
        r=previous[uid]['DIRTY_SELECTOR'];save(i,'OLD_DIRTY_HGB',POOL.index(r['arm']),CostInvoice((Charge('old-whole:'+uid,r['total_governance_seconds']+r['final_forecast_seconds']),)),history=[])
        budget=max(0.,high-old.base_costs[uid]-max(old.forecast_costs[uid+'_'+a] for a in POOL))
        olddec=old_execute(old.episodes[uid],old.pools[uid],oldmodels['utility'],oldmodels['acquisition'],lambda t:(old.evidence[uid][t],old.tool_costs[uid][t]),oldmanifest['estimated_tool_costs'],budget)
        a=POOL.index(olddec['arm']);total=old.base_costs[uid]+olddec['tool_seconds']+olddec['selection_seconds']+old.forecast_costs[uid+'_'+POOL[a]]
        save(i,'OLD_LEARNED_HGB_COMMON_BUDGET',a,CostInvoice((Charge('old-whole:'+uid,total),)),history=olddec['history'],base_seconds=old.base_costs[uid],tool_seconds=olddec['tool_seconds'],selection_seconds=olddec['selection_seconds'],final_forecast_seconds=old.forecast_costs[uid+'_'+POOL[a]])
        for d,b in base.items():
            st=time.perf_counter();a=int(b.predict(data.X[i:i+1])[0]);inv=final_invoice(i,a).merge(CostInvoice((Charge('selection:'+uid,time.perf_counter()-st),)))
            save(i,f'DIRTY_LOSS_TREE_D{d}',a,inv,history=[])
        for c,E in evidence.items():
            Z=np.c_[data.X[i:i+1],E[i:i+1]];cart,median,ok,support=checkpoints['cart'][c]
            st=time.perf_counter();a=int(cart.predict(np.c_[np.where(np.isfinite(Z),Z,median),np.isfinite(Z)])[0]) if ok else int(np.argmin(np.dot(data.weights(fit),data.L[fit])))
            inv=tool_invoice(i,c,'strict_mask').merge(tool_invoice(i,c,'history'),final_invoice(i,a),CostInvoice((Charge('selection:'+uid,time.perf_counter()-st),)))
            save(i,'CART_'+c,a,inv,history=['strict_mask','history'],support_valid=ok)
            st=time.perf_counter();a=int(checkpoints['flat'][c].predict(Z)[0]);inv=tool_invoice(i,c,'strict_mask').merge(tool_invoice(i,c,'history'),final_invoice(i,a),CostInvoice((Charge('selection:'+uid,time.perf_counter()-st),)))
            save(i,'FLAT_LOSS_TREE_'+c,a,inv,history=['strict_mask','history'])
        for setting in selection:
            name=setting['name'];c=setting['evidence'];model=terminals[name];E=evidence[c]
            st=time.perf_counter();a=int(model.predict(data.X[i:i+1],E[i:i+1])[0]);inv=tool_invoice(i,c,'strict_mask').merge(tool_invoice(i,c,'history'),final_invoice(i,a),CostInvoice((Charge('selection:'+uid,time.perf_counter()-st),)))
            save(i,'ALL_'+name,a,inv,history=['strict_mask','history'],terminal_hash=model.frozen_hash)
            if name not in selected:continue
            stop=int(model.base_tree.predict(data.X[i:i+1])[0]);estimate={t:CostInvoice((Charge('estimated:'+t,estimates[name][t]),)) for t in ('strict_mask','history')}
            applicable={'strict_mask':len(mask_views(old.episodes[uid])[0])==3,'history':old.episodes[uid].horizon<len(old.episodes[uid].target)}
            def fetch(t):
                v=visible(E[i:i+1],t);a=int(model.predict(data.X[i:i+1],v)[0]);return AcquiredBranch(POOL[a],tool_invoice(i,c,t).merge(final_invoice(i,a)),array_hash(v),model.frozen_hash)
            for bname,B in budgets.items():
                for mode,order,label in [('learned',None,'AGENT'),('fixed',('history',),'FIXED_HISTORY'),('fixed',('strict_mask',),'FIXED_MASK'),('simple',('history','strict_mask'),'VISIBLE_CONDITION'),('random',None,'RANDOM')]:
                    st=time.perf_counter();result=execute_one_step(terminal_hash=model.frozen_hash,visible_features=data.X[i],stop_arm=POOL[stop],stop_invoice=final_invoice(i,stop),branch_estimates=estimate,budget=B,applicable=applicable,model=acquirers[name],fetch=fetch,mode=mode,tool_order=order,condition=bool(data.X[i,1]>0 and data.X[i,4]>=.5),random_key=uid)
                    inv=CostInvoice(tuple(Charge(**q) for q in result['invoice']['charges'])).merge(CostInvoice((Charge('selection:'+uid,time.perf_counter()-st),)))
                    extra={k:v for k,v in result.items() if k not in ('arm','invoice','total_seconds','budget_overrun')}
                    save(i,f'{label}_{name}_{bname}',POOL.index(result['arm']),inv,**extra)
                    decisions[-1]['budget_overrun']=inv.total_seconds>B
    atomic_json(root/'decisions.json',decisions)
    grouped=defaultdict(list)
    for r in decisions:grouped[r['policy'],r['source'],r['horizon'],r['condition']].append(r)
    detail=[dict(policy=k[0],source=k[1],horizon=k[2],condition=k[3],episodes=len(v),mase=float(np.mean([r['mase'] for r in v])),mae=float(np.mean([r['mae'] for r in v])),total_seconds=float(np.mean([r['total_seconds'] for r in v])),task_harm=float(np.mean([r['task_harm'] for r in v])),mean_tools=float(np.mean([len(r.get('history',[])) for r in v])),budget_overruns=sum(r['budget_overrun'] for r in v)) for k,v in grouped.items()]
    table=[]
    for name in sorted({r['policy'] for r in decisions}):
        rows=[r for r in detail if r['policy']==name];assert len(rows)==18
        table.append(dict(policy=name,episodes=156,parents=26,**{k:float(np.mean([r[k] for r in rows])) for k in ('mase','mae','total_seconds','task_harm','mean_tools')},budget_overruns=sum(r['budget_overruns'] for r in rows),status='completed_dev_not_confirmatory'))
    atomic_json(root/'metrics_by_group.json',detail);atomic_json(root/'table.json',table)
    atomic_json(root/'status.json',dict(status='completed',policies=len(table),decisions=len(decisions),runtime_seconds=time.perf_counter()-start,selected=selected,heldout_labels_read=0,promotion=False))
    print(json.dumps(dict(status='completed',policies=len(table),selected=selected,runtime_seconds=time.perf_counter()-start)),flush=True)

if __name__=='__main__':main()
