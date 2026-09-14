"""Frozen parent partitions and observable features for v4.3.1."""
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from introact_ts.v43.agent_fit import AgentDataset
from introact_ts.v43.agent_inputs import POOL,context_scale
from introact_ts.v43.data_contract import as_of

FEATURE_NAMES=('horizon_ratio','missing_fraction','longest_gap_fraction','covariate_missing_fraction',
 'gap_covariate_observed_fraction','observed_adjacent_change','log_context_scale','zero_fraction',
 'recent_zero_fraction','recent_scale_ratio','recent_level_shift','benchmark_phase','log_period')
PERIODS={'ETTm1':96,'Solar':144,'US_Term_Structure':5}

def dirty_features(e,period):
    x=e.target;obs=np.isfinite(x);v=x[obs];missing=~obs
    bounds=np.flatnonzero(np.diff(np.r_[False,missing,False]));gap=max((b-a for a,b in zip(bounds[::2],bounds[1::2])),default=0)
    scale=context_scale(e);adj=obs[:-1]&obs[1:];recent=x[-min(len(x),96):];recent=recent[np.isfinite(recent)]
    return np.array([e.horizon/192,missing.mean(),gap/len(x),np.isnan(e.covariates).mean(),
      np.isfinite(e.covariates[missing]).mean() if missing.any() else 1.,
      np.abs(np.diff(x)[adj]).mean()/scale if adj.any() else np.nan,np.log1p(scale),np.mean(v==0),
      np.mean(recent==0) if len(recent) else np.nan,np.std(recent)/scale if len(recent) else np.nan,
      (np.median(recent)-np.median(v))/scale if len(recent) else np.nan,(e.context_end%period)/period,np.log1p(period)],dtype=float)

def aligned_views(e):
    r=len(e.target)-e.horizon
    assert r>0
    full=as_of(e,r,e.horizon)
    short=replace(full,uid=full.uid+':same32',horizon=32)
    return full,short,r

def source_parent_weights(uids,meta):
    counts=Counter(meta[u]['parent_group'] for u in uids)
    per_source={s:len({meta[u]['parent_group'] for u in uids if meta[u]['source']==s}) for s in {meta[u]['source'] for u in uids}}
    w=np.array([1/(counts[meta[u]['parent_group']]*per_source[meta[u]['source']]) for u in uids])
    return w/w.sum()

class SprintData:
    def __init__(self,root='results/v431/20260914-sprint'):
        self.root=Path(root);self.old=AgentDataset('results/v43/20260914T141030.324186Z-agent')
        self.meta=json.loads((self.root/'partition.json').read_text());self.uids=list(self.meta)
        self.X=np.stack([dirty_features(self.old.episodes[u],PERIODS[self.meta[u]['source']]) for u in self.uids])
        self.L=np.array([[self.old.labels[u,a]['mase'] for a in POOL] for u in self.uids])
        self.parents=np.array([self.meta[u]['parent_group'] for u in self.uids]);self.roles=np.array([self.meta[u]['v431_role'] for u in self.uids])
    def ids(self,role):return np.flatnonzero(self.roles==role)
    def weights(self,indices):return source_parent_weights([self.uids[i] for i in indices],self.meta)
    def evidence(self,condition):
        if condition=='old32':history={u:self.old.evidence[u]['history_probe'] for u in self.uids}
        else:history=json.loads((self.root/'history/evidence.json').read_text())[condition]
        mask={u:self.old.evidence[u]['strict_mask'] for u in self.uids}
        return np.array([[np.nan if x is None else x for a in POOL for x in mask[u][a]]+[np.nan if x is None else x for a in POOL for x in history[u][a]] for u in self.uids])
