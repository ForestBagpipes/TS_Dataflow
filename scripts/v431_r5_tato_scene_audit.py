#!/usr/bin/env python3
"""Audit completed TRAIN-scene TATO artifacts, then score saved old-DEV outputs.
No tuning, model execution, or calibration/test access. Pending scenes stay pending.
"""
from pathlib import Path
from collections import Counter
import hashlib,json,argparse
import numpy as np
import joblib
from v431_r3_statistics import macro,blocked_bootstrap
ROOT=Path('results/v431-r5');SCENES=ROOT/'tato-scene';OLD=Path('results/v43/20260914T141030.324186Z-agent')
BASELINES=('FIXED_A0_NATIVE','FIXED_A2_SINGLE','REFERENCE_FREE','R5','R2_EXISTING_CART','TATO_NATIVE_8')
POOL=('A0_NATIVE','A0_FFILL','A2_SINGLE','A3_COV','A4_RIDGE_CONTEXT')
BUDGETS={'low':.8140623268639832,'high':3.5}

def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def arrsha(x):
 x=np.ascontiguousarray(x);return hashlib.sha256(x.dtype.str.encode()+str(x.shape).encode()+x.tobytes()).hexdigest()
def point_hash(x):return hashlib.sha256(np.asarray(x).tobytes()).hexdigest()
def write(p,v):
 p.parent.mkdir(exist_ok=True,parents=True);q=p.with_suffix('.tmp');q.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n');q.replace(p)

def summary(rows):
 good=[r for r in rows if r.get('mase') is not None]
 out={'episodes':len(rows),'parents':len({r['parent_group'] for r in rows}),'successful_episodes':len(good),
      'failed_or_not_run_episodes':len(rows)-len(good),'mase_full_denominator':macro(rows,'mase') if len(good)==len(rows) else None,
      'mase_success_subset_only':macro(good,'mase') if good else None,
      'complete_cost_records':sum(r.get('total_seconds') is not None for r in rows),
      'budget_overruns':sum(r.get('total_seconds') is not None and r['total_seconds']>r['budget'] for r in rows)}
 costs=[r for r in rows if r.get('total_seconds') is not None]
 out['seconds_macro_available_records']=macro(costs,'total_seconds') if costs else None
 out['max_seconds']=max((r['total_seconds'] for r in costs),default=None)
 return out

def scene_request_path(directory):
 run=directory/'run';candidates=sorted(directory.glob('request*.json'))
 if (run/'frozen_scene.json').exists():
  expected=read(run/'frozen_scene.json')['request_sha256']
  matches=[p for p in candidates if sha(p)==expected]
  assert matches,'Frozen request hash must match an archived request'
  # Byte-identical preregistered/resolved copies have the same verified identity.
  return next((p for p in matches if p.name=='request.resolved.json'),matches[0])
 for name in ('request.resolved.json','request.json','request.preregistered.json'):
  if (directory/name).exists():return directory/name
 raise ValueError('No request found')

def verify_cache_amendment(request):
 amendment=request.get('cache_amendment')
 if amendment is None:return None
 original_path=Path(amendment['original_request']);assert sha(original_path)==amendment['original_request_sha256']
 original=read(original_path)
 fixed=('family','horizon','source','target_channel','target_field','condition','context','train_parents','dev_parents','rows','trials','inputs_sha256','seed','adapter_sha256','reference_frozen_sha256','supervision')
 assert all(request[k]==original[k] for k in fixed),'Cache amendment changed method, supervision, or input identity'
 assert 0<request['max_seconds']<=original['max_seconds']==600
 assert request['trials']==original['trials']==500
 assert amendment['original_worker_sha256']==original['worker_sha256']
 assert amendment['new_worker_sha256']==request['worker_sha256']==sha(Path('scripts/v431_r5_tato_cached_scene.py'))
 assert amendment['cache_module_sha256']==request['cache_module_sha256']==sha(Path('scripts/v431_r5_tato_parent_cache.py'))
 proof_paths={'bolt_audit_sha256':SCENES/'train_cache_reuse_audit.json',
              'timesfm_audit_sha256':SCENES/'timesfm_train_cache_reuse_audit.json'}
 for key,path in proof_paths.items():assert amendment[key]==sha(path)
 assert sha(request['inputs'])==original['inputs_sha256']
 return dict(amendment,verified=True,original_status='superseded_before_execution',
  scope='same TRAIN supervision/data/500 trials/600 second cap; only native prediction memoization changed')

