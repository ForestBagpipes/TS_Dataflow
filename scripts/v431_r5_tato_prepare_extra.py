#!/usr/bin/env python3
"""Metadata-preregistered extra TATO scenes; no GPU or DEV target access."""
import json,hashlib
from pathlib import Path
import numpy as np
import joblib
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'results/v43/20260914T141030.324186Z-agent';OUT=ROOT/'results/v431-r5/tato-scene-extra'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def arrsha(a):
 a=np.ascontiguousarray(a);return hashlib.sha256(a.dtype.str.encode()+str(a.shape).encode()+a.tobytes()).hexdigest()
def main():
 OUT.mkdir(exist_ok=True)
 frozen=ROOT/'results/v431-r5/fit/models_frozen.json';mp=frozen.with_name('models.joblib');assert sha(mp)==json.loads(frozen.read_text())['sha256']
 models=joblib.load(mp)['families'];parents=[set(m['reference'].training_parents) for m in models.values()];assert all(p==parents[0] for p in parents)
 meta=json.loads((OLD/'episode_manifest.json').read_text());manifest={r['source']:r for r in json.loads((OLD/'data_manifest.json').read_text())}
 queue=[]
 with np.load(OLD/'contexts.npz',allow_pickle=False) as x,np.load(OLD/'targets.npz',allow_pickle=False) as y:
  # All added source/family H96 scenes precede all H192 scenes.
  for h in (96,192):
   for source in ('Solar','US_Term_Structure'):
    record=manifest[source];bounds=record['split_bounds']['train'];field=record['channels'][0]
    for family in ('bolt','timesfm'):
     name=f'{source.lower()}-{family}-h{h}';out=OUT/name;out.mkdir(exist_ok=False)
     train=sorted([u for u,m in meta.items() if m['source']==source and m['split']=='train' and m['parent_group'] in parents[0] and m['condition']=='target_block_10' and m['horizon']==h],key=lambda u:meta[u]['raw_start'])[:500]
     dev=sorted([u for u,m in meta.items() if m['source']==source and m['split']=='dev' and m['condition']=='target_block_10' and m['horizon']==h],key=lambda u:meta[u]['raw_start'])
     assert train and dev and len(train)==len({meta[u]['parent_group'] for u in train})
     arrays={};rows=[]
     for role,ids in [('train',train),('dev',dev)]:
      for u in ids:
       m=meta[u];a=x[u+'_target'];assert a.shape==(512,)
       row=dict(uid=u,role=role,parent=m['parent_group'],source=source,horizon=h,raw_start=m['raw_start'],origin=m['context_end'],input_hash=arrsha(a))
       arrays[u+'_context']=a.copy()
       if role=='train':
        assert bounds[0]<=m['raw_start'] and m['context_end']+h<=bounds[1]
        target=y[u+'_values'];mask=y[u+'_mask'];arrays[u+'_target']=target;arrays[u+'_mask']=mask
        row.update(train_bounds=bounds,target_hash=arrsha(target),mask_hash=arrsha(mask))
       rows.append(row)
     np.savez(out/'inputs.npz',**arrays)
     request=dict(status='preregistered_not_run',family=family,horizon=h,source=source,target_channel=0,target_field=field,condition='target_block_10',context=512,
      train_parents=len(train),dev_parents=len(dev),rows=rows,trials=500,max_seconds=600,pilot_requests=min(20,len(train)),inputs=str(out/'inputs.npz'),inputs_sha256=sha(out/'inputs.npz'),output=str(out),seed=101,
      worker_sha256=sha(ROOT/'scripts/v431_r5_tato_scene.py'),adapter_sha256=sha(ROOT/'scripts/v431_r5_prepare_main.py'),reference_frozen_sha256=sha(frozen),
      supervision='r5 T_fit parents only; no gate/check/acq/calibration/test',protocol='native TATO TRAIN mean MSE L512; not official full reproduction',budgets=[.8140623268639832,3.5],heldout_labels_read=0,
      queue_rule='after first four ETTm1 scenes; all source/family H96 before H192; only if available time before 04:45; runtime duration may shrink from 600 solely by remaining wall time; archive preregistered request and resolved hash; otherwise not_run')
     p=out/'request.preregistered.json';p.write_text(json.dumps(request,indent=2)+'\n')
     queue.append(dict(order=len(queue),scene=name,source=source,target_field=field,family=family,horizon=h,train_parents=len(train),dev_parents=len(dev),request=str(p),request_sha256=sha(p),status='not_run_preregistered',max_seconds_upper_bound=600))
 result=dict(status='prepared_no_GPU_run',queue=queue,selection='metadata only, not performance',worker_sha256=sha(ROOT/'scripts/v431_r5_tato_scene.py'),heldout_labels_read=0)
 (OUT/'queue.preregistered.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(queue,indent=2))
if __name__=='__main__':main()
