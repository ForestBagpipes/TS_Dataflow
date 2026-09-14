# v4.3.1-r2 真实在线回放与独立审计

审计时间：2026-09-15 00:48，Asia/Shanghai。两家族均在当前服务器完成真实模型在线回放，随后由独立 CPU 程序事后复核通过。此验收证明已执行路径与冻结策略、模型输出和成本记录一致；不构成方法晋升或主动获取有效性的证据。

## 实际覆盖与成本

自然样例固定为原协议各来源前最多 3 个 dev parent 的 H96、target-block，共 7 个，两家族使用相同 UID；未按新结果筛选。自然策略预算均为每请求 3.5 秒。受控样例用于验证路径，单独统计。

| 实际项 | Chronos-Bolt | TimesFM |
|---|---:|---:|
| 自然样例 | 7 | 7 |
| 受控样例 | 5 | 3 |
| 自然实际工具调用 | 0，全部 STOP | 6 次 mask，另 1 例 STOP |
| 受控实际工具调用 | 4 | 1 |
| 原始模型响应记录数，含 TS-ICL | 46 | 55 |
| 自然请求热墙钟合计，秒 | 1.961043 | 4.028969 |
| 全部请求热墙钟合计，秒 | 3.888174 | 4.841732 |
| 服务启动墙钟，秒 | 8.602828 | 8.904448 |
| 其余进程开销，秒 | 2.041725 | 1.893599 |
| 完整验证子进程墙钟，秒 | 14.532727 | 15.639779 |
| 自然请求热预算超支 | 0 | 0 |
| 受控请求热预算超支 | 1，B=0 | 1，B=0 |
| 冻结策略逐例重放 | 12/12 通过 | 10/10 通过 |

完整进程时间包含自然与受控工作负载，以及进程启动和退出；上述成本不可写成仅运行自然样例的独立冷启动延迟。服务启动不从成本中抹除，热请求也不是纯 GPU 内核时间。原始账单及完整核对结果分别保存在 [Bolt 进程账单](../results/v431-r2/online-bolt/process_accounting.json)、[TimesFM 进程账单](../results/v431-r2/online-timesfm/process_accounting.json)、[Bolt 独立验证](../results/v431-r2/online-bolt/independent_verification.json)和 [TimesFM 独立验证](../results/v431-r2/online-timesfm/independent_verification.json)。

## 通过的契约

- 两家族自然 7 例的动作、已取得证据和最终预测均与离线冻结 `R2_AGENT_high` 对应记录一致。独立评估器在最终预测保存后才读取已有 dev 目标，以共同有限值评分 mask 重算误差；calibration/test 读取为 0。
- 在线进程对 18 个旧及 r2 标签、证据、候选和预测缓存路径执行开档拒绝预检，均被拒绝；意外访问计数为 0。所有最终预测与候选档案的修改时间均早于屏障解封，最终预测文件哈希与屏障记录一致。每家族的具体路径及解封时间见 `protocol.json` 与 `label_access_barrier.json`。
- 冻结 `models.joblib`、终态 manifest、完整状态策略哈希与在线生产代码哈希一致。每个模型请求的输入、mask、辅助通道、可用时间和原始时间索引哈希均核对；治理候选的已观测位置保持不变。
- 已得工具证据由当前真实执行产生，未得证据不进入策略。Bolt 受控 `both` 分支实际完成 mask 与 history 两项工具；history 仅用目标跨度原点之前的输入重新治理，不截取当前治理输出。
- 原始 worker 点预测与分位数逐项核对。Bolt 使用其原始中位数输出；TimesFM 使用其原生 point，不能以分位数中位数替换。TimesFM 内部旧逻辑槽位 `bolt` 经 `backbone_routing.json` 显式映射为实际 `model_key=timesfm`，模型身份与服务环境均通过复核。
- TimesFM 共 10 次最终预测服务请求，对应 9 个独立原生预测文件和 1 次同输入缓存命中；缓存命中保留实际请求成本，不计作新的 GPU 推断。55 条原始模型响应包含 TS-ICL 请求，不能解释为 55 次 TimesFM 推断。
- 完整观测受控样例直接 KEEP。失败注入发生在真实 mask 工具完成后、history 开始前；两家族均保留已经发生的工具支出，再实际生成固定参照候选及最终预测，未使用失败填零。
- B=0 拒绝取证，但最终预测仍然产生正成本并明确记录超支。这是完整预算不可行分支的回归证据，不能声称已满足零预算或硬实时保证。受控强制工具只检查接线；其预算规则单列，未用于自然策略成绩。

## 冻结身份与复核入口

模型文件 SHA256：`e5640384086b357e779e043b38fece89ba87e286d93fa3c1ed98649642e815f4`。

Bolt 完整状态策略 SHA256：`4dea4092c127f6b76c397e7bf4dfa9a2834573ad69fd040c8c2822bda7869c19`。

TimesFM 完整状态策略 SHA256：`ee571fc72ef310b129420d6cb09c807c51acac6ef63b4e76996c9094396bcb38`。

在线生产脚本 SHA256：`2551d8e61fee91f993b9b7c9cb04dde5e40b62e72b4a03890e1fd5e20d42c77b`。独立复核脚本 SHA256：`46faf4fb7dff19b773507dc0ea2981b6c0b6c1d40008c068a5ca8947875419a4`。

实现入口为 [在线回放](../scripts/v431_r2_online.py)和[独立复核](../scripts/v431_r2_verify_online.py)。实际 CPU 复核命令如下，日志位于 `logs/v431-r2/verify-online-{bolt,timesfm}.log`：

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" scripts/v431_r2_verify_online.py results/v431-r2/online-bolt
"$W2_CORE_PY" scripts/v431_r2_verify_online.py results/v431-r2/online-timesfm
```

## 结论边界

TimesFM 的 6 次自然 mask 调用补齐了完整 agent 实际取证路径的运行证据。当前共同开发表中，TimesFM `R2_AGENT_high` MASE 为 1.069398，与固定 mask CART 相同；旧同证据 CART 为 1.069086。因此主动选择验证工具的额外收益仍未成立。Bolt 自然策略全部 STOP，MASE 1.157005，等同其 train 冻结固定参照。7 例在线审计只验证机制一致性，不替代 26 个独立 dev parent、156 个变体的共同方法比较，更不能把变体数当独立样本量。

本轮不据此晋升方法，不打开 calibration/test；保留 `PICS_joint_relabel` 历史 incumbent。后续论证应同时保留自然取证已运行、固定流程等效和零预算不可行这三项事实。
