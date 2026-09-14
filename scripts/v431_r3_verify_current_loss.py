#!/usr/bin/env python3
"""Independent offline loss recount on the 17 registered TRAIN check targets only."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np


def main():
    root=Path('results/v431-r3')
    old=Path('results/v43/20260914T141030.324186Z-agent')
    read=lambda p:json.loads(p.read_text())
    meta=read(root/'probes/main/generalization_metadata.json')
    manifest=read(root/'terminal_manifest.json')
    assert len(meta)==17
    assert all(m['split']=='train' and m['v431_role']=='T_check' and m['horizon']==192
               and m['parent_group'] in manifest['check_parent_ids'] for m in meta.values())
    scales=read(root/'probes/main/mase_scales.json')
    scores={};original_targets={};outputs=0
    for family in ('bolt','timesfm'):
        folder=root/('generalization-current-'+family)
        assert read(folder/'status.json')['status']=='completed'
        with np.load(folder/'predictions.npz',allow_pickle=False) as predictions, np.load(old/'targets.npz',allow_pickle=False) as target:
            for uid,m in meta.items():
                # These exact original raw/H192 TRAIN targets were already evaluated before r3.
                key=m['base_uid']; y=target[key+'_values'];mask=target[key+'_mask']
                assert len(y)==192 and mask.dtype==bool and mask.any() and np.isfinite(y[mask]).all()
                original_targets[uid]=key
                for arm in ('A0_NATIVE','A0_FFILL','A2_SINGLE','A3_COV','A4_RIDGE_CONTEXT'):
                    pred=predictions[uid+'_'+arm];assert np.isfinite(pred[mask]).all()
                    mae=float(np.abs(pred[mask]-y[mask]).mean())
                    scores[family,uid,arm]=(mae,mae/scales[m['source']]);outputs+=1
    decisions=read(root/'new_combination_decisions.json')
    for row in decisions:
        mae,mase=scores[row['family'],row['episode_uid'],row['arm']]
        assert np.isclose(mae,row['mae'],atol=1e-12,rtol=1e-12)
        assert np.isclose(mase,row['mase'],atol=1e-12,rtol=1e-12)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out=root/'verification'/(stamp+'-current-loss-main');out.mkdir()
    paths=[Path(__file__),root/'new_combination_decisions.json',root/'probes/main/generalization_metadata.json',old/'targets.npz']
    report={'status':'passed','scope':'Independent MAE/MASE recount only after prediction, frozen-policy evaluation complete',
            'parents':17,'raw_predictions':outputs,'decision_rows':len(decisions),'original_train_target_keys':original_targets,
            'calibration_test_decoded':0,'new_source_future_values_read':0,
            'existing_train_target_slices_decoded':34,
            'file_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(out/'report.json'),**{k:v for k,v in report.items() if k not in ('file_sha256','original_train_target_keys')}}))


if __name__=='__main__':main()
