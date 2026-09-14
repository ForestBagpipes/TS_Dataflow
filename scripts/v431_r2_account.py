#!/usr/bin/env python3
"""Append separately measured missing planning costs without altering frozen outputs."""
import json,time
from pathlib import Path
import joblib,numpy as np
from introact_ts.v431_r2.data import R2Data,ROOT,read,sha
from introact_ts.v431_r2.policy import EvidenceState
from introact_ts.v431.acquisition import Charge,CostInvoice
from introact_ts.v43.agent_inputs import mask_views
from introact_ts.v43.cli import atomic_json
from v431_r2_fit import grouped_summary

def main():
    tick=time.perf_counter();assert not (ROOT/'accounted_decisions.json').exists()
    frozen={p:sha(ROOT/p) for p in ('models.joblib','models_frozen.json','terminal_manifest.json','terminal_freeze.json','value_labels.json','decisions.json','table.json')}
    data=R2Data();models=joblib.load(ROOT/'models.joblib');manifest=read(ROOT/'terminal_manifest.json');rows=read(ROOT/'decisions.json');charges={};timings=[]
    for family,policy in models['policies'].items():
        for i in data.ids('dev'):
            u=data.uids[i];e=data.episodes[u];t=time.perf_counter();policy.choose(data.X[i],EvidenceState(),fully_observed=bool(data.complete[i]))
            validmask=len(mask_views(e)[0])==3;validhistory=e.horizon<512
            applicable={'mask':validmask,'history':validhistory,'both':validmask and validhistory}
            estimates={k:CostInvoice((Charge('estimated-complete-'+k,v),)) for k,v in manifest['families'][family]['branch_estimates'].items()}
            seconds=time.perf_counter()-t
            charges[family,u,'r2']=Charge('initial-choice-and-admission-preparation:'+family+':'+u,seconds)
            cart,med,_=models['legacy_carts'][family];t=time.perf_counter();z=np.r_[data.X[i],data.mask[i],data.history[family][i]];cart.predict(np.r_[np.where(np.isfinite(z),z,med),np.isfinite(z)][None]);legacy=time.perf_counter()-t
            charges[family,u,'legacy']=Charge('existing-cart-selection:'+family+':'+u,legacy)
            timings.append(dict(family=family,episode_uid=u,initial_choice_and_admission_seconds=seconds,existing_cart_selection_seconds=legacy))
    fixed={'KEEP','FIXED_TSICL','FIXED_REFERENCE'};added=0.;count=0
    for r in rows:
        if r['policy'] in fixed:continue
        charge=charges[r['family'],r['episode_uid'],'legacy' if r['policy']=='EXISTING_SAME_EVIDENCE_CART' else 'r2']
        inv=CostInvoice(tuple(Charge(**x) for x in r['invoice']['charges'])).merge(CostInvoice((charge,)));r['invoice']=inv.as_dict();r['total_seconds']=inv.total_seconds
        budget=r.get('budget',manifest['budgets']['high']);r['budget_overrun']=inv.total_seconds>budget+1e-12
        added+=charge.seconds;count+=1
    table,detail=grouped_summary(rows)
    for p,digest in frozen.items():assert sha(ROOT/p)==digest,'frozen artifact was changed'
    atomic_json(ROOT/'accounted_decisions.json',rows);atomic_json(ROOT/'accounted_table.json',table);atomic_json(ROOT/'accounted_metrics_by_source.json',detail)
    atomic_json(ROOT/'planning_cost_samples.json',timings)
    atomic_json(ROOT/'accounting_audit.json',dict(status='passed',original_frozen_sha256=frozen,rows_supplemented=count,summed_recharged_planning_seconds=added,process_body_seconds=time.perf_counter()-tick,protocol='one new actual timing per family/UID for equivalent previously unmetered planning; original predictions/models/labels preserved',complete_scope='batch components including planning; raw process online cost separate',value_labels='initial and post-evidence selection already measured at label generation; no label/model change',heldout_labels_read=0))
    print(json.dumps(read(ROOT/'accounting_audit.json')),flush=True)

if __name__=='__main__':main()
