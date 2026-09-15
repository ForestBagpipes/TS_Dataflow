#!/usr/bin/env python3
"""Frozen TRAIN scoring followed by one common DEV matrix on real current forecasts."""
from pathlib import Path
import argparse,hashlib,json,time
from collections import defaultdict
import joblib
import numpy as np
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v431_r4.branch_cost import BranchCost
from introact_ts.v431_r4.trajectory_dataset import group_weights
from introact_ts.v431_r5.scoring import (FreeReference,crossfit_reference,SharedRidge,
    paired_training_rows,response_features)
from introact_ts.v431_r5.controller import run,TrialResult
from introact_ts.v431_r5.geometry import project_scores,distance_bounds
from v431_r4_run import row_record,summarize

ROOT=Path('results/v431-r5')
BUDGETS={'low':.8140623268639832,'high':3.5}
MODES=('current','free','history','prior')


def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    def convert(v):
        if isinstance(v,np.ndarray):return v.tolist()
        if isinstance(v,np.generic):return v.item()
        raise TypeError(type(v).__name__)
    t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False,default=convert)+'\n');t.replace(p)


def load(suite,family,role=None):
    d=joblib.load(ROOT/'data'/suite/(family+'.joblib'))
    if role is not None:
        ix=np.flatnonzero(d['batch'].roles==role);d=subset(d,ix)
    return d


def subset(d,ix):
    return {k:(v.subset(ix) if k=='batch' else v[ix] if isinstance(v,np.ndarray)
               else [v[i] for i in ix] if isinstance(v,list) and len(v)==len(d['batch'].uids) else v)
            for k,v in d.items()}


def histories(d,refs):
    h=np.full((len(refs),5,7),np.nan)
    for i,p in enumerate(d['history_predictions']):
        if p is not None:
            for a in range(5):h[i,a]=response_features(p[refs[i]],p[a],d['batch'].rows[i]['origin_scale']['value'])
    return h


def training_rows(d,refs,mode):
    b=d['batch'];return paired_training_rows(b.visible,d['predictions'],
        [r['origin_scale']['value'] for r in b.rows],b.losses,refs,b.parents,b.sources,
        mode=mode,history=histories(d,refs) if mode=='history' else None)


class OfflineTrials:
    """Only query(action) discloses a current prediction; cost dedup follows materialization."""
    def __init__(self,d,i):self.d=d;self.i=i;self.cache={};self.calls=[]
    def __call__(self,a):
        meta=self.d['cache_metadata'][self.i][a]
        # Same request/model/H/masks are invariant here; input hash remains
        # hidden until this action has incurred its materialization cost.
        key=meta['input_version_hash'];reused=key in self.cache
        p=self.d['predictions'][self.i][a].copy()
        if reused:
            assert np.array_equal(p,self.cache[key]),'Same input/model yielded incompatible prediction'
        self.cache[key]=p
        identity={k:meta[k] for k in ('source','parent','origin','L','H','target_mask_hash',
            'auxiliary_mask_hash','input_version_hash','model','prediction_dtype','prediction_hash','cache_key')}
        identity['reused_already_executed_forecast']=reused
        r=TrialResult(a,p,key,identity,float(self.d['governance_costs'][self.i,a]),
            0. if reused else float(self.d['forecast_costs'][self.i,a]),
            status='alias' if meta.get('alias') else 'completed',
            actual_action=POOL.index(meta['actual_arm']),alias_reason=meta.get('unsupported_reason'))
        self.calls.append(r);return r


