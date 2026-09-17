"""Local matching and the conservative gate (task book §3, Module 3).

Given a query state and a replay bank, every legal action is scored by the
weighted utility of its ``K`` nearest historical executions *of the same
action*, penalised by a local-uncertainty term.  The gate then either picks the
best action or abstains to the reference.

The four ablations that are not "remove a feature block" or "remove the gate"
are expressed as constructor flags on one implementation, so the ablation
cannot drift from the full method by accident:

* ``local=False``            -> A1 Global Replay
* ``use_intervention=False`` -> A2 w/o Intervention State
* ``use_forecast=False``     -> A3 w/o Forecast State
* ``conservative=False``     -> A4 w/o Conservative Gate
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .protocol import (ACTIONS, BANK_BLOCK, BETA_GRID, K_GRID,
                       REFERENCE_ACTION, TAU_EPSILON)
from .replay import ReplayBank

#: Slices of the concatenated state vector.
STATE_SLICES = {
    "mask": slice(0, 6),
    "context": slice(6, 12),
    "intervention": slice(12, 17),
    "forecast": slice(17, 22),
}

#: The full state is 22-dimensional; a sliced variant must keep at least the
#: mask block, otherwise the "state" carries no information about the request.
MIN_STATE_DIM = 6


class StandardizedEuclidean:
    """Continuous feature scaling, fitted on Replay-Fit and then frozen.

    The scaler is fitted once on the replay bank of the fit block and reused
    unchanged for the gate block, the evaluation block and every later
    backbone, which is what stops the distance metric from being retuned.
    """

    def __init__(self) -> None:
        self.mean: np.ndarray | None = None
        self.scale: np.ndarray | None = None

    def fit(self, vectors: np.ndarray) -> "StandardizedEuclidean":
        vectors = np.asarray(vectors, dtype=np.float64)
        if vectors.ndim != 2 or vectors.shape[0] == 0:
            raise ValueError("scaler needs a non-empty 2-D matrix")
        self.mean = vectors.mean(axis=0)
        scale = vectors.std(axis=0)
        scale = np.where(scale > 1e-12, scale, 1.0)
        self.scale = scale
        return self

    def transform(self, vectors: np.ndarray) -> np.ndarray:
        if self.mean is None or self.scale is None:
            raise RuntimeError("scaler has not been fitted")
        vectors = np.asarray(vectors, dtype=np.float64)
        if vectors.shape[-1] != self.mean.shape[0]:
            raise ValueError("feature dimension mismatch with the fitted scaler")
        return (vectors - self.mean) / self.scale

    def distance(self, query: np.ndarray, candidates: np.ndarray) -> np.ndarray:
        """Euclidean distance after standardization."""
        query = self.transform(np.asarray(query, dtype=np.float64).reshape(1, -1))
        candidates = self.transform(np.asarray(candidates, dtype=np.float64))
        return np.sqrt(np.sum((candidates - query) ** 2, axis=1))


@dataclass
class ActionScore:
    """One action's local evidence."""

    action: str
    available: bool
    mu: float = float("nan")
    sigma: float = float("nan")
    n_eff: float = 0.0
    score: float = float("-inf")
    neighbours: int = 0
    requested_k: int = 0
    support: int = 0
    reason: str | None = None
    indices: tuple[int, ...] = ()


@dataclass
class Selection:
    """The selector's decision and the evidence behind it."""

    action: str
    reference: str
    scores: dict[str, ActionScore] = field(default_factory=dict)
    conservative: bool = True
    local: bool = True
    k: int = 0
    beta: float = 0.0

    @property
    def intervened(self) -> bool:
        return self.action != self.reference

    @property
    def estimated_utility(self) -> float:
        item = self.scores.get(self.action)
        return float("nan") if item is None else item.mu

    def trace(self) -> dict:
        return {
            "selected": self.action,
            "reference": self.reference,
            "intervened": self.intervened,
            "conservative": self.conservative,
            "local": self.local,
            "k": self.k,
            "beta": self.beta,
            "scores": {name: {"available": s.available, "mu": _clean(s.mu),
                              "sigma": _clean(s.sigma), "n_eff": _clean(s.n_eff),
                              "score": _clean(s.score), "neighbours": s.neighbours,
                              "support": s.support, "reason": s.reason}
                       for name, s in self.scores.items()},
        }


