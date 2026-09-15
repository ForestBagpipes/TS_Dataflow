"""Small deployment contracts only; real frozen-policy audit is recorded separately."""
from types import SimpleNamespace
import numpy as np
import pytest
from introact_ts.v431_r4.joint_policy import JointPolicy,VisibleState,AcquiredEvidence

def fixture():
 n=40; y=np.arange(n)%2; loss=np.ones((n,5))*3;loss[y==0,0]=0;loss[y==1,1]=0
 return SimpleNamespace(visible=np.zeros((n,1)),free_names=('missing_fraction',),evidence={'H':y[:,None]},
  evidence_names={'H':('history_mae',)},supported={'H':np.ones(n,bool)},tool_costs={'H':np.full(n,.1)},
  action_costs=np.full((n,5),.1),parents=np.array(list(map(str,range(n)))),roles=['T_fit']*n,
  fully_observed=np.zeros(n,bool),weights=np.full(n,1/n),losses=loss)

def test_only_registered_purchased_tool_features_are_accepted():
 p=JointPolicy().fit(fixture(),tools=('H',));v=VisibleState({'missing_fraction':.2},False,{'H':True})
 with pytest.raises(ValueError):p.decide(v,AcquiredEvidence('H32',{'history_mae':0}))
 with pytest.raises(ValueError):p.decide(VisibleState(dict(v.features,future_mae=0),False,v.applicable))
 assert p.decide(v,AcquiredEvidence('H',{'history_mae':None}))['reason']=='missing_evidence_fallback'

def test_complete_target_and_unsupported_do_not_acquire():
 p=JointPolicy().fit(fixture(),tools=('H',))
 d=p.decide(VisibleState({'missing_fraction':0},True,{'H':True}),remaining_budget=0)
 assert d['arm']=='A0_NATIVE' and d['total_budget_unmet'] and d['estimated_final_seconds']>0
 d=p.decide(VisibleState({'missing_fraction':.2},False,{'H':False}))
 assert d['reason']=='unsupported_tool_fallback' and d['kind']=='submit'

