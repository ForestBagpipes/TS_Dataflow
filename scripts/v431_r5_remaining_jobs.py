#!/usr/bin/env python3
"""Deadline-bounded native-backbone check or official-unit baseline queue."""
import argparse,fcntl,hashlib,json,os,subprocess,time
from datetime import datetime
from pathlib import Path

ROOT=Path('results/v431-r5')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atom(p,x):
    p=Path(p);q=p.with_suffix('.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');q.replace(p)
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['chronos2','official96']);p.add_argument('--deadline',default='2026-09-16T04:45:00+08:00');a=p.parse_args()
    end=datetime.fromisoformat(a.deadline).timestamp();path=ROOT/(a.mode+'-queue-status.json')
    if path.exists():raise RuntimeError('Preserve old queue status')
    state=dict(status='waiting',mode=a.mode,pid=os.getpid(),deadline=a.deadline,jobs=[],code_sha256=sha(__file__))
    atom(path,state);python=os.environ['W2_CHRONOS_PY']
    if a.mode=='chronos2':
        downloaded=ROOT/'chronos2-native-check/download-status.json'
        while time.time()<end-120:
            if downloaded.exists() and read(downloaded)['status'] in ('completed','failed'):break
            time.sleep(10)
        if not downloaded.exists() or read(downloaded)['status']!='completed':
            state.update(status='not_run_download_or_deadline');atom(path,state);return
        jobs=[dict(name='chronos2-'+suite,command=[python,'scripts/v431_r5_chronos2_native_check.py','--run','--suite',suite]) for suite in ('train','dev')]
    else:
        previous=ROOT/'tato-scene-extra/queue.execution.json'
        while time.time()<end-90:
            if previous.exists() and read(previous)['status']=='finished_with_explicit_missing_or_partial':break
            time.sleep(10)
        jobs=[dict(name=f'{f}-h{h}',request=str(ROOT/f'tato-official96/{f}-h{h}/request.json')) for f in ('bolt','timesfm') for h in (96,192)]
    state['jobs']=jobs
    for idx,job in enumerate(jobs):
        if time.time()>end-90:
            job['status']='not_run_deadline';atom(path,state);continue
        with Path('locks/r5-online-queue.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            remaining=end-time.time()
            if remaining<90:
                job['status']='not_run_deadline_after_queue_wait';atom(path,state);continue
            if a.mode=='official96':
                old=Path(job['request']);r=read(old);r['max_seconds']=min(r['max_seconds'],remaining/(len(jobs)-idx))
                r['time_resolution']=dict(rule='remaining wall-time fair allocation only; no score input',original_sha256=sha(old),deadline=a.deadline)
                resolved=old.with_name('request.resolved.json')
                if resolved.exists():raise RuntimeError('Resolved request exists')
                atom(resolved,r);job.update(resolved_request=str(resolved),resolved_sha256=sha(resolved),max_seconds=r['max_seconds'],
                  command=[python,'scripts/v431_r5_tato_official96_scene.py','--request',str(resolved)])
            log=Path('logs/v431-r5')/(a.mode+'-queue-'+job['name']+'.log')
            job.update(status='running',started_local=datetime.now().astimezone().isoformat(),log=str(log));state['status']='running';atom(path,state)
            tick=time.perf_counter()
            with log.open('x') as f:
                proc=subprocess.Popen(job['command'],stdout=f,stderr=subprocess.STDOUT);job['pid']=proc.pid;atom(path,state);code=proc.wait()
            job.update(status='process_completed' if code==0 else 'process_failed',exit_code=code,seconds=time.perf_counter()-tick);atom(path,state)
            if a.mode=='chronos2' and code:
                for skipped in jobs[idx+1:]:skipped['status']='not_run_train_acceptance_failed'
                break
    state.update(status='finished',finished_local=datetime.now().astimezone().isoformat());atom(path,state)
if __name__=='__main__':main()
