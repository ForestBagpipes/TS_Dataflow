# IntroAct-TS: Evidence-Seeking Data Governance for Time Series Foundation Models

状态：包含本轮真实开发结果的论证草稿，主表由同一汇总脚本维护。当前完整 agent 未超过强固定与普通 CART，不构成方法晋升、SOTA 或确认成功。

## 背景与问题
真实时序同时含数据缺陷与应保留的真实变化。治理改变TSFM可用信息；修复更接近缺口真值未必改善预测。保存原始副本提供可逆性，却未给出部署时采用哪个治理版本的决策规则。未来真值不可见、验证有计算成本，因此研究有代价的合法证据如何支持治理与停止。

## 定义
每个 episode 固定原始时间区间上的 context、future 和共同 finite 评价 mask。部署时仅可观察 dirty context、mask、按发布时间截断的辅助通道及合法频率；当前 future 的数值仅在预测落盘后的 evaluator 中可见。固定动作目录为 KEEP、FFILL、单变量 TS-ICL、多变量 TS-ICL 和 context ridge。知道动作类型不代表已取得其输出，生成和预测都必须实际执行并计费。

记初始可见统计为 z，已取得证据集合为 E，实际计算账单为 Γ，预算为 B，状态为 s=(z,E,Γ,B)。本轮基础决策只读取 13 个 dirty/as-of 统计；未取得的工具列保持 NaN，不能用离线候选值或未调用工具的预测结果补齐。训练损失 L[i,a] 是冻结目标 TSFM 在同一 future、同一评分 mask 上使用动作 a 后的 MASE。正式权重先平衡来源，再平衡该来源的独立 parent，最后分配给同 parent 的跨度/缺陷变体；不能把 156 个变体当作 156 个独立窗口。事后 oracle 仅检验候选是否有选择空间。

## 方法
训练分为按原始时间与 parent 隔离的 T_fit、T_gate、T_check、T_acq。基础树和证据提案只在 T_fit 拟合，独立 T_gate 用于审核与小范围配置选择；T_check 只报告冻结策略检查，不能据其结果继续调参。T_acq 的完整读取范围不与前三组交叉。

对基础树叶子 R，直接优化动作的真实加权任务代价：

\[
a_R=\arg\min_a\sum_{i\in R}w_iL[i,a],\qquad
J(R)=\min_a\sum_{i\in R}w_iL[i,a].
\]

从训练分位切点中选择最大化 J(R)−J(R_left)−J(R_right) 的合法分裂，平局优先单变量 TS-ICL。基础深度只比较 1/2，每个训练叶至少有 16 个独立 parent，每连续特征最多 16 个切点；不把代价矩阵压成最优动作类别后替代此目标。基础树仅用 dirty 统计，尚未生成候选的值不进入分裂。

证据细化在每个基础叶后最多添加一层。候选规则在 T_fit 提出，在该叶的独立 T_gate 可用证据窗口审核：至少 8 个验证 parent，且相对父策略收益的经验性 90% 分组 bootstrap 下界大于 0 才保留。未满足支持或收益条件、以及部署时该证据未取得，均保持父策略。另保留不剪枝消融；总深度不超过 3、终叶不超过 8。该有限样本审核不是安全证书，回到 TS-ICL 也不能保证每个窗口无害。

工具目录包含严格遮挡验证和历史预测验证。遮挡工具仅以当前可见观测点建立伪缺口，在重新治理后计算修复证据，不读取原本缺失位置的 clean 真值。历史工具以 exclusive cutoff r=512−H 建立 X[:r]，重新治理该前缀，再用当前 context 中已知的 dirty X[r:r+H] 验证；辅助通道和尺度拟合服从相同 as-of 边界。三种预登记条件分别是旧 448/480 原点 H32、r 原点 H32、r 原点完整 H；后两者共享输入和候选生成，分别计算覆盖与成本。

终态策略 π 的序列化 hash 冻结后，才在 T_acq 产生其对应的工具价值标签：

