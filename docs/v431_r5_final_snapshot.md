# r5 最终交付快照

生成时间：2026-09-16T21:52:57.184125+08:00。仅汇总已落盘并独立审核的记录，未完成项保留。
r5开发准入失败，模型与配置保持冻结，不增加搜索、不解封calibration/test。PICS_joint_relabel保留历史身份。

## TATO 缩放长度单位的场景适配

| 场景 | TRAIN/DEV parent | 审计状态 | 试验/成功/失败/中断 | MASE | 搜索秒 | 热部署秒/窗 |
| --- | --- | --- | --- | --- | --- | --- |
| bolt-h192 | 29/14 | audited_completed | 500/500/0/0 | 1.178885 | 821.340192 | 0.057689 |
| bolt-h96 | 29/14 | audited_completed | 500/500/0/0 | 1.101865 | 527.935827 | 0.038954 |
| timesfm-h192 | 29/14 | audited_completed | 500/500/0/0 | 1.345721 | 1695.896858 | 0.112477 |
| timesfm-h96 | 29/14 | audited_completed | 500/500/0/0 | 1.337974 | 1747.215826 | 0.114251 |
| solar-bolt-h96 | 22/11 | audited_completed | 500/500/0/0 | 2.070091 | 357.512743 | 0.041433 |
| us_term_structure-bolt-h96 | 3/1 | audited_completed | 500/500/0/0 | 0.766494 | 69.852663 | 0.042954 |
| us_term_structure-timesfm-h96 | 3/1 | audited_completed | 500/500/0/0 | 1.150837 | 173.885380 | 0.115517 |
| solar-bolt-h192 | 22/11 | audited_completed | 500/500/0/0 | 2.563880 | 489.068933 | 0.054595 |
| solar-timesfm-h192 | 22/11 | audited_completed | 500/500/0/0 | 1.322594 | 983.917747 | 0.105451 |
| solar-timesfm-h96 | 22/11 | audited_completed | 500/500/0/0 | 1.246931 | 963.359102 | 0.102796 |
| us_term_structure-bolt-h192 | 3/1 | audited_completed | 500/500/0/0 | 0.819709 | 85.364614 | 0.054673 |
| us_term_structure-timesfm-h192 | 3/1 | audited_completed | 500/500/0/0 | 0.930269 | 161.948814 | 0.107002 |

## TATO 官方96单位、当前L512约束的场景适配

| 场景 | TRAIN/DEV parent | 审计状态 | 试验/成功/失败/中断 | MASE | 搜索秒 | 热部署秒/窗 |
| --- | --- | --- | --- | --- | --- | --- |
| bolt-h192 | 29/14 | audited_completed | 500/33/467/0 | 1.806359 | 68.055181 | 0.058575 |
| bolt-h96 | 29/14 | audited_completed | 500/33/467/0 | 1.254998 | 59.776859 | 0.039426 |
| timesfm-h192 | 29/14 | audited_completed | 500/33/467/0 | 1.497541 | 129.141017 | 0.112943 |
| timesfm-h96 | 29/14 | audited_completed | 500/33/467/0 | 1.408024 | 128.510358 | 0.105296 |

缩放单位为Bolt16/TimesFM32；官方单位为96。两者均为当前L512和有限TRAIN支持的适配，不是官方L1440、500个训练实例、top16/Pareto/OT完整复现。500 trial不等于500个独立parent。超时搜索可冻结已完成训练最优方案，但不能称完整500trial。原始失败保留。

## 三来源共同子集

每家族26 parent、52个target_block_10变体；与旧156变体主表不同，不得直接比较绝对MASE。未完成场景使全分母MASE保持空缺。
| 家族 | 方法 | 完成/登记窗 | MASE完整分母 | 秒/窗（已取得记录） | 超高预算 |
| --- | --- | --- | --- | --- | --- |
| bolt | FIXED_A0_NATIVE_high | 52/52 | 1.297844 | 0.089790 | 0 |
| bolt | FIXED_A2_SINGLE_high | 52/52 | 1.145283 | 0.121571 | 0 |
| bolt | R2_EXISTING_CART_high | 52/52 | 1.114892 | 0.795358 | 0 |
| bolt | R5_high | 52/52 | 1.131513 | 0.110751 | 0 |
| bolt | REFERENCE_FREE_high | 52/52 | 1.131513 | 0.110635 | 0 |
| bolt | TATO_NATIVE_8_high | 52/52 | 1.661713 | 0.671905 | 0 |
| bolt | TATO_SCENE_high | 52/52 | 1.416821 | 0.048383 | 0 |
| timesfm | FIXED_A0_NATIVE_high | 52/52 | 1.198786 | 0.195610 | 0 |
| timesfm | FIXED_A2_SINGLE_high | 52/52 | 1.133136 | 0.230168 | 0 |
| timesfm | R2_EXISTING_CART_high | 52/52 | 1.052183 | 1.304882 | 0 |
| timesfm | R5_high | 52/52 | 1.057130 | 0.465782 | 0 |
| timesfm | REFERENCE_FREE_high | 52/52 | 1.052925 | 0.219465 | 0 |
| timesfm | TATO_NATIVE_8_high | 52/52 | 1.506187 | 0.999743 | 0 |
| timesfm | TATO_SCENE_high | 52/52 | 1.222388 | 0.109582 | 0 |

缺少场景：无。

## TATO费用分账

