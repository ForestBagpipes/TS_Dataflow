#!/usr/bin/env python3
"""Build a bounded audit package: code, metadata, small traces, no weights/data."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path('results/v431-r4')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    files = set()
    for pattern in ('docs/v431_r4*.md', 'scripts/*v431_r4*.py', 'src/introact_ts/v431_r4/*.py',
                    'tests/v431_r4/*.py', 'configs/v431-r4/*.json'):
        files.update(Path('.').glob(pattern))
    for name in ('AGENTS.md', 'README.md', 'docs/HANDOFF.md', 'docs/version_ledger.md',
                 'docs/claims.md', 'docs/novelty_matrix.md', 'docs/paper_v431_draft.md',
                 'docs/experiment-matrix.md', 'scripts/env_new_server.sh'):
        files.add(Path(name))
    # Relevant original implementation, not third-party weights/checkpoints.
    for directory in ('src/introact_ts/v43', 'src/introact_ts/v431',
                      'src/introact_ts/v431_r2', 'src/introact_ts/v431_r3'):
        files.update(Path(directory).rglob('*.py'))
    for name in ('scripts/v431_r3_collect.py', 'scripts/v431_r3_fit.py',
                 'scripts/online_v43_agent.py', 'scripts/v431_r2_services.py',
                 'scripts/serve_v43_model.py', 'scripts/serve_v431_timesfm.py'):
        if Path(name).is_file():
            files.add(Path(name))
    for pattern in ('*queue*.json', 'common*json', 'cost_summary.json', 'r3_hash_compatibility.json',
                    'fit/models_frozen.json', 'fit/manifest.json',
                    'verification/*.json', 'trajectory-final/*/support.json',
                    'trajectory-final/*/status.json', 'trajectory-final/files_sha256.json',
                    'legacy*/status.json', 'legacy*/execution.json', 'legacy*/terminal_freeze.json',
                    'legacy*/acquisition_report.json', 'baseline_audit/financial_audit.json',
                    'evaluation/*/common_table.json', 'evaluation/*/common_sources.json',
                    'online-*/status.json', 'online-*/process_accounting.json',
                    'online-*/decisions.json', 'online-*/verification.json',
                    'online-*/visibility_barrier.json', 'online-*/protocol.json',
                    'online-*/service/load-*.response.json',
                    'online-*/service/model_manifest.json', 'online-*/service/code_manifest.json',
                    'online-*/service/service_startup.json'):
        files.update(ROOT.glob(pattern))
    files.update(Path('logs/v431-r4').glob('online*.log'))
    snapshots = {}
    originals = {}
    external = read(ROOT / 'baseline_audit/external_hot_costs.json')
    trial_failures = []
    for scope, record in external['tato'].items():
        path = Path(record['status_file']).parent / 'decisions.json'
        originals[str(path)] = sha(path)
        for row in read(path):
            for trial in row['trials']:
                if trial['status'] != 'completed':
                    trial_failures.append({'scope': scope, 'episode_uid': row['episode_uid'],
                                           'parent_group': row['parent_group'], **trial})
    snapshots['failures/tato-all-failed-trials.json'] = trial_failures
    for suite in ('dev', 'financial'):
        path = ROOT / 'evaluation' / suite / 'common_decisions.json'
        rows = read(path)
        originals[str(path)] = sha(path)
        selected = [r for r in rows if r['policy'] == 'JOINT_high']
        # A few actual paths; source/label values are only previously used DEV.
        snapshots['samples/' + suite + '-paths.json'] = selected[:3] + selected[-3:]
        failures = [dict(family=r['family'], policy=r['policy'], uid=r['episode_uid'],
                         budget=r['budget'], total_seconds=r['total_seconds'],
                         budget_overrun=r.get('budget_overrun'), trace=r.get('trace', {}))
                    for r in rows if r.get('budget_overrun') or
                    r.get('trace', {}).get('supported') is False]
        snapshots['failures/' + suite + '-all-path-failures.json'] = failures
    # Summaries retain every comparison; bulky per-parent bootstrap inputs stay
    # in the hashed server artifact and are reproduced by the included script.
    stats = read(ROOT / 'statistics.json')
    originals[str(ROOT / 'statistics.json')] = sha(ROOT / 'statistics.json')
    def reduce(value, key=''):
        if isinstance(value, dict):
            return {k: reduce(v, k) for k, v in value.items()}
        if isinstance(value, list):
            if len(value) > 40 and ('rows' in key or 'paths' in key or 'episodes' in key):
                return {'retained_on_server': True, 'count': len(value), 'examples': value[:2]}
            return [reduce(v) for v in value]
        return value
    snapshots['statistics_summary.json'] = reduce(stats)
    # Paired raw historical predictions, at most four existing TRAIN examples.
    from introact_ts.v431_r4.trajectory_dataset import r3_api
    selected_uids = []
    for row in read(ROOT / 'evaluation/T_fit/decisions.json'):
        if row['policy'] == 'JOINT_high' and row.get('trace', {}).get('tool') and row['episode_uid'] not in selected_uids:
            selected_uids.append(row['episode_uid'])
        if len(selected_uids) == 2:
            break
    api = r3_api()
    for family in ('bolt', 'timesfm'):
        ledger, provenance = api.load_probe_ledger(Path('results/v431-r3'), family, selected_uids, 'main')
        snapshots['samples/' + family + '-paired-raw-predictions.json'] = {
            'family': family, 'scope': 'previously used TRAIN, never deployment-visible supervision',
            'rows': [ledger[u, atom] for u in selected_uids for atom in ('long', 'short')],
            'provenance': provenance}
    for name in ('hot_costs.json', 'baseline_audit/hot_costs.json',
                 'baseline_audit/external_hot_costs.json', 'fit/models.joblib',
                 'legacy-final/models.joblib'):
        path = ROOT / name
        originals[str(path)] = sha(path)
    manifest = {'commit': commit, 'created_at': datetime.now(timezone.utc).isoformat(),
                'working_tree_status': subprocess.check_output(['git', 'status', '--porcelain'], text=True),
                'scope': 'r4 code/config/support/tables/sample raw predictions/cost/failures; no weights or datasets',
                'files': {str(p): sha(p) for p in sorted(files)},
                'large_server_artifacts_sha256': originals,
                'historical_original_prediction_files_unchanged': True}
    snapshots['manifest.json'] = manifest
    output = ROOT / ('review-' + commit[:12] + '.tar.gz')
    if output.exists():
        raise RuntimeError('Review package exists; do not overwrite its identity')
    with tarfile.open(output, 'w:gz') as tar:
        for p in sorted(files):
            tar.add(p, arcname=str(p), recursive=False)
        for name, value in snapshots.items():
            data = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    with tarfile.open(output) as tar:
        assert all(not (p.name.startswith('/') or '..' in Path(p.name).parts) for p in tar.getmembers())
    delivery = {'commit': commit, 'path': str(output), 'sha256': sha(output),
                'bytes': output.stat().st_size, 'created_at': manifest['created_at']}
    (ROOT / 'review_package.json').write_text(json.dumps(delivery, indent=2) + '\n')
    print(json.dumps(delivery))


if __name__ == '__main__':
    main()
