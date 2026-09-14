#!/usr/bin/env python3
"""Single-GPU queue worker for official TATO/Bolt and fixed TimesFM rows.

CPU preparation: worker.py --prepare RUN --output OUT --backend tato
Queue execution: w2-chronos/bin/python worker.py --request OUT/request.json
No target/future file is opened by either path. Root evaluates predictions later.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import numpy as np
from tato_adapter import ROOT, COMMIT, sha, official_identity, adapt_window

POOL=['A0_NATIVE','A0_FFILL','A2_SINGLE','A3_COV','A4_RIDGE_CONTEXT']


def atom(path, value):
    path=Path(path); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False));tmp.replace(path)


def array_sha(x):
    x=np.ascontiguousarray(x)
    return __import__('hashlib').sha256(x.dtype.str.encode()+str(x.shape).encode()+x.tobytes()).hexdigest()


def prepare(run, output, backend):
    run=Path(run).resolve(); out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    meta=json.loads((run/'episode_manifest.json').read_text())
    records=[]; arrays={}
    with np.load(run/('contexts.npz' if backend=='tato' else 'candidates.npz'),allow_pickle=False) as f:
        for uid,m in sorted(meta.items()):
            if m['role']!='dev': continue
            for arm in (['TATO_NATIVE_SPACE'] if backend=='tato' else POOL):
                key=uid+'_target' if backend=='tato' else uid+'_'+arm
                x=f[key].copy(); output_key=uid+'_'+arm;arrays[output_key]=x
                records.append(dict(episode_uid=uid,arm=arm,input_key=output_key,input_sha256=array_sha(x),
                    horizon=m['horizon'],parent_group=m['parent_group'],source=m['source'],
                    raw_start=m['raw_start'],context_end=m['context_end'],condition=m['condition'],split=m['split']))
    with (out/'inputs.npz').open('xb') as f:np.savez(f,**arrays)
    request=dict(schema_version=1,backend=backend,created_at=datetime.now(timezone.utc).isoformat(),
        inputs=str(out/'inputs.npz'),inputs_sha256=sha(out/'inputs.npz'),rows=records,
        output=str(out),seed=101,trials=8,bridge='observed_linear_only_if_nan',
        budget_scope='fixed_8_trial_short_budget; wall-clock costs retained; no equal-budget claim',
        official_tato_commit=COMMIT,adapter_sha256=sha(Path(__file__).with_name('tato_adapter.py')),
        worker_sha256=sha(__file__),source_context_file_sha256=sha(run/('contexts.npz' if backend=='tato' else 'candidates.npz')),
        no_future_file_access=True,source_run=str(run))
    atom(out/'request.json',request)
    print(json.dumps(dict(request=str(out/'request.json'),rows=len(records),parents=len({r['parent_group'] for r in records}))))


@contextmanager
def gpu_lock():
    with (ROOT/'locks/gpu.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        pids=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
        if pids:raise RuntimeError('GPU has active processes; root must schedule this worker after them')
        yield


class Bolt:
    def __init__(self,out):
        import torch
        from chronos import BaseChronosPipeline,ChronosBoltPipeline
        record=json.loads((ROOT/'configs/v43/model_manifest.bootstrap.json').read_text())['models']['bolt']
        for v in record['files'].values():
            if sha(v['path'])!=v['sha256']:raise RuntimeError('Bolt immutable model file hash changed')
        self.model=BaseChronosPipeline.from_pretrained(record['snapshot_path'],device_map='cuda',torch_dtype=torch.bfloat16,local_files_only=True)
        if not isinstance(self.model,ChronosBoltPipeline):raise RuntimeError('wrong backbone')
        self.quantiles=self.model.model.config.chronos_config['quantiles'];self.out=out;self.calls=[];self.cache={};self.counter=0
        self.identity=dict(repo_id=record['repo_id'],revision=record['revision'],dtype='bfloat16',environment_python=sys.executable,
            weight_sha256=record['files']['model.safetensors']['sha256'])

    def forecast(self,x,horizon):
        import torch
        x=np.asarray(x); key=array_sha(x)+':'+str(horizon)
        if key in self.cache:
            self.calls.append(dict(cache_key=key,cache_hit=True,seconds=0.));return self.cache[key].copy()
        tick=time.perf_counter();torch.cuda.reset_peak_memory_stats()
        tensors=[torch.from_numpy(v[:,0].astype(np.float32)) for v in x]
        with torch.inference_mode():raw=self.model.predict(tensors,horizon)
        torch.cuda.synchronize();raw=raw.float().cpu().numpy();seconds=time.perf_counter()-tick
        if not np.isfinite(raw).all():raise FloatingPointError('raw Bolt quantiles nonfinite')
        point=raw[:,self.quantiles.index(.5),:,None]
        name=f'call_{self.counter:05d}';self.counter+=1
        np.savez(self.out/'raw'/f'{name}.npz',input=x,quantiles=raw,point=point)
        self.calls.append(dict(cache_key=key,cache_hit=False,seconds=seconds,raw_file='raw/'+name+'.npz',
            raw_sha256=sha(self.out/'raw'/f'{name}.npz'),peak_gpu_bytes=torch.cuda.max_memory_allocated(),horizon=horizon))
        self.cache[key]=point.copy();return point


class TimesFM:
    def __init__(self,out):
        source=ROOT/'.cache/v431-timesfm-source';sys.path.insert(0,str(source/'src'))
        import torch,timesfm
        record=json.loads((ROOT/'logs/v431/baselines/timesfm-preparation.json').read_text())
        if record['status']!='downloaded_not_validated':raise RuntimeError('TimesFM weights not downloaded')
        weight=Path(record['snapshot_path'])/'model.safetensors';expected=next(x['lfs']['sha256'] for x in record['files'] if x['name']=='model.safetensors')
        if sha(weight)!=expected:raise RuntimeError('TimesFM weight sha mismatch')
        self.model=timesfm.TimesFM_2p5_200M_torch.from_pretrained(record['snapshot_path'],torch_compile=False,local_files_only=True)
        self.model.compile(timesfm.ForecastConfig(max_context=512,max_horizon=192,normalize_inputs=True,
            per_core_batch_size=1,use_continuous_quantile_head=True,force_flip_invariance=True,
            infer_is_positive=True,fix_quantile_crossing=True))
        if next(self.model.model.parameters()).device.type!='cuda':raise RuntimeError('TimesFM not on GPU')
        self.identity=dict(repo_id=record['repo_id'],revision=record['revision'],weight_sha256=expected,
            source_commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
            installed_package='task-source-overlay; unchanged chronos environment',native_nan_behavior='official context-only linear interpolation and leading-NaN strip')
        self.out=out;self.calls=[];self.cache={};self.counter=0

    def forecast(self,x,horizon):
        import torch
        x=np.asarray(x);key=array_sha(x)+':'+str(horizon)
        if key in self.cache:
            self.calls.append(dict(cache_key=key,cache_hit=True,seconds=0.));return self.cache[key].copy()
        if np.isinf(x).any() or not np.isfinite(x).any():raise ValueError('TimesFM invalid/all-missing context rejected')
        tick=time.perf_counter();torch.cuda.reset_peak_memory_stats()
        with torch.inference_mode():point,quantiles=self.model.forecast(horizon=horizon,inputs=[v[:,0].copy() for v in x])
        torch.cuda.synchronize();elapsed=time.perf_counter()-tick;point=np.asarray(point);quantiles=np.asarray(quantiles)
        if not np.isfinite(point).all() or not np.isfinite(quantiles).all():raise FloatingPointError('TimesFM output nonfinite')
        name=f'call_{self.counter:05d}';self.counter+=1
        np.savez(self.out/'raw'/f'{name}.npz',input=x,quantiles=quantiles,point=point)
        self.calls.append(dict(cache_key=key,cache_hit=False,seconds=elapsed,raw_file='raw/'+name+'.npz',
            raw_sha256=sha(self.out/'raw'/f'{name}.npz'),peak_gpu_bytes=torch.cuda.max_memory_allocated(),horizon=horizon))
        result=point[:,:,None];self.cache[key]=result.copy();return result


def execute(path):
    request=json.loads(Path(path).read_text());out=Path(request['output']);tick=time.perf_counter()
    if request['worker_sha256']!=sha(__file__) or request['adapter_sha256']!=sha(Path(__file__).with_name('tato_adapter.py')):raise RuntimeError('worker source changed after manifest')
    if request['inputs_sha256']!=sha(request['inputs']):raise RuntimeError('input file hash changed')
    status=dict(status='running',pid=os.getpid(),worker_python=sys.executable,request_sha256=sha(path),rows_done=0,future_labels_read=0,heldout_labels_read=0)
    atom(out/'status.json',status);(out/'raw').mkdir(exist_ok=False);predictions={};records=[]
    try:
        with gpu_lock():
            import torch
            torch.manual_seed(request['seed']);np.random.seed(request['seed'])
            load_tick=time.perf_counter();model=Bolt(out) if request['backend']=='tato' else TimesFM(out)
            torch.cuda.synchronize();load_seconds=time.perf_counter()-load_tick
            identity=model.identity
            if request['backend']=='tato':identity['official']=official_identity()
            atom(out/'identity.json',identity)
            # Real model synthetic capability checks precede data evaluation.
            smoke=np.sin(np.arange(512)*.1)[None,:,None];smoke[0,100:150,0]=np.nan
            if request['backend']=='timesfm':
                for horizon in (96,192):
                    p=model.forecast(smoke,horizon)
                    if p.shape!=(1,horizon,1):raise RuntimeError('TimesFM capability shape failed')
                atom(out/'capability.json',dict(status='passed',scope='real GPU nan/H96/H192 synthetic interface only',calls=len(model.calls)))
            with np.load(request['inputs'],allow_pickle=False) as f:
                for row in request['rows']:
                    start=time.perf_counter();x=f[row['input_key']].copy()
                    if array_sha(x)!=row['input_sha256']:raise RuntimeError('row identity changed')
                    before=len(model.calls)
                    if request['backend']=='tato':
                        prediction,detail=adapt_window(x,row['horizon'],model,trials=request['trials'],seed=request['seed'])
                    else:
                        prediction=model.forecast(x[None,:,None],row['horizon'])[0,:,0];detail={}
                    predictions[row['input_key']]=prediction
                    calls=model.calls[before:]
                    records.append(dict(**row,**detail,wall_seconds=time.perf_counter()-start,prediction_sha256=array_sha(prediction),model_calls=calls,
                        actual_model_calls=sum(not c['cache_hit'] for c in calls), cache_hits=sum(c['cache_hit'] for c in calls)))
                    atom(out/'decisions.json',records);atom(out/'calls.json',model.calls)
                    status.update(rows_done=len(records),elapsed_seconds=time.perf_counter()-tick);atom(out/'status.json',status)
                    print(json.dumps({k:status[k] for k in ('rows_done','elapsed_seconds')}),flush=True)
            with (out/'predictions.npz').open('xb') as f:np.savez(f,**predictions)
            status.update(status='completed',model_load_seconds=load_seconds,total_wall_seconds=time.perf_counter()-tick,
                prediction_file_sha256=sha(out/'predictions.npz'),actual_model_calls=sum(not x['cache_hit'] for x in model.calls),peak_gpu_bytes=torch.cuda.max_memory_allocated())
            status['all_row_wall_seconds']=sum(row['wall_seconds'] for row in records)
            status['process_overhead_seconds']=status['total_wall_seconds']-status['all_row_wall_seconds']
            atom(out/'status.json',status)
    except BaseException as exc:
        status.update(status='failed',error=f'{type(exc).__name__}: {exc}',elapsed_seconds=time.perf_counter()-tick)
        atom(out/'status.json',status);traceback.print_exc();raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare');p.add_argument('--output');p.add_argument('--backend',choices=['tato','timesfm']);p.add_argument('--request')
    a=p.parse_args()
    if a.prepare:prepare(a.prepare,a.output,a.backend)
    elif a.request:execute(a.request)
    else:p.error('choose --prepare or --request')
