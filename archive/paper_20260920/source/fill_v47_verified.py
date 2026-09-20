#!/usr/bin/env python3
"""Audit a revision without replacing missing evidence with dummy results."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def main():
    source = ROOT / 'latex/IntroActTS_20260919_v47_revised.tex'
    text = source.read_text()
    placeholders = re.findall(r'\\ph\{([^{}]+)\}', text)
    evidence = {}
    for path in sorted((ROOT / 'results/v47_verified/protocol').glob('selection_*.json')):
        payload = json.loads(path.read_text())
        if payload.get('test_records_read') != 0:
            raise RuntimeError(f'Invalid TRAIN-only evidence: {path}')
        evidence[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = dict(status='incomplete' if placeholders else 'requires_result_audit',
                  source=str(source.relative_to(ROOT)),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  placeholder_occurrences=len(placeholders),
                  unresolved_keys=sorted(set(placeholders)),
                  verified_training_sources=evidence,
                  test_results_read=0, dummy_results_used=False,
                  warning='This is a post-hoc revision draft, not a completed experimental paper.')
    target = ROOT / 'docs/v47_paper_readiness.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'unresolved_keys'}, indent=2))


if __name__ == '__main__':
    main()
