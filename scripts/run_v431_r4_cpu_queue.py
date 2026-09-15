#!/usr/bin/env python3
"""Persistent sequential CPU fitting/evaluation queue; no GPU jobs."""
from datetime import datetime,timezone
import json,os,subprocess,sys,time
from pathlib import Path

root=Path('results/v431-r4');logs=Path('logs/v431-r4');logs.mkdir(parents=True,exist_ok=True)
status={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),'jobs':[],'gpu_jobs':0}
def save():
    p=root/'cpu_queue_status.json';t=p.with_suffix('.json.tmp');t.write_text(json.dumps(status,indent=2)+'\n');t.replace(p)
jobs=[('fit',['--fit']),('train-library',['--evaluate','--role','T_fit']),('dev',['--evaluate']),
      ('check',['--evaluate','--role','T_check']),('old-acq',['--evaluate','--role','T_acq']),
      ('financial',['--evaluate','--suite','financial']),('generalization',['--evaluate','--suite','generalization'])]
save()
for name,args in jobs:
    cmd=[sys.executable,'scripts/v431_r4_run.py',*args];start=time.perf_counter();path=logs/('cpu-'+name+'-first.log')
    row={'name':name,'command':cmd,'status':'running','log':str(path),'started_at':datetime.now(timezone.utc).isoformat()}
    status['jobs'].append(row);status['active_job']=name
    with path.open('x') as f:
        p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT);row['pid']=p.pid;save()
        code=p.wait()
    row.update(exit_code=code,status='completed' if code==0 else 'failed',seconds=time.perf_counter()-start,finished_at=datetime.now(timezone.utc).isoformat());save()
    if code:
        status['status']='failed';save();raise SystemExit(code)
status.update(status='completed',finished_at=datetime.now(timezone.utc).isoformat());save()
