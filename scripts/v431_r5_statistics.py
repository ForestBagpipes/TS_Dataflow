#!/usr/bin/env python3
"""Descriptive r5 comparisons on already exported evaluation ledgers only."""
from pathlib import Path
from collections import defaultdict,Counter
import argparse,json,hashlib
import numpy as np
import joblib
from v431_r3_statistics import macro,blocked_bootstrap

ROOT=Path('results/v431-r5')

def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

def group(rows):
    result=defaultdict(list)
    for r in rows:result[r['family'],r['policy']].append(r)
    return result

def pairs(left,right,*,same_trace=False):
    a={r['episode_uid']:r for r in left};b={r['episode_uid']:r for r in right}
    assert len(a)==len(left) and len(b)==len(right),'Repeated policy uid'
    common=sorted(set(a)&set(b));result=[]
    for uid in common:
        l,r=a[uid],b[uid]
        assert all(l[k]==r[k] for k in ('source','parent_group','horizon','raw_start'))
        if same_trace:
            assert l['trace']['queried_actions']==r['trace']['queried_actions'],'Not a fixed common trace'
        row={k:l[k] for k in ('episode_uid','source','parent_group','raw_start','horizon','condition')}
        row.update({k:float(l[k])-float(r[k]) for k in ('mase','total_seconds','switch_gain','wrong_switch_loss')})
        row.update(action_changed=l['arm']!=r['arm'],prediction_changed=l['forecast_hash']!=r['forecast_hash'])
        ls,rs=l.get('score_metrics'),r.get('score_metrics')
        if ls is not None and rs is not None:
            row['gain_vector_squared_error']=ls['projected_squared_error']-rs['projected_squared_error']
        result.append(row)
    if not result:return {'status':'missing_common_support'}
    fields=['mase','total_seconds','switch_gain','wrong_switch_loss']
    eligible=[x for x in result if 'gain_vector_squared_error' in x]
    out={'status':'computed_descriptive','same_query_trace_required':same_trace,
         'left_episodes':len(left),'right_episodes':len(right),'common_episodes':len(common),
         'parents':len({x['parent_group'] for x in result}),
         'missing_left':sorted(set(b)-set(a)),'missing_right':sorted(set(a)-set(b)),
         'differences':{k:blocked_bootstrap(result,k) for k in fields},
         'improved':sum(x['mase'] < -1e-12 for x in result),
         'worsened':sum(x['mase'] > 1e-12 for x in result),
         'equal':sum(abs(x['mase']) <= 1e-12 for x in result),
         'action_changes':sum(x['action_changed'] for x in result),
         'prediction_changes':sum(x['prediction_changed'] for x in result),
         'tail_harm':sorted(result,key=lambda x:x['mase'],reverse=True)[:10],
         'by_source':{s:macro([x for x in result if x['source']==s],'mase') for s in sorted({x['source'] for x in result})}}
    if eligible:out['gain_vector_squared_error_difference']=blocked_bootstrap(eligible,'gain_vector_squared_error')
    return out


def summarize(rows):
    output=[]
    for (family,policy),rs in sorted(group(rows).items()):
        score=[];solver=[];reasons=Counter();failures=[]
        for r in rs:
            t=r.get('trace',{})
            if isinstance(t,dict):
                reasons[t.get('reason','unrecorded')]+=1
                if t.get('failure'):failures.append({'episode_uid':r['episode_uid'],'reason':t['failure']})
            solver.extend(r.get('solver',[]))
            m=r.get('score_metrics')
            if m is not None:score.append({**r,**m})
        summary={'family':family,'policy':policy,'episodes':len(rs),'parents':len({r['parent_group'] for r in rs}),
                 'mase':macro(rs,'mase'),'seconds':macro(rs,'total_seconds'),
                 'switch_gain':macro(rs,'switch_gain'),'wrong_switch_loss':macro(rs,'wrong_switch_loss'),
                 'p95_seconds':float(np.quantile([r['total_seconds'] for r in rs],.95)),
                 'max_seconds':max(r['total_seconds'] for r in rs),
                 'budget_overruns':sum(r['total_seconds']>r['budget']+1e-12 for r in rs),
                 'at_least_three_distinct_prediction_episodes':sum(r.get('unique_predictions',0)>=3 for r in rs),
                 'failure_count':len(failures),'failures':failures,'reasons':dict(reasons)}
        if score:
            summary['score_metrics']={k:macro(score,k) for k in ('raw_squared_error','projected_squared_error','raw_violation','projected_violation','projection_active','rank_changed')}
            summary['score_metrics']['eligible_episodes']=len(score)
            summary['score_metrics']['eligible_parents']=len({r['parent_group'] for r in score})
            flat_truth=[v for r in score for v in r['true_gains'][1:]]
            summary['score_metrics']['zero_true_gain_coordinates']=sum(abs(v)<=1e-12 for v in flat_truth)
        if solver:
            gaps=[x['gap'] for x in solver if x.get('gap') is not None]
            summary['solver']={'calls':len(solver),'statuses':dict(Counter(x['status'] for x in solver)),
                'converged':sum(x['converged'] for x in solver),'max_gap':max(gaps) if gaps else None,
                'mean_gap':float(np.mean(gaps)) if gaps else None,
                'seconds':sum(x['elapsed_seconds'] for x in solver),
                'max_seconds':max(x['elapsed_seconds'] for x in solver)}
        output.append(summary)
    return output


