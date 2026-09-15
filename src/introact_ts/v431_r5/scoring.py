"""Small TRAIN-only score models. No cache or future-label access at prediction."""
from dataclasses import dataclass
import hashlib
import json
import numpy as np
from introact_ts.v431_r4.trajectory_dataset import group_weights

ALPHAS = (0.1, 1.0, 10.0)
RESPONSE_NAMES = ('signed_mean', 'absolute_mean', 'absolute_max', 'first_half_absolute',
                  'second_half_absolute', 'lead_trend', 'last_difference')


def response_features(reference, candidate, scale):
    """Exactly seven paid current-task responses, in origin-scale units."""
    p0, pa = np.asarray(reference, float), np.asarray(candidate, float)
    if p0.shape != pa.shape or p0.ndim != 1 or len(p0) < 2:
        raise ValueError('Predictions must share the complete H >= 2')
    if not np.isfinite(p0).all() or not np.isfinite(pa).all() or not np.isfinite(scale) or scale <= 0:
        raise ValueError('Finite predictions and positive visible scale required')
    d = (pa-p0)/scale
    t = np.linspace(-.5, .5, len(d)); mid = len(d)//2
    return np.array([d.mean(), np.abs(d).mean(), np.abs(d).max(),
                     np.abs(d[:mid]).mean(), np.abs(d[mid:]).mean(),
                     np.dot(t, d)/np.dot(t, t), d[-1]])


def reference_features(reference, scale):
    """Seven summaries of already executed p0; never receives another action."""
    return response_features(np.zeros_like(reference, dtype=float), reference, scale)


def _check_fit(roles):
    if any(str(r) not in ('fit', 'T_fit') for r in roles):
        raise ValueError('Only fit labels may train this model')


@dataclass
class FreeReference:
    """Fixed depth-one cost-sensitive free tree, >=16 distinct active parents/leaf."""
    reference_arm: int = 2
    node: dict = None

    def fit(self, batch):
        _check_fit(batch.roles)
        x, loss = np.asarray(batch.visible, float), np.asarray(batch.losses, float)
        if np.isinf(x).any() or not np.isfinite(loss).all():
            raise ValueError('Nonfinite reference fit')
        self.impute=np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0. for c in x.T])
        x=np.where(np.isfinite(x),x,self.impute)
        p, w = np.asarray(batch.parents), np.asarray(batch.weights)
        active = ~np.asarray(batch.fully_observed, bool)
        self.training_parents = sorted(set(map(str, p)))
        self.free_names = tuple(batch.free_names)
        def leaf(mask):
            count = len(set(p[mask]))
            if count < 16:
                return dict(arm=self.reference_arm, parents=count, fallback=True)
            a = min(range(5), key=lambda a:(float(np.dot(w[mask],loss[mask,a])), a != self.reference_arm, a))
            return dict(arm=a, parents=count, fallback=False)
        self.node = leaf(active)
        best = (float(np.dot(w[active],loss[active,self.node['arm']])), 0)
        if len(set(p[active])) >= 32:
            for j in range(x.shape[1]):
                for q in sorted(set(np.quantile(x[:,j], [.25,.5,.75]).tolist())):
                    left, right = active & (x[:,j]<=q), active & (x[:,j]>q)
                    if min(len(set(p[left])), len(set(p[right]))) < 16: continue
                    l,r = leaf(left),leaf(right)
                    score = (float(np.dot(w[left],loss[left,l['arm']])+np.dot(w[right],loss[right,r['arm']])),1)
                    if score < best:
                        best=score; self.node=dict(feature=j,threshold=float(q),left=l,right=r)
        return self

    def predict(self, visible, fully_observed=False):
        if fully_observed: return 0
        if self.node is None: return self.reference_arm
        x=np.asarray(visible,float)
        if x.shape != (len(self.free_names),) or np.isinf(x).any():
            raise ValueError('Reference receives only finite whitelisted free vector')
        x=np.where(np.isfinite(x),x,self.impute)
        n=self.node
        if 'feature' in n: n=n['left'] if x[n['feature']]<=n['threshold'] else n['right']
        return int(n['arm'])


