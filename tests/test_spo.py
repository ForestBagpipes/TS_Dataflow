"""SPO value tables, reward shaping and budget allocation."""
import numpy as np
import pytest

from introact_ts.spo import (ARMS, FIRST, AFTER_STRUCT, AFTER_UTIL, TABLES,
                             SPOConfig, ValueTables, allocate_budget,
                             shielded_reward, table_for)
from introact_ts.types import Action, Verdict


def test_tables_start_optimistic():
    from introact_ts.spo import N_SLOTS
    t = ValueTables(n_clusters=12)
    for name in TABLES:
        # One column per (arm, rung) slot, not per arm. Three settings of one
        # operator used to share a cell, which tied their bounds and left the
        # policy unable to rank them.
        assert t.Q[name].shape == (12, N_SLOTS)
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


def test_ucb_masks_infeasible_slots():
    from introact_ts.spo import slot
    t = ValueTables(n_clusters=2)
    t.t = 100
    feasible = {slot(Action.IMPUTE, "default"), slot(Action.DESPIKE, "default")}
    score = t.ucb(FIRST, 0, feasible=feasible)
    assert np.isfinite(score[slot(Action.IMPUTE, "default")])
    assert score[slot(Action.DENOISE, "default")] == -np.inf
    # A rung of a feasible arm that was not offered is masked too, which is
    # what keeps the bound from ranking a setting the proposer never gave.
    assert score[slot(Action.IMPUTE, "aggressive")] == -np.inf
    assert t.select(FIRST, 0, feasible={slot(Action.DENOISE, "conservative")})         == (Action.DENOISE, "conservative")
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


def test_set_column_writes_every_table_and_every_rung():
    from introact_ts.spo import TIERS, slot
    t = ValueTables(n_clusters=4)
    t.set_column(None, Action.RESEGMENT, -0.01, 20)
    for name in TABLES:
        for tier in TIERS:
            a = slot(Action.RESEGMENT, tier)
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


def test_injection_only_targets_unvisited_arms():
    from introact_ts.spo import SPOPolicy, INJECT_PARAMS
    t = ValueTables(n_clusters=2)
    # Mark IMPUTE as visited, leave the rest optimistic.
    t.warm_start(FIRST, 0, Action.IMPUTE, [0.5, 0.5])
    pol = SPOPolicy(t, p_inject=1.0, seed=1)
    assert Action.IMPUTE not in pol.unvisited(FIRST, 0)
    for _ in range(20):
        out = pol.inject([(Action.KEEP, {})], 0, [], FIRST)
        assert out[0][0] is not Action.IMPUTE
        assert out[0][0] in (Action.DESPIKE, Action.DENOISE, Action.RESEGMENT)
        # Injected candidates carry the conservative parameter set.
        assert out[0][1] == INJECT_PARAMS[out[0][0]]


def test_injection_respects_probability_and_is_reproducible():
    from introact_ts.spo import SPOPolicy
    def count(p, seed):
        pol = SPOPolicy(ValueTables(n_clusters=1), p_inject=p, seed=seed)
        return sum(len(pol.inject([(Action.KEEP, {})], 0, [], FIRST)) > 1
                   for _ in range(400))
    assert count(0.0, 3) == 0
    lo, hi = count(0.05, 3), count(0.5, 3)
    assert lo < hi
    # Same seed gives the same draw sequence, so a rerun reproduces exactly.
    assert count(0.05, 3) == count(0.05, 3)


def test_injection_skips_what_the_window_already_tried():
    from introact_ts.spo import SPOPolicy
    from introact_ts.types import ActionRecord, Verdict
    pol = SPOPolicy(ValueTables(n_clusters=1), p_inject=1.0, seed=2)
    hist = [ActionRecord(step=0, action=a, params={}, verdict=Verdict.ROLLED_BACK_UTILITY,
                         delta_utility=0.0, struct_distortion=0.0, risk=0.0,
                         utility_before=0.0, utility_after=0.0)
            for a in (Action.DESPIKE, Action.DENOISE, Action.RESEGMENT)]
    out = pol.inject([(Action.KEEP, {})], 0, hist, FIRST)
    # Only IMPUTE is left unvisited and untried, so that is what may appear.
    assert all(a in (Action.KEEP, Action.IMPUTE) for a, _ in out)


def test_order_puts_an_injected_arm_through_the_bound():
    from introact_ts.spo import SPOPolicy
    pol = SPOPolicy(ValueTables(n_clusters=1), p_inject=1.0, seed=4)
    out = pol.order([(Action.KEEP, {})], 0, [])
    # The injected arm is an arm, so it ranks ahead of the terminal action.
    assert out[0][0] in ARMS
    assert out[-1][0] is Action.KEEP
    assert sum(pol.injected.values()) == 1


def _drive(policy, steps=90, seed=11):
    """Run a fixed pseudo episode sequence, returning the arms chosen."""
    import numpy as np
    from introact_ts.types import Verdict
    rng = np.random.RandomState(seed)
    picked = []
    for _ in range(steps):
        cl = int(rng.randint(4))
        ordered = policy.order([(a, {}) for a in ARMS], cl, [])
        arm = ordered[0][0]
        picked.append(arm.value)
        verdict = (Verdict.ACCEPTED if rng.rand() < 0.4
                   else Verdict.ROLLED_BACK_STRUCTURE)
        policy.observe(cl, arm, verdict, float(rng.rand()), 1, [])
    return picked


