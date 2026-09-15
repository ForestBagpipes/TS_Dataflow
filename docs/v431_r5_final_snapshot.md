# r5 关机前交付快照

生成时间：2026-09-16T04:09:15.020832+08:00。仅汇总已落盘并独立审核的记录，未完成项保留。
r5开发准入失败，模型与配置保持冻结，不增加搜索、不解封calibration/test。PICS_joint_relabel保留历史身份。

## TATO 缩放长度单位的场景适配

| 场景 | TRAIN/DEV parent | 审计状态 | 试验/成功/失败 | MASE | 搜索秒 | 热部署秒/窗 |
| --- | --- | --- | --- | --- | --- | --- |
| bolt-h192 | 29/14 | audited_completed | 500/500/0 | 1.178885 | 821.340192 | 0.057689 |
| bolt-h96 | 29/14 | audited_completed | 500/500/0 | 1.101865 | 527.935827 | 0.038954 |
| timesfm-h192 | 29/14 | audited_completed | 500/500/0 | 1.345721 | 1695.896858 | 0.112477 |
| timesfm-h96 | 29/14 | audited_completed | 500/500/0 | 1.337974 | 1747.215826 | 0.114251 |
| solar-bolt-h192 | 22/11 | pending_frozen_and_all_saved_deployment | None/None/None | 未取得 | 未取得 | 未取得 |
| solar-bolt-h96 | 22/11 | audited_completed | 500/500/0 | 2.070091 | 357.512743 | 0.041433 |
| solar-timesfm-h192 | 22/11 | pending_frozen_and_all_saved_deployment | None/None/None | 未取得 | 未取得 | 未取得 |
| solar-timesfm-h96 | 22/11 | audited_partial | 247/247/0 | 1.241464 | 535.282539 | 0.110404 |
| us_term_structure-bolt-h192 | 3/1 | pending_frozen_and_all_saved_deployment | None/None/None | 未取得 | 未取得 | 未取得 |
| us_term_structure-bolt-h96 | 3/1 | pending_frozen_and_all_saved_deployment | None/443/None | 未取得 | 未取得 | 未取得 |
| us_term_structure-timesfm-h192 | 3/1 | pending_frozen_and_all_saved_deployment | None/None/None | 未取得 | 未取得 | 未取得 |
| us_term_structure-timesfm-h96 | 3/1 | pending_frozen_and_all_saved_deployment | None/None/None | 未取得 | 未取得 | 未取得 |

## TATO 官方96单位、当前L512约束的场景适配

| 场景 | TRAIN/DEV parent | 审计状态 | 试验/成功/失败 | MASE | 搜索秒 | 热部署秒/窗 |
| --- | --- | --- | --- | --- | --- | --- |
| bolt-h192 | 29/14 | pending_frozen_and_all_saved_deployment | None/None/None | 未取得 | 未取得 | 未取得 |
| bolt-h96 | 29/14 | pending_frozen_and_all_saved_deployment | None/None/None | 未取得 | 未取得 | 未取得 |
| timesfm-h192 | 29/14 | pending_frozen_and_all_saved_deployment | None/None/None | 未取得 | 未取得 | 未取得 |
| timesfm-h96 | 29/14 | pending_frozen_and_all_saved_deployment | None/None/None | 未取得 | 未取得 | 未取得 |

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
| bolt | TATO_SCENE_high | 39/52 | 未取得 | 0.044877 | 0 |
| timesfm | FIXED_A0_NATIVE_high | 52/52 | 1.198786 | 0.195610 | 0 |
| timesfm | FIXED_A2_SINGLE_high | 52/52 | 1.133136 | 0.230168 | 0 |
| timesfm | R2_EXISTING_CART_high | 52/52 | 1.052183 | 1.304882 | 0 |
| timesfm | R5_high | 52/52 | 1.057130 | 0.465782 | 0 |
| timesfm | REFERENCE_FREE_high | 52/52 | 1.052925 | 0.219465 | 0 |
| timesfm | TATO_NATIVE_8_high | 52/52 | 1.506187 | 0.999743 | 0 |
| timesfm | TATO_SCENE_high | 39/52 | 未取得 | 0.111884 | 0 |

缺少场景：solar-bolt-h192, solar-timesfm-h192, us_term_structure-bolt-h192, us_term_structure-bolt-h96, us_term_structure-timesfm-h192, us_term_structure-timesfm-h96。

## TATO费用分账

下表仅累计已独立审核场景；在途部分不写成零。搜索包含其中模型调用，不能再把原生模型时间重复加到搜索时间。完整子进程包含搜索、加载等阶段，不与阶段时间相加。
| 协议 | 已审场景 | 搜索秒 | 冷加载秒 | 物理调用/命中 | 外层计时覆盖/秒 |
| --- | --- | --- | --- | --- | --- |
| scenes | 6 | 5685.183985 | 23.285829 | 70771/3741 | 2/908.287683 |
| official96_scenes | 0 | 0.000000 | 0.000000 | 0/0 | 未测量 |

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
| tato-scene-extra/queue.execution.json | running | 2026-09-16T04:25:00+08:00 |
| official96-queue-status.json | waiting | 2026-09-16T04:45:00+08:00 |
| chronos2-queue-status.json | finished | 2026-09-16T04:45:00+08:00 |

服务器预定关机2026-09-16 05:04:31 Asia/Shanghai；本程序不执行关机。新重任务截至04:45，随后保存提交与审阅包。重启后不得原样复用已过期deadline覆盖旧状态。
