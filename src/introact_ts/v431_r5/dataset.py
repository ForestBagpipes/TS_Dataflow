"""Offline r5 ledger bridge; never import this module in deployment runtime."""
import importlib.util
import json
import time
from pathlib import Path
from collections import Counter
import numpy as np
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.schemas import array_hash, json_hash
from introact_ts.v43.data_io import file_hash
from introact_ts.v431_r4.trajectory_dataset import load_data, r3_api
from introact_ts.v431_r3.probe import prepare_probe, registered_specs, visible_descriptor

OLD=Path('results/v43/20260914T141030.324186Z-agent')
R4=Path('results/v431-r4')
_DATA={}


def script(name):
    spec=importlib.util.spec_from_file_location(name,Path('scripts')/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def read(path):return json.loads(Path(path).read_text())


def model_identity(family):
    manifest=read(OLD/'model_manifest.json')
    if family=='bolt':
        m=manifest['models']['bolt']
        return dict(checkpoint=m['repo_id'],revision=m['revision'],model_dtype='bfloat16',
                    native_settings={'point':'native median quantile','input_dtype':'float32',
                                     'task':'forecast','covariate_mode':'none'},
                    source='src/introact_ts/v43/workers/chronos_worker.py',
                    source_sha256=file_hash('src/introact_ts/v43/workers/chronos_worker.py'),
                    model_manifest_sha256=file_hash(OLD/'model_manifest.json'))
    m=read('results/v431/20260914-sprint/timesfm/identity.json')
    return dict(checkpoint=m['repo_id'],revision=m['revision'],weight_sha256=m['weight_sha256'],
                model_dtype='float32',native_settings={'max_context':512,'max_horizon':192,
                'point':'native point output','normalize_inputs':True,'input_dtype':'float32',
                'full_config_source':'scripts/v431_baselines/worker.py'},
                source='scripts/v431_baselines/worker.py',source_sha256=file_hash('scripts/v431_baselines/worker.py'),
                identity_file_sha256=file_hash('results/v431/20260914-sprint/timesfm/identity.json'))


def free_history_coverage(episode,scale):
    """Current mask/as-of metadata only; does not execute a historical model."""
    prepared=prepare_probe(episode,registered_specs(episode.horizon)['long'],scale)
    if prepared.status!='prepared':return np.nan,dict(status='unsupported',reason=prepared.reason)
    return visible_descriptor(prepared.view)['covariate_coverage'],dict(status='available',input_hash=prepared.input_hash)


def load(suite,family):
    if suite not in ('main','financial') or family not in ('bolt','timesfm'):raise ValueError('Unregistered suite/family')
    begun=time.perf_counter();b=script('v431_r4_run').load_batch(suite,family)
    if suite not in _DATA:_DATA[suite]=load_data(suite)
    data=_DATA[suite];api=r3_api()
    ledger,probe_provenance=api.load_probe_ledger(Path('results/v431-r3'),family,list(b.uids),suite)
    costs=read(R4/'baseline_audit/hot_costs.json');reprice=script('v431_r4_hot_costs').reprice_invoice
    predictions=[];history=[];gov=[];forecast=[];feature_seconds=[];metadata=[];newfeature=[];coverage_audit=[]
    model=model_identity(family)
    for i,uid in enumerate(b.uids):
        e=data.episodes[uid];row=b.rows[i];S=row['origin_scale']['value'];atom=ledger[uid,'long']
        tick=time.perf_counter();coverage,coverage_state=free_history_coverage(e,S);elapsed=time.perf_counter()-tick
        newfeature.append(coverage);feature_seconds.append(float(row['feature_seconds'])+elapsed)
        old=atom.get('probe_descriptor',{}).get('covariate_coverage')
        if np.isfinite(coverage):
            if atom['status']=='completed':assert old is not None and abs(float(old)-coverage)<1e-12,'Coverage reconstruction differs'
        else:assert atom['status']!='completed','Known historical descriptor lost'
        coverage_audit.append(dict(uid=str(uid),value=None if not np.isfinite(coverage) else coverage,
             old_value=old,state=coverage_state,preparation_seconds=elapsed,models_called=0))
        raw=[np.asarray(data.predictions[family][uid][a]) for a in POOL]
        pred=np.stack(raw);assert pred.shape==(5,e.horizon) and np.isfinite(pred).all()
        gr=[];fc=[];identities=[]
        for a,name in enumerate(POOL):
            action=row['actions'][name];assert array_hash(raw[a])==action['prediction_hash'],'Changed cached prediction dtype/bytes'
            candidate=data.old.pools[uid][name]
            assert array_hash(candidate)==action['input_hash'],'Changed input version'
            hot,cold=reprice(action['invoice'],costs)
            candidate_charges=[c for c in hot['charges'] if c['key'].startswith('candidate:')]
            forecast_charges=[c for c in hot['charges'] if c['key'].startswith('forecast:')]
            assert len(candidate_charges)+len(forecast_charges)==len(hot['charges']), 'Unclassified invoice fee'
            cg=sum(c['seconds'] for c in candidate_charges);cf=sum(c['seconds'] for c in forecast_charges)
            assert abs(cg+cf+row['feature_seconds']-b.action_costs[i,a])<1e-8,'r4 hot invoice disagreement'
            gr.append(cg);fc.append(cf)
            identity=dict(source=e.source,parent=e.parent_group,origin=e.context_end,raw_start=e.raw_start,
                L=len(e.target),H=e.horizon,target_mask_hash=array_hash(e.observed_mask),
                auxiliary_mask_hash=array_hash(np.isfinite(e.covariates)),timestamps_hash=array_hash(e.timestamps),
                availability_hash=array_hash(e.availability),input_version_hash=action['input_hash'],
                model=model,prediction_hash=array_hash(raw[a]),prediction_dtype=str(raw[a].dtype),
                candidate_dtype=str(candidate.dtype),numeric_protocol='native selected point, no averaging or correction',
                arm=name,actual_arm=action.get('actual_action',name),unsupported_reason=action.get('reason'),
                alias=action.get('identical_to',[]),hot_invoice=hot,cold_seconds=cold)
            identity['cache_key']=json_hash(identity);identities.append(identity)
        predictions.append(pred);gov.append(gr);forecast.append(fc);metadata.append(identities)
        history.append(np.asarray([atom['raw_predictions'][a] for a in POOL],float) if atom['status']=='completed' else None)
    b.visible=np.column_stack((b.visible,newfeature));b.free_names=tuple(b.free_names)+('known_history_covariate_coverage',)
    feature_seconds=np.asarray(feature_seconds)
    # Keep original r4 action fee intact; r5 callers explicitly combine one
    # feature cost with actually queried governance/forecast charges.
    support={role:dict(parents=len(set(b.parents[b.roles==role])),variants=int(np.sum(b.roles==role))) for role in sorted(set(b.roles))}
    audit=dict(status='completed',suite=suite,family=family,roles=support,
        current_prediction_checks=len(b.uids)*5,coverage_rows=len(b.uids),
        coverage_supported=int(sum(np.isfinite(newfeature))),coverage_no_model_calls=True,
        current_context=512,horizons=[96,192],current_prediction_reexecutions=0,
        history_is_not_current_task=True,history_available=sum(x is not None for x in history),
        initialization_seconds=time.perf_counter()-begun,source_hashes={
            str(R4/'trajectory-final'/suite/(family+'.joblib')):file_hash(R4/'trajectory-final'/suite/(family+'.joblib')),
            str(R4/'hot_costs.json'):file_hash(R4/'hot_costs.json'),
            str(R4/'baseline_audit/hot_costs.json'):file_hash(R4/'baseline_audit/hot_costs.json'),
            'src/introact_ts/v431_r5/dataset.py':file_hash('src/introact_ts/v431_r5/dataset.py')},
        probe_provenance=probe_provenance,heldout_labels_read=False,offline_contains_train_and_old_dev_supervision=True)
    return dict(batch=b,predictions=predictions,governance_costs=np.asarray(gov),forecast_costs=np.asarray(forecast),
                history_predictions=history,feature_seconds=feature_seconds,cache_metadata=metadata,
                coverage_audit=coverage_audit,provenance=audit)
