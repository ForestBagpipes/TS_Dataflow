"""Minimal evidence-acquiring deployment policy. No task-label reader here."""
from copy import deepcopy
from dataclasses import dataclass
import time
import numpy as np
from .agent_inputs import POOL,TOOLS,context_scale
from .schemas import array_hash,json_hash,require

FEATURE_NAMES=(
    'horizon_ratio','missing_fraction','longest_gap_fraction','covariate_missing_fraction','gap_covariate_observed_fraction',
    'observed_adjacent_change','log_context_scale','filled_fraction','fill_level','fill_spread','candidate_roughness',
    *('arm_'+a for a in POOL),'mask_acquired','history_acquired','mask_mae','mask_dispersion','mask_support',
    'history_gain','history_dispersion','history_support')


@dataclass(frozen=True)
class EvidenceState:
    history: tuple=()
    values: tuple=()

    def acquire(self,tool,values):
        require(tool in TOOLS and tool not in self.history,'invalid/repeated evidence tool')
        require(set(values)==set(POOL),'incomplete tool evidence')
        frozen=tuple((a,tuple(values[a])) for a in POOL)
        require(all(len(v)==3 and all(x is None or np.isfinite(x) for x in v) for _,v in frozen),'invalid tool evidence')
        return EvidenceState(self.history+(tool,),self.values+((tool,frozen),))

    def get(self,tool,arm):
        data=dict(self.values)
        return dict(data[tool])[arm] if tool in data else (None,None,None)


def features(episode,pool,arm,state):
    require(arm in POOL and set(pool)==set(POOL),'candidate pool mismatch')
    x=episode.target;c=pool[arm];missing=np.isnan(x);observed=~missing
    scale=context_scale(episode);median=float(np.median(x[observed]))
    bounds=np.flatnonzero(np.diff(np.r_[False,missing,False]))
    longest=max((b-a for a,b in zip(bounds[::2],bounds[1::2])),default=0)
    adjacent=observed[:-1]&observed[1:]
    rough=np.isfinite(c[:-1])&np.isfinite(c[1:]);filled=missing&np.isfinite(c)
    values=[episode.horizon/192,float(missing.mean()),longest/len(x),float(np.isnan(episode.covariates).mean()),
            float(np.isfinite(episode.covariates[missing]).mean()) if missing.any() else 1.,
            float(np.abs(np.diff(x)[adjacent]).mean()/scale) if adjacent.any() else None,np.log1p(scale),
            float(filled.sum()/max(1,missing.sum())),float((np.mean(c[filled])-median)/scale) if filled.any() else None,
            float(np.std(c[filled])/scale) if filled.any() else None,
            float(np.abs(np.diff(c)[rough]).mean()/scale) if rough.any() else None,
            *[float(arm==a) for a in POOL],float('strict_mask' in state.history),float('history_probe' in state.history),
            *state.get('strict_mask',arm),*state.get('history_probe',arm)]
    require(len(values)==len(FEATURE_NAMES),'feature schema mismatch')
    # Missing evidence remains NaN for the model, with explicit acquired flags.
    return np.array([np.nan if v is None else v for v in values],dtype=np.float64)


def scores(episode,pool,state,model):
    output={'A0_NATIVE':0.}
    arms=list(POOL[1:]);vectors=np.stack([features(episode,pool,a,state) for a in arms])
    predictions=np.asarray(model.predict(vectors))
    require(predictions.shape==(len(arms),) and np.isfinite(predictions).all(),'invalid utility model output')
    keep=array_hash(pool['A0_NATIVE'])
    for arm,value in zip(arms,predictions):output[arm]=0. if array_hash(pool[arm])==keep else float(value)
    return output


def choose(episode,pool,state,model):
    values=scores(episode,pool,state,model)
    best=max(POOL,key=lambda a:values[a])
    return (best if values[best]>0 else 'A0_NATIVE'),values


def acquisition_features(episode,pool,state,model,tool):
    require(tool in TOOLS,'unknown acquisition target')
    values=scores(episode,pool,state,model)
    # Each component is drawn from the current visible state, never the ledger.
    return np.r_[np.concatenate([features(episode,pool,a,state) for a in POOL[1:]]),
                 [values[a] for a in POOL],[float(tool==t) for t in TOOLS]]


def execute_policy(episode,pool,utility,value_model,fetch,estimated_costs,budget,*,mode='learned',fixed_order=TOOLS):
    require(budget is None or np.isfinite(budget) and budget>=0,'invalid budget')
    state=EvidenceState();spent=0.;trace=[];selection_seconds=0.;overrun=False
    for step in range(2):
        start=time.perf_counter();arm,gains=choose(episode,pool,state,utility)
        remaining=float('inf') if budget is None else max(0.,budget-spent)
        eligible=[t for t in TOOLS if t not in state.history and estimated_costs[t]<=remaining]
        tool=None;values={}
        if mode in ('fixed','all'):
            tool=next((t for t in fixed_order if t in eligible),None)
        elif mode=='learned':
            for t in eligible:
                v=float(value_model.predict(acquisition_features(episode,pool,state,utility,t)[None])[0])
                require(np.isfinite(v),'nonfinite tool value');values[t]=v
            tool=max(values,key=values.get) if values and max(values.values())>0 else None
        elif mode!='simple':raise ValueError('unknown policy mode')
        selection_seconds+=time.perf_counter()-start
        before=dict(step=step,history=list(state.history),selected_before=arm,predicted_utility=gains,predicted_tool_values=values,
                    tool=tool,remaining_budget=None if budget is None else remaining,
                    visible_feature_hash=array_hash(features(episode,pool,arm,state)))
        if tool is None:
            trace.append(dict(before,status='stopped'));break
        # Fetch is the only route to hidden tool output and its actual invoice.
        evidence,cost=fetch(tool)
        require(np.isfinite(cost) and cost>=0,'invalid actual tool cost')
        state=state.acquire(tool,evidence);spent+=cost
        overrun=budget is not None and spent>budget+1e-12
        trace.append(dict(before,status='budget_overrun' if overrun else 'acquired',actual_cost=cost,cumulative_tool_cost=spent))
        if overrun:break
    start=time.perf_counter();arm,gains=choose(episode,pool,state,utility);selection_seconds+=time.perf_counter()-start
    return dict(arm=arm,history=list(state.history),tool_seconds=spent,selection_seconds=selection_seconds,
                budget=budget,budget_overrun=overrun,trace=trace,predicted_utility=gains)
