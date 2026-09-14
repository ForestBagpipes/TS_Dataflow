# IntroAct-TS v3.5: ACV — 预注册文档

**Action-Conditioned Verification（动作位置对齐的 TSFM 后果验证）**

- 创建日期：2026-09-03
- 状态：PLANNED（预注册冻结后才允许看新结果）
- **§0–§9 为预注册区**；**§10 起为 post-hoc 区**。严禁倒填。

---

## §0. 定位与继承结论

IntroAct-TS 是面向 TSFM 的数据治理 Agent：缺陷感知 → 候选治理动作 → TSFM/结构后果验证 → 选择最佳动作或 KEEP → 风险控制 → 审计溯源。不改成异常检测、单纯插值、新 backbone、通用 LLM Agent。

Incumbent：**PICS_joint_relabel**（bcov 0.2727，CHR 0.2053，pme 0.0091，gain 0.0919，damage 0.0402）。

继承结论（本轮不得违背）：

1. MAST-PICS 被 PICS Pareto 支配，停止开发（仅可选失败对照）。
2. v3.4 证明旧 PICS score 上条件阈值 oracle 上限 bcov 0.061–0.093 → **禁止继续在旧 PICS score 上调阈值**。
3. shadow certificate AUROC=0.351 → **禁止增加 shadow mask 数量/几何/组合特征**。
4. RESEGMENT oracle coverage=0，继续关闭。
5. v3.3 clean rerun 已完成且逐值一致，本轮不重跑。
6. v3.5 必须引入**新的部署可得候选级证据**。

## §1. 核心假设

v3.4 shadow 失败因为它在"别的位置"模拟缺失，测的是局部插值难度而非实际候选动作的后果。v3.5 改为动作位置对齐验证：

**Prequential evidence**：候选动作修改真实支撑集 S(a) 后，取 S(a) 之后未被动作修改的真实观测块 Y。把 KEEP 和 APPLY 后的历史输入同一个冻结 TSFM，预测完全相同的 Y：

```
G_prequential(a) = forecast_error(KEEP → Y) − forecast_error(APPLY(a) → Y)
```

G>0 表示执行动作后真实后续观测更容易被 TSFM 正确预测。这不是 clean reference 也不是缺失真值，是部署时已出现的动作之后真实观测。

**Support conformity（第二独立证据）**：精确遮住实际 changed support（不让 TSFM 看见 candidate 在 support 内填入的值），让 TSFM 从支撑集外上下文重建 support，比较 KEEP 值与 candidate 值谁更接近 TSFM 条件重建。该证据不能单独形成方法，只与 prequential 做消融/联合。

## §2. 数据流（冻结规范）

每个 sample_uid 的动作集合必须包含 KEEP。对每个 candidate：

1. 从正式 operator output 取 touched_mask/changed_support。
2. support 分解为连续 runs。
3. 为每个 run 选动作后真实有限观测 anchor：
   - anchor 不能被动作修改；target 必须来自 original observed data；不允许用 materialized NaN 作 target；
   - 固定 horizons：8、16、32，长度不足跳过；最多 3 个有效 anchors；
   - 选择规则只能由 sample_uid 和 support 决定。
4. KEEP/APPLY 使用完全相同 target、anchor、context length、reference scale、TSFM checkpoint。
5. 输出：`preq_gain_mean/median/min/std/win_rate/valid_anchors/lcb`。
6. `preq_gain_lcb = mean_gain − 1.645·std_gain/√n_valid`；n_valid=1 时用 gain_min，不伪造标准误。
7. support conformity 输出：`support_gain_mean/min/model_disagree/valid_views/lcb`。
8. **预注册三个固定连续分数**：A. prequential-only = `preq_gain_lcb`；B. support-only = `support_gain_lcb`；C. joint = `min(preq_gain_lcb, support_gain_lcb)`。
9. 禁止看到标签后改变分数方向或权重。

无有效 post-action anchor 的候选：`prequential_supported=0`；仍可算 support conformity；**不得把缺失特征填 0 伪装成正常证据**；正式策略默认 KEEP，除非 support-only 臂独立过预注册门。

