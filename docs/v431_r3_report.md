# v4.3.1-r3 实际执行报告

本轮为开发验证，未晋升；PICS_joint_relabel保留原协议incumbent，calibration/test封存。所有实验和统计在当前服务器，三环境和两个真实模型家族复用。

## 实际代码差异与旧STOP原因

旧agent全部STOP来自自身D2基础策略，156/156与基础强制STOP一致；并未约定STOP必为TS-ICL。相对固定TSICL，26次预测真正变化中3好23坏，主要Solar退步；旧获取标签没有正增量、lambda0，并非重复成本扣罚。r2已修无证据为train固定参照，Bolt1.157005；TimesFM1.069398与固定mask CART相同，不把工程修复写研究成功。详见[r2逐窗审计](v431_r2_stop_audit.md)。

r3新增probe.py的ProbeSpec/Result与严格几何、response.py的真实任务映射、acquisition.py同冻结pi价值标签、canonical输入去重collector、runtime与online实际取证、独立预处理/输出/成本审计。旧v35先整段治理再截anchor的顺序不能作为新合法依据；最新r2/3已先截再治理，没有直接宣称所有旧结果或最新代码泄漏。具体路径与函数见[代码审计](v431_r3_code_audit.md)。

## 方法和预登记

固定五臂为Native KEEP、FFILL、单变量TS-ICL、多变量TS-ICL和context ridge；有效观测不覆盖，没有预测后残差臂。A4不支持时原函数明确回Native，历史Collector丢失detail的缺项由独立support账本补齐，不能把此别名当成功ridge。

无证据使用75个训练parent内选定的每家族固定TS-ICL参照，完整target直接KEEP。主状态模型用54 fit、21 gate，17 check和18 acq保持隔离。H32、目标H、同origin长短控制分别有对应可见状态；未知响应不填零。当前dirty先截历史前缀，当前缺口按距origin位置复制，再分别治理；仅使用当时可用协变量和当前可见历史目标，覆盖至少max(16,ceil(Hq/2))。H96/192的long为416/320步，short为352/256步。历史匹配H仍不等于匹配部署L512。

d_long=(MAE_reference,long−MAE_action,long)/S_t；d_short同尺度；κ=d_long−d_short；z=((512−Lq)/64)κ。S_t为既有正TRAIN MASE尺度，跨动作和长短固定。κ是整条治理管线对更早观测的有符号响应，不是市场因果效应或已证线性外推律。

共享低维ridge拟合Δ_t−d_long，预测时在原MASE单位加回d_long；每动作截距、共享斜率、fit-only标准化，alpha仅0.1/1/10在gate选。直接收益ridge使用同输入/容量/搜索预算，CART同已取得证据。分歧对照严格用旧probe.py的mean_t std_view(raw predictions)/S_t，不以abs(κ)/2冒充。等次数普通回测在r和r−64两个origin，与控制的同origin不同长度区分；两者真实秒数不必相同，预算按完整分支检查。

冻结所有终态和支持规则后，在18独立acq parent用同一冻结策略计算停止与取得证据后的真实任务损失差，扣完整部署成本差。获取器最多一次决策，选H32/H/control或STOP，原low0.8140623268639832秒/high3.5秒及lambda规则不改。只在预计净值>0、工具适用且预算可行时取证；所有失败费用和最终动作/预测费用保留。部署不预先取得全池候选或隐藏probe结果。

## 支持、吞吐与长短四格

原三来源完整合法非重叠TRAIN为110 parent（59/44/7），64上限未截断；不是把26个DEV当train。主账本816变体加17个check专用新位置，共833输入、3332原子规格；2624可准备、708不支持。新增[358,409)×H192只在T_check17，未增加独立parent，未用于训练或阈值选择。额外来源/事件协议不能无登记混进旧主表。

首批20parent采集69.129秒，不据表现选方法。首个ETTm1 target-block/H96的固定TSICL long/short MAE为3.156923/2.829195，多变量TSICL为0.616306/1.455822，κ=+0.463917；这是历史测量，非当前任务成功。完整四格和原始hash见pilot_first_report.json。

学习曲线（仅检查，不选比例）：

