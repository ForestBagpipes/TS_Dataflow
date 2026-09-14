from dataclasses import replace
import numpy as np
import pytest
from introact_ts.v43.schemas import Candidate, ContractError, array_hash, verify_impute
from introact_ts.v43.data_contract import ReadInterval, audit_reads, as_of, origin_indices, split_intervals
from introact_ts.v43.candidates import generate_base
from introact_ts.v43.task_labels import read_target
from introact_ts.v43.adaptation import export_training_pairs


def test_observed_write_and_immutable_storage(episode):
    out = episode.target.copy()
    out[np.isnan(out)] = 4.
    candidate = Candidate(episode.uid, "fill", out)
    verify_impute(episode, candidate)
    assert candidate.target[130] == 1e6
    with pytest.raises(ValueError):
        episode.target.setflags(write=True)
    with pytest.raises(ValueError):
        candidate.target[0] = 7
    out[130] = 0
    with pytest.raises(ContractError, match="observed write"):
        verify_impute(episode, Candidate(episode.uid, "bad", out))
    assert np.isnan(episode.target[72:88]).all()


def test_short_gap_preserves_axis(episode):
    x = episode.target.copy()
    x[8:10] = np.nan
    e = replace(episode, target=x)
    keep, short = generate_base(e)
    assert array_hash(keep.target) == array_hash(x)
    assert np.isfinite(short.target[8:10]).all()
    assert np.isnan(short.target[72:88]).all()
    assert len(short.target) == len(e.timestamps)


@pytest.mark.parametrize("start,stop,parent", [(159, 200, "different_hash"), (0, 5, "same_parent")])
def test_split_overlap_ignores_channel_and_content_hash(start, stop, parent):
    a = ReadInterval("s", "sync_panel", "same_parent", "train", 0, 168)
    b = ReadInterval("s", "sync_panel", parent, "dev", start, stop)
    with pytest.raises(ContractError):
        audit_reads([a, b])
    audit_reads([a, ReadInterval("s", "sync_panel", "p2", "dev", 168, 240)])


def test_asof_poison_and_delayed_covariates(episode):
    a = episode.availability.copy()
    a[20:30, 1] = 120
    e = replace(episode, availability=a)
    before = as_of(e, 100, 8)
    x, z = e.target.copy(), e.covariates.copy()
    x[100:] = -1e10
    z[100:] = 1e12
    z[20:30, 0] = -1e20
    after = as_of(replace(e, target=x, covariates=z), 100, 8)
    assert array_hash(before.target) == array_hash(after.target)
    assert array_hash(before.covariates) == array_hash(after.covariates)
    assert len(after.target) == 100 and after.raw_start == 0
    assert np.isnan(after.covariates[20:30, 0]).all()


def test_labels_open_only_after_split_check_and_adaptation_targets(episode):
    calls = []
    def reader(lo, hi):
        calls.append((lo, hi))
        return np.arange(lo, hi, dtype=float)
    for split in ("calibration", "test"):
        with pytest.raises(ContractError):
            read_target(reader, replace(episode, split=split))
    assert calls == []
    y = read_target(reader, episode)
    assert calls == [(160, 168)]
    keep, short = generate_base(episode)
    filled = episode.target.copy()
    filled[np.isnan(filled)] = 4.
    short = Candidate(episode.uid, "fill", filled)
    a = export_training_pairs(episode, keep, y, episode.target)
    b = export_training_pairs(episode, short, y, episode.target)
    for key in ("pair_id", "Y_common_hash", "test_input_hash"):
        assert a[key] == b[key]
    assert a["Y_common"].tobytes() == b["Y_common"].tobytes()
    assert array_hash(a["X_raw"]) != array_hash(b["X_governed"])


def test_original_split_origin_limits():
    bounds = split_intervals(2842)
    indices = origin_indices(2842)
    assert len(indices["train"]) == 3 and indices["dev"] == []
    for split, origins in indices.items():
        for origin in origins:
            assert bounds[split][0] <= origin-512 and origin+32 <= bounds[split][1]


def test_hash_shape_dtype_and_full_precision():
    x = np.array([1., np.nan], dtype=np.float64)
    for y in (x.astype(np.float32), x.reshape(1, 2), x+1e-10):
        assert array_hash(x) != array_hash(y)
    y = x.copy()
    y.view(np.uint64)[1] = 0x7ff8000000000012
    assert array_hash(x) == array_hash(y)
