#!/usr/bin/env python3
"""Recover explicit A4 support metadata without changing frozen producers.

CPU-only audit: the actual frozen ridge function is evaluated once per distinct
prepared payload. Existing and later completed candidate caches are checked by
hash, while pending GPU work stays pending rather than becoming a false pass.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from collections import Counter
import numpy as np

from introact_ts.v43.cli import atomic_json
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.p2_candidates import ridge_candidate
from introact_ts.v43.schemas import Episode, array_hash, require
from introact_ts.v431_r3.probe import canonical_view_hash


def read(path):
    return json.loads(Path(path).read_text())


def compare_cache(root, row):
    files = sorted((root / row['suite'] / 'candidate_cache').glob('*/' + row['cache_input_hash'] + '.json'))
    checked = []
    for path in files:
        record = read(path)
        require(record['status'] == 'completed', 'Incomplete candidate cache was exposed')
        require(record['identity']['input_hash'] == row['cache_input_hash'], 'Candidate cache uses another payload')
        require(file_hash(record['array_path']) == record['array_sha256'], 'Candidate numeric archive changed')
        with np.load(record['array_path'], allow_pickle=False) as arrays:
            digest = array_hash(arrays['A4_RIDGE_CONTEXT'])
        require(digest == record['array_hashes']['A4_RIDGE_CONTEXT'] == row['candidate_hash'], 'Derived A4 differs from actual cached candidate')
        checked.append(dict(path=str(path), cache_sha256=file_hash(path), candidate_hash=digest))
    return dict(status='matched' if checked else 'pending_candidate_generation', caches=checked)


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--root', type=Path, default=Path('results/v431-r3/probes'))
    parser.add_argument('--recheck', type=Path, help='Earlier support report: check newly completed caches without refitting ridge')
    args = parser.parse_args();begun = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = args.root.parent / 'ridge_support' / (stamp + '.json');out.parent.mkdir(exist_ok=True)
    report = dict(status='running', started_at=stamp, future_labels_read=0, heldout_labels_read=0,
                  producer_unchanged=True, source_sha256={str(p): file_hash(p) for p in
                    [Path(__file__), Path('src/introact_ts/v43/p2_candidates.py'), Path('src/introact_ts/v43/candidates.py')]})
    try:
        if args.recheck:
            prior = read(args.recheck);require(prior['status'] == 'completed', 'Cannot inherit incomplete support audit')
            for p, digest in prior['source_sha256'].items():
                if p != str(Path(__file__)):
                    require(file_hash(p) == digest, 'Ridge source changed before cache recheck')
            unique, lineage = prior['unique_payloads'], prior['lineage']
            report['rechecked_from'] = dict(path=str(args.recheck), sha256=file_hash(args.recheck))
        else:
            unique, lineage = [], []
            for suite in ('main', 'financial'):
                root = args.root / suite;meta = read(root / 'episode_manifest.json')
                preparation = read(root / 'preparation.json')
                require(file_hash(root / 'probe_manifest.json') == preparation['files']['probe_manifest.json'], 'Frozen probe ledger changed')
                seen = {}
                for row in read(root / 'probe_manifest.json'):
                    link = dict(suite=suite, base_uid=row['base_uid'], probe=row['spec']['name'], parent_group=row['parent_group'],
                                source=row['source'], split=row['split'], input_hash=row['input_hash'],
                                probe_status=row['status'], probe_reason=row['reason'])
                    if row['status'] != 'prepared':
                        lineage.append(link);continue
                    canonical = row['cache_input_hash'];link['cache_input_hash'] = canonical
                    if canonical not in seen:
                        require(file_hash(row['array_path']) == row['array_sha256'], 'Prepared numeric input changed')
                        with np.load(row['array_path'], allow_pickle=False) as f:
                            values = {name: f[name] for name in ('target', 'covariates', 'timestamps', 'availability')}
                        m = meta[row['base_uid']]
                        view = Episode(row['view_uid'], m['source'], m.get('panel', m['source']), m['parent_group'], m['split'],
                                       0, row['raw_start'], row['context_end'], row['spec']['horizon'], **values)
                        require(canonical_view_hash(view) == canonical, 'Canonical A4 input changed')
                        tick = time.perf_counter();candidate, detail = ridge_candidate(view);elapsed = time.perf_counter() - tick
                        item = dict(suite=suite, cache_input_hash=canonical, candidate_hash=array_hash(candidate.target),
                                    native_input_hash=array_hash(view.target), actual_fit_detail=detail,
                                    equals_native=np.array_equal(candidate.target, view.target, equal_nan=True),
                                    cpu_reconstruction_seconds=elapsed)
                        require(detail['status'] in ('completed', 'unsupported', 'not_needed'), 'Unrecorded ridge support outcome')
                        if detail['status'] != 'completed':
                            require(item['equals_native'], 'Fallback/not-needed A4 changed dirty input')
                        unique.append(item);seen[canonical] = item
                    link['actual_fit_detail'] = seen[canonical]['actual_fit_detail'];lineage.append(link)
        for row in unique:
            row['cache_verification'] = compare_cache(args.root, row)
        report.update(status='completed', unique_payloads=unique, lineage=lineage,
                      unique_payload_count=len(unique), lineage_count=len(lineage),
                      unique_support_counts=dict(Counter(r['actual_fit_detail']['status'] for r in unique)),
                      cache_status=dict(Counter(r['cache_verification']['status'] for r in unique)),
                      interpretation='A4 unsupported/not_needed preserves native input; this is not an independent successful ridge action')
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}');raise
    finally:
        report['runtime_seconds'] = time.perf_counter() - begun
        atomic_json(out, report)
        print(json.dumps(dict(path=str(out), **{k: v for k, v in report.items() if k not in ('unique_payloads', 'lineage')})), flush=True)


if __name__ == '__main__':
    main()
