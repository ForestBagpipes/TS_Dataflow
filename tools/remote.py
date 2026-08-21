"""Small SSH helper for driving the GPU node from the workstation.

The node is reached by password rather than a key, and `ssh` on this box has no
`sshpass`, so paramiko is the only non interactive route. Everything here is
plumbing: connect, run a short command, launch a detached long run, tail a log,
pull a file back.

Launching needs care. A backgrounded process started through `exec_command`
keeps the channel open until its inherited descriptors close, so a naive
`nohup ... &` makes the caller hang until the run finishes. `launch` closes all
three descriptors and does not wait on the channel.

Usage:
    python tools/remote.py run "nvidia-smi"
    python tools/remote.py tail /root/autodl-tmp/fixcmp_xl.log 40
    python tools/remote.py get results/fix_compare.json .tmp/fix_compare.json
"""

import sys
import time
from pathlib import Path

import paramiko

HOST = "connect.bjb2.seetacloud.com"
PORT = 44405
USER = "root"
PASSWORD = "xReODsFqxx71"

#: Repository root on the node. It is synced by file copy and carries no .git,
#: which is why long runs there pass --allow-dirty-tree and lean on the code
#: hash instead.
REMOTE_ROOT = "/root/autodl-tmp/work2"
PYTHON = "/root/autodl-tmp/envs/w2/bin/python"

#: Weights are cached locally and the node cannot reach huggingface.co direct,
#: so runs go offline against the cache. Omitting these sends every backend
#: through a five deep retry before it gives up and the pool comes up short.
OFFLINE_ENV = (
    "HF_HOME=/root/autodl-tmp/.cache/huggingface "
    "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_XET=1"
)
#: For the rare command that must fetch something. The node reaches the mirror
#: but not the origin.
ONLINE_ENV = (
    "HF_HOME=/root/autodl-tmp/.cache/huggingface "
    "HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 "
    "HF_HUB_DOWNLOAD_TIMEOUT=120"
)


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              timeout=20, banner_timeout=20, auth_timeout=20)
    return c


def run(cmd, timeout=90, client=None):
    """Run a short command and return its combined output."""
    own = client is None
    c = client or connect()
    try:
        _, out, err = c.exec_command(cmd, timeout=timeout)
        text = (out.read().decode("utf-8", "replace")
                + err.read().decode("utf-8", "replace"))
        return text.strip()
    finally:
        if own:
            c.close()


def launch(cmd, log, env=OFFLINE_ENV, cwd=REMOTE_ROOT, client=None):
    """Start a detached long run and return without waiting for it.

    stdin comes from /dev/null and both output streams go to the log, so the
    exec channel has nothing left holding it open.
    """
    own = client is None
    c = client or connect()
    try:
        # Nothing is read back. Even with all three descriptors redirected the
        # exec channel can stay open behind a detached child, so waiting on it
        # is what hangs rather than anything about the child itself. The caller
        # confirms the launch with `alive` instead.
        full = (f"cd {cwd} && setsid env {env} {cmd} "
                f"< /dev/null > {log} 2>&1 &")
        c.exec_command(full, timeout=30)
        time.sleep(3)
        return "launched"
    finally:
        if own:
            c.close()


def alive(pattern, client=None):
    n = run(f"ps aux | grep -c '[{pattern[0]}]{pattern[1:]}'", client=client)
    try:
        return int(n.strip().splitlines()[-1])
    except Exception:
        return 0


def tail(log, n=40, drop_progress=True, client=None):
    """Last n log lines, with tqdm carriage return spam optionally removed."""
    filt = (" | grep -vE 'it/s\\]|Retrying|Errno 101'" if drop_progress else "")
    return run(f"tail -n {n} {log}{filt}", client=client)


def get(remote_rel, local_path, client=None):
    own = client is None
    c = client or connect()
    try:
        sftp = c.open_sftp()
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        sftp.get(f"{REMOTE_ROOT}/{remote_rel}", str(local_path))
        sftp.close()
        return local_path
    finally:
        if own:
            c.close()


def put(local_path, remote_rel, client=None):
    own = client is None
    c = client or connect()
    try:
        sftp = c.open_sftp()
        sftp.put(str(local_path), f"{REMOTE_ROOT}/{remote_rel}")
        sftp.close()
        return run(f"md5sum {REMOTE_ROOT}/{remote_rel}", client=c)
    finally:
        if own:
            c.close()


def wait(pattern, log, every=60, limit=7200, client=None):
    """Poll until the process is gone, printing the log tail as it goes."""
    own = client is None
    c = client or connect()
    try:
        t0 = time.time()
        while time.time() - t0 < limit:
            if alive(pattern, client=c) == 0:
                return "done"
            time.sleep(every)
        return "timeout"
    finally:
        if own:
            c.close()


if __name__ == "__main__":
    verb = sys.argv[1]
    if verb == "run":
        print(run(sys.argv[2], timeout=int(sys.argv[3]) if len(sys.argv) > 3 else 90))
    elif verb == "tail":
        print(tail(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 40))
    elif verb == "alive":
        print(alive(sys.argv[2]))
    elif verb == "get":
        print(get(sys.argv[2], sys.argv[3]))
    elif verb == "put":
        print(put(sys.argv[2], sys.argv[3]))
    else:
        raise SystemExit(f"unknown verb {verb}")
