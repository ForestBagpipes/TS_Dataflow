"""Synthetic contract tests only; run in the designated server environment."""
from types import SimpleNamespace
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from introact_ts.v44 import protocol as historical
from introact_ts.v47_verified import actions as A, grid as G, protocol as P
from introact_ts.v47_verified import select as S


def spec(source="s", parent="p", block="bankx"):
    return G.EpisodeSpec("e", source, parent, P.CONTEXT, 0, 96,
                         P.PATTERNS[0], .1, "main", block, 1, 1)


def test_keep_preserves_nan_and_is_unchanged():
    panel = np.array([[1.234567891], [np.nan], [2.]])
    out = A.apply_action("KEEP", panel)
    assert out.applicable and not out.changed
    np.testing.assert_array_equal(out.panel, panel)


def test_protocol_does_not_extend_historical_actions(monkeypatch):
    before = historical.ACTIONS
    assert P.ACTIONS == ("KEEP", "FFILL", "SINGLE_TSICL", "MULTI_TSICL", "CONTEXT_RIDGE", "SAITS")
    monkeypatch.setattr(P, "ACTIONS", P.ACTIONS + ("TEST_ONLY",))
    assert historical.ACTIONS == before


def test_repair_guard_rejects_observation_rewrite_and_extreme_value():
    ref = np.array([1., np.nan, 2., 3.])
    assert A.implausible_reason(np.array([1., 2., 2., 3.]), ref) is None
    assert "observed" in A.implausible_reason(np.array([1.1, 2., 2., 3.]), ref)
    assert "plausible" in A.implausible_reason(np.array([1., 1e12, 2., 3.]), ref)


def test_context_reader_never_requests_future(monkeypatch, tmp_path):
    info = SimpleNamespace(path="unused", columns=1)
    monkeypatch.setattr(G.R, "source_registry", lambda root: {"s": info})
    def rows(path):
        for i in range(P.CONTEXT):
            yield i, [str(i)]
        raise AssertionError("future row requested")
    monkeypatch.setattr(G.R, "source_rows", rows)
    monkeypatch.setattr(G.R, "read_windows", lambda *a, **k: pytest.fail("future reader used"))
    output = list(G.iter_contexts(tmp_path, [spec()]))
    assert len(output) == 1
    assert output[0][1][-1, 0] == P.CONTEXT - 1
    assert np.isnan(output[0][2]).any()


def test_pilot_retains_whole_parents_across_sources():
    specs = [replace(spec(s, f"{s}-{i}"), read_start=i * 704,
                     origin=i * 704 + P.CONTEXT, episode_id=f"{s}-{i}-{j}")
             for s in ("a", "b") for i in range(20) for j in range(2)]
    chosen = G.select_pilot_specs(specs, 32)
    assert len(chosen) == 64
    assert len({s.parent for s in chosen if s.source == "a"}) == 16
    assert G.mask_seed_of("bankx2") != G.mask_seed_of("bankx")


def test_no_feasible_grid_refuses_freeze(monkeypatch):
    monkeypatch.setattr(S, "distance_matrices", lambda *a, **k: {})
    monkeypatch.setattr(S, "score_grid", lambda *a, **k: {})
    monkeypatch.setattr(S, "decide", lambda *a, **k: [])
    monkeypatch.setattr(S, "outcomes", lambda *a: dict(mase=np.array([1.]),
        intervention_rate=1., conditional_hir=.8, harmful_loss=.2, beneficial_precision=.2))
    monkeypatch.setattr(S, "source_macro", lambda *a: 1.)
    with pytest.raises(ValueError, match="harm cap"):
        S.select_hyperparameters(None, None, k_grid=(8,), beta_grid=(0.,), cap=.5)


def test_pilot_public_api_accepts_parent_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(G.R, "source_registry", lambda root: {})
    monkeypatch.setattr(G, "parents_of", lambda *args: [])
    assert G.episode_specs(tmp_path, "bankx", parent_limit=32) == []


def test_frozen_protocol_matches_code_constants():
    root = Path(__file__).resolve().parents[2]
    frozen = json.loads((root / "configs/v47-verified/protocol.json").read_text())
    assert frozen["context_length"] == P.CONTEXT
    assert tuple(frozen["horizons"]) == P.HORIZONS
    assert tuple(frozen["patterns"]) == P.PATTERNS
    assert tuple(frozen["bank_severities"]) == P.SEVERITIES
    assert tuple(frozen["actions"]) == P.ACTIONS
    assert tuple(frozen["selector"]["k_grid"]) == P.K_GRID
    assert tuple(frozen["selector"]["beta_grid"]) == P.BETA_GRID
    assert frozen["selector"]["plausibility_scales"] == P.PLAUSIBILITY_SCALES
    assert tuple(frozen["train_parent_split"].values()) == P.SPLIT_RATIOS
    assert frozen["bootstrap"]["resamples"] == P.BOOTSTRAP_RESAMPLES
    assert frozen["bootstrap"]["seed"] == P.BOOTSTRAP_SEED
    assert {name: item["batch_size"] for name, item in
            frozen["inference_batching"].items()} == P.INFERENCE_BATCH_SIZE
    probe = json.loads((root / "configs/v47-verified/batch_probe_decision.json").read_text())
    assert probe["future_arrays_read"] == probe["test_records_read"] == 0
    assert probe["decision"] == P.INFERENCE_BATCH_SIZE
    assert probe["backbones"]["bolt"]["status"] == "failed"
    assert probe["backbones"]["timesfm"]["status"] == "passed"
    assert probe["backbones"]["chronos2"]["status"] == "passed"
