"""Protocol-repaired r3 controls; no changes to the frozen r3 implementation."""
from pathlib import Path
import copy,json,time
import numpy as np
import joblib
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.cli import atomic_json
from introact_ts.v431.acquisition import Charge,CostInvoice,ValueLabelRow
from introact_ts.v431_r3.response import ResponsePolicy,PSI_NAMES,state_from_results,STATE_PRIMITIVES
from introact_ts.v431_r3.acquisition import fit_acquirer,make_value_labels
from .trajectory_dataset import r3_api

STATES=('H32','H','control','equal-cost','disagreement')

def build_legacy_evidence(batch,reference_action,root=Path('results/v431-r3'),suite='main'):
    """Only acquired historical records; current supervision never enters Evidence."""
    api=r3_api();ledger,provenance=api.load_probe_ledger(Path(root),batch.family,list(batch.uids),'financial' if suite=='financial' else 'main')
    result={s:[] for s in STATES};reference=POOL[reference_action]
    for i,u in enumerate(batch.uids):
        scale=batch.rows[i]['origin_scale']['value'];atoms={}
        for atom in ('h32','long','short','second'):
            r=copy.deepcopy(ledger[u,atom])
            if r['status']=='completed':
                ratio=r['current_scale']/scale
                r['psi']['observed_mad_difference_over_current_scale']*=ratio
                r['current_scale']=scale;r['reference_arm']=reference
                r['gain']={a:(r['mae'][reference]-r['mae'][a])/scale for a in POOL}
            atoms[atom]=r
        for state in STATES:result[state].append(state_from_results(state,atoms,reference_arm=reference))
    return result,provenance

def _subset_evidence(e,ix):return {s:[rows[i] for i in ix] for s,rows in e.items()}
def _fit_terminal(batch,fit,gate,reference,estimator,evidence):
    f=batch.subset(fit);g=batch.subset(gate)
    model=ResponsePolicy(reference,list(set(f.parents)),batch.free_names,PSI_NAMES,estimator,states=STATES)
    model.fit(_subset_evidence(evidence,fit),f.losses,f.weights,f.parents,
      gate_evidence=_subset_evidence(evidence,gate),gate_losses=g.losses,gate_weights=g.weights,gate_parents=g.parents)
    return model

def staged_partition(batch):
    terminal=[];acq=[]
    for source in sorted(set(batch.sources)):
        ids=np.flatnonzero((batch.roles=='T_fit')&(batch.sources==source))
        parents=sorted(set(batch.parents[ids]),key=lambda p:min(batch.rows[i]['meta']['raw_start'] for i in ids if batch.parents[i]==p))
        n=int(np.floor(len(parents)*2/3));left=set(parents[:n])
        terminal.extend(i for i in ids if batch.parents[i] in left);acq.extend(i for i in ids if batch.parents[i] not in left)
    return np.array(sorted(terminal),int),np.array(sorted(acq),int)

def fit_staged_acquisition(batch,policy,evidence,acq_indices):
    """Call only after terminal freeze; accepts caller-corrected complete costs."""
    rows=[];a=batch.subset(acq_indices);fingerprint=policy.frozen_hash
    forbidden=set(policy.training_parent_ids)|set(policy.reference_parent_ids)
    assert not forbidden & set(a.parents)
    provenance=[]
    for j,i in enumerate(acq_indices):
        u=str(batch.uids[i]);before=policy.choose(batch.visible[i],None,fully_observed=bool(batch.fully_observed[i]))['action']
        for tool in ('H32','H','control'):
            if not batch.supported[tool][i]:continue
            after=policy.choose(batch.visible[i],evidence[tool][i],fully_observed=bool(batch.fully_observed[i]))['action']
            stop=CostInvoice((Charge('final:'+u+':'+str(before),float(batch.action_costs[i,before])),))
            ti=CostInvoice((Charge('tool:'+u+':'+tool,float(batch.tool_costs[tool][i])),))
            acquired=ti.merge(CostInvoice((Charge('final:'+u+':'+str(after),float(batch.action_costs[i,after])),)))
            rows.append(ValueLabelRow(u,str(batch.parents[i]),tool,fingerprint,tuple(batch.visible[i]),float(batch.losses[i,before]),float(batch.losses[i,after]),stop,acquired,weight=float(a.weights[j]),tool_invoice=ti))
            provenance.append({'uid':u,'parent':str(batch.parents[i]),'original_role':'T_fit','r4_usage':'legacy_internal_acquisition_holdout','legacy_label_role_token':'T_acq','tool':tool,'before_action':before,'after_action':after,'terminal_hash':fingerprint,'evidence_hash':evidence[tool][i].identity_hash})
    assert policy.frozen_hash==fingerprint
    if not rows:return None,[],provenance
    diffs=np.ravel(a.losses[:,policy.reference_action,None]-a.losses)
    acquirer=fit_acquirer(rows,fingerprint,batch.free_names,task_differences=diffs,forbidden_parents=forbidden)
    return acquirer,make_value_labels(rows,fingerprint,acquirer.lambda_value),provenance

