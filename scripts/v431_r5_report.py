#!/usr/bin/env python3
"""Render r5 delivery from completed ledgers, without fitting or model calls."""
import json
from pathlib import Path
import numpy as np

R=Path('results/v431-r5'); D=Path('docs')
def read(p):return json.loads(Path(p).read_text())
def table(rows,cols):
    return '| '+' | '.join(x[0] for x in cols)+' |\n| '+' | '.join('---' for _ in cols)+' |\n'+'\n'.join('| '+' | '.join(str(fn(r)) for _,fn in cols)+' |' for r in rows)+'\n'
def main():
    dev=read(R/'evaluation/dev/common_table.json'); fin=read(R/'evaluation/financial/common_table.json')
    mechanisms=read(R/'evaluation/dev/mechanism_table.json')
    manifest=read(R/'fit/manifest.json'); online=[]; accounting={}; failures=[]; pilot=[]
    for f in ('bolt','timesfm'):
        rows=read(R/f'online-{f}/decisions.json'); accounting[f]=read(R/f'online-{f}/process_accounting.json')
        for budget in ('low','high'):
            rs=[r for r in rows if not r['controlled'] and r['budget_name']==budget]
            seconds=[r['hot_request_seconds'] for r in rs]
            online.append(dict(family=f,budget=budget,n=len(rs),nonstop=sum(r['actual_versions']>1 for r in rs),
              mean=float(np.mean(seconds)),p95=float(np.quantile(seconds,.95)),maximum=max(seconds),
              overruns=sum(r['budget_overrun'] for r in rs),failures=sum(bool(r['failure']) for r in rs)))
        for r in rows:
            if r['pilot']:pilot.append(dict(family=f,parent=r['parent_group'],seconds=r['hot_request_seconds'],versions=r['actual_versions']))
            if r['budget_overrun'] or r['failure']:
                failures.append(dict(family=f,case=r['case_id'],controlled=r['controlled'],seconds=r['hot_request_seconds'],
                  budget=r['budget'],reason=r['controller']['reason'],failure=r['failure']))
    out=dict(online=online,process=accounting,failures=failures,pilot=pilot,
      fit_seconds=manifest['elapsed_seconds'],dev_evaluation_seconds=read(R/'evaluation/dev/status.json')['seconds'],
      financial_evaluation_seconds=read(R/'evaluation/financial/status.json')['seconds'],
      development_gate='failed',calibration_test='sealed',new_offline_model_predictions=0,
      historical_compute='retained original invoices; not made free by cache reuse')
    (R/'delivery_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    cols=[('家族',lambda r:r['family']),('方法',lambda r:r['policy']),('MASE ↓',lambda r:f"{r['mase']:.6f}"),
      ('账本秒/窗',lambda r:f"{r['total_seconds']:.6f}"),('超预算',lambda r:r['budget_overruns'])]
    selected=['FIXED_A0_NATIVE_high','FIXED_A2_SINGLE_high','TRAIN_BEST_FIXED_FLOW_high','LEGACY_DIRECT_control_high',
      'LEGACY_CART_H_high','R2_EXISTING_CART_high','R4_JOINT_high','R4_FREE_COVERAGE_high','R5_RAW_high','R5_SINGLE_high',
      'R5_high','FIXED_COUNT_2_high','FIXED_ORDER_3_high','TATO_NATIVE_8_high']
    t=table([r for r in dev if r['policy'] in selected],cols)
    ft=table([r for r in fin if r['policy'] in ['FIXED_A0_NATIVE_high','FIXED_A2_SINGLE_high','R4_FREE_COVERAGE_high','R5_high']],cols)
    mt=table(mechanisms,cols)
    ot=table(online,[('家族',lambda r:r['family']),('预算',lambda r:r['budget']),('请求/自然取证',lambda r:f"{r['n']}/{r['nonstop']}"),
      ('平均秒',lambda r:f"{r['mean']:.6f}"),('P95秒',lambda r:f"{r['p95']:.6f}"),('最大秒',lambda r:f"{r['maximum']:.6f}"),
      ('超支/失败',lambda r:f"{r['overruns']}/{r['failures']}")])
    report='''# v4.3.1-r5 实际交付报告

结论：候选实现与共同开发比较已完成，但未通过预登记主实验准入。不继续扩大r5配置搜索，calibration/test继续封存。Bolt主策略没有自然试运行增量；TimesFM主动策略弱于冻结强简单流程与免费策略。几何降低收益向量误差不等于改善最终预测。PICS_joint_relabel保持历史协议身份。

## 实际实现与代码归因

- `v431_r5/dataset.py`核验当前L512/H96、H192真实原生预测及输入/mask/模型/dtype身份。无输入变更，离线共同筛选复用原始预测和MAE；没有把历史probe冒充当前任务。
- `scoring.py`使用共享斜率与动作截距的轻量ridge、固定七响应、fit内标准化与向前purged参考交叉拟合。学习单位MAE/origin合法S，外层报告MASE分母独立保存。
- `geometry.py`实现单臂、成对和完整联合可行域；部署使用unknown未来mask的保守共同凸包。FW保留gap/迭代上限/超时，没有修改或融合预测。
- `controller.py:run`只接可见输入、已取得TrialResult、成本与预算；最多参考加两个版本，直接返回已经执行的预测。canonical复用只在付出治理费用并发现输入相同后发生。
- `scripts/v431_r5_online.py`真实模型逐版本执行；所有最终预测保存前屏蔽未来标签与未查询档案。完整输入KEEP，预算不足与试运行失败均显式记录。
- r4历史协变量覆盖可由当前mask与合法历史前缀直接计算：主账本768/816支持、48显式unsupported；支持记录与旧值完全一致。`R4_FREE_COVERAGE`保留原阈值直接读此免费值，取消为获取相同覆盖值而运行历史模型的费用，原r4结果不覆盖。

## 训练与合法空间

两家族均110登记TRAIN parent、26已用DEV parent；fit54parent/324变体、gate21parent。严格同来源向前完整区间隔离下，54个参考OOF块中35个过去支持不足16，走登记的TS-ICL回退；不能说这些参考均由足够支持学得。当前评分器1296动作对仍只有54个parent，历史评分器51parent。

每家族fit有222/324窗至少三个数值不同预测，source宏权重覆盖77.78%。高预算可行oracle相对参考空间Bolt0.195371、TimesFM0.140426，单位MAE/originS；已计真实路径组件及预留，仅诊断，不是部署成绩或外层MASE。空间存在不能证明当前证据可泛化利用。

## 共同DEV主表

同26parent/156相关变体，三个来源，旧DEV反复开发使用；3.5秒预算。组件账本保留原始计算费用并加本轮评分/求解，不能替代下文单请求墙钟。R2为不同信息完整方法，TATO为8trial短预算适配，非官方完整复现。两预算、固定五臂及全部方法详见共同主表。

'''+t+'''
## 固定查询轨迹的机制表

CURRENT四种评分保持完全相同查询轨迹和原始评分。FREE/HISTORY改变信息，HISTORY额外支付历史模型费；不能将其当同成本比较。完整输入保持KEEP。

'''+mt+'''
FULL−RAW的90%描述性source/parent时间块区间：Bolt −0.001197 [−0.003590,0]，TimesFM +0.000418 [+0.000128,+0.000926]。Bolt改善仅来自同一个ETTm1 parent的两个相关变体；TimesFM三个改变窗口都退步。固定轨迹至少三个不同预测的覆盖Bolt103窗/26parent、TimesFM102窗/25parent。收益向量平方误差分别5.130355→5.129511、1.212782→1.203550。该数学/评分性质不能升级为最终任务收益。

## 真实在线与完整费用

每家族44请求：3个TRAIN固定路径吞吐测量、38自然请求、3受控分支。自然取证不代表自然缺口。低预算0.8140623268639832秒，高预算3.5秒。

'''+ot+f'''
Bolt模型加载{accounting['bolt']['model_startup_seconds']:.6f}秒、完整进程{accounting['bolt']['process_wall_seconds']:.6f}秒；TimesFM加载{accounting['timesfm']['model_startup_seconds']:.6f}秒、进程{accounting['timesfm']['process_wall_seconds']:.6f}秒。首次TRAIN三版本分别{pilot[0]['seconds']:.6f}/{pilot[3]['seconds']:.6f}秒，只测吞吐，没有按其表现选方法。

拟合及gate冻结{manifest['elapsed_seconds']:.6f}秒，DEV账本评估{out['dev_evaluation_seconds']:.6f}秒、金融{out['financial_evaluation_seconds']:.6f}秒。离线预测新增0，复用了已发生计算且保留原发票；真实在线推断另记，不能写成总实验成本为零。冷启动、进程其他开销、训练与请求不得混算。

## 失败、超支与回退

Bolt自然低预算金融一例1.346169秒超支；TimesFM自然低预算一例1.049711秒，剩余时间不足使求解超时，保留前一次合法动作。高预算自然请求无超支。两个零预算受控请求仍付出真实最终预测费用并标预算未满足；两个取证后故障受控请求保留前一版本和已发生费用。不是所有请求都满足预算。

固定轨迹完整FW分别14/15次达到迭代上限，最大gap分别0.002538/0.004460，作为带余项近似解保留。数据准备首次因NumPy整数JSON序列化失败，修复仅存储后重跑，失败目录保留。全部最终在线预测与对应已执行版本数值一致；dtype/hash差异单独核验，不能靠名称匹配。

## 金融条件

'''+ft+'''
仅Brent Europe现货报价与Kim–Wright拟合远期利率两个parent、12相关变体，部分重叠旧DEV，非独立确认。Bolt原生KEEP明显强于r5；TimesFM微小差异不足支持金融泛化。完整观测、受控删除分别记录；可验证自然缺口仍缺项，日历、发布时间和历史vintage不足以宣称严格point-in-time。自然查询不是自然缺口验证，有效观测与真实跳变不覆盖。

## 基线、主实验准备与论文边界

已真实执行的近期对照仍是TATO两家族8trial适配。TimesFM旧1248trial中的546长度失败追溯至trimmer seq_l×32超过历史320/416，未删除失败或改称官方完整搜索。500训练实例/500trial场景级入口与8来源主矩阵已准备，完整官方运行未完成。已取得7来源元数据/文件；Weather以及独立区间重叠、缺口mask和许可核验以main-preparation最新状态为准，未将几何容量当真实样本。TimesFM-3、Chronos-2未执行，不能列为已击败对手。

当前支持：冻结TSFM治理的可执行、输入保护及费用审计；无需未来标签的联合收益可行域及近似投影误差关系；旧DEV上评分误差降低而动作选择可能恶化的经验负结果。不支持：联合约束预测优势、主动取证优势、金融泛化、独立确认、SOTA或录用保证。三角不等式、凸包、投影与FW为已有方法。

主实验准备继续，但r5方法实验准入失败，不能解封确认集挽救开发结果。下一步收口基线与未用来源/时间块协议，保持r5冻结，不增加特征或模型搜索。

提交和审阅包SHA见版本台账/交付清单；本文由实际账本生成，数字不依赖聊天转述。
'''
    audit=read(R/'statistics/online_audit.json')
    actual=[]
    for family,v in audit['families'].items():
        actual.extend(dict(family=family,**r) for r in v['actual_online_score_tables'])
    report+='\n## 在线真实返回的任务结果补表\n\n低预算真实费用改变TimesFM七条自然轨迹，不能拿离线主表代替。以下输出均在最终预测写盘后独立评分；主集合只是按元数据选择的7窗验收子集，不代表完整DEV。\n\n'+table(actual,[
      ('家族',lambda r:r['family']),('集合/预算/条件',lambda r:r['suite']+'/'+r['budget']+'/'+r['condition']),
      ('窗/parent',lambda r:str(r['episodes'])+'/'+str(r['parents'])),('实际MASE',lambda r:f"{r['mase']:.6f}"),
      ('KEEP',lambda r:f"{r['keep_mase']:.6f}"),('免费参照',lambda r:f"{r['reference_free_mase']:.6f}")])
    report+='\n两次自然超支的预测封装墙钟远大于原服务GPU runtime且load_seconds为0；进程/IPC/调度等剩余墙钟原因未进一步定位，不能归因模型冷启动或FW独自耗时。全部费用和超时保留。\n'
    (D/'v431_r5_report.md').write_text(report)
    old=D/'paper_v431_draft.md';archive=D/'paper_v431_draft_r4_archived.md'
    if not archive.exists():archive.write_bytes(old.read_bytes())
    paper='''# IntroAct-TS: A Task-Consistent Data Governance Agent for Time Series Foundation Models

中文：面向时间序列基础模型的任务一致数据治理智能体

v4.3.1-r5开发论文草稿；研究未晋升，以下结果仅已反复使用DEV。金融为重点应用，不具备金融泛化证据。r4原稿保留归档。

## 问题与方法

在有效观测不覆盖、未来不可见、模型冻结的条件下，为不完整输入选择可执行版本及值得运行的候选。五臂保持Native、FFILL、单变量/多变量TS-ICL、context ridge；完整输入直接KEEP。免费参考先执行当前L512、H96/H192任务，轻量收益评分器读取已付费预测响应，联合几何约束评分，预算控制器最多运行三个版本，最终直接提交其中一个原生预测。没有融合输出、预测后修正或骨干训练。

参考策略采用fit内parent隔离向前交叉拟合，监督为真实未来MAE差除以origin合法S，未来标签只在TRAIN监督/独立离线评估出现。部署未知评分mask时使用全部lead折点共同凸包，不偷读未来非空位置。求解器记录FW gap与时间限制，失败保留上一次有效决策并支付费用。

对真实同任务收益向量g，精确欧氏投影保证整体向量平方误差不增；近似解有2gap余项。该性质不保证逐坐标改善、排序或最终MASE改善。当前实验恰好显示评分误差下降仍可能选择更差动作。

## 实验

'''+t+'\n固定同查询机制：\n\n'+mt+'''
旧DEV26parent/156变体，不能当156个独立样本。R2信息不同；TATO8trial不等完整复现。主候选TimesFM弱于冻结TRAIN强简单流程；Bolt等免费参考。联合约束和主动调用贡献均未成立，主实验准入失败。金融仅2parent，Bolt KEEP比治理强；自然缺口缺项。确认集封存。

## 与已有研究的关系及局限

TATO、Task-oriented Time Series Imputation和TS-ICL已研究任务导向输入治理；Forecast with Forecasts等已使用预测输出信息；DIME、Amortized Bayesian Experimental Design for Decision-Making、Loss-Conditioned State Execution涉及决策证据与计算选择。凸投影、损失向量几何及Frank-Wolfe不是本文发明。文献逐项来源与边界见v431_r5_literature.md和novelty_matrix.md。

本轮新测量/约束的可实现性已验证，独有预测增量待验证且当前DEV不支持。不能将工程正确性、oracle空间、自然调用或评分误差性质包装为SOTA。不宣称零样本跨家族迁移、金融point-in-time或TSFM适配训练收益。
'''
    old.write_text(paper)
    print(json.dumps(dict(status='rendered',report=str(D/'v431_r5_report.md'),summary=str(R/'delivery_summary.json'))))
if __name__=='__main__':main()