def crossfit_reference(batch):
    """Purged source-local forward fits; incomparable source clocks never pooled.

    Full read interval includes TRAIN future supervision. Related variants stay
    together. Small historical prefixes use protocol A2, not a fitted champion.
    """
    _check_fit(batch.roles)
    actions=np.full(len(batch.parents),2,int); audit=[]
    parents=np.asarray(batch.parents); sources=np.asarray(batch.sources)
    starts=np.asarray([int(r['meta']['raw_start']) for r in batch.rows])
    ends=np.asarray([int(r['meta']['context_end'])+int(r['meta']['horizon']) for r in batch.rows])
    for parent in sorted(set(parents)):
        val=parents==parent; source=set(sources[val])
        if len(source)!=1: raise ValueError('Parent crosses source identity')
        cutoff=int(starts[val].min())
        eligible=(sources==next(iter(source))) & (parents!=parent)
        train_parents=[p for p in set(parents[eligible]) if int(ends[parents==p].max())<=cutoff]
        ix=np.flatnonzero(np.isin(parents,train_parents))
        model=FreeReference().fit(batch.subset(ix)) if len(ix) else None
        for i in np.flatnonzero(val):
            actions[i]=0 if batch.fully_observed[i] else (2 if model is None else model.predict(batch.visible[i]))
        audit.append(dict(parent=str(parent),source=str(next(iter(source))),validation_read_start=cutoff,
                          training_parents=list(map(str,sorted(train_parents))),parent_count=len(train_parents),
                          training_max_read_end=int(ends[ix].max()) if len(ix) else None,
                          fallback=len(train_parents)<16,clock_rule='same-source-forward-complete-read-purge'))
    return actions,audit


class SharedRidge:
    """Shared slopes plus five action intercepts; weighted standardization fit-only."""
    def fit(self, features, actions, targets, weights, *, alpha, roles, parents=None):
        _check_fit(roles)
        if alpha not in ALPHAS: raise ValueError('Unregistered alpha')
        x=np.asarray(features,float); a=np.asarray(actions,int); y=np.asarray(targets,float); w=np.asarray(weights,float)
        if x.ndim!=2 or len(x)==0 or len(x)!=len(y) or len(a)!=len(y) or len(w)!=len(y):
            raise ValueError('Invalid training shapes')
        if np.isinf(x).any() or not all(np.isfinite(v).all() for v in (y,w)) or (w<0).any() or w.sum()<=0 or ((a<0)|(a>=5)).any():
            raise ValueError('Invalid ridge values')
        self.input_width=x.shape[1]
        self.impute=np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0. for c in x.T])
        x=np.column_stack((np.where(np.isfinite(x),x,self.impute),np.isnan(x).astype(float)))
        w=w/w.sum();self.alpha=float(alpha)
        self.mean=np.sum(w[:,None]*x,axis=0)
        self.scale=np.sqrt(np.sum(w[:,None]*(x-self.mean)**2,axis=0));self.scale[self.scale<1e-12]=1.
        design=np.column_stack(((x-self.mean)/self.scale,np.eye(5)[a]))
        self.coefficients=np.linalg.solve(design.T@(w[:,None]*design)+alpha*np.eye(design.shape[1]),design.T@(w*y))
        self.parent_count=None if parents is None else len(set(parents))
        return self

    def predict(self, features, actions):
        x=np.asarray(features,float);a=np.asarray(actions,int)
        if x.ndim==1:x=x[None,:]
        a=np.atleast_1d(a)
        if x.shape!=(len(a),self.input_width) or np.isinf(x).any() or ((a<0)|(a>=5)).any():
            raise ValueError('Finite purchased feature vector and legal action required')
        x=np.column_stack((np.where(np.isfinite(x),x,self.impute),np.isnan(x).astype(float)))
        return np.column_stack(((x-self.mean)/self.scale,np.eye(5)[a]))@self.coefficients

    @property
    def frozen_hash(self):
        payload=dict(alpha=self.alpha,impute=self.impute.tolist(),mean=self.mean.tolist(),scale=self.scale.tolist(),coefficients=self.coefficients.tolist())
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def paired_training_rows(free, predictions, scales, losses, references, parents, sources,
                         *, mode='current', history=None):
    """Offline TRAIN array builder. Runtime uses scalar response_features only.

    Caller must pass only fit rows and OOF references. All modes append seven
    fields so model capacity is equal. Historical seven fields are supplied by
    caller with their real purchased provenance; absent evidence is not zero.
    """
    if mode not in ('current','free','prior','history'): raise ValueError('Unknown mode')
    features=[];actions=[];targets=[];weights=[];ids=[]
    rowweights=group_weights(parents,sources)
    for i,ref in enumerate(references):
        p0=np.asarray(predictions[i][int(ref)],float)
        for a in range(5):
            if a==ref:continue
            if mode=='current':extra=response_features(p0,predictions[i][a],scales[i])
            elif mode=='prior':extra=reference_features(p0,scales[i])
            elif mode=='free':extra=np.zeros(7)  # explicitly absent feature block, not observed evidence
            else:
                if history is None:raise ValueError('Purchased history required')
                extra=np.asarray(history[i,a],float)
                if extra.shape!=(7,) or not np.isfinite(extra).all():continue
            features.append(np.r_[free[i],extra]);actions.append(a)
            targets.append(losses[i,int(ref)]-losses[i,a]);weights.append(rowweights[i]/4);ids.append(i)
    return dict(features=np.asarray(features),actions=np.asarray(actions),targets=np.asarray(targets),
                weights=np.asarray(weights),indices=np.asarray(ids))
