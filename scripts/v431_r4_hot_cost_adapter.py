#!/usr/bin/env python3
"""Map audited immutable charge keys to r4 batches; no prediction recomputation."""
import hashlib
import json
from pathlib import Path
from v431_r4_hot_costs import reprice_invoice


def main():
    root=Path('results/v431-r4')
    source=root/'baseline_audit/hot_costs.json'
    audit=json.loads(source.read_text())
    assert audit['status']=='completed'
    rows={};sources={};counts={}
    for suite in ('main','financial','generalization'):
        rows[suite]={};counts[suite]={}
        for family in ('bolt','timesfm'):
            path=root/'trajectory-final'/suite/(family+'.rows.json')
            sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            items=json.loads(path.read_text());rows[suite][family]={}
            for item in items:
                actions={a:reprice_invoice(r['invoice'],audit)[1] for a,r in item['actions'].items()}
                tools={t:reprice_invoice(r['invoice'],audit)[1] for t,r in item['tools'].items()}
                rows[suite][family][item['uid']]=dict(action_cold_seconds=actions,tool_cold_seconds=tools)
            counts[suite][family]=len(items)
    output=root/'hot_costs.json'
    if output.exists():raise RuntimeError('Refuse to overwrite frozen adapter')
    result=dict(status='completed',rows=rows,counts=counts,sources=sources,
        native_sidecar=str(source),native_sidecar_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Only explicit model-load allocation removed; projection, current diagnostics and all other overhead retained',
        physical_loads=audit['physical_loads'])
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],counts=counts,output=str(output))))


if __name__=='__main__':main()