def canonical_digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def audit_native_calls(calls,run,model,request,strict_raw):
 """Verify first physical source and nonzero lookup accounting without GPU replay."""
 request_rows={r['uid']:r for r in request['rows']};checked=0;maxgpu=0;hits=[];failures=[]
 memo={};protocol=model.get('cache_numeric_protocol');base_identity={k:v for k,v in model.items() if k!='cache_numeric_protocol'}
 for index,call in enumerate(calls):
  is_parent_cache='cache_identity' in call
  if is_parent_cache:
   identity=call['cache_identity'];row=request_rows[call['episode_uid']]
   assert identity['parent']==row['parent'] and identity['H']==call['horizon']
   assert identity['model_identity_hash']==canonical_digest(base_identity)
   assert identity['numeric_protocol_hash']==canonical_digest(protocol)
   assert call['cache_key']==canonical_digest(identity)
   assert np.isfinite(call['seconds']) and call['seconds']>=0
   assert np.isfinite(call['lookup_seconds']) and call['lookup_seconds']>=0
   assert call['seconds']+1e-12>=call['lookup_seconds']
   expected_scope='train_cross_trial' if row['role']=='train' else 'deployment_request'
   assert call['cache_scope']==expected_scope
   if row['role']=='dev':assert not call['cache_hit'],'Cross-request deployment cache hit prohibited'
   if call.get('status')=='failed':
    assert not call['cache_hit'] and call['native_compute_seconds'] is None
    failures.append({'index':index,'uid':call['episode_uid'],'seconds':call['seconds'],'reason':call.get('error')});continue
   if call['cache_hit']:
    first=int(call['first_call_index']);assert first<index and first in memo
    prior=calls[first];assert not prior['cache_hit'] and prior['cache_scope']=='train_cross_trial'
    assert prior['cache_identity']==identity
    assert call['first_raw_file']==prior['raw_file'] and call['first_raw_sha256']==prior['raw_sha256']
    assert call['point_hash']==memo[first]['point_hash']
    assert call['first_charged_seconds']==prior['seconds']
    assert call['native_compute_seconds']==0. and call['seconds']==call['lookup_seconds']
    hits.append({'index':index,'first_index':first,'uid':call['episode_uid'],'seconds':call['seconds'],'first_charged_seconds':call['first_charged_seconds']});continue
  elif call['cache_hit']:
   continue
  if not strict_raw:
   if is_parent_cache:memo[index]={'point_hash':call['point_hash']}
   continue
  file=run/call['raw_file'];assert sha(file)==call['raw_sha256']
  with np.load(file,allow_pickle=False) as raw:
   x=raw['input'];point=raw['point'];assert np.isfinite(point).all() and np.isfinite(x).all()
   if is_parent_cache:
    assert identity['input_hash']==arrsha(x) and identity['dtype']==x.dtype.str and identity['shape']==list(x.shape)
    native_point=point if point.ndim==3 else point[:,:,None]
    assert call['point_hash']==arrsha(native_point)
    assert call['first_raw_file']==call['raw_file'] and call['first_raw_sha256']==call['raw_sha256']
    assert call['first_call_index']==index and call['first_charged_seconds']==call['seconds']
    assert call['seconds']+1e-8>=call['native_compute_seconds']>=0
    memo[index]={'point_hash':arrsha(native_point)}
   else:assert call['cache_key']==arrsha(x)+':'+str(call['horizon'])
  maxgpu=max(maxgpu,int(call.get('peak_gpu_bytes') or 0));checked+=1
 return {'physical_raw_checked':checked,'peak_gpu_bytes':maxgpu,'parent_scoped_cache_hits':len(hits),
   'lookup_seconds':sum(r['seconds'] for r in hits),'native_first_cost_not_erased':True,
   'deployment_cross_request_hits':0,'failed_forecasts':failures,'hit_examples':hits[:10],
   'scope':'TRAIN native outputs only; same parent/model/protocol/input/dtype/H; DEV request cache cleared'}

