# IntroAct-TS v4.4 — TRAIN-Eval 准入批次报告

2026-09-17。**TRAIN-only**。calibration / test 全程未读取（`heldout_labels_read = 0`）。

本批完成任务书 Step 5–8：两骨干 Counterfactual Replay bank、K/beta Gate 选择、
TRAIN-Eval 准入阶梯与五项消融。**结论：本批不构成方法晋升。**

---

## 1. 执行摘要

- Replay-Fit / Gate / TRAIN-Eval 三块全部跑完，两骨干（Bolt、TimesFM）各
  5440 条 replay 记录。
- K/beta Gate 从 9 组合法配置中选出 **K = 8, β = 1.64**（两骨干共用一组）。
- Full IntroAct 的 source-macro MASE 低于 Native KEEP 与 R2-CART 对照，且在
  Bolt 上显著（区间不含零）。
- **但方法自身的消融几乎全部优于 Full**：移除保守闸门（A4）在两个骨干上都
  **显著**更好；Bolt 上移除 intervention 特征块（A2）、把检索换成 ridge（A5）也显著更好。
- Full 在两个骨干上的平均排名分别为 6.660 / 6.870（10 个可部署方法中第 8 / 第 8）。
- 按任务书 §21，**停止方法扩展，保留负结果，确认集保持封存**。

---

## 2. 冻结协议与本次配置

| 项 | 值 |
|---|---|
| context L | 512 |
| horizon H | 96, 192 |
| pattern | P1_point, P2_target_block, P3_shared_block, P4_tail |
| severity（本批） | 0.10（main） |
| Replay-Fit severity | 每 episode 由 hash 决定，实测 359 / 350 / 379 |
| 动作池 | KEEP, FFILL, SINGLE_TSICL, MULTI_TSICL, CONTEXT_RIDGE |
| reference | KEEP |
| protocol seed | 20260917 |
| TRAIN 内部分割 | replay_fit 136 / gate 48 / train_eval 46 parents（60/20/20，purge 704） |
| episodes | replay_fit 1088 / gate 384 / train_eval 368 |
| **gate 选出** | **K = 8, β = 1.64**（joint objective 1.899294） |
| 聚合 | variant → parent → source → 八来源等权 macro（头条 = 各 horizon×pattern 单元等权平均） |
| 统计 | parent 单位配对聚类 bootstrap，10,000 次，seed 101，95% 区间 |

Gate 九组配置的联合目标（越小越好）：

| K | β | joint | Bolt | TimesFM | HL | HIR | 干预率 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 1.64 | **1.899294** | 1.918441 | 1.880146 | 0.02978 | 0.1380 | 0.3385 |
| 8 | 1.00 | 1.902431 | 1.940484 | 1.864378 | 0.03961 | 0.2292 | 0.5404 |
| 32 | 1.64 | 1.909410 | 1.913385 | 1.905435 | 0.03218 | 0.1589 | 0.3945 |
| 16 | 1.64 | 1.914539 | 1.922629 | 1.906448 | 0.03437 | 0.1432 | 0.3620 |
| 8 | 0.00 | 1.918459 | 1.980318 | 1.856600 | 0.05260 | 0.3672 | 0.7930 |
| 16 | 1.00 | 1.919766 | 1.936693 | 1.902838 | 0.04404 | 0.2461 | 0.5521 |
| 32 | 1.00 | 1.928545 | 1.967511 | 1.889579 | 0.04186 | 0.2565 | 0.6094 |
| 16 | 0.00 | 1.936732 | 2.020609 | 1.852856 | 0.05973 | 0.3620 | 0.8138 |
| 32 | 0.00 | 1.945069 | 1.987443 | 1.902695 | 0.05210 | 0.3581 | 0.8060 |

联合目标随 β 单调下降、随干预率单调上升：**越保守越好**，这本身说明增益主要来自"少动"。

---

## 3. 产物与身份

运行代码：`096c60aeb23ebbd2808e011c04b331bc4cccef4f`
（`codex/introactts-v43-bootstrap`，已推送远端）。

