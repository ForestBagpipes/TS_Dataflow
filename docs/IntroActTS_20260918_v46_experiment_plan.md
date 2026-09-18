# IntroAct-TS 实验执行规划（v46 冻结版）

面向对象：执行实验的 Agent。
上游依据：`G:/introact_ts_iclr27_review_log.md` §37（时间预算冻结版）、§53（结果结构）、§48（mask 裁决）、§54（加速判断）、§55（解释规则）、§56（页数合规）、§57（一句话总指令）。
LaTeX 目标文件：`latex/IntroActTS_20260918_v45_review.tex`（正文 9 页，**1111** 个 `\ph{}` 占位符）。
回填后另存为 `latex/IntroActTS_<date>_v46_<stage>.tex`，不要就地覆盖 v45。
本文件不改变算法，只规定跑什么、按什么顺序跑、结果填到哪里。

> **v46 与 v45 的差异（先读这一段）**
> v45 版规划与 LaTeX 有 13 处口径冲突，本版逐条修掉。执行 Agent 只能按本文件执行，
> v45 版规划已作废。差异清单：
> 1. 主表 roster 改为 `KEEP + Best Fixed + R2-CART + T1 + TOI + TATO + SRDI`，加 `IntroAct-TS`；
>    `ChannelTokenFormer` 降为 **external forecasting reference**（只报 Overall 与成本，无 per-backbone 列，不入 rank，不进 Table 2）。
> 2. `TOI-VSF` 与 `GIMCC` 移出主表，只出现在附录 B extended comparison。
> 3. 30/50% severity **统一为与 Table 3 相同的七方法**，不再要求全 baseline。
> 4. **删除 E.1 全 baseline historical-support refit**（原先要求所有 baseline 在 25/50/100% 重训，是最贵的一批）；
>    只保留 IntroAct-TS 自己的 replay-bank 25/50/100% 消融，且列为 P2。
> 5. replay bank 按 **backbone × source × horizon** 分片。
> 6. 新增 **gate harm cap** 冻结项，值必须从实际配置读出并写进 `freeze_note.md`。
> 7. `fig1_stats.json` 的 action 键换成真实 catalog 五元组。
> 8. 占位符总数由 1322 收敛到 1111，family 重新划分。
> 9. `VIDA`、finance case study、ordering stability 全部关闭。
> 10. 新增"诊断计数规则冻结"一节，把四条 CPU 规则写死。

---

## 0. 一句话总指令

**先只读核查 final TEST 与实际代码口径，再冻结一个不改算法的 v46；主 GPU 任务只负责生成
unique-input prediction cache，所有 selector、oracle、heterogeneity、reconstruction 与 utility
对比、harm、ablation、bootstrap、表格与图片都从同一份 cache 派生；10% 做主比较，30/50% 只做
七方法核心 robustness；删掉 support refit、VIDA、finance、extra horizons、10-seed full matrix
等非必要分支；优先产出能够完整填满修订后 LaTeX 的主文与附录结果。**

---

## 1. 最终交付物与验收标准

| 编号 | 交付物 | 位置 | 验收标准 |
|---|---|---|---|
| D1 | 最终 TEST manifest（split boundary、parent id、origin id） | `results/v46/protocol/test_manifest.json` | 每个 source 一份，含 TRAIN/TEST 边界与 $L+H$ purge 说明 |
| D2 | catalog prediction cache（unique input hash → prediction） | `results/v46/pred_cache/` | 按 `source/backbone/horizon` 分片，可增量写入，可断点续跑 |
| D3 | 主比较结果（Table 1） | `results/v46/main_results/main_10.json` | 8 方法 × 3 backbone × 2 horizon × 8 source + MACRO，另加 CTF 的 Overall 与 Oracle 诊断 |
| D4 | harm / governance 诊断（Table 2） | `results/v46/diagnostics/harm.json` | 6 指标 × 8 方法（不含 CTF） |
| D5 | severity robustness（Table 3） | `results/v46/robustness/severity.json` | 3 severity × 7 方法 × 3 backbone |
| D6 | ablation（Table 4） | `results/v46/ablations/ablation.json` | Full + A1–A5 + Reconstruction Oracle |
| D7 | 附录表（per-source / per-pattern / per-severity / replay size / gate grid / 3-mask / extended） | `results/v46/` 对应子目录 | 全部可从 D2 派生 |
| D8 | 成本与失败审计 | `results/v46/cost_audit/cost.json` | offline 成本、online 成本、失败率、超时率、P95 延迟 |
| D9 | `fig1_stats.json` | `latex/figure/fig1_stats.json` | schema 见 §11，供 Figure 1(a) 直接读取 |
| D10 | 回填后的 `.tex` 与 PDF | `latex/IntroActTS_<date>_v46_<stage>.tex` | 0 error、0 undefined reference、0 Overfull、正文 ≤ 9 页 |

**硬性验收**：D3 的每一个 cell 都必须来自同一份 D2 cache，不得出现某个方法单独重跑
backbone 推理的情况。

---

## 2. P0：开跑前冻结（只读核查与登记，不跑任何重任务）

