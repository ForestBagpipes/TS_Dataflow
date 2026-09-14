#!/usr/bin/env python3
"""Separate frozen TimesFM/TATO adapter; leaves Bolt worker and adapter intact."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import tato_adapter
import worker


def native_timesfm_pipeline(params, model, horizon):
    factory,_=tato_adapter.load_official()
    return factory.build_trial_pipeline_by_transformation_names(SimpleNamespace(params=dict(params)),
        model,tato_adapter.NAMES,dict(pred_len=horizon,patch_len=32,data_patch_len=32,model_patch_len=32),mode='test',plt=False)


def activate():
    tato_adapter.pipeline=native_timesfm_pipeline


def prepare(run,out):
    worker.prepare(run,out,'tato')
    path=Path(out)/'request.json';request=json.loads(path.read_text())
    request.update(backbone_family='timesfm',native_patch_size=32,timesfm_tato_adapter_sha256=worker.sha(__file__),
        protocol_note='All official trimmer5..15 retained; at 320/416 cutoff, too-long candidate trials fail visibly. No extra history/padding future.')
    worker.atom(path,request)


class CheckedTimesFM(worker.TimesFM):
    def __init__(self,out):
        super().__init__(out)
        # Independent real-model acceptance before applying the native TATO
        # transformation grid. These calls are separately identified in calls.
        smoke=np.sin(np.arange(512)*.1)[None,:,None];smoke[0,100:150,0]=np.nan
        for horizon in (96,192):
            prediction=self.forecast(smoke,horizon)
            if prediction.shape!=(1,horizon,1):raise RuntimeError('TimesFM/TATO family acceptance shape failed')
        worker.atom(out/'capability.json',dict(status='passed',scope='real TimesFM GPU NaN H96/H192; no method claim',calls=len(self.calls)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare');parser.add_argument('--output');parser.add_argument('--request');parser.add_argument('--verify')
    args=parser.parse_args()
    if args.prepare:prepare(args.prepare,args.output)
    elif args.request:
        request=json.loads(Path(args.request).read_text())
        if request['timesfm_tato_adapter_sha256']!=worker.sha(__file__):raise RuntimeError('TimesFM/TATO adapter changed after registration')
        activate();worker.Bolt=CheckedTimesFM;worker.execute(args.request)
    elif args.verify:
        activate()
        from verify_and_score import main
        main(args.verify)
    else:parser.error('choose --prepare, --request, or --verify')
