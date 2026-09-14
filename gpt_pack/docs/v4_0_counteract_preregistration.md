# IntroAct-TS v4.0: COUNTERACT-TS — 预注册文档

预注册时间：2026-09-03（服务器日期），任何 v4.0 计算之前冻结。
状态：FROZEN。结果只能追加到 §11 post-hoc 区，不得改写 §0–§10。

## §0. 定位（不可变）

IntroAct-TS 是面向 TSFM 的风险可控数据治理 Agent：缺陷感知 → 候选治理动作 → 干预风险判断 → commit/abstain → 审计轨迹。核心问题：在多个候选清洗动作中选择能提升下游 TSFM 效用且不损伤数据的动作，证据不足时 KEEP/abstain。不得改成普通插补、异常检测、单纯 forecasting 或通用 AutoML。

## §1. 本轮禁止事项（冻结）

1. 不得在 v3.9 的 posterior width / 模型分歧 / seam / bridge deviation 上换分类器或调阈值；
2. 不得新增同一冻结 TSFM 的 reconstruction/forecast error view；
3. 不得使用 source_id、true_kind、clean target、sample_uid 作为部署特征；
4. 不得在冻结的 89 个长缺口窗口上反复调参（它们只作冻结评估）；
5. 未通过信号门不得集成或跑 smoke350；
6. 不做文献调研（方向已由规划会话确定）。

## §2. Phase 0：预注册与完整性（20–30 min CPU）

新建 `experiments/v40_counterfactual_bank.py`、`experiments/v40_action_critic.py`、`experiments/v40_compare_arms.py`、`tests/test_v40_counterfactual_bank.py`、`tests/test_v40_action_critic.py`。

冻结输入：PICS_joint_relabel incumbent；v3.9 D 臂；89 个 long-gap 窗口；`v39_longgap_candidates/probe/oracle`；1599-window manifest 及全部哈希。

隔离与泄漏规则（红线）：

- 候选生成完成并 freeze 后才能接触 clean/label；
- 同一 clean_parent_uid 不得跨训练/验证/测试；
- LODO 时目标 source 的任何派生窗口不得进入训练；
- 89 个 long-gap 只作冻结评估，不参与训练或阈值选择；
- true_kind/clean/source_id 不进入模型输入；source 只允许作为 Group-DRO 分组标签。

目标预算（沿用 v3.9 冻结数字）：D 臂基线至少需新增 15 个 B&S 窗口、增加 5.632 gain 总和；同时必须净移除至少 1 次 protected edit 并降低 harmful commits，否则即使加入长缺口修复也无法满足 CHR/pme。

输出：`results/v40_integrity.json`、`results/v40_target_budget.json`、`results/v40_counterfactual_bank_manifest.json`。

## §3. Phase 1：Counterfactual Action Bank（45–90 min）

pilot 规模约 4,000–6,000 episode，不直接生成超大语料。训练窗口必须与冻结评估 UID 隔离。

污染机制：missing_scattered、missing_block、spike、noise、flatline、duplicate、level_shift、10%–20% mixed corruption；每种至少 3 个 severity；missing_block 长度覆盖 5%–50% 窗口。

动作集合：KEEP、FACT_SHORT、TSICL_LONG、当前 IMPUTE/DESPIKE/DENOISE、现有 conservative/seasonal/linear proposer；仅在语义适用时生成候选。每个 episode 对所有适用动作执行。标签继续调用冻结的 canonical `compute_action_labels` 路径，不新造另一套 NMSE。

每条记录包含：episode_uid、clean_parent_uid、source、corruption、severity、family、action、candidate_hash、input_hash、mask_hash、before/after、gain、true_loss、harmful、beneficial_and_safe、protected、provenance。

数据来源：如服务器能快速取得公开数据，加入至少 8 个训练来源（优先复用 SHoTClean/公开时序数据），下载、许可证、哈希全部登记；当前 6 个开发来源仍按 LODO 隔离。

## §4. Phase 2：Action-Delta Critic（30–60 min）

模型轻量（<5M 参数）。输入：dirty series、repaired series、repair delta、raw mask/support mask、冻结 TSFM embedding before/after/delta、family/action embedding、gap length/support ratio 等部署可得结构量。禁止 source 名称、clean、true_kind、真实标签入模。

结构：共享 Siamese 1D encoder + action token + 三 head——gain 的 q10/q50/q90 分位数；harmful probability；protected-edit probability。

损失：L = pinball(gain quantiles) + λ_h·BCE(harm) + λ_p·BCE(protected) + λ_r·pairwise action-vs-KEEP ranking。训练用 source × family × severity Group-DRO。

消融比较：raw/stat-only、TSFM latent-only、delta-only、full COUNTERACT、full without Group-DRO。

