"""Official TATO adapter: immutable source, explicit NaN bridge, no future API."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL = ROOT / 'third_party/TATO'
COMMIT = '402bbc8998c49e2f33d9afbcc42140347a6b8c36'
NAMES = ['trimmer', 'inputer', 'denoiser', 'warper', 'differentiator', 'normalizer', 'sampler', 'aligner']
sys.path[:0] = [str(ROOT / '.cache/v431-baseline-deps'), str(OFFICIAL)]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def official_identity():
    commit = subprocess.check_output(['git', '-C', str(OFFICIAL), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != COMMIT: raise RuntimeError('official TATO commit changed')
    dirty = subprocess.check_output(['git', '-C', str(OFFICIAL), 'status', '--porcelain'], text=True)
    if dirty: raise RuntimeError('official TATO checkout was modified')
    return dict(commit=commit, source_sha256={str(p.relative_to(OFFICIAL)): sha(p) for p in sorted(OFFICIAL.rglob('*.py'))}, license_sha256=sha(OFFICIAL/'LICENSE'))


def load_official():
    # Preserve finite-output clipping exactly. Official nonfinite replacement is
    # prohibited in this project and is converted to a visible failed trial.
    import utils.clip as clipping
    if not getattr(clipping.my_clip, '_v431_guard', False):
        original = clipping.my_clip
        def checked_clip(seq_in, seq_out, *args, **kwargs):
            if not np.isfinite(seq_out).all(): raise FloatingPointError('TATO nonfinite output; official numeric replacement disabled')
            out = original(seq_in, seq_out, *args, **kwargs)
            if not np.isfinite(out).all(): raise FloatingPointError('TATO clipping produced nonfinite output')
            return out
        checked_clip._v431_guard = True
        clipping.my_clip = checked_clip
    from pipeline.pipeline_factory import PipelineFactory
    from tuner.tuner_factory import TunerFactory
    return PipelineFactory, TunerFactory


def bridge(x):
    x = np.asarray(x, dtype=np.float64).copy()
    if x.ndim != 1 or np.isinf(x).any(): raise ValueError('invalid context')
    valid = np.isfinite(x)
    if not valid.any(): raise ValueError('all-missing context unsupported; no fallback')
    if valid.all(): return x
    x[~valid] = np.interp(np.flatnonzero(~valid), np.flatnonzero(valid), x[valid])
    return x


def vanilla():
    return dict(inference_mode='infer1', clip_factor='none', trimmer_seq_l=15,
                inputer_detect_method='none', inputer_fill_method='linear_interpolate',
                denoiser_method='none', warper_method='none', differentiator_n=0,
                normalizer_method='none', normalizer_mode='input', sampler_factor=1,
                aligner_mode='none', aligner_method='edge_pad')


def pipeline(params, model, horizon):
    import optuna
    factory, _ = load_official()
    trial = optuna.trial.FixedTrial(params)
    # FixedTrial.params is populated only after suggestions; the factory reads
    # params directly, so use a simple trial-shaped immutable parameter holder.
    from types import SimpleNamespace
    trial = SimpleNamespace(params=dict(params))
    return factory.build_trial_pipeline_by_transformation_names(trial, model, NAMES,
        dict(pred_len=horizon, patch_len=16, data_patch_len=16, model_patch_len=16), mode='test', plt=False)


def predict_native(params, model, context, horizon, *, enable_bridge=True):
    x = np.asarray(context, dtype=np.float64)
    if x.ndim != 1 or len(x) < 240: raise ValueError('context too short for complete native trimmer search')
    before = x.copy()
    start = time.perf_counter()
    value = bridge(x) if enable_bridge else x.copy()
    bridge_seconds = time.perf_counter() - start
    p = pipeline(params, model, horizon)
    transformed = p.preprocess(value[None, :, None].copy())
    if not np.isfinite(transformed).all(): raise FloatingPointError('TATO transformed input nonfinite')
    raw = model.forecast(transformed, p.pred_len)
    if not np.isfinite(raw).all(): raise FloatingPointError('backbone raw output nonfinite')
    output = np.asarray(p.postprocess(raw))[0, :, 0]
    if output.shape != (horizon,) or not np.isfinite(output).all(): raise FloatingPointError('invalid external original-grid prediction')
    if not np.array_equal(x, before, equal_nan=True): raise AssertionError('original context was modified')
    return output, dict(bridge_used=bool(np.isnan(x).any()) and enable_bridge,
        bridge_seconds=bridge_seconds, model_input_shape=list(transformed.shape),
        model_horizon=p.pred_len, external_horizon=horizon)


def adapt_window(context, horizon, model, trials=8, seed=101):
    """Only dirty current-context is accepted. Future target cannot be passed."""
    import optuna
    _, tuner_factory = load_official()
    x = np.asarray(context, dtype=np.float64)
    cutoff = len(x) - horizon
    prefix = x[:cutoff].copy(); seen_validation = x[cutoff:].copy()
    valid = np.isfinite(seen_validation)
    if cutoff not in (416, 320) or not valid.any(): raise ValueError('unsupported historical origin/support')
    tuner = tuner_factory.build_optuna_tuner(enqueue_param_dicts=[vanilla()], mode='train', seed=seed)
    distribution = tuner_factory.build_search_space(NAMES, patch_len=16)
    ledger = []; start = time.perf_counter()
    for number in range(trials):
        trial = tuner.pick_trial(distribution); tick = time.perf_counter()
        row = dict(trial=number, params=dict(trial.params), validation_cutoff=cutoff,
                   validation_horizon=horizon, observed_validation_count=int(valid.sum()))
        try:
            prediction, detail = predict_native(trial.params, model, prefix, horizon)
            loss = float(np.mean(np.abs(prediction[valid] - seen_validation[valid])))
            tuner.tell(trial, loss)
            row.update(status='completed', validation_mae=loss, prediction=prediction.tolist(), **detail)
        except (ValueError, FloatingPointError, AssertionError) as exc:
            tuner.study.tell(trial, state=optuna.trial.TrialState.FAIL)
            row.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        row['wall_seconds'] = time.perf_counter() - tick; ledger.append(row)
    successful = [r for r in ledger if r['status'] == 'completed']
    if not successful: raise RuntimeError('all TATO trials failed; no replacement prediction')
    best = min(successful, key=lambda r: (r['validation_mae'], r['trial']))
    selection_seconds = time.perf_counter() - start
    tick = time.perf_counter()
    prediction, detail = predict_native(best['params'], model, x, horizon)
    return prediction, dict(selected_trial=best['trial'], selected_params=best['params'], trials=ledger,
        historical_validation_seconds=selection_seconds, final_governance_and_forecast_seconds=time.perf_counter()-tick,
        future_labels_read=0, heldout_labels_read=0, **detail)
