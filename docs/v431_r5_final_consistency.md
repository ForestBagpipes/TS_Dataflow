# r5 最终一致性核对

2026-09-16，当前服务器只读冻结资产与已有结果复核。未修改冻结源码、未训练、未启动 GPU、未打开 calibration/test；没有重复运行无关测试。本文件是检查记录，不替代共同主表。

## 冻结资产

逐文件重新计算 SHA256，`results/v431-r5/fit/manifest.json` 登记的运行入口及 geometry、dataset、scoring、controller 五个源码均与当前文件一致；两个 main 数据 joblib 与冻结 input_sha256 一致。`models.joblib` 与 `models_frozen.json` 登记值一致，manifest 本身亦一致。

- 模型 SHA256：`6bac8291c9c06eca4cb2c6f9a9b6fe49373d51815ff302421fc92b70c6d12792`。
- manifest SHA256：`54604b188f06b550dfdd7b2dd6ac194342619f0bd61e3c5c5db13fb4da5b60fe`。
- 两家族真实 fit/gate 为54/21 parent；current/free/prior支持54 parent，history支持51 parent。1296动作监督行不是1296独立样本。

上述检查只证明已登记文件未变，不是所有依赖的软件供应链证明。文档、后置统计及新骨干原生验收源码不冒充这套冻结候选的组成部分。

## 主表和机制结论

读取共同主表与实际 decisions 后，下列高预算数值相符：

| 方法 | Bolt MASE | TimesFM MASE |
|---|---:|---:|
| r5 | 1.152415 | 1.074244 |
| 免费参考 | 1.152415 | 1.069398 |
| r4免费覆盖修复 | 1.152415 | 1.069398 |
| DIRECT_control | 1.146635 | 1.095305 |
| CART_H | 1.168004 | 1.069398 |
| 继承R2 CART | 1.136486 | 1.069086 |

R2信息不同，不能作为同信息消融。r5未同时超过两家族强简单对照。Bolt与免费参考的预测相同；TimesFM退步。固定轨迹FULL相对RAW为Bolt −0.001197、TimesFM +0.000418；不能将整体评分误差下降改写为最终预测改善。

固定轨迹拥有至少三个数值不同预测的窗口为Bolt103、TimesFM102；这是机制实验的覆盖，不能移植为自适应主方法的覆盖。实际 `evaluation/dev/decisions.json` 中：

| 主方法 | low 至少3不同预测 | high 至少3不同预测 | 各预算完整分母 |
|---|---:|---:|---:|
| Bolt r5 | 0 | 0 | 156 |
| TimesFM r5 | 5 | 9 | 156 |

因而Bolt主策略未自然触发可支撑高阶联合几何贡献的三不同预测场景。TimesFM高预算也只有9窗，不能写成广泛覆盖。

## 失败、超时和费用不可混用

离线TimesFM `R5_high` 保留一次真实求解失败：UID `c82550222faa9ce22b0f7f5322de427c12bd953d485265d4098c52bcc1a40ecf`，ETTm1:47440:48144、H192、target_block_10。已查询2版本，求解局部时间限制触发，返回参考A4_RIDGE_CONTEXT；记录 `solver_timeout_STOP`，求解耗时0.063718秒、0迭代、gap未知，完整组件费用0.492545秒。这次没有超过3.5秒总预算。主表“超支0”不等于“失败0”。失败窗口仍在156分母中，不填零、不删除。

这与真实在线TimesFM低预算 `main-natural-low-3` 是两条不同事件。后者UID前缀b1a39ab1407，完整请求1.049711秒，第二版本预测封装返回后预算耗尽，求解立即停止；不能把它说成离线高预算的同一次失败，也不能全归因于几何算法耗时。

在线自然请求每家族38次（每预算19），不是完整156窗在线实测。Bolt低预算有1次1.346169秒超支；TimesFM低预算有1次1.049711秒超支及失败；高预算自然抽样均无超支。受控故障和零预算各自另列，不能冒充自然发生。TimesFM低预算7窗最终动作不同于离线，费用尾部可改变行为；其高预算抽样动作一致。

