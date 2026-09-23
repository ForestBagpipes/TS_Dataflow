#!/usr/bin/env python3
"""Transfer helper for the v54 server.

The host's SFTP subsystem refuses absolute paths (every open returns ENOENT),
so files move as base64 over the exec channel instead.  Small payloads only --
a few MB at most.

usage:
  ssh_v54_sync.py pull <remote_path> <local_path>
  ssh_v54_sync.py push <local_path> <remote_path>
  ssh_v54_sync.py exec <command> [timeout]
"""
from __future__ import annotations

import base64
import pathlib
import shlex
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ssh_v54 import connect, run  # noqa: E402


def main() -> None:
    mode = sys.argv[1]
    client = connect()
    try:
        if mode == "pull":
            code, out, err = run(client, f"base64 -w0 {shlex.quote(sys.argv[2])}",
                                 timeout=600)
            if code != 0:
                raise SystemExit(f"remote read failed: {err[:400]}")
            pathlib.Path(sys.argv[3]).write_bytes(base64.b64decode(out))
            print(f"pulled {len(out)} b64 chars -> {sys.argv[3]}")
        elif mode == "push":
            blob = base64.b64encode(
                pathlib.Path(sys.argv[2]).read_bytes()).decode()
            remote = shlex.quote(sys.argv[3])
            code, out, err = run(
                client, f"printf '%s' {shlex.quote(blob)} | base64 -d > {remote}",
                timeout=600)
            if code != 0:
                raise SystemExit(f"remote write failed: {err[:400]}")
            print(f"pushed {len(blob)} b64 chars -> {sys.argv[3]}")
        elif mode == "exec":
            code, out, err = run(client, sys.argv[2],
                                 timeout=int(sys.argv[3]) if len(sys.argv) > 3 else 600)
            sys.stdout.write(out)
            sys.stderr.write(err)
            sys.exit(code)
        else:
            raise SystemExit(__doc__)
    finally:
        client.close()


if __name__ == "__main__":
    main()
