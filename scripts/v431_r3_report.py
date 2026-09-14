#!/usr/bin/env python3
"""One common result ledger drives r3 report, tables and the paper draft."""
from collections import defaultdict
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import numpy as np
from introact_ts.v43.data_io import file_hash
from v431_r3_fit import summarize

ROOT = Path('results/v431-r3')
R2 = Path('results/v431-r2')
SPRINT = Path('results/v431/20260914-sprint')
FIN = R2 / 'financial-observation-index-r1'


def read(p, default=None):
    return json.loads(Path(p).read_text()) if Path(p).exists() else default


def write(p, obj):
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def display(rows):
    s = '| 家族 | 方法 | MASE ↓ | 秒/窗 | 工具/窗 | parent | 超预算窗 |\n|---|---|---:|---:|---:|---:|---:|\n'
    for r in rows:
        s += f"| {r['family']} | {r['policy']} | {r['mase']:.6f} | {r['total_seconds']:.6f} | {r['tool_count']:.3f} | {r['parents']} | {r['budget_overruns']} |\n"
    return s


def attribution(paired):
    names = {'agent_vs_fixed_reference':'主动 vs 固定强参照',
             'agent_vs_frozen_fixed_acquisition':'主动 vs 同冻结固定获取',
             'agent_vs_random_feasible':'主动 vs 随机可行获取',
             'response_vs_no_kappa':'响应 vs 无κ',
             'response_vs_raw_forecast_dispersion':'响应 vs 旧原始预测分歧',
             'response_vs_equal_cost_ordinary_history':'响应 vs 双原点普通回测',
             'response_vs_same_evidence_CART':'响应 vs 同证据CART',
             'response_vs_same_capacity_direct_ridge':'响应 vs 同容量直接回归'}
    result = '| 家族 | 比较（高预算） | MASE收益↑ | 95%分组区间 | 共同parent/窗 | 范围 |\n|---|---|---:|---|---|---|\n'
    selected = []
    for r in paired.get('comparisons', []):
        if r['suite']!='main' or r['comparison'] not in names or not r['left'].endswith('_high'):
            continue
        m = r['mase_difference']; support = r['support']
        if m.get('mean') is None:
            gain, interval = '不支持', '不计算'
        else:
            gain = f"{-m['mean']:.6f}"
            ci = m.get('ci95')
            interval = f"[{ -ci[1]:.6f}, { -ci[0]:.6f}]" if ci else '未计算'
        result += f"| {r['family']} | {names[r['comparison']]} | {gain} | {interval} | {support['common_parents']}/{support['common_episodes']} | {r['scope']} |\n"
        selected.append(r)
    if not selected:
        return '配对统计尚未完成，不能先判模块有效。\n'
    return result+'\n收益为右侧参照减左侧方法。完整表与共同支持机制子集不可混为同一分母；重复DEV、小来源支持及单一时间块限制区间解释，均非独立确认。\n'


def curve_display(records):
    if not isinstance(records, list):
        return '学习曲线尚未完成。\n'
    result = '| 家族 | fit parent | 额外gate parent | 状态 | check MASE | check固定参照 |\n|---|---:|---:|---|---:|---:|\n'
    for r in records:
        result += f"| {r['family']} | {r['fit_parents']} | {r['gate_parents']} | {r['state']} | {r['mase']:.6f} | {r['reference_mase']:.6f} |\n"
    return result+'\n各比例共用独立17-parent检查集；额外21个gate parent参与alpha/参照选择，不能把13个fit parent称为全部监督仅13。100%始终为主模型，不据曲线选比例。\n'


