# IntroAct-TS v3.4: SCRC-PICS — 预注册文档

**Shadow-Certified, Risk-Controlled PICS（影子反事实认证的条件风险治理策略）**

- 创建日期：2026-09-03
- 状态：PLANNED（预注册完成后才开始看新结果）
- 本文档分两个区：**§0–§8 为预注册内容**（在任何 v3.4 新结果产生前冻结）；**§9 以后为 post-hoc 结果区**（逐阶段追加，明确标注 post-hoc）。严禁把结果倒填进预注册区。

---

## §0. 方法定位（不可变）

IntroAct-TS 是面向时间序列基础模型（TSFM）的数据治理 Agent。部署条件下不知道污染真值、不能访问 clean reference；Agent 为时序窗口提出治理动作，根据统计证据、TSFM 后果和风险证书决定提交或 abstain。本轮只在现有方法上优化，不改成异常检测、单纯插值/去噪、新 backbone、通用 LLM Agent 或纯 reconstruction-RMSE 清洗系统。

## §1. Incumbent 与历史继承

- **正式母体（incumbent）：PICS_joint_relabel**（v3.3 新标签协议）：
  bcov=0.273，CHR=0.205，pme=0.0091，gain=0.092，damage=0.040。
- MAST-PICS 已被 PICS Pareto 支配，本轮不再调参，仅作 negative ablation（可选第 8 臂）。
- RESEGMENT 的 oracle coverage 为 0，本轮继续封闭，不重新启用。
- v3.3 已证明：把 benefit head 改成单纯 beneficial 会丢失安全信息——v3.4 **禁止**这么做。
- v3.3 标签修复（`materialize_for_probe`、IMPUTE action-semantic 标签、canonical uncentered finite-mask NMSE、CHR 命名）全部保留，不重定义。
- 不再宣称 MAST support index 已验证；不开发新 novelty/support 模块。OOD consequence veto 沿用 v3.3 已验证的安全壳，仅作最外层 veto，不是本轮主创新。

## §2. v3.4 方法定义

保留 PICS 双监督头：

- benefit head：目标 = beneficial_and_safe；
- harm head：目标 = harmful。

接受规则：

```
accept(x,a) =
    PICS_benefit(x,a) >= tau_b[family]
    AND PICS_harm(x,a) <= tau_h[family]
    AND conditional-risk controller permits commit
    AND fixed OOD consequence veto passes
    AND shadow certificate passes（仅 IMPUTE）
```

### §2.1 Shadow Intervention Certificate（仅 IMPUTE）

动机：PICS 的 31 条 harmful commits 中 27 条是 IMPUTE；真实 missing 真值不可见。

- 不使用 true_kind 或 clean reference。
- 在原窗口有限观测区域内，选择与真实 missing evidence 几何相似的 pseudo-gap：missing_block 用连续块；scattered evidence 用分散点模式。
- pseudo-gap 不得与真实缺失目标重叠。
- 每个 sample_uid 用固定哈希种子生成 **3 个 deterministic shadow masks**。
- 每个 pseudo-gap：(a) 隐藏已知观测值；(b) 用候选 IMPUTE 方法恢复；(c) 同时运行 KEEP/`materialize_for_probe` 基准；(d) 用被隐藏但真实已知的值计算误差。
- 输出特征（至少）：
  `shadow_valid_trials`、`shadow_candidate_error_mean`、`shadow_candidate_error_q90`、`shadow_candidate_error_std`、`shadow_keep_error_mean`、`shadow_gain_mean = keep_error − candidate_error`、`shadow_gain_worst`、`shadow_stability`。
- 若观测跨度不足以完成至少 2 个有效 trial：`shadow_support=0`，本轮默认 abstain 该 IMPUTE。
- 该证书只评价算子在当前窗口局部结构上的可靠性，**不得**描述成真实缺失值的无偏误差估计。

### §2.2 Conditional-Risk Controller（CRC）

- 停止使用"所有窗口平均 corrected risk"选阈值（会被 KEEP/拒绝窗口稀释）。
- 直接计算：
  - `CHR = harmful accepted / all accepted`
  - `conditional_mean_loss = sum(loss of accepted) / all accepted`