| 家族 | fit parent | 额外gate parent | 状态 | check MASE | check固定参照 |
|---|---:|---:|---|---:|---:|
| bolt | 13 | 21 | H32 | 1.328637 | 1.328637 |
| bolt | 13 | 21 | H | 1.328637 | 1.328637 |
| bolt | 13 | 21 | control | 1.328637 | 1.328637 |
| bolt | 27 | 21 | H32 | 1.367222 | 1.328637 |
| bolt | 27 | 21 | H | 1.332584 | 1.328637 |
| bolt | 27 | 21 | control | 1.334370 | 1.328637 |
| bolt | 54 | 21 | H32 | 1.404076 | 1.328637 |
| bolt | 54 | 21 | H | 1.340747 | 1.328637 |
| bolt | 54 | 21 | control | 1.339151 | 1.328637 |
| timesfm | 13 | 21 | H32 | 1.162536 | 1.162536 |
| timesfm | 13 | 21 | H | 1.162536 | 1.162536 |
| timesfm | 13 | 21 | control | 1.162536 | 1.162536 |
| timesfm | 27 | 21 | H32 | 1.155652 | 1.162536 |
| timesfm | 27 | 21 | H | 1.149586 | 1.162536 |
| timesfm | 27 | 21 | control | 1.155641 | 1.162536 |
| timesfm | 54 | 21 | H32 | 1.159826 | 1.162536 |
| timesfm | 54 | 21 | H | 1.148845 | 1.162536 |
| timesfm | 54 | 21 | control | 1.153286 | 1.162536 |

各比例共用独立17-parent检查集；额外21个gate parent参与alpha/参照选择，不能把13个fit parent称为全部监督仅13。100%始终为主模型，不据曲线选比例。


## 本轮结论与冻结状态

bolt：完整agent MASE 1.156351，训练固定参照 1.157005，同冻结固定取证 1.156351；组件秒/窗分别 0.284957/0.120142/0.284946。

timesfm：完整agent MASE 1.102669，训练固定参照 1.096135，同冻结固定取证 1.096019；组件秒/窗分别 0.600939/0.230177/0.592392。

Bolt主动与固定取证在156/156个窗口动作和预测完全相同；TimesFM主动较固定取证退步，主DEV主动贡献不成立。两家族响应均未胜原始预测分歧，且未一致优于等次数回测、同容量直接回归或同证据CART，不能保留“有符号响应已证明独有增量”的主张。新表Bolt同容量DIRECT_control为1.146643；TimesFM普通CART_H32/H为1.069398，更简单对照已具有较强点估计。旧r2同证据CART作为继承完整原生方法另列，其信息与新control状态不同，不混作同信息消融。

训练支持已覆盖原三来源登记边界内110个独立parent。学习曲线13 fit低于16支持阈值，全部回参照；27→54 fit时Bolt控制状态检查MASE从1.334370变为1.339151，TimesFM从1.155641变为1.153286，不能笼统归因于“再加数据就会有效”。实际每工具仅16个有效acq parent，获取树均为常数根叶；当前自然调用依赖已学工具均值、适用性与预算，并未学出逐窗分裂规则。

预登记未见位置×H192的17-parent检查：TimesFM agent1.260234、固定取证1.288577、固定参照1.318134，但与随机1.267781的分组区间仍跨零；Bolt agent1.190724与固定取证完全相同。该局部结果是内部检查，不推翻主DEV结论，也不是独立确认。

金融两parent附表：Bolt agent3.103498劣于固定参照3.069683；TimesFM agent4.920632低于参照5.212728和固定取证5.139345，但8/12窗口实际超出3.5秒预算，不能认定同预算优势。原始完整输入五臂保持同输入/同预测，只支持观测保留；自然缺口和严格历史可用版本验证仍缺项。

## 同一DEV共同结果

