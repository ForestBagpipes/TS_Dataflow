"""Pairwise decision-regret ranking (r2 Module 2).

The v4.4 result said two things at once: counterfactual replay carries real
information (a parametric replay predictor beat both KEEP and the strong
control), and *averaging gains with a distance metric* does not turn that
information into good decisions.  The second half is the reason this module
exists.

What is learned here is not the gain vector.  For one historical episode with
losses ``L_{i,a}``, every ordered pair of executable actions contributes

* a preference label ``y = 1[L_{i,a} < L_{i,b}]``, and
* an importance weight ``w = |L_{i,a} - L_{i,b}|``,

so a pair that is nearly tied barely matters and a pair where the wrong choice
costs a lot matters a great deal.  The model is a single scoring function
``f`` over ``(episode, action)`` features, trained on the *difference*
``f(x_a) - f(x_b)``, and the deployed preference is

    ``p(a > b | z) = sigmoid(f(x_a) - f(x_b))``.

That is exactly a ranking objective: it optimises the order of the actions,
which is what the deployed decision consumes, rather than the squared error of
a quantity (the gain) that is then re-sorted.

KEEP is not special.  It enters every pair like any other action, so abstention
is what the model predicts when KEEP wins, not something imposed afterwards by
a fixed beta.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ..v44.protocol import ACTIONS, REFERENCE_ACTION
from . import features as F
from .dataset import EpisodeView
from .protocol_r2 import (
    LEARNER_ENSEMBLE,
    LEARNER_LINEAR,
    LEARNER_TREE,
    LINEAR_PARAMS,
    TREE_PARAMS,
)


@dataclass
class PairSet:
    """The pairwise training set, kept explicit so it can be audited."""

    X: np.ndarray
    y: np.ndarray
    w: np.ndarray
    episodes: np.ndarray
    left: list[str]
    right: list[str]

    def __len__(self) -> int:
        return int(self.X.shape[0])

    def summary(self) -> dict:
        return {
            "pairs": len(self),
            "features": int(self.X.shape[1]) if self.X.size else 0,
            "episodes": int(np.unique(self.episodes).size) if len(self) else 0,
            "positive_pairs": int(self.y.sum()) if len(self) else 0,
            "positive_ratio": float(self.y.mean()) if len(self) else None,
            "weight_sum": float(self.w.sum()) if len(self) else 0.0,
            "zero_weight_pairs": int((self.w <= 0).sum()) if len(self) else 0,
            "mean_weight": float(self.w.mean()) if len(self) else None,
        }


def _rows(episodes: list[EpisodeView]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Stack every executable ``(episode, action)`` feature row."""
    rows, owners, actions = [], [], []
    for index, episode in enumerate(episodes):
        for action in episode.legal():
            rows.append(episode.actions[action].features)
            owners.append(index)
            actions.append(action)
    if not rows:
        raise RuntimeError("no executable (episode, action) rows in this block")
    return np.vstack(rows), np.asarray(owners, dtype=np.int64), actions


def build_pairs(episodes: list[EpisodeView], *,
                scaler: StandardScaler | None = None) -> tuple[PairSet, StandardScaler]:
    """Ordered-pair training set from historical episodes.

    Pairs never cross episodes: a preference is only ever asserted between two
    actions evaluated on the *same* window, which is the only comparison the
    counterfactual replay actually supports.

    Each row is the action-conditional pair design of :func:`features.pair_design`,
    not the raw difference of the two feature vectors -- see that function for
    why the raw difference cannot express a state-dependent preference.
    """
    matrix, owners, actions = _rows(episodes)
    if scaler is None:
        scaler = StandardScaler().fit(matrix)
    scaled = scaler.transform(matrix)

    index: dict[int, list[int]] = {}
    for position, owner in enumerate(owners):
        index.setdefault(int(owner), []).append(position)

    X, y, w, ep, left, right = [], [], [], [], [], []
    for owner, positions in index.items():
        losses = {actions[p]: episodes[owner].actions[actions[p]].loss
                  for p in positions}
        for i in positions:
            for j in positions:
                if i == j:
                    continue
                a, b = actions[i], actions[j]
                la, lb = losses[a], losses[b]
                X.append(F.pair_design(scaled[i], scaled[j]))
                y.append(1.0 if la < lb else 0.0)
                w.append(abs(la - lb))
                ep.append(owner)
                left.append(a)
                right.append(b)
    return (PairSet(X=np.asarray(X, dtype=np.float64),
                    y=np.asarray(y, dtype=np.float64),
                    w=np.asarray(w, dtype=np.float64),
                    episodes=np.asarray(ep, dtype=np.int64),
                    left=left, right=right), scaler)


