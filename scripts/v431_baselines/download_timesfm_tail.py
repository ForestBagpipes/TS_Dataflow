#!/usr/bin/env python3
"""Resume task-owned verified range prefixes using smaller independent tails."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,json,time
from pathlib import Path
import requests
from download_timesfm import ROOT,META,REPO,REVISION,EXPECTED,SIZE,PART,atom


def main():
    start=time.perf_counter();out=ROOT/'.cache/v431-timesfm-ranges';tail=out/'tails';tail.mkdir(exist_ok=True)
    plans=[]
    for i in range((SIZE+PART-1)//PART):
        path=out/f'part-{i:03d}';end=min(SIZE,(i+1)*PART)
        if path.exists():continue
        partial=path.with_suffix('.partial');prefix=partial.stat().st_size if partial.exists() else 0
        for lo in range(i*PART+prefix,end,4*1024*1024):plans.append(dict(part=i,lo=lo,hi=min(end,lo+4*1024*1024)-1,prefix=prefix))
    atom(ROOT/'logs/v431/baselines/timesfm-tail-plan.json',dict(plans=plans,status='registered_before_requests'))
    def fetch(plan):
        lo,hi=plan['lo'],plan['hi'];path=tail/f'{lo}-{hi}';tick=time.perf_counter()
        if path.exists() and path.stat().st_size==hi-lo+1:return plan|dict(cached=True)
        errors=[]
        for retry in range(4):
            session=requests.Session();session.trust_env=False
            try:
                with session.get(f'https://huggingface.co/{REPO}/resolve/{REVISION}/model.safetensors?download=true&v431_tail={lo}_{retry}',headers={'Range':f'bytes={lo}-{hi}'},stream=True,timeout=(10,25)) as r:
                    r.raise_for_status()
                    if r.status_code!=206 or r.headers.get('Content-Range')!=f'bytes {lo}-{hi}/{SIZE}':raise RuntimeError('invalid exact tail range')
                    with path.with_suffix('.tmp').open('wb') as f:
                        for b in r.iter_content(1024*1024):
                            f.write(b)
                            if time.perf_counter()-tick>60:raise TimeoutError('tail exceeded total time budget')
                    if path.with_suffix('.tmp').stat().st_size!=hi-lo+1:raise RuntimeError('tail size mismatch')
                    path.with_suffix('.tmp').replace(path)
                return plan|dict(seconds=time.perf_counter()-tick,retries=errors)
            except Exception as e:errors.append(type(e).__name__);tick=time.perf_counter()
        raise RuntimeError(f'tail {lo} failed {errors}')
    done=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(fetch,p) for p in plans]):
            done.append(future.result());r=dict(status='running',completed=len(done),total=len(plans),seconds=time.perf_counter()-start,parts=done)
            atom(ROOT/'logs/v431/baselines/timesfm-tail-status.json',r);print(json.dumps({k:v for k,v in r.items() if k!='parts'}),flush=True)
    for i in sorted({p['part'] for p in plans}):
        path=out/f'part-{i:03d}';partial=path.with_suffix('.partial');original=partial.read_bytes() if partial.exists() else b''
        with path.open('wb') as f:
            f.write(original)
            for p in sorted([p for p in plans if p['part']==i],key=lambda p:p['lo']):f.write((tail/f"{p['lo']}-{p['hi']}").read_bytes())
        if path.stat().st_size!=min(SIZE,(i+1)*PART)-i*PART:raise RuntimeError('assembled part size mismatch')
    assembled=out/'assembled.safetensors';h=hashlib.sha256()
    with assembled.open('wb') as f:
        for i in range((SIZE+PART-1)//PART):
            with (out/f'part-{i:03d}').open('rb') as src:
                for b in iter(lambda:src.read(8*1024*1024),b''):f.write(b);h.update(b)
    if h.hexdigest()!=EXPECTED or assembled.stat().st_size!=SIZE:raise RuntimeError('full official weight SHA/size mismatch')
    hub=Path('/home/vipuser/work2-cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch');dest=hub/'blobs'/EXPECTED;assembled.replace(dest)
    snapshot=hub/'snapshots'/REVISION;link=snapshot/'model.safetensors'
    if not link.exists():link.symlink_to(Path('../../blobs')/EXPECTED)
    original=json.loads(META.read_text());original.update(status='downloaded_not_validated',snapshot_path=str(snapshot),verified_sha256=EXPECTED,tail_seconds=time.perf_counter()-start)
    atom(META,original);atom(ROOT/'logs/v431/baselines/timesfm-tail-status.json',dict(status='completed',seconds=time.perf_counter()-start,parts=done,sha256=EXPECTED))
    print('verified_ready_for_GPU_queue',flush=True)


if __name__=='__main__':main()
