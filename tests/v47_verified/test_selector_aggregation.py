"""Regression contracts; execute only in the designated server environment."""
from types import SimpleNamespace

import numpy as np
import pytest

from introact_ts.v47_verified import select as S


def queries(source, parent, horizon, severity):
    n = len(parent)
    return SimpleNamespace(source=np.array(source), parent=np.array(parent),
                           horizon=np.array(horizon), severity=np.array(severity),
                           episode=np.arange(n))


def test_bootstrap_point_matches_cell_source_macro_with_unbalanced_support():
    q = queries(["a", "a", "a", "b"], ["p", "p", "q", "r"],
                [96, 96, 192, 96], [.1] * 4)
    a, b = np.array([1., 1., 9., 3.]), np.zeros(4)
    result = S.paired_cluster_bootstrap(q, a, b, resamples=30)
    assert result["difference"] == pytest.approx(S.source_macro(q, a - b))
    assert result["difference"] == pytest.approx(5.5)


def test_lopo_scaler_excludes_all_query_parent_states():
    per = {}
    for action in S.ACTIONS:
        z = np.array([[1000., 0.], [-1000., 0.], [0., 0.], [2., 2.]])
        per[action] = S.ActionBank(z, np.zeros(4), np.array(["p", "p", "q", "r"]),
                                   np.array(["s"] * 4), np.array([96] * 4), np.array([.1] * 4))
    bank = SimpleNamespace(per=per)
    q = queries(["s"], ["p"], [96], [.1])
    q.Z = {a: np.array([[1., 0.]]) for a in S.ACTIONS}
    distances = S.distance_matrices(bank, q, lopo=True)
    for action in S.ACTIONS:
        assert np.isinf(distances[action][0, :2]).all()
        np.testing.assert_allclose(distances[action][0, 2:], [1., np.sqrt(5.)])


def fixed_queries():
    q = queries(["a"] * 10 + ["b"], [str(i) for i in range(11)],
                [96] * 11, [.1] * 11)
    q.legal = {a: np.zeros(11, bool) for a in S.ACTIONS}
    q.utility = {a: np.full(11, np.nan) for a in S.ACTIONS}
    q.metric = {"mase": {a: np.full(11, np.nan) for a in S.ACTIONS}}
    q.legal[S.REFERENCE][:] = True
    q.metric["mase"][S.REFERENCE][:] = 10.
    q.utility[S.REFERENCE][:] = 0.
    first, second = S.NONREF[:2]
    q.legal[first][:] = True
    q.metric["mase"][first][:] = [1.] * 10 + [12.]
    q.utility[first][:] = [9.] * 10 + [-2.]
    q.legal[second][-1] = True
    q.metric["mase"][second][-1] = 0.
    q.utility[second][-1] = 10.
    return q, first, second


def test_harm_anchor_and_best_fixed_share_macro_and_keep_denominator(monkeypatch):
    q, first, second = fixed_queries()
    # Episode means prefer first; source-macro with unsupported KEEP prefers second.
    result = S.harm_cap(None, q)
    assert result["anchor"] == second
    assert result["action_source_macro_mase"][first] == pytest.approx(6.5)
    assert result["action_source_macro_mase"][second] == pytest.approx(5.)
    monkeypatch.setattr(S, "Queries", lambda *args, **kwargs: q)
    assert S.best_fixed_action(SimpleNamespace(catalogs=[], blocks=())) == second


def test_fixed_evaluation_refuses_missing_keep_loss():
    q, first, second = fixed_queries()
    q.metric["mase"][S.REFERENCE][0] = np.nan
    with pytest.raises(ValueError, match="every request"):
        S.harm_cap(None, q)
