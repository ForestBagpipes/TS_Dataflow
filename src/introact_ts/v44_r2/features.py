"""The r2 feature set: 12 episode-state + 5 action-identity + 2 intervention.

The v4.4 ablation already answered the question this module would otherwise
have to ask again: ``A3_WO_FORECAST`` (dropping the reference-forecast block)
and ``A2_WO_INTERVENTION`` were *better* than the full v4.4 state on Bolt, and
the forecast block was no better than neutral on TimesFM.  A feature group that
the data has already rejected is not re-entered under a new name.

So the r2 state keeps only what the evidence did not reject, and adds the one
thing a *ranking* learner needs and a distance metric did not: the identity of
the action being scored.  Without it the learner would have to infer which
action a row describes from the intervention block alone, which is impossible
for the two TS-ICL arms (they are the same block with a different encoder).

* **episode state** (12) -- what is missing and what the visible past looks
  like.  Shared by every action of one episode.
* **action identity** (5) -- one-hot over the frozen action order.
* **minimal intervention** (2) -- ``fraction_changed`` and
  ``near_origin_change``.  Input-only: computed from the candidate input and
  the reference input, never from any forecast.

Everything here is a pure function of the masked request and the candidate
input, so the same call is valid on the replay path and on the live path.
"""

from __future__ import annotations

import numpy as np

from ..v44 import state as ST
from ..v44.protocol import ACTIONS

#: The twelve episode-state features, in order.  The first six are the mask
#: state and the last six the visible-context descriptors; both are reused
#: verbatim from ``introact_ts.v44.state`` so r2 and v4.4 cannot drift apart on
#: what "missing ratio" or "seasonal ACF" means.
EPISODE_STATE_FEATURES = ST.MASK_FEATURES + ST.CONTEXT_FEATURES

#: One-hot action identity.
ACTION_FEATURES = tuple(f"is_{name}" for name in ACTIONS)

#: The only two intervention summaries kept.  Indices into
#: ``ST.INTERVENTION_FEATURES``, which is
#: ``(mean_abs_change, max_abs_change, fraction_changed, change_trend,
#: near_origin_change)``.
INTERVENTION_KEEP = ("fraction_changed", "near_origin_change")
_INTERVENTION_INDEX = tuple(ST.INTERVENTION_FEATURES.index(name)
                            for name in INTERVENTION_KEEP)

#: The frozen, ordered r2 feature list.
FEATURE_NAMES = EPISODE_STATE_FEATURES + ACTION_FEATURES + INTERVENTION_KEEP

STATE_DIM = len(FEATURE_NAMES)


def episode_state(mask: np.ndarray, reference_target: np.ndarray,
                  period: int) -> np.ndarray:
    """The twelve features shared by every action of one episode."""
    return np.concatenate([
        ST.mask_features_from_mask(mask),
        ST.context_features(reference_target, period),
    ])


def intervention_minimal(candidate_target: np.ndarray,
                         reference_target: np.ndarray,
                         scale: float) -> np.ndarray:
    """The two surviving intervention summaries (input-only)."""
    full = ST.intervention_features(candidate_target, reference_target, scale)
    return full[list(_INTERVENTION_INDEX)]


def action_one_hot(action: str) -> np.ndarray:
    if action not in ACTIONS:
        raise ValueError(f"unregistered action {action!r}")
    vector = np.zeros(len(ACTIONS), dtype=np.float64)
    vector[ACTIONS.index(action)] = 1.0
    return vector


def action_features(*, action: str, episode_state_vector: np.ndarray,
                    candidate_target: np.ndarray | None,
                    reference_target: np.ndarray,
                    scale: float) -> np.ndarray:
    """The full 19-dim feature vector of one ``(episode, action)`` row.

    ``candidate_target`` is ``None`` when the action is not executable for this
    request; the row is then not built at all by the caller, so the ``None``
    branch exists only to keep the contract explicit.
    """
    if candidate_target is None:
        raise ValueError("a feature row requires an executable candidate input")
    return np.concatenate([
        np.asarray(episode_state_vector, dtype=np.float64),
        action_one_hot(action),
        intervention_minimal(candidate_target, reference_target, scale),
    ])


def assert_dimension(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float64).reshape(-1)
    if vector.size != STATE_DIM:
        raise ValueError(f"expected {STATE_DIM} features, got {vector.size}")
    if not np.isfinite(vector).all():
        raise ValueError("feature vector must be finite")
    return vector


# -- the pairwise design ----------------------------------------------------
#
# A preference model is trained on ``f(x_a) - f(x_b)``.  Naively that means
# feeding the learner ``x_a - x_b``, and that silently deletes the entire
# episode-state block: the twelve state features are a property of the
# *request*, so they are identical for every action of one episode and their
# difference is exactly zero.  A learner on raw differences therefore cannot
# see the state at all -- it can only ever recover one global action order,
# which is the opposite of "choose the action that fits this episode".
#
# The state only becomes usable through its **interaction with the action**:
# the whole question is which action is best *given* the state.  So the pair is
# re-encoded as that interaction, keeping the same three information groups the
# r2 plan froze and adding nothing:
#
#   ``state (x) (onehot_a - onehot_b)``   12 * 5 = 60   action-conditional state
#   ``onehot_a - onehot_b``                    5        state-free action taste
#   ``intervention_a - intervention_b``        2        input-only intervention
#
# The first block is what lets a *linear* model express "when the gap is in the
# tail, FFILL is better than MULTI_TSICL": it is a per-action linear score
# ``w_a . state``.  Trees get the same block and can additionally bend it.

#: ``len(EPISODE_STATE_FEATURES) * len(ACTIONS)``.
INTERACTION_DIM = len(EPISODE_STATE_FEATURES) * len(ACTIONS)

#: The frozen width of one pairwise row.
PAIR_DIM = INTERACTION_DIM + len(ACTIONS) + len(INTERVENTION_KEEP)

_STATE_SLICE = slice(0, len(EPISODE_STATE_FEATURES))
_ACTION_SLICE = slice(len(EPISODE_STATE_FEATURES),
                      len(EPISODE_STATE_FEATURES) + len(ACTIONS))
_INTERVENTION_SLICE = slice(len(EPISODE_STATE_FEATURES) + len(ACTIONS),
                            STATE_DIM)


def pair_design(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """The ``PAIR_DIM`` design row for the ordered pair ``(left, right)``.

    Both arguments are 19-dim action vectors of the *same* episode, so their
    state blocks must agree; that is asserted rather than assumed, because a
    pair built across two requests is not a counterfactual comparison and must
    never reach the learner.
    """
    left = assert_dimension(left)
    right = assert_dimension(right)
    if not np.array_equal(left[_STATE_SLICE], right[_STATE_SLICE]):
        raise ValueError("a pair must be built from one episode's two actions")
    action_delta = left[_ACTION_SLICE] - right[_ACTION_SLICE]
    state = left[_STATE_SLICE]
    return np.concatenate([
        np.kron(action_delta, state),
        action_delta,
        left[_INTERVENTION_SLICE] - right[_INTERVENTION_SLICE],
    ])


def assert_pair_dimension(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float64).reshape(-1)
    if vector.size != PAIR_DIM:
        raise ValueError(f"expected {PAIR_DIM} pair features, got {vector.size}")
    if not np.isfinite(vector).all():
        raise ValueError("pair design must be finite")
    return vector
