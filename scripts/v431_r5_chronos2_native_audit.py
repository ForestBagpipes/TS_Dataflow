#!/usr/bin/env python3
"""Post-completion native-only evaluation; sealed labels are never opened."""
import json,time
from collections import defaultdict
from pathlib import Path
import numpy as np
from introact_ts.v43.schemas import array_hash
from introact_ts.v431_r4.trajectory_dataset import group_weights
from v431_r5_chronos2_native_check import OUT,OLD,REG,REVISION,WEIGHT_SHA,sha,write


def aggregate(rows):
    w=group_weights([r['parent'] for r in rows],[r['source'] for r in rows])
    return dict(parents=len({r['parent'] for r in rows}),variants=len(rows),
        **{k:float(np.dot(w,[r[k] for r in rows])) for k in ('mase','mae','component_seconds')},
        over_low=sum(r['component_seconds']>.8140623268639832 for r in rows),
        over_high=sum(r['component_seconds']>3.5 for r in rows))


def main():
    target=OUT/'audit'
    if (target/'status.json').exists() and json.loads((target/'status.json').read_text()).get('status')=='completed':
        raise RuntimeError('Preserve first completed native audit')
    started=time.perf_counter();status={}
    for suite in ('train','dev'):
        p=OUT/suite/'status.json';status[suite]=json.loads(p.read_text()) if p.exists() else {'status':'not_started'}
    queuepath=OUT.parent/'chronos2-queue-status.json'
    queue=json.loads(queuepath.read_text()) if queuepath.exists() else {'jobs':[]}
    jobs={r['name']:r for r in queue['jobs']}
    queue_ready=all(jobs.get('chronos2-'+suite,{}).get('status')=='process_completed' and 'seconds' in jobs.get('chronos2-'+suite,{}) for suite in ('train','dev'))
    if any(r['status']!='completed' for r in status.values()) or not queue_ready:
        write(target/'status.json',dict(status='waiting_for_complete_predictions',runs=status,future_labels_read=False))
        Path('docs/v431_r5_chronos2_native_results.md').write_text('# Chronos-2原生KEEP独立结果\n\nTRAIN/DEV原始预测尚未全部完成，后置评估未读未来标签。\n\n'+
            '\n'.join(f"- {k}：{v['status']}。" for k,v in status.items())+
            '\n\n也需等待外层队列完成并保存完整子进程计时。不将下载、输入准备或部分接口运行当作r5在Chronos-2上有效；不将其称第三独立家族。\n')
        return
    checked=[];runs={};predictions={};qlevels=json.loads((REG/'config.json').read_text())['chronos_config']['quantiles'];qindex=qlevels.index(.5)
    for suite in ('train','dev'):
        root=OUT/suite;st=status[suite]
        assert sha(root/'predictions.npz')==st['prediction_sha256'] and sha(root/'records.json')==st['records_sha256']
        assert st['weight_sha256']==WEIGHT_SHA
        records=json.loads((root/'records.json').read_text());manifest=json.loads((OUT/(suite+'-manifest.json')).read_text())
        byuid={r['episode_uid']:r for r in manifest};assert len(records)==len(byuid)
        assert len(records)==(4 if suite=='train' else 156)
        assert len({r['parent'] for r in records})==(1 if suite=='train' else 26)
        with np.load(root/'predictions.npz',allow_pickle=False) as outputs,np.load(OUT/(suite+'-inputs.npz'),allow_pickle=False) as inputs:
            for r in records:
                u=r['episode_uid'];m=byuid[u];x=inputs[u];p=outputs[u];raw=outputs[u+'_quantiles']
                assert r['revision']==REVISION and r['cache_identity']==m['cache_identity']
                assert array_hash(x)==m['target_hash'] and array_hash(np.isfinite(x))==m['target_mask_hash']
                assert p.shape==(m['H'],) and raw.shape==(1,len(qlevels),m['H']) and np.isfinite(p).all()
                assert np.array_equal(p,raw[0,qindex]) and array_hash(p)==r['prediction_hash']
                assert str(p.dtype)==r['prediction_dtype']
                assert sha(r['raw_file'])==r['raw_file_sha256']
                with np.load(r['raw_file'],allow_pickle=False) as one:
                    assert np.array_equal(p,one['point']) and np.array_equal(raw,one['quantiles'])
                if suite=='dev':predictions[u]=p.copy()
                checked.append(dict(suite=suite,uid=u,point_hash=r['prediction_hash'],input_hash=m['target_hash'],native_median_exact=True))
        physical=[r for r in records if not r['cache_hit']]
        runs[suite]=dict(parents=len({r['parent'] for r in records}),variants=len(records),physical_requests=len(physical),
            reused_requests=sum(r['cache_hit'] for r in records),cold_load_seconds=st['cold_model_load_seconds'],
            runner_body_seconds=st['full_process_seconds'],full_subprocess_seconds=jobs['chronos2-'+suite]['seconds'],
            actual_physical_native_seconds=sum(r['charged_native_seconds'] for r in physical),
            counterfactual_charged_native_seconds=sum(r['charged_native_seconds'] for r in records),
            physical_native_mean=float(np.mean([r['charged_native_seconds'] for r in physical])),
            physical_native_p95=float(np.quantile([r['charged_native_seconds'] for r in physical],.95)),
            physical_native_max=max(r['charged_native_seconds'] for r in physical),peak_gpu_bytes=st['peak_gpu_bytes'])
    # All raw predictions and their identities are verified above. Only now may
    # this separate evaluator access previously used DEV target observations.
    meta=json.loads((OLD/'episode_manifest.json').read_text());scales=json.loads((OLD/'mase_scales.json').read_text())
    records=json.loads((OUT/'dev/records.json').read_text());rows=[]
    with np.load(OLD/'targets.npz',allow_pickle=False) as labels:
        for r in records:
            u=r['episode_uid'];m=meta[u];assert m['split']=='dev'
            y=labels[u+'_values'];mask=labels[u+'_mask'].astype(bool)
            assert y.shape==mask.shape==predictions[u].shape and mask.any() and np.isfinite(y[mask]).all()
            scale=float(scales[m['source']]);assert np.isfinite(scale) and scale>0
            mae=float(np.abs(predictions[u][mask]-y[mask]).mean())
            rows.append(dict(uid=u,parent=m['parent_group'],source=m['source'],horizon=m['horizon'],condition=m['condition'],
                model='chronos-2',policy='Native KEEP',mae=mae,mase=mae/scale,report_scale=scale,
                component_seconds=r['charged_native_seconds'],prediction_hash=r['prediction_hash'],
                score_mask_hash=array_hash(mask),score_support=int(mask.sum()),cache_hit=r['cache_hit']))
    allrows=list(rows);old=json.loads(Path('results/v431-r5/evaluation/dev/common_decisions.json').read_text())
    wanted={'FIXED_A0_NATIVE_high','R5_high'};table=[dict(model='chronos-2',policy='Native KEEP',**aggregate(rows))]
    ids={r['uid'] for r in rows}
    for family in ('bolt','timesfm'):
        for policy in wanted:
            rr=[r for r in old if r['family']==family and r['policy']==policy];assert {r['episode_uid'] for r in rr}==ids
            compact=[dict(uid=r['episode_uid'],parent=r['parent_group'],source=r['source'],mase=r['mase'],mae=r['mae'],component_seconds=r['total_seconds']) for r in rr]
            table.append(dict(model=family,policy=policy,**aggregate(compact)))
    sources={s:aggregate([r for r in rows if r['source']==s]) for s in sorted({r['source'] for r in rows})}
    download=json.loads((OUT/'download-status.json').read_text());write(target/'rows.json',rows);write(target/'table.json',table)
    write(target/'sources.json',sources);write(target/'prediction_checks.json',checked)
    write(target/'status.json',dict(status='completed',scope='old DEV backbone-only sensitivity, not r5 cross-backbone governance',
        runs=runs,download_seconds=download.get('elapsed_seconds'),download_bytes=download.get('bytes'),
        calibration_test_labels_read=False,old_dev_labels_read_only_after_predictions_verified=True,
        single_request_budget_scope='native model calls only; complete governance/controller request latency not benchmarked for Chronos-2',
        comparisons_cost_warning='Bolt/TimesFM baseline invoices include preparation; Chronos-2 native timing is separate and not claimed same whole-request budget',
        audit_seconds=time.perf_counter()-started,script_sha256=sha(__file__)))
    lines=['# Chronos-2原生KEEP独立敏感性结果','','旧DEV26 parent、156相关变体。Chronos-2仅执行Native KEEP，没有训练或运行r5治理策略；不是第三独立家族，不能把骨干提升归为治理收益。','',
       '| 骨干 | 方法 | MASE | 费用秒/窗* | >3.5秒 |','|---|---|---:|---:|---:|']
    for r in table:lines.append(f"| {r['model']} | {r['policy']} | {r['mase']:.6f} | {r['component_seconds']:.6f} | {r['over_high']} |")
    lines+=['','*Chronos-2列只计原生模型调用donor费用；Bolt/TimesFM列沿原完整组件invoice。口径不同，不能据此宣称完整请求同预算优势。','',
      '## 实际执行成本','',f"下载{download.get('bytes')}字节，耗时{download.get('elapsed_seconds',0):.3f}秒；未安装或升级环境。"]
    for suite,r in runs.items():lines.append(f"- {suite}：{r['parents']} parent/{r['variants']}变体；物理推断{r['physical_requests']}次、复用{r['reused_requests']}次。冷加载{r['cold_load_seconds']:.6f}秒，runner主体{r['runner_body_seconds']:.6f}秒（不含初始import），外层队列完整子进程{r['full_subprocess_seconds']:.6f}秒；物理native总{r['actual_physical_native_seconds']:.6f}秒；native均值/P95/最大{r['physical_native_mean']:.6f}/{r['physical_native_p95']:.6f}/{r['physical_native_max']:.6f}秒，峰值显存{r['peak_gpu_bytes']/2**30:.3f}GiB。")
    lines+=['','## 验证与限制','','160个原始预测均核验输入身份、输出dtype/hash、逐请求原始quantiles和原生中位点完全一致；全部预测落盘并验证后才读取已使用DEV目标。封存集合未读。','',
      '完整/NaN以及H96/H192的TRAIN接口验收仅1个parent4案例，不是广泛训练支持。完整单请求处理/输出/策略预算未针对Chronos-2完整验收；DEV去重后的批处理进程平均不替代热请求延迟保证。','',
      '该结果仅是冻结新骨干的原生KEEP敏感性对照。没有Chronos-2治理候选共同表，也没有r5在该骨干上的收益主张。']
    Path('docs/v431_r5_chronos2_native_results.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(status='completed',table=table,runs=runs)),flush=True)


if __name__=='__main__':main()