def _clean(value: float) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if np.isfinite(value) else None


class ConservativeSelector:
    """Replay retrieval plus a conservative abstention rule."""

    def __init__(self, *, k: int = 16, beta: float = 1.0, local: bool = True,
                 use_intervention: bool = True, use_forecast: bool = True,
                 conservative: bool = True, exclude_reference_from_bank: bool = False):
        if k not in K_GRID:
            raise ValueError(f"K must be one of {K_GRID}, got {k}")
        if not any(abs(beta - b) < 1e-12 for b in BETA_GRID):
            raise ValueError(f"beta must be one of {BETA_GRID}, got {beta}")
        self.k = int(k)
        self.beta = float(beta)
        self.local = bool(local)
        self.use_intervention = bool(use_intervention)
        self.use_forecast = bool(use_forecast)
        self.conservative = bool(conservative)
        self.exclude_reference_from_bank = bool(exclude_reference_from_bank)
        self.scaler: StandardizedEuclidean | None = None

    # -- feature handling ---------------------------------------------------

    def blocks(self) -> tuple[str, ...]:
        blocks = ["mask", "context"]
        if self.use_intervention:
            blocks.append("intervention")
        if self.use_forecast:
            blocks.append("forecast")
        return tuple(blocks)

    def project(self, vector: np.ndarray) -> np.ndarray:
        vector = np.asarray(vector, dtype=np.float64).reshape(-1)
        pieces = [vector[STATE_SLICES[name]] for name in self.blocks()]
        out = np.concatenate(pieces)
        if out.size < MIN_STATE_DIM:
            raise ValueError("projected state is degenerate")
        return out

    def fit(self, bank: ReplayBank, *, block_of: dict[str, str] | None = None,
            block: str = "replay_fit") -> "ConservativeSelector":
        """Fit the feature scaler on the fit block only."""
        vectors = [self.project(record.state_vector)
                   for record in bank.records
                   if record.scored
                   and (block_of is None or block_of.get(record.parent) == block)]
        if not vectors:
            raise RuntimeError("no replay records available to fit the scaler")
        self.scaler = StandardizedEuclidean().fit(np.vstack(vectors))
        return self

    # -- scoring ------------------------------------------------------------

    def _action_scores(self, query_vector, bank: ReplayBank, *,
                       legal: tuple[str, ...], block_of: dict[str, str] | None,
                       block: str | None, exclude_parent: str | None) -> dict[str, ActionScore]:
        if self.scaler is None:
            raise RuntimeError("selector must be fitted before scoring")
        per_action = isinstance(query_vector, dict)
        query = None if per_action else self.project(query_vector)
        scores: dict[str, ActionScore] = {}
        for action in ACTIONS:
            if action not in legal:
                scores[action] = ActionScore(action, available=False, support=0,
                                             reason="not legal for this request")
                continue
            candidates = bank.by_action(action, exclude_parent=exclude_parent,
                                        block=block, block_of=block_of)
            if not candidates:
                scores[action] = ActionScore(action, available=False, support=0,
                                             reason="no replay support")
                continue
            utilities = np.array([r.utility_vs_reference for r in candidates],
                                 dtype=np.float64)
            support = len(candidates)

            if not self.local:
                # A1: global replay -- the whole action's support, no retrieval.
                sigma = float(np.std(utilities))
                n_eff = float(support)
                mu = float(np.mean(utilities))
                scores[action] = ActionScore(
                    action, available=True, mu=mu, sigma=sigma, n_eff=n_eff,
                    score=self._score(mu, sigma, n_eff), neighbours=support,
                    requested_k=support, support=support,
                    indices=tuple(range(support)))
                continue

            matrix = np.vstack([self.project(r.state_vector) for r in candidates])
            # The intervention block is action-specific, so a request has one
            # query vector per action; everything else is shared.
            this_query = self.project(query_vector[action]) if per_action else query
            distances = self.scaler.distance(this_query, matrix)
            k_eff = min(self.k, support)          # K > NN support -> fall back
            order = np.argsort(distances, kind="stable")[:k_eff]
            d = distances[order]
            g = utilities[order]

            tau = float(np.median(d)) + TAU_EPSILON
            weights = np.exp(-d / tau)
            weight_sum = float(weights.sum())
            if not np.isfinite(weight_sum) or weight_sum <= 0:
                weights = np.ones_like(d)
                weight_sum = float(weights.sum())
            mu = float(np.dot(weights, g) / weight_sum)
            sigma = float(np.sqrt(np.dot(weights, (g - mu) ** 2) / weight_sum))
            n_eff = float(weight_sum ** 2 / np.dot(weights, weights))
            n_eff = float(np.clip(n_eff, 1.0, float(k_eff)))   # numerical guard
            scores[action] = ActionScore(
                action, available=True, mu=mu, sigma=sigma, n_eff=n_eff,
                score=self._score(mu, sigma, n_eff), neighbours=int(k_eff),
                requested_k=self.k, support=support,
                indices=tuple(int(i) for i in order))
        return scores

    def _score(self, mu: float, sigma: float, n_eff: float) -> float:
        if not np.isfinite(mu):
            return float("-inf")
        if not self.conservative:
            return float(mu)
        penalty = self.beta * sigma / np.sqrt(max(n_eff, 1.0))
        value = mu - penalty
        return float(value) if np.isfinite(value) else float("-inf")

    # -- decision -----------------------------------------------------------

    def select(self, query_vector: np.ndarray, bank: ReplayBank, *,
               legal: tuple[str, ...] = ACTIONS,
               block_of: dict[str, str] | None = None,
               block: str | None = None,
               exclude_parent: str | None = None) -> Selection:
        scores = self._action_scores(query_vector, bank, legal=legal,
                                     block_of=block_of, block=block,
                                     exclude_parent=exclude_parent)
        reference = REFERENCE_ACTION if REFERENCE_ACTION in legal else legal[0]
        eligible = [name for name in ACTIONS
                    if name in legal and scores[name].available]
        if not eligible:
            return Selection(reference, reference, scores, self.conservative,
                             self.local, self.k, self.beta)

        if self.conservative:
            best = max(eligible, key=lambda name: (scores[name].score,
                                                   -ACTIONS.index(name)))
            if scores[best].score <= 0.0:
                # Every legal action's conservative lower bound is non-positive:
                # abstain rather than gamble (task book §3, Module 3).
                return Selection(reference, reference, scores, True, self.local,
                                 self.k, self.beta)
            return Selection(best, reference, scores, True, self.local, self.k,
                             self.beta)

        best = max(eligible, key=lambda name: (scores[name].score,
                                               -ACTIONS.index(name)))
        return Selection(best, reference, scores, False, self.local, self.k,
                         self.beta)


def select_action(query_vector: np.ndarray, bank: ReplayBank, *, k: int,
                  beta: float, legal: tuple[str, ...] = ACTIONS,
                  block_of: dict[str, str] | None = None,
                  block: str = BANK_BLOCK,
                  exclude_parent: str | None = None,
                  **flags) -> Selection:
    """Convenience entry point used by the gate sweep and the evaluation.

    ``block`` names the block the *bank* was built from (see
    :data:`introact_ts.v44.protocol.BANK_BLOCK`), not the block the request
    being scored belongs to.
    """
    selector = ConservativeSelector(k=k, beta=beta, **flags)
    selector.fit(bank, block_of=block_of, block=block)
    return selector.select(query_vector, bank, legal=legal, block_of=block_of,
                           block=block, exclude_parent=exclude_parent)
