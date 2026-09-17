"""Stage 2: cross-fitted expected-regret components for the r2 decision score.

Stage 1 asked "which action is preferred" and answered with a pairwise
preference model.  That question is scale-free: a preference of 0.6 for FFILL
over KEEP is worth exactly as much whether the wrong choice costs 0.001 or 2.0
of MASE.  The stage-1 result shows the price of that blindness -- it beat the
strong controls on the average and still lost the rank contest, because it
intervened on 89-99% of windows and 42% of those interventions were harmful.

Stage 2 keeps the preference model and adds the missing magnitude: two
regressors estimate the **expected regret** ``r_{i,a} = L_{i,a} - min_b L_{i,b}``
of each action, and the deployed score is

    ``S_a = l1 * z(S_a^pair) - l2 * z(r_a^ridge) - l3 * z(r_a^tree)``

with ``l >= 0`` and ``l1 + l2 + l3 = 1`` chosen on TRAIN-Gate.

Two implementation choices are stated rather than hidden:

* the three components are **standardised within the episode's legal set**
  before they are mixed.  A Borda score lives on ``[0, 4]`` and a regret lives
  in MASE units; subtracting one from the other without a common scale would
  make ``l`` meaningless, so the plan's formula is read as a statement about
  *standardised* components.
* the two regressors are **cross-fitted** when they are used inside the block
  they are fitted on (:func:`cross_fitted_regret`).  The reported numbers fit on
  Replay-Fit and predict on a parent-disjoint block, so no in-sample optimism
  enters them; the cross-fitted variant exists so the same quantity can also be
  read honestly within one block, which is what the stage-2 gate needs to
  compare ``l`` values without rewarding whichever component overfits most.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.tree import DecisionTreeRegressor

from ..v44.protocol import ACTIONS, REFERENCE_ACTION
from .dataset import EpisodeView
from .protocol_r2 import (
    REGRET_RIDGE,
    REGRET_TREE,
    RIDGE_PARAMS,
    REGRET_TREE_PARAMS,
)

#: An action needs this many fitted rows before it gets its own regressor.
MIN_SUPPORT = 8


def regret_rows(episodes: list[EpisodeView]
                ) -> tuple[np.ndarray, np.ndarray, list[str], list[int]]:
    """``(features, regret, actions, owners)`` over every executable row.

    The target is regret, not utility: ``r_{i,a} = L_{i,a} - min_b L_{i,b}`` is
    zero for the best action of the episode and positive for every other, which
    is exactly the quantity the deployed decision is trying to minimise.
    """
    rows, targets, actions, owners = [], [], [], []
    for index, episode in enumerate(episodes):
        legal = episode.legal()
        if len(legal) < 2:
            continue
        best = min(episode.actions[a].loss for a in legal)
        for action in legal:
            rows.append(episode.actions[action].features)
            targets.append(float(episode.actions[action].loss - best))
            actions.append(action)
            owners.append(index)
    if not rows:
        raise RuntimeError("no executable (episode, action) rows for the regret fit")
    return (np.asarray(rows, dtype=np.float64),
            np.asarray(targets, dtype=np.float64), actions, owners)


class RegretModel:
    """One regressor per action, mirroring the v4.4 A5 controls exactly.

    The v4.4 A5 controls fitted a model per action on the *utility*; this fits
    the same model per action on the *regret*.  Keeping the estimator and its
    hyper-parameters identical is what makes "r2 ridge" and "A5 ridge"
    comparable rather than merely similarly named.
    """

    def __init__(self, *, kind: str):
        if kind not in (REGRET_RIDGE, REGRET_TREE):
            raise ValueError(f"unregistered regret kind {kind!r}")
        self.kind = kind
        self.models: dict[str, object] = {}
        self.support: dict[str, int] = {}
        self.residual: dict[str, float] = {}
        self.target_summary: dict = {}

    def _make(self):
        if self.kind == REGRET_RIDGE:
            return Ridge(**RIDGE_PARAMS)
        return DecisionTreeRegressor(**REGRET_TREE_PARAMS)

    def fit(self, episodes: list[EpisodeView]) -> "RegretModel":
        features, targets, actions, _owners = regret_rows(episodes)
        actions = np.asarray(actions)
        self.target_summary = {
            "rows": int(targets.size),
            "mean": float(targets.mean()),
            "median": float(np.median(targets)),
            "zero_ratio": float((targets <= 1e-12).mean()),
        }
        for action in ACTIONS:
            mask = actions == action
            if int(mask.sum()) < MIN_SUPPORT:
                continue
            x, y = features[mask], targets[mask]
            model = self._make().fit(x, y)
            self.models[action] = model
            self.residual[action] = float(np.std(y - model.predict(x)))
            self.support[action] = int(mask.sum())
        if not self.models:
            raise RuntimeError("no action had enough rows to fit a regret model")
        return self

    def predict(self, episode: EpisodeView) -> dict[str, float]:
        """Predicted regret per executable action; ``nan`` when unfitted."""
        out: dict[str, float] = {}
        for action in episode.legal():
            model = self.models.get(action)
            if model is None:
                out[action] = float("nan")
                continue
            row = np.asarray(episode.actions[action].features,
                             dtype=np.float64).reshape(1, -1)
            out[action] = float(model.predict(row)[0])
        return out

    def notes(self) -> dict:
        return {"kind": self.kind, "support": dict(sorted(self.support.items())),
                "residual_std": {k: round(v, 6) for k, v in
                                 sorted(self.residual.items())},
                "target": self.target_summary}


# -- standardisation and combination ----------------------------------------


def standardise(values: dict[str, float]) -> dict[str, float]:
    """Z-score within one episode's legal set.

    A set whose values are all equal -- or that contains an unfitted action --
    standardises to zeros rather than to an arbitrary ordering, so a component
    that has nothing to say cannot outvote one that has.
    """
    finite = {key: value for key, value in values.items()
              if value is not None and np.isfinite(value)}
    if not finite:
        return {key: 0.0 for key in values}
    array = np.asarray(list(finite.values()), dtype=np.float64)
    spread = float(array.std())
    mean = float(array.mean())
    out = {key: 0.0 for key in values}
    if spread <= 1e-12:
        return out
    for key, value in finite.items():
        out[key] = float((value - mean) / spread)
    return out


def borda(pair_probabilities: dict[tuple[str, str], float]) -> dict[str, float]:
    """``S_a = sum_{b != a} p(a > b)``."""
    scores: dict[str, float] = {}
    for (left, _right), value in pair_probabilities.items():
        scores[left] = scores.get(left, 0.0) + value
    return scores


@dataclass
class Components:
    """The three standardised components of one episode, kept auditable."""

    pair: dict[str, float]
    ridge: dict[str, float]
    tree: dict[str, float]
    raw_pair: dict[str, float] = field(default_factory=dict)
    raw_ridge: dict[str, float] = field(default_factory=dict)
    raw_tree: dict[str, float] = field(default_factory=dict)

    def combine(self, lambdas: tuple[float, float, float]) -> dict[str, float]:
        first, second, third = lambdas
        keys = set(self.pair) | set(self.ridge) | set(self.tree)
        return {key: (first * self.pair.get(key, 0.0)
                      - second * self.ridge.get(key, 0.0)
                      - third * self.tree.get(key, 0.0))
                for key in keys}

    def trace(self) -> dict:
        return {"pair": dict(sorted(self.pair.items())),
                "ridge": dict(sorted(self.ridge.items())),
                "tree": dict(sorted(self.tree.items()))}


def components(episode: EpisodeView, pair_probabilities: dict,
               ridge_model: RegretModel,
               tree_model: RegretModel) -> Components | None:
    legal = episode.legal()
    if len(legal) < 2:
        return None
    raw_pair = borda(pair_probabilities)
    raw_ridge = ridge_model.predict(episode)
    raw_tree = tree_model.predict(episode)
    return Components(pair=standardise(raw_pair), ridge=standardise(raw_ridge),
                      tree=standardise(raw_tree), raw_pair=raw_pair,
                      raw_ridge=raw_ridge, raw_tree=raw_tree)


def select(scores: dict[str, float], legal: tuple[str, ...]) -> str:
    """``argmax`` with ties to KEEP, restricted to the executable actions."""
    candidates = {a: scores.get(a, 0.0) for a in legal}
    if not candidates:
        return REFERENCE_ACTION
    return max(sorted(candidates),
               key=lambda a: (candidates[a], a == REFERENCE_ACTION))


def decide_from_components(components_obj: Components, pair_probabilities: dict,
                           legal: tuple[str, ...], *,
                           lambdas: tuple[float, float, float],
                           tau: float):
    """The stage-2 decision: combined score, then the same single veto.

    The veto is unchanged from stage 1 and is deliberately still read off the
    **pairwise** probability ``p(a* > KEEP)``: the regret components adjust which
    action wins, but "am I confident enough to depart from the reference at all"
    remains a question about preference, not about magnitude.
    """
    from .ranking import Decision

    if len(legal) < 2:
        return Decision(REFERENCE_ACTION, {}, {}, False, None, tau,
                        REFERENCE_ACTION, legal)
    scores = components_obj.combine(lambdas)
    winner = select(scores, legal)
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


# -- cross-fitting ----------------------------------------------------------


def cross_fitted_regret(episodes: list[EpisodeView], *, kind: str,
                        folds: int = 5, seed: int | None = None
                        ) -> dict[str, dict[str, float]]:
    """Out-of-fold predicted regret, parent as the fold unit.

    A regret regressor fitted and scored on the same rows reports a residual it
    does not have, and the stage-2 gate would then prefer whichever component
    overfits hardest.  Predicting every episode from a model that never saw its
    parent removes that preference by construction.
    """
    from .ranking import parent_folds
    from ..v44.protocol import PROTOCOL_SEED

    seed = PROTOCOL_SEED if seed is None else int(seed)
    out: dict[str, dict[str, float]] = {}
    for held in parent_folds(episodes, folds=folds, seed=seed):
        held_set = set(held)
        train = [e for e in episodes if e.parent not in held_set]
        test = [e for e in episodes if e.parent in held_set]
        if not train or not test:
            continue
        model = RegretModel(kind=kind).fit(train)
        for episode in test:
            out[episode.episode] = model.predict(episode)
    return out


# -- orchestration ----------------------------------------------------------


def fit_all(fit_episodes: list[EpisodeView], *, frozen: dict):
    """Fit the three frozen components on one block, in the frozen order.

    ``frozen`` is the stage-1 selection: the pairwise learner family and its
    ensemble weight are carried over unchanged, so stage 2 adds the regret
    terms and nothing else.
    """
    from .ranking import PairwiseRanker

    ranker = PairwiseRanker(learner=frozen["learner"],
                            alpha=frozen["alpha"]).fit(fit_episodes)
    ridge = RegretModel(kind=REGRET_RIDGE).fit(fit_episodes)
    tree = RegretModel(kind=REGRET_TREE).fit(fit_episodes)
    return ranker, ridge, tree


def prepare(episodes: list[EpisodeView], ranker, ridge: RegretModel,
            tree: RegretModel) -> tuple[dict[str, Components], dict[str, dict],
                                        dict[str, tuple[str, ...]]]:
    """Per-episode ``(components, pair probabilities, legal actions)``.

    Computed once so the lambda/tau sweep only re-weights numbers that were
    already produced -- the sweep cannot change a prediction, only how it is
    combined.
    """
    prepared: dict[str, Components] = {}
    pair_probabilities: dict[str, dict] = {}
    legals: dict[str, tuple[str, ...]] = {}
    for episode in episodes:
        probabilities = ranker.pair_probabilities(episode)
        pair_probabilities[episode.episode] = probabilities
        legals[episode.episode] = episode.legal()
        built = components(episode, probabilities, ridge, tree)
        if built is not None:
            prepared[episode.episode] = built
    return prepared, pair_probabilities, legals


def decisions_for(episodes: list[EpisodeView], prepared: dict[str, Components],
                  pair_probabilities: dict[str, dict],
                  legals: dict[str, tuple[str, ...]], *,
                  lambdas: tuple[float, float, float],
                  tau: float) -> dict:
    """Deploy one ``(lambda, tau)`` over a block, falling back to KEEP."""
    from .ranking import Decision

    out = {}
    for episode in episodes:
        key = episode.episode
        built = prepared.get(key)
        if built is None:
            out[key] = Decision(REFERENCE_ACTION, {}, {}, False, None, tau,
                                REFERENCE_ACTION, legals.get(key, ()))
            continue
        out[key] = decide_from_components(built, pair_probabilities[key],
                                          legals[key], lambdas=lambdas, tau=tau)
    return out
