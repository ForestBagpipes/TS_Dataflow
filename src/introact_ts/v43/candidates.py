"""Context-only imputation and strict nested residual validation."""
import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from .schemas import Candidate, array_hash, require, verify_impute


def prepare_model_input(target, *, native_nan):
    x = np.array(target, copy=True)
    require(x.ndim == 1 and not np.isinf(x).any(), "invalid model input")
    if native_nan or np.isfinite(x).all():
        return x
    valid = np.flatnonzero(np.isfinite(x))
    require(len(valid) > 0, "fixed forward-fill unsupported for all-missing input")
    # Shared legacy rule: leading values use first observation, then forward fill.
    x[:valid[0]] = x[valid[0]]
    for i in range(valid[0]+1, len(x)):
        if np.isnan(x[i]):
            x[i] = x[i-1]
    return x


def generate_base(episode):
    """Only currently implemented cheap proposals; no fake TSICL/PICS arms."""
    x = episode.target.copy()
    missing = np.isnan(x)
    boundaries = np.flatnonzero(np.diff(np.r_[False, missing, False]))
    for lo, hi in zip(boundaries[::2], boundaries[1::2]):
        if hi-lo <= 3 and lo > 0 and hi < len(x):
            x[lo:hi] = np.linspace(x[lo-1], x[hi], hi-lo+2)[1:-1]
    result = [Candidate(episode.uid, "KEEP", episode.target),
              Candidate(episode.uid, "FACT_SHORT", x)]
    for c in result:
        verify_impute(episode, c)
    return result


def resolve_candidate(episode, candidate):
    require(candidate.episode_uid == episode.uid, "candidate identity mismatch")
    return candidate if candidate.applicable else Candidate(episode.uid, "KEEP", episode.target)


class UnsupportedResidual(ValueError):
    pass


