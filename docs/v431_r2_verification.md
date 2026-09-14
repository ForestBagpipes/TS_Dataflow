# v4.3.1-r2 独立复核

2026-09-15，Asia/Shanghai。两阶段均在当前服务器的 core 环境以 CPU 执行。校验未启动 GPU、未重训部署模型、未修改冻结结果，未读取 calibration/test 标签。

## 结论与原始记录

真实预测、数据隔离、终态冻结、获取标签和共同主表通过独立复核；原主表漏计的规划费用已通过派生账本补全并独立复核。费用补全未改变方法效果、动作或预测哈希。本结果是实现与记录的验收，不构成方法晋升。

| 阶段 | 原始报告 | 实际通过范围 |
|---|---|---|
| 原始预测与决策复核，46.804 秒 | [20260914T165023.775309Z.json](../results/v431-r2/verification/20260914T165023.775309Z.json) | 5010 个 TimesFM 请求、3504 份原生 point/quantiles 输出、8160 项两家族任务损失、648 条获取标签、4992 行共同决策 |
| 派生费用复核，1.317 秒 | [20260914T165433.061318Z.json](../results/v431-r2/verification/20260914T165433.061318Z.json) | 312 组实测规划样本、4056 行费用补全、936 行固定策略保持不变、96 行来源表和 32 行主表 |

首次执行因审计脚本尚未识别 `initial-selection`、`post-evidence-selection` 费用字段而失败。[失败记录](../results/v431-r2/verification/20260914T164915.834933Z.json)完整保留。仅补充了审计字段支持，未通过修改生产模型、标签或结果消除失败。

## 数据、模型与决策

- TimesFM 请求与输入、原始 mask、availability、原生输出、模型 revision、权重 SHA、官方代码 commit 及生产者源文件相符；跨请求缓存命中按实际唯一调用重新计价。
- 当前输入为 512 步；历史输入分别为 416/320 步，exclusive cutoff 与原始时间一致，没有读取该历史原点后的输入来生成候选。
- fit/check/acq 为 75/17/18 个独立 parent，dev 为 26 个；完整原始读取区间无跨组重叠。18/37/75 个拟合 parent 严格嵌套，check/acq 不进入拟合子集，来源宏平均和同 parent 六变体权重正确。
- 两家族的 6 个工具可见状态模型通过检查；终态冻结早于获取标签。648 条标签均用同一冻结策略两端的真实任务预测损失和实际费用差重算，角色全部为 T_acq。24 行固定学习曲线独立复算相符。
- 32 个策略均使用共同 156 个 episode、26 个 parent。STOP、强制 STOP 与家族固定参照的候选输入和实际预测一致；完整观测输入的五臂与 KEEP 等价。
- 两个预算合计：Bolt 312 行全部 STOP；TimesFM 200 行获取 mask、112 行 STOP。TimesFM 每预算实际调用 100/156 个 episode，主表 `tool_count=0.444444` 为来源宏平均，不是 episode 微平均。

## 费用补全与范围

[planning_cost_samples.json](../results/v431-r2/planning_cost_samples.json)保存两家族各 156 个请求的独立实测。新策略补初始选择、`mask_views` 适用性检查和预算估计对象准备；旧同证据 CART 仅补预测选择；KEEP、固定 TS-ICL 和固定参照不补 dirty 或规划费用。

逐条核对新增账项的 family/UID、样本映射和值完全一致，旧账项未减少或修改，没有重复收费身份。624 项实际计时之和为 **0.259831 秒**；这些样本在不同策略的假定部署账单中分别计入，累计新增 **2.586319 秒**，不能把后者当作本次 CPU 计时的实际墙钟。

[accounted_decisions.json](../results/v431-r2/accounted_decisions.json)、[accounted_table.json](../results/v431-r2/accounted_table.json)及[来源表](../results/v431-r2/accounted_metrics_by_source.json)均重新求和。4992 行超支标记复核后仍全部为 false。模型、标签、原决策与原主表文件 SHA 保持不变，任务效果指标逐项保持不变。

此处费用是实际组件费用加等价 CPU 复测规划费用，不能标成原始请求的连续墙钟追踪。训练、初始化与数据加载、缓存生成、审计开销仍单独列账；在线冷启动、热请求和完整 worker 过程计时见对应在线产物。本脚本未重复审计在线记录、TATO 或新增金融条件表。

## 复现与状态

校验入口为 [scripts/v431_r2_verify.py](../scripts/v431_r2_verify.py)，独立读取数据和原始结果，主表宏平均重新计算，不调用生产汇总函数。

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" scripts/v431_r2_verify.py --phase all
"$W2_CORE_PY" scripts/v431_r2_verify.py --phase accounting
```

第二个命令只核对派生费用，无需重新扫描模型原始输出。每次调用保存新的时间戳报告，历史失败和已通过报告均保留。完整方法仍未晋升，PICS_joint_relabel 的历史 incumbent 地位不变，calibration/test 继续封存。