@dataclass
class Decision:
    """One deployed decision and the evidence behind it."""

    action: str
    scores: dict[str, float]
    pair_probabilities: dict[tuple[str, str], float]
    vetoed: bool
    veto_probability: float | None
    tau: float
    borda_winner: str
    legal: tuple[str, ...] = ()

    @property
    def intervened(self) -> bool:
        return self.action != REFERENCE_ACTION

    def trace(self) -> dict:
        return {
            "selected": self.action,
            "borda_winner": self.borda_winner,
            "vetoed": self.vetoed,
            "veto_probability": self.veto_probability,
            "tau": self.tau,
            "scores": {k: float(v) for k, v in sorted(self.scores.items())},
            "legal": list(self.legal),
        }


class PairwiseRanker:
    """A scoring function trained on pairwise preferences, plus Borda voting."""

    def __init__(self, *, learner: str, alpha: float | None = None):
        if learner not in (LEARNER_LINEAR, LEARNER_TREE, LEARNER_ENSEMBLE):
            raise ValueError(f"unregistered learner {learner!r}")
        if learner == LEARNER_ENSEMBLE and alpha is None:
            raise ValueError("the ensemble needs an explicit alpha")
        if learner != LEARNER_ENSEMBLE and alpha is not None:
            raise ValueError("alpha is only meaningful for the ensemble")
        self.learner = learner
        self.alpha = None if alpha is None else float(alpha)
        self.scaler: StandardScaler | None = None
        self.linear: LogisticRegression | None = None
        self.tree: HistGradientBoostingClassifier | None = None
        self.pair_summary: dict = {}
        self.notes: dict = {}

    # -- fitting ------------------------------------------------------------

    def _needs_linear(self) -> bool:
        return self.learner in (LEARNER_LINEAR, LEARNER_ENSEMBLE)

    def _needs_tree(self) -> bool:
        return self.learner in (LEARNER_TREE, LEARNER_ENSEMBLE)

    def fit(self, episodes: list[EpisodeView]) -> "PairwiseRanker":
        pairs, scaler = build_pairs(episodes)
        self.scaler = scaler
        self.pair_summary = pairs.summary()
        if len(np.unique(pairs.y)) < 2:
            raise RuntimeError("the pairwise set has only one preference class")
        if self._needs_linear():
            self.linear = LogisticRegression(**LINEAR_PARAMS)
            self.linear.fit(pairs.X, pairs.y, sample_weight=pairs.w)
            self.notes["linear"] = {
                "params": {k: v for k, v in LINEAR_PARAMS.items()},
                "coef_norm": float(np.linalg.norm(self.linear.coef_)),
                "intercept": float(self.linear.intercept_[0]),
            }
        if self._needs_tree():
            self.tree = HistGradientBoostingClassifier(**TREE_PARAMS)
            self.tree.fit(pairs.X, pairs.y, sample_weight=pairs.w)
            self.notes["tree"] = {
                "params": {k: v for k, v in TREE_PARAMS.items()},
                "n_iter": int(getattr(self.tree, "n_iter_", 0)),
            }
        return self

    # -- scoring ------------------------------------------------------------

    def _probability(self, differences: np.ndarray) -> np.ndarray:
        if self.learner == LEARNER_LINEAR:
            return self.linear.predict_proba(differences)[:, 1]
        if self.learner == LEARNER_TREE:
            return self.tree.predict_proba(differences)[:, 1]
        linear = self.linear.predict_proba(differences)[:, 1]
        tree = self.tree.predict_proba(differences)[:, 1]
        return self.alpha * linear + (1.0 - self.alpha) * tree

    def pair_probabilities(self, episode: EpisodeView
                           ) -> dict[tuple[str, str], float]:
        """``p(a > b)`` for every ordered pair of executable actions."""
        legal = episode.legal()
        if len(legal) < 2:
            return {}
        if self.scaler is None:
            raise RuntimeError("ranker must be fitted before scoring")
        keys = [(a, b) for a in legal for b in legal if a != b]
        left_rows = self.scaler.transform(
            np.vstack([episode.actions[a].features for a, _b in keys]))
        right_rows = self.scaler.transform(
            np.vstack([episode.actions[b].features for _a, b in keys]))
        design = np.vstack([F.pair_design(left_rows[i], right_rows[i])
                            for i in range(len(keys))])
        probabilities = self._probability(design)
        return {key: float(value) for key, value in zip(keys, probabilities)}

    def borda(self, pair_probabilities: dict[tuple[str, str], float]
              ) -> dict[str, float]:
        """``S_a = sum_{b != a} p(a > b)`` over the executable actions."""
        scores: dict[str, float] = {}
        for (a, _b), value in pair_probabilities.items():
            scores[a] = scores.get(a, 0.0) + value
        return scores

    def decide(self, episode: EpisodeView, *, tau: float) -> Decision:
        """Borda winner, then a single confidence veto against KEEP."""
        legal = episode.legal()
        if len(legal) < 2:
            return Decision(REFERENCE_ACTION, {}, {}, False, None, tau,
                            REFERENCE_ACTION, legal)
        return decide_from(self.pair_probabilities(episode), legal, tau=tau)