结论写进 `results/v46/protocol/freeze_note.md`，逐条给出「已确认 / 需要补」的判定。
**十项全部登记完毕才允许启动 P1。**

### 2.1 最终 TEST population（最高优先级）

1. 只读检查 split 逻辑，确认每个 source 是否存在真正未参与开发的 chronological TEST。
2. 若已存在：登记 manifest 与 split boundary（`\ph{TEST_MANIFEST}`、`\ph{TEST_SOURCES}`、
   `\ph{TEST_PARENTS}`、`\ph{TEST_ORIGINS}`），并确认 TEST 与所有设计决策、超参选择、
   归一化完全隔离。
3. 若不存在：**必须先补独立 TEST 再开始主结果**。禁止把 TRAIN-eval 改名冒充 TEST。
4. 同时登记三个 TRAIN 子块规模：replay-fit（`\ph{FIT_SOURCES}` / `\ph{FIT_PARENTS}` /
   `\ph{FIT_ORIGINS}`）、gate（`\ph{GATE_*}`）、TRAIN-eval（`\ph{EVAL_*}`）。

### 2.2 方法冻结：不新增任何模块

不加入 support gate，不新增 learned encoder，不改变 action catalog。只允许修符号与文字：

- 状态向量写作 $z_{i,a}$；
- 动作数用 $J$（$\calA = \{a_0, \dots, a_J\}$），近邻数用 $k$；
- `KEEP` 是 act-or-keep 的 reference action $a_0$，$\calA^{+} = \calA \setminus \{a_0\}$；
- 术语 `legal` → `admissible`，`lower-confidence` → `conservative score`；
- 只有 $\max_{a \in \calA^{+}} S_a > 0$ 才执行，否则返回 reference action。

**action catalog 已冻结为代码里的五元组**，不得改名、不得增删：

```
ACTIONS = ("KEEP", "FFILL", "SINGLE_TSICL", "MULTI_TSICL", "CONTEXT_RIDGE")
REFERENCE_ACTION = "KEEP"
```

### 2.3 Scope claim 冻结

只声称 registered missingness grid 内的 selective intervention，以及 configuration transfer
到 held-out backbone family。删除 out-of-support、formal risk guarantee、
natural-missingness generalisation 三类超出证据的表述。

### 2.4 实验协议冻结

- 8 sources：ETTh1、ETTh2、ETTm1、ETTm2、Electricity、Exchange、Traffic、Weather；
- 3 frozen backbones：Chronos-Bolt、TimesFM-2.5、Chronos-2；
- $L = 512$，$H \in \{96, 192\}$，`PARENT_STRIDE = 704`；
- 4 deterministic missingness patterns（P1–P4），severity 10 / 30 / 50，`MAIN_SEVERITY = 0.10`；
- 主矩阵使用**一个** deterministic protocol seed（`PROTOCOL_SEED = 20260917`）；
- Chronos-Bolt 与 TimesFM-2.5 用于方法开发；Chronos-2 只在配置冻结后进入，算法与超参完全一致，
  replay bank 用 Chronos-2 自己重建。因此正文只能称 **configuration transfer**，不能称
  replay-bank transfer。

**replay bank 必须按 horizon 分片（v46 新增约束）。**
realised utility 在预测 horizon 上度量，所以 $g_{i,a}$ 在 $H = 96$ 与 $H = 192$ 是两个不同的量，
不能共享同一个邻域。落盘路径固定为：

```
results/v46/replay_bank/<backbone>/<source>/<horizon>.npz
```

一个请求只与自己 horizon 匹配的 bank slice 打分。`ReplayRecord` 已含 `horizon` 字段，
这一步不需要改任何算法，只是切分与索引方式。

### 2.5 指标冻结（v46 修正）

- Primary = **source-macro MASE**；Secondary = **RMSSE**；
- MSE / MAE 只保留在 per-source 附录；
- **MASE 与 RMSSE 共用同一个 seasonal naive difference series，但不共用它的幂次**：

$$\mathrm{MASE} = \frac{\mathrm{MAE}}{\frac{1}{T-m}\sum_t \lvert y_t - y_{t-m} \rvert},
\qquad
\mathrm{RMSSE} = \sqrt{\frac{\mathrm{MSE}}{\frac{1}{T-m}\sum_t (y_t - y_{t-m})^2}}$$

- seasonal period $m$ 取 `protocol.py` 的 `SEASONAL_PERIODS`：
  ETTh1/ETTh2 = 24、ETTm1/ETTm2 = 96、Electricity = 24、**Exchange = 5**、Traffic = 24、Weather = 144。
  注意 Exchange 是 5 不是 7，回填季节表时按代码写。
- denominator 在 **TRAIN** 上算，用 target channel 的 seasonal naive error。
- 季节性退化（TRAIN 常数或全缺失）时 metric **报 missing，不报 0**。
- channel aggregation、source-macro aggregation 两处口径写进配置文件并在结果里可追溯。

### 2.6 统计冻结

