#!/usr/bin/env python3
"""Build versioned CPU-only r4 ledger from verified raw predictions."""
import argparse,json,time
from pathlib import Path
from collections import Counter
import joblib,numpy as np
from introact_ts.v431_r4.trajectory_dataset import load_data,build_batch
from introact_ts.v43.cli import atomic_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=['main','generalization','financial'],default='main');p.add_argument('--train-only',action='store_true');p.add_argument('--output',default='results/v431-r4/trajectory');a=p.parse_args()
    out=Path(a.output)/a.suite;out.mkdir(parents=True,exist_ok=True)
    if (out/'status.json').exists():raise RuntimeError('Do not overwrite existing trajectory snapshot')
    tick=time.perf_counter();d=load_data(a.suite)
    ids=np.flatnonzero(d.roles!='dev') if a.train_only else np.arange(len(d.uids));summary={}
    for family in ['bolt','timesfm']:
        b,pr=build_batch(d,family,suite=a.suite,indices=ids)
        joblib.dump(b,out/(family+'.joblib'));atomic_json(out/(family+'.rows.json'),b.rows)
        byrole={}
        for role in sorted(set(b.roles)):
            z=b.subset(np.flatnonzero(b.roles==role))
            byrole[role]={'parents':len(set(z.parents)),'episodes':len(z.uids),'sources':dict(Counter(z.sources)),
              'origin_scale_branches':dict(Counter(r['origin_scale']['branch'] for r in z.rows)),
              'effective_tool_support':{t:{'parents':len(set(z.parents[m])),'episodes':int(m.sum())} for t,m in z.supported.items()},
              'fixed_learning_losses':np.dot(z.weights,z.losses).tolist(),
              'diagnostic_action_oracle_learning_loss':float(np.dot(z.weights,np.min(z.losses,axis=1))),
              'action_p95_seconds':np.quantile(z.action_costs,.95,axis=0).tolist(),
              'tool_p95_seconds':{t:float(np.quantile(v,.95)) for t,v in z.tool_costs.items()}}
        summary[family]={'roles':byrole,'provenance':pr}
    atomic_json(out/'support.json',summary);atomic_json(out/'status.json',{'status':'completed','seconds':time.perf_counter()-tick,'suite':a.suite,'train_only':a.train_only,'note':'Offline supervision loader accesses previously used TRAIN/DEV archives; train-only output performs no DEV strategy evaluation. Heldout calibration/test not accessed.'})
if __name__=='__main__':main()
