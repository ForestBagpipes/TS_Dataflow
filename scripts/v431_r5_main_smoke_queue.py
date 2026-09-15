#!/usr/bin/env python3
"""One bounded GPU queue for the already selected TRAIN-only interface cases."""
import fcntl
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def main():
    root = Path('results/v431-r5/main-train-smoke')
    state_path = root / 'queue.json'
    if state_path.exists():
        raise RuntimeError('Preserve prior queue state')
    deadline = '2026-09-16T04:45:00+08:00'
    end = datetime.fromisoformat(deadline).timestamp()
    previous = json.loads(Path('results/v431-r5/official96-queue-status.json').read_text())
    assert previous['status'] == 'finished', 'Earlier GPU queue has not finished'
    state = dict(status='running', pid=os.getpid(), deadline=deadline,
                 queue_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), jobs=[])
    write(state_path, state)
    for family in ('bolt', 'timesfm'):
        job = dict(family=family)
        state['jobs'].append(job)
        waited = time.perf_counter()
        with Path('locks/r5-online-queue.lock').open('a') as mutex:
            fcntl.flock(mutex, fcntl.LOCK_EX)
            job['queue_wait_seconds'] = time.perf_counter() - waited
            if time.time() > end - 90:
                job['status'] = 'not_run_deadline'
                write(state_path, state)
                continue
            active = subprocess.check_output(
                ['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
            if active:
                job['status'] = 'not_run_other_gpu_process'
                write(state_path, state)
                continue
            command = [os.environ['W2_CHRONOS_PY'], 'scripts/v431_r5_main_train_smoke.py',
                       '--family', family, '--deadline', deadline]
            job.update(command=command, status='running', started_at=datetime.now().astimezone().isoformat())
            write(state_path, state)
            begun = time.perf_counter()
            with (root / (family + '-process.log')).open('x') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                job['pid'] = process.pid
                write(state_path, state)
                code = process.wait()
            job.update(exit_code=code, complete_subprocess_seconds=time.perf_counter() - begun,
                       status='process_completed' if code == 0 else 'process_failed')
            write(state_path, state)
    state.update(status='finished', finished_at=datetime.now().astimezone().isoformat())
    write(state_path, state)


if __name__ == '__main__':
    main()
