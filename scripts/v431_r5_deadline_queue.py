#!/usr/bin/env python3
"""Sequential optional baseline jobs, with an explicit shutdown-time reserve.

This process never shuts down the server or stops unrelated processes.
Worker owns gpu.lock; this queue owns only the distinct project queue mutex.
"""
import argparse,fcntl,hashlib,json,os,subprocess,sys,time
from datetime import datetime
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
def atom(p,x):
    p=Path(p);q=p.with_suffix('.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');q.replace(p)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--deadline',default='2026-09-16T04:45:00+08:00')
    p.add_argument('--queue',default='results/v431-r5/tato-scene-extra/queue.preregistered.json')
    p.add_argument('--worker',default='scripts/v431_r5_tato_scene.py')
    p.add_argument('--status',default=None)
    a=p.parse_args();deadline=datetime.fromisoformat(a.deadline).timestamp();q=Path(a.queue)
    status=Path(a.status) if a.status else q.with_name('queue.execution.json');jobs=read(q)['queue']
    if status.exists():raise RuntimeError('Preserve queue execution; do not restart blindly')
    state=dict(status='waiting_for_primary_scenes',pid=os.getpid(),deadline=a.deadline,
      preregister_sha256=sha(q),jobs=jobs,server_shutdown_invoked=False,queue_code_sha256=sha(__file__),worker=str(Path(a.worker).resolve()))
    atom(status,state)
    primary=[Path('results/v431-r5/tato-scene')/name/'run/status.json' for name in
      ['bolt-h96','bolt-h192','timesfm-h96','timesfm-h192']]
    while time.time()<deadline:
        if all(x.exists() and read(x).get('status') in ('completed','partial','failed') for x in primary):break
        time.sleep(10)
    worker=Path(a.worker).resolve()
    interpreter=os.environ['W2_CHRONOS_PY']
    for j in jobs:
        # The queue wait is not a worker/request cost; re-evaluate after the lock.
        wait_started=time.perf_counter()
        with Path('locks/r5-online-queue.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            j['queue_wait_seconds']=time.perf_counter()-wait_started
            remaining=deadline-time.time()
            unstarted=sum(x.get('status')=='not_run_preregistered' for x in jobs)
            if remaining<90:
                j.update(status='not_run_deadline',remaining_seconds=remaining);atom(status,state);continue
            original=Path(j['request']);assert sha(original)==j['request_sha256']
            r=read(original);out=original.parent
            allocation=min(j['max_seconds_upper_bound'],remaining-90*max(0,unstarted-1))
            if allocation<90:
                j.update(status='not_run_insufficient_queue_budget',remaining_seconds=remaining);atom(status,state);continue
            r['max_seconds']=float(allocation)
            r['time_resolution']=dict(absolute_deadline=a.deadline,remaining_seconds=remaining,
              rule='after queue lock: minimum preregistered cap and remaining wall budget; no loss input',original_request_sha256=sha(original))
            resolved=out/'request.resolved.json'
            if resolved.exists():raise RuntimeError('Resolved request already exists')
            atom(resolved,r);cmd=[interpreter,str(worker),'--request',str(resolved)]
            log=out/'queue-worker.log';j.update(status='running',resolved_request=str(resolved),resolved_sha256=sha(resolved),
              command=cmd,max_seconds=allocation,started_local=datetime.now().astimezone().isoformat())
            state['status']='running';atom(status,state)
            begun=time.perf_counter()
            with log.open('x') as f:
                proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT);j['pid']=proc.pid;atom(status,state)
                code=proc.wait()
            j.update(exit_code=code,wall_seconds=time.perf_counter()-begun,
              wall_scope='full child process after queue lock; queue wait separately recorded')
        final=out/'run/status.json'
        j['status']=read(final).get('status','failed') if final.exists() and code==0 else 'process_failed'
        atom(status,state)
    state['status']='finished_with_explicit_missing_or_partial';state['finished_local']=datetime.now().astimezone().isoformat();atom(status,state)
if __name__=='__main__':main()
