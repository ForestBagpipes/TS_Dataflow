#!/usr/bin/env python3
"""Separate Chronos-2 native KEEP acceptance; never an r5 governance result."""
import argparse,fcntl,hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
import numpy as np
from introact_ts.v43.schemas import array_hash,json_hash

REVISION='29ec3766d36d6f73f0696f85560a422f50e8498c'
WEIGHT_SHA='ddcda3c7508bf2528087723e98a20707cc04b7f370ae275a9fd88078ddba4f42'
CACHE=Path('/home/vipuser/work2-cache/chronos2-native-check')/REVISION
OUT=Path('results/v431-r5/chronos2-native-check')
OLD=Path('results/v43/20260914T141030.324186Z-agent')
REG=Path('results/v431-r5/backbone-registry/chronos-2')


def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def write(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp')
    q.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n');q.replace(p)


def download():
    OUT.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    weight=CACHE/'model.safetensors';begun=time.perf_counter()
    report=dict(model='amazon/chronos-2',revision=REVISION,license='Apache-2.0',status='downloading',model_path=str(CACHE))
    write(OUT/'download-status.json',report)
    for name in ('config.json','README.md'):
        source=REG/name;dest=CACHE/name
        if dest.exists():assert sha(source)==sha(dest),'Existing metadata differs'
        else:dest.write_bytes(source.read_bytes())
    try:
        if not weight.exists():
            part=CACHE/'model.safetensors.part'
            if part.exists():raise RuntimeError('Prior partial download exists; inspect before resuming')
            url=f'https://huggingface.co/amazon/chronos-2/resolve/{REVISION}/model.safetensors'
            request=urllib.request.Request(url,headers={'User-Agent':'IntroAct-TS-native-interface-check'})
            with urllib.request.urlopen(request,timeout=60) as response,part.open('xb') as f:
                n=0;last=0
                while True:
                    b=response.read(1024*1024)
                    if not b:break
                    f.write(b);n+=len(b)
                    if n-last>=32*1024*1024:
                        report.update(bytes=n,elapsed_seconds=time.perf_counter()-begun);write(OUT/'download-status.json',report);print(json.dumps(report),flush=True);last=n
            assert part.stat().st_size==477930472 and sha(part)==WEIGHT_SHA,'Downloaded model bytes do not match official LFS'
            part.replace(weight)
        assert weight.stat().st_size==477930472 and sha(weight)==WEIGHT_SHA,'Existing model weights differ'
        report.update(status='completed',bytes=weight.stat().st_size,weight_sha256=sha(weight),
                      config_sha256=sha(CACHE/'config.json'),elapsed_seconds=time.perf_counter()-begun)
    except Exception as e:
        report.update(status='failed',error=type(e).__name__+': '+str(e),elapsed_seconds=time.perf_counter()-begun)
        write(OUT/'download-status.json',report);raise
    write(OUT/'download-status.json',report);print(json.dumps(report),flush=True)


def prepare():
    if (OUT/'input-status.json').exists():raise RuntimeError('Preserve first prepared input manifest')
    meta=json.loads((OLD/'episode_manifest.json').read_text());wanted={}
    fitmeta=json.loads(Path('results/v431/20260914-sprint/partition.json').read_text())
    parents=sorted({r['parent_group'] for u,r in meta.items() if fitmeta[u]['v431_role']=='T_fit' and r['source']=='ETTm1'},
                   key=lambda p:int(p.split(':')[1]))
    first=parents[0]
    wanted['train']=[u for u,r in meta.items() if r['parent_group']==first and r['horizon'] in (96,192) and r['condition'] in ('raw','target_block_10')]
    wanted['dev']=[u for u,r in meta.items() if r['split']=='dev']
    assert len(wanted['train'])==4 and len(wanted['dev'])==156
    files={}
    with np.load(OLD/'contexts.npz',allow_pickle=False) as contexts:
        for suite,uids in wanted.items():
            arrays={};rows=[]
            for u in uids:
                r=meta[u];x=contexts[u+'_target'].copy();z=contexts[u+'_covariates'];t=contexts[u+'_timestamps'];availability=contexts[u+'_availability']
                assert x.shape==(512,) and np.isfinite(x).any() and not np.isinf(x).any()
                assert array_hash(x)==r['target_hash'],'Current raw input identity changed'
                arrays[u]=x
                identity=dict(episode_uid=u,parent=r['parent_group'],source=r['source'],split=r['split'],
                    raw_start=r['raw_start'],origin=r['context_end'],L=512,H=r['horizon'],condition=r['condition'],
                    target_hash=array_hash(x),target_mask_hash=array_hash(np.isfinite(x)),auxiliary_mask_hash=array_hash(np.isfinite(z)),
                    timestamps_hash=array_hash(t),availability_hash=array_hash(availability),input_dtype=str(x.dtype),
                    arm='A0_NATIVE',model='amazon/chronos-2',revision=REVISION,model_dtype='float32',
                    native=dict(context_length=512,cross_learning=False,batch_size=1,point_quantile=.5,limit_prediction_length=True),
                    labels_read=False,nan_count=int(np.isnan(x).sum()))
                identity['cache_identity']=json_hash(identity);rows.append(identity)
            target=OUT/(suite+'-inputs.npz');target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:np.savez(f,**arrays)
            write(OUT/(suite+'-manifest.json'),rows);files[str(target)]=sha(target)
    config=dict(version='chronos2-native-check-v1',model='amazon/chronos-2',revision=REVISION,weight_sha256=WEIGHT_SHA,
        local_model_path=str(CACHE),environment='existing w2-chronos, no dependency changes',model_dtype='float32',
        native_context=512,horizons=[96,192],point_quantile=.5,cross_learning=False,batch_size=1,
        purpose='native KEEP interface and separate backbone sensitivity; not third independent family or r5 governance',
        inputs=files,metadata_only_selection=True,heldout_labels_read=False,source_sha256=sha(__file__))
    write('configs/v431-r5/chronos2-native-check.json',config);write(OUT/'input-status.json',dict(status='prepared',**config))
    print(json.dumps(dict(status='prepared',train_cases=4,train_parents=1,old_dev_cases=156,old_dev_parents=26,source_sha256=sha(__file__))))


def run(suite,deadline='2026-09-16T04:45:00+08:00'):
    from datetime import datetime
    deadline_wall=datetime.fromisoformat(deadline).timestamp()
    dest=OUT/suite
    if dest.exists():raise RuntimeError('Preserve original native run directory')
    dest.mkdir(parents=True);started=time.perf_counter()
    records=[];load_seconds=None;active_request=None;physical_calls=0
    stage='identity_validation';stage_started=started
    try:
        if time.time()>=deadline_wall:raise TimeoutError('registered computation deadline reached before initialization')
        config=json.loads(Path('configs/v431-r5/chronos2-native-check.json').read_text())
        inputs=OUT/(suite+'-inputs.npz');assert sha(inputs)==config['inputs'][str(inputs)]
        assert sha(CACHE/'model.safetensors')==WEIGHT_SHA
        assert sha(CACHE/'config.json')==sha(REG/'config.json')
        rows=json.loads((OUT/(suite+'-manifest.json')).read_text())
        if suite=='train':
            assert all(r['split']=='train' for r in rows)
            partition=json.loads(Path('results/v431/20260914-sprint/partition.json').read_text())
            # The current r5 producer stores this same immutable r4 role table.
            current_roles={x['uid']:x['role'] for x in json.loads(Path('results/v431-r4/trajectory-final/main/bolt.rows.json').read_text())}
            assert all(partition[r['episode_uid']]['v431_role']=='T_fit' for r in rows)
            assert all(current_roles[r['episode_uid']]=='T_fit' for r in rows)
            fitparents={x['parent'] for x in json.loads(Path('results/v431-r5/fit/manifest.json').read_text())['families']['bolt']['oof']}
            assert all(r['parent'] in fitparents for r in rows),'Acceptance parent not in actual r5 fit'
            assert len(rows)==4 and len({r['parent'] for r in rows})==1
        else:assert len(rows)==156 and len({r['parent'] for r in rows})==26
        write(dest/'runtime_identity.json',dict(suite=suite,parents=len({r['parent'] for r in rows}),variants=len(rows),
            input_preparation_sha256=config['source_sha256'],runtime_source_sha256=sha(__file__),
            checkpoint_revision=REVISION,input_manifest_sha256=sha(OUT/(suite+'-manifest.json')),
            r5_fit_manifest_sha256=sha('results/v431-r5/fit/manifest.json'),future_labels_read=False,
            computation_deadline=deadline,pre_execution_revision_reason='deadline guard only; unchanged model/input/native settings'))
        if suite=='dev':assert (OUT/'train/status.json').exists() and json.loads((OUT/'train/status.json').read_text())['status']=='completed'
        with Path('locks/gpu.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            visible=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
            assert not visible,'Foreign GPU task present; root must queue this job'
            import torch,chronos
            from chronos import Chronos2Pipeline
            assert Path(os.sys.executable).resolve()==Path('/home/vipuser/work2-envs/w2-chronos/bin/python').resolve()
            torch.set_num_threads(1);torch.manual_seed(101);np.random.seed(101)
            stage='model_load';stage_started=time.perf_counter();tick=stage_started
            write(dest/'progress.json',dict(status='loading',pid=os.getpid(),completed=0,total=len(rows)))
            pipeline=Chronos2Pipeline.from_pretrained(str(CACHE),device_map='cuda',torch_dtype=torch.float32,local_files_only=True)
            torch.cuda.synchronize();load_seconds=time.perf_counter()-tick
            assert isinstance(pipeline,Chronos2Pipeline) and all(p.device.type=='cuda' for p in pipeline.model.parameters())
            quantiles=pipeline.quantiles;assert .5 in quantiles
            outputs={};memo={};(dest/'requests').mkdir()
            with np.load(inputs,allow_pickle=False) as data:
                for i,r in enumerate(rows):
                    if time.time()>=deadline_wall:
                        stage='deadline_before_next_request';stage_started=time.perf_counter()
                        raise TimeoutError('registered computation deadline reached; completed predictions preserved')
                    stage='request';stage_started=time.perf_counter();active_request=dict(index=i,episode_uid=r['episode_uid'],started_elapsed_seconds=stage_started-started)
                    write(dest/'progress.json',dict(status='running',completed=len(records),total=len(rows),active_request=active_request,
                        cold_model_load_seconds=load_seconds,completed_physical_calls=physical_calls))
                    x=data[r['episode_uid']].copy();before=x.copy();key=(array_hash(x),r['H']);tick=time.perf_counter()
                    # Keep latency as real uncached single requests in acceptance;
                    # DEV uses native same-input/H dedup but retains donor cost.
                    if suite=='dev' and key in memo:
                        pred,raw,seconds=memo[key];cache_hit=True
                    else:
                        torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();t0=time.perf_counter()
                        physical_calls+=1
                        with torch.inference_mode():out=pipeline.predict([torch.from_numpy(x.astype(np.float32)).unsqueeze(0)],prediction_length=r['H'],
                            context_length=512,batch_size=1,cross_learning=False,limit_prediction_length=True)
                        torch.cuda.synchronize();seconds=time.perf_counter()-t0
                        assert len(out)==1 and tuple(out[0].shape)==(1,len(quantiles),r['H'])
                        raw=out[0].float().cpu().numpy();pred=raw[0,quantiles.index(.5)].copy();cache_hit=False;memo[key]=(pred,raw,seconds)
                    assert np.isfinite(pred).all() and np.array_equal(before,x,equal_nan=True)
                    outputs[r['episode_uid']]=pred;outputs[r['episode_uid']+'_quantiles']=raw
                    persistence_started=time.perf_counter();rawpath=dest/'requests'/f'{i:04d}.npz';temp=rawpath.with_suffix('.npz.tmp')
                    with temp.open('xb') as f:
                        np.savez(f,point=pred,quantiles=raw);f.flush();os.fsync(f.fileno())
                    temp.replace(rawpath)
                    rec=dict(**r,prediction_hash=array_hash(pred),prediction_dtype=str(pred.dtype),shape=list(pred.shape),
                        charged_native_seconds=float(seconds),current_execution_seconds=time.perf_counter()-tick,cache_hit=cache_hit,
                        peak_gpu_bytes=int(torch.cuda.max_memory_allocated()),labels_read=False,
                        raw_file=str(rawpath),raw_file_sha256=sha(rawpath),raw_persistence_seconds=time.perf_counter()-persistence_started)
                    records.append(rec)
                    write(dest/'records.json',records)
                    write(dest/'progress.json',dict(completed=i+1,total=len(rows),last=rec))
                    active_request=None
            stage='final_archive';stage_started=time.perf_counter()
            with (dest/'predictions.npz').open('xb') as f:np.savez(f,**outputs)
            write(dest/'records.json',records)
            write(dest/'status.json',dict(status='completed',suite=suite,requests=len(records),parents=len({r['parent'] for r in records}),physical_native_calls=physical_calls,
                cold_model_load_seconds=load_seconds,full_process_seconds=time.perf_counter()-started,
                peak_gpu_bytes=max(r['peak_gpu_bytes'] for r in records),torch_version=torch.__version__,chronos_version=chronos.__version__,
                prediction_sha256=sha(dest/'predictions.npz'),records_sha256=sha(dest/'records.json'),weight_sha256=WEIGHT_SHA,
                process_pid=os.getpid(),future_labels_read=False,source_sha256=sha(__file__),
                interpretation='native interface/backbone-only sensitivity, no governance success claim'))
            print(json.dumps(json.loads((dest/'status.json').read_text())),flush=True)
    except Exception as e:
        write(dest/'records.json',records)
        write(dest/'status.json',dict(status='partial_deadline' if isinstance(e,TimeoutError) else 'failed',error=type(e).__name__+': '+str(e),elapsed_seconds=time.perf_counter()-started,
            computation_deadline=deadline,eligible_for_dev_scoring=False,
            failed_stage=stage,failed_stage_host_wall_seconds=time.perf_counter()-stage_started,
            active_request=active_request,completed_requests=len(records),attempted_physical_calls=physical_calls,
            cold_model_load_seconds=load_seconds,completed_charged_native_seconds=sum(r['charged_native_seconds'] for r in records),
            completed_physical_native_seconds=sum(r['charged_native_seconds'] for r in records if not r['cache_hit']),
            incomplete_stage_cost_policy='Retain measured host wall; missing CUDA completion is unknown, not zero',
            durable_raw_files=[r['raw_file'] for r in records],runtime_source_sha256=sha(__file__)));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--download',action='store_true');p.add_argument('--prepare',action='store_true')
    p.add_argument('--run',action='store_true');p.add_argument('--suite',choices=['train','dev'],default='train')
    p.add_argument('--deadline',default='2026-09-16T04:45:00+08:00');args=p.parse_args()
    if args.download:download()
    if args.prepare:prepare()
    if args.run:run(args.suite,args.deadline)
