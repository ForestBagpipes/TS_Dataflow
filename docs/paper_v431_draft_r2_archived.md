# IntroAct-TS: A Financial Data Governance Agent for Time Series Foundation Models

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

| 模型 | 方法 | MASE ↓ | 批量秒/窗 |
|---|---|---:|---:|
| bolt | EXISTING_SAME_EVIDENCE_CART | 1.136486 | 0.657985 |
| bolt | FIXED_ACQUIRE_CART_high | 1.214872 | 0.472348 |
| bolt | FIXED_REFERENCE | 1.157005 | 0.120142 |
| bolt | FIXED_TSICL | 1.157005 | 0.120142 |
| bolt | KEEP | 1.258454 | 0.089880 |
| bolt | R2_AGENT_high | 1.157005 | 0.122043 |
| timesfm | EXISTING_SAME_EVIDENCE_CART | 1.069086 | 1.072156 |
| timesfm | FIXED_ACQUIRE_CART_high | 1.069398 | 0.340510 |
| timesfm | FIXED_REFERENCE | 1.096135 | 0.230020 |
| timesfm | FIXED_TSICL | 1.096135 | 0.230020 |
| timesfm | KEEP | 1.139837 | 0.200703 |
| timesfm | R2_AGENT_high | 1.069398 | 0.340542 |
| bolt | TATO_8_NATIVE_SPACE | 1.685227 | 0.703174 |
| timesfm | TATO_8_NATIVE_SPACE | 1.529002 | 1.023989 |

Bolt修正后全部STOP，等于固定参照，是工程正确性。TimesFM r2有开发收益但与固定mask CART同效果，主动取证额外贡献未成立。旧全证据CART更低点估计不能归为新机制。主表与论文同由`v431_r2_report.py`填入，配对区间按source和时间parent块统计，完整数据见[共同表](v431_r2_main_table.md)。

| 家族 | 拟合parent | 全证据检查MASE | 同子集固定参照 |
|---|---:|---:|---:|
| bolt | 18 | 1.390925 | 1.328637 |
| bolt | 37 | 1.390925 | 1.328637 |
| bolt | 75 | 1.334069 | 1.328637 |
| timesfm | 18 | 1.226401 | 1.162536 |
| timesfm | 37 | 1.226401 | 1.162536 |
| timesfm | 75 | 1.150880 | 1.162536 |

18/37/75拟合parent使用同一17-parent检查集，另18获取parent保持隔离；100%预先指定，不据曲线选最优比例。支持增大改善检查误差，但获取树仍无法形成两个各16parent叶。数据支持和证据特征分辨力不能以大量相关变体替代。

## 金融条件与外推限制

本地Oil为Brent现货报价，USTS目标为Kim–Wright拟合一年后远期利率，不将二者泛称同一种成交价格。作者快照与本地train逐值一致，实际发布时间和历史修订无法完全恢复，不宣称严格PIT。自然NaN可能混合无记录/休市/不可用，尚无可靠自然缺口分类。

独立附表在既有原始split边界内，取保留真实日期及行映射的全字段有记录事件，H按观测事件而非原B日网格计；它是预登记完整案例子集及受控删除实验，重跑所有共同对照，不能与旧表横比，也不能代表自然金融缺口或全部原始数据。完整有效输入五臂应no-op，同预测不是治理提升。未来日期/存在模式只归evaluator，未进入agent。

| 家族 | 方法 | 条件/范围 | MASE ↓ | 秒/窗 |
|---|---|---|---:|---:|
| bolt | EXISTING_SAME_EVIDENCE_CART | 全部 | 3.088108 | 5.145917 |
| bolt | FIXED_ACQUIRE_CART_high | 全部 | 3.069683 | 3.733802 |
| bolt | FIXED_ACQUIRE_CART_low | 全部 | 2.820959 | 1.466814 |
| bolt | FIXED_REFERENCE | 全部 | 3.069683 | 1.184308 |
| bolt | FIXED_TSICL | 全部 | 3.069683 | 1.184308 |
| bolt | KEEP | 全部 | 2.820959 | 0.475021 |
| bolt | R2_AGENT_high | 全部 | 3.069683 | 1.186296 |
| bolt | R2_AGENT_low | 全部 | 3.069683 | 1.186422 |
| bolt | TATO_NATIVE_8TRIALS_OBSERVED_LINEAR | 全部 | 4.698655 | 1.034955 |
| timesfm | EXISTING_SAME_EVIDENCE_CART | 全部 | 4.890237 | 4.347875 |
| timesfm | FIXED_ACQUIRE_CART_high | 全部 | 4.890237 | 1.575240 |
| timesfm | FIXED_ACQUIRE_CART_low | 全部 | 4.890237 | 1.575307 |
| timesfm | FIXED_REFERENCE | 全部 | 5.212728 | 0.956247 |
| timesfm | FIXED_TSICL | 全部 | 5.212728 | 0.956247 |
| timesfm | KEEP | 全部 | 5.225872 | 0.247486 |
| timesfm | R2_AGENT_high | 全部 | 4.890237 | 1.575274 |
| timesfm | R2_AGENT_low | 全部 | 4.890237 | 1.575391 |
| timesfm | TATO_NATIVE_8TRIALS_OBSERVED_LINEAR | 全部 | 4.980245 | 1.396753 |


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
