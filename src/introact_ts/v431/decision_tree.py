"""Small deterministic trees minimizing five-arm task loss directly.

Weights are final row contributions supplied by the experiment protocol.  In
particular, callers must divide a parent's mass among its correlated variants;
this module never turns variants into additional independent support.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import numpy as np


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def validate_training(X, losses, weights, parents):
    X = np.asarray(X, dtype=np.float64)
    losses = np.asarray(losses, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    parents = np.asarray(parents).astype(str)
    if X.ndim != 2 or losses.shape != (len(X), 5):
        raise ValueError("Require X[n,p] and complete five-arm losses[n,5]")
    if weights.shape != (len(X),) or parents.shape != (len(X),):
        raise ValueError("weights and parents must have one entry per row")
    if not len(X) or not np.isfinite(losses).all():
        raise ValueError("Empty or failed/missing task losses are not trainable")
    if np.isinf(X).any() or not np.isfinite(weights).all():
        raise ValueError("Features permit NaN, not infinity; weights must be finite")
    if (weights < 0).any() or weights.sum() <= 0:
        raise ValueError("weights must be nonnegative with positive total mass")
    return X, losses, weights, parents


def weighted_action(losses, weights, tie_action=2):
    risks = np.sum(losses * weights[:, None], axis=0)
    best = float(np.min(risks))
    # Only exact/numerical equality is a tie; this tolerance is serialized.
    tied = np.flatnonzero(np.isclose(risks, best, rtol=1e-12, atol=1e-14))
    action = int(tie_action if tie_action in tied else tied[0])
    return action, float(risks[action])


def split_thresholds(values, maximum=16):
    finite_values = np.asarray(values)[np.isfinite(values)]
    values = np.unique(finite_values)
    if len(values) < 2:
        return np.empty(0, dtype=float)
    # Thresholds between observations avoid an empty upper child.  At most the
    # registered number of training quantile positions is considered.
    cuts = values[:-1] / 2.0 + values[1:] / 2.0
    if len(cuts) <= maximum:
        return cuts
    probabilities = np.linspace(0, 1, maximum + 2)[1:-1]
    # Include the median even with an even-sized grid, so a root with exactly
    # 2 * min_parents can make its sole supported balanced split.
    probabilities[np.argmin(np.abs(probabilities - 0.5))] = 0.5
    quantiles = np.quantile(finite_values, probabilities)
    return np.unique(quantiles[quantiles < values[-1]])


class LossTree:
    """CART-shaped tree whose impurity is minimum weighted task loss.

    NaN is never imputed with a numeric zero.  Both missing routes are evaluated
    during fitting and the selected boolean route is part of the frozen tree.
    """

    def __init__(self, max_depth=1, min_parents=16, max_thresholds=16,
                 tie_action=2):
        if not 0 <= max_depth <= 3:
            raise ValueError("The registered total tree depth is at most three")
        if min_parents < 1 or not 1 <= max_thresholds <= 16:
            raise ValueError("Invalid parent support or threshold count")
        if tie_action not in range(5):
            raise ValueError("tie_action must identify one of the five arms")
        self.max_depth = int(max_depth)
        self.min_parents = int(min_parents)
        self.max_thresholds = int(max_thresholds)
        self.tie_action = int(tie_action)

    def fit(self, X, losses, weights, parents):
        X, losses, weights, parents = validate_training(X, losses, weights, parents)
        if len(np.unique(parents[weights > 0])) < self.min_parents:
            raise ValueError("Root has fewer than the required independent parents")
        self.n_features_in_ = X.shape[1]
        self.fit_parent_hash = canonical_hash(sorted(set(parents[weights > 0])))
        self.training_parent_ids = sorted(set(parents[weights > 0]))

        def build(rows, depth, node_id):
            action, risk = weighted_action(losses[rows], weights[rows], self.tie_action)
            node = {"id": int(node_id), "action": action, "risk": risk,
                    "parent_count": int(len(np.unique(parents[rows][weights[rows] > 0]))),
                    "weight": float(weights[rows].sum())}
            if depth >= self.max_depth:
                return node
            best = None
            best_gain = 1e-12
            for feature in range(X.shape[1]):
                vals = X[rows, feature]
                finite = np.isfinite(vals)
                for threshold in split_thresholds(vals[weights[rows] > 0], self.max_thresholds):
                    for missing_left in (False, True):
                        left = (finite & (vals <= threshold)) | (~finite & missing_left)
                        sides = (rows[left], rows[~left])
                        if any(len(np.unique(parents[s][weights[s] > 0])) < self.min_parents
                               for s in sides):
                            continue
                        child_risk = sum(weighted_action(losses[s], weights[s], self.tie_action)[1]
                                         for s in sides)
                        gain = risk - child_risk
                        if gain > best_gain:
                            best_gain = float(gain)
                            best = (feature, float(threshold), missing_left, sides)
            if best is not None:
                feature, threshold, missing_left, sides = best
                node.update(feature=feature, threshold=threshold,
                            missing_left=bool(missing_left), gain=best_gain,
                            left=build(sides[0], depth + 1, node_id * 2 + 1),
                            right=build(sides[1], depth + 1, node_id * 2 + 2))
            return node

        self.root_ = build(np.arange(len(X)), 0, 0)
        return self

    def _features(self, X):
        if not hasattr(self, "root_"):
            raise ValueError("LossTree has not been fitted")
        X = np.asarray(X, dtype=np.float64)
        if X.ndim != 2 or X.shape[1] != self.n_features_in_ or np.isinf(X).any():
            raise ValueError("Feature dimension mismatch or infinite feature")
        return X

    def _leaf(self, row):
        node = self.root_
        while "feature" in node:
            value = row[node["feature"]]
            left = node["missing_left"] if np.isnan(value) else value <= node["threshold"]
            node = node["left"] if left else node["right"]
        return node

    def predict(self, X):
        return np.asarray([self._leaf(row)["action"] for row in self._features(X)], dtype=int)

    def leaf_ids(self, X):
        return np.asarray([self._leaf(row)["id"] for row in self._features(X)], dtype=int)

    def to_dict(self):
        if not hasattr(self, "root_"):
            raise ValueError("LossTree has not been fitted")
        return copy.deepcopy({"kind": "v431_task_loss_tree", "schema": 1,
                              "config": {"max_depth": self.max_depth,
                                         "min_parents": self.min_parents,
                                         "max_thresholds": self.max_thresholds,
                                         "tie_action": self.tie_action},
                              "n_features": self.n_features_in_,
                              "fit_parent_hash": self.fit_parent_hash,
                              "training_parent_ids": self.training_parent_ids,
                              "tie_rtol": 1e-12, "tie_atol": 1e-14,
                              "root": self.root_})

    @classmethod
    def from_dict(cls, state):
        if state.get("kind") != "v431_task_loss_tree" or state.get("schema") != 1:
            raise ValueError("Unsupported frozen tree identity")
        tree = cls(**state["config"])
        tree.n_features_in_ = int(state["n_features"])
        tree.fit_parent_hash = state["fit_parent_hash"]
        tree.training_parent_ids = list(state["training_parent_ids"])
        if canonical_hash(sorted(tree.training_parent_ids)) != tree.fit_parent_hash:
            raise ValueError("Training parent identity hash mismatch")
        tree.root_ = copy.deepcopy(state["root"])
        return tree

    @property
    def frozen_hash(self):
        return canonical_hash(self.to_dict())
