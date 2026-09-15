#!/usr/bin/env python3
"""只读 r2/r3 已查看的金融账本，拆分费用；不加载模型或原始标签。"""
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/v431-r4/baseline_audit'


def read(path):
    return json.loads(path.read_text())


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    path = ROOT / 'results/v431-r3/financial_decisions.json'
    rows = read(path)
    selected = {p: {r['episode_uid']: r for r in rows
                   if r['family'] == 'timesfm' and r['policy'] == p}
                for p in ('CART_H32_high', 'CART_H_high')}
    assert set(selected['CART_H32_high']) == set(selected['CART_H_high'])
    pairs = []
    for uid, a in selected['CART_H32_high'].items():
        b = selected['CART_H_high'][uid]
        item = {k: a[k] for k in ('episode_uid', 'source', 'parent_group', 'horizon', 'condition')}
        item.update(action_equal=a['arm'] == b['arm'], prediction_hash_equal=a['forecast_hash'] == b['forecast_hash'],
                    candidate_hash_equal=a['candidate_hash'] == b['candidate_hash'], loss_equal=a['mase'] == b['mase'])
        for label, r in (('H32', a), ('H', b)):
            groups = collections.defaultdict(float)
            charges = r['invoice']['charges']
            assert len({c['key'] for c in charges}) == len(charges)
            for c in charges:
                groups[c['key'].split(':')[0]] += c['seconds']
            assert abs(sum(groups.values())-r['total_seconds']) < 1e-9
            item[label] = dict(arm=r['arm'], forecast_hash=r['forecast_hash'], candidate_hash=r['candidate_hash'],
                               mase=r['mase'], total_seconds=r['total_seconds'], tool_count=r['tool_count'],
                               high_overrun=r['total_seconds'] > 3.5, components=dict(groups), invoice=r['invoice'])
        pairs.append(item)
    sessions = []
    for session in sorted((ROOT/'results/v431-r3/probes/financial/sessions').glob('*')):
        if not (session/'cost_ledger.json').exists():
            continue
        shards = []
        for c in read(session/'cost_ledger.json'):
            response = read(session/(c['shard']+'.response.json'))
            inv = [r for r in read(session/'model_invoices.json') if r['shard'] == c['shard']]
            shards.append(dict(**c, actual_response_load_seconds=response.get('service_initial_load_seconds'),
                               cache_hits=sum(bool(r.get('cache_hit', False)) for r in response['rows']),
                               non_cache_calls=sum(not r.get('cache_hit', False) for r in response['rows']),
                               allocated_overhead_per_request=inv[0]['allocated_shard_overhead_seconds'],
                               response_file=str((session/(c['shard']+'.response.json')).relative_to(ROOT))))
        sessions.append(dict(session=str(session.relative_to(ROOT)), shards=shards))
    tato = {}
    for family, folder in [('bolt', 'tato'), ('timesfm', 'timesfm_tato')]:
        directory = ROOT/'results/v431/20260914-sprint'/folder
        decisions = read(directory/'decisions.json')
        trials = [t for r in decisions for t in r['trials']]
        tato[family] = dict(episodes=len(decisions), trials=len(trials),
                            failures=dict(collections.Counter(t.get('error') for t in trials if t['status'] != 'completed')),
                            summary=read(directory/'summary.json'), source=str(directory.relative_to(ROOT)))
    old = read(ROOT/'results/v431-r2/finance/audit.json')
    metadata = [{k: r[k] for k in ('record', 'identity', 'timezone', 'train_statistics',
                                 'natural_gap_status', 'verified_natural_expected_observation_gap_set', 'adjustment')}
                for r in old['records'] if r['record']['source'] in ('Oil_Price', 'US_Term_Structure')]
    result = dict(status='completed', input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  method='existing reviewed DEV ledger only; no raw future, calibration or test read',
                  pairs=pairs, pair_count=len(pairs), parent_count=len({r['parent_group'] for r in pairs}),
                  all_final_hashes_equal=all(r['prediction_hash_equal'] and r['candidate_hash_equal'] for r in pairs),
                  actual_high_overruns={k: sum(r[k]['high_overrun'] for r in pairs) for k in ('H32', 'H')},
                  sessions=sessions, tato=tato, inherited_financial_metadata=metadata)
    (OUT/'financial_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('status', 'pair_count', 'parent_count', 'all_final_hashes_equal', 'actual_high_overruns')}, ensure_ascii=False))


if __name__ == '__main__':
    run()