## §3. TSFM_RECONSTRUCT_IMPUTE（实验性算子，与 verifier 分开判定）

1. 仅在正式路由已提出 IMPUTE 时生成，不用 true_kind；
2. 按真实 missing runs 重建；
3. 不改 observed finite points；
4. 保留 linear、seasonal、KEEP 等现有 operator；
5. TSFM_RECONSTRUCT 只是候选动作，不自动提交；
6. 多个 reconstruction-capable backends 时：一个生成动作、其他验证，不允许同一模型是唯一 proposer+verifier；
7. 只有一个可重建 backend：如实标注 single-model，只能依赖 post-action observed anchors 验证，不能宣称 cross-model certificate。

目的：扩展 Agent 动作工具箱，由同一 ACV 机制决定用 linear/seasonal/TSFM reconstruction/KEEP。

## §4. Phase 0：文档和证据可用性审计（5–10 min CPU）

不重跑 v3.3/v3.4。读取冻结：`results/v33_clean_rerun*.json`、`results/v33_training_data.jsonl`、`results/v33_harmful_commits.json`、`results/v34_conditional_risk_frontier.json`、`results/v34_shadow_records.jsonl`、seed-101 manifest、TSFM checkpoints。

新建 `experiments/v35_acv_support_audit.py` → `results/v35_acv_support_audit.json`。只结构审计，不调 TSFM：

- 2414 candidate 中多少有 changed support；
- 多少有 ≥1/2/3 个有效 post-action anchors；
- 分 family/source/missing geometry；
- 每窗口 candidate/operator 数；多少窗口可形成 action tournament；
- support 处于窗口末尾导致无法 prequential 验证的比例。

**Phase 0 门**：全部 candidate changed support 可验证；≥85% eligible candidates 有 ≥1 有效 anchor；≥70% 有 ≥2；anchor target 与 changed support 交集为 0；anchor target 全部来自 original finite observations。低于覆盖门不停止，继续 support conformity，但预先记录 prequential 适用边界。

## §5. Phase 1：全候选 ACV 探针（30–60 min，RTX 5090）

新建 `experiments/v35_acv_probe.py`、`tests/test_acv_probe.py` → `results/v35_acv_records.jsonl`、`results/v35_acv_probe.json`。

- 全部 2414 候选，不只看 PICS accepted；推理批量化，不逐 candidate 启动模型。
- 测试：KEEP/APPLY anchor 完全一致；support mask 不泄漏 candidate 值；修改 anchor target 时测试必须失败；多进程/重复执行数值一致；clean/true_kind/evaluation label 不进入 probe；原 operator output hash 与 v3.3 一致；每条记录含 model/checkpoint/config/input/output hash。
- **特征文件生成并冻结后，才连接 evaluation labels**。

报告三个总体：全部 candidate；PICS 接受的 151 commits；PICS 拒绝但 beneficial_and_safe 的候选。分层：family、source、missing_block/missing_scattered（仅离线分析层）、operator/method、anchor coverage。

**主要信号门**：

- A（PICS accepted 上预测 harmful）：harmful AUROC ≥0.75；harmful AUPRC 比 PICS harm score 至少 +0.05。
- B（误拒 accepted b&s ≤20% 工作点）：harmful recall ≥70%；IMPUTE harmful recall ≥70%；有足够样本的主要 source recall 均 ≥50%。
- C（PICS rejected 的 b&s 中）：LODO 阈值下新增 beneficial coverage ≥0.05；新增 candidate 的 CHR ≤0.10。
- D（evidence coverage）：prequential 或 support 至少一项有效的 candidate ≥90%。

绿灯：A、B、C、D 全过。黄灯：A/B 过 C 不过 → 只能作安全 veto；C 过 A/B 不过 → 只能作 coverage proposal。红灯：A、B 均失败 → 停止 ACV 集成，登记诊断分支。

**primary score 预注册为 prequential-only**；support-only 和 joint 是预注册消融，不得看结果后改 primary。

