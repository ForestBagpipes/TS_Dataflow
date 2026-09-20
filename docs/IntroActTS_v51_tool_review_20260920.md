# IntroActTS v51 配置工具审阅记录

审阅日期：2026-09-20。对象：`latex/IntroActTS_20260920_v51.tex` 及同名 33 页 PDF，正文结束于第 9 页。本报告不修改论文。

## 执行状态与边界

采用 work2 已配置的学术论文修改协作插件，实际入口为 `archive/paper_20260920/retired/.paper-review-tool/REVIEW_ONLY.md`，版本 `vendor-v0.1.0`。已读取其主工作流、八个角色的技能和职责设计，按措辞、引用、逻辑、数学、实验设计、结果资格、逻辑跨节复核、叙事、衔接的顺序进行单宿主只读审查。没有启动外部审稿服务，也没有八个独立模型或跨模型验证。

本轮目录为 `.academic-collab/runs/v51_review_20260920/`。其中保存 original、baseline、working 三份字节相同的论文及图表依赖，另存 SHA-256 清单。working 仅为归档副本，没有编辑。

配置服务器的 SSH 认证失败，未能运行要求的服务器解释器。依据 REVIEW_ONLY 第 6 条，正式 `append_event → lint → render` 未执行，权威账本为空。本报告及 event_drafts.json 是意见草稿，内容已到问题清单呈现阶段，不声称正式产生 FINDING_SET_PRESENTED 事件。没有作者确认、问题冻结、修订提案、投票或修改事件。

作者明确要求审阅到建议，并在工具外另行做独立评阅和规划。本工具报告仅列问题、依据、影响和方向。后续独立规划不冒充插件全票通过的方案。

## 领域画像与证据资格

论文研究固定预测器下的逐请求输入修复选择。历史窗口提供全部可用动作的预测效用，部署时用局部加权效用与离散惩罚决定修复或 KEEP。研究属于监督式逐实例算法选择及时间序列预测前处理。将它称为具有自主取证或在线学习能力的 agent，没有当前方法依据。

证据分为四类：论文内可定位陈述和表格，已存在的 v51 文献元数据核查，少量本轮读取的原始 JSON 或静态实现，审阅者推断。文稿明确保留 v47 事后结果，不能将 v47_verified 开发文件当作该稿完成验证的依据。

结果分析角色只完成来源资格检查。作者尚未确认本轮逐表运行身份、聚合口径和最终结果资格，该角色不对这些数值作新的科学解释。其余角色可以指出文内矛盾与缺失的实验控制。

已浏览本地十篇参照论文的题名与摘要，并重点阅读 Faster Cascades、AlphaEdit、Learning Dynamics 的相关正文。它们是第三方参考样本，不是作者自身写作样本。未建立作者 Style Profile，也未将 ICLR 获奖自动等同于技能要求的 CCF-A 分级。本轮未补齐该技能的独立分级核验，语言校准为有来源但非全条件验收。

## 论证与方法账本

| 论断 | 现有材料 | 专业判断 | 必要边界 |
|---|---|---|---|
| 重构准确不必然带来预测改善 | §4.2、附录重构排名诊断 | 部分支持 | 先核对动作支持集与聚合身份，不能宣称重构指标普遍无用 |
| 不同请求需要不同动作 | 图3、catalog oracle | 存在选择空间 | hindsight oracle 的空间不证明可部署选择器能够利用空间 |
| 近邻状态提供可迁移效用 | §3.2、附录 local transfer | 部分支持且有反例 | 距离与误差弱相关，不能把距离当可信度证明 |
| 惩罚产生更可信的干预 | §3.4、operating 表 | 机制归因缺控制 | 降低干预频率与提高选择质量需要分开 |
| 方法优于简单策略 | 主表、paired interval | 只支持有限结论 | 对 Best Fixed 和 CART 的区间包含零，不等于等效，也不足以证明更优 |
| 每请求至多两次调用 | §3.5、成本附录 | 仅预测骨干调用计数 | 还需要计入全部候选构建、修复模型和实际端到端时间 |
| 独立泛化 | §4.1、§4.5 | 当前未建立 | TEST 参与开发，各严重度在 replay 中出现，各骨干另建 bank |

数学账本涵盖效用差、回放差、指数权重、加权均值与方差、权重有效样本量、惩罚分数、MASE/RMSSE、oracle opportunity。本文没有需要补证的主定理，不能因为目标为 ICLR 而添加装饰性定理。

