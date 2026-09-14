# IntroAct-TS v3.6: PAIR — 预注册文档

**Pairwise Action-Improvement Ranking（窗口内成对动作改进排序）**

- 创建日期：2026-09-03
- 状态：PLANNED（预注册冻结后才允许看 v3.6 held-out 结果）
- **§0–§10 为预注册区**；**§11 起为 post-hoc 区**。严禁倒填、严禁事后改门。

---

## §0. 定位（不可变）

IntroAct-TS 是面向 TSFM 的数据治理 Agent：读取待治理序列、TSFM 可部署侧信号和候选治理动作，在 KEEP/DESPIKE/DENOISE/IMPUTE/RESEGMENT 中决定是否修改及采用什么动作，目标是提高 TSFM 下游效用同时控制错误修改与条件危害。不改成单纯清洗、异常检测、TSFM benchmark、纯审计/负结果论文或脱离 TSFM 后果信号的预处理。

最终目标：相同数据/污染/指标/TSFM backbone 下与近期顶会 baseline 公平比较获 SOTA；方法与实验强度达 ICLR 投稿要求；体现 TSFM、数据治理、风险控制、Agent 决策、可复现工程能力。

## §1. 继承事实

Incumbent：**PICS_joint_relabel**（bcov 0.2727，CHR 0.2053，pme 0.0091，gain 0.0919，damage 0.0402）。

已证明（不得重犯）：
1. 旧 PICS 分数上调阈值无解（v3.4 oracle 上限 bcov 0.061–0.093）；
2. shadow pseudo-gap 不预测真实 missing 修复危害（AUROC 0.351）；
3. ACV primary AUROC 0.623，不能作正式风险证书；
4. 冻结 TSFM reconstruction 是中性化器（harmful 0.539→0.289 但 b&s 0.460→0.172）；
5. **禁止再添加同类 TSFM reconstruction/prediction error view**；
6. RESEGMENT 继续关闭；
7. v3.5 support-only（AUROC 0.708；DESPIKE 0.788；missing_block 0.787；IMPUTE 0.622；missing_scattered 近随机）只能作为动机，不能追认为 v3.5 正式结果。

## §2. 核心假设

PICS 把候选动作当彼此独立的绝对分类；部署真正要解决的是：同一窗口内某动作是否比 KEEP 更好、多个动作中哪个相对最好。跨数据集的绝对特征尺度、TSFM loss 和风险概率漂移；**同一窗口内的动作差分、排序和相对位置更可能消除窗口难度与数据源偏移**。

v3.6 用 episode/window 内成对偏好学习：`P(a_i ≻ a_j | x, φ_i − φ_j)`，每个 episode = 一个窗口上的 KEEP + 全部候选动作。这是候选排序器，不是新清洗算子。

## §3. 偏好标签（严格定义，不得临时创造标签）

1. beneficial_and_safe 动作 ≻ KEEP；
2. KEEP ≻ 所有非 beneficial_and_safe 动作；
3. 两个 B&S 动作之间，真实 gain 更高、loss 更低者优先；
4. 两个均非 B&S 的动作默认不参与训练；
5. clean、true_kind、source identity 只可用于训练标签审计和结果分层，**不得成为部署输入特征**。

## §4. Phase 0：预注册与完整性（CPU 5–10 min，API 0）

新建 `experiments/v36_pair_dataset.py`、`tests/test_v36_pair_dataset.py`。

数据层完整性检查（任一不过即停止并回归代码，不得继续训练）：
1. 从冻结 2414 候选重建 episode；
2. 每个 episode 唯一对应 sample_uid；
3. KEEP 必须存在且唯一（KEEP 为隐式动作时的构造规则写入代码注释）；
4. 候选 family/action 不得重复；
5. 正向 pair 与反向 pair 对称；
6. pair 不跨窗口；
7. held-out source 的窗口、pair、PCA 参数不进入训练或标定；
8. 记录 corpus manifest、input hash、code hash、pair count、episode count；
9. 复核标签、operator output 与 v3.3 relabel 表一致。

## §5. Phase 1：现有特征快速检验（CPU 15–30 min，API 0）

禁止先改正式 src/。新建 `experiments/v36_pair_ranker_probe.py` → `results/v36_pair_probe.json`、`results/v36_pair_predictions.jsonl`。