def replay(d,i,model,budget,*,mode='full',schedule='selective',lam=0.,max_versions=3,score_mode='current'):
    b=d['batch'];x=b.visible[i];ref=model['reference'];fees=model['cost'];callback=OfflineTrials(d,i)
    estimate=lambda a:fees.action_estimate(a,dict(zip(b.free_names,x)))+.051
    pre=float(d['feature_seconds'][i]);historical=None
    if score_mode=='history':
        reference=ref.predict(x,bool(b.fully_observed[i]));p=d['history_predictions'][i]
        if p is None:schedule='reference'
        else:
            historical=np.asarray([response_features(p[reference],p[a],b.rows[i]['origin_scale']['value']) for a in range(5)])
            pre+=float(b.tool_costs['H'][i])
    result=run(x,b.rows[i]['origin_scale']['value'],bool(b.fully_observed[i]),budget,ref,
        model['critics'][score_mode],model['prior'],estimate,callback,mode=mode,schedule=schedule,
        lambda_value=lam,max_versions=max_versions,initial_seconds=pre,simulate_costs=True,
        score_mode=score_mode,history_responses=historical)
    result.pop('final_prediction')
    result['history_tool_seconds']=0. if score_mode!='history' or historical is None else float(b.tool_costs['H'][i])
    return result


def risk(d,traces):
    b=d['batch'];a=np.array([x['action'] for x in traces]);return (
        float(np.dot(b.weights,b.losses[np.arange(len(a)),a])),
        float(np.dot(b.weights,[x['total_seconds'] for x in traces])))


def fit():
    out=ROOT/'fit'
    if (out/'models_frozen.json').exists():raise RuntimeError('Refuse to overwrite frozen models')
    out.mkdir(parents=True,exist_ok=True);begun=time.perf_counter();models={'families':{}}
    manifest={'status':'fitting','source_sha256':{},'input_sha256':{},'families':{},
        'mask_protocol':'unknown future effective scoring mask; max-lead bound / common hull',
        'budgets':BUDGETS,'max_versions':3,'lambda_candidates':[0.,.01,.1],
        'solver':dict(tolerance=1e-8,max_iter=2048,time_limit_seconds=.05),
        'branch_overhead_reservation':.051,'output_reserve':.001,'dev_consulted':False}
    for family in ('bolt','timesfm'):
        d=load('main',family,'T_fit');gate=load('main',family,'T_gate');b=d['batch'];g=gate['batch']
        assert not set(b.parents)&set(g.parents)
        reference=FreeReference().fit(b);oof,audit=crossfit_reference(b)
        gr=np.array([reference.predict(x,c) for x,c in zip(g.visible,g.fully_observed)])
        fm={'reference':reference,'critics':{},'cost':BranchCost.fit(b),'lambda':{}}
        report={'oof':audit,'reference_tree':reference.node,'fit_parents':len(set(b.parents)),
                'gate_parents':len(set(g.parents)),'scorers':{},'lambda_gate':{}}
        labels=[]
        for mode in MODES:
            train=training_rows(d,oof,mode);val=training_rows(gate,gr,mode);choices=[]
            for alpha in (.1,1.,10.):
                model=SharedRidge().fit(train['features'],train['actions'],train['targets'],train['weights'],alpha=alpha,
                    roles=b.roles[train['indices']],parents=b.parents[train['indices']])
                pred=model.predict(val['features'],val['actions'])
                mse=float(np.average((pred-val['targets'])**2,weights=val['weights']))
                choices.append((mse,alpha,model))
            mse,alpha,model=min(choices,key=lambda z:(z[0],z[1]))
            if mode=='prior':fm['prior']=model
            else:fm['critics'][mode]=model
            report['scorers'][mode]=dict(alpha=alpha,hash=model.frozen_hash,rows=len(train['targets']),
                parents=len(set(b.parents[train['indices']])),gate_mse=mse,
                search=[dict(alpha=a,gate_mse=e,hash=m.frozen_hash) for e,a,m in choices])
            labels.extend(dict(uid=str(b.uids[i]),parent=str(b.parents[i]),mode=mode,action=int(a),
                               reference_action=int(oof[i]),gain=float(y),unit='MAE/origin_scale')
                          for i,a,y in zip(train['indices'],train['actions'],train['targets']))
        # Freeze terminal objects before selecting acquisition price on gate.
        joblib.dump(fm,out/(family+'-terminal.joblib'))
        report['terminal_sha256']=sha(out/(family+'-terminal.joblib'))
        write(out/(family+'-training_labels.json'),labels)
        for bn,budget in BUDGETS.items():
            choices=[]
            for lam in (0.,.01,.1):
                ts=[replay(gate,i,fm,budget,lam=lam) for i in range(len(g.uids))]
                loss,seconds=risk(gate,ts);choices.append((loss,seconds,lam))
                write(out/(family+'-gate-'+bn+'-'+str(lam)+'.json'),ts)
            selected=min(choices);fm['lambda'][bn]=selected[2]
            report['lambda_gate'][bn]={'selected':selected[2],'choices':choices}
        models['families'][family]=fm;manifest['families'][family]=report
        manifest['input_sha256'][family]=sha(ROOT/'data/main'/(family+'.joblib'))
        write(out/'progress.json',{'family':family,'status':'running','elapsed_seconds':time.perf_counter()-begun})
    for p in [Path(__file__),*Path('src/introact_ts/v431_r5').glob('*.py')]:manifest['source_sha256'][str(p)]=sha(p)
    joblib.dump(models,out/'models.joblib');manifest.update(status='completed',elapsed_seconds=time.perf_counter()-begun)
    write(out/'manifest.json',manifest)
    write(out/'models_frozen.json',{'sha256':sha(out/'models.joblib'),'manifest_sha256':sha(out/'manifest.json'),
                                  'elapsed_seconds':manifest['elapsed_seconds']})
    print(json.dumps({'status':'frozen','seconds':manifest['elapsed_seconds']}),flush=True)


