"""Offline TRAIN supervision and purchased-evidence ledger, not runtime state."""
from dataclasses import dataclass, fields
from collections import Counter
import importlib.util,json,time
from pathlib import Path
import numpy as np
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.schemas import array_hash
from introact_ts.v43.p2_candidates import ridge_candidate
from introact_ts.v43.data_io import file_hash
from introact_ts.v431.data import PERIODS
from introact_ts.v431.acquisition import CostInvoice
from .origin_scale import origin_scale,visible_features,FREE_NAMES,SCALE_VERSION

TOOLS={'H32':('h32',),'H':('long',),'control':('long','short')}
def r3_api():
    spec=importlib.util.spec_from_file_location('r3_fit_reader',Path('scripts/v431_r3_fit.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def group_weights(parents,sources):
    c=Counter(parents);ps={s:len(set(p for p,ss in zip(parents,sources) if ss==s)) for s in set(sources)}
    w=np.array([1/(c[p]*ps[s]) for p,s in zip(parents,sources)],float)
    return w/w.sum() if len(w) else w

@dataclass
class TrajectoryBatch:
    uids: np.ndarray
    parents: np.ndarray
    sources: np.ndarray
    roles: np.ndarray
    visible: np.ndarray
    losses: np.ndarray
    report_losses: np.ndarray
    action_costs: np.ndarray
    evidence: dict
    tool_costs: dict
    supported: dict
    fully_observed: np.ndarray
    weights: np.ndarray
    free_names: tuple
    evidence_names: dict
    rows: list
    family: str
    def subset(self,indices,*,reweight=True):
        ix=np.asarray(indices)
        if ix.dtype==bool:ix=np.flatnonzero(ix)
        kw={}
        for f in fields(self):
            v=getattr(self,f.name)
            if isinstance(v,np.ndarray):kw[f.name]=v[ix]
            elif f.name in ('evidence','tool_costs','supported'):kw[f.name]={k:a[ix] for k,a in v.items()}
            elif f.name=='rows':kw[f.name]=[v[i] for i in ix]
            else:kw[f.name]=v
        if reweight:kw['weights']=group_weights(kw['parents'],kw['sources'])
        return TrajectoryBatch(**kw)

def evidence_features(atoms,tool,scale):
    names=[];values=[]
    for atom in TOOLS[tool]:
        r=atoms[atom]
        if r['status']!='completed':return None,None
        for arm in POOL:names.append(atom+':mae_origin:'+arm);values.append(r['mae'][arm]/scale)
        for key in ('coverage','support_count'):names.append(atom+':'+key);values.append(float(r[key]))
        d=r['probe_descriptor']
        for key in ('length_horizon_ratio','target_coverage','covariate_coverage'):
            names.append(atom+':'+key);values.append(float(d[key]))
    if tool=='control':
        for arm in POOL:
            p=np.array([atoms[a]['raw_predictions'][arm] for a in TOOLS[tool]])
            names.append('raw_forecast_std_origin:'+arm);values.append(float(np.std(p,axis=0).mean()/scale))
    return tuple(names),np.asarray(values,float)

def load_data(suite='main',root=Path('results/v431-r3')):
    api=r3_api()
    if suite=='main':return api.R2Data()
    # External data do not use policy decisions. Verify immutable asset bytes,
    # avoiding r3's BLAS-derived presentation hash recomputation.
    def asset_freeze_only(path):
        frozen=json.loads((path/'models_frozen.json').read_text())
        for name,key in [('models.joblib','sha256'),('terminal_manifest.json','terminal_manifest_sha256'),
          ('value_labels.json','value_labels_sha256'),('label_provenance.json','label_provenance_sha256'),
          ('proxy_target_pairs.json','proxy_target_pairs_sha256')]:
            assert file_hash(path/name)==frozen[key], 'Frozen r3 asset changed: '+name
        manifest=json.loads((path/'terminal_manifest.json').read_text())
        for name,digest in manifest['source_hashes'].items():assert file_hash(name)==digest
        return None,manifest
    api.frozen_models=asset_freeze_only
    return api.ExternalEvaluationData(Path(root),suite)

def build_batch(data,family,*,suite='main',root=Path('results/v431-r3'),indices=None):
    api=r3_api();ix=np.arange(len(data.uids)) if indices is None else np.asarray(indices)
    uids=[data.uids[i] for i in ix]
    ledger,provenance=api.load_probe_ledger(Path(root),family,uids,'financial' if suite=='financial' else 'main')
    visible=[];scales=[];rows=[];cost=[];ev={t:[] for t in TOOLS};fees={t:[] for t in TOOLS};supported={t:[] for t in TOOLS};names={}
    for i,u in zip(ix,uids):
        e=data.episodes[u];period=PERIODS.get(e.source,5);tick=time.perf_counter();s=origin_scale(e.target,period);x=visible_features(e,period,s);diagnostic=time.perf_counter()-tick
        visible.append(x);scales.append(s.value);atoms={a:ledger[u,a] for a in ('h32','long','short','second')}
        toolrows={}
        for tool,primitives in TOOLS.items():
            tick=time.perf_counter();nn,v=evidence_features(atoms,tool,s.value);projection=time.perf_counter()-tick
            valid=v is not None
            if valid:names[tool]=nn
            ev[tool].append(v);supported[tool].append(valid)
            inv=CostInvoice().merge(*(api.invoice(atoms[a]['invoice']) for a in primitives))
            fees[tool].append(inv.total_seconds+projection)
            toolrows[tool]={'status':'completed' if valid else 'unsupported','reason':None if valid else [atoms[a].get('reason') for a in primitives if atoms[a]['status']!='completed'],
              'primitives':list(primitives),'invoice':inv.as_dict(),'projection_seconds':projection,'learning_scale':s.value,
              'metadata_applicable':all(atoms[a]['metadata_status']=='prepared' for a in primitives),
              'input_hashes':[atoms[a]['input_hash'] for a in primitives],
              'model_hashes':[atoms[a].get('model_identity_hash') for a in primitives]}
        invoices=[data.final_invoice(family,i,a,False) for a in range(5)];cost.append([v.total_seconds+diagnostic for v in invoices])
        hashes=[array_hash(data.old.pools[u][a]) for a in POOL];predhash=[array_hash(data.predictions[family][u][a]) for a in POOL]
        rebuilt,ridge_detail=ridge_candidate(e)
        assert np.allclose(rebuilt.target,data.old.pools[u][POOL[4]],rtol=1e-6,atol=1e-8,equal_nan=True), 'Current ridge replay differs numerically from frozen candidate'
        ridge_detail={**ridge_detail,'reconstruction_exact_hash':array_hash(rebuilt.target)==hashes[4],'reconstruction_max_abs_difference':float(np.nanmax(np.abs(rebuilt.target-data.old.pools[u][POOL[4]]))) if np.isfinite(rebuilt.target).any() else None}
        aliases={a:{'input_hash':hashes[k],'prediction_hash':predhash[k],
          'identical_to':[b for j,b in enumerate(POOL) if j<k and hashes[j]==hashes[k]],
          'native_alias':bool(k and hashes[k]==hashes[0]),
          'reason':'same_input_and_prediction' if k and hashes[k]==hashes[0] and predhash[k]==predhash[0] else None,
          'invoice':invoices[k].as_dict()} for k,a in enumerate(POOL)}
        aliases[POOL[4]]['support_detail']=ridge_detail
        aliases[POOL[4]]['actual_action']='A0_NATIVE' if ridge_detail['status']=='unsupported' else POOL[4]
        aliases[POOL[4]]['reason']=ridge_detail.get('reason')
        rows.append({'uid':u,'family':family,'source':e.source,'parent':e.parent_group,'role':str(data.roles[i]),'meta':data.meta[u],
          'origin_scale':s.to_dict(),'outer_report_scale':float(data.MAE[family][i,0]/data.L[family][i,0]) if data.L[family][i,0]!=0 else None,
          'target_input_hash':array_hash(e.target),'covariate_hash':array_hash(e.covariates),'mask_hash':array_hash(e.observed_mask),
          'actions':aliases,'tools':toolrows,'feature_seconds':diagnostic,'scale_version':SCALE_VERSION})
    for tool in TOOLS:
        if tool not in names:raise RuntimeError('No evidence field schema available: '+tool)
        ev[tool]=np.array([np.full(len(names[tool]),np.nan) if v is None else v for v in ev[tool]])
    parents=np.asarray([data.parents[i] for i in ix]);sources=np.asarray([data.meta[u]['source'] for u in uids])
    batch=TrajectoryBatch(np.asarray(uids),parents,sources,np.asarray(data.roles)[ix],np.asarray(visible),data.MAE[family][ix]/np.asarray(scales)[:,None],data.L[family][ix].copy(),np.asarray(cost),
      ev,{k:np.asarray(v) for k,v in fees.items()},{k:np.asarray(v,bool) for k,v in supported.items()},np.asarray(data.complete)[ix],group_weights(parents,sources),FREE_NAMES,names,rows,family)
    return batch,{'probe_sources':provenance,'scale_version':SCALE_VERSION,'suite':suite,'code_hashes':{p:file_hash(p) for p in ('src/introact_ts/v431_r4/origin_scale.py','src/introact_ts/v431_r4/trajectory_dataset.py')},'prediction_reexecution_required':False}
