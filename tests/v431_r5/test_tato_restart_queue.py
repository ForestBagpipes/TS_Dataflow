import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
QUEUE_SCRIPT = ROOT / "scripts/v431_r5_tato_restart_queue.py"
AUDIT_SCRIPT = ROOT / "scripts/v431_r5_tato_scene_audit.py"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_scene(root, name, status, trials, completed, worker, cache_module):
    scene = root / name
    scene.mkdir(parents=True)
    inputs = scene / "inputs.npz"
    inputs.write_bytes(b"fixed-inputs")
    request = {
        "family": "timesfm",
        "horizon": 96,
        "source": "Solar",
        "target_channel": 0,
        "target_field": "POWER_136",
        "condition": "target_block_10",
        "context": 512,
        "train_parents": 22,
        "dev_parents": 11,
        "rows": [{"uid": "u1", "role": "train", "parent": "p1"}],
        "trials": 500,
        "inputs": str(inputs),
        "inputs_sha256": sha(inputs),
        "seed": 101,
        "adapter_sha256": "adapter",
        "reference_frozen_sha256": "reference",
        "supervision": "TRAIN only",
        "worker_sha256": sha(worker),
        "cache_module_sha256": sha(cache_module),
        "output": str(scene),
        "max_seconds": 600.0,
        "heldout_labels_read": 0,
        "cache_amendment": {"original_request": "immutable"},
    }
    request_path = scene / "request.resolved.json"
    write_json(request_path, request)
    frozen = {
        "request_sha256": sha(request_path),
        "full_search_completed": status == "completed",
        "actual_trials": trials,
        "completed_trials": completed,
        "requested_trials": 500,
    }
    write_json(scene / "run/status.json", {"status": status, "trials": trials, "completed_trials": completed})
    write_json(scene / "run/frozen_scene.json", frozen)
    return scene, request


def test_prepare_registers_only_partial_scenes_and_preserves_identity(tmp_path):
    queue = load_module(QUEUE_SCRIPT, "restart_queue")
    worker = tmp_path / "worker.py"
    cache = tmp_path / "cache.py"
    worker.write_text("worker-v1\n")
    cache.write_text("cache-v1\n")
    source = tmp_path / "source"
    partial, original = make_scene(source, "solar-timesfm-h96", "partial", 247, 247, worker, cache)
    make_scene(source, "solar-bolt-h96", "completed", 500, 500, worker, cache)

    result = queue.prepare_restart_queue(source, tmp_path / "restart", 1200.0, worker, cache)

    assert [job["scene"] for job in result["queue"]] == ["solar-timesfm-h96"]
    assert result["server_shutdown_invoked"] is False
    request = json.loads((tmp_path / "restart/solar-timesfm-h96/request.preregistered.json").read_text())
    for key in queue.IDENTITY_KEYS:
        assert request[key] == original[key]
    assert request["output"] == str((tmp_path / "restart/solar-timesfm-h96").resolve())
    assert request["max_seconds"] == 1200.0
    amendment = request["restart_amendment"]
    assert amendment["mode"] == "fresh_deterministic_from_trial_zero"
    assert amendment["source_scene"] == str(partial.resolve())
    assert amendment["source_request_sha256"] == sha(partial / "request.resolved.json")
    assert amendment["source_status_sha256"] == sha(partial / "run/status.json")
    assert amendment["source_frozen_sha256"] == sha(partial / "run/frozen_scene.json")


def test_prepare_refuses_existing_restart_root(tmp_path):
    queue = load_module(QUEUE_SCRIPT, "restart_queue_existing")
    worker = tmp_path / "worker.py"
    cache = tmp_path / "cache.py"
    worker.write_text("worker-v1\n")
    cache.write_text("cache-v1\n")
    source = tmp_path / "source"
    make_scene(source, "solar-timesfm-h96", "partial", 247, 247, worker, cache)
    output = tmp_path / "restart"
    output.mkdir()
    with pytest.raises(FileExistsError):
        queue.prepare_restart_queue(source, output, 1200.0, worker, cache)