def frozen():
    out=ROOT/'fit';f=read(out/'models_frozen.json');assert sha(out/'models.joblib')==f['sha256']
    assert sha(out/'manifest.json')==f['manifest_sha256'];m=read(out/'manifest.json')
    for p,v in m['source_sha256'].items():assert sha(p)==v,('Changed frozen source',p)
    return joblib.load(out/'models.joblib'),m


def record(d,i,name,t,budget,*,mode='full',schedule='selective',score_mode='current'):
    b=d['batch'];ref=t['reference_action'];r=row_record(b,i,name,{**t,'tool_count':t['versions']-1},ref,budget,
        origin='r5',information='current task trial responses' if score_mode=='current' else score_mode)
    r.update(versions=t['versions'],geometry_mode=mode,schedule=schedule,score_mode=score_mode,
             unique_predictions=len({d['cache_metadata'][i][a]['prediction_hash'] for a in t['queried_actions']}))
    raw=np.array(t['raw']);z=np.array(t['gains']);actions=t['queried_actions']
    truth=b.losses[i,ref]-b.losses[i,actions]
    r['score_metrics']=None
    if not t.get('failure') and len(raw)==len(z)==len(truth):
        p=np.stack([d['predictions'][i][a] for a in actions]);D=distance_bounds(p,b.rows[i]['origin_scale']['value'])
        r['score_metrics']=dict(raw_squared_error=float(np.sum((raw-truth)**2)),projected_squared_error=float(np.sum((z-truth)**2)),
            raw_violation=float(np.maximum(np.abs(raw[:,None]-raw[None,:])-D,0).max()),
            projected_violation=float(np.maximum(np.abs(z[:,None]-z[None,:])-D,0).max()),
            projection_active=bool(np.max(np.abs(z-raw))>1e-8),rank_changed=bool(np.argmax(raw)!=np.argmax(z)),
            true_gains=truth.tolist())
    r['solver']=[x['projection'] for x in t['trace'] if 'projection' in x]
    return r