def audit_scene(directory,strict_raw=True):
 request_path=scene_request_path(directory);request=read(request_path);run=directory/'run';train=[x for x in request['rows'] if x['role']=='train'];dev=[x for x in request['rows'] if x['role']=='dev']
 result={'scene':directory.name,'family':request['family'],'horizon':request['horizon'],
   'requested_trials':request['trials'],'train_parents':len({r['parent'] for r in train}),'dev_parents':len({r['parent'] for r in dev}),
   'unit_protocol':'official96' if directory.parent.name=='tato-official96' else 'scaled_unit_scene','request_sha256':sha(request_path),'request_path':str(request_path),'source':request['source'],'condition':request['condition'],'target_field':request['target_field'],'protocol':request['protocol'],'rows':[]}
 prereg=directory/'request.preregistered.json'
 if not prereg.exists() and request_path.name!='request.json':prereg=directory/'request.json'
 if prereg.exists():
  old=read(prereg)
  fixed=('family','horizon','source','target_channel','target_field','condition','context','train_parents','dev_parents','rows','trials','inputs_sha256','seed','worker_sha256','adapter_sha256','reference_frozen_sha256','supervision')
  assert all(request[k]==old[k] for k in fixed),'Resolved request changed preregistered method/data identity'
  for unit_key in ('patch_len','data_patch_len','model_patch_len','initial_trimmer_seq_l'):
   if unit_key in old:assert request[unit_key]==old[unit_key]
  assert 0<request['max_seconds']<=old['max_seconds']
  result['request_resolution']={'preregistered_sha256':sha(prereg),'resolved_sha256':sha(request_path),'maximum_seconds':request['max_seconds'],'preregistered_seconds':old['max_seconds']}
 result['cache_amendment_audit']=verify_cache_amendment(request)
 # Check packed roles without opening any original DEV target.
 frozen_ref=read(ROOT/'fit/models_frozen.json');assert sha(ROOT/'fit/models.joblib')==frozen_ref['sha256']
 reference_parents=set(joblib.load(ROOT/'fit/models.joblib')['families'][request['family']]['reference'].training_parents)
 assert {r['parent'] for r in train}<=reference_parents
 with np.load(request['inputs'],allow_pickle=False) as packed:
  expected_keys={r['uid']+'_context' for r in request['rows']}|{r['uid']+suffix for r in train for suffix in ('_target','_mask')}
  assert set(packed.files)==expected_keys,'Packed scene includes unexpected target/feature arrays'
  for r in request['rows']:
   assert r['source']==request['source'] and r['horizon']==request['horizon']
   assert packed[r['uid']+'_context'].shape==(512,) and arrsha(packed[r['uid']+'_context'])==r['input_hash']
 result['preparation_role_audit']='exact T_fit parents and context-only DEV archive; no DEV target keys'
 if (directory/'pilot/status.json').exists():result['pilot']=read(directory/'pilot/status.json')
 required=('status.json','frozen_scene.json','deployment.json','predictions.npz','trials.json','model_identity.json','calls.json')
 if any(not (run/p).exists() for p in required):
  result['status']='pending_frozen_and_all_saved_deployment';result['missing']=[p for p in required if not (run/p).exists()]
  if (run/'status.json').exists():
   terminal=read(run/'status.json');result['worker_status']=terminal
   if terminal.get('status')=='failed':result['status']='worker_failed_without_saved_frozen_deployment'
  return result
 status=read(run/'status.json')
 if status['status'] not in ('completed','partial'):
  result['status']='pending_worker_completion';result['worker_status']=status;return result
 frozen=read(run/'frozen_scene.json');deployment=read(run/'deployment.json')
 assert frozen['status']=='frozen_from_TRAIN' and frozen['request_sha256']==sha(request_path)
 assert {r['uid'] for r in deployment}=={r['uid'] for r in dev},'Incomplete deployment manifest; do not open DEV labels yet'
 assert sha(request['inputs'])==request['inputs_sha256']
 assert not {r['parent'] for r in train}&{r['parent'] for r in dev}
 inputs=np.load(request['inputs'],allow_pickle=False);trials=read(run/'trials.json');complete=[]
 # Verify every saved TRAIN score independently, not just the chosen trial.
 train_index={r['uid']:r for r in train};trainchecks=0
 for trial in trials:
  scores=[];pfile=run/f"train_predictions_{trial['trial']:04d}.npz"
  with np.load(pfile,allow_pickle=False) as preds:
   for sample in trial['samples']:
    uid=sample['uid'];row=train_index[uid];p=preds[uid];x=inputs[uid+'_context'];y=inputs[uid+'_target'];mask=inputs[uid+'_mask'].astype(bool)&np.isfinite(y)
    assert p.shape==(request['horizon'],) and np.isfinite(p).all()
    assert row['input_hash']==arrsha(x) and row['target_hash']==arrsha(y) and row['mask_hash']==arrsha(inputs[uid+'_mask'])
    assert sample['prediction_hash']==arrsha(p) and sample['prediction_sha256']==point_hash(p)
    assert sample['input_sha256']==point_hash(x.astype(np.float64))
    assert row['train_bounds'][0]<=row['raw_start'] and row['origin']+request['horizon']<=row['train_bounds'][1]
    mse=float(np.mean((p[mask]-y[mask])**2));mae=float(np.mean(np.abs(p[mask]-y[mask])))
    assert abs(mse-sample['train_mse'])<=1e-9*max(1,abs(mse)) and abs(mae-sample['train_mae'])<=1e-9*max(1,abs(mae))
    scores.append(mse);trainchecks+=1
   if trial['status']=='completed':
    assert {s['uid'] for s in trial['samples']}==set(train_index)
    assert abs(float(np.mean(scores))-trial['train_macro_mse'])<=1e-9*max(1,abs(trial['train_macro_mse']))
    complete.append(trial)
 best=min(complete,key=lambda t:(t['train_macro_mse'],t['trial']))
 assert frozen['trial']==best['trial'] and frozen['params']==best['params']
 assert frozen['train_macro_mse']==best['train_macro_mse']
 dataset=joblib.load(ROOT/'data/main'/(request['family']+'.joblib'));batch=dataset['batch'];indices={str(u):i for i,u in enumerate(batch.uids)}
 meta=read(OLD/'episode_manifest.json');identity=read(run/'model_identity.json');model=identity['backbone'];expected=dataset['cache_metadata'][0][0]['model']
 assert model['repo_id']==expected['checkpoint'] and model['revision']==expected['revision']
 assert frozen['model_identity']==model
 calls=read(run/'calls.json')
 cache_audit=audit_native_calls(calls,run,model,request,strict_raw)
 rawchecked=cache_audit['physical_raw_checked'];maxgpu=cache_audit['peak_gpu_bytes']
 common=read(ROOT/'evaluation/dev/common_decisions.json');baseline={(r['policy'],r['episode_uid']):r for r in common if r['family']==request['family']}
 devindex={r['uid']:r for r in dev};comparisons=[]
 tato8_path=Path('results/v431/20260914-sprint')/('tato' if request['family']=='bolt' else 'timesfm_tato')/'predictions.npz'
 tato8=np.load(tato8_path,allow_pickle=False)
 # Only here, after frozen/deployment/archives/terminal status verified, open old DEV labels.
 with np.load(run/'predictions.npz',allow_pickle=False) as predictions,np.load(OLD/'targets.npz',allow_pickle=False) as targets:
  for item in deployment:
   u=item['uid'];row=devindex[u];m=meta[u];pos=indices[u];scale=float(batch.rows[pos]['outer_report_scale']);y=targets[u+'_values'];mask=targets[u+'_mask'].astype(bool)&np.isfinite(y)
   assert m['split']=='dev' and m['source']==request['source'] and m['horizon']==request['horizon'] and m['parent_group']==row['parent']
   assert m['condition']==request['condition'] and row['input_hash']==arrsha(inputs[u+'_context'])
   basic={'episode_uid':u,'source':m['source'],'parent_group':m['parent_group'],'raw_start':m['raw_start'],'horizon':m['horizon'],'condition':m['condition'],
      'target_hash':arrsha(y),'effective_mask_hash':arrsha(mask),'score_positions':int(mask.sum()),'outer_report_scale':scale}
   measured=None
   if item['status']=='completed':
    p=predictions[u];np.testing.assert_array_equal(p,np.load(run/('deploy-'+u+'.npy')))
    assert p.shape==y.shape==(request['horizon'],) and np.isfinite(p).all()
    assert item['prediction_hash']==arrsha(p) and item['prediction_sha256']==point_hash(p)
    assert item['input_sha256']==point_hash(inputs[u+'_context'].astype(np.float64))
    mae=float(np.mean(abs(p[mask]-y[mask])));mse=float(np.mean((p[mask]-y[mask])**2));measured=mae/scale
    assert abs(mae-item['mae'])<=1e-9*max(1,mae) and abs(mse-item['mse'])<=1e-9*max(1,mse)
   for bn,budget in BUDGETS.items():
    scene={**basic,'policy':'TATO_SCENE_'+bn,'family':request['family'],'mase':measured,'budget':budget,
           'status':item['status'],'total_seconds':item.get('hot_request_seconds'),'failure':item.get('error'),
           'original_context_length':512,'transformed_input_shape':item.get('model_input_shape'),'model_horizon':item.get('model_horizon'),
           'prediction_dtype':item.get('prediction_dtype'),'input_hash':row['input_hash'],'model_revision':model['revision']}
    result['rows'].append(scene)
    for base in BASELINES:
     key=(base+'_'+bn,u);assert key in baseline,('Missing same UID baseline',key)
     old=baseline[key];assert old['horizon']==basic['horizon'] and old['parent_group']==basic['parent_group']
     assert abs(float(old['report_scale'])-scale)<1e-12
     cached=(dataset['predictions'][pos][POOL.index(old['arm'])] if old['arm'] in POOL else tato8[u+'_TATO_NATIVE_SPACE'])
     assert cached.shape==y.shape
     old_mae=float(np.mean(np.abs(cached[mask]-y[mask])))
     assert abs(old_mae/scale-old['mase'])<=1e-9*max(1,abs(old['mase'])),'Inherited baseline target/mask mismatch'
     result['rows'].append({**basic,'policy':base+'_'+bn,'family':request['family'],'mase':old['mase'],
                          'budget':budget,'status':'inherited_completed','total_seconds':old['total_seconds'],
                          'information':old.get('information'),'original_row_origin':old.get('origin')})
     if measured is not None:comparisons.append({**basic,'comparison':'TATO_SCENE_'+bn+' minus '+base+'_'+bn,'mase_difference':measured-old['mase']})
 result.update(status='audited_'+status['status'],worker_status=status,frozen=frozen,model_identity=identity,
   train_prediction_scores_checked=trainchecks,raw_model_calls_checked=rawchecked,peak_gpu_bytes=maxgpu,train_native_cache_audit=cache_audit,
   trial_status_counts=dict(Counter(t['status'] for t in trials)),failures=[{'trial':t['trial'],'status':t['status'],'error':t.get('error'),'completed_train_samples':len(t['samples']),'wall_seconds':t['wall_seconds']} for t in trials if t['status']!='completed'],
   cost={'cold_seconds':status['cold_seconds'],'offline_search_seconds':status['search_seconds'],'sum_trial_wall_seconds':sum(t['wall_seconds'] for t in trials),
         'deployment_hot_seconds':sum(r.get('hot_request_seconds',0) for r in deployment),'worker_wall_seconds':status['wall_seconds'],
         'raw_model_seconds':sum(c.get('native_compute_seconds',c.get('seconds',0)) for c in calls if c.get('native_compute_seconds',c.get('seconds',0)) is not None),
         'native_compute_unknown_failed_attempts':sum(c.get('status')=='failed' and c.get('native_compute_seconds') is None for c in calls),
         'actual_model_calls':sum(not c['cache_hit'] and c.get('status')!='failed' for c in calls),
         'cache_hits':sum(c['cache_hit'] for c in calls),'maximum_actual_trial_shape':None,
         'call_count_scope':'successfully recorded native forecasts; failed branch elapsed remains included in trial/search wall'},
   pairwise_successful_uid_diagnostics={name:blocked_bootstrap([r for r in comparisons if r['comparison']==name],'mase_difference') for name in sorted({r['comparison'] for r in comparisons})},
   hashes={str(run/p):sha(run/p) for p in required},
   limitations=[request['source']+' target_block_10 only; old DEV subset, not independent confirmation',
    str(len(train))+' rather than 500 independent TRAIN instances; L512 rather than official L1440',
    'Original native transformations may modify valid inputs; distinct native baseline information and action space',
    'Search may be deadline-partial; no missing windows removed or failure zero-filled',
    'Worker-stage timer excludes pre-execute imports/hash checks; primary full OS process not separately measured'])
 result['cost']['worker_stage_wall_seconds']=result['cost'].pop('worker_wall_seconds')
 result['cost'].update(complete_subprocess_wall_seconds=None,pre_worker_import_seconds=None,
   timer_scope='worker-stage timer starts after imports and initial hash checks; not full OS process')
 if directory.parent.name in ('tato-scene-extra','tato-scene-extra-cached'):
  q=ROOT/'tato-scene-extra/queue.execution.json'
  if q.exists():
   job=next((j for j in read(q).get('jobs',[]) if j.get('scene')==directory.name),None)
   if job and 'wall_seconds' in job:
    if job.get('wall_scope')=='full child process after queue lock; queue wait separately recorded':
     result['cost']['complete_subprocess_wall_seconds']=job['wall_seconds']
     result['cost']['queue_wait_seconds']=job.get('queue_wait_seconds')
     result['cost']['outer_job_scope']=job['wall_scope']
    else:
     result['cost']['outer_job_wall_including_queue_seconds']=job['wall_seconds']
     result['cost']['outer_job_scope']='legacy v1 timer starts before mutex acquisition; includes waiting, not isolated child process'
  result['cost'].setdefault('outer_job_scope','not measured yet; resolve v1/v2 from recorded wall_scope')
 if directory.parent.name=='tato-official96':
  q=ROOT/'official96-queue-status.json'
  if q.exists():
   job=next((j for j in read(q).get('jobs',[]) if j.get('name')==directory.name),None)
   if job and 'seconds' in job:result['cost']['complete_subprocess_wall_seconds']=job['seconds']
  result['cost']['outer_job_scope']='remaining_jobs timer starts after mutex acquisition and covers subprocess launch/wait'
 groups={p:[r for r in result['rows'] if r['policy']==p] for p in sorted({r['policy'] for r in result['rows']})}
 result['table']=[{'policy':p,**summary(rr)} for p,rr in groups.items()]
 inputs.close();tato8.close();return result


