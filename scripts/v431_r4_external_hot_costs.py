#!/usr/bin/env python3
"""Cost-only sidecar for inherited full methods, preserving incomplete scope."""
import json
from collections import Counter
from pathlib import Path
from v431_r4_hot_costs import sha, reprice_invoice


def main():
    root=Path('results/v431-r4/baseline_audit');native=root/'hot_costs.json'
    side=json.loads(native.read_text());sources={str(native):sha(native)};rows={'main':{},'financial':{}}
    def read(p):
        p=Path(p);sources[str(p)]=sha(p);return json.loads(p.read_text())
    def add(suite,r,kind):
        family,policy,uid=r['family'],r['policy'],r['episode_uid'];unknown=[];cold=0.
        for c in r['invoice']['charges']:
            value=side['charges'].get(c['key'])
            if value is not None:
                assert abs(value['original_seconds']-c['seconds'])<1e-8
                cold+=value['explicit_load_seconds']
            elif c['key'].startswith('tool:'):
                unknown.append(c['key'])
            else:
                assert not c['key'].startswith(('candidate:','forecast:','probe-candidates:','probe-forecast:')),c['key']
        original=r['total_seconds'];assert abs(original-r['invoice']['total_seconds'])<1e-8
        assert 0<=cold<=original
        out=dict(original_seconds=original,hot_seconds=original-cold,cold_seconds=cold,
            source_scope=kind,status='partial_cold_classification' if unknown else 'explicit_load_separated',
            scope='partial: unresolved mask/history full original fees retained' if unknown else 'only explicit model-load separated; all other overhead retained',
            uncorrected_scope=unknown)
        rows[suite].setdefault(family,{}).setdefault(policy,{})[uid]=out
    for suite,filename in [('main','decisions.json'),('financial','financial_decisions.json')]:
        for r in read(Path('results/v431-r3')/filename):add(suite,r,'r3_legacy')
    for r in read('results/v431-r3/common_decisions.json'):
        if r['policy']=='R2_EXISTING_CART':add('main',r,'r2_legacy_different_evidence')
    for r in read('results/v431-r2/financial-observation-index-r1/common_financial_decisions.json'):
        if r['policy']=='EXISTING_SAME_EVIDENCE_CART':
            r=dict(r,policy='R2_EXISTING_CART');add('financial',r,'r2_legacy_different_evidence')
    tato={}
    for suite,base,bname,tname in [('main',Path('results/v431/20260914-sprint'),'tato','timesfm_tato'),
        ('financial',Path('results/v431-r2/financial-observation-index-r1'),'tato','timesfm-tato')]:
        for family,folder in [('bolt',bname),('timesfm',tname)]:
            directory=base/folder;status=read(directory/'status.json');scored=read(directory/'scored_rows.json');decisions=read(directory/'decisions.json')
            n=len(scored);assert n==len(decisions);load=status['model_load_seconds'];assert load<=status['process_overhead_seconds']
            policy='TATO_8_NATIVE_SPACE' if suite=='main' else 'TATO_NATIVE_8TRIALS_OBSERVED_LINEAR'
            target=rows[suite].setdefault(family,{}).setdefault(policy,{})
            for r in scored:
                target[r['episode_uid']]=dict(original_seconds=r['total_seconds'],hot_seconds=r['total_seconds']-load/n,
                    cold_seconds=load/n,source_scope='TATO_8_trial_native_space',status='explicit_load_separated',
                    scope='only explicit model-load/N separated; original failed trials, final prediction and remaining overhead retained',
                    uncorrected_scope=[])
            failures=Counter(t.get('error') for r in decisions for t in r['trials'] if t['status']!='completed')
            tato[suite+':'+family]=dict(status_file=str(directory/'status.json'),status_sha256=sha(directory/'status.json'),
                records=n,physical_model_load_seconds=load,cold_seconds_per_record=load/n,trial_failures=dict(failures))
    out=root/'external_hot_costs.json'
    if out.exists():raise RuntimeError('Preserve frozen external cost snapshot')
    output=dict(status='completed',rows=rows,sources=sources,tato=tato,script_sha256=sha(__file__),
       limitation='R2 mask/history tool cold attribution not recovered; retains full tool fee and is not strictly matched resident cost',
       untouched='All old predictions, method decisions, failed trials and old reported costs preserved')
    out.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':'completed','rows':sum(len(rr) for fs in rows.values() for ps in fs.values() for rr in ps.values()),'output':str(out)}))


if __name__=='__main__':main()
