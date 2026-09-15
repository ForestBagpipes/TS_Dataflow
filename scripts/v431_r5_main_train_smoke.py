#!/usr/bin/env python3
"""TRAIN-only native KEEP interface preparation; no future labels or loss."""
import argparse,fcntl,hashlib,json,os,sys,time,itertools
from datetime import datetime
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/v431-r5/main-train-smoke';CONFIG=ROOT/'configs/v431-r5/main_train_smoke.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for v in iter(lambda:f.read(1048576),b''):h.update(v)
 return h.hexdigest()
def arrsha(a):
 a=np.ascontiguousarray(a);return hashlib.sha256(a.dtype.str.encode()+str(a.shape).encode()+a.tobytes()).hexdigest()
def write(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix('.tmp');q.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n');q.replace(p)
def prepare():
 from v431_r5_main_audit import source_rows
 protocol_path=ROOT/'configs/v431-r5/main_protocol_v2.json';protocol=json.loads(protocol_path.read_text())
 audit_path=ROOT/'results/v431-r5/main-preparation/audit-v2/timestamp_audit.json';audit=json.loads(audit_path.read_text())
 bad={r['parent'] for r in audit['affected_parent_windows']};time_info={r['source']:r for r in audit['sources']}
 OUT.mkdir(exist_ok=False);arrays={};rows=[];selected=[]
 for info in protocol['sources']:
  choices=sorted([w for w in protocol['windows_metadata'] if w['source']==info['source'] and w['role']=='train' and w['parent'] not in bad],key=lambda w:w['read_start'])
  if not choices:selected.append(dict(source=info['source'],status='unsupported_no_legal_train_parent'));continue
  w=choices[0];lo,hi=info['split_bounds']['train'];assert lo<=w['read_start'] and w['origin']+192<=hi
  assert sha(ROOT/info['path'])==info['file_sha256']
  values=[]
  for idx,cells in itertools.islice(source_rows(ROOT/info['path']),w['origin']):
   if idx>=w['read_start']:values.append([float(c) if c.strip() else np.nan for c in cells])
  values=np.asarray(values);assert values.shape==(512,info['columns']) and not np.isinf(values).any()
  raw=values[:,0].copy();selected.append(dict(source=info['source'],parent=w['parent'],role='train',numeric_read=[w['read_start'],w['origin']],forecast_labels_read=0,time_status=time_info[info['source']]['status'],legacy_exposure=w['legacy_exposure']))
  for condition in ('raw','target_block_10'):
   x=raw.copy()
   if condition!='raw':x[230:281]=np.nan
   observed=np.isfinite(raw)&np.isfinite(x);assert np.array_equal(x[observed],raw[observed])
   for h in (96,192):
    uid=f"{info['source']}-{condition}-h{h}";arrays[uid]=x.copy()
    rows.append(dict(uid=uid,source=info['source'],parent=w['parent'],role='train',target_channel=0,target_field=info['target'],condition=condition,L=512,H=h,
     read_start=w['read_start'],origin=w['origin'],input_hash=arrsha(x),target_mask_hash=arrsha(np.isfinite(x)),auxiliary_hash=arrsha(values[:,1:]),
     raw_target_hash=arrsha(raw),raw_complete=bool(np.isfinite(raw).all()),missing_count=int(np.isnan(x).sum()),time_status=time_info[info['source']]['status'],data_sha256=info['file_sha256']))
 np.savez(OUT/'inputs.npz',**arrays)
 config=dict(status='prepared_no_forecast',purpose='TRAIN native KEEP input/model interface only; not r5 promotion or independent confirmation',
  protocol_sha256=sha(protocol_path),timestamp_audit_sha256=sha(audit_path),worker_sha256=sha(__file__),native_backend_sha256=sha(ROOT/'scripts/v431_baselines/worker.py'),
  inputs=str(OUT/'inputs.npz'),inputs_sha256=sha(OUT/'inputs.npz'),rows=rows,selected=selected,per_family_requests=len(rows),
  families=['bolt','timesfm'],seed=101,heldout_labels_read=0,forecast_target_labels_read=0,numerical_scope='only selected TRAIN input rows',
  missing_semantics={'bolt':'native ChronosBolt NaN path; unchanged input passed directly','timesfm':'official context-only interpolation and leading-NaN stripping; all-missing explicitly rejected'},
  all_sources_original_clock_verified=False,ordinal_clock_note='Electricity/Exchange/Traffic have no original clock; interface check only, no strict point-in-time claim')
 write(CONFIG,config);write(OUT/'prepare_status.json',config);print(json.dumps(dict(status='prepared',sources=len(selected),requests_per_family=len(rows),labels_read=0)))
def run(family,deadline):
 sys.path.insert(0,str(ROOT/'scripts/v431_baselines'))
 import worker as backend
 config=json.loads(CONFIG.read_text());assert sha(__file__)==config['worker_sha256'];assert sha(ROOT/'scripts/v431_baselines/worker.py')==config['native_backend_sha256'];assert sha(config['inputs'])==config['inputs_sha256']
 dest=OUT/family;dest.mkdir(exist_ok=False);(dest/'raw').mkdir();records=[];outputs={};begin=time.perf_counter();end=datetime.fromisoformat(deadline).timestamp()
 # Input file contains contexts only. This worker has no evaluation reader.
 with np.load(config['inputs'],allow_pickle=False) as f:inputs={k:f[k].copy() for k in f.files}
 if time.time()>=end:write(dest/'status.json',dict(status='not_run_deadline'));return
 with (ROOT/'locks/gpu.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if time.time()>=end:write(dest/'status.json',dict(status='not_run_deadline_after_lock'));return
  import torch
  torch.set_num_threads(1);torch.manual_seed(101);np.random.seed(101)
  tick=time.perf_counter();model=(backend.Bolt if family=='bolt' else backend.TimesFM)(dest);torch.cuda.synchronize();cold=time.perf_counter()-tick
  write(dest/'model_identity.json',dict(model=model.identity,native_backend_sha256=config['native_backend_sha256'],cold_seconds=cold,missing_semantics=config['missing_semantics'][family]))
  for row in config['rows']:
   if time.time()>=end:records.append(dict(row,status='not_run_deadline'));continue
   torch.cuda.synchronize();tick=time.perf_counter()
   x=inputs[row['uid']];assert arrsha(x)==row['input_hash'];before=x.copy();model.cache.clear()
   try:
    if not np.isfinite(x).any():raise ValueError('all-missing native input unsupported; no zero replacement')
    pred=model.forecast(x[None,:,None],row['H'])[0,:,0]
    assert pred.shape==(row['H'],) and np.isfinite(pred).all();assert np.array_equal(x,before,equal_nan=True)
    outputs[row['uid']]=pred.copy();np.save(dest/(row['uid']+'.npy'),pred)
    response=dict(row,status='completed',prediction_hash=arrsha(pred),prediction_dtype=str(pred.dtype),native_NaN_input_preserved=True)
    torch.cuda.synchronize();response['hot_request_seconds']=time.perf_counter()-tick;records.append(response)
   except Exception as e:records.append(dict(row,status='failed',error=repr(e),incurred_seconds=time.perf_counter()-tick))
   write(dest/'records.json',records);write(dest/'calls.json',model.calls)
  np.savez(dest/'predictions.npz',**outputs)
 write(dest/'records.json',records);write(dest/'status.json',dict(status='completed' if len(outputs)==len(config['rows']) else 'partial',family=family,completed=len(outputs),requests=len(config['rows']),failures=sum(r['status']=='failed' for r in records),cold_seconds=cold,wall_seconds=time.perf_counter()-begin,forecast_target_labels_read=0,heldout_labels_read=0,loss_computed=False,deadline=deadline))
 print(json.dumps(json.loads((dest/'status.json').read_text())))
def main():
 p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--family',choices=['bolt','timesfm']);p.add_argument('--deadline',default='2026-09-16T04:45:00+08:00');a=p.parse_args()
 if a.prepare:prepare()
 elif a.family:run(a.family,a.deadline)
 else:p.error('choose --prepare or --family')
if __name__=='__main__':main()
