"""Train-only response maps for frozen, actually acquired probe evidence."""
from __future__ import annotations
from dataclasses import dataclass
import copy
import numpy as np
from sklearn.tree import DecisionTreeClassifier

from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.schemas import array_hash
from introact_ts.v431.decision_tree import canonical_hash
from introact_ts.v431.acquisition import _validate_feature_names
from .probe import PSI_NAMES


STATE_PRIMITIVES = {'H32': ('h32',), 'H': ('long',), 'control': ('long', 'short'),
                    'equal-cost': ('long', 'second'), 'disagreement': ('long', 'short')}
ALPHAS = (.1, 1., 10.)
CART_CONFIG = {'max_depth': 3, 'min_samples_leaf': 96, 'random_state': 101}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def historical_argmax(reference_action, evidence, *, fully_observed=False):
    """Unlearned H32/H ranking control, with the same paid acquired evidence."""
    if fully_observed:
        return 0
    if evidence is None or evidence.status != 'completed':
        return int(reference_action)
    require(evidence.kind in ('H32', 'H'), 'Historical argmax uses a single ordinary probe')
    gains = np.asarray(evidence.d, float)
    require(gains[reference_action] == 0., 'Historical reference gain changed')
    best = float(gains.max())
    return int(reference_action) if gains[reference_action] == best else int(np.flatnonzero(gains == best)[0])


class PriorRidge:
    """Weighted ridge around a declared coefficient prior, including intercept.

    Minimize sum_i w_i (y_i - [x_i,1] beta)^2 + alpha ||beta-prior||^2.
    Source/parent weights are retained exactly as supplied. A residual map
    anchors its measured-response coefficient at one; an otherwise identical
    direct ridge anchors every coefficient at zero. No fitted coefficients,
    target labels or feature transforms are shared across fitting partitions.
    """

    def __init__(self, alpha=1., response_coordinate=0, fit_intercept=True):
        require(float(alpha) in (.1, 1., 10.), 'Unregistered ridge regularization')
        self.alpha = float(alpha)
        self.response_coordinate = response_coordinate
        self.fit_intercept = bool(fit_intercept)

    def fit(self, X, y, sample_weight):
        require(not hasattr(self, 'coef_'), 'Frozen ridge cannot be refitted')
        X, y, w = np.asarray(X, float), np.asarray(y, float), np.asarray(sample_weight, float)
        require(X.ndim == 2 and y.shape == w.shape == (len(X),), 'Ridge input shape mismatch')
        require(len(X) > 0 and np.isfinite(X).all() and np.isfinite(y).all(), 'Ridge requires actual finite evidence and labels')
        require(np.isfinite(w).all() and (w > 0).all(), 'Invalid source-parent weights')
        self.n_features_in_ = X.shape[1]
        prior = np.zeros(self.n_features_in_+int(self.fit_intercept))
        if self.response_coordinate is not None:
            require(isinstance(self.response_coordinate, int) and 0 <= self.response_coordinate < self.n_features_in_, 'Invalid anchored response coordinate')
            prior[self.response_coordinate] = 1.
        design = np.c_[X, np.ones(len(X))] if self.fit_intercept else X
        gram = design.T @ (w[:, None] * design) + self.alpha * np.eye(design.shape[1])
        residual = y-design @ prior
        coef = prior + np.linalg.solve(gram, design.T @ (w*residual))
        require(np.isfinite(coef).all(), 'Nonfinite fitted coefficients')
        self.coef_ = coef[:-1] if self.fit_intercept else coef
        self.intercept_, self.prior_ = float(coef[-1]) if self.fit_intercept else 0., prior
        self.training_identity_ = {'design': array_hash(X), 'targets': array_hash(y), 'weights': array_hash(w)}
        return self

    def predict(self, X):
        require(hasattr(self, 'coef_'), 'Unfitted ridge')
        X = np.asarray(X, float)
        require(X.ndim == 2 and X.shape[1] == self.n_features_in_ and np.isfinite(X).all(), 'Unavailable or invalid ridge evidence')
        return X @ self.coef_ + self.intercept_

    def to_dict(self):
        require(hasattr(self, 'coef_'), 'Unfitted ridge')
        return {'alpha': self.alpha, 'response_coordinate': self.response_coordinate, 'fit_intercept': self.fit_intercept,
                'coefficients': self.coef_.tolist(), 'intercept': self.intercept_,
                'prior': self.prior_.tolist(), 'training_identity': self.training_identity_}

    @property
    def frozen_hash(self):
        return canonical_hash(self.to_dict())


