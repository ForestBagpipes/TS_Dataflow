#!/usr/bin/env python3
"""Main-matrix metadata, legacy interval overlap, and context-only mask audit.

No current forecast targets, calibration/test numerical cells, or models read.
"""
import argparse,copy,csv,gzip,hashlib,io,json,time
from datetime import datetime
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from introact_ts.v43.schemas import array_hash,json_hash
from v431_r5_prepare_main import metadata,sha

ROOT=Path('results/v431-r5/main-preparation');OUT=ROOT/'audit-v2'
SOURCE_NAMES=('ETTh1','ETTh2','ETTm1','ETTm2','Electricity','Exchange','Traffic','Weather')


def write(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def axis(source,start,end):
    if source.startswith('ETT'):
        scale=4 if source.startswith('ETTh') else 1
        return 'ETT_station_'+source[-1],start*scale,end*scale
    return source,start,end


def old_intervals():
    intervals=[];files={};unknown=Counter()
    for path in [Path('results/v40_bank_parents.jsonl'),Path('results/v40_rescue_bank_parents.jsonl')]:
        files[str(path)]=sha(path)
        for line in path.open():
            r=json.loads(line)
            if r['source'] in SOURCE_NAMES:
                intervals.append(dict(source=r['source'],start=int(r['start']),end=int(r['start'])+512,
                    parent=r['clean_parent_uid'],scope='old_seen_reconstruction_input',file=str(path)))
    for path in [Path('results/v43/20260914T131623.999847Z-p2/episode_manifest.json'),
                 Path('results/v43/20260914T141030.324186Z-agent/episode_manifest.json')]:
        files[str(path)]=sha(path)
        obj=json.loads(path.read_text());rows=obj.values() if isinstance(obj,dict) else obj
        for r in rows:
            if r['source'] in SOURCE_NAMES:
                intervals.append(dict(source=r['source'],start=int(r['raw_start']),end=int(r['context_end'])+int(r['horizon']),
                    parent=r.get('parent_group'),scope='old_current_input_and_target_interval',file=str(path)))
    path=Path('results/p0_corpus_manifest_a.json');files[str(path)]=sha(path)
    for r in json.loads(path.read_text())['records']:
        if r['dataset'] in SOURCE_NAMES:unknown[r['dataset']]+=1
    unique={json_hash(x):x for x in intervals}
    return list(unique.values()),files,dict(unknown)


def source_rows(path):
    """Container rows returned as strings; caller converts only allowed contexts."""
    p=Path(path);opener=gzip.open if p.suffix=='.gz' else open
    with opener(p,'rt',encoding='utf-8',newline='') as f:
        rows=csv.reader(f)
        if p.suffix!='.gz':next(rows)
        for idx,row in enumerate(rows):
            yield idx,(row if p.suffix=='.gz' else row[1:])


def masks_for_source(info,windows):
    windows=sorted(windows,key=lambda x:x['read_start']);iterator=iter(source_rows(info['path']));cursor=-1;current=None
    rows=[];parsed=0;samples={};conditions=('raw','target_block_10','shared_block_10')
    for w in windows:
        a,b=w['read_start'],w['origin'];role=w['role'];lo,hi=info['split_bounds'][role]
        assert role in ('train','dev') and lo<=a<b and w['max_target_end']<=hi
        block=[]
        while cursor < b-1:
            cursor,current=next(iterator)
            if cursor>=a:
                block.append([float(x) if x.strip() else np.nan for x in current]);parsed+=1
        values=np.asarray(block,float);assert values.shape==(512,info['columns']) and not np.isinf(values).any()
        for cond in conditions:
            modified=values.copy()
            if cond!='raw':modified[230:281,0]=np.nan
            if cond=='shared_block_10':modified[230:281,1:]=np.nan
            mask=np.isfinite(modified)
            valid=np.isfinite(values)&mask
            assert np.array_equal(values[valid],modified[valid])
            for H in (96,192):
                record=dict(source=info['source'],parent=w['parent'],role=role,read_start=a,origin=b,
                    L=512,H=H,condition=cond,target_channel=0,data_sha256=info['file_sha256'],
                    target_hash=array_hash(modified[:,0]),auxiliary_hash=array_hash(modified[:,1:]),
                    target_mask_hash=array_hash(mask[:,0]),auxiliary_mask_hash=array_hash(mask[:,1:]),
                    natural_context_nonfinite_count=int((~np.isfinite(values)).sum()),
                    natural_target_nonfinite_count=int((~np.isfinite(values[:,0])).sum()),
                    numerical_rows_read=[a,b],forecast_target_numerical_rows_read=0,
                    availability_protocol='original row interval end; exact release delay/vintage unknown',
                    mask_recipe='v43 seed101 fixed [230,281), preserve observed values',
                    legacy_exposure=w['legacy_exposure'],independent_confirmation=False)
                record['uid']=json_hash(record);rows.append(record)
            if role not in samples:samples[role]={}
            if not samples[role] or samples[role].get('_parent')==w['parent']:
                samples[role].update(_parent=w['parent']);samples[role][cond]=mask
    for role,v in samples.items():
        parent=v.pop('_parent');target=OUT/'mask-samples'/(info['source']+'-'+role+'.npz');target.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(target,**v)
        write(target.with_suffix('.json'),dict(parent=parent,source=info['source'],role=role,arrays='observation masks only; no data/targets',sha256=sha(target)))
    return rows,parsed


def audit():
    if (OUT/'status.json').exists():raise RuntimeError('Preserve first completed v2 audit')
    started=time.perf_counter();path=Path('configs/v431-r5/main_protocol.json');v1=json.loads(path.read_text());v1sha=sha(path)
    v2=copy.deepcopy(v1);v2.update(version='v431-r5-main-preparation-v2',parent_protocol_sha256=v1sha,
        status='metadata_masks_ready_method_gate_failed_not_released',update_basis='metadata and prior-exposure only; no outcome selection')
    weather=next(s for s in v2['sources'] if s['source']=='Weather')
    if Path(weather['path']).exists():
        weather.update(metadata(weather['path']));n=weather['rows'];bounds=dict(train=[0,int(.6*n)],dev=[int(.6*n),int(.75*n)],calibration=[int(.75*n),int(.85*n)],test=[int(.85*n),n])
        weather.update(status='metadata_prepared_not_model_ready',license='CC BY 4.0 official TS-Library dataset card and MPI-Jena provider',
            provider='https://huggingface.co/datasets/thuml/Time-Series-Library',
            provider_revision='2b66e59ee19dac8f6f19fb5d4997f289fdfea357',target='p (mbar), atmospheric pressure; channel 0 inherited rule',
            split_bounds=bounds,split_provenance='same preregistered 60_15_10_15 rule; file newly available',
            timezone='not_declared_in_benchmark_file',historical_vintage='unknown',prediction_labels_read=0,
            capacity={role:(hi-lo)//704 for role,(lo,hi) in bounds.items()})
        for role in ('train','dev'):
            lo,hi=bounds[role]
            for begin in range(lo,hi-704+1,704):
                v2['windows_metadata'].append(dict(source='Weather',role=role,parent=f'Weather:{begin}:{begin+704}',
                    read_start=begin,origin=begin+512,max_target_end=begin+704,horizons=[96,192]))
    old,oldfiles,unknown=old_intervals();aligned=[]
    for r in old:
        group,a,b=axis(r['source'],r['start'],r['end']);aligned.append((group,a,b,r))
    overlap=[];counts=defaultdict(Counter)
    for w in v2['windows_metadata']:
        group,a,b=axis(w['source'],w['read_start'],w['max_target_end'])
        hits=[r for g,c,d,r in aligned if g==group and max(a,c)<min(b,d)]
        same=[r for r in hits if r['source']==w['source']];cross=[r for r in hits if r['source']!=w['source']]
        source_unknown=sum(n for s,n in unknown.items() if axis(s,0,1)[0]==group)
        state='known_prior_interval_overlap' if hits else 'legacy_source_exposure_positions_unresolved' if source_unknown else 'no_known_overlap_in_audited_manifests'
        w['legacy_exposure']=state;w['synchronous_group']=group;w['independent_confirmation']=False
        key=(w['source'],w['role']);counts[key]['parents']+=1;counts[key][state]+=1
        counts[key]['same_source_overlap']+=bool(same);counts[key]['cross_frequency_overlap']+=bool(cross)
        overlap.append(dict(parent=w['parent'],source=w['source'],role=w['role'],complete_read_interval=[w['read_start'],w['max_target_end']],
            synchronous_group=group,canonical_interval=[a,b],state=state,same_source_hits=len(same),cross_frequency_hits=len(cross),
            old_overlap_examples=hits[:5],unlocalized_legacy_source_records=source_unknown))
    contract=[];numeric_counts={}
    for source in v2['sources']:
        if not Path(source['path']).exists():continue
        ww=[w for w in v2['windows_metadata'] if w['source']==source['source']]
        rows,parsed=masks_for_source(source,ww);contract.extend(rows);numeric_counts[source['source']]=parsed
    summary=[dict(source=s,role=r,**dict(c)) for (s,r),c in sorted(counts.items())]
    v2.update(previous_seen_metadata_hashes=oldfiles,exposure_policy='full interval intersection incl same-station ETT hourly/quarter-hour variants',
        heldout_labels_read=0,forecast_target_labels_read=0,method_admission='failed r5; no independent confirmation release',
        mask_contract_path=str(OUT/'mask_contract.json'),mask_contract_sha256=None)
    write(OUT/'mask_contract.json',contract);v2['mask_contract_sha256']=sha(OUT/'mask_contract.json')
    write(OUT/'overlap.json',overlap);write(OUT/'support.json',summary);write(OUT/'legacy_inventory.json',dict(files=oldfiles,unlocalized_corpus_records=unknown,interval_count=len(old)))
    write(OUT/'manifest_v2.json',v2);write('configs/v431-r5/main_protocol_v2.json',v2)
    weatherlog=Path('/tmp/v431-r5-weather-download.json')
    if weatherlog.exists():write(OUT/'weather_download.json',json.loads(weatherlog.read_text()))
    assert sha(path)==v1sha,'Original v1 modified'
    write(OUT/'status.json',dict(status='completed_metadata_and_masks_no_models',elapsed_seconds=time.perf_counter()-started,
        sources=len(v2['sources']),parent_windows=len(v2['windows_metadata']),mask_contract_rows=len(contract),
        numeric_context_rows_by_source=numeric_counts,forecast_target_rows_parsed=0,calibration_test_rows_parsed=0,
        previous_protocol_sha256=v1sha,v2_sha256=sha(OUT/'manifest_v2.json'),script_sha256=sha(__file__),
        independent_confirmation_claim=False,method_gate_released=False))
    print(json.dumps(dict(support=summary,mask_rows=len(contract),seconds=time.perf_counter()-started),ensure_ascii=False))


def temporal_audit():
    target=OUT/'timestamp_audit.json'
    if target.exists():raise RuntimeError('Preserve first timestamp audit')
    protocol=json.loads((OUT/'manifest_v2.json').read_text());reports=[];flags=[]
    for info in protocol['sources']:
        if Path(info['path']).suffix!='.csv':
            reports.append(dict(source=info['source'],status='ordinal_only_original_clock_unavailable'));continue
        expected=3600 if info['source'].startswith('ETTh') else 900 if info['source'].startswith('ETTm') else 600
        previous=None;counts=Counter();events=[]
        with open(info['path']) as f:
            next(f)
            for index,line in enumerate(f):
                stamp=datetime.fromisoformat(line.split(',',1)[0])
                if previous is not None:
                    delta=int((stamp-previous).total_seconds());counts[delta]+=1
                    if delta!=expected:events.append(dict(row=index,previous=str(previous),current=str(stamp),delta_seconds=delta))
                previous=stamp
        reports.append(dict(source=info['source'],status='timestamp_only_audited',expected_delta_seconds=expected,
             differences=dict(counts),events=events,timezone='not declared; not inferred from server'))
        for w in protocol['windows_metadata']:
            if w['source']!=info['source']:continue
            crossed=[e for e in events if w['read_start']<=e['row']<w['max_target_end']]
            if crossed:flags.append(dict(parent=w['parent'],source=w['source'],role=w['role'],events=crossed,
                status='unsupported_pending_explicit_time_contract',rule='retain row; no dedup, shift, calendar fill or silent drop'))
    write(target,dict(status='completed_metadata_only',sources=reports,affected_parent_windows=flags,
         numerical_observations_read=0,labels_read=0,v2_sha256=sha(OUT/'manifest_v2.json'),
         inherited_code_sha256_note='v2.code_sha256 inherited from v1; actual v2 producer digest is audit-v2/status.json.script_sha256',
         no_confirmation_release=True))
    print(json.dumps(dict(events=[(r['source'],len(r.get('events',[]))) for r in reports],affected=flags),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--temporal',action='store_true');args=p.parse_args()
    if args.temporal:temporal_audit()
    else:audit()
