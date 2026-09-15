# v4.3.1-r5 实际交付报告

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

| 家族 | 方法 | MASE ↓ | 账本秒/窗 | 超预算 |
| --- | --- | --- | --- | --- |
| bolt | FIXED_A0_NATIVE_high | 1.258454 | 0.089821 | 0 |
| bolt | FIXED_A2_SINGLE_high | 1.157005 | 0.116324 | 0 |
| bolt | FIXED_COUNT_2_high | 1.181290 | 0.183072 | 0 |
| bolt | FIXED_ORDER_3_high | 1.226845 | 0.253486 | 0 |
| bolt | LEGACY_CART_H_high | 1.168004 | 0.195538 | 0 |
| bolt | LEGACY_DIRECT_control_high | 1.146635 | 0.279529 | 0 |
| bolt | R2_EXISTING_CART_high | 1.136486 | 0.655479 | 0 |
| bolt | R4_FREE_COVERAGE_high | 1.152415 | 0.113136 | 0 |
| bolt | R4_JOINT_high | 1.154124 | 0.196145 | 0 |
| bolt | R5_RAW_high | 1.152415 | 0.114238 | 0 |
| bolt | R5_SINGLE_high | 1.152415 | 0.114236 | 0 |
| bolt | R5_high | 1.152415 | 0.114237 | 0 |
| bolt | TATO_NATIVE_8_high | 1.685227 | 0.676848 | 0 |
| bolt | TRAIN_BEST_FIXED_FLOW_high | 1.154554 | 0.198152 | 0 |
| timesfm | FIXED_A0_NATIVE_high | 1.139837 | 0.196681 | 0 |
| timesfm | FIXED_A2_SINGLE_high | 1.096135 | 0.222397 | 0 |
| timesfm | FIXED_COUNT_2_high | 1.083706 | 0.373463 | 0 |
| timesfm | FIXED_ORDER_3_high | 1.085207 | 0.535471 | 0 |
| timesfm | LEGACY_CART_H_high | 1.069398 | 0.580216 | 0 |
| timesfm | LEGACY_DIRECT_control_high | 1.095305 | 0.582770 | 0 |
| timesfm | R2_EXISTING_CART_high | 1.069086 | 1.066250 | 0 |
| timesfm | R4_FREE_COVERAGE_high | 1.069398 | 0.219311 | 0 |
| timesfm | R4_JOINT_high | 1.069398 | 0.580257 | 0 |
| timesfm | R5_RAW_high | 1.072391 | 0.374219 | 0 |
| timesfm | R5_SINGLE_high | 1.074180 | 0.386583 | 0 |
| timesfm | R5_high | 1.074244 | 0.386979 | 0 |
| timesfm | TATO_NATIVE_8_high | 1.529002 | 0.999094 | 0 |
| timesfm | TRAIN_BEST_FIXED_FLOW_high | 1.069398 | 0.580168 | 0 |

## 固定查询轨迹的机制表

CURRENT四种评分保持完全相同查询轨迹和原始评分。FREE/HISTORY改变信息，HISTORY额外支付历史模型费；不能将其当同成本比较。完整输入保持KEEP。

| 家族 | 方法 | MASE ↓ | 账本秒/窗 | 超预算 |
| --- | --- | --- | --- | --- |
| bolt | MECH_CURRENT_FULL | 1.226845 | 0.253519 | 0 |
| bolt | MECH_CURRENT_PAIR | 1.228042 | 0.251720 | 0 |
| bolt | MECH_CURRENT_RAW | 1.228042 | 0.251026 | 0 |
| bolt | MECH_CURRENT_SINGLE | 1.228042 | 0.251056 | 0 |
| bolt | MECH_FREE_RAW | 1.412477 | 0.251027 | 0 |
| bolt | MECH_HISTORY_RAW | 1.179009 | 0.442365 | 0 |
| timesfm | MECH_CURRENT_FULL | 1.085207 | 0.535496 | 0 |
| timesfm | MECH_CURRENT_PAIR | 1.089609 | 0.526898 | 0 |
| timesfm | MECH_CURRENT_RAW | 1.084789 | 0.526191 | 0 |
| timesfm | MECH_CURRENT_SINGLE | 1.089609 | 0.526222 | 0 |
| timesfm | MECH_FREE_RAW | 1.077708 | 0.526193 | 0 |
| timesfm | MECH_HISTORY_RAW | 1.088962 | 0.888182 | 0 |

