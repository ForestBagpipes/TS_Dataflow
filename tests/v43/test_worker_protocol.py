from copy import deepcopy
import numpy as np
import pytest
from introact_ts.v43.schemas import ContractError, array_hash
from introact_ts.v43.worker_protocol import cache_key, verify_response
from introact_ts.v43.worker_protocol import submit_batch


def fixture():
    r = dict(schema_version=1, request_id="request-1", model_revision="a"*40,
             code_hash="b"*64, environment_hash="c"*64, task="forecast", horizon=3,
             dtype="float64", seed=101, covariate_mode="none", batch_size=4, normalization="native")
    r["rows"] = [dict(episode_uid=u, candidate_id="KEEP", input_hash="d"*64,
                      raw_mask_hash="e"*64, covariate_hash="f"*64, availability_hash="a"*64,
                      timestamps_hash="b"*64, cutoff=512, parameters_hash="c"*64, output_length=3)
                 for u in ("a", "b")]
    predictions = [np.array([1., 2., 3.]), np.array([4., 5., 6.])]
    response = deepcopy(r)
    response.update(status="completed", units="original")
    for row, p in zip(response["rows"], predictions):
        row.update(prediction_hash=array_hash(p), shape=[3], runtime_seconds=.1, peak_gpu_bytes=10)
    return r, response, predictions


@pytest.mark.parametrize("key,value", [("request_id", "wrong"), ("model_revision", "d"*40),
    ("horizon", 4), ("units", "normalized"), ("environment_hash", "wrong"), ("status", "failed")])
def test_worker_identity_whole_batch_rejected(key, value):
    request, response, predictions = fixture()
    assert len(verify_response(request, response, predictions)) == 2
    response[key] = value
    with pytest.raises(ContractError):
        verify_response(request, response, predictions)


@pytest.mark.parametrize("fault", ["drop", "reverse", "nan", "hash", "dtype"])
def test_worker_rows_cannot_be_dropped_or_replaced(fault):
    request, response, predictions = fixture()
    if fault == "drop":
        response["rows"].pop()
    elif fault == "reverse":
        response["rows"].reverse()
    elif fault == "nan":
        predictions[1][0] = np.nan
    elif fault == "hash":
        predictions[1][0] += 1
    else:
        predictions[1] = predictions[1].astype(np.float32)
    with pytest.raises(ContractError):
        verify_response(request, response, predictions)


@pytest.mark.parametrize("field", ["input_hash", "raw_mask_hash", "covariate_hash", "availability_hash",
                                    "timestamps_hash", "cutoff", "parameters_hash", "candidate_id"])
def test_cache_covers_semantic_inputs(field):
    request, _, _ = fixture()
    other = deepcopy(request)
    other["rows"][0][field] = 513 if field == "cutoff" else ("0"*64 if field.endswith("hash") else "changed")
    assert cache_key(request) != cache_key(other)
    other = deepcopy(request)
    other["request_id"] = "another-job"
    assert cache_key(request) == cache_key(other)


def test_real_subprocess_file_roundtrip_and_nonzero_failure(tmp_path, monkeypatch):
    import json
    import os
    import subprocess
    import sys
    request, _, _ = fixture()
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    stub = tmp_path / "protocol_test_worker.py"
    stub.write_text('''import argparse,json,numpy as np
from introact_ts.v43.schemas import array_hash
p=argparse.ArgumentParser()
for key in ("request","response","predictions"): p.add_argument("--"+key)
a=p.parse_args()
r=json.load(open(a.request))
r.update(status="completed", units="original")
arrays={}
for i,row in enumerate(r["rows"]):
    pred=np.arange(row["output_length"],dtype=r["dtype"])
    row.update(prediction_hash=array_hash(pred),shape=list(pred.shape),runtime_seconds=0.,peak_gpu_bytes=0)
    arrays[f"row_{i}"]=pred
np.savez(a.predictions,**arrays)
json.dump(r,open(a.response,"w"))
''')
    monkeypatch.setenv("PYTHONPATH", str(tmp_path)+os.pathsep+os.environ["PYTHONPATH"])
    result = submit_batch(sys.executable, "protocol_test_worker", path, tmp_path/"response.json", tmp_path/"predictions.npz", 10)
    assert len(result) == 2 and result[0].shape == (3,)
    with pytest.raises(ContractError, match="already exists"):
        submit_batch(sys.executable, "protocol_test_worker", path, tmp_path/"response.json", tmp_path/"predictions.npz", 10)
    (tmp_path / "failed_test_worker.py").write_text("raise SystemExit(7)\n")
    with pytest.raises(subprocess.CalledProcessError):
        submit_batch(sys.executable, "failed_test_worker", path, tmp_path/"failed.json", tmp_path/"failed.npz", 10)
    assert not (tmp_path/"failed.npz").exists()


def test_worker_reads_verified_numeric_payload_only(episode, tmp_path):
    from introact_ts.v43.workers.common import load_inputs
    from introact_ts.v43.schemas import json_hash
    request, _, _ = fixture()
    row = request["rows"][0]
    payload = dict(target=episode.target, raw_mask=episode.observed_mask, covariates=episode.covariates,
                   availability=episode.availability, timestamps=episode.timestamps)
    names = dict(target="input_hash", raw_mask="raw_mask_hash", covariates="covariate_hash",
                 availability="availability_hash", timestamps="timestamps_hash")
    for name, key in names.items():
        row[key] = array_hash(payload[name])
    path = tmp_path / "payload.npz"
    np.savez(path, **payload)
    row.update(array_path=str(path), parameters={}, parameters_hash=json_hash({}))
    request["rows"] = [row]
    actual = load_inputs(request)[0]
    assert array_hash(actual["target"]) == array_hash(episode.target)
    poisoned = dict(payload)
    poisoned["covariates"] = episode.covariates.copy()
    poisoned["covariates"][0, 0] += 1e10
    np.savez(path, **poisoned)
    with pytest.raises(ContractError, match="hash mismatch"):
        load_inputs(request)
