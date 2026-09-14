"""Monitor preflight, heartbeat and manifest."""
import json
import time
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from monitor import (Monitor, PreflightError, config_hash, status)


def test_config_hash_is_order_and_precision_stable():
    a = config_hash({"k": 12, "c_u": 1.0, "seed": 20260818})
    b = config_hash({"seed": 20260818, "c_u": 1.00000000001, "k": 12})
    assert a == b
    assert config_hash({"k": 12}) != config_hash({"k": 10})


def test_preflight_aborts_on_wrong_pool_size():
    m = Monitor("t", require_pool=3, require_clean_tree=False)
    with pytest.raises(PreflightError) as e:
        m.preflight(pool_size=2)
    assert "pool_size" in str(e.value)


def test_preflight_aborts_on_config_hash_mismatch():
    m = Monitor("t", config={"k": 12}, require_clean_tree=False,
                expect_config_hash="deadbeefdeadbeef")
    with pytest.raises(PreflightError) as e:
        m.preflight()
    assert "config_hash" in str(e.value)


def test_preflight_passes_when_everything_holds():
    m = Monitor("t", config={"k": 12}, require_pool=3, require_clean_tree=False,
                expect_config_hash=config_hash({"k": 12}))
    checks = m.preflight(pool_size=3)
    assert all(c["ok"] for c in checks)


def test_heartbeat_rate_limits_but_force_wins(tmp_path, monkeypatch):
    import monitor as M
    monkeypatch.setattr(M, "HEARTBEAT", tmp_path / "hb.jsonl")
    m = Monitor("t", require_clean_tree=False, beat_every=999)
    m.beat("a", force=True)
    m.beat("b")            # rate limited away
    m.beat("c", force=True)
    rows = [json.loads(l) for l in (tmp_path / "hb.jsonl").read_text().splitlines()]
    assert [r["stage"] for r in rows] == ["a", "c"]


def test_heartbeat_carries_newest_output_age(tmp_path, monkeypatch):
    import monitor as M
    monkeypatch.setattr(M, "HEARTBEAT", tmp_path / "hb.jsonl")
    monkeypatch.setattr(M, "ROOT", tmp_path)
    out = tmp_path / "r.json"
    out.write_text('{"x": 1}')
    m = Monitor("t", expects=["r.json"], require_clean_tree=False)
    m.beat("work", done=3, total=10, force=True)
    rec = json.loads((tmp_path / "hb.jsonl").read_text().splitlines()[-1])
    assert rec["frac"] == 0.3
    assert rec["newest_output"]["file"] == "r.json"
    assert rec["newest_output"]["age_s"] < 5


def test_manifest_records_md5_and_flags_missing(tmp_path, monkeypatch):
    import monitor as M
    monkeypatch.setattr(M, "MANIFEST", tmp_path / "mf.jsonl")
    monkeypatch.setattr(M, "HEARTBEAT", tmp_path / "hb.jsonl")
    monkeypatch.setattr(M, "ROOT", tmp_path)
    (tmp_path / "there.json").write_text("a\nb\n")
    m = Monitor("t", expects=["there.json", "gone.json"], require_clean_tree=False)
    rec = m.finish(git_add=False)
    by = {f["file"]: f for f in rec["files"]}
    assert by["there.json"]["lines"] == 2
    assert len(by["there.json"]["md5"]) == 32
    assert by["gone.json"]["exists"] is False


def test_status_separates_alive_stalled_done(tmp_path):
    hb, mf = tmp_path / "heartbeat.jsonl", tmp_path / "manifest.jsonl"
    now = time.time()
    rows = [
        {"run_id": "a-1", "name": "alive", "ts_epoch": now - 5, "stage": "x",
         "frac": 0.5, "elapsed_s": 5},
        {"run_id": "b-2", "name": "stalled", "ts_epoch": now - 9999, "stage": "y",
         "frac": 0.1, "elapsed_s": 10},
        {"run_id": "c-3", "name": "done", "ts_epoch": now - 9999, "stage": "finish",
         "frac": 1.0, "elapsed_s": 20},
    ]
    hb.write_text("\n".join(json.dumps(r) for r in rows))
    mf.write_text(json.dumps({"run_id": "c-3", "name": "done"}))
    got = {r["name"]: r["state"] for r in status(tmp_path, stale_after=180)}
    assert got == {"alive": "alive", "stalled": "stalled", "done": "done"}


def test_code_hash_detects_a_changed_or_missing_file(tmp_path):
    from monitor import code_hash
    (tmp_path / "a.py").write_text("one")
    (tmp_path / "b.py").write_text("two")
    files = ("a.py", "b.py")
    h1, per1 = code_hash(files, root=tmp_path)
    assert "MISSING" not in per1.values()
    # A byte change moves the hash.
    (tmp_path / "b.py").write_text("three")
    h2, _ = code_hash(files, root=tmp_path)
    assert h1 != h2
    # A missing file is recorded, not skipped, so a truncated deployment cannot
    # hash the same as a complete one.
    (tmp_path / "b.py").unlink()
    h3, per3 = code_hash(files, root=tmp_path)
    assert per3["b.py"] == "MISSING"
    assert h3 not in (h1, h2)


def test_preflight_aborts_on_code_hash_mismatch():
    m = Monitor("t", require_clean_tree=False,
                expect_code_hash="0000000000000000")
    with pytest.raises(PreflightError) as e:
        m.preflight()
    assert "code_hash" in str(e.value)


def test_missing_expected_hash_is_a_failure_not_a_skip():
    # The first xl learning run started with no expected hash and its config
    # silently omitted reward_clip. An optional assertion is no assertion.
    m = Monitor("t", config={"k": 12}, require_clean_tree=False)
    with pytest.raises(PreflightError) as e:
        m.preflight()
    assert "config_hash" in str(e.value)
    assert "no expected hash" in str(e.value)


def test_a_run_with_no_config_still_needs_no_hash():
    # Utilities that carry no decisive settings are not forced to declare one.
    m = Monitor("t", config={}, require_clean_tree=False)
    assert all(c["ok"] for c in m.preflight())


def test_learn_config_keys_match_the_pre_registration():
    from pathlib import Path
    from monitor import LEARN_CONFIG_KEYS
    doc = Path(__file__).resolve().parent.parent / "docs" / "spo_preregistration.md"
    text = doc.read_text(encoding="utf-8")
    missing = [k for k in LEARN_CONFIG_KEYS if f"| {k} |" not in text]
    assert not missing, f"keys absent from the pre registration table: {missing}"
