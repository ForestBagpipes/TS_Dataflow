#!/usr/bin/env python3
"""Missing TimesFM train/current and aligned-history outputs, never evaluator labels."""
import argparse, hashlib, json, os, sys, time, traceback
from pathlib import Path
import numpy as np
from introact_ts.v43.schemas import array_hash

ROOT=Path('/home/vipuser/work/work2')
OLD=ROOT/'results/v43/20260914T141030.324186Z-agent'
SPRINT=ROOT/'results/v431/20260914-sprint'
OUT=ROOT/'results/v431-r2/timesfm-cache'
sys.path.insert(0,str(ROOT/'scripts/v431_baselines'))
from worker import TimesFM, gpu_lock, sha, atom

def prepare():
    OUT.mkdir(parents=True,exist_ok=False)
    meta=json.loads((OLD/'episode_manifest.json').read_text());rows=[];sources={}
    for phase,directory,prefix in [('current',OLD,'final'),('history',SPRINT/'history','targeth')]:
        for h in (96,192):
            p=directory/f'{prefix}-h{h}-bolt.request.json';q=json.loads(p.read_text());sources[str(p)]=sha(p)
            for r in q['rows']:
                uid=r['episode_uid'].split(':asof:',1)[0]
                if phase=='current' and meta[uid]['role']=='dev':continue
                assert meta[uid]['split'] in ('train','dev')
                rows.append(dict(r,phase=phase,base_uid=uid,horizon=h,source=meta[uid]['source'],
                    parent_group=meta[uid]['parent_group'],split=meta[uid]['split'],array_sha256=sha(r['array_path'])))
    request=dict(schema='v431_r2_timesfm_cache_1',seed=101,rows=rows,source_requests=sources,
        worker_sha256=sha(__file__),backend_source_sha256=sha(ROOT/'scripts/v431_baselines/worker.py'),
        model_record_sha256=sha(ROOT/'logs/v431/baselines/timesfm-preparation.json'),
        origin_cache_policy='reuse immutable inputs and masks; current DEV predictions reused from verified v431 archive',
        labels_access='none',future_labels_read=0,heldout_labels_read=0)
    atom(OUT/'request.json',request);print(json.dumps({'requests':len(rows),'output':str(OUT)}),flush=True)

def execute():
    p=OUT/'request.json';q=json.loads(p.read_text());tick=time.perf_counter()
    assert q['worker_sha256']==sha(__file__) and q['backend_source_sha256']==sha(ROOT/'scripts/v431_baselines/worker.py')
    assert q['model_record_sha256']==sha(ROOT/'logs/v431/baselines/timesfm-preparation.json')
    for source,digest in q['source_requests'].items():assert sha(source)==digest
    s=dict(status='running',pid=os.getpid(),started_at=time.time(),request_sha256=sha(p),rows_done=0,future_labels_read=0,heldout_labels_read=0)
    atom(OUT/'status.json',s);(OUT/'raw').mkdir(exist_ok=False);records=[];predictions={}
    try:
        with gpu_lock():
            import torch
            torch.manual_seed(q['seed']);np.random.seed(q['seed']);t=time.perf_counter();model=TimesFM(OUT)
            torch.cuda.synchronize();s['model_load_seconds']=time.perf_counter()-t;atom(OUT/'identity.json',model.identity)
            with (OUT/'resources.jsonl').open('x') as resources:
                for k,r in enumerate(q['rows']):
                    assert sha(r['array_path'])==r['array_sha256']
                    with np.load(r['array_path'],allow_pickle=False) as f:
                        x=f['target'];assert array_hash(x)==r['input_hash']
                        for a,b in [('raw_mask','raw_mask_hash'),('covariates','covariate_hash'),('timestamps','timestamps_hash'),('availability','availability_hash')]:assert array_hash(f[a])==r[b]
                    t=time.perf_counter();prediction=model.forecast(x[None,:,None],r['horizon'])[0,:,0]
                    assert prediction.shape==(r['horizon'],) and np.isfinite(prediction).all()
                    key=f"{r['phase']}_{r['episode_uid']}_{r['candidate_id']}";predictions[key]=prediction
                    records.append(dict(**r,key=key,prediction_hash=array_hash(prediction),wall_seconds=time.perf_counter()-t,model_call=model.calls[-1]))
                    if (k+1)%50==0 or k+1==len(q['rows']):
                        s.update(rows_done=k+1,elapsed_seconds=time.perf_counter()-tick);atom(OUT/'status.json',s)
                        atom(OUT/'records.json',records);atom(OUT/'calls.json',model.calls)
                        resources.write(json.dumps(dict(time=time.time(),pid=os.getpid(),cuda_allocated=torch.cuda.memory_allocated(),cuda_peak=torch.cuda.max_memory_allocated()))+'\n');resources.flush()
                        print(json.dumps(s),flush=True)
            with (OUT/'predictions.npz').open('xb') as f:np.savez(f,**predictions)
            unique={c['cache_key']:c for c in model.calls if not c['cache_hit']}
            s.update(status='completed',elapsed_seconds=time.perf_counter()-tick,actual_model_calls=len(unique),prediction_sha256=sha(OUT/'predictions.npz'))
            overhead=max(0.,s['elapsed_seconds']-sum(c['seconds'] for c in unique.values()))/len(unique)
            for r in records:r['charged_seconds']=unique[r['model_call']['cache_key']]['seconds']+overhead
            atom(OUT/'records.json',records);atom(OUT/'cost_scope.json',dict(total_process_body_seconds=s['elapsed_seconds'],allocated_overhead_per_unique_call=overhead,cross_row_cache_hits_repriced=True,python_pre_main_import_seconds='not_measured_offline',candidate_generation='reused_previous_actual_cost_not_free'))
    except BaseException as e:s.update(status='failed',error=f'{type(e).__name__}: {e}');traceback.print_exc();raise
    finally:atom(OUT/'status.json',s)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','execute']);a=p.parse_args()
    prepare() if a.action=='prepare' else execute()
