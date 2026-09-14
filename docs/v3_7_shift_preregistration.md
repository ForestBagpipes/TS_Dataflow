# IntroAct-TS v3.7: SHIFT — 预注册文档

**Shift-aware Hierarchical Intervention Filtering with Target-weighted Risk Control（面向目标域偏移的分层动作选择与风险控制）**

- 创建日期：2026-09-03
- 状态：PLANNED（预注册冻结后才允许看 v3.7 新结果）
- **§0–§10 为预注册区**；**§11 起为 post-hoc 区**。严禁倒填、严禁事后改门、严禁事后换主臂。

---

## §0. 定位（不可变）

IntroAct-TS 是面向 TSFM 的数据治理 Agent：依据待治理序列、TSFM 部署可得响应、数据质量证据和候选治理动作，在 KEEP/DENOISE/DESPIKE/IMPUTE/RESEGMENT 中决定是否治理及采用什么动作。目标：提升 TSFM 下游效用、控制错误修改与条件危害、同基准同 TSFM 同污染协议下超过近期顶会 baseline、达到 ICLR 方法与实证要求。不得改成普通清洗、异常检测、纯 benchmark、纯审计或负结果论文。本轮不做文献调研（由规划会话负责）。

## §1. 继承事实与本轮诊断

Incumbent：**PICS_joint_relabel**（bcov 0.2727，CHR 0.2053，pme 0.0091，gain 0.0919，damage 0.0402）。

v3.6 留下的关键事实：
- `PAIR_absolute/logreg`：held-out pairwise accuracy 0.716、AUROC 0.804——**排序信号存在**；
- logreg 一致优于 HGB，禁止通过增加模型容量解决；
- ETT held-out 泛化差，28 条 harmful 全在 ETT；USTS/Oil/Crypto 排序好却因跨源 margin/calibration 几乎零提交；
- 故障必须拆成"排序错误"与"校准/选择错误"两部分，不得笼统归为特征无效。

**本轮冻结决策：采用 v3.6 的 `PAIR_absolute/logreg` 作为 action-value 基础分数。** 该选择来自冻结的 v3.6 结果，v3.7 结果出来后不得更换。

## §2. 方法定义：SHIFT 四模块

1. **Global action-value ranker**：v3.6 `PAIR_absolute/logreg`，估计候选相对 KEEP 的价值。
2. **Source specialist bank**：各训练 source 的轻量 family-aware logistic specialist；source ID 不得作为目标域样本特征。
3. **Unlabeled target fingerprint/router**：用目标批次部署可得的统计、时频结构和 TSFM 响应分布，计算目标域与各训练域相似度并组合 specialist。
4. **Target-weighted conditional-risk controller**：用无标签目标域协变量估计 calibration importance weight，直接约束已提交动作中的 harmful 比例（不是被 KEEP 稀释的 corpus risk）；支撑不足、权重退化或专家分歧过大时回退 KEEP。

本轮不更新 TSFM 参数、不用 target 真值、不加 reconstruction/prediction error view、不启用 RESEGMENT。

部署协议固定：batch 数据治理（治理前可见当前目标批次的无标签窗口）；streaming 可由最近无标签窗口组成滚动 buffer；target buffer <32 窗口进入 cold-start，默认全局保守策略或 KEEP；当前实验用 batch 模式。

## §3. Phase 0：预注册与校准上界审计（CPU 10–20 min，16–24 线程，GPU 0，API 0）

新建 `experiments/v37_shift_headroom.py`、`tests/test_v37_shift_headroom.py` → `results/v37_shift_headroom.json`、`results/v37_calibration_transfer.json`。不修改正式 src/。

### §3.1 冻结分数复现
从 `results/v36_pair_probe.json`、`results/v36_pair_predictions.jsonl`、`results/v36_pair_dataset.jsonl` 恢复 PAIR_absolute/logreg，逐 fold 复现 pairwise AUROC/accuracy、p_vs_keep、calibration margin、candidate rank、selected commit、source/family 分布。与 v3.6 差异必须 <1e-9，否则停止并回归 v3.6 代码。