**Phase 2 首个决定门（只看冻结的 89 个 TS-ICL long-gap）：**

1. harmful AUROC ≥0.75；
2. AUPRC 相对 prevalence 提升 ≥0.10；
3. 风险控制点至少保留 55/75 个 B&S；
4. harmful ≤3 且 CHR CP95 上界 ≤0.15；
5. risk–coverage frontier 严格优于 raw TS-ICL 和 v3.9 MIRAGE；
6. 至少 4/6 source 不劣化；
7. 不允许靠 source identity 获得结果。

train 好而 LODO 差 → 唯一预注册 rescue：action bank 扩到约 20,000 episode、增加公开来源、强化 source-group DRO，再训练一次。train 和 LODO 都低于门 → 立即停止，记诊断分支，不得换分类器追指标。

## §5. Phase 3：全族集成（仅 Phase 2 通过）

策略：以 v3.9 D（FACT_SHORT-first + PICS_non_IMPUTE）为基础；加入通过 critic 的 TSICL_LONG；对 D 中原有 commits 也用同一 critic 重新评估（不是只增加动作）；复用冻结的结构保护证据清除 protected/OOD edits；每个窗口选 q10(gain) 最大且 harm/protection 上界过门的动作，否则 KEEP。

比较臂：COUNTERACT_stat_only、COUNTERACT_latent_only、COUNTERACT_without_DRO、COUNTERACT_longgap_only、COUNTERACT_full（primary）、PICS_joint_relabel、v3.9 D、raw TSICL、oracle。

**v4.0-pre 晋级门：** paired bootstrap 下相对 incumbent 的 bcov 或 gain 显著提升；CHR 必须下降；pme、damage 不得变差；OOD edit≤0.05；risk–coverage frontier 至少一个非平凡区间严格支配 incumbent。

**正式 v4.0 门：** bcov≥0.30；gain≥0.10；action-conditional CHR≤0.10；CHR CP95 upper≤0.15；pme≤0.0055；damage≤0.0402；beneficial commits≥10；逐 source/family 报告且无单一来源携带全部改善；synthetic/real OOD edit≤0.05。未过 v4.0-pre 不形成版本；正式门通过才允许 smoke350（至少 3 seeds）。

## §6. 结果回归代码（预注册义务）

harmful 与 rejected-beneficial 全量台账：sample_uid、source、family、action、特征、分位数、before/after、loss、gain。每项异常数字定位到具体函数与代码行。排除 label、mask、normalization、support drift、split leakage、denominator、freeze 顺序后才能写"信号失败"。对所有提升检查是否由某一 source/family/少量 UID 携带。所有候选、模型、结果登记 manifest 与 sha256。

## §7. 服务器与资源纪律

所有生成、训练、测试、pytest、基线和统计计算只在 `/root/autodl-tmp/work2`。本地只编辑、同步、查看。开始前记录 nvidia-smi/CPU/内存/磁盘/现有进程。GPU 空闲充分利用 RTX 5090；有他人任务时限制显存 CPU，不杀不暂停不影响。CPU n_jobs≤32（按空闲量）。外部 LLM/API=0；模型和数据下载登记 URL、revision、license、sha256。全流程写日志；结束确认无本项目残留进程。不执行 git add/commit。

预计：Phase 0 20–30 min；Phase 1 45–90 min；Phase 2 30–60 min；Phase 3 视门控。

## §8. 文档与 DOCX

每阶段同步：`docs/v4_0_counteract_preregistration.md`、`docs/version_ledger.md`、`docs/diagnostic-playbook.md`、`docs/HANDOFF.md`、`docs/data_provenance_contract.md`；预注册区与 post-hoc 区严格分离，禁止回改门槛；服务器与本地逐文件 sha256 一致。

DOCX：只有 COUNTERACT 获得正向可复核改善（至少 v4.0-pre）才更新；RED 诊断或纯计划不写。触发时：以 docx/ 下最新进度文档为母版；用服务器实际日期新建文件；不覆盖旧文件，同日已存在用 -v02/-v03；只更新框架、方法、技术路线、创新点和已验证方法进展；DOCX 生成、渲染、逐页检查只能在服务器执行；同步回本地并核对 sha256。

## §9. smoke350

只有正式 v4.0 全部门过才允许申请（至少 3 seeds）；未过门不运行、不消耗 API。通过后先汇报门控表、paired bootstrap、OOD、harmful 台账，等用户确认再启动。

## §10. 最终汇报格式

总门控；主指标表；长缺口 75/14 去害结果；Pareto；逐 source/family；bootstrap；OOD；消融；harmful/rejected-beneficial 代码归因；资源耗时；API=0；代码/结果/文档路径；hash；DOCX 是否触发；smoke350 是否允许；残留进程状态。

