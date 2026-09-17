"""v4.4 frozen protocol constants.

This module is the single source of truth for everything that must be frozen
*before* any model runs: the context length, the horizons, the missingness
pattern generators' seeds, the severity ladder, the legal governance action
pool, the only two searchable hyper-parameters (K and beta), the seasonal
periods used by MASE/RMSSE, and the TRAIN-internal split ratios.

Nothing here may be tuned after looking at a result.  The task book (§4, §7,
§8, §9, §10) allows exactly one search over ``K x beta`` and forbids every
other knob.

``PROTOCOL_SEED`` is deliberately a fixed literal rather than a timestamp:
the mask hashes must be reproducible from the repository alone.
"""

from __future__ import annotations

import hashlib

# -- forecasting protocol ---------------------------------------------------

#: Context length.  Fixed by the task book (§7); extra horizons may only ever
#: appear in the appendix, never as a new main condition.
CONTEXT = 512

#: Main horizons.
HORIZONS = (96, 192)

#: Parent stride inherited from the r5 main protocol (``L + max(H)``).
PARENT_STRIDE = 704

#: Missingness patterns fixed in the main text (§8).
PATTERNS = ("P1_point", "P2_target_block", "P3_shared_block", "P4_tail")

#: Severity ladder (§9).  ``MAIN_SEVERITY`` is the only main-experiment
#: severity; the other two are robustness conditions.  Replay-Fit draws a
#: *mixed* support from all three, decided by hash per historical episode.
SEVERITIES = (0.10, 0.30, 0.50)
MAIN_SEVERITY = 0.10
ROBUSTNESS_SEVERITIES = (0.30, 0.50)

#: Mask seed namespace.  Frozen literal, never derived from wall clock.
PROTOCOL_SEED = 20260917

# -- legal governance actions (§2) ------------------------------------------

#: The five legal actions.  Order is frozen because it defines the argmax
#: tie-break and the recorded action index.
ACTIONS = (
    "KEEP",
    "FFILL",
    "SINGLE_TSICL",
    "MULTI_TSICL",
    "CONTEXT_RIDGE",
)

#: The reference action ``a_0`` used to define utility.
REFERENCE_ACTION = "KEEP"

ACTION_INDEX = {name: i for i, name in enumerate(ACTIONS)}

# -- the only searchable hyper-parameters (§4) ------------------------------

K_GRID = (8, 16, 32)
BETA_GRID = (0.0, 1.0, 1.64)

#: Small positive constant added to ``median(d)`` when forming ``tau`` so a
#: degenerate (all-zero distance) neighbourhood does not divide by zero.
TAU_EPSILON = 1e-12

# -- TRAIN-internal split (§10) ---------------------------------------------

#: Replay-Fit / Gate / TRAIN-Eval.
SPLIT_RATIOS = (0.60, 0.20, 0.20)
SPLIT_NAMES = ("replay_fit", "gate", "train_eval")

#: The block the replay bank is built from.  Every retrieval and every control
#: fit is restricted to it (task book §10), so a request evaluated on the Gate
#: or TRAIN-Eval block can never read a record from its own block.
#:
#: This names the block a *record* belongs to, never the block a request is
#: evaluated on.  Passing an evaluation block as a retrieval guard filters the
#: bank down to nothing and makes the selector abstain on every request.
BANK_BLOCK = "replay_fit"

#: Minimum purge between split blocks, in raw rows.
PURGE = CONTEXT + max(HORIZONS)  # 704

# -- datasets (§5) ----------------------------------------------------------

#: The eight sources.  None may be dropped because of its result.
SOURCES = (
    "ETTh1",
    "ETTh2",
    "ETTm1",
    "ETTm2",
    "Electricity",
    "Exchange",
    "Traffic",
    "Weather",
)

#: Naive seasonal period used by MASE / RMSSE denominators, from the declared
#: sampling frequency of each source (see ``configs/v431-r5/main_protocol_v2.json``).
SEASONAL_PERIODS = {
    "ETTh1": 24,        # 1h
    "ETTh2": 24,        # 1h
    "ETTm1": 96,        # 15min
    "ETTm2": 96,        # 15min
    "Electricity": 24,  # 1h
    "Exchange": 5,      # daily observations
    "Traffic": 24,      # 1h
    "Weather": 144,     # 10min
}

#: Backbones.  Bolt and TimesFM are the development pair; Chronos-2 may only
#: be added after the method is frozen (§6, §25).
DEV_BACKBONES = ("bolt", "timesfm")
ALL_BACKBONES = ("bolt", "timesfm", "chronos2")

# -- aggregation (§13) ------------------------------------------------------

#: variant -> parent -> source -> equal-weight source macro average.
AGGREGATION_ORDER = ("variant", "parent", "source", "macro")

#: Statistics (§14).
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 101
CI_LEVEL = 0.95

#: Pre-registered epsilon below which the Catalog Gap Closed denominator is
#: treated as degenerate and the window is excluded from the CGC mean (§28).
CGC_EPSILON = 1e-9


def mask_seed(source: str, parent: str, origin: int, horizon: int,
              pattern: str, protocol_seed: int = PROTOCOL_SEED) -> int:
    """Deterministic 64-bit mask seed.

    The seed depends only on the frozen identity tuple required by the task
    book (§8): source, parent, origin, horizon, pattern, protocol seed.  It
    must not depend on the observed values, on a severity, or on anything the
    model later produces.
    """
    if pattern not in PATTERNS:
        raise ValueError(f"unregistered missingness pattern: {pattern}")
    key = f"{source}|{parent}|{int(origin)}|{int(horizon)}|{pattern}|{int(protocol_seed)}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def seasonal_period(source: str) -> int:
    try:
        return SEASONAL_PERIODS[source]
    except KeyError as exc:  # pragma: no cover - guarded by source registry
        raise KeyError(f"no seasonal period registered for source {source!r}") from exc