def mechanism(d,i,fm,budget):
    base=replay(d,i,fm,budget,mode='raw',schedule='fixed');rows=[];b=d['batch'];actions=base['queried_actions'];ref=base['reference_action']
    for scoremode in ('current','free','history'):
        extra_cost=0.;raw=np.zeros(len(actions));supported=True
        for j,a in enumerate(actions[1:],1):
            if scoremode=='current':extra=response_features(d['predictions'][i][ref],d['predictions'][i][a],b.rows[i]['origin_scale']['value'])
            elif scoremode=='free':extra=np.zeros(7)
            else:
                hp=d['history_predictions'][i]
                if hp is None:supported=False;break
                extra=response_features(hp[ref],hp[a],b.rows[i]['origin_scale']['value']);extra_cost=float(b.tool_costs['H'][i])
            raw[j]=fm['critics'][scoremode].predict(np.r_[b.visible[i],extra],[a])[0]
        for mode in (('raw','single','pair','full') if scoremode=='current' else ('raw',)):
            t={**base,'trace':[],'raw':raw.tolist(),'gains':[0.]*len(actions),'action':ref,
               'total_seconds':base['total_seconds']+extra_cost,'failure':None}
            if supported:
                proj=project_scores(np.stack([d['predictions'][i][a] for a in actions]),raw,
                      b.rows[i]['origin_scale']['value'],mode=mode,time_limit_seconds=.05)
                t['trace']=[{'projection':proj.to_dict()}];t['total_seconds']+=proj.elapsed_seconds
                if proj.status not in ('failed','timeout'):
                    t['gains']=proj.scores.tolist();j=0 if proj.scores.max()<=0 else min(range(len(actions)),key=lambda j:(-proj.scores[j],j!=0,actions[j]));t['action']=actions[j]
                else:t['failure']=proj.reason
            else:t['failure']='historical_evidence_unsupported'
            t['final_input_hash']=d['cache_metadata'][i][t['action']]['input_version_hash']
            t['final_identity']=next(q['identity'] for q in base['queried'] if q['action']==t['action'])
            r=record(d,i,'MECH_'+scoremode.upper()+'_'+mode.upper(),t,budget,mode=mode,schedule='same_fixed_trace',score_mode=scoremode)
            r['mechanism_scope']='same queried current versions; history additionally pays full H evidence'
            r['history_supported']=supported;r['history_seconds']=extra_cost;rows.append(r)
    return rows


def evaluate(suite='main',role='dev'):
    models,manifest=frozen();name=role if suite=='main' else suite;out=ROOT/'evaluation'/name
    if (out/'status.json').exists():raise RuntimeError('Preserve original evaluation')
    begun=time.perf_counter();rows=[];mechanisms=[]
    for family,fm in models['families'].items():
        d=load(suite,family,role if suite=='main' else None);b=d['batch']
        for bn,budget in BUDGETS.items():
            variants=[('R5','full','selective',3),('R5_RAW','raw','selective',3),('R5_SINGLE','single','selective',3),
                ('FIXED_ORDER_3','full','fixed',3),('FIXED_COUNT_2','full','fixed',2),('ALL_FIVE','full','all',5),
                ('REFERENCE_FREE','raw','reference',1)]
            for label,mode,sched,count in variants:
                for i in range(len(b.uids)):
                    t=replay(d,i,fm,budget,mode=mode,schedule=sched,lam=fm['lambda'][bn],max_versions=count)
                    rows.append(record(d,i,label+'_'+bn,t,budget,mode=mode,schedule=sched))
            if bn=='high':
                for i in range(len(b.uids)):mechanisms.extend(mechanism(d,i,fm,budget))
        print(json.dumps({'family':family,'evaluation':name,'seconds':time.perf_counter()-begun}),flush=True)
    table,sources=summarize(rows);mt,ms=summarize(mechanisms)
    write(out/'decisions.json',rows);write(out/'table.json',table);write(out/'sources.json',sources)
    write(out/'mechanism_rows.json',mechanisms);write(out/'mechanism_table.json',mt)
    write(out/'status.json',dict(status='completed',seconds=time.perf_counter()-begun,rows=len(rows),mechanism_rows=len(mechanisms),model_sha256=sha(ROOT/'fit/models.joblib')))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fit',action='store_true');p.add_argument('--evaluate',action='store_true')
    p.add_argument('--suite',default='main',choices=['main','financial']);p.add_argument('--role',default='dev',choices=['dev','T_fit','T_check','T_acq'])
    a=p.parse_args()
    if a.fit:fit()
    elif a.evaluate:evaluate(a.suite,a.role)
    else:p.error('--fit or --evaluate required')
