from dataclasses import replace
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.schemas import Episode, ContractError, array_hash
from introact_ts.v431_r3.probe import registered_specs, prepare_probe, score_probe, paired_response, proxy_mismatch, PSI_NAMES, canonical_view_hash


def episode(h=96, gap=(230, 281), shared=False):
    t = np.arange(512, dtype=np.int64)
    x = np.arange(512, dtype=float)
    z = np.c_[x + 5., 2 * x]
    if gap:
        x[slice(*gap)] = np.nan
        if shared:
            z[slice(*gap)] = np.nan
    return Episode('u', 'source', 'panel', 'parent', 'train', 0, 704, 1216, h,
                   t, x, z, np.repeat(t[:, None], 3, axis=1))


def test_fixed_mask_lags_same_endpoint_and_actual_short_input():
    e = episode(shared=True);spec = registered_specs(96)
    long, short = [prepare_probe(e, spec[k], 7.) for k in ('long', 'short')]
    assert long.status == short.status == 'prepared'
    assert len(long.view.target) == 416 and len(short.view.target) == 352
    np.testing.assert_array_equal(np.flatnonzero(long.copied_mask[:, 0]), np.arange(134, 185))
    np.testing.assert_array_equal(np.flatnonzero(short.copied_mask[:, 0]), np.arange(70, 121))
    assert long.view.context_end == short.view.context_end == 1120
    assert short.view.raw_start == 768
    np.testing.assert_array_equal(long.view.target[64:], short.view.target)
    np.testing.assert_array_equal(long.view.covariates[64:], short.view.covariates)
    np.testing.assert_array_equal(long.validation, short.validation)
    np.testing.assert_array_equal(long.scoring_mask, short.scoring_mask)
    assert long.input_hash != short.input_hash
    assert np.isnan(long.view.target[230:281]).all()  # original dirty gap remains
    assert np.isnan(long.view.target[134:185]).all()  # no clean value used


def test_H192_short_gap_outside_is_explicit_no_movement():
    e = episode(192);spec = registered_specs(192)
    assert prepare_probe(e, spec['long'], 3.).status == 'prepared'
    for name in ('short', 'second'):
        p = prepare_probe(e, spec[name], 3.)
        assert p.status == 'unsupported' and p.view is None
        assert p.reason == 'copied_current_gap_outside_probe_prefix'
    assert prepare_probe(episode(192, (358, 409)), spec['short'], 3.).status == 'prepared'


def test_asof_covariates_and_original_time_are_preserved():
    e = episode();a = e.availability.copy();a[190, 1] = 500
    e = replace(e, availability=a)
    p = prepare_probe(e, registered_specs(96)['long'], 3.)
    assert np.isnan(p.view.covariates[190, 0])
    assert np.isfinite(e.covariates[190, 0])
    np.testing.assert_array_equal(p.view.timestamps, e.timestamps[:416])
    assert array_hash(e.target) == array_hash(episode().target)


def test_validation_enforces_current_publication_time_and_half_coverage():
    e = episode(gap=None)
    # Exercise the defensive scoring boundary against an invalid archived
    # snapshot: Episode normally rejects these finite unpublished values itself.
    a = e.availability.copy();a[416:465, 0] = 700
    object.__setattr__(e, 'availability', a)
    p = prepare_probe(e, registered_specs(96)['long'], 2.)
    assert p.scoring_mask.sum() == 47
    assert p.status == 'unsupported' and p.reason == 'insufficient_currently_observed_historical_validation'
    a[464, 0] = 464
    q = prepare_probe(e, registered_specs(96)['long'], 2.)
    assert q.scoring_mask.sum() == 48 and q.status == 'prepared'


def test_task_scale_reference_signed_response_and_no_missing_zero():
    e = episode();spec = registered_specs(96)
    long, short = [prepare_probe(e, spec[k], 10.) for k in ('long', 'short')]
    results = []
    for p, offset in ((long, 1.), (short, 2.)):
        pred = {a: p.validation + (0. if a == 'A2_SINGLE' else offset) for a in POOL}
        results.append(score_probe(p, 'bolt', pred, 'frozenmodel', {'charges': [], 'total_seconds': 0.}, reference_arm='A2_SINGLE'))
    response = paired_response(*results)
    assert response['kappa']['A2_SINGLE'] == 0.
    assert response['kappa']['A0_NATIVE'] == pytest.approx(.1)
    assert response['z']['A0_NATIVE'] == pytest.approx(.15)
    assert 'future' not in results[0].to_dict() and results[0].current_scale == 10.
    with pytest.raises(ContractError, match='model_identity'):
        paired_response(results[0], replace(results[1], model_identity_hash='stale'))
    with pytest.raises(ContractError, match='five-arm'):
        score_probe(long, 'bolt', {}, 'm', {'charges': [], 'total_seconds': 0.}, reference_arm='A2_SINGLE')
    with pytest.raises(ContractError, match='positive'):
        prepare_probe(e, spec['long'], 0.)


def test_psi_only_visible_inputs_and_frozen_names():
    e = episode();p = prepare_probe(e, registered_specs(96)['short'], 4.)
    psi = proxy_mismatch(e, p.view, 4.)
    assert tuple(psi) == PSI_NAMES and all(np.isfinite(list(psi.values())))
    assert psi['length_horizon_ratio_difference'] == pytest.approx((352 - 512) / 96)
    assert len(p.view.target) < len(e.target)