---

## §11. Post-hoc 结果区（逐阶段追加）

### §11.1 Phase 0（完成，2026-09-03）

`experiments/v40_counterfactual_bank.py`（integrity/budget/manifest/fetch-data 四个 stage）+ `tests/test_v40_counterfactual_bank.py`（58 pure-function 用例，服务器 `w2` 环境 pytest 全绿）已上线并在服务器执行。

- **integrity**：`n_hash_mismatch=0`，`all_pass=true`。771 个评估窗口、89 个 long-gap 子集、1599 语料唯一性、PICS_joint_relabel 5 项 spot-check 全部与冻结值 4 位小数一致。→ `results/v40_integrity.json` (sha256 `ce64ebd2…`)
- **budget**：从 v3.9 原样复核并 carry-over，无漂移：D 臂需 +15 B&S 窗口、+5.632 gain、净移除 ≥1 protected edit、harmful 需降到 15 以下。→ `results/v40_target_budget.json` (sha256 `31616f76…`)
- **fetch-data**：`pub:electricity`/`pub:traffic`（laiguokun/multivariate-time-series-data GitHub 镜像）连接在 DNS/connect 层挂起，两次实测（一次无超时挂起被外层 kill，一次加 35s SIGALRM 硬超时后干净失败）确认该镜像从服务器不可达；按预注册诚实回退，公开来源 0/2，pilot 只用 6 个开发来源。→ `results/v40_data_registry.json` (sha256 `e06a883f…`)
- **manifest**：冻结 bank 设计（7 机制×3 severity×150 + 630 mixed + 420 clean = 4200 episode；missing_block 5%–50%；8 动作；red-line 字段清单）。→ `results/v40_counterfactual_bank_manifest.json` (sha256 `62142617…`)

**运行时发现并修复的基础设施问题**（工程健壮性修复，不改变实验设计，未触碰冻结数字）：`urllib.request.urlretrieve` 无超时参数导致公开数据抓取在 DNS 层无限期挂起 → 加 `socket.setdefaulttimeout` + 每次尝试 35s `SIGALRM` 硬超时。

耗时：约 12 分钟（含两次 fetch-data 重试）。API 调用 0 次。

### §11.2 Phase 1（完成，2026-09-03）

Counterfactual Action Bank pilot：4200 episode（3150 单机制 + 630 mixed + 420 clean control）× 8 动作 = 33600 条记录，全部走冻结的 `v33_labels.compute_action_labels` 路径打标签。

- **parents**：2100 父窗口（6 开发来源各 350），与 1599 语料库、771 评估帧、彼此之间三重隔离全部通过（`intersect_manifest_1599_uids=[]`、`intersect_eval_771_uids=[]`、`n_parent_series_hash_in_manifest=0`、split 不交叉）。→ `results/v40_bank_isolation.json` (sha256 `dde5cb16…`)
- **candidates → tsicl(GPU) → freeze**：33600 条候选记录 digest `3e499b40…`，`evaluate` 阶段重新推导每条候选并重验哈希，`max fill drift=0.0`（FACT_SHORT/TSICL_LONG 零观测支撑漂移的红线约束成立）。→ `results/v40_bank_freeze.json` (sha256 `36552129…`)
- **evaluate 产出**：`results/v40_bank_records.jsonl`（33600 条，含 labels 命名空间）+ `results/v40_bank_report.json` (sha256 `b2338875…`)。长缺口专项（648 个 missing_block/含 missing_block 的 mixed episode）：TSICL_LONG applicable 644，B&S 524（81.4%），harmful 120（18.6%），与 v3.9 冻结的 89 窗口 75/14 方向一致、量级可比。Train/val/test = 3368/394/438（80.2%/9.4%/10.4%），6 个开发来源在三个 split 均有覆盖。
- **GPU**：`w2-v39-impute` 环境（`tsicl==0.2.1`，checkpoint sha256 `a67ae9f6…` 与 v3.9 相同），峰值显存 251 MB，14 秒处理 649 条 worklist，0 unsupported。

**运行时发现并修复的三处实现 bug**（真实执行中触发，已定位到函数与代码行，不改变冻结的标签路径/度量/预注册门槛）：

1. `stage_parents`：窗口抽样对"本次运行内已选中的 (channel, start)"未去重，只对照冻结语料库——财金类来源历史长度较短时同一起点被跨 seed_off 迭代重复抽中，`parent_uid_unique=False`。修复：按源维护 `seen_keys` 集合去重。
2. `stage_candidates`：gated-out 的 `tsicl_long` 记录既不进 `tsicl_worklist`（该分支只在 gated-in 时触发）也不写入任何文件（末尾 `if action != "tsicl_long":` 无条件跳过），3551 个 episode 被静默丢弃，`freeze` 报 "action set 不全"。修复：`tsicl_long` 文件句柄一并预开，gated-out 记录直接写入；`stage_tsicl` 改 append 模式续写 GPU 结果并加行数断言。
3. `stage_evaluate`：标签联结处用三元表达式把 `rebuild_tsicl_output`（2 元组）与 `run_cpu_action`（4 元组）按 4 变量统一解包 → `ValueError`。修复：拆为显式 `if/else`，与哈希复核段落已有写法一致。