| 家族 | 方法 | MASE ↓ | 秒/窗 | 工具/窗 | parent | 超预算窗 |
|---|---|---:|---:|---:|---:|---:|
| bolt | CART_H32_high | 1.210484 | 0.225270 | 0.444 | 26 | 0 |
| bolt | CART_H_high | 1.203353 | 0.305781 | 0.444 | 26 | 0 |
| bolt | CART_control_high | 1.157005 | 0.283899 | 0.444 | 26 | 0 |
| bolt | DIRECT_control_high | 1.146643 | 0.283285 | 0.444 | 26 | 0 |
| bolt | FIXED_REFERENCE | 1.157005 | 0.120142 | 0.000 | 26 | 0 |
| bolt | FIXED_TSICL | 1.157005 | 0.120142 | 0.000 | 26 | 0 |
| bolt | KEEP | 1.258454 | 0.089880 | 0.000 | 26 | 0 |
| bolt | R2_EXISTING_CART | 1.136486 | 0.657985 | 2.000 | 26 | 0 |
| bolt | R3_AGENT_high | 1.156351 | 0.284957 | 0.444 | 26 | 0 |
| bolt | R3_FIXED_TOOL_high | 1.156351 | 0.284946 | 0.444 | 26 | 0 |
| bolt | R3_RANDOM_high | 1.168931 | 0.253947 | 0.367 | 26 | 0 |
| bolt | RESIDUAL_H_high | 1.153110 | 0.310894 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_control_high | 1.156351 | 0.281960 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_disagreement_high | 1.156327 | 0.282220 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_equal-cost_high | 1.162748 | 0.279957 | 0.444 | 26 | 0 |
| bolt | TATO_8_NATIVE_SPACE | 1.685227 | 0.703174 | 8.000 | 26 | 0 |
| timesfm | CART_H32_high | 1.069398 | 0.596548 | 0.444 | 26 | 0 |
| timesfm | CART_H_high | 1.069398 | 0.587328 | 0.444 | 26 | 0 |
| timesfm | CART_control_high | 1.096135 | 0.591610 | 0.444 | 26 | 0 |
| timesfm | DIRECT_control_high | 1.096564 | 0.589380 | 0.444 | 26 | 0 |
| timesfm | FIXED_REFERENCE | 1.096135 | 0.230177 | 0.000 | 26 | 0 |
| timesfm | FIXED_TSICL | 1.096135 | 0.230020 | 0.000 | 26 | 0 |
| timesfm | KEEP | 1.139837 | 0.200703 | 0.000 | 26 | 0 |
| timesfm | R2_EXISTING_CART | 1.069086 | 1.072156 | 2.000 | 26 | 0 |
| timesfm | R3_AGENT_high | 1.102669 | 0.600939 | 0.444 | 26 | 0 |
| timesfm | R3_FIXED_TOOL_high | 1.096019 | 0.592392 | 0.444 | 26 | 0 |
| timesfm | R3_RANDOM_high | 1.091977 | 0.530007 | 0.367 | 26 | 0 |
| timesfm | RESIDUAL_H_high | 1.085811 | 0.588517 | 0.444 | 26 | 0 |
| timesfm | RESIDUAL_control_high | 1.096019 | 0.589449 | 0.444 | 26 | 0 |
| timesfm | RESIDUAL_disagreement_high | 1.092599 | 0.589145 | 0.444 | 26 | 0 |
| timesfm | RESIDUAL_equal-cost_high | 1.091448 | 0.588512 | 0.444 | 26 | 0 |
| timesfm | TATO_8_NATIVE_SPACE | 1.529002 | 1.023989 | 8.000 | 26 | 0 |

完整表见[v431_r3_main_table.md](v431_r3_main_table.md)，包括低/高预算、全部状态和强对照；不能把大量相关输出计作独立样本。TATO保留原生空间，仅8trial本地短预算适配，不是官方完整复现；未执行其他近期官方方法不能称击败。

配对效果与共同支持机制见`paired_comparisons.json`、`mechanism_common_support.json`和`statistics.json`。按source/时间parent块处理依赖；单一USTS DEV parent及重复使用DEV限制区间解释。

## 模块归因的实际配对结果

