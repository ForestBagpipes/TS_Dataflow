# IntroAct-TS v4.4 — 协议冻结与执行流水线

状态：**开发中（TRAIN-only）**。r5 全部历史保留、未覆盖；calibration/test 未解封。

本文件记录 v4.4 的冻结协议、隔离实现位置与分阶段执行方式。所有常量定义在
`src/introact_ts/v44/protocol.py`，是唯一事实来源。

## 1. 与 r5 的关系

v4.3.1-r5 方法准入失败（Bolt r5 退化为免费参考、TimesFM 主动策略弱于冻结强简单策略、
gain-vector SSE 下降未转化为 final MASE 改善）。v4.4 **不继续搜索 r5 的凸投影 / acquisition
参数**，改为三个模块：

1. **Counterfactual Replay** — 历史 TRAIN episode 上对五个合法动作做反事实执行，存
   `(state, action, utility)`。
2. **Task-State Matching** — 22 维任务状态（mask 6 + visible context 6 + intervention 5 +
   reference forecast 5），同动作内 K 近邻检索。
3. **Conservative Intervention** — 加权效用减去局部不确定性下界，全部非正则弃权回 KEEP。

r5 的源码、报告、预测缓存、费用账本、失败日志、协议 ID、PICS_joint_relabel 与旧 DEV 结果
全部保留，v4.4 只新增文件，不修改 `v43/`、`v431/`、`v431_r2/`、`v431_r3/`、`v431_r4/`、
`v431_r5/` 任何内容。

## 2. 冻结协议

| 项 | 值 |
|---|---|
| context L | 512 |
| horizon H | 96, 192（主）；其他 horizon 只能进附录 |
| pattern | P1_point, P2_target_block, P3_shared_block, P4_tail |
| severity | 10%（main）、30%/50%（robustness）；Replay-Fit 按 hash 混合 |
| 动作池 | KEEP, FFILL, SINGLE_TSICL, MULTI_TSICL, CONTEXT_RIDGE |
| reference | KEEP |
| 可搜索超参 | K ∈ {8,16,32} × beta ∈ {0,1,1.64}，共 9 组，两骨干共用一组 |
| protocol seed | 20260917（字面量，不用时间戳） |
| TRAIN 内部分割 | Replay-Fit 60% / Gate 20% / TRAIN-Eval 20%，purge = L + max(H) = 704 |
| 聚合 | variant → parent → source → 八来源等权 macro |
| 统计 | parent 为单位的 paired cluster bootstrap，10,000 次，seed 101 |

季节周期（MASE / RMSSE 分母）：ETTh1/2 = 24，ETTm1/2 = 96，Electricity = 24，
Exchange = 5，Traffic = 24，Weather = 144。

MASE 分母 = 原始（未加 mask）context 上的 `mean|Δ_period|`；RMSSE 分母 = 同位置的
`mean(Δ²)`。分母在同一窗口的所有 pattern 间完全相同，且其 identity 写入每条 replay 记录。

## 3. 数据集与 parent

八来源沿用 `configs/v431-r5/main_protocol_v2.json` 的 60/15/10/15 切分与
`windows_metadata`。TRAIN parent 共 232 个，其中 `Weather:19008:19712` 与
`Weather:21120:21824` 被 r5 时间戳审计判为 unsupported，继续排除 → 合法 TRAIN parent 230 个。

实测分块（`results/v44/protocol/protocol_freeze.json`）：

| block | parents | episodes |
|---|---:|---:|
| replay_fit | 136 | 1088 |
| gate | 48 | 384 |
| train_eval | 46 | 368 |

Replay-Fit 的 severity 由 hash 决定（每个 episode 一个），实测分布 359/350/379，接近均衡。

## 4. 隔离实现

```
src/introact_ts/v44/
  protocol.py    冻结常量、mask seed、季节周期
  masking.py     P1–P4 确定性 mask 生成器 + mixed severity
  actions.py     五个治理动作（KEEP/FFILL/两档 TS-ICL/Context Ridge）
  state.py       22 维任务状态特征
  replay.py      ReplayRecord + cache identity + ReplayBank
  matching.py    StandardizedEuclidean + KNN + conservative gate
  metrics.py     MASE/MSE/MAE/RMSSE + HIR/HL/CGC + 分层聚合
  splits.py      Replay-Fit/Gate/TRAIN-Eval 划分与 purge 审计
  statistics.py  paired cluster bootstrap + Holm + average rank + cell win
  registry.py    八来源注册表与流式行读取
  pipeline.py    共享的 masked panel 迭代器（A/B/C 阶段共用）
  catalog.py     评估用 episode catalog
  methods.py     Full + A1–A5 消融 + Native KEEP / Best Fixed / R2-CART / Oracle
```