### §3.2 排序问题 vs 校准问题（两个仅诊断、不得部署的 target-label oracle）
- `oracle_target_threshold_global`：保持 global score 不变，只允许 held-out 标签选 family threshold；
- `oracle_target_expert_mixture`：允许 held-out 标签选训练 source expert 的凸组合及 threshold。

记录每折在 CHR≤0.10、pme≤0.0055、damage≤0.0402 约束下的最大 bcov/gain。

**判读（决定 Phase 1 主臂，写死）**：
- 两个 oracle 都无法达到 bcov≥0.30、gain≥0.10 → SHIFT 红灯，停止；
- global oracle 达标 → 主要问题是 target calibration，Phase 1 主臂 = `SHIFT_global_IW`；
- global 不达标但 expert-mixture 达标 → 必须用 specialist router，Phase 1 主臂 = `SHIFT_expert_IW`；
- Phase 1 结果出来后不得改变主臂。

### §3.3 Calibration transfer matrix
训练 source calibration → held-out source 的完整转移矩阵：CHR、bcov、gain、pme、score quantile shift、B&S/harm score separation、threshold、commit family。目标：确认相似 source 的校准是否更可迁移。该矩阵只用于方法诊断，不能用 held-out 标签选部署专家。

## §4. Phase 1：无标签目标域 SHIFT probe（仅 Phase 0 至少一个 oracle 达标才执行）

新建 `experiments/v37_shift_probe.py`、`tests/test_v37_shift.py` → `results/v37_shift_probe.json`、`results/v37_shift_predictions.jsonl`、`results/v37_shift_weights.jsonl`。

### §4.1 Target fingerprint（按 family 分别构造，只用部署可得量）
数值特征 robust quantiles（10/25/50/75/90%）、median/MAD/IQR、missing fraction、touched fraction、trend、ACF、spectral entropy、dominant frequency、changepoint/shape/structure 特征、现有 TSFM normalized response 特征分布、family proposal rate、candidate count。禁止：source ID、true_kind、clean target、beneficial/harmful 标签、held-out loss、sample_uid 编码。标准化参数只在训练 source 拟合。

### §4.2 Specialist router
每个训练 source×family 一个 L2 logistic specialist，外加 global expert。相似权重 `π_s(x_t)=softmax(−d(F_t,F_s)/τ)`，τ 固定为训练 source 两两距离中位数（不做 held-out 调参）。主分数 `p_mix = λ·p_global + (1−λ)·Σ_s π_s·p_s`，**λ=0.5 固定**；有效 specialist 少于 2 时用 global。记录 expert disagreement；分歧超过训练 calibration 95% 分位数时拒绝该候选。

### §4.3 Target importance weighting（每 held-out fold 内）
1. source calibration candidates 与无标签 target candidates 训练平衡 L2 logistic domain discriminator；2. 不输入 task label；3. `w(x)=p(target|x)/(1−p(target|x))·(n_s/n_t)`；4. 权重裁剪到 [0.1, 10]；5. `ESS=(Σw)²/Σw²`；6. 按 family 分别计算。

低支撑判定（该 family 全部 KEEP，不得强行外推）：ESS<30；或 ESS/n<0.10；或 discriminator AUROC>0.95 且 overlap mass<0.10。

### §4.4 Cross-fitted calibration
不得只用原 20% calibration slice。训练 source 上按 sample_uid cross-fitting：每个 source row 由未见过它的 scorer 产生 OOF score；target fingerprint 和 importance weight 不用目标标签；threshold 只在 weighted OOF source episodes 上选择；直接优化 conditional harmful risk；first-commit episode replay 保持；family-specific threshold 只在 weighted accepted ESS≥30 时有效。开发阶段风险上界用按 sample_uid 的 deterministic weighted block bootstrap 95% 上界；**不得宣传为已证明的 distribution-free theorem**。

### §4.5 对比臂（不得事后删除失败臂）
1. PICS_joint_relabel；2. PAIR_absolute_logreg_global；3. SHIFT_score_quantile_only；4. SHIFT_expert_only；5. SHIFT_IW_only；6. SHIFT_overlap_only；7. SHIFT_full；8. oracle_target_threshold（仅上界）。

