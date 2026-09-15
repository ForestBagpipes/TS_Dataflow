#!/usr/bin/env python3
"""Render the r4 report and paper from the same audited comparison table."""
import json
from pathlib import Path

ROOT = Path('results/v431-r4')
DOC = Path('docs')


def read(path):
    return json.loads(Path(path).read_text())


def table(suite, high_only=False):
    path = ROOT / 'evaluation' / suite / 'common_table.json'
    common = path.exists()
    if not common:
        path = path.with_name('table.json')
    rows = read(path)
    if isinstance(rows, dict):
        rows = rows.get('rows', rows.get('table', []))
    lines = ['| 家族 | 方法 | MASE ↓ | 常驻组件秒/窗 | 工具/窗 | parent/变体 | 超预算 |',
             '|---|---|---:|---:|---:|---:|---:|']
    for row in rows:
        if high_only and row['policy'].endswith('_low'):
            continue
        lines.append(f"| {row['family']} | {row['policy']} | {row['mase']:.6f} | "
                     f"{row['total_seconds']:.6f} | {row['tool_count']:.3f} | "
                     f"{row['parents']}/{row['episodes']} | {row['budget_overruns']} |")
    return '\n'.join(lines), common


def online_section():
    lines = ['## 真实在线验收与最终交付', '',
             '下列自然请求指冻结策略自行决定是否取证，不表示已核实自然缺口。每家族主表7个预选请求、金融12个请求，另3个受控案例。两家族按GPU队列串行，模型常驻；TimesFM清除跨请求预测缓存，保留请求内canonical去重。', '',
             '| 家族 | 自然请求 | 实际原子probe | STOP | 热请求均秒 | 最大秒 | 热超预算 | 模型启动秒 | 完整进程秒 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for family in ('bolt', 'timesfm'):
        path = ROOT / ('online-' + family + '-r1')
        if not (path / 'status.json').exists() or read(path / 'status.json')['status'] != 'completed':
            lines.append(f'\n{family}在线尚未完成；不填预计结果。')
            continue
        rows = read(path / 'decisions.json')
        natural = [r for r in rows if not r['controlled']]
        cost = read(path / 'process_accounting.json')
        hot = [r['hot_request_seconds'] for r in natural]
        lines.append(f"| {family} | {len(natural)} | {sum(r['actual_tool_calls'] for r in natural)} | "
                     f"{sum(r['branch'] is None for r in natural)} | {sum(hot)/len(hot):.6f} | "
                     f"{max(hot):.6f} | {sum(r['budget_overrun'] for r in natural)} | "
                     f"{cost['model_startup_seconds']:.6f} | {cost['process_wall_seconds']:.6f} |")
    lines.extend(['', '首次在线因父队列与子服务重复持有同一GPU锁，在加载前失败。保留原日志和源码，后续仅外层改独立队列锁，原GPU服务锁不改；同时准入和取证后的剩余预算扣除全部已发生墙钟时间。重试新目录online-bolt-r1/online-timesfm-r1均完成。', '',
                  'Bolt首次自然历史H探针约3.557446秒，最终请求3.688580秒，超出3.5秒；完整记录回退和总预算未满足，不删除首调用尾部。金融12请求每家族实际high均0超支，不能据此把旧low金融超支或未知自然缺口验证改成通过。两家族均覆盖受控完整KEEP、预算不足、实际probe后注入失败回退；受控结果不当作策略收益。', '',
                  '全部44个最终预测与各自所选动作对应缓存通过预登记数值容忍复核，不能说hash逐位一致：Bolt候选15/22、预测22/22逐位一致；TimesFM候选12/22、预测0/22逐位一致。TF仅保存dtype不同（在线float64、旧缓存float32），44个预测相对各自所选动作缓存的数值最大绝对差均为0；候选最大差约2.35e-13。模型身份、读取barrier与费用审计详见[v431_r4_online_verification.md](v431_r4_online_verification.md)。19个自然动作与离线JOINT_high一致数为Bolt18/19、TimesFM19/19；Bolt首次超时使原ridge改为预算回退A2，这是实际延迟触发的合法分支，不将其单窗收益当方法成绩，也不说自然部署动作全部等同账本主表。所有final落盘前禁止读取评价标签/隐藏证据，六类封存文件探测被拒绝、无意外访问；calibration/test未读。', '',
                  '[完整费用分类](v431_r4_cost_summary.md)保留各原始SHA：本轮联合CPU搜索进程50.929471秒、legacy终态5.213832秒、获取监督拟合3.046058秒；历史r3探针6job完整进程1574.471400秒仍保留，不因本轮复用清零。这不是穷尽全部历史研发费用。模型加载、历史离线推断、TRAIN搜索、部署治理及最终预测分别保留。完整进程包含受控测试与启动/退出，不把其摊销值冒充热请求。probe数不是TSFM forward数，实际原始调用见service响应与验收。', '',
                  '精简审阅包发布到artifacts/reviews/v431-r4-review.tar.gz，包含源代码、配置、角色/支持、原始配对预测样例、失败/成本及自然轨迹；身份见同目录JSON。它绑定代码提交，随后发布包的提交不改变该代码身份。经检查以codex-save-local推送当前codex分支；Windows同步以实际登录与本机快进状态为准，服务器不能宣称已观察到F盘落盘。'])
    return '\n'.join(lines)


def main():
    dev, common = table('dev')
    financial, financial_common = table('financial')
    main_table = f'''# v4.3.1-r4 共同开发结果

共同 DEV 为旧的26个 parent、156个相关变体、3个来源。按 source→parent→variant 逐层等权，外层 MASE 分母与旧表一致。该集合多次用于开发，不是独立确认。学习尺度已改为每个 origin 可见输入尺度；原预测与 MAE 复用。

当前完整比较合并状态：DEV={common}，金融={financial_common}。False 表示仍仅新策略矩阵，不能称近期基线完整交付。信息不同的 R2、旧 r3、TATO 是完整方法对照，不是同信息消融。TATO 仅8 trial原生空间短预算适配，未完成官方全协议。Bolt low在TRAIN未找到覆盖所有窗口的可行固定流程，TRAIN_BEST_FIXED_FLOW明确为N/A，因此每套是107组，不能补零或删失败制造最佳流程。

low=0.8140623268639832秒，high=3.5秒。费用为原常驻组件账本加新决策费用；只有明确实测模型加载从热费移到冷费。R2部分旧mask/历史工具缺可单独归因的加载记录，保留原费用，属于保守未完全分离口径，不冒充严格hot-only。缓存不免费，失败费用不删除。自然单请求总墙钟见在线验收，不能用本表批量组件费用代替。

## 原共同 DEV

{dev}

## 金融观测事件附表

两个已核实金融 parent、12个变体，与旧开发数据部分重叠。此附表有自己的冻结观测事件协议，不能横比原共同 DEV 的绝对 MASE。Brent为现货报价，Kim–Wright为拟合远期利率；不是两个成交价格系列。

{financial}

完整逐窗原始记录在 results/v431-r4/evaluation/，条件、来源、跨度与描述性配对区间见 [统计审计](v431_r4_statistics.md)。完整分母保留超支、不支持及回退，机制子集不替换全表。
'''
    (DOC / 'v431_r4_main_table.md').write_text(main_table)
    frozen = read(ROOT / 'fit/models_frozen.json')
    report = f'''# v4.3.1-r4 执行报告

联合有限策略已实现、冻结并完成两家族原 DEV、TRAIN、旧 check/acq、金融和新位置回归评估。尚无方法晋升：Bolt高预算JOINT为1.154124，弱于同语法分阶段1.150787；TimesFM为1.069398，与仅免费特征相同，后者费用更低。两家族相对固定参照的90% source/parent时间块区间均跨零。按预登记停止本轮算法扩张，不启动第五轮特征，不打开calibration/test。

起点 a5d395cf9cd369941be51c6fbaf290971d3144b8。拟合冻结于 {frozen['completed_at']}，训练入口墙钟 {frozen['elapsed_seconds']:.3f} 秒；模型文件 SHA256 `{frozen['sha256']}`。这是有限CPU搜索时间，不包括历史预测、基线搜索、加载和新在线计算。实际执行命令与阶段用时见 results/v431-r4/cpu_queue_status.json。

## 实际改动与支持

新增 origin_scale、trajectory_dataset、branch_cost、joint_policy 四模块，沿用五臂、历史先截断再治理、ProbeSpec/Result、输入去重和观测保护。详见[真实函数映射](v431_r4_code_map.md)。没有预测后残差臂；context ridge在支持不足时显式回退Native，真实动作和费用保留。

修复整外层TRAIN尺度进入内部早期学习目标及历史汇总的问题：当前请求学习尺度仅dirty512点的有限季节差分对（至少16），不足依次lag1、MAD、固定下限；外层报告尺度另存。原始预测输入不变，故复用原始预测/MAE；不把学习标签修复误称新的模型推断。旧r3源码和结果保留，修复重训比较另列。

原TRAIN110个parent，fit54/gate21/check17/acq18；主工具有效支持51/20/16/16。多变体不增加parent。主联合策略只fit训练、gate选择免费二分及原lambda；旧acq仅回归。修复后的r3分阶段在原fit内35个parent拟合终态、19个拟合获取（有效18），并非用110个parent拟合获取器。

策略有限语法、fit内25/50/75分位阈值和每个可执行学习终叶至少16有效parent均保持。主JOINT与通用成本敏感联合树实质相同，合并为一方法，不能作为两项创新互相比胜。每家族实际拟合56个预登记配置。Bolt累计评分57108个分支、8720个证据二分；TimesFM为95022、8760；各392个免费二分候选。这些是DP实际评分次数，存在配置间重复，不冒充独立样本或唯一完整策略数；逐配置计数见冻结清单。

## 实际结果与归因

两家族高预算JOINT都选择固定H取证，再按 `long:covariate_coverage` 的训练阈值0.7548076923076923选择单变量TS-ICL或context ridge。完整输入直接KEEP，工具不适用或预算不足走明确回退。因此存在自然取证不等于学到了有增量的选择性取证。

Bolt JOINT和固定H的原DEV预测相同，MASE1.154124；相对固定参照差−0.002880，90%描述区间[−0.025061,0.019077]。同语法分阶段为1.150787，修复后DIRECT_control为1.146635，继承R2 CART为1.136486。TRAIN选定固定流程为1.154554，JOINT相对它的差−0.000430、区间[−0.011763,0.011953]。TimesFM JOINT、固定H、修复后CART_H、TRAIN最佳固定流程和仅免费特征均1.069398；相对参照差−0.026737，区间[−0.059739,0.003962]；仅免费特征约0.218154秒，JOINT约0.580257秒。继承R2 CART为1.069086，差异全部落在单一USTS parent，bootstrap退化不能解释成显著。不能把治理选择点估计归为主动验证收益。

合法动作、预算动作、完整冻结路径oracle及证据排序诊断已在TRAIN账本计算，均仅解释候选空间，不是部署成绩。inclusive路径库含固定五臂时可能平凡等价动作oracle，learned-only另列。完整路径包含证据及最终动作/预测费用。oracle仅在TRAIN诊断使用真实未来损失选择这些完整计费路径，不能部署；路径库仅含已执行T_fit的策略，不含未评估的legacy路径。Bolt low名义树中0parent终态不可执行，实际均走登记的预算回退，不能说它是学得有效叶；详见[冻结验收](v431_r4_verification.md)。原始统计见 results/v431-r4/statistics.json。

## 金融与费用

金融Bolt JOINT3.041944，仍弱于Native KEEP2.820959；不能只挑固定TS-ICL3.069683比较。TimesFM JOINT4.890237，与免费策略相同。完整target五臂相同输入/预测只说明no-op与观测保留。自然NaN缺日历、发布时间和历史vintage分类，不能声称自然缺口治理或严格point-in-time已验证。

金融旧TimesFM CART_H32与CART_H的12个动作、候选和预测hash逐窗相同。旧6/0超支差来自执行费用，首H32分片的明确模型加载被记入常驻调用。精确分离加载后旧H32约1.764402秒，H约0.980006秒，均0个high超支；其余开销保留。这是费用分类修复，不是方法收益。旧r3原表不回写。

当前账本high下JOINT在原DEV和金融均无超支；low金融Bolt10/12、TimesFM2/12超支，说明仅TRAIN成本估计不能保证金融时延尾部。最终预测仍计费，零取证不写成零费用。自然单请求与冷启动验收由在线日志单列，不能以账本无超支替代。

## 基线与主张边界

TATO两家族仅已有8trial原生空间适配；主DEV每家族1248trial，TimesFM546次原生长度不支持失败完整保留，未增加历史或改horizon救失败。官方500trial等配置/依赖差异见[基线协议](v431_r4_baseline_protocol.md)。TimesFM-3、Chronos-2只登记公开版本、许可和适配条件，未下载或运行，不算完成新家族。TimesFM-3模型许可含非商业/非生产限制，不能把代码Apache许可冒充权重许可。

当前可支持的是可运行的任务损失治理策略、可见状态隔离、成本与数据契约及负结果归因；尚不支持响应独有增量、选择性取证优势、金融有效性、SOTA或ICLR录用。单一USTS parent、反复DEV比较和两金融parent限制保留。PICS_joint_relabel保持历史incumbent。

## 交付入口与未完成

共同矩阵：[主表](v431_r4_main_table.md)。协议：[预登记](v431_r4_preregister.md)。统计：[描述性审计](v431_r4_statistics.md)。金融：[身份和费用](v431_r4_financial_audit.md)。代码：[函数依赖](v431_r4_code_map.md)。自然在线及费用见下节；审阅包身份与提交见artifacts/reviews/v431-r4-review.json，代码提交与后续发布包提交分别记录。

近期基线官方完整复现、更多独立金融支持、可验证自然缺口及独立确认仍未完成。确认集继续封存，后续优先完成独立评估协议与数据支持，而非基于本表追加特征寻找胜例。
'''
    (DOC / 'v431_r4_report.md').write_text(report + '\n' + online_section() + '\n')
    archive = DOC / 'paper_v431_draft_r3_archived.md'
    paper = DOC / 'paper_v431_draft.md'
    if not archive.exists():
        archive.write_bytes(paper.read_bytes())
    compact, _ = table('dev', True)
    paper.write_text('''# IntroAct-TS: A Task-Aware Data Governance Agent for Frozen Time Series Foundation Models

中文：面向冻结时间序列基础模型的任务感知数据治理智能体

v4.3.1-r4开发论文草稿。金融为重点应用，现有证据不支持金融领域有效性或SOTA。原r3论证及负结果保存在[旧稿](paper_v431_draft_r3_archived.md)。

## 背景与问题

冻结TSFM的输入可能存在观测覆盖缺口。治理改变模型可见信息，但修复误差下降不必然改善当前预测。真实跳变可以正确，完整有效输入允许KEEP。研究问题是在未来结果不可见且验证预算有限时，如何选择合法输入治理动作与必要的历史验证步骤。备份只提供恢复能力，不是方法创新。本工作不训练TSFM参数，不改变原目标变量或转向交易收益。

## 定义

请求包含当前可见512点输入及mask、合法协变量、H96/H192、固定模型revision和剩余预算。动作集为Native KEEP、FFILL、单变量TS-ICL、多变量TS-ICL、context ridge，有效观测不覆盖。工具H32、H、control按各历史origin先截断再生成候选，未得到的工具结果不是可见特征。训练监督为真实当前未来MAE除以当前origin可见尺度；部署状态不携带未来。报告使用另行冻结的外层TRAIN MASE尺度。路径费用包含取证、治理、最终预测、失败与决策，冷启动分开记录。

## 可运行方法

用source、parent、variant逐层配权的TRAIN最终任务损失和完整费用联合选择有限策略。语法最多一次免费特征二分，每支直接提交或调用一个预登记工具组合，取证后最多一次已得证据二分。每个可执行学习终叶至少16有效fit parent，阈值只来自fit分位点。gate只选免费二分与原lambda；平局低成本、少节点、固定参照。运行时decide只接受typed可见状态、实际证据和剩余预算，完整targetKEEP；预算不足、工具不支持/失败均明确回退。

该实现采用通用成本敏感有限策略搜索，不把通用联合树重命名为独有创新。原r3的κ/z响应作为负结果对照保留，不进入主候选。本文目前是有数据/费用审计的系统及经验性研究候选，尚非已证独有算法贡献。

## 实验与结果

同26个反复使用的DEV parent、156个相关变体，两家族独立TRAIN拟合，未宣称零样本迁移。外层MASE不变；变体不能当独立样本。高预算3.5秒，完整低预算表和条件/来源结果见[共同表](v431_r4_main_table.md)。成本为常驻组件实测归因，在线总墙钟另验。R2部分旧mask/history工具无法完全分离冷启动，保留保守原费，不称严格hot-only。

''' + compact + '''

联合策略未胜强简单方法：Bolt弱于分阶段同语法对照；TimesFM与仅免费特征同预测、但取证费用更高。两家族相对参照的描述性区间均跨零。r4与固定H同效，不支持选择性取证增量。不能把旧R2不同证据的CART当作同信息消融，也不能把未充分支持的旧获取器作为唯一强对照。

金融附表仅2个parent：Bolt JOINT3.041944弱于KEEP2.820959；TimesFM JOINT4.890237与免费策略同效。旧TimesFM H32/H相同预测但不同费用，由原始加载归因解释；修正费用分类不提供预测收益。自然缺口和历史vintage核实缺项，完整输入no-op不算预测改善。

## 相关工作与必要证据

TATO输入变换搜索、Task-oriented Imputation下游任务导向、CSDI条件插补、DIME/TNDP效用与成本敏感获取、ImputePilot以及嵌套上下文研究均需明确归因，见[创新矩阵](novelty_matrix.md)。普通cost-sensitive策略是必要对照，与本实现相同则合并。主动机制必须超过固定流程，响应测量必须超过通用分歧与等成本回测；目前这两项均未获支持。TATO只有两家族短预算适配，不是官方完整复现，不据此宣称SOTA。

## 限制与后续检验

单一USTS parent、反复DEV、小金融支持、相关变体、部分自然缺失原因未知及成本跨域尾部限制结论。TRAIN oracle仅诊断，不是在线策略分数；真实自然取证也只说明执行了分支。校准与test保持封存。按预登记停止扩展本轮算法，优先补齐强基线和独立评估协议；本稿不保证ICLR录用，不将工程正确性当方法成功。
''' + '\n' + online_section() + '\n')


if __name__ == '__main__':
    main()
