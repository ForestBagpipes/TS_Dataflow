#!/usr/bin/env python3
"""Minimal paramiko helper for the v54 server run. Not for secrets storage."""
from __future__ import annotations

import sys
import paramiko

HOSTS = [("223.109.239.30", 23524), ("180.127.11.167", 23524)]
USER = "vipuser"
PASSWORD = "Eenaec9b"


def connect() -> paramiko.SSHClient:
    last = None
    for host, port in HOSTS:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(host, port=port, username=USER, password=PASSWORD,
                           timeout=15, allow_agent=False, look_for_keys=False)
            return client
        except Exception as exc:  # noqa: BLE001
            last = exc
            try:
                client.close()
            except Exception:
                pass
    raise SystemExit(f"SSH connect failed on all hosts: {last}")


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 600) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")


def main() -> None:
    client = connect()
    try:
        mode = sys.argv[1]
        if mode == "exec":
            code, out, err = run(client, sys.argv[2],
                                 timeout=int(sys.argv[3]) if len(sys.argv) > 3 else 600)
            sys.stdout.write(out)
            sys.stderr.write(err)
            sys.exit(code)
        elif mode == "put":
            sftp = client.open_sftp()
            sftp.put(sys.argv[2], sys.argv[3])
            sftp.close()
            print("put ok")
        elif mode == "get":
            sftp = client.open_sftp()
            sftp.get(sys.argv[2], sys.argv[3])
            sftp.close()
            print("get ok")
        else:
            raise SystemExit("usage: ssh_v54.py exec|put|get ...")
    finally:
        client.close()


if __name__ == "__main__":
    main()