- parent 是外层统计单位，先核查 parent 是否重叠；
- 若 parent 已按不重叠或 block 组织，继续用 paired cluster bootstrap；
- 若高度重叠，改用现有可生成的 temporal block id 聚类；
- 主比较用 **2,000 次** bootstrap 与 Holm correction，不再增加 resample 数
  （`BOOTSTRAP_RESAMPLES` 在协议里登记为 10,000，主比较只取前 2,000 次，登记清楚即可）；
- mask 变体**不作为独立统计样本**。

### 2.7 baseline 与模型版本冻结（v46 修正）

主比较 roster 固定为八行，另加两个非排名行：

| 行 | 类型 | 需要跑的实验 |
|---|---|---|
| Native KEEP | Frozen TSFM | 无额外训练，读 cache |
| Best Fixed | Frozen TSFM | 无额外训练，读 cache 后处理 |
| R2-CART | Selector | 只在 TRAIN 上拟合一次 |
| T1 | Reconstruction | 每个 source 训练一次 |
| TOI | Task-oriented | 每个 source 训练一次 |
| TATO | Data-side adaptation | 每个 source 训练一次 |
| SRDI | Missing-input repair | 每个 source 训练一次 |
| IntroAct-TS | Frozen governance | 读 cache，无 backbone 重跑 |
| ChannelTokenFormer | **External reference** | 完整预测架构，只报 Overall 与成本，无 per-backbone 列，不入 rank，不进 Table 2 |
| Catalog Oracle | Diagnostic | 纯后处理，灰色，不入 rank |

- `TOI-VSF` 与 `GIMCC` **不进主表**，只在附录 B extended comparison 出现。
  - `TOI-VSF` 有官方 repo（`docs/baseline_audit.csv` 记为 `vendored_pending`），照常跑，
    回填 `\ph{TOIVSF_BOLT/_TF/_CH2/_OVR/_RANK}`。
  - `GIMCC` 无官方实现（记为 `no_code_unsupported`）。**它是 best-effort 项，不占关键路径**：
    在吞吐探针窗口内找不到可比实现就直接把该行写成 unavailable，**不要自己重实现**，
    重实现的结果与原文数字不可比。回填 `\ph{GIMCC_*}` 只在拿到可比实现时才做。
- `VIDA` 无官方实现（`no_code_unfound`），**完全不跑**，LaTeX 里已删除其占位符。
- 固定 model revision、baseline code revision、failure policy。
- pretraining-overlap audit 只做文档，不新增数据集。

登记到 `\ph{REV_BOLT}`、`\ph{REV_TF}`、`\ph{REV_CH2}`、`\ph{PROTOCOL_COMMIT}`。

### 2.8 gate harm cap 冻结（v46 新增，P0）

方法节写的是「harmful-intervention rate 不超过一个预先登记的 cap，然后取 gate MASE 最好的格点」，
但**代码里目前不存在这个 cap**。`matching.py` 的 `ConservativeSelector` 只有
`k / beta / local / use_intervention / use_forecast / conservative / exclude_reference_from_bank`
参数，gate 判据就是 $\max S_a > 0$，没有任何 cap 逻辑。

因此这一项必须在读取 TEST 之前作为协议常量落地：

1. 从当前 resolved 配置里读出实际使用的 cap 值（若无显式配置，取 gate split 上
   harmful-intervention rate 的一个预先声明分位数，并把这个定义写清楚）；
2. 把值写进 `freeze_note.md` 与配置快照；
3. 回填 `\ph{GATE_HARM_CAP}`；
4. 明确 fallback：没有任何格点满足 cap 时，退回最保守的格点，也就是 penalty strength 最大的那个。

**cap 与最终选中的 $(k, \beta)$ 都不能在 evaluation 数据上选。**

### 2.9 诊断计数规则冻结（v46 新增，P0）

四条规则全是 CPU 后处理，不耗 GPU 时间，但必须在读 TEST 记录之前固定，否则同一份预测会
报出不同的数。回填时不得改动这些定义。

1. **Oracle-best action**：取 admissible action 中 realised loss 最小的那个。
   **打平按 frozen catalog order 取第一个**，所以各 action 的 best-episode share 之和为 1。
   unsupported、aliased、failed 的 action 不属于 admissible，**排除在 argmin 之外**，
   不能当成一个 loss 计入。
2. **Utility sign**：$g_{i,a} = 0$ 表示该 action 与 reference 在该 episode 上不可区分。
   **严格 $g_{i,a} < 0$ 才计 harmful，严格 $g_{i,a} > 0$ 才计 beneficial**，
   零值既不进 conditional harmful rate 也不进 beneficial precision，单独报一个计数。
3. **Beneficial precision**：分子是 utility 严格为正的已执行干预数，分母是已执行干预数。
   **分母为 0 时报 missing，不报 0。**
4. **Opportunity strata**：no-op 边界与 low-to-high 边界是 gate split 上**预先声明的两个分位数**，
   只算一次，原样用到 TEST。所有方法共用同一对边界，**不按方法重算**。
   两个值都要与 resolved 配置一起登记。

### 2.10 freeze note

