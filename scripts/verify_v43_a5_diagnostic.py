#!/usr/bin/env python3
"""Recompute missed-eta task scores and pool oracles from raw saved forecasts."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import array_hash
from introact_ts.v43.worker_protocol import verify_response


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path)
    root=parser.parse_args().run;old=Path('results/v43/20260914T131623.999847Z-p2')
    destination=root/'independent_verification.json';assert not destination.exists()
    rows=json.loads((root/'candidate_diagnostics.json').read_text())
    labels=json.loads((root/'task_labels.json').read_text())
    scales=json.loads((old/'mase_scales.json').read_text())
    oracle=json.loads((root/'oracle_scope_comparison.json').read_text())
    aliases=json.loads((old/'forecast_aliases.json').read_text())
    report=dict(status='running',new_future_labels_read=0,heldout_labels_read=0,verifier_sha256=file_hash(__file__))
    try:
        for path in root.glob('*.request.json'):
            stem=path.name.removesuffix('.request.json');request=json.loads(path.read_text());response=json.loads((root/(stem+'.response.json')).read_text())
            with np.load(root/(stem+'.predictions.npz')) as points,np.load(root/(stem+'.predictions.raw.npz')) as raw:
                values=[points[f'row_{i}'] for i in range(len(request['rows']))];verify_response(request,response,values)
                for i,(p,r) in enumerate(zip(values,response['rows'])):
                    q=raw[f'row_{i}'];assert array_hash(q)==r['raw_hash'];np.testing.assert_array_equal(p,q[0,4])
        scores={};groups=defaultdict(lambda:defaultdict(list));rejected=[]
        with np.load(root/'forecasts.npz') as forecasts,np.load(old/'forecasts.npz') as previous,np.load(old/'targets.npz') as targets,np.load(root/'candidates.npz') as candidates,np.load(old/'candidates.npz') as old_candidates:
            for row in labels:
                uid,arm=row['episode_uid'],row['arm'];y,m=targets[uid+'_values'],targets[uid+'_mask'];p=forecasts[uid+'_'+arm]
                mae=float(abs(p[m]-y[m]).mean());np.testing.assert_allclose([mae,mae/scales[row['source']]],[row['mae'],row['mase']],rtol=1e-12,atol=1e-12)
                scores[uid,arm]=mae
            for uid,row in rows.items():
                y,m=targets[uid+'_values'],targets[uid+'_mask']
                losses={a:float(abs(previous[aliases[uid+'_'+a]][m]-y[m]).mean())/scales[row['source']] for a in ('A0_NATIVE','A0_FFILL','A2_SINGLE','A3_COV','A4_RIDGE_CONTEXT','A5_STATIC')}
                for a in losses:assert array_hash(old_candidates[uid+'_'+a])==array_hash(old_candidates[aliases[uid+'_'+a]])
                base=min(v for a,v in losses.items() if a!='A5_STATIC');static=min(base,losses['A5_STATIC']);best=static
                if 'variants' in row:
                    chosen={0.:'ETA_0',.5:'ETA_HALF',1.:'ETA_1'}[row['static_record']['eta']]
                    np.testing.assert_array_equal(candidates[uid+'_'+chosen],old_candidates[uid+'_A5_STATIC'])
                    for arm,variant in row['variants'].items():assert array_hash(candidates[uid+'_'+arm])==variant['candidate_hash']
                    arm=min(row['variants'],key=lambda a:scores[uid,a]);gain=scores[uid,chosen]-scores[uid,arm]
                    if gain>1e-9:rejected.append(uid)
                    best=min(base,scores[uid,arm]/scales[row['source']])
                for name,value in (('fixed5',base),('plus_static',static),('plus_all_eta',best)):groups[row['source']][name].append(value)
        for source,values in groups.items():
            for name,values in values.items():np.testing.assert_allclose(np.mean(values),oracle['by_source'][source][name],rtol=1e-12,atol=1e-12)
        recorded=json.loads((root/'beneficial_static_rejected.json').read_text())
        assert set(rejected)=={r['episode_uid'] for r in recorded}
        report.update(status='completed',task_labels=len(labels),new_raw_forecasts=92,missed_eta_alternatives=len(rejected),oracle_scopes_verified=3,promotion=False)
    except Exception as exc:report.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:destination.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