def numeric_prediction_counts(rows,suite):
    """Count actual floating values, never cache hashes or dtype identities."""
    data_suite='financial' if suite=='financial' else 'main'
    by_family={}
    for r in rows:
        t=r.get('trace',{})
        if not isinstance(t,dict) or 'queried_actions' not in t:continue
        family=r['family']
        if family not in by_family:
            path=ROOT/'data'/data_suite/(family+'.joblib')
            d=joblib.load(path)
            by_family[family]=({str(uid):i for i,uid in enumerate(d['batch'].uids)},d['predictions'])
        indices,predictions=by_family[family]
        actual=predictions[indices[r['episode_uid']]]
        distinct=[]
        for a in t['queried_actions']:
            prediction=np.asarray(actual[a],dtype=np.float64)
            if not any(np.array_equal(prediction,v) for v in distinct):distinct.append(prediction)
        r['hash_unique_predictions_before_numeric_audit']=r.get('unique_predictions')
        r['unique_predictions']=len(distinct)
    return {'definition':'np.array_equal on float64 numerical arrays; dtype/hash excluded',
            'checked_rows':sum('hash_unique_predictions_before_numeric_audit' in r for r in rows),
            'changed_counts':sum(r.get('hash_unique_predictions_before_numeric_audit')!=r['unique_predictions']
                                for r in rows if 'hash_unique_predictions_before_numeric_audit' in r)}


def projection_certificate(rows):
    certificates=[]
    for r in rows:
        if r.get('geometry_mode')!='full' or r.get('score_metrics') is None:continue
        t=r['trace'];raw=np.asarray(t['raw']);z=np.asarray(t['gains']);g=np.asarray(r['score_metrics']['true_gains'])
        if len(raw)!=len(z) or len(z)!=len(g):continue
        solvers=r.get('solver',[])
        if not solvers or solvers[-1]['status'] in ('failed','timeout'):continue
        gap=solvers[-1]['gap']
        residual=float(np.sum((z-g)**2)-np.sum((raw-g)**2)+np.sum((raw-z)**2)-2*gap)
        certificates.append(dict(episode_uid=r['episode_uid'],family=r['family'],residual=residual,gap=gap))
    return {'checked':len(certificates),'violations_over_1e8':sum(x['residual']>1e-8 for x in certificates),
            'max_residual':max((x['residual'] for x in certificates),default=None),
            'worst_rows':sorted(certificates,key=lambda x:x['residual'],reverse=True)[:5]}


def process(suite):
    directory=ROOT/'evaluation'/suite
    core=directory/'decisions.json';common=directory/'common_decisions.json';mechanism=directory/'mechanism_rows.json'
    if not core.exists():return {'status':'pending_inputs'}
    selected=common if common.exists() else core
    rows=read(selected);numeric_audit=numeric_prediction_counts(rows,suite);groups=group(rows);comp=[]
    for family in ('bolt','timesfm'):
        for budget in ('low','high'):
            left='R5_'+budget
            if (family,left) not in groups:continue
            for fam,right in sorted(groups):
                if fam!=family or right==left or not right.endswith('_'+budget):continue
                comp.append({'family':family,'left':left,'right':right,
                             **pairs(groups[family,left],groups[family,right])})
    output={'status':'completed','input_path':str(selected),'input_sha256':sha(selected),
            'full_method_summary':summarize(rows),'adaptive_comparisons':comp,'numeric_prediction_audit':numeric_audit,
            'warning':'Adaptive paths can differ; geometry attribution uses the separate fixed-query mechanism table only.'}
    if mechanism.exists():
        mr=read(mechanism);mechanism_numeric=numeric_prediction_counts(mr,suite);mg=group(mr);mc=[]
        for family in ('bolt','timesfm'):
            for left,right in [('MECH_CURRENT_FULL','MECH_CURRENT_RAW'),('MECH_CURRENT_FULL','MECH_CURRENT_SINGLE'),
                               ('MECH_CURRENT_FULL','MECH_CURRENT_PAIR'),('MECH_CURRENT_RAW','MECH_FREE_RAW'),
                               ('MECH_CURRENT_RAW','MECH_HISTORY_RAW')]:
                if (family,left) not in mg or (family,right) not in mg:continue
                for subset in ('all','three_distinct_predictions'):
                    ll=mg[family,left];rr=mg[family,right]
                    if subset!='all':
                        ll=[r for r in ll if r.get('unique_predictions',0)>=3]
                        rr=[r for r in rr if r.get('unique_predictions',0)>=3]
                    mc.append({'family':family,'left':left,'right':right,'subset':subset,**pairs(ll,rr,same_trace=True)})
        output['mechanism']={'input_path':str(mechanism),'input_sha256':sha(mechanism),
                             'summary':summarize(mr),'comparisons':mc,'numeric_prediction_audit':mechanism_numeric,
                             'projection_certificate':projection_certificate(mr),
                             'scope':'Current raw/single/pair/full share exact queried actions. History pays additional H evidence. Fewer than 3 distinct forecasts cannot establish higher-order contribution.'}
    return output


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--suite',default='all');a=parser.parse_args()
    suites=['dev','financial','T_check','T_acq','T_fit'] if a.suite=='all' else [a.suite]
    out={'status':'descriptive_only','seed':101,'bootstrap_replicates':2000,
         'resampling':'source fixed; adjacent two-parent temporal blocks within source; parent variants remain together',
         'calibration_test_read':False,'suites':{s:process(s) for s in suites}}
    write(ROOT/'statistics/report.json',out)
    print(json.dumps({s:v['status'] for s,v in out['suites'].items()}))

if __name__=='__main__':main()