上面 2.1–2.9 的结论、cap 值、两个 strata 边界、四个 revision、协议 commit
全部落进 `results/v46/protocol/freeze_note.md`，并在其中显式声明
「以下决策在读取任何 TEST 记录之前完成」。

---

## 3. 运行架构：数据产物 DAG 与缓存原则

**不要按「实验名称」一个个重跑，要按数据产物 DAG 组织。** 六个原则：

1. **Trainable imputer 每个 source 只训练一次**，使用 TRAIN 中预先定义的 severity mixture，
   不按 backbone 重训。
2. **candidate repaired inputs 按 `source/parent/horizon/pattern/severity/method` 生成一次并缓存。**
3. **每个 frozen backbone 对每个 unique input hash 只预测一次。** KEEP、四个 catalog actions、
   以及各 published baseline 的输入全部写入 prediction cache。
4. **Best Fixed、R2-CART、IntroAct-TS、Catalog Oracle、Action Heterogeneity、A1–A5
   全部只读同一份 catalog cache**，不重复任何 backbone inference。
5. **bootstrap、rank disagreement、risk–intervention curve、表格与图片全部在 CPU 上与 GPU
   主任务并行后处理。**
6. **每完成一个 source/backbone 就立刻写 raw prediction 与 aggregate**，避免整批失败后重跑。

依赖关系：

```
TRAIN split ──> replay bank 构建（按 backbone/source/horizon 分片）
                    └─> catalog action outcomes（cached）
TEST split ──> candidate inputs ──> unique-input prediction cache ──┬─> Table 1 主比较
                                        │                            ├─> Action Heterogeneity
                                        │                            ├─> Reconstruction vs Utility
                                        │                            ├─> Harm / governance（Table 2）
                                        │                            ├─> A1–A5 消融（Table 4）
                                        │                            ├─> 30/50 robustness（Table 3）
                                        │                            └─> 全部附录表
                                        └─> CPU 后处理：bootstrap / 曲线 / 图 / 表
```

---

## 4. 吞吐探针与裁剪顺序

### 4.1 先做 10–15 分钟吞吐探针

正式全量前，用一个固定小切片测量三件事：

1. 每个 baseline 的训练 / 推理吞吐；
2. 三个 backbone 的 unique-input inference 吞吐；
3. candidate construction 的耗时。

用真实 ledger 外推剩余 ETA。**不要凭经验估。**

### 4.2 固定裁剪顺序（不允许看结果后挑实验）

若探针显示时间不够，按下面顺序裁，前面的裁完才允许动后面的：

1. 先取消 3-mask stability；
2. 再取消 replay-size ablation（它已经是 P2）；
3. 再把 30/50% robustness 缩成 KEEP、R2-CART、T1、TATO、IntroAct-TS；
4. **最后才允许减少 10% 主比较。**

**10% 的 full main table、Action Heterogeneity、Reconstruction-vs-Utility、Selective Harm
与核心 Ablation 永远不裁。** 这套顺序保证最先保住的是决定 accept/reject 的证据。

---

## 5. P1：必须产出的主证据（七项）

### P1-1 Action Heterogeneity（纯后处理）

直接从 catalog action 的 TEST 预测派生：

- oracle-best action 在每个 episode 上的分布 → `fig1_stats.json` 的 `best_action_share`
  （五键 `KEEP / FFILL / SINGLE_TSICL / MULTI_TSICL / CONTEXT_RIDGE`）；
- Best Fixed 与 Catalog Oracle 的 gap → `best_fixed_gap`、`\ph{MAIN_HET_GAP}`；
- 各 action 的 positive / harmful utility rate。

打平规则按 §2.9 第 1 条。**几乎不增加模型推理。** 这是 Introduction 的第一条动机证据，必须有。

### P1-2 Reconstruction vs Forecast Utility（纯后处理）

- within-parent rank disagreement → `\ph{RANK_DISAGREE_STATS}`；
- pairwise discordance → `\ph{DISCORDANT_RATE}`；
- winner agreement；
- pooled Spearman correlation（仅作 descriptive summary）→ `\ph{RHO_BOLT}` / `\ph{RHO_TF}` / `\ph{RHO_CH2}`；
- 额外产出 non-deployable 的 **Reconstruction Oracle** 诊断 → `\ph{RECON_ORACLE_MASE}`、`\ph{ABL_ORACLE_*}`。

**重建排名只收真正输出 hidden-position 重建的方法（T1 / TOI / SRDI）**，
回填 `\ph{REC_T1_*}` / `\ph{REC_TOI_*}` / `\ph{REC_SRDI_*}`。
IntroAct-TS 返回的是执行输入后的预测，**不进这个排名**。Reconstruction Oracle 单独作
catalog diagnostic，不与任何方法同列比较。

全部来自已有 controlled-deletion 结果。

### P1-3 Main Comparison at 10%（Table 1）

