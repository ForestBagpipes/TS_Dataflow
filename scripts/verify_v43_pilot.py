#!/usr/bin/env python3
"""从保存的原始数组独立重算pilot，不调用生产评估函数或打开留出标签。"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from introact_ts.v43.data_io import read_rows
from introact_ts.v43.schemas import array_hash


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    args = p.parse_args()
    root = args.run
    output = root / 'independent_verification.json'
    assert not output.exists(), 'preserve existing verification'
    report = dict(status='running', started_at=time.time(), scope='H32_interface_pilot_only',
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  heldout_labels_read=0, new_future_labels_read=0)
    try:
        run_status = json.loads((root / 'status.json').read_text())
        assert run_status['status'] == 'completed' and run_status['n_origins'] == 32
        records = json.loads((root / 'data_manifest.json').read_text())
        origins = json.loads((root / 'origin_manifest.json').read_text())
        assert len(origins) == 32 and all(o['split'] in ('train', 'dev') for o in origins)
        config = json.loads((root / 'semantic_gate.json').read_text())['config']
        scales = {}
        for r in records:
            lo, hi = r['split_bounds']['train']
            x = read_rows(r, lo, hi, 'train')[1][:, config['data']['pilot_target_channel']]
            season = config['data']['seasonal_periods'][r['source']]
            mask = np.isfinite(x[season:]) & np.isfinite(x[:-season])
            scales[r['source']] = float(np.abs(x[season:][mask] - x[:-season][mask]).mean())
        saved_scales = json.loads((root / 'mase_scales.json').read_text())
        for name, value in scales.items():
            assert value > 0
            np.testing.assert_allclose(value, saved_scales[name], rtol=1e-12, atol=1e-12)
        costs, outputs, rows_by_shard = {}, {}, {}
        for shard, count in (('tsicl_single', 32), ('tsicl_cov', 32), ('bolt', 96)):
            request = json.loads((root / f'{shard}.request.json').read_text())
            response = json.loads((root / f'{shard}.response.json').read_text())
            assert response['status'] == 'completed'
            assert len(request['rows']) == len(response['rows']) == count
            with np.load(root / f'{shard}.predictions.npz', allow_pickle=False) as a, np.load(root / f'{shard}.predictions.raw.npz', allow_pickle=False) as raw:
                assert set(a.files) == set(raw.files) == {f'row_{i}' for i in range(count)}
                outputs[shard] = [a[f'row_{i}'] for i in range(count)]
                for i, (q, s, prediction) in enumerate(zip(request['rows'], response['rows'], outputs[shard])):
                    assert q['episode_uid'] == s['episode_uid'] and q['candidate_id'] == s['candidate_id']
                    assert prediction.shape == (q['output_length'],) and np.isfinite(prediction).all()
                    assert array_hash(prediction) == s['prediction_hash']
                    assert array_hash(raw[f'row_{i}']) == s['raw_hash'] and np.isfinite(raw[f'row_{i}']).all()
                    if shard != 'bolt':
                        with np.load(q['array_path'], allow_pickle=False) as payload:
                            x = payload['target']
                            observed = np.isfinite(x)
                            assert prediction[observed].tobytes() == x[observed].tobytes()
                            np.testing.assert_array_equal(prediction[~observed], raw[f'row_{i}'][0, 0, ~observed, 1])
                    else:
                        np.testing.assert_array_equal(prediction, raw[f'row_{i}'][0, 4])
            rows_by_shard[shard] = request['rows']
            costs[shard] = dict(n_requests=count, inference_seconds=sum(r['runtime_seconds'] for r in response['rows']),
                                peak_gpu_bytes=max(response['load_peak_gpu_bytes'], *(r['peak_gpu_bytes'] for r in response['rows'])))
        saved_costs = json.loads((root / 'cost_ledger.json').read_text())
        for c in saved_costs:
            for k in ('n_requests', 'inference_seconds', 'peak_gpu_bytes'):
                np.testing.assert_allclose(c[k], costs[c['shard']][k], rtol=1e-12, atol=1e-12)
        labels = json.loads((root / 'task_labels.json').read_text())
        assert len(labels) == 96
        label_lookup = {(r['episode_uid'], r['candidate_id']): r for r in labels}
        assert len(label_lookup) == 96
        grouped, harms = collections.defaultdict(list), collections.Counter()
        by_split = collections.defaultdict(list)
        origin_lookup = {(o['source'], o['context_end']): o for o in origins}
        with np.load(root / 'targets.npz', allow_pickle=False) as targets:
            for i, row in enumerate(rows_by_shard['bolt']):
                uid, arm = row['episode_uid'], row['candidate_id']
                old = label_lookup[uid, arm]
                source = old['source']
                origin = origin_lookup[source, row['cutoff']]
                y, mask = targets[f'{uid}_values'], targets[f'{uid}_mask']
                assert y.shape == (32,) and np.array_equal(mask, np.isfinite(y)) and mask.any()
                prediction, keep = outputs['bolt'][i], outputs['bolt'][i // 3 * 3]
                assert rows_by_shard['bolt'][i // 3 * 3]['candidate_id'] == 'KEEP'
                mae = float(np.abs(prediction[mask] - y[mask]).mean())
                keep_mae = float(np.abs(keep[mask] - y[mask]).mean())
                values = dict(mae=mae, mse=float(np.square(prediction[mask] - y[mask]).mean()),
                              mase=mae / scales[source], task_gain=keep_mae - mae)
                for key, value in values.items():
                    np.testing.assert_allclose(value, old[key], rtol=1e-12, atol=1e-12)
                harm = mae > keep_mae + 1e-9
                assert harm == old['task_harm'] and int(mask.sum()) == old['n_scored']
                grouped[arm, source].append(values)
                by_split[arm, origin['split'], source].append(values)
                harms[arm] += int(harm)
        comparison = json.loads((root / 'comparison.json').read_text())
        macro = {}
        for arm in ('KEEP', 'TSICL_SINGLE', 'TSICL_COV'):
            macro[arm] = {}
            for key in ('mae', 'mase', 'task_gain'):
                v = float(np.mean([np.mean([x[key] for x in grouped[arm, r['source']]]) for r in records]))
                np.testing.assert_allclose(v, comparison['arms'][arm]['source_macro_' + key], rtol=1e-12, atol=1e-12)
                macro[arm][key] = v
        report.update(status='completed', origins=32, split_counts=dict(collections.Counter(o['split'] for o in origins)),
                      verified_imputations=64, verified_forecasts=96, observed_write_violations=0,
                      independent_macro=macro, task_harm_counts=dict(harms), recomputed_costs=costs,
                      promotion=False, confidence_interval=None,
                      limitation='train/dev mixed H32 diagnostic; full A0-A5 H96/H192 and source support pending')
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['finished_at'] = time.time()
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
