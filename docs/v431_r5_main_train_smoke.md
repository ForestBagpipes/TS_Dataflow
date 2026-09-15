# r5 主矩阵 TRAIN 原生 KEEP 接口准备

2026-09-16 04:30（Asia/Shanghai）。本任务是主矩阵输入和模型接口验收，不是 r5 晋升、预测效果实验或独立确认。

## 已冻结的输入

`scripts/v431_r5_main_train_smoke.py --prepare` 已完成。依据 `configs/v431-r5/main_protocol_v2.json` 及 `results/v431-r5/main-preparation/audit-v2/timestamp_audit.json`，对八个已登记来源分别选取最早合法 TRAIN parent，排除时间审计明确受影响的窗口。每个 parent 使用 L512，H96/H192，各有原始输入及已登记的 target_block_10（位置 `[230:281]`，51 点）两种条件：每家族 32 次，两个家族至多 64 次预测。

仅解析所选 TRAIN 的 512 点上下文；未解析预测区间数值，没有读取 DEV/calibration/test 标签，没有计算损失。文件全字节 SHA 仅用于身份核验。目标保持 channel 0（ETT 为 HUFL，不冒称官方 OT）。原始 target 是否完整及其缺失数逐行记录；原始输入不能自动称为完整有效数据。

Electricity、Exchange、Traffic 缺少原始时钟，本次只作原始行序下的接口检查，不宣称其历史时间可用性已经核实。Weather 已知时间异常区间排除，最早所选窗口不受影响。旧 TRAIN 暴露状态继承记录，不称新确认集。

配置：`configs/v431-r5/main_train_smoke.json`；输入与准备记录：`results/v431-r5/main-train-smoke/`。脚本、原生后端、协议、时间审计、原文件、输入和 mask 均有 SHA；运行前重新核验关键 hash。

## 原生缺失与费用

直接调用已验收 `scripts/v431_baselines/worker.py` 的 `Bolt` / `TimesFM` 原生后端，不经过 TATO 的 NaN bridge 或治理流水线。Bolt 接受原始 NaN；TimesFM 使用官方实现中仅基于当前 context 的插值及前导 NaN 去除。脚本不修改输入，不填零；全缺失显式 unsupported。每个请求清空后端缓存，按家族常驻单模型。预测直接落盘，不读取 future，也不计算 MASE。

每次保留原生调用、原始预测、dtype、hash、失败和实际热请求时间；冷加载、完整进程时间单列。冷加载在 CUDA 同步后截时；热请求在预先 CUDA 同步后开始，包含输入读取/hash/拷贝、缓存清空、模型执行、输入不变校验、预测写盘、返回元数据及末端同步；账本批次写入另由完整进程费用包含。这些是本次实测，不由旧批量时间推断预算保证。

运行前修订上述计时位置，原配置及准备记录保留为 `*.pre_timing_amendment.json`。第二次运行前边界审计发现原准备器在 `break` 前曾获取 origin 行字符串，但未数值解析、保存、评分或用于选择。此事实保留，不能说此前物理行读取完全不触及该行。修复为 `islice(..., origin)`，重新只读取上下文，8 来源的 32 份冻结输入（包括 NaN）逐值相同。第二次修订前文件另保留为 `*.pre_boundary_amendment.json`。最终 worker SHA 为 `414ccdf7a7984c35d01717b10b0e76704f21b1dab9f276da23ade0d8af44106d`，配置 SHA 为 `83d72dd5e366f15e280dda421804ac3d684c734c1a16c881d0830c298aef058c`；没有修改输入、模型或试验条件。

## 调度命令

服务器执行，root 统一队列；本子任务没有自行启动 GPU。脚本自身持有 `locks/gpu.lock`，外层不能重复持同一把锁。

```bash
source scripts/env_new_server.sh
"$W2_CHRONOS_PY" scripts/v431_r5_main_train_smoke.py --family bolt --deadline 2026-09-16T04:45:00+08:00 > logs/v431-r5/main-train-smoke-bolt.log 2>&1
"$W2_CHRONOS_PY" scripts/v431_r5_main_train_smoke.py --family timesfm --deadline 2026-09-16T04:45:00+08:00 > logs/v431-r5/main-train-smoke-timesfm.log 2>&1
```

预期为同一健康环境、一次一个模型、batch 1 的小规模任务；实际耗时尚未测量。截止时间在模型加载前及每次请求前检查，不启动过时请求。失败、未运行和超时保留；没有未来标签，因此本轮不会生成方法效果结论。

CPU 准备结果：8 来源、每家族 32 请求、forecast/heldout 标签读取 0。脚本已通过 `py_compile`。实际 GPU 状态以两个家族的 `status.json` 为准。
