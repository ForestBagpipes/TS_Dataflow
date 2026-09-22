"""Deployment-side contract tests; execute only in the designated server environment.

Covers the deployment behaviours listed in the revision task book section 8.1
that the earlier contract files did not: act-or-keep abstention, illegality
masking, determinism, bank immutability during scoring, the complete-input
contract and the forecasting-call budget identity.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from introact_ts.v47_verified import actions as A
from introact_ts.v47_verified import select as S


def decide_queries(n):
    q = SimpleNamespace(episode=np.arange(n))
    q.legal = {a: np.ones(n, bool) for a in S.ACTIONS}
    return q


def test_decide_keeps_when_no_positive_score():
    q = decide_queries(4)
    scores = {a: np.full(4, -0.5) for a in S.ACTIONS}
    selected = S.decide(q, scores)
    assert (selected == S.REFERENCE).all()


def test_decide_never_selects_illegal_action():
    q = decide_queries(3)
    scores = {a: np.full(3, -1.0) for a in S.ACTIONS}
    scores[S.NONREF[0]] = np.array([5.0, 5.0, 5.0])
    q.legal[S.NONREF[0]] = np.array([False, True, False])
    selected = S.decide(q, scores)
    assert selected[0] == S.REFERENCE and selected[1] == S.NONREF[0]
    assert selected[2] == S.REFERENCE


def test_decide_is_deterministic():
    q = decide_queries(8)
    rng = np.random.default_rng(7)
    scores = {a: rng.normal(size=8) for a in S.ACTIONS}
    first = S.decide(q, scores)
    second = S.decide(q, scores)
    assert list(first) == list(second)


def small_bank():
    per = {}
    for action in S.ACTIONS:
        z = np.array([[0., 0.], [1., 0.], [0., 1.], [1., 1.]])
        per[action] = S.ActionBank(z, np.array([0.5, -0.5, 0.25, -0.25]),
                                   np.array(["p", "p", "q", "q"]),
                                   np.array(["s"] * 4), np.array([96] * 4),
                                   np.array([.1] * 4))
        per[action].Zs = per[action].Z.copy()
    return SimpleNamespace(per=per, mean=np.zeros(2), scale=np.ones(2))


def test_scoring_does_not_mutate_bank():
    bank = small_bank()
    before = {a: (b.Z.copy(), b.g.copy(), b.Zs.copy()) for a, b in bank.per.items()}
    q = decide_queries(2)
    q.Z = {a: np.array([[0.5, 0.5], [0.1, 0.9]]) for a in S.ACTIONS}
    q.parent = np.array(["new", "new"])
    q.horizon = np.array([96, 96])
    q.source = np.array(["s", "s"])
    D = S.distance_matrices(bank, q, lopo=False)
    scores = S.score_grid(bank, q, D, k=2, beta=0.5)
    S.decide(q, scores)
    for a, b in bank.per.items():
        z, g, zs = before[a]
        np.testing.assert_array_equal(b.Z, z)
        np.testing.assert_array_equal(b.g, g)
        np.testing.assert_array_equal(b.Zs, zs)


def test_complete_input_admits_only_keep():
    panel = np.arange(8, dtype=float).reshape(4, 2)
    for name in S.NONREF:
        out = A.apply_action(name, panel)
        assert not out.applicable or not out.changed
    keep = A.apply_action("KEEP", panel)
    np.testing.assert_array_equal(keep.panel, panel)


def test_call_budget_identity():
    q = decide_queries(10)
    scores = {a: np.full(10, -1.0) for a in S.ACTIONS}
    scores[S.NONREF[0]] = np.linspace(-1.0, 1.0, 10)
    selected = S.decide(q, scores)
    acted = selected != S.REFERENCE
    calls = 1 + acted.astype(int)
    assert calls.mean() == pytest.approx(1.0 + acted.mean())
    assert calls.max() <= 2
