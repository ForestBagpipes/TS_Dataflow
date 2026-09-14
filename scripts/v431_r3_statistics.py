#!/usr/bin/env python3
"""Independent source/parent statistics from frozen r3 evaluator artifacts.

No model loading, fitting, target archive or held-out reader. Oracle quantities
are used only for the explicitly labelled historical-selection regret audit.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

N_BOOT = 2000
SEED = 101
EPS = 1e-12
POOL = ('A0_NATIVE', 'A0_FFILL', 'A2_SINGLE', 'A3_COV', 'A4_RIDGE_CONTEXT')
SUITES = {'main': '', 'check': 'check_', 'new_combination': 'new_combination_', 'financial': 'financial_'}
METRICS = ('mase', 'mae', 'total_seconds', 'tool_count', 'switch_gain', 'wrong_switch_loss', 'net_gain')


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path);tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False, ensure_ascii=False) + '\n')
    tmp.replace(path)


def sign(value):
    return 'positive' if value > EPS else 'negative' if value < -EPS else 'zero'


def macro(rows, field):
    """Each source has equal mass; each parent shares its mass over variants."""
    groups = defaultdict(list)
    for r in rows:
        groups[r['source'], r['parent_group']].append(float(r[field]))
    sources = defaultdict(list)
    for (source, _), values in groups.items():
        sources[source].append(float(np.mean(values)))
    return float(np.mean([np.mean(values) for values in sources.values()])) if sources else None


def blocked_bootstrap(rows, field):
    """Nonoverlapping adjacent two-parent blocks within each fixed source.

    An odd final parent is retained as a singleton. Resampled source means use
    the actual number of resampled parents, not equal weighting of blocks.
    Horizons/variants never leave their parent. Sources themselves are fixed.
    """
    parent = defaultdict(list);times = {}
    for row in rows:
        key = row['source'], row['parent_group'];parent[key].append(float(row[field]))
        times[key] = min(times.get(key, row['raw_start']), row['raw_start'])
    if not parent:
        return {'status': 'unsupported_empty_common_support', 'mean': None, 'ci90': None, 'ci95': None}
    rng = np.random.default_rng(SEED);replicates = np.zeros(N_BOOT);layout = {}
    source_names = sorted({k[0] for k in parent})
    for source in source_names:
        keys = sorted([k for k in parent if k[0] == source], key=lambda k: (times[k], k[1]))
        values = np.array([np.mean(parent[k]) for k in keys])
        blocks = [list(range(j, min(j + 2, len(keys)))) for j in range(0, len(keys), 2)]
        sums = np.array([values[b].sum() for b in blocks]);counts = np.array([len(b) for b in blocks])
        chosen = rng.integers(0, len(blocks), size=(N_BOOT, len(blocks)))
        replicates += sums[chosen].sum(axis=1) / counts[chosen].sum(axis=1) / len(source_names)
        layout[source] = {'parents': len(keys), 'blocks': len(blocks),
                          'parent_blocks': [[keys[j][1] for j in b] for b in blocks]}
    scarce = [s for s, v in layout.items() if v['blocks'] < 2]
    return {'status': 'computed_descriptive', 'mean': macro(rows, field),
            'ci90': np.quantile(replicates, [.05, .95]).tolist(),
            'ci95': np.quantile(replicates, [.025, .975]).tolist(),
            'n_bootstrap': N_BOOT, 'seed': SEED, 'source_block_layout': layout,
            'sources_with_fewer_than_two_blocks': scarce,
            'uncertainty_limit': 'fixed observed sources; singleton sources cannot estimate their time-dependence uncertainty',
            'confirmatory_test': False}


def metadata(root):
    combined = {}
    for suite in ('main', 'financial'):
        path = root / 'probes' / suite / 'episode_manifest.json'
        if path.exists():
            for uid, m in read(path).items():
                if uid in combined:
                    require(combined[uid]['parent_group'] == m['parent_group'], 'Metadata UID changed parent')
                combined[uid] = m
    return combined


def planned_comparisons(budgets):
    result = []
    for budget in budgets:
        result.extend([
            ('agent_vs_fixed_reference', 'R3_AGENT_' + budget, 'FIXED_REFERENCE', ()),
            ('agent_vs_frozen_fixed_acquisition', 'R3_AGENT_' + budget, 'R3_FIXED_TOOL_' + budget, ()),
            ('agent_vs_random_feasible', 'R3_AGENT_' + budget, 'R3_RANDOM_' + budget, ()),
            ('response_vs_no_kappa', 'RESIDUAL_control_' + budget, 'RESIDUAL_H_' + budget, ('control', 'H')),
            ('response_vs_raw_forecast_dispersion', 'RESIDUAL_control_' + budget, 'RESIDUAL_disagreement_' + budget, ('control', 'disagreement')),
            ('response_vs_equal_cost_ordinary_history', 'RESIDUAL_control_' + budget, 'RESIDUAL_equal-cost_' + budget, ('control', 'equal-cost')),
            ('response_vs_same_evidence_CART', 'RESIDUAL_control_' + budget, 'CART_control_' + budget, ('control', 'control')),
            ('response_vs_same_capacity_direct_ridge', 'RESIDUAL_control_' + budget, 'DIRECT_control_' + budget, ('control', 'control')),
            ('target_H_vs_H32', 'RESIDUAL_H_' + budget, 'RESIDUAL_H32_' + budget, ('H', 'H32')),
        ])
    return result


def paired(left, right, *, require_states=(), mechanism=None):
    left = {r['episode_uid']: r for r in left};right = {r['episode_uid']: r for r in right}
    require(set(left) == set(right), 'Paired policies have different full denominators')
    all_uids = set(left);common = set(all_uids)
    support = {'full_episodes': len(all_uids), 'full_parents': len({r['parent_group'] for r in left.values()}),
               'parent_count_semantics': 'unsupported/excluded parents have at least one such episode; they can also have supported episodes and are not additive'}
    if require_states:
        details = []
        for side, (rows, state) in enumerate(zip((left, right), require_states)):
            measured = {u for u in all_uids if (state, u) in mechanism}
            acquired = {u for u, r in rows.items() if u in measured and r['actual_state'] == state}
            fallback = {u for u in acquired if rows[u]['status'] == 'fallback'}
            details.append({'side': 'left' if side == 0 else 'right', 'state': state,
                            'evidence_supported_episodes': len(measured),
                            'unsupported_episodes': len(all_uids - measured),
                            'unsupported_parents': len({rows[u]['parent_group'] for u in all_uids - measured}),
                            'not_acquired_despite_supported': len(measured - acquired),
                            'acquired_with_terminal_fallback_episodes': len(fallback)})
            common &= acquired
        support['sides'] = details
    values = []
    for uid in sorted(common):
        a, b = left[uid], right[uid]
        for field in ('source', 'parent_group', 'horizon', 'condition', 'raw_start'):
            require(a[field] == b[field], 'Paired task metadata differ')
        item = {k: a[k] for k in ('episode_uid', 'source', 'parent_group', 'horizon', 'condition', 'raw_start')}
        for metric in ('mase', 'mae', 'total_seconds', 'tool_count'):
            item[metric + '_difference'] = a[metric] - b[metric]
        item.update(action_changed=float(a['arm'] != b['arm']),
                    forecast_changed=float(a.get('forecast_hash') != b.get('forecast_hash'))
                        if 'forecast_hash' in a and 'forecast_hash' in b else None,
                    left_terminal_fallback=float(a['status'] == 'fallback'), right_terminal_fallback=float(b['status'] == 'fallback'))
        values.append(item)
    support.update(common_episodes=len(common), common_parents=len({r['parent_group'] for r in values}),
                   common_sources=sorted({r['source'] for r in values}), common_episode_uids=sorted(common),
                   excluded_episodes=len(all_uids-common),
                   excluded_parents=len({left[u]['parent_group'] for u in all_uids-common}))
    result = {'difference_direction': 'left_minus_right; negative MASE/cost favors left',
              'support': support, 'mase_difference': blocked_bootstrap(values, 'mase_difference'),
              'mae_difference': macro(values, 'mae_difference'), 'seconds_difference': macro(values, 'total_seconds_difference'),
              'tool_count_difference': macro(values, 'tool_count_difference'),
              'paired_improved_equal_worse': {k: sum(sign(-r['mase_difference']) == k for r in values)
                                              for k in ('positive', 'zero', 'negative')},
              'action_changes': int(sum(r['action_changed'] for r in values)),
              'forecast_changes': int(sum(r['forecast_changed'] for r in values))
                  if values and all(r['forecast_changed'] is not None for r in values) else None}
    return result, values


def mechanism_statistics(rows, universe):
    """Sign and ranking diagnostics, with no oracle row in deployment tables."""
    output = []
    groups = defaultdict(list)
    for row in rows:
        groups[row['family'], row['state']].append(row)
    for (family, state), group in sorted(groups.items()):
        actual = universe[family];require(len({r['episode_uid'] for r in group}) == len(group), 'Duplicate mechanism row')
        observations = [];rank = [];mapped_observations = [];response_quadrants = Counter()
        for r in group:
            ref = POOL.index(r['reference_arm']);d = np.asarray(r['measured_gain'], float);target = np.asarray(r['current_task_gain'], float)
            require(d.shape == target.shape == (5,) and np.isfinite(d).all() and np.isfinite(target).all(), 'Malformed real mechanism gains')
            require(abs(d[ref]) <= EPS and abs(target[ref]) <= EPS, 'Reference gain not zero')
            base = {k: r[k] for k in ('episode_uid', 'source', 'parent_group', 'horizon', 'condition', 'raw_start')}
            for arm in range(5):
                if arm == ref:
                    continue
                ms, ts = sign(d[arm]), sign(target[arm]);cell = ms + '/' + ts
                observations.append(dict(base, measured_sign=ms, current_sign=ts, same_sign=float(ms == ts),
                                         **{'cell_' + m + '/' + t: float(cell == m + '/' + t)
                                            for m in ('negative', 'zero', 'positive') for t in ('negative', 'zero', 'positive')}))
                if r.get('mapped_gain') is not None:
                    mapped = np.asarray(r['mapped_gain'], float)
                    require(mapped.shape == (5,) and np.isfinite(mapped).all(), 'Malformed fitted response gain')
                    ps = sign(mapped[arm]);mapped_cell = ps + '/' + ts
                    mapped_observations.append(dict(base, measured_sign=ps, current_sign=ts, same_sign=float(ps == ts),
                        **{'cell_' + m + '/' + t: float(mapped_cell == m + '/' + t)
                           for m in ('negative', 'zero', 'positive') for t in ('negative', 'zero', 'positive')}))
                if state == 'control':
                    require(r['extra'] is not None and len(r['extra']) == 5, 'Measured signed response is missing')
                    # z is a strictly positive fixed multiple of kappa.
                    response_quadrants[ms + '/' + sign(r['extra'][arm]) + '/' + ts] += 1
            best = float(d.max());chosen = ref if d[ref] == best else int(np.flatnonzero(d == best)[0])
            if actual[r['episode_uid']]['fully_observed']:
                chosen = 0
            oracle_gain = float(target.max());gain = float(target[chosen])
            require(oracle_gain-gain >= -EPS, 'Negative true ranking regret')
            rank.append(dict(base, historical_selected_arm=POOL[chosen], actual_gain_of_historical_argmax=gain,
                             actual_wrong_switch_loss=max(-gain, 0.), selection_regret_to_five_arm_oracle=oracle_gain-gain))
        confusion = Counter((r['measured_sign'], r['current_sign']) for r in observations)
        supported = {r['episode_uid'] for r in group};missing = set(actual)-supported
        counts = {s: sum(r['current_sign'] == s for r in observations) for s in ('negative', 'zero', 'positive')}
        output.append({'family': family, 'state': state, 'sign_epsilon': EPS, 'reference_arm_excluded_from_sign_counts': True,
            'episodes': len(group), 'parents': len({r['parent_group'] for r in group}),
            'unsupported_episodes': len(missing), 'unsupported_parents': len({actual[u]['parent_group'] for u in missing}),
            'parent_count_semantics': 'unsupported parents have at least one unsupported episode; they may also appear among supported parents',
            'nonreference_arm_comparisons': len(observations), 'current_sign_counts': counts,
            'measured_sign_counts': {s: sum(r['measured_sign'] == s for r in observations) for s in counts},
            'sign_confusion_counts': {m + '/' + t: confusion[m, t] for m in counts for t in counts},
            'source_parent_weighted_sign_confusion': {m + '/' + t: macro(observations, 'cell_' + m + '/' + t) for m in counts for t in counts},
            'source_parent_weighted_sign_agreement': macro(observations, 'same_sign'),
            'mapped_gain_available_episodes': len({r['episode_uid'] for r in mapped_observations}),
            'mapped_gain_unavailable_episodes': len(group)-len({r['episode_uid'] for r in mapped_observations}),
            'mapped_sign_agreement': macro(mapped_observations, 'same_sign'),
            'mapped_sign_confusion_counts': dict(Counter(r['measured_sign']+'/'+r['current_sign'] for r in mapped_observations)),
            'mapped_source_parent_weighted_sign_confusion': {m+'/'+t: macro(mapped_observations, 'cell_'+m+'/'+t) for m in counts for t in counts},
            'd_long_kappa_current_sign_counts': dict(response_quadrants) if state == 'control' else None,
            'historical_argmax_actual_gain': macro(rank, 'actual_gain_of_historical_argmax'),
            'historical_argmax_wrong_switch_loss': macro(rank, 'actual_wrong_switch_loss'),
            'historical_argmax_oracle_selection_regret': blocked_bootstrap(rank, 'selection_regret_to_five_arm_oracle'),
            'oracle_scope': 'diagnostic ranking regret only; not a method score or an acquisition label', 'per_episode_ranking': rank})
    return output


def analyze_suite(root, suite, prefix, meta, budgets):
    names = [prefix + suffix for suffix in ('decisions.json', 'table.json', 'mechanism_rows.json', 'support.json', 'evaluation_status.json')]
    missing = [name for name in names if not (root / name).exists()]
    if missing:
        return {'status': 'pending_inputs', 'missing': missing}, [], [], {}, []
    status = read(root / names[-1]);require(status['status'] == 'completed', 'Evaluation is not complete: ' + suite)
    rows, table, mechanism, support = [read(root / n) for n in names[:4]]
    for r in rows + mechanism:
        require(r['episode_uid'] in meta, 'Unregistered current UID')
        m = meta[r['episode_uid']]
        require(r['parent_group'] == m['parent_group'] and r['source'] == m['source'], 'Metadata lineage changed')
        r['raw_start'] = m['raw_start']
        require(r.get('split', m['split']) in ('train', 'dev'), 'Held-out record reached statistics')
    by = defaultdict(list);universe = {};summaries = []
    for r in rows:
        require(all(np.isfinite(r[k]) for k in METRICS), 'Nonfinite metric or failed window silently removed')
        by[r['family'], r['policy']].append(r)
    require({k[0] for k in by} == {'bolt', 'timesfm'}, 'A completed suite must include both registered families')
    for family in sorted({k[0] for k in by}):
        refs = by[family, 'FIXED_REFERENCE'];universe[family] = {r['episode_uid']: r for r in refs}
        require(len(universe[family]) == len(refs), 'Duplicate reference UID')
        for (f, p), rs in by.items():
            if f == family:
                require(len(rs) == len(refs) and {r['episode_uid'] for r in rs} == set(universe[family]), 'Policy dropped/duplicated common windows')
    expected = {(r['family'], r['policy']): r for r in table}
    require(set(expected) == set(by) and len(expected) == len(table), 'Main table has missing/duplicate policy groups')
    source_detail = []
    for key, rs in sorted(by.items()):
        item = dict(family=key[0], policy=key[1], **{k: macro(rs, k) for k in METRICS})
        for field in METRICS:
            np.testing.assert_allclose(item[field], expected[key][field], rtol=1e-12, atol=1e-12)
        item.update(episodes=len(rs), parents=len({r['parent_group'] for r in rs}), sources=len({r['source'] for r in rs}),
                    budget_overruns=sum(r['budget_overrun'] for r in rs))
        for field in ('episodes', 'parents', 'sources', 'budget_overruns'):
            require(item[field] == expected[key][field], 'Table support or budget count differs: '+field)
        summaries.append(item)
        cells = defaultdict(list)
        for r in rs:
            cells[r['source'], r['horizon'], r['condition']].append(r)
        for cell, values in sorted(cells.items()):
            source_detail.append(dict(suite=suite, family=key[0], policy=key[1], source=cell[0], horizon=cell[1], condition=cell[2],
                                      episodes=len(values), parents=len({r['parent_group'] for r in values}), **{k: macro(values, k) for k in METRICS}))
    comparisons = [];common_support = []
    for family in sorted(universe):
        mech = {(r['state'], r['episode_uid']): r for r in mechanism if r['family'] == family}
        for name, left, right, states in planned_comparisons(budgets):
            require((family, left) in by and (family, right) in by, 'A registered comparison method has not run')
            result, paired_rows = paired(by[family, left], by[family, right], require_states=states, mechanism=mech)
            entry = dict(suite=suite, family=family, comparison=name, left=left, right=right,
                         scope='common_supported_and_actually_acquired' if states else 'full_common_denominator', **result)
            comparisons.append(entry)
            if states:
                common_support.append(entry)
            cells = defaultdict(list)
            for r in paired_rows:
                cells[r['source'], r['horizon'], r['condition']].append(r)
            for cell, values in sorted(cells.items()):
                source_detail.append(dict(suite=suite, family=family, comparison=name, left=left, right=right,
                    scope=entry['scope'], source=cell[0], horizon=cell[1], condition=cell[2], episodes=len(values),
                    parents=len({r['parent_group'] for r in values}), **{k: macro(values, k)
                       for k in ('mase_difference', 'mae_difference', 'total_seconds_difference', 'tool_count_difference')}))
    observed_support = {(f, state): len({u for (s, u) in [(r['state'], r['episode_uid']) for r in mechanism if r['family'] == f] if s == state})
                        for f in universe for state in ('H32', 'H', 'control', 'equal-cost', 'disagreement')}
    for row in support:
        require(row['supported_rows'] == observed_support[row['family'], row['state']], 'Published mechanism support disagrees with rows')
    stats = {'status': 'completed', 'full_coverage_table_recomputed': summaries,
             'sign_and_ranking_diagnostics': mechanism_statistics(mechanism, universe),
             'source_files_sha256': {n: sha(root / n) for n in names}}
    return stats, comparisons, source_detail, {'suite': suite, 'state_support': support, 'comparisons': common_support}, rows


def self_test():
    rows = [dict(source='A', parent_group='a', raw_start=0, value=0.),
            dict(source='A', parent_group='b', raw_start=10, value=10.),
            dict(source='B', parent_group='c', raw_start=20, value=2.)]
    require(macro(rows, 'value') == 3.5, 'Source macro-average failed')
    require(macro(rows + [rows[0]] * 50, 'value') == 3.5, 'Replicating a parent expanded its mass')
    a = blocked_bootstrap(rows, 'value');b = blocked_bootstrap(rows + [rows[0]] * 50, 'value')
    require(a == b and a['n_bootstrap'] == 2000, 'Parent blocks split variants or changed deterministic bootstrap')
    require([sign(x) for x in (-2e-12, -1e-12, 0., 1e-12, 2e-12)] == ['negative', 'zero', 'zero', 'zero', 'positive'], 'Signed zero boundary wrong')
    print('PASS source macro weights; parent replication; grouped deterministic bootstrap; signed zero threshold')


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--root', type=Path, default=Path('results/v431-r3'))
    parser.add_argument('--self-test', action='store_true');args = parser.parse_args()
    if args.self_test:
        return self_test()
    root = args.root;meta = metadata(root)
    manifest = read(root / 'terminal_manifest.json') if (root / 'terminal_manifest.json').exists() else read('configs/v431_r3/manifest.json')
    result = {'status': 'running', 'created_at': datetime.now(timezone.utc).isoformat(), 'script_sha256': sha(__file__),
              'statistical_rule': {'source_equal_weight': True, 'parent_grouped_variants': True, 'time_block_parents': 2,
                  'n_bootstrap': N_BOOT, 'seed': SEED, 'zero_threshold': EPS, 'calibration_test_read': False,
                  'oracle_only_for_ranking_diagnostics': True}, 'suites': {}}
    paired_rows, details, common = [], [], []
    for suite, prefix in SUITES.items():
        try:
            value, p, d, c, _ = analyze_suite(root, suite, prefix, meta, list(manifest['budgets']))
        except Exception as exc:
            # Preserve failed audits as immutable artifacts; no partially
            # checked suite contributes numerical conclusions.
            value = {'status': 'failed', 'error': type(exc).__name__ + ': ' + str(exc)}
            p, d, c = [], [], {}
        result['suites'][suite] = value;paired_rows.extend(p);details.extend(d)
        if c:
            common.append(c)
    complete = [s for s, v in result['suites'].items() if v['status'] == 'completed']
    failed = [s for s, v in result['suites'].items() if v['status'] == 'failed']
    result.update(status='failed' if failed else 'completed' if len(complete) == len(SUITES) else 'partial' if complete else 'pending_inputs',
                  completed_suites=complete, failed_suites=failed, method_promoted=False, confirmatory_test=False)
    outputs = {'statistics.json': result, 'paired_comparisons.json': {'status': result['status'], 'comparisons': paired_rows},
               'source_horizon_condition.json': {'status': result['status'], 'rows': details},
               'mechanism_common_support.json': {'status': result['status'], 'suites': common}}
    snapshot = root / 'statistics_runs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');snapshot.mkdir(parents=True)
    for name, value in outputs.items():
        write(snapshot / name, value);write(root / name, value)
    print(json.dumps(dict(status=result['status'], snapshot=str(snapshot), completed_suites=complete,
                          paired_comparisons=len(paired_rows), source_horizon_condition_rows=len(details))), flush=True)
    if result['status'] == 'pending_inputs':
        raise SystemExit(2)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
