#!/usr/bin/env python3
"""One source for the complete development table, sprint report and paper rows."""
from collections import defaultdict
from datetime import datetime,timezone
import csv,json,hashlib
from pathlib import Path
import joblib
import numpy as np

ROOT=Path('results/v431/20260914-sprint')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    manifest=read(ROOT/'terminal_manifest.json');models=joblib.load(ROOT/'models.joblib')
    accounted=(ROOT/'accounted_table.json').exists()
    table=read(ROOT/('accounted_table.json' if accounted else 'table.json'))
    decisions=read(ROOT/('accounted_decisions.json' if accounted else 'decisions.json'))
    for row in table:row.update(backbone='chronos-bolt-base',comparison_scope='shared_five_candidate_pool',cost_scope='measured_batch_components_plus_diagnostic' if accounted else 'measured_batch_components_diagnostic_pending')
    missing=[];baseline_audits={}
    for folder,backbone,policy in [('tato','chronos-bolt-base','TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR'),('timesfm','timesfm-2.5-200m','FIXED_FIVE'),('timesfm_tato','timesfm-2.5-200m','TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR')]:
        path=ROOT/folder/'baseline_table.json'
        if path.exists():
            extra=read(path)
            for row in extra:row['comparison_scope']='native_external_baseline' if 'tato' in folder else 'same_frozen_candidates_second_family'
            table+=extra
            scored=read(ROOT/folder/'scored_rows.json')
            if isinstance(scored,dict):scored=scored.get('rows',scored)
            if isinstance(scored,list):
                for r in scored:r['backbone']=backbone
                decisions+=scored
            baseline_audits[folder]=dict(table_sha256=sha(path),status=read(ROOT/folder/'status.json'))
        else:
            status=read(ROOT/folder/'status.json') if (ROOT/folder/'status.json').exists() else {'status':'pending'}
            missing.append(dict(backend=folder,backbone=backbone,policy=policy,status=status))
    (ROOT/'common_table.json').write_text(json.dumps(table,indent=2)+'\n')
    fields=['backbone','policy','mase','mae','total_seconds','mean_tools','task_harm','episodes','parents','status','budget_overruns','comparison_scope','cost_scope']
    with Path('docs/v431_main_table.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');writer.writeheader();writer.writerows(table)
    full='| Backbone / 策略 | MASE ↓ | 治理+最终预测秒数 | 工具均次 | parent |\n|---|---:|---:|---:|---:|\n'
    for r in table:full+=f"| {r['backbone']} / {r['policy']} | {r['mase']:.6f} | {r['total_seconds']:.4f} | {r.get('mean_tools',0):.2f} | {r['parents']} |\n"
    Path('docs/v431_main_table.md').write_text('# v4.3.1 共同开发主表（全部已完成比较臂）\n\n同26个dev parent/156变体；MASE为source×horizon×condition等权宏平均。秒数为批量测量/重计部署组件；完整冷启动与热请求单独列在冲刺报告。TATO为8trial适配，预算仅事后审计。\n\n'+full+'\n未完成项：'+json.dumps(missing,ensure_ascii=False)+'\n')
    lookup={r['policy']:r for r in table if r['backbone']=='chronos-bolt-base'}
    names=['FIXED_A0_NATIVE','FIXED_A2_SINGLE','OLD_DIRTY_HGB','OLD_LEARNED_HGB_COMMON_BUDGET','DIRTY_LOSS_TREE_D1','DIRTY_LOSS_TREE_D2','CART_target_horizon','FLAT_LOSS_TREE_target_horizon','ALL_'+manifest['selected'][0],'ALL_d2_target_horizon_unpruned','AGENT_'+manifest['selected'][0]+'_high','TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR']
    selected='| Chronos-Bolt共同策略 | MASE ↓ | 批量组件秒数 |\n|---|---:|---:|\n'
    for name in names:
        if name in lookup:
            r=lookup[name];selected+=f"| {name} | {r['mase']:.6f} | {r['total_seconds']:.4f} |\n"
    # Conditional source-parent bootstrap, preserving all six related variants.
    base=read(ROOT/'decisions.json');parents=defaultdict(lambda:defaultdict(list))
    reference={r['episode_uid']:r for r in base if r['policy']=='FIXED_A2_SINGLE'}
    switches={}
    for policy in sorted({r['policy'] for r in base}):
        groups=defaultdict(list);changed=improved=harmed=0
        for r in base:
            if r['policy']!=policy:continue
            ref=reference[r['episode_uid']];gain=ref['mase']-r['mase']
            changed+=r['arm']!=ref['arm'];improved+=gain>1e-12;harmed+=gain < -1e-12
            groups[r['source'],r['parent_group']].append([max(gain,0.),max(-gain,0.),gain])
        sources=defaultdict(list)
        for (source,_),values in groups.items():sources[source].append(np.mean(values,axis=0))
        aggregate=np.mean([np.mean(values,axis=0) for values in sources.values()],axis=0)
        switches[policy]=dict(reference='FIXED_A2_SINGLE',changed_variants=int(changed),improved_variants=int(improved),harmed_variants=int(harmed),source_parent_macro_gross_gain=float(aggregate[0]),source_parent_macro_wrong_switch_loss=float(aggregate[1]),source_parent_macro_net_gain=float(aggregate[2]),parents=len(groups),variants=156)
    (ROOT/'switch_mechanisms.json').write_text(json.dumps(switches,indent=2)+'\n')
    for r in base:parents[r['source'],r['parent_group']][r['policy']].append(r['mase'])
    compared=['FIXED_A2_SINGLE','CART_target_horizon','AGENT_'+manifest['selected'][0]+'_high','ALL_'+manifest['selected'][0]]
    rng=np.random.default_rng(101);draws=np.zeros((2000,len(compared)))
    for source in sorted({k[0] for k in parents}):
        values=np.array([[np.mean(v[n]) for n in compared] for (s,_),v in parents.items() if s==source])
        draws+=values[rng.integers(0,len(values),size=(2000,len(values)))].mean(axis=1)/3
    cis={}
    for k,name in enumerate(compared[1:],1):cis[name]=dict(reference='FIXED_A2_SINGLE',gain_mase=lookup['FIXED_A2_SINGLE']['mase']-lookup[name]['mase'],conditional_95_interval=np.quantile(draws[:,0]-draws[:,k],[.025,.975]).tolist())
    (ROOT/'paired_intervals.json').write_text(json.dumps(dict(scope='exploratory_source_parent_bootstrap_not_confirmatory',repeats=2000,seed=101,comparisons=cis),indent=2)+'\n')
    cart_features={c:sorted(set(int(v) for v in tup[0].tree_.feature if v>=0)) for c,tup in models['cart'].items()}
    online=read(ROOT/'online-7/process_accounting.json') if (ROOT/'online-7/process_accounting.json').exists() else {'status':'pending'}
    verification={p.name:read(p) for p in (ROOT/'verifications').glob('*.json')}
    hashes={str(p):sha(p) for p in [ROOT/'terminal_manifest.json',ROOT/'models_frozen.json',ROOT/'value_labels.json',ROOT/'partition.json',Path('configs/v431/sprint_manifest.json'),ROOT/'common_table.json']}
    evidence=dict(created_at=datetime.now(timezone.utc).isoformat(),run=str(ROOT.resolve()),method_status='not_promoted',incumbent='PICS_joint_relabel',config_count=8,selected=manifest['selected'],budgets=manifest['budgets'],partition_counts=manifest['partition_counts'],table_rows=len(table),missing=missing,conditional_intervals=cis,cart_split_indices=cart_features,online=online,baseline_audits=baseline_audits,artifact_sha256=hashes,heldout_labels_read=0,promotion=False)
    Path('docs/v431_sprint_evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    (ROOT/'sprint_status.json').write_text(json.dumps(dict(status='development_delivery_complete' if not missing else 'development_delivery_partial_second_family_in_flight',updated_at=evidence['created_at'],method_status='not_promoted',report='docs/v431_sprint_report.md',completed_comparisons=len(table),missing=missing,heldout_labels_read=0,next_step='finish registered baseline verification; calibration/test remain sealed'),indent=2)+'\n')
    report='''# v4.3.1 当日并行冲刺交付

本轮交付的是完整可执行方法和真实共同开发表；新方法没有晋升。用户时区Asia/Shanghai，启动2026-09-14 23:28:17，截止24:00，T=1903秒。三线按文件归属并行推进，无等待H2显著性才启动的串行门。所有计算均在当前服务器，三个环境未重装，GPU始终按root统一队列串行；代理/Codex服务未更改。

## 共同结果

'''+selected+'''
完整表包含所有已完成策略，见[v431_main_table.md](v431_main_table.md)和机器可读[v431_main_table.csv](v431_main_table.csv)，由同一 `scripts/v431_report.py` 同时填入本报告和论文草稿。新旧方法在同一156变体/26父组重算；没有按成绩删来源。原五臂oracle仅作诊断，不进入方法排名。

新单步agent在dev全部STOP，MASE1.200158，落后于固定TS-ICL1.157005；主动获取贡献未成立。普通CART为1.136486，比当前新方法好，不能把普通gating能达到的收益写成我们证据层的独有突破。其实际两个分裂特征是dirty最长缺口比例（索引2）与已取得ridge伪块误差（拼接索引25），三个历史配置均未用历史特征，因而动作一致；它仍按预登记全部调用收费，没有看结果后削减预算来美化。

目标跨度证据也没有带来本轮核心增益：三种历史配置的d2剪枝策略均为1.191788，不剪枝目标跨度为1.184872，都未优于固定TS-ICL。H1选择空间仍存在；H2有普通遮挡gating的开发信号，但提出的任务树/细化没有额外优势；H3未成立。普通CART对固定TSICL的条件配对gain区间见机器证据，不能当作独立确认或ICLR/SOTA声明。

## 终态、获取与信息契约

固定五臂，dirty基础特征13项，不含候选输出、source名字、路径、真实缺陷类或future。按source原始时间拆54 T_fit/21 T_gate/17 T_check/18 T_acq，完整704跨度同组。8个预登记终态配置；基础depth1/2、每训练叶>=16独立parent、最多16训练切点，细化最多一层。独立gate至少8parent且经验90%分组收益下界>0保留；不剪枝两项消融原样报告。

T_gate选出d2_target_horizon_gated和d2_old32_gated后，先写terminal hash与模型JSON，再生成T_acq的432条工具值标签。两端均是同一个冻结pi，正/零/负值保留；完整分支费用差包括最终动作/预测改变和共享组件。每工具depth2回归树受18个parent限制不能拆为两个各16的叶，实际是根叶；lambda只在T_acq内部LOPO选择，两配置均选择0。没有为避免全STOP而放宽支持或改阈值。

准入用完整分支预估费用，非DeltaC，统一low=0.814062327秒、high=3.5秒，由T_fit/T_gate成本冻结。实际超支保留；固定全部证据和外部TATO为原生工具计划，超支作事后审计，不能称硬wall-clock保证。候选输出在当前策略决定后才生成和计费；旧HGB使用候选值特征，因此保留全池生成成本。

## 历史增量与来源审计

L512、extra_history0、H96/H192。新origin exclusive r=416/320，使用dirty前缀重新生成五臂，验证同一dirty中r之后已发生的32步或目标H步。没有裁切最终治理后的context、补读context之前或读clean。新增1,120次真实TSICL插补和5,536次Bolt预测，生成816 episode的两种新跨度证据；执行体389.808秒。两个新条件共享相同历史候选，部署费用分别计。

历史生产进程因复用SprintData曾打开已读train/dev标签档案，但这些标签未进入工具公式或worker，原始future新读取0，heldout0；这一点已单独记录，不能把该离线生产器称为完全不打开evaluator的部署入口。其实际源文件副本和SHA保存于history/producer_source。真正在线入口另用文件访问屏障封存9档案。所有时间/量纲/availability/原始预测已独立核对。

## 近期baseline与第二家族

TATO立即接入官方八类变换及原生流水线，未限制为我们五臂。缺失context采用显式observed-linear桥接，原生无桥接NaN失败保留；8trial在dirty内部r=L-H验证，最终future不进入优化。Bolt实际156窗、1,248成功trial、837次唯一真实预测，独立重放全部原始quantile、正逆变换和选择通过；MASE1.685227是短预算本地适配结果，不能称击败官方论文完整复现。低预算68/156超支，高预算0，费用已补计跨窗cache命中，不能把他窗先算出的预测当免费。

TimesFM是独立家族，模型与官方来源revision另冻结。当前完成范围由下方动态记录给出；未完成项不填预计数字，Chronos2不冒充第二家族。TimesFM原生NaN处理、patch32、不同trimmer支持和TATO失败trial全部单列。

'''+json.dumps(baseline_audits,ensure_ascii=False,indent=2)+'''

未完成或在途：
'''+json.dumps(missing,ensure_ascii=False,indent=2)+'''

## 成本与在线执行

训练搜索/开发评价记录12.418秒；历史离线执行体389.808秒；TATO/Bolt记录worker wall79.907秒。离线pipeline初始化与未包住的解释器导入不能伪装为已精确测得的完整进程时间。组件表按原实测治理/工具/预测计费，后续单次dirty诊断补计保留为派生账本，不覆盖原冻结记录；共享诊断同时加到STOP和获取，DeltaC和训练value严格不变。

7例完整新agent在线回放只读上下文，封存9个evaluator/候选/工具档案，最终预测全部写盘后解封复核。实际全部STOP，仍真实生成所选治理和最终TSFM输出；没有先免费生成全池。动作、轨迹、候选和预测7/7一致。热请求合计1.864326秒，模型服务启动8.703547秒，其余初始化与退出1.968878秒；完整进程12.536751秒，平均1.790964秒，热/冷均无本次观察超支。此回放没有触发在线取证分支，不把离线证据生成称为agent实际在线取证。

## 通过、失败与冻结状态

22项本轮触及的语义测试通过，未机械重跑旧58项。历史6,656原始输出及主表6,708决策/2,768当前原始预测、8终态hash、2获取器与432条价值标签、LOPO隔离独立复核通过。首次history测试夹具availability少一列导致失败，修正夹具后通过；verifier先后漏识别新增计时key的失败保留，未改模型输出或填零。

源码实现和开发配置已冻结可复运行；不满足方法晋升和独立确认条件，calibration/test继续封存。只证明当前受控缺失治理协议，不证明真实valid-event识别、TSFM参数适配或文本LLM训练改善。完整方法执行而无增益仍是本轮真实交付，PICS_joint_relabel保持历史incumbent。

入口：`scripts/v431_fit_evaluate.py`（拒覆盖冻结模型）、`scripts/v431_online.py`（重复需新output-name）、`scripts/v431_verify.py`、baseline worker/verify、`scripts/v431_report.py`。全部逐窗值、原始预测、invoice、模型和训练manifest保留在 `results/v431/20260914-sprint`，大缓存与权重不进入Git。
'''
    Path('docs/v431_sprint_report.md').write_text(report)
    paper=Path('docs/paper_v431_draft.md');text=paper.read_text();begin='<!-- GENERATED_RESULTS_BEGIN -->';end='<!-- GENERATED_RESULTS_END -->'
    before,remaining=text.split(begin,1);_,after=remaining.split(end,1)
    generated=selected+'\n完整共同表： [v431_main_table.md](v431_main_table.md)。'+f" 当前已完成 {len(table)} 个模型/方法组合，缺项 {json.dumps(missing,ensure_ascii=False)}。"+'\n\n本轮结果否定当前完整新agent优于强固定/CART对照的主张。新agent全部STOP，不能宣称主动获取贡献。普通CART使用dirty缺口与ridge遮挡误差，历史跨度变化未产生增量；因此证据细化不是已证实的独有突破。TATO为显式NaN桥接+8trial适配，非官方完整复现；跨家族结论以完整共同表为限。\n\n条件source-parent bootstrap：'+json.dumps(cis,ensure_ascii=False)+'。区间未校正连续parent残余相关、配置多重比较；USTS一个dev parent，仅开发诊断。\n'
    paper.write_text(before+begin+'\n'+generated+'\n'+end+after)
    print(json.dumps(dict(table_rows=len(table),missing=len(missing),cost_accounted=accounted)),flush=True)

if __name__=='__main__':main()