另有两处**未修复、确认无害的死代码路径**（从未被真实流水线调用）：`inject_bank` 对未知 mechanism 的字典查找早于分支判断，抛 `KeyError` 而非 `ValueError`；`validate_record(rec, labeled=False)` 因 `REQUIRED_RECORD_FIELDS` 与 `CANDIDATE_FORBIDDEN_KEYS` 字段集合重叠而永远无法返回空列表（流水线只以 `labeled=True` 调用）。

耗时：约 20 分钟。API 调用 0 次。GPU 峰值 251 MB，结束确认 0 MiB 释放、无残留进程。

---

### §11.3 Phase 2 implementation freeze（2026-09-04，任何 Phase 2 计算之前冻结）

本节在 Phase 2 任何训练/特征缓存之前写定。§0–§10 不变。以下全部为预注册值，训练后不得回改；违反即作废该次训练。

**服务器状态（2026-09-04 00:50 CST 记录）**：RTX 5090 0 MiB/32607 MiB、0% util、无 GPU 进程；208 核，load 14.1；内存 754 GB（可用 625）；`/root/autodl-tmp` 可用 83 GB；他人仅容器常驻服务（supervisord/autopanel/jupyter/tensorboard/proxy），无他人计算任务；无 v40 残留进程。据此 GPU 满额使用，CPU `n_jobs≤32`。

**执行环境**：`/root/autodl-tmp/envs/w2/bin/python`（torch 2.9.1+cu128，CUDA 可用，`momentfm` 已装）。TS-ICL 不再需要（候选已在 bank 内）。

**F1. 冻结 TSFM 条件输入来源与 pooling**
- 后端：`introact_ts.backends.moment.MomentTSFM`，`AutonLab/MOMENT-1-large`，HF 快照 `ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc`（与 v3.9 `results/v39_model_manifest.json` 同一 revision，MIT），`HF_HUB_OFFLINE=1` 离线读缓存，权重全程冻结、仅 `eval()` 前向。
- 输入长度 512，与窗口长度相同，无裁剪无填充。
- pooling：调用 `model.embed(x_enc, input_mask, reduction="none")` 保留 patch 轴后，对 patch 轴做**均值池化**得到单个 1024 维向量（不使用 `encode()` 的分块 n_layers 拆分——那是 v2 表示动力学研究的接口，本轮只需要一个稳定的窗口级表示）。
- 每条 applicable 记录取三个向量：`emb_before`（materialized dirty）、`emb_after`（repaired）、`emb_delta = emb_after − emb_before`。KEEP 行的 after≡before，delta 恒为 0 向量，这是刻意保留的对照。
- NaN 处理：送入 MOMENT 前用 `introact_ts.probe.materialize_for_probe` 物化（与冻结评估路径同一函数），保证 before 侧与部署时探针看到的序列一致。

**F2. 序列输入与 normalization**
- 五条通道，均长 512：materialized dirty、repaired、repair delta(= repaired − dirty_materialized)、raw missing mask、touched/support mask。
- 窗口内 robust normalization：仅用**该窗口 dirty 序列的有限点**计算 `med = median`、`scale = max(IQR/1.349, 1e-8)`；dirty/repaired/delta 三条数值通道共用同一组 (med, scale)（delta 只除 scale 不减 med），使 delta 与序列同尺度可比。两条 mask 通道不归一化。
- 归一化参数逐窗口计算，不跨窗口、不跨 source、不使用任何 held-out fold 统计量，因此结构上不可能从 held-out source 泄漏。
- TSFM embedding 标准化：逐维 z-score，均值/标准差**只在该 fold 的 inner-train parent 上估计**，应用到 inner-val 与 held-out test。
- 部署可得结构标量（不含任何标签信息）：raw-NaN 占比、最长 NaN run/T、NaN run 数、touched 占比、n_filled/T、support ratio（有限点占比）、dirty 的 robust scale 与 IQR/std 比、delta 的 L1/L∞ 相对 scale、gap 是否触边界。全部由 dirty/repaired/mask 直接导出。

**F3. 禁止入模字段（结构性保证）**
`source` / source embedding / source_id、`true_kind`、clean series、clean target、`sample_uid` 与其哈希、真实 gain/true_loss/harmful/beneficial_and_safe/protected 标签、任何冻结评估标签。特征缓存脚本以显式白名单构建张量，并在测试中断言黑名单字段不出现在特征命名空间。`source` 仅作 Group-DRO 分组标签与报告维度。

