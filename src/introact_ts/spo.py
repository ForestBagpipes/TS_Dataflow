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

from .types import Action, MUTATING_ACTIONS, Verdict

#: Operators the policy chooses among. Terminal actions end the episode and are
#: not learned over, they are the policy's option to stop rather than an arm.
ARMS = (Action.IMPUTE, Action.DESPIKE, Action.DENOISE, Action.RESEGMENT)

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


@dataclass
class ValueTables:
    """Q and visit counts for every table, cluster and arm.

    Shapes are (n_clusters, len(ARMS)) per table. ``t`` is the global decision
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
            shape = (self.n_clusters, len(ARMS))
            for name in TABLES:
                self.Q[name] = np.full(shape, self.cfg.optimistic_init, dtype=np.float64)
                self.N[name] = np.full(shape, self.cfg.optimistic_visits, dtype=np.int64)
                self.optimistic[name] = np.ones(shape, dtype=bool)
        if not self.cluster_map:
            self.cluster_map = {c: c for c in range(self.n_clusters)}

    def resolve(self, cluster: int) -> int:
        """Tail clusters route to the large cluster they were merged into."""
        return self.cluster_map.get(int(cluster), int(cluster))

    def warm_start(self, table: str, cluster: int, arm: Action, rewards) -> None:
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
        j, a = self.resolve(cluster), ARMS.index(arm)
        self.Q[table][j, a] = float(rewards.mean())
        self.N[table][j, a] = int(min(rewards.size, self.cfg.warm_start_cap))
        self.optimistic[table][j, a] = False

    def set_column(self, table: str, arm: Action, value: float, visits: int) -> None:
        """Set a whole operator column, for an arm with no cluster level structure.

        Stage zero found RESEGMENT's admission rate flat across clusters at every
        k tested, permutation p from 0.81 to 0.96. Seeding it per cluster would
        encode noise as signal, so the column carries its global mean instead.
        """
        a = ARMS.index(arm)
        for name in ([table] if table else TABLES):
            self.Q[name][:, a] = value
            self.N[name][:, a] = visits
            self.optimistic[name][:, a] = False

    def ucb(self, table: str, cluster: int, feasible) -> np.ndarray:
        """Upper confidence bound over the arms, section 3.4's formula.

        Infeasible arms are masked to negative infinity rather than dropped, so
        the returned vector stays aligned with ARMS.
        """
        j = self.resolve(cluster)
        q = self.Q[table][j]
        n = np.maximum(self.N[table][j], 1)
        t = max(self.t, 1)
        width = self.cfg.c_u * np.sqrt(2.0 * np.log(t) / n)
        score = q + width
        mask = np.array([a in feasible for a in ARMS])
        return np.where(mask, score, -np.inf)

    def select(self, table: str, cluster: int, feasible) -> Optional[Action]:
        """Pick the highest bound among feasible arms, or None if none are."""
        score = self.ucb(table, cluster, feasible)
        if not np.isfinite(score).any():
            return None
        return ARMS[int(np.argmax(score))]

    def update(self, table: str, cluster: int, arm: Action, reward: float) -> None:
        """Incremental mean update, the standard form."""
        j, a = self.resolve(cluster), ARMS.index(arm)
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

    def __init__(self, tables: ValueTables, cfg: SPOConfig = None):
        self.tables = tables
        self.cfg = cfg or tables.cfg
        #: Per cell counters for reporting, keyed by (table, cluster, arm).
        self.visits = defaultdict(int)
        self.accepts = defaultdict(int)
        self.rewards = defaultdict(list)
        #: Q value after every update, for the learning curves.
        self.trace = defaultdict(list)

    @staticmethod
    def _prev_verdict(records):
        """Verdict of the last adjudicated candidate, or None if there is none."""
        for r in reversed(records):
            if r.action in MUTATING_ACTIONS and r.verdict is not Verdict.NO_OP:
                return r.verdict
        return None

    def table_of(self, records) -> str:
        return table_for(self._prev_verdict(records))

    def order(self, candidates, cluster: int, records) -> list:
        """Reorder the proposer's candidates by the upper confidence bound.

        Terminal actions keep their position, because they are the policy's
        option to stop rather than arms it is choosing among, and moving them
        would change when an episode ends rather than what it tries.
        """
        if not candidates:
            return candidates
        table = self.table_of(records)
        feasible = {a for a, _ in candidates if a in ARMS}
        if not feasible:
            return candidates
        score = self.tables.ucb(table, cluster, feasible)
        rank = {ARMS[i]: -score[i] for i in range(len(ARMS)) if np.isfinite(score[i])}

        arms, tail = [], []
        for a, p in candidates:
            (arms if a in rank else tail).append((a, p))
        arms.sort(key=lambda ap: rank[ap[0]])
        return arms + tail

    def observe(self, cluster: int, action: Action, verdict, delta_utility: float,
                probes: int, records) -> float:
        """Update the table this decision came from, and return the reward."""
        if action not in ARMS:
            return 0.0
        table = self.table_of(records[:-1] if records else [])
        reward = shielded_reward(verdict, delta_utility, probes, self.cfg)
        self.tables.update(table, cluster, action, reward)

        key = (table, self.tables.resolve(cluster), action.value)
        self.visits[key] += 1
        self.accepts[key] += int(getattr(verdict, "value", verdict) == "ACCEPTED")
        self.rewards[key].append(reward)
        j, a = self.tables.resolve(cluster), ARMS.index(action)
        self.trace[key].append(float(self.tables.Q[table][j, a]))
        return reward

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