下表仅累计已独立审核场景；在途部分不写成零。搜索包含其中模型调用，不能再把原生模型时间重复加到搜索时间。完整子进程包含搜索、加载等阶段，不与阶段时间相加。
| 协议 | 已审场景 | 搜索秒 | 冷加载秒 | 物理调用/命中 | 外层计时覆盖/秒 |
| --- | --- | --- | --- | --- | --- |
| scenes | 12 | 8077.298699 | 48.843767 | 96043/12061 | 8/3347.901091 |
| official96_scenes | 4 | 385.483416 | 16.145947 | 3884/0 | 4/417.413003 |

## Chronos-2原生KEEP敏感性

同旧DEV26 parent/156变体，先保存全部预测后独立评分。仅更换骨干原生KEEP，未训练或执行Chronos-2治理策略，不归因r5、不当第三独立家族。
| 骨干 | 方法 | MASE |
| --- | --- | --- |
| chronos-2 | Native KEEP | 0.957177 |
| bolt | R5_high | 1.152415 |
| bolt | FIXED_A0_NATIVE_high | 1.258454 |
| timesfm | R5_high | 1.074244 |
| timesfm | FIXED_A0_NATIVE_high | 1.139837 |

下载477930472字节/917.244秒；TRAIN成功完整子进程6.369213秒、DEV7.965819秒；首次记录层失败6.313467秒另计且保留。DEV104次物理调用、52次合法复用。原生GPU调用均值不能替代完整请求延迟或同预算优势。实际许可/模型revision与原始预测审核另有账本。

Chronos-2并非逐来源普遍更强：ETTm1为1.142987，弱于Native Bolt的0.997525及两个r5；Solar和单parent USTS的点估计较低。逐来源同UID表见v431_r5_final_consistency。

## 主实验准备与缺项

8来源登记286 parent（232train/54dev）、1716输入与mask契约。只读合法context与元数据，未解析封存未来标签。重叠/时间审核后104 parent未发现已知旧读取重叠或时间异常（84train/20dev），不等于已确认独立样本。Weather两个TRAIN parent时间异常保留unsupported。当前286个context无原生NaN，自然缺口轨道仍缺少验证；金融仅两个已用parent，不能支持金融泛化。

TimesFM-3只核版本与许可，未下载运行。官方完整TATO、8来源r5主矩阵及独立确认均未运行。r5未优于强简单对照，保持停止扩展。

费用说明：TRAIN搜索、下载、冷启动、请求和排队分别记账；primary TATO旧worker计时不含进程初始import，未测外层时间记未知。extra/official队列另记锁后完整子进程墙钟。TRAIN缓存保存历史首次实际计算，DEV请求缓存逐窗清空，未将离线预计算当免费在线信息。

## 队列与交接

| 队列 | 状态 | 截止 |
| --- | --- | --- |
| tato-scene-extra/queue.execution.json | finished_with_explicit_missing_or_partial | 2026-09-16T04:25:00+08:00 |
| official96-queue-status.json | finished | 2026-09-16T04:45:00+08:00 |
| chronos2-queue-status.json | finished | 2026-09-16T04:45:00+08:00 |
| tato-scene-restart-20260916/queue.execution.json | finished_with_failures | 已完成 |
| tato-scene-restart-20260916-r2/queue.execution.json | completed | 已完成 |

早期队列中的关机时间与deadline属于重启前历史记录，均未复用或覆盖。restart首次启动因解释器依赖错误在模型加载前失败并保留；r2使用预登记解释器完成5个场景。本程序不执行关机，也不把失败启动计作实验结果。

## 八来源TRAIN原生接口实测

每家族8个parent、32个请求；原完整/51点受控缺口、H96/H192。全部来自登记TRAIN输入，没有读取未来目标或计算MASE。不是r5治理成功或独立确认。
| 家族 | 请求 | 完整进程秒 | 加载秒 | 请求均值/P95/最大秒 | low/high超支 |
| --- | --- | --- | --- | --- | --- |
| bolt | 32 | 9.037680 | 3.684794 | 0.097813/0.058662/1.640939 | 1/0 |
| timesfm | 32 | 10.215027 | 4.437755 | 0.125508/0.146894/0.360361 | 0/0 |

原准备器曾多获取origin行CSV字符串但未数值解析、保存或用于特征/评分；执行前改为islice严格在origin前停止，32个冻结输入逐值相同，历史事实与旧配置保留。Electricity/Exchange/Traffic只验证行序接口，原始时钟缺失不宣称严格历史可用性。

## 合法TRAIN原生预测库

审核状态：passed。登记230个合法TRAIN parent（232减两个Weather异常），每家族920个原生KEEP请求；不读取预测目标、不计算MASE、不拟合r5，不能把230写成r5实际拟合支持。
| 家族 | 已核请求 | 完整进程秒 | 加载秒 | 热请求均值秒 | 最大秒 | low/high超支 |
| --- | --- | --- | --- | --- | --- | --- |
| bolt | 920 | 61.725627 | 3.835074 | 0.050755 | 1.541830 | 1/0 |
| timesfm | 920 | 114.301073 | 3.882193 | 0.108647 | 0.388591 | 0/0 |

只有表中已经完成审核的家族可称通过；未审核或截止未运行窗口不删除。原生预测库服务后续已登记基线准备，当前没有主矩阵方法成绩或独立确认结论。