def fit_legacy(main_batches,out,*,fit_acquisition=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if (out/'terminal_freeze.json').exists():raise RuntimeError('Refuse frozen legacy overwrite')
    bundle={'families':{},'version':'v431-r4-legacy-retrained'};manifest={'families':{},'heldout_calibration_test_reads':0,'old_acq_usage':'regression_only','states':list(STATES),'unit':'MAE/request_origin_scale','root_cost_override_supported':True}
    start=time.perf_counter()
    for family,batch in main_batches.items():
        fit=np.flatnonzero(batch.roles=='T_fit');gate=np.flatnonzero(batch.roles=='T_gate')
        assert len(set(batch.parents[fit]))==54 and len(set(batch.parents[gate]))==21
        f=batch.subset(fit);reference=int(np.argmin(np.dot(f.weights,f.losses)))
        e,provenance=build_legacy_evidence(batch,reference)
        policies={name:_fit_terminal(batch,fit,gate,reference,name,e) for name in ('residual','direct','cart')}
        small,acq=staged_partition(batch);sf=batch.subset(small);sref=int(np.argmin(np.dot(sf.weights,sf.losses)))
        se=e if sref==reference else build_legacy_evidence(batch,sref)[0]
        staged=_fit_terminal(batch,small,gate,sref,'residual',se)
        bundle['families'][family]={'full_policies':policies,'staged_policy':staged,'full_reference':reference,'staged_reference':sref,'staged_acq_indices':acq.tolist()}
        manifest['families'][family]={'full_reference':POOL[reference],'full_hashes':{k:v.frozen_hash for k,v in policies.items()},'staged_reference':POOL[sref],'staged_hash':staged.frozen_hash,
         'fit_parents':sorted(set(batch.parents[fit])),'gate_parents':sorted(set(batch.parents[gate])),'staged_terminal_parents':sorted(set(batch.parents[small])),'staged_acquisition_parents':sorted(set(batch.parents[acq])),
         'staged_effective_acquisition':{t:len(set(batch.parents[acq][batch.supported[t][acq]])) for t in ('H32','H','control')},'probe_sources':provenance,'state_support':{k:v.audit_ for k,v in policies.items()}}
    # Freeze terminal object before any corresponding acquisition labels exist.
    joblib.dump(bundle,out/'terminal_models.joblib');manifest['terminal_models_sha256']=file_hash(out/'terminal_models.joblib')
    atomic_json(out/'terminal_freeze.json',manifest)
    if fit_acquisition:
        for family,batch in main_batches.items():
            fb=bundle['families'][family];e,_=build_legacy_evidence(batch,fb['staged_reference'])
            aq,labels,prov=fit_staged_acquisition(batch,fb['staged_policy'],e,np.array(fb['staged_acq_indices']))
            fb['staged_acquirer']=aq
            atomic_json(out/(family+'.value_labels.json'),labels);atomic_json(out/(family+'.label_provenance.json'),prov)
            atomic_json(out/(family+'.acquisition_report.json'),{'status':'unsupported_no_rows'} if aq is None else aq.report)
    joblib.dump(bundle,out/'models.joblib')
    atomic_json(out/'status.json',{'status':'completed','seconds':time.perf_counter()-start,'models_sha256':file_hash(out/'models.joblib'),'dev_policy_evaluations':0,'acquisition_fitted':fit_acquisition})
    return bundle

def finalize_legacy_acquisition(main_batches,terminal_root,out):
    """Complete labels after an explicit cost-ledger correction, without refitting."""
    terminal_root,out=Path(terminal_root),Path(out)
    out.mkdir(parents=True,exist_ok=True)
    if (out/'status.json').exists():raise RuntimeError('Refuse acquisition freeze overwrite')
    manifest=json.loads((terminal_root/'terminal_freeze.json').read_text())
    assert file_hash(terminal_root/'terminal_models.joblib')==manifest['terminal_models_sha256']
    bundle=joblib.load(terminal_root/'terminal_models.joblib')
    for family,batch in main_batches.items():
        fb=bundle['families'][family];policy=fb['staged_policy']
        assert policy.frozen_hash==manifest['families'][family]['staged_hash']
        # Resolve by frozen parent identity, independent of the caller's row order.
        parents=set(manifest['families'][family]['staged_acquisition_parents'])
        ix=np.flatnonzero(np.isin(batch.parents,list(parents)))
        assert set(batch.roles[ix])=={'T_fit'}
        e,_=build_legacy_evidence(batch,fb['staged_reference'])
        aq,labels,provenance=fit_staged_acquisition(batch,policy,e,ix)
        fb['staged_acquirer']=aq
        atomic_json(out/(family+'.value_labels.json'),labels)
        atomic_json(out/(family+'.label_provenance.json'),provenance)
        atomic_json(out/(family+'.acquisition_report.json'),{'status':'unsupported_no_rows'} if aq is None else aq.report)
    joblib.dump(bundle,out/'models.joblib')
    atomic_json(out/'status.json',{'status':'completed','terminal_freeze_sha256':file_hash(terminal_root/'terminal_freeze.json'),'models_sha256':file_hash(out/'models.joblib'),'dev_policy_evaluations':0})
    return bundle