**F4. 模型结构（目标 <5M 参数）**
1. **Siamese 1D residual encoder（dirty 与 repaired 共享权重）**：Conv1d(1→64,k7,s2) → 3 个残差块（64→64→96→128，每块两层 k5 + GroupNorm + GELU，stride 2）→ mean-pool 与 max-pool 拼接 → 每支 256 维。
2. **delta encoder（独立、更小）**：输入 3 通道（repair delta、raw missing mask、support mask）→ Conv1d(3→48,k7,s2) → 2 个残差块（48→48→64）→ mean+max pool → 128 维。
3. **TSFM 投影**：before/after/delta 三个 1024 维各经独立 Linear(1024→96) + LayerNorm → 288 维。
4. **动作条件**：`Embedding(8 actions→32)` + `Embedding(6 families→16)` = 48 维。
5. **结构标量**：MLP(→64)。
6. **融合**：拼接 256+256+128+288+48+64 = 1040 → Linear(1040→256) + LayerNorm + GELU + Dropout(0.1) → Linear(256→128) + GELU。
7. **三个 head**（各自 Linear(128→·)）：gain 分位数 q10/q50/q90；harmful logit；protected-edit logit。
参数量在训练开始时实测写入 `results/v40_critic_lodo.json`，若 ≥5M 则判为违反冻结并停止。

**F5. 损失与权重（冻结）**
`L = pinball(gain q10/q50/q90) + λ_h·BCE(harmful) + λ_p·BCE(protected) + λ_r·pairwise_rank(action vs KEEP)`，λ_h=1.0，λ_p=0.5，λ_r=0.3，pinball 权重 1.0，分位点 (0.1, 0.5, 0.9)。
- pairwise ranking **只在同一 episode 内**构造：该 episode 的每个 applicable 非 KEEP 动作与它自己的 KEEP 行配对，标签为 `gain_action > gain_KEEP`，margin ranking loss。禁止跨 episode 随机配对。
- BCE 正类权重按 inner-train 的类频率倒数，上限 20。

**F6. Group-DRO（冻结更新方式）**
- 分组键：`source × family × severity`。ERM warm-up 5 epoch，之后启用 Group-DRO。
- 在线指数权重：`q_g ← q_g · exp(η_q · L_g)` 后归一化，`η_q = 0.01`。
- **每组损失先按 episode 聚合**（episode 内 action 行取均值）再按组平均，33600 个 action 行不作独立样本。
- 小组保护与上限：episode 数 <20 的组先按 `family × severity` 并入 small-group pool；权重上限 `q_g ≤ 10/G`（G 为组数），截断后重新归一化。
- 必须报告 `max(q)/uniform`、q 的熵随 epoch 的轨迹与是否饱和；worst-group loss 下降**不能**单独作为泛化改善的结论（DRO 对离群点敏感，见 Zhai et al., ICML 2021, https://proceedings.mlr.press/v139/zhai21a.html）。
- ERM 与 Group-DRO 两版都保留为消融臂。

**F7. 优化与早停（冻结）**
seed **20260904**（首次决定门只跑这一个 seed；仅在绿灯后补 3 个 seeds）。AdamW，lr 3e-4，weight decay 1e-2，5 epoch 线性 warm-up + cosine 衰减，最多 60 epoch，batch = 64 个 episode（同一 episode 的全部 applicable action 行同批，pairwise 需要）。早停指标 = inner-val 的 `harmful AUROC + gain Spearman`（等权），patience 10，恢复最优 checkpoint。torch/numpy/cuda 随机种子全部固定，`torch.use_deterministic_algorithms` 尽力开启（不可用的算子记录在 diagnostics）。

**F8. LODO split（冻结）**
6 折，每折完整移除一个开发来源：held-out source 的**全部 parent 及其全部 episode 与 8 个 action 行**构成外层测试集；其余 5 个来源的 parent 按 `clean_parent_uid` 的 sha256 首字节做 85/15 inner-train / inner-val 二分，parent 绝不跨界。primary 评估用这 6 折 LODO，不使用 Phase 1 的随机 80/10/10 split（后者仅作 bank 内部报告）。

**F9. 阈值选择规则（冻结）**
只在该折的 inner-val 上选，绝不看 held-out source，也不使用其 prevalence。网格：`τ_h ∈ {0.02,0.04,…,0.60}` × `q10(gain) > δ ∈ {0, 1e-4, 1e-3, 5e-3, 1e-2}` × `τ_p ∈ {0.2, 0.35, 0.5, 1.0}`。对每个网格点算 inner-val 的 action-conditional CHR 及其 Clopper–Pearson 95% 上界与 B&S coverage；取**满足 CHR CP95 上界 ≤0.15 的点中 B&S coverage 最大者**。若无网格点满足，该折记 `no_calibrated_point`（沿用 v3.9 约定），不放宽。

