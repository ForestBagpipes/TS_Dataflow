"""CPU-only transformation contract; its dummy forecaster is never research output."""
import json
from pathlib import Path
import numpy as np
from tato_adapter import ROOT, official_identity, load_official, bridge, predict_native, vanilla, adapt_window


class ShapeOnly:
    def forecast(self, x, horizon):
        return np.repeat(x[:, -1:, :], horizon, axis=1)


def main():
    out = ROOT/'logs/v431/baselines'; out.mkdir(parents=True, exist_ok=True)
    result = dict(scope='CPU transformation semantics only; no model performance claim', official=official_identity())
    x=np.sin(np.arange(512)*.1)+3.; x[350:401]=np.nan; original=x.copy()
    y=bridge(x); assert np.array_equal(y[np.isfinite(x)],x[np.isfinite(x)])
    parameters=vanilla(); parameters['normalizer_method']='standard'
    try: predict_native(parameters,ShapeOnly(),x,96,enable_bridge=False)
    except FloatingPointError as e: result['native_missing_input']=dict(status='unsupported',error=str(e))
    else: raise AssertionError('expected no-bridge nonfinite propagation')
    checks=[]
    _,factory=load_official()
    spaces=factory.build_search_space(['trimmer','inputer','denoiser','warper','differentiator','normalizer','sampler','aligner'],16)
    result['native_search_dimensions']={k:str(v) for k,v in spaces.items()}
    for horizon in (96,192):
        prediction,record=adapt_window(x,horizon,ShapeOnly())
        assert prediction.shape==(horizon,) and np.isfinite(prediction).all()
        assert all(row['validation_cutoff']==512-horizon for row in record['trials'])
        checks.append(dict(horizon=horizon,successful_trials=sum(r['status']=='completed' for r in record['trials']),record=record))
    # Changing suffix cannot affect preprocessing of prefix at the exclusive cutoff.
    changed=x.copy(); changed[416:]=1e9
    assert np.array_equal(bridge(x[:416]),bridge(changed[:416]))
    assert np.array_equal(x,original,equal_nan=True)
    try: bridge(np.full(512,np.nan))
    except ValueError: pass
    else: raise AssertionError('all missing silently repaired')
    result.update(status='passed',checks=checks,original_time_unchanged=True,original_observed_unchanged=True,
        prefix_suffix_poison_check=True,all_missing_rejection=True)
    (out/'tato-cpu-smoke.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k!='checks'}))


if __name__=='__main__': main()
