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
      'tests/v431_r5/*.py','configs/v431-r5/*.json','docs/figures/v431-r5/*']:
        files.update(Path('.').glob(pattern))
    for name in ['AGENTS.md','README.md','docs/HANDOFF.md','docs/version_ledger.md','docs/claims.md',
      'docs/novelty_matrix.md','docs/paper_v431_draft.md','docs/paper_v431_r5_method.md','docs/experiment-matrix.md','scripts/env_new_server.sh',
      'scripts/v431_r4_online.py','scripts/online_v43_agent.py','scripts/v431_r2_services.py',
      'scripts/serve_v43_model.py','scripts/serve_v431_r2_timesfm.py','scripts/v431_r3_statistics.py']:
        files.add(Path(name))
    for folder in ['v43','v431','v431_r2','v431_r3','v431_r4']:
        files.update((Path('src/introact_ts')/folder).rglob('*.py'))
    for pattern in ['delivery_summary.json','final_snapshot.json','docx_export_audit.json','actual_commands.json','strong_simple_freeze.json',
      'fit/manifest.json','fit/models_frozen.json','space/summary.json','data/*/support*.json','data/status.json',
      'statistics/*audit*.json','statistics/fixed_trace_changed_windows.json','evaluation/*/common*table.json',
      'evaluation/*/mechanism_table.json','evaluation/*/status.json','main-preparation/*.json',
      'online-*/status.json','online-*/visibility_barrier.json','online-*/process_accounting.json',
      'online-*/service/service_startup.json','evaluation/*/allfive-executed/table.json',
      'statistics/cost_information.json','statistics/backbone_source_comparison.json',
      'statistics/projection_ranking_counterexample.json','main-preparation/audit-v2/*.json',
      'backbone-registry/registry.json','chronos2-native-check/*status.json',
      'chronos2-native-check/support-audit.json','chronos2-native-check/audit/*.json',
      '*queue-status.json','tato-scene/audit.json','tato-scene/*/request*.json',
      'tato-scene/*/run/status.json','tato-scene/*/run/frozen*.json',
      'tato-scene-extra/queue*.json','tato-scene-extra/*/request*.json',
      'tato-scene-extra/*/run/status.json','tato-official96/*/request*.json',
      'tato-official96/*/run/status.json','tato-scene/train_cache_reuse_audit*.json',
      'tato-scene-extra/cache_queue_handoff.json','tato-scene-extra/*amendment.json',
      'tato-scene-extra-cached/queue*.json','tato-scene-extra-cached/*/request*.json',
      'tato-scene-extra-cached/*/run/status.json','tato-scene-extra-cached/*/run/frozen*.json',
      'tato-scene-restart-*/queue*.json','tato-scene-restart-*/*/request*.json',
      'tato-scene-restart-*/*/run/status.json','tato-scene-restart-*/*/run/frozen*.json',
      'chronos2-native-check/retry-map.json','chronos2-native-check/attempt1-record-failure/queue*.json',
      'chronos2-native-check/attempt1-record-failure/train/status.json',
      'chronos2-queue-status.attempt1-failed.json','main-train-smoke/*.json',
      'main-train-smoke/*/status.json','main-train-smoke/*/model_identity.json',
      'main-train-smoke/*/records.json','main-train-smoke/*/calls.json',
      'main-train-bank/*.json','main-train-bank/*/status.json',
      'main-train-bank/*/model_identity.json','main-train-bank/*/records.json',
      'main-train-bank/*/calls.json']:
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
          supervision_loss_mae_over_origin_scale=b.losses[i],origin_scale=b.rows[i]['origin_scale'],
          scope='Previously used r5 TRAIN native forecasts and loss supervision; no original dataset or future target values') for i in idx]
    # Small raw forecast samples only; never include original inputs or future targets.
    tato_folders=['tato-scene','tato-scene-extra-cached','tato-official96']
    tato_folders += sorted(p.name for p in R.glob('tato-scene-restart-*') if p.is_dir())
    for folder in tato_folders:
        for prediction_file in sorted((R/folder).glob('*/run/predictions.npz')):
            originals[str(prediction_file)]=sha(prediction_file)
            with np.load(prediction_file,allow_pickle=False) as values:
                chosen=sorted(values.files)[:1]
                snapshots[f'samples/{folder}-{prediction_file.parents[1].name}.json']=dict(
                    scope='one saved deployment prediction; source labels/inputs excluded',
                    prediction_file_sha256=sha(prediction_file),
                    forecasts={k:values[k].tolist() for k in chosen})
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