**F10. 冻结 89 个 long-gap 的一次性打开条件**
六折 checkpoint、阈值、配置、manifest 全部写盘并 sha256 登记之后，才读取 89 窗口标签；每个窗口只由"未在其 source 上训练过"的对应 fold 模型预测。Phase 2 决定门沿用 §4 的 7 条，一字不改。

**F11. 唯一 rescue 的触发条件（冻结）**
仅当 `bank inner-val harmful AUROC ≥ 0.80` **且** `frozen-89 LODO harmful AUROC < 0.75` 才触发（含义：学会了训练来源但跨来源失效）。rescue 只做一次：bank 扩到约 20,000 episode、增加公开来源、**模型结构与主要超参数不变**、强化 source-balanced 训练、重训一次。公开来源改用官方入口（UCI ElectricityLoadDiagrams20112014 `https://archive.ics.uci.edu/dataset/321/electricity`，CC BY 4.0；Monash Forecasting Repository `https://zenodo.org/communities/forecasting/`），连接/读取超时 30–60 秒，登记 URL/license/hash；仍不可达则记 `external-data-blocked`，**不得**用 held-out 89 窗口扩充训练。
若 `bank inner-val harmful AUROC < 0.75`：判为当前输入表示无法学习动作后果，直接 RED 停止，不得更换模型追指标。

**F12'. Phase 2 结果见 §11.4；rescue 见 §11.5。**

**F12. Phase 2 产出文件（冻结清单）**
`results/v40_label_audit.json`、`results/v40_group_support.json`、`results/v40_feature_cache.*`、`results/v40_feature_manifest.json`、`results/v40_critic_lodo.json`、`results/v40_critic_predictions.jsonl`、`results/v40_critic_checkpoints.json`、`results/v40_critic_ablation.json`、`results/v40_critic_training_diagnostics.json`；代码 `experiments/v40_action_critic.py`，测试 `tests/test_v40_action_critic.py`。五个预注册臂：`stat_only`、`TSFM_latent_only`、`delta_only`、`full_COUNTERACT`、`full_without_GroupDRO`。

---

### §11.4 Phase 2 结果（2026-09-04，冻结 89 决定门 **未通过**）

**Phase 2.0 审计**（`results/v40_label_audit.json`、`results/v40_group_support.json`）：五项硬检查全过。33,600 行 = 4,200 episode × 8 动作，无丢行，不适用一律显式 `applicable=false`；无 episode 跨 parent，无 parent 跨 split，无 episode 的 8 个动作跨 split；六折 LODO 每折留出 350 父窗口 / 5,600 行，inner train/val ≈ 85/15；冻结 89 在 decide 阶段之前未被打开；protected 编辑行 739 条覆盖全部 6 个来源（≥100 且 ≥3 源）→ protection head 按预注册取 **primary** 角色。分组 180 个（6 源 × 6 族 × 5 severity），episode 级支持全部 ≥20，小组池化未触发。

**Phase 2.1 特征缓存**（`results/v40_feature_manifest.json`）：16,227 条 applicable 行；候选哈希 100% 复现；FACT_SHORT/TSICL_LONG 的观测支撑漂移 `max=0.0`；**跨两次独立进程 bit-identical**（含 GPU 上的 MOMENT embedding）。GPU 峰值 1,643 MiB，单次 61 秒。

**Phase 2.3 六折 LODO ×五臂**（`results/v40_critic_lodo.json`、`v40_critic_ablation.json`、`v40_critic_training_diagnostics.json`，30 次训练，seed 20260904）：

| 臂 | 参数量 | bank 留出源 AUROC 均值 | 最低折 | inner-val AUROC | bank bcov | bank CHR |
|---|---|---|---|---|---|---|
| stat_only | 68,389 | 0.8650 | 0.8532 | 0.8704 | 0.2019 | 0.0505 |
| TSFM_latent_only | 416,453 | 0.8745 | 0.8529 | 0.9111 | 0.3295 | 0.1221 |
| delta_only | 145,909 | 0.8874 | 0.8604 | 0.9061 | 0.2543 | 0.0975 |
| full_COUNTERACT | 954,229 | 0.8993 | 0.8646 | **0.9287** | 0.3533 | 0.1207 |
| full_without_GroupDRO | 954,229 | **0.9021** | 0.8727 | 0.9229 | 0.3557 | 0.1261 |

