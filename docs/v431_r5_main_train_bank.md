# r5 主矩阵 TRAIN 原生 KEEP 预测银行

2026-09-16 04:37:33（Asia/Shanghai）准备完成，未由准备 agent 启动 GPU。此任务收集后续基线接口资产，不拟合 r5、不计算未来误差、不作为方法晋升或独立确认。

## 冻结支持

| 来源 | 合法 TRAIN parent |
|---|---:|
| ETTh1 | 14 |
| ETTh2 | 14 |
| ETTm1 | 59 |
| ETTm2 | 59 |
| Electricity | 22 |
| Exchange | 6 |
| Traffic | 14 |
| Weather | 42 |
| 合计 | 230 |

继承主协议 v2，排除时间审计命中的两个 Weather parent。每个 parent 为 L512、H96/H192，各含 raw 和 target_block_10，共 920 请求/家族，两个原骨干共至多 1840 请求。并未增加 r5 有效训练支持，未读 DEV/calibration/test 标签。

每来源单次流式遍历，仅把选中 TRAIN 上下文转换成数值；上下文不重叠，`islice` 截止最大 origin，目标区间不用于输入。所有有效观测保留，受控缺口统一 `[230:281]`。原始缺失保持 NaN。Electricity、Exchange、Traffic 没有原始时钟，仍只能认定为行序接口资产，不能宣称严格历史可用性已核实。

## 实现与身份

新入口 `scripts/v431_r5_main_train_bank.py`，配置 `configs/v431-r5/main_train_bank.json`，结果 `results/v431-r5/main-train-bank/`。新 runner 显式映射旧 smoke 模块的 `OUT`、`CONFIG`，复用已验收 `run`；没有修改 smoke、r5、TATO 或原生后端源码。

- runner SHA：`cfa5a278779102ddebea77b75ee6233a6b7c105eea77e40f2ef991df1ebd79b7`
- smoke worker SHA：`414ccdf7a7984c35d01717b10b0e76704f21b1dab9f276da23ade0d8af44106d`
- config SHA：`a6afc91f20b179ab7ba1ab00f34c407522dcd2ec6e7b079855a33d25a75a1ba4`

运行前核对 runner、worker、后端及输入 SHA。每个请求独立清除模型预测缓存；按家族常驻加载，原生 NaN 语义、同步计时、原始预测和失败记录沿用 smoke。没有输出 MAE、MASE 或方法收益。

## 执行和截止

```bash
source scripts/env_new_server.sh
"$W2_CHRONOS_PY" scripts/v431_r5_main_train_bank.py --family bolt --deadline 2026-09-16T04:44:00+08:00 > logs/v431-r5/main-train-bank-bolt.log 2>&1
"$W2_CHRONOS_PY" scripts/v431_r5_main_train_bank.py --family timesfm --deadline 2026-09-16T04:44:00+08:00 > logs/v431-r5/main-train-bank-timesfm.log 2>&1
```

脚本持 `locks/gpu.lock`，root 统一顺序调度，父层不重复持同锁。04:44 后不开始新请求，未运行请求仍计入完整分母。基于真实 32 请求 smoke，Bolt 热均值约 0.098 秒，TimesFM 约 0.126 秒；含日志增长的准备估计为 Bolt 90–130 秒、TimesFM 120–160 秒，另加加载，不构成预算保证。实际完成范围和费用只认各家族 `status.json`、`records.json`、`calls.json`。

准备检查：8 来源、230 parent、920 请求/家族，context 形状与合法 TRAIN 边界断言通过；`py_compile` 通过。GPU 结果尚待 root 队列执行。
