> 2026-09-16 04:23 执行状态更新：本页下文保留准备时的协议与预登记状态。实际执行已推进：四个ETTm1 TATO场景各500trial完成，追加来源部分搜索按截止保留partial；Chronos-2原生KEEP已完成旧DEV26parent/156变体，MASE0.957177。Weather文件、输入/mask及重叠审核已完成准备。最新完整状态以 [交付快照](v431_r5_final_snapshot.md)、[TATO实际结果](v431_r5_tato_scene_results.md)、[Chronos-2结果](v431_r5_chronos2_native_results.md) 和 [主矩阵准备](v431_r5_main_readiness.md) 为准。准备文中的“未运行”不覆盖后续真实记录；官方完整复现和r5主矩阵确认仍未完成。

# Chronos-2 原生KEEP独立接口验收

本页是r5候选冻结后的骨干接口/敏感性准备，不是第三个独立模型家族，不改变r5两家族主表，不将骨干自身差异归因于治理。当前GPU验收状态以 `results/v431-r5/chronos2-native-check/{train,dev}/status.json` 为准，本文不把下载和输入准备写成已通过模型实验。

## 资产与配置

- 模型：`amazon/chronos-2`，revision `29ec3766d36d6f73f0696f85560a422f50e8498c`，Apache-2.0。
- 官方权重477,930,472字节，SHA256 `ddcda3c7508bf2528087723e98a20707cc04b7f370ae275a9fd88078ddba4f42`。
- 独立缓存：`/home/vipuser/work2-cache/chronos2-native-check/29ec3766d36d6f73f0696f85560a422f50e8498c`。不覆盖旧bootstrap模型状态，不提交权重。
- 复用现有w2-chronos的Chronos2Pipeline，不安装依赖；模型float32，当前context512，H96/H192，batch_size1，cross_learning=False，取原生0.5分位点。
- 下载日志：`logs/v431-r5/chronos2-native-check-download.log`，明确校验配置及完整权重hash，不凭文件存在认为下载完成。

## 实际已准备的输入

只从旧当前context缓存读取数据；**1个独立T_fit parent、4个相关案例**，为 `ETTm1:0:704` 的raw/target_block_10 × H96/H192，不是4个独立parent。已逐UID核对旧partition、r4当前role表，并核对其属于实际r5参考策略fit的OOF parent清单。raw完整有限，受控缺口保留原51个NaN。另准备旧DEV **26个parent、156个相关context**；它们仍是旧开发样本，不是新确认。支持审核保存于 `support-audit.json`。

输入manifest包含source、parent、origin、L/H、mask、时间和availability hash、原输入dtype/hash、原生预测配置和模型revision。没有读取当前future目标、旧候选预测或calibration/test标签。准备日志：`logs/v431-r5/chronos2-native-check-prepare.log`。

## root统一GPU队列入口

```bash
source scripts/env_new_server.sh
"$W2_CHRONOS_PY" scripts/v431_r5_chronos2_native_check.py --run --suite train
```

TRAIN接口真实通过后才可运行：

```bash
source scripts/env_new_server.sh
"$W2_CHRONOS_PY" scripts/v431_r5_chronos2_native_check.py --run --suite dev
```

脚本自身单进程持有`locks/gpu.lock`，不得再由父进程重复flock。发现其他GPU任务则明确失败退出，不终止任何他人任务。首次输出目录不覆盖。

TRAIN逐个请求真实推断，记录模型冷加载、首次分支、每请求CUDA同步费用、原生分位输出、峰值显存和完整进程费用。DEV允许已执行的相同input/H推断去重，但每窗口仍保留原始donor费用，缓存不使方法成本归零。输入有效观测不得被适配器改变；输出必须有限且形状正确。

GPU前补充持久化：每个已完成请求立即保存 `requests/NNNN.npz` 的原始quantiles和point，flush/fsync后原子替换；逐请求保存records/progress。中途失败仍保留所有已完成原始预测、原始收费、物理调用费、冷加载以及失败阶段host wall。CUDA完成时间不可得时标未知，不填零。最后合并npz不再是唯一原始预测副本。

原input-status及准备源码hash不改；新增runtime_identity区分旧输入生成源码hash与本次运行源码hash。已核对安装源码：`pipeline.quantiles`确为property，预测输出为列表，其中张量形状 `(n_variates,n_quantiles,H)`。这仅为CPU源码接口核查，实际GPU形状仍须运行时断言。

GPU开始前增加截止保护（不改模型、输入或预测设置）：默认`--deadline 2026-09-16T04:45:00+08:00`，初始化及每个新请求前检查。到时保留已完成逐请求预测和费用，状态为`partial_deadline`，不得进入DEV完整评分；不终止其他进程。一次已经开始的原生调用不强行中断，结束后在下一请求前停止。

后续即使完成DEV原生KEEP，也只能报告骨干敏感性。它未训练r5 critic，没有执行治理候选，不能证明r5改善Chronos-2。真实评价必须在预测落盘后另由独立旧DEV评估器读取已使用的目标；本接口脚本本身始终不读未来标签。

### 03:23 首次运行与记录修复

首次 TRAIN 子进程实际调用一次原生模型后，记录构造的重复 `labels_read` 关键字触发 TypeError。外层子进程为 6.313467 秒；原始 quantiles/point 已持久化，保存在 `results/v431-r5/chronos2-native-check/attempt1-record-failure/train/requests/0000.npz`。原 status 的 durable 列表尚未追加这条记录，不等于文件不存在。旧失败目录、日志及队列状态完整归档，逐文件 hash 与路径映射见 `retry-map.json`。

修复仅将记录构造改为复制 manifest 后显式更新执行字段，重复字段 CPU 回归通过；模型、输入、原生设置和截止时间未变，不重复下载。新尝试沿原 CLI 由统一 GPU 队列启动。后置审计单列该失败尝试费用；首次失败不参与 DEV 评分，也不将已发生费用归零。
