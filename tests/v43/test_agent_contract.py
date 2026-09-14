from dataclasses import replace
import numpy as np
import pytest
from introact_ts.v43.schemas import Episode,ContractError,array_hash
from introact_ts.v43.agent_inputs import POOL,TOOLS,mask_views,history_views,training_origins
from introact_ts.v43.agent_policy import EvidenceState,features,FEATURE_NAMES,execute_policy
from introact_ts.v43.agent_fit import audit_partitions


@pytest.fixture
def agent_episode():
    t=np.arange(512,dtype=np.int64);x=np.sin(t/17);x[230:281]=np.nan
    z=np.column_stack((np.sin(t/17),np.cos(t/17)))
    return Episode('agent-test','s','p','parent','train',0,0,512,96,t,x,z,np.broadcast_to(t[:,None],(512,3)))


def test_agent_mask_probe_regenerates_without_hidden_block(agent_episode):
    views,_=mask_views(agent_episode)
    for i,(view,block) in enumerate(views):
        poisoned=agent_episode.target.copy();poisoned[block]+=1e8
        again,_=mask_views(replace(agent_episode,target=poisoned))
        np.testing.assert_array_equal(view.target,again[i][0].target)
        assert np.isnan(view.target[block]).all()


def test_agent_historical_prefix_excludes_later_target_and_covariates(agent_episode):
    for view,r in history_views(agent_episode):
        x=agent_episode.target.copy();z=agent_episode.covariates.copy();x[r:]+=1e9;z[r:]+=1e9
        other=next(e for e,cut in history_views(replace(agent_episode,target=x,covariates=z)) if cut==r)
        assert array_hash(view.target)==array_hash(other.target)
        assert array_hash(view.covariates)==array_hash(other.covariates)
        assert len(view.target)==r and view.horizon==32


def test_evidence_snapshot_and_hidden_features_are_isolated(agent_episode):
    pool={a:np.where(np.isnan(agent_episode.target),1.,agent_episode.target) for a in POOL};pool['A0_NATIVE']=agent_episode.target
    hidden={t:{a:[1.,2.,1.] for a in POOL} for t in TOOLS}
    state=EvidenceState();before=features(agent_episode,pool,'A2_SINGLE',state)
    hidden['strict_mask']['A2_SINGLE'][0]=1e12
    np.testing.assert_array_equal(before,features(agent_episode,pool,'A2_SINGLE',state))
    acquired=state.acquire('history_probe',hidden['history_probe'])
    v=features(agent_episode,pool,'A2_SINGLE',acquired)
    hidden['history_probe']['A2_SINGLE'][0]=1e12
    np.testing.assert_array_equal(v,features(agent_episode,pool,'A2_SINGLE',acquired))
    assert not any(any(word in name for word in ('source','uid','future','seed','condition','oracle')) for name in FEATURE_NAMES)


class ZeroUtility:
    def predict(self,x):return np.zeros(len(x))


class PositiveValue:
    def predict(self,x):return np.ones(len(x))


def test_budget_overrun_retained_without_hiding_cost(agent_episode):
    pool={a:agent_episode.target for a in POOL};calls=[]
    def fetch(tool):
        calls.append(tool);return {a:[1.,0.,1.] for a in POOL},2.
    result=execute_policy(agent_episode,pool,ZeroUtility(),PositiveValue(),fetch,{t:.5 for t in TOOLS},1.)
    assert len(calls)==1 and result['budget_overrun'] and result['tool_seconds']==2.
    assert result['trace'][0]['status']=='budget_overrun' and result['arm']=='A0_NATIVE'


def test_zero_budget_never_reads_hidden_ledger(agent_episode):
    def fetch(tool):raise AssertionError('hidden evidence was read')
    result=execute_policy(agent_episode,{a:agent_episode.target for a in POOL},ZeroUtility(),PositiveValue(),fetch,{t:1. for t in TOOLS},0.)
    assert result['history']==[] and result['arm']=='A0_NATIVE'


def test_temporal_roles_do_not_use_dev_or_duplicate_parents():
    r=dict(source='s',panel='p',file_sha256='a'*64,split_bounds={'train':[0,7040]})
    origins=training_origins([r]);assert len(origins)==10
    assert [o['role'] for o in origins]==['scorer_fit']*7+['acquisition_fit']*3
    meta={o['uid']:o for o in origins};assert audit_partitions(meta)=={'scorer_fit':7,'acquisition_fit':3}
    copied=dict(origins[0],role='acquisition_fit');meta['bad']=copied
    with pytest.raises(ContractError,match='parent leaks'):audit_partitions(meta)


def test_distinct_parent_names_cannot_hide_overlap():
    common=dict(source='s',horizon=192,split='train')
    meta={'a':dict(common,parent_group='a',role='scorer_fit',raw_start=0,context_end=512),
          'b':dict(common,parent_group='b',role='acquisition_fit',raw_start=600,context_end=1112)}
    with pytest.raises(ContractError,match='overlapping'):audit_partitions(meta)
