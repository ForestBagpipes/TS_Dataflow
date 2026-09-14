#!/usr/bin/env python3
"""CPU-only monitor: evaluate completed queued family runs without starting GPU."""
import json,os,subprocess,time
from pathlib import Path
from tato_adapter import ROOT


def main():
    base=ROOT/'results/v431/20260914-sprint';logs=ROOT/'logs/v431/20260914-sprint'
    python='/home/vipuser/work2-envs/w2-chronos/bin/python';state={};start=time.perf_counter()
    for name in ('timesfm','timesfm_tato'):
        directory=base/name
        while True:
            status=json.loads((directory/'status.json').read_text()) if (directory/'status.json').exists() else {}
            if status.get('status')=='failed':raise RuntimeError(f'{name} worker failed: {status.get("error")}')
            if status.get('status')=='completed':break
            if time.perf_counter()-start>1800:raise TimeoutError('GPU queue did not finish within monitor window; no GPU task was started by this monitor')
            time.sleep(2)
        args=[python,str(ROOT/'scripts/v431_baselines/verify_and_score.py'),str(directory)] if name=='timesfm' else [python,str(ROOT/'scripts/v431_baselines/timesfm_tato_worker.py'),'--verify',str(directory)]
        env=dict(os.environ,CUDA_VISIBLE_DEVICES='')
        with (logs/(name+'-independent.log')).open('w') as f:result=subprocess.run(args,env=env,stdout=f,stderr=subprocess.STDOUT)
        state[name]=dict(exit_code=result.returncode,seconds_since_monitor_start=time.perf_counter()-start)
        (logs/'baseline-monitor-status.json').write_text(json.dumps(state,indent=2))
        if result.returncode:raise RuntimeError(f'{name} independent verification failed; inspect its raw log')
        print(json.dumps(state),flush=True)


if __name__=='__main__':main()