- 规模：8 sources × 3 backbones × 2 horizons × 4 patterns；
- 方法：八行排名 roster（§2.7）+ CTF external reference + Catalog Oracle diagnostic；
- headline 用 MASE 与 RMSSE，**删除跨 source 的 raw Overall MSE**；
- Catalog Oracle 单独灰色 diagnostic，不参与 rank；
- 回填 `\ph{SRC_<BACK>_<METHOD>_<H>_<SRC>}` 系列（432 个）与
  `\ph{<METHOD>_BOLT/_TF/_CH2/_OVR/_RMSSE/_RANK}`；
- 文字结论回填 `\ph{MAIN_READING}`、`\ph{MAIN_DELTA_CI}`、`\ph{MAIN_BACKBONE}`、
  `\ph{MAIN_BASELINE_SPREAD}`、`\ph{MAIN_R2CART}`、`\ph{MAIN_RANK}`、`\ph{STRONG_BASELINE}`。

### P1-4 Selective Harm（Table 2）

输出六个量：intervention rate、conditional HIR、harmful loss、beneficial precision、
missed opportunity，以及默认 operating point 的 MASE。

- 表内只放共享 frozen-backbone reference contract 的方法（八行，**不含 CTF**）；
- 回填 `\ph{HARM_IR_*}`、`\ph{HARM_HIR_*}`、`\ph{HARM_HL_*}`、`\ph{HARM_BP_*}`、
  `\ph{HARM_MO_*}`、`\ph{HARM_MASE_*}`；
- 计数规则严格按 §2.9；
- risk–intervention curve 从已存 score **后处理**，`\ph{HARM_RISKCURVE}`；
  **不在 TEST 上重新选择阈值**。

### P1-5 核心 Ablation（Table 4）

A1 Global Utility、A2 w/o Intervention State、A3 w/o Reference-Forecast State、
A4 w/o Conservative Gate、A5 Parametric Utility Predictor。

- **复用同一 catalog prediction cache，原则上不重跑 backbone**；
- Reconstruction Oracle 作诊断，不训练新模型；
- 回填 `\ph{ABL_FULL_*}`、`\ph{ABL_A1..A5_*}`（MASE / IR / HIR / HL / CALLS / LAT）、
  `\ph{ABL_ORACLE_*}`、`\ph{AF_*}` 系列；
- 文字结论 `\ph{ABL_READING}`。

### P1-6 Backbone transfer

Chronos-2 保留完整 10% 主矩阵。其 replay bank 由 Chronos-2 自己离线构建，
正文明确称 **configuration transfer**。回填 `\ph{ROBUST_CH2}`、`\ph{OURS_CH2}`、
`\ph{RB_*_CH2}` 等。**CTF 没有 per-backbone 列，不要给它填 CH2 cell。**

### P1-7 End-to-end cost

优先使用正式 run 中记录的 candidate construction、backbone calls、retrieval、wall-clock。

- 口径：`one forecasting-backbone call for the reference action plus one more if an
  intervention is executed`；
- 回填 `\ph{CALLS_OFFLINE}`、`\ph{CALLS_SELECTOR}`、`\ph{CALLS_CAND_N}`、`\ph{CALLS_ACT_N}`、
  `\ph{CALLS_ACT_SHARE}`、`\ph{CALLS_KEEP_N}`、`\ph{CALLS_KEEP_SHARE}`、`\ph{COST_CALLS}`、
  `\ph{COST_LATENCY}`、`\ph{CALLS_COLD_N}`、`\ph{CALLS_COLD_LATENCY}`、`\ph{CALLS_FAIL_COST}`；
- 每个方法另有 `\ph{<METHOD>_CAND}`、`\ph{<METHOD>_CALLS}`、`\ph{<METHOD>_MEAN/_MAX/_P95}`、
  `\ph{<METHOD>_OFF}`；
- 成本表 roster：T1 / TOI / TATO / SRDI / CTF / IntroAct-TS；
  **扩展方法（TOI-VSF、GIMCC）不给独立成本行**；
- 若需要专门测速，只在预先固定的代表性 request subset 上重复，**不做完整第二遍**。

---

## 6. P1.5：缩减稳健性矩阵（全而不重）

10% 是完整主比较。30% 与 50% 只跑覆盖全部核心对照类型的七类，
**与 Table 3 使用同一套方法，同一批记录**：

| 类别 | 方法 | 占位符前缀 |
|---|---|---|
| no-op | Native KEEP | `\ph{RB_KEEP_30/50}` |
| fixed policy | Best Fixed | `\ph{RB_BF_30/50}` |
| simple selector | R2-CART | `\ph{RB_R2_30/50}` |
| reconstruction | T1 | `\ph{RB_T1_30/50}` |
| task-oriented | TOI | `\ph{RB_TOI_30/50}` |
| data-side adaptation | TATO | `\ph{RB_TATO_30/50}` |
| ours | IntroAct-TS | `\ph{RB_OURS_30/50}` |

**SRDI 不在这一套里**，附录 C 的 10/30/50 三张表与 Table 3 都用这七类。

同时回填 `\ph{RB_*_10}`、`\ph{RB_*_CH2}`、`\ph{RB_*_WORST}`、`\ph{ROBUST_10/30/50}`、
`\ph{ROBUST_CH2}`、`\ph{ROBUST_WORST}`、`\ph{ROBUST_READING}`，以及
`\ph{SEV10-*}` / `\ph{SEV30-*}` / `\ph{SEV50-*}` 系列（键名用连字符风格
`SEV30-XXX-YYY`，例如 `SEV30-TOI-MASE`）。

