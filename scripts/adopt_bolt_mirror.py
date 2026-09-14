#!/usr/bin/env python3
"""完整官方哈希通过后，串行替换本项目未完成的Bolt传输并接续验收。"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import psutil
from download_bootstrap_wheels import ROOT, STAGE, atomic, digest
from switch_bootstrap_downloads import listener_alive, terminate_owned


def owned(pid, fragment):
    p = psutil.Process(pid)
    assert p.uids().real == os.getuid() and fragment in ' '.join(p.cmdline())
    return p


def main():
    logs = ROOT / 'logs/v43/bolt-mirror-20260914'
    assert not (logs / 'adoption.json').exists(), 'existing transition must be reviewed and preserved'
    state = json.loads((logs / 'status.json').read_text())
    assert state['status'] == 'verified'
    source = Path(state['path'])
    model = json.loads((STAGE / 'logs/models/bolt.record.json').read_text())
    expected = model['repository_files']['model.safetensors']
    assert state['official_revision'] == model['revision']
    assert source.stat().st_size == expected['size']
    assert digest(source) == expected['lfs_sha256'] == state['sha256']
    receipt = dict(status='verified_pending_adoption', at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   mirror=state, official_revision=model['revision'], proxy_listener_before=listener_alive(),
                   codex_or_proxy_configuration_modified=False)
    if model['status'] in ('ready', 'downloaded_pending_inference'):
        receipt['status'] = 'original_download_finished_no_replacement'
        atomic(logs / 'adoption.json', receipt)
        print(receipt['status'])
        return
    assert model['status'] == 'pending_download'
    continuation = json.loads((STAGE / 'continuation-status.json').read_text())
    assert continuation['status'] == 'preparing_models'
    outer = owned(continuation['pid'], str(STAGE / 'after-env-bootstrap.py'))
    parents = [p for p in outer.children() if str(STAGE / 'prepare-models.py') in p.cmdline()]
    assert len(parents) == 1
    controller = owned(parents[0].pid, str(STAGE / 'prepare-models.py'))
    children = [p for p in controller.children() if '--action' in p.cmdline() and 'download' in p.cmdline() and 'bolt' in p.cmdline()]
    assert len(children) == 1, 'original download advanced; inspect rather than interrupt inference'
    child = owned(children[0].pid, str(STAGE / 'prepare-models.py'))
    queued = json.loads((ROOT / 'results/v43/pilot_queue_status.json').read_text())
    assert queued['status'] == 'waiting_for_models'
    queue = owned(queued['pid'], 'scripts/run_v43_pilot_queue.py')
    hub = Path(os.environ['HF_HOME']) / 'hub'
    storage = hub / 'models--amazon--chronos-bolt-base'
    snapshot = storage / 'snapshots' / model['revision']
    assert (snapshot / 'config.json').is_file()
    lock_path = hub / '.locks/models--amazon--chronos-bolt-base' / (state['sha256'] + '.lock')
    assert lock_path.is_file(), 'expected actual HF lock must already exist'
    receipt['old_processes'] = [dict(pid=p.pid, created_at=p.create_time()) for p in (outer, controller, child)]
    atomic(logs / 'adoption.json', receipt)
    suspended = []
    try:
        for p in (queue, outer, controller, child):
            p.suspend()
            suspended.append(p)
        backup = logs / 'before-adoption'
        backup.mkdir(exist_ok=False)
        for p in (STAGE / 'logs/models').glob('*.record.json'):
            shutil.copy2(p, backup / p.name)
        shutil.copy2(ROOT / 'configs/v43/model_manifest.bootstrap.json', backup / 'model-manifest.json')
        shutil.copy2(STAGE / 'continuation-status.json', backup / 'continuation-status.json')
        for partial in (storage / 'blobs').glob(state['sha256'] + '*.incomplete'):
            target = backup / partial.name
            shutil.copy2(partial, target)
            receipt.setdefault('preserved_unverified_partials', []).append(dict(path=str(target), bytes=target.stat().st_size))
        for p in (child, controller, outer):
            terminate_owned(p)
        receipt['status'] = 'old_transport_stopped'
        atomic(logs / 'adoption.json', receipt)
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            blob = storage / 'blobs' / state['sha256']
            if blob.exists():
                assert digest(blob) == state['sha256']
            else:
                temp = blob.with_name(blob.name + '.verified-mirror-tmp')
                assert not temp.exists()
                shutil.copy2(source, temp)
                assert digest(temp) == state['sha256']
                temp.replace(blob)
            pointer = snapshot / 'model.safetensors'
            if pointer.exists():
                assert digest(pointer) == state['sha256']
            else:
                pointer.symlink_to(os.path.relpath(blob, snapshot))
            receipt['cache_path'] = str(pointer)
        receipt['status'] = 'imported_verified_mirror'
        atomic(logs / 'adoption.json', receipt)
        subprocess.run(['tmux', '-S', '/tmp/tmux-1000/default', 'new-session', '-d',
                        '-s', 'work2-after-bolt-mirror-20260914', '-c', str(ROOT),
                        'source scripts/env_new_server.sh && exec "$W2_CORE_PY" /home/vipuser/work2-staging/bootstrap-20260914/after-env-bootstrap.py >> logs/v43/bolt-mirror-20260914/resume-models.log 2>&1'], check=True)
        deadline = time.monotonic() + 15
        while True:
            resumed = json.loads((STAGE / 'continuation-status.json').read_text())
            if resumed.get('pid') != outer.pid and resumed.get('status') in ('preparing_models', 'completed'):
                receipt['resumed_pid'] = resumed['pid']
                break
            assert time.monotonic() < deadline, 'model continuation did not resume'
            time.sleep(.2)
        receipt['proxy_listener_after'] = listener_alive()
        receipt['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        atomic(logs / 'adoption.json', receipt)
    except Exception as exc:
        receipt['error'] = f'{type(exc).__name__}: {exc}'
        atomic(logs / 'adoption.json', receipt)
        raise
    finally:
        for p in reversed(suspended):
            try:
                if p.is_running() and p.status() == psutil.STATUS_STOPPED:
                    p.resume()
            except psutil.NoSuchProcess:
                pass
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