def combined_registered_matrix(directories,scene_results):
 common=read(ROOT/'evaluation/dev/common_decisions.json')
 baseline={(r['family'],r['policy'],r['episode_uid']):r for r in common}
 known={r['scene']:r for r in scene_results};rows=[]
 for directory in directories:
  request=read(scene_request_path(directory));scene=known[directory.name]
  verified={(r['policy'],r['episode_uid']):r for r in scene.get('rows',[])}
  for record in request['rows']:
   if record['role']!='dev':continue
   uid=record['uid']
   for bn,budget in BUDGETS.items():
    for method in (*BASELINES,'TATO_SCENE'):
     policy=method+'_'+bn
     if (policy,uid) in verified:r=dict(verified[policy,uid])
     elif method!='TATO_SCENE':
      old=baseline[request['family'],policy,uid]
      r={k:old[k] for k in ('family','policy','episode_uid','source','parent_group','raw_start','horizon','condition','mase','total_seconds','budget')}
      r['status']='inherited_old_DEV_score_not_new_scene_evaluation'
     else:
      r=dict(family=request['family'],policy=policy,episode_uid=uid,source=request['source'],
       parent_group=record['parent'],raw_start=record['raw_start'],horizon=request['horizon'],condition=request['condition'],
       mase=None,total_seconds=None,budget=budget,status=scene['status'])
     r['scene']=directory.name;rows.append(r)
 groups={}
 for r in rows:
  key=r['family'],r['policy'];groups.setdefault(key,[]).append(r)
 tables=[]
 for (family,policy),rr in sorted(groups.items()):
  assert len({r['episode_uid'] for r in rr})==len(rr),'Duplicate registered scene UID'
  tables.append({'family':family,'policy':policy,**summary(rr)})
 return {'scope':'all preregistered three-source target_block_10 H96/H192 UIDs; not original156',
  'registered_scenes':len(directories),'rows':rows,'table':tables,
  'missing_scene_results':[r['scene'] for r in scene_results if not r['status'].startswith('audited_')],
  'warning':'Inherited baseline scores were already evaluated previously. Missing new scene predictions remain null in full denominator; no new DEV target is read for pending scenes.'}