\[
v(i,q)=L[i,\pi(s)]-L[i,\pi(s+e_q)]
       -\lambda\{C_{\mathrm{acquire}}(i,q)-C_{\mathrm{STOP}}(i)\}.
\]

两端必须使用同一冻结 π 的实际选择。完整分支费用包含工具、最后实际治理动作及最终预测；共享计算按计算身份去重，不能把工具费用单独冒充完整成本差。正值、零值和负值标签全部保留；终态 hash 变化立即使旧标签失效。每个工具拟合同族深度至多 2 的回归树，叶子至少 16 个独立 parent；本次 T_acq 只有 18 个 parent，因此保持根叶，不能靠变体扩大模型容量。仅比较 λ=0 与 0.1×训练任务差绝对值中位数/正工具费用中位数，在 T_acq 内按 parent 留一验证选择；尺度退化仅用 0。获取前特征不包含 e_q。

部署算法如下，首次调用与 STOP 分支共同保留费用记录：

1. 读取固定 dirty context 和 as-of 协变量，计算 z，以空证据执行 π 得到立即 STOP 的基础动作。
2. 对适用工具预测净价值；以训练阶段冻结的完整分支费用估计检查 B。准入使用获取分支总费用，不能使用可能为负的成本差代替。
3. 若无适用且预算允许的正价值工具则 STOP；否则只取得净价值最高的一项工具证据，更新状态并重新执行同一 π。首轮最多调用一次工具。
4. 只生成最终选中的当前治理候选，调用固定 checkpoint 的真实 TSFM 预测。若候选不适用，遵循冻结动作语义并显式记录原因；模型失败不能填零、删窗或更换模型。
5. 保存原始区间、mask、动作及证据、候选/预测 hash、模型 revision、终态 hash 与逐项账单，形成可追踪的治理血缘。实际超支照实保留；全部最终预测写盘后才开放 evaluator。

本轮实现对应 `decision_tree.py`、`terminal.py`、`acquisition.py` 与 `v431_online.py`；批量组件成本、在线热请求、模型启动及整个子进程剩余开销分开记录后完整加总，不将缓存命中抹去的实验时间等同于免费训练或部署。

### 与已有工作的关系

