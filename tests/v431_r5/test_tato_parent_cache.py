"""CPU fake-backend contracts, not numerical TSFM performance tests."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from v431_r5_tato_parent_cache import ParentScopedForecast

class FakeBackend:
    def __init__(self):
        self.identity={'checkpoint':'CPU-test-only','revision':'v1','dtype':'float64'}
        self.cache={};self.calls=[];self.n=0
    def forecast(self,x,horizon):
        self.n+=1
        prediction=np.repeat(np.asarray(x)[:,-1:,:],horizon,axis=1)
        self.calls.append(dict(cache_hit=False,seconds=.001,raw_file=f'fake-{self.n}',
                               raw_sha256=str(self.n),peak_gpu_bytes=0))
        return prediction

@pytest.fixture
def setup_cache():
    backend=FakeBackend();model=ParentScopedForecast(backend,{'config':'fixed'})
    x=np.arange(8,dtype=float)[None,:,None]
    model.set_scope('p1','train','u1')
    return backend,model,x

def test_same_parent_cross_trial_hit(setup_cache):
    b,m,x=setup_cache;m.forecast(x,2);m.set_scope('p1','train','u1');m.forecast(x,2)
    assert b.n==1 and m.calls[-1]['cache_hit']

def test_returned_copy_cannot_mutate_native_cache(setup_cache):
    b,m,x=setup_cache;p=m.forecast(x,2);p[:]=999
    np.testing.assert_array_equal(m.forecast(x,2),np.full((1,2,1),7.))
    assert b.n==1

def test_cross_parent_is_a_physical_miss(setup_cache):
    b,m,x=setup_cache;m.forecast(x,2);m.set_scope('p2','train','u2');m.forecast(x,2)
    assert b.n==2 and not m.calls[-1]['cache_hit']

def test_horizon_is_part_of_identity(setup_cache):
    b,m,x=setup_cache;m.forecast(x,2);p=m.forecast(x,3)
    assert b.n==2 and p.shape==(1,3,1)
    assert m.calls[0]['cache_key']!=m.calls[1]['cache_key']

def test_dtype_is_part_of_identity(setup_cache):
    b,m,x=setup_cache;m.forecast(x,2);m.forecast(x.astype(np.float32),2)
    assert b.n==2
    assert m.calls[0]['cache_identity']['dtype']!=m.calls[1]['cache_identity']['dtype']

def test_each_deployment_request_clears_train_and_prior_request_cache(setup_cache):
    b,m,x=setup_cache;m.forecast(x,2)
    for uid in ('d1','d2'):
        m.set_scope('p1','dev',uid);m.forecast(x,2)
        assert not m.calls[-1]['cache_hit']
        assert m.calls[-1]['cache_scope']=='deployment_request'
    assert b.n==3

def test_hit_preserves_first_raw_and_cost_provenance(setup_cache):
    b,m,x=setup_cache;m.forecast(x,2);m.forecast(x,2)
    first,hit=m.calls
    assert hit['first_call_index']==0
    assert hit['first_raw_file']==first['raw_file']
    assert hit['first_raw_sha256']==first['raw_sha256']
    assert hit['first_charged_seconds']==first['seconds']
    assert hit['point_hash']==first['point_hash']
    assert hit['native_compute_seconds']==0
    assert hit['seconds']==hit['lookup_seconds']>=0
    assert first['native_compute_seconds']==.001