def audit_frozen():
 import importlib.util,json,hashlib
 from pathlib import Path
 from collections import defaultdict
 from datetime import datetime,timezone
 spec=importlib.util.spec_from_file_location('r4_frozen_run','scripts/v431_r4_run.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
 models,manifest=run.frozen();results=[];failures=[]
 for family,policies in models.items():
  whole=run.load_batch('main',family);fit=whole.subset(whole.roles=='T_fit');gate=whole.subset(whole.roles=='T_gate')
  assert not set(fit.parents)&set(gate.parents)
  sources=set(fit.sources)
  for s in sources:assert abs(fit.weights[fit.sources==s].sum()-1/len(sources))<1e-10
  for name,p in policies.items():
   checks=[];threshold_checks=0
   for j,n in enumerate(fit.free_names):
    x=fit.visible[:,j];x=x[np.isfinite(x)];expected=sorted(set(np.quantile(x,[.25,.5,.75]).tolist())) if len(x) else []
    assert p.free_thresholds[n]==expected;threshold_checks+=1
   for t in p.tools:
    valid=fit.supported[t]
    for j,n in enumerate(fit.evidence_names[t]):
     x=fit.evidence[t][valid,j];x=x[np.isfinite(x)];expected=sorted(set(np.quantile(x,[.25,.5,.75]).tolist())) if len(x) else []
     assert p.evidence_thresholds[t][n]==expected;threshold_checks+=1
   assert set(p.training_parents)==set(fit.parents)==set(p.cost.fit_parents)
   leaf_parents=defaultdict(set);decisions=[];risk=0.;cost=0.;natural=defaultdict(int)
   best=np.argmin(fit.losses,axis=1);best[np.isclose(fit.losses[:,p.reference_arm],fit.losses.min(axis=1),rtol=0,atol=1e-12)]=p.reference_arm
   for i in range(len(fit.uids)):
    t=run.trace(p,fit,i,measure=False);a=t['action'];c=t['total_seconds'];cost+=fit.weights[i]*c
    objective=fit.losses[i,a] if p.objective=='task' else float(a!=best[i]);risk+=fit.weights[i]*(objective+p.lambda_value*c)
    if fit.fully_observed[i]:assert a==0 and t['tool'] is None
    node=p.tree;path='root'
    if node['kind']=='free_split':
     v=fit.visible[i,list(fit.free_names).index(node['feature'])];side='left' if v<=node['threshold'] else 'right';node=node[side];path+='.'+side
    after=t['after'];reason=after['reason'];natural[(t['tool'] or 'STOP')]+=1
    if reason=='policy_STOP':leaf_parents[path+'.submit'].add(str(fit.parents[i]))
    if reason=='evidence_commit':
     leaf=node['terminal'];tool=node['tool']
     if leaf['kind']=='split':
      val=fit.evidence[tool][i,list(fit.evidence_names[tool]).index(leaf['feature'])];side='left' if val<=leaf['threshold'] else 'right';path+='.'+side
     leaf_parents[path+'.'+tool].add(str(fit.parents[i]))
   support={k:len(v) for k,v in leaf_parents.items()};bad={k:v for k,v in support.items() if v<16}
   if bad:failures.append(dict(family=family,policy=name,kind='leaf_support',detail=bad))
   if abs(risk-p.fit_objective)>1e-9 or abs(cost-p.fit_cost)>1e-9:failures.append(dict(family=family,policy=name,kind='runtime_objective_cost_mismatch',risk=risk,fit_risk=p.fit_objective,cost=cost,fit_cost=p.fit_cost))
   results.append(dict(family=family,policy=name,hash=p.frozen_hash,tree=p.tree,threshold_checks=threshold_checks,
    fit_parents=len(set(fit.parents)),gate_parents=len(set(gate.parents)),support=support,fit_requested_tools=dict(natural),
    independently_replayed_objective=risk,stored_objective=p.fit_objective,
    independently_replayed_cost=cost,stored_cost=p.fit_cost,counts=p.counts))
 coverage=[]
 for suite in ('dev','T_check','T_acq','T_fit','financial','generalization'):
  d=Path('results/v431-r4/evaluation')/suite;path=d/'common_decisions.json'
  if not path.exists():path=d/'decisions.json'
  if not path.exists():coverage.append(dict(suite=suite,status='pending'));continue
  rows=json.loads(path.read_text());groups=defaultdict(list)
  for r in rows:groups[r['family'],r['policy']].append(r)
  for family in ('bolt','timesfm'):
   expected={r['episode_uid'] for r in groups[family,'JOINT_high']}
   for (f,name),rr in groups.items():
    if f!=family:continue
    actual={r['episode_uid'] for r in rr};ok=actual==expected and len(actual)==len(rr)
    if not ok:failures.append(dict(suite=suite,family=f,policy=name,kind='denominator',missing=sorted(expected-actual),extra=sorted(actual-expected)))
   coverage.append(dict(suite=suite,family=family,expected_episodes=len(expected),policy_count=sum(f==family for f,p in groups),status='checked'))
 out=dict(status='passed' if not failures else 'failed',created_at=datetime.now(timezone.utc).isoformat(),
  model_sha256=run.sha(Path('results/v431-r4/fit/models.joblib')),manifest_sha256=run.sha(Path('results/v431-r4/fit/manifest.json')),
  hot_cost_sha256=run.sha(Path('results/v431-r4/hot_costs.json')),frozen_policies=results,coverage=coverage,failures=failures,
  limitation='CPU typed replay of frozen policies, not real online GPU branch execution. Input/prediction reuse relies on frozen r3 provenance; no current future is a runtime feature.')
 path=Path('results/v431-r4/verification/frozen_policy.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
 print(json.dumps({'status':out['status'],'policies':len(results),'failures':failures}))
 return out


def audit_online():
 import json,hashlib,re
 from pathlib import Path
 from collections import defaultdict
 from datetime import datetime,timezone
 from introact_ts.v431_r4.trajectory_dataset import load_data
 from introact_ts.v43.schemas import array_hash
 base=Path('results/v431-r4');data={s:load_data(s) for s in ('main','financial')};out={'families':{},'failures':[]}
 for family in ('bolt','timesfm'):
  path=base/('online-'+family+'-r1');status=json.loads((path/'status.json').read_text());assert status['status']=='completed'
  protocol=json.loads((path/'protocol.json').read_text());rows=json.loads((path/'decisions.json').read_text());account=json.loads((path/'process_accounting.json').read_text());barrier=json.loads((path/'visibility_barrier.json').read_text())
  assert barrier['status']=='passed' and barrier['unexpected']==0 and barrier['denied_preflight']==6 and barrier['before_evaluator_open'] and barrier['all_final_predictions_saved']
  assert len(rows)==22 and sum(not r['controlled'] for r in rows)==19
  model=json.loads((path/'service/model_manifest.json').read_text());response_rows=[]
  for f in (path/'service').glob('r3-*.response.json'):
   response=json.loads(f.read_text());assert response['status']=='completed'
   key=response['model_key'];assert response['model_revision']==model['models'][key]['revision']
   num=int(f.name.split('-')[1])
   for r in response['rows']:
    assert r['actual_batch_size']==1
    response_rows.append(dict(sequence=num,model=key,task=response['task'],input_hash=r['input_hash'],prediction_hash=r['prediction_hash'],runtime_seconds=r['runtime_seconds'],cache_hit=r.get('cache_hit'),raw_native_file=r.get('raw_native_file'),response_file=str(f)))
  target_rows=[r for r in response_rows if r['model']==family]
  if family=='timesfm':
   assert all(r['cache_hit'] is False for r in target_rows)
   native=[r['raw_native_file'] for r in target_rows];assert len(set(native))==len(native)
   assert all(Path(f).exists() for f in native)
   assert len(list((path/'service/timesfm-native/raw').glob('*.npz')))==len(native)
  cases=[];previous=0
  with np.load(path/'live_arrays.npz',allow_pickle=False) as arrays:
   for row in rows:
    d=data[row['suite']];u=row['episode_uid'];arm=row['final']['arm'];wanted=d.predictions[family][u][arm];pred=arrays[row['case_id']+'_prediction'];candidate=arrays[row['case_id']+'_candidate'];expected=d.old.pools[u][arm]
    assert np.allclose(pred,wanted,rtol=1e-6,atol=1e-5) and np.allclose(candidate,expected,rtol=1e-6,atol=1e-5,equal_nan=True)
    pm=float(np.max(np.abs(pred-wanted)));cm=float(np.max(np.abs(candidate[np.isfinite(candidate)]-expected[np.isfinite(candidate)])))
    assert np.array_equal(np.isfinite(candidate),np.isfinite(expected))
    assert array_hash(pred)==row['final']['prediction_hash'] and array_hash(candidate)==row['final']['candidate_hash']
    assert (array_hash(pred)==array_hash(wanted))==row['prediction_hash_equal']
    assert (array_hash(candidate)==array_hash(expected))==row['candidate_hash_equal']
    assert abs(sum(row['component_seconds'].values())-row['hot_request_seconds'])<1e-8
    assert row['budget_overrun']==(row['hot_request_seconds']>row['budget'])
    assert abs(row['before_remaining_budget']-max(0,row['budget']-row['before_elapsed_seconds']))<1e-9
    if row['after_elapsed_seconds'] is not None:assert abs(row['after_remaining_budget']-max(0,row['budget']-row['after_elapsed_seconds']))<1e-9
    assert row['actual_tool_calls']==len(row['actual_probes'])
    if row['fully_observed']:assert arm=='A0_NATIVE' and row['branch'] is None
    if row['branch'] is None:assert row['before_decision']==row['after_decision']
    final_keys=[c['key'] for c in row['final']['invoice']['charges']];seq=int(final_keys[0].split('-')[1]);rr=[r for r in response_rows if previous<r['sequence']<=seq];previous=seq
    cases.append(dict(case_id=row['case_id'],suite=row['suite'],controlled=row['controlled'],episode_uid=u,origin_uid=row.get('origin_uid'),parent_group=row['parent_group'],source=row['source'],H=row['horizon'],branch=row['branch'],online_arm=arm,online_actual_action=row['final']['actual_action'],
      primitive_probes=row['actual_tool_calls'],backbone_prediction_api_rows=sum(r['model']==family for r in rr),tsicl_imputation_api_rows=sum(r['model']=='tsicl' for r in rr),
      candidate_max_abs_difference=cm,prediction_max_abs_difference=pm,candidate_hash_equal=row['candidate_hash_equal'],prediction_hash_equal=row['prediction_hash_equal'],
      prediction_dtype=str(pred.dtype),cached_prediction_dtype=str(wanted.dtype),prediction_values_exact_equal=bool(np.array_equal(pred,wanted)),prediction_hash_equal_after_cached_dtype_cast=array_hash(pred.astype(wanted.dtype))==array_hash(wanted),
      hot_seconds=row['hot_request_seconds'],components=row['component_seconds'],budget=row['budget'],budget_overrun=row['budget_overrun'],failure=row['failure'],
      before_remaining=row['before_remaining_budget'],after_remaining=row['after_remaining_budget'],final_reason=row['after_decision']['reason'],final_estimate_unmet=row['after_decision']['total_budget_unmet']))
  assert sum(r['backbone_prediction_api_rows'] for r in cases)==len(target_rows)
  assert abs(account['hot_request_seconds']-sum(r['hot_seconds'] for r in cases))<1e-8
  assert abs(account['process_wall_seconds']-account['hot_request_seconds']-account['model_startup_seconds']-account['remaining_overhead_seconds'])<1e-8
  summaries={}
  for name,group in [('natural',[r for r in cases if not r['controlled']]),('main_natural',[r for r in cases if not r['controlled'] and r['suite']=='main']),('financial_natural',[r for r in cases if not r['controlled'] and r['suite']=='financial']),('controlled',[r for r in cases if r['controlled']])]:
   summaries[name]=dict(requests=len(group),acquisition_decisions=sum(r['branch'] is not None for r in group),primitive_probes=sum(r['primitive_probes'] for r in group),backbone_prediction_api_rows=sum(r['backbone_prediction_api_rows'] for r in group),tsicl_imputation_api_rows=sum(r['tsicl_imputation_api_rows'] for r in group),hot_mean=float(np.mean([r['hot_seconds'] for r in group])),hot_p95=float(np.quantile([r['hot_seconds'] for r in group],.95)),hot_max=max(r['hot_seconds'] for r in group),overruns=sum(r['budget_overrun'] for r in group),tool_failure_requests=sum(bool(r['failure']) for r in group))
  offline_comparison=[]
  for suite in ('main','financial'):
   ep=base/'evaluation'/('dev' if suite=='main' else 'financial')/'decisions.json'
   erows=json.loads(ep.read_text());mapping={r['episode_uid']:r for r in erows if r['family']==family and r['policy']=='JOINT_high'}
   context_path=Path('results/v43/20260914T141030.324186Z-agent/contexts.npz') if suite=='main' else Path('results/v431-r2/financial-observation-index-r1/contexts.npz')
   with np.load(context_path,allow_pickle=False) as original,np.load(path/'live_arrays.npz',allow_pickle=False) as actual_arrays:
    for r in rows:
     if r['suite']!=suite:continue
     target=original[r['episode_uid']+'_target'];candidate=actual_arrays[r['case_id']+'_candidate'];observed=np.isfinite(target)
     assert np.array_equal(candidate[observed],target[observed]),'Observed value overwritten'
     if r['controlled']:continue
     old=mapping[r['episode_uid']]
     assert r['parent_group']==old['parent_group'] and r['source']==old['source'] and r['horizon']==old['horizon'] and r['raw_start']==old['raw_start']
     before_arm=old['arm'];after_arm=r['final']['arm']
     expected_pred=data[suite].predictions[family][r['episode_uid']][before_arm];actual_pred=actual_arrays[r['case_id']+'_prediction']
     offline_comparison.append(dict(case_id=r['case_id'],suite=suite,episode_uid=r['episode_uid'],origin_uid=r.get('origin_uid'),parent_group=r['parent_group'],offline_arm=before_arm,online_arm=after_arm,arm_equal=before_arm==after_arm,
      offline_branch=old['trace'].get('tool'),online_branch=r['branch'],prediction_max_abs_difference=float(np.max(np.abs(actual_pred-expected_pred))),prediction_values_equal=bool(np.array_equal(actual_pred,expected_pred)),reason=r['after_decision']['reason'],offline_mase=old['mase'],online_mase=r['mase']))
  out['families'][family]=dict(natural_offline_action_comparison=offline_comparison,natural_offline_action_equal=sum(r['arm_equal'] for r in offline_comparison),observed_input_values_preserved=True,path=str(path),status='passed',protocol_sha256=hashlib.sha256((path/'protocol.json').read_bytes()).hexdigest(),decisions_sha256=hashlib.sha256((path/'decisions.json').read_bytes()).hexdigest(),barrier=barrier,model_revision=model['models'][family]['revision'],
   summaries=summaries,cases=cases,process_accounting=account,response_rows=response_rows,
   candidate_max_abs_difference=max(r['candidate_max_abs_difference'] for r in cases),prediction_max_abs_difference=max(r['prediction_max_abs_difference'] for r in cases),
   candidate_hash_equal=sum(r['candidate_hash_equal'] for r in cases),prediction_hash_equal=sum(r['prediction_hash_equal'] for r in cases),
   cross_request_cache_verification='all TimesFM native files unique and cache_hit false; wrapper clears memoized predictions each call' if family=='timesfm' else 'Bolt worker calls official predict separately for each response row; no inter-request prediction memoization')
 out.update(status='passed',created_at=datetime.now(timezone.utc).isoformat(),limitation='All 19 natural requests reuse already-viewed DEV/financial cases, not independent confirmation. Primitive probes differ from model prediction API rows; internal neural forward count was not instrumented. Full process includes 3 controlled requests.',numerical_tolerance={'rtol':1e-6,'atol':1e-5},prior_failure='online-bolt initial attempt failed at nested GPU lock before model work; retained, not counted as successful latency')
 p=base/'verification/online.json';p.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'status':out['status'],'families':{f:x['summaries'] for f,x in out['families'].items()}}))
 return out

if __name__=='__main__':
 import sys
 if '--online' in sys.argv:audit_online()
 else:audit_frozen()
