"""SPO value tables, reward shaping and budget allocation."""
import numpy as np
import pytest

from introact_ts.spo import (ARMS, FIRST, AFTER_STRUCT, AFTER_UTIL, TABLES,
                             SPOConfig, ValueTables, allocate_budget,
                             shielded_reward, table_for)
from introact_ts.types import Action, Verdict


def test_tables_start_optimistic():
    t = ValueTables(n_clusters=12)
    for name in TABLES:
        assert t.Q[name].shape == (12, 4)
        assert t.optimistic[name].all()
        assert np.allclose(t.Q[name], t.cfg.optimistic_init)


def test_reward_clip_bounds_the_admitted_reward():
    # Theorem 5's regret bound needs a bounded reward. Unclipped, one window
    # with a utility change of 65 dominates an exploration width of 0.87.
    cfg = SPOConfig(reward_clip=2.78)
    assert shielded_reward(Verdict.ACCEPTED, 65.2, 1, cfg) == 2.78
    assert shielded_reward(Verdict.ACCEPTED, 0.2, 1, cfg) == pytest.approx(0.2)
    # Clipping is one sided, a rollback cost is already bounded by c0.
    assert shielded_reward(Verdict.ROLLED_BACK_UTILITY, 65.2, 1, cfg) == -cfg.c0


def test_reward_is_shielded_not_raw():
    cfg = SPOConfig()
    # An admitted candidate earns its utility change.
    assert shielded_reward(Verdict.ACCEPTED, 2.5, 1, cfg) == 2.5
    # A rollback earns the negated probe cost regardless of how good the raw
    # utility change looked. This is the mechanism experiment two tests.
    assert shielded_reward(Verdict.ROLLED_BACK_STRUCTURE, 9.9, 1, cfg) == -cfg.c0
    assert shielded_reward(Verdict.ROLLED_BACK_UTILITY, 9.9, 3, cfg) == -3 * cfg.c0
    # Terminal and inapplicable earn zero.
    assert shielded_reward(Verdict.NO_OP, 5.0, 1, cfg) == 0.0


def test_table_routing_by_previous_verdict():
    assert table_for(None) == FIRST
    assert table_for(Verdict.ROLLED_BACK_STRUCTURE) == AFTER_STRUCT
    assert table_for(Verdict.ROLLED_BACK_UTILITY) == AFTER_UTIL
    # A risk rollback has no dedicated table, it falls back to the first.
    assert table_for(Verdict.ROLLED_BACK_RISK) == FIRST


def test_warm_start_uses_expected_shielded_reward():
    t = ValueTables(n_clusters=3)
    # Ten adjudicated, two admitted at +1.0, eight rolled back at -c0.
    rewards = [1.0, 1.0] + [-t.cfg.c0] * 8
    t.warm_start(FIRST, 0, Action.IMPUTE, rewards)
    q = t.Q[FIRST][0, ARMS.index(Action.IMPUTE)]
    assert q == pytest.approx(0.2 * 1.0 + 0.8 * (-t.cfg.c0))
    assert not t.optimistic[FIRST][0, ARMS.index(Action.IMPUTE)]
    # A cell nobody visited stays optimistic and stays above a seeded one.
    assert t.optimistic[FIRST][1, ARMS.index(Action.IMPUTE)]
    assert t.Q[FIRST][1, ARMS.index(Action.IMPUTE)] > q


def test_ucb_masks_infeasible_arms():
    t = ValueTables(n_clusters=2)
    t.t = 100
    score = t.ucb(FIRST, 0, feasible={Action.IMPUTE, Action.DESPIKE})
    assert np.isfinite(score[ARMS.index(Action.IMPUTE)])
    assert score[ARMS.index(Action.DENOISE)] == -np.inf
    assert t.select(FIRST, 0, feasible={Action.DENOISE}) is Action.DENOISE
    assert t.select(FIRST, 0, feasible=set()) is None


def test_update_is_incremental_mean():
    t = ValueTables(n_clusters=1, cfg=SPOConfig(optimistic_visits=1,
                                                optimistic_init=0.0))
    a = ARMS.index(Action.IMPUTE)
    t.update(FIRST, 0, Action.IMPUTE, 1.0)
    # One pseudo visit at 0.0 plus one real at 1.0 gives 0.5.
    assert t.Q[FIRST][0, a] == pytest.approx(0.5)
    assert t.t == 1
    assert not t.optimistic[FIRST][0, a]


def test_set_column_writes_every_table():
    t = ValueTables(n_clusters=4)
    t.set_column(None, Action.RESEGMENT, -0.01, 20)
    a = ARMS.index(Action.RESEGMENT)
    for name in TABLES:
        assert np.allclose(t.Q[name][:, a], -0.01)
        assert not t.optimistic[name][:, a].any()


def test_tail_cluster_routing():
    t = ValueTables(n_clusters=5, cluster_map={0: 0, 1: 1, 2: 2, 3: 1, 4: 2})
    t.warm_start(FIRST, 1, Action.IMPUTE, [2.0] * 4 + [-0.01] * 4)
    # Cluster 3 was merged into 1, so it reads 1's value.
    assert t.Q[FIRST][t.resolve(3), ARMS.index(Action.IMPUTE)] == \
           t.Q[FIRST][1, ARMS.index(Action.IMPUTE)]


def test_budget_skips_settled_clean_windows():
    t = ValueTables(n_clusters=2)
    t.set_column(None, Action.IMPUTE, 1.0, 5)
    clusters = [0, 0, 1, 1]
    costs = [1.0, 1.0, 1.0, 1.0]
    skip = [False, True, False, True]
    alloc = allocate_budget(clusters, costs, t, total_budget=10, skip_mask=skip)
    assert alloc[1] == 0 and alloc[3] == 0
    assert alloc[0] > 0 and alloc[2] > 0
    assert alloc.sum() <= 10


def test_budget_respects_the_total():
    t = ValueTables(n_clusters=1)
    alloc = allocate_budget([0] * 10, [3.0] * 10, t, total_budget=7)
    assert alloc.sum() <= 7