- 阈值选择目标：在条件危害约束下最大化 beneficial coverage。
- 每个 family 独立阈值，全局仍须满足风险门。
- 报告全局、source、family、source×family 四层风险。
- CHR 用一侧 95% Clopper-Pearson upper bound；conditional mean loss 同时报告 bootstrap 或 empirical-Bernstein upper bound。
- **不允许 harm cap 落在 0.95 网格边界**；最优值在搜索边界视为校准失败。
- 先做 replay 可行性分析（Phase 1）再决定集成，不盲目重训完整版本。

## §3. 固定协议

- 标签：v3.3 action-semantic 标签（不变）；`true_kind`/`clean_series`/`clean_hash`/真值 NMSE 只在 evaluation namespace。
- 语料：冻结 seed-101 1599 窗口 manifest；候选表 `results/v33_training_data.jsonl`（2414 候选）。
- 划分：leave-one-real-dataset-out（LODO）；同一 sample_uid 的全部候选同 split；test dataset 不参与训练/归一化/calibration。
- 模型：HistGradientBoostingClassifier，max_depth=3，max_iter=100，learning_rate=0.05，l2_regularization=1.0，random_state=20260901。除非预注册明确只改一个变量，否则冻结。
- 评估：first-commit episode replay；sample_uid 配对 bootstrap（≥10000 次）；threshold search、risk certification、held-out evaluation 分开；calibration split 按 source 分层并由 sample_uid 哈希确定，记录 split hash。
- RESEGMENT 封闭；OOD 用冻结 seed-313 96 窗口集（64 synthetic + 32 real）。
- 本轮 API 调用 = 0；不重训 TSFM；不装大依赖；不做无边界网格搜索。

## §4. Phase 0：完整性与干净基线（15–20 min）

1. 检查服务器资源和残留进程。
2. 对修正后的 `experiments/v33_compare_arms.py` 做一次完整干净重跑——不得继续使用手工修补后的 OOD 分类 JSON 作为正式基线。
3. 验证：八臂主要数值与现记录一致；OOD stratum 分类正确；PICS_joint_relabel 的 first-commit 记录可逐 sample_uid 回放；manifest/hash/provenance 完整。
4. 若 PICS 数值出现超过 1e-9 的非预期变化，立即停止 v3.4，先定位代码。

输出：`results/v33_clean_rerun.json`、`results/v33_clean_rerun_manifest.json`。

## §5. Phase 1：条件风险可行性 replay（15–30 min，CPU）

新建 `experiments/v34_conditional_risk_frontier.py` → `results/v34_conditional_risk_frontier.json`。

- 只用 v3.3 已保存的 OOF/LODO PICS 分数与修正标签（或由冻结候选表 + 冻结超参确定性重建，不重跑 TSFM）。
- 以 first-commit episode 为单位细化 tau_b/tau_h 网格。
- 比较四种 selector：当前 PICS threshold；corpus-risk selector；direct conditional-risk selector；per-family conditional-risk selector。
- 每个工作点输出：commit、harm count、CHR、CHR 上界、conditional mean loss、pme、bcov、gain、damage、source/family 分布。
- 给出 risk-coverage Pareto 曲线和与 PICS 的逐 sample_uid 配对差异。

判定：
- 若仅靠阈值 replay 已存在 CHR≤0.10、bcov≥0.273、pme≤0.0091 的点，保留为 CRC-only arm；
- 无论是否存在都继续 Phase 2；不得把 post-hoc 最佳点当正式测试结果；
- 若任何阈值达到 CHR≤0.10 都使 bcov<0.20，明确记录 "score ranking insufficient"。

## §6. Phase 2：Shadow Certificate 信号探针（30–45 min）

新建 `experiments/v34_shadow_certificate.py`、`tests/test_shadow_certificate.py` → `results/v34_shadow_certificate.json`、`results/v34_shadow_records.jsonl`。

对象：全部 IMPUTE candidate；重点单独分析当前 PICS 接受的 IMPUTE；source 至少分 US Term Structure、ETTm1、ETTh2、其余来源。

完整性要求：
- shadow mask 由 sample_uid 决定，同一输入多进程结果完全一致；
- mask 不触碰真实 missing target；
- 不读取 clean/reference/true_kind；
- operator 输出和正式 IMPUTE 实现逐值一致；
- 每条记录保存 mask hash、operator hash、manifest hash。

