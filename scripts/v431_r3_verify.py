#!/usr/bin/env python3
"""Independent incremental r3 audit. CPU only; never opens deployment targets.

Numeric probe reconstruction deliberately does not call producer prepare/score.
Exit codes: 0 fully passed, 1 failed, 2 incomplete/pending. No source result is
overwritten. Every invocation writes a new immutable verification directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

import numpy as np

POOL = ('A0_NATIVE', 'A0_FFILL', 'A2_SINGLE', 'A3_COV', 'A4_RIDGE_CONTEXT')
FIELDS = ('target', 'covariates', 'timestamps', 'availability')
FORBIDDEN = {'targets.npz', 'task_labels.json', 'evaluator_metadata.json'}
VERIFIED_MODEL_FILES = {}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def ah(value):
    a = np.array(value, copy=True, order='C')
    if a.dtype.kind not in 'biuf':
        raise ValueError('Only numeric arrays may be audited')
    if a.dtype.kind == 'f':
        a[np.isnan(a)] = np.nan
    header = json.dumps([a.dtype.str, list(a.shape)], separators=(',', ':'))
    return hashlib.sha256(header.encode() + b'\0' + a.tobytes()).hexdigest()


def jh(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def arrays(path):
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k].copy() for k in f.files}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def eq(a, b, name):
    require(np.array_equal(np.asarray(a), np.asarray(b), equal_nan=True), name)


def close(a, b, name):
    require(np.isfinite(a) and np.isfinite(b) and np.isclose(a, b, rtol=1e-11, atol=1e-12), name)


def barrier(event, arguments):
    if event == 'open' and isinstance(arguments[0], (str, bytes, os.PathLike)):
        require(Path(os.fsdecode(arguments[0])).name not in FORBIDDEN,
                'Verifier prohibits deployment-future/evaluator files')


class Audit:
    def __init__(self, phase):
        self.phase = phase
        self.checks = Counter()
        self.failures = []
        self.pending = []
        self.details = {}

    def check(self, category, key, fn):
        try:
            value = fn()
            self.checks[category] += 1
            return value
        except Exception as exc:
            self.failures.append(dict(category=category, key=str(key),
                                      error=type(exc).__name__ + ': ' + str(exc)))
            return None

    @property
    def status(self):
        return 'failed' if self.failures else 'pending' if self.pending else 'passed'


def expected_spec(h, name):
    require(h in (96, 192), 'Unregistered task horizon')
    start, origin, horizon = {'h32': (0, 480, 32), 'long': (0, 512-h, h),
                              'short': (64, 512-h, h), 'second': (0, 448-h, h)}[name]
    return dict(name=name, start=start, origin=origin, horizon=horizon, current_origin=512)


def reconstruct(current, meta, row, scale, *, saved_view=True):
    """Independent numpy implementation of the registered readable intervals."""
    spec = row['spec'];name = spec['name']
    require(spec == expected_spec(meta['horizon'], name), 'Spec changed registered origin/H/64')
    require(meta['split'] in ('train', 'dev'), 'Held-out episode in probe suite')
    require(len(current['target']) == 512, 'Current context length changed')
    require(meta['context_end'] - meta['raw_start'] == 512, 'Original row interval changed')
    require(np.isfinite(scale) and scale > 0, 'Nonpositive TRAIN MASE scale')
    require(all(len(current[k]) == 512 for k in FIELDS), 'Context fields disagree')
    t = current['timestamps'];a = current['availability']
    v = np.c_[current['target'], current['covariates']]
    require(a.shape == v.shape and np.all(np.diff(t) > 0), 'Timestamp/availability shape or order')
    require(not np.isinf(v).any(), 'Infinity cannot become a missing observation')
    require(not np.any(np.isfinite(v) & (a > t[-1])), 'Current unavailable value exposed')
    start, origin, horizon = spec['start'], spec['origin'], spec['horizon']
    target = current['target'][origin:origin+horizon]
    mask = np.isfinite(target) & (a[origin:origin+horizon, 0] <= t[-1])
    rr, cc = np.where(~np.isfinite(v));shifted = rr + origin - 512
    outside = (shifted < start) | (shifted >= origin)
    reason = 'copied_current_gap_outside_probe_prefix' if outside.any() else None
    if reason is None and mask.sum() < max(16, int(np.ceil(horizon/2))):
        reason = 'insufficient_currently_observed_historical_validation'
    current_hash = jh({k: ah(current[k]) for k in FIELDS})
    identity = dict(base_uid=row['base_uid'], current_input_hash=current_hash, spec=spec,
                    mask_policy='all_visible_channel_missing_at_fixed_origin_relative_lags')
    copied = np.zeros((origin-start, v.shape[1]), dtype=bool)
    if reason:
        identity.update(status='unsupported', reason=reason,
                        outside_gap_positions=[[int(r), int(c)] for r,c in zip(shifted[outside], cc[outside])])
        values = None
    else:
        copied[shifted-start, cc] = True
        pv = v[start:origin].copy()
        pv[a[start:origin] > t[origin-1]] = np.nan
        pv[copied] = np.nan
        values = dict(target=pv[:,0], covariates=pv[:,1:], timestamps=t[start:origin],
                      availability=a[start:origin], raw_mask=np.isfinite(pv[:,0]),
                      copied_mask=copied, historical_validation=target, scoring_mask=mask)
        identity['fields'] = {k: ah(values[k]) for k in ('target', 'covariates', 'timestamps', 'availability', 'raw_mask')}
    require(row['status'] == ('unsupported' if reason else 'prepared') and row['reason'] == reason,
            'Support changed or failure silently replaced')
    require(row['current_input_hash'] == current_hash and row['input_hash'] == jh(identity), 'Probe input identity mismatch')
    require(row['spec_hash'] == jh(spec), 'Probe spec hash mismatch')
    for key, val in [('scoring_mask_hash', mask), ('historical_validation_hash', target), ('copied_mask_hash', copied)]:
        require(row[key] == ah(val), 'Probe '+key+' mismatch')
    require(row['support_count'] == int(mask.sum()), 'Historical score denominator changed')
    close(row['coverage'], float(mask.mean()), 'Historical score coverage changed')
    close(row['current_scale'], scale, 'Probe is not in fixed current-task MASE units')
    require(row.get('future_labels_read') == 0, 'Producer reports deployment future read')
    if values is not None:
        canonical = jh(dict(horizon=horizon, raw_mask=ah(values['raw_mask']),
                            **{k: ah(values[k]) for k in FIELDS}))
        if saved_view:
            require(row['cache_input_hash'] == canonical, 'Canonical payload hash differs from real view')
            require(row['raw_start'] == meta['raw_start']+start and row['context_end'] == meta['raw_start']+origin,
                    'Historical original-row boundary mismatch')
            require(sha(row['array_path']) == row['array_sha256'], 'Prepared view file changed')
            saved = arrays(row['array_path'])
            require(set(saved) == set(values), 'Unexpected/missing prepared view fields')
            for k in values:
                eq(saved[k], values[k], 'Prepared view mismatch: '+k)
    return dict(values=values, target=target, mask=mask, spec=spec, row=row, scale=scale,
                current=current, meta=meta)


def invoice(inv):
    charges = inv['charges'];keys = [c['key'] for c in charges]
    require(len(keys) == len(set(keys)), 'Shared cost charged twice in one invoice')
    require(all(np.isfinite(c['seconds']) and c['seconds'] >= 0 for c in charges), 'Invalid actual charge')
    close(sum(c['seconds'] for c in charges), inv['total_seconds'], 'Invoice total disagrees')
    return {c['key']: c['seconds'] for c in charges}


def ridge_unavailable(values):
    """Independent support predicates of frozen ridge; no model/output fallback."""
    x,z=values['target'],values['covariates'];missing=np.isnan(x)
    if not missing.any():return None
    if z.shape[1]==0 or np.isfinite(z[missing]).mean()<.5:return 'insufficient gap covariates'
    valid=np.isfinite(x)
    if valid.sum()<32:return 'insufficient residual support'
    columns=np.any(np.isfinite(z[valid]),axis=0)
    if not columns.any():return 'no supported covariates'
    if 2*int(columns.sum())>8 and min(8,int(columns.sum()),int(valid.sum())//8)<1:
        return 'insufficient PCA support'
    return None


def cached(path):
    path = Path(path)
    # Producer keeps retry/orphan NPZ files and binds a timestamped data file
    # from a canonical 64-hex JSON sidecar. Never infer the latest retry.
    rec = read(path.with_name(path.name.split('.')[0]+'.json'))
    require(rec['status'] == 'completed', 'Incomplete cache used')
    require(Path(rec['array_path']).resolve() == path.resolve(), 'Cache file path mismatch')
    require(sha(path) == rec['array_sha256'], 'Cache file hash mismatch')
    data = arrays(path)
    require(set(data) == set(POOL), 'Cache five-arm denominator changed')
    require({a:ah(data[a]) for a in POOL} == rec['array_hashes'], 'Cache array hash mismatch')
    return rec, data


def raw_session(path, *, source_override=None):
    """Validate native raw outputs and requests; no model loading or evaluation."""
    path = Path(path);model = read(path/'model_manifest.json');code = read(path/'code_manifest.json')
    sources = read(path/'producer_sources.json') if source_override is None else source_override
    require(jh(code['files'])==code['hash'],'Legacy worker code identity malformed')
    for filename,digest in code['files'].items():
        require(sha(filename)==digest,'Legacy worker source changed: '+filename)
    for filename,digest in sources.items():
        require(sha(filename) == digest, 'Producer source changed: '+filename)
    result = [];files = {};index = defaultdict(list)
    for response_path in sorted(path.glob('*.response.json')):
        response = read(response_path)
        if response['status'] == 'loaded':
            continue
        require(response['status'] == 'completed', 'A failed raw response cannot be hidden')
        prefix = str(response_path)[:-len('.response.json')]
        request_path = Path(prefix+'.request.json');request = read(request_path)
        key = request['model_key'];record = model['models'][key]
        for item in record.get('files',{}).values():
            fp=Path(item['path']);st=fp.stat();identity=(str(fp.resolve()),st.st_size,st.st_mtime_ns,item['sha256'])
            if identity not in VERIFIED_MODEL_FILES:
                require(sha(fp)==item['sha256'],'Actual model/checkpoint file changed')
                VERIFIED_MODEL_FILES[identity]=True
        require(sha(request['model_manifest'])==sha(path/'model_manifest.json'),'Worker used another actual model manifest')
        server='scripts/serve_v431_r2_timesfm.py' if key=='timesfm' else 'scripts/serve_v43_model.py'
        require(response['service_sha256']==sha(server),'Actual server source changed')
        for name in ('request_id','model_revision','model_key','code_hash','environment_hash','task','horizon','dtype','seed','covariate_mode','normalization'):
            require(request[name] == response[name], 'Request-response identity mismatch: '+name)
        require(request['model_revision'] == record['revision'], 'Raw response changed model revision')
        require(request['code_hash'] == code['hash'], 'Raw response changed code identity')
        require(request['environment_hash'] == record['environment_lock_sha256'] == sha(record['environment_lock']), 'Environment lock changed')
        require(Path(response['worker_python']).resolve() == Path(record['environment_python']).resolve(), 'Wrong worker interpreter')
        require(response['units'] == 'original', 'Worker changed physical units')
        pp = Path(prefix+'.predictions.npz');rp = Path(response['raw_predictions']['path'])
        require(sha(rp) == response['raw_predictions']['sha256'], 'Native raw file hash changed')
        raw,pred = arrays(rp),arrays(pp)
        require(len(request['rows']) == len(response['rows']) == len(pred) == len(raw), 'Raw request/output denominator changed')
        for i,(rq,rs) in enumerate(zip(request['rows'], response['rows'])):
            for name,value in rq.items():
                require(rs[name] == value, 'Worker rewrote request row '+name)
            x = arrays(rq['array_path']);point = pred[f'row_{i}'];native = raw[f'row_{i}']
            for name,hname in [('target','input_hash'),('covariates','covariate_hash'),('raw_mask','raw_mask_hash'),('timestamps','timestamps_hash'),('availability','availability_hash')]:
                require(ah(x[name]) == rq[hname], 'Worker input hash mismatch '+name)
            require(np.isfinite(native).all() and np.isfinite(point).all(), 'Nonfinite model response')
            require(ah(native) == rs['raw_hash'] and ah(point) == rs['prediction_hash'], 'Raw/point content hash mismatch')
            require(list(native.shape) == rs['raw_shape'] and list(point.shape) == rs['shape'], 'Raw/point shape mismatch')
            if key == 'bolt':
                require(native.shape == (1,9,request['horizon']), 'Unexpected frozen Bolt quantile shape')
                actual = native[0,4].astype(request['dtype'])
            elif key == 'tsicl':
                require(native.shape == (1,1,len(x['target']),3), 'Unexpected frozen TS-ICL quantile shape')
                actual = native[0,0,:,1].astype(request['dtype'])
                actual[np.isfinite(x['target'])] = x['target'][np.isfinite(x['target'])]
            elif key == 'timesfm':
                native_record = arrays(rs['raw_native_file'])
                eq(native_record['input'][0,:,0], x['target'], 'Native TimesFM input differs')
                eq(native_record['quantiles'], native, 'Native TimesFM quantiles differ')
                actual = native_record['point'][0].astype(request['dtype'])
            else:
                raise AssertionError('Unregistered actual backbone '+key)
            eq(point, actual, 'Point prediction is not frozen native estimator')
            entry = dict(model_key=key, task=request['task'], mode=request['covariate_mode'],
                               horizon=request['horizon'], uid=rq['episode_uid'], arm=rq['candidate_id'],
                               input=x, point=point, row=rs, request=str(request_path),
                               session=str(path))
            result.append(entry)
            index[key,request['horizon'],*(ah(x[k]) for k in ('target','covariates','timestamps','availability'))].append(entry)
        for p in (request_path,response_path,pp,rp):files[str(p)] = sha(p)
    invoices = read(path/'model_invoices.json') if (path/'model_invoices.json').exists() else []
    return dict(rows=result, index=index, model=model, code=code, sources=sources, files=files, invoices=invoices)


def verify_record(record, prepared, sessions):
    row = prepared['row'];family = record['family']
    require(family in ('bolt','timesfm'), 'Unknown family')
    for name in ('input_hash','spec','scoring_mask_hash','current_scale','support_count','coverage'):
        require(record[name] == row[name], 'Atomic result changed '+name)
    if row['status'] == 'unsupported':
        require(record['status'] == 'unsupported' and record['reason'] == row['reason'], 'Unsupported became success')
        require(not record['mae'] and not record['gain'] and not record['raw_predictions'], 'Unsupported evidence filled with zero')
        return None
    require(record['status'] == 'completed', 'Supported probe has no actual result')
    require(record.get('future_labels_read') == 0, 'Future read in probe output')
    ref = read('results/v431-r3/reference_manifest.json')
    require(record['reference_arm'] == ref['families'][family]['arm'] and record['reference_manifest_hash'] == jh(ref), 'Reference changed')
    cc, candidates = cached(record['candidate_cache']);fc, forecasts = cached(record['forecast_cache'])
    family_identity = fc['identity']['family_hash'];producer = sessions[fc['producer_session']]
    expected_family = jh(dict(family=family, model=producer['model']['models'][family], code=producer['code']['hash'], source=jh(producer['sources'])))
    require(family_identity == expected_family == record['model_identity_hash'], 'Actual model/cache identity changed')
    require(fc['identity']['candidate_hashes'] == {a:ah(candidates[a]) for a in POOL}, 'Forecast cache used other candidates')
    governance = sessions[cc['producer_session']]
    require(cc['identity']['governance_hash'] == jh(dict(model=governance['model']['models']['tsicl'], code=governance['code']['hash'], source=jh(governance['sources']))), 'Governance identity changed')
    values = prepared['values'];observed = values['raw_mask'];x = values['target']
    canonical = jh(dict(horizon=row['spec']['horizon'], raw_mask=ah(observed),
                        **{k:ah(values[k]) for k in FIELDS}))
    require(record['cache_input_hash'] == row['cache_input_hash'] == canonical,
            'Atomic/cache alias input identity mismatch')
    require(cc['identity']['input_hash'] == fc['identity']['input_hash'] == canonical,
            'Cache keyed by another physical input')
    require(record['raw_worker_session'] == fc['producer_session'], 'Raw worker lineage changed')
    fallback=[]
    for arm in POOL:
        require(candidates[arm].shape == x.shape and candidates[arm].dtype == x.dtype, 'Candidate changed time/dtype')
        eq(candidates[arm][observed], x[observed], 'Candidate overwrote an observed value')
        if arm == 'A0_NATIVE':eq(candidates[arm], x, 'KEEP is not native dirty input')
        elif arm=='A4_RIDGE_CONTEXT' and not np.isfinite(candidates[arm]).all():
            reason=ridge_unavailable(values)
            require(reason is not None, 'Ridge nonfinite without a declared support failure')
            eq(candidates[arm],x,'Unsupported ridge is not exact native fallback')
            fallback.append(dict(arm=arm,status='unsupported',fallback='A0_NATIVE',reason=reason,
                                 provenance='independent_context_support_reconstruction; producer omitted status metadata'))
        else:require(np.isfinite(candidates[arm]).all(), 'Non-native candidate contains failed fill')
        if arm in ('A2_SINGLE','A3_COV') and not observed.all():
            hits = governance['index'].get(('tsicl',row['spec']['horizon'],*(ah(values[k]) for k in ('target','covariates','timestamps','availability'))), [])
            mode = 'none' if arm == 'A2_SINGLE' else 'past_only'
            require(any(r['mode']==mode and np.array_equal(r['point'],candidates[arm]) for r in hits),
                    'TS-ICL candidate lacks raw actual generation')
        pred = np.asarray(record['raw_predictions'][arm], dtype=forecasts[arm].dtype)
        require(pred.shape == (row['spec']['horizon'],) and np.isfinite(pred).all(), 'Invalid raw historical prediction')
        eq(pred, forecasts[arm], 'Recorded forecast differs from immutable cache')
        require(record['prediction_hashes'][arm] == ah(pred), 'Prediction identity mismatch')
        mae = float(np.mean(np.abs(pred[prepared['mask']] - prepared['target'][prepared['mask']])))
        close(mae, record['mae'][arm], 'Historical MAE/score mask mismatch')
    for arm in POOL:
        close((record['mae'][record['reference_arm']] - record['mae'][arm])/prepared['scale'],
              record['gain'][arm], 'Historical gain not fixed current MASE units')
    aliases = fc['aliases'];require(set(aliases) == set(POOL), 'Missing forecast aliases')
    distinct = {}
    for arm in POOL:
        alias = aliases[arm];require(alias in POOL, 'Unregistered alias')
        eq(candidates[arm], candidates[alias], 'Aliased inputs differ')
        eq(forecasts[arm], forecasts[alias], 'Aliased forecasts differ')
        close(fc['arm_seconds'][arm], fc['arm_seconds'][alias], 'Alias repricing differs')
        distinct[alias] = fc['arm_seconds'][arm]
        hits = producer['index'].get((family,row['spec']['horizon'],ah(candidates[arm]),
                                     *(ah(values[k]) for k in ('covariates','timestamps','availability'))), [])
        require(hits, 'No actual worker request for cached candidate')
        require(any(np.array_equal(r['point'],forecasts[arm]) for r in hits), 'Cached point has no raw worker provenance')
        invoice_hits = [i for i in producer['invoices'] for hit in hits
                        if i['episode_uid']==hit['uid'] and i['arm']==hit['arm']
                        and hit['request'].endswith(i['shard']+'.request.json')]
        if family == 'timesfm':
            native_files = {h['row']['raw_native_file'] for h in hits}
            original = [h for h in producer['rows'] if h['model_key']=='timesfm'
                        and h['row']['raw_native_file'] in native_files and not h['row']['cache_hit']]
            invoice_hits = [i for i in producer['invoices'] for hit in original
                            if i['episode_uid']==hit['uid'] and i['arm']==hit['arm']
                            and hit['request'].endswith(i['shard']+'.request.json')]
        require(any(np.isclose(i['charged_seconds'],fc['arm_seconds'][arm],rtol=1e-11,atol=1e-12)
                    for i in invoice_hits), 'Forecast cost is not original actual worker invoice')
    # Equal candidate values must share a forecast, not be billed as separate arms.
    for arm in POOL:
        for other in POOL:
            if ah(candidates[arm]) == ah(candidates[other]):
                require(aliases[arm] == aliases[other], 'Equal five-arm input double charged')
    close(sum(distinct.values()), fc['actual_forecast_seconds'], 'Forecast alias sum mismatch')
    close(sum(cc['direct_seconds'].values()), cc['generation_seconds'], 'Governance component sum mismatch')
    charge = invoice(record['invoice'])
    for kind, amount in [('probe-prepare:',row['preparation_seconds']), ('probe-candidates:',cc['generation_seconds']),
                         ('probe-forecast:',fc['actual_forecast_seconds'])]:
        billed = [v for k,v in charge.items() if k.startswith(kind)]
        require(len(billed) == 1, 'Missing or duplicate cost component '+kind)
        close(billed[0], amount, 'Invoice component repricing changed '+kind)
    return dict(candidates=candidates, forecasts=forecasts, record=record, fallback=fallback)


def audit_probes(audit, root, suite, backend_check, selected_sessions=()):
    out = root/'probes'/suite
    if not (out/'preparation.json').exists():
        audit.pending.append('Missing prepared suite '+str(out));return
    prep = read(out/'preparation.json')
    for name,digest in prep['files'].items():
        audit.check('frozen_preparation',name,lambda p=out/name,h=digest: require(sha(p)==h,'Prepared file changed'))
    meta = read(out/'episode_manifest.json');context = arrays(out/'contexts.npz');scales = read(out/'mase_scales.json')
    manifest = read(out/'probe_manifest.json');prepared = {}
    session_dirs=sorted((out/'sessions').glob('*')) if (out/'sessions').exists() else []
    if selected_sessions:
        selected={Path(p).resolve() for p in selected_sessions}
        session_dirs=[p for p in session_dirs if p.resolve() in selected]
        require(len(session_dirs)==len(selected),'Requested verification session does not exist in suite')
        parents=set()
        for p in session_dirs:
            if (p/'records.json').exists():parents.update(r['parent_group'] for r in read(p/'records.json'))
        manifest=[r for r in manifest if r['parent_group'] in parents]
        audit.details['scope']='explicit session subset; not full-suite validation'
    for row in manifest:
        uid = row['base_uid'];key = uid,row['spec']['name']
        require(key not in prepared,'Duplicate input manifest row')
        result = audit.check('independent_context_geometry',key,lambda row=row,uid=uid: reconstruct(
            {k:context[uid+'_'+k] for k in FIELDS},meta[uid],row,scales[meta[uid]['source']]))
        if result is not None:prepared[key] = result
    roles = defaultdict(set)
    for m in meta.values():roles[m['parent_group']].add(m['v431_role'])
    audit.check('parent_isolation',suite,lambda: require(all(len(v)==1 for v in roles.values()),'Parent crosses training/evaluation role'))
    actual = {};session_records = [];session_paths = set();statuses=[]
    for session in session_dirs:
        status = read(session/'status.json');statuses.append(dict(path=str(session),**status))
        if status['status'] != 'completed':audit.pending.append('Producer session '+str(session)+' '+status['status'])
        if not (session/'records.json').exists():continue
        if status.get('records_sha256'):
            audit.check('session_records_hash',session,lambda s=session,st=status: require(sha(s/'records.json')==st['records_sha256'],'Session records changed'))
        rows = read(session/'records.json');session_records.extend(rows)
        for r in rows:
            if r['status']=='completed':
                cc,_=cached(r['candidate_cache']);fc,_=cached(r['forecast_cache'])
                session_paths.update((cc['producer_session'],fc['producer_session']))
    sessions = {}
    for path in sorted(session_paths):
        result = audit.check('actual_raw_worker',path,lambda path=path:raw_session(path))
        if result is not None:sessions[path]=result
    for r in session_records:
        key = r['base_uid'],r.get('probe',r['spec']['name']);family=r['family']
        if key not in prepared:continue
        result=audit.check('atomic_result',(family,*key),lambda r=r,key=key:verify_record(r,prepared[key],sessions))
        if result is not None:
            old=actual.get((family,*key))
            if old is not None:
                audit.check('resume_agreement',(family,*key),lambda old=old,r=r:require(old['record']['prediction_hashes']==r['prediction_hashes'],'Resume changed actual predictions'))
            actual[family,*key]=result
    pairs=[];preprocessing=[];information_identical=[];backend_memo={}
    for family in ('bolt','timesfm'):
        for uid in meta:
            lk,sk=(family,uid,'long'),(family,uid,'short')
            if lk not in actual or sk not in actual:continue
            long,short=actual[lk],actual[sk];l=long['record'];s=short['record']
            def pair():
                for key in ('model_identity_hash','reference_arm','scoring_mask_hash','current_scale'):
                    require(l[key]==s[key],'Incomparable long/short '+key)
                require(l['spec']['origin']==s['spec']['origin'] and l['spec']['horizon']==s['spec']['horizon'] and s['spec']['start']-l['spec']['start']==64,'Long/short geometry changed')
                scale=l['current_scale'];kappa={a:((l['mae'][l['reference_arm']]-l['mae'][a])-(s['mae'][s['reference_arm']]-s['mae'][a]))/scale for a in POOL}
                return dict(family=family,base_uid=uid,kappa=kappa,z={a:(512-(l['spec']['origin']-l['spec']['start']))/64*kappa[a] for a in POOL},current_scale=scale)
            p=audit.check('paired_gain_current_scale',(family,uid),pair)
            if p is not None:pairs.append(p)
            if backend_check:
                from introact_ts.v431_r3.backend_inputs import compare_inputs
                for arm in POOL:
                    memo_key=(family,ah(long['candidates'][arm]),ah(short['candidates'][arm]))
                    def compare(arm=arm,memo_key=memo_key):
                        if memo_key not in backend_memo:
                            backend_memo[memo_key]=compare_inputs(long['candidates'][arm],short['candidates'][arm],family)
                        return dict(backend_memo[memo_key])
                    rec=audit.check('official_preprocessing',(family,uid,arm),compare)
                    if rec is not None:
                        rec.update(base_uid=uid,arm=arm);preprocessing.append(rec)
                        if rec['actual_preprocessing_identical']:information_identical.append(rec)
    expected=sum(s['requested_probes'] for s in statuses) if selected_sessions else len(manifest)*2
    seen={(r['family'],r['base_uid'],r.get('probe',r['spec']['name'])) for r in session_records}
    if len(seen)<expected:audit.pending.append(f'Atomic family coverage {len(seen)}/{expected}; no failure-window deletion')
    if pairs and not backend_check:audit.pending.append('Official preprocessing not checked; use --backend-inputs in existing Chronos CPU environment')
    audit.details.update(suite=suite,prepared_probes=len(manifest),preparation_support=dict(Counter(r['status'] for r in manifest)),
                         expected_family_records=expected,available_family_records=len(seen),sessions=statuses,
                         independent_pairs=pairs,actual_backend_input_comparisons=preprocessing,
                         distinct_backend_preprocessing_pairs=len(backend_memo),
                         response_invalid_same_actual_information=information_identical,
                         explicit_ridge_fallbacks=[dict(family=k[0],base_uid=k[1],probe=k[2],**fb)
                                                  for k,v in actual.items() for fb in v['fallback']],
                         model_accuracy_claim=False,new_future_labels_read=0,heldout_labels_read=0)


def audit_models(audit, root):
    """Frozen hashes, TRAIN parent/source weighting, fitted support and value math."""
    path=root/'terminal_freeze.json'
    if not path.exists():audit.pending.append('Missing frozen terminal manifest '+str(path));return
    import joblib
    freeze=read(path);manifest=read(root/'terminal_manifest.json')
    require(sha(root/'terminal_models.joblib')==freeze['sha256'],'Terminal model artifact changed')
    require(sha(root/'terminal_manifest.json')==freeze['terminal_manifest_sha256'],'Terminal manifest changed')
    for p,h in manifest['source_hashes'].items():
        audit.check('terminal_sources',p,lambda p=p,h=h:require(sha(p)==h,'Fitted source changed'))
    ref=read(root/'reference_manifest.json')
    require(jh(ref['families'])==ref['reference_hash']==manifest['reference_hash'],'Frozen reference mismatch')
    require(manifest['heldout_labels_read']==0 and manifest['dev_results_consulted_for_fit'] is False,'Illegal fitted label role')
    config=read('configs/v431_r3/manifest.json')
    require(sha('configs/v431_r3/manifest.json')==manifest['config_sha256'],'Fit registration changed')
    require(config['ridge_alphas']==[.1,1,10] and manifest['budgets']==config['budgets'],'Unregistered fit search/budget')
    partition=read('results/v431/20260914-sprint/partition.json')
    ids={r:[u for u,m in partition.items() if m['v431_role']==r] for r in ('T_fit','T_gate','T_check','T_acq','dev')}
    parents={r:{partition[u]['parent_group'] for u in us} for r,us in ids.items()}
    counts={'T_fit':54,'T_gate':21,'T_check':17,'T_acq':18,'dev':26}
    for role,expected in counts.items():
        require(len(parents[role])==expected,'Independent parent denominator changed: '+role)
        if role!='dev':require(set(manifest[role[2:].lower()+'_parent_ids'])==parents[role],'Frozen role parent list mismatch')
        for other in counts:
            if other!=role:require(not parents[role]&parents[other],'Parent crosses roles')
    ranges={}
    for uid,m in partition.items():
        key=m['source'],m['parent_group'];lo,hi=m['raw_start'],m['context_end']+m['horizon']
        if key in ranges:lo,hi=min(lo,ranges[key][0]),max(hi,ranges[key][1])
        ranges[key]=lo,hi,m['v431_role']
    for source in {s for s,_ in ranges}:
        intervals=sorted((lo,hi,role,p) for (s,p),(lo,hi,role) in ranges.items() if s==source)
        for i,left in enumerate(intervals):
            for right in intervals[i+1:]:
                if right[0]>=left[1]:break
                require(left[2]==right[2],'Raw full-read interval crosses fitted/evaluation role')
    def weights(uids):
        n=Counter(partition[u]['parent_group'] for u in uids)
        bysource=defaultdict(set)
        for u in uids:bysource[partition[u]['source']].add(partition[u]['parent_group'])
        w=np.array([1/(n[partition[u]['parent_group']]*len(bysource[partition[u]['source']])) for u in uids])
        return w/w.sum()
    terminal=joblib.load(root/'terminal_models.joblib')['policies'];signatures={}
    for family,policies in terminal.items():
        require(family in ('bolt','timesfm') and set(policies)=={'residual','direct','cart'},'Terminal comparator matrix changed')
        fm=manifest['families'][family]
        require(fm['reference']==ref['families'][family],'Terminal changed family reference')
        for method,p in policies.items():
            def policy_check(p=p,method=method):
                d=p.to_dict();digest=jh(d)
                require(digest==p.frozen_hash==fm['terminal_hashes'][method]==freeze['terminal_hashes'][family][method],'Policy hash drift')
                require(set(d['fit_parent_ids'])==parents['T_fit'] and set(d['gate_parent_ids'])==parents['T_gate'],'Fit/gate model overlap')
                require(set(d['training_parent_ids'])==parents['T_fit']|parents['T_gate'],'Training parent scope changed')
                require(set(d['reference_parent_ids'])<=parents['T_fit']|parents['T_gate'],'Reference uses other role')
                require(d['reference_gain']==0 and d['tie_action']==d['reference_action'],'Reference zero/tie altered')
                require(not d['kappa_clipped'],'Signed response clipped')
                for name in d['feature_names']:
                    require(not any(x in name.lower() for x in ('source','path','future','oracle','label','true_')),'Forbidden dirty-only feature')
                for role,key in [('T_fit','fit'),('T_gate','gate')]:
                    require(ah(weights(ids[role]))==d['training_identity'][key+'_weights'],'Source/parent weights changed')
                    require(jh([partition[u]['parent_group'] for u in ids[role]])==d['training_identity'][key+'_parent_hash'],'Training row order/parent identity changed')
                    for state in d['states']:
                        require(len(d['training_identity'][key+'_evidence_hashes'][state])==len(ids[role]),'Evidence training denominator changed')
                for state,r in d['audit'].items():
                    require(r['fit_role']=='T_fit' and r['selection_role']=='T_gate','State selection role changed')
                    if r['status']!='fitted':
                        require(state not in d['models'] and bool(r.get('reason')),'Unsupported state replaced with a fake model');continue
                    require(r['fit_supported_parents']>=16 and r['gate_supported_rows']>0,'Unsupported state fitted')
                    if method=='cart':
                        require(min(r['leaf_parent_counts'].values())>=16 and r['cart_config']['max_depth']<=3,'CART parent/depth cap violated')
                    else:
                        require(r['alpha_candidates']==[.1,1.,10.],'Alpha grid expanded')
                        expected=min(r['gate_candidates'],key=lambda v:(v['weighted_task_risk'],v['alpha']))
                        require(r['alpha']==expected['alpha'],'Alpha not train-gate minimum')
                        m=d['models'][state];transform=m['transform']
                        require(np.isfinite(m['coefficients']).all() and np.isfinite(transform['mean']).all()
                                and np.all(np.asarray(transform['scale'])>0),'Invalid fit-only transform/coefficient')
                        require(m['response_coordinate'] is None and not m['fit_intercept'],'Residual/direct parameterization changed')
                        mean=np.asarray(transform['mean']);scale=np.asarray(transform['scale']);width=len(mean)
                        coefficient=np.asarray(m['coefficients']);slope=coefficient[:width]/scale
                        actual_slope=slope.copy()
                        if method=='residual':actual_slope[0]+=1.
                        eq(actual_slope,m['original_gain_unit_slopes'],'Raw gain-unit response slope differs from fitted coefficients')
                        eq(coefficient[width:]-float(slope@mean),m['original_gain_unit_arm_intercepts'],'Raw gain-unit arm intercept differs')
                        require(m['add_back_unstandardized_d']==(method=='residual'),'Residual prior is in standardized rather than raw d units')
                        require(m['arm_intercept_order']==[POOL[j] for j in range(5) if j!=d['reference_action']],'Arm intercept order changed')
                x=np.zeros(len(d['feature_names']));x[list(d['feature_names']).index('missing_fraction')]=.1
                require(p.choose(x,None)['action']==d['reference_action'],'No-evidence STOP changed own reference')
                x[list(d['feature_names']).index('missing_fraction')]=0
                require(p.choose(x,None)['action']==0,'Complete raw input is not KEEP')
                return digest
            digest=audit.check('terminal_policy',(family,method),policy_check)
            if digest is not None:signatures[family,method]=digest
    audit.details.update(terminal_freeze_sha256=sha(path),parent_counts={r:len(p) for r,p in parents.items()},
                         terminal_hashes={f:{m:h for (ff,m),h in signatures.items() if ff==f} for f in terminal})
    frozen_path=root/'models_frozen.json'
    if not frozen_path.exists():audit.pending.append('Acquisition model/value labels not frozen');return
    frozen=read(frozen_path)
    require(sha(root/'models.joblib')==frozen['sha256'] and sha(root/'value_labels.json')==frozen['value_labels_sha256'], 'Acquirer or value labels changed')
    require(sha(root/'terminal_manifest.json')==frozen['terminal_manifest_sha256'],'Acquirer uses another terminal manifest')
    require(sha(root/'proxy_target_pairs.json')==frozen['proxy_target_pairs_sha256']==manifest['proxy_target_pairs_sha256'],'Training proxy/current-task pairs changed')
    require(sha(root/'training_projection_costs.json')==manifest['training_projection_costs_sha256'],'Training evidence projection cost changed')
    proxy_pairs=read(root/'proxy_target_pairs.json');pair_keys=set();pair_counts=Counter()
    pair_weights={role:dict(zip(ids[role],weights(ids[role]))) for role in ('T_fit','T_gate','T_acq')}
    for r in proxy_pairs:
        def pair_check(r=r):
            key=r['family'],r['uid'],r['state'];require(key not in pair_keys,'Duplicated proxy/current-task pair');pair_keys.add(key)
            role=r['role'];require(role in ('T_fit','T_gate','T_acq') and r['uid'] in ids[role] and r['split']=='train','Proxy/current-task pair contains CHECK/DEV/heldout')
            require(r['parent']==partition[r['uid']]['parent_group'],'Proxy/current-task parent changed')
            L=np.asarray(r['current_five_losses']);reference=POOL.index(r['reference_arm'])
            require(L.shape==(5,) and np.isfinite(L).all() and r['scale']>0,'Invalid current-task TRAIN losses/scale')
            eq(L[reference]-L,r['current_actual_delta'],'TRAIN target uses another reference/current-task loss')
            close(r['source_parent_weight'],pair_weights[role][r['uid']],'Proxy pair parent/source weight changed')
            if r['status']=='completed':
                first='h32' if r['state']=='H32' else 'long'
                historical=r['raw_historical_mae'][first]
                require(historical is not None,'Completed TRAIN evidence lacks historical MAE')
                eq(np.array([(historical[r['reference_arm']]-historical[a])/r['scale'] for a in POOL]),r['d'],'TRAIN measured d is not actual raw MAE gain/current S')
            else:require(r['d'] is None and r['extra'] is None,'Unavailable TRAIN evidence filled with values')
            pair_counts[r['family']+':'+role]+=1
        audit.check('training_proxy_target_pair',(r['family'],r['uid'],r['state']),pair_check)
    projections=read(root/'training_projection_costs.json')
    require(len(projections)==len(proxy_pairs),'Projection invoice denominator differs from actual TRAIN states')
    projection_seconds=Counter()
    for r in projections:
        require((r['family'],r['uid'],r['state']) in pair_keys and r['role'] in ('T_fit','T_gate','T_acq'),'Projection cost has another data role')
        projection_seconds[r['family']]+=sum(invoice(r['invoice']).values())
    audit.details.update(training_proxy_target_pair_counts=dict(pair_counts),training_projection_seconds=dict(projection_seconds))
    for family,policies in terminal.items():
        fit_gate_pairs=[r for r in proxy_pairs if r['family']==family and r['role'] in ('T_fit','T_gate')]
        for method,p in policies.items():
            require(p.to_dict()['training_identity']['proxy_target_pair_fit_gate_hash']==jh(fit_gate_pairs),'Response policy not bound to original TRAIN proxy/task pairs')
    bundle=joblib.load(root/'models.joblib');labels=read(root/'value_labels.json');counts_by_family={}
    for family,rows in labels.items():
        aq=bundle['acquirers'][family];fm=manifest['families'][family];seen=set()
        require(aq.terminal_hash==fm['terminal_hash']==signatures[family,'residual'],'Acquirer uses stale terminal')
        require(all(p.frozen_hash==signatures[family,m] for m,p in bundle['policies'][family].items()),'Terminal changed during acquisition fit')
        rw=weights(ids['T_acq']);expected_weight=dict(zip(ids['T_acq'],rw))
        for row in rows:
            def label_check(row=row):
                key=row['uid'],row['tool'];require(key not in seen,'Duplicated uid/tool label');seen.add(key)
                require(row['uid'] in ids['T_acq'] and row['parent'] in parents['T_acq'] and row['role']=='T_acq','Label entered wrong role')
                require(row['terminal_hash']==aq.terminal_hash,'Value label terminal changed')
                require(row['tool'] in ('H32','H','control') and row['acquisition_steps']==1,'Unregistered active tool/multiple steps')
                close(row['weight'],expected_weight[row['uid']],'Acquisition source-parent weight changed')
                stop,acquire,tool=(invoice(row[k]) for k in ('stop_invoice','acquire_invoice','tool_invoice'))
                require(all(acquire.get(k)==v for k,v in tool.items()),'Tool missing from complete branch')
                require(all(acquire[k]==v for k,v in stop.items() if k in acquire),'Shared cost repriced')
                close(sum(stop.values()),row['stop_cost'],'STOP cost mismatch')
                close(sum(acquire.values()),row['acquire_cost'],'Acquisition cost mismatch')
                close(row['acquire_cost']-row['stop_cost'],row['delta_cost'],'Cost difference substituted for complete branch')
                close(row['task_gain']-row['lambda']*row['delta_cost'],row['value'],'Net-value formula wrong')
                require(row['lambda']==aq.lambda_value,'Value label uses another price')
            audit.check('acquisition_value',(family,row['uid'],row['tool']),label_check)
        report=aq.report;require(report['max_depth']==2 and report['min_leaf_independent_parents']>=16,'Acquirer complexity changed')
        price=.1*report['task_scale']/report['positive_tool_cost_scale'] if report['scale_status']=='valid' else 0.
        require(report['lambda_candidates']==([0.,price] if price>0 else [0.]),'Unregistered price search')
        best=max(report['cv_summary'],key=lambda r:(r['weighted_cv_utility'],-r['lambda']))
        require(best['lambda']==aq.lambda_value,'Price not selected in T_acq')
        for cv in report['cv_records']:
            require(cv['held_parent'] not in cv['train_parents'] and set(cv['train_parents'])<=parents['T_acq'],'Acquisition LOPO leaks parent')
        trees={}
        for tool,tree in aq.models.items():
            require(tree.max_depth<=2 and tree.min_parents>=16 and tree.max_cutpoints<=16,'Actual acquisition tree exceeds registered limits')
            leaves=[];split_count=0;stack=[tree.root_]
            while stack:
                node=stack.pop();require(node.depth<=2 and node.parent_count>=16,'Actual acquisition node has insufficient independent parents')
                if node.feature is None:
                    require(node.left is None and node.right is None,'Leaf retains hidden acquisition subtrees');leaves.append(node.parent_count)
                else:
                    require(node.left is not None and node.right is not None and node.parent_count>=32,'Acquisition split cannot support two independent leaves')
                    split_count+=1;stack.extend((node.left,node.right))
            trees[tool]={'split_count':split_count,'leaf_parent_counts':leaves,'constant_root':split_count==0,'root_value':tree.root_.value}
        counts_by_family[family]=dict(rows=len(rows),positive=sum(r['value']>0 for r in rows),zero=sum(r['value']==0 for r in rows),negative=sum(r['value']<0 for r in rows),actual_trees=trees)
    audit.details['acquisition_labels']=counts_by_family
    provenance_path=root/'label_provenance.json'
    if not provenance_path.exists():
        audit.pending.append('Acquisition value arithmetic checked; missing before/after label provenance');return
    require(sha(provenance_path)==frozen['label_provenance_sha256'],'Value provenance not bound to frozen model')
    provenance=read(provenance_path)
    from introact_ts.v431_r3.response import ResponseEvidence
    for family,records in provenance.items():
        policy=bundle['policies'][family]['residual'];indexed={(r['uid'],r['tool']):r for r in labels[family]}
        require(len(records)==len(indexed),'Value label provenance denominator differs')
        for r in records:
            def replay(r=r):
                label=indexed[r['uid'],r['tool']]
                require(r['role']=='T_acq' and r['parent'] in parents['T_acq'],'Provenance outside independent T_acq')
                require(r['terminal_freeze_sha256']==sha(path),'Label generated against another terminal freeze')
                require(r['before_terminal_hash']==r['after_terminal_hash']==policy.frozen_hash,'Different policies used for two value endpoints')
                x=np.array([np.nan if v is None else v for v in r['dirty_features']],float)
                require(ah(x)==r['dirty_features_hash'],'Dirty feature snapshot changed')
                L=np.asarray(r['five_losses'],float);require(L.shape==(5,) and np.isfinite(L).all(),'Malformed five-arm T_acq loss')
                state=ResponseEvidence(**r['after_state'])
                before=policy.choose(x,None,fully_observed=r['fully_observed'])
                after=policy.choose(x,state,fully_observed=r['fully_observed'])
                require(before['action']==r['stop_action'] and after['action']==r['acquire_action'],'Actual frozen policy does not choose labeled arms')
                close(L[before['action']],r['stop_loss'],'Stop loss does not match actual selected arm')
                close(L[after['action']],r['acquire_loss'],'Acquired loss does not match actual selected arm')
                close(r['stop_loss']-r['acquire_loss'],label['task_gain'],'Value uses oracle or historical gain instead of terminal decision')
                close(r['source_parent_weight'],label['weight'],'Provenance weight mismatch')
            audit.check('independent_value_policy_replay',(family,r['uid'],r['tool']),replay)


def audit_current(audit, root):
    """New check-only current forecasts and original target routing, no labels."""
    source=root/'probes/main';meta=read(source/'generalization_metadata.json')
    current=arrays(source/'generalization_contexts.npz')
    old=Path('results/v43/20260914T141030.324186Z-agent')
    oldmeta=read(old/'episode_manifest.json');oldcontext=arrays(old/'contexts.npz')
    partition=read('results/v431/20260914-sprint/partition.json')
    terminal=read(root/'terminal_manifest.json');routing=[]
    require(len(meta)==17 and len({m['parent_group'] for m in meta.values()})==17,'New combination independent parent count changed')
    for u,m in meta.items():
        def context_check(u=u,m=m):
            base=m['base_uid'];b=oldmeta[base]
            require(m['generalization_only'] and m['v431_role']=='T_check' and partition[base]['v431_role']=='T_check','New position entered wrong training/evaluation role')
            require(m['parent_group'] in terminal['check_parent_ids'] and b['condition']=='raw','New position not based on original CHECK raw input')
            for k in ('source','parent_group','split','raw_start','context_end','horizon'):
                require(m[k]==b[k],'New position changed original target routing '+k)
            require(m['gap']==[358,409] and m['horizon']==192,'New position/horizon changed registration')
            require(u==jh(dict(base_raw_uid=base,gap=[358,409],horizon=192,protocol='r3_check_only')),'New position UID changed')
            x=oldcontext[base+'_target'].copy();x[358:409]=np.nan
            eq(x,current[u+'_target'],'New input differs from exact controlled deletion')
            for k in ('covariates','timestamps','availability'):eq(current[u+'_'+k],oldcontext[base+'_'+k],'New position changed original '+k)
            routing.append(dict(uid=u,base_uid=base,source=m['source'],parent=m['parent_group'],target_array_key=base+'_values',scoring_mask_array_key=base+'_mask',target_raw_bounds=[m['context_end'],m['context_end']+192],target_archive=str(old/'targets.npz'),target_values_read=False))
        audit.check('new_position_and_target_routing',u,context_check)
    families={};governance=None
    for family in ('bolt','timesfm'):
        out=root/('generalization-current-'+family)
        if not (out/'status.json').exists() or read(out/'status.json')['status']!='completed':
            audit.pending.append('Missing complete new-position predictions '+str(out));continue
        manifest=read(out/'manifest.json');status=read(out/'status.json')
        require(status['episodes']==17 and status['future_labels_read']==status['heldout_labels_read']==manifest['future_labels_read']==0,'Current producer read future or changed denominator')
        require(manifest['input_sha256']==sha(source/'generalization_contexts.npz') and manifest['episode_manifest_sha256']==sha(source/'generalization_metadata.json'),'New current producer used another input')
        for f,h in manifest['files'].items():require(sha(out/f)==h,'Frozen new current output changed')
        raw=audit.check('current_raw_worker',family,lambda out=out,manifest=manifest:raw_session(out/'service',source_override=manifest['producer_sources']))
        if raw is None:continue
        require(manifest['model_identity']==jh(raw['model']['models'][family]),'Current model identity changed')
        candidates=arrays(out/'candidates.npz');predictions=arrays(out/'predictions.npz');costs=read(out/'forecast_costs.json')
        direct=read(out/'direct_candidate_costs.json')
        require(set(candidates)==set(predictions)==set(costs)=={u+'_'+a for u in meta for a in POOL},'New current five-arm denominator changed')
        if family=='bolt':governance=raw
        else:
            require(manifest['candidate_reuse']==str(root/'generalization-current-bolt'),'Second family changed shared governance')
            eq_candidates=families['bolt']['candidates']
            require(all(np.array_equal(candidates[k],eq_candidates[k],equal_nan=True) for k in candidates),'Families used different new-position candidates')
        for u,m in meta.items():
            fields={k:current[u+'_'+k] for k in FIELDS};observed=np.isfinite(fields['target'])
            for arm in POOL:
                def forecast_check(u=u,m=m,arm=arm,fields=fields,observed=observed):
                    c,p=candidates[u+'_'+arm],predictions[u+'_'+arm]
                    require(c.shape==(512,) and p.shape==(192,) and np.isfinite(p).all(),'Malformed new current output')
                    eq(c[observed],fields['target'][observed],'New current candidate changed observed input')
                    if arm=='A0_NATIVE':eq(c,fields['target'],'New KEEP is not original controlled input')
                    elif arm=='A4_RIDGE_CONTEXT' and not np.isfinite(c).all():
                        require(ridge_unavailable(fields) is not None,'Unexplained unsupported new ridge');eq(c,fields['target'],'Ridge fallback changed Native')
                    else:require(np.isfinite(c).all(),'New current imputation contains failed fill')
                    hashes=tuple(ah(fields[k]) for k in ('covariates','timestamps','availability'))
                    if arm in ('A2_SINGLE','A3_COV'):
                        g=governance['index'].get(('tsicl',192,ah(fields['target']),*hashes),[])
                        mode='none' if arm=='A2_SINGLE' else 'past_only'
                        require(any(v['mode']==mode and np.array_equal(v['point'],c) for v in g),'New candidate lacks actual TSICL provenance')
                    hits=raw['index'].get((family,192,ah(c),*hashes),[])
                    require(any(np.array_equal(v['point'],p) for v in hits),'New current forecast differs from native model point')
                    if family=='timesfm':
                        native={v['row']['raw_native_file'] for v in hits}
                        hits=[v for v in raw['rows'] if v['model_key']=='timesfm' and v['row']['raw_native_file'] in native and not v['row']['cache_hit']]
                    invoices=[i for v in hits for i in raw['invoices'] if i['episode_uid']==v['uid'] and i['arm']==v['arm'] and v['request'].endswith(i['shard']+'.request.json')]
                    require(any(np.isclose(i['charged_seconds'],costs[u+'_'+arm],rtol=1e-11,atol=1e-12) for i in invoices),'New current forecast cost differs from original actual invoice')
                    require(np.isfinite(direct[u][arm]) and direct[u][arm]>=0,'New current governance cost invalid')
                audit.check('new_current_forecast',(family,u,arm),forecast_check)
        families[family]=dict(candidates=candidates,predictions=predictions)
    decisions=root/'new_combination_decisions.json'
    if decisions.exists():
        for r in read(decisions):
            u,a,f=r['episode_uid'],r['arm'],r['family']
            def decision_check(r=r,u=u,a=a,f=f):
                require(u in meta and r['parent_group']==meta[u]['parent_group'],'Evaluated another CHECK target')
                require(r['candidate_hash']==ah(families[f]['candidates'][u+'_'+a]) and r['forecast_hash']==ah(families[f]['predictions'][u+'_'+a]),'CHECK decisions scored different cached predictions')
                require(r['terminal_hash']==terminal['families'][f]['terminal_hash'],'CHECK decision uses another frozen terminal')
                invoice(r['invoice'])
            audit.check('new_current_evaluation_binding',(f,u,r['policy']),decision_check)
    audit.details.update(original_target_routing=routing,scope='Actual current candidate/model/cost and original raw-target routing; evaluator loss values are not reopened or independently recomputed',target_future_values_read=False,heldout_labels_read=0)


def audit_online(audit, root, online_path):
    outputs=[online_path] if online_path else [root/'online-bolt',root/'online-timesfm']
    for out in outputs:
        if not (out/'status.json').exists():audit.pending.append('Missing completed online output '+str(out));continue
        status=read(out/'status.json')
        if status['status']!='completed':audit.pending.append('Online status '+str(out)+' '+status['status']);continue
        result=audit.check('online_suite',out,lambda out=out:verify_online_suite(root,out))
        if result is not None:audit.details[str(out)]=result


def verify_online_suite(root,out):
    import joblib
    from introact_ts.v431_r3.response import state_from_results
    protocol=read(out/'protocol.json');rows=read(out/'decisions.json');visibility=read(out/'visibility_barrier.json')
    status=read(out/'status.json');accounting=read(out/'process_accounting.json')
    frozen=read(root/'models_frozen.json');manifest=read(root/'terminal_manifest.json')
    require(sha(root/'models.joblib')==frozen['sha256']==protocol['model_sha256'],'Online uses another complete model')
    require(sha(root/'terminal_manifest.json')==frozen['terminal_manifest_sha256'],'Online terminal manifest changed')
    require(sha('scripts/v431_r3_online.py')==protocol['source_sha256'],'Online producer changed')
    require(visibility['status']=='passed' and visibility['before_evaluator_open'] and visibility['predictions_saved'],'Outputs not frozen before evaluation')
    require(visibility['unexpected']==0 and not visibility['open'] and visibility['denied_preflight']==len(protocol['hidden_archives']),'Hidden-evidence barrier failed')
    require(sha(out/'live_arrays.npz')==visibility['live_arrays_sha256'],'Live final arrays changed')
    require(status['heldout_labels_read']==protocol['heldout_labels_read']==0,'Online held-out read')
    require(accounting['status']=='completed' and accounting['exit_code']==0,'Online process incomplete')
    require(len(rows)==len(protocol['plan'])==status['cases']==11,'Online case denominator changed')
    family=protocol['family'];bundle=joblib.load(root/'models.joblib')
    policy=bundle['policies'][family]['residual'];acquirer=bundle['acquirers'][family]
    require(protocol['terminal_hash']==policy.frozen_hash==acquirer.terminal_hash,'Online/acquirer terminal mismatch')
    override={'scripts/v431_r3_online.py':protocol['source_sha256']}
    for r in rows:
        for p in r['actual_probes']:
            if p['status']=='completed':override['src/introact_ts/v431_r3/runtime.py']=p['live_runtime_source_sha256']
    service=raw_session(out/'service',source_override=override)
    old=Path('results/v43/20260914T141030.324186Z-agent')
    meta=read(old/'episode_manifest.json');current=arrays(old/'contexts.npz');scales=read(old/'mase_scales.json');live=arrays(out/'live_arrays.npz')
    natural=0;calls=0;pairs=[]
    plans={r['case_id']:r for r in protocol['plan']}
    for r in rows:
        case=r['case_id'];plan=plans[case];uid=r['episode_uid'];m=meta[uid]
        require(m['split']=='dev','Natural verification case outside existing DEV')
        fields={k:current[uid+'_'+k] for k in FIELDS};x=np.asarray(r['visible_features'],float)
        complete=bool(np.isfinite(fields['target']).all());require(complete==r['fully_observed'],'Raw/no-op condition fabricated')
        for k,v in plan.items():
            expected='stop' if k=='mode' and complete else v
            require(r[k]==expected,'Online case plan changed '+k)
        before=policy.choose(x,None,fully_observed=complete)
        require(before==r['before_decision'],'Online STOP baseline differs from frozen policy')
        fm=manifest['families'][family];eligible=[];values={};primitive_support={}
        original=np.c_[fields['target'],fields['covariates']]
        missing_rows=np.where(~np.isfinite(original))[0]
        for name in ('h32','long','short'):
            spec=expected_spec(m['horizon'],name);o=spec['origin'];h=spec['horizon']
            relocated=missing_rows+o-512
            mask=np.isfinite(fields['target'][o:o+h]) & (fields['availability'][o:o+h,0]<=fields['timestamps'][-1])
            primitive_support[name]=bool(np.all((relocated>=spec['start'])&(relocated<o)) and mask.sum()>=max(16,int(np.ceil(h/2))))
        required={'H32':('h32',),'H':('long',),'control':('long','short')}
        for tool in ('H32','H','control'):
            if tool not in r['estimated_branch_costs']:continue
            if plan['mode']=='fixed' and tool!=plan['branch']:continue
            require(r['estimated_branch_costs'][tool]==fm['branch_estimates'][tool],'Online changed frozen branch price')
            supported=not complete and all(primitive_support[p] for p in required[tool])
            if not supported:
                require(r['excluded'].get(tool)=='unsupported','Metadata-unsupported branch not excluded');continue
            if r['estimated_branch_costs'][tool]>r['budget']+1e-12:
                require(r['excluded'].get(tool)=='estimated_complete_branch_exceeds_budget','Budget admission used delta cost');continue
            if r['mode']=='stop':continue
            require(r['estimated_branch_costs'][tool]<=r['budget']+1e-12,'Over-budget branch admitted')
            eligible.append(tool)
            value=acquirer.predict(x,tool,policy.frozen_hash)
            if value is not None:
                values[tool]=value
                if plan['mode']=='learned':close(value,r['predicted_values'][tool],'Online acquisition score differs from actual model')
            elif plan['mode']=='learned':
                require(r['excluded'].get(tool)=='unsupported_train_parent_count','Unavailable acquirer treated as zero-valued model')
        if plan['mode']=='learned' and not complete:
            selected=max(values,key=values.get) if values and max(values.values())>0 else None
            require(r['branch']==selected,'Learned acquisition differs from positive feasible value')
        if complete:require(r['arm']=='A0_NATIVE' and r['branch'] is None,'Raw input changed or acquired evidence')
        if r['branch'] is None:
            require(not r['actual_probes'] and r['arm']==before['arm'],'STOP performed hidden tool or changed own base action')
        atoms={};derived={}
        for atom in r['actual_probes']:
            require(atom['status']=='completed','Unexpected real tool failure in finished verification case')
            name=atom['probe'];p=reconstruct(fields,m,atom['prepared'],scales[m['source']],saved_view=False)
            require(atom['model_identity_hash']==atom['checkpoint_record_hash']==jh(service['model']['models'][family]),'Online actual model record mismatch')
            require(set(atom['raw_predictions'])==set(POOL),'Online primitive five-arm denominator')
            for arm in POOL:
                pred=np.asarray(atom['raw_predictions'][arm]);require(ah(pred)==atom['prediction_hashes'][arm],'Online primitive prediction hash')
                mse=float(np.abs(pred[p['mask']]-p['target'][p['mask']]).mean())
                close(mse,atom['mae'][arm],'Online historical raw MAE/mask mismatch')
                close((atom['mae'][atom['reference_arm']]-mse)/scales[m['source']],atom['gain'][arm],'Online historical MASE gain mismatch')
                hits=service['index'].get((family,p['spec']['horizon'],atom['candidate_hashes'][arm],
                    *(ah(p['values'][k]) for k in ('covariates','timestamps','availability'))),[])
                require(any(np.array_equal(h['point'],pred) for h in hits),'Online primitive lacks actual worker output')
                for hit in hits:
                    eq(hit['input']['target'][p['values']['raw_mask']],p['values']['target'][p['values']['raw_mask']],'Online probe overwrote observed input')
            invoice(atom['invoice']);atoms[name]=atom;derived[name]=p
        if r['failure']:
            require(case=='failed-after-real-long' and r['branch']=='H' and len(atoms)==1 and 'long' in atoms,'Failure not after recorded real probe')
            require(r['failure']['failed_values_filled'] is False and r['arm']==before['arm'],'Failure substituted fake evidence or changed fallback')
            require(r['status']=='failed_fallback' and r['evidence_hash'] is None,'Failure consumed evidence')
        elif r['branch'] is not None:
            state=state_from_results(r['branch'],atoms,reference_arm=POOL[policy.reference_action])
            require(state.evidence_hash==r['evidence_hash'],'Online evidence lineage changed')
            after=policy.choose(x,state,fully_observed=complete)
            require(after==r['after_decision'] and after['arm']==r['arm'],'Online final differs from actual acquired state')
        if 'long' in atoms and 'short' in atoms:
            require(atoms['long']['scoring_mask_hash']==atoms['short']['scoring_mask_hash'],'Online pair uses different targets')
            pairs.append(dict(case_id=case,kappa={a:atoms['long']['gain'][a]-atoms['short']['gain'][a] for a in POOL}))
        candidate,prediction=live[case+'_candidate'],live[case+'_prediction'];final=r['final']
        require(final['candidate_hash']==ah(candidate) and final['prediction_hash']==ah(prediction),'Final live array identity changed')
        eq(candidate[np.isfinite(fields['target'])],fields['target'][np.isfinite(fields['target'])],'Final rewrote complete observations')
        hits=service['index'].get((family,m['horizon'],ah(candidate),*(ah(fields[k]) for k in ('covariates','timestamps','availability'))),[])
        require(any(np.array_equal(h['point'],prediction) for h in hits),'Final not an actual model prediction')
        require(final['arm']==r['arm'],'Forecasted another governance action')
        hot=invoice(r['invoice']);close(sum(hot.values()),r['hot_request_seconds'],'Hot request cost double counted')
        close(r['hot_request_seconds']+r['allocated_startup_seconds']+r['allocated_other_process_seconds'],r['total_seconds'],'Complete process allocation wrong')
        require(r['budget_overrun']==(r['hot_request_seconds']>r['budget']+1e-12),'Hot budget flag wrong')
        require(r['complete_process_budget_overrun']==(r['total_seconds']>r['budget']+1e-12),'Cold/process budget flag wrong')
        if not r['controlled']:
            natural+=1;calls+=r['actual_tool_calls'];require(r['mode']=='learned' and r['budget']==manifest['budgets']['high'],'Natural case changed budget or forced tool')
    require(natural==7 and calls==accounting['natural_actual_tool_calls'],'Controlled cases counted as method acquisition')
    close(sum(r['total_seconds'] for r in rows),accounting['process_wall_seconds'],'Process costs not fully allocated')
    return dict(status='passed',family=family,cases=len(rows),natural_requests=natural,natural_actual_tool_calls=calls,
                controlled_cases=4,independent_live_pairs=pairs,process_wall_seconds=accounting['process_wall_seconds'],
                natural_complete_budget_overruns=sum(r['complete_process_budget_overrun'] for r in rows if not r['controlled']),
                no_new_target_read=True,scope='actual outputs/state/cost audit; no accuracy significance claim')


def self_test():
    # Poisoned numeric output cannot be accepted, and duplicate cost keys fail.
    for inv in [dict(charges=[dict(key='x',seconds=1),dict(key='x',seconds=1)],total_seconds=2),
                dict(charges=[dict(key='x',seconds=-1)],total_seconds=-1)]:
        try:invoice(inv)
        except AssertionError:pass
        else:raise AssertionError('Invalid invoice accepted')
    require(expected_spec(192,'short')==dict(name='short',start=64,origin=320,horizon=192,current_origin=512),'Registered geometry')
    require(ah(np.array([np.nan]))==ah(np.array([np.nan])),'NaN identity')
    return dict(status='passed',scope='verifier fail-closed smoke checks, no model validation')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=('probes','models','current','online'))
    parser.add_argument('--root',type=Path,default=Path('results/v431-r3'))
    parser.add_argument('--suite',choices=('main','financial'),default='main')
    parser.add_argument('--backend-inputs',action='store_true')
    parser.add_argument('--online-path',type=Path)
    parser.add_argument('--session',type=Path,action='append',default=[],
                        help='Audit this production session only; may repeat; report remains explicitly scoped')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args();sys.addaudithook(barrier)
    if args.self_test:print(json.dumps(self_test()));return 0
    parser.error('--phase is required') if not args.phase else None
    audit=Audit(args.phase);begun=datetime.now(timezone.utc);verifier_start_sha=sha(__file__)
    try:
        if args.phase=='probes':audit_probes(audit,args.root,args.suite,args.backend_inputs,args.session)
        elif args.phase=='models':audit_models(audit,args.root)
        elif args.phase=='current':audit_current(audit,args.root)
        else:audit_online(audit,args.root,args.online_path)
    except Exception as exc:
        audit.failures.append(dict(category='audit_runtime',error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc()))
    output=args.root/'verification'/(begun.strftime('%Y%m%dT%H%M%S.%fZ')+'-'+args.phase+'-'+args.suite)
    output.mkdir(parents=True,exist_ok=False)
    report=dict(status=audit.status,phase=args.phase,created_utc=begun.isoformat(),
                verifier_sha256=verifier_start_sha,verifier_end_sha256=sha(__file__),python=sys.executable,checks=dict(audit.checks),
                failures=audit.failures,pending=audit.pending,details=audit.details,
                no_deployment_target_read=True,no_gpu_model_loaded=True,
                actual_model_files_verified=len(VERIFIED_MODEL_FILES))
    (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(output),status=audit.status,checks=dict(audit.checks),
                         failures=len(audit.failures),pending=audit.pending),ensure_ascii=False))
    return {'passed':0,'failed':1,'pending':2}[audit.status]


if __name__=='__main__':
    raise SystemExit(main())