**Per-pattern 结果固定在 10% 主矩阵上生成**，不增加额外推理 → `\ph{P<1..4>_<METHOD>}`、
`\ph{PR_<METHOD>}`。论文只声称 within-grid robustness，**不声称 50% unseen**。

---

## 7. P2：只做低成本附录（主要为后处理）

保留并执行：

1. full per-source / per-pattern / per-severity tables；
2. **replay size 25 / 50 / 100%，只做 IntroAct-TS 自己的 bank**
   （复用 replay 与 prediction cache）→ `\ph{RS25_*}` / `\ph{RS50_*}` / `\ph{RS100_*}`；
   **不做任何 baseline 的 support refit**，见 §8；
3. $k$、$\beta$ gate grid → `\ph{OPPSENS_<HALF/ONE/TWO>_<LOW/HIGH/NOOP/OVR>}`；
4. full feature-group ablation（若只需重算 selector）；
5. failure / timeout audit → `\ph{CALLS_FAIL_*}`、`\ph{CALLS_TIMEOUT_*}`、`\ph{FAILRATE}`；
6. reproducibility manifests 与 raw-record schema。

**Mask stability 只做 3-mask 代表性检查，不做 10 seed 全量重跑：**

- 主 seed + 2 个额外 deterministic mask seeds，共 3 个 realisation；
- 预先固定的 stratified TEST subset：全部 8 sources、P1–P4、10% severity、$H = 96$、
  Chronos-Bolt 与 held-out Chronos-2；
- 只比较 Native KEEP、R2-CART、IntroAct-TS；
- 报告 3 个 mask realisation 的 mean / range → `\ph{SEED1..3_MASE/_DELTA/_IR}`、
  `\ph{SEED_SPREAD_BOLT/_CH2}`、`\ph{SEED_IR_SPREAD_BOLT/_CH2}`；
- **seed 仍不作为独立统计样本。**

---

## 8. 明确删除项（不再为其保留占位符）

以下分支不执行，也不应在结果里出现。**v46 已从 LaTeX 删掉对应占位符，
若结果里出现这些键说明跑错了版本。**

- **E.1 全 baseline historical-support refit**（原先要求所有 baseline 在 25/50/100%
  重新拟合，三张表）。这是最贵的一批，与「replay size 是低成本后处理」直接冲突，整块删除。
  只保留 IntroAct-TS 自己的 replay-bank 消融，且降为 P2；
- VIDA extended comparison（无官方实现）；
- ordering stability / record-order reshuffle 消融（`ABL_STAB_*`、`ABL_RANKFULL_*`）；
- finance case study 与全部 `FIN*` 占位符；
- P5 asynchronous availability；
- support gate 与 OOD leave-one-* stress tests；
- 新 GIFT-Eval 数据集；
- additional horizons；
- previous-cycle Frank–Wolfe negative-result 数值表；
- 新的 reconstruction-supervised learned selector；
- 10-seed 全量稳定性表。

---

## 9. 结果解释规则（先于数字冻结，避免看结果改口径）

1. **Action heterogeneity**：若 Best Fixed 与 Catalog Oracle 的 gap 很小，不能把
   instance-level selection 写成强必要性，收窄为「can help on heterogeneous episodes」。
   gap 清楚存在才保留强动机。
2. **Reconstruction vs utility**：若 within-parent rank correlation 高且 winner agreement
   很高，删除「reconstruction is unreliable」强结论，只说二者并不完全等价。
3. **A4 gate**：若去掉 gate 后 HIR / HL 明显上升而 MASE 没有同步改善，
   conservative act-or-keep 得到直接支持。若 gate 几乎不影响 harm，不要把它写成主要创新点。
4. **R2-CART**：IntroAct-TS 必须至少在 primary metric 或 harm/accuracy trade-off 上体现
   相对 simple selector 的可解释优势，否则复杂方法缺少必要性。
5. **Chronos-2**：只要冻结配置不重新调参并保持可用，就支持 configuration transfer。
   不要求它在每个 cell 都最好。
6. **Published baselines**：主表报告所有真实结果，不因为某个 baseline 赢某些 cell
   就删除或更换。
7. **CTF**：它是 external reference，只报 Overall 与成本。**不要因为它在某个 backbone
   上表现好就给它加 per-backbone 列**，也不要把它放进 Table 2。

---

## 10. LaTeX 占位符回填契约

**完整键清单**：`docs/v46_placeholder_keys.csv`（1111 行，两列 `key,family`，无 `other` 残留）。
执行 agent 按 `family` 分组逐批回填。

### 10.1 family 汇总

