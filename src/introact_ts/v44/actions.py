"""The five legal governance actions (task book §2).

Every action is a pure function of the *current* context and mask.  None of
them reads a future label, a candidate forecast, or any result produced by a
model: the only model-shaped dependency is the injected imputer used by the two
TS-ICL actions, and that imputer is a frozen checkpoint applied to the
intervention input only.

The actions return the full modified panel *and* the target-channel series that
is actually handed to the frozen TSFM.  Keeping both makes the "final
prediction matches the truly executed version" audit trivial (§18 test 14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

import numpy as np

from .hashing import array_hash, require
from .protocol import ACTIONS, REFERENCE_ACTION

#: Minimum observed rows before the context ridge is allowed to fit.
RIDGE_MIN_ROWS = 32

#: Dimension cap for the context ridge, matching the frozen r5 A4_RIDGE_CONTEXT
#: recipe: standardise, optionally PCA down to at most this many components,
#: then ridge.  Fixed, not searched.
RIDGE_MAX_FEATURES = 8

#: Ridge regularisation.  Fixed, not searched: the task book forbids adding
#: any hyper-parameter search beyond ``K`` and ``beta``.
RIDGE_ALPHA = 1.0

#: Minimum fraction of finite covariates at the gap positions before the
#: context ridge is allowed to run (frozen r5 rule).
RIDGE_MIN_GAP_COVERAGE = 0.5


class Imputer(Protocol):
    """Frozen intervention tool contract.

    ``impute_single`` receives the target channel with NaNs and returns a fully
    finite series of the same length.  ``impute_multi`` additionally receives
    the covariate columns.  Implementations must be pure: same input, same
    output, no state carried between calls.
    """

    def impute_single(self, target: np.ndarray) -> np.ndarray: ...

    def impute_multi(self, target: np.ndarray, covariates: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class ActionOutcome:
    """One executed governance action."""

    name: str
    target: np.ndarray           # model input for the target channel
    panel: np.ndarray            # (L, C) modified panel
    applicable: bool = True
    reason: str | None = None
    changed: bool = False        # did the action alter the reference input?
    input_hash: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", np.asarray(self.target, dtype=np.float64))
        object.__setattr__(self, "panel", np.asarray(self.panel, dtype=np.float64))
        require(self.name in ACTIONS, f"unregistered action {self.name!r}")
        require(self.target.ndim == 1, "target must be one-dimensional")
        require(self.panel.shape[0] == len(self.target), "panel/target length mismatch")
        if not self.input_hash:
            object.__setattr__(self, "input_hash", array_hash(self.target))
        if not self.applicable:
            require(bool(self.reason), "unsupported action requires a reason")


def _fill_forward(x: np.ndarray) -> np.ndarray:
    """Forward fill; leading gaps take the first observation."""
    out = np.array(x, dtype=np.float64, copy=True)
    valid = np.flatnonzero(np.isfinite(out))
    if len(valid) == 0:
        raise ValueError("forward fill unsupported for an all-missing series")
    out[: valid[0]] = out[valid[0]]
    last = out[valid[0]]
    for i in range(valid[0] + 1, len(out)):
        if not np.isfinite(out[i]):
            out[i] = last
        else:
            last = out[i]
    return out


def _ridge_impute(target: np.ndarray, covariates: np.ndarray, *,
                  alpha: float = RIDGE_ALPHA,
                  min_rows: int = RIDGE_MIN_ROWS,
                  max_features: int = RIDGE_MAX_FEATURES) -> np.ndarray:
    """Context ridge: predict the target's gaps from the other channels.

    Faithful to the frozen r5 ``A4_RIDGE_CONTEXT`` recipe -- standardise the
    covariates (with explicit missing indicators), optionally PCA down to
    ``max_features`` components, then ridge on the rows where the target is
    observed.  Fitted only on the known context, and it refuses rather than
    silently degrading to a different estimator.
    """
    from sklearn.decomposition import PCA
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    target = np.asarray(target, dtype=np.float64)
    covariates = np.asarray(covariates, dtype=np.float64)
    missing = ~np.isfinite(target)
    observed = np.isfinite(target)
    if not missing.any():
        return target.copy()
    if covariates.ndim != 2 or covariates.shape[0] != len(target):
        raise ValueError("covariate shape mismatch")
    if covariates.shape[1] == 0:
        raise ValueError("context ridge requires at least one covariate")
    if float(np.isfinite(covariates[missing]).mean()) < RIDGE_MIN_GAP_COVERAGE:
        raise ValueError("insufficient gap covariates")

    train_x = covariates[observed]
    y_train = target[observed]
    if len(y_train) < min_rows:
        raise ValueError("insufficient observed rows for context ridge")
    columns = np.any(np.isfinite(train_x), axis=0)
    if not columns.any():
        raise ValueError("no supported covariates")
    query_x = covariates[missing][:, columns]
    train_x = train_x[:, columns]

    median = np.nanmedian(train_x, axis=0)
    median = np.where(np.isfinite(median), median, 0.0)
    train_missing = ~np.isfinite(train_x)
    query_missing = ~np.isfinite(query_x)
    train_x = np.where(train_missing, median, train_x)
    query_x = np.where(query_missing, median, query_x)
    supported_channels = train_x.shape[1]

    # The dimension cap covers the missing indicators as well as the values.
    train_x = np.column_stack((train_x, train_missing))
    query_x = np.column_stack((query_x, query_missing))
    scaler = StandardScaler().fit(train_x)
    train_x = scaler.transform(train_x)
    query_x = scaler.transform(query_x)
    if train_x.shape[1] > max_features:
        dim = min(max_features, supported_channels, len(train_x) // 8)
        if dim < 1:
            raise ValueError("insufficient PCA support")
        pca = PCA(n_components=dim, svd_solver="full").fit(train_x)
        train_x = pca.transform(train_x)
        query_x = pca.transform(query_x)

    model = Ridge(alpha=alpha).fit(train_x, y_train)
    filled = target.copy()
    filled[missing] = model.predict(query_x)
    if not np.isfinite(filled).all():
        raise ValueError("context ridge produced non-finite values")
    return filled


def _guard(name: str, filled: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Sanity gate every action must pass before it may be executed."""
    filled = np.asarray(filled, dtype=np.float64)
    require(filled.shape == reference.shape, f"{name}: changed the time axis")
    require(not np.isinf(filled).any(), f"{name}: produced infinities")
    observed = np.isfinite(reference)
    require(np.array_equal(filled[observed], reference[observed]),
            f"{name}: rewrote an observed value")
    require(np.isfinite(filled).all(), f"{name}: left a gap unfilled")
    return filled


