"""A frozen CART for each actually acquired evidence state, plus a fixed prior."""
from __future__ import annotations

from dataclasses import dataclass
import copy

import numpy as np
from sklearn.tree import DecisionTreeClassifier

from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.schemas import array_hash
from introact_ts.v431.decision_tree import canonical_hash, validate_training, weighted_action


TOOLS = ('mask', 'history')
STATE_TOOLS = {'none': (), 'mask': ('mask',), 'history': ('history',), 'both': TOOLS}
CART_CONFIG = dict(max_depth=3, min_samples_leaf=96, random_state=101)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def freeze_reference(losses, weights, parents):
    """Caller supplies only its registered T_fit + T_gate reference rows."""
    _, L, w, p = validate_training(np.zeros((len(losses), 1)), losses, weights, parents)
    action, risk = weighted_action(L, w, tie_action=2)
    return {'action': action, 'arm': POOL[action], 'parent_ids': sorted(set(p[w > 0])),
            'weighted_risks': (np.sum(L * w[:, None], axis=0) / w.sum()).tolist(),
            'chosen_weighted_risk': risk / float(w.sum()), 'tie_action': 2,
            'losses_hash': array_hash(L), 'weights_hash': array_hash(w), 'parents_hash': canonical_hash(p.tolist())}


@dataclass(frozen=True)
class EvidenceState:
    # A row is (tool, immutable values or None, status, reason). Unacquired
    # values have no object in this state, rather than a zero-filled vector.
    entries: tuple = ()

    def acquire(self, tool, values=None, *, status='completed', reason=None):
        require(tool in TOOLS and tool not in self.tools, 'Unknown or repeated evidence tool')
        require(status in ('completed', 'unsupported', 'failed'), 'Invalid evidence result status')
        if status == 'completed':
            array = np.asarray(values, float)
            require(array.shape == (15,) and not np.isinf(array).any(), 'Evidence must have 15 finite-or-NaN fields')
            frozen = tuple(float(value) for value in array)
        else:
            require(values is None and bool(reason), 'Failed evidence needs an explicit reason, not fabricated values')
            frozen = None
        return EvidenceState(self.entries + ((tool, frozen, status, reason),))

    @property
    def tools(self):
        return tuple(row[0] for row in self.entries)

    @property
    def kind(self):
        present = set(self.tools)
        require(len(present) == len(self.entries) and present <= set(TOOLS), 'Invalid evidence state identity')
        return 'both' if len(present) == 2 else next(iter(present)) if present else 'none'

    def result(self, tool):
        require(tool in self.tools, 'Unacquired evidence is unavailable')
        return next(row for row in self.entries if row[0] == tool)


def supported_rows(evidence):
    array = np.asarray(evidence, float)
    require(array.ndim == 2 and array.shape[1] == 15 and not np.isinf(array).any(), 'Evidence schema mismatch')
    values = array.reshape(len(array), 5, 3)
    # KEEP mask errors may be NaN, with support 0; other supported arms make
    # the tool usable. No failed task loss or unavailable tool is set to zero.
    return np.any(np.isfinite(values[:, :, 0]) & np.isfinite(values[:, :, 1])
                  & np.isfinite(values[:, :, 2]) & (values[:, :, 2] > 0), axis=1)


