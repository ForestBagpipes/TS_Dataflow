"""Train-only evidence refinement with an independently audited rejection gate."""
from __future__ import annotations

import copy

import numpy as np

from .decision_tree import (LossTree, canonical_hash, split_thresholds,
                            validate_training, weighted_action)


def grouped_gain_interval(gains, weights, parents, *, groups=None, repeats=1000,
                          seed=101):
    """Empirical 90% parent bootstrap; optional source strata stay metadata.

    Every parent's correlated rows are aggregated before resampling.  The
    supplied final row weights determine each parent's mass and task gain.
    This is an empirical development rule, not a formal safety certificate.
    """
    parents = np.asarray(parents).astype(str)
    weights = np.asarray(weights, dtype=float)
    gains = np.asarray(gains, dtype=float)
    groups = np.repeat("all", len(parents)) if groups is None else np.asarray(groups).astype(str)
    if not (gains.shape == weights.shape == parents.shape == groups.shape):
        raise ValueError("Bootstrap arrays must have equal one-dimensional shape")
    ids = np.unique(parents[weights > 0])
    if not len(ids):
        raise ValueError("No positive-mass bootstrap parent")
    grouped = {}
    for parent in ids:
        idx = parents == parent
        strata = np.unique(groups[idx])
        if len(strata) != 1:
            raise ValueError("A parent cannot cross bootstrap source strata")
        grouped.setdefault(strata[0], []).append(
            (float(np.sum(gains[idx] * weights[idx])), float(np.sum(weights[idx]))))
    rng = np.random.default_rng(seed)
    draws = np.zeros(repeats, dtype=float)
    total_weight = float(weights.sum())
    for entries in grouped.values():
        entries = np.asarray(entries)
        # Preserve the original source mass rather than letting a bootstrap
        # sample reweight the source-macro objective.
        stratum_mass = float(entries[:, 1].sum()) / total_weight
        sample = rng.integers(0, len(entries), size=(repeats, len(entries)))
        sums = entries[sample].sum(axis=1)
        draws += stratum_mass * sums[:, 0] / sums[:, 1]
    return {"mean_gain": float(np.sum(gains * weights) / total_weight),
            "lower_90": float(np.quantile(draws, 0.05)),
            "upper_90": float(np.quantile(draws, 0.95)),
            "parent_count": int(len(ids)), "repeats": int(repeats),
            "seed": int(seed), "grouping": "parent_within_supplied_stratum"}


