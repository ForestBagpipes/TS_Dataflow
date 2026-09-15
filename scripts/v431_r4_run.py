#!/usr/bin/env python3
"""Finite preregistered r4 search and common offline evaluation on real ledgers."""
from collections import defaultdict
from datetime import datetime, timezone
import argparse, hashlib, json, time
from pathlib import Path
import joblib
import numpy as np
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v431_r4.joint_policy import JointPolicy, VisibleState, AcquiredEvidence
from introact_ts.v431_r4.trajectory_dataset import group_weights

ROOT=Path('results/v431-r4')
INPUT=ROOT/'trajectory-final'
BUDGETS={'low':0.8140623268639832,'high':3.5}
VARIANTS={'JOINT':{}, 'FREE_ONLY':{'tools':()}, 'JOINT_CLASSIFICATION':{'objective':'classification'},
          'STAGED':{'staged':True}, 'FIXED_H32':{'forced_tool':'H32'},
          'FIXED_H':{'forced_tool':'H'}, 'FIXED_CONTROL':{'forced_tool':'control'}}


def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n');temp.replace(p)


def load_batch(suite,family):
    """The only input switch is an audited hot/cold sidecar, never a new prediction."""
    b=joblib.load(INPUT/suite/(family+'.joblib'))
    side=ROOT/'hot_costs.json'
    if side.exists():
        obj=read(side)
        if obj['status']!='completed':raise RuntimeError('Hot/cold accounting incomplete')
        changes=obj.get('rows',{}).get(suite,{}).get(family,{})
        for i,u in enumerate(b.uids):
            row=changes.get(str(u),{})
            for arm,value in row.get('action_cold_seconds',{}).items():
                j=POOL.index(arm);assert 0<=value<=b.action_costs[i,j]+1e-8
                b.action_costs[i,j]-=value
            for tool,value in row.get('tool_cold_seconds',{}).items():
                assert 0<=value<=b.tool_costs[tool][i]+1e-8
                b.tool_costs[tool][i]-=value
            b.rows[i]['r4_cold_cost_separated']=row
    return b


def state(b,i):
    return VisibleState(dict(zip(b.free_names,b.visible[i].tolist())),bool(b.fully_observed[i]),
                        {t:bool(b.rows[i]['tools'][t]['metadata_applicable']) for t in b.evidence})


def trace(policy,b,i,*,measure=True):
    begun=time.perf_counter();visible=state(b,i);before=policy.decide(visible,None,policy.budget)
    requested=before.get('tool') if before['kind']=='acquire' else None
    toolcost=0.;after=before
    if requested is not None:
        toolcost=float(b.tool_costs[requested][i])
        evidence=AcquiredEvidence(requested,dict(zip(b.evidence_names[requested],b.evidence[requested][i].tolist()))
                                   if b.supported[requested][i] else {},
                                   'completed' if b.supported[requested][i] else 'unsupported')
        after=policy.decide(visible,evidence,max(0.,policy.budget-toolcost))
        assert after['kind']=='submit'
    elapsed=time.perf_counter()-begun if measure else 0.
    action=int(after['action']);cost=float(b.action_costs[i,action])+toolcost+elapsed
    return dict(action=action,tool=requested,tool_cost_seconds=toolcost,decision_seconds=elapsed,
                total_seconds=cost,tool_count=0 if requested is None else (2 if requested=='control' else 1),
                before=before,after=after,budget_overrun=cost>policy.budget+1e-12,
                supported=requested is None or bool(b.supported[requested][i]))


def risk(policy,b):
    traces=[trace(policy,b,i,measure=False) for i in range(len(b.uids))]
    a=np.array([r['action'] for r in traces]);c=np.array([r['total_seconds'] for r in traces])
    task=float(np.dot(b.weights,b.losses[np.arange(len(a)),a]-b.losses[:,policy.reference_arm]))
    # Across lambda candidates, gate uses the same task-risk criterion (zero
    # error tolerance), not differently priced utilities incomparable in cost.
    return task,float(np.dot(b.weights,c))