离线组件invoice加当前CPU墙钟、在线完整请求墙钟、模型原生推断时间是不同口径。不得把三者混成同预算保证。已有在线审计分别保留完整进程、服务启动和请求墙钟，没有将它们相加重复计费。

## Chronos-2单独敏感性表

`chronos2-native-check/audit/status.json` 完成，160条原始输出校验通过后才读旧DEV标签。旧DEV26 parent/156变体，Native KEEP MASE0.957177；这是新骨干原生结果，没有运行r5治理，不是第三独立模型家族，更不是r5跨骨干成功。

费用0.017027秒/窗是按source/parent/variant宏平均的原生推断donor费用。DEV实际104次推断、52次复用，物理推断总1.947477秒，外层完整子进程7.965819秒；两者不是同一指标。去除首次物理调用后103次均值/P95/最大0.015432/0.016373/0.020114秒，仍不是完整请求时延保证。TRAIN仅1parent4案例，外层6.369213秒。

首次记录关键字冲突失败已保留：外层6.313467秒、实际一次模型调用、持久化原始输出。原失败status的durable列表为空，原因是records追加前异常；实际0000.npz及hash仍在归档。独立结果状态的prior_failed_attempts保留该成本。下载917.244秒单列，不归为推断费用，也不因后续缓存复用归零。

## 仍未验证

- r5联合约束和选择性调用未通过两家族开发准入，不支持方法晋升或SOTA。
- 完整请求所有窗口的预算合规未验证，且抽样已有低预算反例。
- 金融仅2parent，Bolt治理弱于KEEP；自然缺口轨道仍缺，完整输入一致仅说明KEEP契约通过。
- 8-trial TATO适配与后续有限scene试验不能写成官方完整500-trial复现；官方与受限治理协议须分开。
- Chronos-2未执行治理共同表，不支持把其骨干改善归因于本方法。
- 旧DEV、已看check/acq及金融附表均非独立确认。calibration/test继续封存。

审阅证据入口：`fit/manifest.json`、`fit/models_frozen.json`、`evaluation/dev/decisions.json`、`evaluation/dev/common_table.json`、`statistics/report.json`、`statistics/online_audit.json`、`chronos2-native-check/audit/status.json`。本轮核对未发现新增冻结文件或上述数字矛盾；明确保留了超支列无法表达的失败，以及固定轨迹与自适应覆盖的区别。

## 同UID逐来源骨干敏感性比较

使用现成共同决策与Chronos-2审计行，核对五个方法的156个UID完全相同，按source→parent→variant权重计算。每个来源内parent等权，同parent变体再等权；未运行推理、未读取任何新标签。

| 来源 | parent / 变体 | Native Bolt | Native TimesFM | Native Chronos-2 | Bolt r5 | TimesFM r5 |
|---|---:|---:|---:|---:|---:|---:|
| ETTm1 | 14 / 84 | 0.997525 | 1.180916 | 1.142987 | 1.026034 | 1.051444 |
| Solar | 11 / 66 | 1.751732 | 1.193565 | 0.766117 | 1.420680 | 1.121500 |
| US_Term_Structure | 1 / 6 | 1.026104 | 1.045030 | 0.962426 | 1.010530 | 1.049787 |

Chronos-2宏平均更低不等于逐来源普遍更强：ETTm1上它弱于Native Bolt以及两家族r5；Solar与USTS上它的点估计低于表中其余方法。Solar上的点估计差异未附本分析的统计区间，不能称统计显著，也不能外推为所有来源的治理增益。这里只比较冻结骨干的原生KEEP及已有r5输出，没有Chronos-2治理实验；USTS仅1parent，不能支持泛化。原始小表及输入hash见 `results/v431-r5/statistics/backbone_source_comparison.json`。