def test_prepare_preflights_every_source_before_creating_output(tmp_path):
    queue = load_module(QUEUE_SCRIPT, "restart_queue_preflight")
    worker = tmp_path / "worker.py"
    cache = tmp_path / "cache.py"
    worker.write_text("worker-v1\n")
    cache.write_text("cache-v1\n")
    source = tmp_path / "source"
    scene, _ = make_scene(source, "solar-timesfm-h96", "partial", 247, 247, worker, cache)
    (scene / "inputs.npz").write_bytes(b"tampered-after-registration")
    output = tmp_path / "restart"

    with pytest.raises(AssertionError):
        queue.prepare_restart_queue(source, output, 1200.0, worker, cache)
    assert not output.exists()


def test_restart_audit_rejects_identity_tampering(tmp_path):
    queue = load_module(QUEUE_SCRIPT, "restart_queue_audit")
    audit = load_module(AUDIT_SCRIPT, "restart_audit")
    worker = tmp_path / "worker.py"
    cache = tmp_path / "cache.py"
    worker.write_text("worker-v1\n")
    cache.write_text("cache-v1\n")
    source = tmp_path / "source"
    make_scene(source, "solar-timesfm-h96", "partial", 247, 247, worker, cache)
    queue.prepare_restart_queue(source, tmp_path / "restart", 1200.0, worker, cache)
    request_path = tmp_path / "restart/solar-timesfm-h96/request.preregistered.json"
    request = json.loads(request_path.read_text())

    verified = audit.verify_restart_amendment(request)
    assert verified["verified"] is True
    request["rows"] = [{"uid": "tampered"}]
    with pytest.raises(AssertionError):
        audit.verify_restart_amendment(request)


def test_restart_audit_rejects_time_above_registered_cap(tmp_path):
    queue = load_module(QUEUE_SCRIPT, "restart_queue_cap")
    audit = load_module(AUDIT_SCRIPT, "restart_audit_cap")
    worker = tmp_path / "worker.py"
    cache = tmp_path / "cache.py"
    worker.write_text("worker-v1\n")
    cache.write_text("cache-v1\n")
    source = tmp_path / "source"
    make_scene(source, "solar-timesfm-h96", "partial", 247, 247, worker, cache)
    queue.prepare_restart_queue(source, tmp_path / "restart", 1200.0, worker, cache)
    request = json.loads((tmp_path / "restart/solar-timesfm-h96/request.preregistered.json").read_text())
    request["max_seconds"] = 1200.1
    with pytest.raises(AssertionError):
        audit.verify_restart_amendment(request)


def test_restart_prefix_audit_checks_params_scores_and_prediction_hashes(tmp_path):
    queue = load_module(QUEUE_SCRIPT, "restart_queue_prefix")
    audit = load_module(AUDIT_SCRIPT, "restart_audit_prefix")
    worker = tmp_path / "worker.py"
    cache = tmp_path / "cache.py"
    worker.write_text("worker-v1\n")
    cache.write_text("cache-v1\n")
    source = tmp_path / "source"
    partial, _ = make_scene(source, "solar-timesfm-h96", "partial", 2, 1, worker, cache)
    old_trials = [
        {
            "trial": 0,
            "params": {"context_len": 512},
            "status": "completed",
            "train_macro_mse": 1.25,
            "samples": [{"uid": "u1", "train_mse": 1.25, "train_mae": 0.5, "prediction_hash": "p0"}],
        },
        {
            "trial": 1,
            "params": {"context_len": 448},
            "status": "partial",
            "samples": [{"uid": "u1", "train_mse": 1.5, "train_mae": 0.6, "prediction_hash": "p1"}],
        },
    ]
    write_json(partial / "run/trials.json", old_trials)
    np.savez(partial / "run/train_predictions_0000.npz", u1=np.array([1.0, 2.0]))
    np.savez(partial / "run/train_predictions_0001.npz", u1=np.array([3.0, 4.0]))
    queue.prepare_restart_queue(source, tmp_path / "restart", 1200.0, worker, cache)
    request = json.loads((tmp_path / "restart/solar-timesfm-h96/request.preregistered.json").read_text())
    new_run = tmp_path / "restart/solar-timesfm-h96/run"
    new_trials = json.loads(json.dumps(old_trials))
    new_trials[0]["samples"][0]["prediction_hash"] = "p0-near-but-not-bitwise"
    new_trials[1]["samples"][0]["prediction_hash"] = "p1-near-but-not-bitwise"
    new_trials[1].update(status="completed", train_macro_mse=1.5)
    new_trials.append(
        {"trial": 2, "params": {"context_len": 384}, "status": "completed", "samples": []}
    )
    write_json(
        new_run / "trials.json",
        new_trials,
    )
    np.savez(new_run / "train_predictions_0000.npz", u1=np.array([1.0, 2.0 + 1e-13]))
    np.savez(new_run / "train_predictions_0001.npz", u1=np.array([3.0 - 1e-13, 4.0]))

    result = audit.verify_restart_prefix(request, new_run)
    assert result["source_trials_checked"] == 2
    assert result["completed_trials_reproduced"] == 1
    assert result["sample_predictions_reproduced"] == 2
    assert result["bitwise_prediction_hash_matches"] == 0
    assert result["numerically_reproduced_hash_mismatches"] == 2

    new_trials = json.loads((new_run / "trials.json").read_text())
    new_trials[1]["params"]["context_len"] = 320
    write_json(new_run / "trials.json", new_trials)
    with pytest.raises(AssertionError):
        audit.verify_restart_prefix(request, new_run)

    new_trials[1]["params"]["context_len"] = 448
    write_json(new_run / "trials.json", new_trials)
    np.savez(new_run / "train_predictions_0001.npz", u1=np.array([3.0, 4.1]))
    with pytest.raises(AssertionError):
        audit.verify_restart_prefix(request, new_run)


