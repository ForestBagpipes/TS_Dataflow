#!/usr/bin/env python3
"""Independent raw-output/metric audit; no new future or held-out reads."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from introact_ts.v43.data_io import read_rows
from introact_ts.v43.schemas import array_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    root = args.run
    def read(name):
        return json.loads((root/(name+'.json')).read_text())
    destination = root/'independent_verification.json'
    assert not destination.exists(), 'existing audit must be preserved'
    report = dict(status='running', started_at=time.time(), new_future_labels_read=0, heldout_labels_read=0,
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    try:
        status = read('status')
        assert status['status'] == 'completed' and status['n_episodes'] == 156
        episodes, aliases, indices = read('episode_manifest'), read('forecast_aliases'), read('candidate_index')
        arms = read('arm_manifest')['executed']
        assert len(episodes) == 156 and all(e['split'] == 'dev' for e in episodes.values())
        config = read('semantic_gate')['config']
        scales = {}
        for record in read('data_manifest'):
            lo, hi = record['split_bounds']['train']
            x = read_rows(record, lo, hi, 'train')[1][:, 0]
            period = config['data']['seasonal_periods'][record['source']]
            finite = np.isfinite(x[period:]) & np.isfinite(x[:-period])
            scale = float(np.abs(x[period:][finite]-x[:-period][finite]).mean()) if finite.any() else None
            scales[record['source']] = scale if scale and np.isfinite(scale) else None
        assert scales == read('mase_scales')
        n_imputations, n_forecasts, peak, inference = 0, 0, 0, 0.
        worker_forecasts = {}
        nested_inputs = defaultdict(set)
        for request_path in sorted(root.glob('*.request.json')):
            shard = request_path.name.removesuffix('.request.json')
            request, response = read(shard+'.request'), read(shard+'.response')
            assert response['status'] == 'completed'
            for name, value in request.items():
                if name != 'rows':
                    assert response[name] == value
            assert len(request['rows']) == len(response['rows'])
            peak = max(peak, response['load_peak_gpu_bytes'])
            with np.load(root/(shard+'.predictions.npz'), allow_pickle=False) as predictions, np.load(root/(shard+'.predictions.raw.npz'), allow_pickle=False) as raw:
                assert set(predictions.files) == set(raw.files) == {f'row_{i}' for i in range(len(request['rows']))}
                for i, (q, r) in enumerate(zip(request['rows'], response['rows'])):
                    assert all(r[k] == v for k, v in q.items())
                    pred, quantiles = predictions[f'row_{i}'], raw[f'row_{i}']
                    assert array_hash(pred) == r['prediction_hash'] and array_hash(quantiles) == r['raw_hash']
                    assert pred.shape == (q['output_length'],) and np.isfinite(pred).all() and np.isfinite(quantiles).all()
                    with np.load(q['array_path'], allow_pickle=False) as payload:
                        for name, key in [('target','input_hash'),('covariates','covariate_hash'),('raw_mask','raw_mask_hash'),('timestamps','timestamps_hash'),('availability','availability_hash')]:
                            assert array_hash(payload[name]) == q[key]
                        if request['task'] == 'impute':
                            x = payload['target']; seen = np.isfinite(x)
                            assert pred[seen].tobytes() == x[seen].tobytes()
                            np.testing.assert_array_equal(pred[~seen], quantiles[0,0,~seen,1])
                            n_imputations += 1
                            if request['covariate_mode'] == 'none':
                                nested_inputs[q['episode_uid']].add(q['input_hash'])
                        else:
                            np.testing.assert_array_equal(pred, quantiles[0,4])
                            worker_forecasts[q['episode_uid']+'_'+q['candidate_id']] = pred
                            n_forecasts += 1
                    peak = max(peak, r['peak_gpu_bytes'])
                    inference += r['runtime_seconds']
        costs = read('cost_ledger')
        assert n_imputations+n_forecasts == sum(c['n_requests'] for c in costs)
        assert peak == max(c['peak_gpu_bytes'] for c in costs)
        np.testing.assert_allclose(inference, sum(c['inference_seconds'] for c in costs), rtol=1e-12)
        evidence, plans = read('candidate_evidence'), read('mask_plans')
        with np.load(root/'candidates.npz', allow_pickle=False) as candidates, np.load(root/'forecasts.npz', allow_pickle=False) as predictions, np.load(root/'targets.npz', allow_pickle=False) as targets:
            assert set(predictions.files) == set(worker_forecasts)
            assert len(indices) == len(candidates.files) == len(episodes)*len(arms)
            for key in predictions.files:
                np.testing.assert_array_equal(predictions[key], worker_forecasts[key])
            for row in indices:
                uid, arm, key = row['episode_uid'], row['arm'], row['array_key']
                x, c = candidates[uid+'_A0_NATIVE'], candidates[key]
                observed = np.isfinite(x)
                assert array_hash(c) == row['hash'] and c[observed].tobytes() == x[observed].tobytes()
                alias = aliases[key]
                assert alias.startswith(uid+'_') and array_hash(c) == array_hash(candidates[alias])
            for uid in episodes:
                e = evidence[uid]['A5_STATIC']
                if e.get('fallback') == 'A2_SINGLE':
                    np.testing.assert_array_equal(candidates[uid+'_A5_STATIC'], candidates[uid+'_A2_SINGLE'])
                else:
                    loss = np.mean(e['outer_mae'], axis=0)
                    assert e['eta'] == (0.,.5,1.)[int(np.argmin(loss))]
                    assert e['eta'] == 0 or loss[(0.,.5,1.).index(e['eta'])] < loss[0]
                if plans[uid]['blocks'] is not None:
                    assert nested_inputs[uid] == set(plans[uid]['masked_input_hashes']) and len(nested_inputs[uid]) == 7
                original = candidates[uid+'_A0_NATIVE']
                assert array_hash(np.isfinite(original)) == episodes[uid]['observed_mask_hash']
            labels = read('task_labels')
            assert len(labels) == len(episodes)*len(arms)
            assert len({(r['episode_uid'],r['arm']) for r in labels}) == len(labels)
            grouped, harms, by_episode = defaultdict(list), Counter(), defaultdict(list)
            shared_targets = {}
            for row in labels:
                uid, arm = row['episode_uid'], row['arm']
                y, mask = targets[uid+'_values'], targets[uid+'_mask']
                assert np.array_equal(mask,np.isfinite(y)) and array_hash(y) == row['future_hash'] and array_hash(mask) == row['mask_hash']
                assert mask.any(), 'this audit requires explicit extension for unscorable future'
                identity = (row['parent_group'], row['horizon'])
                shared_targets.setdefault(identity,array_hash(y))
                assert shared_targets[identity] == array_hash(y)
                prediction = predictions[aliases[uid+'_'+arm]]
                keep = predictions[aliases[uid+'_A0_NATIVE']]
                mae = float(np.abs(prediction[mask]-y[mask]).mean())
                km = float(np.abs(keep[mask]-y[mask]).mean())
                values = dict(mae=mae,mse=float(np.square(prediction[mask]-y[mask]).mean()),mase=mae/scales[row['source']],task_gain=km-mae,task_harm=mae>km+1e-9)
                for name,value in values.items():
                    np.testing.assert_allclose(value,row[name],rtol=1e-12,atol=1e-12)
                grouped[arm,row['source'],row['horizon'],row['condition']].append(values)
                harms[arm] += int(values['task_harm'])
                by_episode[uid].append(row)
            for oracle in read('oracle_labels'):
                expected = min(by_episode[oracle['episode_uid']],key=lambda r:r['mae'])
                assert oracle['mae'] == expected['mae'] and oracle['chosen_arm'] == expected['arm']
            comparison = read('comparison')
            macro = {}
            for arm in arms:
                macro[arm] = {metric: float(np.mean([np.mean([v[metric] for v in values]) for key,values in grouped.items() if key[0]==arm])) for metric in ('mae','mse','mase','task_gain','task_harm')}
                for name,value in macro[arm].items():
                    np.testing.assert_allclose(value,comparison['source_macro'][arm][name],rtol=1e-12,atol=1e-12)
        report.update(status='completed',episodes=len(episodes),verified_imputations=n_imputations,verified_forecasts=n_forecasts,candidate_labels=len(labels),observed_write_violations=0,independent_macro=macro,task_harm_counts=dict(harms),peak_gpu_bytes=peak,worker_inference_seconds=inference,promotion=False,confidence_interval=None)
    except Exception as exc:
        report.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['finished_at'] = time.time()
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        print(json.dumps(report,ensure_ascii=False))


if __name__ == '__main__':
    main()
