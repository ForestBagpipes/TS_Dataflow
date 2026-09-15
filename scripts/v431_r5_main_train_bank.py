#!/usr/bin/env python3
"""TRAIN-only Native KEEP bank; future labels never parsed or scored."""
import argparse,datetime,itertools,json,sys
from pathlib import Path
import numpy as np
import v431_r5_main_train_smoke as smoke
from v431_r5_main_audit import source_rows
ROOT=smoke.ROOT;OUT=ROOT/'results/v431-r5/main-train-bank';CONFIG=ROOT/'configs/v431-r5/main_train_bank.json'
def prepare():
 protocol_path=ROOT/'configs/v431-r5/main_protocol_v2.json';protocol=json.loads(protocol_path.read_text())
 audit_path=ROOT/'results/v431-r5/main-preparation/audit-v2/timestamp_audit.json';audit=json.loads(audit_path.read_text());bad={x['parent'] for x in audit['affected_parent_windows']};times={x['source']:x['status'] for x in audit['sources']}
 OUT.mkdir(exist_ok=False);arrays={};rows=[];selected=[];support={}
 for info in protocol['sources']:
  windows=sorted([x for x in protocol['windows_metadata'] if x['source']==info['source'] and x['role']=='train' and x['parent'] not in bad],key=lambda x:x['read_start']);support[info['source']]=len(windows)
  assert smoke.sha(ROOT/info['path'])==info['file_sha256']
  if not windows:continue
  for a,b in zip(windows,windows[1:]):assert a['origin']<=b['read_start']
  lo,hi=info['split_bounds']['train'];wi=0;values=[]
  for idx,cells in itertools.islice(source_rows(ROOT/info['path']),max(x['origin'] for x in windows)):
   w=windows[wi]
   if idx<w['read_start']:continue
   assert w['read_start']<=idx<w['origin'];values.append([float(c) if c.strip() else np.nan for c in cells])
   if idx+1!=w['origin']:continue
   assert lo<=w['read_start'] and w['origin']+192<=hi
   v=np.asarray(values);assert v.shape==(512,info['columns']) and not np.isinf(v).any();raw=v[:,0].copy()
   selected.append(dict(source=info['source'],parent=w['parent'],role='train',numeric_read=[w['read_start'],w['origin']],forecast_labels_read=0,time_status=times[info['source']],legacy_exposure=w['legacy_exposure']))
   for condition in ('raw','target_block_10'):
    x=raw.copy()
    if condition!='raw':x[230:281]=np.nan
    mask=np.isfinite(x);assert np.array_equal(x[mask],raw[mask])
    for h in (96,192):
     uid=f"{info['source']}-o{w['origin']}-{condition}-h{h}";arrays[uid]=x.copy()
     rows.append(dict(uid=uid,source=info['source'],parent=w['parent'],role='train',target_channel=0,target_field=info['target'],condition=condition,L=512,H=h,read_start=w['read_start'],origin=w['origin'],input_hash=smoke.arrsha(x),target_mask_hash=smoke.arrsha(np.isfinite(x)),auxiliary_hash=smoke.arrsha(v[:,1:]),raw_target_hash=smoke.arrsha(raw),raw_complete=bool(np.isfinite(raw).all()),missing_count=int(np.isnan(x).sum()),time_status=times[info['source']],data_sha256=info['file_sha256']))
   values=[];wi+=1
   if wi==len(windows):break
  assert wi==len(windows)
 np.savez(OUT/'inputs.npz',**arrays)
 old=json.loads((ROOT/'configs/v431-r5/main_train_smoke.json').read_text())
 config=dict(status='prepared_no_forecast',purpose='TRAIN-only Native KEEP bank; no scoring, no r5 fitting, no promotion or independent confirmation',protocol_sha256=smoke.sha(protocol_path),timestamp_audit_sha256=smoke.sha(audit_path),runner_sha256=smoke.sha(__file__),worker_sha256=smoke.sha(smoke.__file__),native_backend_sha256=smoke.sha(ROOT/'scripts/v431_baselines/worker.py'),inputs=str(OUT/'inputs.npz'),inputs_sha256=smoke.sha(OUT/'inputs.npz'),rows=rows,selected=selected,support=support,excluded_timestamp_parents=sorted(bad),per_family_requests=len(rows),families=['bolt','timesfm'],seed=101,heldout_labels_read=0,forecast_target_labels_read=0,numerical_scope='only selected TRAIN context rows; one string-stream pass per source',missing_semantics=old['missing_semantics'],all_sources_original_clock_verified=False,ordinal_clock_note=old['ordinal_clock_note'],runtime_reuse='smoke.run with explicit OUT and CONFIG module mapping; source file unchanged',selection_frozen_at=datetime.datetime.now().astimezone().isoformat())
 smoke.write(CONFIG,config);smoke.write(OUT/'prepare_status.json',config);print(json.dumps(dict(support=support,parents=len(selected),per_family_requests=len(rows),runner_sha256=config['runner_sha256'],worker_sha256=config['worker_sha256'],config_sha256=smoke.sha(CONFIG))))
def main():
 p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--family',choices=['bolt','timesfm']);p.add_argument('--deadline',default='2026-09-16T04:44:00+08:00');a=p.parse_args()
 if a.prepare:prepare()
 elif a.family:
  config=json.loads(CONFIG.read_text());assert smoke.sha(__file__)==config['runner_sha256'];smoke.OUT=OUT;smoke.CONFIG=CONFIG;smoke.run(a.family,a.deadline)
 else:p.error('choose --prepare or --family')
if __name__=='__main__':main()
