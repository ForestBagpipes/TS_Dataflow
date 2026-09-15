"""Request-visible learning units; never the outer reporting denominator."""
from dataclasses import dataclass, asdict
import numpy as np

SCALE_VERSION = 'r4-visible-seasonal-lag1-mad-eps-v1'
EPSILON = 1e-8
@dataclass(frozen=True)
class OriginScale:
    value: float
    branch: str
    period: int
    seasonal_pairs: int
    adjacent_pairs: int
    observed_values: int
    floor_applied: bool
    version: str = SCALE_VERSION
    def to_dict(self): return asdict(self)

def origin_scale(target, period, *, epsilon=EPSILON):
    x=np.asarray(target,dtype=float)
    if x.ndim != 1 or len(x)>512: raise ValueError('Only current one-dimensional context up to 512 is allowed')
    if period<1 or int(period)!=period or epsilon!=EPSILON: raise ValueError('Unregistered scale geometry')
    def differences(lag):
        ok=np.isfinite(x[lag:]) & np.isfinite(x[:-lag])
        return np.abs(x[lag:][ok]-x[:-lag][ok])
    seasonal=differences(int(period)); adjacent=differences(1);v=x[np.isfinite(x)]
    if len(seasonal)>=16: value=float(seasonal.mean());branch='seasonal'
    elif len(adjacent)>=16: value=float(adjacent.mean());branch='lag1'
    elif len(v): value=float(np.median(np.abs(v-np.median(v))));branch='visible_mad'
    else:value=0.;branch='no_visible_values'
    return OriginScale(max(value,epsilon),branch,int(period),len(seasonal),len(adjacent),len(v),value<epsilon)

FREE_NAMES=('horizon_ratio','missing_fraction','longest_gap_fraction','covariate_missing_fraction',
 'gap_covariate_observed_fraction','observed_adjacent_change','log_origin_scale','zero_fraction',
 'recent_zero_fraction','recent_scale_ratio','recent_level_shift','known_phase','log_period')

def visible_features(e,period,scale=None):
    scale=origin_scale(e.target,period) if scale is None else scale
    x=np.asarray(e.target);obs=np.isfinite(x);v=x[obs];miss=~obs
    bounds=np.flatnonzero(np.diff(np.r_[False,miss,False]));gap=max((b-a for a,b in zip(bounds[::2],bounds[1::2])),default=0)
    adj=obs[:-1]&obs[1:];recent=x[-min(len(x),96):];recent=recent[np.isfinite(recent)]
    cov=np.asarray(e.covariates)
    return np.array([e.horizon/192,miss.mean(),gap/len(x),float((~np.isfinite(cov)).mean()) if cov.size else 1.,
      float(np.isfinite(cov[miss]).mean()) if miss.any() and cov[miss].size else (1. if not miss.any() else 0.),
      np.abs(np.diff(x)[adj]).mean()/scale.value if adj.any() else np.nan,np.log1p(scale.value),np.mean(v==0) if len(v) else np.nan,
      np.mean(recent==0) if len(recent) else np.nan,np.std(recent)/scale.value if len(recent) else np.nan,
      (np.median(recent)-np.median(v))/scale.value if len(recent) else np.nan,(e.context_end%period)/period,np.log1p(period)],dtype=float)
