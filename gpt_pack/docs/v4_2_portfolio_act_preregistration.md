# IntroAct-TS v4.2: PORTFOLIO-ACT — 预注册文档

Risk-Budgeted Counterfactual Action Portfolio for TSFM Data Governance

预注册时间：2026-09-05（服务器日期 00:55 CST），任何 v4.2 计算之前冻结。
状态：FROZEN。结果只能追加到 §11 post-hoc 区，不得改写 §0–§10。

## §0. 方法定位（不可变）

IntroAct-TS 是面向 TSFM 的数据治理 Agent：感知缺陷 → 用统计或 TSFM/TS-ICL proposer 生成治理动作 → 在不知道 clean target 与 true_kind 的部署条件下对动作做反事实风险控制 → 只提交收益足够且满足伤害、保护层与 OOD 约束的动作 → 目标是在同一 benchmark 与评价口径下超过近期顶会 baseline。本轮不得改变任务方向，不得退化为普通插补模型或单纯异常检测模型。

## §1. 与 v4.1 的本质区别

v4.1 MASK-COUNTERACT 已于 2026-09-04 关闭为 RED 诊断分支，其记录与结果保持冻结，本轮不得覆盖。v4.1 的自由度是「每窗只有一个 TSICL_LONG，只能接受或拒绝」；v4.2 换掉的正是这一自由度：

| | v4.1 | v4.2 |
|---|---|---|
| 每窗候选 | 单一 TSICL_LONG | KEEP、TSICL_LONG、linear、seasonal、conservative，以及缓存可用时的 MOMENT/fm_mean |
| 学习目标 | action-vs-KEEP | 全部适用动作之间的 all-pairs / listwise preference |
| 决策结构 | 单动作阈值接受 | 先形成安全动作集合，再在安全集合内选收益最大者 |
| 晋升依据 | 单动作 55/75 门 + 双参照 strict-Pareto | 整个 Agent 的 bcov/gain/CHR/pme/damage 增量预算门（§4） |

**v4.1 的两个门被显式废除**，理由是设计错误而非事后放宽：（i）「TSICL 单动作 B&S≥55/75」是模块级指标，与最终集成目标不一致；（ii）「同时严格支配 raw TSICL 与零伤害 abstainer」在 (coverage, harm) 平面上几何不可满足——两个参照分居任何风险受控工作点的两侧。替换门见 §4，全部在本轮运行前写定，之后不得修改。

## §2. 方法定义

1. **候选池**：每个窗口保留全部语义适用动作，KEEP 始终在候选集合中。
2. **偏好学习**：在同一 episode 内构造所有非 KEEP 动作之间的 pair。标签顺序为 **B&S > neutral > harmful**；同为 B&S 时 gain 高者优先；同为 harmful 时 loss 低者优先。
3. **两段式决策**：先由 action-specific harm controller 得到安全动作集合，再在安全集合内按预测收益排序择一；无安全动作时 KEEP。
4. **禁止入模**：source、clean、true_kind、sample_uid、任何真实标签。
5. **模型族**：优先 logistic / HGB，不得搜索大量模型与种子。TSFM latent 只作消融臂 G，不作 primary——v4.0 已证明它会过拟合合成库结构。

## §3. Phase 0：诊断与 headroom（CPU，API 0，禁止先训练）

复用 `results/v39_longgap_candidates.jsonl`、`results/v39_longgap_oracle.json`、`results/v39_longgap_probe.json`、`results/v40_phase3_pool.jsonl`、`results/v41_selector_rows.jsonl` 与 v3.9 D 的逐窗口决策记录（`results/v39_phase0_records.jsonl`）。

### §3.1 Phase 0-A：arm B 精确集成回放

把 v4.1 arm B 的长缺口动作（24 B&S / 1 harmful）按 first-commit 协议加入 v3.9 D，**完全不改阈值**。输出：commits、B&S、harmful、bcov、gain、CHR、CP95、pme、damage；与 §4 正式目标的逐项剩余差距；overlap/conflict 及最终采用动作；arm B 新增动作的 gain sum。