**预注册信号门（四项）：**
1. 当前 PICS 接受的 IMPUTE 上，harmful AUROC ≥ 0.75；
2. harmful AUPRC 比现有 PICS harm score 至少提高 0.05；
3. 在误拒 beneficial_and_safe ≤20% 的工作点上：harmful IMPUTE recall ≥70%；US Term Structure、ETTm1、ETTh2 中有足够样本的来源 recall 均 ≥50%；
4. shadow_valid_trials≥2 的候选比例 ≥90%。

若四项中两项以上失败：不得集成完整 v3.4；shadow certificate 记为诊断失败；直接输出失败样本及代码路径，不做第二轮自由调参。

## §7. Phase 3：集成 SCRC-PICS（30–60 min，仅 Phase 2 基本通过时执行）

新建 `src/introact_ts/scrc_pics.py`、`experiments/v34_compare_arms.py`、`tests/test_scrc_pics.py`；不覆盖 `pics.py`/`mast_pics.py`。

正式臂：
1. v2_frozen_relabel
2. v3_2_bugfix_relabel
3. PICS_joint_relabel（incumbent）
4. CRC_only
5. shadow_veto_only
6. SCRC_PICS
7. oracle_relabel
8. MAST_support_consequence（可选，失败对照）

SCRC_PICS = PICS dual heads + shadow 特征/证书。必须报告 shadow 作为 feature / 作为 veto / joint 三种用法消融。不得把 shadow score 当真值硬编码。

## §8. v3.4 正式硬门（全部满足才登记正式版本）

安全：pme ≤ 0.0055；CHR ≤ 0.10；CHR 一侧 95% 上界 < PICS 点估计 0.205；conditional mean loss < 0.205；damage ≤ 0.040；synthetic OOD edit ≤ 0.05；real OOD edit = 0；collision-free OOD edit = 0。

活性：bcov ≥ 0.300；contaminated gain ≥ 0.100；commit rate 不靠单一 source；任一数据集占 beneficial commits ≤ 50%。

相对提升：同一 LODO/first-commit 协议下不被 PICS Pareto 支配；pme、CHR、bcov、gain 至少三项严格优于 PICS，且 CHR 与 bcov 必须同时优于；配对 bootstrap 报告差值及 95% CI。

完整性：所有新增和现有测试通过；部署路径无 true_kind/clean reference；每条结果含 sample_uid、输入/输出 hash、manifest hash、代码版本；v3.3 incumbent 可精确 replay。

任一硬门失败：v3.4 只登记诊断分支；不运行 smoke350；不第二轮自由调参；不调用外部 API。

通过后动作：smoke350 三个预注册 seed（先查资源、不用 API）；任一 seed CHR>0.15 或 pme>0.0091 即停止扩展并回归代码。外部 baseline 复现不在本轮。

## §9. harmful commit 强制代码回归（预注册的分析要求）

对 SCRC_PICS 的全部 harmful commits 输出 JSONL，逐条含：sample_uid、fold/source、true_kind（仅离线分析）、route/family/operator/method、PICS benefit/harm score、全部 shadow 特征、tau_b/tau_h、CRC 证书状态、OOD consequence 状态、最终 accept 分支、before/after/loss、对应源码函数名与行号/条件。

汇总必须回答六问：剩余伤害是否仍集中 IMPUTE；shadow 误判来源；是否单 source 主导；风险失败是 ranking/样本量/阈值实现哪类；被拒 beneficial 被哪个门挡住；coverage 损失能否由具体 veto 分支解释。

---

## §10. Post-hoc 结果区（逐阶段追加）

（本节全部为 post-hoc 记录，与 §0–§9 预注册内容严格分区。）

### §10.1 Phase 0：完整性与干净基线 — PASS（2026-09-03）