@dataclass(frozen=True)
class ResponseEvidence:
    """Immutable measured state. Absent primitives have no feature values."""
    kind: str
    d: tuple | None = None
    psi: tuple | None = None
    extra: tuple | None = None
    status: str = 'completed'
    reason: str | None = None
    evidence_hash: str | None = None
    primitive_hashes: tuple = ()
    requested_kind: str | None = None

    def __post_init__(self):
        require(self.kind in STATE_PRIMITIVES, 'Unknown response evidence state')
        require(self.requested_kind is None or self.requested_kind in STATE_PRIMITIVES, 'Unknown requested state')
        object.__setattr__(self, 'primitive_hashes', tuple((str(k), str(v)) for k, v in self.primitive_hashes))
        require(self.status in ('completed', 'unsupported', 'failed'), 'Unknown response status')
        if self.status != 'completed':
            require(self.d is None and self.psi is None and self.extra is None and bool(self.reason),
                    'Unavailable response cannot contain fabricated feature values')
            return
        require(bool(self.evidence_hash), 'Actual evidence identity required')
        require(set(k for k, v in self.primitive_hashes) == set(STATE_PRIMITIVES[self.kind])
                and all(bool(v) for _, v in self.primitive_hashes), 'Missing actual primitive identities')
        for name in ('d', 'psi', 'extra'):
            value = getattr(self, name)
            if value is not None:
                a = np.asarray(value, float)
                require(a.ndim == 1 and np.isfinite(a).all(), 'Unavailable/nonfinite evidence is not a feature')
                object.__setattr__(self, name, tuple(map(float, a)))
        require(self.d is not None and len(self.d) == 5 and self.psi is not None, 'Incomplete gain/psi schema')
        need_extra = self.kind in ('control', 'equal-cost', 'disagreement')
        require((self.extra is not None) == need_extra, 'No-kappa state may not read/fill an unavailable response')
        require(not need_extra or len(self.extra) == 5, 'Response extra must have five actual arm values')

    @property
    def tools(self):
        return STATE_PRIMITIVES[self.kind]

    @property
    def identity_hash(self):
        return canonical_hash({'kind': self.kind, 'd': self.d, 'psi': self.psi, 'extra': self.extra,
                               'status': self.status, 'reason': self.reason,
                               'evidence_hash': self.evidence_hash, 'primitive_hashes': self.primitive_hashes,
                               'requested_kind': self.requested_kind})

    def arm_features(self, arm):
        require(self.status == 'completed', 'Unacquired or failed response is unavailable')
        return np.r_[self.d[arm], [] if self.extra is None else [self.extra[arm]], self.psi]


ResponseState = ResponseEvidence


