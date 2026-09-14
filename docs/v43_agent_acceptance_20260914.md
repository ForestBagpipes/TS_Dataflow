# v4.3 最小agent验收：问题、机制与实验对应

依据2026-09-14用户本轮消息冻结。用户链接指向sandbox:/workspace/scratch/477a27e80c71/deliverables/IntroActTS_新服务器完整执行方案_20260914.md；该路径当前不在本服务器可见文件系统，未声称已读取附件第24节全文。本记录忠实落实消息中明确的目标与三项任务，附件原文待可访问后再核对细则。

## 验收问题

在未来真值不可见、计算预算有限时，agent如何获取合法证据，选择有助于真实TSFM的治理动作，并在证据不足时停止或KEEP。备份可恢复但不能替代当前版本选择。重建误差与任务效果分开，51项测试和8.06%的TS-ICL基线收益不归属于拟议agent。

| 核心假设 | 实施与对照 | 可报告结论 |
|---|---|---|
| H1 需要因数据而异的治理 | 固定KEEP/FFILL/TSICL_SINGLE/TSICL_COV/RIDGE_CONTEXT候选池；最佳固定策略与分组开发oracle | oracle只说明可选空间，非部署成绩 |
| H2 合法证据有助于判断 | dirty-only简单选择器、masked-only、history-only、全部证据的同族动作评分器；训练parents和dev分离 | 比固定及简单基线的真实MASE/危害/原始保护层效果 |
| H3 主动获取胜过固定流程 | 同池同信息，固定两种工具顺序、学习获取与停止、全部调用；完整成本及真实按需回放 | 同预算任务收益或同效果成本改善，包含基线候选和加载成本 |

首轮将residual从核心贡献中移出，作为可选候选诊断，不以A5阴性推断完整agent阴性。旧PICS_joint_relabel保持incumbent；A1和更多来源/模型不是本轮最小agent实现的先决阻塞。

## 当前先后顺序

1. 复用P2原始遮挡、candidate/forecast缓存审计A5。逐episode报告辅助可观測比例、支持、eta、delta与候选hash、预测变化、静态拒绝原因。为未执行的eta=0.5/1候选只补缺少的真实Bolt预测，比较静态规则与可选残差池开发上界。
2. 固定候选池，按source-parent聚合开发oracle增量，明确已有结果只证明选择空间。用train训练、dev检验合法证据是否可学习；不在dev行随机切分自证泛化。
3. 最小agent采用固定初始候选池，基础候选费用全部入账；两个可选验证工具为strict_mask与history_probe。mask工具对可见伪块重新生成候选；history工具在448/480时点以当时dirty前缀重新治理并预测H32，禁止裁剪使用未来信息生成的最终候选。两个工具共享固定候选池，后取证据才进入状态，最多两轮；全部调用对照使用同一评分器。

训练来源先保持ETTm1/Solar/USTS；只使用train/dev完整原始区间，L512/H96,H192，raw/target_block10/shared_block10，seed101、通道0。train父区间按时间70% scorer-fit、30% acquisition-fit；dev仅做评估。utility学习真实task loss差异，工具值由已固定评分器在acquisition-fit上的实际决策前后损失差减成本产生；不能使用逐窗oracle动作作为工具标签。

风险与成本：只报告支持范围内经验task harm与结构写入检查，不伪称未实现的校准/安全保证；自然缺失clean未知时修复风险标签为null。成本分C_base、C_tools、C_selection、共同forecast；缓存回放保留原始producer身份与生成成本，不把命中视为免费，不冒充新代码重算。至少一次真实在线按需调用回放核验动作与费用。

## 新意边界（来源已只读核验）

[TATO官方仓库](https://github.com/thulab/TATO)已提供自适应输入变换及优化搜索。[AegisTS v6论文](https://arxiv.org/abs/2605.04902v6)已研究分层清洗顺序/方法选择并结合上下游奖励。不能把变换、清洗agent或下游奖励本身称为新意；本项目的合法证据、面向任务的决策与预算获取机制必须由H2/H3消融证明额外价值。现阶段无ICLR级充分实验证据。


### 2026-09-14 执行结果回填

本轮三项任务已经执行并独立复核，结果为H1选择空间存在、当前H2/H3未成立。19策略及7例真实在线、完整费用、A5遗漏强度和保留失败见[v43_agent_report_20260914.md](v43_agent_report_20260914.md)。未进入独立确认，不推进方法晋升；下一步train内机制诊断先行。
