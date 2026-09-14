#!/usr/bin/env python3
"""Audit actual decisions, task errors, accounting, partitions and paired dev CIs."""
import argparse
from collections import defaultdict,Counter
import hashlib
import json
from pathlib import Path
import time
import joblib
import numpy as np
from introact_ts.v43.agent_fit import AgentDataset
from introact_ts.v43.agent_inputs import POOL,TOOLS
from introact_ts.v43.agent_policy import choose,EvidenceState
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import array_hash
from introact_ts.v43.worker_protocol import verify_response


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);root=parser.parse_args().run
    out=root/'agent';destination=out/'independent_verification.json';assert not destination.exists()
    report=dict(status='running',started_at=time.time(),new_future_labels_read=0,heldout_labels_read=0,
                verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    try:
        data=AgentDataset(root);manifest=json.loads((out/'model_manifest.json').read_text());assert file_hash(out/'models.joblib')==manifest['model_sha256']
        models=joblib.load(out/'models.joblib');decisions=json.loads((out/'decisions.json').read_text());summary=json.loads((out/'comparison.json').read_text())
        dev={u for u,m in data.meta.items() if m['role']=='dev'}
        policy_ids=defaultdict(set)
        for row in decisions:policy_ids[row['policy']].add(row['episode_uid'])
        assert all(ids==dev for ids in policy_ids.values())
        grouped,parent_values=defaultdict(list),defaultdict(dict)
        with np.load(root/'forecasts.npz',allow_pickle=False) as forecasts,np.load(root/'targets.npz',allow_pickle=False) as targets:
            for row in decisions:
                uid,arm=row['episode_uid'],row['arm'];e=data.episodes[uid]
                y,m=targets[uid+'_values'],targets[uid+'_mask'];p=forecasts[uid+'_'+arm]
                assert np.array_equal(m,np.isfinite(y)) and np.isfinite(p).all()
                mae=float(np.abs(p[m]-y[m]).mean());mase=mae/data.read('mase_scales')[e.source]
                np.testing.assert_allclose([mae,mase],[row['mae'],row['mase']],rtol=1e-12,atol=1e-12)
                assert array_hash(data.pools[uid][arm])==row['candidate_hash']
                assert len(row['history'])<=2 and len(set(row['history']))==len(row['history'])
                charge=sum(data.tool_costs[uid][t] for t in row['history'])
                np.testing.assert_allclose(charge,row['tool_seconds'],rtol=1e-12,atol=1e-12)
                expected=(data.direct_costs[uid][arm] if row.get('direct_cost') else data.base_costs[uid])+charge+row['selection_seconds']
                np.testing.assert_allclose(expected,row['total_governance_seconds'],rtol=1e-12,atol=1e-12)
                assert row['budget_overrun']==(row['budget'] is not None and charge>row['budget']+1e-12)
                if row['policy'].startswith(('LEARNED_','FIXED_MASK_HISTORY_','FIXED_HISTORY_MASK_')) or row['policy']=='ALL_EVIDENCE':
                    state=EvidenceState()
                    for step in row['trace']:
                        assert list(state.history)==step['history']
                        before,_=choose(e,data.pools[uid],state,models['utility']);assert before==step['selected_before']
                        if step['tool'] is not None:state=state.acquire(step['tool'],data.evidence[uid][step['tool']])
                    final,_=choose(e,data.pools[uid],state,models['utility']);assert final==arm
                grouped[row['policy'],row['source'],row['horizon'],row['condition']].append(row)
                parent_values[row['source'],row['parent_group']].setdefault(row['policy'],[]).append(mase)
        for name in policy_ids:
            rows=[v for k,v in grouped.items() if k[0]==name]
            for metric in ('mae','mase','task_harm','total_governance_seconds','tool_seconds'):
                value=float(np.mean([np.mean([x[metric] for x in v]) for v in rows]))
                np.testing.assert_allclose(value,summary['policies'][name][metric],rtol=1e-12,atol=1e-12)
        ledger=json.loads((out/'tool_value_training_ledger.json').read_text())
        for row in ledger:
            uid=row['episode_uid'];assert data.meta[uid]['role']=='acquisition_fit'
            gain=data.labels[uid,row['before']]['mase']-data.labels[uid,row['after']]['mase']
            np.testing.assert_allclose(row['value_label'],gain-manifest['penalty']*data.tool_costs[uid][row['tool']],rtol=1e-12,atol=1e-12)
        worker_rows=0;raw_count=0
        for path in sorted(root.glob('*.request.json')):
            shard=path.name.removesuffix('.request.json');request=json.loads(path.read_text());response=json.loads((root/(shard+'.response.json')).read_text())
            with np.load(root/(shard+'.predictions.npz'),allow_pickle=False) as predictions,np.load(root/(shard+'.predictions.raw.npz'),allow_pickle=False) as raw:
                values=[predictions[f'row_{i}'] for i in range(len(request['rows']))]
                verify_response(request,response,values)
                for i,(q,r,p) in enumerate(zip(request['rows'],response['rows'],values)):
                    quantile=raw[f'row_{i}'];assert array_hash(quantile)==r['raw_hash'] and np.isfinite(quantile).all()
                    if request['task']=='forecast':np.testing.assert_array_equal(p,quantile[0,4])
                    else:
                        with np.load(q['array_path'],allow_pickle=False) as payload:
                            x=payload['target'];observed=np.isfinite(x)
                            assert p[observed].tobytes()==x[observed].tobytes()
                            np.testing.assert_array_equal(p[~observed],quantile[0,0,~observed,1])
                    raw_count+=1
                worker_rows+=len(values)
        # Conditional within-source parent resampling preserves all six variants.
        # It does not pretend the lone USTS dev parent establishes domain generality.
        names=sorted(policy_ids);sources=sorted({k[0] for k in parent_values});rng=np.random.default_rng(101)
        arrays={s:np.array([[np.mean(v[n]) for n in names] for (source,_),v in parent_values.items() if source==s]) for s in sources}
        draws=np.zeros((2000,len(names)))
        for values in arrays.values():
            indices=rng.integers(0,len(values),size=(2000,len(values)));draws+=values[indices].mean(axis=1)/len(sources)
        references=['TRAIN_BEST_FIXED','DIRTY_SELECTOR','ALL_EVIDENCE','FIXED_MASK_HISTORY_one_tool','FIXED_HISTORY_MASK_one_tool']
        comparisons={}
        for name in ['ALL_EVIDENCE','LEARNED_one_tool','LEARNED_two_tools']:
            comparisons[name]={}
            for reference in references:
                gain=draws[:,names.index(reference)]-draws[:,names.index(name)]
                comparisons[name][reference]=dict(mean_mase_gain=summary['policies'][reference]['mase']-summary['policies'][name]['mase'],
                    conditional_parent_bootstrap_95_interval=np.quantile(gain,[.025,.975]).tolist())
        atomic=dict(scope='exploratory_within_source_parent_bootstrap',unit='source_parent_all_horizons_conditions_together',repeats=2000,seed=101,
                    limitation='conditional on these three sources; USTS has one parent; not confirmatory or cross-domain coverage',comparisons=comparisons)
        (out/'paired_comparisons.json').write_text(json.dumps(atomic,indent=2)+'\n')
        report.update(status='completed',dev_parents=len(parent_values),dev_episodes=len(dev),policy_count=len(policy_ids),decisions=len(decisions),
                      verified_worker_rows=worker_rows,verified_raw_quantile_rows=raw_count,observed_write_violations=0,
                      partition_counts=data.partition_counts,tool_training_rows=len(ledger),promotion=False)
    except Exception as exc:report.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:
        report['finished_at']=time.time();destination.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