## §5. Phase 1 晋级门（最低"正向方法进展"门，非最终 ICLR 门）

SHIFT_full 须同时满足：CHR≤0.15；bcov≥0.2727；gain≥0.0919；damage≤0.0402；pme≤0.0091；≥2 family 有 beneficial commit；≥4/6 source 的 CHR/bcov 方向不劣于 PICS；任一 source commit 占比≤50%；risk–coverage frontier 在主要工作区间 Pareto 支配 PICS；与 PICS 的核心改善经 sample_uid 配对 bootstrap 95% CI 不跨零。

判定：全过 → 绿灯进 Phase 2；只有 CHR 或 bcov 一项轻微未达但已有带 CI 的 Pareto 改善 → 黄灯，只登记方法候选，不调第二轮参数；无 Pareto 改善、改善仅来自一折/一族、或 ESS gate 关闭大多数族 → 红灯，停止（不得运行 latent、smoke350 或新算子）。

## §6. Phase 2：正式集成（仅 Phase 1 绿灯）

新建 `src/introact_ts/shift_controller.py`、`experiments/v37_compare_arms.py`、`tests/test_shift_controller.py`；不覆盖 PICS。

正式门：CHR≤0.10；CHR CP95 上界≤0.15；conditional mean loss≤0.10；pme≤0.0055；damage≤0.0402；bcov≥0.30；gain≥0.10；synthetic/real/collision-free OOD edit 均≤0.05；≥2 family 有有效收益；≥5/6 source 不劣于 PICS；配对 bootstrap 支持改进；risk–coverage Pareto 支配 PICS。全部通过才登记正式 v3.7 并申请 smoke350；任一失败只登记诊断或候选分支。

## §7. 结果回归代码（预注册义务）

所有 harmful/new/rejected commit 回溯：sample_uid、source/stratum/family、global/specialist score、source similarity weights、domain weight、weight clipping 状态、ESS/overlap、expert disagreement、selected threshold、hard veto、candidate rank、before/after/loss/gain、first-commit 路径、产生决策的函数与代码行。重点回答六问：ETT harmful 是否被 overlap/risk controller 拒绝；USTS/Oil/Crypto 高质量候选是否从零提交恢复；改善来自专家路由/IW 还是 overlap abstention；目标污染比例改变 fingerprint 的失败；target batch 小时是否错误放宽；权重裁剪是否主导。任何异常先回归代码再谈统计解释，不得先调阈值。

## §8. 开发数据防过拟合声明

六个 real source 从本轮起标记为 **development domains**，不得再称最终 untouched test。只有 v3.7 正式门通过才进入论文级外部评价（≥3 个从未参与版本决策的新冻结数据源、固定污染/保护层/TSFM/算子/指标、规划会话核验的 baseline、多 TSFM backbone、三 seed 配对 CI）。本轮不自行搜索或选择 baseline。

## §9. 服务器纪律

只在 /root/autodl-tmp/work2 运行；本地只编辑/读取/同步/核 hash。每阶段开始记录 hostname、nvidia-smi、CPU/内存/磁盘、他人进程。本轮主要 CPU（16–24 线程，最多 32），不占满，不干扰他人，不制造无意义 GPU 工作。Phase 0/1 预计 30–60 分钟。API=0。结束清理残留进程。

## §10. 文档与 DOCX

每阶段同步：本文档、version_ledger、diagnostic-playbook、HANDOFF、data_provenance_contract。预注册与 post-hoc 严格分区。v3.6 红灯不补 DOCX。只有 Phase 1 出现经配对检验支持的 Pareto 改善或 Phase 2 正式通过才更新 DOCX（以 docx/ 最新进度文档为母版；服务器 `date +%Y%m%d` 取日期；不覆盖旧文件，同日期用 -v02/-v03；只改框架/方法/技术路线/创新点/已验证正向进展；渲染逐页检查；DOCX/渲染/代码/结果两地核 sha256）。

---

## §11. Post-hoc 结果区（逐阶段追加）

（本节全部为 post-hoc 记录，与 §0–§10 预注册内容严格分区。）