def _fit_predict(z_train, y_train, z_query, min_rows, max_features, alpha):
    valid = np.isfinite(y_train)
    z_train, y_train = z_train[valid], y_train[valid]
    if len(y_train) < min_rows or z_train.shape[1] == 0:
        raise UnsupportedResidual("insufficient residual support")
    columns = np.any(np.isfinite(z_train), axis=0)
    if not columns.any():
        raise UnsupportedResidual("no supported covariates")
    train, query = z_train[:, columns], z_query[:, columns]
    med = np.nanmedian(train, axis=0)
    train_missing, query_missing = np.isnan(train), np.isnan(query)
    train, query = np.where(train_missing, med, train), np.where(query_missing, med, query)
    supported_channels = train.shape[1]
    # The dimension cap covers missing indicators as well as filled values.
    train = np.column_stack((train, train_missing))
    query = np.column_stack((query, query_missing))
    scaler = StandardScaler().fit(train)
    train, query = scaler.transform(train), scaler.transform(query)
    if train.shape[1] > max_features:
        dim = min(max_features, supported_channels, len(train)//8)
        if dim < 1:
            raise UnsupportedResidual("insufficient PCA support")
        pca = PCA(n_components=dim, svd_solver="full").fit(train)
        train, query = pca.transform(train), pca.transform(query)
    return Ridge(alpha=alpha).fit(train, y_train).predict(query)


def freeze_blocks(target, length, seed=101):
    """Select using only finite masks, time positions and the fixed seed."""
    require(length > 0, "invalid block length")
    finite = np.isfinite(target)
    starts = np.arange(0, len(target)-length+1, length)
    starts = starts[[finite[s:s+length].all() for s in starts]]
    if len(starts) < 3:
        raise UnsupportedResidual("fewer than three observed blocks")
    chosen = np.random.default_rng(seed).choice(starts, size=3, replace=False)
    return tuple((np.arange(len(target)) >= s) & (np.arange(len(target)) < s+length)
                 for s in sorted(chosen))


def _validate_blocks(x, blocks):
    require(len(blocks) == 3, "three blocks required")
    used = np.zeros(len(x), dtype=bool)
    for b in blocks:
        require(b.dtype == bool and b.shape == x.shape and b.any(), "invalid block mask")
        require(not (used & b).any() and np.isfinite(x[b]).all(), "overlap/missing in pseudo block")
        require(np.all(np.diff(np.flatnonzero(b)) == 1), "pseudo block not contiguous")
        used |= b


def outer_prediction(target, covariates, blocks, outer, imputer, *, min_rows=32,
                     max_features=8, alpha=1.0):
    """Return frozen base/delta, without reading outer truth for scoring.

    imputer is a context-array callable. Production must bind a real worker;
    tests deliberately use a global-mean stub sensitive to forbidden values.
    """
    x, z = np.asarray(target), np.asarray(covariates)
    _validate_blocks(x, blocks)
    require(outer in range(3) and z.ndim == 2 and len(z) == len(x), "invalid outer input")
    missing, bk = np.isnan(x), blocks[outer]

    def base(mask):
        view = x.copy()
        view[mask] = np.nan
        prediction = np.asarray(imputer(view))
        require(prediction.shape == x.shape and np.isfinite(prediction[mask]).all(), "imputer failed")
        return prediction

    residuals, features = [], []
    for i, bi in enumerate(blocks):
        if i != outer:
            p = base(missing | bk | bi)
            residuals.append(x[bi]-p[bi])
            features.append(z[bi])
    delta = _fit_predict(np.concatenate(features), np.concatenate(residuals), z[bk],
                         min_rows, max_features, alpha)
    return base(missing | bk)[bk].copy(), delta.copy()


def residual_correct(episode, imputer, blocks, *, min_rows=32, max_features=8, alpha=1.0):
    x, z = episode.target, episode.covariates
    _validate_blocks(x, blocks)
    missing = np.isnan(x)
    if not missing.any() or z.shape[1] == 0 or np.isfinite(z[missing]).mean() < .5:
        return Candidate(episode.uid, "RESIDUAL", x, False, "insufficient gap covariates"), None
    # Invocation-local memoization: one fixed adapter/config, at most seven
    # distinct masked inputs. Persistent cross-run keys belong to the protocol.
    cache = {}
    backend = imputer
    def imputer(view):
        key = array_hash(view)
        if key not in cache:
            pred = np.asarray(backend(view.copy()))
            require(pred.shape == x.shape and np.isfinite(pred[np.isnan(view)]).all(), "imputer failed")
            cache[key] = pred.copy()
        return cache[key].copy()
    try:
        evidence = []
        for k, bk in enumerate(blocks):
            base, delta = outer_prediction(x, z, blocks, k, imputer, min_rows=min_rows,
                                           max_features=max_features, alpha=alpha)
            # Only now open the observed outer block for evidence scoring.
            evidence.append([float(np.mean(abs(base+eta*delta-x[bk]))) for eta in (0., .5, 1.)])
        losses = np.mean(evidence, axis=0)
        eta = (0., .5, 1.)[int(np.argmin(losses))]
        rows, features = [], []
        for bi in blocks:
            view = x.copy()
            view[missing | bi] = np.nan
            pred = np.asarray(imputer(view))
            require(pred.shape == x.shape and np.isfinite(pred[missing | bi]).all(), "imputer failed")
            rows.append(x[bi]-pred[bi])
            features.append(z[bi])
        delta = _fit_predict(np.concatenate(features), np.concatenate(rows), z[missing],
                             min_rows, max_features, alpha)
        base = np.asarray(imputer(x.copy()))
        require(base.shape == x.shape and np.isfinite(base[missing]).all(), "imputer failed")
        output = x.copy()
        output[missing] = base[missing]+eta*delta
        c = Candidate(episode.uid, "RESIDUAL", output)
        verify_impute(episode, c)
        return c, {"eta": eta, "outer_mae": evidence, "unique_base_inputs": len(cache)}
    except UnsupportedResidual as exc:
        return Candidate(episode.uid, "RESIDUAL", x, False, str(exc)), None