| 产物 | SHA-256 |
|---|---|
| `results/v44/protocol/protocol_freeze.json` | `fe1d77ffb61557a32f3ddac33b20847d60a82149e1067db5fd48d0311f5e1e29` |
| `results/v44/banks/replay_fit/replay_bank_bolt.summary.json` | `e23a1af8116dbdf8d4034583acd9ae8dc770263deae7c03e8c1632339d7a400b` |
| `results/v44/banks/replay_fit/replay_bank_timesfm.summary.json` | `ad21374c945ab5cb749b80fa50c534e41cf45714ab2d821e4143abcfbe9603b8` |
| `results/v44/gate/gate_sweep.json` | `025c72f6377a90fce969dc9162fd8b0644f33aa433788ac5db66a2e3982d75e0` |
| `results/v44/evaluation/train_eval.json` | `e99dae3f8664cc800aecd50a4473e471d42eb34757cf8f9f07915bf0d3206c4f` |
| `results/v44/evaluation/admission.json` | `0253dbe52c4e45df7fb7e56adc0c8b1112a12b9d364496bc02e858988f94b619` |

规范表：`table_train_eval.csv`（22 行）、`table_train_eval_cells.csv`（176 行）、
`table_train_eval_pairs.csv`（6 行）、`claims.md`。

复现命令：

```bash
source scripts/env_new_server.sh
bash scripts/v44_run_pipeline.sh          # 幂等：已有产物则跳过
"$W2_CORE_PY" -u scripts/v44_admission.py
"$W2_CORE_PY" -u scripts/v44_train_eval_tables.py
```

---

## 4. TRAIN-Eval 主表（368 episodes / 46 parents / 8 sources / H∈{96,192} × 4 patterns）

### Bolt

| method | macro MASE | 干预率 | HIR | Harmful Loss | CGC |
|---|---:|---:|---:|---:|---:|
| NATIVE_KEEP | 1.179735 | 0.0000 | 0.0000 | 0.00000 | 0.0000 |
| BEST_FIXED | 1.179735 | 0.0000 | 0.0000 | 0.00000 | 0.0000 |
| R2_CART | 1.178209 | 0.1196 | 0.0489 | 0.00960 | −0.5081 |
| **FULL_INTROACT** | **1.165800** | 0.1984 | 0.0842 | 0.01180 | −0.0566 |
| A1_GLOBAL_REPLAY | 1.153256 | 1.0000 | 0.4212 | 0.03859 | −1.4952 |
| A2_WO_INTERVENTION | 1.159657 | 0.2201 | 0.0815 | 0.01068 | −0.0218 |
| A3_WO_FORECAST | 1.162388 | 0.2283 | 0.0897 | 0.01259 | −0.5674 |
| A4_WO_GATE | 1.142909 | 0.7065 | 0.2745 | 0.02586 | −0.6916 |
| A5_PARAMETRIC_RIDGE | 1.140129 | 0.8016 | 0.2908 | 0.02546 | 0.0497 |
| A5_PARAMETRIC_CART | 1.153831 | 0.6495 | 0.2962 | 0.01883 | −0.2586 |
| CATALOG_ORACLE（诊断） | 1.056632 | 0.8125 | 0.0000 | 0.00000 | 1.0000 |

Bolt 上 **BEST_FIXED = KEEP**，即 Gate 块上没有任何固定动作的平均效用高于 KEEP。

### TimesFM

| method | macro MASE | 干预率 | HIR | Harmful Loss | CGC |
|---|---:|---:|---:|---:|---:|
| NATIVE_KEEP | 1.242208 | 0.0000 | 0.0000 | 0.00000 | 0.0000 |
| BEST_FIXED | 1.103034 | 0.7500 | 0.2826 | 0.04126 | −10.3060 |
| R2_CART | 1.146845 | 0.2717 | 0.0788 | 0.00921 | 0.0468 |
| **FULL_INTROACT** | **1.101261** | 0.4538 | 0.1875 | 0.02882 | −0.1314 |
| A1_GLOBAL_REPLAY | 1.101755 | 1.0000 | 0.3940 | 0.04860 | −10.3175 |
| A2_WO_INTERVENTION | 1.100069 | 0.4511 | 0.1739 | 0.02697 | 0.0590 |
| A3_WO_FORECAST | 1.095083 | 0.4511 | 0.1658 | 0.02661 | −0.2403 |
| A4_WO_GATE | 1.085381 | 0.8750 | 0.3397 | 0.03418 | −3.9394 |
| A5_PARAMETRIC_RIDGE | 1.088242 | 0.8071 | 0.2908 | 0.03082 | −1.0059 |
| A5_PARAMETRIC_CART | 1.080967 | 0.9103 | 0.3342 | 0.03423 | −0.5591 |
| CATALOG_ORACLE（诊断） | 1.016391 | 0.8315 | 0.0000 | 0.00000 | 1.0000 |

