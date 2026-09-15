import numpy as np
import pytest
from types import SimpleNamespace
from introact_ts.v431_r5.scoring import (response_features,reference_features,SharedRidge,
    FreeReference,crossfit_reference,paired_training_rows)

def batch(n=40):
    class Batch(SimpleNamespace):
        def subset(self,ix):
            return Batch(**{k:([v[i] for i in ix] if k=='rows' else v[ix] if isinstance(v,np.ndarray) else v) for k,v in vars(self).items()})
    return Batch(visible=np.arange(n)[:,None].astype(float),losses=np.tile([2.,2.,1.,2.,2.],(n,1)),
        fully_observed=np.zeros(n,bool),parents=np.array([str(i) for i in range(n)]),
        sources=np.array(['same']*n),roles=np.array(['T_fit']*n),weights=np.ones(n)/n,
        free_names=('visible',),rows=[dict(meta=dict(raw_start=i*1000,context_end=i*1000+512,horizon=96)) for i in range(n)])

def test_response_is_current_complete_and_scaled():
    got=response_features(np.zeros(4),np.array([0.,2.,4.,6.]),2.)
    np.testing.assert_allclose(got,[1.5,1.5,3.,.5,2.5,3.,3.])
    np.testing.assert_equal(reference_features(np.array([0.,2.,4.,6.]),2.),got)
    with pytest.raises(ValueError):response_features([1,2],[1],1)
    with pytest.raises(ValueError):response_features([1,2],[1,np.nan],1)

def test_fit_gate_labels_refused():
    with pytest.raises(ValueError):SharedRidge().fit([[1]],[0],[1],[1],alpha=.1,roles=['dev'])
    b=batch();b.roles[0]='dev'
    with pytest.raises(ValueError):FreeReference().fit(b)

def test_crossfit_forward_parent_purge_and_fallback():
    b=batch();a,log=crossfit_reference(b)
    for entry in log:
        assert entry['parent'] not in entry['training_parents']
        if entry['training_max_read_end'] is not None:
            assert entry['training_max_read_end']<=entry['validation_read_start']
    assert sum(r['fallback'] for r in log)==16
    np.testing.assert_equal(a,np.full(40,2))
    # Poison each held-out parent's labels independently; its OOF action cannot change.
    for j in [0,20,39]:
        other=batch();other.losses[j]=[0,100,100,100,100]
        assert crossfit_reference(other)[0][j]==a[j]

def test_ref_complete_keep_and_parent_leaf_support():
    b=batch();b.losses[:20,0]=0.;b.losses[20:,4]=0.
    model=FreeReference().fit(b)
    assert model.node['left']['parents']>=16 and model.node['right']['parents']>=16
    assert model.predict([30],True)==0
    b.parents[:]=b.parents[0]
    assert FreeReference().fit(b).node['fallback']

def test_ridge_fit_only_imputer_and_prediction_no_target():
    x=np.array([[1,np.nan],[2,3],[3,6]],float)
    m=SharedRidge().fit(x,[0,1,2],[1,2,3],[1,1,1],alpha=.1,roles=['fit']*3)
    assert m.impute[1]==4.5
    digest=m.frozen_hash
    assert np.isfinite(m.predict([[1000,np.nan]],[3])).all()
    assert m.frozen_hash==digest
    with pytest.raises(ValueError):m.predict([[np.inf,2]],[0])

def test_prior_never_uses_unqueried_predictions():
    p=[np.arange(20.).reshape(5,4)]
    args=([np.array([1.])],p,[2.],np.zeros((1,5)),[2],['p'],['s'])
    before=paired_training_rows(*args,mode='prior')
    p[0][0]=np.nan;p[0][1]=np.inf;p[0][3:]=1e10
    after=paired_training_rows(*args,mode='prior')
    np.testing.assert_equal(before['features'],after['features'])