def report_markdown(report):
 lines=['# TATO TRAIN场景搜索：真实子集结果与审核','',
 '本表限预登记 target_block_10、H96/H192。ETTm1每场景29 fit/14 DEV parent；Solar22/11；USTS3/1。三来源合并每家族26 parent/52相关变体，与原156变体不同，所有对照按相同UID重算。未执行场景保留缺项。原生场景搜索不受五臂约束；使用冻结骨干、相同当前目标和原始评价mask。不是官方完整复现，不是新的确认集，不改原r5共同主表。','',
 '|场景|状态|成功/实际/登记trial|DEV成功/登记|TRAIN选择核验|', '|---|---|---|---|---|']
 for scene in report['scenes']:
  st=scene['status']
  if st.startswith('audited_'):v=scene['worker_status'];counts=f"{v['completed_trials']}/{v['trials']}/{scene['requested_trials']}";dev=f"{v['deploy_completed']}/{scene['dev_parents']}";checked=str(scene['train_prediction_scores_checked'])
  else:counts='未完成';dev='未评分';checked='待验证'
  lines.append(f"|{scene['scene']}|{st}|{counts}|{dev}|{checked}|")
 lines += ['', '## 全部预登记来源共同子表', '', '|家族|方法|完整窗/parent|已预测窗|完整分母MASE|成功子集MASE（诊断）|', '|---|---|---|---|---:|---:|']
 for row in report['combined']['table']:
  val=lambda k:'缺项' if row[k] is None else f"{row[k]:.6f}"
  lines.append(f"|{row['family']}|{row['policy']}|{row['episodes']}/{row['parents']}|{row['successful_episodes']}|{val('mase_full_denominator')}|{val('mase_success_subset_only')}|")
 primary_names={'bolt-h96','bolt-h192','timesfm-h96','timesfm-h192'}
 primary_complete={s['scene'] for s in report['scenes'] if s['scene'] in primary_names and s['status'].startswith('audited_')}
 if primary_complete==primary_names:
  lines += ['', '## 首四ETTm1共同子表', '', '每家族14 parent、28个target_block_10变体；仅ETTm1，不代替三来源52变体完整表。以下为high预算同UID比较，完整原生方法的信息与搜索协议不同。', '', '|家族|方法|MASE|完整窗/parent|费用秒/窗|超支|', '|---|---|---:|---|---:|---:|']
  primary_rows=[x for x in report['combined']['rows'] if x['scene'] in primary_names and x['policy'].endswith('_high')]
  for family in ('bolt','timesfm'):
   for policy in sorted({x['policy'] for x in primary_rows}):
    t=summary([x for x in primary_rows if x['family']==family and x['policy']==policy])
    val='缺项' if t['mase_full_denominator'] is None else f"{t['mase_full_denominator']:.6f}"
    cost='未知' if t['seconds_macro_available_records'] is None else f"{t['seconds_macro_available_records']:.6f}"
    lines.append(f"|{family}|{policy}|{val}|{t['episodes']}/{t['parents']}|{cost}|{t['budget_overruns']}|")
 for scene in report['scenes']:
  if not scene['status'].startswith('audited_'):continue
  lines += ['', '## '+scene['scene'],'', '|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|', '|---|---:|---:|---:|---:|---:|']
  for row in scene['table']:
   val=lambda k:'未完整' if row[k] is None else f"{row[k]:.6f}"
   lines.append(f"|{row['policy']}|{val('mase_full_denominator')}|{val('mase_success_subset_only')}|{val('seconds_macro_available_records')}|{row['failed_or_not_run_episodes']}|{row['budget_overruns']}|")
  c=scene['cost'];lines += ['',f"模型冷启动 {c['cold_seconds']:.3f} 秒；离线搜索 {c['offline_search_seconds']:.3f} 秒；DEV部署热请求累计 {c['deployment_hot_seconds']:.3f} 秒；worker阶段 {c['worker_stage_wall_seconds']:.3f} 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。",'',
   '失败trial状态：'+json.dumps(scene['trial_status_counts'],ensure_ascii=False)+'。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。']
 lines += ['', '## 官方96单位独立实验', '', '以下采用官方patch/data/model单位96，seq_l=5..15原样保留。L512下大部分长度不支持，失败原样记录。与scaled-unit场景实验分别报告，不把两种协议混称官方完整复现。', '', '|scene|状态|成功/实际/登记trial|新scene MASE（high）|完整子进程秒|', '|---|---|---|---:|---:|']
 for sc in report.get('official96_scenes',[]):
  if sc['status'].startswith('audited_'):
   st=sc['worker_status'];t=next(r for r in sc['table'] if r['policy']=='TATO_SCENE_high');v=t['mase_full_denominator'];v='缺项' if v is None else f"{v:.6f}";wall=sc['cost']['complete_subprocess_wall_seconds'];wall='未单独测量' if wall is None else f"{wall:.3f}";counts=f"{st['completed_trials']}/{st['trials']}/{sc['requested_trials']}"
  else:v='未评分';wall='未完成';counts='未完成'
  lines.append(f"|{sc['scene']}|{sc['status']}|{counts}|{v}|{wall}|")
  if sc['status'].startswith('audited_'):
   lines += ['', '|官方96同UID方法|MASE完整分母|部署费用秒/窗|超预算|','|---|---:|---:|---:|']
   for t in sc['table']:
    v=t['mase_full_denominator'];v='缺项' if v is None else f"{v:.6f}";c=t['seconds_macro_available_records'];c='未完成' if c is None else f"{c:.6f}"
    lines.append(f"|{t['policy']}|{v}|{c}|{t['budget_overruns']}|")
 lines += ['', '计时口径：首四scene的status.wall_seconds只涵盖worker阶段，前置import及部分hash检查未单独计时，不能称完整OS进程。extra v1队列wall_seconds从等mutex前开始，包含排队；v2由wall_scope明确标注锁后完整子进程时间，并单列queue_wait_seconds，按实际记录区分。official96的remaining_jobs job.seconds在锁后计时，才可作为完整子进程墙钟。未记录的开销保持未知，不补造0。', '', '冻结选择只从完成的TRAIN trial按宏平均MSE取最小值，平局取最早trial；独立重算每个已保存TRAIN样本与最终DEV预测。只有冻结文件、完整部署manifest、最终预测归档及worker终态均存在才读取旧DEV目标。不存在的结果保持待运行；部分结果不填零，也不偷偷缩小完整表分母。', '',
 '## TRAIN角色与时间输入代码审核', '',
 '首批 prepare 和额外 prepare_extra 都先从已冻结免费参考的 training_parents 取T_fit父组，再按 source/H/target_block_10 选取独立parent。准备包只含全部请求的512点脏context，以及TRAIN请求的target/mask；DEV没有目标数组。独立审计检查包键集合严格相等，不允许额外标签或特征数组。各TRAIN请求完整context+H读取在原TRAIN边界内。', '',
 '实际 forecast(row, params) 只把该row的context、H、当前trial参数交给 execute_frozen_scene；预测完成后才取TRAIN目标计算MSE/MAE，并向Optuna反馈。不存在把早期TRAIN origin之后的值追加到模型输入或作为归一化数据的接口。TRAIN标签影响离线搜索参数是有监督拟合，不是无偏训练性能，也不能作为该早期origin部署时已有的证据。最终DEV部署只使用冻结参数与该DEV context，不把TRAIN/DEV目标传入预测函数。该结论基于具体输入键、调用链与保存的模型输入，不声称通用形式化信息流证明。', '',
 '额外resolved request仅允许登记运行时上限因剩余时间缩短；source、field、H、condition、UID、trial数与TRAIN监督角色必须与preregistered文件完全一致。缓存修订使用独立worker并绑定cache_amendment：原request/worker与新worker/module SHA分别保留，只替代尚未执行extra，不双计16个scene。原输入、参数、500trial与600秒上限保持不变。每次TRAIN缓存命中校验相同parent、checkpoint、native config、dtype、实际输入及H、首次raw文件/point/hash与首次真实费用；lookup+copy另收费，部署每请求清缓存。USTS仅3个TRAIN parent和1个DEV parent，其支持局限必须保留。']
 return '\n'.join(lines)+'\n'

