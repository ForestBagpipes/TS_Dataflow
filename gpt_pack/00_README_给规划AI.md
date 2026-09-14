# IntroAct-TS 项目简报包 — 给规划 AI 的背景与提问

> 用途：本包用于向外部规划 AI（GPT）完整介绍项目现状，请它就"创新出发点被质疑"后的**目标调整与下一步规划**给出方案。包内是项目真实文档与结果快照，未做美化。

## 0. 一句话定位

IntroAct-TS 是一个**面向时间序列基础模型（TSFM）的风险可控数据治理 Agent**：读取待治理的时间序列，在 KEEP / DENOISE / DESPIKE / IMPUTE 等候选治理动作中决定是否修改数据、采用什么动作，目标是在提升 TSFM 下游效用的同时控制错误修改与条件危害，并保存可审计轨迹。

## 1. 被质疑的问题（本次咨询的核心）

评审/他人质疑：**"现在数据治理都有备份，原始数据都有保留，治理错了能回退，因此风险可控的数据治理创新出发点不足。"**

我们需要的不是安慰，而是**可执行的重定位方案**。请重点回答：

1. **问题设定重塑**：在什么真实场景下"治理错了不能简单回退"是成立的？候选方向（请评估并补充）：
   - 流式/在线治理：数据进入训练管道即被消费，回退意味着重训或污染已扩散到下游模型/特征库；
   - 治理动作影响的是**基础模型本身的预训练/微调语料**，错误修改被模型吸收后无法定位回退（参数级污染）；
   - 治理决策本身要过**合规/审计**门槛（金融、医疗时序），"先改了再说，错了回滚"在监管下不成立，需要的是**事前风险证书**而非事后回退；
   - 回退成本不对称：回退恢复的是原始**坏**数据，真正的问题是如何在"不改（保留缺陷）"与"改错（引入新缺陷）"之间做事前选择——这正是我们的 CHR/pme 指标刻画的，但叙事上没有讲清楚。
2. **创新点重述**：现有素材（Agent 闭环、风险证书、LODO 条件风险、保护层误编辑 pme、OOD 编辑安全、action-semantic 标签、反事实动作库 + critic）能组合出哪些站得住的 contribution？哪条主线最适合 ICLR？
3. **下一步实验规划**：在 `docs/version_ledger.md` 已排除的 7 条路线（阈值重选、shadow 证书、动作条件后果验证、窗内成对排序、目标域校准、候选语义拆分+证书算子、冻结基础模型插补+不确定性门控）之外，还有什么**我们没试过且与现有工程资产兼容**的方向？特别是：
   - 候选池价值已被证明存在（unrestricted oracle bcov 0.6591 / gain 0.1969 / CHR 0），缺的是**部署可得的逐窗风险证据**——这个缺口有什么新证据来源？
   - v4.0 的反事实动作库 + action-delta critic（自我对弈式反事实监督）是否是对的路？如何加强？
4. **与"数据治理岗位"能力的对齐**：论文叙事如何同时服务求职（数据质量、基础模型反馈、风险控制、RL、实验诊断、工程复现）？

## 2. 当前方法状态（截至 2026-09-03）

**正式 incumbent：PICS_joint_relabel**（冻结 seed-101 语料，771 窗评估框架，LODO 六折，first-commit 协议）：

| 指标 | 值 | 含义 |
|---|---|---|
| bcov | 0.2727 | beneficial coverage（有益修复覆盖） |
| CHR | 0.2053 | conditional harmful rate（已提交动作中的有害比例）——**未达自定的 ≤0.10 安全门** |
| pme | 0.0091 | protected mis-edit（保护层误编辑率） |
| gain | 0.0919 | contaminated 窗上的下游 canonical NMSE 改善 |
| damage | 0.0402 | 综合损害（含裁剪与丢弃修正后的口径） |

关键事实：

- **候选池里价值充足**：unrestricted oracle bcov 0.6591 / gain 0.1969 / CHR 0（290 commits）；瓶颈在选择器与部署可得证据，不在池子。
- **算子层已有两块验证过的资产**：FACT_SHORT（raw NaN gap 1–3 证书插值：执行窗精度 0.864 / CHR 0.136）；TSICL_LONG（冻结 TS-ICL 模型填 25–63 长缺口：75 B&S / 14 harmful of 89，但其失败窗对一切部署可得不确定性信号不可见）。
- **v3.9 目标预算**（相对 D 臂基线 bcov 0.2659）：正式目标还需 +15 B&S 窗、+5.63 gain 和，且 CHR/pme 必须靠**净减害**达成，不能只靠添加新动作。

## 3. 版本简史（详见 docs/version_ledger.md 与各 preregistration）

- v1：旧"低损害 SOTA"结论因 damage 口径错误作废（0.13 → 实际 0.68）；
- v2/v3.x：结构 veto、PICS 分数成为 incumbent；
- v3.2–v3.9 连续 7 条路线预注册后被实验排除（见 ledger，全部有 bit-exact 回放与哈希台账）；
- v4.0 COUNTERACT-TS：预注册已冻结（`docs/v4_0_counteract_preregistration.md`），Phase 0+1（反事实动作库 pilot）刚启动即因本地配额中断，**尚未产生任何结果**。

## 4. 工程资产（可复用，详见 docs/data_provenance_contract.md）

- 冻结语料：1599 sample_uid / 771 评估窗 / 6 个真实来源（ETTh1/h2/m1、Oil、USTS、Crypto）+ seed-313 OOD；
- 标签管线：action-semantic 标签（canonical NMSE + KEEP 反事实），全部 bit-exact 可复现；
- 评测框架：LODO 六折、first-commit、sample_uid 配对 bootstrap、KEEP 占位分母固定；
- 已下载模型：MOMENT-1-large、chronos-bolt、timesfm-2.5、TS-ICL v1、OpenFIM（全部官方来源、hash 登记）；
- 完整的预注册-执行-post-hoc-回放工程纪律（每版有 preregistration、manifest、双进程确定性校验）。

## 5. 包内文件导航

- `docs/HANDOFF.md` — 项目交接总览（含 v3.2–v3.9 每版结论段落）；
- `docs/version_ledger.md` — 版本台账（哪些路线已排除、为什么）；
- `docs/diagnostic-playbook.md` — 28 棵诊断树（失败模式与规则的积累）；
- `docs/v3_4…v4_0 各 preregistration` — 每轮的冻结方案与 post-hoc 结果区；
- `docs/claims.md`、`docs/experiment-matrix.md`、`docs/modality_generalisation.md` 等 — 论文主张与实验矩阵；
- `paper/` — 论文各章 Markdown 草稿（中英文）；
- `results_selected/` — 关键结果 JSON（incumbent 复现、oracle 回放、mask 审计、长缺口探针、BRIDGE 信号门、目标预算、显著性检验）；
- `work2_summary.md`、`research_brief_ts_dataflow.md` — 早期项目摘要与数据流简报。

## 6. 约束（规划时请遵守）

- 不隐瞒失败、不改口径、不做不公平比较；
- SOTA 是靠实验达成的目标，不是预先宣称的结论；
- 尽量复用现有工程资产，不另起炉灶换主题；
- 若建议引入新场景/新数据/新 baseline，请给出具体可执行的获取与协议设计。