## 发现清单

优先级 P0 表示会阻断科学结论或结果可信度，P1 表示影响贡献或复现，P2 表示主要影响表达。所有项均为未冻结草稿。位置使用当前 LaTeX 标签，避免不同 PDF 阅读器页码造成歧义。

| ID / 主责 | 级别 | 位置与证据 | 问题、影响及建议方向 |
|---|---|---|---|
| W-001 措辞 | P2 | `app:ope-positioning`、`app:baseline-availability` | 附录有口语化断言和重复解释，如 `nothing of the kind`。建议术语固定、减少辩护式句子，保留实验限制与真实负结果。 |
| W-002 措辞 | P1 | `sec:method-decision`，score at zero 的解释 | 零分是人为规则的阈值，不能自然读成统计上无法区分或安全边界。建议与该分数的经验性质保持一致。 |
| CIT-001 引用 | P1 | `app:ope-positioning`，OPE requires propensity correction | 表述过强。OPE 还存在 direct model 方法，部分反馈不意味着所有估计器必须显式 propensity weighting。建议限定对比范围，交逻辑角色处理。 |
| CIT-002 引用 | P1 | `tab:app-availability` | BRITS 被 SAITS superseded、未运行 CSDI 却称超部署预算、若干无公开实现的陈述，需要各自证据与检索日期。不可将未运行写成已经比较过。 |
| CIT-003 引用 | P1 | §4.1、`tab:app-repro` | 2024 TimesFM 论文可支持模型家族，不能单独识别 2.5 checkpoint。附录只写 local snapshot pinned，不给具体修订标识。建议补版本来源与实际运行身份。 |
| L-001 逻辑 | P0 | §4.1 与 `tab:app-roster`、`app:diagnostic-conventions` | 正文承认 TEST 参与开发，附录却声称比较和计数在任何评估记录读取前固定。可能是本轮运行前与整个开发前被混用，需核对时间线后统一，不宜仅删掉披露。 |
| L-002 逻辑 | P1 | §3.2、`app:transfer`、`tab:app-transfer` | 文称最远五分位误差最大。TimesFM 最近组 0.559，最远组 0.205。现存 `transfer_test_timesfm.json` 也记录约 0.5588 和 0.2048。该总括陈述与表相矛盾，不能作为局部性证据。 |
| L-003 逻辑 | P0 | `tab:app-features`，intervention state | 对缺失参考值定义 `X^a-X^0` 缺少数值语义。静态代码 `src/introact_ts/v44/state.py:197` 的差值随后 nan_to_num 为零，在 reference 为 NaN 的调用条件下会抹去四项幅度特征。需追踪实际 reference 数据和运行版本，当前不能断言所有历史运行都受影响。 |
| M-001 数学 | P1 | `eq:local-moments`、`eq:score` | 权重 n_eff 描述权重集中度，不自动成为独立历史父样本数。同一 parent 的多个 mask/horizon/severity 可共同入邻域。论文已否认风险保证，仍需避免把该量解释为经验证的均值不确定性。移交实验设计核对聚类处理。 |
| M-002 数学 | P1 | §3.4 与 catalog/contract | 邻域为空、有效记录不足 k、全部修复不可用、零距离以及并列最高分等分支未完整形式化。KEEP 总可用不等于所有前置计算均有定义。建议在不改变已实现语义的前提下补齐契约。 |
| E-001 实验设计 | P0 | §4.1、`app:splits` | 拟合与 TEST 时间不交叉不能消除开发过程中反复读取 TEST 的自适应偏差。需要未参与方法和报告设计的确认集及冻结方案。bootstrap 不能补足此项。 |
| E-002 实验设计 | P1 | 表2 A2/A5 | A2 数值优于 full，A5 MASE 接近且略低。当前实验不能支撑 22 维 action-conditioned 检索是必要技术贡献。建议将结构选择留在开发集，做针对性机制与交互比较，保留负结果。 |
| E-003 实验设计 | P0 | 图4、`tab:app-operating` | β 增大时干预率下降，条件伤害率变化小。缺少同干预率、同预算比较，无法区分谨慎少干预与真正更会选择。建议补匹配覆盖率的控制。 |
| E-004 实验设计 | P1 | `app:baseline-config` | TATO 使用 48 trials、8 TRAIN 窗口，其他方法可使用完整 replay；并包含额外线性插值。需区分监督量、搜索预算和输入契约，补线性插值控制与可比预算，不能把现有结果外推为优于官方完整方法。 |
| E-005 实验设计 | P1 | §4.5 | 10/30/50% 全部在 replay，严重度曲线不是未知缺失机制测试。需要留出一种机制或未见严重度及自然缺失验证，或保留严格的 within-grid 结论。 |
| R-001 结果资格 | P0 | `app:reprodetails` 与 `figure/data/provenance.json` | 当前图形链条证明图等于已有表格；还不等于逐表追溯到运行、预测及统计口径。需逐表建立 record/config/code/model/mask 身份，未经确认不进入结果解释角色。 |
| R-002 结果资格 | P0 | `app:seeds` 对照 `tab:app-src-bolt-96`、`tab:app-src-ch2-96` | 稳定性段落称 H=96，primary seed 的 MASE 却均为 1.378；H=96 主分表分别为 1.173、1.111。可能混用双 horizon 汇总，需要原始运行映射，不能直接替换成任一较有利数值。 |
| R-003 结果资格 | P0 | `tab:app-efficiency`、`tab:app-calls` | 三骨干平均 65.4% 后对应 497/760 的计数身份不清。固定 SAITS/TATO 完全相同的 latency 三元组也需来源。TimesFM 现存日志将约 103.90 ms 定义为单次骨干调用、2.27 ms 为检索，不能直接推出稿中 95 ms 为端到端。需建立独立测量映射。 |
| R-004 结果资格 | P1 | `tab:app-recutils`、`tab:heterogeneity`、`tab:app-opp-sizes` | 两个效用表的样本范围与聚合不够明确，某些动作可用样本不同。机会分层的 parent 计数可能因变体跨层重叠，需明确是否为可重叠独立计数，不能把分层行当互斥 parent 分区。 |
| N-001 叙事 | P1 | 引言最后两段、结论 | 主问题明确，但贡献仍接近一个完整实现说明。需要突出哪一项关于逐请求决策的知识被可靠建立，不能由题目 governance 推导出机制创新。建议首尾围绕一个有证据的决策结论。 |
| C-001 衔接 | P1 | §4.4 首次出现 harmful loss、missed opportunity | 关键指标未在主实验前给清楚定义和分母，读者先看结论后找统计口径。建议先交代定义再解释实验。 |
| C-002 衔接 | P2 | `app:map` 与末尾 `Numerical Values for Action Utility` | 新增数值附录不在导航表中，正文图3的底表位于探索材料之后。建议未来整理导航与证据阅读顺序，不在本轮移动。 |

