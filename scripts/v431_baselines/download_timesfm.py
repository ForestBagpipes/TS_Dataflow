#!/usr/bin/env python3
"""Task-only direct ranged download; never changes global proxy configuration."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time
import requests

ROOT=Path(__file__).resolve().parents[2]
META=ROOT/'logs/v431/baselines/timesfm-preparation.json'
REPO='google/timesfm-2.5-200m-pytorch'
REVISION='1d952420fba87f3c6dee4f240de0f1a0fbc790e3'
EXPECTED='2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8'
SIZE=925181104
PART=16*1024*1024


def atom(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)


def main():
    start=time.perf_counter();out=ROOT/'.cache/v431-timesfm-ranges';out.mkdir(exist_ok=True)
    original=json.loads(META.read_text());original.update(status='downloading',download_route='8_direct_range_streams',first_stream_preserved='existing .incomplete untouched')
    atom(META,original)
    def fetch(number):
        lo=number*PART;hi=min(SIZE,(number+1)*PART)-1;path=out/f'part-{number:03d}'
        if path.exists() and path.stat().st_size==hi-lo+1:return dict(part=number,bytes=hi-lo+1,cached=True)
        begin=time.perf_counter();errors=[]
        for retry in range(3):
            session=requests.Session();session.trust_env=False
            try:
                url=f'https://huggingface.co/{REPO}/resolve/{REVISION}/model.safetensors?download=true&v431_part={number}'
                with session.get(url,headers={'Range':f'bytes={lo}-{hi}'},timeout=(15,90),stream=True) as response:
                    response.raise_for_status()
                    if response.status_code!=206 or response.headers.get('Content-Range')!=f'bytes {lo}-{hi}/{SIZE}':raise RuntimeError('server did not honor exact requested range')
                    size=0
                    with path.with_suffix('.partial').open('wb') as f:
                        for block in response.iter_content(1024*1024):f.write(block);size+=len(block)
                    if size!=hi-lo+1:raise RuntimeError('partial range length mismatch')
                    path.with_suffix('.partial').replace(path)
                return dict(part=number,bytes=size,seconds=time.perf_counter()-begin,retries=errors)
            except Exception as exc:
                # Signed redirect URLs/tokens are intentionally not logged.
                errors.append(type(exc).__name__)
        raise RuntimeError(f'part {number} failed: {errors}')
    rows=[]
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            pending=[pool.submit(fetch,i) for i in range((SIZE+PART-1)//PART)]
            for future in as_completed(pending):
                rows.append(future.result());record=dict(status='running',completed_parts=len(rows),total_parts=len(pending),bytes=sum(r['bytes'] for r in rows),seconds=time.perf_counter()-start,parts=rows)
                atom(ROOT/'logs/v431/baselines/timesfm-range-status.json',record)
                print(json.dumps({k:v for k,v in record.items() if k!='parts'}),flush=True)
        hub=Path('/home/vipuser/work2-cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch')
        assembled=out/'assembled.safetensors';h=hashlib.sha256()
        with assembled.open('wb') as dest:
            for i in range((SIZE+PART-1)//PART):
                with (out/f'part-{i:03d}').open('rb') as src:
                    for block in iter(lambda:src.read(8*1024*1024),b''):dest.write(block);h.update(block)
        if h.hexdigest()!=EXPECTED or assembled.stat().st_size!=SIZE:raise RuntimeError('TimesFM full weight hash/size mismatch')
        target=hub/'blobs'/EXPECTED
        # Both locations are under the same /home filesystem on this server.
        assembled.replace(target)
        snapshot=hub/'snapshots'/REVISION;snapshot.mkdir(parents=True,exist_ok=True)
        link=snapshot/'model.safetensors'
        if not link.exists():link.symlink_to(Path('../../blobs')/EXPECTED)
        original.update(status='downloaded_not_validated',snapshot_path=str(snapshot),download_seconds=time.perf_counter()-start,verified_sha256=EXPECTED,range_parts=len(rows))
        atom(META,original)
        atom(ROOT/'logs/v431/baselines/timesfm-range-status.json',dict(status='completed',seconds=time.perf_counter()-start,parts=rows,sha256=EXPECTED))
    except Exception as exc:
        atom(ROOT/'logs/v431/baselines/timesfm-range-status.json',dict(status='failed',error=str(exc),seconds=time.perf_counter()-start,parts=rows));raise


if __name__=='__main__':main()
