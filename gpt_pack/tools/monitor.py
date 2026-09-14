"""Run monitoring for long jobs. Assert before, heartbeat during, manifest after.

Three failures motivated this, all of them real and all of them silent at the
time they happened.

**A run on stale code.** The container has been reassigned twice. A run started
after a reassignment used a `types.py` that was several commits behind the
local one and failed only when it reached a method that did not exist yet. A
degraded environment that does not raise is worse, an xl ablation ran to
completion on two backends instead of three and its numbers were not comparable
to anything.

**A run whose state could not be told apart from a dead one.** Tailing a log
answers whether output appeared recently, not whether the process is making
progress, and not whether the file it claims to be writing is actually growing.

**A result file that never left the container.** `utility_only_gate.json` sat
untracked on disk while its numbers were being quoted in a report.

So: assertions that abort before the main loop rather than warn, a heartbeat
carrying the mtime of what is being written, and a manifest that stages the
outputs into git when the run ends.

Usage from an experiment:

    from monitor import Monitor
    mon = Monitor("spo_learning", expects=["results/spo_learning.json"],
                  config={"k": 12, "split_seed": 20260818, "reward_clip": 5.887,
                          "alpha": 0.02, "c_u": 1.0},
                  require_pool=3)
    mon.start()                          # asserts, then writes the run record
    for i, w in enumerate(windows):
        ...
        mon.beat("curating", done=i + 1, total=len(windows))
    mon.finish()                         # md5, line counts, git add

Query from a laptop:

    python tools/monitor.py status       # local
    python tools/monitor.py status --remote
"""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
HEARTBEAT = LOGS / "heartbeat.jsonl"
MANIFEST = LOGS / "manifest.jsonl"
RUNS = LOGS / "runs.jsonl"

#: Abort if the volume holding the outputs has less than this free.
MIN_FREE_GB = 5.0

#: Every key that must appear in a learning run's config hash. Adding a
#: hyperparameter without adding it here leaves it outside the assertion, which
#: is how reward_clip escaped on the first xl run. `test_monitor` checks this
#: list against docs/spo_preregistration.md so the two cannot drift.
LEARN_CONFIG_KEYS = (
    "k", "split_seed", "corpus_seed", "scale", "alpha", "c_u", "c0",
    "optimistic_init", "warm_start_cap", "tail_floor", "reward_clip",
    "p_inject", "t_cal",
)

#: Default seconds between heartbeat lines. `beat` is cheap to call in a tight
#: loop, it only writes when this much time has passed.
BEAT_EVERY = 30.0


def _git(*args, cwd=ROOT):
    try:
        out = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                             text=True, timeout=30)
        return out.stdout.strip(), out.returncode
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}", 1


