#!/usr/bin/env python3
"""Summarize measured costs without adding overlapping wall/component ledgers."""
import hashlib
import json
from pathlib import Path
import numpy as np


def main():
    root=Path('results/v431-r4');sources={}
    def read(p):
        p=Path(p);sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();return json.loads(p.read_text())
    queue=read(root/'cpu_queue_status.json');fit=read(root/'fit/models_frozen.json')
    cpu=dict(joint_search_process_seconds=next(j['seconds'] for j in queue['jobs'] if j['name']=='fit'),
        joint_search_internal_seconds=fit['elapsed_seconds'],
        original_r4_evaluation_process_seconds=sum(j['seconds'] for j in queue['jobs'] if j['name']!='fit'),
        legacy_terminal_retrain_internal_seconds=read(root/'legacy/status.json')['seconds'],
        legacy_acquisition_finalize_internal_seconds=read(root/'legacy-final/execution.json')['seconds'],
        final_trajectory_preparation_internal_seconds={s:read(root/'trajectory-final'/s/'status.json')['seconds'] for s in ('main','financial','generalization')},
        scope='Measured separate operations; internal timing is contained in parent process, never added twice; incomplete total development CPU')
    online={}
    for family in ('bolt','timesfm'):
        p=root/('online-'+family+'-r1');a=read(p/'process_accounting.json');rows=read(p/'decisions.json');startup=read(p/'service/service_startup.json')
        assert a['status']=='completed'
        assert abs(a['process_wall_seconds']-a['hot_request_seconds']-a['model_startup_seconds']-a['remaining_overhead_seconds'])<1e-8
        subsets={}
        for suite in ('main','financial'):
            r=[x for x in rows if not x['controlled'] and x['suite']==suite];t=np.array([x['hot_request_seconds'] for x in r])
            subsets[suite]=dict(requests=len(r),parents=len({x['parent_group'] for x in r}),
                hot_sum_seconds=float(t.sum()),hot_mean_seconds=float(t.mean()),hot_p95_seconds=float(np.quantile(t,.95)),
                hot_max_seconds=float(t.max()),high_budget_overruns=sum(x['budget_overrun'] for x in r),
                probe_calls=sum(x['actual_tool_calls'] for x in r),acquisition_decisions=sum(x['branch'] is not None for x in r))
        online[family]=dict(process_wall_seconds=a['process_wall_seconds'],all_22_hot_seconds=a['hot_request_seconds'],
            model_startup_wall_seconds=a['model_startup_seconds'],explicit_model_load_seconds=sum(r['load_seconds'] for r in startup),
            startup_detail=startup,remaining_process_seconds=a['remaining_overhead_seconds'],natural_subsets=subsets,
            controlled_hot_seconds=sum(r['hot_request_seconds'] for r in rows if r['controlled']),
            scope='One resident family, 19 natural plus 3 controlled; initializations and process overhead not hidden in hot; do not add subset sums to all_22')
    failed=read(root/'online-bolt/process_accounting.json')
    online['preserved_first_failure']=dict(process_wall_seconds=failed['process_wall_seconds'],exit_code=failed['exit_code'],
        reason='outer GPU queue held same gpu.lock as inner nonblocking model service',model_load_completed=False)
    historical=read('results/v431-r3/queue_status.json')
    jobs=historical['jobs'];probes=[j for j in jobs if j['name'] not in ('check-current-bolt','check-current-timesfm')]
    checks=[j for j in jobs if j['name'] in ('check-current-bolt','check-current-timesfm')]
    native=read(root/'baseline_audit/hot_costs.json');distinct={k:v for k,v in native['charges'].items() if k.startswith(('probe-candidates:','probe-forecast:'))}
    historical_cost=dict(r3_probe_generation_process_seconds=sum(j['complete_process_seconds'] for j in probes),
        r3_check_current_generation_process_seconds=sum(j['complete_process_seconds'] for j in checks),
        jobs=[dict(name=j['name'],seconds=j['complete_process_seconds'],log=j['log'],status=j['status']) for j in jobs],
        distinct_priced_probe_payload_keys=len(distinct),
        distinct_priced_probe_payload_seconds=sum(v['original_seconds'] for v in distinct.values()),
        scope='Historical r3 actual sequential process walls include pilot plus incremental maximum and financial; payload prices deduplicated by canonical charge key but are counterfactual-priced, not another physical wall total',
        this_round_probe_prediction_reexecution=0,older_v43_v431_r2_generation='Not exhaustively totalled; retained original ledgers remain chargeable, not zero')
    tato={}
    for suite,base,tf in [('main',Path('results/v431/20260914-sprint'),'timesfm_tato'),
        ('financial',Path('results/v431-r2/financial-observation-index-r1'),'timesfm-tato')]:
        for family,folder in [('bolt','tato'),('timesfm',tf)]:
            p=base/folder;s=read(p/'status.json');r=read(p/'decisions.json')
            tato[suite+':'+family]=dict(process_seconds=s['total_wall_seconds'],model_load_seconds=s['model_load_seconds'],
                actual_model_calls=s['actual_model_calls'],request_records=len(r),trial_records=sum(len(x['trials']) for x in r),
                failed_trials=sum(t['status']!='completed' for x in r for t in x['trials']),
                scope='historical 8-trial native adaptation; search/final prediction/model load included; not official full reproduction; do not add load again')
    out=dict(status='completed',cpu=cpu,online=online,historical_probes=historical_cost,tato=tato,sources=sources,
        limitations=['No complete lifetime experiment total: older v43/r2 generation, uninstrumented analysis and checks not exhaustively attributed.',
          'The 68.936773 seconds cold-sidecar physical load scan is historical overlapping evidence, not current CPU or new runtime.',
          'Hot timings from 7 main and 12 financial natural requests are small repeated-DEV engineering samples, not tail-latency guarantees.'],
        no_new_predictions_or_labels_read=True,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (root/'cost_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    lines=['# r4 实测费用分类汇总','', '本表只汇总已经发生的日志与费用账本，没有重跑GPU或读取新标签。完整源文件SHA见 `results/v431-r4/cost_summary.json` 的 `sources`。费用类别有包含关系，不把进程总时长与其内部加载、推理重复相加。','',
      '| 本轮CPU工作 | 秒 | 口径 |','|---|---:|---|',
      f"| 联合策略及登记对照搜索 | {cpu['joint_search_process_seconds']:.6f} | 完整子进程；内部拟合 {cpu['joint_search_internal_seconds']:.6f} 已包含 |",
      f"| 首套TRAIN/DEV/check/acq/金融评估 | {cpu['original_r4_evaluation_process_seconds']:.6f} | CPU队列子进程合计 |",
      f"| 修复尺度后legacy终态重训 | {cpu['legacy_terminal_retrain_internal_seconds']:.6f} | 内部函数计时 |",
      f"| 冻结legacy终态后的获取监督及拟合 | {cpu['legacy_acquisition_finalize_internal_seconds']:.6f} | 内部函数计时 |",'',
      '最终trajectory准备内部秒：'+json.dumps(cpu['final_trajectory_preparation_internal_seconds'])+'。初次准备/兼容恢复、共同表汇总及未计时审计未计入上述数值，不将此局部汇总称为全部研发CPU成本。','',
      '| 本轮在线家族 | 完整进程秒 | startup墙钟秒 | 其中明确模型load秒 | 22请求hot秒 | 其余进程秒 |',
      '|---|---:|---:|---:|---:|---:|']
    for f in ('bolt','timesfm'):
        a=online[f];lines.append(f"| {f} | {a['process_wall_seconds']:.6f} | {a['model_startup_wall_seconds']:.6f} | {a['explicit_model_load_seconds']:.6f} | {a['all_22_hot_seconds']:.6f} | {a['remaining_process_seconds']:.6f} |")
    lines += ['', '| 自然请求 | n | hot均秒 | P95秒 | 最大秒 | 高预算超支 | 原子probe调用 |','|---|---:|---:|---:|---:|---:|---:|']
    for f in ('bolt','timesfm'):
        for s,a in online[f]['natural_subsets'].items():lines.append(f"| {f}/{s} | {a['requests']} | {a['hot_mean_seconds']:.6f} | {a['hot_p95_seconds']:.6f} | {a['hot_max_seconds']:.6f} | {a['high_budget_overruns']} | {a['probe_calls']} |")
    lines += ['',f"首Bolt锁冲突失败仍保留，完整失败进程 {failed['process_wall_seconds']:.6f} 秒；未完成模型load。以上22请求含19自然与3受控，受控强制故障不计方法收益。原子probe次数不是模型forward次数，实际forward由独立在线验证及service响应计数。自然请求只测有限样本，P95为描述性分位，不能当稳定SLA。",'',
      f"历史r3探针生成完整进程合计 **{historical_cost['r3_probe_generation_process_seconds']:.6f} 秒**；另外新位置current预测 **{historical_cost['r3_check_current_generation_process_seconds']:.6f} 秒**。六个探针任务包含pilot后增量最大账本及金融，未重复整个最大集合。本轮复用预测，新增离线探针生成0次，历史成本没有因此清零。",'',
      f"canonical去重的探针candidate/forecast收费key共 {len(distinct)}，原摊价合计 {historical_cost['distinct_priced_probe_payload_seconds']:.6f} 秒。该数属于counterfactual部署价（跨请求cache重计原推理），不是额外物理进程时间，不能加到上述生成进程合计；准备和score CPU不在此key小计。",'',
      '| 历史TATO适配 | 完整进程秒 | 其中load秒 | 实际模型调用 | trial失败/总数 |','|---|---:|---:|---:|---:|']
    for k,a in tato.items():lines.append(f"| {k} | {a['process_seconds']:.6f} | {a['model_load_seconds']:.6f} | {a['actual_model_calls']} | {a['failed_trials']}/{a['trial_records']} |")
    lines += ['', '以上TATO均为8trial原生空间短预算适配，不是官方完整复现。失败trial仍包含在实际搜索墙钟中；old预测缓存共享减少实验调用，并不使独立部署取证免费。官方完整baseline与旧v43/r2全部历史生成总费尚未穷尽归因，明确保留缺项。', '',
      '冷/热分类sidecar扫描到的历史显式load 68.936773秒跨多个旧账本，不能当本轮CPU、独立新增计算或完整训练成本。预算low/high维持0.8140623268639832/3.5秒，在线以自然请求真实hot判定：金融两家族high均0超支，Bolt主表首请求1次超支仍保留。', '',
      '复现：`source scripts/env_new_server.sh` 后执行 `$W2_CORE_PY scripts/v431_r4_cost_summary.py`；仅读已有JSON/日志，不调用模型。']
    Path('docs/v431_r4_cost_summary.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(status='completed',cpu=cpu,online={f:online[f]['natural_subsets'] for f in ('bolt','timesfm')},historical_probe_seconds=historical_cost['r3_probe_generation_process_seconds']),ensure_ascii=False))


if __name__=='__main__':main()
