"""Dual verification of a candidate intervention.

An action is committed only if all three conditions hold simultaneously:

    Accept(a) = 1[ dU(a) > eps  AND  D_struct(x, a(x)) < tau  AND  R(a) < eta ]

The utility term alone is not enough, and this is the crux of the method: an
over-aggressive smoother reliably lowers forecast error while destroying the
peaks and regime structure that made the window informative. The structural
term vetoes exactly those edits. The risk term vetoes edits the agent cannot
justify -- low-confidence hypotheses, expensive rewrites, or gains that rest on
a single behavioural dimension rather than a broad improvement.

The two ``require_*`` switches exist so ablations can disable structural
verification or post-hoc re-probing without touching the agent loop.
"""

from dataclasses import dataclass

import numpy as np

from .types import Verdict


@dataclass
class VerifyConfig:
    epsilon: float = 0.005
    tau: float = 0.12
    eta: float = 0.62
    require_structure: bool = True
    require_reprobe: bool = True
    require_risk: bool = True


def improvement_consistency(z_before: np.ndarray, z_after: np.ndarray) -> float:
    """Fraction of behaviour dimensions that moved in the right direction.

    A genuine repair shows up across many signals at once. A gain concentrated
    in one dimension -- typically forecast error, the one an over-smoother can
    game -- is treated as weak evidence.
    """
    z_before = np.asarray(z_before, dtype=np.float64)
    z_after = np.asarray(z_after, dtype=np.float64)
    if z_before.size == 0:
        return 0.5
    moved = z_after < z_before - 1e-9
    unchanged = np.abs(z_after - z_before) <= 1e-9
    n_eff = max(int(np.sum(~unchanged)), 1)
    return float(np.sum(moved) / n_eff)


def improvement_depth(z_before: np.ndarray, z_after: np.ndarray) -> float:
    """How far the improved dimensions actually moved, in [0, 1].

    Companion to :func:`improvement_consistency`, which counts how many
    dimensions moved the right way but not by how much. A broad but negligible
    improvement and a broad decisive one are indistinguishable to breadth
    alone, and only the second is evidence that the edit worked.

    The median is over improved dimensions only, in calibrated z units, so one
    dimension collapsing does not carry the score.
    """
    z_before = np.asarray(z_before, dtype=np.float64)
    z_after = np.asarray(z_after, dtype=np.float64)
    if z_before.size == 0:
        return 0.5
    gains = z_before - z_after
    improved = gains[gains > 1e-9]
    if improved.size == 0:
        return 0.0
    # One z unit of median improvement is already a decisive edit, so that is
    # where this saturates.
    return float(np.clip(float(np.median(improved)), 0.0, 1.0))


def action_risk(
    success_depth: float,
    cost: float,
    consistency: float,
) -> float:
    """Decision risk R(a) in [0, 1]. Lower means safer to commit.

    The first term used to be the hypothesis posterior, and that was wrong on
    a measurable basis rather than a stylistic one. The posterior answers which
    kind of window this is, not whether this edit succeeded, and the two are
    anti correlated in practice: on the 2000 window run the most confident
    tenth of windows received a wrong edit 59.5 percent of the time against
    48.4 percent overall. Conditioning the risk of acting on it made the agent
    boldest exactly where it was least reliable.

    All three terms now describe the edit under consideration. Depth is how far
    the behavioural evidence moved, breadth is how many dimensions moved, cost
    is what the operator charged. The weights are unchanged so the substitution
    is the only difference from the previous rule.
    """
    depth_term = 1.0 - float(np.clip(success_depth, 0.0, 1.0))
    cost_term = float(np.clip(cost, 0.0, 1.0))
    cons_term = 1.0 - float(np.clip(consistency, 0.0, 1.0))
    return float(np.clip(0.45 * depth_term + 0.25 * cost_term + 0.30 * cons_term, 0.0, 1.0))


def verify(
    delta_utility: float,
    struct_distortion: float,
    risk: float,
    cfg: VerifyConfig = None,
) -> Verdict:
    """Apply the acceptance rule and report which condition failed, if any."""
    cfg = cfg or VerifyConfig()

    if cfg.require_reprobe and not (delta_utility > cfg.epsilon):
        return Verdict.ROLLED_BACK_UTILITY
    if cfg.require_structure and not (struct_distortion < cfg.tau):
        return Verdict.ROLLED_BACK_STRUCTURE
    if cfg.require_risk and not (risk < cfg.eta):
        return Verdict.ROLLED_BACK_RISK
    return Verdict.ACCEPTED