def state_from_results(kind, atomic_results, *, reference_arm, psi_names=PSI_NAMES, allow_degrade_to_H=False):
    """Build only the requested measured state, shared by offline and online.

    Atomic results use ProbeResult.to_dict() plus the dirty-only `psi` mapping.
    The disagreement control applies the old standard-deviation statistic to
    this family's same long/short pair; it does not relabel old Bolt evidence.
    No unrequested primitive or candidate array is inspected here.
    """
    require(kind in STATE_PRIMITIVES and reference_arm in POOL, 'Unknown state/reference identity')
    if kind == 'control' and allow_degrade_to_H and 'long' in atomic_results and atomic_results['long'].get('status') == 'completed':
        if 'short' not in atomic_results or atomic_results['short'].get('status') != 'completed':
            actual = state_from_results('H', {'long': atomic_results['long']}, reference_arm=reference_arm, psi_names=psi_names)
            return ResponseEvidence(actual.kind, actual.d, actual.psi, actual.extra, actual.status,
                                    'requested_control_degraded_to_actually_acquired_H', actual.evidence_hash,
                                    actual.primitive_hashes, requested_kind='control')
    needed = STATE_PRIMITIVES[kind]
    atoms = {}
    for key in needed:
        if key not in atomic_results:
            return ResponseEvidence(kind, status='unsupported', reason=key+':not_acquired')
        atom = atomic_results[key]
        if atom.get('status') != 'completed':
            status = 'failed' if atom.get('status') == 'failed' else 'unsupported'
            return ResponseEvidence(kind, status=status, reason=key+':'+str(atom.get('reason', atom.get('status'))))
        atoms[key] = atom
    ordinary = list(needed)
    primary = atoms[ordinary[0]]
    gains, identities = {}, []
    for key in ordinary:
        atom = atoms[key]
        require(atom['reference_arm'] == reference_arm, 'Probe was scored against another frozen reference')
        for name in ('base_uid', 'family', 'current_scale', 'model_identity_hash'):
            require(atom[name] == primary[name], 'Inconsistent state primitive '+name)
        scale = float(atom['current_scale'])
        require(np.isfinite(scale) and scale > 0, 'Invalid current-task scale')
        require(set(atom['mae']) == set(POOL), 'Five actual raw probe losses required')
        values = np.array([(atom['mae'][reference_arm]-atom['mae'][a])/scale for a in POOL])
        require(np.isfinite(values).all(), 'Nonfinite probe gain')
        if 'gain' in atom:
            require(np.allclose(values, [atom['gain'][a] for a in POOL], rtol=1e-10, atol=1e-10), 'Probe gain scale/reference mismatch')
        gains[key] = values
        identities.append((key, canonical_hash({k: atom.get(k) for k in
                          ('base_uid', 'probe', 'input_hash', 'model_identity_hash', 'spec', 'scoring_mask_hash',
                           'current_scale', 'reference_arm', 'mae', 'prediction_hashes', 'psi')})))
    require(set(primary['psi']) == set(psi_names), 'Probe mismatch feature schema changed')
    psi = tuple(primary['psi'][key] for key in psi_names)
    extra = None
    if kind in ('control', 'disagreement'):
        long, short = atoms['long'], atoms['short']
        require(long['scoring_mask_hash'] == short['scoring_mask_hash'], 'Response pair scoring masks differ')
        require(long['spec']['origin'] == short['spec']['origin'] and long['spec']['horizon'] == short['spec']['horizon']
                and short['spec']['start']-long['spec']['start'] == 64, 'Response pair endpoint or length decrement changed')
        length = long['spec']['origin']-long['spec']['start']
        factor = (long['spec']['current_origin']-length)/64
        if kind == 'control':
            extra = factor*(gains['long']-gains['short'])
        else:
            # Original multi-view forecast dispersion, not |kappa| or the std
            # of historical error gains. No validation values enter this term.
            values = []
            for arm in POOL:
                pair = []
                for atom in (long, short):
                    pred = np.asarray(atom['raw_predictions'][arm], float)
                    require(pred.shape == (atom['spec']['horizon'],) and np.isfinite(pred).all(), 'Actual full-horizon prediction required for dispersion')
                    require('prediction_hashes' not in atom or array_hash(pred) == atom['prediction_hashes'][arm], 'Raw dispersion prediction identity changed')
                    pair.append(pred)
                values.append(float(np.std(np.asarray(pair), axis=0, ddof=0).mean()/long['current_scale']))
            extra = np.asarray(values)
    elif kind == 'equal-cost':
        require(atoms['long']['spec']['origin']-atoms['second']['spec']['origin'] == 64
                and atoms['long']['spec']['horizon'] == atoms['second']['spec']['horizon'], 'Equal-cost ordinary origins changed')
        extra = gains['second']
    payload = {'kind': kind, 'd': gains[ordinary[0]].tolist(), 'psi': psi,
               'extra': None if extra is None else np.asarray(extra).tolist(), 'primitives': identities}
    return ResponseEvidence(kind, payload['d'], psi, payload['extra'], evidence_hash=canonical_hash(payload), primitive_hashes=tuple(identities))