| family | 数量 | 键模式 | 来源实验 | 落到哪里 |
|---|---|---|---|---|
| `table1_per_source_cell` | 432 | `SRC_<BACK>_<METHOD>_<H>_<SRC>`，`<METHOD>` ∈ `KEEP/BF/R2/T1/TOI/TATO/SRDI/OURS/ORACLE` | P1-3 | 附录 B per-source 表（3 backbone × 2 horizon 各一张） |
| `appendix_severity_table` | 109 | `SEV<10/30/50>-<METHOD>-<MASE/RMSE/MAE/MSE/RANK>` | P1.5 | 附录 C severity 表 |
| `appendix_ablation` | 55 | `AF_<FULL/A1..A5/ORACLE>_<MASE/RMSE/MAE/MSE/CHIR/HL/IR/CALLS>` | P1-5 | 附录 E 全量消融表 |
| `table2_harm` | 55 | `HARM_<IR/HIR/HL/BP/MO/MASE>[_<METHOD>]`、`HARM_RISKCURVE`、`HARM_READING` | P1-4 | Table 2 + Figure 3(b) |
| `table1_per_source_macro` | 54 | `SRC_<BACK>_<METHOD>_<H>_MACRO` | P1-3 | 附录 B macro 行 |
| `table1_ranked_cell` | 53 | `<METHOD>_<BOLT/TF/CH2/OVR/RMSSE/RANK>` | P1-3 / P1-7 | Table 1 表头列 |
| `appendix_cost` | 47 | `CALLS_*`、`COST_*`、`<METHOD>_<CAND/CALLS/MEAN/MAX/P95/OFF>` | P1-7 | 附录 F |
| `table4_ablation` | 47 | `ABL_<FULL/A1..A5/ORACLE>_<MASE/HIR/HL/IR/CALLS/LAT>`、`ABL_READING` | P1-5 | Table 4 |
| `appendix_per_pattern` | 40 | `P<1..4>_<METHOD>`、`PR_<METHOD>` | P1-3 后处理 | 附录 B per-pattern 表 |
| `table3_robustness` | 40 | `RB_<METHOD>_<10/30/50/CH2/WORST>`、`ROBUST_*` | P1.5 | Table 3 |
| `appendix_mask_stability` | 25 | `SEED1..3_<MASE/DELTA/IR>`、`SEED_SPREAD_*`、`SEED_IR_SPREAD_*`、`SEED_MASK/ORDER/SELECTOR` | P2 | 附录 E |
| `appendix_operating_points` | 24 | `NOOP_<METHOD>`、`LOWOP_<METHOD>`、`HIGHOP_<METHOD>` | P1-4 后处理 | 附录 B |
| `narrative_sentence` | 22 | `MAIN_READING`、`HARM_READING`、`ABL_READING`、`ROBUST_READING`、`RANK_DISAGREE_STATS`、`DISCORDANT_RATE`、`CONCLUSION_CLOSING`、`CONCL_*`、`ABSTRACT_CLOSING`、`COLDSTART`、`STRONG_BASELINE` | 全部 | 正文自然语言段 |
| `appendix_opportunity_strata` | 20 | `OVR_<METHOD>`、`STRATUM_<NOOP/LOW/HIGH>_<N/SHARE/MED/P90>` | P1-1 后处理 | 附录 B |
| `appendix_extended_comparison` | 18 | `TOIVSF_<BOLT/TF/CH2/OVR/RANK>`、`CTF_<OVR/RMSSE/OFF/CAND/CALLS/MEAN/P95/MAX>` | P1-3 / P1-7 | 附录 B / F |
| `appendix_reconstruction` | 17 | `REC_<T1/TOI/SRDI>_<MASE/MAE/MSE/GAIN>`、`RECON_ORACLE_MASE`、`RHO_*`、`DISCORDANT_RATE` | P1-2 | 附录 D |
| `appendix_replay_size` | 15 | `RS<25/50/100>_<MASE/IR/HIR/HL/CALLS>` | P2 | 附录 A |
| `appendix_protocol_counts` | 14 | `TEST_*`、`FIT_*`、`GATE_*`、`EVAL_*` | P0 | 附录 A |
| `appendix_gate_grid` | 12 | `OPPSENS_<HALF/ONE/TWO>_<LOW/HIGH/NOOP/OVR>` | P2 | 附录 E |
| `appendix_reproducibility` | 11 | `REV_<BOLT/TF/CH2>`、`PYVERSION`、`NUMPYVERSION`、`PANDASVERSION`、`SKLEARNVERSION`、`TORCHVERSION`、`HARDWARE`、`PRECISION`、`PROTOCOL_COMMIT` | P0 | 附录 G |
| `doc_comment` | 1 | 文件头注释里的示例键，不是真实占位符 | — | — |

**v46 已删除、不要再建的键族**：`FIN*`（finance）、`VIDA_*`、
`SUPPORT<25/50/100>_<METHOD>`（全 baseline support refit）、`OFFLINE_<METHOD>`、
`ABL_STAB_*` / `ABL_RANKFULL_*`、`CTF_BOLT` / `CTF_TF` / `CTF_CH2`（CTF 无 per-backbone 列）。

### 10.2 回填纪律

1. **数字格式统一**：MASE / RMSSE / MAE / RMSE / MSE 保留 3 位小数；百分比保留 1 位小数；
   call count 用整数；延迟用毫秒整数。
