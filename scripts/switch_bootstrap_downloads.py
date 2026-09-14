#!/usr/bin/env python3
"""一次性、身份核验后的 work2 下载切线；仅向列明的项目进程发信号。"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import psutil
from download_bootstrap_wheels import BASE, LOG, ROOT, STAGE, atomic, digest


def identity(pid, created, fragment):
    p = psutil.Process(pid)
    if p.uids().real != os.getuid() or abs(p.create_time() - created) > 0.02:
        raise ValueError(f'process owner/time mismatch: {pid}')
    if fragment not in ' '.join(p.cmdline()):
        raise ValueError(f'process command mismatch: {pid}')
    return p


def listener_alive():
    with socket.socket() as s:
        s.settimeout(3)
        return s.connect_ex(('127.0.0.1', 17890)) == 0


def stopped(p):
    return not p.is_running() or p.status() == psutil.STATUS_ZOMBIE


def terminate_owned(p):
    if stopped(p):
        return
    try:
        p.terminate()
        p.resume()
    except psutil.NoSuchProcess:
        return
    deadline = time.monotonic() + 10
    while not stopped(p):
        if time.monotonic() > deadline:
            raise RuntimeError(f'graceful termination timed out: {p.pid}; no forced kill')
        time.sleep(0.1)


def main():
    rows = json.loads((LOG / 'wheel-manifest.json').read_text())['packages']
    if len(rows) != 25 or (LOG / 'transition.json').exists():
        raise ValueError('need complete manifest and a fresh transition')
    parent = identity(45580, 1789377897.93, str(STAGE / 'bootstrap-envs.sh'))
    pip = identity(61386, 1789385264.55, '/w2-chronos/bin/python -m pip install torch==2.9.1')
    continuation = identity(47722, 1789378825.96, str(STAGE / 'after-env-bootstrap.py'))
    queue = identity(58448, 1789382957.68, 'scripts/run_v43_pilot_queue.py')
    if pip.ppid() != parent.pid:
        raise ValueError('unexpected installer parent')
    record = dict(status='preparing_switch', at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  old_installers=[dict(pid=p.pid, create_time=p.create_time()) for p in (parent, pip)],
                  observers=[continuation.pid, queue.pid], preserved=[],
                  proxy_listener_before=listener_alive(), proxy_service_modified=False,
                  codex_configuration_modified=False, bandwidth_limit_mib_per_second=8)
    atomic(LOG / 'transition.json', record)
    (BASE / 'preserved').mkdir(parents=True, exist_ok=True)
    suspended = []
    try:
        for p in (continuation, queue, parent, pip):
            p.suspend()
            suspended.append(p)
        for p in suspended:
            if p.status() != psutil.STATUS_STOPPED:
                raise ValueError(f'not suspended: {p.pid}')
        for filename in ('status.json', 'continuation-status.json'):
            shutil.copy2(STAGE / filename, LOG / ('before-' + filename))
        shutil.copy2(STAGE / 'bootstrap-envs.sh', LOG / 'original-bootstrap-envs.sh')
        shutil.copy2(STAGE / 'logs/bootstrap.log', LOG / 'original-bootstrap.log')
        expected = {r['filename']: r for r in rows}
        for source in Path('/tmp').glob('pip-unpack-*/*.whl'):
            info = source.stat()
            if source.name not in expected or info.st_uid != os.getuid() or info.st_mtime < pip.create_time():
                continue
            row = expected[source.name]
            if info.st_size > row['size_bytes']:
                raise ValueError(f'oversized source: {source}')
            dest = BASE / 'preserved' / source.name
            if dest.exists():
                raise ValueError(f'duplicate preserved file: {dest}')
            shutil.copy2(source, dest)
            checksum = digest(dest)
            complete = dest.stat().st_size == row['size_bytes']
            if complete and checksum != row['sha256']:
                raise ValueError(f'complete preserved file checksum mismatch: {source}')
            record['preserved'].append(dict(source=str(source), destination=str(dest),
                                            bytes=dest.stat().st_size, sha256=checksum,
                                            complete_official_hash_verified=complete))
        record['status'] = 'downloads_preserved'
        atomic(LOG / 'transition.json', record)
        terminate_owned(pip)
        terminate_owned(parent)
        record['status'] = 'old_installer_stopped'
        atomic(LOG / 'transition.json', record)
        shutil.copy2(STAGE / 'status.json', LOG / 'original-stop-status.json')
        with (STAGE / 'bootstrap.lock').open('a') as lock:
            deadline = time.monotonic() + 5
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.1)
            fcntl.flock(lock, fcntl.LOCK_UN)
        subprocess.run(['tmux', '-S', '/tmp/tmux-1000/default', 'new-session', '-d',
                        '-s', 'work2-bootstrap-direct-20260914', '-c', str(ROOT),
                        'bash /home/vipuser/work/work2/scripts/resume-bootstrap-envs.sh'], check=True)
        deadline = time.monotonic() + 20
        while True:
            state = json.loads((STAGE / 'status.json').read_text())
            new_pid = state.get('pid')
            if new_pid != parent.pid and state.get('status') == 'running':
                new = psutil.Process(new_pid)
                if str(ROOT / 'scripts/resume-bootstrap-envs.sh') not in ' '.join(new.cmdline()):
                    raise ValueError('unexpected resumed bootstrap identity')
                record['resumed_pid'] = new_pid
                record['resumed_phase'] = state['phase']
                break
            if time.monotonic() > deadline:
                raise RuntimeError('resumed bootstrap did not reach running')
            time.sleep(0.2)
        record['switch_completed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record['proxy_listener_after'] = listener_alive()
        atomic(LOG / 'transition.json', record)
    except Exception as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
        atomic(LOG / 'transition.json', record)
        raise
    finally:
        for p in reversed(suspended):
            if p.is_running() and p.status() == psutil.STATUS_STOPPED:
                p.resume()
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
