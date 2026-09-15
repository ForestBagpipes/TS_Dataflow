# r5 TRAIN 路径空间与共同对照审计

## 冻结强简单参照

`results/v431-r5/strong_simple_freeze.json` 直接继承 `results/v431-r4/common_fixed_freeze.json` 的原T_fit选择及哈希，不依据本轮DEV重新选择家族冠军。高预算开发门槛比较臂为 `TRAIN_BEST_FIXED_FLOW_high`。原低预算没有为所有家族提供一致可行的固定流程，因此共同表保留缺项，不制造一个低预算冠军。

该参照不是本轮唯一必须超过的对照：同信息免费策略、DIRECT_control、CART_H和继承R2完整方法均保留。R2证据不同，不当作同信息消融。TATO仍是原8-trial适配，费用与失败沿原审计记录继承。

## 实验A：只在TRAIN计算的可行空间

真实入口：`scripts/v431_r5_common.py --space`。每家族54 fit parent、324相关变体。参考来自本轮已冻结的免费参考策略。完整有效target只允许KEEP；不完整输入从五臂中枚举参考加零、一、两个不同动作，最多三个版本。每预算、每家族3876条路径，共15504条，保留全部路径charge与失败预算状态。

物化每个候选后才可看到input hash，所有候选物化费用都计费；同请求已执行的相同模型、输入、H预测才复用预测，不再收重复forecast费用。每条路径包含参考执行、候选治理、未共享预测和当前免费特征时间。几何求解尚未按每条oracle路径实测，因而**单列登记的每新增版本0.05秒求解上限与0.001秒输出预留**；预算可行性按已测组件费用加预留判定，不能把此诊断称为在线延迟保证。

| 家族 | 预算 | reference loss | 参考到可行oracle的收益 | 参考本身超预算窗 | 平均可行动作数 |
|---|---|---:|---:|---:|---:|
| Bolt | low | 3.214790 | 0.195371 | 2 | 4.101533 |
| Bolt | high | 3.214790 | 0.195371 | 0 | 4.111111 |
| TimesFM | low | 2.870430 | 0.140387 | 0 | 4.105364 |
| TimesFM | high | 2.870430 | 0.140426 | 0 | 4.111111 |

单位为MAE/origin可见尺度，**不是对外报告MASE**。无可行路径时不生成免费oracle胜例，记录reference infeasible，并在完整分母中将可行oracle增量记为0。上述oracle用未来真值选路径和已执行终动作，只是诊断上界，不是可部署方法。

两家族均222/324窗有至少三个数值不同预测；按source/parent/variant宏权重覆盖率均77.78%，不能把该宏比例误写为简单窗比例。加权数值不同预测数量分别3.666667和3.618600；平均已登记alias数1.333333。多动作、多个路径均不增加独立parent支持。

完整文件：`results/v431-r5/space/paths.json`、`windows.json`、`summary.json`、`status.json`。实际日志 `logs/v431-r5/space-first.log`。空间存在不意味着score或查询策略能够实现空间收益。

## 原r4阈值的免费覆盖修复对照

`repaired_coverage` 原样复用两家族 `JOINT_high` 冻结终态：`long:covariate_coverage <= 0.7548076923076923` 选A2，否则选context ridge。不重训阈值或动作。该覆盖已确认可以由当前mask及availability构造，故本对照无需历史模型。完整KEEP、metadata unsupported、低预算回退沿原冻结action成本和fallback顺序。

| 旧DEV | 原r4-JOINT MASE | 免费覆盖修复 MASE | 修复后组件秒/窗 |
|---|---:|---:|---:|
| Bolt | 1.154124 | 1.152415 | 0.113136 |
| TimesFM | 1.069398 | 1.069398 | 0.219311 |

Bolt动作可能因无需为历史模型预留预算而变化，不能把差值解释成新增预测信息。TimesFM预测保持一致且减少历史调用费用。本轮r5应与此修复版免费流程比较，不能仅比较有冗余付费的原r4。

金融修复对照：Bolt MASE3.042476、组件0.700892秒；TimesFM MASE4.890237、组件0.435840秒。仍只有2parent、12变体，不能据此证明金融泛化；Bolt仍弱于历史金融KEEP2.820959。

## 共同表完整性与实际失败

`--merge main` 生成11700行、75个家族/策略组；`--merge financial` 生成900行、75组。对每个方法核验共同UID、source、parent、候选输入身份和逐窗报告MASE，保留完整分母。75而非76源于原表缺一项 `TRAIN_BEST_FIXED_FLOW_low`，没有填造缺失方法结果。

继承baseline保留原path/hash、信息条件和费用范围；其历史组件计时不是本轮自然在线墙钟。原r4共同表不覆盖，r5合并输出位于 `results/v431-r5/evaluation/{dev,financial}/common_*.json`。

首次DEV合并实现对每条旧行重复计算同一大文件SHA，造成无效CPU开销；仅终止本子任务自己的该合并进程，将SHA移至循环外，再完成合并。原日志 `common-dev-first.log` 保留；首次未写共同结果，第二次输出为首份完成表。金融首次合并完成。此调整没有修改预测、策略或统计规则。

共同结果已经通知主执行agent及几何统计agent。后续正式结论由主表、同信息固定轨迹消融和真实在线验收共同给出，不能从oracle或免费覆盖修复直接推断r5方法成功。
