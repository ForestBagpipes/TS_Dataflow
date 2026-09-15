from types import SimpleNamespace
import numpy as np
import pytest
from introact_ts.v431_r4.joint_policy import JointPolicy, VisibleState, AcquiredEvidence

def batch(n=40):
    x=np.arange(n)%2
    losses=np.ones((n,5))*3
    losses[:,2]=2
    losses[x==0,0]=0; losses[x==1,1]=0
    return SimpleNamespace(visible=np.zeros((n,1)),free_names=('missing_fraction',),
        evidence={'H':x[:,None].astype(float)},evidence_names={'H':('historical_mae',)},
        supported={'H':np.ones(n,bool)},tool_costs={'H':np.ones(n)*.1},action_costs=np.ones((n,5))*.1,
        parents=np.array([str(i) for i in range(n)]),roles=['T_fit']*n,
        fully_observed=np.zeros(n,bool),weights=np.ones(n)/n,losses=losses)

def test_joint_real_path_and_whitelist():
    p=JointPolicy().fit(batch(),tools=('H',),allow_free_split=False)
    v=VisibleState({'missing_fraction':.1},False,{'H':True})
    assert p.decide(v)['kind']=='acquire'
    assert p.decide(v,AcquiredEvidence('H',{'historical_mae':0}))['action']==0
    assert p.decide(v,AcquiredEvidence('H',{'historical_mae':1}))['action']==1
    assert p.counts['evidence_splits_scored']>0
    with pytest.raises(TypeError):p.decide({'losses':[0]*5})
    with pytest.raises(ValueError):p.decide(v,AcquiredEvidence('H',{'historical_mae':0,'future':1}))

def test_budget_complete_and_failure():
    p=JointPolicy().fit(batch(),tools=('H',),allow_free_split=False)
    v=VisibleState({'missing_fraction':.1},False,{'H':True})
    assert p.decide(v,remaining_budget=0)['total_budget_unmet']
    assert p.decide(v,AcquiredEvidence('H',{},'failed'))['reason']=='tool_failure_fallback'
    assert p.decide(VisibleState(v.features,True,v.applicable))['action']==0
    assert p.decide(v,remaining_budget=.15)['reason']=='budget_fallback'

def test_independent_parent_support_not_variants():
    b=batch(); b.parents=np.array(['same']*40)
    p=JointPolicy().fit(b,tools=('H',))
    assert p.tree['kind']=='submit'
    assert p.counts['evidence_splits_scored']==0

def test_fit_role_and_cost_identity():
    b=batch();b.roles[-1]='T_gate'
    with pytest.raises(ValueError):JointPolicy().fit(b,tools=('H',))
    b=batch();b.action_costs[0,0]=np.nan
    with pytest.raises(ValueError):JointPolicy().fit(b,tools=('H',))

def test_complete_inputs_do_not_supply_learned_leaf_support():
    b=batch();b.fully_observed[:30]=True
    p=JointPolicy().fit(b,tools=('H',))
    assert p.tree['kind']=='submit'

def test_cost_penalty_and_fixed_tool():
    b=batch(); b.tool_costs['H'][:]=1
    p=JointPolicy().fit(b,tools=('H',),lambda_value=10,allow_free_split=False)
    assert p.tree['kind']=='submit'
    q=JointPolicy().fit(b,tools=('H',),forced_tool='H',allow_free_split=False)
    assert q.tree['kind']=='acquire'
    assert q.cost.reservation('H')==pytest.approx(1.21)
    assert len(q.frozen_hash)==64

def test_unreachable_expensive_final_does_not_exclude_cheap_path():
    b=batch();b.action_costs[:,4]=100
    p=JointPolicy().fit(b,tools=('H',),allow_free_split=False,budget=.5)
    assert p.tree['kind']=='acquire'
    assert 4 not in p.tree['reachable_arms']
    v=VisibleState({'missing_fraction':.1},False,{'H':True})
    assert p.decide(v)['estimated_branch_seconds']<.5

def test_horizon_bucket_reservation_matches_runtime():
    b=batch(80);b.free_names=('horizon_ratio',);b.visible=np.repeat([.5,1.],40)[:,None]
    b.action_costs[:40,:]=2; b.action_costs[40:,:]=.1
    p=JointPolicy().fit(b,tools=('H',),forced_tool='H',allow_free_split=False,budget=.5)
    assert p.decide(VisibleState({'horizon_ratio':.5},False,{'H':True}))['reason']=='budget_fallback'
    assert p.decide(VisibleState({'horizon_ratio':1.},False,{'H':True}))['kind']=='acquire'

def test_staged_free_router_keeps_global_frozen_terminals():
    b=batch(80);b.visible=np.arange(80)[:,None]/80
    p=JointPolicy().fit(b,tools=('H',),staged=True)
    assert p.staged and 'H' in p.staged_terminals
    frozen=p.staged_terminals['H'][0]
    def walk(node):
        if node['kind']=='free_split':walk(node['left']);walk(node['right'])
        elif node['kind']=='acquire':
            assert node['terminal']['feature']==frozen['feature']
            assert node['terminal']['threshold']==frozen['threshold']
            assert node['terminal']['left']['arm']==frozen['left']['arm']
            assert node['terminal']['right']['arm']==frozen['right']['arm']
    walk(p.tree)

def test_post_tool_remaining_budget_selects_frozen_feasible_fallback():
    b=batch();b.action_costs[:,2]=.3
    p=JointPolicy().fit(b,tools=('H',),allow_free_split=False)
    v=VisibleState({'missing_fraction':.1},False,{'H':True})
    d=p.decide(v,AcquiredEvidence('H',{},'failed'),remaining_budget=.15)
    assert d['estimated_final_seconds']<=.15 and not d['total_budget_unmet']
    d=p.decide(v,AcquiredEvidence('H',{},'failed'),remaining_budget=.01)
    assert d['total_budget_unmet'] and d['estimated_final_seconds']==pytest.approx(.11)