**这是诊断臂，即使结果正向也不形成版本。**

### §3.2 Phase 0-B：多动作 portfolio oracle

在 frozen89 开发窗口上，用已有候选统计：(1) 每窗适用动作集合；(2) 至少存在一个 B&S 动作的窗口数；(3) 14 个 harmful TSICL 窗口中存在安全替代的个数；(4) 75 个 TSICL B&S 窗口换动作会丢失的个数；(5) best-fixed-action 与 portfolio oracle 的差距；(6) oracle 各动作选中次数与 gain sum；(7) v3.9 D + portfolio oracle 的完整集成指标。

**此处允许读取开发标签测 headroom，但不得用 oracle 选择任何部署规则。**

### §3.3 Phase 0 继续门（全部为 AND）

1. long-gap 至少 **80/89** 存在 B&S 动作；
2. 至少 **10/14** harmful TSICL 窗口存在安全替代；
3. portfolio oracle 比 best fixed proposer 多恢复至少 **10** 个 B&S；
4. 集成 oracle 满足 bcov≥0.30、gain≥0.10、CHR≤0.10、pme≤0.0055、damage≤0.0402。

**未通过则停止并回归候选生成代码，不得训练选择器。**

输出：`results/v42_phase0a_integration.json`、`results/v42_phase0b_portfolio_oracle.json`。

## §4. v4.2 正式晋升门（增量预算门，运行前写定）

相对 v3.9 D 的增量：新增 B&S **≥15**；gain sum 增加 **≥5.6319**；harmful commits 由 15 降到 **≤14**；protected edits 由 2 降到 **≤1**。

最终绝对值：bcov **≥0.30**；gain **≥0.10**；action-conditional CHR **≤0.10**；CHR CP95 上界 **≤0.15**；pme **≤0.0055**；damage 不得差于 v3.9 D 的 **0.0195**。并在目标风险区间比较 risk–coverage frontier。

v3.9 D 的基线数值在 Phase 0-A 中由代码重新读出并记录，不采用记忆值。

## §5. Phase 1：选择器（仅 Phase 0 通过后执行，优先 CPU）

校准与训练总体：21k bank / 168k records 中 `gap_frac ∈ [0.05, 0.12]` 的 episode，每个 episode 保留全部适用动作。

**固定臂**：A `best_fixed_action`；B `v41_arm_B`；C `pointwise_action_classifier`；D `action_vs_keep_pairwise`；E `all_pairs_stat_only_ranker`；F `PORTFOLIO_ACT`（all-pairs ranker + action-specific harm controller + benefit ranking，primary）；G `F + TSFM latent`（消融）；H `oracle`（上界，不参与规则选择）。

**Phase 1 LODO 继续门（全部为 AND）**：top-1 B&S precision **≥0.90**；action-conditional CHR **≤0.10**；CHR CP95 **≤0.15**；safe-action recall **≥0.60**；相对 best-fixed-action 的 B&S coverage 提升 **≥0.10**；至少 **5/6** source 不劣；all-pairs 相对 action-vs-KEEP **降低 portfolio regret**；protected edit **=0**。

阈值只在各 LODO fold 的训练/验证来源上选取，不得使用 target source identity，不得看 held-out 标签后调整。**只有 Phase 1 通过才打开 frozen89 做一次 v4.2 开发决策。**

## §6. Confirmatory benchmark（协议现在冻结，v4.2-pre 通过后才生成/开标签）

frozen89 **永久只作开发集**。confirmatory 集合：新 parent、新 corruption seed；在当前 6 源之外增加 UCI ElectricityLoadDiagrams20112014（dataset 321，CC BY 4.0）与可用的 Monash 来源；方法、阈值、checkpoint、配置全部先冻结并写 sha256；**confirmatory 标签只允许打开一次**；confirmatory FAIL 后不得在该集合上调参。

## §7. 服务器与资源纪律