class ResponsePolicy:
    """Shared response slopes, per-arm intercepts, and independent gate choice.

    Residual and direct ridge have identical train-normalized inputs and width.
    Residual fits Delta-d and adds original-unit d back. This anchors beta1 at
    one without clipping signed kappa or standardizing the task-loss target.
    The CART comparator sees exactly the same acquired gain/response/psi group.
    """

    def __init__(self, reference_action, reference_parent_ids, feature_names, psi_names,
                 estimator='residual', states=tuple(STATE_PRIMITIVES)):
        require(estimator in ('residual', 'direct', 'cart'), 'Unregistered response estimator')
        require(int(reference_action) in range(5), 'Unknown reference action')
        _validate_feature_names(tuple(feature_names))
        _validate_feature_names(tuple(psi_names))
        require(bool(psi_names) and len(set(psi_names)) == len(psi_names), 'Invalid fixed psi schema')
        require(set(states) <= set(STATE_PRIMITIVES) and bool(states), 'Unknown frozen states')
        self.reference_action, self.reference_parent_ids = int(reference_action), sorted(set(map(str, reference_parent_ids)))
        self.feature_names, self.psi_names = tuple(feature_names), tuple(psi_names)
        self.estimator, self.states = estimator, tuple(states)

    def _check_evidence(self, evidence, n):
        require(set(evidence) == set(self.states), 'State evidence schema changed')
        for state in self.states:
            require(len(evidence[state]) == n, 'State row count mismatch')
            for e in evidence[state]:
                require(isinstance(e, ResponseEvidence) and e.kind == state, 'Wrong acquired state')
                if e.status == 'completed':
                    require(len(e.psi) == len(self.psi_names) and e.d[self.reference_action] == 0., 'Psi width or reference gain changed')

    @staticmethod
    def _loss_inputs(losses, weights, parents):
        L, w, p = np.asarray(losses, float), np.asarray(weights, float), np.asarray(parents, str)
        require(L.ndim == 2 and L.shape[1] == 5 and w.shape == p.shape == (len(L),), 'Training shapes differ')
        require(np.isfinite(L).all() and np.isfinite(w).all() and (w > 0).all(), 'Invalid actual training losses/weights')
        return L, w, p

    def _expanded(self, evidence, L, w, rows):
        arms = [a for a in range(5) if a != self.reference_action]
        features, actions, targets, weights = [], [], [], []
        for i in rows:
            for a in arms:
                features.append(evidence[i].arm_features(a))
                actions.append(arms.index(a))
                targets.append(L[i, self.reference_action]-L[i, a])
                weights.append(w[i]/len(arms))
        return np.asarray(features), np.asarray(actions), np.asarray(targets), np.asarray(weights)

    @staticmethod
    def _episode_features(e):
        return np.r_[e.d, [] if e.extra is None else e.extra, e.psi]

    def _gains(self, model, transform, e):
        if self.estimator == 'cart':
            action = int(model.predict(self._episode_features(e)[None])[0])
            return None, action
        arms = [a for a in range(5) if a != self.reference_action]
        f = np.asarray([e.arm_features(a) for a in arms])
        x = (f-transform['mean'])/transform['scale']
        pred = model.predict(np.c_[x, np.eye(4)])
        if self.estimator == 'residual':
            pred = pred + f[:, 0]
        gains = np.zeros(5)
        gains[arms] = pred
        best = float(gains.max())
        action = self.reference_action if gains[self.reference_action] == best else int(np.flatnonzero(gains == best)[0])
        return gains, action

    def fit(self, evidence, losses, weights, parents, *, gate_evidence, gate_losses,
            gate_weights, gate_parents):
        require(not hasattr(self, 'models_'), 'Frozen response policy cannot be refitted')
        L, w, p = self._loss_inputs(losses, weights, parents)
        G, gw, gp = self._loss_inputs(gate_losses, gate_weights, gate_parents)
        require(not set(p) & set(gp), 'Fit/gate parent overlap')
        require(set(self.reference_parent_ids) <= set(p) | set(gp), 'Reference uses parents outside fit/gate')
        self._check_evidence(evidence, len(L)); self._check_evidence(gate_evidence, len(G))
        self.fit_parent_ids_, self.gate_parent_ids_ = sorted(set(p)), sorted(set(gp))
        self.training_parent_ids = sorted(set(p) | set(gp))
        self.training_identity_ = {'fit_loss': array_hash(L), 'gate_loss': array_hash(G),
                                   'fit_weights': array_hash(w), 'gate_weights': array_hash(gw),
                                   'fit_parent_hash': canonical_hash(p.tolist()), 'gate_parent_hash': canonical_hash(gp.tolist()),
                                   'fit_evidence_hashes': {s: [e.identity_hash for e in evidence[s]] for s in self.states},
                                   'gate_evidence_hashes': {s: [e.identity_hash for e in gate_evidence[s]] for s in self.states}}
        self.models_, self.transforms_, self.audit_ = {}, {}, {}
        for state in self.states:
            E, GE = evidence[state], gate_evidence[state]
            rows = np.array([i for i, e in enumerate(E) if e.status == 'completed'], dtype=int)
            grows = [i for i, e in enumerate(GE) if e.status == 'completed']
            audit = {'fit_supported_rows': len(rows), 'fit_supported_parents': len(set(p[rows])),
                     'gate_supported_rows': len(grows), 'gate_supported_parents': len(set(gp[grows])),
                     'primitives': list(STATE_PRIMITIVES[state]), 'alpha_candidates': [] if self.estimator == 'cart' else list(ALPHAS),
                     'fit_role': 'T_fit', 'selection_role': 'T_gate', 'unsupported_behavior': 'frozen_reference'}
            self.audit_[state] = audit
            if len(set(p[rows])) < 16 or not grows:
                audit.update(status='unsupported', reason='insufficient_fit_parent_or_gate_state_support')
                continue
            if self.estimator == 'cart':
                if len(rows) < CART_CONFIG['min_samples_leaf']:
                    audit.update(status='unsupported', reason='fewer_than_96_CART_rows'); continue
                Z = np.asarray([self._episode_features(E[i]) for i in rows])
                labels = np.argmin(L[rows], axis=1)
                labels[L[rows, self.reference_action] == np.min(L[rows], axis=1)] = self.reference_action
                model = DecisionTreeClassifier(**CART_CONFIG).fit(Z, labels, sample_weight=w[rows])
                leaf = model.apply(Z)
                support = {int(a): len(set(p[rows][leaf == a])) for a in np.unique(leaf)}
                audit.update(leaf_parent_counts=support, cart_config=dict(CART_CONFIG))
                if min(support.values()) < 16:
                    audit.update(status='unsupported', reason='CART_leaf_has_fewer_than_16_parents'); continue
                self.models_[state], self.transforms_[state] = model, None
                audit.update(status='fitted', alpha=None, input_width=Z.shape[1]); continue
            F, arms, y, ew = self._expanded(E, L, w, rows)
            mean = np.average(F, axis=0, weights=ew)
            variance = np.average((F-mean)**2, axis=0, weights=ew)
            scale = np.sqrt(variance); scale[scale < 1e-12] = 1.
            transform = {'mean': mean, 'scale': scale}
            design = np.c_[(F-mean)/scale, np.eye(4)[arms]]
            target = y-F[:, 0] if self.estimator == 'residual' else y
            proposals = []
            for alpha in ALPHAS:
                model = PriorRidge(alpha, response_coordinate=None, fit_intercept=False).fit(design, target, ew)
                actions = np.full(len(G), self.reference_action, dtype=int)
                for i in grows:
                    _, actions[i] = self._gains(model, transform, GE[i])
                risk = float(np.dot(gw, G[np.arange(len(G)), actions])/gw.sum())
                proposals.append((risk, alpha, model))
            risk, alpha, model = min(proposals, key=lambda r: (r[0], r[1]))
            self.models_[state], self.transforms_[state] = model, transform
            audit.update(status='fitted', alpha=alpha, gate_weighted_task_risk=risk,
                         gate_candidates=[{'alpha': a, 'weighted_task_risk': r} for r, a, _ in proposals],
                         input_width=design.shape[1], target='Delta-d_in_original_MASE_units' if self.estimator == 'residual' else 'Delta_in_original_MASE_units')
        return self

    def choose(self, dirty_features, state=None, *, fully_observed=False):
        require(hasattr(self, 'models_'), 'Unfitted response policy')
        x = np.asarray(dirty_features, float)
        require(x.shape == (len(self.feature_names),) and not np.isinf(x).any(), 'Invalid dirty-only feature snapshot')
        complete = bool(fully_observed or ('missing_fraction' in self.feature_names and x[self.feature_names.index('missing_fraction')] == 0.))
        result = {'action': self.reference_action, 'arm': POOL[self.reference_action], 'status': 'fixed_reference',
                  'reason': 'no_evidence_acquired', 'state': 'none' if state is None else state.kind,
                  'reference_arm': POOL[self.reference_action], 'estimated_gains': None}
        result['requested_state'] = 'none' if state is None else state.requested_kind or state.kind
        if complete:
            return {**result, 'action': 0, 'arm': POOL[0], 'status': 'no_op', 'reason': 'fully_observed_input'}
        if state is None:
            return result
        require(isinstance(state, ResponseEvidence) and state.kind in self.states, 'Unknown acquired response state')
        if state.status != 'completed':
            return {**result, 'status': 'fallback', 'reason': state.status+':'+state.reason}
        if state.kind not in self.models_:
            return {**result, 'status': 'fallback', 'reason': self.audit_[state.kind]['reason']}
        self._check_evidence({s: [state] if s == state.kind else [ResponseEvidence(s, status='unsupported', reason='not_requested')] for s in self.states}, 1)
        gains, action = self._gains(self.models_[state.kind], self.transforms_[state.kind], state)
        return {**result, 'action': action, 'arm': POOL[action], 'status': 'selected', 'reason': None,
                'estimated_gains': None if gains is None else gains.tolist(), 'evidence_hash': state.evidence_hash}

    def to_dict(self):
        require(hasattr(self, 'models_'), 'Unfitted response policy')
        models = {}
        for s, m in self.models_.items():
            if self.estimator == 'cart':
                t = m.tree_
                models[s] = {'classes': m.classes_.tolist(), 'left': t.children_left.tolist(), 'right': t.children_right.tolist(),
                             'features': t.feature.tolist(), 'thresholds': t.threshold.tolist(), 'values': t.value.tolist()}
            else:
                transform = self.transforms_[s]
                width = len(transform['mean'])
                slope = m.coef_[:width]/transform['scale']
                original_slope = slope.copy()
                if self.estimator == 'residual':
                    original_slope[0] += 1.
                models[s] = {**m.to_dict(), 'transform': {k: v.tolist() for k, v in transform.items()},
                             'original_gain_unit_slopes': original_slope.tolist(),
                             'original_gain_unit_arm_intercepts': (m.coef_[width:]-float(slope @ transform['mean'])).tolist(),
                             'arm_intercept_order': [POOL[a] for a in range(5) if a != self.reference_action],
                             'add_back_unstandardized_d': self.estimator == 'residual'}
        return copy.deepcopy({'version': 'v4.3.1-r3', 'estimator': self.estimator, 'reference_action': self.reference_action,
                              'reference_parent_ids': self.reference_parent_ids, 'training_parent_ids': self.training_parent_ids,
                              'fit_parent_ids': self.fit_parent_ids_, 'gate_parent_ids': self.gate_parent_ids_,
                              'feature_names': self.feature_names, 'psi_names': self.psi_names, 'states': self.states,
                              'models': models, 'audit': self.audit_, 'training_identity': self.training_identity_,
                              'reference_gain': 0., 'tie_action': self.reference_action, 'kappa_clipped': False,
                              'all_unknown_or_failed_state_behavior': 'fixed_reference', 'complete_observation': 'KEEP'})

    @property
    def frozen_hash(self):
        return canonical_hash(self.to_dict())