臂（至少）：
1. PICS_joint_relabel（冻结 incumbent 回放）；
2. pointwise_same_features（与 PAIR 完全相同特征的普通点式分类器）；
3. PAIR_absolute（候选绝对特征的成对差）；
4. **PAIR_episode_relative（正式候选）**；
5. oracle_relabel。

PAIR_episode_relative 特征白名单（只能由部署可得量构造）：
- candidate 相对 KEEP 的差值；
- candidate 相对 episode 中位数/最优值/最差值的差值；
- episode 内 percentile/rank；
- 候选数量；
- family/action type；
- 已有结构信号、效用信号、support 信号及其窗口内相对量；
- family 与少量预注册相对特征交互（交互项清单在代码中固定并在结果 JSON 记录）。

禁止：source ID、clean target、true_kind、held-out 标签、sample_uid 编码、全数据拟合的归一化器、held-out 结果驱动的特征增删。

模型（仓库已有依赖，不装新包）：正则化 logistic pairwise classifier；HistGradientBoosting pairwise classifier。(i,j) 与 (j,i) 对称加入训练；source-balanced sample weight；LODO 每折独立训练、标定、预测。

动作选择：每候选相对 KEEP 及其他候选的 win probability → tournament score；KEEP 默认优先；候选相对 KEEP 的 margin 与风险壳同时通过才 commit；保留已有结构/OOD consequence hard veto；RESEGMENT 关闭；first-commit 协议保留（候选顺序由部署可得 score 决定）。

## §6. Phase 1 晋级门

先报告学习问题本身：pairwise held-out accuracy；pairwise AUROC/AUPRC；top-1 B&S precision；top-1 harmful rate；分 family/source/污染类型；被选动作相对 oracle-best 的 regret。

- **绿灯**（同时满足）：pooled pairwise accuracy ≥0.70；主要 source 至少 5/6 ≥0.60；bcov≥0.2727 时 CHR 相对 PICS 降 ≥30%（≤约 0.144），或 CHR 不高于 PICS 时 bcov 绝对提升 ≥0.03；gain ≥0.0919；damage ≤0.0402；至少两个 operator family 有有效 commit。→ 直接进 Phase 3。
- **黄灯**：pairwise accuracy ≥0.65 且风险—覆盖前沿明确优于 pointwise/PICS，但未达绿灯。→ 才允许 Phase 2 latent。
- **红灯**：pairwise accuracy <0.60；或前沿无实质改善；或改善只来自单个 source/family。→ 立即停止 v3.6，不调第二轮参数，不登记正式版本。

## §7. Phase 2：support-aligned TSFM latent（仅黄灯时；GPU 15–30 min）

不是再加 prediction/reconstruction error，而是读冻结 TSFM 内部表示判断"动作改变了什么语义结构"。新建 `experiments/v36_support_latents.py`、`tests/test_v36_support_latents.py` → `results/v36_support_latents_manifest.json`。

只用现有可 encode 的冻结 backend；若只有 MOMENT 稳定暴露 embedding，如实命名 **MOMENT verifier instantiation**，不得宣称多 TSFM 通用。before/after 序列分别编码，touched mask 映射到 token/patch，只提取紧凑摘要：support token mean/max/std；support 左右 halo；before-after latent delta；support 与 halo cosine/distance；boundary latent discontinuity；support/halo layerwise delta norm；相对 KEEP 的上述差值。禁止展开完整 embedding。

PCA：最多 16 维；每 LODO fold 只在训练 source 拟合；保存 PCA 参数及 hash；held-out 只 transform；不得用标签选维度。

比较 PAIR_relative vs PAIR_relative_latent。latent 晋级（全部满足）：CHR 绝对下降 ≥0.03，或 CHR 不升时 bcov +≥0.03；pairwise accuracy +≥0.03；≥4/6 source 方向一致；不只靠 DESPIKE 单族。否则丢弃 latent，保留纯 PAIR。

## §8. Phase 3：集成与正式比较（仅 Phase 1 绿灯或 Phase 2 晋级后）

新建不覆盖：`src/introact_ts/pair_ranker.py`、`experiments/v36_compare_arms.py`、`tests/test_pair_ranker.py`。不得覆盖/破坏 PICS incumbent；独立类独立配置。

正式八臂：v2_frozen_relabel；PICS_joint_relabel；pointwise_same_features；PAIR_absolute；PAIR_episode_relative；PAIR_relative_latent（仅 latent 过门）；PAIR_without_source_balance；oracle_relabel。

