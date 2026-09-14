#!/usr/bin/env python3
"""固定版本/官方哈希，直连分段下载；不安装、不修改共享代理或 Python 环境。"""
import argparse
import concurrent.futures
import hashlib
import html.parser
import json
import os
from pathlib import Path
import shutil
import time
import urllib.parse
import urllib.request

ROOT = Path('/home/vipuser/work/work2')
STAGE = Path('/home/vipuser/work2-staging/bootstrap-20260914')
BASE = ROOT / '.cache/bootstrap-direct-20260914'
LOG = ROOT / 'logs/v43/direct-switch-20260914'
CHUNK = 16 * 1024 * 1024
RATE = 2 * 1024 * 1024  # 每连接上限；4连接总上限8 MiB/s。


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def client():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.hrefs.extend(v for k, v in attrs if k == 'href')


def wheel_link(index, filename):
    with client().open(index, timeout=30) as r:
        p = Links()
        p.feed(r.read(8 * 1024 * 1024).decode())
        matches = {urllib.parse.urljoin(r.url, h) for h in p.hrefs
                   if urllib.parse.unquote(urllib.parse.urlsplit(h).path).rsplit('/', 1)[-1] == filename}
    if len(matches) != 1:
        raise ValueError(f'{index}: exact wheel matches={len(matches)}: {filename}')
    url = matches.pop()
    sha = urllib.parse.parse_qs(urllib.parse.urlsplit(url).fragment)['sha256'][0]
    return urllib.parse.urldefrag(url)[0], sha


def prepare():
    report = json.loads((STAGE / 'logs/w2-tsicl.torch-install.json').read_text())
    rows = []
    for item in report['install']:
        name, version = item['metadata']['name'], item['metadata']['version']
        original = item['download_info']['url']
        filename = urllib.parse.unquote(original.rsplit('/', 1)[-1])
        sha = item['download_info']['archive_info'].get('hashes', {}).get('sha256')
        if name in ('torch', 'triton'):
            filename = filename.replace('cp312', 'cp311')
            official, sha = wheel_link(f'https://download.pytorch.org/whl/cu126/{name}/', filename)
            url, mirror_sha = wheel_link(f'https://mirror.sjtu.edu.cn/pytorch-wheels/cu126/{name}/', filename)
            if sha != mirror_sha:
                raise ValueError(f'{name}: mirror and official hash mismatch')
        elif name.startswith('nvidia-'):
            official, url = original, original
        else:
            if 'cp312' in filename or sha is None:
                filename = filename.replace('cp312', 'cp311')
                official, sha = wheel_link(f'https://pypi.org/simple/{name.lower()}/', filename)
            else:
                official = original
            url, mirror_sha = wheel_link(f'https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/{name.lower()}/', filename)
            if sha != mirror_sha:
                raise ValueError(f'{name}: mirror and official hash mismatch')
        req = urllib.request.Request(url, headers={'Range': 'bytes=0-0'})
        with client().open(req, timeout=30) as r:
            content_range = r.headers.get('Content-Range', '')
            if r.status != 206 or not content_range.startswith('bytes 0-0/'):
                raise ValueError(f'{name}: range probe failed {r.status} {content_range}')
            size = int(content_range.split('/')[1])
            r.read(1)
            final_host = urllib.parse.urlsplit(r.url).hostname
        rows.append(dict(name=name, version=version, filename=filename, sha256=sha,
                         size_bytes=size, official_url=official, download_url=url,
                         route='direct', final_host=final_host))
        print(f'MANIFEST {name} {version} {size}', flush=True)
    atomic(LOG / 'wheel-manifest.json', dict(packages=rows, workers=4, max_mib_per_second=8,
                                           source_report_sha256=digest(STAGE / 'logs/w2-tsicl.torch-install.json')))


