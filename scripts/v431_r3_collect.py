#!/usr/bin/env python3
"""Prepare context-only probes, then collect resumable real family predictions.

Only --collect starts model services; the root agent owns that GPU queue.
Successful per-input caches are immutable and bind source/model/input hashes.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import traceback

import numpy as np
import yaml

from introact_ts.v43.agent_collect import Collector
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.cli import atomic_json, code_manifest
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import Episode, array_hash, json_hash, require
from introact_ts.v431_r3.probe import prepare_probe, registered_specs, score_probe, proxy_mismatch, visible_descriptor, canonical_view_hash

OLD = Path('results/v43/20260914T141030.324186Z-agent')
FIN = Path('results/v431-r2/financial-observation-index-r1')
FIELDS = ('target', 'covariates', 'timestamps', 'availability')


def read(path):
    return json.loads(Path(path).read_text())


def archive(path, values):
    with Path(path).open('xb') as stream:
        np.savez_compressed(stream, **values)


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')


def producer_identity():
    paths = [Path(__file__), Path('src/introact_ts/v431_r3/probe.py'),
             Path('scripts/online_v43_agent.py'), Path('scripts/v431_r2_services.py'),
             Path('scripts/serve_v43_model.py'), Path('scripts/serve_v431_r2_timesfm.py')]
    return {str(p): file_hash(p) for p in paths}


def load_episodes(root):
    meta = read(root / 'episode_manifest.json')
    result = {}
    with np.load(root / 'contexts.npz', allow_pickle=False) as f:
        for uid, m in meta.items():
            require(m['split'] in ('train', 'dev'), 'Collector refuses held-out input')
            values = {k: f[uid + '_' + k] for k in FIELDS}
            for name, key in [('target', 'target_hash'), ('covariates', 'covariate_hash'),
                              ('timestamps', 'timestamps_hash'), ('availability', 'availability_hash')]:
                if key in m:
                    require(array_hash(values[name]) == m[key], 'Immutable current context changed')
            result[uid] = Episode(uid, m['source'], m.get('panel', m['source']), m['parent_group'],
                m['split'], 0, m['raw_start'], m['context_end'], m['horizon'], **values)
    return result, meta


def prepare(root, suite):
    out = root / suite
    require(not (out / 'preparation.json').exists(), 'Prepared suite is immutable; use it directly for resume')
    out.mkdir(parents=True, exist_ok=True)
    source = OLD if suite == 'main' else FIN
    begun = time.perf_counter();episodes, meta = load_episodes(source)
    scales = read(source / 'mase_scales.json')
    extra = {}
    if suite == 'main':
        roles = read('results/v431/20260914-sprint/partition.json')
        for uid, m in meta.items():
            m['v431_role'] = roles[uid]['v431_role']
            m['suite'] = 'main';m['generalization_only'] = False
        from dataclasses import replace
        raw = [e for uid, e in episodes.items() if meta[uid]['v431_role'] == 'T_check'
               and meta[uid]['condition'] == 'raw' and e.horizon == 192]
        require(len(raw) == 17, 'Registered 17 independent check parents changed')
        for e in raw:
            uid = json_hash(dict(base_raw_uid=e.uid, gap=[358, 409], horizon=192, protocol='r3_check_only'))
            x = e.target.copy();x[358:409] = np.nan
            new = replace(e, uid=uid, target=x)
            extra[uid] = new
            meta[uid] = dict(meta[e.uid], base_uid=e.uid, condition='target_block_10_position358_check_only',
                             target_hash=array_hash(x), generalization_only=True, v431_role='T_check',
                             gap=[358, 409], scale=scales[e.source])
        episodes.update(extra)
    else:
        for uid, m in meta.items():
            m.update(suite='financial', generalization_only=False, v431_role='dev')
    for uid, e in episodes.items():
        meta[uid].update(scale=scales[e.source], base_uid=meta[uid].get('base_uid', uid),
                         raw_start=e.raw_start, context_end=e.context_end,
                         **{k + '_hash': array_hash(getattr(e, n)) for n, k in
                            [('target', 'target'), ('covariates', 'covariate'), ('timestamps', 'timestamps'), ('availability', 'availability')]})
    archive(out / 'contexts.npz', {uid + '_' + k: getattr(e, k) for uid, e in episodes.items() for k in FIELDS})
    atomic_json(out / 'episode_manifest.json', meta);atomic_json(out / 'mase_scales.json', scales)
    if extra:
        archive(out / 'generalization_contexts.npz', {uid + '_' + k: getattr(e, k) for uid, e in extra.items() for k in FIELDS})
        atomic_json(out / 'generalization_metadata.json', {uid: meta[uid] for uid in extra})
    records = [];viewdir = out / 'views';viewdir.mkdir(exist_ok=True)
    for uid, e in episodes.items():
        for spec in registered_specs(e.horizon).values():
            tick = time.perf_counter();p = prepare_probe(e, spec, scales[e.source]);row = p.metadata()
            row.update(source=e.source, parent_group=e.parent_group, split=e.split,
                       v431_role=meta[uid]['v431_role'], generalization_only=meta[uid]['generalization_only'],
                       current_descriptor=visible_descriptor(e), current_task_horizon=e.horizon)
            if p.view is not None:
                path = viewdir / (p.input_hash + '.npz')
                archive(path, {**{k: getattr(p.view, k) for k in FIELDS}, 'raw_mask': p.view.observed_mask,
                               'copied_mask': p.copied_mask, 'historical_validation': p.validation,
                               'scoring_mask': p.scoring_mask})
                row.update(array_path=str(path), array_sha256=file_hash(path), raw_start=p.view.raw_start,
                           context_end=p.view.context_end, probe_descriptor=visible_descriptor(p.view),
                           psi=proxy_mismatch(e, p.view, scales[e.source]), cache_input_hash=canonical_view_hash(p.view))
            row['preparation_seconds'] = time.perf_counter() - tick;records.append(row)
    atomic_json(out / 'probe_manifest.json', records)
    summary = dict(status='prepared', suite=suite, original_episodes=len(episodes) - len(extra),
                   added_check_only_episodes=len(extra), parents=len({e.parent_group for e in episodes.values()}),
                   train_parents=len({e.parent_group for e in episodes.values() if e.split == 'train'}),
                   dev_parents=len({e.parent_group for e in episodes.values() if e.split == 'dev'}),
                   probes=len(records), support=dict(Counter(r['status'] for r in records)),
                   coverage_rule='max(16,ceil(.5*Hq)); paired probes use identical current-visible target mask',
                   producer_sources=producer_identity(), source_contexts_sha256=file_hash(source / 'contexts.npz'),
                   files={name: file_hash(out / name) for name in ('contexts.npz', 'episode_manifest.json', 'mase_scales.json', 'probe_manifest.json')},
                   future_labels_read=0, preparation_seconds=time.perf_counter() - begun)
    atomic_json(out / 'preparation.json', summary);print(json.dumps(summary), flush=True)


def cache_read(path, identity):
    if not path.exists():
        return None
    record = read(path)
    require(record['identity'] == identity and record['status'] == 'completed', 'Cache identity changed or cache incomplete')
    require(file_hash(record['array_path']) == record['array_sha256'], 'Cached numeric artifact changed')
    with np.load(record['array_path'], allow_pickle=False) as f:
        values = {a: f[a] for a in POOL}
    require({a: array_hash(v) for a, v in values.items()} == record['array_hashes'], 'Cached arrays differ from frozen content')
    return record, values


def cache_write(path, identity, values, extra):
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), 'Never overwrite a completed cache')
    # An interrupted write without a completed JSON record remains an orphaned
    # historical artifact; a retry writes a fresh file rather than overwriting it.
    target = path.with_name(path.stem + '.' + stamp() + '.npz');archive(target, values)
    record = dict(status='completed', identity=identity, array_path=str(target), array_sha256=file_hash(target),
                  array_hashes={a: array_hash(v) for a, v in values.items()}, **extra)
    atomic_json(path, record)
    return record


def collect(root, suite, family, split, limit, batch_parents):
    # Guard the evaluator boundary before any input is opened; imported Collector
    # is used only for pools/forecasts, never its label-reading run_collect entry.
    def barrier(event, args):
        if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
            require(Path(os.fsdecode(args[0])).name not in ('targets.npz', 'task_labels.json', 'evaluator_metadata.json'),
                    'Deployment-future evaluator is sealed during probe collection')
    sys.addaudithook(barrier)
    from online_v43_agent import Services
    from v431_r2_services import R2Services, with_timesfm
    out = root / suite;preparation = read(out / 'preparation.json')
    for name, digest in preparation['files'].items():
        require(file_hash(out / name) == digest, 'Prepared context/probe ledger changed')
    require(preparation['producer_sources'] == producer_identity(), 'Prepared producer source changed; explicit new preparation required')
    records = read(out / 'probe_manifest.json');episodes, meta = load_episodes(out)
    scales = read(out / 'mase_scales.json')
    chosen_parents = sorted({r['parent_group'] for r in records if split == 'all' or r['split'] == split},
                            key=lambda p: (p.split(':')[0], min(e.raw_start for e in episodes.values() if e.parent_group == p)))
    if limit:
        require(split == 'train', 'Throughput pilot limit applies to train metadata only')
        # Source round-robin preserves mechanism coverage without reading outcomes.
        bysource = {}
        for p in chosen_parents:
            bysource.setdefault(p.split(':')[0], []).append(p)
        chosen_parents = [v[i] for i in range(max(map(len, bysource.values()))) for v in bysource.values() if i < len(v)][:limit]
    selected = [r for r in records if r['parent_group'] in set(chosen_parents)]
    config = yaml.safe_load((OLD / 'resolved_config.yaml').read_text());model = read(OLD / 'model_manifest.json')
    if family == 'timesfm':
        model = with_timesfm(model)
    code = code_manifest();source_hash = json_hash(producer_identity())
    governance_hash = json_hash(dict(model=model['models']['tsicl'], code=code['hash'], source=source_hash))
    family_hash = json_hash(dict(family=family, model=model['models'][family], code=code['hash'], source=source_hash))
    reference_manifest = read('results/v431-r3/reference_manifest.json')
    reference = reference_manifest['families'][family]['arm']
    session = out / 'sessions' / (stamp() + '-' + family);session.mkdir(parents=True)
    status = dict(status='running', family=family, suite=suite, pid=os.getpid(), parents=len(chosen_parents),
                  requested_probes=len(selected), completed=0, reused_candidates=0, reused_predictions=0,
                  new_future_labels_read=0, heldout_labels_read=0)
    atomic_json(session / 'model_manifest.json', model);atomic_json(session / 'code_manifest.json', code)
    atomic_json(session / 'producer_sources.json', producer_identity());atomic_json(session / 'status.json', status)
    collector = Collector(config, session, code, status, model)
    services = None;results = [];begun = time.perf_counter();native_prices = {}
    try:
        for chunk, start in enumerate(range(0, len(chosen_parents), batch_parents)):
            parents = set(chosen_parents[start:start + batch_parents]);rows = [r for r in selected if r['parent_group'] in parents]
            prepared, candidate_values, candidate_records, missing = {}, {}, {}, []
            representatives, aliases, cache_keys = {}, {}, {}
            for row in rows:
                uid, name = row['base_uid'], row['spec']['name']
                p = prepare_probe(episodes[uid], registered_specs(episodes[uid].horizon)[name], scales[episodes[uid].source])
                require(p.input_hash == row['input_hash'], 'Prepared probe does not replay exactly')
                if p.status == 'unsupported':
                    charge = dict(key='probe-prepare:' + p.input_hash, seconds=row['preparation_seconds'])
                    results.append(dict(row, family=family, model_identity_hash=family_hash, reference_arm=reference,
                                        probe=name, invoice={'charges': [charge], 'total_seconds': charge['seconds']},
                                        raw_predictions={}, mae={}, gain={}))
                    continue
                require(file_hash(row['array_path']) == row['array_sha256'], 'Prepared as-of input file changed')
                prepared[p.view.uid] = (p, row)
                canonical = canonical_view_hash(p.view)
                require(canonical == row['cache_input_hash'], 'Canonical worker payload identity changed')
                cache_keys[p.view.uid] = canonical
                if canonical in representatives:
                    aliases[p.view.uid] = representatives[canonical]
                    continue
                representatives[canonical] = p.view.uid
                aliases[p.view.uid] = p.view.uid
                identity = dict(input_hash=canonical, governance_hash=governance_hash)
                cached = cache_read(out / 'candidate_cache' / governance_hash / (canonical + '.json'), identity)
                if cached is None:
                    missing.append(p.view)
                else:
                    candidate_records[p.view.uid], candidate_values[p.view.uid] = cached
                    status['reused_candidates'] += 1
            if missing:
                if services is None:
                    services = Services(session, model, code, status, collector) if family == 'bolt' else R2Services(session, model, code, status, collector)
                    collector.call = services.call
                pools, costs, _ = collector.pools(missing, f'chunk{chunk}-pool')
                for view in missing:
                    p, row = prepared[view.uid];values = pools[view.uid]
                    canonical = cache_keys[view.uid]
                    identity = dict(input_hash=canonical, governance_hash=governance_hash)
                    record = cache_write(out / 'candidate_cache' / governance_hash / (canonical + '.json'), identity, values,
                                         dict(producer_session=str(session), generation_seconds=costs[view.uid],
                                              direct_seconds=collector.component_costs[view.uid]))
                    candidate_records[view.uid], candidate_values[view.uid] = record, values
            for view_uid, representative in aliases.items():
                if view_uid != representative:
                    candidate_records[view_uid] = candidate_records[representative]
                    candidate_values[view_uid] = candidate_values[representative]
                    status['reused_candidates'] += 1
            missing_forecasts = []
            completed_forecasts = {}
            for view_uid, (p, row) in prepared.items():
                if aliases[view_uid] != view_uid:
                    continue
                canonical = cache_keys[view_uid]
                identity = dict(input_hash=canonical, family_hash=family_hash,
                                candidate_hashes={a: array_hash(v) for a, v in candidate_values[view_uid].items()})
                cached = cache_read(out / 'forecast_cache' / family_hash / (canonical + '.json'), identity)
                if cached is None:
                    missing_forecasts.append(p.view)
                else:
                    completed_forecasts[view_uid] = cached;status['reused_predictions'] += 1
            if missing_forecasts:
                if services is None:
                    services = Services(session, model, code, status, collector) if family == 'bolt' else R2Services(session, model, code, status, collector)
                    collector.call = services.call
                pred, costs = collector.forecasts(missing_forecasts, candidate_values, f'chunk{chunk}-forecast')
                # TimesFM's resident model deduplicates across request UIDs.
                # Reuse saves offline work, but deployment must pay the original
                # non-hit prediction cost, not the tiny cache lookup duration.
                if family == 'timesfm':
                    for h in sorted({v.horizon for v in missing_forecasts}):
                        response = read(session / f'chunk{chunk}-forecast-h{h}-bolt.response.json')
                        for r in response['rows']:
                            k = r['episode_uid'], r['candidate_id'];raw = r['raw_native_file']
                            if not r['cache_hit']:
                                native_prices[raw] = costs[k]
                            require(raw in native_prices, 'Cross-request prediction hit lacks its actual original invoice')
                            costs[k] = native_prices[raw]
                        for v in (v for v in missing_forecasts if v.horizon == h):
                            for arm in POOL:
                                alias = collector.forecast_aliases[f'chunk{chunk}-forecast', v.uid, arm]
                                costs[v.uid, arm] = costs[alias]
                for view in missing_forecasts:
                    p, row = prepared[view.uid];values = {a: pred[view.uid, a] for a in POOL}
                    canonical = cache_keys[view.uid]
                    identity = dict(input_hash=canonical, family_hash=family_hash,
                                    candidate_hashes={a: array_hash(v) for a, v in candidate_values[view.uid].items()})
                    arm_aliases = {a: collector.forecast_aliases[f'chunk{chunk}-forecast', view.uid, a][1] for a in POOL}
                    distinct = {arm_aliases[a]: costs[view.uid, a] for a in POOL}
                    record = cache_write(out / 'forecast_cache' / family_hash / (canonical + '.json'), identity, values,
                        dict(producer_session=str(session), actual_forecast_seconds=sum(distinct.values()),
                             arm_seconds={a: costs[view.uid, a] for a in POOL}, aliases=arm_aliases))
                    completed_forecasts[view.uid] = record, values
            for view_uid, representative in aliases.items():
                if view_uid != representative:
                    completed_forecasts[view_uid] = completed_forecasts[representative]
                    status['reused_predictions'] += 1
            for view_uid, (p, row) in prepared.items():
                record, predictions = completed_forecasts[view_uid]
                tick = time.perf_counter()
                charges = [dict(key='probe-prepare:' + p.input_hash, seconds=row['preparation_seconds']),
                           dict(key='probe-candidates:' + cache_keys[view_uid], seconds=candidate_records[view_uid]['generation_seconds']),
                           dict(key='probe-forecast:' + family_hash + ':' + cache_keys[view_uid], seconds=record['actual_forecast_seconds'])]
                invoice = dict(charges=charges, total_seconds=sum(c['seconds'] for c in charges))
                result = score_probe(p, family, predictions, family_hash, invoice, reference_arm=reference).to_dict()
                charge = dict(key='probe-score:' + family + ':' + p.input_hash, seconds=time.perf_counter() - tick)
                result['invoice']['charges'].append(charge);result['invoice']['total_seconds'] += charge['seconds']
                result.update(psi=row['psi'], current_descriptor=row['current_descriptor'], probe_descriptor=row['probe_descriptor'],
                              spec_hash=p.spec.hash, parent_group=row['parent_group'], source=row['source'], split=row['split'],
                              v431_role=row['v431_role'], generalization_only=row['generalization_only'],
                              candidate_cache=candidate_records[view_uid]['array_path'], forecast_cache=record['array_path'],
                              cache_input_hash=cache_keys[view_uid], alias_view_uid=aliases[view_uid],
                              raw_worker_session=record['producer_session'], reference_manifest_hash=json_hash(reference_manifest))
                results.append(result);status['completed'] += 1
            atomic_json(session / 'records.json', results);atomic_json(session / 'status.json', status)
        status.update(status='completed', elapsed_seconds=time.perf_counter() - begun,
                      unsupported=sum(r['status'] == 'unsupported' for r in results),
                      records_sha256=file_hash(session / 'records.json'))
    except BaseException as exc:
        status.update(status='failed', error=f'{type(exc).__name__}: {exc}', elapsed_seconds=time.perf_counter() - begun)
        traceback.print_exc();raise
    finally:
        if services is not None:
            services.close()
        atomic_json(session / 'status.json', status);print(json.dumps(dict(session=str(session), **status)), flush=True)


def main():
    parser = argparse.ArgumentParser();mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true');mode.add_argument('--collect', action='store_true')
    parser.add_argument('--run', type=Path, default=Path('results/v431-r3/probes'))
    parser.add_argument('--suite', choices=('main', 'financial'), default='main')
    parser.add_argument('--family', choices=('bolt', 'timesfm'), default='bolt')
    parser.add_argument('--split', choices=('all', 'train', 'dev'), default='all')
    parser.add_argument('--limit-train-parents', type=int, default=0)
    parser.add_argument('--batch-parents', type=int, default=4)
    args = parser.parse_args();require(args.batch_parents > 0 and args.limit_train_parents >= 0, 'Invalid batch/support cap')
    if args.prepare:
        prepare(args.run, args.suite)
    else:
        collect(args.run, args.suite, args.family, args.split, args.limit_train_parents, args.batch_parents)


if __name__ == '__main__':
    main()
