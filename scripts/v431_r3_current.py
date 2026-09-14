#!/usr/bin/env python3
"""Generate the preregistered 17 check-only current forecasts, without labels."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import numpy as np
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.cli import atomic_json
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import Episode, array_hash, require
from introact_ts.v431_r3.runtime import LiveRuntime


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('results/v431-r3'))
    p.add_argument('--family', required=True, choices=['bolt', 'timesfm'])
    args = p.parse_args()
    root = args.root
    source = root / 'probes/main'
    meta = json.loads((source / 'generalization_metadata.json').read_text())
    require(len(meta) == 17 and all(m['generalization_only'] and m['v431_role'] == 'T_check' and m['horizon'] == 192 for m in meta.values()), 'Check-only support changed')
    episodes = []
    with np.load(source / 'generalization_contexts.npz', allow_pickle=False) as f:
        for u, m in meta.items():
            fields = {k: f[u + '_' + k] for k in ('target', 'covariates', 'timestamps', 'availability')}
            require(array_hash(fields['target']) == m['target_hash'], 'Check context changed')
            episodes.append(Episode(u, m['source'], m['source'], m['parent_group'], 'train', 0, m['raw_start'], m['context_end'], 192, **fields))
    out = root / ('generalization-current-' + args.family)
    out.mkdir(exist_ok=False)
    begin = time.perf_counter()
    status = dict(status='running', pid=os.getpid(), family=args.family, episodes=len(episodes),
                  started_at=datetime.now(timezone.utc).isoformat(), future_labels_read=0, heldout_labels_read=0)
    atomic_json(out / 'status.json', status)
    runtime = None
    try:
        runtime = LiveRuntime(out / 'service', args.family, episodes[0])
        producer = root / 'generalization-current-bolt'
        if args.family == 'timesfm':
            manifest = json.loads((producer / 'manifest.json').read_text())
            require(file_hash(producer / 'candidates.npz') == manifest['files']['candidates.npz'], 'Shared candidate identity changed')
            require(file_hash(source / 'generalization_contexts.npz') == manifest['input_sha256'], 'Shared context identity changed')
            with np.load(producer / 'candidates.npz', allow_pickle=False) as f:
                pools = {e.uid: {a: f[e.uid + '_' + a] for a in POOL} for e in episodes}
            direct = json.loads((producer / 'direct_candidate_costs.json').read_text())
        else:
            pools, _, _ = runtime.collector.pools(episodes, 'check-current')
            direct = runtime.collector.component_costs
        predictions, costs = runtime.collector.forecasts(episodes, pools, 'check-current')
        with (out / 'candidates.npz').open('xb') as f:
            np.savez(f, **{u + '_' + a: v for u, pool in pools.items() for a, v in pool.items()})
        with (out / 'predictions.npz').open('xb') as f:
            np.savez(f, **{u + '_' + a: v for (u, a), v in predictions.items()})
        atomic_json(out / 'forecast_costs.json', {u + '_' + a: v for (u, a), v in costs.items()})
        atomic_json(out / 'direct_candidate_costs.json', direct)
        manifest = dict(family=args.family, input_sha256=file_hash(source / 'generalization_contexts.npz'),
                        episode_manifest_sha256=file_hash(source / 'generalization_metadata.json'),
                        files={n: file_hash(out / n) for n in ('candidates.npz', 'predictions.npz', 'forecast_costs.json', 'direct_candidate_costs.json')},
                        producer_sources={__file__: file_hash(__file__), 'src/introact_ts/v431_r3/runtime.py': file_hash('src/introact_ts/v431_r3/runtime.py')},
                        candidate_reuse=str(producer) if args.family == 'timesfm' else None,
                        model_identity=runtime.identity, future_labels_read=0)
        atomic_json(out / 'manifest.json', manifest)
        status['status'] = 'completed'
    except BaseException as exc:
        status.update(status='failed', error=repr(exc))
        raise
    finally:
        if runtime:
            runtime.close()
        status['process_body_seconds'] = time.perf_counter() - begin
        atomic_json(out / 'status.json', status)
        print(json.dumps(status), flush=True)


if __name__ == '__main__':
    main()