按决策代价训练树的思想借鉴 [SPO Trees 原论文](https://proceedings.mlr.press/v119/elmachtoub20a.html)，不能将成本敏感分裂本身列为原创。证据不足时保持参照策略的设计受到 [SPIBB 原论文](https://arxiv.org/abs/1712.06924)启发，但本项目没有满足或证明其批量强化学习理论条件，不能迁移其安全保证。按需取得信息与停止是 [DIME 官方实现](https://github.com/suinleelab/DIME) 所研究动态特征选择的相关方向；本轮学习的是冻结治理决策的实际损失变化，没有声称实现了 DIME 的条件互信息目标。

[TATO 官方实现](https://github.com/thulab/TATO)已研究 TSFM 输入变换优化，不能把推理前变换或搜索本身写成新意。本项目待验证的增量是具有严格时间权限的治理证据、可拒绝的动作更新以及面向完整部署收益的取证决策；只有共同主表与控制信息/预算的消融支持时，才可将它们提升为方法贡献。本轮尚未建立这种优势。

### 拟议贡献与实际证据对应

| 待检验主张 | 对应实际比较或审计 | 本轮允许的论断 |
|---|---|---|
| 因数据而异地治理有价值 | 固定五臂、dirty 成本敏感树、同证据普通 CART、诊断 oracle | 存在候选选择空间；不能用 oracle 当作部署收益 |
| 直接任务损失学习优于简单选择 | dirty loss tree、平面成本敏感树与 CART | 普通 CART 为 1.136486，优于固定 TS-ICL 的点估计，但配对区间跨 0；直接任务树尚无优势 |
| 任务跨度对齐的历史证据有额外价值 | 旧 H32、同原点 H32、完整目标 H 三种条件 | 当前 CART 的动作主要依赖缺口和遮挡证据；历史跨度改变尚未证明额外增量 |
| 可拒绝细化优于普通 gating | 剪枝/不剪枝、平面树与同证据 CART | 当前实现未超过 CART，不能称为独有突破或安全保证 |
| 按实际部署收益主动取证有效 | 固定单工具、条件调用、随机获取、全部调用与单步 agent | 新 agent 为 1.200158 且全部 STOP；主动获取贡献未成立 |
| 完整系统的读取权限和费用可信 | 7 例真实在线、14 份模型原始输出、独立读取屏障与成本复核 | STOP 路径和真实最终预测通过；这 7 例没有实际触发工具，不能冒称已验证主动取证在线路径 |
| 优于近期方法且跨 TSFM 家族成立 | TATO 原生变换空间适配、第二家族共同表 | 仅按实际完成范围报告；8-trial 适配不等于官方完整复现，缺项不能算作胜出 |

## 实验预登记
固定三来源、26dev parent/156相关变体；110train parent四段隔离。比较固定五臂、旧HGB、dirty loss tree、同证据CART/flat loss tree、剪枝/不剪枝、固定/条件/random工具、新单步agent、全部调用及官方TATO短预算适配。第二独立TSFM优先TimesFM。共同origin、finite mask、source宏权重；离线生成/训练搜索/部署/最终预测费用分别报告。

<!-- GENERATED_RESULTS_BEGIN -->
| Chronos-Bolt共同策略 | MASE ↓ | 批量组件秒数 |
|---|---:|---:|
| FIXED_A0_NATIVE | 1.258454 | 0.0899 |
| FIXED_A2_SINGLE | 1.157005 | 0.1201 |
| OLD_DIRTY_HGB | 1.165414 | 0.1592 |
| OLD_LEARNED_HGB_COMMON_BUDGET | 1.190112 | 0.4766 |
| DIRTY_LOSS_TREE_D1 | 1.163685 | 0.1066 |
| DIRTY_LOSS_TREE_D2 | 1.200158 | 0.1117 |
| CART_target_horizon | 1.136486 | 0.6580 |
| FLAT_LOSS_TREE_target_horizon | 1.165232 | 0.6625 |
| ALL_d2_target_horizon_gated | 1.191788 | 0.6637 |
| ALL_d2_target_horizon_unpruned | 1.184872 | 0.6569 |
| AGENT_d2_target_horizon_gated_high | 1.200158 | 0.1122 |
| TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR | 1.685227 | 0.7032 |

完整共同表： [v431_main_table.md](v431_main_table.md)。 当前已完成 50 个模型/方法组合，缺项 []。

本轮结果否定当前完整新agent优于强固定/CART对照的主张。新agent全部STOP，不能宣称主动获取贡献。普通CART使用dirty缺口与ridge遮挡误差，历史跨度变化未产生增量；因此证据细化不是已证实的独有突破。TATO为显式NaN桥接+8trial适配，非官方完整复现；跨家族结论以完整共同表为限。

条件source-parent bootstrap：{"CART_target_horizon": {"reference": "FIXED_A2_SINGLE", "gain_mase": 0.02051873866115983, "conditional_95_interval": [-0.012210532054364138, 0.0716598409204611]}, "AGENT_d2_target_horizon_gated_high": {"reference": "FIXED_A2_SINGLE", "gain_mase": -0.04315313707710855, "conditional_95_interval": [-0.07616418487538508, -0.016768135648880633]}, "ALL_d2_target_horizon_gated": {"reference": "FIXED_A2_SINGLE", "gain_mase": -0.034783537436829715, "conditional_95_interval": [-0.06829325221953789, -0.0095467652846367]}}。区间未校正连续parent残余相关、配置多重比较；USTS一个dev parent，仅开发诊断。

<!-- GENERATED_RESULTS_END -->

## 适用边界与待验证贡献
开发集已多轮使用，不是独立确认；USTS只有一个dev parent。主机制未胜过普通gating时保留相当/失败结论；获取全STOP不支持主动贡献。仅验证推理前治理，未证明TSFM参数适配或文本大模型训练收益。独立calibration/test在满足完整冻结条件前封存。