def sign_display(statistics):
    result = '| 家族 | 状态 | parent/窗 | 历史符号一致率（含零） | 双方非零一致率 | 当前零收益/非参照比较 | 历史排序错误损失 |\n|---|---|---|---:|---:|---|---:|\n'
    for r in statistics.get('suites', {}).get('main', {}).get('sign_and_ranking_diagnostics', []):
        if r['state'] not in ('H32','H','control'):
            continue
        c = r['source_parent_weighted_sign_confusion']
        denom = sum(v for k,v in c.items() if 'zero' not in k)
        agree = sum(c.get(k,0.) for k in ('negative/negative','positive/positive'))
        nonzero = f'{agree/denom:.3%}' if denom else '不支持'
        result += f"| {r['family']} | {r['state']} | {r['parents']}/{r['episodes']} | {r['source_parent_weighted_sign_agreement']:.3%} | {nonzero} | {r['current_sign_counts']['zero']}/{r['nonreference_arm_comparisons']} | {r['historical_argmax_wrong_switch_loss']:.6f} |\n"
    return result+'\n排除恒零参照臂；零收益独列，含零一致率不是治理有效率。排序错误损失为按历史收益选臂在当前任务相对固定参照造成的损失；完整五臂oracle排序遗憾只在机器诊断表中，不是方法成绩。不同状态支持范围不同，因果归因仍须用共同支持机制表。\n'


def cost_audit(suites, queue, online):
    budgets = read(ROOT/'terminal_manifest.json')['budgets']
    audit = {'budget_thresholds':budgets, 'suite_rows':[], 'offline_generation':queue.get('jobs',[]),
             'cpu_fit_and_evaluation':read(ROOT/'cpu_queue_status.json',{}).get('jobs',[]),
             'online_process':online, 'cache_reuse_is_not_free_deployment':True,
             'historical_cost_provenance':['results/v431-r2/accounted_decisions.json',
                  'results/v431/20260914-sprint/accounted_table.json'],
             'scope':'Actual component charges, retrospective budget audit; no prediction or policy is changed.'}
    for suite, rows in suites.items():
        groups = defaultdict(list)
        for r in rows:
            groups[r['family'],r['policy']].append(r)
        for (family, policy), group in sorted(groups.items()):
            audit['suite_rows'].append(dict(suite=suite,family=family,policy=policy,episodes=len(group),
                 total_charged_component_seconds=sum(r['total_seconds'] for r in group),
                 exceed_low=sum(r['total_seconds']>budgets['low']+1e-12 for r in group),
                 exceed_high=sum(r['total_seconds']>budgets['high']+1e-12 for r in group),
                 scope='retrospective; not a common enforced budget for native fixed/TATO'))
    write(ROOT/'complete_cost_audit.json',audit)
    return audit


def outcome_text(table):
    t = {(r['family'],r['policy']):r for r in table}
    lines = []
    for f in ('bolt','timesfm'):
        a,b,c = (t[f,p] for p in ('R3_AGENT_high','FIXED_REFERENCE','R3_FIXED_TOOL_high'))
        lines.append(f"{f}：完整agent MASE {a['mase']:.6f}，训练固定参照 {b['mase']:.6f}，同冻结固定取证 {c['mase']:.6f}；组件秒/窗分别 {a['total_seconds']:.6f}/{b['total_seconds']:.6f}/{c['total_seconds']:.6f}。")
    return '\n\n'.join(lines)+'''\n\nBolt主动与固定取证在156/156个窗口动作和预测完全相同；TimesFM主动较固定取证退步，主DEV主动贡献不成立。两家族响应均未胜原始预测分歧，且未一致优于等次数回测、同容量直接回归或同证据CART，不能保留“有符号响应已证明独有增量”的主张。新表Bolt同容量DIRECT_control为1.146643；TimesFM普通CART_H32/H为1.069398，更简单对照已具有较强点估计。旧r2同证据CART作为继承完整原生方法另列，其信息与新control状态不同，不混作同信息消融。

训练支持已覆盖原三来源登记边界内110个独立parent。学习曲线13 fit低于16支持阈值，全部回参照；27→54 fit时Bolt控制状态检查MASE从1.334370变为1.339151，TimesFM从1.155641变为1.153286，不能笼统归因于“再加数据就会有效”。实际每工具仅16个有效acq parent，获取树均为常数根叶；当前自然调用依赖已学工具均值、适用性与预算，并未学出逐窗分裂规则。

预登记未见位置×H192的17-parent检查：TimesFM agent1.260234、固定取证1.288577、固定参照1.318134，但与随机1.267781的分组区间仍跨零；Bolt agent1.190724与固定取证完全相同。该局部结果是内部检查，不推翻主DEV结论，也不是独立确认。

金融两parent附表：Bolt agent3.103498劣于固定参照3.069683；TimesFM agent4.920632低于参照5.212728和固定取证5.139345，但8/12窗口实际超出3.5秒预算，不能认定同预算优势。原始完整输入五臂保持同输入/同预测，只支持观测保留；自然缺口和严格历史可用版本验证仍缺项。
'''