所有计算只在 `/root/autodl-tmp/work2`；本地只编辑、查看、同步。他人的 panorama 任务不得停止、抢占或影响。Phase 0/1 优先纯 CPU；启动前重新检查 CPU/内存/GPU/磁盘与其他进程；只有新增未缓存 TSFM 候选确有必要时才使用 GPU，且不超过实时空闲显存的 35%。API 调用保持 0。每阶段结束检查本项目残留进程。

## §8. 结果必须回归代码

异常结果逐项回到：sample_uid / candidate hash → 每窗候选集合 → applicable gate → all-pairs 标签方向 → episode/split 泄漏 → KEEP 与 first-commit → risk/benefit score 调用点 → action conflict → harmful/protected commit → 具体文件、函数与行号。禁止只用「模型泛化差」「数据不足」作结论。

## §9. 文档与 DOCX

新建本文件；同步 `docs/version_ledger.md`、`docs/diagnostic-playbook.md`、`docs/HANDOFF.md`、`docs/data_provenance_contract.md`。**v4.1 保持关闭，其记录不得覆盖。** 预注册区与 post-hoc 区分离，执行后不得回改门槛。

DOCX：RED/诊断结果不更新；只有 §4 正式门全部通过形成 v4.2-pre 才更新；基于 `docx/` 中最新进度文档；日期用 **2026-09-05**；不覆盖同日期文件，使用 `-v02`/`-v03`；保留同日期所有旧版本；只修改框架、方法、技术路线、创新点与已验证方法进展；生成、渲染与逐页检查只在服务器；回传本地后校验 sha256。

## §10. 提升纪律

v4.2 只有严格超过 incumbent / v3.9 D 才能成为正式版本；未过门只登记诊断分支；不得用改指标、改总体、改标签或事后选门槛制造提升；每一项提升必须能回溯到 sample_uid、原始记录、代码与哈希；没有正向改进时不运行 smoke350、不更新 DOCX。

---

## §11. Post-hoc 结果区（逐阶段追加）

（待填。每阶段记录：结论、耗时、资源、结果文件 hash。）

### §11.1 Phase 0 结果（2026-09-05，继续门 **未通过** 1/4，停止）

纯 CPU，API 0，GPU 未使用（期间他人 panorama 任务占 23.3 GB，未触碰）。

#### Phase 0-A：arm B 精确集成回放（诊断臂，不形成版本）

v3.9 D 基线由 `v39_phase0_records.jsonl` 经 canonical `_episode_metrics` 重新读出，**未采用记忆值**：commits 132 / B&S 117 / harmful 15 / bcov 0.2659 / gain 0.0872 / CHR 0.1136 / pme 0.0060 / **damage 0.0195**（与 §4 引用的基线一致）。

| | v3.9 D | + arm B | Δ |
|---|---|---|---|
| commits | 132 | 157 | +25 |
| B&S | 117 | **141** | **+24** |
| harmful | 15 | 16 | **+1** |
| gain sum | — | — | **+3.2194** |
| bcov | 0.2659 | **0.3205** | +0.0546 |
| gain | 0.0872 | 0.0945 | +0.0073 |
| CHR | 0.1136 | 0.1019 | −0.0117 |
| CHR CP95 | — | 0.1507 | — |
| pme | 0.0060 | 0.0060 | 0 |
| damage | 0.0195 | 0.0208 | +0.0013 |

first-commit 冲突 **0**（arm B 的 24 个长缺口动作全部落在 D 未提交的窗口上，协议未被触发）。对照 §4 正式门的剩余差距：新增 B&S 已达标（需 15，实得 24）、bcov 已超（0.3205 ≥ 0.30）；未达标项为 gain sum 尚差 **2.4125**、harmful 需降到 ≤14 而实际升到 **16**、gain 差 0.0055、CHR 超 0.0019、pme 超 0.00054、damage 超 0.00125。

#### Phase 0-B：多动作 portfolio oracle

