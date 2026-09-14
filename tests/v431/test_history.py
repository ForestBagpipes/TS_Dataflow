from dataclasses import replace
import numpy as np
from introact_ts.v43.schemas import Episode
from introact_ts.v431.data import aligned_views,source_parent_weights,dirty_features,FEATURE_NAMES

def episode(h=192):
    return Episode('x','s','s','p','train',0,0,512,h,np.arange(512),np.arange(512,dtype=float),np.ones((512,2)),np.tile(np.arange(512)[:,None],(1,3)))

def test_aligned_history_no_future_values():
    for h in (96,192):
        e=episode(h);a,b,r=aligned_views(e);x=e.target.copy();x[r:]=-999
        changed=replace(e,target=x);c,d,_=aligned_views(changed)
        assert r==512-h and a.horizon==h and b.horizon==32
        np.testing.assert_array_equal(a.target,c.target);np.testing.assert_array_equal(b.target,d.target)
        assert len(a.target)==r

def test_parent_variant_weights_and_schema():
    m={'a':dict(source='x',parent_group='p'),'b':dict(source='x',parent_group='p'),'c':dict(source='x',parent_group='q'),'d':dict(source='y',parent_group='r')}
    w=source_parent_weights(list(m),m)
    np.testing.assert_allclose(w,[.125,.125,.25,.5])
    assert len(dirty_features(episode(),96))==len(FEATURE_NAMES)==13