**主方法选择规则（写死）**：Phase 2 未晋级 → PAIR_episode_relative 为主方法；Phase 2 晋级 → PAIR_relative_latent 为主方法；不得看正式 held-out 表后重新挑主臂。

## §9. 正式 v3.6 硬门

安全：CHR ≤0.10；CHR CP95 上界 ≤0.15；conditional mean loss ≤0.10；pme ≤0.0055；damage ≤0.0402；synthetic OOD edit ≤0.05；real OOD edit ≤0.05；collision-free OOD edit ≤0.05。

活性：bcov ≥0.30；gain ≥0.10；beneficial commits ≥10；至少两个 family 有 beneficial commit；任一 source 的 commit 占比 ≤50%。

相对改进：对 PICS 的核心安全或覆盖改进有 sample_uid 配对 bootstrap 95% CI 支持；风险—覆盖曲线在主要工作区间 Pareto 支配 PICS；不能只 pooled mean 变好而多数 source 变差。

全部通过才登记 v3.6 并申请 smoke350；否则只记诊断分支，不运行 smoke350，不调用外部 API。

## §10. 分析回归代码、停止条件、adaptive promotion、禁止事项、DOCX 条件

**回归代码**：任何 FAIL/异常/source-specific 退化必须回溯到 sample_uid、source、family/action、candidate rank、KEEP score、pairwise win probabilities、margin、hard veto、touched support、before/after/loss/gain、最终 first-commit 分支、产生判断的函数与代码行。至少输出：harmful commits 全量台账；PICS 选中而 PAIR 拒绝；PAIR 新增选中且 B&S；PAIR 新增 harmful；与 oracle-best 不一致的 episode；各类错误的代码路径与共同特征。某折失败时按序排查：标签/episode 构建 → pair 方向 → LODO 泄漏 → score 聚合 → KEEP 比较逻辑 → 特征无判别力 → 跨 source 泛化。**不能先调阈值**。

**停止条件**：Phase 0 完整性不过；Phase 1 红灯；Phase 2 latent 不晋级且 Phase 1 仅黄灯（黄灯+latent 失败 → 诊断分支）；正式硬门任一失败。停止时只登记诊断分支，不调第二轮参数，不调用 API。

**Adaptive promotion 规则**：晋级路径唯一——Phase 1 绿灯直接进 Phase 3；Phase 1 黄灯只允许 Phase 2 latent 这一条增量路径；latent 过门才进 Phase 3；其余任何组合都不得进入 Phase 3。主方法臂由 §8 写死规则决定，不得事后改选。

**禁止事项**：改 PICS 阈值；shadow masking；新增 reconstruction/prediction error view；RESEGMENT；新装包；无边界超参搜索；用 true_kind/clean/source ID 做部署特征；全数据归一化；事后挑冠军臂；本地运行任何实验。

**DOCX 更新条件**（满足任一才更新）：Phase 1 PAIR 绿灯；Phase 2 latent 过增量门；Phase 3 正式方法过门；配对检验确认新 Pareto 改善。单纯计划/红灯/诊断/失败不得写入 DOCX。更新时：以 docx/ 目录最新进度文档为母版；用服务器 `date +%Y%m%d` 取实际日期；新建当日文件不覆盖旧文件（同日期用 -v02/-v03）；只改框架、方法、技术路线、创新点和已验证正向进展；不动个人信息/计划/经费/签字；每页渲染检查版式/分页/表格/中文字体；DOCX、渲染、代码、结果本地与服务器逐一核对 sha256。

---

## §11. Post-hoc 结果区（逐阶段追加）

（本节全部为 post-hoc 记录，与 §0–§10 预注册内容严格分区。）

### §11.1 Phase 0：episode/pair 数据集 — 完整性 9/9 PASS（2026-09-03）

- 新建 `experiments/v36_pair_dataset.py`（sha256 9fed3a59…4d9e2）、`tests/test_v36_pair_dataset.py`（12 项服务器测试全过，含两进程逐位一致）；未修改任何已有文件。
- 输出：`results/v36_pair_dataset.jsonl`（5402 条 pair = 2701 正 + 2701 反严格对称，sha256 7278cb27…815539b）、`results/v36_pair_integrity.json`（sha256 3902eb7b…1556213）。
- 827 episodes = 冻结表窗口数 = sample_uid 数；KEEP 每 episode 唯一（合成隐式动作：true_loss=0、features={}，语义在代码注释）；episode↔uid 双射；pair 不跨窗口；标签抽查 20/20 与 v3.3 表逐值一致。
- pair 构成：B&S vs KEEP 2412 条（每候选恰一条 vs KEEP，规则 1/2）；B&S-B&S 287 条（规则 3）；规则 3 tie 449（不生成 pair，已计数）；规则 4 排除 non-B&S×non-B&S 1763（仅审计计数）。
- 分 source episode/pair：USTS 265/1580、ETTh1 167/1016、ETTh2 116/898、ETTm1 106/746、Oil Price 86/498、Crypto 31/236；语料内 ood:* 三源（pulse_train/random_walk/staircase）照常建 episode，是否入训练由 Phase 1 LODO 决定。
- 服务器耗时 0.84s（CPU）。本地↔服务器 sha256 一致。

