"""Distribution free calibration of the structural threshold.

The threshold tau was set by hand, and the honest statement in
`docs/ablation_ladder.md` was that a sweep showed 0.12 sits off the efficient
frontier while declining to move it, because choosing a value after seeing the
failure it prevents is tuning against the test corpus. Selecting on a held out
seed fixed the methodology but still yields a number with no guarantee attached.

This replaces the number with a procedure that carries one. Given a calibration
corpus and a target level alpha, it returns a threshold for which the expected
fraction of windows the system damages is at most alpha, with a finite sample
guarantee that assumes only exchangeability between calibration and deployment
data and nothing about the distribution.

The risk function, fixed here so it cannot be adjusted after seeing results:

    L_i(lambda) = 1 if window i comes out worse than it went in, else 0

measured as normalised mean squared error against the pristine series, with a
tolerance of 1e-9. It is bounded in [0, 1] by construction, which is what the
guarantee requires, and it is monotone in lambda because a larger structural
budget admits a superset of the edits a smaller one admits. Monotonicity is
what lets a single threshold family be calibrated without a multiplicity
correction, and it is verified empirically rather than assumed, see
`check_monotone`.

Note on what is guaranteed. The bound is on the fraction of *windows* damaged
across the corpus, not on the fraction of *committed edits* that are harmful.
The two differ whenever a method edits only part of the corpus, and the first
is the quantity a curation user cares about, since it is the share of their
data that got worse.

Reference: conformal risk control, which extends split conformal prediction
from coverage of a set to the expectation of any bounded monotone loss.
"""

from dataclasses import dataclass

import numpy as np

#: Upper bound of the loss. A zero one loss, so exactly 1.
LOSS_BOUND = 1.0


@dataclass
class ConformalThreshold:
    """The calibrated threshold and the evidence behind it."""

    lambda_star: float
    alpha: float
    n_calibration: int
    empirical_risk: float
    #: The corrected risk that had to clear alpha, (n * R + B) / (n + 1).
    corrected_risk: float
    grid: tuple
    risk_curve: tuple
    monotone: bool


def risk_curve(losses_by_lambda: dict) -> tuple:
    """Empirical risk at each threshold, sorted by threshold ascending.

    ``losses_by_lambda`` maps a threshold to a per window 0/1 loss array. All
    arrays must cover the same windows in the same order.
    """
    grid = tuple(sorted(losses_by_lambda))
    curve = tuple(float(np.mean(losses_by_lambda[g])) for g in grid)
    return grid, curve


def check_monotone(curve: tuple, tol: float = 1e-12) -> bool:
    """Is the empirical risk non decreasing in the threshold?

    Reported rather than enforced. A violation does not invalidate the bound on
    its own, since the guarantee is driven by the corrected empirical risk, but
    it means the threshold family is not nested the way the derivation assumes
    and that has to be visible.
    """
    return all(b >= a - tol for a, b in zip(curve[:-1], curve[1:]))


def calibrate(losses_by_lambda: dict, alpha: float) -> ConformalThreshold:
    """Largest threshold whose corrected empirical risk clears alpha.

    The correction is the finite sample term from conformal risk control:

        (n * R_hat(lambda) + B) / (n + 1) <= alpha

    with B the loss bound. It is what turns an empirical average over n
    calibration points into a bound on the expectation at a fresh point. With
    no admissible threshold the most conservative one in the grid is returned,
    since refusing to act is always available and always safe.
    """
    grid, curve = risk_curve(losses_by_lambda)
    n = len(next(iter(losses_by_lambda.values())))
    admissible = [
        (g, r) for g, r in zip(grid, curve)
        if (n * r + LOSS_BOUND) / (n + 1) <= alpha
    ]
    if admissible:
        g_star, r_star = admissible[-1]
    else:
        g_star, r_star = grid[0], curve[0]
    return ConformalThreshold(
        lambda_star=float(g_star),
        alpha=float(alpha),
        n_calibration=int(n),
        empirical_risk=float(r_star),
        corrected_risk=float((n * r_star + LOSS_BOUND) / (n + 1)),
        grid=grid,
        risk_curve=curve,
        monotone=check_monotone(curve),
    )


