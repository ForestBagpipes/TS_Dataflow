"""Explicit official 96-step transformation units, restricted L512 inputs.

All seq_l=5..15 retained. Infeasible lengths are rejected, never rescaled.
"""
import hashlib
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/v431_baselines'))
import tato_adapter

def initial_params():
    p=tato_adapter.vanilla();p['trimmer_seq_l']=7
    return p

def make_pipeline(model,horizon,params):
    factory,_=tato_adapter.load_official()
    return factory.build_trial_pipeline_by_transformation_names(SimpleNamespace(params=dict(params)),model,tato_adapter.NAMES,
        dict(pred_len=horizon,patch_len=96,data_patch_len=96,model_patch_len=96),mode='test',plt=False)

def execute_frozen_scene(model,context,horizon,params,family):
    if family not in ('bolt','timesfm'):raise ValueError('Unregistered family')
    x=np.asarray(context,dtype=np.float64)
    if x.shape!=(512,) or horizon not in (96,192):raise ValueError('Unregistered L512 task')
    started=time.perf_counter();seq=int(params['trimmer_seq_l'])
    if seq not in range(5,16):raise ValueError('Outside retained official seq_l=5..15')
    if seq*96>len(x):raise ValueError(f'unsupported_official_trimmer: {seq}*96={seq*96} > legal context {len(x)}; no rescaling')
    pipeline=make_pipeline(model,horizon,params)
    transformed=pipeline.preprocess(tato_adapter.bridge(x)[None,:,None])
    if transformed.shape[1]>512:raise ValueError('Unsupported transformed input beyond frozen backbone context; no hidden truncation')
    if not np.isfinite(transformed).all():raise FloatingPointError('Nonfinite transformed input')
    raw=model.forecast(transformed,pipeline.pred_len)
    if not np.isfinite(raw).all():raise FloatingPointError('Nonfinite raw forecast')
    final=np.asarray(pipeline.postprocess(raw))[0,:,0]
    if final.shape!=(horizon,) or not np.isfinite(final).all():raise FloatingPointError('Invalid original-grid forecast')
    return final,dict(seconds=time.perf_counter()-started,model_input_shape=list(transformed.shape),model_horizon=pipeline.pred_len,
        input_sha256=hashlib.sha256(x.tobytes()).hexdigest(),prediction_sha256=hashlib.sha256(final.tobytes()).hexdigest(),
        patch_len=96,data_patch_len=96,model_patch_len=96,trimmer_seq_l=seq,actual_trimmer_length=seq*96)