`hashing.py` 直接复用 `introact_ts.v43.schemas` 的 `array_hash`/`json_hash`，保证与项目
既有缓存 identity 逐字节一致。

## 5. 分阶段执行

| 阶段 | 脚本 | 环境 | 说明 |
|---|---|---|---|
| A | `scripts/v44_replay_prepare.py` | w2-core | CPU 动作候选输入 + future + 分母 |
| B | `scripts/v44_replay_tsicl.py` | w2-tsicl | 冻结 TS-ICL 的两档插补 |
| C | `scripts/v44_replay_forecast.py` | w2-chronos | 冻结 TSFM 对全部去重候选输入做预测 |
| D | `scripts/v44_replay_bank.py` | w2-core | 打分 + 状态特征 + 写 replay bank |
| gate | `scripts/v44_selector.py --mode gate` | w2-core | 9 组 K×beta，两骨干联合选择 |
| eval | `scripts/v44_selector.py --mode eval` | w2-core | TRAIN-Eval 准入 + 5 项消融 |

一键驱动：`bash scripts/v44_run_pipeline.sh`（幂等：已有产物则跳过）。

GPU 阶段遵守 `locks/gpu.lock` + `nvidia-smi` 互斥；不终止他人进程。

## 6. 泄漏边界

- mask 只由 `(source, parent, origin, horizon, pattern, protocol_seed)` 的 hash 决定，
  不读任何数值。
- 部署侧 `state.state_vector` 的形参集合被单元测试钉死为
  `{masked_panel, reference_target, period, candidate_target, reference_prediction}`；
  `reference_forecast_features` 只接受一个 prediction。
- 候选动作的 intervention 特征只用**输入**，不使用候选预测。
- replay bank 读 TRAIN future（这是方法所需的训练记忆）；部署选择器不读。
- calibration / test 全程未打开。

## 7. 单元测试

`tests/v44/test_v44_contracts.py`，25 项，覆盖任务书 §18 的 15 条契约：
mask hash 确定性、split 不重叠与 purge、future 未进入状态特征、reference forecast 特征
只来自 reference、intervention 特征不读候选未来、重复 input hash 一致、replay 查询不跨块、
K>NN 回退、n_eff 合法、零方差效用不产生 NaN、全负分弃权、unsupported 不参与 argmax、
failure 回退、最终预测与执行版本一致、完整输入回 KEEP，另加 mask 形状/severity、
动作不改写观测值、指标同分母、聚合不把变体当独立样本、cache identity 绑定、bank 往返、
记录 schema 完整性。

服务器运行：`source scripts/env_new_server.sh && $W2_CORE_PY -m pytest tests/v44 -q`

## 8. 正式 baseline 可用性（Step 10 前置盘点）

任务书 §15 要求的五个 published baseline 在本仓库的实际可用状态：

| baseline | 仓库内实现 | 证据 |
|---|---|---|
| TATO | **有**（`third_party/TATO` 官方实现 + `scripts/v431_r5_tato_scene.py`、`v431_r5_tato_official96_scene.py`、`v431_r5_tato_cached_scene.py`） | r5 已完成 5 场景 × 500 trials、官方 96 单位四场景，见 `docs/v431_r5_tato_scene_results.md`、`docs/v431_r5_tato_official96.md` |
| BRITS | **无** | 全仓库无实现、无运行记录 |
| CSDI | **无** | `docs/novelty_matrix.md`、`docs/v431_r3_related_work.md` 明确记录"CSDI 未运行""本项目未运行官方 CSDI" |
| TOI（Task-oriented Imputation） | **无** | 仅出现在文献对照，无代码 |
| T1（TimeInf） | **部分**：`third_party/TimeInf` 有源码，但项目内无 TSFM 适配器、无运行记录 | `third_party/TimeInf/PROVENANCE.md` |

结论：Step 10 不能按"五个 baseline 都有现成实现"推进。必须逐项给出"已运行 / 需实现 / 记录为
unsupported"的显式状态，不得用近似方法冒名，也不得静默替换。此表在 Step 10 实际执行前保持更新。
