#!/usr/bin/env python3
"""Metadata-only main matrix preparation; TRAIN-only TATO scene-search API.

Default execution never parses numerical observations or starts a model.
scene_search is an explicitly separate API for the single GPU queue.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/v431-r5/main-preparation'
SOURCES = {
    **{n: dict(path=f'data/ETT-small_{n}.csv', frequency='1h' if 'h' in n else '15min',
              provider='https://github.com/zhouhaoyi/ETDataset', license='CC BY-ND 4.0', target='HUFL (channel 0; inherited v43)')
       for n in ('ETTh1','ETTh2','ETTm1','ETTm2')},
    'Electricity': dict(path='data/r5-public/electricity.txt.gz', frequency='1h', target='first channel (index 0; inherited v43 rule)',
                        provider='https://github.com/laiguokun/multivariate-time-series-data', license='research availability stated; redistribution grant unresolved'),
    'Exchange': dict(path='data/exchange.txt.gz', frequency='daily observations; calendar unresolved', target='first channel (index 0; inherited v43 rule)',
                     provider='https://github.com/laiguokun/multivariate-time-series-data', license='research availability stated; redistribution grant unresolved'),
    'Traffic': dict(path='data/r5-public/traffic.txt.gz', frequency='1h; timestamp mapping unresolved', target='first channel (index 0; inherited v43 rule)',
                    provider='https://github.com/laiguokun/multivariate-time-series-data', license='research availability stated; redistribution grant unresolved'),
    'Weather': dict(path='data/r5-public/weather.csv', frequency='10min', target='first value channel (index 0; provider mapping pending)',
                    provider='https://github.com/thuml/Time-Series-Library', license='benchmark archive/license mapping unresolved'),
}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def metadata(path):
    """Read only container bytes, column names, row counts and CSV time column."""
    path=Path(path); result={'file_sha256':sha(path),'bytes':path.stat().st_size}
    if path.suffix=='.gz':
        with gzip.open(path,'rb') as f:
            first=f.readline(); result['columns']=first.count(b',')+1
            result['rows']=int(bool(first))+sum(1 for _ in f)
        result.update(time_mode='ordinal_only_no_fabricated_timestamp',start=None,end=None)
    else:
        with path.open('rb') as f:
            header=f.readline().decode().strip().split(',');first=None;last=None;count=0
            for line in f:
                if line.strip():
                    stamp=line.split(b',',1)[0].decode();first=stamp if first is None else first;last=stamp;count+=1
        result.update(rows=count,columns=len(header)-1,column_names=header[1:],start=first,end=last,
                      time_mode='original_csv_timestamp_timezone_not_declared')
    return result

def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    old_path=ROOT/'results/v43/20260914T141030.324186Z-agent/data_manifest.json'
    old={r['source']:r for r in json.loads(old_path.read_text())}
    rows=[];windows=[]
    for name,info in SOURCES.items():
        r={'source':name,**info}; p=ROOT/info['path']
        if not p.exists():r.update(status='missing_file',split_bounds=None);rows.append(r);continue
        r.update(metadata(p)); n=r['rows']
        bounds=old[name]['split_bounds'] if name in old else dict(train=[0,int(.6*n)],dev=[int(.6*n),int(.75*n)],calibration=[int(.75*n),int(.85*n)],test=[int(.85*n),n])
        r.update(status='metadata_prepared_not_model_ready',split_bounds=bounds,
                 split_provenance='inherited_unchanged' if name in old else 'r5_preregistered_60_15_10_15',
                 prediction_labels_read=0,timezone='unknown',historical_vintage='unknown')
        r['capacity']={role:max(0,(hi-lo)//704) for role,(lo,hi) in bounds.items()}
        for role in ('train','dev'):
            lo,hi=bounds[role]
            for begin in range(lo,hi-704+1,704):
                windows.append(dict(source=name,role=role,parent=f'{name}:{begin}:{begin+704}',read_start=begin,
                                    origin=begin+512,max_target_end=begin+704,horizons=[96,192]))
        rows.append(r)
    protocol=dict(version='v431-r5-main-preparation-v1',status='prepared_not_executed',context=512,horizons=[96,192],
                  families=['chronos-bolt-base','timesfm-2.5-200m'],budgets_seconds=[.8140623268639832,3.5],
                  sources=rows,windows_metadata=windows,heldout_labels_read=0,metadata_bytes_hashed=True,
                  parent_stride=704,tracks=['complete_target_KEEP','controlled_missingness_existing_v43_recipe','verified_natural_gaps_if_available'],
                  target_rule='channel 0 inherited v43; ETT HUFL, independently confirm new provider field identity before model execution',
                  mask_rule='reuse frozen v43 observation-only masks; store concrete mask/input hashes before inference; never mask to improve candidate win rate',
                  scoring='same future positions; source/parent/variant macro MASE; origin learning scale separate',
                  release_gate='both families beat TRAIN-frozen simple controls; joint geometry same-information incremental on >=1 and non-worse other; online budget and all boundaries pass; otherwise keep sealed',
                  official_TATO=dict(trials=500,samples=500,top_k=16,context=1440,status='not_run_separate_protocol'),
                  scene_TATO=dict(trials=500,max_distinct_train_samples=500,context=512,metric='source/parent macro MSE',status='API_prepared_not_run_not_full_official_reproduction'),
                  code_sha256=sha(__file__),old_manifest_sha256=sha(old_path))
    for path in (OUT/'manifest.json',ROOT/'configs/v431-r5/main_protocol.json'):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(protocol,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':protocol['status'],'sources':[{k:r.get(k) for k in ('source','status','rows','columns','capacity')} for r in rows]},indent=2))

def validate_train_samples(samples):
    """Reject non-TRAIN, cross-boundary, duplicate IDs and malformed arrays."""
    import numpy as np
    if not samples:raise ValueError('no legal TRAIN sample')
    seen=set()
    for s in samples:
        if s['role']!='train':raise ValueError('scene search accepts TRAIN only')
        lo,hi=s['train_bounds'];x=np.asarray(s['context']);y=np.asarray(s['target']);h=int(s['horizon'])
        if not(lo<=s['read_start'] and s['read_start']+len(x)==s['origin'] and s['origin']+h<=hi):raise ValueError('TRAIN interval crossing')
        if x.shape!=(512,) or y.shape!=(h,) or h not in (96,192):raise ValueError('invalid scene shape')
        if np.isinf(x).any() or not np.isfinite(x).any() or not np.isfinite(y).any():raise ValueError('unsupported scene values')
        if s['uid'] in seen:raise ValueError('duplicate TRAIN sample id')
        seen.add(s['uid'])

def scene_search(model,samples,output,*,family,trials=500,max_samples=500,seed=101):
    """Original TATO native transformation space, searched offline on TRAIN.

    Caller owns the unique GPU lock/model lifetime and supplies audited TRAIN
    samples. This is same-backbone scene adaptation, not official full protocol.
    Online execution calls execute_frozen_scene with no target parameter.
    """
    import sys
    import numpy as np
    from types import SimpleNamespace
    sys.path.insert(0,str(ROOT/'scripts/v431_baselines'))
    import tato_adapter as adapter
    validate_train_samples(samples)
    if family not in ('bolt','timesfm'):raise ValueError('unregistered family')
    samples=sorted(samples,key=lambda s:(s['source'],s['parent'],s['uid']))
    # No duplicate upsampling to pretend there are 500 independent observations.
    indices=np.linspace(0,len(samples)-1,min(max_samples,len(samples)),dtype=int)
    samples=[samples[int(i)] for i in indices]
    if len({s['horizon'] for s in samples})!=1:raise ValueError('freeze one scene per source/horizon/track')
    import optuna
    factory,tuner_factory=adapter.load_official();identity=adapter.official_identity()
    tuner=tuner_factory.build_optuna_tuner(enqueue_param_dicts=[adapter.vanilla()],mode='train',seed=seed)
    patch=16 if family=='bolt' else 32
    distribution=tuner_factory.build_search_space(adapter.NAMES,patch_len=patch)
    out=Path(output);out.mkdir(parents=True,exist_ok=False);ledger=[];tick=time.perf_counter()
    for number in range(trials):
        trial=tuner.pick_trial(distribution);row=dict(trial=number,params=dict(trial.params),samples=[]);t=time.perf_counter()
        try:
            grouped={}
            for s in samples:
                y=np.asarray(s['target']);valid=np.isfinite(y)
                p,detail=execute_frozen_scene(model,s['context'],s['horizon'],trial.params,family)
                loss=float(np.mean((p[valid]-y[valid])**2));grouped.setdefault(s['source'],{}).setdefault(s['parent'],[]).append(loss)
                row['samples'].append(dict(uid=s['uid'],mse=loss,**detail))
            score=float(np.mean([np.mean([np.mean(v) for v in parents.values()]) for parents in grouped.values()]))
            tuner.tell(trial,score);row.update(status='completed',train_mse=score)
        except (ValueError,AssertionError,FloatingPointError) as exc:
            tuner.study.tell(trial,state=optuna.trial.TrialState.FAIL);row.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        row['seconds']=time.perf_counter()-t;ledger.append(row)
        (out/'trials.json').write_text(json.dumps(ledger,indent=2))
    good=[r for r in ledger if r['status']=='completed']
    if not good:raise RuntimeError('all scene trials failed; no fallback or fabricated forecast')
    best=min(good,key=lambda r:(r['train_mse'],r['trial']))
    result=dict(status='completed_scene_adaptation_not_full_official',params=best['params'],family=family,
                horizon=samples[0]['horizon'],seconds=time.perf_counter()-tick,official=identity,
                samples=len(samples),parents=len({s['parent'] for s in samples}),trials=trials,
                failures=len(ledger)-len(good),heldout_labels_read=0,code_sha256=sha(__file__))
    (out/'frozen_scene.json').write_text(json.dumps(result,indent=2));return result

def execute_frozen_scene(model,context,horizon,params,family):
    """Deployment API: current dirty context only, no search and no future."""
    import sys
    import numpy as np
    from types import SimpleNamespace
    sys.path.insert(0,str(ROOT/'scripts/v431_baselines'))
    import tato_adapter as adapter
    if family not in ('bolt','timesfm'):raise ValueError('unknown family')
    x=np.asarray(context,dtype=np.float64)
    if x.shape!=(512,) or horizon not in (96,192):raise ValueError('unregistered task')
    factory,_=adapter.load_official();patch=16 if family=='bolt' else 32;tick=time.perf_counter()
    p=factory.build_trial_pipeline_by_transformation_names(SimpleNamespace(params=dict(params)),model,adapter.NAMES,
             dict(pred_len=horizon,patch_len=patch,data_patch_len=patch,model_patch_len=patch),mode='test',plt=False)
    transformed=p.preprocess(adapter.bridge(x)[None,:,None])
    if not np.isfinite(transformed).all():raise FloatingPointError('nonfinite transformed input')
    raw=model.forecast(transformed,p.pred_len)
    if not np.isfinite(raw).all():raise FloatingPointError('nonfinite model output')
    final=np.asarray(p.postprocess(raw))[0,:,0]
    if final.shape!=(horizon,) or not np.isfinite(final).all():raise FloatingPointError('invalid final original-grid output')
    return final,dict(seconds=time.perf_counter()-tick,model_input_shape=list(transformed.shape),model_horizon=p.pred_len,
                      input_sha256=hashlib.sha256(x.tobytes()).hexdigest(),prediction_sha256=hashlib.sha256(final.tobytes()).hexdigest())

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args();prepare()