CGC 分母：368 个窗口中 299 个可用，69 个因可达 gap ≤ ε=1e-9 被排除（已计数，未静默删除）。
**近 1/5 的请求里没有任何合法动作能超过 KEEP**，这是目录本身的结构性事实。

---

## 5. 配对聚类 bootstrap（Full − X，负值 = Full 更好）

### Bolt

| 对照 | 差值 | 95% CI | 区间不含零 | 判定 |
|---|---:|:---:|:---:|---|
| NATIVE_KEEP | −0.013935 | [−0.025312, −0.003841] | 是 | Full 显著更好 |
| BEST_FIXED | −0.013935 | [−0.025312, −0.003841] | 是 | Full 显著更好（对照即 KEEP） |
| R2_CART | −0.012409 | [−0.023248, −0.002524] | 是 | Full 显著更好 |
| A1_GLOBAL_REPLAY | +0.012544 | [−0.009752, +0.034636] | 否 | 不可区分 |
| A2_WO_INTERVENTION | **+0.006143** | [+0.001355, +0.012622] | 是 | **消融显著更好** |
| A3_WO_FORECAST | +0.003412 | [−0.008325, +0.014227] | 否 | 不可区分 |
| A4_WO_GATE | **+0.022891** | [+0.010849, +0.036081] | 是 | **消融显著更好** |
| A5_PARAMETRIC_RIDGE | **+0.025671** | [+0.010871, +0.040826] | 是 | **消融显著更好** |
| A5_PARAMETRIC_CART | +0.011969 | [−0.003564, +0.028910] | 否 | 不可区分 |

### TimesFM

| 对照 | 差值 | 95% CI | 区间不含零 | 判定 |
|---|---:|:---:|:---:|---|
| NATIVE_KEEP | −0.140948 | [−0.207415, −0.083152] | 是 | Full 显著更好 |
| BEST_FIXED | −0.001773 | [−0.016374, +0.012968] | **否** | **不可区分** |
| R2_CART | −0.045584 | [−0.088717, −0.004198] | 是 | Full 显著更好 |
| A1_GLOBAL_REPLAY | −0.000494 | [−0.013430, +0.012757] | 否 | 不可区分 |
| A2_WO_INTERVENTION | +0.001192 | [−0.004054, +0.007884] | 否 | 不可区分 |
| A3_WO_FORECAST | +0.006178 | [−0.001312, +0.013735] | 否 | 不可区分 |
| A4_WO_GATE | **+0.015880** | [+0.003289, +0.028557] | 是 | **消融显著更好** |
| A5_PARAMETRIC_RIDGE | +0.013019 | [−0.001008, +0.027022] | 否 | 不可区分 |
| A5_PARAMETRIC_CART | **+0.020294** | [+0.008517, +0.032690] | 是 | **消融显著更好** |

无任何对照因 parents 不配对而被丢弃（`unpaired_dropped = 0`）。

---

## 6. 排名与单元格胜负

平均排名（在每个 `(source, parent, horizon, pattern, severity)` 单元内排名后取均值，越小越好）：

| 方法 | Bolt | TimesFM |
|---|---:|---:|
| A2_WO_INTERVENTION | **3.049** | **3.804** |
| A1_GLOBAL_REPLAY | 4.715 | 4.030 |
| A3_WO_FORECAST | 4.014 | 4.614 |
| A4_WO_GATE | 4.611 | 4.807 |
| A5_PARAMETRIC_CART | 5.329 | 4.986 |
| A5_PARAMETRIC_RIDGE | 5.168 | 5.405 |
| BEST_FIXED | 5.731 | 5.905 |
| **FULL_INTROACT** | **6.660** | **6.870** |
| NATIVE_KEEP | 7.533 | 7.024 |
| R2_CART | 8.190 | 7.554 |