FULL−RAW的90%描述性source/parent时间块区间：Bolt −0.001197 [−0.003590,0]，TimesFM +0.000418 [+0.000128,+0.000926]。Bolt改善仅来自同一个ETTm1 parent的两个相关变体；TimesFM三个改变窗口都退步。固定轨迹至少三个不同预测的覆盖Bolt103窗/26parent、TimesFM102窗/25parent。收益向量平方误差分别5.130355→5.129511、1.212782→1.203550。该数学/评分性质不能升级为最终任务收益。

## 真实在线与完整费用

每家族44请求：3个TRAIN固定路径吞吐测量、38自然请求、3受控分支。自然取证不代表自然缺口。低预算0.8140623268639832秒，高预算3.5秒。

| 家族 | 预算 | 请求/自然取证 | 平均秒 | P95秒 | 最大秒 | 超支/失败 |
| --- | --- | --- | --- | --- | --- | --- |
| bolt | low | 19/0 | 0.198203 | 0.720163 | 1.346169 | 1/0 |
| bolt | high | 19/0 | 0.098390 | 0.147643 | 0.150280 | 0/0 |
| timesfm | low | 19/10 | 0.330497 | 0.555525 | 1.049711 | 1/1 |
| timesfm | high | 19/12 | 0.392487 | 0.680643 | 2.441758 | 0/0 |

Bolt模型加载8.131706秒、完整进程24.330024秒；TimesFM加载7.747072秒、进程31.187600秒。首次TRAIN三版本分别1.008279/2.474587秒，只测吞吐，没有按其表现选方法。

拟合及gate冻结3.704531秒，DEV账本评估14.143840秒、金融0.914863秒。离线预测新增0，复用了已发生计算且保留原发票；真实在线推断另记，不能写成总实验成本为零。冷启动、进程其他开销、训练与请求不得混算。

## 失败、超支与回退

Bolt自然低预算金融一例1.346169秒超支；TimesFM自然低预算一例1.049711秒，剩余时间不足使求解超时，保留前一次合法动作。高预算自然请求无超支。两个零预算受控请求仍付出真实最终预测费用并标预算未满足；两个取证后故障受控请求保留前一版本和已发生费用。不是所有请求都满足预算。

固定轨迹完整FW分别14/15次达到迭代上限，最大gap分别0.002538/0.004460，作为带余项近似解保留。数据准备首次因NumPy整数JSON序列化失败，修复仅存储后重跑，失败目录保留。全部最终在线预测与对应已执行版本数值一致；dtype/hash差异单独核验，不能靠名称匹配。

## 金融条件

| 家族 | 方法 | MASE ↓ | 账本秒/窗 | 超预算 |
| --- | --- | --- | --- | --- |
| bolt | FIXED_A0_NATIVE_high | 2.820959 | 0.457274 | 0 |
| bolt | FIXED_A2_SINGLE_high | 3.069683 | 0.980261 | 0 |
| bolt | R4_FREE_COVERAGE_high | 3.042476 | 0.700892 | 0 |
| bolt | R5_high | 3.042476 | 0.701972 | 0 |
| timesfm | FIXED_A0_NATIVE_high | 5.225872 | 0.192058 | 0 |
| timesfm | FIXED_A2_SINGLE_high | 5.212728 | 0.714782 | 0 |
| timesfm | R4_FREE_COVERAGE_high | 4.890237 | 0.435840 | 0 |
| timesfm | R5_high | 4.890106 | 0.851277 | 0 |

仅Brent Europe现货报价与Kim–Wright拟合远期利率两个parent、12相关变体，部分重叠旧DEV，非独立确认。Bolt原生KEEP明显强于r5；TimesFM微小差异不足支持金融泛化。完整观测、受控删除分别记录；可验证自然缺口仍缺项，日历、发布时间和历史vintage不足以宣称严格point-in-time。自然查询不是自然缺口验证，有效观测与真实跳变不覆盖。