class RefinedPolicy:
    """At most one evidence split after each frozen dirty-only leaf.

    The evidence used by a split must have been acquired: NaN always means keep
    the parent policy, never take an implicit learned missing-evidence branch.
    fit/gate inputs may contain train data only; their parent sets must be disjoint.
    """

    def __init__(self, base_tree, min_fit_parents=16, min_gate_parents=8,
                 bootstrap_repeats=1000, seed=101, prune=True):
        if base_tree.max_depth > 2:
            raise ValueError("Evidence refinement requires a base depth of at most two")
        self.base_tree = LossTree.from_dict(base_tree.to_dict())
        self.min_fit_parents = int(min_fit_parents)
        self.min_gate_parents = int(min_gate_parents)
        self.bootstrap_repeats = int(bootstrap_repeats)
        self.seed = int(seed)
        self.prune = bool(prune)

    def fit(self, X_dirty, X_evidence, losses, weights, parents,
            gate_X_dirty, gate_X_evidence, gate_losses, gate_weights, gate_parents,
            gate_groups=None):
        X, L, w, p = validate_training(X_dirty, losses, weights, parents)
        GX, GL, Gw, Gp = validate_training(gate_X_dirty, gate_losses, gate_weights, gate_parents)
        E = np.asarray(X_evidence, dtype=float)
        GE = np.asarray(gate_X_evidence, dtype=float)
        if E.ndim != 2 or E.shape[0] != len(X) or GE.shape != (len(GX), E.shape[1]):
            raise ValueError("Evidence shape mismatch")
        if np.isinf(E).any() or np.isinf(GE).any():
            raise ValueError("Evidence permits unavailable NaN, not infinity")
        if set(p) & set(Gp) or set(self.base_tree.training_parent_ids) & set(Gp):
            raise ValueError("Gate parents overlap fit/base parents")
        if not set(p).issubset(self.base_tree.training_parent_ids):
            raise ValueError("Refinement fit parents must belong to base fit data")
        if gate_groups is not None and np.asarray(gate_groups).shape != (len(GX),):
            raise ValueError("Gate strata shape mismatch")
        groups = None if gate_groups is None else np.asarray(gate_groups)
        self.n_evidence_features_ = E.shape[1]
        self.gate_parent_hash = canonical_hash(sorted(set(Gp)))
        self.refinements_ = {}
        self.audit_ = []
        leaves = self.base_tree.leaf_ids(X)
        gleaves = self.base_tree.leaf_ids(GX)
        actions = self.base_tree.predict(X)
        gactions = self.base_tree.predict(GX)
        for leaf_id in sorted(set(leaves)):
            rows = np.flatnonzero(leaves == leaf_id)
            parent_action = int(actions[rows[0]])
            parent_risk = float(np.sum(w[rows] * L[rows, parent_action]))
            proposal = None
            best_gain = 1e-12
            for feature in range(E.shape[1]):
                values = E[rows, feature]
                finite = np.isfinite(values)
                for threshold in split_thresholds(values[w[rows] > 0], self.base_tree.max_thresholds):
                    lr = rows[finite & (values <= threshold)]
                    rr = rows[finite & (values > threshold)]
                    if any(len(np.unique(p[r][w[r] > 0])) < self.min_fit_parents for r in (lr, rr)):
                        continue
                    la, lcost = weighted_action(L[lr], w[lr], self.base_tree.tie_action)
                    ra, rcost = weighted_action(L[rr], w[rr], self.base_tree.tie_action)
                    missing = rows[~finite]
                    cost = lcost + rcost + float(np.sum(w[missing] * L[missing, parent_action]))
                    if parent_risk - cost > best_gain:
                        best_gain = parent_risk - cost
                        proposal = {"feature": feature, "threshold": float(threshold),
                                    "left_action": la, "right_action": ra,
                                    "parent_action": parent_action,
                                    "fit_gain_weighted": float(best_gain),
                                    "left_fit_parents": int(len(np.unique(p[lr][w[lr] > 0]))),
                                    "right_fit_parents": int(len(np.unique(p[rr][w[rr] > 0]))),
                                    "missing_route": "parent_policy"}
            audit = {"base_leaf": int(leaf_id), "parent_action": parent_action,
                     "proposal": copy.deepcopy(proposal), "accepted": False}
            if proposal is None:
                audit["reason"] = "no_supported_positive_fit_gain"
                self.audit_.append(audit)
                continue
            gr = np.flatnonzero(gleaves == leaf_id)
            available = np.isfinite(GE[gr, proposal["feature"]])
            supported = gr[available]
            count = len(np.unique(Gp[supported][Gw[supported] > 0]))
            audit["gate_supported_parents"] = int(count)
            if count >= self.min_gate_parents:
                pa = np.where(GE[supported, proposal["feature"]] <= proposal["threshold"],
                              proposal["left_action"], proposal["right_action"])
                gains = GL[supported, gactions[supported]] - GL[supported, pa]
                audit["gate"] = grouped_gain_interval(
                    gains, Gw[supported], Gp[supported],
                    groups=None if groups is None else groups[supported],
                    repeats=self.bootstrap_repeats, seed=self.seed + int(leaf_id))
                accepted = audit["gate"]["lower_90"] > 0
                audit["reason"] = "gate_positive_lower_bound" if accepted else "gate_not_positive"
            else:
                accepted = False
                audit["reason"] = "insufficient_gate_parent_support"
            if not self.prune:
                accepted = True
                audit["unpruned_ablation"] = True
            audit["accepted"] = bool(accepted)
            if accepted:
                self.refinements_[str(int(leaf_id))] = proposal
            self.audit_.append(audit)
        return self

    def predict(self, X_dirty, X_evidence):
        E = np.asarray(X_evidence, dtype=float)
        actions = self.base_tree.predict(X_dirty)
        leaves = self.base_tree.leaf_ids(X_dirty)
        if E.shape != (len(actions), self.n_evidence_features_) or np.isinf(E).any():
            raise ValueError("Evidence shape mismatch or infinite evidence")
        for i, leaf in enumerate(leaves):
            rule = self.refinements_.get(str(int(leaf)))
            if rule is None or not np.isfinite(E[i, rule["feature"]]):
                continue
            actions[i] = rule["left_action"] if E[i, rule["feature"]] <= rule["threshold"] else rule["right_action"]
        return actions

    def to_dict(self):
        if not hasattr(self, "refinements_"):
            raise ValueError("RefinedPolicy has not been fitted")
        return copy.deepcopy({"kind": "v431_rejectable_refinement", "schema": 1,
                              "base": self.base_tree.to_dict(),
                              "config": {"min_fit_parents": self.min_fit_parents,
                                         "min_gate_parents": self.min_gate_parents,
                                         "bootstrap_repeats": self.bootstrap_repeats,
                                         "seed": self.seed, "prune": self.prune},
                              "n_evidence_features": self.n_evidence_features_,
                              "gate_parent_hash": self.gate_parent_hash,
                              "refinements": self.refinements_, "audit": self.audit_})

    @classmethod
    def from_dict(cls, state):
        if state.get("kind") != "v431_rejectable_refinement" or state.get("schema") != 1:
            raise ValueError("Unsupported frozen refinement identity")
        policy = cls(LossTree.from_dict(state["base"]), **state["config"])
        policy.n_evidence_features_ = int(state["n_evidence_features"])
        policy.gate_parent_hash = state["gate_parent_hash"]
        policy.refinements_ = copy.deepcopy(state["refinements"])
        policy.audit_ = copy.deepcopy(state["audit"])
        return policy

    @property
    def frozen_hash(self):
        return canonical_hash(self.to_dict())
