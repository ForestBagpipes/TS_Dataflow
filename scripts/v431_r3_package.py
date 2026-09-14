#!/usr/bin/env python3
"""Export a small, auditable r3 review package; never include weights or credentials."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'results/v431-r3'


def read(p):
    return json.loads(Path(p).read_text())


def write(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = args.output or RUN / ('review-'+stamp)
    out.mkdir(exist_ok=False)
    revision = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    def copy(p, dest=None):
        p = Path(p)
        if not p.is_absolute(): p = ROOT/p
        assert p.is_file(), p
        assert p.suffix in ('.py','.json','.md','.csv','.yaml','.xml','.log'), p
        target = out/(dest or str(p.relative_to(ROOT)))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p,target)
    for p in sorted((ROOT/'docs').glob('v431_r3*.md')):
        copy(p)
    for p in ['docs/v431_r3_main_table.csv','docs/paper_v431_draft.md','docs/novelty_matrix.md',
              'docs/v431_r2_stop_audit.md','docs/v431_r2_financial_audit.md','configs/v431_r3/manifest.json',
              'scripts/run_v431_r3_queue.py','scripts/env_new_server.sh']:
        if p.endswith('.sh'):
            target=out/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/p,target)
        else: copy(p)
    for directory, pattern in [('src/introact_ts/v431_r3','*.py'),('scripts','v431_r3*.py'),('tests/v431_r3','*.py')]:
        for p in sorted((ROOT/directory).glob(pattern)): copy(p)
    for name in ['resolved_config.json','reference_manifest.json','terminal_manifest.json','models_frozen.json',
                 'terminal_freeze.json','label_provenance.json','learning_curve_manifest.json',
                 'queue_status.json','cpu_queue_status.json','fit_status.json','report_evidence.json',
                 'complete_cost_audit.json','support.json','check_support.json','new_combination_support.json',
                 'financial_support.json','common_table.json','common_financial_table.json',
                 'pilot_first_report.json','delivery_status.json']:
        # The full per-label provenance remains on the server; export only examples below.
        if name == 'label_provenance.json': continue
        copy(RUN/name, 'evidence/'+name)
    copy(RUN/'producer-reference/v431_r3_fit.py','producer-reference/v431_r3_fit.py')
    for name in ('response-tests.log','response-tests-first-failed.log','response-tests.xml','current-loss-independent.log'):
        copy(ROOT/'logs/v431-r3'/name,'logs/'+name)
    for p in sorted((RUN/'verification').glob('*/report.json')):
        d=read(p)
        # Reports can contain many low-level pair records; export their overview and original SHA.
        compact={k:v for k,v in d.items() if not isinstance(v,list) or len(v)<=25}
        compact['server_report_path']=str(p.relative_to(ROOT));compact['server_report_sha256']=sha(p)
        write(out/'verification'/p.parent.name/'report_summary.json',compact)
    for p in (RUN/'verification').glob('scale_scope_*.json'): copy(p,'verification/'+p.name)
    pair=read(RUN/'paired_comparisons.json')
    for x in pair['comparisons']:
        for k in ('mase_difference','mae_difference','seconds_difference','tool_count_difference'):
            if isinstance(x.get(k),dict): x[k].pop('source_block_layout',None)
        x.get('support',{}).pop('common_episode_uids',None)
    write(out/'evidence/paired_comparisons_compact.json',pair)
    stats=read(RUN/'statistics.json')
    for suite in stats['suites'].values():
        for x in suite.get('sign_and_ranking_diagnostics',[]):
            x.pop('per_episode_ranking',None)
            x.get('historical_argmax_oracle_selection_regret',{}).pop('source_block_layout',None)
    write(out/'evidence/statistics_compact.json',stats)
    curves=read(RUN/'learning_curves.json')
    write(out/'evidence/learning_curves_compact.json',[
        {k:v for k,v in x.items() if k not in ('check_episodes','fit_parent_ids','gate_parent_ids','check_parent_ids')}
        for x in curves])
    pilot_uid='c61b47da8ff0149ac27a3c20074ebe0b6734c83e32454ec3be11dfceb5761c7d'
    examples={}
    for session in sorted((RUN/'probes/main/sessions').iterdir()):
        records=session/'records.json'
        if not records.exists():continue
        for row in read(records):
            if row['base_uid']==pilot_uid and row['spec']['name'] in ('long','short') and row['status']=='completed':
                examples.setdefault((row['family'],row['spec']['name']),row)
    assert len(examples)==4
    write(out/'examples/four_paired_measurements.json',list(examples.values()))
    for family in ('bolt','timesfm'):
        d=RUN/('online-'+family)
        rows=read(d/'decisions.json')
        selected=[x for x in rows if x['case_id'] in ('natural-0','natural-3','natural-6','complete-raw','budget-zero','failed-after-real-long')]
        write(out/f'examples/{family}_natural_and_controlled.json',selected)
        with np.load(d/'live_arrays.npz',allow_pickle=False) as f:
            arrays={k:f[k] for k in f.files if any(k.startswith(x['case_id']+'_') for x in selected)}
        np.savez_compressed(out/f'examples/{family}_actual_final_arrays.npz',**arrays)
        for name in ('protocol.json','process_accounting.json','visibility_barrier.json','status.json'):
            copy(d/name,f'evidence/online-{family}/'+name)
        for name in ('model_manifest.json','code_manifest.json','service_startup.json'):
            copy(d/'service'/name,f'evidence/online-{family}/service/'+name)
    commands={'environment':'source scripts/env_new_server.sh','gpu_jobs':read(RUN/'queue_status.json')['jobs'],
              'cpu_jobs':read(RUN/'cpu_queue_status.json')['jobs'],
              'online_commands':[[str(ROOT/'scripts/v431_r3_online.py'),'--family',f] for f in ('bolt','timesfm')],
              'report_command':'"$W2_CORE_PY" scripts/v431_r3_report.py',
              'statistics_command':'"$W2_CORE_PY" scripts/v431_r3_statistics.py',
              'interpretation':'All computations executed on this server; GPU sequential under project lock.'}
    write(out/'actual_commands.json',commands)
    write(out/'commit.json',{'commit':revision,'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
                            'created_at':datetime.now(timezone.utc).isoformat(),'excluded':['weights','credentials','joblib models','full datasets','other projects']})
    (out/'README.md').write_text('IntroAct-TS v4.3.1-r3 精简审阅包\n\n先读 docs/v431_r3_report.md、主表、novelty_matrix 与 verification；源码和少量实际历史/在线数组用于追溯。模型权重、完整数据及拟合joblib不打包；服务器原缓存和环境仍保留，可按实际命令复核。候选已冻结，研究未晋升；整体TRAIN尺度、金融自然缺口/历史vintage、主动效果及成本失败见报告。\n')
    hashes={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    write(out/'files.sha256.json',hashes)
    archive=out.with_suffix('.tar.gz')
    with tarfile.open(archive,'w:gz') as f: f.add(out,arcname=out.name)
    record={'path':str(archive),'sha256':sha(archive),'bytes':archive.stat().st_size,
            'files':len(hashes)+1,'commit':revision,'directory':str(out)}
    write(RUN/'review_package.json',record)
    print(json.dumps(record,ensure_ascii=False))


if __name__=='__main__':main()