class StatePolicy:
    """State-specific ordinary CART with the unchanged r1 CART hyperparameters.

    All three models use T_fit only. The fixed reference is supplied from a
    separately recorded train-only selection; neither dev nor acquisition
    labels enter fitting. Missing evidence groups are absent from that state's
    schema. Within an acquired group, missing columns have explicit flags.
    """

    def __init__(self, reference_action, reference_parent_ids, feature_names):
        require(int(reference_action) in range(len(POOL)), 'Invalid fixed reference')
        self.reference_action = int(reference_action)
        self.reference_parent_ids = sorted(set(map(str, reference_parent_ids)))
        require(bool(self.reference_parent_ids), 'Fixed reference training identity required')
        self.feature_names = tuple(feature_names)
        require(bool(self.feature_names) and len(set(self.feature_names)) == len(self.feature_names), 'Invalid dirty feature schema')
        forbidden = ('source', 'path', 'condition', 'future', 'clean', 'oracle', 'candidate', 'evidence', 'forecast')
        require(not any(any(word in name.lower() for word in forbidden) for name in self.feature_names),
                'Unavailable or identifying dirty feature')

    def fit(self, X_dirty, evidence, losses, weights, parents):
        require(not hasattr(self, 'models_'), 'Frozen state policy cannot be fitted again')
        X, L, w, p = validate_training(X_dirty, losses, weights, parents)
        require(X.shape[1] == len(self.feature_names), 'Dirty feature dimensions changed')
        require(set(evidence) == set(TOOLS), 'Training needs separate mask and history evidence')
        E = {tool: np.asarray(evidence[tool], float) for tool in TOOLS}
        for value in E.values():
            require(value.shape == (len(X), 15) and not np.isinf(value).any(), 'Invalid training evidence')
        self.training_parent_ids = sorted(set(p[w > 0]))
        self.models_, self.transforms_, self.audit_ = {}, {}, {}
        self.training_identity_ = {'dirty': array_hash(X), 'losses': array_hash(L), 'weights': array_hash(w),
                                   'parents': canonical_hash(p.tolist()),
                                   'evidence': {t: array_hash(E[t]) for t in TOOLS}}
        for state in ('mask', 'history', 'both'):
            tools = STATE_TOOLS[state]
            supported = (w > 0) & np.logical_and.reduce([supported_rows(E[t]) for t in tools])
            rows = np.flatnonzero(supported)
            count = len(set(p[rows]))
            audit = {'state': state, 'tools': list(tools), 'tool_count': len(tools),
                     'supported_rows': len(rows), 'supported_parents': count,
                     'unsupported_rows': int((~supported).sum()), 'cart_config': dict(CART_CONFIG)}
            self.audit_[state] = audit
            if count < 16 or len(rows) < 96:
                audit.update(status='unsupported', reason='insufficient_training_parent_or_row_support')
                continue
            Z = np.c_[X, *(E[t] for t in tools)]
            present_columns = np.flatnonzero(np.isfinite(Z[rows]).any(axis=0))
            require(len(present_columns) > 0, 'No legal input feature available')
            selected = Z[rows][:, present_columns]
            median = np.nanmedian(selected, axis=0)
            require(np.isfinite(median).all(), 'Invalid acquired-state training median')
            design = np.c_[np.where(np.isfinite(selected), selected, median), np.isfinite(selected)]
            model = DecisionTreeClassifier(**CART_CONFIG).fit(design, np.argmin(L[rows], axis=1), sample_weight=w[rows])
            leaf_ids = model.apply(design)
            support = {int(leaf): len(set(p[rows][leaf_ids == leaf])) for leaf in np.unique(leaf_ids)}
            audit.update(leaf_parent_counts={str(k): v for k, v in support.items()},
                         fit_parent_ids=sorted(set(p[rows])), actual_depth=int(model.get_depth()),
                         actual_leaves=int(model.get_n_leaves()))
            if any(count < 16 for count in support.values()):
                audit.update(status='unsupported', reason='CART_leaf_has_fewer_than_16_independent_parents')
                # Do not lower support, prune ad hoc, or substitute a deeper fit.
                continue
            self.models_[state] = model
            self.transforms_[state] = {'columns': present_columns, 'median': median}
            audit.update(status='fitted', reason=None, input_feature_count=design.shape[1],
                         dropped_all_missing_columns=int(Z.shape[1] - len(present_columns)))
        return self

    def choose(self, dirty_features, state, *, fully_observed=False):
        require(hasattr(self, 'models_'), 'State policy must be frozen after fitting')
        require(isinstance(state, EvidenceState), 'Only acquired EvidenceState objects are accepted')
        x = np.asarray(dirty_features, float)
        require(x.shape == (len(self.feature_names),) and not np.isinf(x).any(), 'Dirty feature mismatch')
        kind = state.kind
        result = {'state': kind, 'history': list(state.tools), 'reference_arm': POOL[self.reference_action]}
        fully_observed = bool(fully_observed or ('missing_fraction' in self.feature_names
                              and x[self.feature_names.index('missing_fraction')] == 0.))
        if fully_observed:
            return {**result, 'action': 0, 'arm': POOL[0], 'status': 'no_op', 'reason': 'fully_observed_input'}
        if kind == 'none':
            return {**result, 'action': self.reference_action, 'arm': POOL[self.reference_action],
                    'status': 'fixed_reference', 'reason': 'no_evidence_acquired'}
        for tool in STATE_TOOLS[kind]:
            _, values, status, reason = state.result(tool)
            if status != 'completed':
                return {**result, 'action': self.reference_action, 'arm': POOL[self.reference_action],
                        'status': 'fallback', 'reason': f'{tool}:{status}:{reason}'}
            if not supported_rows(np.asarray(values)[None])[0]:
                return {**result, 'action': self.reference_action, 'arm': POOL[self.reference_action],
                        'status': 'fallback', 'reason': f'{tool}:insufficient_current_support'}
        if kind not in self.models_:
            return {**result, 'action': self.reference_action, 'arm': POOL[self.reference_action],
                    'status': 'fallback', 'reason': self.audit_[kind]['reason']}
        z = np.r_[x, *(state.result(t)[1] for t in STATE_TOOLS[kind])]
        transform = self.transforms_[kind]
        selected = z[transform['columns']]
        design = np.r_[np.where(np.isfinite(selected), selected, transform['median']), np.isfinite(selected)]
        try:
            action = int(self.models_[kind].predict(design[None])[0])
        except Exception as exc:
            return {**result, 'action': self.reference_action, 'arm': POOL[self.reference_action],
                    'status': 'fallback', 'reason': f'CART_inference_failed:{type(exc).__name__}:{exc}'}
        require(action in range(len(POOL)), 'State model returned an invalid action')
        return {**result, 'action': action, 'arm': POOL[action], 'status': 'selected', 'reason': None}

    def predict(self, X_dirty, states, *, fully_observed=None):
        X = np.asarray(X_dirty, float)
        require(len(X) == len(states), 'State batch mismatch')
        observed = np.zeros(len(X), dtype=bool) if fully_observed is None else np.asarray(fully_observed, bool)
        require(observed.shape == (len(X),), 'Observation batch mismatch')
        return np.asarray([self.choose(x, state, fully_observed=bool(full))['action']
                           for x, state, full in zip(X, states, observed)], dtype=int)

    def to_dict(self):
        require(hasattr(self, 'models_'), 'Unfitted state policy cannot be frozen')
        trees = {}
        for state, model in self.models_.items():
            tree = model.tree_
            trees[state] = {'classes': model.classes_.tolist(), 'n_features': int(model.n_features_in_),
                           'children_left': tree.children_left.tolist(), 'children_right': tree.children_right.tolist(),
                           'features': tree.feature.tolist(), 'thresholds': tree.threshold.tolist(),
                           'values': tree.value.tolist(), 'weighted_samples': tree.weighted_n_node_samples.tolist(),
                           'transform': {k: v.tolist() for k, v in self.transforms_[state].items()}}
        return copy.deepcopy({'kind': 'v431_r2_evidence_state_CART', 'schema': 1,
            'reference_action': self.reference_action, 'reference_parent_ids': self.reference_parent_ids,
            'feature_names': list(self.feature_names), 'training_parent_ids': self.training_parent_ids,
            'training_identity': self.training_identity_, 'cart_config': dict(CART_CONFIG),
            'state_tools': STATE_TOOLS, 'models': trees, 'audit': self.audit_,
            'no_evidence': 'fixed_reference', 'fully_observed': 'KEEP',
            'unsupported_or_failed': 'explicit_fixed_reference', 'unknown_tool_values': 'absent'})

    @property
    def frozen_hash(self):
        return canonical_hash(self.to_dict())
