#!/usr/bin/env python3
"""Only missing target-aligned history views; one sequential GPU producer."""
from collections import defaultdict
from datetime import datetime,timezone
import json,os,time
from pathlib import Path
import numpy as np
import yaml
from introact_ts.v43.agent_collect import Collector
from introact_ts.v43.agent_inputs import POOL,context_scale
from introact_ts.v43.cli import atomic_json,code_manifest
from introact_ts.v43.schemas import array_hash
from introact_ts.v431.data import SprintData,aligned_views

def main():
    data=SprintData();root=data.root/'history';root.mkdir(exist_ok=False)
    old=data.old;config=yaml.safe_load((old.root/'resolved_config.yaml').read_text());code=code_manifest();model=old.read('model_manifest')
    status=dict(status='running',phase='history_views',pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat(),heldout_labels_read=0,new_future_labels_read=0)
    atomic_json(root/'status.json',status);atomic_json(root/'model_manifest.json',model);atomic_json(root/'code_manifest.json',code)
    (root/'resolved_config.yaml').write_text(yaml.safe_dump(config));start=time.perf_counter()
    try:
        collector=Collector(config,root,code,status,model)
        full,short,origins=[],[],{}
        for uid in data.uids:
            a,b,r=aligned_views(old.episodes[uid]);full.append(a);short.append(b);origins[uid]=dict(full=a.uid,short=b.uid,cutoff=r)
            assert np.array_equal(a.target,b.target,equal_nan=True) and len(a.target)==512-old.episodes[uid].horizon
        atomic_json(root/'view_manifest.json',origins)
        pools,cost,_=collector.pools(full,'aligned')
        spools={s.uid:pools[f.uid] for f,s in zip(full,short)}
        status['phase']='same_origin32';atomic_json(root/'status.json',status)
        p32,c32=collector.forecasts(short,spools,'same32')
        status['phase']='target_horizon';atomic_json(root/'status.json',status)
        ph,ch=collector.forecasts(full,pools,'targeth')
        evidence={};costs={};prediction_store={}
        for condition,views,forecasts,fcost,prefix in [('same_origin32',short,p32,c32,'same32'),('target_horizon',full,ph,ch,'targeth')]:
            ev,co={},{}
            for uid,view,fullview in zip(data.uids,views,full):
                t=time.perf_counter();e=old.episodes[uid];r=origins[uid]['cutoff'];y=e.target[r:r+view.horizon];mask=np.isfinite(y)
                keep=forecasts[view.uid,'A0_NATIVE'];base=float(abs(keep[mask]-y[mask]).mean()) if mask.any() else None
                ev[uid]={a:[(base-float(abs(forecasts[view.uid,a][mask]-y[mask]).mean()))/context_scale(e) if mask.any() else None,0. if mask.any() else None,float(mask.mean())] for a in POOL}
                unique={collector.forecast_aliases[prefix,view.uid,a]:fcost[view.uid,a] for a in POOL}
                co[uid]=cost[fullview.uid]+sum(unique.values())+time.perf_counter()-t
                for a in POOL:prediction_store[condition+'_'+uid+'_'+a]=forecasts[view.uid,a]
            evidence[condition]=ev;costs[condition]=co
        atomic_json(root/'evidence.json',evidence);atomic_json(root/'tool_costs.json',costs)
        with (root/'forecasts.npz').open('xb') as f:np.savez(f,**prediction_store)
        atomic_json(root/'candidate_hashes.json',{u:{a:array_hash(v) for a,v in p.items()} for u,p in pools.items()})
        status.update(status='completed',episodes=len(data.uids),phase='complete',governance_reused_between_conditions=True,imputation_calls=sum(x['n_requests'] for x in collector.worker_costs if x['task']=='impute'),forecast_calls=sum(x['n_requests'] for x in collector.worker_costs if x['task']=='forecast'))
    except Exception as exc:status.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:status['runtime_seconds']=time.perf_counter()-start;atomic_json(root/'status.json',status);print(json.dumps(status),flush=True)

if __name__=='__main__':main()