def merge_external(rows, *, financial=False):
    rows = list(rows)
    ref = {(r['family'], r['episode_uid']): r for r in rows if r['policy']=='FIXED_REFERENCE'}
    if financial:
        extras = [dict(r) for r in read(FIN/'common_financial_decisions.json', []) if 'TATO' in r['policy']]
    else:
        extras = []
        for f, folder in [('bolt','tato'),('timesfm','timesfm_tato')]:
            extras += [dict(r, family=f, policy='TATO_8_NATIVE_SPACE') for r in read(SPRINT/folder/'scored_rows.json', [])]
        for r in read(R2/'accounted_decisions.json', []):
            if r['policy']=='EXISTING_SAME_EVIDENCE_CART':
                extras.append(dict(r, policy='R2_EXISTING_CART'))
    for r in extras:
        k = (r['family'], r['episode_uid'])
        if k not in ref:
            raise ValueError('External baseline is outside the common origin manifest')
        gain = ref[k]['mase']-r['mase']
        flags = r.get('budget_overrun', False)
        r.update(switch_gain=max(gain,0.), wrong_switch_loss=max(-gain,0.), net_gain=gain,
                 tool_count=8 if 'TATO' in r['policy'] else r.get('tool_count',2),
                 budget_overrun=flags.get('high',False) if isinstance(flags,dict) else bool(flags),
                 inherited_completed_baseline=True)
        if 'TATO' in r['policy']:
            r['limitations']='8 official-space trials and explicit observed-linear bridge; not official full reproduction; trial count is not agent evidence calls'
        rows.append(r)
    return rows


