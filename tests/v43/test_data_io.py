import numpy as np
import pytest
from introact_ts.v43.data_io import read_rows, select_pilot
from introact_ts.v43.data_contract import split_intervals
from introact_ts.v43.schemas import ContractError


def test_streaming_npz_preserves_nan_without_loading_objects(tmp_path):
    path = tmp_path / "panel.npz"
    values = np.arange(200., dtype=float).reshape(100, 2)
    values[8, 1] = np.nan
    np.savez_compressed(path, values=values, channels=np.array(["a", "b"], dtype=object))
    record = dict(path=str(path), shape=[100, 2], split_bounds=split_intervals(100))
    timestamps, actual = read_rows(record, 5, 10, "train")
    np.testing.assert_array_equal(timestamps, np.arange(5, 10))
    np.testing.assert_array_equal(actual, values[5:10])
    with pytest.raises(ContractError, match="held-out"):
        read_rows(record, 85, 90, "test")
    with pytest.raises(ContractError, match="crosses split"):
        read_rows(record, 59, 61, "train")


def test_origin_selection_uses_lengths_only():
    records = [dict(source=f"s{i}", panel=f"p{i}", shape=[n, 3], file_sha256="a"*64)
               for i, n in enumerate([17420, 17420, 69680, 2842, 9326, 5035])]
    origins = select_pilot(records)
    assert len(origins) == 32 and len({r["uid"] for r in origins}) == 32
    for record in records:
        intervals = sorted((r["raw_start"], r["context_end"]+32) for r in origins if r["source"] == record["source"])
        assert all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:]))
    assert sum(r["source"] == "s3" for r in origins) == 3