## 基线、主实验准备与论文边界

已真实执行的近期对照仍是TATO两家族8trial适配。TimesFM旧1248trial中的546长度失败追溯至trimmer seq_l×32超过历史320/416，未删除失败或改称官方完整搜索。500训练实例/500trial场景级入口与8来源主矩阵已准备，完整官方运行未完成。已取得7来源元数据/文件；Weather以及独立区间重叠、缺口mask和许可核验以main-preparation最新状态为准，未将几何容量当真实样本。TimesFM-3、Chronos-2未执行，不能列为已击败对手。

当前支持：冻结TSFM治理的可执行、输入保护及费用审计；无需未来标签的联合收益可行域及近似投影误差关系；旧DEV上评分误差降低而动作选择可能恶化的经验负结果。不支持：联合约束预测优势、主动取证优势、金融泛化、独立确认、SOTA或录用保证。三角不等式、凸包、投影与FW为已有方法。

主实验准备继续，但r5方法实验准入失败，不能解封确认集挽救开发结果。下一步收口基线与未用来源/时间块协议，保持r5冻结，不增加特征或模型搜索。

提交和审阅包SHA见版本台账/交付清单；本文由实际账本生成，数字不依赖聊天转述。

## 在线真实返回的任务结果补表

低预算真实费用改变TimesFM七条自然轨迹，不能拿离线主表代替。以下输出均在最终预测写盘后独立评分；主集合只是按元数据选择的7窗验收子集，不代表完整DEV。

| 家族 | 集合/预算/条件 | 窗/parent | 实际MASE | KEEP | 免费参照 |
| --- | --- | --- | --- | --- | --- |
| bolt | main/low/all | 7/7 | 1.135352 | 1.194534 | 1.135352 |
| bolt | main/low/controlled_deletion | 7/7 | 1.135352 | 1.194534 | 1.135352 |
| bolt | main/high/all | 7/7 | 1.135352 | 1.194534 | 1.135352 |
| bolt | main/high/controlled_deletion | 7/7 | 1.135352 | 1.194534 | 1.135352 |
| bolt | financial/low/all | 12/2 | 3.042476 | 2.820959 | 3.042476 |
| bolt | financial/low/complete_observed | 4/2 | 2.947084 | 2.947084 | 2.947084 |
| bolt | financial/low/controlled_deletion | 8/2 | 3.090172 | 2.757896 | 3.090172 |
| bolt | financial/high/all | 12/2 | 3.042476 | 2.820959 | 3.042476 |
| bolt | financial/high/complete_observed | 4/2 | 2.947084 | 2.947084 | 2.947084 |
| bolt | financial/high/controlled_deletion | 8/2 | 3.090172 | 2.757896 | 3.090172 |
| timesfm | main/low/all | 7/7 | 1.116049 | 1.069442 | 1.105792 |
| timesfm | main/low/controlled_deletion | 7/7 | 1.116049 | 1.069442 | 1.105792 |
| timesfm | main/high/all | 7/7 | 1.059280 | 1.069442 | 1.105792 |
| timesfm | main/high/controlled_deletion | 7/7 | 1.059280 | 1.069442 | 1.105792 |
| timesfm | financial/low/all | 12/2 | 4.890366 | 5.225872 | 4.890237 |
| timesfm | financial/low/complete_observed | 4/2 | 4.586061 | 4.586061 | 4.586061 |
| timesfm | financial/low/controlled_deletion | 8/2 | 5.042518 | 5.545777 | 5.042324 |
| timesfm | financial/high/all | 12/2 | 4.890106 | 5.225872 | 4.890237 |
| timesfm | financial/high/complete_observed | 4/2 | 4.586061 | 4.586061 | 4.586061 |
| timesfm | financial/high/controlled_deletion | 8/2 | 5.042129 | 5.545777 | 5.042324 |

两次自然超支的预测封装墙钟远大于原服务GPU runtime且load_seconds为0；进程/IPC/调度等剩余墙钟原因未进一步定位，不能归因模型冷启动或FW独自耗时。全部费用和超时保留。
