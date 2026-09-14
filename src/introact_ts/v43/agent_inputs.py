"""Fixed candidate pool and legal verification views for the minimal agent."""
from dataclasses import replace
import numpy as np
from .candidates import freeze_blocks, UnsupportedResidual
from .data_contract import as_of
from .data_io import load_context
from .p2_data import corrupt_context
from .schemas import array_hash, json_hash, require

POOL = ('A0_NATIVE','A0_FFILL','A2_SINGLE','A3_COV','A4_RIDGE_CONTEXT')
TOOLS = ('strict_mask','history_probe')


def training_origins(records, maximum=64):
    result=[]
    for r in records:
        lo,hi=r['split_bounds']['train']
        ends=list(range(lo+512,hi-192+1,704))[:maximum]
        cut=int(.7*len(ends))
        require(cut>0 and cut<len(ends),'insufficient temporal train partitions')
        for i,end in enumerate(ends):
            fields=dict(source=r['source'],panel=r['panel'],split='train',raw_start=end-512,
                        context_end=end,horizon=192,target_channel=0,data_hash=r['file_sha256'])
            result.append(dict(fields,uid=json_hash(fields),parent_group=f"{r['panel']}:{end-512}:{end+192}",
                               role='scorer_fit' if i<cut else 'acquisition_fit'))
    return result


def materialize_training(records, origins, config):
    lookup={r['source']:r for r in records};episodes=[];meta={}
    for origin in origins:
        raw=load_context(lookup[origin['source']],origin)
        for h in (96,192):
            fields={k:origin[k] for k in ('source','panel','split','raw_start','context_end','target_channel','data_hash')}
            fields['horizon']=h
            horizon_raw=replace(raw,uid=json_hash(fields),horizon=h)
            for condition in config['p2']['conditions']:
                e=corrupt_context(horizon_raw,condition,config['data']['pilot_block'],config['seed'])
                episodes.append(e)
                meta[e.uid]=dict(source=e.source,parent_group=e.parent_group,split=e.split,role=origin['role'],
                                  horizon=h,condition=condition,raw_start=e.raw_start,context_end=e.context_end,
                                  target_hash=array_hash(e.target),covariate_hash=array_hash(e.covariates))
    return episodes,meta


def mask_views(episode, length=51, seed=101):
    try:blocks=freeze_blocks(episode.target,length,seed)
    except UnsupportedResidual as exc:return [],str(exc)
    result=[]
    for i,b in enumerate(blocks):
        x=episode.target.copy();x[b]=np.nan
        result.append((replace(episode,uid=episode.uid+f':mask:{i}',target=x),b))
    return result,None


def history_views(episode):
    return [(as_of(episode,r,32),r) for r in (448,480)]


def context_scale(episode):
    x=episode.target[np.isfinite(episode.target)]
    require(len(x)>0,'all missing context unsupported')
    median=float(np.median(x));mad=float(np.median(np.abs(x-median)))
    # Feature/evidence normalizer only. The task MASE denominator is untouched.
    return max(mad,abs(median)*1e-6,1e-6)
