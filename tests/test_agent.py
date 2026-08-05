"""End-to-end behaviour of the closed loop, including verification and rollback."""

import numpy as np
import pytest
from conftest import synth

from introact_ts.agent import AgentConfig, IntroActAgent
from introact_ts.types import Action, ROLLBACK_VERDICTS, TSWindow, Verdict
from introact_ts.verify import (
    VerifyConfig,
    action_risk,
    improvement_consistency,
    verify,
)


def corpus():
    ws, wid = [], 0
    for k in range(20):
        c = synth(k)
        ws.append(TSWindow(window_id=(wid := wid + 1), series=c.copy(),
                           stratum="clean", clean_series=c))
    for k in range(20, 30):
        c = synth(k)
        s = c.copy()
        s[[80, 140, 200, 280, 350]] += 40.0  # above the spike sensitivity floor
        ws.append(TSWindow(window_id=(wid := wid + 1), series=s,
                           stratum="contaminated", contamination="spike",
                           clean_series=c))
    for k in range(30, 40):
        c = synth(k)
        s = c.copy()
        s[150:200] = np.nan
        ws.append(TSWindow(window_id=(wid := wid + 1), series=s,
                           stratum="contaminated", contamination="missing",
                           clean_series=c))
    for k in range(40, 50):
        c = synth(k)
        c[220:250] += 22.0
        ws.append(TSWindow(window_id=(wid := wid + 1), series=c.copy(),
                           stratum="rare_valid", clean_series=c.copy()))
    return ws


@pytest.fixture(scope="module")
def run(models_module):
    ws = corpus()
    agent = IntroActAgent(models_module, AgentConfig(K_peers=10))
    return ws, agent.run(ws)


@pytest.fixture(scope="module")
def models_module():
    from introact_ts.tsfm import make_model_pool

    return make_model_pool((0, 1, 2))


# -- verification rule ------------------------------------------------------


def test_acceptance_requires_all_three_conditions():
    cfg = VerifyConfig(epsilon=0.0, tau=0.5, eta=0.5)
    assert verify(1.0, 0.1, 0.1, cfg) is Verdict.ACCEPTED
    assert verify(-1.0, 0.1, 0.1, cfg) is Verdict.ROLLED_BACK_UTILITY
    assert verify(1.0, 0.9, 0.1, cfg) is Verdict.ROLLED_BACK_STRUCTURE
    assert verify(1.0, 0.1, 0.9, cfg) is Verdict.ROLLED_BACK_RISK


def test_disabled_checks_stop_vetoing():
    assert verify(-1.0, 0.9, 0.9, VerifyConfig(
        require_reprobe=False, require_structure=False, require_risk=False
    )) is Verdict.ACCEPTED


def test_improvement_consistency_counts_directions():
    before = np.array([1.0, 1.0, 1.0, 1.0])
    assert improvement_consistency(before, np.array([0.0, 0.0, 0.0, 0.0])) == 1.0
    assert improvement_consistency(before, np.array([2.0, 2.0, 2.0, 2.0])) == 0.0
    assert improvement_consistency(before, np.array([0.0, 0.0, 2.0, 2.0])) == 0.5


def test_action_risk_is_bounded_and_monotone():
    assert 0.0 <= action_risk(1.0, 0.0, 1.0) <= 1.0
    assert action_risk(0.1, 0.9, 0.1) > action_risk(0.9, 0.1, 0.9)


# -- closed loop ------------------------------------------------------------


def test_every_window_yields_a_trace(run):
    ws, traces = run
    assert len(traces) == len(ws)
    assert [t.window_id for t in traces] == [w.window_id for w in ws]


def test_original_data_is_preserved_in_the_trace(run):
    ws, traces = run
    for w, t in zip(ws, traces):
        assert np.array_equal(t.initial_series, np.nan_to_num(w.series, nan=np.nan),
                              equal_nan=True)


def test_rolled_back_windows_keep_their_data(run):
    """A rejected candidate must leave no trace in the series."""
    _, traces = run
    for t in traces:
        rolled_only = t.records and all(
            r.verdict in ROLLBACK_VERDICTS or r.verdict is Verdict.NO_OP
            for r in t.records
        )
        if rolled_only:
            assert np.array_equal(t.final_series, t.initial_series, equal_nan=True)


def test_committed_edits_all_passed_verification(run):
    _, traces = run
    for t in traces:
        if t.modified:
            accepted = [r for r in t.records if r.accepted]
            assert accepted
            for r in accepted:
                assert r.delta_utility > 0.0
                assert r.struct_distortion < VerifyConfig().tau


def test_clean_windows_are_left_alone(run):
    ws, traces = run
    clean = [t for t in traces if t.stratum == "clean"]
    assert sum(t.modified for t in clean) <= 0.25 * len(clean)


def test_rare_valid_windows_are_protected(run):
    _, traces = run
    rare = [t for t in traces if t.stratum == "rare_valid"]
    assert sum(t.modified for t in rare) <= 0.2 * len(rare)


def test_spikes_are_repaired_towards_the_truth(run):
    ws, traces = run
    byid = {w.window_id: w for w in ws}
    improved = 0
    for t in traces:
        if t.contamination != "spike":
            continue
        c = byid[t.window_id].clean_series
        before = np.mean((t.initial_series - c) ** 2)
        after = np.mean((t.final_series - c[t.crop_offset:][: len(t.final_series)]) ** 2)
        improved += int(after < before)
    assert improved >= 5


def test_probe_budget_is_respected(run):
    _, traces = run
    limit = AgentConfig().max_probe_calls
    assert all(t.probe_calls <= limit for t in traces)


def test_trace_summary_is_serialisable(run):
    import json

    _, traces = run
    payload = json.dumps([t.summary() for t in traces], default=float)
    assert len(payload) > 0


def test_disabling_verification_edits_more(models_module):
    """The ablation must actually change behaviour, or it proves nothing."""
    ws = corpus()
    strict = IntroActAgent(models_module, AgentConfig(K_peers=10)).run(ws)
    loose = IntroActAgent(models_module, AgentConfig(
        K_peers=10,
        verification=VerifyConfig(
            require_structure=False, require_reprobe=False, require_risk=False
        ),
    )).run(ws)
    assert sum(t.modified for t in loose) >= sum(t.modified for t in strict)
    assert sum(t.n_rollbacks for t in loose) == 0
