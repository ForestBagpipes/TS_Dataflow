#!/usr/bin/env python3
"""An explicitly identified TimesFM service using the existing strict file protocol."""
import argparse,copy,fcntl,json,os,subprocess,sys,time,traceback
from pathlib import Path
import numpy as np
from introact_ts.v43.schemas import array_hash,require
from introact_ts.v43.worker_protocol import validate_request,verify_response
from introact_ts.v43.workers.common import load_inputs,atomic_json
from introact_ts.v43.data_io import file_hash
sys.path.insert(0,str(Path(__file__).parent/'v431_baselines'))
from worker import TimesFM

def main():
    p=argparse.ArgumentParser();p.add_argument('--allowed',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    out=Path(args.output);(out/'raw').mkdir(exist_ok=False);model=None;bound=None
    for line in sys.stdin:
        command=json.loads(line)
        if command['action']=='close':return
        q=json.loads(Path(command['request']).read_text());response=copy.deepcopy(q)
        response.update(status='running',units='original',worker_pid=os.getpid(),worker_python=sys.executable,service_sha256=file_hash(__file__))
        try:
            validate_request(q);require(q['model_key']=='timesfm' and q['task']=='forecast','wrong TimesFM service request')
            identity=tuple(q[k] for k in ('model_revision','environment_hash','code_hash','model_key','seed','normalization'))
            require(bound is None or identity==bound,'resident model identity changed')
            allowed=json.loads(Path(args.allowed).read_text())
            for a in allowed:
                proc=Path(f"/proc/{a['pid']}");ticks=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
                require(ticks==a['start_ticks'] and proc.stat().st_uid==os.getuid(),'allowed process identity changed')
            with Path(q['gpu_lock']).open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                visible=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
                require(not visible or {int(s) for s in visible.splitlines()} <= {a['pid'] for a in allowed},'foreign GPU task')
                import torch
                if model is None:
                    record=json.loads(Path(q['model_manifest']).read_text())['models']['timesfm']
                    require(record['revision']==q['model_revision'],'TimesFM revision differs')
                    require(Path(sys.executable).resolve()==Path(record['environment_python']).resolve(),'TimesFM wrong interpreter')
                    require(file_hash(record['environment_lock'])==q['environment_hash']==record['environment_lock_sha256'],'environment lock changed')
                    for item in record['files'].values():require(file_hash(item['path'])==item['sha256'],'TimesFM model file changed')
                    official=subprocess.check_output(['git','-C',record['official_code_path'],'rev-parse','HEAD'],text=True).strip();require(official==record['official_code_commit'],'TimesFM source changed')
                    require(file_hash(Path(__file__).parent/'v431_baselines/worker.py')==record['adapter_sha256'],'TimesFM adapter changed')
                    torch.manual_seed(q['seed']);np.random.seed(q['seed']);tick=time.perf_counter();model=TimesFM(out);torch.cuda.synchronize()
                    response['service_initial_load_seconds']=time.perf_counter()-tick;bound=identity
                else:response['service_initial_load_seconds']=0.
                response['load_seconds']=response['service_initial_load_seconds'];response['load_peak_gpu_bytes']=torch.cuda.max_memory_allocated();response['actual_model_identity']=model.identity
                if command['action']=='load':response['status']='loaded';atomic_json(command['response'],response);continue
                payloads=load_inputs(q);predictions=[];raw={}
                for i,(r,payload) in enumerate(zip(response['rows'],payloads)):
                    tick=time.perf_counter();point=model.forecast(payload['target'][None,:,None],q['horizon'])[0,:,0].astype(q['dtype']);call=model.calls[-1]
                    original=next(v for v in model.calls if v['cache_key']==call['cache_key'] and not v['cache_hit'])
                    with np.load(out/original['raw_file'],allow_pickle=False) as f:quantiles=f['quantiles'];native=f['point'][0]
                    require(np.array_equal(point,native.astype(q['dtype'])),'native TimesFM point changed')
                    r.update(prediction_hash=array_hash(point),shape=list(point.shape),runtime_seconds=time.perf_counter()-tick,peak_gpu_bytes=torch.cuda.max_memory_allocated(),raw_shape=list(quantiles.shape),raw_hash=array_hash(quantiles),actual_batch_size=1,cache_hit=call['cache_hit'],raw_native_file=str(out/original['raw_file']))
                    predictions.append(point);raw[f'row_{i}']=quantiles
                response['status']='completed';verify_response(q,response,predictions)
                target=Path(command['predictions'])
                with target.open('xb') as f:np.savez(f,**{f'row_{i}':x for i,x in enumerate(predictions)})
                rawpath=target.with_name(target.stem+'.raw.npz')
                with rawpath.open('xb') as f:np.savez(f,**raw)
                response['raw_predictions']=dict(path=str(rawpath),sha256=file_hash(rawpath));atomic_json(command['response'],response)
        except Exception as e:response.update(status='failed',error=f'{type(e).__name__}: {e}');atomic_json(command['response'],response);traceback.print_exc();raise

if __name__=='__main__':main()
