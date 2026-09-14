"""Explicit A4/A5 deployment behavior; no future/evaluation imports."""
from itertools import combinations
import numpy as np
from .candidates import UnsupportedResidual, _fit_predict, freeze_blocks, residual_correct
from .schemas import Candidate, array_hash, require, verify_impute


def ridge_candidate(episode, *, history=None, min_rows=32, max_features=8, alpha=1.0):
    missing = np.isnan(episode.target)
    arm = "A4_RIDGE_FULL" if history is not None else "A4_RIDGE_CONTEXT"
    if not missing.any():
        return Candidate(episode.uid, arm, episode.target), dict(status="not_needed", fit_rows=0)
    z = episode.covariates
    if z.shape[1] == 0 or np.isfinite(z[missing]).mean() < .5:
        return Candidate(episode.uid, arm, episode.target), dict(status="unsupported", fallback="A0_NATIVE", reason="insufficient gap covariates")
    y, train = (episode.target, z) if history is None else history
    require(train.ndim == 2 and train.shape == (len(y), z.shape[1]), "history geometry mismatch")
    try:
        pred = _fit_predict(train, y, z[missing], min_rows, max_features, alpha)
    except UnsupportedResidual as exc:
        return Candidate(episode.uid, arm, episode.target), dict(status="unsupported", fallback="A0_NATIVE", reason=str(exc))
    require(np.isfinite(pred).all(), "ridge produced nonfinite output")
    x = episode.target.copy()
    x[missing] = pred
    result = Candidate(episode.uid, arm, x)
    verify_impute(episode, result)
    return result, dict(status="completed", fit_rows=int(np.isfinite(y).sum()))


def residual_plan(episode, length=51, seed=101):
    x, z = episode.target, episode.covariates
    if not np.isnan(x).any():
        return None, {}, "no missing target"
    if z.shape[1] == 0 or np.isfinite(z[np.isnan(x)]).mean() < .5:
        return None, {}, "insufficient gap covariates"
    try:
        blocks = freeze_blocks(x, length, seed)
    except UnsupportedResidual as exc:
        return None, {}, str(exc)
    views = {array_hash(x): x.copy()}
    for indices in [*(combinations(range(3), 1)), *(combinations(range(3), 2))]:
        view = x.copy()
        for i in indices:
            view[blocks[i]] = np.nan
        views[array_hash(view)] = view
    require(len(views) == 7, "nested input plan must contain seven distinct masks")
    return blocks, views, None


def static_residual(episode, base, blocks, predictions, reason=None, **kwargs):
    verify_impute(episode, base)
    require(np.isfinite(base.target).all(), "A2 base failure")
    if blocks is None:
        return Candidate(episode.uid, "A5_STATIC", base.target), dict(status="unsupported" if np.isnan(episode.target).any() else "not_needed", fallback="A2_SINGLE", reason=reason)
    def imputer(view):
        key = array_hash(view)
        require(key in predictions, "missing real nested worker output")
        return predictions[key].copy()
    candidate, evidence = residual_correct(episode, imputer, blocks, **kwargs)
    if not candidate.applicable:
        return Candidate(episode.uid, "A5_STATIC", base.target), dict(status="unsupported", fallback="A2_SINGLE", reason=candidate.reason)
    return Candidate(episode.uid, "A5_STATIC", candidate.target), dict(status="completed", **evidence)
