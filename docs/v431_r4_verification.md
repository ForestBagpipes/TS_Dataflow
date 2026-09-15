# v4.3.1-r4 冻结策略与运行契约独立核验

本核验针对实际冻结模型、真实 TRAIN 账本和已经生成的六套离线逐窗结果，不把测试通过或产生取证动作当作方法有效。服务器 CPU 执行；没有重新推断模型或读取 calibration/test。真实 GPU 自然在线验收由独立在线记录补充，本页的 typed replay 不能替代该验收。

## 冻结与训练隔离

已核验 `fit/models_frozen.json` 对模型及 manifest 的 SHA，manifest 中的实际源文件和 hot/cold sidecar SHA 全部一致。检查对象为两家族各 14 个冻结策略，共 28 个。

- 每家族 fit 54 个独立 parent、324 个相关变体；gate 21 个 parent，与 fit 不交叉。工具有效 fit 为 51 个 parent，不用登记总数冒充有效支持。
- 所有免费特征阈值均精确等于 fit 中 25%、50%、75% 分位去重值；所有工具证据阈值仅来自 fit 内该工具的有效记录。没有用 gate、DEV 重新计算阈值。
- 费用模型 parent 身份与 fit 完全一致。按 H 分桶使用 TRAIN 最大费用 ×1.1，缺桶用 TRAIN 粗粒度值；取证仅预留实际可达终态动作，未执行的昂贵动作不能排除廉价路径。
- source 等权经数值验证，parent 的变体不增加 parent 数。可执行学习终叶均至少 16 个 fit parent。
- 旧 acq 只用于冻结后回归；它不是本轮独立确认集，也没有被用于再次训练获取器。

## 实际策略结构

| 家族与预算 | 冻结结构 | DEV 取证/STOP | 含义 |
|---|---|---|---|
| Bolt low | 提交固定动作的名义节点，实际走预算回退 | H 0 / STOP 156 | 没有学到可用取证规则 |
| Bolt high | H → 历史协变量覆盖二分 → A2 或 context ridge | H 50 / STOP 106 | 没有学得可选免费分支；调用差异由支持和预算约束产生 |
| TimesFM low | 当前协变量缺失比例二分 → ridge 或 A2 | H 0 / STOP 156 | 仅免费特征策略 |
| TimesFM high | H → 历史协变量覆盖二分 → A2 或 context ridge | H 100 / STOP 56 | 没有学得可选免费分支；不能将自然调用解释为主动获取增量 |

high 两家族证据阈值均为 `long:covariate_coverage <= 0.7548076923076923`。左叶 A2、右叶 context ridge，各自覆盖 51 个有效 fit parent。同 parent 的相关变体可进入不同叶，但在每叶只计一次 parent。

Bolt low 的不可执行名义终态记录 `fit_parents=0`，并未获得有效学习支持；其部署记录从不以 `policy_STOP` 执行该叶，而是进入冻结预算回退。核验按实际可执行路径检查支持，明确保留该限制，不将它描述成 16-parent 学得规则。

完整有效 target 直接 Native KEEP。上述 STOP 数包含完整输入、工具不支持和预算回退，不能把 STOP 一律解释为固定 TS-ICL。TimesFM low 也可能因剩余预算转用冻结回退顺序中的其他可行动作。

## 真实账本与执行一致性

对 28 个冻结策略逐一执行全部 324 个 fit 变体，共 9,072 条 CPU typed replay：

1. 传入部署入口的只有 `VisibleState` 白名单；取得指定工具后才构造对应 `AcquiredEvidence`。
2. 用真实工具费用减少剩余预算，再调用冻结终态，叠加所选最终治理及预测费用。
3. 按实际 task/classification 目标及 lambda 重算 fit 目标与费用，均与冻结模型保存值在 `1e-9` 容差内一致。
4. 检查每条完整 target 记录都提交 KEEP 且不取证。unsupported、缺失证据、工具错误与预算不足使用冻结可行回退；所有最终动作都放不下时仍记录正费用及预算未满足，不以零费用掩盖。

轻量回归另覆盖：未购工具身份拒绝、未来字段拒绝、缺失证据不是实测零、完整输入零预算仍有真实最终成本、昂贵但不可达的动作不影响廉价分支、按 H 预算准入一致，以及工具失败后选择剩余预算内的回退。

本轮治理输入与原始预测没有变化；原始观测保护和预测身份沿用原冻结预测账本及 r3 已验收血缘。本核验没有借 origin 尺度修正重新生成或替换旧模型预测。新学习尺度与外层报告尺度单列。

## 分母与不确定性

六套评估逐家族/策略检查 UID 集合及唯一性：DEV、T_check、T_acq、T_fit、金融附表、新位置组合检查均保留完整分母。DEV 与金融附表的 legacy/TATO `common_decisions.json` 已再次核验通过，分别为 16,692 行/107 组、1,284 行/107 组；其他四套仍是原 r4 策略矩阵，不声称补跑了外部基线。Bolt low 在 TRAIN 上不存在整覆盖预算可行的最强固定流程，该比较组显式缺失，不补零；已实际运行的每组保留全部 UID。

描述性统计由 `scripts/v431_r4_statistics.py` 生成，source 内按原时间相邻两个 parent 分块、2000 次 bootstrap、seed 101，变体和跨度不拆 parent。单一 USTS parent 与两个金融 parent 的时间不确定性不可识别；旧 DEV 反复使用，不构成确认。TimesFM 相对旧 R2 CART 的差异只落在单一 USTS parent，使 bootstrap 区间退化为同一点；这不意味着差异获得了精确或显著的总体证据。

## 可复核入口

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" -m pytest tests/v431_r4/test_runtime_contract.py -q
"$W2_CORE_PY" tests/v431_r4/test_runtime_contract.py
"$W2_CORE_PY" scripts/v431_r4_statistics.py
```

- 冻结审计：`results/v431-r4/verification/frozen_policy.json`
- 实际执行日志：`logs/v431-r4/frozen-policy-verification.log`
- 运行契约测试日志：`logs/v431-r4/runtime-contract-tests.log`
- 描述性统计及原始配对行：`results/v431-r4/statistics.json`
- 历史各次统计快照：`results/v431-r4/statistics_runs/`

当前结论是实现与账本一致，尚非方法晋升。high 两家族的主树均为固定 H 取证结构，不能宣称已学得有额外收益的选择性获取。
