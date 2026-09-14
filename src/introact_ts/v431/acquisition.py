"""One-step evidence acquisition bound to a frozen terminal governance policy.

This module never receives a candidate array, forecast, or unacquired evidence
when selecting a tool. Training losses are evaluator-only inputs. Every cost is
a complete deployment branch invoice, including final governance and forecast.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from typing import Callable, Mapping, Sequence

import numpy as np


def _require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class Charge:
    key: str
    seconds: float

    def __post_init__(self):
        _require(isinstance(self.key, str) and bool(self.key), "empty charge identity")
        _require(math.isfinite(self.seconds) and self.seconds >= 0, "invalid actual cost")


@dataclass(frozen=True)
class CostInvoice:
    charges: tuple[Charge, ...] = ()

    def __post_init__(self):
        distinct = {}
        for charge in self.charges:
            _require(isinstance(charge, Charge), "untyped cost charge")
            if charge.key in distinct:
                _require(distinct[charge.key] == charge.seconds,
                         "shared charge identity has conflicting costs")
            distinct[charge.key] = charge.seconds
        object.__setattr__(self, "charges", tuple(Charge(k, v) for k, v in sorted(distinct.items())))

    @property
    def total_seconds(self):
        return float(sum(c.seconds for c in self.charges))

    def merge(self, *others: CostInvoice):
        return CostInvoice(self.charges + tuple(c for other in others for c in other.charges))

    def as_dict(self):
        return {"charges": [{"key": c.key, "seconds": c.seconds} for c in self.charges],
                "total_seconds": self.total_seconds}


@dataclass(frozen=True)
class ValueLabelRow:
    uid: str
    parent: str
    tool: str
    terminal_hash: str
    features: tuple[float, ...]
    stop_loss: float
    acquire_loss: float
    stop_invoice: CostInvoice
    acquire_invoice: CostInvoice
    weight: float = 1.
    role: str = "T_acq"
    tool_invoice: CostInvoice = field(default_factory=CostInvoice)

    def __post_init__(self):
        _require(self.role == "T_acq", "acquisition labels must come only from T_acq")
        _require(bool(self.uid) and bool(self.parent) and bool(self.tool) and bool(self.terminal_hash),
                 "missing acquisition label identity")
        _require(math.isfinite(self.stop_loss) and math.isfinite(self.acquire_loss), "invalid task loss")
        _require(math.isfinite(self.weight) and self.weight > 0, "invalid sample weight")
        _require(all(not math.isinf(v) for v in self.features), "infinite visible feature")
        object.__setattr__(self, "features", tuple(float(v) for v in self.features))
        _require(isinstance(self.stop_invoice, CostInvoice) and isinstance(self.acquire_invoice, CostInvoice),
                 "complete branch invoices required")
        _require(isinstance(self.tool_invoice, CostInvoice), "tool invoice required")
        # Same hash means the same measured computation in every branch.
        self.stop_invoice.merge(self.acquire_invoice)
        acquire_charges = {c.key: c.seconds for c in self.acquire_invoice.charges}
        _require(all(acquire_charges.get(c.key) == c.seconds for c in self.tool_invoice.charges),
                 "tool cost missing from complete acquisition branch")

    @property
    def task_gain(self):
        return self.stop_loss - self.acquire_loss

    @property
    def delta_cost(self):
        return self.acquire_invoice.total_seconds - self.stop_invoice.total_seconds


def make_value_labels(rows: Sequence[ValueLabelRow], terminal_hash: str, lambda_value: float):
    """Keep positive, zero and negative values; reject every stale-policy row."""
    _require(math.isfinite(lambda_value) and lambda_value >= 0, "invalid lambda")
    output = []
    for row in rows:
        _require(row.terminal_hash == terminal_hash, "terminal hash invalidates old value labels")
        output.append({"uid": row.uid, "parent": row.parent, "tool": row.tool,
                       "terminal_hash": terminal_hash, "role": row.role, "weight": row.weight,
                       "task_gain": row.task_gain, "delta_cost": row.delta_cost,
                       "stop_cost": row.stop_invoice.total_seconds,
                       "acquire_cost": row.acquire_invoice.total_seconds,
                       "stop_invoice": row.stop_invoice.as_dict(),
                       "acquire_invoice": row.acquire_invoice.as_dict(),
                       "tool_invoice": row.tool_invoice.as_dict(),
                       "lambda": lambda_value, "value": row.task_gain - lambda_value * row.delta_cost})
    return output


@dataclass
class RegressionNode:
    value: float
    parent_count: int
    row_count: int
    depth: int
    feature: int | None = None
    threshold: float | None = None
    missing_left: bool = True
    left: RegressionNode | None = None
    right: RegressionNode | None = None


class ParentRegressionTree:
    """Squared-loss tree whose *independent parent* support bounds every leaf.

    Variants remain separate feature/loss observations with caller-supplied
    source/parent weights. A split must leave >=16 distinct parents on both
    sides; repeated horizons or corruption variants never supply that support.
    """

    def __init__(self, max_depth=2, min_parents=16, max_cutpoints=16):
        _require(0 <= max_depth <= 2, "acquisition tree depth must be <=2")
        _require(min_parents >= 16, "cannot relax independent-parent support below 16")
        _require(1 <= max_cutpoints <= 16, "too many cutpoints")
        self.max_depth = max_depth
        self.min_parents = min_parents
        self.max_cutpoints = max_cutpoints

    def fit(self, X, y, parents, sample_weight=None):
        X, y = np.asarray(X, float), np.asarray(y, float)
        parents = np.asarray(parents, dtype=str)
        weights = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, float)
        _require(X.ndim == 2 and y.shape == parents.shape == weights.shape == (len(X),),
                 "tree training shape mismatch")
        _require(np.isfinite(y).all() and not np.isinf(X).any(), "nonfinite training values")
        _require(np.isfinite(weights).all() and (weights > 0).all(), "invalid training weights")
        _require(len(set(parents)) >= self.min_parents, "insufficient independent train parents")
        self.n_features_in_ = X.shape[1]

        def summary(indices):
            w, target = weights[indices], y[indices]
            mean = float(np.dot(w, target) / w.sum())
            return mean, float(np.dot(w, (target - mean) ** 2))

        def build(indices, depth):
            mean, objective = summary(indices)
            nparents = len(set(parents[indices]))
            node = RegressionNode(mean, nparents, len(indices), depth)
            if depth >= self.max_depth or nparents < 2 * self.min_parents:
                return node
            best = None
            for feature in range(X.shape[1]):
                values = X[indices, feature]
                finite = values[np.isfinite(values)]
                if len(np.unique(finite)) < 2:
                    continue
                cuts = np.unique(np.quantile(finite,
                                  np.linspace(0, 1, self.max_cutpoints + 2)[1:-1]))
                for threshold in cuts:
                    for missing_left in (True, False):
                        goes_left = values <= threshold
                        goes_left[np.isnan(values)] = missing_left
                        left, right = indices[goes_left], indices[~goes_left]
                        if min(len(set(parents[left])), len(set(parents[right]))) < self.min_parents:
                            continue
                        gain = objective - summary(left)[1] - summary(right)[1]
                        if gain > 1e-12 and (best is None or gain > best[0] + 1e-12):
                            best = (gain, feature, float(threshold), missing_left, left, right)
            if best is not None:
                _, node.feature, node.threshold, node.missing_left, left, right = best
                node.left, node.right = build(left, depth + 1), build(right, depth + 1)
            return node

        self.root_ = build(np.arange(len(X)), 0)
        return self

    def predict(self, X):
        X = np.asarray(X, float)
        _require(X.ndim == 2 and X.shape[1] == self.n_features_in_ and not np.isinf(X).any(),
                 "tree prediction shape/nonfinite mismatch")
        output = []
        for row in X:
            node = self.root_
            while node.feature is not None:
                value = row[node.feature]
                left = node.missing_left if np.isnan(value) else value <= node.threshold
                node = node.left if left else node.right
            output.append(node.value)
        return np.asarray(output)


def _validate_feature_names(names):
    # The caller freezes the exact dirty-only schema. Explicitly reject common
    # accidental evaluator/candidate joins instead of ignoring those columns.
    forbidden = ("source", "path", "condition", "clean", "candidate", "evidence",
                 "forecast", "prediction", "future", "oracle", "uid", "parent", "seed")
    _require(bool(names) and len(names) == len(set(names)), "empty/duplicate feature schema")
    _require(all(isinstance(n, str) and n and not any(word in n.lower() for word in forbidden)
                 for n in names), "acquisition schema contains unavailable/identity features")


def _fit_tool_models(rows, price, tools):
    models, support = {}, {}
    for tool in tools:
        subset = [r for r in rows if r.tool == tool]
        count = len({r.parent for r in subset})
        support[tool] = {"parents": count, "rows": len(subset),
                         "status": "fitted" if count >= 16 else "unsupported_parent_count"}
        if count < 16:
            continue
        model = ParentRegressionTree().fit([r.features for r in subset],
                    [r.task_gain - price * r.delta_cost for r in subset],
                    [r.parent for r in subset], [r.weight for r in subset])
        models[tool] = model
    return models, support


@dataclass
class Acquirer:
    terminal_hash: str
    feature_names: tuple[str, ...]
    models: dict[str, ParentRegressionTree]
    lambda_value: float
    report: dict = field(default_factory=dict)

    def predict(self, features, tool, terminal_hash):
        _require(terminal_hash == self.terminal_hash, "terminal hash invalidates trained acquirer")
        values = np.asarray(features, float)
        _require(values.shape == (len(self.feature_names),) and not np.isinf(values).any(),
                 "invalid visible feature vector")
        if tool not in self.models:
            return None
        result = float(self.models[tool].predict(values[None])[0])
        _require(math.isfinite(result), "nonfinite predicted acquisition value")
        return result


def fit_acquirer(rows: Sequence[ValueLabelRow], terminal_hash: str, feature_names,
                 task_differences=None, forbidden_parents=()):
    """Select only registered prices with leave-one-parent-out T_acq validation.

    Each held-out objective uses the *same* positive reference price, so price
    models are compared on identical realised utility. Ties select lambda=0.
    Training-only support failures are explicit and cause that tool to STOP.
    No external/dev features or outcomes are accepted by this function.
    """
    rows = tuple(rows)
    feature_names = tuple(feature_names)
    _validate_feature_names(feature_names)
    _require(bool(rows), "no T_acq labels")
    _require(not ({r.parent for r in rows} & set(forbidden_parents)), "terminal/acquisition parent overlap")
    _require(all(r.terminal_hash == terminal_hash for r in rows), "terminal hash invalidates old value labels")
    _require(all(r.role == "T_acq" and len(r.features) == len(feature_names) for r in rows),
             "invalid acquisition training role/schema")
    seen = [(r.uid, r.tool) for r in rows]
    _require(len(seen) == len(set(seen)), "duplicate acquisition episode/tool labels")
    # Within an episode tool choice may not expose different feature snapshots.
    snapshots = {}
    for row in rows:
        if row.uid in snapshots:
            _require(np.array_equal(snapshots[row.uid], row.features, equal_nan=True),
                     "tool-dependent hidden feature snapshot")
        snapshots[row.uid] = row.features
    differences = np.asarray([r.task_gain for r in rows] if task_differences is None
                             else task_differences, float)
    _require(differences.size > 0 and np.isfinite(differences).all(), "invalid train task scale")
    task_scale = float(np.median(np.abs(differences)))
    # Price scale uses actual tool cost, not the complete branch difference.
    # An acquired final action can be cheaper; its saving belongs in delta_cost.
    positive = [r.tool_invoice.total_seconds for r in rows if r.tool_invoice.total_seconds > 0]
    cost_scale = float(np.median(positive)) if positive else 0.
    scale_ok = task_scale > 0 and cost_scale > 0
    reference_price = 0.1 * task_scale / cost_scale if scale_ok else 0.
    prices = [0., reference_price] if scale_ok else [0.]
    tools = tuple(sorted({r.tool for r in rows}))
    parents = tuple(sorted({r.parent for r in rows}))
    cv_records, summaries = [], []
    for price in prices:
        numerator, denominator = 0., 0.
        for held_parent in parents:
            train = [r for r in rows if r.parent != held_parent]
            models, support = _fit_tool_models(train, price, tools)
            by_uid = {}
            for row in rows:
                if row.parent == held_parent:
                    by_uid.setdefault(row.uid, []).append(row)
            for uid, options in by_uid.items():
                values = {r.tool: float(models[r.tool].predict(np.asarray(r.features)[None])[0])
                          for r in options if r.tool in models}
                selected = max(values, key=values.get) if values and max(values.values()) > 0 else None
                choice = next((r for r in options if r.tool == selected), None)
                weight = options[0].weight
                utility = 0. if choice is None else choice.task_gain - reference_price * choice.delta_cost
                numerator += weight * utility
                denominator += weight
                cv_records.append({"lambda": price, "held_parent": held_parent, "uid": uid,
                                   "train_parents": sorted({r.parent for r in train}),
                                   "tool_support": support, "tool": selected,
                                   "predicted_values": values, "realized_utility": utility,
                                   "weight": weight})
        summaries.append({"lambda": price, "weighted_cv_utility": numerator / denominator})
    best = max(summaries, key=lambda row: (row["weighted_cv_utility"], -row["lambda"]))
    price = best["lambda"]
    models, support = _fit_tool_models(rows, price, tools)
    report = {"terminal_hash": terminal_hash, "feature_names": list(feature_names),
              "train_role": "T_acq", "parents": len(parents), "rows": len(rows),
              "lambda_candidates": prices, "lambda": price, "task_scale": task_scale,
              "positive_tool_cost_scale": cost_scale,
              "scale_status": "valid" if scale_ok else "degenerate_only_lambda_zero",
              "selection": "leave_one_parent_out_T_acq", "reference_price": reference_price,
              "cv_summary": summaries, "cv_records": cv_records, "tool_support": support,
              "max_depth": 2, "min_leaf_independent_parents": 16,
              "model_family": "one parent-constrained squared-loss tree per tool",
              "cutpoints_per_feature": 16,
              "unsupported_behavior": "STOP with explicit status; no zero-valued fake model"}
    return Acquirer(terminal_hash, feature_names, models, price, report)


@dataclass(frozen=True)
class AcquiredBranch:
    arm: str
    invoice: CostInvoice
    evidence_hash: str
    terminal_hash: str


def execute_one_step(*, terminal_hash: str, visible_features, stop_arm: str,
                     stop_invoice: CostInvoice, branch_estimates: Mapping[str, CostInvoice],
                     budget: float | None, applicable: Mapping[str, bool],
                     model: Acquirer | None, fetch: Callable[[str], AcquiredBranch],
                     mode="learned", tool_order=None, condition=False, random_key="", seed=101):
    """Choose STOP or one tool; only fetch() can expose that tool's evidence.

    branch_estimates must be *complete* branches, not marginal tool costs.
    stop_invoice is also complete. Actual costs are retained on budget overrun;
    rejecting a branch never refunds already executed work.
    """
    _require(budget is None or math.isfinite(budget) and budget >= 0, "invalid complete budget")
    _require(mode in ("learned", "fixed", "simple", "random", "stop"), "unknown one-step mode")
    _require(isinstance(stop_invoice, CostInvoice), "complete STOP invoice required")
    if model is not None:
        _require(model.terminal_hash == terminal_hash, "terminal hash invalidates trained acquirer")
    values, excluded = {}, {}
    order = tuple(sorted(branch_estimates)) if tool_order is None else tuple(tool_order)
    _require(len(order) == len(set(order)) and set(order) <= set(branch_estimates), "invalid tool order")
    eligible = []
    for tool in order:
        invoice = branch_estimates[tool]
        _require(isinstance(invoice, CostInvoice), "complete branch invoice required, not cost difference")
        if not applicable.get(tool, False):
            excluded[tool] = "unsupported"
        elif budget is not None and invoice.total_seconds > budget + 1e-12:
            excluded[tool] = "estimated_complete_branch_exceeds_budget"
        else:
            eligible.append(tool)
    selected = None
    if mode == "learned":
        _require(model is not None, "learned mode requires frozen acquirer")
        for tool in eligible:
            value = model.predict(visible_features, tool, terminal_hash)
            if value is None:
                excluded[tool] = "unsupported_train_parent_count"
            else:
                values[tool] = value
        if values and max(values.values()) > 0:
            selected = max(values, key=values.get)
    elif mode == "fixed" or mode == "simple" and condition:
        selected = eligible[0] if eligible else None
    elif mode == "random" and eligible:
        _require(seed == 101, "random acquisition seed is pre-registered as 101")
        # Include STOP so random is a genuine matched acquisition control.
        digest = hashlib.sha256(f"{seed}:{random_key}".encode()).digest()
        options = [None, *eligible]
        selected = options[int.from_bytes(digest[:8], "big") % len(options)]
    arm, invoice, evidence_hash = stop_arm, stop_invoice, None
    if selected is not None:
        branch = fetch(selected)
        _require(isinstance(branch, AcquiredBranch) and isinstance(branch.invoice, CostInvoice),
                 "acquisition did not return actual complete branch")
        _require(branch.terminal_hash == terminal_hash, "acquired branch used a different terminal policy")
        _require(bool(branch.arm) and bool(branch.evidence_hash), "missing action/evidence identity")
        arm, invoice, evidence_hash = branch.arm, branch.invoice, branch.evidence_hash
    overrun = budget is not None and invoice.total_seconds > budget + 1e-12
    return {"terminal_hash": terminal_hash, "mode": mode, "arm": arm,
            "tool": selected, "history": [] if selected is None else [selected],
            "status": "budget_overrun" if overrun else "STOP" if selected is None else "COMMIT",
            "budget": budget, "budget_overrun": overrun,
            "total_seconds": invoice.total_seconds, "invoice": invoice.as_dict(),
            "stop_total_seconds": stop_invoice.total_seconds,
            "delta_cost": invoice.total_seconds - stop_invoice.total_seconds,
            "evidence_hash": evidence_hash, "predicted_values": values, "excluded": excluded,
            "estimated_branch_costs": {t: i.total_seconds for t, i in branch_estimates.items()}}
