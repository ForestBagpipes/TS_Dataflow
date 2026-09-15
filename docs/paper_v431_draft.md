# IntroAct-TS: A Task-Consistent Data Governance Agent for Time Series Foundation Models

中文：面向时间序列基础模型的任务一致数据治理智能体

v4.3.1-r5开发论文草稿；研究未晋升，以下结果仅已反复使用DEV。金融为重点应用，不具备金融泛化证据。r4原稿保留归档。

## 问题与方法

在有效观测不覆盖、未来不可见、模型冻结的条件下，为不完整输入选择可执行版本及值得运行的候选。五臂保持Native、FFILL、单变量/多变量TS-ICL、context ridge；完整输入直接KEEP。免费参考先执行当前L512、H96/H192任务，轻量收益评分器读取已付费预测响应，联合几何约束评分，预算控制器最多运行三个版本，最终直接提交其中一个原生预测。没有融合输出、预测后修正或骨干训练。

参考策略采用fit内parent隔离向前交叉拟合，监督为真实未来MAE差除以origin合法S，未来标签只在TRAIN监督/独立离线评估出现。部署未知评分mask时使用全部lead折点共同凸包，不偷读未来非空位置。求解器记录FW gap与时间限制，失败保留上一次有效决策并支付费用。

对真实同任务收益向量g，精确欧氏投影保证整体向量平方误差不增；近似解有2gap余项。该性质不保证逐坐标改善、排序或最终MASE改善。当前实验恰好显示评分误差下降仍可能选择更差动作。

## 实验

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

固定同查询机制：

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

旧DEV26parent/156变体，不能当156个独立样本。R2信息不同；TATO8trial不等完整复现。主候选TimesFM弱于冻结TRAIN强简单流程；Bolt等免费参考。联合约束和主动调用贡献均未成立，主实验准入失败。金融仅2parent，Bolt KEEP比治理强；自然缺口缺项。确认集封存。

## 与已有研究的关系及局限

TATO、Task-oriented Time Series Imputation和TS-ICL已研究任务导向输入治理；Forecast with Forecasts等已使用预测输出信息；DIME、Amortized Bayesian Experimental Design for Decision-Making、Loss-Conditioned State Execution涉及决策证据与计算选择。凸投影、损失向量几何及Frank-Wolfe不是本文发明。文献逐项来源与边界见v431_r5_literature.md和novelty_matrix.md。

本轮新测量/约束的可实现性已验证，独有预测增量待验证且当前DEV不支持。不能将工程正确性、oracle空间、自然调用或评分误差性质包装为SOTA。不宣称零样本跨家族迁移、金融point-in-time或TSFM适配训练收益。

# r5 方法与论证正文（供论文生成器引用）

## 研究问题与可观测状态

给定预测时点 t 前可获得的多变量输入 X、观测掩码 M、可用时间元数据及预测跨度 H，冻结基础模型 F 的参数。治理动作 a 只修改允许填补的输入位置，生成合法版本 X^(a)，随后取得当前任务预测 p_a=F(X^(a))。有效观测不覆盖；完整有效目标按契约直接 KEEP。Native KEEP、FFILL、单变量 TS-ICL、多变量 TS-ICL、context ridge 构成固定动作目录；不支持的动作保留请求身份、实际别名与费用。

部署状态只包括当前免费描述、已经执行版本的预测和已付成本。未来目标、未来评分mask及未执行候选预测不能进入此状态。历史probe的内部任务与当前L512/H96或H192任务不等同。这里的任务是选择输入版本，不是预测器路由或预测融合。

训练和几何计算使用当前origin可见的正尺度 S_t；对外报告另用外层TRAIN冻结的MASE分母。前者按可见季节差分对、lag-1差分、MAD及固定下限顺序确定，记录支持和回退。两者不互换；历史预测的输入处理不得使用更晚origin的尺度。

## 当前任务响应与收益评分

免费参考策略首先选择并真实执行 a_0。对已查询候选 a，七项响应为 p_a−p_0 的有符号均值、平均绝对值、最大绝对值、前半/后半平均绝对值、沿lead线性趋势及末lead差，均除以 S_t。原始收益评分器采用动作截距和共享ridge斜率，监督是合法TRAIN当前任务的 MAE(p_0)−MAE(p_a)，再除以 S_t。预测差特征和任务收益监督各有先例；它们本身不构成原创主张。

免费参考在fit内按同来源、完整读取区间和parent进行forward/purge交叉拟合。未来监督区间必须在被预测训练parent的读取起点之前；相关变体不跨组。同来源较早TRAIN支持不足16parent时使用登记回退，不使用本parent标签补支持。最终参考与评分器只用fit，正则0.1/1/10与调用价格0/0.01/0.1在gate选择；每家族规则相同、参数分别拟合。源、parent、变体逐层等权，重复扰动不扩张parent支持。

## 无未来标签的收益向量约束

对已查询集合 Q，参考编号为0。令

\[
\ell(p,y)=\sum_{h=1}^{H}w_h|p_h-y_h|/S_t,\qquad
 g_a(y)=\ell(p_0,y)-\ell(p_a,y),\quad g_0=0.
\]

权重非负、和为1，且各动作使用同一目标和同一评分规则。若权重在预测前未知，不以查看未来有效mask确定它们。

绝对损失给出必要距离约束 |g_a−g_b|≤D_ab。已知固定权重时 D_ab 为加权预测绝对距离；未知评分位置时使用 max_h|p_a,h−p_b,h|/S_t。单臂区间截断和全部成对距离约束作为独立简单对照。

