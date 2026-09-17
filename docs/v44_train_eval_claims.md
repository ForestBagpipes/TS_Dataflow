# v4.4 TRAIN-Eval 准入批次 — 可支持与不可支持的陈述

数据来源：`results/v44/evaluation/train_eval.json`（frozen K=8, beta=1.64）与 `admission.json`。协议 `PROTOCOL_SEED=20260917`，统计为 parent 单位配对聚类 bootstrap，10000 次重采样，seed 101。
**calibration / test 全程未读取**（`heldout_labels_read=0`）。

## 可以陈述

- `bolt`：Full IntroAct 的 source-macro MASE 为 `1.165800`，低于 Native KEEP 与 R2-CART。
  - 点估计低于的对照：beats_NATIVE_KEEP, beats_BEST_FIXED, beats_R2_CART。
- `timesfm`：Full IntroAct 的 source-macro MASE 为 `1.101261`，低于 Native KEEP 与 R2-CART。
  - 点估计低于的对照：beats_NATIVE_KEEP, beats_BEST_FIXED, beats_R2_CART。
- 保守闸门确实降低了有害干预比例（见 `table_train_eval.csv` 的 `hir` 列）。

## 不可以陈述

- 不可以说 v4.4 方法优于其自身消融：
  - `bolt`：移除下列模块后指标**不变差或更好**：A1_GLOBAL_REPLAY, A2_WO_INTERVENTION, A3_WO_FORECAST, A4_WO_GATE, A5_PARAMETRIC_CART, A5_PARAMETRIC_RIDGE。
  - `timesfm`：移除下列模块后指标**不变差或更好**：A2_WO_INTERVENTION, A3_WO_FORECAST, A4_WO_GATE, A5_PARAMETRIC_CART, A5_PARAMETRIC_RIDGE。
- 不可以说三个模块均有贡献；`A4_WO_GATE` 在两个骨干上都显著优于 Full，即保守闸门以平均精度为代价换取更低的 HIR，这是治理权衡，不是精度增益。
- 不可以说超过 Best Fixed 已被证实：TimesFM 上 Full 与 Best Fixed 的配对区间跨零。
- 不可以引用任何 calibration / test 数字；本批次未打开。
- 不可以声称 SOTA、显著优于文献方法或已通过独立确认。
- Catalog Oracle 是事后诊断，不入排名、不入 claim。

## 结论

本批次**不构成方法晋升**。按任务书 §21，方法扩展停止，保留 v4.4 负结果，确认集保持封存。
