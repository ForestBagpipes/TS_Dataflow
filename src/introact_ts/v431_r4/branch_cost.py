"""TRAIN-only conservative hot-path reservations; measured cost remains separate."""
from dataclasses import dataclass
import numpy as np

@dataclass
class BranchCost:
    action_seconds: tuple
    tool_seconds: dict
    fit_parents: tuple
    diagnostics: dict
    tool_buckets: dict
    action_buckets: dict

    @classmethod
    def fit(cls, batch):
        a=np.asarray(batch.action_costs,float)
        if a.shape != (len(batch.parents),5) or not np.isfinite(a).all() or (a<0).any():
            raise ValueError('Five actual finite nonnegative final-action costs required')
        tools={}; diag={}
        for tool, costs in batch.tool_costs.items():
            valid=np.asarray(batch.supported[tool],bool)&np.isfinite(costs)
            if np.any(np.asarray(costs)[valid]<0):raise ValueError('Negative measured cost')
            tools[tool]=1.1*float(np.max(np.asarray(costs)[valid])) if valid.any() else None
            diag[tool]={'parents':len(set(np.asarray(batch.parents)[valid])), 'rows':int(valid.sum()),
                        'p50':float(np.median(np.asarray(costs)[valid])) if valid.any() else None,
                        'p95':float(np.quantile(np.asarray(costs)[valid],.95)) if valid.any() else None}
        buckets={};action_buckets={}
        if 'horizon_ratio' in batch.free_names:
            h=np.asarray(batch.visible)[:,list(batch.free_names).index('horizon_ratio')]
            for value in np.unique(h[np.isfinite(h)]):
                ok=h==value;n=len(set(np.asarray(batch.parents)[ok]))
                if n>=16:action_buckets[str(float(value))]={'seconds':(1.1*np.max(a[ok],axis=0)).tolist(),'parents':n}
            for tool,costs in batch.tool_costs.items():
                buckets[tool]={}
                for value in np.unique(h[np.isfinite(h)]):
                    ok=(h==value)&np.asarray(batch.supported[tool],bool)&np.isfinite(costs)
                    n=len(set(np.asarray(batch.parents)[ok]))
                    if n>=16:buckets[tool][str(float(value))]={'seconds':1.1*float(np.max(np.asarray(costs)[ok])),'parents':n}
        return cls(tuple((1.1*np.max(a,axis=0)).tolist()),tools,tuple(sorted(set(batch.parents))),diag,buckets,action_buckets)

    def action_estimate(self, arm, features=None):
        if features is not None and features.get('horizon_ratio') is not None:
            bucket=self.action_buckets.get(str(float(features['horizon_ratio'])))
            if bucket is not None:return bucket['seconds'][arm]
        return self.action_seconds[arm]

    def reservation(self, tool=None, features=None, arms=None):
        """Reserve any possible terminal action before acquiring hidden evidence."""
        final=max(self.action_estimate(a,features) for a in (range(5) if arms is None else arms))
        if tool is None:return final
        value=self.tool_seconds.get(tool)
        if features is not None and features.get('horizon_ratio') is not None:
            bucket=self.tool_buckets.get(tool,{}).get(str(float(features['horizon_ratio'])))
            if bucket is not None:value=bucket['seconds']
        return float('inf') if value is None else value+final

    def to_dict(self):
        return dict(action_seconds=list(self.action_seconds),tool_seconds=self.tool_seconds,
                    fit_parents=list(self.fit_parents),diagnostics=self.diagnostics,tool_buckets=self.tool_buckets,action_buckets=self.action_buckets,
                    rule='1.1 times fit maximum per tool plus maximum final action; H buckets with >=16 fit parents; global coarse fallback, no DEV timing fitting',
                    units='seconds; hot measured tool plus final governance and prediction')