全部 <5M 参数（预算 respected）。**Group-DRO 未优于 ERM**：ERM 版本的留出源 AUROC 反而略高（0.9021 vs 0.8993），仅 inner-val 略低；按 Zhai et al. (ICML 2021) 的告诫，不得仅凭 worst-group loss 下降宣称泛化改善——此处连 held-out 均值都没有改善。

**Phase 2.4 冻结 89 一次性决定**（`results/v40_frozen89_decision.json`、`v40_frozen89_rows.jsonl`）：30 个 checkpoint 先复核 sha256 通过，再打开标签；89 窗口重建哈希全部复现，标签精确 75 B&S / 14 harmful。

| 臂 | commits | B&S 保留 /75 | harmful /14 | CHR | CHR CP95 | harmful AUROC | 过门 |
|---|---|---|---|---|---|---|---|
| stat_only | 14 | 14 | 0 | 0.000 | 0.193 | **0.877** | 4/8 |
| TSFM_latent_only | 23 | 21 | 2 | 0.087 | 0.249 | 0.575 | 3/8 |
| delta_only | 3 | 3 | 0 | 0.000 | 0.632 | 0.610 | 2/8 |
| **full_COUNTERACT（primary）** | 16 | 16 | 0 | 0.000 | 0.171 | **0.529** | 3/8 |
| full_without_GroupDRO | 7 | 6 | 1 | 0.143 | 0.521 | 0.499 | 2/8 |

**决定门判定：未通过。** 主要失败项：G3 保留 B&S ≥55 —— 实际仅 14–23；G1 harmful AUROC ≥0.75 —— primary 仅 0.529（stat_only 0.877 通过）；G5 CHR CP95 ≤0.15 —— 因 commit 数太少而上界宽（0.171–0.632）。安全侧本身没有问题：harmful commit 为 0–2。

**回归代码的归因（§6 义务，已逐项排除后才写结论）**

已排除：checkpoint–fold 对应（每个窗口由排除其 source 的折打分，六折阈值互不相同）；freeze 顺序（先校验 30 个 checkpoint 再读标签）；标签与哈希（89 窗口哈希复现、标签精确 75/14；Phase 3 池中用 canonical 路径重算 TS-ICL 标签同样得到 75/14，FACT_SHORT 得到 76/12，与 v3.9 冻结值一致）；support drift（TS-ICL 契约漂移恒 0）；normalization（窗口内 robust 归一，两条路径调用同一函数）；split leakage（LODO 按 source，89 窗口的 source 全在 6 个开发来源内）；分母（B&S 保留数为直接计数，bcov 分母恒为 89）。

定位到的真实成因是**训练分布与评估域的缺口尺度错配**，可追到具体常量与代码行：

- `experiments/v40_counterfactual_bank.py::SEVERITY_RANGES["missing_block"]` = low (0.05,0.12) / mid (0.15,0.30) / high (0.35,0.50)，三档等量各 150 episode；而冻结评估语料的注入器只写 25–63/512（5%–12%）。因此 bank 中 missing_block 的平均缺口占比 **0.245**，冻结 89 只有 **0.089**；support_ratio 0.755 vs 0.911；`delta_l1_over_scale` 0.338 vs 0.073。**只有 bank 的 low 档与评估域重叠。**
- 后果一（增益尺度）：TS-ICL 在 bank 大缺口上的增益中位数 0.0824 / p90 0.6494，冻结 89 只有 0.0229 / 0.2566（约 1/3.6）。`ActionCritic.head_gain` 的 q10 学到偏大的尺度，`v40_action_critic.py::PolicyView.select` 的 `q10 > delta` 门在 89 个窗口里对 **72 个**判为负增益而弃权——绑定约束是 q10 而非 harm。
- 后果二（判别力）：`head_harm` 在被大缺口结构主导的融合表示上失去分辨力，primary 的 harm_prob 在 harmful 上均值 0.300、在 B&S 上 0.266（几乎重合，AUROC 0.529）；而只用 13 个显式结构标量的 stat_only 为 0.5375 vs 0.4663（AUROC 0.877）。full 臂包含 stat 块却更差，说明不是容量问题，而是序列/TSFM/delta 分支拟合了 bank 特有结构并主导了融合表示。
- 放大因素：89 个窗口中 41 个（46%）来自 US Term Structure，而该折在 inner-val 上选出的阈值最严（`tau_h=0.04`，其余五折 0.24–0.54），进一步压低覆盖。

这一外扩本身是 Phase 1 预注册时刻意做的（bank manifest 的 `missing_block_extension` 明确写了"必须教会 critic 比评估语料更长的缺口"）。v4.0 的结论是：**该外扩在长缺口方向上买到的泛化，代价是小缺口评估域上的尺度失配与表示漂移。**

**未修改任何门槛，未在 89 窗口上调参。** 阈值全部来自各折 inner-val，`no_calibrated_point` 未发生。

