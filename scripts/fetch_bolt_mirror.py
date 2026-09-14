#!/usr/bin/env python3
"""下载已与官方LFS哈希匹配的Bolt副本到独立文件；不写正在使用的HF缓存。"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

from download_bootstrap_wheels import atomic, digest, ROOT


def main():
    logdir = ROOT / 'logs/v43/bolt-mirror-20260914'
    logdir.mkdir(parents=True, exist_ok=True)
    base = ROOT / '.cache/bolt-mirror-20260914'
    base.mkdir(parents=True, exist_ok=True)
    with (base / 'download.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        route = json.loads((ROOT / 'logs/v43/direct-switch-20260914/bolt-modelscope-route.json').read_text())
        record = json.loads(Path('/home/vipuser/work2-staging/bootstrap-20260914/logs/models/bolt.record.json').read_text())
        expected = record['repository_files']['model.safetensors']
        assert route['expected_sha256'] == expected['lfs_sha256']
        assert route['expected_bytes'] == expected['size']
        partial, complete = base / 'model.safetensors.incomplete', base / 'model.safetensors'
        state = dict(status='downloading', pid=os.getpid(), started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     source_url=route['url'], source_revision=route['revision'], official_repo=record['repo_id'],
                     official_revision=record['revision'], expected_sha256=expected['lfs_sha256'],
                     expected_bytes=expected['size'], path=str(partial), route='direct', limit_mib_per_second=4,
                     shared_proxy_modified=False, live_hf_cache_modified=False)

        def save():
            state['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            atomic(logdir / 'status.json', state)
            atomic(ROOT / 'results/v43/bolt_mirror_status.json', state)

        try:
            assert not complete.exists(), 'completed mirror artifact already exists; inspect before reuse'
            command = ['curl', '--noproxy', '*', '--location', '--continue-at', '-', '--retry', '2',
                       '--retry-delay', '2', '--fail', '--max-time', '900', '--connect-timeout', '15',
                       '--limit-rate', '4M', '--silent', '--show-error', '--output', str(partial), route['url']]
            with (logdir / 'curl.log').open('a') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                state['download_pid'] = process.pid
                save()
                while process.poll() is None:
                    state['downloaded_bytes'] = partial.stat().st_size if partial.exists() else 0
                    save()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        pass
                assert process.returncode == 0, f'curl failed: {process.returncode}'
            state.update(status='verifying', downloaded_bytes=partial.stat().st_size)
            save()
            assert partial.stat().st_size == expected['size'], 'mirror size mismatch'
            checksum = digest(partial)
            assert checksum == expected['lfs_sha256'], 'mirror differs from official SHA256'
            partial.replace(complete)
            state.update(status='verified', path=str(complete), sha256=checksum)
            save()
        except Exception as exc:
            state.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            save()
            raise


if __name__ == '__main__':
    main()
