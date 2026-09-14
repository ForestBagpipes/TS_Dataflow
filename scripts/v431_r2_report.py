#!/usr/bin/env python3
"""Joint r2 result, grouped comparisons, report and paper from immutable records."""
from collections import defaultdict
from datetime import datetime,timezone
import csv,hashlib,json
from pathlib import Path
import numpy as np

ROOT=Path('results/v431-r2');SPRINT=Path('results/v431/20260914-sprint')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')

def paired(rows,family,policy,reference):
    pairs={r['episode_uid']:r for r in rows if r['family']==family and r['policy']==reference}
    groups=defaultdict(list)
    for r in rows:
        if r['family']==family and r['policy']==policy:
            ref=pairs[r['episode_uid']];groups[r['source'],r['parent_group']].append((r['raw_start'],ref['mase']-r['mase']))
    assert len(groups)==26
    rng=np.random.default_rng(101);draw=np.zeros(2000);source_details={}
    for s in sorted({k[0] for k in groups}):
        values=sorted([(v[0][0],float(np.mean([z[1] for z in v]))) for (source,p),v in groups.items() if source==s])
        blocks=[values[i:i+2] for i in range(0,len(values),2)];numer=np.array([sum(v for _,v in b) for b in blocks]);denom=np.array([len(b) for b in blocks]);index=rng.integers(0,len(blocks),size=(2000,len(blocks)))
        draw+=(numer[index].sum(axis=1)/denom[index].sum(axis=1))/3
        source_details[s]=dict(parent_count=len(values),time_blocks=len(blocks),mean_gain=float(np.mean([v for _,v in values])))
    return dict(reference=reference,gain_mase=float(np.mean([d['mean_gain'] for d in source_details.values()])),interval_95=np.quantile(draw,[.025,.975]).tolist(),bootstrap_repeats=2000,seed=101,grouping='source-stratified adjacent-two-parent time blocks; all six variants stay grouped',sources=source_details,interpretation='exploratory repeatedly used DEV; one USTS block cannot estimate its sampling variation')