- 对修正后的 `experiments/v33_compare_arms.py` 做了完整干净重跑（服务器，约 41 min，2400% CPU，无 GPU、无 API），输出到独立的 `results/v33_clean_rerun*.json` 五件套 + `results/v33_clean_rerun_manifest.json`（输入/代码/输出 sha256 全登记）。
- 与既有 `results/v33_arms_compare.json` 深比较：**全部数值差异为 0（容差 1e-9）**；仅有的结构差异是修正版脚本在 `historical_dev` 的 per-form 记录里新增 `stratum` 字段，以及旧文件里手工补丁留下的 `config/ood_classification` 说明字段。无超过 1e-9 的非预期变化。
- OOD stratum 分类正确：`ood:exchange`/`ood:solar` = real_ood；`ood:random_walk`/`staircase`/`pulse_train`/`sawtooth` = clean_ood（synthetic 64 窗、real 32 窗）。PICS_joint_relabel synthetic 编辑 4/64=0.0625（全部是 pulse_train 上的 DESPIKE），real 0/32；MAST_support_consequence 0/64、0/32。
- first-commit 逐条核对：`v33_clean_rerun_harmful.json` 与旧记录的 `harmful_commits`/`all_commits` 按 (sample_uid, family) 序列完全一致（PICS_joint_relabel：151 commits / 31 harmful；MAST_support_consequence：102 / 31）。
- **结论：v3.3 基线干净可复现，手工修补版 JSON 已被干净重跑完全取代为正式基线；v3.4 可以继续。**

### §10.2 Phase 2：Shadow Certificate 信号探针 — 诊断失败（3/4 门 FAIL，2026-09-3）

探针对象：全部 1154 条 IMPUTE 候选；评估总体 = PICS_joint_relabel 接受的 106 条 IMPUTE commits（27 harmful / 79 beneficial_and_safe，与 v3.3 记录逐条一致，106/106 join 成功）。

四项预注册信号门：

| 门 | 结果 | 数字 |
| --- | --- | --- |
| 1. harmful AUROC ≥ 0.75（主特征 shadow_gain_mean） | **FAIL** | AUROC = 0.351 |
| 2. harmful AUPRC 比 PICS harm score 提高 ≥ 0.05 | **FAIL** | 0.2063 vs 0.1986（+0.0077） |
| 3. bs 误拒 ≤20% 时 harmful recall ≥70% 且有样本来源 ≥50% | **FAIL** | recall = 7.4%（2/27）@ bs 误拒 10.1%；USTS 7.7%（1/13）、ETTm1 0%（0/9） |
| 4. shadow_valid_trials ≥ 2 的候选比例 ≥ 90% | **PASS** | 1151/1154 = 99.74% |

- 失败是**信号层面**而非实现层面：完整性硬校验全部通过——冻结语料经 `build_calibration.build(n=1600, seed=101, source='mixed')` 精确重建（1599 窗、0 hash 不匹配）；1154 条候选的证书路径算子输出与候选表 `output_hash` 逐值一致（0 不匹配）；证书不读 clean/true_kind；`tests/test_shadow_certificate.py` 15 项服务器测试全过（含两独立进程逐字节一致）。
- 反向信号解释：harmful 接受的 IMPUTE 平均 shadow gain（0.2851）反而略高于非 harmful（0.2771）。shadow gain 大只说明"填充远好于 KEEP/ffill"，这多出现在 KEEP 极差的窗口，与该窗口真实 missing 目标上是否有害不对应——**pseudo-gap 上的可观测误差对真实 missing 目标的 harmfulness 区分度不足**。report-only 特征（candidate_error_mean/q90/std、keep_error_mean、stability）AUROC 也仅 0.44–0.68。
- 25 条未被工作点捕获的 harmful 样本清单在 `results/v34_shadow_certificate.json` 的 `evaluation.failure_samples`；逐候选记录在 `results/v34_shadow_records.jsonl`（1154 条，含 mask hash、trial 级 operator hash、manifest hash）。
- **按预注册 §6：四项中三项失败 → 不集成完整 v3.4，shadow certificate 登记为诊断失败分支，不做第二轮自由调参，Phase 3 不执行。** 若要再把 shadow 用作特征，属于新预注册范围。

输出与 hash：
- `results/v34_shadow_certificate.json` sha256 fbd16c4eb6baa7d831f78156fc7d5c313052d7dacac32ad1c97ed2702353f31e
- `results/v34_shadow_records.jsonl` sha256 bc61e17867cf89196d2194e4ce7d53fec6f252fc9fba7579e0f5fcff974f40e7
- 服务器耗时 13.1s（语料重建 12.4s + 证书计算 0.4s，n_jobs=32）。

### §10.3 Phase 1：条件风险可行性 replay — score ranking insufficient（2026-09-03）

新建 `experiments/v34_conditional_risk_frontier.py`（未改动任何已有文件），输出 `results/v34_conditional_risk_frontier.json`（sha256 `0266d23f269a3c1dd36d82e2f5b04a9d56287236a85d5902cb2c00b2a6260bdd`）。PICS 的 LODO 分数由冻结候选表 + 冻结 HGB 配置确定性重建（不重跑 TSFM）。