def apply_action(name: str, panel: np.ndarray, *, imputer: Imputer | None = None,
                 reference: str = REFERENCE_ACTION) -> ActionOutcome:
    """Execute one governance action on ``panel`` (``(L, C)``, channel 0 = target)."""
    if name not in ACTIONS:
        raise ValueError(f"unregistered action {name!r}")
    panel = np.asarray(panel, dtype=np.float64)
    if panel.ndim != 2:
        raise ValueError("panel must be two-dimensional")
    target = panel[:, 0]
    covariates = panel[:, 1:]
    reference_target = target.copy()

    def outcome(filled: np.ndarray, *, applicable: bool = True,
                reason: str | None = None, metadata: dict | None = None) -> ActionOutcome:
        new_panel = panel.copy()
        if applicable:
            new_panel[:, 0] = filled
        return ActionOutcome(
            name=name,
            target=new_panel[:, 0],
            panel=new_panel,
            applicable=applicable,
            reason=reason,
            changed=bool(applicable and not np.array_equal(filled, reference_target)),
            metadata=metadata or {},
        )

    if name == "KEEP":
        # The native contract: hand the incomplete series to the TSFM as-is.
        return outcome(reference_target, metadata={"strategy": "native_nan"})

    if not np.isnan(reference_target).any():
        # A complete target has nothing to intervene on; every non-KEEP action
        # is an alias of the reference by contract (task book §17 C1).
        return outcome(reference_target, metadata={"strategy": "no_gap_alias"})

    if name == "FFILL":
        try:
            filled = _fill_forward(reference_target)
        except ValueError as exc:
            return outcome(reference_target, applicable=False, reason=str(exc))
        return outcome(filled, metadata={"strategy": "forward_fill"})

    if name == "SINGLE_TSICL":
        if imputer is None:
            return outcome(reference_target, applicable=False,
                           reason="no imputer bound for single TS-ICL")
        try:
            filled = _guard(name, imputer.impute_single(reference_target.copy()),
                            reference_target)
        except Exception as exc:  # noqa: BLE001 - recorded, never silent
            return outcome(reference_target, applicable=False,
                           reason=f"{type(exc).__name__}: {exc}")
        return outcome(filled, metadata={"strategy": "tsicl_single"})

    if name == "MULTI_TSICL":
        if imputer is None:
            return outcome(reference_target, applicable=False,
                           reason="no imputer bound for multi TS-ICL")
        try:
            filled = _guard(name,
                            imputer.impute_multi(reference_target.copy(), covariates.copy()),
                            reference_target)
        except Exception as exc:  # noqa: BLE001 - recorded, never silent
            return outcome(reference_target, applicable=False,
                           reason=f"{type(exc).__name__}: {exc}")
        return outcome(filled, metadata={"strategy": "tsicl_multi"})

    if name == "CONTEXT_RIDGE":
        try:
            filled = _guard(name, _ridge_impute(reference_target, covariates),
                            reference_target)
        except Exception as exc:  # noqa: BLE001 - recorded, never silent
            return outcome(reference_target, applicable=False,
                           reason=f"{type(exc).__name__}: {exc}")
        return outcome(filled, metadata={"strategy": "context_ridge"})

    raise AssertionError("unreachable")  # pragma: no cover


def legal_actions(panel: np.ndarray) -> tuple[str, ...]:
    """The legal action set for this request.

    A complete target admits only KEEP: there is no gap to govern, and the
    complete-input contract requires the selector to abstain (§31 D).
    """
    panel = np.asarray(panel, dtype=np.float64)
    if not np.isnan(panel[:, 0]).any():
        return (REFERENCE_ACTION,)
    return ACTIONS


def execute_catalog(panel: np.ndarray, *, imputer: Imputer | None = None,
                    actions: Sequence[str] = ACTIONS) -> dict[str, ActionOutcome]:
    """Execute the whole catalog and mark aliases against the reference input."""
    reference = apply_action(REFERENCE_ACTION, panel, imputer=imputer)
    outcomes: dict[str, ActionOutcome] = {}
    for name in actions:
        item = reference if name == REFERENCE_ACTION else apply_action(
            name, panel, imputer=imputer)
        outcomes[name] = item
    return outcomes


def alias_groups(outcomes: dict[str, ActionOutcome]) -> dict[str, str]:
    """Map each action to the canonical action with the identical model input."""
    canonical: dict[str, str] = {}
    seen: dict[str, str] = {}
    for name in ACTIONS:
        item = outcomes.get(name)
        if item is None:
            continue
        owner = seen.get(item.input_hash)
        if owner is None:
            seen[item.input_hash] = name
            canonical[name] = name
        else:
            canonical[name] = owner
    return canonical
