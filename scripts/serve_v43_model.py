#!/usr/bin/env python3
"""Task-owned persistent model service for actual online replay, file protocol."""
import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import numpy as np
from introact_ts.v43.schemas import array_hash,require
from introact_ts.v43.worker_protocol import validate_request,verify_response
from introact_ts.v43.workers.common import verify_model,load_inputs,atomic_json
from introact_ts.v43.data_io import file_hash


def ticks(pid):return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--key',choices=['tsicl','bolt'],required=True)
    parser.add_argument('--allowed',required=True)
    args=parser.parse_args()
    loader_module='introact_ts.v43.workers.tsicl_worker' if args.key=='tsicl' else 'introact_ts.v43.workers.chronos_worker'
    from importlib import import_module
    adapter=import_module(loader_module)
    model=None;bound=None
    for line in sys.stdin:
        command=json.loads(line)
        if command['action']=='close':return
        request=json.loads(Path(command['request']).read_text());response=deepcopy(request)
        response.update(status='running',units='original',worker_pid=os.getpid(),worker_python=sys.executable,
                        service_sha256=file_hash(__file__))
        try:
            validate_request(request)
            identity=tuple(request[k] for k in ('model_revision','environment_hash','code_hash','model_key','seed','normalization'))
            require(bound is None or identity==bound,'live model identity changed')
            require(request['task']==('impute' if args.key=='tsicl' else 'forecast'),'unsupported live task')
            allowed=json.loads(Path(args.allowed).read_text())
            require(all(ticks(item['pid'])==item['start_ticks'] and Path(f"/proc/{item['pid']}").stat().st_uid==os.getuid() for item in allowed),'service identity changed')
            with Path(request['gpu_lock']).open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                visible=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
                require(not visible or {int(x) for x in visible.splitlines()}<={i['pid'] for i in allowed},'foreign GPU process; service refuses to interfere')
                import torch
                if model is None:
                    record=verify_model(request,args.key)
                    torch.manual_seed(request['seed']);np.random.seed(request['seed'])
                    torch.cuda.reset_peak_memory_stats();start=time.perf_counter();model=adapter.load(record);torch.cuda.synchronize()
                    response['service_initial_load_seconds']=time.perf_counter()-start
                    bound=identity
                else:response['service_initial_load_seconds']=0.
                response['load_seconds']=response['service_initial_load_seconds'];response['load_peak_gpu_bytes']=torch.cuda.max_memory_allocated()
                if command['action']=='load':
                    response.update(status='loaded');atomic_json(command['response'],response);continue
                payloads=load_inputs(request);predictions=[];raw={}
                for i,(row,payload) in enumerate(zip(response['rows'],payloads)):
                    torch.cuda.reset_peak_memory_stats();start=time.perf_counter()
                    point,quantiles=adapter.predict(model,payload,request,row)
                    require(np.isfinite(quantiles).all(),'nonfinite live raw output')
                    torch.cuda.synchronize();runtime=time.perf_counter()-start;p=np.asarray(point,dtype=request['dtype'])
                    row.update(prediction_hash=array_hash(p),shape=list(p.shape),runtime_seconds=runtime,peak_gpu_bytes=torch.cuda.max_memory_allocated(),
                               raw_shape=list(quantiles.shape),raw_hash=array_hash(quantiles),actual_batch_size=1)
                    predictions.append(p);raw[f'row_{i}']=quantiles
                response['status']='completed';verify_response(request,response,predictions)
                output=Path(command['predictions'])
                with output.open('xb') as f:np.savez(f,**{f'row_{i}':v for i,v in enumerate(predictions)})
                raw_path=output.with_name(output.stem+'.raw.npz')
                with raw_path.open('xb') as f:np.savez(f,**raw)
                response['raw_predictions']=dict(path=str(raw_path),sha256=file_hash(raw_path))
                atomic_json(command['response'],response)
        except Exception as exc:
            response.update(status='failed',error=f'{type(exc).__name__}: {exc}');atomic_json(command['response'],response)
            traceback.print_exc();raise


if __name__=='__main__':main()
