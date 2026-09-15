# IntroAct-TS: A Financial Data Governance Agent for Time Series Foundation Models

中文：面向时间序列基础模型的金融数据治理智能体

v4.3.1-r3开发论证草稿；尚无SOTA或独立确认声明。

## 背景与定义

真实金融价格可以正确，跳变不能自动视为错误。对于确有观测覆盖不足的输入，治理改变固定TSFM使用的信息，但更低插补误差不必然改善预测。本项目研究未来不可见、验证计算有限时，如何取得证据、选择保留或治理，并停止。备份仅工程恢复能力，不承担创新主张。动作在同一target/context边界/horizon/checkpoint上比较任务MASE，未来标签只在合法训练或冻结后评价命名空间中使用。

## 完整方法

固定五臂为Native KEEP、FFILL、单变量TS-ICL、多变量TS-ICL和context ridge；有效观测不覆盖，没有预测后残差臂。A4不支持时原函数明确回Native，历史Collector丢失detail的缺项由独立support账本补齐，不能把此别名当成功ridge。

无证据使用75个训练parent内选定的每家族固定TS-ICL参照，完整target直接KEEP。主状态模型用54 fit、21 gate，17 check和18 acq保持隔离。H32、目标H、同origin长短控制分别有对应可见状态；未知响应不填零。当前dirty先截历史前缀，当前缺口按距origin位置复制，再分别治理；仅使用当时可用协变量和当前可见历史目标，覆盖至少max(16,ceil(Hq/2))。H96/192的long为416/320步，short为352/256步。历史匹配H仍不等于匹配部署L512。

d_long=(MAE_reference,long−MAE_action,long)/S_t；d_short同尺度；κ=d_long−d_short；z=((512−Lq)/64)κ。S_t为既有正TRAIN MASE尺度，跨动作和长短固定。κ是整条治理管线对更早观测的有符号响应，不是市场因果效应或已证线性外推律。

共享低维ridge拟合Δ_t−d_long，预测时在原MASE单位加回d_long；每动作截距、共享斜率、fit-only标准化，alpha仅0.1/1/10在gate选。直接收益ridge使用同输入/容量/搜索预算，CART同已取得证据。分歧对照严格用旧probe.py的mean_t std_view(raw predictions)/S_t，不以abs(κ)/2冒充。等次数普通回测在r和r−64两个origin，与控制的同origin不同长度区分；两者真实秒数不必相同，预算按完整分支检查。

冻结所有终态和支持规则后，在18独立acq parent用同一冻结策略计算停止与取得证据后的真实任务损失差，扣完整部署成本差。获取器最多一次决策，选H32/H/control或STOP，原low0.8140623268639832秒/high3.5秒及lambda规则不改。只在预计净值>0、工具适用且预算可行时取证；所有失败费用和最终动作/预测费用保留。部署不预先取得全池候选或隐藏probe结果。

## 相关工作和增量归因

TATO已有冻结TSFM输入变换搜索，Task-oriented Imputation已有下游收益治理，DIME/TNDP已有成本敏感信息获取和决策效用实验设计，CSDI/ImputePilot已有插补与选择流程，嵌套上下文和旧项目multiview均有先例。具体primary链接和必要消融见[创新矩阵](novelty_matrix.md)；不把组合模块、ridge残差写成原创或继承理论保证。拟检验增量只在有符号测量是否比通用证据更有助实际治理，以及获取是否比固定取证更好。

## 实际结果解释

bolt：完整agent MASE 1.156351，训练固定参照 1.157005，同冻结固定取证 1.156351；组件秒/窗分别 0.284957/0.120142/0.284946。

timesfm：完整agent MASE 1.102669，训练固定参照 1.096135，同冻结固定取证 1.096019；组件秒/窗分别 0.600939/0.230177/0.592392。

Bolt主动与固定取证在156/156个窗口动作和预测完全相同；TimesFM主动较固定取证退步，主DEV主动贡献不成立。两家族响应均未胜原始预测分歧，且未一致优于等次数回测、同容量直接回归或同证据CART，不能保留“有符号响应已证明独有增量”的主张。新表Bolt同容量DIRECT_control为1.146643；TimesFM普通CART_H32/H为1.069398，更简单对照已具有较强点估计。旧r2同证据CART作为继承完整原生方法另列，其信息与新control状态不同，不混作同信息消融。

训练支持已覆盖原三来源登记边界内110个独立parent。学习曲线13 fit低于16支持阈值，全部回参照；27→54 fit时Bolt控制状态检查MASE从1.334370变为1.339151，TimesFM从1.155641变为1.153286，不能笼统归因于“再加数据就会有效”。实际每工具仅16个有效acq parent，获取树均为常数根叶；当前自然调用依赖已学工具均值、适用性与预算，并未学出逐窗分裂规则。