def test_theorem_six_recording_does_not_change_decisions():
    # Section 3.5's instrumentation is recording only. If it ever moved a
    # decision the numbers it collects would describe a policy nobody ran.
    from introact_ts.spo import SPOConfig, SPOPolicy
    quiet = SPOConfig(reward_clip=5.0, t_cal=0)
    loud = SPOConfig(reward_clip=5.0, t_cal=10)
    a = _drive(SPOPolicy(ValueTables(n_clusters=4, cfg=quiet), quiet, seed=7))
    b = _drive(SPOPolicy(ValueTables(n_clusters=4, cfg=loud), loud, seed=7))
    assert a == b


def test_theorem_six_report_carries_the_three_bound_terms():
    from introact_ts.spo import SPOConfig, SPOPolicy
    cfg = SPOConfig(reward_clip=5.0, t_cal=10)
    pol = SPOPolicy(ValueTables(n_clusters=4, cfg=cfg), cfg, seed=7)
    _drive(pol)
    r = pol.theorem6_report()
    assert r["t_cal"] == 10 and r["reward_clip"] == 5.0
    assert r["n_decisions_with_choice"] > 0
    assert r["intervals"] and all(iv["n_min"] >= 1 for iv in r["intervals"])
    # The gap is a top two distance, so it is never negative.
    assert r["gamma"]["q0.00"] >= 0.0
    assert 0.0 <= r["gamma"]["zero_share"] <= 1.0


def test_a_zero_gap_reports_an_infinite_bound_rather_than_a_clipped_one():
    # Unvisited cells share an optimistic value and a visit count, so their
    # bounds are exactly equal and gamma is exactly zero. Theorem 6's worst
    # case form is then vacuous, and saying so is the point of measuring it.
    from introact_ts.spo import SPOConfig, SPOPolicy
    cfg = SPOConfig(reward_clip=5.0, t_cal=10)
    pol = SPOPolicy(ValueTables(n_clusters=4, cfg=cfg), cfg, seed=7)
    _drive(pol)
    if pol.theorem6_report()["gamma"]["q0.00"] == 0.0:
        assert pol.theorem6_report()["tv_bound_at_gamma_q0.00"] == float("inf")


def test_a_refused_candidate_updates_its_own_slot():
    """The policy learns where not to go from refusals, so they must land.

    A refusal carries the negated probe cost rather than nothing, and it has to
    reach the slot of the exact operator and rung that was refused. Before the
    rung dimension existed a refusal of the aggressive setting was recorded
    against the same cell as an acceptance of the conservative one, which is the
    two cancelling rather than the policy learning.
    """
    from introact_ts.policy import _at_rung
    from introact_ts.spo import SPOConfig, SPOPolicy, ValueTables, slot

    cfg = SPOConfig()
    tables = ValueTables(n_clusters=2, cfg=cfg)
    pol = SPOPolicy(tables, cfg, p_inject=0.0, seed=0)
    aggressive = _at_rung(Action.DESPIKE, "aggressive")

    before = float(tables.Q[FIRST][0, slot(Action.DESPIKE, "aggressive")])
    r = pol.observe(0, Action.DESPIKE, Verdict.ROLLED_BACK_STRUCTURE, 0.0, 1,
                    [], params=aggressive)
    assert r < 0.0, "a refusal must cost something, not nothing"

    hit = slot(Action.DESPIKE, "aggressive")
    assert tables.N[FIRST][0, hit] > cfg.optimistic_visits
    assert float(tables.Q[FIRST][0, hit]) < before
    # The other rungs of the same operator are untouched.
    for other in ("default", "conservative"):
        j = slot(Action.DESPIKE, other)
        assert tables.optimistic[FIRST][0, j], f"{other} was written to"


def test_the_bound_ranks_two_rungs_of_one_operator():
    """Two settings of one operator must be orderable, which was the point."""
    from introact_ts.policy import _at_rung
    from introact_ts.spo import SPOConfig, SPOPolicy, ValueTables

    cfg = SPOConfig()
    tables = ValueTables(n_clusters=2, cfg=cfg)
    pol = SPOPolicy(tables, cfg, p_inject=0.0, seed=0)
    # Teach it that the aggressive rung gets refused here.
    for _ in range(6):
        pol.observe(0, Action.DESPIKE, Verdict.ROLLED_BACK_STRUCTURE, 0.0, 1,
                    [], params=_at_rung(Action.DESPIKE, "aggressive"))

    cands = [(Action.DESPIKE, _at_rung(Action.DESPIKE, "aggressive")),
             (Action.DESPIKE, _at_rung(Action.DESPIKE, "conservative")),
             (Action.KEEP, {})]
    ordered = pol.order(list(cands), 0, [])
    first = ordered[0]
    assert first[0] is Action.DESPIKE
    from introact_ts.policy import rung_of
    assert rung_of(Action.DESPIKE, first[1]) != "aggressive", (
        "the refused rung should not stay first once it has been paid for")