2. **不要改动词汇**：占位符周围的句子已按「不用引号、破折号、分号」写死，
   回填只替换 `\ph{...}` 本身，不要顺手重写句子。
3. **不要新增表格行**：Table 1–4 的行集合已与 §53 冻结，增行会破坏 9 页预算。
4. **一致性检查**：`\ph{SRC_*_MACRO}` 必须等于对应 `SRC_*_<SRC>` 的 source-macro 聚合；
   `\ph{<METHOD>_OVR}` 必须与 `\ph{SRC_*_<METHOD>_*_MACRO}` 的聚合一致。回填脚本里加断言。
5. **Oracle 行永远是灰色 diagnostic**，不参与 rank，回填时保持 `\oracle{}` 包裹。
6. **回填后必须重编译并检查**：0 error、0 undefined reference、0 Overfull、正文 ≤ 9 页。

---

## 11. `fig1_stats.json` schema

Figure 1(a) 直接读这个文件，**文件缺失时脚本画虚线占位，绝不造数**。

```json
{
  "best_action_share": {
    "KEEP": 0.0,
    "FFILL": 0.0,
    "SINGLE_TSICL": 0.0,
    "MULTI_TSICL": 0.0,
    "CONTEXT_RIDGE": 0.0
  },
  "best_fixed_gap": 0.0,
  "n_episodes": 0,
  "protocol_seed": 0
}
```

- 五个键就是 `src/introact_ts/v44/protocol.py` 里的 `ACTIONS`，顺序即 frozen catalog order。
  **不要用 `MEAN_IMPUTE / LOCF / CHANNEL_MEDIAN / INTERP`**，那套名字在代码里不存在；
- `best_action_share`：每个 catalog action 成为 oracle-best 的 episode 占比，五键之和为 1。
  打平按 frozen catalog order 取第一个，与 §2.9 第 1 条一致；
- `best_fixed_gap`：best fixed catalog action 与 catalog oracle 的 source-macro MASE 差距；
- `n_episodes`：参与统计的 evaluation episode 数，应等于 `\ph{TEST_PARENTS}` ×
  `\ph{TEST_ORIGINS}` 的口径；
- 生成后重跑 `latex/figure/build_figures.py` 重出
  `fig1_selective_governance.eps/.pdf/.pptx`。

---

## 12. 结果落盘目录

```
results/v46/
  protocol/          test_manifest.json, freeze_note.md, split_boundaries.json
  pred_cache/        <source>/<backbone>/<horizon>.parquet（unique input hash → prediction）
  replay_bank/       <backbone>/<source>/<horizon>.npz
  baselines/         <method>/<source>/*.json
  train_eval/        TRAIN-eval 与 gate 块结果
  main_results/      main_10.json, main_per_source.json, main_per_pattern.json
  diagnostics/       harm.json, rank_disagreement.json, opportunity_strata.json, governance_curve.json
  ablations/         ablation.json, feature_groups.json, replay_size.json, gate_grid.json
  robustness/        severity.json, chronos2_transfer.json, mask_stability.json
  cost_audit/        cost.json, failures.json, latency.json
```

原始记录一律保留：`raw_record_schema.json` 说明每条记录至少含
`source, parent_id, origin_id, horizon, pattern, severity, method, backbone_revision,
input_hash, action, utility, prediction_hash`。

---

## 13. 提交前自检清单

- [ ] TEST manifest 已登记，且 TEST 未参与任何设计决策；
- [ ] `freeze_note.md` 含 gate harm cap 值、两个 strata 边界、四个 revision、协议 commit；
- [ ] replay bank 按 `<backbone>/<source>/<horizon>.npz` 分片，没有跨 horizon 混用；
- [ ] 主比较每个 cell 都命中 prediction cache，无重复 backbone 推理；
- [ ] Table 1 的 `MACRO` 与 `OVR` 一致性断言通过；
- [ ] Catalog Oracle 未进入任何 rank；
- [ ] ChannelTokenFormer 只有 Overall 与成本，没有 per-backbone cell，未进 Table 2；
- [ ] harm 六项指标齐全，计数规则按 §2.9，risk curve 未在 TEST 上重选阈值；
- [ ] Reconstruction 排名只含 T1 / TOI / SRDI，IntroAct-TS 不在其中；
- [ ] A1–A5 只读同一 cache；
- [ ] Chronos-2 文字称 configuration transfer；
- [ ] 30/50% 只有七类方法，per-pattern 只在 10%；
- [ ] 3-mask 只报 mean / range，未当独立样本；
- [ ] 删除清单里的分支没有偷偷跑并写进结果（尤其全 baseline support refit）；
- [ ] 没有出现 `FIN*` / `VIDA_*` / `SUPPORT*` / `ABL_STAB_*` / `OFFLINE_*` / `CTF_<BACK>` 键；
- [ ] `fig1_stats.json` 已按 §11 生成并重出图；
- [ ] 回填后重编译：0 error / 0 undefined / 0 Overfull / 正文 ≤ 9 页。