def test_cache_requires_exact_identity_and_content(tmp_path):
    spec = importlib.util.spec_from_file_location('r3collect', Path('scripts/v431_r3_collect.py'))
    mod = importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    values = {a: np.arange(5, dtype=float) for a in POOL};path = tmp_path / 'cache.json'
    assert mod.cache_read(path, {'model': 'a'}) is None
    mod.cache_write(path, {'model': 'a'}, values, {})
    record, restored = mod.cache_read(path, {'model': 'a'})
    np.testing.assert_array_equal(restored['A0_NATIVE'], values['A0_NATIVE'])
    with pytest.raises(ContractError, match='identity'):
        mod.cache_read(path, {'model': 'b'})
    Path(record['array_path']).write_bytes(b'corrupt')
    with pytest.raises(ContractError, match='artifact'):
        mod.cache_read(path, {'model': 'a'})


def test_same_H32_actual_input_reused_across_current_horizon_lineage():
    a = episode(96);b = replace(episode(192), uid='second-current-uid')
    pa = prepare_probe(a, registered_specs(96)['h32'], 3.)
    pb = prepare_probe(b, registered_specs(192)['h32'], 3.)
    assert pa.input_hash != pb.input_hash
    assert canonical_view_hash(pa.view) == canonical_view_hash(pb.view)
    changed = replace(pb.view, target=pb.view.target + 1.)
    assert canonical_view_hash(pa.view) != canonical_view_hash(changed)


def test_collector_deduplicates_real_payloads_and_resumes_without_services(tmp_path, monkeypatch):
    """Contract test only: fake workers count calls, never produce an experiment."""
    import json
    import sys
    import types
    spec = importlib.util.spec_from_file_location('r3collect_unit', Path('scripts/v431_r3_collect.py'))
    mod = importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    out = tmp_path / 'main';out.mkdir();(out / 'views').mkdir()
    episodes = {'u': episode(96), 'v': replace(episode(192), uid='v')}
    meta = {u: dict(source=e.source, parent_group=e.parent_group, split='train', raw_start=e.raw_start,
                    context_end=e.context_end, horizon=e.horizon) for u, e in episodes.items()}
    mod.archive(out / 'contexts.npz', {u + '_' + k: getattr(e, k) for u, e in episodes.items() for k in mod.FIELDS})
    mod.atomic_json(out / 'episode_manifest.json', meta);mod.atomic_json(out / 'mase_scales.json', {'source': 3.})
    rows = []
    for u, e in episodes.items():
        p = prepare_probe(e, registered_specs(e.horizon)['h32'], 3.)
        path = out / 'views' / (u + '.npz');mod.archive(path, {'target': p.view.target})
        rows.append(dict(p.metadata(), split='train', source='source', parent_group='parent', v431_role='T_fit',
                         generalization_only=False, array_path=str(path), array_sha256=mod.file_hash(path),
                         cache_input_hash=canonical_view_hash(p.view), preparation_seconds=.01,
                         psi=proxy_mismatch(e, p.view, 3.), current_descriptor={}, probe_descriptor={}))
    mod.atomic_json(out / 'probe_manifest.json', rows)
    monkeypatch.setattr(mod, 'producer_identity', lambda: {'unit': 'fixture'})
    mod.atomic_json(out / 'preparation.json', {'producer_sources': {'unit': 'fixture'},
        'files': {n: mod.file_hash(out / n) for n in ('contexts.npz', 'episode_manifest.json', 'mase_scales.json', 'probe_manifest.json')}})
    old = tmp_path / 'old';old.mkdir();(old / 'resolved_config.yaml').write_text('seed: 101\n')
    mod.atomic_json(old / 'model_manifest.json', {'models': {'tsicl': {'revision': 'unit'}, 'bolt': {'revision': 'unit'}}})
    monkeypatch.setattr(mod, 'OLD', old);monkeypatch.setattr(mod, 'code_manifest', lambda: {'hash': 'unit'})
    real_read = mod.read
    monkeypatch.setattr(mod, 'read', lambda p: {'families': {'bolt': {'arm': 'A2_SINGLE'}}}
                        if str(p).endswith('reference_manifest.json') else real_read(p))
    monkeypatch.setattr(sys, 'addaudithook', lambda hook: None)
    counts = {'pools': 0, 'forecasts': 0, 'services': 0}

    class FakeCollector:
        def __init__(self, *args):
            self.component_costs = {};self.forecast_aliases = {}

        def pools(self, views, prefix):
            counts['pools'] += len(views)
            self.component_costs.update({e.uid: {a: .1 for a in POOL} for e in views})
            return ({e.uid: {a: e.target.copy() for a in POOL} for e in views}, {e.uid: .5 for e in views}, {})

        def forecasts(self, views, pools, prefix):
            counts['forecasts'] += len(views)
            self.forecast_aliases.update({(prefix, e.uid, a): (e.uid, 'A0_NATIVE') for e in views for a in POOL})
            return ({(e.uid, a): np.zeros(e.horizon) for e in views for a in POOL},
                    {(e.uid, a): .2 for e in views for a in POOL})

    class FakeServices:
        def __init__(self, *args):
            counts['services'] += 1
        def call(self, *args):
            raise AssertionError('Fake Collector should not request actual workers')
        def close(self):
            pass

    monkeypatch.setattr(mod, 'Collector', FakeCollector)
    monkeypatch.setitem(sys.modules, 'online_v43_agent', types.SimpleNamespace(Services=FakeServices))
    monkeypatch.setitem(sys.modules, 'v431_r2_services', types.SimpleNamespace(R2Services=FakeServices, with_timesfm=lambda m: m))
    mod.collect(tmp_path, 'main', 'bolt', 'train', 0, 4)
    assert counts == {'pools': 1, 'forecasts': 1, 'services': 1}
    mod.collect(tmp_path, 'main', 'bolt', 'train', 0, 4)
    assert counts == {'pools': 1, 'forecasts': 1, 'services': 1}
    sessions = sorted((out / 'sessions').glob('*/records.json'))
    assert len(sessions) == 2 and all(len(json.loads(p.read_text())) == 2 for p in sessions)
