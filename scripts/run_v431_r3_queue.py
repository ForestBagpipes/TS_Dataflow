#!/usr/bin/env python3
"""Single-server sequential r3 GPU queue with process/resource evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path('/home/vipuser/work/work2')
OUT = ROOT / 'results/v431-r3'
LOG = ROOT / 'logs/v431-r3'


def atom(path, obj):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2) + '\n')
    tmp.replace(path)


def main():
    assert os.environ.get('W2_CORE_PY') == sys.executable, 'source env_new_server.sh and use W2_CORE_PY'
    LOG.mkdir(exist_ok=True)
    py = sys.executable
    base = [py, 'scripts/v431_r3_collect.py', '--collect', '--run', 'results/v431-r3/probes', '--batch-parents', '4']
    jobs = []
    for family in ('bolt', 'timesfm'):
        jobs.extend([(family + '-pilot20', base + ['--family', family, '--split', 'train', '--limit-train-parents', '20']),
                     (family + '-maximum', base + ['--family', family, '--split', 'all'])])
    for family in ('bolt', 'timesfm'):
        jobs.append(('financial-' + family, base + ['--suite', 'financial', '--family', family]))
    for family in ('bolt', 'timesfm'):
        jobs.append(('check-current-' + family, [py, 'scripts/v431_r3_current.py', '--family', family]))
    state = dict(status='running', pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat(),
                 phase='serial_gpu_probes', jobs=[dict(name=n, command=c, status='queued') for n, c in jobs],
                 calibration_test_read=False, report='docs/v431_r3_plan.md')
    atom(OUT / 'queue_status.json', state)
    for job in state['jobs']:
        started = time.perf_counter()
        log = LOG / (job['name'] + '.log')
        with log.open('x') as stream, (LOG / (job['name'] + '.resources.jsonl')).open('x') as resource:
            process = subprocess.Popen(job['command'], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            job.update(status='running', pid=process.pid, log=str(log), started_at=datetime.now(timezone.utc).isoformat())
            state['active_job'] = job['name']
            atom(OUT / 'queue_status.json', state)
            while process.poll() is None:
                try:
                    gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader,nounits'], text=True).strip()
                    rss = [s for s in Path(f'/proc/{process.pid}/status').read_text().splitlines() if s.startswith(('VmRSS:', 'VmHWM:'))]
                    resource.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(), pid=process.pid, gpu=gpu, rss=rss)) + '\n')
                    resource.flush()
                except (OSError, subprocess.SubprocessError) as exc:
                    resource.write(json.dumps(dict(resource_error=repr(exc))) + '\n')
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            job.update(status='completed' if process.returncode == 0 else 'failed', exit_code=process.returncode,
                       complete_process_seconds=time.perf_counter() - started,
                       finished_at=datetime.now(timezone.utc).isoformat())
            atom(OUT / 'queue_status.json', state)
        print(json.dumps(job), flush=True)
        if process.returncode:
            state.update(status='failed', phase='job_failed', error=job['name'])
            atom(OUT / 'queue_status.json', state)
            raise SystemExit(process.returncode)
    state.update(status='completed', phase='all_frozen_input_predictions_ready',
                 finished_at=datetime.now(timezone.utc).isoformat())
    atom(OUT / 'queue_status.json', state)


if __name__ == '__main__':
    main()