def fit():
    out=ROOT/'fit';out.mkdir(parents=True,exist_ok=True)
    if (out/'models_frozen.json').exists():raise RuntimeError('Frozen r4 models must never be overwritten')
    if not (ROOT/'hot_costs.json').exists():raise RuntimeError('Finish audited hot/cold cost separation before fitting')
    started=time.perf_counter();models={};manifest={'version':'v4.3.1-r4','started_at':datetime.now(timezone.utc).isoformat(),
       'budgets':BUDGETS,'families':{},'main_identity':'JOINT is the generic cost-sensitive finite-grammar policy; not two methods',
       'gate_selection':'free split enablement and registered lambda only, per declared comparison family',
       'old_acq_role':'frozen regression only','dev_consulted':False,'heldout_decoded':False,
       'hot_cost_sha256':sha(ROOT/'hot_costs.json'),'input_files':{},'source_sha256':{}}
    for family in ('bolt','timesfm'):
        b=load_batch('main',family);fitb=b.subset(b.roles=='T_fit');gate=b.subset(b.roles=='T_gate')
        assert len(set(fitb.parents))==54 and len(set(gate.parents))==21 and not set(fitb.parents)&set(gate.parents)
        manifest['input_files'][family]=sha(INPUT/'main'/(family+'.joblib'))
        risks=np.dot(fitb.weights,fitb.losses);reference=min(range(5),key=lambda a:(risks[a],np.dot(fitb.weights,fitb.action_costs[:,a]),a!=2,a))
        differences=np.abs(fitb.losses-fitb.losses[:,reference,None]).ravel()
        costs=np.concatenate([fitb.tool_costs[t][fitb.supported[t]] for t in fitb.evidence]);positive=costs[costs>0]
        numerator=float(np.median(differences));denominator=float(np.median(positive)) if len(positive) else 0.
        lambdas=[0.] if numerator<=0 or denominator<=0 else [0.,.1*numerator/denominator]
        fm={'reference_action':reference,'reference_arm':POOL[reference],'reference_fit_risks':risks.tolist(),
            'lambda_candidates':lambdas,'lambda_numerator':numerator,'lambda_denominator':denominator,
            'fit_parents':sorted(set(fitb.parents)),'gate_parents':sorted(set(gate.parents)),'search':{},'selected':{}}
        models[family]={}
        for budget_name,budget in BUDGETS.items():
            for variant,kwargs in VARIANTS.items():
                name=variant+'_'+budget_name;choices=[]
                for split in (False,True):
                    for lam in lambdas:
                        tick=time.perf_counter()
                        policy=JointPolicy().fit(fitb,reference_arm=reference,budget=budget,lambda_value=lam,
                                                allow_free_split=split,**kwargs)
                        objective,cost=risk(policy,gate)
                        choices.append((objective,cost,policy.to_dict()['tree'],split,lam,policy,time.perf_counter()-tick))
                # Model-node count is an explicit tie-breaker, never DEV performance.
                def nodes(x):return 1+sum(nodes(v) for v in x.values() if isinstance(v,dict))
                best=min(choices,key=lambda r:(r[0],r[1],nodes(r[2]),r[3],r[4]))
                models[family][name]=best[5]
                fm['search'][name]=[dict(gate_objective=r[0],gate_seconds=r[1],allow_free_split=r[3],lambda_value=r[4],
                     seconds=r[6],counts=r[5].counts,hash=r[5].frozen_hash) for r in choices]
                fm['selected'][name]=best[5].to_dict()
                write(out/'progress.json',{'status':'running','family':family,'last_policy':name,'elapsed_seconds':time.perf_counter()-started})
                print(f'{family} {name} fitted gate={best[0]:.6g}',flush=True)
        manifest['families'][family]=fm
    for p in [Path(__file__),*[Path('src/introact_ts/v431_r4')/n for n in
              ('joint_policy.py','branch_cost.py','origin_scale.py','trajectory_dataset.py')]]:
        manifest['source_sha256'][str(p)]=sha(p)
    joblib.dump(models,out/'models.joblib');write(out/'manifest.json',manifest)
    write(out/'models_frozen.json',{'sha256':sha(out/'models.joblib'),'manifest_sha256':sha(out/'manifest.json'),
                                   'completed_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-started})
    write(out/'progress.json',{'status':'completed','elapsed_seconds':time.perf_counter()-started})


def frozen():
    out=ROOT/'fit';f=read(out/'models_frozen.json');m=read(out/'manifest.json')
    assert sha(out/'models.joblib')==f['sha256'] and sha(out/'manifest.json')==f['manifest_sha256']
    assert sha(ROOT/'hot_costs.json')==m['hot_cost_sha256']
    for path,value in m['source_sha256'].items():assert sha(path)==value,('Frozen execution code changed',path)
    return joblib.load(out/'models.joblib'),m


def row_record(b,i,name,t,reference,budget,*,origin='r4',information='typed legal free and acquired history'):
    a=t['action'];m=b.rows[i]['meta'];gain=float(b.report_losses[i,reference]-b.report_losses[i,a])
    result={'family':b.family,'policy':name,'episode_uid':str(b.uids[i]),'parent_group':str(b.parents[i]),
       'source':str(b.sources[i]),'role':str(b.roles[i]),'split':m['split'],'raw_start':m['raw_start'],
       'horizon':m['horizon'],'condition':m['condition'],'arm':POOL[a],'reference_arm':POOL[reference],
       'mase':float(b.report_losses[i,a]),'mae':float(b.losses[i,a]*b.rows[i]['origin_scale']['value']),
       'learning_loss':float(b.losses[i,a]),'learning_scale':b.rows[i]['origin_scale'],
       'report_scale':b.rows[i]['outer_report_scale'],'total_seconds':t['total_seconds'],'tool_count':t.get('tool_count',0),
       'budget':budget,'budget_overrun':t['total_seconds']>budget+1e-12,
       'switch_gain':max(gain,0.),'wrong_switch_loss':max(-gain,0.),'net_gain':gain,
       'candidate_hash':b.rows[i]['actions'][POOL[a]]['input_hash'],'forecast_hash':b.rows[i]['actions'][POOL[a]]['prediction_hash'],
       'action_identity':b.rows[i]['actions'][POOL[a]],'trace':t,'origin':origin,'information':information}
    return result


def summarize(rows):
    groups=defaultdict(list)
    for r in rows:groups[r['family'],r['policy']].append(r)
    table=[];sources=[]
    columns=('mase','mae','total_seconds','tool_count','switch_gain','wrong_switch_loss','net_gain')
    for (f,p),rr in sorted(groups.items()):
        assert len({r['episode_uid'] for r in rr})==len(rr)
        w=group_weights([r['parent_group'] for r in rr],[r['source'] for r in rr])
        table.append(dict(family=f,policy=p,parents=len({r['parent_group'] for r in rr}),episodes=len(rr),
          sources=len({r['source'] for r in rr}),budget_overruns=sum(r['budget_overrun'] for r in rr),
          **{k:float(np.dot(w,[r[k] for r in rr])) for k in columns}))
        for source in sorted({r['source'] for r in rr}):
            sr=[r for r in rr if r['source']==source];sw=group_weights([r['parent_group'] for r in sr],[source]*len(sr))
            sources.append(dict(family=f,policy=p,source=source,parents=len({r['parent_group'] for r in sr}),episodes=len(sr),
                 **{k:float(np.dot(sw,[r[k] for r in sr])) for k in columns}))
    return table,sources


def evaluate(suite='main',role='dev'):
    models,manifest=frozen();out=ROOT/'evaluation'/(suite if suite!='main' else role)
    if (out/'status.json').exists():raise RuntimeError('Preserve first frozen evaluation snapshot')
    started=time.perf_counter();rows=[]
    for family in ('bolt','timesfm'):
        b=load_batch(suite,family)
        if suite=='main':b=b.subset(b.roles==role)
        reference=manifest['families'][family]['reference_action']
        for name,p in models[family].items():
            for i in range(len(b.uids)):rows.append(row_record(b,i,name,trace(p,b,i),reference,p.budget))
        for budget_name,budget in BUDGETS.items():
            for a in range(5):
                for i in range(len(b.uids)):
                    actual=0 if b.fully_observed[i] else a
                    t={'action':actual,'tool':None,'tool_count':0,'total_seconds':float(b.action_costs[i,actual]),'reason':'complete_KEEP' if actual!=a else 'fixed_action'}
                    rows.append(row_record(b,i,'FIXED_'+POOL[a]+'_'+budget_name,t,reference,budget))
            for i in range(len(b.uids)):
                a=0 if b.fully_observed[i] else reference
                rows.append(row_record(b,i,'FIXED_REFERENCE_'+budget_name,{'action':a,'tool':None,'tool_count':0,'total_seconds':float(b.action_costs[i,a])},reference,budget))
    table,sources=summarize(rows);write(out/'decisions.json',rows);write(out/'table.json',table);write(out/'sources.json',sources)
    write(out/'status.json',{'status':'completed','seconds':time.perf_counter()-started,'rows':len(rows),'groups':len(table),
                            'heldout_read':False,'frozen_manifest_sha256':sha(ROOT/'fit/manifest.json')})
    print(json.dumps({'suite':suite,'role':role,'rows':len(rows),'groups':len(table)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--fit',action='store_true');parser.add_argument('--evaluate',action='store_true')
    parser.add_argument('--suite',choices=['main','financial','generalization'],default='main');parser.add_argument('--role',default='dev',choices=['dev','T_check','T_acq','T_fit'])
    args=parser.parse_args()
    if args.fit:fit()
    if args.evaluate:evaluate(args.suite,args.role)
