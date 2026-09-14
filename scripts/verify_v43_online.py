#!/usr/bin/env python3
"""Independent post-execution audit of actual sequential online replay."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import joblib
import numpy as np
from introact_ts.v43.agent_fit import AgentDataset
from introact_ts.v43.agent_policy import execute_policy
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import array_hash
from introact_ts.v43.worker_protocol import verify_response


def main():
    parser=argparse.ArgumentParser();parser.add_argument('online',type=Path)
    out=parser.parse_args().online.resolve();root=out.parent
    destination=out/'independent_verification.json';assert not destination.exists()
    report=dict(status='running',heldout_labels_read=0,verifier_sha256=file_hash(__file__))
    try:
        status=json.loads((out/'status.json').read_text());assert status['status']=='completed'
        barrier=json.loads((out/'label_access_barrier.json').read_text())
        assert barrier['denied_preflight']==6 and barrier['denied_unexpected']==0
        assert file_hash(out/'forecasts.npz')==barrier['final_forecasts_sha256']
        assert (out/'forecasts.npz').stat().st_mtime <= datetime.fromisoformat(barrier['released_at']).timestamp()
        data=AgentDataset(root)
        manifest=json.loads((root/'agent/model_manifest.json').read_text())
        assert file_hash(root/'agent/models.joblib')==manifest['model_sha256']
        models=joblib.load(root/'agent/models.joblib')
        rows=json.loads((out/'decisions.json').read_text())
        protocol=json.loads((out/'protocol.json').read_text())
        chosen=[]
        for source in sorted({m['source'] for m in data.meta.values()}):
            uids=[u for u,m in data.meta.items() if m['role']=='dev' and m['source']==source and m['horizon']==96 and m['condition']=='target_block_10']
            chosen+=sorted(uids,key=lambda u:data.meta[u]['raw_start'])[:3]
        assert chosen==protocol['uids']==[r['episode_uid'] for r in rows]
        startup=sum(r['wall_seconds'] for r in json.loads((out/'service_startup.json').read_text()))
        with np.load(root/'targets.npz',allow_pickle=False) as targets,np.load(out/'forecasts.npz',allow_pickle=False) as forecasts,np.load(root/'forecasts.npz',allow_pickle=False) as old:
            for row in rows:
                uid=row['episode_uid'];acquired=row['acquired']
                def fetch(tool):return acquired[tool]['evidence'],acquired[tool]['actual_seconds']
                replay=execute_policy(data.episodes[uid],data.pools[uid],models['utility'],models['acquisition'],fetch,manifest['estimated_tool_costs'],manifest['budgets']['two_tools'])
                assert replay['arm']==row['arm'] and replay['history']==row['history']
                assert replay['budget_overrun']==row['budget_overrun']
                np.testing.assert_allclose(replay['tool_seconds'],row['tool_seconds'],rtol=1e-12,atol=1e-12)
                for tool,record in acquired.items():
                    for arm in manifest['pool']:
                        np.testing.assert_allclose(np.array(record['evidence'][arm],dtype=float),np.array(data.evidence[uid][tool][arm],dtype=float),rtol=1e-6,atol=1e-5)
                y,m=targets[uid+'_values'],targets[uid+'_mask'];p=forecasts[uid]
                np.testing.assert_allclose(p,old[uid+'_'+row['arm']],rtol=1e-6,atol=1e-5)
                np.testing.assert_allclose(float(abs(p[m]-y[m]).mean()),row['mae'],rtol=1e-12,atol=1e-12)
                expected=row['base_seconds']+row['tool_seconds']+row['selection_seconds']+startup/len(rows)
                np.testing.assert_allclose(expected,row['total_governance_seconds'],rtol=1e-12,atol=1e-12)
        worker_rows=0
        for path in sorted(out.glob('case*.request.json')):
            stem=path.name.removesuffix('.request.json');request=json.loads(path.read_text());response=json.loads((out/(stem+'.response.json')).read_text())
            assert response['service_sha256']==file_hash('scripts/serve_v43_model.py')
            with np.load(out/(stem+'.predictions.npz'),allow_pickle=False) as points,np.load(out/(stem+'.predictions.raw.npz'),allow_pickle=False) as raw:
                values=[points[f'row_{i}'] for i in range(len(request['rows']))];verify_response(request,response,values)
                for i,(q,r,p) in enumerate(zip(request['rows'],response['rows'],values)):
                    quantile=raw[f'row_{i}'];assert array_hash(quantile)==r['raw_hash']
                    if request['task']=='forecast':np.testing.assert_array_equal(p,quantile[0,4])
                    else:
                        with np.load(q['array_path'],allow_pickle=False) as payload:
                            x=payload['target'];observed=np.isfinite(x)
                            assert p[observed].tobytes()==x[observed].tobytes()
                            np.testing.assert_array_equal(p[~observed],quantile[0,0,~observed,1])
                worker_rows+=len(values)
        report.update(status='completed',episodes=len(rows),verified_worker_rows=worker_rows,actual_cost_policy_replays=len(rows),
            budget_overruns=sum(r['budget_overrun'] for r in rows),offline_full_trace_agreements=sum(r['decision_agreement'] for r in rows),promotion=False)
    except Exception as exc:report.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:destination.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
