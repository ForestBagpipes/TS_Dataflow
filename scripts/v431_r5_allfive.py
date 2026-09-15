#!/usr/bin/env python3
"""Higher-cost all-five comparison: acquire every incomplete-input version first.

This is not a budget-feasible r5 method. Complete inputs retain mandatory KEEP.
Original bounded ALL_FIVE and all first-result files remain unchanged.
"""
import json,time
from pathlib import Path
import numpy as np
from introact_ts.v431_r5.scoring import response_features
from introact_ts.v431_r5.geometry import project_scores
from v431_r5_run import ROOT,load,frozen,OfflineTrials,record,write,sha
from v431_r4_run import summarize


def main():
    models,_=frozen()
    for suite in ('main','financial'):
        name='dev' if suite=='main' else suite;out=ROOT/'evaluation'/name/'allfive-executed'
        if (out/'status.json').exists():raise RuntimeError('Preserve executed all-five snapshot')
        rows=[]
        for family,fm in models['families'].items():
            d=load(suite,family,'dev' if suite=='main' else None);b=d['batch']
            for i,x in enumerate(b.visible):
                begun=time.perf_counter();ref=fm['reference'].predict(x,bool(b.fully_observed[i]));callback=OfflineTrials(d,i)
                actions=[ref] if b.fully_observed[i] else [ref]+[a for a in range(5) if a!=ref]
                trials=[callback(a) for a in actions]  # Every version executed before terminal geometry.
                assert len(trials)==(1 if b.fully_observed[i] else 5)
                raw=np.zeros(len(actions));gains=raw.copy();chosen=0;solver=[];failure=None
                if len(actions)>1:
                    features=[np.r_[x,response_features(trials[0].prediction,t.prediction,b.rows[i]['origin_scale']['value'])] for t in trials[1:]]
                    raw[1:]=fm['critics']['current'].predict(features,actions[1:])
                    result=project_scores(np.stack([t.prediction for t in trials]),raw,b.rows[i]['origin_scale']['value'],
                        weights=None,mode='full',max_iter=2048,tolerance=1e-8,time_limit_seconds=.05)
                    solver=[dict(projection=result.to_dict(),raw=raw.tolist())]
                    if result.status in ('failed','timeout'):failure=result.reason
                    else:
                        gains=result.scores
                        chosen=0 if gains.max()<=0 else min(range(len(actions)),key=lambda j:(-gains[j],j!=0,actions[j]))
                seconds=float(d['feature_seconds'][i]+sum(t.seconds for t in trials)+time.perf_counter()-begun+.001)
                trace=dict(action=actions[chosen],reference_action=ref,reason='complete_KEEP' if len(actions)==1 else 'all_five_executed_before_terminal',
                    queried_actions=actions,queried=[t.summary() for t in trials],raw=raw.tolist(),gains=gains.tolist(),
                    trace=solver,total_seconds=seconds,versions=len(actions),failure=failure,
                    budget_overrun=seconds>3.5,final_input_hash=trials[chosen].input_hash,final_identity=trials[chosen].identity,
                    output_reserve=.001,cost_scope='uncapped all-five historical components + CPU wall; 3.5s flag is diagnostic only')
                r=record(d,i,'ALL_FIVE_EXECUTED_UNCAPPED',trace,3.5,mode='full',schedule='all')
                r['comparison_budget_enforced']=False;rows.append(r)
        table,sources=summarize(rows);write(out/'decisions.json',rows);write(out/'table.json',table);write(out/'sources.json',sources)
        common=json.loads((out.parent/'common_decisions.json').read_text());extended=common+rows
        et,es=summarize(extended);write(out.parent/'common_extended_decisions.json',extended)
        write(out.parent/'common_extended_table.json',et);write(out.parent/'common_extended_sources.json',es)
        write(out/'status.json',dict(status='completed',rows=len(rows),models_sha256=sha(ROOT/'fit/models.joblib'),
            incomplete_requests_all_five=True,complete_requests_KEEP=True,original_common_untouched=True,
            script_sha256=sha(__file__),comparison='explicit higher-cost ablation, not same-budget method'))
        print(json.dumps(dict(suite=suite,table=table)),flush=True)


if __name__=='__main__':main()
