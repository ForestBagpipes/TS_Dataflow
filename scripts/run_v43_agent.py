#!/usr/bin/env python3
"""Run collection then frozen policy fitting in an independent monitored session."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import psutil
from introact_ts.v43.cli import atomic_json


def main():
    root=Path(__file__).resolve().parents[1]
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out=root/'results/v43'/(stamp+'-agent');logs=root/'logs/v43'/(stamp+'-agent');logs.mkdir(parents=True)
    state=dict(status='running',wrapper_pid=os.getpid(),owner=psutil.Process().username(),started_at=stamp,run=str(out),logs=str(logs))
    path=root/'results/v43/agent_queue_status.json';atomic_json(logs/'launch.json',state)
    phases=[('collection',[sys.executable,'-m','introact_ts.v43.cli','agent-collect','--config',str(root/'configs/v43/agent_minimal.yaml'),'--out',str(out)]),
            ('fit_evaluate',[sys.executable,str(root/'scripts/fit_v43_agent.py'),str(out)])]
    code=0
    with (logs/'resources.jsonl').open('x') as resources:
        for phase,command in phases:
            with (logs/(phase+'.log')).open('x') as log:
                process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
                state.update(phase=phase,pid=process.pid);atomic_json(path,state)
                while process.poll() is None:
                    sample=dict(at=datetime.now(timezone.utc).isoformat(),phase=phase,pid=process.pid)
                    try:
                        p=psutil.Process(process.pid)
                        sample.update(processes=[dict(pid=q.pid,rss=q.memory_info().rss,cpu_seconds=sum(q.cpu_times()[:2])) for q in [p,*p.children(recursive=True)] if q.is_running()],
                                      available_memory=psutil.virtual_memory().available,
                                      gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip())
                    except (OSError,psutil.Error,subprocess.SubprocessError) as exc:sample['resource_error']=str(exc)
                    resources.write(json.dumps(sample)+'\n');resources.flush()
                    state['last_resource_sample']=sample;atomic_json(path,state)
                    try:process.wait(timeout=30)
                    except subprocess.TimeoutExpired:pass
            code=process.returncode
            if code:break
    state.update(status='completed' if code==0 else 'failed',exit_code=code,finished_at=datetime.now(timezone.utc).isoformat())
    atomic_json(path,state);atomic_json(logs/'terminal.json',state);print(json.dumps(state),flush=True)
    return code


if __name__=='__main__':raise SystemExit(main())
