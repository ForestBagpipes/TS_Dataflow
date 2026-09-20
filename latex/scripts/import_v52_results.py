"""Copy recorded server summaries into a portable figure evidence manifest.

No predictions, tests, bootstrap sampling or experiments are executed here.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'latex/figure/data/v52_evidence.json'
records = {}
for folder in ['evaluation', 'gate_controls']:
    for path in sorted((ROOT / 'results/v52_ablation' / folder).glob('*.json')):
        raw = json.loads(path.read_text(encoding='utf8'))
        if folder == 'evaluation':
            data = {k: raw[k] for k in ['backbone', 'block', 'frozen', 'episodes', 'parents', 'comparisons']}
            data['rows'] = {m: {k: row[k] for k in ['mase', 'rmsse', 'intervention_rate', 'conditional_hir', 'harmful_loss']} for m, row in raw['rows'].items()}
        else:
            data = {'calibration': raw['calibration'], 'backbone': raw['backbone'], 'blocks': {}}
            for block, result in raw['blocks'].items():
                data['blocks'][block] = {'comparisons': result['comparisons'], 'rows': {m: {k: row[k] for k in ['mase', 'rmsse', 'intervention_rate', 'conditional_hir', 'harmful_loss']} for m, row in result['rows'].items()}}
        records[f'{folder}/{path.name}'] = {'source': str(path.relative_to(ROOT)).replace('\\', '/'), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'data': data}
assert len(records) == 21, len(records)
OUT.write_text(json.dumps({'server_commit_reported_by_author': 'e78f206', 'scope': 'Recorded v52 server summaries. Post-hoc evaluation. No local statistical rerun.', 'records': records}, indent=2) + '\n', encoding='utf8')
print(OUT)
