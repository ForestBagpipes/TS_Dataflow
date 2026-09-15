#!/usr/bin/env python3
"""Build immutable CPU r5 current-task ledgers; no TSFM execution."""
import argparse,json,time
from pathlib import Path
import joblib
from introact_ts.v431_r5.dataset import load
from introact_ts.v43.data_io import file_hash

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default='results/v431-r5/data');a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    if (out/'status.json').exists():raise RuntimeError('Never overwrite first completed r5 ledger')
    started=time.perf_counter();files={};reports=[]
    for suite in ('main','financial'):
        for family in ('bolt','timesfm'):
            target=out/suite/(family+'.joblib');target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():raise RuntimeError('Existing first ledger: '+str(target))
            data=load(suite,family);joblib.dump(data,target);files[str(target)]=file_hash(target)
            report=data['provenance'];reports.append(report)
            target.with_suffix('.support.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
            target.with_suffix('.coverage.json').write_text(json.dumps(data['coverage_audit'],indent=2,ensure_ascii=False)+'\n')
            print(json.dumps({k:report[k] for k in ('suite','family','roles','current_prediction_checks','coverage_supported','initialization_seconds')},ensure_ascii=False),flush=True)
    (out/'status.json').write_text(json.dumps(dict(status='completed',seconds=time.perf_counter()-started,
        files=files,suites=reports,script_sha256=file_hash(__file__)),indent=2,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
