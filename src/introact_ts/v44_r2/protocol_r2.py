"""v4.4-r2 frozen constants.

Everything here is decided *before* any score is looked at.  The r2 revision
keeps the v4.4 protocol (context, horizons, patterns, severities, splits,
action pool, reference action, aggregation, statistics) untouched and only
replaces the searchable quantities:

* v4.4 searched ``K x beta`` (9 configurations) for a KNN + lower-confidence
  bound selector.
* v4.4-r2 searches ``model config x tau`` (7 x 4 = 28 configurations) for a
  pairwise decision-regret ranker plus a single confidence veto.

No other knob exists.  In particular there is no per-backbone hyper-parameter:
the learner family, the ensemble weight and the veto threshold are shared by
both development backbones, and Chronos-2 later inherits them unchanged.
"""

from __future__ import annotations

from ..v44.protocol import (  # re-exported so r2 never redefines the protocol
    ACTIONS,
    ALL_BACKBONES,
    BANK_BLOCK,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    CI_LEVEL,
    CONTEXT,
    DEV_BACKBONES,
    HORIZONS,
    MAIN_SEVERITY,
    PATTERNS,
    PROTOCOL_SEED,
    PURGE,
    REFERENCE_ACTION,
    ROBUSTNESS_SEVERITIES,
    SEASONAL_PERIODS,
    SEVERITIES,
    SOURCES,
    SPLIT_NAMES,
    SPLIT_RATIOS,
)

#: The only veto thresholds that may be searched.  0.50 is the "almost no
#: extra conservatism" end, so the method is allowed to conclude from the data
#: that an extra conservative penalty is unnecessary.  A large beta-style grid
#: is explicitly forbidden.
TAU_GRID = (0.50, 0.55, 0.60, 0.65)

#: Ensemble weight on the linear scorer.  ``alpha=1`` is pure linear and
#: ``alpha=0`` is pure tree, so the endpoints coincide with the two standalone
#: learners and the grid is a genuine interpolation between them.
ALPHA_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)

#: The three learner families of the frozen comparison.
LEARNER_LINEAR = "L1_PAIRWISE_LOGISTIC"
LEARNER_TREE = "L2_PAIRWISE_HIST_GB"
LEARNER_ENSEMBLE = "L3_LINEAR_TREE_ENSEMBLE"
LEARNERS = (LEARNER_LINEAR, LEARNER_TREE, LEARNER_ENSEMBLE)

#: The standalone learners have no ensemble weight; only the ensemble sweeps
#: ``ALPHA_GRID``.  That is what makes the candidate count 1 + 1 + 5 = 7.
ENSEMBLE_ONLY = LEARNER_ENSEMBLE

#: Fixed learner hyper-parameters.  They are declared here, once, so they are
#: visibly frozen rather than tuned per backbone or per block.
LINEAR_PARAMS = dict(C=1.0, max_iter=5000, solver="lbfgs")
TREE_PARAMS = dict(
    max_iter=200,
    learning_rate=0.06,
    max_leaf_nodes=15,
    min_samples_leaf=40,
    l2_regularization=1.0,
    early_stopping=False,
    random_state=101,
)

#: The weight that makes a pair matter: how much forecasting loss a wrong
#: preference costs.  Recorded so the loss can be recomputed.
PAIR_WEIGHT_RULE = "abs(L_a - L_b)"

#: A candidate whose KEEP rate is exactly 0 or 1 is not a selective method at
#: all.  Admission criterion R5; applied at selection time as well so a
#: degenerate candidate cannot win the gate by copying a strong reference.
KEEP_RATE_OPEN_INTERVAL = (0.0, 1.0)

#: -- stage 2 (plan §12, permitted exactly once) ----------------------------
#
# Stage 1 ranks actions by preference.  A preference is scale-free, so it says
# nothing about how much a wrong choice costs, and stage 1 duly bought its
# gains with a 42% harmful-intervention rate.  Stage 2 adds the two regret
# estimates back into the score, weighted by a simplex-constrained triple.

#: ``S_a = l1 * S_a^pair - l2 * r_a^ridge - l3 * r_a^tree`` with the three
#: weights non-negative and summing to one.  Coarse grid, step 0.25.
LAMBDA_STEP = 0.25

#: ``Ridge`` alpha for the first regret component.  Same value the v4.4 A5
#: control used, so the two are directly comparable.
RIDGE_PARAMS = dict(alpha=1.0)

#: The second regret component.  Identical to the v4.4 A5 CART control
#: (``methods.R2_CART_PARAMS``) so "r2 tree" means the same model as "A5 CART",
#: with the regression target changed from utility to regret and nothing else.
REGRET_TREE_PARAMS = dict(max_depth=3, min_samples_leaf=96, random_state=101)

#: The two regret components of the ensemble.
REGRET_RIDGE = "ridge"
REGRET_TREE = "tree"
REGRET_KINDS = (REGRET_RIDGE, REGRET_TREE)


def lambda_grid() -> list[tuple[float, float, float]]:
    """The 15 simplex points of step 0.25, in reporting order.

    ``(1, 0, 0)`` is stage 1 exactly, so the stage-2 search cannot lose to the
    configuration it is built on.
    """
    steps = [round(index * LAMBDA_STEP, 10) for index in
             range(int(round(1.0 / LAMBDA_STEP)) + 1)]
    out: list[tuple[float, float, float]] = []
    for first in steps:
        for second in steps:
            third = round(1.0 - first - second, 10)
            if -1e-9 <= third <= 1.0 + 1e-9:
                out.append((first, second, max(third, 0.0)))
    return out


def learner_configs() -> list[dict]:
    """The seven frozen model configurations, in reporting order."""
    configs = [
        {"config": LEARNER_LINEAR, "learner": LEARNER_LINEAR, "alpha": None},
        {"config": LEARNER_TREE, "learner": LEARNER_TREE, "alpha": None},
    ]
    for alpha in ALPHA_GRID:
        configs.append({"config": f"{LEARNER_ENSEMBLE}[a={alpha:g}]",
                        "learner": LEARNER_ENSEMBLE, "alpha": float(alpha)})
    return configs


def candidate_grid() -> list[dict]:
    """The 28 candidates: seven model configurations crossed with four taus."""
    return [{**config, "tau": float(tau)}
            for config in learner_configs() for tau in TAU_GRID]