| 家族 | 比较（高预算） | MASE收益↑ | 95%分组区间 | 共同parent/窗 | 范围 |
|---|---|---:|---|---|---|
| bolt | 主动 vs 固定强参照 | 0.000654 | [-0.022673, 0.026833] | 26/156 | full_common_denominator |
| bolt | 主动 vs 同冻结固定获取 | -0.000000 | [-0.000000, -0.000000] | 26/156 | full_common_denominator |
| bolt | 主动 vs 随机可行获取 | 0.012580 | [-0.007216, 0.031598] | 26/156 | full_common_denominator |
| bolt | 响应 vs 无κ | -0.004163 | [-0.008426, -0.000396] | 25/50 | common_supported_and_actually_acquired |
| bolt | 响应 vs 旧原始预测分歧 | -0.000106 | [-0.000319, -0.000000] | 25/50 | common_supported_and_actually_acquired |
| bolt | 响应 vs 双原点普通回测 | 0.028786 | [-0.023305, 0.102455] | 25/50 | common_supported_and_actually_acquired |
| bolt | 响应 vs 同证据CART | 0.002942 | [-0.102031, 0.120750] | 25/50 | common_supported_and_actually_acquired |
| bolt | 响应 vs 同容量直接回归 | -0.043684 | [-0.120932, 0.030112] | 25/50 | common_supported_and_actually_acquired |
| timesfm | 主动 vs 固定强参照 | -0.006534 | [-0.069293, 0.039582] | 26/156 | full_common_denominator |
| timesfm | 主动 vs 同冻结固定获取 | -0.006650 | [-0.066643, 0.031453] | 26/156 | full_common_denominator |
| timesfm | 主动 vs 随机可行获取 | -0.010692 | [-0.069787, 0.029651] | 26/156 | full_common_denominator |
| timesfm | 响应 vs 无κ | 0.037489 | [0.003635, 0.085886] | 25/50 | common_supported_and_actually_acquired |
| timesfm | 响应 vs 旧原始预测分歧 | -0.015392 | [-0.062519, 0.016316] | 25/50 | common_supported_and_actually_acquired |
| timesfm | 响应 vs 双原点普通回测 | -0.020572 | [-0.066260, 0.007415] | 25/50 | common_supported_and_actually_acquired |
| timesfm | 响应 vs 同证据CART | 0.000522 | [-0.068347, 0.076954] | 25/50 | common_supported_and_actually_acquired |
| timesfm | 响应 vs 同容量直接回归 | 0.002449 | [-0.025603, 0.025292] | 25/50 | common_supported_and_actually_acquired |

收益为右侧参照减左侧方法。完整表与共同支持机制子集不可混为同一分母；重复DEV、小来源支持及单一时间块限制区间解释，均非独立确认。

## 历史证据与部署收益

| 家族 | 状态 | parent/窗 | 历史符号一致率（含零） | 双方非零一致率 | 当前零收益/非参照比较 | 历史排序错误损失 |
|---|---|---|---:|---:|---|---:|
| bolt | H | 25/150 | 73.282% | 59.923% | 200/600 | 0.059130 |
| bolt | H32 | 25/150 | 72.971% | 59.456% | 200/600 | 0.119024 |
| bolt | control | 25/100 | 81.209% | 62.419% | 200/400 | 0.054576 |
| timesfm | H | 25/150 | 72.119% | 58.178% | 200/600 | 0.034430 |
| timesfm | H32 | 25/150 | 65.936% | 48.904% | 200/600 | 0.095826 |
| timesfm | control | 25/100 | 77.618% | 55.235% | 200/400 | 0.041701 |

排除恒零参照臂；零收益独列，含零一致率不是治理有效率。排序错误损失为按历史收益选臂在当前任务相对固定参照造成的损失；完整五臂oracle排序遗憾只在机器诊断表中，不是方法成绩。不同状态支持范围不同，因果归因仍须用共同支持机制表。

## 金融条件

Brent Europe现货报价（USD/barrel）与Kim–Wright拟合一年后瞬时远期利率（百分点）已核身份，后者不是成交价格。原快照缺历史vintage和可靠发布时间还原，因此不声称严格PIT。自然NaN缺少休市/应有观测缺失分类，自然缺口效果仍缺项。

金融附表沿r2预登记financial-observation-index-r1：在原split内取有完整记录的事件，保留原值/原始日期映射，H按观测事件，MASE用对应TRAIN lag5。它与原B网格主表不同，不能横比绝对MASE。两个DEV日期不重叠；TRAIN1242个共同有限日期的水平Pearson为−0.142379。Oil未来4行、USTS H192未来161行与旧pilot/DEV重叠，绝非独立确认。长短控制支持8/12变体，其中完整raw4个，受控H96仅4变体/2parent。完整五臂no-op同预测仅说明观测保留，不能写治理提升。

