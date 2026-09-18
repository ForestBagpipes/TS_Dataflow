# IntroAct-TS 实验执行规划（v45 冻结版）

面向对象：执行实验的 Agent。
上游依据：`G:/introact_ts_iclr27_review_log.md` §37（时间预算冻结版）、§53（结果结构）、§54（加速判断）、§55（解释规则）、§57（一句话总指令）。
LaTeX 目标文件：`latex/IntroActTS_20260918_v45_review.tex`（已冻结，正文 9 页，1322 个 `\ph{}` 占位符）。
本文件不改变算法，只规定跑什么、按什么顺序跑、结果填到哪里。

---

## 0. 一句话总指令

**先核查 final TEST 和实际代码口径，再冻结不改算法的 v45；主 GPU 任务只负责生成 unique-input prediction cache，所有 selector、oracle、heterogeneity、reconstruction/utility、harm、ablation、bootstrap、表格和图片都从同一 cache 派生；10% 做全 baseline 主比较，30/50% 做核心 baseline robustness；删掉 P5、support-OOD、extra horizons、finance、10-seed full matrix 等非必要分支；优先产出能够完整填满修订后 LaTeX 的主文与附录结果。**

---

## 1. 最终交付物与验收标准

一次完整的执行应产出下面这组文件，并且每个文件都能被 LaTeX 回填脚本直接消费。

| 编号 | 交付物 | 位置 | 验收标准 |
|---|---|---|---|
| D1 | 最终 TEST manifest（split boundary、parent id、origin id） | `results/v45/protocol/test_manifest.json` | 每个 source 一份，含 TRAIN/TEST 边界与 $L+H$ purge 说明 |
| D2 | catalog prediction cache（unique input hash → prediction） | `results/v45/pred_cache/` | 按 `source/backbone/horizon` 分片，可增量写入，可断点续跑 |
| D3 | 主比较结果（Table 1） | `results/v45/main_results/main_10.json` | 10 方法 × 3 backbone × 2 horizon × 8 source + MACRO |
| D4 | harm / governance 诊断（Table 2） | `results/v45/diagnostics/harm.json` | 6 指标 × 9 方法 |
| D5 | severity robustness（Table 3） | `results/v45/robustness/severity.json` | 3 severity × 7 方法 × 3 backbone |
| D6 | ablation（Table 4） | `results/v45/ablations/ablation.json` | Full + A1–A5 + Reconstruction Oracle |
| D7 | 附录表（per-source / per-pattern / per-severity / replay size / gate grid / 3-mask） | `results/v45/` 对应子目录 | 全部可从 D2 派生 |
| D8 | 成本与失败审计 | `results/v45/cost_audit/cost.json` | offline 成本、online 成本、失败率、超时率、P95 延迟 |
| D9 | `fig1_stats.json` | `latex/figure/fig1_stats.json` | schema 见 §11，供 Figure 1(a) 直接读取 |
| D10 | 回填后的 `.tex` 与 PDF | `latex/IntroActTS_<date>_v46_<stage>.tex` | 0 error、0 undefined reference、正文 ≤ 9 页 |

**硬性验收**：D3 的每一个 cell 都必须来自同一份 D2 cache；不得出现某个方法单独重跑 backbone 推理的情况。

---

## 2. P0：开跑前冻结（20–30 分钟，只读核查）

这一段不允许跑任何重任务，只做只读核查与登记。核查结论写进 `results/v45/protocol/freeze_note.md`，逐条给出「已确认 / 需要补」的判定。

### 2.1 最终 TEST population（最高优先级）

