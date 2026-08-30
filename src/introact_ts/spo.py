"""SPO, policy optimisation and budget allocation from shielded feedback.

This is the fourth module. CDP builds the state, SIR re runs the intervention in
a sandbox, CDS adjudicates, and SPO learns which operator to propose in which
kind of window and how to spend the probe budget across a corpus.

Design follows section 3.4 of the progress document. It is a contextual bandit
rather than deep reinforcement learning, because the decision sequence is short,
most windows finish within three steps, the state is low dimensional after CDP,
and the action set is small. Action selection is upper confidence bound over the
shielded feasible set

    a_t = argmax_{a in A_shield(s)} [ Q(j, a) + c_u * sqrt( 2 ln t / n(j, a) ) ]

where j is the profile cluster and A_shield(s) is non empty by theorem 2.

**Three tables, not one.** Section 3.4 requires the rollback reason to enter the
context so that a structural veto and a utility veto lead to different follow up
distributions. That is implemented as three separate tables:

    Q0        the first proposal in a window
    Q_struct  a retry after the structural condition rejected the previous one
    Q_util    a retry after the utility condition rejected the previous one

The reason they are separate rather than one table with an extra feature is that
the two vetoes point in different directions. A structural veto means the
footprint was too large, so the follow up should be a smaller footprint
operator. A utility veto means the defect diagnosis may be wrong, so the follow
up should reconsider which defect is present. A single table would average these
into one ordering, which is exactly the failure the fixed rule showed.

**Reward is the shielded value, never the raw one.** An admitted candidate earns
its utility change, a rolled back one earns the negated probe cost, and a
terminal action earns zero. Learning from raw delta utility would train the
policy toward edits the shield rejects, which is the mechanism experiment two
tests.

This module performs no file IO. Warm start statistics are passed in.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .policy import _key as _key_of
from .policy import rung_of
from .types import Action, MUTATING_ACTIONS, Verdict

#: Operators the policy chooses among. Terminal actions end the episode and are
#: not learned over, they are the policy's option to stop rather than an arm.
ARMS = (Action.IMPUTE, Action.DESPIKE, Action.DENOISE, Action.RESEGMENT)

#: Parameter rungs the value table distinguishes, in `policy.RUNG_ORDER`'s
#: order. An arm and a rung together are one slot, which is the unit the bound
#: ranks and the unit a reward updates.
#:
#: Before this the table was indexed by arm alone, so three settings of one
#: operator shared a cell, their bounds were equal, and `sorted` left them in
#: the order they arrived. The policy could reorder operators and not settings,
#: which is most of what there is to choose between once the proposer has routed
#: a defect to its operator.
TIERS = ("default", "conservative", "aggressive")
N_SLOTS = len(ARMS) * len(TIERS)


def slot(arm: Action, tier: str = "default") -> int:
    """Flat index of one (arm, rung) pair."""
    t = TIERS.index(tier) if tier in TIERS else 0
    return ARMS.index(arm) * len(TIERS) + t


def slot_arm(i: int) -> Action:
    return ARMS[i // len(TIERS)]


def slot_tier(i: int) -> str:
    return TIERS[i % len(TIERS)]

#: Parameters an injected candidate carries, one per operator.
#:
#: Section 3.4 requires an injected candidate to take the least aggressive
#: setting the operator offers, because it is probing a cell with no
#: information behind it and should not also carry an aggressive configuration.
#: Two of these used to be empty dicts, which falls back to the operator's own
#: default rather than to its conservative end, so the requirement held for
#: DENOISE alone. That is an implementation not matching a stated design, and
#: the correction is recorded in docs/spo_preregistration.md with its date.
#:
#: The wording in 3.4 is now the least aggressive setting rather than the most
#: conservative one, because IMPUTE's conservatism is in not assuming a period
#: rather than in a magnitude, and one word cannot describe both axes.
INJECT_PARAMS = {
    # Linear fill assumes no periodicity, against the seasonal default.
    Action.IMPUTE: {"method": "linear"},
    # n_sigma raised and max_width cut to one, so only the narrowest and most
    # extreme excursions are touched. Defaults are 4.0 and 3.
    Action.DESPIKE: {"n_sigma": 6.0, "max_width": 1},
    # Window five against the default eleven, the shortest the operator allows.
    Action.DENOISE: {"strength": "light"},
    # Keeps at least nine tenths of the window, against a default that permits
    # discarding half of it.
    Action.RESEGMENT: {"min_keep_frac": 0.9},
}

#: Which table a candidate belongs to, keyed by the verdict on the previous
#: candidate in the same window. The first candidate has no predecessor.
FIRST = "Q0"
AFTER_STRUCT = "Q_struct"
AFTER_UTIL = "Q_util"
TABLES = (FIRST, AFTER_STRUCT, AFTER_UTIL)


@dataclass
class SPOConfig:
    """Hyperparameters, initial values from table 3 of the progress document."""

    #: Exploration coefficient of the upper confidence bound.
    c_u: float = 1.0
    #: Probe cost conversion. A rollback earns -c0 times the probes it burned.
    c0: float = 0.01
    #: Value given to a cell the fixed policy never visited, so the bound sends
    #: the policy there. Set above any plausible real value on purpose.
    optimistic_init: float = 1.0
    #: Prior strength of the warm start, in pseudo visits. A cell warm started
    #: from m adjudicated candidates enters with min(m, warm_start_cap) visits,
    #: so history informs the estimate without freezing it.
    warm_start_cap: int = 20
    #: Visits credited to an optimistically initialised cell. One, so a single
    #: real observation moves it substantially.
    optimistic_visits: int = 1
    #: Upper bound the admitted reward is clipped to, or None for no clipping.
    #:
    #: This is not cosmetic. Theorem 5 gives a regret of O(sqrt(T d log T)) for
    #: the upper confidence bound policy, and that analysis requires the reward
    #: to be bounded or sub Gaussian. The measured utility change is neither. On
    #: the reference corpus its median is 0.202 while its 99th percentile is
    #: 54.9, so six windows out of 404 admissions carry values that exceed the
    #: exploration width of 0.872 by more than an order of magnitude. Left
    #: unclipped, whichever cell holds one of those six is selected forever and
    #: the bound stops exploring, which breaks the theorem's premise rather than
    #: its conclusion.
    #:
    #: The bound is a quantile of the *training* split only, passed in by the
    #: caller, so the evaluation split never informs it.
    reward_clip: Optional[float] = None
    #: Decisions between two conformal recalibrations, section 3.5's T_cal.
    #:
    #: Theorem 6 bounds the guarantee's decay between calibrations by
    #: 2 q T_cal / (gamma n_min), so the interval is the only term in that bound
    #: the implementation chooses. It is recorded here rather than left to the
    #: caller so it enters the configuration hash, which means a run cannot
    #: report the bound under one interval while having used another.
    t_cal: int = 500


@dataclass
class ValueTables:
    """Q and visit counts for every table, cluster and arm.

    Shapes are (n_clusters, N_SLOTS) per table, a slot being one arm at one
    parameter rung. ``t`` is the global decision
    count the confidence width is computed against, shared across tables because
    it counts decisions the policy made, not updates to one cell.
    """

    n_clusters: int
    cfg: SPOConfig = field(default_factory=SPOConfig)
    Q: dict = field(default_factory=dict)
    N: dict = field(default_factory=dict)
    t: int = 0
    #: Cells that hold an optimistic value rather than a warm started one, for
    #: reporting which parts of the grid the policy is exploring blind.
    optimistic: dict = field(default_factory=dict)
    #: Maps a tail cluster onto the large cluster it was merged into. Identity
    #: for every cluster that was not merged.
    cluster_map: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.Q:
            shape = (self.n_clusters, N_SLOTS)
            for name in TABLES:
                self.Q[name] = np.full(shape, self.cfg.optimistic_init, dtype=np.float64)
                self.N[name] = np.full(shape, self.cfg.optimistic_visits, dtype=np.int64)
                self.optimistic[name] = np.ones(shape, dtype=bool)
        if not self.cluster_map:
            self.cluster_map = {c: c for c in range(self.n_clusters)}

    def resolve(self, cluster: int) -> int:
        """Tail clusters route to the large cluster they were merged into."""
        return self.cluster_map.get(int(cluster), int(cluster))

    def warm_start(self, table: str, cluster: int, arm: Action, rewards,
                   tier: str = "default") -> None:
        """Seed one cell from what the fixed policy actually earned there.

        ``rewards`` is the sequence of shielded rewards, one per adjudicated
        candidate, already passed through :func:`shielded_reward` and therefore
        already clipped. Averaging them is the estimate the policy would hold
        after seeing that history, which is what a warm start should be. Note
        that rolled back candidates contribute their negative probe cost, so a
        cell where nothing was ever admitted seeds below zero rather than at
        zero, and the policy has a reason to prefer an unvisited cell over a
        known bad one.
        """
        rewards = np.asarray(list(rewards), dtype=np.float64)
        if rewards.size == 0:
            return
        j, a = self.resolve(cluster), slot(arm, tier)
        self.Q[table][j, a] = float(rewards.mean())
        self.N[table][j, a] = int(min(rewards.size, self.cfg.warm_start_cap))
        self.optimistic[table][j, a] = False

    def set_column(self, table: str, arm: Action, value: float, visits: int) -> None:
        """Set a whole operator column, for an arm with no cluster level structure.

        Stage zero found RESEGMENT's admission rate flat across clusters at every
        k tested, permutation p from 0.81 to 0.96. Seeding it per cluster would
        encode noise as signal, so the column carries its global mean instead.
        """
        for t in TIERS:
            a = slot(arm, t)
            for name in ([table] if table else TABLES):
                self.Q[name][:, a] = value
                self.N[name][:, a] = visits
                self.optimistic[name][:, a] = False

    def ucb(self, table: str, cluster: int, feasible) -> np.ndarray:
        """Upper confidence bound over the arms, section 3.4's formula.

        ``feasible`` is a set of slot indices. Infeasible slots are masked to
        negative infinity rather than dropped, so the returned vector stays
        aligned with the flat slot order.
        """
        j = self.resolve(cluster)
        q = self.Q[table][j]
        n = np.maximum(self.N[table][j], 1)
        t = max(self.t, 1)
        width = self.cfg.c_u * np.sqrt(2.0 * np.log(t) / n)
        score = q + width
        mask = np.array([i in feasible for i in range(N_SLOTS)])
        return np.where(mask, score, -np.inf)

    def select(self, table: str, cluster: int, feasible):
        """Highest bound among feasible slots, as (arm, rung), or None."""
        score = self.ucb(table, cluster, feasible)
        if not np.isfinite(score).any():
            return None
        i = int(np.argmax(score))
        return slot_arm(i), slot_tier(i)

    def update(self, table: str, cluster: int, arm: Action, reward: float,
               tier: str = "default") -> None:
        """Incremental mean update, the standard form, on one slot."""
        j, a = self.resolve(cluster), slot(arm, tier)
        self.N[table][j, a] += 1
        n = self.N[table][j, a]
        self.Q[table][j, a] += (reward - self.Q[table][j, a]) / n
        self.optimistic[table][j, a] = False
        self.t += 1

    def snapshot(self) -> dict:
        """Plain nested lists, for a caller that wants to persist the tables."""
        return {
            "n_clusters": self.n_clusters,
            "arms": [a.value for a in ARMS],
            "tiers": list(TIERS),
            "t": self.t,
            "cluster_map": {str(k): v for k, v in self.cluster_map.items()},
            "Q": {k: v.tolist() for k, v in self.Q.items()},
            "N": {k: v.tolist() for k, v in self.N.items()},
            "optimistic": {k: v.tolist() for k, v in self.optimistic.items()},
        }


def shielded_reward(verdict, delta_utility: float, probes: int,
                    cfg: SPOConfig) -> float:
    """The reward SPO learns from. Never the raw utility change.

    An admitted candidate earns its utility change as the shield measured it. A
    rolled back one earns the negated cost of the probes it burned, which is what
    makes a hopeless proposal expensive rather than free. Terminal actions and
    inapplicable operators earn zero, they neither helped nor cost a decision.
    """
    name = getattr(verdict, "value", verdict)
    if name == "ACCEPTED":
        r = float(delta_utility)
        return r if cfg.reward_clip is None else min(r, cfg.reward_clip)
    if name.startswith("ROLLED_BACK"):
        return -cfg.c0 * float(max(probes, 1))
    return 0.0


def table_for(previous_verdict) -> str:
    """Which table a candidate is drawn from, given the verdict before it."""
    if previous_verdict is None:
        return FIRST
    name = getattr(previous_verdict, "value", previous_verdict)
    if name == "ROLLED_BACK_STRUCTURE":
        return AFTER_STRUCT
    if name == "ROLLED_BACK_UTILITY":
        return AFTER_UTIL
    return FIRST


def allocate_budget(clusters, costs, tables: ValueTables, total_budget: int,
                    skip_mask=None) -> np.ndarray:
    """Spread a corpus level probe budget over windows, section 3.4.

    Windows are ranked by expected return over cost, expected return being the
    best value any arm offers in that window's cluster. A window whose defect
    posterior is settled and points at clean gets zero and is skipped outright,
    which is where the saving comes from.

    Args:
        clusters: per window cluster id.
        costs: per window estimated probe cost, same length.
        total_budget: probes to distribute.
        skip_mask: per window bool, True means settled and clean, give it zero.

    Returns:
        Integer probes per window, summing to at most ``total_budget``.
    """
    clusters = np.asarray(clusters, dtype=int)
    costs = np.asarray(costs, dtype=np.float64)
    n = len(clusters)
    alloc = np.zeros(n, dtype=np.int64)
    skip = (np.zeros(n, dtype=bool) if skip_mask is None
            else np.asarray(skip_mask, dtype=bool))

    value = np.array([tables.Q[FIRST][tables.resolve(c)].max() for c in clusters])
    ratio = value / np.maximum(costs, 1e-9)
    ratio[skip] = -np.inf

    order = np.argsort(-ratio)
    left = int(total_budget)
    for i in order:
        if left <= 0 or skip[i] or not np.isfinite(ratio[i]):
            break
        take = int(min(max(1, round(costs[i])), left))
        alloc[i] = take
        left -= take
    return alloc


class SPOPolicy:
    """Chooses the order candidates are tried in, and learns from the verdicts.

    This wraps :class:`ValueTables` into the shape ``curate_window`` needs. The
    proposer still generates the candidate set, and the shield still decides
    what is admitted. What the policy changes is which candidate is tried first,
    which is the only thing stage zero found learnable structure in.

    The table a decision is drawn from depends on the verdict of the previous
    candidate in the same window, so a retry after a structural veto and a retry
    after a utility veto consult different estimates.
    """

    def __init__(self, tables: ValueTables, cfg: SPOConfig = None,
                 p_inject: float = 0.0, seed: int = 20260819):
        self.tables = tables
        self.cfg = cfg or tables.cfg
        #: Probability of forcing an unvisited operator into the candidate set.
        #:
        #: Optimistic initialisation acts on the selection layer, and the first
        #: xl run showed that is the wrong layer for this corpus. Clusters 1 and
        #: 11 hold 392 windows between them, 19.6 percent of the corpus, and the
        #: proposer never emits DENOISE on any of them because their dominant
        #: defect is never noise. The bound cannot select what is not offered,
        #: so both cells were visited zero times and their Q stayed at the
        #: optimistic value from start to finish.
        #:
        #: Injection puts the operator into the candidate set directly. The
        #: injected candidate goes through the sandbox and the full shield like
        #: any other, so theorem 3 covers it without modification, the structural
        #: bound holds for every committed edit regardless of where the candidate
        #: came from.
        self.p_inject = float(p_inject)
        #: Whether the policy learns from the shielded reward or from the raw
        #: utility change. True is the method. False is the ablation rung that
        #: section 3.3 predicts will drive the policy toward flattening edits,
        #: because an unfiltered delta utility rewards exactly the actions the
        #: structural condition exists to stop.
        self.shaped_reward = True
        self._rng = np.random.RandomState(seed)
        #: Injection counters, for reporting how much of the exploration was
        #: forced rather than chosen.
        self.injected = defaultdict(int)
        #: Per cell counters for reporting, keyed by (table, cluster, arm).
        self.visits = defaultdict(int)
        self.accepts = defaultdict(int)
        self.rewards = defaultdict(list)
        #: Q value after every update, for the learning curves.
        self.trace = defaultdict(list)

        # -- theorem 6 instrumentation, recording only --------------------
        #
        # The theorem bounds the decay of the risk guarantee between two
        # calibrations by 2 q T_cal / (gamma n_min), and section 3.5 notes the
        # gap condition gamma > 0 has never been checked against data. Nothing
        # below feeds a decision. The bound's three measurable terms are
        # collected so experiment six's calibration interval rung can compare
        # the predicted decay against the observed one, and so the lower tail of
        # gamma can say whether the worst case form of the theorem applies at
        # all or whether it has to be restated in expectation.
        #
        #: Gap between the best and second best upper confidence bound at every
        #: decision where at least two arms were feasible.
        self.ucb_gaps = []
        #: One entry per completed calibration interval.
        self.intervals = []
        #: Cells updated since the last interval boundary, and their counts.
        self._interval_updates = defaultdict(int)
        self._interval_start_t = int(self.tables.t)

    @staticmethod
    def _prev_verdict(records):
        """Verdict of the last adjudicated candidate, or None if there is none."""
        for r in reversed(records):
            if r.action in MUTATING_ACTIONS and r.verdict is not Verdict.NO_OP:
                return r.verdict
        return None

    def table_of(self, records) -> str:
        return table_for(self._prev_verdict(records))

    def unvisited(self, table: str, cluster: int):
        """Arms with no observation at any rung, in the given table.

        Reported per arm rather than per slot because injection offers an
        operator the proposer never routed to, and offering one rung of an
        operator the policy has never seen is the same probe as offering
        another. The rung an injected candidate carries is fixed by
        INJECT_PARAMS.
        """
        j = self.tables.resolve(cluster)
        out = []
        for a in ARMS:
            if all(self.tables.optimistic[table][j, slot(a, t)] for t in TIERS):
                out.append(a)
        return out

    def inject(self, candidates, cluster: int, records, table: str) -> list:
        """Add an unvisited operator to the candidate set, with probability.

        Only operators the window has not already tried are eligible, so an
        injection never re proposes something the shield already ruled on in
        this episode.
        """
        if self.p_inject <= 0.0:
            return candidates
        tried = {r.action for r in records}
        present = {a for a, _ in candidates}
        pool = [a for a in self.unvisited(table, cluster)
                if a not in tried and a not in present]
        if not pool:
            return candidates
        if self._rng.random_sample() >= self.p_inject:
            return candidates
        arm = pool[int(self._rng.randint(len(pool)))]
        self.injected[(table, self.tables.resolve(cluster), arm.value)] += 1
        return [(arm, dict(INJECT_PARAMS.get(arm, {})))] + list(candidates)

    def order(self, candidates, cluster: int, records) -> list:
        """Reorder the proposer's candidates by the upper confidence bound.

        Terminal actions keep their position, because they are the policy's
        option to stop rather than arms it is choosing among, and moving them
        would change when an episode ends rather than what it tries.
        """
        if not candidates:
            return candidates
        table = self.table_of(records)
        candidates = self.inject(candidates, cluster, records, table)
        # A candidate's slot is its operator and its parameter rung together,
        # so two settings of one operator are ranked against each other rather
        # than tied. Ranking them was impossible while the table was indexed by
        # operator alone.
        slots = {}
        for a, p in candidates:
            if a in ARMS:
                slots[(a, _key_of(p))] = slot(a, rung_of(a, p))
        if not slots:
            return candidates
        score = self.tables.ucb(table, cluster, set(slots.values()))
        self._record_gap(score, table, cluster)

        arms, tail = [], []
        for a, p in candidates:
            (arms if a in ARMS else tail).append((a, p))
        arms.sort(key=lambda ap: -score[slots[(ap[0], _key_of(ap[1]))]])
        return arms + tail

    def _record_gap(self, score: np.ndarray, table: str, cluster: int) -> None:
        """Store the top two gap of one decision's confidence bounds.

        Theorem 6's second inequality needs gamma, the infimum over states of
        the distance between the best and second best bound. A single arm is
        not a choice, so those decisions contribute nothing.
        """
        finite = np.sort(score[np.isfinite(score)])[::-1]
        if finite.size < 2:
            return
        self.ucb_gaps.append({
            "t": int(self.tables.t),
            "table": table,
            "cluster": int(self.tables.resolve(cluster)),
            "gap": float(finite[0] - finite[1]),
            "n_feasible": int(finite.size),
        })

    def _close_interval(self) -> None:
        """Snapshot one calibration interval's minimum visit count.

        The minimum is taken over cells that were actually updated in the
        interval. A cell nobody touched has an unchanged Q and contributes
        nothing to the total variation, so counting its zero visits would drive
        the bound to infinity for a reason that has nothing to do with the
        quantity being bounded.
        """
        counts = list(self._interval_updates.values())
        self.intervals.append({
            "t_start": self._interval_start_t,
            "t_end": int(self.tables.t),
            "n_updates": int(sum(counts)),
            "cells_touched": len(counts),
            "n_min": int(min(counts)) if counts else 0,
            "n_min_cumulative": int(min(
                self.tables.N[t][j, a]
                for (t, j, a) in self._interval_updates)) if counts else 0,
        })
        self._interval_updates = defaultdict(int)
        self._interval_start_t = int(self.tables.t)

    def observe(self, cluster: int, action: Action, verdict, delta_utility: float,
                probes: int, records, params=None) -> float:
        """Update the slot this decision came from, and return the reward.

        Every adjudicated candidate updates its own slot, refused ones
        included. A refusal is the only evidence the policy gets that a given
        operator at a given rung does not clear the shield in this cluster, and
        without it the table would learn from acceptances alone and never learn
        where not to go. The reward for a refusal is the negated probe cost, so
        it is a small negative rather than a zero.
        """
        if action not in ARMS:
            return 0.0
        tier = rung_of(action, params or {})
        table = self.table_of(records[:-1] if records else [])
        if self.shaped_reward:
            reward = shielded_reward(verdict, delta_utility, probes, self.cfg)
        else:
            # The raw reading, whatever the shield decided. The candidate is
            # still rolled back, so this changes what is learned and not what is
            # committed, which is the comparison experiment two needs.
            reward = float(delta_utility)
            if self.cfg.reward_clip is not None:
                reward = min(reward, float(self.cfg.reward_clip))
        self.tables.update(table, cluster, action, reward, tier=tier)

        j0, a0 = self.tables.resolve(cluster), slot(action, tier)
        self._interval_updates[(table, j0, a0)] += 1
        if self.cfg.t_cal and self.tables.t - self._interval_start_t >= self.cfg.t_cal:
            self._close_interval()

        key = (table, self.tables.resolve(cluster), f"{action.value}|{tier}")
        self.visits[key] += 1
        self.accepts[key] += int(getattr(verdict, "value", verdict) == "ACCEPTED")
        self.rewards[key].append(reward)
        j, a = self.tables.resolve(cluster), slot(action, tier)
        self.trace[key].append(float(self.tables.Q[table][j, a]))
        return reward

    def injection_report(self) -> dict:
        return {f"{t}|{c}|{a}": n for (t, c, a), n in self.injected.items()}

    def theorem6_report(self, quantiles=(0.0, 0.01, 0.05, 0.25, 0.50)) -> dict:
        """The three measurable terms of theorem 6's decay bound.

        Returns the empirical distribution of the confidence bound gap, the per
        interval minimum visit count, and the bound each interval implies. The
        bound is 2 q T_cal / (gamma n_min) with q the reward clip, and it is
        evaluated at several lower quantiles of gamma rather than at the
        infimum alone: section 3.5 states the worst case form fails if the lower
        tail of gamma reaches zero, and reporting the quantiles is how that is
        decided rather than assumed.

        A gamma of zero produces an infinite bound. That is the theorem's own
        content, not a defect in the measurement, so it is reported as infinity
        rather than clipped.
        """
        gaps = np.array([g["gap"] for g in self.ucb_gaps], dtype=np.float64)
        if self._interval_updates:
            self._close_interval()
        q = self.cfg.reward_clip
        out = {
            "t_cal": int(self.cfg.t_cal),
            "reward_clip": float(q) if q is not None else None,
            "n_decisions_with_choice": int(gaps.size),
            "gamma": {},
            "intervals": list(self.intervals),
        }
        if gaps.size:
            out["gamma"] = {
                **{f"q{p:.2f}": float(np.quantile(gaps, p)) for p in quantiles},
                "mean": float(gaps.mean()),
                "n_zero": int(np.sum(gaps <= 1e-12)),
                "zero_share": float(np.mean(gaps <= 1e-12)),
            }
        if gaps.size and q is not None and self.intervals:
            n_min = [iv["n_min"] for iv in self.intervals if iv["n_min"] > 0]
            for p in quantiles:
                g = float(np.quantile(gaps, p))
                key = f"tv_bound_at_gamma_q{p:.2f}"
                if g <= 1e-12 or not n_min:
                    out[key] = float("inf")
                else:
                    out[key] = [2.0 * float(q) * self.cfg.t_cal / (g * nm)
                                for nm in n_min]
        return out

    def report(self) -> dict:
        """Per cell visits, admission rate, mean reward and the Q trajectory."""
        out = {}
        for key, n in self.visits.items():
            table, cluster, arm = key
            out[f"{table}|{cluster}|{arm}"] = {
                "visits": n,
                "accepts": self.accepts[key],
                "accept_rate": self.accepts[key] / n if n else 0.0,
                "mean_reward": float(np.mean(self.rewards[key])) if self.rewards[key] else 0.0,
                "q_trace": self.trace[key],
            }
        return out