Full 对 Native KEEP 的 64 个 `source × horizon × pattern` 单元格：
Bolt 8 胜 / 53 平 / 3 负；TimesFM 22 胜 / 33 平 / 9 负。
**收益高度集中**：大多数窗口 Full 与 KEEP 完全相同（弃权），少数窗口贡献了全部增益。

---

## 7. 准入判定

### 7.1 G1：Full 不弱于 Best Fixed

- Bolt：Full 1.165800 < BEST_FIXED 1.179735，配对区间不含零 → **通过**。
- TimesFM：Full 1.101261 < BEST_FIXED 1.103034，但差值 −0.001773、
  区间 [−0.016374, +0.012968] **跨零** → 点估计通过，**统计上未确立**。

### 7.2 模块贡献：**失败**

任务书要求三个模块各自有贡献，即移除任一模块后方法应当变差。实测：

- **A4_WO_GATE（移除 Module 3 保守闸门）在两个骨干上都显著优于 Full**
  （Bolt +0.022891、TimesFM +0.015880，区间均不含零）。
  闸门确实把 HIR 从 0.2745 / 0.3397 降到 0.0842 / 0.1875，但它同时把平均 MASE 拉高。
  **这是治理与精度的权衡，不是精度增益。**
- **A2_WO_INTERVENTION 在 Bolt 上显著优于 Full**（+0.006143）：intervention 特征块
  在 mask + context 之外没有提供可用信息。
- **A5_PARAMETRIC_RIDGE 在 Bolt 上显著优于 Full**（+0.025671）、
  A5_PARAMETRIC_CART 在 TimesFM 上显著优于 Full（+0.020294）：
  用轻量参数化预测器替换 KNN 检索更好，Module 2 的检索形式未被支持。
- A1_GLOBAL_REPLAY 在两个骨干上都**不显著**——即"局部匹配"相对"全局回放"
  没有可测的贡献。

### 7.3 结论

按任务书 §21：**准入不通过。停止方法扩展；保留 v4.4 负结果；不得打开 test。**

需要说明的口径限制：本机只保存了 G1 的判据原文，G2–G6 的完整条文存在于对话中、
未落盘。上述判定不依赖 G2–G6 的具体阈值——因为"每个模块必须有贡献"这一条在
两个骨干上都不成立，任何要求模块贡献的读法都会得出同一结论。

---

## 8. 本批**不**支持的陈述

- 不说 v4.4 优于其自身消融；事实相反。
- 不说三个模块均有贡献。
- 不说超过 Best Fixed 已被证实（TimesFM 上区间跨零）。
- 不引用任何 calibration / test 数字。
- 不声称 SOTA、显著优于文献方法或通过独立确认。
- Catalog Oracle 只是事后诊断，不入排名、不入 claim。

## 9. 本批**可以**支持的陈述

- 冻结 TSFM 的治理动作选择可以在 TRAIN 内部、不读确认集的前提下被完整评测。
- 在冻结的 512 上下文与 10% 缺失条件下，**保守弃权能显著降低有害干预比例**，
  但**以平均精度为代价**；在 Bolt 上该代价（+0.0229 MASE）超过了它对对照的增益（−0.0139）。
- 五动作目录在约 19% 的窗口上是退化的：没有任何合法动作能超过 KEEP。
- 与 Native KEEP 相比，Full IntroAct 的改进在 Bolt 上显著、在 TimesFM 上更大
  （−0.1409），但两者都由少数单元格驱动。

---

## 10. 后续（待确认后执行）

1. 是否按 §21 停止方法扩展并转入负结果交付（推荐）。
2. G2–G6 原文是否需要补入仓库；若用户提供，将逐条补判并更新本报告。
3. Step 10 的五个正式 published baseline 中，仓库内只有 **TATO** 有官方实现；
   BRITS / CSDI / TOI 无实现，T1(TimeInf) 只有上游源码无适配器。
   在准入未通过的前提下，按 §21 不应启动该批。