预登记未见位置×H192的17-parent检查：TimesFM agent1.260234、固定取证1.288577、固定参照1.318134，但与随机1.267781的分组区间仍跨零；Bolt agent1.190724与固定取证完全相同。该局部结果是内部检查，不推翻主DEV结论，也不是独立确认。

金融两parent附表：Bolt agent3.103498劣于固定参照3.069683；TimesFM agent4.920632低于参照5.212728和固定取证5.139345，但8/12窗口实际超出3.5秒预算，不能认定同预算优势。原始完整输入五臂保持同输入/同预测，只支持观测保留；自然缺口和严格历史可用版本验证仍缺项。

## 共同实验

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

同26个反复开发parent/156相关变体，按source和时间parent分组。表由同一汇总脚本生成，额外候选/探针不增加独立样本。外部TATO仅短预算适配，近期基线全协议复现仍不完整，不能称SOTA。支持及模块配对归因见[r3报告](v431_r3_report.md)。

## 模块消融与主张边界

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

## 金融验证范围

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

## 适用条件与限制

原[230,281)缺口的H192短上下文放不完整，按unsupported回退，不能移动缺口制造支持。长短响应不是因果量，跨L/H预测收益迁移需要单独验证。训练内新位置×H只作固定check，不能当独立DEV确认；完整观测no-op不提供预测提升。主动全STOP、工具后动作不变或与固定流程同效均应作为负结果。在线强制分支只验工程。

当前没有方法晋升，PICS_joint_relabel保持历史incumbent。calibration/test继续封存；不将未完成实验、开发胜出、环境验收或工程测试写成ICLR录用或SOTA证据。

## 证据符号与排序诊断

| 家族 | 状态 | parent/窗 | 历史符号一致率（含零） | 双方非零一致率 | 当前零收益/非参照比较 | 历史排序错误损失 |
|---|---|---|---:|---:|---|---:|
| bolt | H | 25/150 | 73.282% | 59.923% | 200/600 | 0.059130 |
| bolt | H32 | 25/150 | 72.971% | 59.456% | 200/600 | 0.119024 |
| bolt | control | 25/100 | 81.209% | 62.419% | 200/400 | 0.054576 |
| timesfm | H | 25/150 | 72.119% | 58.178% | 200/600 | 0.034430 |
| timesfm | H32 | 25/150 | 65.936% | 48.904% | 200/600 | 0.095826 |
| timesfm | control | 25/100 | 77.618% | 55.235% | 200/400 | 0.041701 |

排除恒零参照臂；零收益独列，含零一致率不是治理有效率。排序错误损失为按历史收益选臂在当前任务相对固定参照造成的损失；完整五臂oracle排序遗憾只在机器诊断表中，不是方法成绩。不同状态支持范围不同，因果归因仍须用共同支持机制表。

## 冻结状态和协议限制

实际有效fit为51 parent、gate20、acq16（角色清单分别为54/21/18）。获取LOPO每折只剩15 parent，低于16门槛，两个lambda的CV效用均为0；lambda=0来自已登记平局规则，不能称费用权重已被有力验证。

继承尺度限制：`v43/p2.py`从整个source TRAIN计算MASE常数，ETTm1[0,41808)、Solar[0,31536)、USTS[0,5595)。早期TRAIN origin在512等位置，故该常数包含其后来TRAIN观测，也包含内部gate/check/acq数据。r3将其用于d、κ及psi的尺度差归一化，不能声称所有内部预处理严格处于外层检查组之外或每个TRAIN origin严格PIT。DEV时整个TRAIN已在过去，calibration/test未参与。按本轮既定分母保持共同可比性，未在看完DEV后更换尺度重拟；此限制阻止把当前开发结果提升为严格在线金融确认。

主表预算是常驻模型的部署组件预算。两家族各7个自然在线窗口，Bolt6次选择control（12实际probe）、TimesFM6次选择H32（6实际probe），各1次STOP；自然hot与11请求分摊完整进程成本超支均为0。完整进程墙钟分别26.271817/27.357047秒，模型启动9.057486/9.410971秒，单次冷启动已超过3.5秒，不将分摊延迟写成单请求冷启动达标。两个受控B0请求仍必须最终预测，真实超支保留；工具后故障是受控注入，不能当自然故障率。

只读原始完整金融记录、受控删除和已核价格/利率字段；自然缺口、严格历史发布/复权vintage、独立金融确认、近期baseline官方完整预算复现仍未完成。本轮候选及监督已冻结以便复核，但开发晋升条件不满足，calibration/test继续封存；不增加配置或用确认集挽救开发失败。
