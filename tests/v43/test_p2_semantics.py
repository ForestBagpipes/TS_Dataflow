from dataclasses import replace
import gzip
import numpy as np
import pytest
from introact_ts.v43.data_contract import split_intervals
from introact_ts.v43.data_io import read_rows
from introact_ts.v43.p2_data import select_dev, corrupt_context, legal_history
from introact_ts.v43.p2_candidates import ridge_candidate, residual_plan, static_residual
from introact_ts.v43.schemas import Candidate, ContractError, array_hash, verify_impute


def test_gzip_only_converts_allowed_rows(tmp_path):
    path = tmp_path / "panel.txt.gz"
    with gzip.open(path, "wt") as f:
        f.write("1,2\n3,\n"+"FORBIDDEN_LABEL,NOT_NUMERIC\n"*8)
    r = dict(path=str(path), shape=[10, 2], split_bounds=split_intervals(10))
    t, x = read_rows(r, 0, 2, "train")
    assert t.tolist() == [0, 1] and np.isnan(x[1, 1])
    with pytest.raises(ContractError, match="held-out"):
        read_rows(r, 9, 10, "test")


def test_formal_parents_shared_by_horizons_not_counted_twice():
    r = dict(source="s", panel="p", shape=[10000, 3], split_bounds=split_intervals(10000), file_sha256="a"*64)
    origins = select_dev([r])
    assert len(origins) == 4 and len({r["parent_group"] for r in origins}) == 2
    a, b, c, d = origins
    assert a["raw_start"] == b["raw_start"] and c["raw_start"] == d["raw_start"]
    assert b["context_end"]+192 <= c["raw_start"]
    assert all(r["split"] == "dev" for r in origins)


def test_shared_mask_hides_siblings_and_preserves_time(episode):
    e = corrupt_context(episode, "shared_block_10", [50, 66], 101)
    assert np.isnan(e.covariates[50:66]).all() and np.isnan(e.target[50:66]).all()
    assert array_hash(e.timestamps) == array_hash(episode.timestamps)
    assert e.parent_group == episode.parent_group and e.uid != episode.uid


def test_full_history_does_not_reopen_current_gap_truth(episode):
    e = replace(episode, split="dev", raw_start=100, context_end=260)
    r = dict(split_bounds={"dev": [90, 500]})
    seen = []
    def reader(record, start, stop, split):
        seen.append((start, stop, split))
        assert stop == e.raw_start
        return np.arange(start, stop), np.ones((stop-start, 3))
    x, z, span = legal_history(r, e, reader)
    assert seen == [(90, 100, "dev")] and span == [90, 260]
    np.testing.assert_array_equal(x[-160:], e.target)
    np.testing.assert_array_equal(z[-160:], e.covariates)
    assert np.isnan(x[-160:][72:88]).all()


def test_a5_unsupported_returns_verified_a2_not_keep(episode):
    z = np.full_like(episode.covariates, np.nan)
    e = replace(episode, covariates=z)
    base = Candidate(e.uid, "A2_SINGLE", np.where(np.isnan(e.target), 5., e.target))
    blocks, views, reason = residual_plan(e, 16)
    result, evidence = static_residual(e, base, blocks, {}, reason)
    assert evidence["fallback"] == "A2_SINGLE" and reason and views == {}
    assert array_hash(result.target) == array_hash(base.target) != array_hash(e.target)
    verify_impute(e, result)


def test_nested_plan_and_missing_prediction_cannot_silently_fallback(episode):
    blocks, views, reason = residual_plan(episode, 16)
    assert len(views) == 7 and reason is None
    base = Candidate(episode.uid, "A2_SINGLE", np.nan_to_num(episode.target))
    with pytest.raises(ContractError, match="missing real nested"):
        static_residual(episode, base, blocks, {})
    assert sorted(int(np.isnan(x).sum()) for x in views.values()) == [16, 32, 32, 32, 48, 48, 48]


def test_ridge_observed_writes_and_explicit_support(episode):
    candidate, evidence = ridge_candidate(episode)
    verify_impute(episode, candidate)
    assert evidence["status"] == "completed" and np.isfinite(candidate.target).all()
    e = replace(episode, covariates=np.full_like(episode.covariates, np.nan))
    candidate, evidence = ridge_candidate(e)
    assert evidence["fallback"] == "A0_NATIVE" and evidence["status"] == "unsupported"
    assert array_hash(candidate.target) == array_hash(e.target)


def test_static_equal_outer_losses_choose_eta_zero(episode):
    x = episode.covariates[:, 0].copy()
    x[np.isnan(episode.target)] = np.nan
    e = replace(episode, target=x)
    blocks, views, _ = residual_plan(e, 16)
    predictions = {key: np.where(np.isnan(view), e.covariates[:, 0], view) for key, view in views.items()}
    base = Candidate(e.uid, "A2_SINGLE", predictions[array_hash(x)])
    result, evidence = static_residual(e, base, blocks, predictions)
    assert evidence["eta"] == 0.0
    assert array_hash(result.target) == array_hash(base.target)