def damage_loss(nmse_before: np.ndarray, nmse_after: np.ndarray,
                discard_share=None, tol: float = 1e-9) -> np.ndarray:
    """The fixed loss: one per window that came out worse than it went in.

    **Discarding data is damage and this had to be written in explicitly.** The
    distance comparison alone cannot see a crop: a protected window's clean
    reference is the window itself, so cropping it leaves the surviving span
    point wise correct and the distance unchanged. Measured on seed 0, 66 crops
    committed inside protected strata discarded a median 40 percent of their
    window and every one of them scored zero damage.

    That is the same blind spot `structure._discard_distortion` fixes for the
    structural condition, and it is fixed the same way here so that the shield,
    the loss and the calibration all mean one thing by damage. Without it a per
    family calibration would hand the cropping family a loose threshold on the
    evidence that cropping never hurts.

    ``discard_share`` is the fraction of the window's variation that was thrown
    away, in [0, 1], which keeps the loss bounded as conformal risk control
    requires. A window that was not cropped passes zero and is judged exactly as
    before.
    """
    a = np.asarray(nmse_after, dtype=np.float64)
    b = np.asarray(nmse_before, dtype=np.float64)
    worse = (a > b + tol).astype(np.float64)
    if discard_share is None:
        return worse
    d = np.clip(np.asarray(discard_share, dtype=np.float64), 0.0, 1.0)
    return np.maximum(worse, d)


# -- fallback for a non monotone risk curve ---------------------------------
#
# The single parameter calibration above assumes the thresholds form a nested
# family, which shows up empirically as a monotone risk curve. When that fails,
# selecting the largest admissible threshold is no longer justified by the
# derivation and a multiplicity correction is required.
#
# Fixed sequence testing is the right correction here rather than Bonferroni.
# The thresholds are ordered by construction, so the family of hypotheses
#
#     H_lambda : R(lambda) > alpha
#
# can be tested from the most conservative threshold upward, stopping at the
# first one that cannot be rejected. That controls the family wise error rate
# at level delta without splitting it across the grid, which Bonferroni would
# do and which costs power in proportion to the grid size. It also does not
# require monotonicity: it only requires that the ordering be fixed in advance,
# which it is.


def bentkus_p_value(risk_hat: float, alpha: float, n: int) -> float:
    """p value for H: R > alpha, from Bentkus' inequality for a bounded loss.

    Valid for any loss in [0, 1] with no distributional assumption. Returns 1
    when the empirical risk is at or above alpha, since there is then no
    evidence against the hypothesis.
    """
    from scipy.stats import binom

    if not np.isfinite(risk_hat) or risk_hat >= alpha:
        return 1.0
    k = int(np.ceil(n * risk_hat))
    return float(min(1.0, np.e * binom.cdf(k, n, alpha)))


def fixed_sequence_select(losses_by_lambda: dict, alpha: float,
                          delta: float = 0.05) -> dict:
    """Largest threshold reachable by testing the ordered family in sequence.

    Walks the thresholds from most to least conservative, testing each at level
    delta, and stops at the first one it cannot reject. The last rejected
    threshold is returned. If none is rejected the most conservative threshold
    in the grid is returned, since declining to act is always available.
    """
    grid = tuple(sorted(losses_by_lambda))
    n = len(next(iter(losses_by_lambda.values())))
    selected, tested = grid[0], []
    for g in grid:
        r = float(np.mean(losses_by_lambda[g]))
        p = bentkus_p_value(r, alpha, n)
        tested.append({"lambda": float(g), "risk": r, "p": p,
                       "rejected": bool(p <= delta)})
        if p <= delta:
            selected = g
        else:
            break
    return {"lambda_star": float(selected), "alpha": float(alpha),
            "delta": float(delta), "n": int(n), "tested": tested,
            "method": "fixed sequence testing with Bentkus p values"}