对每个lead，在所有已查询预测值 b 处构造折点向量

\[
 v_{h,b,a}=(|p_{0,h}-b|-|p_{a,h}-b|)/S_t.
\]

实际lead收益曲线在相邻折点间线性、两端常数。因此所有可能真实收益都在这些折点的凸包内。已知固定权重时使用各lead凸包的加权Minkowski和 C；未知权重时使用全部lead折点的共同凸包 C_unknown。后者允许更宽的收益组合，代价是约束更保守。这里是包含真实收益的凸可行外包，不声称每个凸组合都对应某个实际未来序列。

将原始评分 r 投影到对应集合，仅校正评分，不修改任何预测。参考坐标保持0；校正收益最大者若非正则保留参考。其余并列采用预登记动作顺序。最终输出始终为一个已执行版本的原生预测。

## 数值求解与性质

主实验使用unknown集合。Frank–Wolfe初始化 z=0；每个lead最小/最大折点向量互为相反数，因而0属于其凸包。线性oracle按当前梯度选折点，已知权重时逐lead选择后加权求和，未知权重时在全部折点中选一个。令 d=s−z、gap=〈z−r,z−s〉，精确线搜索步长为 clip(gap/||d||²,0,1)。实现固定最多2048次迭代、gap容差1e-8、每次求解配置0.05秒软时限，并记录实际gap、耗时和状态；逐迭代检查不能抢占正在进行的NumPy/SLSQP调用，因此不是硬实时上界。

对任意集合内真实收益g，精确欧氏投影 z 满足

\[
\|z-g\|^2\le\|r-g\|^2-\|r-z\|^2.
\]

理由是投影的一阶最优条件 〈z−r,g−z〉≥0，加上范数展开。对FW可行近似解，有 〈z−r,g−z〉≥−gap，同样展开得到右侧增加2gap的关系。凸投影及FW为已有数学工具；该性质仅控制整个向量平方误差，不保证逐坐标误差、动作排名、MASE或逐请求无害。迭代上限返回带gap近似；超时和非有限输入导致保留上次有效决策并停止。

两个不同预测时约束可能退化为区间。高阶证据必须在至少三个数值不同预测的共同支持子集分析；不同dtype/hash不自动计为不同预测。

## 选择性执行与完整费用

预查询先验 μ_a 只读免费信息和已执行参考预测。当前已查询最大校正收益为m，下一动作按 μ_a−m−λC_est(a) 排序。只有该值为正且整个分支可容纳于剩余预算时才执行，否则STOP。主候选最多参考加两个候选动作请求；别名或相同输入去重后独特预测可能少于三个；该规则是成本敏感启发式，不是最优信息价值定理。

可执行步骤如下：

1. 计算合法免费状态与S_t；完整输入选择KEEP，否则由冻结免费参考选择动作。
2. 物化并执行参考预测，记录实际输入、mask、checkpoint/revision、dtype与费用。
3. 在尚未执行动作中，使用先验及完整预计分支费用检查是否继续。
4. 仅在实际执行成功后揭示新预测，计算当前任务响应和联合评分；更新可提交动作。
5. 达到版本上限、下一可行候选的先验净效用非正、预算不足或执行/求解失败则停止，输出上次有效已执行预测。已查询最大校正收益非正只使当前提交保持参考，不单独禁止继续查询。

费用包括预处理、策略、物化、模型、求解和输出。每新增候选预留0.051秒决策/求解费用，输出另预留0.001秒。物化后才可按真实输入身份共享预测；未查询候选不能通过缓存先泄露。已发生成本不在最终动作排名中再次惩罚。预算不足以支付首个预测时仍报告预算未满足，不将STOP算成零费用。预计费用不能保证真实墙钟；超支、首次惰性分支和失败费用完整保留。

## 证据层级与当前否定结果

共同开发比较回答三件不同的事：相同查询集合下评分约束是否有增量；相同复用条件下选择性执行是否优于固定流程；完整方法是否优于TRAIN预先选定强简单对照。r5在这些开发门槛上没有取得共同支持。Bolt完整方法等于免费参照；TimesFM完整方法弱于免费流程；固定轨迹投影虽降低向量误差，却在TimesFM上恶化最终MASE。不会将自然调用或可行oracle空间替代方法收益。

旧DEV只有26parent，并已反复使用；描述性区间按来源和parent块处理相关变体，不解释为新确认检验。金融仅两个parent且部分重叠旧DEV，无可验证自然缺口，无法支持金融泛化。公开主矩阵准备和后续强基线复核不改变这些边界。只有新候选将来按原登记满足条件并冻结后，才能依既定规则进入独立确认；本轮不解封。

## 共同统计图

![r5与强简单流程及同查询评分对照](figures/v431-r5/development_differences.svg)

图由同一统计JSON生成，没有额外训练或选择窗口。区间仅对已观察来源内部的parent时间块重采样；USTS只有一个parent，无法估计该来源的时间不确定性。部分区间退化成点反映支持不足，不能解释为没有不确定性。脚本为`v431_r5_plot.py`，保留PDF/SVG及对应数值和输入hash。

高预算自适应路径实际至少三个不同预测的覆盖为Bolt0窗、TimesFM9窗；固定轨迹机制实验的103/102窗覆盖是另一种实验条件。TimesFM离线高预算另有1次求解超时回退，主表已保留；不能把它与真实在线低预算超时混为同一事件，也不能将固定轨迹覆盖外推为实际主动调用覆盖。


## 关机前追加的基线与准备状态

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
