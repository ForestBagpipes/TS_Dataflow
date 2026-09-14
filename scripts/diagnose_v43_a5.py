#!/usr/bin/env python3
"""Rebuild rejected residual strengths from audited cached real imputation."""
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import numpy as np
import yaml
from introact_ts.v43.batch_executor import make_executor
from introact_ts.v43.candidates import _fit_predict
from introact_ts.v43.cli import atomic_json, code_manifest
from introact_ts.v43.frozen_archive import FrozenP2Archive
from introact_ts.v43.schemas import Candidate, array_hash, require, verify_impute, json_hash
from introact_ts.v43.task_labels import TaskTarget, evaluate_pair


def main():
    root=Path('/home/vipuser/work/work2')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out=root/'results/v43'/(stamp+'-a5-diagnostic');out.mkdir()
    config=yaml.safe_load((root/'configs/v43/p2_first_dev.yaml').read_text())
    start=time.perf_counter();code=code_manifest()
    status=dict(status='running',scope='posthoc_rejected_eta_diagnostic',new_future_labels_read=0,heldout_labels_read=0)
    atomic_json(out/'code_manifest.json',code)
    atomic_json(out/'status.json',status)
    (out/'resolved_config.yaml').write_text(yaml.safe_dump(config,sort_keys=False))
    try:
        gate=json.loads(Path(config['runtime']['semantic_gate']).read_text())
        require(gate['status']=='completed' and gate['code_hash']==code['hash'] and gate['config_hash']==json_hash(config),'CPU gate stale')
        archive=FrozenP2Archive(root/'results/v43/20260914T131623.999847Z-p2',root/'docs/v43_p2_evidence_20260914.json')
        atomic_json(out/'imported_producer.json',archive.provenance)
        model=json.loads(Path(config['models']['manifest']).read_text());atomic_json(out/'model_manifest.json',model)
        call,costs=make_executor(config,out,code,atomic_json,status,model)
        plans,evidence=archive.read('mask_plans'),archive.read('candidate_evidence')
        arrays,rows,predictions,requests={},{},{},defaultdict(list)
        for uid,e in archive.contexts.items():
            selected=evidence[uid]['A5_STATIC'];missing=np.isnan(e.target)
            coverage=float(np.isfinite(e.covariates[missing]).mean()) if missing.any() else None
            rows[uid]=dict(episode_uid=uid,source=e.source,parent_group=e.parent_group,horizon=e.horizon,condition=archive.meta[uid]['condition'],
                          missing_count=int(missing.sum()),covariate_observed_fraction_at_gap=coverage,static_record=selected)
            if selected['status']!='completed':continue
            blocks=[np.isin(np.arange(len(e.target)),indices) for indices in plans[uid]['blocks']]
            ys,zs=[],[]
            for block in blocks:
                view=e.target.copy();view[block]=np.nan
                key=array_hash(view);require(key in archive.base_predictions[uid],'missing cached single-block input')
                ys.append(e.target[block]-archive.base_predictions[uid][key][block]);zs.append(e.covariates[block])
            delta=_fit_predict(np.concatenate(zs),np.concatenate(ys),e.covariates[missing],32,8,1.)
            base=archive.candidates[uid+'_A2_SINGLE']
            rows[uid].update(delta_l1=float(np.abs(delta).mean()),delta_linf=float(np.abs(delta).max()),base_hash=array_hash(base),variants={})
            for eta,name in ((0.,'ETA_0'),(.5,'ETA_HALF'),(1.,'ETA_1')):
                x=e.target.copy();x[missing]=base[missing]+eta*delta
                verify_impute(e,Candidate(uid,name,x));key=uid+'_'+name;arrays[key]=x
                imported=None
                for arm in archive.read('arm_manifest')['executed']:
                    if array_hash(x)==array_hash(archive.candidates[uid+'_'+arm]):imported=arm;break
                rows[uid]['variants'][name]=dict(eta=eta,candidate_hash=array_hash(x),changed_from_base=bool(array_hash(x)!=array_hash(base)),
                                                gap_delta_l1=float(np.abs(x[missing]-base[missing]).mean()),imported_forecast_arm=imported)
                if imported is not None:predictions[key]=archive.forecast(uid,imported)
                else:requests[e.horizon].append((e,name,x))
                if eta==selected['eta']:
                    require(array_hash(x)==array_hash(archive.candidates[uid+'_A5_STATIC']),'cached reconstruction disagrees with original A5')
        atomic_json(out/'candidate_diagnostics.json',rows)
        with (out/'candidates.npz').open('xb') as f:np.savez(f,**arrays)
        for horizon,reqs in requests.items():
            preds=call('bolt','forecast','none',reqs,f'h{horizon}-rejected')
            for (e,arm,_),pred in zip(reqs,preds):predictions[e.uid+'_'+arm]=pred
        with (out/'forecasts.npz').open('xb') as f:np.savez(f,**predictions)
        # Reuse already-opened dev labels only after all new forecasts pass.
        targets=archive.arrays('targets.npz');scales=archive.read('mase_scales');labels=[];rejected=[]
        for uid,row in rows.items():
            if 'variants' not in row:continue
            target=TaskTarget(uid,'dev',targets[uid+'_values'],targets[uid+'_mask']);keep=archive.forecast(uid,'A0_NATIVE')
            own=[]
            for arm,v in row['variants'].items():
                pred=predictions[uid+'_'+arm]
                label=dict(evaluate_pair(target,keep,pred,scale=scales[row['source']]),arm=arm,**{k:row[k] for k in ('source','parent_group','horizon','condition')})
                v['forecast_changed_from_base']=bool(array_hash(pred)!=array_hash(archive.forecast(uid,'A2_SINGLE')))
                v['forecast_l1_delta']=float(np.abs(pred-archive.forecast(uid,'A2_SINGLE')).mean())
                labels.append(label);own.append(label)
            selected_name={0.:'ETA_0',.5:'ETA_HALF',1.:'ETA_1'}[row['static_record']['eta']]
            static=next(x for x in own if x['arm']==selected_name);best=min(own,key=lambda x:x['mae'])
            if best['mae']<static['mae']-1e-9:rejected.append(dict(episode_uid=uid,source=row['source'],parent_group=row['parent_group'],horizon=row['horizon'],static_eta=row['static_record']['eta'],best_arm=best['arm'],missed_task_gain=static['mae']-best['mae']))
        atomic_json(out/'candidate_diagnostics.json',rows);atomic_json(out/'task_labels.json',labels);atomic_json(out/'beneficial_static_rejected.json',rejected)
        status.update(status='completed',supported_episodes=sum('variants' in r for r in rows.values()),additional_tsicl_calls=0,additional_bolt_calls=sum(len(r) for r in requests.values()),
                      static_rejected_better_episodes=len(rejected),static_rejected_better_parents=len({r['parent_group'] for r in rejected}),promotion=False)
    except Exception as exc:
        status.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:
        status['runtime_seconds']=time.perf_counter()-start
        atomic_json(out/'status.json',status);atomic_json(root/'results/v43/a5_diagnostic_status.json',dict(status,run=str(out)))
        print(json.dumps(dict(out=str(out),**status)),flush=True)


if __name__=='__main__':main()
