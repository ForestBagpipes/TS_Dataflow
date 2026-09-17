"""IntroAct-TS v4.4 -- isolated implementation.

v4.4 replaces the r5 convex-projection search with three modules:

1. :mod:`introact_ts.v44.replay`  -- counterfactual replay of historical
   ``(episode, action)`` executions into a TRAIN-only bank.
2. :mod:`introact_ts.v44.state`   -- task-state features (mask / visible
   context / intervention / reference forecast).
3. :mod:`introact_ts.v44.matching` -- local matching plus a conservative
   abstention gate.

Supporting modules freeze the protocol (:mod:`protocol`), the missingness
generators (:mod:`masking`), the five governance actions (:mod:`actions`), the
metrics and aggregation ladder (:mod:`metrics`), the TRAIN-internal split
(:mod:`splits`) and the statistics (:mod:`statistics`).

The package is deliberately isolated: it imports only the canonical hash
helpers from the frozen v4.3 code and never writes to any r5 artifact.
"""

from .protocol import (
    ACTIONS,
    ALL_BACKBONES,
    BETA_GRID,
    CONTEXT,
    DEV_BACKBONES,
    HORIZONS,
    K_GRID,
    MAIN_SEVERITY,
    PATTERNS,
    PROTOCOL_SEED,
    REFERENCE_ACTION,
    SEVERITIES,
    SOURCES,
)

__all__ = [
    "ACTIONS",
    "ALL_BACKBONES",
    "BETA_GRID",
    "CONTEXT",
    "DEV_BACKBONES",
    "HORIZONS",
    "K_GRID",
    "MAIN_SEVERITY",
    "PATTERNS",
    "PROTOCOL_SEED",
    "REFERENCE_ACTION",
    "SEVERITIES",
    "SOURCES",
]