九个冻结 proposer 的逐窗口标签：tsicl 75 B&S / 14 harmful（89 适用）、linear_bridge 69/19、impute_current_best 69/16、impute_conservative 67/18、impute_default 59/17、fm_mean 57/32、seasonal_existing 51/24、moment 46/43、openfim 33/56。75 个窗口有 8 个可选动作，其余 10/3/1 个窗口分别有 6/5/7 个。

| 继续门 | 实测 | 门槛 | 判定 |
|---|---|---|---|
| 至少一个 B&S 动作的窗口 | **81/89** | ≥80 | **PASS** |
| harmful TS-ICL 存在安全替代 | **6/14** | ≥10 | **FAIL** |
| portfolio 比 best fixed 多恢复 | **+6**（81 vs tsicl 75） | ≥10 | **FAIL** |
| 集成 oracle bcov/gain/CHR/pme/damage | 0.4341 / 0.1050 / 0.0728 / **0.0060** / 0.0195 | ≥0.30 / ≥0.10 / ≤0.10 / ≤0.0055 / ≤0.0402 | **FAIL**（仅 pme） |

**结论：1/4，按 §3.3 停止，回归候选生成代码，不训练选择器。**

#### 回归代码的归因（§8 逐项）

1. **门 2 与门 1 的 8 个窗口是同一批**：`windows_with_no_bs_action` 恰为 8 个，与 14 个 harmful TS-ICL 中缺少安全替代的 8 个重合。这 8 个窗口**全部是 `missing_block`**，来源分布为 US Term Structure 6 / ETTm1 1 / Oil Price 1。即：在这些窗口上，九个 proposer **无一** 给出 B&S 结果。这是候选池的能力边界，不是选择器的判别问题——任何选择器在一个不含安全动作的集合上都无法产出安全提交。
2. **门 3 的 +6 说明九个 proposer 高度冗余**：oracle 的选择计数为 tsicl 75、fm_mean 3、impute_conservative 2、moment 1。除 TS-ICL 外的八个 proposer 合计只贡献 6 个 TS-ICL 覆盖不到的窗口。九者机制同源（单序列插值或基础模型 infill），成功与失败的窗口高度重合，因此「多动作组合」在当前池上几乎等价于「用 TS-ICL 一个动作」。
3. **门 4 只败在 pme，且 pme 与基线完全相同（0.0060）**：portfolio 只在受污染窗口上新增长缺口动作，**结构上无法移除 D 已有的 protected edit**。§4 要求 protected edits 由 2 降到 ≤1，这与 v3.9 冻结预算的 `pme_headroom_edits = -1` 是同一件事——需要的是移除既有编辑的机制，而不是新增动作。
4. **一处必须声明的测量局限**：`stage_phase0b` 的集成使用 `v40_phase3_pool.jsonl` 的逐窗口 gain，而该池只汇集了 TSICL_LONG 家族。因此 6 个非 TS-ICL 的 oracle 选择因无 gain 记录被跳过（`n_added_from_portfolio=74`、`added_without_gain_record=6`），**门 4 的 bcov/gain/CHR 实际描述的是 TS-ICL-only oracle，而非真正的 portfolio 集成**。这不改变判定：门 2 与门 3 是纯标签集合运算，与 gain 无关。若后续要评估真 portfolio 集成，须先把非 TS-ICL proposer 的逐窗口 gain 纳入统一池。

#### 对候选生成的可操作方向（假设，待检验，不作结论）

八个不可修复窗口全为 `missing_block` 且 6/8 集中在 US Term Structure —— 该源是 40 通道耦合的远期利率曲线。现有九个 proposer 全部只使用窗口内单序列信息；同一时间戳上的兄弟通道信息从未被用于重建。这是当前候选池未覆盖的机制方向，也是 §3.3 所要求的「回归候选生成代码」的具体着力点。

耗时约 4 分钟。Phase 1 **未执行**（§5 要求 Phase 0 通过）。**不触发 DOCX**（诊断结果）。**不允许 smoke350**。incumbent 仍为 PICS_joint_relabel。