def fetch_chunk(task):
    row, start, end, directory = task
    target = directory / f'{start:012d}-{end:012d}.chunk'
    receipt = target.with_suffix('.json')
    if target.exists() and receipt.exists():
        saved = json.loads(receipt.read_text())
        if target.stat().st_size == end - start + 1 and digest(target) == saved['sha256']:
            return
        raise ValueError(f'corrupt saved chunk: {target}')
    partial = target.with_suffix('.incomplete')
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(row['download_url'], headers={'Range': f'bytes={start}-{end}'})
            with client().open(req, timeout=45) as r, partial.open('wb') as out:
                expected = f"bytes {start}-{end}/{row['size_bytes']}"
                if r.status != 206 or r.headers.get('Content-Range') != expected:
                    raise ValueError(f'wrong range: {r.status} {r.headers.get("Content-Range")} expected {expected}')
                total, began = 0, time.monotonic()
                while total < end - start + 1:
                    block = r.read(min(256 * 1024, end - start + 1 - total))
                    if not block:
                        raise ValueError('early EOF')
                    out.write(block)
                    total += len(block)
                    delay = total / RATE - (time.monotonic() - began)
                    if delay > 0:
                        time.sleep(delay)
                if r.read(1):
                    raise ValueError('response exceeds requested range')
            partial.replace(target)
            atomic(receipt, dict(sha256=digest(target), start=start, end=end))
            print(f'CHUNK_OK {row["name"]} {start}-{end} attempt={attempt}', flush=True)
            return
        except Exception as exc:
            print(f'CHUNK_ERROR {row["name"]} {start}-{end} attempt={attempt} {type(exc).__name__}: {exc}', flush=True)
            if attempt == 3:
                raise


def download():
    rows = json.loads((LOG / 'wheel-manifest.json').read_text())['packages']
    wheelhouse = BASE / 'wheels'
    wheelhouse.mkdir(parents=True, exist_ok=True)
    tasks, plans = [], []
    for row in rows:
        target = wheelhouse / row['filename']
        if target.exists():
            if target.stat().st_size != row['size_bytes'] or digest(target) != row['sha256']:
                raise ValueError(f'wheelhouse checksum mismatch: {target}')
            print(f'REUSE_VERIFIED {row["name"]}', flush=True)
            continue
        prefix = BASE / 'preserved' / row['filename']
        offset = prefix.stat().st_size if prefix.exists() else 0
        if offset > row['size_bytes']:
            raise ValueError(f'oversized prefix: {prefix}')
        directory = BASE / 'chunks' / row['filename']
        directory.mkdir(parents=True, exist_ok=True)
        chunks = [(row, start, min(start + CHUNK, row['size_bytes']) - 1, directory)
                  for start in range(offset, row['size_bytes'], CHUNK)]
        tasks.extend(chunks)
        plans.append((row, prefix, chunks))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for future in concurrent.futures.as_completed([pool.submit(fetch_chunk, task) for task in tasks]):
            future.result()
    verified = []
    for row, prefix, chunks in plans:
        target = wheelhouse / row['filename']
        temp = target.with_suffix('.assembling')
        with temp.open('wb') as output:
            if prefix.exists():
                with prefix.open('rb') as f:
                    shutil.copyfileobj(f, output, 4 * 1024 * 1024)
            for _, start, end, directory in chunks:
                with (directory / f'{start:012d}-{end:012d}.chunk').open('rb') as f:
                    shutil.copyfileobj(f, output, 4 * 1024 * 1024)
        if temp.stat().st_size != row['size_bytes'] or digest(temp) != row['sha256']:
            raise ValueError(f'complete official SHA256 mismatch: {temp}')
        temp.replace(target)
        print(f'WHEEL_VERIFIED {row["name"]} {row["sha256"]}', flush=True)
    for row in rows:
        target = wheelhouse / row['filename']
        if digest(target) != row['sha256']:
            raise ValueError(f'final checksum mismatch: {target}')
        verified.append(dict(**row, local_path=str(target)))
    atomic(LOG / 'verified-wheels.json', dict(status='completed', packages=verified))
    (LOG / 'chronos-torch-local.txt').write_text(''.join(
        f"{row['local_path']} --hash=sha256:{row['sha256']}\n" for row in verified))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'download'))
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else download)()
