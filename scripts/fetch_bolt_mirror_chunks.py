#!/usr/bin/env python3
"""复用单流镜像前缀，以4路小段补齐同一官方SHA256权重。"""
import concurrent.futures
import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil

import download_bootstrap_wheels as transport
from download_bootstrap_wheels import ROOT, atomic, digest, fetch_chunk


def main():
    base = ROOT / '.cache/bolt-mirror-20260914'
    logs = ROOT / 'logs/v43/bolt-mirror-20260914'
    with (base / 'download.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior = json.loads((logs / 'status.json').read_text())
        assert prior['status'] == 'failed' and 'curl failed: -15' in prior['error']
        atomic(logs / 'single-stream-final-status.json', prior)
        prefix = base / 'single-stream-prefix'
        assert not prefix.exists()
        (base / 'model.safetensors.incomplete').rename(prefix)
        offset = prefix.stat().st_size
        assert 0 < offset < prior['expected_bytes']
        state = dict(status='downloading_chunks', pid=os.getpid(), route='direct', workers=4,
                     limit_mib_per_second=4, expected_bytes=prior['expected_bytes'],
                     expected_sha256=prior['expected_sha256'], official_revision=prior['official_revision'],
                     source_url=prior['source_url'], source_revision=prior['source_revision'],
                     prefix_bytes=offset, prefix_sha256=digest(prefix),
                     started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     shared_proxy_modified=False, live_hf_cache_modified=False)
        directory = base / 'chunks'
        directory.mkdir(exist_ok=True)
        row = dict(name='bolt', download_url=prior['source_url'], size_bytes=prior['expected_bytes'])
        chunks = [(row, start, min(start + 4 * 1048576, prior['expected_bytes']) - 1, directory)
                  for start in range(offset, prior['expected_bytes'], 4 * 1048576)]

        def save():
            state['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            state['downloaded_bytes'] = offset + sum(p.stat().st_size for p in directory.glob('*.chunk'))
            atomic(logs / 'status.json', state)
            atomic(ROOT / 'results/v43/bolt_mirror_status.json', state)

        try:
            transport.RATE = 1048576  # Four connections, each capped at 1 MiB/s.
            save()
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                for future in concurrent.futures.as_completed([pool.submit(fetch_chunk, chunk) for chunk in chunks]):
                    future.result()
                    save()
            target = base / 'model.safetensors'
            assert not target.exists()
            partial = base / 'model.safetensors.assembling'
            state['status'] = 'verifying'
            save()
            with partial.open('wb') as output:
                with prefix.open('rb') as f:
                    shutil.copyfileobj(f, output, 4 * 1048576)
                for _, start, end, folder in chunks:
                    with (folder / f'{start:012d}-{end:012d}.chunk').open('rb') as f:
                        shutil.copyfileobj(f, output, 4 * 1048576)
            assert partial.stat().st_size == prior['expected_bytes'], 'mirror size mismatch'
            checksum = digest(partial)
            assert checksum == prior['expected_sha256'], 'mirror official SHA256 mismatch'
            partial.replace(target)
            state.update(status='verified', path=str(target), sha256=checksum)
            save()
        except Exception as exc:
            state.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            save()
            raise


if __name__ == '__main__':
    main()