耗时：Phase 2.0 约 1 分钟；2.1 约 2×61 秒（含确定性复算）；2.3 30 次训练约 48 分钟；2.4 约 20 秒。GPU 峰值 1.6 GB（训练期显存上限设为卡的 0.35，因期间出现他人任务 `calib_trainer.py`，全程未杀、未暂停、未受影响，对方任务已自行结束）。API 调用 0 次。

**执行中修复的一处真实 bug**：`stage_features` 早期版本把 KEEP / DESPIKE 在含真实 NaN 窗口上的候选输出直接当作 repaired 通道，导致 1,741 行（keep 1,232 + despike 509）的 repaired/delta 通道与 `delta_l1/linf_over_scale` 出现 NaN，并把 NaN 送进了 MOMENT（MOMENT 静默返回有限值，等于混入未经验证的语义）。修复：新增 `as_probe_series()`，按冻结标签路径的同一约定 `materialize_for_probe` 物化候选后再构造通道与 embedding；候选哈希仍对原始算子输出校验。补了 5 个针对"候选仍带 NaN"的单元测试（原合成窗口全有限，覆盖不到）。

### §11.5 唯一预注册 rescue（2026-09-04，已构建、**未完成训练**）

**触发条件成立**（§11.3 F11）：`full_COUNTERACT` 的 bank inner-val harmful AUROC = 0.9287 ≥ 0.80，冻结 89 的 harmful AUROC = 0.529 < 0.75 —— 即"学会了训练来源但跨来源失效"。rescue 因此被授权执行一次。

**运行前写下的预测（避免事后合理化）**：§11.4 的诊断指向训练分布与评估域的**缺口尺度错配**，而 rescue 的预注册内容只允许"扩到约 2 万 episode + 增加公开来源 + 强化 source 平衡"，**不允许改 severity 设计**（那属于对着冻结 89 调参，§1.4 禁止）。同分布的更多数据通常不解决分布错配，因此预计 rescue 仍不过门；但新增公开来源确实改变来源多样性，值得如实一跑。

**公开来源尝试（本轮新证据，修正 §11.1 的结论范围）**：`raw.githubusercontent.com` 不可达是**镜像特有**问题，不是全网封锁。官方入口实测全部可达：`archive.ics.uci.edu` HTTP 200 / 1.9 s，`zenodo.org` HTTP 200 / 2.4 s。UCI ElectricityLoadDiagrams20112014（dataset 321，CC BY 4.0）开始下载后实测吞吐约 40 KB/s，10 分钟仅取得 24.8 MB / 约 260 MB，按此速率需约 1.8 小时，超出本轮预算 → 终止并删除半成品，记为 **reachable-but-throughput-limited**（不是 external-data-blocked）。rescue 因此仍在 6 个开发来源上执行；UCI 源对后续轮次仍然可用，只需要更长的下载窗口。

**已完成**：`V40_BANK_SCALE=5` 重建动作库 —— 21,000 episode（7 机制 × 3 severity × 750 + 3,150 mixed + 2,100 clean）× 8 动作 = **168,000 条记录**，5,250 个父窗口（6 源各 875，每父 4 episode），隔离检查全过，freeze digest `366eb376…`，`max fill drift = 0.0`，标签走同一条冻结 canonical 路径。**severity 设计、机制集合、动作集合、模型结构与主要超参数一律未改。** 产出写入独立的 `v40_rescue_*` 路径，Phase 1/2 的产物与哈希未被触碰。

**未完成**：rescue 的特征缓存与六折重训（仅 primary 臂 `full_COUNTERACT`，因 5 倍数据下五臂全扫约需 1.5 小时 GPU，而决定门只读 primary；此范围收窄为执行层决定，已在此声明，未改动任何门槛）。服务器需要关闭，训练未启动。

**因此 v4.0 的当前状态：Phase 2 决定门未通过，rescue 已备好但未执行完毕；不形成版本，登记为诊断分支。** Phase 3 依 §5 未执行（其 `stage_arms` 内置断言会在 Phase 2 未过时直接拒绝运行）——尽管候选池 `results/v40_phase3_pool.jsonl`（1,833 条，哈希全复现）已备好，且其中用 canonical 路径重算的 TS-ICL 标签精确复现冻结的 75/14、FACT_SHORT 复现 76/12。

**恢复方法**（服务器重启后）：
1. `V40_BANK_SCALE=5 V40_RESCUE=1 V40_ARMS=full_COUNTERACT python experiments/v40_action_critic.py features`
2. 同样环境变量下 `... train`，再 `... decide`
3. 若 rescue 仍不过门 → 按 §4 记为 RED 诊断分支收尾，**不得**更换模型追指标。
