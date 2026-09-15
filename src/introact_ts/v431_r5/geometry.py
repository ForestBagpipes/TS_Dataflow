"""Label-free absolute-loss gain geometry; no prediction mixing is performed."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from time import perf_counter
import numpy as np


@dataclass
class ProjectionResult:
    scores: np.ndarray
    status: str
    converged: bool
    gap: float | None
    iterations: int
    elapsed_seconds: float
    objective: float | None
    timed_out: bool = False
    reason: str | None = None

    def to_dict(self):
        value = asdict(self)
        value['scores'] = self.scores.tolist()
        return value


def _validate(predictions, raw, scale, weights):
    p = np.asarray(predictions, dtype=np.float64)
    r = np.asarray(raw, dtype=np.float64)
    if p.ndim != 2 or min(p.shape) < 1 or r.shape != (p.shape[0],):
        raise ValueError('expected predictions K x H and raw K')
    if not np.isfinite(p).all() or not np.isfinite(r).all():
        raise ValueError('nonfinite predictions or scores')
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('scale must be positive and finite')
    if r[0] != 0:
        raise ValueError('reference score must be exactly zero')
    w = None if weights is None else np.asarray(weights, dtype=np.float64)
    if w is not None and (w.shape != (p.shape[1],) or not np.isfinite(w).all()
                          or (w < 0).any() or abs(w.sum() - 1) > 1e-12):
        raise ValueError('known weights must be nonnegative and sum to one')
    return p, r, w


def breakpoint_vectors(predictions, scale):
    """Return H x K_breakpoints x K_actions vectors (duplicates retained)."""
    p = np.asarray(predictions, dtype=np.float64)
    # axes: lead, candidate breakpoint, action
    distance = np.abs(p.T[:, :, None] - p.T[:, None, :])
    return (distance[:, :, :1] - distance) / scale


def distance_bounds(predictions, scale, weights=None):
    p = np.asarray(predictions, dtype=np.float64)
    distances = np.abs(p[:, None, :] - p[None, :, :]) / scale
    return distances.max(axis=2) if weights is None else distances @ weights


def _lmo(vertices, direction, weights):
    products = vertices @ direction
    if weights is None:
        return vertices.reshape(-1, vertices.shape[-1])[np.argmin(products)]
    selected = vertices[np.arange(len(vertices)), np.argmin(products, axis=1)]
    return weights @ selected


class _Timeout(Exception):
    pass


def project_scores(predictions, raw, scale, weights=None, mode='full', *,
                   max_iter=2048, tolerance=1e-8, time_limit_seconds=0.05,
                   previous_scores=None):
    """Project scores; timeout/failure returns previous scores and a failure status.

    `weights=None` means that the future scoring mask/weights are unknown.
    Nonconverged FW iterates remain feasible and have a recorded gap; timeout
    never returns a new decision. Caller must preserve its last valid action.
    """
    start = perf_counter()
    backup = np.asarray(raw if previous_scores is None else previous_scores,
                        dtype=np.float64).copy()
    def failure(reason, timed_out=False, iterations=0, gap=None):
        return ProjectionResult(backup, 'timeout' if timed_out else 'failed', False,
                                gap, iterations, perf_counter()-start, None,
                                timed_out, reason)
    def clock_check():
        if perf_counter() - start >= time_limit_seconds:
            raise _Timeout()
    iterations = 0
    gap = None
    try:
        p, r, w = _validate(predictions, raw, scale, weights)
        if backup.shape != r.shape:
            raise ValueError('previous_scores shape mismatch')
        if max_iter < 1 or tolerance < 0 or not np.isfinite(tolerance):
            raise ValueError('invalid iteration/tolerance parameters')
        if not np.isfinite(time_limit_seconds) or time_limit_seconds < 0:
            raise ValueError('time budget must be finite and nonnegative')
        clock_check()
        if mode == 'raw':
            return ProjectionResult(r.copy(), 'completed', True, 0., 0,
                                    perf_counter()-start, 0.)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            bounds = distance_bounds(p, scale, w)
        if not np.isfinite(bounds).all():
            raise FloatingPointError("nonfinite prediction distances")
        if mode == 'single':
            z = np.clip(r, -bounds[:, 0], bounds[:, 0]); z[0] = 0.
            clock_check()
            return ProjectionResult(z, 'completed', True, 0., 0,
                                    perf_counter()-start, float(.5*np.sum((z-r)**2)))
        if mode == 'pair':
            from scipy.optimize import minimize, linprog
            # Reference is eliminated: x contains actions 1..K-1 only.
            if len(r) == 1:
                return ProjectionResult(r.copy(), 'completed', True, 0., 0,
                                        perf_counter()-start, 0.)
            a, b = [], []
            for i in range(len(r)):
                for j in range(i):
                    row = np.zeros(len(r)); row[i] = 1; row[j] = -1
                    a.extend((row[1:], -row[1:])); b.extend((bounds[i,j], bounds[i,j]))
            a, b = np.asarray(a), np.asarray(b)
            def callback(_):
                clock_check()
            opt = minimize(lambda x: .5*np.sum((x-r[1:])**2), np.zeros(len(r)-1),
                           jac=lambda x: x-r[1:], method='SLSQP',
                           constraints={'type':'ineq', 'fun':lambda x:b-a@x,
                                        'jac':lambda x:-a}, callback=callback,
                           options={'maxiter':max_iter, 'ftol':min(1e-12,tolerance or 1e-12)})
            clock_check()
            if not opt.success or np.max(a@opt.x-b) > 1e-8:
                return failure('pair QP failed: '+opt.message, iterations=opt.nit)
            gradient = opt.x-r[1:]
            lp = linprog(gradient, A_ub=a, b_ub=b, bounds=[(None,None)]*len(gradient),
                         method='highs', options={'time_limit':max(1e-6,time_limit_seconds-(perf_counter()-start))})
            clock_check()
            if not lp.success:
                return failure('pair gap LP failed: '+lp.message, iterations=opt.nit)
            gap = max(0.,float(gradient@(opt.x-lp.x)))
            z = np.r_[0.,opt.x]
            return ProjectionResult(z, 'completed' if gap<=tolerance else 'iteration_limit',
                                    gap<=tolerance, gap, opt.nit, perf_counter()-start,
                                    float(.5*np.sum((z-r)**2)))
        if mode != 'full':
            raise ValueError('unknown mode')
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            vertices = breakpoint_vectors(p, scale)
        if not np.isfinite(vertices).all():
            raise FloatingPointError("nonfinite breakpoint vertices")
        z = np.zeros_like(r)
        gap = None
        iterations = 0
        for _ in range(max_iter):
            clock_check()
            gradient = z-r
            s = _lmo(vertices, gradient, w)
            gap = max(0., float(gradient@(z-s)))
            if gap <= tolerance:
                break
            direction = s-z
            norm2 = float(direction@direction)
            if norm2 <= 0:
                return failure('positive gap with zero direction', iterations=iterations, gap=gap)
            z += np.clip(gap/norm2, 0., 1.)*direction
            z[0] = 0.
            iterations += 1
        # Gap must refer to the returned final iterate, not its predecessor.
        gradient = z-r
        gap = max(0., float(gradient@(z-_lmo(vertices, gradient, w))))
        clock_check()
        if not np.isfinite(z).all() or not np.isfinite(gap):
            return failure('nonfinite solver output', iterations=iterations)
        return ProjectionResult(z, 'completed' if gap<=tolerance else 'iteration_limit',
                                gap<=tolerance, gap, iterations, perf_counter()-start,
                                float(.5*np.sum((z-r)**2)))
    except _Timeout:
        return failure('solver time budget exhausted', timed_out=True, iterations=iterations, gap=gap)
    except (ValueError, FloatingPointError, OverflowError) as exc:
        return failure(str(exc))
