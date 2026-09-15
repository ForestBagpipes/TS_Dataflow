#!/usr/bin/env python3
"""Separate explicitly measured model load from immutable r2/r3 invoices.

Only measured load is removed. IPC, input preparation, imports not timed as
model load, warmup and all other overhead stay charged. Counterfactual aliases
copy a price, so summed deployment deductions are not physical startup time.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from introact_ts.v43.schemas import array_hash

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT/'results/v43/20260914T141030.324186Z-agent'
R3 = ROOT/'results/v431-r3'
FIN = ROOT/'results/v431-r2/financial-observation-index-r1'
POOL = ('A0_NATIVE', 'A0_FFILL', 'A2_SINGLE', 'A3_COV', 'A4_RIDGE_CONTEXT')


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rel(p):
    return str(Path(p).resolve().relative_to(ROOT))


class Audit:
    def __init__(self):
        self.sessions = {}
        self.charges = {}
        self.sources = {}
        self.physical_loads = {}

    def load(self, p):
        p = Path(p)
        self.sources[rel(p)] = sha(p)
        return read(p)

    def add(self, key, original, donors, scope):
        cold = sum(d['deducted_seconds'] for d in donors)
        if not 0 <= cold <= original+1e-10:
            raise AssertionError((key, cold, original))
        hot = original-cold
        assert abs(hot+cold-original) < 1e-9
        row = dict(original_seconds=original, explicit_load_seconds=cold,
                   retained_hot_seconds=hot, provenance=donors, scope=scope)
        if key in self.charges:
            old = self.charges[key]
            assert abs(old['original_seconds']-original) < 1e-8, key
            assert abs(old['explicit_load_seconds']-cold) < 1e-8, key
        else:
            self.charges[key] = row

    def session(self, p):
        p = Path(p)
        if p in self.sessions:
            return self.sessions[p]
        invoices = self.load(p/'model_invoices.json')
        byshard = defaultdict(list)
        for r in invoices:
            byshard[r['shard']].append(r)
        indexed = {}
        raw_original = {}
        for shard, items in byshard.items():
            path = p/(shard+'.response.json')
            response = self.load(path)
            assert len(items) == len(response['rows'])
            n = len(items)
            assert 'service_initial_load_seconds' in response or 'load_seconds' in response, path
            load = float(response.get('service_initial_load_seconds', response.get('load_seconds')))
            self.physical_loads[rel(path)] = dict(model=response['model_key'], seconds=load,
                included_in_call=True, requests=n, allocation='load/request_count')
            for inv, raw in zip(items, response['rows']):
                assert (inv['episode_uid'], inv['arm']) == (raw['episode_uid'], raw['candidate_id'])
                delta = load/n
                assert 0 <= delta <= inv['allocated_shard_overhead_seconds']+1e-8
                donor = dict(response_file=rel(path), episode_uid=inv['episode_uid'], arm=inv['arm'],
                    response_load_seconds=load, allocation_count=n, deducted_seconds=delta,
                    original_row_seconds=inv['charged_seconds'], input_hash=raw['input_hash'])
                v = dict(invoice=inv, raw=raw, donor=donor)
                indexed[(inv['episode_uid'], inv['arm'])] = v
                if 'raw_native_file' in raw and not raw.get('cache_hit', False):
                    raw_original[raw['raw_native_file']] = v
        # load-only calls precede current/generalization, already separately billed.
        for path in p.glob('load-*.response.json'):
            r = self.load(path)
            self.physical_loads[rel(path)] = dict(model=r['model_key'],
                seconds=float(r.get('service_initial_load_seconds', r.get('load_seconds', 0))),
                included_in_call=False, requests=0, allocation='separate startup; no deployment deduction')
        out = dict(indexed=indexed, raw_original=raw_original, invoices=invoices)
        if (p/'records.json').exists():
            records = self.load(p/'records.json')
            out['canonical_views'] = {r['cache_input_hash']: r['alias_view_uid'] for r in records
                if r.get('status') == 'completed' and 'cache_input_hash' in r}
        self.sessions[p] = out
        return out

    def current_collector(self, directory, session, *, family, prefix, candidates=None):
        """Reconstruct aliases through actual candidate input hashes, not fees."""
        direct = self.load(directory/'direct_candidate_costs.json')
        forecast = self.load(directory/'forecast_costs.json')
        s = self.session(session)
        with np.load(candidates or directory/'candidates.npz', allow_pickle=False) as arrays:
            for uid, prices in direct.items():
                for arm in POOL:
                    donors = []
                    item = s['indexed'].get((uid, arm))
                    # An index also contains forecasts; select exact impute shard.
                    for r in s['invoices']:
                        if r['episode_uid'] == uid and r['arm'] == arm and r['shard'].startswith(prefix) and not r['shard'].endswith('bolt'):
                            path = session/(r['shard']+'.response.json')
                            q = read(path);n=len(q['rows']);load=float(q.get('service_initial_load_seconds',q['load_seconds']))
                            donors.append(dict(response_file=rel(path),episode_uid=uid,arm=arm,
                                response_load_seconds=load,allocation_count=n,deducted_seconds=load/n,
                                original_row_seconds=r['charged_seconds']))
                    self.add('candidate:'+uid+':'+arm, prices[arm], donors, 'current governance '+rel(directory))
                # Find final model rows with matching immutable target input.
                matching = []
                for (u,a), v in s['indexed'].items():
                    if u == uid and v['invoice']['shard'].endswith('bolt') and (v['invoice']['shard'].startswith('final-') or v['invoice']['shard'].startswith('check-current-')):
                        matching.append(v)
                for arm in POOL:
                    digest = array_hash(arrays[uid+'_'+arm])
                    v = next(v for v in matching if v['raw']['input_hash'] == digest)
                    expected = forecast[uid+'_'+arm]
                    assert abs(v['invoice']['charged_seconds']-expected) < 1e-8
                    self.add('forecast:'+family+':'+uid+':'+arm, expected, [v['donor']], 'current forecast '+rel(directory))

    def baseline_forecasts(self, directory, direct):
        status = self.load(directory/'status.json')
        scored = self.load(directory/'scored_rows.json')
        load = status['model_load_seconds'];n=len(scored)
        assert load <= status['process_overhead_seconds']+1e-8
        self.physical_loads[rel(directory/'status.json')] = dict(model='timesfm',seconds=load,
            included_in_call=True,requests=n,allocation='model load/scored record count, exactly as process overhead')
        for r in scored:
            uid,arm=r['episode_uid'],r['arm'];original=r['total_seconds']-direct[uid][arm]
            self.add('forecast:timesfm:'+uid+':'+arm, original,
                [dict(response_file=rel(directory/'status.json'),response_load_seconds=load,
                      allocation_count=n,deducted_seconds=load/n,episode_uid=uid,arm=arm)], 'baseline current')

    def timesfm_train(self):
        directory=ROOT/'results/v431-r2/timesfm-cache'
        status=self.load(directory/'status.json');rows=self.load(directory/'records.json')
        scope=self.load(directory/'cost_scope.json');n=status['actual_model_calls'];load=status['model_load_seconds']
        assert load/n <= scope['allocated_overhead_per_unique_call']+1e-10
        self.physical_loads[rel(directory/'status.json')]=dict(model='timesfm',seconds=load,
            included_in_call=True,requests=n,allocation='model load/unique physical model calls, same as original repricing')
        meta=self.load(OLD/'episode_manifest.json')
        current={(r['base_uid'],r['input_hash']):r for r in rows if r['phase']=='current'}
        with np.load(OLD/'candidates.npz',allow_pickle=False) as p:
            for uid,m in meta.items():
                if m['split']!='train':continue
                for arm in POOL:
                    r=current[uid,array_hash(p[uid+'_'+arm])]
                    self.add('forecast:timesfm:'+uid+':'+arm,r['charged_seconds'],[
                        dict(response_file=rel(directory/'status.json'),record_key=r['key'],response_load_seconds=load,
                            allocation_count=n,deducted_seconds=load/n,episode_uid=uid,arm=arm)],'train TimesFM repriced current')

    def probes(self, suite):
        p=R3/'probes'/suite
        for path in sorted((p/'candidate_cache').glob('*/*.json')):
            c=self.load(path);session=ROOT/c['producer_session'];s=self.session(session)
            canonical=c['identity']['input_hash'];uid=s['canonical_views'][canonical]
            donors=[]
            # Candidate invoices are not indexed by only uid/arm: the same uid
            # later has forecast invoices. Match all imputation response shards.
            for inv in s['invoices']:
                if inv['episode_uid']==uid and '-pool-' in inv['shard']:
                    response_path=session/(inv['shard']+'.response.json');q=read(response_path)
                    load=float(q.get('service_initial_load_seconds',q['load_seconds']));n=len(q['rows'])
                    donors.append(dict(response_file=rel(response_path),episode_uid=uid,arm=inv['arm'],
                        response_load_seconds=load,allocation_count=n,deducted_seconds=load/n,
                        original_row_seconds=inv['charged_seconds']))
            self.add('probe-candidates:'+canonical,c['generation_seconds'],donors,'probe governance '+suite)
        for path in sorted((p/'forecast_cache').glob('*/*.json')):
            c=self.load(path);s=self.session(ROOT/c['producer_session'])
            canonical=c['identity']['input_hash'];uid=s['canonical_views'][canonical];donors=[]
            for arm in sorted(set(c['aliases'].values())):
                v=s['indexed'][uid,arm]
                # Exact original price donor for cross-request cached prediction.
                if 'raw_native_file' in v['raw']:
                    v=s['raw_original'][v['raw']['raw_native_file']]
                assert abs(v['invoice']['charged_seconds']-c['arm_seconds'][arm]) < 1e-8, (path,arm)
                donors.append(v['donor'])
            self.add('probe-forecast:'+c['identity']['family_hash']+':'+canonical,
                     c['actual_forecast_seconds'],donors,'probe forecast '+suite)

    def run(self):
        self.current_collector(OLD,OLD,family='bolt',prefix='base-')
        self.timesfm_train()
        self.baseline_forecasts(ROOT/'results/v431/20260914-sprint/timesfm',self.load(OLD/'direct_candidate_costs.json'))
        self.current_collector(FIN,FIN,family='bolt',prefix='base-')
        self.baseline_forecasts(FIN/'timesfm',self.load(FIN/'direct_candidate_costs.json'))
        for family in ('bolt','timesfm'):
            p=R3/('generalization-current-'+family)
            self.current_collector(p,p/'service',family=family,prefix='check-current-')
        for suite in ('main','financial'):
            self.probes(suite)
        return dict(schema='r4-explicit-model-load-separation-v1',status='completed',charges=self.charges,
            physical_loads=self.physical_loads,sources=self.sources,script_sha256=sha(__file__),
            charge_count=len(self.charges),nonzero_deductions=sum(r['explicit_load_seconds']>0 for r in self.charges.values()),
            physical_explicit_load_seconds=sum(r['seconds'] for r in self.physical_loads.values()),
            remaining_overhead='All other overhead retained; not a guaranteed isolated hot-kernel measurement',
            aliases='Each alternative copies its actual price and measured load allocation; do not sum counterfactual deductions as physical load',
            preservation='No r2/r3 files changed, model input and prediction cache unchanged')


def reprice_invoice(invoice, sidecar):
    """Explicitly mapped charges are corrected; non-model costs stay unchanged."""
    rows=[];removed=0.
    for c in invoice['charges']:
        r=sidecar['charges'].get(c['key'])
        if r is None:
            assert not c['key'].startswith(('candidate:','forecast:','probe-candidates:','probe-forecast:')), 'Missing model cost mapping: '+c['key']
            rows.append(dict(c));continue
        assert abs(r['original_seconds']-c['seconds'])<1e-8, ('Stale cost',c['key'])
        rows.append(dict(key=c['key'],seconds=r['retained_hot_seconds']));removed+=r['explicit_load_seconds']
    total=sum(c['seconds'] for c in rows)
    assert abs(total+removed-invoice['total_seconds'])<1e-8
    return dict(charges=rows,total_seconds=total),removed


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='results/v431-r4/baseline_audit/hot_costs.json');a=p.parse_args()
    out=ROOT/a.output
    if out.exists():raise RuntimeError('Refuse to overwrite immutable cost sidecar')
    result=Audit().run();out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','charge_count','nonzero_deductions','physical_explicit_load_seconds')}))
