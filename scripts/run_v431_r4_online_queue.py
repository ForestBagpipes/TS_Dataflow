#!/usr/bin/env python3
"""Single locked GPU queue, preserving all first-run logs and failures."""
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import argparse
import json
import os
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', default='first')
    args = parser.parse_args()
    if not args.run_id.replace('-', '').isalnum():
        raise ValueError('run-id must be a simple alphanumeric suffix')
    root = Path('results/v431-r4')
    logs = Path('logs/v431-r4')
    status_path = root / ('online_queue_status.json' if args.run_id == 'first'
                          else 'online_queue_status-' + args.run_id + '.json')
    if status_path.exists():
        raise RuntimeError('An online queue status exists; inspect instead of overwriting it')
    state = {'status': 'waiting_gpu_lock', 'pid': os.getpid(), 'jobs': [],
             'started_at': datetime.now(timezone.utc).isoformat()}

    def save():
        temp = status_path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(state, indent=2) + '\n')
        temp.replace(status_path)

    save()
    # Each actual model service already owns gpu.lock during load/inference.
    # Holding that same lock in a parent prevents its child from acquiring it.
    # This queue mutex only prevents duplicate orchestration; GPU ownership
    # remains enforced by the unchanged service and its foreign-PID checks.
    with Path('locks/r4_online_queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state['status'] = 'running'
        for family in ('bolt', 'timesfm'):
            cmd = [sys.executable, 'scripts/v431_r4_online.py', '--family', family]
            if args.run_id != 'first':
                cmd += ['--output-name', 'online-' + family + '-' + args.run_id]
            log = logs / ('online-' + family + '-' + args.run_id + '.log')
            row = {'family': family, 'command': cmd, 'log': str(log),
                   'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat()}
            state['jobs'].append(row)
            started = time.perf_counter()
            with log.open('x') as handle:
                process = subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT)
                row['pid'] = process.pid
                save()
                code = process.wait()
            row.update(exit_code=code, status='completed' if code == 0 else 'failed',
                       wall_seconds=time.perf_counter()-started,
                       finished_at=datetime.now(timezone.utc).isoformat())
            save()
            if code:
                state['status'] = 'failed'
                save()
                raise SystemExit(code)
        state.update(status='completed', finished_at=datetime.now(timezone.utc).isoformat())
        save()


if __name__ == '__main__':
    main()
