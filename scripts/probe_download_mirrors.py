#!/usr/bin/env python3
"""只读探测固定 wheel 的索引与有限文件头；不安装或更改环境。"""
import argparse
import concurrent.futures
import datetime
import html.parser
import json
import pathlib
import time
import urllib.parse
import urllib.request


class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(v for k, v in attrs if k == "href")


def opener(route):
    proxies = {} if route == "direct" else {
        "http": "http://127.0.0.1:17890", "https": "http://127.0.0.1:17890"}
    return urllib.request.build_opener(urllib.request.ProxyHandler(proxies))


def probe(task):
    label, index, filename, route, sample_bytes = task
    result = {"label": label, "index": index, "filename": filename, "route": route}
    start = time.monotonic()
    try:
        client = opener(route)
        with client.open(index, timeout=15) as response:
            parser = Links()
            parser.feed(response.read(4 * 1024 * 1024).decode())
            links = [urllib.parse.urljoin(response.url, h) for h in parser.hrefs
                     if urllib.parse.unquote(urllib.parse.urlsplit(h).path).rsplit("/", 1)[-1] == filename]
        result["index_seconds"] = round(time.monotonic() - start, 3)
        if len(set(links)) != 1:
            raise ValueError(f"expected one exact wheel link; got {len(set(links))}")
        url = links[0]
        result["url"] = url
        result["index_sha256"] = urllib.parse.parse_qs(urllib.parse.urlsplit(url).fragment).get("sha256", [None])[0]
        start = time.monotonic()
        request = urllib.request.Request(urllib.parse.urldefrag(url)[0], headers={"Range": f"bytes=0-{sample_bytes - 1}"})
        with client.open(request, timeout=15) as response:
            data = response.read(sample_bytes)
            result.update(final_url=response.url, http_status=response.status,
                          content_type=response.headers.get("Content-Type"),
                          content_range=response.headers.get("Content-Range"),
                          cache_control=response.headers.get("Cache-Control"),
                          bytes=len(data), zip_magic=data[:4] == b"PK\x03\x04")
        elapsed = time.monotonic() - start
        result.update(sample_seconds=round(elapsed, 3), mib_per_second=round(len(data) / 1048576 / elapsed, 3))
        result["status"] = "sample_ok" if result["zip_magic"] else "invalid_wheel_response"
        result["whole_file_verified"] = False
    except Exception as exc:
        result.update(status="error", error=f"{type(exc).__name__}: {exc}")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--sample-mib", type=int, choices=range(1, 9), default=1)
    p.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = p.parse_args()
    torch = "torch-2.9.1+cu126-cp311-cp311-manylinux_2_28_x86_64.whl"
    cudnn = "nvidia_cudnn_cu12-9.10.2.21-py3-none-manylinux_2_27_x86_64.whl"
    sources = [
        ("pytorch_official", "https://download.pytorch.org/whl/cu126/torch/", torch),
        ("sjtu_torch", "https://mirror.sjtu.edu.cn/pytorch-wheels/cu126/torch/", torch),
        ("nvidia_official", "https://download.pytorch.org/whl/cu126/nvidia-cudnn-cu12/", cudnn),
        ("tuna_cudnn", "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/nvidia-cudnn-cu12/", cudnn),
    ]
    tasks = [(*s, route, args.sample_mib * 1048576) for s in sources for route in ("direct", "server_proxy")]
    report = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "purpose": "bounded route diagnosis, not an installation or full checksum verification",
              "sample_max_bytes": args.sample_mib * 1048576, "workers": args.workers, "results": []}
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(probe, task) for task in tasks]):
            result = future.result()
            report["results"].append(result)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