## §6. Phase 2：TSFM_RECONSTRUCT_IMPUTE 算子探针

与 Phase 1 共用一次模型加载和 GPU 队列。新建 `experiments/v35_tsfm_impute_probe.py`、`tests/test_tsfm_impute_operator.py` → `results/v35_tsfm_impute_records.jsonl`、`results/v35_tsfm_impute_probe.json`。

在相同 routed IMPUTE windows 上配对：KEEP/materialize_for_probe、linear/default、当前实际候选方法、TSFM_RECONSTRUCT_IMPUTE。算子评价标签只在输出冻结后连接。

算子绿灯（全部满足）：

1. 与当前 IMPUTE 同窗口配对：harmful rate 相对下降 ≥25%；
2. beneficial_and_safe rate 不低于当前 IMPUTE；
3. median true loss 严格下降；
4. 至少 3 个真实 source 方向一致；
5. 不修改任何 observed finite value；
6. oracle window coverage 增加 ≥0.03，或相同 coverage 下明显降低 harmful rate。

未过门不集成该算子，不影响 ACV verifier 独立进 Phase 3。

## §7. Phase 3：动作竞赛集成（仅 ACV 或新算子至少一个绿灯）

新建不覆盖：`src/introact_ts/action_conditioned_verifier.py`、`src/introact_ts/acv_policy.py`、`experiments/v35_compare_arms.py`、`tests/test_acv_policy.py`。

核心策略：KEEP 永远合法、分数固定 0；对窗口全部 candidate 算 ACV score；先过现有结构安全壳 + 冻结 OOD consequence veto；按 ACV score 排序；只有最高分 candidate 超过训练来源 calibration 的 family margin 才提交，否则 KEEP；first-commit 协议保留但候选顺序由部署可得 ACV score 决定；PICS score 只作比较臂，不加入主方法。

比较臂：v2_frozen_relabel、PICS_joint_relabel（incumbent）、ACV_prequential_only、ACV_support_only、ACV_joint、PICS_intersection_ACV、ACV_action_tournament（**预注册主臂**）、ACV_tournament+TSFM_RECONSTRUCT（仅算子过门）、oracle_relabel。不得从多臂中临时挑冠军冒充预注册主方法。

## §8. 校准与统计协议

frozen seed-101 corpus；LODO；sample_uid 分组；held-out dataset 不参与训练/归一化/calibration；sample_uid 配对 bootstrap ≥10000；first selected commit；seed-313 OOD。

v3.4 已证明"每折 CP upper≤0.10"在当前样本量下即使接近 oracle 也不可达——v3.5 不把统计功效不足误写成方法失败。风险报告：pooled held-out CHR 点估计；pooled 一侧 95% CP 上界；六个 held-out fold 的 CHR/commit/harm count；与 PICS 的配对 bootstrap 差；source/family 条件风险。**只声称 LODO 实证风险控制，不声称对任意新 source 有形式化 CHR≤0.10 保证**。

## §9. 正式 v3.5 硬门

安全：pooled CHR ≤0.10；pooled CHR CP95 上界 ≤0.15；CHR 明显低于 PICS 0.2053；conditional mean loss ≤0.10；pme ≤0.0055；damage ≤0.0402；synthetic OOD edit ≤0.05；real OOD edit=0；collision-free OOD edit=0。

活性：bcov ≥0.300；contaminated gain ≥0.100；commit 不由单一 source 主导；beneficial commits 最大 source 占比 ≤50%；DENOISE/DESPIKE/IMPUTE 中至少两个 family 有真实提交。

相对 PICS：bcov >0.2727；CHR <0.2053；pme <0.0091；gain >0.0919；risk-coverage 曲线不被 PICS 支配；CHR 配对改善 95% CI 上界 <0；bcov 点估计提高且 95% CI 下界至少 >−0.01。

任一关键安全/活性门失败：只登记诊断分支；不运行 smoke350；不第二轮自由调参；不调用 API。

## §10. 代码回归要求（预注册的分析义务）

