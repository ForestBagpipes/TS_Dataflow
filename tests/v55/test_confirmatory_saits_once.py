"""A confirmatory source must use the same fitted imputer in every block."""

from pathlib import Path
import sys

import numpy as np
import pytest

pytest.importorskip("fcntl")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import v55_confirmatory_saits_once as once


def test_source_is_fitted_once_and_outputs_return_to_correct_blocks(monkeypatch):
    panels = {
        "bankx": [("b", "p0", np.array([[1.], [2.]], dtype=np.float32))],
        "train_eval": [("a", "p1", np.array([[np.nan], [3.]], dtype=np.float32))],
        "test": [("t", "p2", np.array([[4.], [np.nan]], dtype=np.float32))],
    }
    calls = []

    def collect(_root, block, _source, columns):
        return np.array([0]), panels[block]

    def fit(train, query, epochs):
        calls.append((len(train), len(query), epochs))
        raw = np.stack(query)
        return raw, np.where(np.isfinite(raw), raw, 7.0)

    monkeypatch.setattr(once.S, "collect", collect)
    arrays, report = once.source_fit("example", ("train_eval", "test"), 5, fit)
    assert calls == [(1, 2, 5)]
    assert report["fits"] == 1
    np.testing.assert_array_equal(arrays["train_eval"]["a|SAITS"], [7.0, 3.0])
    np.testing.assert_array_equal(arrays["test"]["t|SAITS"], [4.0, 7.0])
