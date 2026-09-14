from dataclasses import replace
import numpy as np
import pytest
from introact_ts.v43.candidates import freeze_blocks, outer_prediction, residual_correct
from introact_ts.v43.schemas import ContractError, array_hash, verify_impute


def mean_imputer(x):
    return np.full_like(x, np.nanmean(x))


def test_outer_poison_masks_base_model_indirect_path(episode):
    blocks = freeze_blocks(episode.target, 16)
    for k, bk in enumerate(blocks):
        before = outer_prediction(episode.target, episode.covariates, blocks, k, mean_imputer)
        poisoned = episode.target.copy()
        poisoned[bk] += 1e10
        after = outer_prediction(poisoned, episode.covariates, blocks, k, mean_imputer)
        assert [array_hash(a) for a in before] == [array_hash(a) for a in after]
        # The stub is deliberately sensitive: an unmasked base call changes.
        assert array_hash(mean_imputer(poisoned)) != array_hash(mean_imputer(episode.target))


def test_residual_finite_values_and_static_eta(episode):
    blocks = freeze_blocks(episode.target, 16)
    c, evidence = residual_correct(episode, mean_imputer, blocks)
    verify_impute(episode, c)
    assert c.applicable and np.isfinite(c.target).all()
    assert evidence["eta"] in (0., .5, 1.)
    assert evidence["unique_base_inputs"] == 7
    assert evidence["eta"] == (0., .5, 1.)[np.argmin(np.mean(evidence["outer_mae"], axis=0))]


def test_insufficient_support_is_explicit_but_backend_failure_raises(episode):
    blocks = freeze_blocks(episode.target, 8)
    c, evidence = residual_correct(episode, mean_imputer, blocks)
    assert not c.applicable and c.reason and evidence is None
    with pytest.raises(ContractError, match="imputer failed"):
        residual_correct(episode, lambda x: np.zeros(2), freeze_blocks(episode.target, 16))
    no_z = replace(episode, covariates=np.full_like(episode.covariates, np.nan))
    c, _ = residual_correct(no_z, mean_imputer, blocks)
    assert not c.applicable


def test_feature_cap_includes_missing_indicators(monkeypatch):
    from introact_ts.v43.candidates import _fit_predict, Ridge
    rng = np.random.default_rng(101)
    z = rng.normal(size=(64, 40))
    z[::3, ::2] = np.nan
    seen = []
    original_fit = Ridge.fit
    def fit(self, x, y, *args, **kwargs):
        seen.append(x.shape[1])
        return original_fit(self, x, y, *args, **kwargs)
    monkeypatch.setattr(Ridge, "fit", fit)
    p = _fit_predict(z, rng.normal(size=64), z[:4], 32, 8, 1.)
    assert seen == [8] and p.shape == (4,) and np.isfinite(p).all()
