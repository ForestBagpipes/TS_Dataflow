#!/usr/bin/env python3
"""Bounded code/ledger review; model weights and datasets are excluded."""
from datetime import datetime,timezone
import hashlib,io,json,subprocess,tarfile
from pathlib import Path
import joblib
import numpy as np

R=Path('results/v431-r5')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def safe(x):
    if isinstance(x,dict):return {str(k):safe(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [safe(v) for v in x]
    if isinstance(x,np.ndarray):return safe(x.tolist())
    if isinstance(x,np.generic):return safe(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x
def main():
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    files=set()
    for pattern in ['docs/v431_r5*.md','scripts/*v431_r5*.py','src/introact_ts/v431_r5/*.py',
      'tests/v431_r5/*.py','configs/v431-r5/*.json']:
        files.update(Path('.').glob(pattern))
    for name in ['AGENTS.md','README.md','docs/HANDOFF.md','docs/version_ledger.md','docs/claims.md',
      'docs/novelty_matrix.md','docs/paper_v431_draft.md','docs/experiment-matrix.md','scripts/env_new_server.sh',
      'scripts/v431_r4_online.py','scripts/online_v43_agent.py','scripts/v431_r2_services.py',
      'scripts/serve_v43_model.py','scripts/serve_v431_timesfm.py','scripts/v431_r3_statistics.py']:
        files.add(Path(name))
    for folder in ['v43','v431','v431_r2','v431_r3','v431_r4']:
        files.update((Path('src/introact_ts')/folder).rglob('*.py'))
    for pattern in ['delivery_summary.json','actual_commands.json','strong_simple_freeze.json',
      'fit/manifest.json','fit/models_frozen.json','space/summary.json','data/*/support*.json','data/status.json',
      'statistics/*audit*.json','statistics/fixed_trace_changed_windows.json','evaluation/*/common*table.json',
      'evaluation/*/mechanism_table.json','evaluation/*/status.json','main-preparation/*.json',
      'online-*/status.json','online-*/visibility_barrier.json','online-*/process_accounting.json',
      'online-*/service/service_startup.json','allfive-executed/*/table.json']:
        files.update(R.glob(pattern))
    snapshots={}; originals={}
    for suite in ['dev','financial']:
        p=R/f'evaluation/{suite}/common_decisions.json'; rows=read(p);originals[str(p)]=sha(p)
        chosen=[r for r in rows if r['policy']=='R5_high']
        snapshots[f'samples/{suite}-r5-decisions.json']=chosen[:2]+chosen[-2:]
        snapshots[f'failures/{suite}-all.json']=[dict(family=r['family'],policy=r['policy'],uid=r['episode_uid'],
          seconds=r['total_seconds'],budget=r['budget'],reason=r.get('trace',{}).get('reason')) for r in rows
          if r['total_seconds']>r['budget'] or r.get('trace',{}).get('failure')]
    for family in ['bolt','timesfm']:
        p=R/f'online-{family}/decisions.json';rows=read(p);originals[str(p)]=sha(p)
        natural=[r for r in rows if not r['controlled']]
        continuing=[r for r in natural if r['actual_versions']>1]
        snapshots[f'samples/{family}-online.json']=natural[:1]+continuing[:2]+[r for r in rows if r['failure'] or r['budget_overrun']]
        p=R/f'data/main/{family}.joblib';d=joblib.load(p);originals[str(p)]=sha(p)
        b=d['batch'];idx=[i for i,r in enumerate(b.roles) if r=='T_fit'][:2]
        snapshots[f'samples/{family}-train-current-predictions.json']=[dict(
          predictions=d['predictions'][i],metadata=d['cache_metadata'][i],
          scope='TRAIN current-task native predictions; no original dataset or future values') for i in idx]
    p=R/'statistics/report.json';originals[str(p)]=sha(p)
    def reduce(v):
        if isinstance(v,dict):return {k:reduce(x) for k,x in v.items()}
        if isinstance(v,list):return [reduce(x) for x in v[:40]] if len(v)>40 else [reduce(x) for x in v]
        return v
    snapshots['statistics_summary_first40_per_long_list.json']=reduce(read(p))
    for p in [R/'fit/models.joblib',R/'statistics/report.json']:
        originals[str(p)]=sha(p)
    snapshots['manifest.json']=dict(commit=commit,created_at=datetime.now(timezone.utc).isoformat(),
      files={str(p):sha(p) for p in sorted(files)},server_artifact_sha256=originals,
      scope='Code, configurations, support, complete tables, cost/failure audit and small prediction/decision samples; no weights/data/credentials',
      working_tree=subprocess.check_output(['git','status','--porcelain'],text=True))
    out=R/f'review-{commit[:12]}.tar.gz'
    if out.exists():raise RuntimeError('Never overwrite review identity')
    with tarfile.open(out,'w:gz') as tar:
        for p in sorted(files):tar.add(p,arcname=str(p),recursive=False)
        for name,value in snapshots.items():
            data=(json.dumps(safe(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode();info=tarfile.TarInfo(name);info.size=len(data)
            tar.addfile(info,io.BytesIO(data))
    with tarfile.open(out) as tar:
        assert all(not(p.name.startswith('/') or '..' in Path(p.name).parts or p.name.endswith(('.joblib','.npz','.safetensors','.csv'))) for p in tar.getmembers())
    delivery=dict(code_commit=commit,path=str(out),sha256=sha(out),bytes=out.stat().st_size)
    (R/'review_package.json').write_text(json.dumps(delivery,indent=2)+'\n');print(json.dumps(delivery))
if __name__=='__main__':main()
