"""Decision-layer contracts for the registered v55 pooling change."""

from types import SimpleNamespace

import numpy as np
import pytest

from introact_ts.v47 import select as old
from introact_ts.v55 import select as pooled


def _fixture():
    per = {}
    for action in old.ACTIONS:
        if action == "FFILL":
            per[action] = SimpleNamespace(
                g=np.array([1.0, 1.0, -1.0, 0.5]),
                parent=np.array(["p1", "p1", "p2", "p3"]),
                source=np.array(["s", "s", "s", "other"]),
            )
        else:
            per[action] = SimpleNamespace(
                g=np.empty(0), parent=np.empty(0, dtype=object),
                source=np.empty(0, dtype=object),
            )
    bank = SimpleNamespace(per=per)
    query = SimpleNamespace(
        episode=np.arange(2), parent=np.array(["p1", "new"]),
        source=np.array(["s", "unseen"]),
        legal={a: np.ones(2, bool) for a in old.ACTIONS},
    )
    distances = {a: np.empty((2, 0)) for a in old.ACTIONS}
    distances["FFILL"] = np.array([[0.0, 0.0, np.inf, np.inf],
                                    [np.inf, np.inf, np.inf, np.inf]])
    return bank, query, distances


def test_source_mean_matches_record_weighted_fixed_policy_and_lopo():
    bank, query, _ = _fixture()
    means = pooled.source_action_means(bank)
    assert means["FFILL"]["s"]["mean"] == pytest.approx(1.0 / 3.0)
    result = pooled.source_vector(means, "FFILL", query, lopo=True)
    assert result[0] == pytest.approx(-1.0)
    assert np.isnan(result[1])


def test_lambda_zero_reproduces_v54_and_infinity_uses_source_mean():
    bank, query, distances = _fixture()
    moments = pooled.local_moments(bank, query, distances, k=4)
    means = pooled.source_action_means(bank)
    old_scores = old.score_grid(bank, query, distances, k=4, beta=1.0)
    zero = pooled.scores_from_moments(moments, means, query, 1.0, 0.0)
    for action in old.ACTIONS:
        np.testing.assert_allclose(zero[action], old_scores[action])
    infinite = pooled.scores_from_moments(moments, means, query, 1.0,
                                           float("inf"))
    assert infinite["FFILL"][0] == pytest.approx(1.0 / 3.0)
    assert infinite["FFILL"][1] == -np.inf


def test_finite_pool_uses_distinct_parent_count_and_source_fallback():
    bank, query, distances = _fixture()
    moments = pooled.local_moments(bank, query, distances, k=4)
    means = pooled.source_action_means(bank)
    score = pooled.scores_from_moments(moments, means, query, 0.0, 4.0)
    # Two records of p1 count as one local parent, with mean 1. The source
    # mean uses the Source Fixed record weighting, (1+1-1)/3 = 1/3.
    assert score["FFILL"][0] == pytest.approx(7.0 / 15.0)
    assert score["FFILL"][1] == -np.inf


def test_conformal_threshold_withdraws_harmful_execution():
    top = np.array([0.5, 0.4, 0.3, -np.inf])
    harm = np.array([0.7, 0.2, 0.0, 0.0])
    result = pooled.crc_threshold_from_arrays(top, harm, alpha=0.1)
    assert result["threshold"] == float("inf")
    assert result["intervention_rate"] == 0.0
    assert result["crc_bound"] <= 0.1


def test_no_feasible_finite_gate_keeps_unseen_high_score():
    query = SimpleNamespace(episode=np.arange(4),
                            legal={a: np.ones(4, bool) for a in old.ACTIONS},
                            utility={a: np.zeros(4) for a in old.ACTIONS})
    query.utility["FFILL"] = np.array([-0.7, -0.2, 0.0, 0.0])
    scores = {a: np.full(4, -np.inf) for a in old.ACTIONS}
    scores["FFILL"] = np.array([0.5, 0.4, 0.3, -np.inf])
    gate = pooled.conformal_threshold(query, scores, alpha=0.1)["selected"]
    assert gate["threshold"] == float("inf")
    future = SimpleNamespace(episode=np.arange(1),
                             legal={a: np.ones(1, bool) for a in old.ACTIONS})
    future_scores = {a: np.full(1, -np.inf) for a in old.ACTIONS}
    future_scores["FFILL"] = np.array([100.0])
    assert pooled.decide(future, future_scores,
                         threshold=gate["threshold"])[0] == old.REFERENCE