def decide_from(pair_probabilities: dict[tuple[str, str], float],
                legal: tuple[str, ...], *, tau: float) -> Decision:
    """The deployed rule, given the pair preferences.

    Split out from :meth:`PairwiseRanker.decide` so the four veto thresholds can
    be swept over one set of pair probabilities instead of recomputing them --
    ``tau`` never changes a preference, only whether it is acted on.
    """
    if len(legal) < 2:
        return Decision(REFERENCE_ACTION, {}, {}, False, None, tau,
                        REFERENCE_ACTION, legal)
    scores: dict[str, float] = {}
    for (a, _b), value in pair_probabilities.items():
        scores[a] = scores.get(a, 0.0) + value
    # Ties go to KEEP: the reference action is the conservative default, so an
    # exact tie must not become an intervention.
    winner = max(sorted(scores), key=lambda a: (scores[a],
                                                a == REFERENCE_ACTION))
    if winner == REFERENCE_ACTION:
        return Decision(REFERENCE_ACTION, scores, pair_probabilities, False,
                        None, tau, winner, legal)
    confidence = pair_probabilities.get((winner, REFERENCE_ACTION))
    if confidence is not None and confidence < tau:
        return Decision(REFERENCE_ACTION, scores, pair_probabilities, True,
                        float(confidence), tau, winner, legal)
    return Decision(winner, scores, pair_probabilities, False,
                    None if confidence is None else float(confidence), tau,
                    winner, legal)


def apply_ranker(ranker: PairwiseRanker, episodes: list[EpisodeView], *,
                 tau: float) -> dict[str, Decision]:
    """Deploy one frozen ranker over a block."""
    return {episode.episode: ranker.decide(episode, tau=tau)
            for episode in episodes}


# -- cross-fitting ----------------------------------------------------------


def parent_folds(episodes: list[EpisodeView], *, folds: int,
                 seed: int) -> list[list[str]]:
    """Partition the distinct parents into ``folds`` disjoint groups.

    The fold unit is the **parent**, never the episode: two episodes of one
    parent share a window family, so an episode-level split would put a near
    copy of the test request in the training set and call the result
    generalisation.  The assignment is a deterministic function of the seed and
    the sorted parent list, so a rerun reproduces it exactly.
    """
    if folds < 2:
        raise ValueError("cross-fitting needs at least two folds")
    parents = sorted({episode.parent for episode in episodes})
    if len(parents) < folds:
        raise ValueError(f"cannot make {folds} folds out of {len(parents)} parents")
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(parents))
    buckets: list[list[str]] = [[] for _ in range(folds)]
    for position, index in enumerate(order):
        buckets[position % folds].append(parents[int(index)])
    return [sorted(bucket) for bucket in buckets]


def cross_fitted_pair_probabilities(
        episodes: list[EpisodeView], *, learner: str, alpha: float | None = None,
        folds: int = 5, seed: int | None = None
) -> dict[str, dict[tuple[str, str], float]]:
    """Out-of-fold ``p(a > b)`` for every episode, parent as the fold unit.

    Each fold is scored by a ranker that was fitted on the *other* folds only,
    so no episode's preference is ever predicted by a model that has seen its
    own parent.  This is the honest way to read a within-TRAIN number, and it is
    the input the second-stage expected-regret ensemble needs.
    """
    from ..v44.protocol import PROTOCOL_SEED

    seed = PROTOCOL_SEED if seed is None else int(seed)
    buckets = parent_folds(episodes, folds=folds, seed=seed)
    probabilities: dict[str, dict[tuple[str, str], float]] = {}
    for held in buckets:
        held_set = set(held)
        train = [e for e in episodes if e.parent not in held_set]
        test = [e for e in episodes if e.parent in held_set]
        if not train or not test:
            continue
        ranker = PairwiseRanker(learner=learner, alpha=alpha).fit(train)
        for episode in test:
            probabilities[episode.episode] = ranker.pair_probabilities(episode)
    return probabilities