| 家族 | 方法 | MASE ↓ | 秒/窗 | 工具/窗 | parent | 超预算窗 |
|---|---|---:|---:|---:|---:|---:|
| bolt | CART_H32_high | 3.069683 | 2.749388 | 0.667 | 2 | 7 |
| bolt | CART_H_high | 3.291740 | 0.760929 | 0.667 | 2 | 0 |
| bolt | CART_control_high | 3.069683 | 1.423560 | 0.667 | 2 | 0 |
| bolt | DIRECT_control_high | 3.069683 | 1.423539 | 0.667 | 2 | 0 |
| bolt | FIXED_REFERENCE | 3.069683 | 1.184308 | 0.000 | 2 | 0 |
| bolt | FIXED_TSICL | 3.069683 | 1.184308 | 0.000 | 2 | 0 |
| bolt | KEEP | 2.820959 | 0.475021 | 0.000 | 2 | 0 |
| bolt | R3_AGENT_high | 3.103498 | 1.344463 | 0.667 | 2 | 0 |
| bolt | R3_FIXED_TOOL_high | 3.103498 | 1.344421 | 0.667 | 2 | 0 |
| bolt | R3_RANDOM_high | 3.030359 | 1.596536 | 0.500 | 2 | 0 |
| bolt | RESIDUAL_H_high | 2.893634 | 1.300360 | 0.667 | 2 | 0 |
| bolt | RESIDUAL_control_high | 3.103498 | 1.341234 | 0.667 | 2 | 0 |
| bolt | RESIDUAL_disagreement_high | 3.069683 | 1.423679 | 0.667 | 2 | 0 |
| bolt | RESIDUAL_equal-cost_high | 3.105497 | 1.154022 | 0.667 | 2 | 0 |
| bolt | TATO_NATIVE_8TRIALS_OBSERVED_LINEAR | 4.698655 | 1.034955 | 8.000 | 2 | 0 |
| timesfm | CART_H32_high | 4.890237 | 2.599254 | 0.667 | 2 | 6 |
| timesfm | CART_H_high | 4.890237 | 1.128813 | 0.667 | 2 | 0 |
| timesfm | CART_control_high | 5.212728 | 1.497164 | 0.667 | 2 | 0 |
| timesfm | DIRECT_control_high | 5.176356 | 1.311738 | 0.667 | 2 | 0 |
| timesfm | FIXED_REFERENCE | 5.212728 | 0.956509 | 0.000 | 2 | 0 |
| timesfm | FIXED_TSICL | 5.212728 | 0.956247 | 0.000 | 2 | 0 |
| timesfm | KEEP | 5.225872 | 0.247486 | 0.000 | 2 | 0 |
| timesfm | R3_AGENT_high | 4.920632 | 2.769635 | 0.667 | 2 | 8 |
| timesfm | R3_FIXED_TOOL_high | 5.139345 | 1.337081 | 0.667 | 2 | 0 |
| timesfm | R3_RANDOM_high | 5.074479 | 1.902638 | 0.500 | 2 | 4 |
| timesfm | RESIDUAL_H_high | 5.006926 | 1.332840 | 0.667 | 2 | 0 |
| timesfm | RESIDUAL_control_high | 5.139345 | 1.333893 | 0.667 | 2 | 0 |
| timesfm | RESIDUAL_disagreement_high | 5.139345 | 1.334046 | 0.667 | 2 | 0 |
| timesfm | RESIDUAL_equal-cost_high | 5.144106 | 1.333316 | 0.667 | 2 | 0 |
| timesfm | TATO_NATIVE_8TRIALS_OBSERVED_LINEAR | 4.980245 | 1.396753 | 8.000 | 2 | 0 |

## 在线、成本与运行范围

