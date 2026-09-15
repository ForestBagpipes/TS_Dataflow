#!/usr/bin/env python3
"""Fit legacy terminal controls, or finish their acquisition after cost audit."""
import argparse
from pathlib import Path
import joblib,numpy as np
from introact_ts.v431_r4.legacy_retrain import fit_legacy,finalize_legacy_acquisition

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--batch-root',default=None,help='Explicit historical cost snapshot; default audited load_batch hot costs')
    p.add_argument('--output',default='results/v431-r4/legacy')
    p.add_argument('--terminal-only',action='store_true')
    p.add_argument('--acquisition-only',action='store_true')
    p.add_argument('--terminal-root',default='results/v431-r4/legacy')
    a=p.parse_args()
    if a.batch_root:
        batches={f:joblib.load(Path(a.batch_root)/(f+'.joblib')) for f in ('bolt','timesfm')}
    else:
        from v431_r4_run import load_batch
        batches={f:load_batch('main',f) for f in ('bolt','timesfm')}
    batches={f:b.subset(np.flatnonzero(b.roles!='dev')) for f,b in batches.items()}
    if a.acquisition_only:
        if a.terminal_only:raise ValueError('Choose one phase')
        finalize_legacy_acquisition(batches,a.terminal_root,a.output)
    else:fit_legacy(batches,a.output,fit_acquisition=not a.terminal_only)
if __name__=='__main__':main()