1. 只读检查现有代码里的 split 逻辑，确认每个 source 是否存在**真正未参与开发**的 chronological TEST。
2. 若已存在：登记 manifest 与 split boundary（`\ph{TEST_MANIFEST}`、`\ph{TEST_SOURCES}`、`\ph{TEST_PARENTS}`、`\ph{TEST_ORIGINS}`），并确认 TEST 与所有设计决策、超参选择、特征归一化完全隔离。
3. 若不存在：**必须先补独立 TEST 再开始主结果**。禁止把 TRAIN-eval 改名冒充 TEST。
4. 同时登记三个 TRAIN 子块的规模：replay-fit（`\ph{FIT_SOURCES}`/`\ph{FIT_PARENTS}`/`\ph{FIT_ORIGINS}`）、gate（`\ph{GATE_*}`）、TRAIN-eval（`\ph{EVAL_*}`）。

### 2.2 方法冻结：今晚不新增任何模块

不允许加入 support gate，不新增 learned encoder，不改变 action catalog。只允许修符号与文字：

- 状态向量写作 $z_{i,a}$；
- 动作数用 $J$（$\mathcal{A}=\{a_0,\dots,a_J\}$），近邻数用 $k$；
- KEEP 是 act-or-keep 的 reference action $a_0$，$\mathcal{A}^{+}=\mathcal{A}\setminus\{a_0\}$；
- 术语 `legal` → `admissible`，`lower-confidence` → `conservative score`；
- 只有 $\max_{a\in\mathcal{A}^{+}} S_a>0$ 才执行，否则返回 reference action。

### 2.3 Scope claim 冻结

只声称 registered missingness grid 内的 selective intervention，以及 configuration transfer 到 held-out backbone family。删除 out-of-support、formal risk guarantee、natural-missingness generalisation 三类超出证据的表述。

### 2.4 实验协议冻结

- 8 sources：ETTh1、ETTh2、ETTm1、ETTm2、Electricity、Exchange、Traffic、Weather；
- 3 frozen backbones：Chronos-Bolt、TimesFM-2.5、Chronos-2；
- $L=512$，$H\in\{96,192\}$；
- 4 deterministic missingness patterns（P1–P4）；
- severity 10 / 30 / 50；
- 主矩阵使用**一个** deterministic protocol seed；
- Chronos-Bolt 与 TimesFM-2.5 用于方法开发；Chronos-2 只在配置冻结后进入，算法与超参完全一致，replay bank 用 Chronos-2 自己重建。因此正文只能称 **configuration transfer**，不能称 replay-bank transfer。

### 2.5 指标冻结

- Primary = **source-macro MASE**；Secondary = RMSSE；
- MSE / MAE 只保留在 per-source 附录；
- MASE denominator、channel aggregation、source-macro aggregation 三处口径必须写进配置文件并在结果里可追溯。

### 2.6 统计冻结

- parent 是外层统计单位；先核查 parent 是否重叠；
- 若 parent 已按不重叠或 block 组织，继续用 paired cluster bootstrap；
- 若高度重叠，改用现有可生成的 temporal block id 聚类；
- 主比较用 **2,000 次** bootstrap 与 Holm correction，不再增加 resample 数；
- mask 变体不作为独立统计样本。

### 2.7 baseline 与模型版本冻结

- 10% 主比较保留全部五个 published baselines：TOI、TOI-VSF、GIMCC、SRDI、ChannelTokenFormer；
- 固定 model revision、baseline code revision、failure policy；
- pretraining-overlap audit 只做文档，不新增数据集。

登记到 `\ph{REV_BOLT}`、`\ph{REV_TF}`、`\ph{REV_CH2}`、`\ph{PROTOCOL_COMMIT}`。

---

## 3. 运行架构：数据产物 DAG 与缓存原则

执行 agent **不要按「实验名称」一个个重跑**，要按数据产物 DAG 组织。六个原则：

1. **Trainable imputer 每个 source 只训练一次**，使用 TRAIN 中预先定义的 severity mixture，不按 backbone 重训。
2. **candidate repaired inputs 按 `source/parent/horizon/pattern/severity/method` 生成一次并缓存。**
3. **每个 frozen backbone 对每个 unique input hash 只预测一次。** KEEP、四个 catalog actions、以及 published baseline 的输入全部写入 prediction cache。
4. **BEST FIXED、R2-CART、IntroAct-TS、Catalog Oracle、Action Heterogeneity、A1–A5 全部只读同一份 catalog cache**，不重复任何 backbone inference。
5. **bootstrap、rank disagreement、risk–intervention curve、表格与图片全部在 CPU 上与 GPU 主任务并行后处理。**
6. **每完成一个 source/backbone 就立刻写 raw prediction 与 aggregate**，避免整批失败后重跑。