def main():
    rows = read(ROOT/'decisions.json')
    if rows is None:
        raise RuntimeError('No completed common r3 evaluation; do not populate estimated results')
    rows = merge_external(rows)
    table, source = summarize(rows)
    write(ROOT/'common_decisions.json', rows)
    write(ROOT/'common_table.json', table)
    write(ROOT/'common_source_table.json', source)
    fields = ['family','policy','sources','parents','episodes','mase','mae','total_seconds','tool_count','budget_overruns','switch_gain','wrong_switch_loss','net_gain']
    with Path('docs/v431_r3_main_table.csv').open('w') as f:
        w = csv.DictWriter(f, fields, extrasaction='ignore', lineterminator='\n')
        w.writeheader();w.writerows(table)
    full = display(table)
    Path('docs/v431_r3_main_table.md').write_text('# v4.3.1-r3 共同开发主表\n\n同三来源、26 parent、156相关变体、共同目标与评分mask，source宏平均并按parent聚合。两个family不是两份独立数据。全表保留不支持、STOP与实际超预算；秒数为部署组件计费，完整冷在线墙钟另报。固定原生方法与TATO未执行同一预算准入时，其超支应按实际秒数另核，不能把缺少预算flag解读为预算内。8个TATO优化trial不同于agent工具调用。\n\n'+full+'\n金融事件索引附表不同协议/分母，不与本表横比。配对统计、共同支持子集与实际适用性见r3报告及机器账本。\n')
    focus = {'KEEP','FIXED_TSICL','FIXED_REFERENCE','R2_EXISTING_CART','CART_control_high','CART_H32_high','CART_H_high',
             'DIRECT_control_high','RESIDUAL_H_high','RESIDUAL_control_high','RESIDUAL_disagreement_high',
             'RESIDUAL_equal-cost_high','R3_FIXED_TOOL_high','R3_RANDOM_high','R3_AGENT_high','TATO_8_NATIVE_SPACE'}
    core = display([r for r in table if r['policy'] in focus])
    financial = read(ROOT/'financial_decisions.json')
    fin_text = '金融r3冻结策略迁移尚未完成，不能填预计数。\n'
    if financial:
        financial = merge_external(financial, financial=True)
        ft, _ = summarize(financial)
        write(ROOT/'common_financial_table.json', ft)
        write(ROOT/'common_financial_decisions.json', financial)
        fin_text = display([r for r in ft if r['policy'] in focus or 'TATO' in r['policy']])
        condition_tables = {}
        for c in sorted({r['condition'] for r in financial}):
            ct, _ = summarize([r for r in financial if r['condition']==c])
            condition_tables[c] = ct
        write(ROOT/'financial_condition_tables.json', condition_tables)
        Path('docs/v431_r3_financial_table.md').write_text('# r3 金融观测事件附表\n\n两parent/12变体；与旧DEV和pilot未来部分重叠，不是确认。无核实自然缺口，只有完整记录与受控删除。\n\n'+display(ft)+'\n'+''.join('\n## '+c+'\n\n'+display([r for r in t if r['policy'] in focus or 'TATO' in r['policy']]) for c,t in condition_tables.items()))
    queue = read(ROOT/'queue_status.json', {})
    online = {f: read(ROOT/('online-'+f)/'process_accounting.json', {'status':'pending'}) for f in ('bolt','timesfm')}
    cost = cost_audit({'main':rows, **({'financial':financial} if financial else {})}, queue, online)
    paired = read(ROOT/'paired_comparisons.json', {'status':'pending'})
    learning = read(ROOT/'learning_curves.json', {'status':'pending'})
    statistics = read(ROOT/'statistics.json', {'status':'pending'})
    mechanism_text = attribution(paired)
    signs = sign_display(statistics)
    outcomes = outcome_text(table)
    freeze = read(ROOT/'models_frozen.json', {})
    pilot = read(ROOT/'pilot_first_report.json', {})
    hashes = {str(p):file_hash(p) for p in [ROOT/'models_frozen.json',ROOT/'terminal_manifest.json',ROOT/'decisions.json',ROOT/'common_table.json',ROOT/'resolved_config.json'] if p.exists()}
    evidence = dict(updated_at=datetime.now(timezone.utc).isoformat(), common_rows=len(table),
                    main_parents=26, main_variants=156, artifacts=hashes, online=online,
                    financial_ready=financial is not None, calibration_test_opened=False, promoted=False)
    write(ROOT/'report_evidence.json', evidence)
    method = '''固定五臂为Native KEEP、FFILL、单变量TS-ICL、多变量TS-ICL和context ridge；有效观测不覆盖，没有预测后残差臂。A4不支持时原函数明确回Native，历史Collector丢失detail的缺项由独立support账本补齐，不能把此别名当成功ridge。

无证据使用75个训练parent内选定的每家族固定TS-ICL参照，完整target直接KEEP。主状态模型用54 fit、21 gate，17 check和18 acq保持隔离。H32、目标H、同origin长短控制分别有对应可见状态；未知响应不填零。当前dirty先截历史前缀，当前缺口按距origin位置复制，再分别治理；仅使用当时可用协变量和当前可见历史目标，覆盖至少max(16,ceil(Hq/2))。H96/192的long为416/320步，short为352/256步。历史匹配H仍不等于匹配部署L512。

d_long=(MAE_reference,long−MAE_action,long)/S_t；d_short同尺度；κ=d_long−d_short；z=((512−Lq)/64)κ。S_t为既有正TRAIN MASE尺度，跨动作和长短固定。κ是整条治理管线对更早观测的有符号响应，不是市场因果效应或已证线性外推律。

共享低维ridge拟合Δ_t−d_long，预测时在原MASE单位加回d_long；每动作截距、共享斜率、fit-only标准化，alpha仅0.1/1/10在gate选。直接收益ridge使用同输入/容量/搜索预算，CART同已取得证据。分歧对照严格用旧probe.py的mean_t std_view(raw predictions)/S_t，不以abs(κ)/2冒充。等次数普通回测在r和r−64两个origin，与控制的同origin不同长度区分；两者真实秒数不必相同，预算按完整分支检查。

冻结所有终态和支持规则后，在18独立acq parent用同一冻结策略计算停止与取得证据后的真实任务损失差，扣完整部署成本差。获取器最多一次决策，选H32/H/control或STOP，原low0.8140623268639832秒/high3.5秒及lambda规则不改。只在预计净值>0、工具适用且预算可行时取证；所有失败费用和最终动作/预测费用保留。部署不预先取得全池候选或隐藏probe结果。
'''
    financial_scope = '''Brent Europe现货报价（USD/barrel）与Kim–Wright拟合一年后瞬时远期利率（百分点）已核身份，后者不是成交价格。原快照缺历史vintage和可靠发布时间还原，因此不声称严格PIT。自然NaN缺少休市/应有观测缺失分类，自然缺口效果仍缺项。

金融附表沿r2预登记financial-observation-index-r1：在原split内取有完整记录的事件，保留原值/原始日期映射，H按观测事件，MASE用对应TRAIN lag5。它与原B网格主表不同，不能横比绝对MASE。两个DEV日期不重叠；TRAIN1242个共同有限日期的水平Pearson为−0.142379。Oil未来4行、USTS H192未来161行与旧pilot/DEV重叠，绝非独立确认。长短控制支持8/12变体，其中完整raw4个，受控H96仅4变体/2parent。完整五臂no-op同预测仅说明观测保留，不能写治理提升。
'''
    report = '# v4.3.1-r3 实际执行报告\n\n本轮为开发验证，未晋升；PICS_joint_relabel保留原协议incumbent，calibration/test封存。所有实验和统计在当前服务器，三环境和两个真实模型家族复用。\n\n## 实际代码差异与旧STOP原因\n\n旧agent全部STOP来自自身D2基础策略，156/156与基础强制STOP一致；并未约定STOP必为TS-ICL。相对固定TSICL，26次预测真正变化中3好23坏，主要Solar退步；旧获取标签没有正增量、lambda0，并非重复成本扣罚。r2已修无证据为train固定参照，Bolt1.157005；TimesFM1.069398与固定mask CART相同，不把工程修复写研究成功。详见[r2逐窗审计](v431_r2_stop_audit.md)。\n\nr3新增probe.py的ProbeSpec/Result与严格几何、response.py的真实任务映射、acquisition.py同冻结pi价值标签、canonical输入去重collector、runtime与online实际取证、独立预处理/输出/成本审计。旧v35先整段治理再截anchor的顺序不能作为新合法依据；最新r2/3已先截再治理，没有直接宣称所有旧结果或最新代码泄漏。具体路径与函数见[代码审计](v431_r3_code_audit.md)。\n\n## 方法和预登记\n\n'+method+'\n## 支持、吞吐与长短四格\n\n原三来源完整合法非重叠TRAIN为110 parent（59/44/7），64上限未截断；不是把26个DEV当train。主账本816变体加17个check专用新位置，共833输入、3332原子规格；2624可准备、708不支持。新增[358,409)×H192只在T_check17，未增加独立parent，未用于训练或阈值选择。额外来源/事件协议不能无登记混进旧主表。\n\n首批20parent采集69.129秒，不据表现选方法。首个ETTm1 target-block/H96的固定TSICL long/short MAE为3.156923/2.829195，多变量TSICL为0.616306/1.455822，κ=+0.463917；这是历史测量，非当前任务成功。完整四格和原始hash见pilot_first_report.json。\n\n学习曲线（仅检查，不选比例）：\n\n```json\n'+json.dumps(learning,ensure_ascii=False,indent=2)+'\n```\n\n## 同一DEV共同结果\n\n'+core+'\n完整表见[v431_r3_main_table.md](v431_r3_main_table.md)，包括低/高预算、全部状态和强对照；不能把大量相关输出计作独立样本。TATO保留原生空间，仅8trial本地短预算适配，不是官方完整复现；未执行其他近期官方方法不能称击败。\n\n配对效果与共同支持机制见`paired_comparisons.json`、`mechanism_common_support.json`和`statistics.json`。按source/时间parent块处理依赖；单一USTS DEV parent及重复使用DEV限制区间解释。\n\n## 金融条件\n\n'+financial_scope+'\n'+fin_text+'\n## 在线、成本与运行范围\n\n```json\n'+json.dumps(online,ensure_ascii=False,indent=2)+'\n```\n\n自然窗口与受控强制调用分开，全部STOP也如实记录；受控长短/工具后故障不算策略增益。零预算拒绝取证仍需最终预测，实际超支不删除。主表是治理/证据/最终推断组件账单，在线另记模型启动、热请求和完整进程墙钟；训练、探针离线生成与实验cache复用成本分离。历史缓存省本轮时间，不抹掉已发生计算。队列实际命令、耗时、PID和资源见queue_status.json与logs/v431-r3。\n\n## 可支持主张与缺项\n\n本文目前只对已核协议中的固定TSFM推理前缺口治理作结论，不涉及交易利润、TSFM参数训练或文本大模型训练。κ存在不代表其部署收益成立；必须同时比较无κ、原始预测分歧、等次数回测、同输入direct/CART。主动获取必须胜同预算固定流程，工程正确性及只胜旧失败agent均不是方法成功。所有负结果保留；没有据DEV失败打开calibration/test。实际模块点估计与区间由同一机器统计生成，最终主张审计更新见[novelty_matrix](novelty_matrix.md)。\n\n独立复核范围、首次失败和未完成项见[v431_r3_verification.md](v431_r3_verification.md)；精简审阅包附配置、实际命令、支持表、相关代码、少量原始成对测量与自然轨迹、费用和commit/hash，无权重和凭据。\n'
    report = report.replace('```json\n'+json.dumps(learning,ensure_ascii=False,indent=2)+'\n```', curve_display(learning))
    report = report.replace('## 金融条件\n', '## 模块归因的实际配对结果\n\n'+mechanism_text+'\n## 金融条件\n')
    constraints = '''实际有效fit为51 parent、gate20、acq16（角色清单分别为54/21/18）。获取LOPO每折只剩15 parent，低于16门槛，两个lambda的CV效用均为0；lambda=0来自已登记平局规则，不能称费用权重已被有力验证。

继承尺度限制：`v43/p2.py`从整个source TRAIN计算MASE常数，ETTm1[0,41808)、Solar[0,31536)、USTS[0,5595)。早期TRAIN origin在512等位置，故该常数包含其后来TRAIN观测，也包含内部gate/check/acq数据。r3将其用于d、κ及psi的尺度差归一化，不能声称所有内部预处理严格处于外层检查组之外或每个TRAIN origin严格PIT。DEV时整个TRAIN已在过去，calibration/test未参与。按本轮既定分母保持共同可比性，未在看完DEV后更换尺度重拟；此限制阻止把当前开发结果提升为严格在线金融确认。

主表预算是常驻模型的部署组件预算。两家族各7个自然在线窗口，Bolt6次选择control（12实际probe）、TimesFM6次选择H32（6实际probe），各1次STOP；自然hot与11请求分摊完整进程成本超支均为0。完整进程墙钟分别26.271817/27.357047秒，模型启动9.057486/9.410971秒，单次冷启动已超过3.5秒，不将分摊延迟写成单请求冷启动达标。两个受控B0请求仍必须最终预测，真实超支保留；工具后故障是受控注入，不能当自然故障率。

只读原始完整金融记录、受控删除和已核价格/利率字段；自然缺口、严格历史发布/复权vintage、独立金融确认、近期baseline官方完整预算复现仍未完成。本轮候选及监督已冻结以便复核，但开发晋升条件不满足，calibration/test继续封存；不增加配置或用确认集挽救开发失败。
'''
    report = report.replace('## 同一DEV共同结果\n', '## 本轮结论与冻结状态\n\n'+outcomes+'\n## 同一DEV共同结果\n')
    report = report.replace('## 金融条件\n', '## 历史证据与部署收益\n\n'+signs+'\n## 金融条件\n')
    report += '\n## 已确认限制与未完成项\n\n'+constraints+'\n完整事后预算核对见`complete_cost_audit.json`；未带预算准入的原生固定方法/TATO也按实际秒数统计low/high超支，绝不将缺flag当0。\n'
    Path('docs/v431_r3_report.md').write_text(report)
    paper = Path('docs/paper_v431_draft.md')
    archive = Path('docs/paper_v431_draft_r2_archived.md')
    if not archive.exists():
        archive.write_bytes(paper.read_bytes())
    draft = '# IntroAct-TS: A Financial Data Governance Agent for Time Series Foundation Models\n\n中文：面向时间序列基础模型的金融数据治理智能体\n\nv4.3.1-r3开发论证草稿；尚无SOTA或独立确认声明。\n\n## 背景与定义\n\n真实金融价格可以正确，跳变不能自动视为错误。对于确有观测覆盖不足的输入，治理改变固定TSFM使用的信息，但更低插补误差不必然改善预测。本项目研究未来不可见、验证计算有限时，如何取得证据、选择保留或治理，并停止。备份仅工程恢复能力，不承担创新主张。动作在同一target/context边界/horizon/checkpoint上比较任务MASE，未来标签只在合法训练或冻结后评价命名空间中使用。\n\n## 完整方法\n\n'+method+'\n## 相关工作和增量归因\n\nTATO已有冻结TSFM输入变换搜索，Task-oriented Imputation已有下游收益治理，DIME/TNDP已有成本敏感信息获取和决策效用实验设计，CSDI/ImputePilot已有插补与选择流程，嵌套上下文和旧项目multiview均有先例。具体primary链接和必要消融见[创新矩阵](novelty_matrix.md)；不把组合模块、ridge残差写成原创或继承理论保证。拟检验增量只在有符号测量是否比通用证据更有助实际治理，以及获取是否比固定取证更好。\n\n## 共同实验\n\n'+core+'\n同26个反复开发parent/156相关变体，按source和时间parent分组。表由同一汇总脚本生成，额外候选/探针不增加独立样本。外部TATO仅短预算适配，近期基线全协议复现仍不完整，不能称SOTA。支持及模块配对归因见[r3报告](v431_r3_report.md)。\n\n## 金融验证范围\n\n'+financial_scope+'\n'+fin_text+'\n## 适用条件与限制\n\n原[230,281)缺口的H192短上下文放不完整，按unsupported回退，不能移动缺口制造支持。长短响应不是因果量，跨L/H预测收益迁移需要单独验证。训练内新位置×H只作固定check，不能当独立DEV确认；完整观测no-op不提供预测提升。主动全STOP、工具后动作不变或与固定流程同效均应作为负结果。在线强制分支只验工程。\n\n当前没有方法晋升，PICS_joint_relabel保持历史incumbent。calibration/test继续封存；不将未完成实验、开发胜出、环境验收或工程测试写成ICLR录用或SOTA证据。\n'
    draft = draft.replace('## 金融验证范围\n', '## 模块消融与主张边界\n\n'+mechanism_text+'\n## 金融验证范围\n')
    draft = draft.replace('## 共同实验\n', '## 实际结果解释\n\n'+outcomes+'\n## 共同实验\n')
    draft += '\n## 证据符号与排序诊断\n\n'+signs+'\n## 冻结状态和协议限制\n\n'+constraints
    paper.write_text(draft)
    print(json.dumps(evidence), flush=True)


if __name__ == '__main__':
    main()
