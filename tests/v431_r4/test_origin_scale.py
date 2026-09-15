import numpy as np
import pytest
from introact_ts.v431_r4.origin_scale import origin_scale

def test_seasonal_visible_only():
    x=np.arange(512,dtype=float);x[200:260]=np.nan
    s=origin_scale(x,96);assert s.value==96 and s.branch=='seasonal'
    assert s.seasonal_pairs==296

def test_fallback_chain():
    assert origin_scale(np.arange(40.),96).branch=='lag1'
    s=origin_scale(np.array([1.,np.nan,3.,np.nan,5.]),96)
    assert s.branch=='visible_mad' and s.value==2
    s=origin_scale(np.ones(40),96)
    assert s.branch=='lag1' and s.floor_applied and s.value==1e-8
    assert origin_scale(np.full(10,np.nan),5).value==1e-8

def test_no_extra_history_or_future():
    with pytest.raises(ValueError):origin_scale(np.ones(513),96)
    with pytest.raises(ValueError):origin_scale(np.ones((2,2)),96)

def test_exact_support_threshold():
    assert origin_scale(np.arange(20.),5).branch=='lag1'
    assert origin_scale(np.arange(21.),5).branch=='seasonal'

def test_missing_evidence_typed_not_zero():
    from introact_ts.v431_r4.trajectory_dataset import evidence_features
    names,values=evidence_features({'h32':{'status':'unsupported'}},'H32',2.)
    assert names is None and values is None

def test_historical_measurement_rebased_from_mae():
    from introact_ts.v431_r4.trajectory_dataset import evidence_features
    from introact_ts.v43.agent_inputs import POOL
    atom={'status':'completed','mae':dict(zip(POOL,[2,4,6,8,10])), 'gain':{a:999 for a in POOL},
     'coverage':1.,'support_count':32,'probe_descriptor':{'length_horizon_ratio':15.,'target_coverage':1.,'covariate_coverage':1.}}
    names,v=evidence_features({'h32':atom},'H32',2.)
    assert np.array_equal(v[:5],[1,2,3,4,5])
    assert not any('kappa' in n or n=='z' for n in names)

def test_parent_variants_cannot_expand_weight():
    from introact_ts.v431_r4.trajectory_dataset import group_weights
    w=group_weights(['a','a','b','c'],['s1','s1','s1','s2'])
    assert np.allclose(w,[.125,.125,.25,.5])