### §11.2 Phase 1：PAIR 快速检验 — 红灯（2026-09-03）

- 实现：`experiments/v36_pair_ranker_probe.py`（sha256 e2231ee8…a14；未改任何已有文件，复用 PICS_JOINT_FEATURES / v2_structure_ok / EPISODE_FAMILY_ORDER）。PICS 臂为冻结记录回放（damage 复算 0.0402075 与基线逐值一致）。
- 输出：`results/v36_pair_probe.json`（sha256 1c11873f…6db）、`results/v36_pair_predictions.jsonl`（13200 行，sha256 2e58bff7…02b）。两轮运行间只修了 AUROC 口径 bug（forward 记录恒 label=1 需按镜像对评估），未改模型/特征/阈值规则。
- 判定臂 PAIR_episode_relative/HGB（pooled，771 real 窗口，LODO 6 折）：commits 68，CHR 0.412，bcov 0.0909，gain 0.0074，damage 0.0363，pme 0.0514。
- 晋级门：pooled pairwise accuracy 0.6454（<0.70 FAIL）；主要 source 4/6 ≥0.60（FAIL；ETTh1 0.497、ETTm1 0.571 拖后）；前沿门 FAIL（bcov 0.0909/CHR 0.412，距 bcov≥0.2727&CHR≤0.144 很远）；gain 0.0074（<0.0919 FAIL）；damage 0.0363（PASS）；≥2 family 有 commit（PASS，DENOISE+IMPUTE）。对照臂：pointwise_same_features/HGB CHR 0.447/bcov 0.0591；oracle bcov 0.6591。
- **判定：红灯**——前沿对 pointwise/PICS 无实质改善（`frontier_better_than_pics_and_pointwise=False`），满足 §6 红灯条件。按 §6/§10：不进 Phase 2 latent、不进 Phase 3、不调第二轮参数、不登记正式版本。
- §10 归因（未调阈值）：标签/episode 构建、pair 方向、LODO 泄漏逐一排除（断言与镜像核验全过）；绑定失败点是**跨 source 泛化**——Oil/Crypto/USTS held-out p_vs_keep→B&S AUROC 0.92–0.99，而 ETT 三源 0.67–0.78、ETTh1 近随机；68 个 commit 全部落在 ETT 三折，28 个 harmful commit 也全部在 ETT（17/28 在保护层窗口，pme 0.0514 = PICS 的 5.7 倍）；regret 集中在 noise/spike 两类污染。logreg 一致优于 HGB（0.721 vs 0.645）但仍远离门线，说明不是模型容量问题。
- 学习指标（held-out，双方向口径）：判定臂 acc 0.645/AUROC 0.724；最佳为 PAIR_absolute/logreg AUROC 0.804——成对偏好信号本身可学，但部署 margin 门在 UST/Oil/Crypto 三折全灭（p_vs_keep 被压在 [0.38,0.59]）。
- 服务器耗时 267s 纯 CPU（RSS ~280MB）；API 0；GPU 未用。

### §11.3 v3.6 总判定：诊断分支，未形成正式版本（2026-09-03）

Phase 1 红灯 → Phase 2/3 未执行。incumbent 仍为 **PICS_joint_relabel**（bcov 0.2727，CHR 0.2053，pme 0.0091，gain 0.0919，damage 0.0402）。不更新 DOCX（红灯不属于"正向方法进展"）。不申请 smoke350。

post-hoc 推断（非预注册结论）：episode 内相对化没有解决跨源漂移——窗口内差分能消除窗口难度，但 ETT 系与 USTS/Oil/Crypto 之间的**动作后果符号差异**（同类动作在不同源上危害方向不同）不是相对化能消除的；这与 v3-pre 以来反复出现的 ETT-held-out 失效是同一堵墙。