```json
{
  "bolt": {
    "status": "completed",
    "exit_code": 0,
    "process_wall_seconds": 26.271817226001076,
    "scope": "full validation worker spawn through exit including controlled cases",
    "requests": 11,
    "natural_requests": 7,
    "hot_request_seconds": 10.06948192800155,
    "model_startup_seconds": 9.05748577399936,
    "remaining_overhead_seconds": 7.144849524000165,
    "natural_actual_tool_calls": 12,
    "natural_hot_seconds": 8.054254293001577,
    "natural_acquisition_decisions": 6
  },
  "timesfm": {
    "status": "completed",
    "exit_code": 0,
    "process_wall_seconds": 27.35704735299987,
    "scope": "full validation worker spawn through exit including controlled cases",
    "requests": 11,
    "natural_requests": 7,
    "hot_request_seconds": 11.237222132996976,
    "model_startup_seconds": 9.410971163002614,
    "remaining_overhead_seconds": 6.708854057000281,
    "natural_actual_tool_calls": 6,
    "natural_hot_seconds": 8.209747515995332,
    "natural_acquisition_decisions": 6
  }
}
```

自然窗口与受控强制调用分开，全部STOP也如实记录；受控长短/工具后故障不算策略增益。零预算拒绝取证仍需最终预测，实际超支不删除。主表是治理/证据/最终推断组件账单，在线另记模型启动、热请求和完整进程墙钟；训练、探针离线生成与实验cache复用成本分离。历史缓存省本轮时间，不抹掉已发生计算。队列实际命令、耗时、PID和资源见queue_status.json与logs/v431-r3。

## 可支持主张与缺项

本文目前只对已核协议中的固定TSFM推理前缺口治理作结论，不涉及交易利润、TSFM参数训练或文本大模型训练。κ存在不代表其部署收益成立；必须同时比较无κ、原始预测分歧、等次数回测、同输入direct/CART。主动获取必须胜同预算固定流程，工程正确性及只胜旧失败agent均不是方法成功。所有负结果保留；没有据DEV失败打开calibration/test。实际模块点估计与区间由同一机器统计生成，最终主张审计更新见[novelty_matrix](novelty_matrix.md)。

独立复核范围、首次失败和未完成项见[v431_r3_verification.md](v431_r3_verification.md)；精简审阅包附配置、实际命令、支持表、相关代码、少量原始成对测量与自然轨迹、费用和commit/hash，无权重和凭据。

## 已确认限制与未完成项

实际有效fit为51 parent、gate20、acq16（角色清单分别为54/21/18）。获取LOPO每折只剩15 parent，低于16门槛，两个lambda的CV效用均为0；lambda=0来自已登记平局规则，不能称费用权重已被有力验证。

继承尺度限制：`v43/p2.py`从整个source TRAIN计算MASE常数，ETTm1[0,41808)、Solar[0,31536)、USTS[0,5595)。早期TRAIN origin在512等位置，故该常数包含其后来TRAIN观测，也包含内部gate/check/acq数据。r3将其用于d、κ及psi的尺度差归一化，不能声称所有内部预处理严格处于外层检查组之外或每个TRAIN origin严格PIT。DEV时整个TRAIN已在过去，calibration/test未参与。按本轮既定分母保持共同可比性，未在看完DEV后更换尺度重拟；此限制阻止把当前开发结果提升为严格在线金融确认。

主表预算是常驻模型的部署组件预算。两家族各7个自然在线窗口，Bolt6次选择control（12实际probe）、TimesFM6次选择H32（6实际probe），各1次STOP；自然hot与11请求分摊完整进程成本超支均为0。完整进程墙钟分别26.271817/27.357047秒，模型启动9.057486/9.410971秒，单次冷启动已超过3.5秒，不将分摊延迟写成单请求冷启动达标。两个受控B0请求仍必须最终预测，真实超支保留；工具后故障是受控注入，不能当自然故障率。

只读原始完整金融记录、受控删除和已核价格/利率字段；自然缺口、严格历史发布/复权vintage、独立金融确认、近期baseline官方完整预算复现仍未完成。本轮候选及监督已冻结以便复核，但开发晋升条件不满足，calibration/test继续封存；不增加配置或用确认集挽救开发失败。

完整事后预算核对见`complete_cost_audit.json`；未带预算准入的原生固定方法/TATO也按实际秒数统计low/high超支，绝不将缺flag当0。
