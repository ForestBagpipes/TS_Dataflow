#!/usr/bin/env python3
"""Independent post-run audit; never executes models or changes policy artifacts."""
import json,hashlib
from pathlib import Path
from collections import Counter
import numpy as np
import joblib
from introact_ts.v43.schemas import array_hash
from v431_r3_statistics import macro

ROOT=Path('results/v431-r5')
POOL=('A0_NATIVE','A0_FFILL','A2_SINGLE','A3_COV','A4_RIDGE_CONTEXT')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def aggregate(rows):
    times=[r['hot_request_seconds'] for r in rows]
    return {'requests':len(rows),'mean_seconds':float(np.mean(times)),'p50_seconds':float(np.quantile(times,.5)),
            'p95_seconds':float(np.quantile(times,.95)),'max_seconds':max(times),
            'overruns':sum(r['hot_request_seconds']>r['budget'] for r in rows),
            'nonstop':sum(r['actual_versions']>1 for r in rows),'failures':sum(bool(r['failure']) for r in rows),
            'trial_versions':sum(r['actual_versions'] for r in rows),
            'actual_forecasts':sum(r['actual_forecast_calls'] for r in rows)}

def main():
    result={'audit_scope':'post-evaluation numerical and invoice audit; no additional inference or hidden split read',
            'families':{},'source_sha256':sha(Path(__file__))}
    context_paths={'main':Path('results/v43/20260914T141030.324186Z-agent/contexts.npz'),
                   'financial':Path('results/v431-r2/financial-observation-index-r1/contexts.npz')}
    contexts={s:np.load(p,allow_pickle=False) for s,p in context_paths.items()}
    for family in ('bolt','timesfm'):
        directory=ROOT/('online-'+family);rows=read(directory/'decisions.json');arrays=np.load(directory/'live_arrays.npz')
        datasets={s:joblib.load(ROOT/'data'/s/(family+'.joblib')) for s in ('main','financial')}
        index={s:{str(u):i for i,u in enumerate(d['batch'].uids)} for s,d in datasets.items()}
        off={}
        for suite in ('dev','financial'):
            off[suite]={r['episode_uid']+r['policy']:r for r in read(ROOT/'evaluation'/suite/'decisions.json') if r['family']==family}
        checks=[];clock_changes=[];failures=[];dtype=Counter();raw_count=0;scored=[]
        for response_path in sorted((directory/'service').glob('r3-*-forecast.response.json')):
            response=read(response_path)
            predpath=response_path.with_name(response_path.name.replace('.response.json','.predictions.npz'))
            with np.load(predpath) as predicted:
                for j,record in enumerate(response['rows']):
                    p=predicted['row_'+str(j)]
                    assert array_hash(p)==record['prediction_hash']
                    assert len(p)==response['horizon'] and np.isfinite(p).all()
                    assert record['input_hash'] and response['model_revision']
                    raw_count+=1
        for r in rows:
            case=r['case_id'];uid=r['episode_uid'];a=r['controller']['action'];p=arrays[case+'_prediction'];candidate=arrays[case+'_candidate']
            assert len(p)==r['horizon'] and np.isfinite(p).all()
            assert array_hash(p)==r['final']['prediction_hash']
            assert array_hash(candidate)==r['final']['input_hash']
            executed=[t for t in r['executed_trials'] if t['action']==a]
            assert executed and executed[0]['identity']['prediction_hash']==array_hash(p)
            assert executed[0]['input_hash']==array_hash(candidate)
            response=read(directory/(case+'.response.json'))
            np.testing.assert_array_equal(np.asarray(response['prediction'],dtype=response['dtype']),p)
            assert response['action']==a and response['input_hash']==array_hash(candidate)
            d=datasets[r['suite']];position=index[r['suite']][uid];expected=d['predictions'][position][a]
            visible=np.array([r['visible_features'][name] if r['visible_features'][name] is not None else np.nan for name in d['batch'].free_names])
            np.testing.assert_allclose(visible,d['batch'].visible[position],rtol=0,atol=0,equal_nan=True)
            difference=float(np.max(np.abs(p.astype(np.float64)-expected.astype(np.float64))))
            assert np.allclose(p,expected,rtol=1e-6,atol=1e-5)
            raw=contexts[r['suite']][uid+'_target'];observed=np.isfinite(raw)
            np.testing.assert_array_equal(candidate[observed],raw[observed])
            dtype[str(p.dtype)+' vs cache '+str(expected.dtype)]+=1
            assert r['budget_overrun']==(r['hot_request_seconds']>r['budget'])
            trial_seconds=sum(t['governance_seconds']+t['forecast_seconds'] for t in r['executed_trials'])
            assert r['hot_request_seconds']+1e-8>=trial_seconds,'Trial phase fee exceeds request wall'
            assert r['actual_forecast_calls']==sum(not t['identity']['within_request_prediction_reuse'] for t in r['executed_trials'])
            checks.append(dict(case_id=case,numeric_prediction_max_abs_difference=difference,
                               final_action=a,actual_forecasts=r['actual_forecast_calls'],executed_versions=len(r['executed_trials']),
                               trial_seconds=trial_seconds,other_request_seconds=r['hot_request_seconds']-trial_seconds))
            if not r['controlled']:
                old=off['dev' if r['suite']=='main' else 'financial'][uid+'R5_'+r['budget_name']]
                loss=d['batch'].report_losses[position]
                ref=r['controller']['reference_action']
                assert abs(float(loss[a])-r['mase'])<1e-12
                scale=d['batch'].rows[position]['outer_report_scale']
                assert abs(r['mae']/float(scale)-r['mase'])<1e-10
                condition_track='complete_observed' if observed.all() else ('controlled_deletion' if r['condition']!='raw' else 'original_nan_cause_unverified')
                scored.append(dict(case_id=case,episode_uid=uid,source=r['source'],parent_group=r['parent_group'],
                    horizon=r['horizon'],condition=r['condition'],condition_track=condition_track,suite=r['suite'],budget_name=r['budget_name'],
                    actual_action=POOL[a],reference_action=POOL[ref],mase=float(loss[a]),keep_mase=float(loss[0]),
                    reference_free_mase=float(loss[ref]),actual_minus_keep=float(loss[a]-loss[0]),
                    actual_minus_reference=float(loss[a]-loss[ref]),mae=r['mae'],report_scale=float(scale)))
                if old['arm']!=r['final']['arm']:
                    clock_changes.append(dict(case_id=case,episode_uid=uid,budget=r['budget'],offline_action=old['arm'],
                      online_action=r['final']['arm'],offline_seconds=old['total_seconds'],online_seconds=r['hot_request_seconds'],
                      reason=r['controller']['reason'],failure=r['failure'],offline_queries=old['trace']['queried_actions'],online_queries=r['controller']['queried_actions'],visible_features_equal=True,offline_mase=old['mase'],online_mase=r['mase']))
            if r['failure'] or r['budget_overrun']:
                failures.append(dict(case_id=case,controlled=r['controlled'],episode_uid=uid,budget=r['budget'],
                    seconds=r['hot_request_seconds'],reason=r['controller']['reason'],failure=r['failure'],
                    executed_trials=r['executed_trials'],controller_trace=r['controller']['trace']))
        controls={r['case_id']:r for r in rows if r['controlled'] and not r['pilot']}
        assert controls['controlled-complete']['controller']['action']==0
        assert controls['controlled-complete']['actual_versions']==1
        assert controls['controlled-budget-zero']['budget_overrun'] and controls['controlled-budget-zero']['actual_versions']==1
        fault=controls['controlled-failure-after-trial']
        assert fault['actual_versions']==2 and fault['controller']['action']==fault['controller']['reference_action'] and fault['failure']
        barrier=read(directory/'visibility_barrier.json');assert barrier['denied_preflight']==5 and barrier['unexpected']==0 and not barrier['open']
        assert barrier['all_final_predictions_saved'] and barrier['before_evaluator_open']
        account=read(directory/'process_accounting.json');startup=read(directory/'service/service_startup.json')
        hot=sum(r['hot_request_seconds'] for r in rows);cold=sum(x['wall_seconds'] for x in startup)
        assert abs(hot-account['hot_request_seconds'])<1e-8 and abs(cold-account['model_startup_seconds'])<1e-8
        assert abs(account['process_wall_seconds']-hot-cold-account['remaining_overhead_seconds'])<1e-8
        natural=[r for r in rows if not r['controlled']]
        score_tables=[]
        for suite in ('main','financial'):
            for budget in ('low','high'):
                group=[r for r in scored if r['suite']==suite and r['budget_name']==budget]
                for condition in ['all']+sorted({r['condition_track'] for r in group}):
                    rr=group if condition=='all' else [r for r in group if r['condition_track']==condition]
                    score_tables.append(dict(suite=suite,budget=budget,condition=condition,episodes=len(rr),
                       parents=len({r['parent_group'] for r in rr}),**{k:macro(rr,k) for k in ('mase','keep_mase','reference_free_mase','actual_minus_keep','actual_minus_reference')}))
        result['families'][family]={'actual_online_score_tables':score_tables,'actual_online_scored_rows':scored,'checked_requests':len(rows),'raw_forecast_response_rows':raw_count,
          'numeric_cache_max_abs_difference':max(x['numeric_prediction_max_abs_difference'] for x in checks),
          'dtype_pairs':dict(dtype),'natural':aggregate(natural),
          'natural_by_budget':{b:aggregate([r for r in natural if r['budget_name']==b]) for b in ('low','high')},
          'natural_financial':aggregate([r for r in natural if r['suite']=='financial']),
          'controlled_cases_passed':['complete_KEEP','zero_budget_not_zero_cost','real_trial_then_injected_failure'],
          'offline_online_action_changes':clock_changes,'failures_and_overruns':failures,
          'request_checks':checks,'visibility_barrier':barrier,'process_accounting':account,
          'input_sha256':{n:sha(directory/n) for n in ('decisions.json','live_arrays.npz','visibility_barrier.json','protocol.json')}}
    for v in contexts.values():v.close()
    (ROOT/'statistics').mkdir(exist_ok=True)
    (ROOT/'statistics/online_audit.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({f:{'natural':r['natural'],'action_changes':len(r['offline_online_action_changes']),'max_abs':r['numeric_cache_max_abs_difference']} for f,r in result['families'].items()},indent=2))

if __name__=='__main__':main()
