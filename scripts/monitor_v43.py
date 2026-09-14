#!/usr/bin/env python3
"""Read-only host monitoring of existing bootstrap/model/pilot processes.

Writes only this project's monitoring reports. Never installs, restarts, signals
processes, or changes GPU settings. Process command lines are never collected.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import psutil

ROOT = Path('/home/vipuser/work/work2')
STAGE = Path('/home/vipuser/work2-staging/bootstrap-20260914')


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {'status': 'not_created'}
    except (OSError, ValueError) as exc:
        return {'status': 'read_error', 'error': str(exc)}


def atomic(path, value):
    temp = path.with_name(path.name + f'.tmp.{os.getpid()}')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    temp.replace(path)


def processes(root_pid):
    if not root_pid:
        return []
    try:
        parent = psutil.Process(root_pid)
        family = [parent]+parent.children(recursive=True)
    except psutil.Error:
        return []
    rows = []
    for process in family:
        try:
            io = process.io_counters()
            downloads = []
            for item in process.open_files():
                if item.path.endswith(('.whl', '.incomplete')):
                    try:
                        downloads.append(dict(name=Path(item.path).name, size_bytes=Path(item.path).stat().st_size))
                    except OSError:
                        pass
            rows.append(dict(pid=process.pid, ppid=process.ppid(), name=process.name(),
                             created_at=process.create_time(), rss_bytes=process.memory_info().rss,
                             read_chars=io.read_chars, write_chars=io.write_chars,
                             read_bytes=io.read_bytes, write_bytes=io.write_bytes, downloads=downloads))
        except (psutil.Error, OSError) as exc:
            rows.append(dict(pid=process.pid, error=type(exc).__name__))
    return rows


def sample():
    environment = read_json(STAGE/'status.json')
    continuation = read_json(STAGE/'continuation-status.json')
    queue = read_json(ROOT/'results/v43/pilot_queue_status.json')
    models = read_json(ROOT/'configs/v43/model_manifest.bootstrap.json')
    states = dict(environment=environment, continuation=continuation, queue=queue)
    pilot_dir = queue.get('pilot_directory')
    pilot = read_json(Path(pilot_dir)/'status.json') if pilot_dir else {'status': 'not_run'}
    process_rows = {name: processes(value.get('pid')) for name, value in states.items()}
    alerts = []
    for name, state in {**states, 'pilot': pilot}.items():
        status = state.get('status', '')
        if 'fail' in status or 'blocked' in status:
            alerts.append(dict(kind='reported_failure_or_block', stage=name, status=status, error=state.get('error')))
        if state.get('pid') and status in ('running', 'waiting_for_models', 'waiting_for_environments', 'preparing_models'):
            if not psutil.pid_exists(state['pid']):
                alerts.append(dict(kind='recorded_pid_missing', stage=name, pid=state['pid']))
    try:
        gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.total,utilization.gpu',
                                       '--format=csv,noheader,nounits'], text=True, stderr=subprocess.STDOUT, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        gpu = None
        alerts.append(dict(kind='gpu_monitor_error', error=str(exc)))
    memory, disk = psutil.virtual_memory(), psutil.disk_usage(ROOT)
    return dict(at=now(), environment={k: environment.get(k) for k in ('status','phase','pid','exit_code')},
                continuation={k: continuation.get(k) for k in ('status','pid','environment_phase','model_exit_code')},
                queue=queue, pilot=pilot, models={k: v.get('status') for k,v in models.get('models',{}).items()},
                processes=process_rows, gpu_mib_used_total_util_percent=gpu, memory_available_bytes=memory.available,
                disk_free_bytes=disk.free, alerts=alerts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=int, default=30)
    parser.add_argument('--max-hours', type=float, default=24)
    args = parser.parse_args()
    if args.interval < 10 or args.max_hours <= 0:
        parser.error('interval must be >=10 seconds and max-hours positive')
    with (ROOT/'locks/v43-monitor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run = ROOT/'logs/v43'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ-monitor')
        run.mkdir(parents=True, exist_ok=False)
        started = time.monotonic()
        previous, last_fingerprint, last_progress = None, None, started
        with (run/'samples.jsonl').open('x') as log:
            while True:
                observation = sample()
                current = time.monotonic()
                writers = observation['processes']['environment']
                fingerprint = (observation['environment']['phase'], [(p.get('pid'),p.get('created_at'),p.get('write_chars')) for p in writers])
                if fingerprint != last_fingerprint:
                    last_progress, last_fingerprint = current, fingerprint
                observation['environment_seconds_without_io_or_phase_change'] = current-last_progress
                if observation['environment']['status']=='running' and current-last_progress > 900:
                    observation['alerts'].append(dict(kind='environment_no_io_progress_15min', action='inspect_only_no_restart'))
                if previous:
                    prev_io = {p.get('pid'):p for group in previous['processes'].values() for p in group}
                    for group in observation['processes'].values():
                        for process in group:
                            old = prev_io.get(process['pid'], {})
                            if old.get('created_at') == process.get('created_at') and 'write_chars' in old and 'write_chars' in process:
                                process['write_bytes_per_second'] = max(0, process['write_chars']-old['write_chars'])/(current-previous['_monotonic'])
                status = 'pilot_completed' if observation['pilot']['status']=='completed' else 'monitoring'
                if current-started >= args.max_hours*3600:
                    status = 'monitoring_window_ended'
                snapshot = dict(status=status, monitor_pid=os.getpid(), monitor_directory=str(run), **observation)
                log.write(json.dumps(snapshot, ensure_ascii=False, allow_nan=False)+'\n')
                log.flush()
                atomic(run/'status.json', snapshot)
                atomic(ROOT/'results/v43/monitor_status.json', snapshot)
                if observation['alerts']:
                    print(json.dumps(dict(at=observation['at'], alerts=observation['alerts'])), flush=True)
                if status != 'monitoring':
                    break
                previous = dict(observation, _monotonic=current)
                time.sleep(args.interval)


if __name__=='__main__':
    main()
