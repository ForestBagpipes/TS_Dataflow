#!/usr/bin/env python3
"""Same-parent TRAIN cached TATO; unchanged search and isolated deployment.
One worker owns gpu.lock; parent queue must use a different mutex.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'results/v43/20260914T141030.324186Z-agent'
sys.path.insert(0,str(ROOT/'scripts/v431_baselines'))
sys.path.insert(0,str(ROOT/'scripts'))

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def atom(p,x):
 p=Path(p);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n');q.replace(p)
def arrsha(x):
 x=np.ascontiguousarray(x);return hashlib.sha256(x.dtype.str.encode()+str(x.shape).encode()+x.tobytes()).hexdigest()

def prepare(args):
 import joblib
 out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 frozen=ROOT/'results/v431-r5/fit/models_frozen.json';f=json.loads(frozen.read_text());mp=frozen.with_name('models.joblib')
 assert sha(mp)==f['sha256']
 refs=joblib.load(mp)['families'];parent_sets=[set(v['reference'].training_parents) for v in refs.values()]
 assert all(s==parent_sets[0] for s in parent_sets),'Different family TRAIN support'
 meta=json.loads((OLD/'episode_manifest.json').read_text());bounds=json.loads((OLD/'data_manifest.json').read_text())
 train_bounds=next(r['split_bounds']['train'] for r in bounds if r['source']=='ETTm1')
 train=[u for u,m in meta.items() if m['split']=='train' and m['source']=='ETTm1' and m['parent_group'] in parent_sets[0] and m['condition']=='target_block_10' and m['horizon']==args.horizon]
 dev=[u for u,m in meta.items() if m['split']=='dev' and m['source']=='ETTm1' and m['condition']=='target_block_10' and m['horizon']==args.horizon]
 train=sorted(train,key=lambda u:meta[u]['raw_start'])[:500];dev=sorted(dev,key=lambda u:meta[u]['raw_start'])
 assert len(train)==len({meta[u]['parent_group'] for u in train}) and train and dev
 arrays={};rows=[]
 with np.load(OLD/'contexts.npz',allow_pickle=False) as x,np.load(OLD/'targets.npz',allow_pickle=False) as y:
  for role,ids in [('train',train),('dev',dev)]:
   for u in ids:
    m=meta[u];a=x[u+'_target'];assert a.shape==(512,)
    row=dict(uid=u,role=role,parent=m['parent_group'],source='ETTm1',horizon=args.horizon,raw_start=m['raw_start'],origin=m['context_end'],input_hash=arrsha(a))
    arrays[u+'_context']=a.copy()
    if role=='train':
     assert train_bounds[0]<=m['raw_start'] and m['context_end']+args.horizon<=train_bounds[1]
     target=y[u+'_values'];mask=y[u+'_mask'];assert target.shape==(args.horizon,)
     arrays[u+'_target']=target;arrays[u+'_mask']=mask
     row.update(train_bounds=train_bounds,target_hash=arrsha(target),mask_hash=arrsha(mask))
    rows.append(row)
 np.savez(out/'inputs.npz',**arrays)
 request=dict(status='prepared_not_run',family=args.family,horizon=args.horizon,source='ETTm1',target_channel=0,target_field='HUFL',condition='target_block_10',context=512,
  train_parents=len(train),dev_parents=len(dev),rows=rows,trials=min(500,args.trials),max_seconds=args.max_seconds,pilot_requests=min(20,len(train)),
  inputs=str(out/'inputs.npz'),inputs_sha256=sha(out/'inputs.npz'),output=str(out),seed=101,
  worker_sha256=sha(__file__),adapter_sha256=sha(ROOT/'scripts/v431_r5_prepare_main.py'),reference_frozen_sha256=sha(frozen),
  supervision='r5 T_fit parents only; no gate/check/acq/calibration/test',
  protocol='native TATO scene-level TRAIN mean MSE, L512; not official L1440/top16/Pareto full reproduction',
  budgets=[.8140623268639832,3.5],heldout_labels_read=0)
 atom(out/'request.json',request);print(json.dumps(dict(request=str(out/'request.json'),train=len(train),dev=len(dev))))

@contextmanager
def gpu_lock():
 with (ROOT/'locks/gpu.lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  yield

class Deadline(Exception):pass

def execute(request,pilot_only):
 from v431_r5_prepare_main import execute_frozen_scene
 import tato_adapter as adapter
 import optuna
 import worker as baseline
 from v431_r5_tato_parent_cache import ParentScopedForecast
 import torch
 r=json.loads(Path(request).read_text());assert sha(__file__)==r['worker_sha256'];assert sha(ROOT/'scripts/v431_r5_prepare_main.py')==r['adapter_sha256'];assert sha(r['inputs'])==r['inputs_sha256'];assert sha(ROOT/'scripts/v431_r5_tato_parent_cache.py')==r['cache_module_sha256']
 out=Path(r['output'])/('pilot' if pilot_only else 'run');out.mkdir(exist_ok=False);(out/'raw').mkdir()
 begin=time.perf_counter();deadline=begin+r['max_seconds'];search_deadline=deadline-60
 atom(out/'status.json',dict(status='running',pid=os.getpid(),start_utc=datetime.now(timezone.utc).isoformat(),request=str(request),pilot_only=pilot_only))
 rows=r['rows'];training=[x for x in rows if x['role']=='train'];dev=[x for x in rows if x['role']=='dev']
 with np.load(r['inputs'],allow_pickle=False) as f:inputs={k:f[k].copy() for k in f.files}
 for row in rows:assert arrsha(inputs[row['uid']+'_context'])==row['input_hash']
 complete=[];trials=[];deployment=[];predictions={};timing=[]
 with gpu_lock():
  load_start=time.perf_counter();model=(baseline.Bolt if r['family']=='bolt' else baseline.TimesFM)(out);cold=time.perf_counter()-load_start
  native_settings=vars(model.model.forecast_config) if hasattr(model.model,'forecast_config') else model.model.model.config.to_dict()
  model=ParentScopedForecast(model,dict(native_settings=native_settings,native_backend_sha256=sha(ROOT/'scripts/v431_baselines/worker.py'),family=r['family'],input_cast='native backend fixed float32',model_dtype='bfloat16' if r['family']=='bolt' else 'float32',point='native selected point; config bound by backend source hash and checkpoint identity'))
  identity=adapter.official_identity();factory,tuner_factory=adapter.load_official()
  atom(out/'model_identity.json',dict(backbone=model.identity,TATO=identity,cold_seconds=cold))
  def forecast(row,params):
   if time.perf_counter()>=deadline:raise Deadline('overall deadline before next model call')
   model.set_scope(row['parent'],row['role'],row['uid'])
   return execute_frozen_scene(model,inputs[row['uid']+'_context'],row['horizon'],params,r['family'])
  if pilot_only:
   for row in training[:r['pilot_requests']]:
    tick=time.perf_counter()
    try:
     p,detail=forecast(row,adapter.vanilla());item=dict(uid=row['uid'],status='completed',**detail,prediction_hash=arrsha(p))
    except (ValueError,AssertionError,FloatingPointError,Deadline) as exc:item=dict(uid=row['uid'],status='failed',error=repr(exc))
    item['wall_seconds']=time.perf_counter()-tick;timing.append(item)
    atom(out/'timing.json',timing)
    if time.perf_counter()>=deadline:break
   atom(out/'calls.json',model.calls)
   atom(out/'status.json',dict(status='completed' if len(timing)==r['pilot_requests'] else 'partial',scope='TRAIN throughput only; no losses computed',requests=len(timing),failures=sum(x['status']!='completed' for x in timing),cold_seconds=cold,wall_seconds=time.perf_counter()-begin,peak_gpu_bytes=torch.cuda.max_memory_allocated(),heldout_labels_read=0));return
  tuner=tuner_factory.build_optuna_tuner(enqueue_param_dicts=[adapter.vanilla()],mode='train',seed=101)
  distribution=tuner_factory.build_search_space(adapter.NAMES,patch_len=16 if r['family']=='bolt' else 32)
  search_begin=time.perf_counter()
  for n in range(r['trials']):
   if time.perf_counter()>=search_deadline:break
   trial=tuner.pick_trial(distribution);entry=dict(trial=n,params=dict(trial.params),samples=[]);tick=time.perf_counter();train_predictions={}
   try:
    errors=[]
    for row in training:
     if time.perf_counter()>=search_deadline:raise Deadline('search deadline; leave 60s for frozen deployment')
     p,detail=forecast(row,trial.params);u=row['uid'];y=inputs[u+'_target'];mask=np.asarray(inputs[u+'_mask'],bool)&np.isfinite(y)
     if not mask.any():raise ValueError('No TRAIN scoring support')
     train_predictions[u]=p.copy();mse=float(np.mean((p[mask]-y[mask])**2));mae=float(np.mean(np.abs(p[mask]-y[mask])));errors.append(mse)
     entry['samples'].append(dict(uid=u,train_mse=mse,train_mae=mae,**detail,prediction_hash=arrsha(p)))
    score=float(np.mean(errors));tuner.tell(trial,score);entry.update(status='completed',train_macro_mse=score);complete.append(entry)
   except (ValueError,AssertionError,FloatingPointError,Deadline) as exc:
    tuner.study.tell(trial,state=optuna.trial.TrialState.FAIL);entry.update(status='partial' if isinstance(exc,Deadline) else 'failed',error=repr(exc))
   np.savez(out/f'train_predictions_{n:04d}.npz',**train_predictions)
   entry['wall_seconds']=time.perf_counter()-tick;trials.append(entry);atom(out/'trials.json',trials);atom(out/'calls.json',model.calls)
   atom(out/'status.json',dict(status='searching',trial_count=len(trials),completed_trials=len(complete),elapsed=time.perf_counter()-begin,heldout_labels_read=0))
   if entry['status']=='partial':break
  search_seconds=time.perf_counter()-search_begin
  if not complete:
   atom(out/'status.json',dict(status='failed',reason='No completed TRAIN trial; no fallback forecast',trials=len(trials),wall_seconds=time.perf_counter()-begin,heldout_labels_read=0));return
  best=min(complete,key=lambda x:(x['train_macro_mse'],x['trial']))
  frozen=dict(status='frozen_from_TRAIN',params=best['params'],trial=best['trial'],train_macro_mse=best['train_macro_mse'],completed_trials=len(complete),requested_trials=r['trials'],actual_trials=len(trials),search_seconds=search_seconds,
   full_search_completed=len(trials)==r['trials'] and not any(x['status']=='partial' for x in trials),request_sha256=sha(request),model_identity=model.identity,protocol=r['protocol'])
  atom(out/'frozen_scene.json',frozen)
  for row in dev:
   if time.perf_counter()>=deadline:
    deployment.append(dict(uid=row['uid'],status='not_run_deadline'));continue
   tick=time.perf_counter()
   try:
    p,detail=forecast(row,best['params']);predictions[row['uid']]=p.copy();np.save(out/('deploy-'+row['uid']+'.npy'),p);item=dict(uid=row['uid'],status='completed',**detail,prediction_hash=arrsha(p),prediction_dtype=str(p.dtype))
   except (ValueError,AssertionError,FloatingPointError,Deadline) as exc:item=dict(uid=row['uid'],status='failed',error=repr(exc))
   item['hot_request_seconds']=time.perf_counter()-tick;item['budget_overruns']={str(b):item['hot_request_seconds']>b for b in r['budgets']};deployment.append(item);atom(out/'deployment.json',deployment)
  np.savez(out/'predictions.npz',**predictions);atom(out/'deployment.json',deployment);atom(out/'calls.json',model.calls)
 # Only after every final DEV prediction is saved can evaluator read its target.
 with np.load(OLD/'targets.npz',allow_pickle=False) as f:
  for item in deployment:
   if item['status']!='completed':continue
   u=item['uid'];y=f[u+'_values'];mask=np.asarray(f[u+'_mask'],bool)&np.isfinite(y);p=predictions[u]
   item.update(mae=float(np.mean(np.abs(p[mask]-y[mask]))),mse=float(np.mean((p[mask]-y[mask])**2)),scored_positions=int(mask.sum()))
 atom(out/'deployment.json',deployment)
 atom(out/'status.json',dict(status='completed' if frozen['full_search_completed'] and all(d['status']=='completed' for d in deployment) else 'partial',
  scope='same-backbone TRAIN scene adaptation; not official full reproduction',trials=len(trials),completed_trials=len(complete),failed_trials=sum(t['status']=='failed' for t in trials),
  train_parents=len(training),dev_parents=len(dev),deploy_completed=len(predictions),cold_seconds=cold,search_seconds=search_seconds,wall_seconds=time.perf_counter()-begin,heldout_labels_read=0,old_dev_labels_evaluated_after_freeze=True))

def main():
 p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--family',choices=['bolt','timesfm']);p.add_argument('--horizon',type=int,choices=[96,192]);p.add_argument('--trials',type=int,default=500);p.add_argument('--max-seconds',type=float,default=900);p.add_argument('--request');p.add_argument('--pilot-only',action='store_true');a=p.parse_args()
 if a.prepare:
  if not a.output or not a.family or not a.horizon:p.error('prepare requires output,family,horizon')
  prepare(a)
 elif a.request:execute(a.request,a.pilot_only)
 else:p.error('choose prepare or request')
if __name__=='__main__':main()