def main():
    assert (ROOT/'accounting_audit.json').exists()
    rows=read(ROOT/'accounted_decisions.json');table=read(ROOT/'accounted_table.json');manifest=read(ROOT/'terminal_manifest.json')
    for family,folder in [('bolt','tato'),('timesfm','timesfm_tato')]:
        for raw in read(SPRINT/folder/'scored_rows.json'):
            match=next(x for x in rows if x['family']==family and x['policy']=='KEEP' and x['episode_uid']==raw['episode_uid'])
            rows.append(dict(raw,family=family,policy='TATO_8_NATIVE_SPACE',raw_start=match['raw_start'],tool_count=8,budget_overrun=raw['budget_overrun']['high']))
        r=read(SPRINT/folder/'baseline_table.json')[0]
        table.append(dict(family=family,policy='TATO_8_NATIVE_SPACE',parents=r['parents'],episodes=r['episodes'],mase=r['mase'],mae=r['mae'],total_seconds=r['total_seconds'],tool_count=8,budget_overruns=r['budget_overruns']['high'],low_budget_overruns=r['budget_overruns']['low'],limitations='8 trials, observed-linear missing bridge, retrospective wall budget; not full official reproduction'))
    write(ROOT/'common_table.json',table)
    comparisons={}
    for f in ('bolt','timesfm'):
        comparisons[f]={}
        for p,ref in [('R2_AGENT_high','FIXED_REFERENCE'),('R2_AGENT_high','FIXED_ACQUIRE_CART_high'),('EXISTING_SAME_EVIDENCE_CART','FIXED_REFERENCE'),('FIXED_ACQUIRE_CART_high','FIXED_REFERENCE')]:comparisons[f][p+'__vs__'+ref]=paired(rows,f,p,ref)
    write(ROOT/'paired_comparisons.json',comparisons)
    grouped=defaultdict(list)
    for r in rows:grouped[r['family'],r['policy'],r['source'],r['horizon'],r['condition']].append(r)
    detail=[dict(family=k[0],policy=k[1],source=k[2],horizon=k[3],condition=k[4],parents=len({r['parent_group'] for r in rs}),mase=float(np.mean([r['mase'] for r in rs])),total_seconds=float(np.mean([r['total_seconds'] for r in rs]))) for k,rs in grouped.items()]
    write(ROOT/'metrics_by_source_horizon_condition.json',detail)
    display='| 模型 | 策略 | MASE ↓ | 秒/窗 | 工具/窗 | parent |\n|---|---|---:|---:|---:|---:|\n'
    for r in table:display+=f"| {r['family']} | {r['policy']} | {r['mase']:.6f} | {r['total_seconds']:.6f} | {r['tool_count']:.3f} | {r['parents']} |\n"
    Path('docs/v431_r2_main_table.md').write_text('# v4.3.1-r2 共同DEV主表\n\n原三来源、26独立parent、156相关变体；所有臂同origin/target/H96、H192/评分mask。MASE及秒数按source/parent宏平均。秒数是补全规划费用后的批量部署组件，冷在线另报。low=0.8140623268639832秒，high=3.5秒；TATO保留8trial原生能力，预算事后审计。\n\n'+display+'\n逐来源/跨度/条件配对表与区间：`results/v431-r2/metrics_by_source_horizon_condition.json`、`paired_comparisons.json`。金融观测索引附表使用新的目标事件索引/MASE分母，不能和本表横比。\n')
    with Path('docs/v431_r2_main_table.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['family','policy','parents','episodes','mase','mae','total_seconds','tool_count','budget_overruns'],extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(table)
    focus=['KEEP','FIXED_TSICL','FIXED_REFERENCE','EXISTING_SAME_EVIDENCE_CART','FIXED_ACQUIRE_CART_high','R2_AGENT_high','TATO_8_NATIVE_SPACE']
    core='| 模型 | 方法 | MASE ↓ | 批量秒/窗 |\n|---|---|---:|---:|\n'
    for r in table:
        if r['policy'] in focus:core+=f"| {r['family']} | {r['policy']} | {r['mase']:.6f} | {r['total_seconds']:.6f} |\n"
    curve='| 家族 | 拟合parent | 全证据检查MASE | 同子集固定参照 |\n|---|---:|---:|---:|\n'
    for r in read(ROOT/'learning_curves.json'):
        if r['state']=='both':curve+=f"| {r['family']} | {r['fit_parents']} | {r['mase']:.6f} | {r['reference_mase']:.6f} |\n"
    online={f:read(ROOT/('online-'+f)/'process_accounting.json') for f in ('bolt','timesfm') if (ROOT/('online-'+f)/'process_accounting.json').exists()}
    financial=ROOT/'financial-observation-index-r1';fin_table=read(financial/'common_financial_table.json') if (financial/'common_financial_table.json').exists() else []
    fin_text='金融附表尚在执行，未填预计数字。'
    if fin_table:
        fin_text='| 家族 | 方法 | 条件/范围 | MASE ↓ | 秒/窗 |\n|---|---|---|---:|---:|\n'
        for r in fin_table:fin_text+=f"| {r.get('family',r.get('backbone',''))} | {r['policy']} | {r.get('condition','全部')} | {r['mase']:.6f} | {r['total_seconds']:.6f} |\n"
    write(ROOT/'report_evidence.json',dict(created_at=datetime.now(timezone.utc).isoformat(),main_comparisons=len(table),main_parents=26,main_variants=156,financial_table_rows=len(fin_table),main_artifact_sha256={str(p):sha(p) for p in [ROOT/'models_frozen.json',ROOT/'terminal_manifest.json',ROOT/'accounted_decisions.json',ROOT/'common_table.json',ROOT/'paired_comparisons.json']},method_promoted=False,heldout_labels_read=0,online=online))
    report='''# v4.3.1-r2 执行报告

本轮完成证据状态一致的候选和两家族共同开发评估；没有方法晋升。PICS_joint_relabel保持历史incumbent，calibration/test封存。所有训练、推断、统计及测试均在当前服务器，复用三个环境与两家族权重，GPU顺序执行。原26个DEV parent永久保留已使用身份，不因换方法而重新称独立确认。

## STOP退步的代码事实

旧v431完整agent的STOP动作来自自身D2基础树，实际156/156与强制STOP的D2完全一致，MASE1.200158。与固定TSICL不同不构成违约：旧实现从未约定STOP总是TSICL。相对TSICL，26个候选/预测真正改变，3改善23恶化；主要错误来自Solar。例699489…的shared窗口进入cov_missing高/scale低叶5选KEEP，MASE4.868631，对应TSICL及CART2.727376。完整UID、特征、叶路径、candidate/prediction hash见[逐窗审计](v431_r2_stop_audit.md)。

旧获取标签没有正收益：history108条全零，mask106零2负且来自同一Solar parent；lambda=0。未发现无证据调用全证据模型、未取得工具填零当已知、旧terminal hash、隐藏cache结果影响STOP或费用二次扣罚。18个获取parent限制可分裂能力，但标签本身无正收益才是此次全STOP的直接证据，不能泛泛归因于26个DEV太少。

## 本轮实现与冻结

`v431_r2/policy.py:StatePolicy`为none/mask/history/both建立明确状态。none采用各家族75个训练parent独立选出的固定TSICL参照，完整有限target强制KEEP。mask/history/both各自只训练和读取其已取得列；支持量、全缺列剔除和有效性flag均属于当前已取得工具。原五臂只填NaN，ridge不支持显式回KEEP；没有预测后残差修正。

普通CART沿用depth3/minleaf96/实际叶至少16parent/seed101，不搜索新深度。旧同证据CART保持原T_fit54作为对照；r2取消本轮不需要的gate配置搜索，合并T_fit54与T_gate21为75拟合parent，T_check17和T_acq18不变。状态集合hash与模型落盘之后，才产生648条同冻结策略前后真实任务损失/完整成本差标签，三种分支mask/history/both，后者是两工具而非一次免费组合。lambda原0/公式规则仅在T_acq LOPO选择，两家族均选0。

完整分支预算沿用low/high，无根据DEV降阈值。获取器每叶16parent，18父组仍只能根叶；TimesFM选择有正平均价值的mask，不能声称已学得丰富的逐窗取证边界。所有固定取证CART与r2共享终态、特征、监督、候选、预算；区别只在获取决策。允许成本替代的任务误差容忍预登记为0 MASE，不事后放宽。

## 真实训练支持与学习曲线

ETTm1/Solar/USTS原train独立704跨度parent为59/44/7，共110，全部已用；64上限未截断任何来源。此前TimesFM train真实预测为0，本轮补齐相同110父组的任务和历史输出，没有拿DEV选固定ridge。75是训练分区复用而非新增原始数据；ETTh与ETTm同步/降采样、Crypto过短DEV等未当独立新支持混入。

固定T_check17的嵌套18/37/75曲线如下，check及acq从未入任何拟合子集，始终使用100%作主候选，没有按检查成绩选择比例。

'''+curve+'''
增加拟合支持改善两家族全证据检查损失，但Bolt仍未胜其固定参照；TimesFM有检查点估计改善。18/37阶段表现相同与实际叶支持有关。曲线不能证明继续加数据必然有效，更未解决获取训练仍18parent的问题。

## 原共同DEV效果与机制

'''+core+'''
Bolt r2全部STOP，与训练固定参照精确同预测1.157005；这是修复无证据策略退化的工程正确性，不是新增研究收益。TimesFM r2为1.069398，相对固定TSICL1.096135改善，但与修正后的固定mask CART完全相同。普通全证据CART1.069086还略优。因此没有证据支持主动获取超越同信息固定取证；其细微计时差不当作系统性成本优势。

相同窗口按source和相邻两个parent的时间块进行2000次配对bootstrap，所有六变体同组。详细点估计/区间：

'''+json.dumps(comparisons,ensure_ascii=False,indent=2)+'''

区间只为重复使用DEV的开发诊断，USTS只有一个parent/一个时间块，无法估计其独立抽样变异；两个模型家族也不是两份独立数据。没有确认性SOTA或显著性晋升。TATO沿用两家族8trial原生空间短预算适配，低预算超支和不支持trial均保留，不能称官方完整复现。

## 金融身份、完整观测与缺口

身份以作者固定CSV和原供应方为证据，本地train数值与作者float32处理语义逐元素匹配。Oil目标0是Europe Brent spot，USD/barrel；USTS目标0是FwdRate_Fitted_1Y/THREEFF0100.B，百分点，为Kim–Wright拟合远期利率而非成交价格。USTS常在下周发布并可能回改，作者快照缺历史vintage；金融结果均不声称严格PIT或预测时点原始版本可恢复。详见[金融审计](v431_r2_financial_audit.md)。

旧工作日网格的原生NaN没有可靠“应有观测缺失”分类，不能把节假日算丢失交易。独立financial-observation-index-r1附表只选择作者快照中全字段有记录的日期，保留原日期/原始行映射/原值，完全在旧train/dev原始边界内；这不是声称当日实际发布。两来源各1个DEV parent，H96/H192为未来96/192条记录事件，MASE为train事件序列lag5，新预处理协议和分母均明确登记，不能与旧B网格MASE横比。

未来记录存在模式由回顾性快照定义，仅evaluator持有future日期/原始行映射，不进入agent。完整有效观测子集上的五臂应全为KEEP同输入/预测，治理额外计算仍计费；受控删除只用于检验缺口处理，不能把该完整案例选择说成来源本身无缺口。无可靠自然缺口/休市分类数据时，自然缺口结果明确缺项；原始大幅变化保持不覆盖。

'''+fin_text+'''

金融两parent的DEV日期不重叠，TRAIN共同有限日期1242个，水平Pearson为−0.142379。Oil未来4行已见于旧pilot，USTS H192未来161行已见于旧DEV，不能称未访问或独立确认。小样本及拟合利率与商品报价口径差异限制外推。该附表是冻结策略迁移诊断，不是金融任务上独立重新开发或确认。金融8次mask为离线策略回放，尚非金融按需在线执行。40个跨家族完整观测输入和预测no-op检查通过。固定方法未执行预算门不表示预算内；完整超预算审计见金融目录budget_flag_audit.json，所有失败及低预算超支保留。

## 在线与完整成本

'''+json.dumps(online,ensure_ascii=False,indent=2)+'''

TimesFM自然7窗真实调用6次mask，Bolt自然7窗全STOP；另有完整raw STOP、B0拒取证、真实工具执行后故障回退，以及必要受控mask/both。受控调用不算自然策略收益。失败耗费及最终回退真实预测全部记录；B0仍需最终预测，明确超支，不声称硬wallclock零成本。

主表补计初始选择/适用性和旧CART推断的实测费用到accounted派生账本，原模型/标签/预测SHA不变。训练搜索、旧缓存生成、TimesFM新增3504唯一真实调用/5010请求577.032秒、在线模型启动/热请求/完整验证worker分别列账；缓存省重复实验时间，不抹掉已发生生成成本。在线冷启动分摊包含受控case，不能冒称natural-only冷延迟。

## 交付、限制和下一步

可执行入口：`v431_r2_predict.py`、`v431_r2_fit.py`、`v431_r2_online.py`、金融inputs/collect/score、独立verify、account和report。状态模型、标签、分区、逐窗输入/预测/特征、成本和原始失败保留在`results/v431-r2/`。只运行本轮相关测试；真实输出复核状态以verification和两online独立报告为准。精简审阅包包含实际命令、resolved config、支持清单、代码、少量原始轨迹和SHA，不含权重或凭据。

当前允许的主张：固定TSFM的缺口治理存在任务差异；证据状态和无证据固定参照可正确实现；TimesFM遮挡CART有开发点估计收益；自然在线取证已实际执行。不能声称主动决策优于同信息固定取证、完整无缺口输入获得预测提升、自然金融缺口已验证、严格PIT、TSFM训练适配或交易盈利。下一步必须针对证据分辨力与独立获取支持注册明确方案；本轮没有打开calibration/test寻找翻盘，也不晋升incumbent。
'''
    Path('docs/v431_r2_report.md').write_text(report)
    paper=Path('docs/paper_v431_draft.md');archive=Path('docs/paper_v431_draft_r1_archived.md')
    if not archive.exists():archive.write_bytes(paper.read_bytes())
    draft='''# IntroAct-TS: A Financial Data Governance Agent for Time Series Foundation Models

中文：面向时间序列基础模型的金融数据治理智能体

工作题目；v4.3.1-r2开发论证草稿。金融适用性仅受下列实际验证范围支持，尚未达到方法晋升或ICLR确认结论。

## 背景与研究问题

金融价格可以完全正确，真实跳变不能自动视为错误。完整有效观测应保留；当输入确有覆盖不足时，不同治理方案会改变固定TSFM利用的信息，较低修复误差并不必然转化为较低预测误差。本文研究在未来真值不可见、验证有成本时，如何选择治理动作与决定是否继续取证。备份是工程能力，不承担创新主张。目标不是交易策略、重新训练TSFM或普通预测器路由。

## 定义与方法

固定目标变量、原始context上界、H96/H192及backbone checkpoint。动作池包含KEEP、FFILL、单变量TSICL、多变量TSICL和context ridge；只有缺失位置允许治理，完整target直接KEEP。损失为共同future和mask上的来源宏平均MASE。样本权重先平衡source及独立parent，再分配给同parent变体；156变体不代表156独立样本。

状态s=(dirty统计z,已取得工具集合E,计算账单Γ,预算B)。无证据使用训练内选出的家族固定强参照。mask、history、both分别有一个固定普通CART：depth3、叶至少96行且16独立parent、seed101，不搜索深度。各状态只读取已取得列，已取得但不支持的证据显式回参照；没有用未取得结果的零填充构造伪证据。both声明为两个工具。

历史验证从当前dirty前缀X[:512−H]重新治理并预测X[512−H:512]，不裁切最终已治理输入或使用clean真值。遮挡验证仅遮住当前已观察值。终态集合π冻结后，在独立T_acq计算v(i,q)=L[i,π(s)]−L[i,π(s+e_q)]−λ(C_acquire−C_STOP)。两端使用同π和实际任务损失；费用含工具、最终治理/预测变化、共享计算去重。获取器depth2/每叶16parent，保持0/登记公式λ与原预算，一次获取决策；正净价值、适用且完整分支预算允许时调用，否则STOP。

部署顺序为诊断→固定参照→取证或STOP→按实际证据状态重选→只生成最终治理→真实TSFM预测→血缘及完整成本。失败工具保留耗费并显式回冻结参照；模型/标签身份不匹配不能静默换模型或填零。源代码与精确算法、冻结时间及在线日志见[r2报告](v431_r2_report.md)。

## 相关工作与拟议增量

输入变换搜索已有[TATO官方实现](https://github.com/thulab/TATO)；直接决策损失思想与[SPO Trees](https://proceedings.mlr.press/v119/elmachtoub20a.html)相关；保持参照与[SPIBB](https://arxiv.org/abs/1712.06924)、按需信息获取与[DIME](https://github.com/suinleelab/DIME)相关。本文不将这些模块本身作为原创，也不继承其理论保证。待检验增量是任务对应证据、状态一致治理及按部署价值取证；必须超越普通gating和固定同信息取证才能成立。

## 共同实验与实际结论

'''+core+'''
Bolt修正后全部STOP，等于固定参照，是工程正确性。TimesFM r2有开发收益但与固定mask CART同效果，主动取证额外贡献未成立。旧全证据CART更低点估计不能归为新机制。主表与论文同由`v431_r2_report.py`填入，配对区间按source和时间parent块统计，完整数据见[共同表](v431_r2_main_table.md)。

'''+curve+'''
18/37/75拟合parent使用同一17-parent检查集，另18获取parent保持隔离；100%预先指定，不据曲线选最优比例。支持增大改善检查误差，但获取树仍无法形成两个各16parent叶。数据支持和证据特征分辨力不能以大量相关变体替代。

## 金融条件与外推限制

本地Oil为Brent现货报价，USTS目标为Kim–Wright拟合一年后远期利率，不将二者泛称同一种成交价格。作者快照与本地train逐值一致，实际发布时间和历史修订无法完全恢复，不宣称严格PIT。自然NaN可能混合无记录/休市/不可用，尚无可靠自然缺口分类。

独立附表在既有原始split边界内，取保留真实日期及行映射的全字段有记录事件，H按观测事件而非原B日网格计；它是预登记完整案例子集及受控删除实验，重跑所有共同对照，不能与旧表横比，也不能代表自然金融缺口或全部原始数据。完整有效输入五臂应no-op，同预测不是治理提升。未来日期/存在模式只归evaluator，未进入agent。

'''+fin_text+'''

## 贡献与证据对应

| 拟议贡献 | 本轮证据 | 允许结论 |
|---|---|---|
| 无证据合理保留强参照 | STOP逐窗hash/预测一致 | 工程修正，不算方法有效性 |
| 证据改善治理选择 | TimesFM状态CART与强固定对照 | 有开发信号，重复DEV和小样本限制 |
| 主动获取胜固定流程 | 相同终态/监督/预算的固定取证与r2 | 当前相同效果，额外贡献未成立 |
| 更多支持带来改善 | 18/37/75对固定check | 检查误差下降，不证明数据越多必然越好 |
| 金融完整观测保护 | 独立完整案例五臂no-op | 保护已观测值，非预测收益 |
| 金融自然缺口有效 | 无已分类自然缺口集 | 缺项，不能替受控删除背书 |
| 在线可执行与全费用 | TimesFM自然6次工具，停止/预算/失败分支 | 实际执行；受控case不算策略成绩 |

## 当前边界

两家族使用同26个重复开发parent，USTS仅一个dev parent；金融新协议仅两parent、DEV日期不重叠但各自未来部分已用于旧pilot/DEV，不提供可靠普适或确认性主张。TATO仅8trial短预算适配，不称官方完整复现。未改善TSFM参数训练、文本大模型训练或交易利润。calibration/test继续封存；当前主张不足以宣称SOTA、方法晋升或录用。r1草稿和所有负结果另存原样历史档案。
'''
    paper.write_text(draft)
    print(json.dumps(dict(main_comparisons=len(table),financial_table_rows=len(fin_table),report='docs/v431_r2_report.md')),flush=True)

if __name__=='__main__':main()