def config_hash(config: dict) -> str:
    """Stable hash of the run's decisive settings.

    Sorted keys and a fixed float format, so the same configuration hashes the
    same on two machines with different dict ordering or repr precision.
    """
    norm = {k: (f"{v:.10g}" if isinstance(v, float) else v)
            for k, v in sorted(config.items())}
    blob = json.dumps(norm, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


#: Source files whose content decides what a run computes. Their combined hash
#: is the version marker, and it is the marker rather than the git commit
#: because the node is synced by rsync and carries no `.git`, so `git rev-parse`
#: returns empty there. A hash over the actual bytes answers the question the
#: commit was meant to answer, namely whether the code that ran is the code that
#: is being reported.
CODE_FILES = (
    "src/introact_ts/spo.py",
    "src/introact_ts/agent.py",
    "src/introact_ts/policy.py",
    "src/introact_ts/verify.py",
    "src/introact_ts/types.py",
    "src/introact_ts/conformal.py",
    "src/introact_ts/structure.py",
)


def code_hash(files=CODE_FILES, root=None):
    """Combined hash of the method layer, plus the per file digests.

    Returns (combined, {relative path: md5 or 'MISSING'}). A missing file is
    recorded rather than skipped, so a truncated deployment does not silently
    produce the same hash as a complete one.
    """
    base = Path(root) if root else ROOT
    per = {}
    h = hashlib.sha256()
    for rel in files:
        p = base / rel
        if p.exists():
            d = file_md5(p)
        else:
            d = "MISSING"
        per[rel] = d
        h.update(rel.encode("utf-8"))
        h.update(d.encode("utf-8"))
    return h.hexdigest()[:16], per


def file_md5(path: Path, chunk=1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def line_count(path: Path) -> int:
    """Lines for text, or -1 for something that is not decodable as text."""
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except Exception:
        return -1


class PreflightError(RuntimeError):
    """Raised when a start assertion fails. The caller must not continue."""


class Monitor:
    """One long run's assertions, heartbeat and manifest."""

    def __init__(self, name, expects=None, config=None, require_pool=None,
                 require_clean_tree=True, expect_config_hash=None,
                 expect_code_hash=None,
                 beat_every=BEAT_EVERY, min_free_gb=MIN_FREE_GB):
        self.name = name
        self.expects = [str(p) for p in (expects or [])]
        self.config = dict(config or {})
        self.require_pool = require_pool
        self.require_clean_tree = require_clean_tree
        self.expect_config_hash = expect_config_hash
        self.expect_code_hash = expect_code_hash
        self.beat_every = float(beat_every)
        self.min_free_gb = float(min_free_gb)
        self.t0 = time.time()
        self._last_beat = 0.0
        self.run_id = f"{name}-{int(self.t0)}-{os.getpid()}"
        LOGS.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- asserts

    def preflight(self, pool_size=None):
        """Every check that must hold before the main loop. Raises on failure.

        Returns the list of checks with their outcomes, so a caller that wants
        to log the passing ones can.
        """
        checks = []

        def add(nameate, ok, detail):
            checks.append({"check": nameate, "ok": bool(ok), "detail": detail})

        # 1. Backend pool. make_pool skips a backend that fails to load and only
        #    raises when none load, which is right for it and wrong here.
        if self.require_pool is not None:
            add("pool_size", pool_size == self.require_pool,
                f"expected {self.require_pool}, got {pool_size}")

        # 2. Working tree. A dirty tree means the code that ran cannot be
        #    recovered from the commit the run records.
        status, rc = _git("status", "--porcelain")
        if self.require_clean_tree:
            add("clean_tree", rc == 0 and not status,
                "clean" if not status else status[:400])

        # 3. Config hash against what the pre registration fixed.
        #
        # This is mandatory rather than optional. The first xl learning run was
        # started without it and its config silently omitted reward_clip, so it
        # hashed differently from the pre registration and nothing stopped it.
        # The omission was found afterwards by reading the log. An assertion
        # that callers may skip is an assertion that will be skipped on the run
        # that needed it, so a missing expected hash is now a failure.
        h = config_hash(self.config)
        if self.config and not self.expect_config_hash:
            add("config_hash", False,
                "no expected hash was supplied, pass expect_config_hash "
                f"(this run would hash to {h})")
        elif self.expect_config_hash:
            add("config_hash", h == self.expect_config_hash,
                f"expected {self.expect_config_hash}, got {h}")

        # 4. Code hash. On the node there is no `.git`, so the commit field is
        #    empty and cannot catch a stale deployment. This compares the method
        #    layer's actual bytes against what the caller expects.
        ch, per_file = code_hash()
        missing = [k for k, v in per_file.items() if v == "MISSING"]
        add("code_present", not missing,
            "all present" if not missing else f"missing {missing}")
        if self.expect_code_hash:
            add("code_hash", ch == self.expect_code_hash,
                f"expected {self.expect_code_hash}, got {ch}")

        # 5. Output paths writable.
        for rel in self.expects:
            p = (ROOT / rel).parent
            try:
                p.mkdir(parents=True, exist_ok=True)
                probe = p / f".w_{os.getpid()}"
                probe.write_text("x", encoding="utf-8")
                probe.unlink()
                add(f"writable:{rel}", True, str(p))
            except Exception as exc:
                add(f"writable:{rel}", False, f"{type(exc).__name__}: {exc}")

        # 6. Free space.
        free_gb = shutil.disk_usage(str(ROOT)).free / 2**30
        add("disk_free", free_gb >= self.min_free_gb,
            f"{free_gb:.1f} GB free, need {self.min_free_gb}")

        failed = [c for c in checks if not c["ok"]]
        if failed:
            lines = "\n".join(f"  FAIL {c['check']}: {c['detail']}" for c in failed)
            raise PreflightError(
                f"{len(failed)} preflight check(s) failed for run {self.name}, "
                f"not entering the main loop\n{lines}")
        return checks

    # ------------------------------------------------------------------ start

    def start(self, pool_size=None):
        checks = self.preflight(pool_size=pool_size)
        commit, _ = _git("rev-parse", "HEAD")
        branch, _ = _git("rev-parse", "--abbrev-ref", "HEAD")
        rec = {
            "event": "start",
            "run_id": self.run_id,
            "name": self.name,
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.t0)),
            "started_epoch": self.t0,
            "git_commit": commit,
            "git_branch": branch,
            "config": self.config,
            "config_hash": config_hash(self.config),
            "code_hash": code_hash()[0],
            "code_files": code_hash()[1],
            "pool_size": pool_size,
            "expects": self.expects,
            "python": sys.version.split()[0],
            "cwd": str(ROOT),
            "checks": checks,
        }
        with open(RUNS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        print(f"[monitor] {self.run_id} started, commit {commit[:8]}, "
              f"config {rec['config_hash']}, {len(checks)} checks passed",
              flush=True)
        self.beat("start", done=0, total=1, force=True)
        return rec

    # -------------------------------------------------------------- heartbeat

    def beat(self, stage, done=None, total=None, force=False, **extra):
        """Append a heartbeat line, at most once per `beat_every` seconds.

        The line carries the mtime and size of the most recently touched
        expected output, which is what distinguishes a run that is working from
        one that is looping without producing anything.
        """
        now = time.time()
        if not force and (now - self._last_beat) < self.beat_every:
            return
        self._last_beat = now

        newest = None
        for rel in self.expects:
            p = ROOT / rel
            if p.exists():
                st = p.stat()
                if newest is None or st.st_mtime > newest["mtime_epoch"]:
                    newest = {
                        "file": rel, "bytes": st.st_size,
                        "mtime_epoch": st.st_mtime,
                        "mtime": time.strftime("%H:%M:%S",
                                               time.localtime(st.st_mtime)),
                        "age_s": round(now - st.st_mtime, 1),
                    }

        rec = {
            "event": "beat", "run_id": self.run_id, "name": self.name,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "ts_epoch": now,
            "elapsed_s": round(now - self.t0, 1),
            "stage": stage,
            "done": done, "total": total,
            "frac": (round(done / total, 4) if (done is not None and total) else None),
            "newest_output": newest,
        }
        rec.update(extra)
        with open(HEARTBEAT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    # ----------------------------------------------------------------- finish

    def finish(self, ok=True, note="", git_add=True):
        """Record md5 and line counts of every output, then stage them."""
        files = []
        for rel in self.expects:
            p = ROOT / rel
            if not p.exists():
                files.append({"file": rel, "exists": False})
                continue
            files.append({
                "file": rel, "exists": True, "bytes": p.stat().st_size,
                "md5": file_md5(p), "lines": line_count(p),
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S",
                                       time.localtime(p.stat().st_mtime)),
            })

        staged, stage_err = [], None
        if git_add:
            present = [f["file"] for f in files if f.get("exists")]
            if present:
                out, rc = _git("add", "--", *present)
                if rc == 0:
                    staged = present
                else:
                    stage_err = out

        commit, _ = _git("rev-parse", "HEAD")
        rec = {
            "event": "finish", "run_id": self.run_id, "name": self.name,
            "ok": bool(ok), "note": note,
            "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_s": round(time.time() - self.t0, 1),
            "git_commit": commit, "config_hash": config_hash(self.config),
            "code_hash": code_hash()[0],
            "files": files, "staged": staged, "stage_error": stage_err,
        }
        with open(MANIFEST, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self.beat("finish", done=1, total=1, force=True)
        missing = [f["file"] for f in files if not f.get("exists")]
        print(f"[monitor] {self.run_id} finished in {rec['elapsed_s']:.0f}s, "
              f"{len(staged)} staged"
              + (f", MISSING {missing}" if missing else ""), flush=True)
        return rec

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.finish(ok=exc_type is None,
                    note="" if exc_type is None else f"{exc_type.__name__}: {exc}")
        return False


# ------------------------------------------------------------------ query CLI


def _tail_jsonl(path, n):
    if not Path(path).exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows[-n:]


def status(logs_dir=LOGS, stale_after=180.0):
    """Alive, stalled or done, judged from the heartbeat rather than a log tail."""
    beats = _tail_jsonl(Path(logs_dir) / "heartbeat.jsonl", 4000)
    fins = _tail_jsonl(Path(logs_dir) / "manifest.jsonl", 200)
    finished = {r["run_id"] for r in fins}
    latest = {}
    for b in beats:
        latest[b["run_id"]] = b

    now = time.time()
    out = []
    for rid, b in sorted(latest.items(), key=lambda kv: kv[1]["ts_epoch"]):
        age = now - b["ts_epoch"]
        if rid in finished:
            state = "done"
        elif age > stale_after:
            state = "stalled"
        else:
            state = "alive"
        out.append({"run_id": rid, "name": b["name"], "state": state,
                    "stage": b.get("stage"), "frac": b.get("frac"),
                    "beat_age_s": round(age, 1),
                    "elapsed_s": b.get("elapsed_s"),
                    "newest_output": b.get("newest_output")})
    return out


def print_status(rows):
    if not rows:
        print("no runs recorded")
        return
    print(f"{'state':<9s}{'name':<22s}{'stage':<16s}{'frac':>7s}"
          f"{'beat age':>10s}{'elapsed':>9s}  newest output")
    for r in rows:
        no = r["newest_output"]
        nos = (f"{no['file']} {no['bytes']}B age {no['age_s']}s" if no else "none")
        frac = f"{r['frac']:.1%}" if r.get("frac") is not None else "-"
        print(f"{r['state']:<9s}{r['name']:<22s}{str(r['stage'])[:15]:<16s}{frac:>7s}"
              f"{r['beat_age_s']:>9.0f}s{r['elapsed_s'] or 0:>8.0f}s  {nos}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="alive, stalled or done")
    st.add_argument("--remote", action="store_true",
                    help="pull logs from the node first, needs W2_PASS and W2_PORT")
    st.add_argument("--stale-after", type=float, default=180.0)
    args = ap.parse_args()

    if args.cmd == "status":
        logs = LOGS
        if args.remote:
            logs = _pull_remote_logs()
        print_status(status(logs, stale_after=args.stale_after))


def _pull_remote_logs():
    """Fetch heartbeat and manifest from the node into a local scratch dir."""
    sys.path.insert(0, os.path.expanduser("~/.w2tools"))
    import remote  # noqa

    dest = LOGS / "remote"
    dest.mkdir(parents=True, exist_ok=True)
    c = remote.client()
    sf = c.open_sftp()
    got = []
    for fn in ("heartbeat.jsonl", "manifest.jsonl", "runs.jsonl"):
        r = f"/root/autodl-tmp/work2/logs/{fn}"
        try:
            sf.get(r, str(dest / fn))
            got.append(fn)
        except Exception as exc:
            print(f"[monitor] could not fetch {fn}: {type(exc).__name__}")
    sf.close()
    c.close()
    print(f"[monitor] pulled {got} into {dest}")
    return dest


if __name__ == "__main__":
    main()