def test_run_queue_requires_completed_worker_terminal_and_is_one_shot(tmp_path, monkeypatch):
    queue_module = load_module(QUEUE_SCRIPT, "restart_queue_run")
    worker = tmp_path / "worker.py"
    cache = tmp_path / "cache.py"
    worker.write_text(
        "import argparse,json,pathlib\n"
        "p=argparse.ArgumentParser();p.add_argument('--request');a=p.parse_args()\n"
        "r=json.loads(pathlib.Path(a.request).read_text());run=pathlib.Path(r['output'])/'run';run.mkdir()\n"
        "(run/'status.json').write_text(json.dumps({'status':'completed'})+'\\n')\n"
    )
    cache.write_text("cache-v1\n")
    source = tmp_path / "source"
    make_scene(source, "solar-timesfm-h96", "partial", 247, 247, worker, cache)
    output = tmp_path / "restart"
    prepared = queue_module.prepare_restart_queue(
        source, output, 1200.0, worker, cache, interpreter=Path(sys.executable)
    )
    assert prepared["interpreter"] == str(Path(sys.executable).absolute())
    monkeypatch.setattr(queue_module.sys, "executable", str(tmp_path / "must-not-be-used"))

    result = queue_module.run_restart_queue(output / "queue.preregistered.json", tmp_path / "queue.lock")
    assert result["status"] == "completed"
    assert result["jobs"][0]["status"] == "completed"
    assert result["jobs"][0]["worker_terminal"]["status"] == "completed"
    assert result["server_shutdown_invoked"] is False
    with pytest.raises(FileExistsError):
        queue_module.run_restart_queue(output / "queue.preregistered.json", tmp_path / "queue.lock")


def test_run_queue_does_not_call_a_zero_exit_partial_completed(tmp_path):
    queue_module = load_module(QUEUE_SCRIPT, "restart_queue_partial")
    worker = tmp_path / "worker.py"
    cache = tmp_path / "cache.py"
    worker.write_text(
        "import argparse,json,pathlib\n"
        "p=argparse.ArgumentParser();p.add_argument('--request');a=p.parse_args()\n"
        "r=json.loads(pathlib.Path(a.request).read_text());run=pathlib.Path(r['output'])/'run';run.mkdir()\n"
        "(run/'status.json').write_text(json.dumps({'status':'partial'})+'\\n')\n"
    )
    cache.write_text("cache-v1\n")
    source = tmp_path / "source"
    make_scene(source, "solar-timesfm-h96", "partial", 247, 247, worker, cache)
    output = tmp_path / "restart"
    queue_module.prepare_restart_queue(source, output, 1200.0, worker, cache)

    result = queue_module.run_restart_queue(output / "queue.preregistered.json", tmp_path / "queue.lock")
    assert result["status"] == "finished_with_failures"
    assert result["jobs"][0]["status"] == "worker_partial"