**完整性自检 PASS**：重建分数经原始代码路径（`PICS.decide`）回放 first-commit episode，pooled 与 6 个折的 PICS_joint_relabel 指标与 `results/v33_arms_compare.json` 全部一致（容差 1e-9；committed=151、CHR=0.205298、bcov=0.272727、pme=0.009063、damage=0.040207、gain=0.091899）。

关键结果（pooled held-out，771 窗口）：

| selector | commits | harm | CHR | CHR CP95 上界 | bcov | pme | damage | gain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pics_threshold（原样回放） | 151 | 31 | 0.2053 | 0.267 | 0.2727 | 0.0091 | 0.0402 | 0.0919 |
| corpus_risk（去 spread gate 对照） | 165 | 42 | 0.2545 | 0.316 | 0.2795 | 0.0242 | 0.0545 | 0.0925 |
| direct_conditional（严格 CHR≤0.10 且 CP 上界≤0.10） | 0 | 0 | — | — | 0 | 0 | 0 | 0 |
| per_family_conditional（严格） | 0 | 0 | — | — | 0 | 0 | 0 | 0 |
| direct_conditional（宽松敏感性 CP<0.205，非正式） | 51 | 19 | 0.3725 | 0.497 | 0.0727 | 0.0091 | 0.0246 | 0.0262 |
| per_family_conditional（宽松） | 21 | 9 | 0.4286 | 0.628 | 0.0273 | 0.0030 | 0.0117 | −0.0001 |

- 严格门在 6/6 个 calibration 折上都找不到可行阈值 → 诚实 selector 提交 0。post-hoc oracle 全网格（9801 点，直接看 held-out，仅作上界分析）：CHR≤0.10 的点上 bcov 最大仅 **0.0614**；oracle per-family 两轮坐标上升也只到 bcov=0.0932 / CHR=0.0889（45 commits、4 harm），且 IMPUTE/DENOISE 的 cap 落在 0.01 搜索边界（已记录为边界命中）。
- **判定（预注册 §5）：score ranking insufficient**——在所有 CHR≤0.10 阈值下 bcov<0.20 成立。PICS 分数排序本身把 harmful 候选排在前面，单靠阈值 replay 无法控制条件风险。
- 宽松门只在 ETTh2/ETTm1 两折可行且 LODO 泛化失败（held-out CHR 0.37/0.43）：calibration 上认证的"安全"阈值跨数据集不迁移。
- corpus_risk 对照显示 spread gate 本身在做功（去掉后 CHR 0.205→0.255、pme 0.009→0.024）。
- 配对 bootstrap（10000 次，seed 20260901）：所有 conditional selector 的 bcov 相对 PICS 显著为负（例：direct_cpUB205 diff=−0.114，95% CI [−0.137, −0.092]）。
- 代码事实：PICS 阈值选择在 `PICS.fit` → `select_episode_thresholds`（`src/introact_ts/pics.py:184-186` → `src/introact_ts/contextual_shield.py:166-220`）；可容性判据是 corrected corpus risk ≤ 0.03（`contextual_shield.py:160-162, 180-182`）——即被 KEEP 稀释的量；网格上限 0.95（`contextual_shield.py:133`）即 v3.3 harm cap 饱和来源。
- 服务器耗时 456.8s（CPU，线程限 32，峰值 RSS 410MB）。

### §10.4 v3.4 总判定：诊断分支，未形成正式版本（2026-09-03）

- Phase 0 PASS：v3.3 基线干净可复现。
- Phase 1：score ranking insufficient——CRC 单独无法达标。
- Phase 2：shadow certificate 3/4 门 FAIL——信号不足，按预注册不集成。
- **Phase 3 未执行**（预注册 §6 的硬条件）。无 SCRC_PICS 臂，无烟 350，无 API 调用，无第二轮调参。
- v3.4 登记为诊断分支。incumbent 仍是 **PICS_joint_relabel**（bcov 0.2727，CHR 0.2053，pme 0.0091，gain 0.0919，damage 0.0402）。
- 两个独立证据（分数排序不足 + pseudo-gap 信号不迁移）共同指向：下一步需要能提高**候选级排序质量**的新部署可得信号或新算子族，而不是在现有分数上继续调阈值。