依赖关系：

```
TRAIN split ──> replay bank 构建 ──> catalog action outcomes（cached）
                                            │
TEST split ──> candidate inputs ──> unique-input prediction cache ──┬─> Table 1 主比较
                                            │                        ├─> Action Heterogeneity
                                            │                        ├─> Reconstruction vs Utility
                                            │                        ├─> Harm / governance（Table 2）
                                            │                        ├─> A1–A5 消融（Table 4）
                                            │                        ├─> 30/50 robustness（Table 3）
                                            │                        └─> 全部附录表
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
2. 再取消 replay-size ablation；
3. 再把 30/50% robustness 缩成 KEEP、R2-CART、T1、TATO、IntroAct-TS；
4. **最后才允许减少 10% 主比较。**

**10% 的 full main table、Action Heterogeneity、Reconstruction-vs-Utility、Selective Harm 与核心 Ablation 永远不裁。** 这套顺序保证最先保住的是决定 accept/reject 的证据。

---

## 5. P1：今晚必须产出的主证据（七项）

### P1-1 Action Heterogeneity（纯后处理）

直接从 catalog action 的 TEST 预测派生：

- oracle-best action 在每个 episode 上的分布 → `\ph{MAIN_HET_SHARES}`；
- BEST FIXED 与 Catalog Oracle 的 gap → `\ph{MAIN_HET_GAP}`、`\ph{MAIN_FIXED_ORACLE_GAP}`；
- 各 action 的 positive / harmful utility rate。

**几乎不增加模型推理。** 这是 Introduction 的第一条动机证据，必须有。

### P1-2 Reconstruction vs Forecast Utility（纯后处理）

- within-parent rank disagreement → `\ph{RANK_DISAGREE_STATS}`；
- pairwise discordance → `\ph{DISCORDANT_RATE}`；
- winner agreement；
- pooled Spearman correlation（仅作 descriptive summary）；
- 额外产出 non-deployable 的 **Reconstruction Oracle** 诊断（`\ph{RECON_ORACLE_MASE}`、`\ph{ABL_ORACLE_*}`）。

全部来自已有 controlled-deletion 结果。

### P1-3 Main Comparison at 10%（Table 1）

- 规模：8 sources × 3 backbones × 2 horizons × 4 patterns；
- 方法：五个 published baselines + Native KEEP + Best Fixed + R2-CART + IntroAct-TS；
- headline 用 MASE 与 RMSSE，**删除跨 source 的 raw Overall MSE**；
- Catalog Oracle 单独灰色 diagnostic，不参与 rank；
- 回填 `\ph{SRC_<BACK>_<METHOD>_<H>_<SRC>}` 系列（480 个）与 `\ph{<METHOD>_BOLT/_TF/_CH2/_OVR/_RMSSE/_RANK}`；
- 文字结论回填 `\ph{MAIN_READING}`、`\ph{MAIN_DELTA_CI}`、`\ph{MAIN_BACKBONE}`、`\ph{MAIN_BASELINE_SPREAD}`、`\ph{MAIN_R2CART}`、`\ph{MAIN_RANK}`。

### P1-4 Selective Harm（Table 2）

输出六个量：intervention rate、conditional HIR、harmful loss、beneficial precision、missed opportunity，以及默认 operating point 的 MASE。

- 回填 `\ph{HARM_IR_*}`、`\ph{HARM_HIR_*}`、`\ph{HARM_HL_*}`、`\ph{HARM_BP_*}`、`\ph{HARM_MO_*}`、`\ph{HARM_MASE_*}`；
- risk–intervention curve 从已存 score **后处理**，`\ph{HARM_RISKCURVE}`；**不在 TEST 上重新选择阈值**。

### P1-5 核心 Ablation（Table 4）

A1 Global Utility、A2 w/o Intervention State、A3 w/o Reference-Forecast State、A4 w/o Conservative Gate、A5 Parametric Utility Predictor。

- **复用同一 catalog prediction cache，原则上不重跑 backbone**；
- A6 用 Reconstruction Oracle 诊断，不训练新模型；
- 回填 `\ph{ABL_FULL_*}`、`\ph{ABL_A1..A5_*}`（MASE / HIR / HL / IR / CALLS / LAT）、`\ph{ABL_ORACLE_*}`、`\ph{ABL_RANKFULL_BOLT/_TF/_CH2}`、`\ph{AF_*}` 系列；
- 文字结论 `\ph{ABL_READING}`。

### P1-6 Backbone transfer

Chronos-2 保留完整 10% 主矩阵。其 replay bank 由 Chronos-2 自己离线构建，正文明确称 **configuration transfer**。回填 `\ph{ROBUST_CH2}`、`\ph{OURS_CH2}`、`\ph{CTF_CH2}` 等。

### P1-7 End-to-end cost

优先使用正式 run 中记录的 candidate construction、backbone calls、retrieval、wall-clock。

- 口径：`one forecasting-backbone call for the reference action plus one more if an intervention is executed`；
- 回填 `\ph{CALLS_OFFLINE}`、`\ph{CALLS_SELECTOR}`、`\ph{CALLS_CAND_N}`、`\ph{CALLS_ACT_N}`、`\ph{CALLS_ACT_SHARE}`、`\ph{CALLS_KEEP_N}`、`\ph{CALLS_KEEP_SHARE}`、`\ph{COST_CALLS}`、`\ph{COST_LATENCY}`；
- 每个方法另有 `\ph{<METHOD>_CAND}`、`\ph{<METHOD>_CALLS}`、`\ph{<METHOD>_MEAN/_MAX/_P95}`、`\ph{<METHOD>_ON25/50/100}`、`\ph{<METHOD>_OFF25/50/100}`、`\ph{<METHOD>_OFF}`；
- 若需要专门测速，只在预先固定的代表性 request subset 上重复，**不做完整第二遍**。

---

## 6. P1.5：缩减稳健性矩阵（全而不重）

10% 是完整主比较。30% 与 50% 只跑覆盖全部核心对照类型的七类：

| 类别 | 方法 | 占位符前缀 |
|---|---|---|
| no-op | Native KEEP | `\ph{RB_KEEP_30/50}` |
| fixed policy | Best Fixed | `\ph{RB_BF_30/50}` |
| simple selector | R2-CART | `\ph{RB_R2_30/50}` |
| reconstruction | T1 | `\ph{RB_T1_30/50}` |
| task-oriented | TOI | `\ph{RB_TOI_30/50}` |
| data-side adaptation | TATO | `\ph{RB_TATO_30/50}` |
| ours | IntroAct-TS | `\ph{RB_OURS_30/50}` |

同时回填 `\ph{RB_*_10}`、`\ph{RB_*_CH2}`、`\ph{RB_*_WORST}`、`\ph{ROBUST_30}`、`\ph{ROBUST_50}`、`\ph{ROBUST_WORST}`、`\ph{ROBUST_READING}`。

**Per-pattern 结果固定在 10% 主矩阵上生成**，不增加额外推理。论文只声称 within-grid robustness，**不声称 50% unseen**。

---

## 7. P2：只做低成本附录（主要为后处理）

保留并执行：

1. full per-source / per-pattern / per-severity tables；
2. replay size 25 / 50 / 100%，复用 replay 与 prediction cache → `\ph{SUPPORT25_*} / \ph{SUPPORT50_*} / \ph{SUPPORT100_*}`；
3. $k$、$\beta$ gate grid → `\ph{OPPSENS_*}`；
4. full feature-group ablation（若只需重算 selector）；
5. failure / timeout audit → `\ph{CALLS_FAIL_*} / \ph{CALLS_TIMEOUT_*} / \ph{FAILRATE}`；
6. reproducibility manifests 与 raw-record schema。

**Mask stability 改成 3-mask 代表性检查，不做 10 seed 全量重跑：**

- 主 seed + 2 个额外 deterministic mask seeds；
- 预先固定的 stratified TEST subset：全部 8 sources、P1–P4、10% severity、$H=96$、Chronos-Bolt 与 held-out Chronos-2；
- 只比较 Native KEEP、R2-CART、IntroAct-TS；
- 报告 3 个 mask realisation 的 mean / range → `\ph{SEED1..6_MASE/_DELTA/_IR}`、`\ph{SEED_SPREAD_BOLT/_CH2}`、`\ph{SEED_IR_SPREAD_BOLT/_CH2}`；
- **seed 仍不作为独立统计样本**。

若提交前还有空闲 GPU，再扩到 10 seeds，扩展结果不改变论文主 claim。

---

## 8. 明确删除项（不再为其保留占位符）

以下分支今晚不执行，也不应在结果里出现：

- P5 asynchronous availability；
- support gate 与 OOD leave-one-* stress tests；
- 新 GIFT-Eval 数据集；
- additional horizons；
- 两个 parent 的 finance case study（除非已经有无需新增运行的 verified natural-missingness 结果）；
- previous-cycle Frank–Wolfe negative-result 数值表；
- 新的 reconstruction-supervised learned selector；
- 10-seed 全量稳定性表。

---

## 9. 结果解释规则（先于数字冻结，避免看结果改口径）

1. **Action heterogeneity**：若 BEST FIXED 与 Catalog Oracle gap 很小，不能把 instance-level selection 写成强必要性，收窄为「can help on heterogeneous episodes」。gap 清楚存在才保留强动机。
2. **Reconstruction vs utility**：若 within-parent rank correlation 高且 winner agreement 很高，删除「reconstruction is unreliable」强结论，只说二者并不完全等价。
3. **A4 gate**：若去掉 gate 后 HIR / HL 明显上升而 MASE 没有同步改善，conservative act-or-keep 得到直接支持。若 gate 几乎不影响 harm，不要把它写成主要创新点。
4. **R2-CART**：IntroAct-TS 必须至少在 primary metric 或 harm/accuracy trade-off 上体现相对 simple selector 的可解释优势，否则复杂方法缺少必要性。
5. **Chronos-2**：只要冻结配置不重新调参并保持可用，就支持 configuration transfer。不要求它在每个 cell 都最好。
6. **Published baselines**：主表报告所有真实结果，不因为某个 baseline 赢某些 cell 就删除或更换。

---

## 10. LaTeX 占位符回填契约

**完整键清单**：`docs/v45_placeholder_keys.csv`（1322 行，两列 `key,family`），执行 agent 可以直接按 `family` 分组逐批回填。下表是按 family 汇总的统计与含义。

### 10.1 family 汇总

| family | 数量 | 键模式 | 来源实验 | 落到哪里 |
|---|---|---|---|---|
| `main_table_cell_per_source` | 540 | `SRC_<BACK>_<METHOD>_<H>_<SRC>` | P1-3 | 附录 B per-source 表（3 backbone × 2 horizon 各一张） |
| `main_table_macro` | 60 | `SRC_<BACK>_<METHOD>_<H>_MACRO` | P1-3 | 附录 B macro 行 |
| `per_method_appendix` | 152 | `<METHOD>_<BOLT/TF/CH2/OVR/RMSSE/RANK/CAND/CALLS/MEAN/MAX/P95/ON*/OFF*/S25_*>` | P1-3 / P1-7 | Table 1 表头列 + 附录 F 成本表 |
| `appendix_severity_table` | 139 | `SEV<10/30/50>-<METHOD>-<MASE/RMSE/MAE/MSE/RANK>` | P1.5 | 附录 C severity 表 |
| `table2_harm` | 61 | `HARM_<IR/HIR/HL/BP/MO/MASE>[_<METHOD>]`、`HARM_RISKCURVE`、`HARM_READING` | P1-4 | Table 2 + 图 3(b) |
| `appendix_ablation` | 55 | `AF_<FULL/A1..A5/ORACLE>_<MASE/RMSE/MAE/MSE/CHIR/HL/IR/CALLS>` | P1-5 | 附录 E 全量消融表 |
| `table4_ablation` | 53 | `ABL_<FULL/A1..A5/ORACLE>_<MASE/HIR/HL/IR/CALLS/LAT>`、`ABL_RANKFULL_*`、`ABL_STAB_*` | P1-5 | Table 4 |
| `table3_robustness` | 39 | `RB_<METHOD>_<10/30/50/CH2/WORST>`、`ROBUST_*` | P1.5 | Table 3 |
| `appendix_per_pattern` | 36 | `P<1..4>_<METHOD>` | P1-3 后处理 | 附录 B per-pattern 表 |
| `appendix_replay_size` | 33 | `SUPPORT<25/50/100>_<METHOD>`、`RS<25/50/100>_*` | P2 | 附录 E |
| `appendix_operating_points` | 27 | `NOOP_*`、`LOWOP_*`、`HIGHOP_*` | P1-4 后处理 | 附录 D |
| `appendix_mask_stability` | 25 | `SEED1..6_*`、`SEED_SPREAD_*`、`SEED_IR_SPREAD_*`、`SEED_MASK/ORDER/SELECTOR` | P2 | 附录 E |
| `appendix_extended_comparison` | 25 | `OVR_<METHOD>`、`PR_<METHOD>`、`OFFLINE_<METHOD>` | P1-3 / P1-7 | 附录 B / F |
| `appendix_reconstruction_oracle` | 24 | `REC_<METHOD>_<MASE/MAE/MSE/GAIN>` | P1-2 | 附录 D |
| `narrative_sentence` | 20 | `MAIN_READING`、`HARM_READING`、`ABL_READING`、`ROBUST_READING`、`RANK_DISAGREE_STATS`、`DISCORDANT_RATE`、`CONCLUSION_CLOSING`、`CONCL_*`、`ABSTRACT_CLOSING`、`COLDSTART` | 全部 | 正文自然语言段 |
| `appendix_protocol_counts` | 18 | `TEST_*`、`FIT_*`、`GATE_*`、`EVAL_*`、`N_DATASETS`、`N_BOOTSTRAP`、`FAILRATE`、`RECON_ORACLE_MASE` | P0 | 附录 A |
| `appendix_cost` | 17 | `CALLS_*`、`COST_*` | P1-7 | 附录 F |
| `supplementary_finance` | 15 | `FIN-*`、`FIN_P1`、`FIN_P2` | 见 §8 删除项 | 补遗（已有结果才填） |
| `appendix_gate_grid` | 12 | `OPPSENS_*` | P2 | 附录 E |
| `appendix_opportunity_strata` | 12 | `STRATUM_*` | P1-1 后处理 | 附录 B |
| `appendix_reproducibility` | 11 | `REV_*`、`PYVERSION`、`NUMPYVERSION`、`PANDASVERSION`、`SKLEARNVERSION`、`TORCHVERSION`、`HARDWARE`、`PRECISION`、`PROTOCOL_COMMIT` | P0 | 附录 G |
| `appendix_baseline_roster` | 5 | `VIDA_*` | P1-3 | 附录 A baseline roster |
| `appendix_rank_disagreement` | 3 | `RHO_BOLT/_TF/_CH2` | P1-2 | 附录 D |

### 10.2 回填纪律

1. **数字格式统一**：MASE / RMSSE / MAE / RMSE / MSE 保留 3 位小数；百分比保留 1 位小数；call count 用整数；延迟用毫秒整数。
2. **不要改动词汇**：占位符周围的句子已按「不用引号、破折号、分号」写死，回填只替换 `\ph{...}` 本身，不要顺手重写句子。
3. **不要新增表格行**：Table 1–4 的行集合已与 §53 冻结，增行会破坏 9 页预算。
4. **一致性检查**：`\ph{SRC_*_MACRO}` 必须等于对应 `SRC_*_<SRC>` 的 source-macro 聚合；`\ph{<METHOD>_OVR}` 必须与 `\ph{SRC_*_<METHOD>_*_MACRO}` 的聚合一致。回填脚本里加断言。
5. **Oracle 行永远是灰色 diagnostic**，不参与 rank，回填时保持 `\oracle{}` 包裹。
6. **回填后必须重编译并检查**：0 error、0 undefined reference、0 Overfull、正文 ≤ 9 页。

---

## 11. `fig1_stats.json` schema

Figure 1(a) 直接读这个文件，**文件缺失时脚本画虚线占位，绝不造数**。

```json
{
  "best_action_share": {
    "KEEP": 0.0,
    "MEAN_IMPUTE": 0.0,
    "LOCF": 0.0,
    "CHANNEL_MEDIAN": 0.0,
    "INTERP": 0.0
  },
  "best_fixed_gap": 0.0,
  "n_episodes": 0,
  "protocol_seed": 0
}
```

- `best_action_share`：每个 catalog action 成为 oracle-best 的 episode 占比，五个键加起来为 1；
- `best_fixed_gap`：best fixed catalog action 与 catalog oracle 的 source-macro MASE 差距；
- `n_episodes`：参与统计的 evaluation episode 数，应等于 `\ph{TEST_PARENTS}` × `\ph{TEST_ORIGINS}` 的口径；
- 生成后重跑 `latex/figure/build_figures.py` 重出 `fig1_selective_governance.eps/.pdf/.pptx`。

---

## 12. 结果落盘目录

```
results/v45/
  protocol/          test_manifest.json, freeze_note.md, split_boundaries.json
  pred_cache/        <source>/<backbone>/<horizon>.parquet（unique input hash → prediction）
  replay_bank/       <backbone>/<source>.npz
  baselines/         <method>/<source>/*.json
  train_eval/        TRAIN-eval 与 gate 块结果
  main_results/      main_10.json, main_per_source.json, main_per_pattern.json
  diagnostics/       harm.json, rank_disagreement.json, opportunity_strata.json, governance_curve.json
  ablations/         ablation.json, feature_groups.json, replay_size.json, gate_grid.json
  robustness/        severity.json, chronos2_transfer.json, mask_stability.json
  cost_audit/        cost.json, failures.json, latency.json
```

原始记录一律保留：`raw_record_schema.json` 说明每条记录至少含 `source, parent_id, origin_id, horizon, pattern, severity, method, backbone_revision, input_hash, action, utility, prediction_hash`。

---

## 13. 提交前自检清单

- [ ] TEST manifest 已登记，且 TEST 未参与任何设计决策；
- [ ] 主比较每个 cell 都命中 prediction cache，无重复 backbone 推理；
- [ ] Table 1 的 `MACRO` 与 `OVR` 一致性断言通过；
- [ ] Catalog Oracle 未进入任何 rank；
- [ ] harm 六项指标齐全，risk curve 未在 TEST 上重选阈值；
- [ ] A1–A5 只读同一 cache；
- [ ] Chronos-2 文字称 configuration transfer；
- [ ] 30/50% 只有七类方法，per-pattern 只在 10%；
- [ ] 3-mask 只报 mean / range，未当独立样本；
- [ ] 删除清单里的分支没有偷偷跑并写进结果；
- [ ] `fig1_stats.json` 已生成并重出图；
- [ ] 回填后重编译：0 error / 0 undefined / 0 Overfull / 正文 ≤ 9 页。