正式主臂输出 `results/v35_harmful_commits.jsonl`、`results/v35_rejected_beneficial.jsonl`、`results/v35_action_tournaments.jsonl`。每条 harmful commit 回答：changed support 产生了哪些 anchors；KEEP/APPLY 每 anchor 预测/误差；prequential/support/safety shell 谁放行；同窗口是否有更安全 candidate 及 tournament 为何没选它；是否由 source/family/operator 主导；决策对应函数与条件。rejected beneficial 回答：无有效未来 anchor / ACV gain 不足 / 跨 view 不稳定 / structure veto / OOD veto / margin 太严。特别检查：harmful action 的 preq_gain 仍明显为正 → 单独列为 "objective mismatch"，不得调阈值掩盖。

---

## §11. Post-hoc 结果区（逐阶段追加）

（本节全部为 post-hoc 记录，与 §0–§9 预注册内容严格分区。）

### §11.1 Phase 0：证据可用性审计 — 覆盖门 FAIL 但按预注册继续（2026-09-03）

- 新建 `experiments/v35_acv_common.py`、`experiments/v35_acv_support_audit.py`、`tests/test_v35_acv_common.py`（13 项服务器测试全过）；未修改任何已有文件。
- 输出：`results/v35_acv_support_audit.json`（sha256 `4c3260545c6a6a499c93b9bacb47449bea48c738ef89e9e6b1878d4b29501ffd`）、`results/v35_acv_support_records.jsonl`（2414 条，sha256 `517fa25405401aa30ac0da1c0588c7ea58b80e5a926b9d9bf825fa4aee38cf42`，n_jobs=32 与 n_jobs=8 两次逐位一致）。
- 五门：1 支持可验证 PASS（2414/2414 算子重跑 output_hash 逐位一致）；2 ≥1 anchor ≥85% **FAIL（76.3%）**；3 ≥2 anchors ≥70% **FAIL（23.3%，严格解读）**；4 anchor∩support=0 PASS；5 anchor 全部 original finite PASS。
- **适用边界（预注册允许记录后继续）**：DENOISE 被结构性排除（savgol 全窗重写，99.3% 无 anchor）；RESEGMENT 裁尾 37.9% 无 anchor；block 缺失多靠窗尾（73.9% ≥1 anchor）而 scattered 96.5%。572/2414（23.7%）无 anchor 全部归因 support 直达窗尾。
- 总证据覆盖（prequential 或 conformity 至少一项）：89.0%（2149/2414）——注意此值低于 Phase 1 门 D 的 90%，Phase 1 须如实报告。
- tournament 可行性：≥2 候选窗口 contaminated 416/440、rare_valid 60/61、changepoint 83/113。
- KEEP 为隐式动作（不在候选表），prequential_supported=0，tournament 分数固定 0。
- **anchor 规则解读修正（主代理决策，先于任何标签接触）**：采用预注册 §2.3 原意的 multi-horizon 解读（每 run 按 8/16/32 各出一个 anchor，封顶 3），Phase 0 冻结的"每 run 1 anchor"为过严解读；两解读数字都保留在 JSON（`alt_multi_anchor_reading`：ge2 覆盖 75.6%）。门 2 在两种解读下均 FAIL，瓶颈与解读无关。
- 服务器耗时约 15s（CPU，n_jobs=32）。

### §11.2 Phase 1：全候选 ACV 探针 — 红灯（2026-09-03）

- 实现：`experiments/v35_acv_probe.py`（+ 更新后的 `v35_acv_common.py` multi-horizon anchor 规则）；模型池 chronos-bolt-base / timesfm-2.5-200m-pytorch / chronos-bolt-small（revision hash 记录在 records），judge=chronos-bolt-base；批推理，模型加载一次。
- 产物：`results/v35_acv_records.jsonl`（2414 条，0 unmatched，sha256 `cab0a9411b70d444f10b5692efa0601b927af11c0095b8bc830befc6d1274de7`）、`results/v35_acv_probe.json`（sha256 `9621d0f74341d44aac5535fbb09a627a9a6db52b41e6db46991758bc1ef96dfb`）；特征文件冻结后才连接标签。incumbent 一致性：PICS bcov 0.272727 与基线吻合。
- 信号门（primary = prequential-only score A，按预注册不改）：

