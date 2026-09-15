import numpy as np
import pytest
from introact_ts.v431_r5.controller import run, TrialResult
from introact_ts.v431_r5.geometry import ProjectionResult

class Reference:
    def predict(self,x,complete): return 2
class Predictor:
    def predict(self,x,actions): return np.array([1. for a in actions])


def trial(action,*,cost=.02,status='completed',prediction=None):
    return TrialResult(action,np.array([action,action+1.],float) if prediction is None else prediction,
                       str(action),{'action':action},cost/2,cost/2,status=status)

def execute_case(callback,**kwargs):
    return run(np.array([1.,2.]),1.,kwargs.pop('fully_observed',False),kwargs.pop('budget',10.),
               Reference(),Predictor(),Predictor(),lambda a:.03,callback,**kwargs)


def test_only_queried_predictions_revealed_and_no_final_reforecast():
    calls=[]
    def cb(a):calls.append(a);return trial(a)
    out=execute_case(cb,mode='raw',schedule='fixed')
    assert calls==[2,0,1] and out['versions']==3
    np.testing.assert_array_equal(out['final_prediction'],[0.,1.])
    assert out['action'] in calls and out['final_input_hash']==str(out['action'])


def test_complete_target_native_keep():
    calls=[]
    def cb(a):calls.append(a);return trial(a)
    out=execute_case(cb,fully_observed=True)
    assert calls==[0] and out['action']==0 and out['reason']=='complete_KEEP'


def test_insufficient_budget_still_charges_reference_forecast():
    calls=[]
    def cb(a):calls.append(a);return trial(a,cost=.1)
    out=execute_case(cb,budget=0.)
    assert calls==[2] and out['budget_overrun'] and out['total_seconds']>=.1


def test_solver_timeout_preserves_preceding_valid_action(monkeypatch):
    count=0
    def proj(p,raw,*args,**kwargs):
        nonlocal count
        count+=1
        if count==1:return ProjectionResult(np.array([0.,1.]),'completed',True,0.,1,0.,0.)
        return ProjectionResult(raw,'timeout',False,None,0,.05,None,True,'timeout')
    monkeypatch.setattr('introact_ts.v431_r5.controller.project_scores',proj)
    out=execute_case(lambda a:trial(a),mode='full',schedule='fixed')
    assert out['action']==0 and out['versions']==3 and out['reason']=='solver_timeout_STOP'
    assert out['total_seconds']>=.06


def test_candidate_failure_keeps_prior_prediction_and_cost():
    def cb(a):return trial(a,cost=.1,status='failed' if a==0 else 'completed')
    out=execute_case(cb,schedule='fixed')
    assert out['action']==2 and out['total_seconds']>=.2 and out['failure']=='trial_failed'


def test_invalid_candidate_still_charges_incurred_trial():
    def cb(a):return trial(a,cost=.2,prediction=np.array([np.nan,1.]) if a==0 else None)
    out=execute_case(cb,schedule='fixed')
    assert out['action']==2 and out['total_seconds']>=.4


def test_failed_reference_rejected():
    with pytest.raises(ValueError):execute_case(lambda a:trial(a,status='failed'))


def test_exception_cost_retained():
    class Failure(RuntimeError):incurred_seconds=.3
    def cb(a):
        if a==0:raise Failure('intentional')
        return trial(a,cost=.2)
    out=execute_case(cb,schedule='fixed')
    assert out['action']==2 and out['total_seconds']>=.5


def test_nonpositive_prior_natural_stop():
    class Negative:
        def predict(self,x,actions):return -np.ones(len(actions))
    calls=[]
    def cb(a):calls.append(a);return trial(a)
    out=run(np.array([1.,2.]),1.,False,10.,Reference(),Predictor(),Negative(),lambda a:.03,cb)
    assert calls==[2] and out['reason']=='nonpositive_prior_STOP'


def test_offline_alias_forecast_dedup_still_pays_materialization(monkeypatch):
    import runpy
    monkeypatch.syspath_prepend('scripts')
    OfflineTrials=runpy.run_path('scripts/v431_r5_run.py',run_name='r5_controller_test')['OfflineTrials']
    meta=dict(source='synthetic',parent='p',origin=512,L=512,H=2,
              target_mask_hash='mask',auxiliary_mask_hash='aux',input_version_hash='same',
              model={'checkpoint':'test-only'},prediction_dtype='float64',prediction_hash='pred',
              cache_key='test',actual_arm='A0_NATIVE',alias=True,unsupported_reason='synthetic alias')
    d={'cache_metadata':[[dict(meta) for _ in range(5)]],
       'predictions':np.zeros((1,5,2)),'governance_costs':np.full((1,5),.03),
       'forecast_costs':np.full((1,5),.2)}
    callback=OfflineTrials(d,0)
    first=callback(2);second=callback(0)
    assert first.forecast_seconds==.2 and second.forecast_seconds==0
    assert first.governance_seconds==second.governance_seconds==.03
    assert second.identity['reused_already_executed_forecast']
    assert second.status=='alias' and second.actual_action==0