def main():
 p=argparse.ArgumentParser();p.add_argument('--scene');p.add_argument('--skip-raw',action='store_true');a=p.parse_args()
 primary=sorted(set(p.parent for p in SCENES.glob('*/request*.json')))
 original_extra=sorted(set(p.parent for p in (ROOT/'tato-scene-extra').glob('*/request*.json')))
 cached_extra=sorted(set(p.parent for p in (ROOT/'tato-scene-extra-cached').glob('*/request*.json')))
 cached_names={p.name for p in cached_extra}
 superseded=[dict(scene=p.name,path=str(p),status='superseded_before_execution') for p in original_extra if p.name in cached_names]
 for old in superseded:assert not (Path(old['path'])/'run').exists(),'Cannot supersede an already executed extra scene'
 directories=primary+[p for p in original_extra if p.name not in cached_names]+cached_extra
 official=sorted(set(p.parent for p in (ROOT/'tato-official96').glob('*/request*.json')))
 if a.scene:
  directories=[d for d in directories if d.name==a.scene];official=[d for d in official if d.name==a.scene]
 assert directories or official
 results=[];official_results=[]
 for d in directories+official:
  try:row=audit_scene(d,strict_raw=not a.skip_raw)
  except Exception as exc:row={'scene':d.name,'status':'audit_failed','error':repr(exc)}
  (official_results if d in official else results).append(row)
 report={'status':'independent_scene_audit','script_sha256':sha(__file__),'old_dev_only':True,'no_calibration_test_read':True,'scenes':results,'superseded_requests':superseded,'official96_scenes':official_results,'combined':combined_registered_matrix(directories,results)}
 write(SCENES/'audit.json',report);Path('docs/v431_r5_tato_scene_results.md').write_text(report_markdown(report))
 print(json.dumps({'scaled':{r['scene']:r['status'] for r in results},'official96':{r['scene']:r['status'] for r in official_results}}))
 if any(r['status']=='audit_failed' for r in results+official_results):raise SystemExit(1)

if __name__=='__main__':main()