| 门 | 结果 | 数字 |
| --- | --- | --- |
| A. accepted 上 harmful AUROC≥0.75 / AUPRC +0.05 | **FAIL** | AUROC 0.623；AUPRC lift +0.008 |
| B. 误拒 b&s≤20% 时 harmful recall≥70% | **FAIL** | recall 25.8%（8/31）；IMPUTE 18.5%（5/27） |
| C. rejected-b&s 中新增 bcov≥0.05 且 CHR≤0.10 | **FAIL** | LODO 阈值下新增接受 0（670 条 rejected-b&s 中无一过阈） |
| D. evidence coverage ≥90% | **FAIL** | 实际 57.6%（1391/2414） |

- 预注册消融（只看结果、不改 primary）：support-only AUROC 0.708、AUPRC lift +0.210；joint AUROC 0.667。support conformity 方向性强于 prequential，但仍低于 AUROC 0.75 门，且按预注册不得事后换 primary。
- **门 D 与 Phase 0 估计的差异如实记录**：Phase 0 结构审计估计 89.0%，实际探针的 conformity 支撑判定更严（需有效模型视图），实现后只有 57.6%。prequential_supported 1370、conformity_supported 1391。
- **判定：红灯（A、B 均失败）→ 按预注册停止 ACV 集成，登记诊断分支。**

### §11.3 Phase 2：TSFM_RECONSTRUCT_IMPUTE 算子探针 — not_green（2026-09-03）

- 实现：`experiments/v35_tsfm_impute_probe.py`；proposer=MOMENT-1-large（唯一原生重建 backend），verifier=chronos-bolt-base + timesfm-2.5（**cross-model 验证、single native-reconstruction backend**，如实标注）。
- 产物：`results/v35_tsfm_impute_records.jsonl`（1154 条，445 窗，sha256 `82535ebaa1d419ff13cd73625c54c9668b8d08b2796bc2c00fee47a26ceaec27`）、`results/v35_tsfm_impute_probe.json`（sha256 `518e6f6d10e9263b6cb229c163e77e5aa3244a5d4841e6b6523bcb8c0dfd8062`）。
- 六门：1 harmful 相对下降 46.5%（0.539→0.289）**PASS**；2 b&s rate 不低于当前 IMPUTE **FAIL（0.172 vs 0.460，大幅下降——TSFM 填补把大量候选变成中性而非有益）**；3 median true loss 1.0→0.0 **PASS**；4 ≥3 真实 source 方向一致 **PASS**（ETTh1/ETTh2/ETTm1 改善；Crypto/Oil Price/USTS 反而变差）；5 不改 observed finite **PASS**（0 violations）；6 oracle window coverage +0.020（0.456→0.476）< 0.03 **FAIL**。
- **判定：not_green → 不集成该算子。**

### §11.4 v3.5 总判定：红灯 + not_green → 诊断分支，无 Phase 3（2026-09-03）

按预注册 §5/§6 与用户执行令（"二者都是红灯，立即停止"）：ACV 红灯且 TSFM 算子 not_green，**Phase 3 未执行**，不制造 v3.5 变体，不运行 smoke350，API 调用 0。incumbent 仍为 **PICS_joint_relabel**。

联合解读（post-hoc 推断，非预注册结论）：三条独立证据线（v3.4 分数排序不足、shadow pseudo-gap 不迁移、v3.5 动作对齐后果信号也不足）共同表明，**当前冻结 TSFM 的预测/重建误差对"真实动作后果"的区分度整体不足**；TSFM_RECONSTRUCT 作为算子能减半 IMPUTE 危害（0.539→0.289）但把有益率从 0.460 压到 0.172——它更像"保守中性化器"而非"修复器"，且 Crypto/Oil/USTS 上方向相反。后续方向由规划会话决定。
