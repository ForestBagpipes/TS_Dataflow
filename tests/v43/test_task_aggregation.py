import numpy as np
import pytest
from introact_ts.v43.candidates import prepare_model_input, resolve_candidate
from introact_ts.v43.schemas import Candidate, ContractError, array_hash
from introact_ts.v43.task_labels import TaskTarget, evaluate_pair, mase_scale
from introact_ts.v43.evaluation import aggregate


@pytest.mark.parametrize("native", [True, False])
def test_native_keep_and_shared_preprocessing(episode, native):
    keep = episode.target.copy()
    a = prepare_model_input(episode.target, native_nan=native)
    b = prepare_model_input(keep, native_nan=native)
    assert array_hash(a) == array_hash(b)
    assert np.isnan(a).any() == native
    # Adapter stubs use one deterministic prediction; no real-model claim.
    pred = np.full(8, np.nanmean(a))
    y = TaskTarget(episode.uid, "dev", np.arange(8.), np.ones(8, dtype=bool))
    r = evaluate_pair(y, pred, pred, scale=2.)
    assert r["task_gain"] == 0 and not r["task_harm"]


def test_common_mask_and_degenerate_mase():
    y = TaskTarget("u", "dev", np.array([1., np.nan, 3.]), np.array([True, False, True]))
    p = np.array([2., 100., 4.])
    row = evaluate_pair(y, p, p, scale=None)
    assert row["mae"] == 1 and row["n_scored"] == 2 and row["mase"] is None
    assert mase_scale(np.ones(10), 1) is None
    p[1] = np.nan
    with pytest.raises(ContractError):
        evaluate_pair(y, p, p, scale=None)


def test_unsupported_and_all_keep_preserve_denominator(episode):
    c = Candidate(episode.uid, "unsupported", episode.target, False, "support")
    assert resolve_candidate(episode, c).candidate_id == "KEEP"
    rows = [{"episode_uid": uid, "status": "completed", "task_gain": 0.} for uid in ("a", "b")]
    report = aggregate(["a", "b"], rows)
    assert report["n_origins"] == 2 and report["mean_task_gain"] == 0
    with pytest.raises(ContractError):
        aggregate(["a", "b"], rows[:1])
    rows[1] = {"episode_uid": "b", "status": "failed", "error": "model OOM"}
    report = aggregate(["a", "b"], rows)
    assert report["status"] == "failed" and report["mean_task_gain"] is None
    assert report["n_origins"] == 2 and report["failed_origins"] == ["b"]