### §11.1 Phase 0：校准上界审计 — 红灯，v3.7 停止（2026-09-03）

- 实现：`experiments/v37_shift_headroom.py`（sha256 88d95a1d…1bbe94）、`tests/test_v37_shift_headroom.py`（11 项服务器测试全过）；未修改任何已有文件。
- 输出：`results/v37_shift_headroom.json`（sha256 45aec5f4…536ff8）、`results/v37_calibration_transfer.json`（sha256 7a895f56…715528）。

**§3.1 冻结分数复现：PASS（max_abs_diff = 0.0）**。6 折逐位一致：pairwise accuracy/AUROC/AUPRC、p_vs_keep、margin、selected commit 集合、source/family 分布，与 v3.6 冻结记录精确相等。

**§3.2 Oracle 上界（约束 CHR≤0.10、pme≤0.0055、damage≤0.0402，pooled）**：

| oracle | bcov | gain | CHR | pme | damage |
| --- | --- | --- | --- | --- | --- |
| oracle_target_threshold_global | 0.0409 | 0.0222 | 0.000 | 0 | 0 |
| oracle_target_expert_mixture | 0.1795 | 0.0225 | 0.048 | 0 | 0.0052 |
| 目标 | ≥0.30 | ≥0.10 | — | — | — |

两个 oracle 都不达标 → **SHIFT 红灯，Phase 1 未启动**（`phase1_primary_arm=null`）。值得注意：两个 oracle 的安全性都轻易达标（CHR 0.00/0.048、pme 0），瓶颈纯粹是**覆盖率与 gain 天花板**——冻结的 PAIR_absolute/logreg 排序在严格安全约束下只剩 18 个全 DENOISE 提交（global）或 gain≈0.02（expert mixture 上限）。这把 v3.6 的诊断收紧了一层：不只是"校准链路"坏，**当前候选池×当前排序的可提取价值上限本身就低于目标**。

**§3.3 Calibration transfer matrix 要点**：
- 排序可迁移、阈值不可迁移：所有 source 对在 target 上的 B&S AUROC 多 >0.72（Oil target 0.99），但跨源 quantile shift 最大 −0.49，USTS/Crypto 校准迁移到 ETT 后 CHR 0.35–0.46；
- ETTh2 作为 target 是主要伤害汇聚点（三个校准源迁入 CHR 0.60–0.67），与 v3.6 "28 条 harmful 全在 ETT"一致；
- "相似 source 校准更可迁移"**不成立**（distance vs CHR：Pearson r=−0.054, p=0.78）；fingerprint 距离被 Crypto 的 missingness 维度主导（z≈8200），距离近似一维——记录为 fingerprint 设计缺陷，供后续参考；
- USTS 行与 Crypto 行 commit 集合完全相同：已核实非 bug（系数不同但 episode 内 top 排序重合，first-commit 选出相同 31 候选）。

- 服务器耗时 9.7s（16 线程 CPU）；API 0；GPU 0。

### §11.2 v3.7 总判定：诊断分支，Phase 1/2 均未执行（2026-09-03）

按预注册 §3.2：两 oracle 均无法达到 bcov≥0.30 且 gain≥0.10 → 红灯。无 SHIFT probe、无正式集成、无 smoke350、无 API、不更新 DOCX。incumbent 仍为 **PICS_joint_relabel**（bcov 0.2727，CHR 0.2053，pme 0.0091，gain 0.0919，damage 0.0402）。

post-hoc 推断（非预注册结论）：连续五轮（v3.2–v3.7）排除的路线——阈值重排、shadow 证书、ACV 后果验证、窗口内成对排序、目标域校准——现在都收敛到同一个更硬的结论：**在当前冻结候选池上，任何"选择/校准"层都无法同时满足 bcov≥0.30 与 CHR≤0.10，因为 oracle 上限本身（bcov 0.18 / gain 0.02）已低于目标**。剩余的正向自由度只剩两个：(a) 提高候选池本身的 beneficial_and_safe 含量（新算子/新 proposer，而非新 verifier）；(b) 重审 oracle 天花板是否与标签口径或候选生成顺序有关。下一步由规划会话决定。