## 跨角色移交与冲突

L-003 → M-001/M-002：数学角色仅核对缺失值定义与边界，实际运行是否使用该静态代码仍待溯源。M-001 → E-003：相关邻居对不确定性解释的影响由实验设计角色负责。E-001 → L-001：保留 post-hoc 历史，不把新独立实验的规划追溯写成原实验属性。R-001 至 R-004 → 作者事实核对：在来源未厘清前不生成结果解释稿。

N-001 与 E-002 的依赖最重要。叙事角色不能用更强的引言去解决 ablation 不支持模块必要性的问题。措辞与衔接可以改善阅读，但不能成为晋升科研结论的证据。

## 本轮外部核验与边界

既有 `reference_audit_v51_20260920.json` 的 40 条元数据核查作为历史记录使用。本轮没有重新认证全部 40 条的全文支持关系，也没有跨模型核验。

定向核对了 [TATO 原论文](https://arxiv.org/abs/2603.00629)的固定骨干和域级转换设定、[TimesFM 官方仓库](https://github.com/google-research/timesfm)的版本体系，以及 [Doubly Robust Policy Evaluation and Learning](https://arxiv.org/abs/1103.4601)的直接建模与 propensity 两类估计关系。它们只支持上述有限核查，不构成穷尽新颖性检索。

参考论文奖项由 [ICLR 2025 官方公告](https://blog.iclr.cc/2025/04/22/announcing-the-outstanding-paper-awards-at-iclr-2025/)确认。Faster Cascades 属于 Honorable Mention，AlphaEdit 与 Learning Dynamics 属于 Outstanding Paper。

本轮停止于意见草稿呈现。所有 Finding 均未由作者确认、未正式冻结、未经过修订评审，没有修改任何论文资产。
