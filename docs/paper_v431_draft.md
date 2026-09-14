# IntroAct-TS: Evidence-Seeking Data Governance for Time Series Foundation Models

状态：开发草稿，结果等待同一汇总脚本写入；不构成录用、SOTA或确认成功。

## 背景与问题
真实时序同时含数据缺陷与应保留的真实变化。治理改变TSFM可用信息；修复更接近缺口真值未必改善预测。保存原始副本提供可逆性，却未给出部署时采用哪个治理版本的决策规则。未来真值不可见、验证有计算成本，因此研究有代价的合法证据如何支持治理与停止。

## 定义
episode具有固定原始context、future和finite评价mask。状态仅含dirty输入、当时可用协变量、已生成候选及已取得的工具结果；动作池含KEEP和四种治理。终态策略pi选择治理动作，获取器至多查询一项工具。目标是source-parent加权真实TSFM任务损失与完整部署成本；事后oracle只用于诊断空间。

## 方法
基础树直接按五臂损失矩阵的最小加权叶风险分裂。证据细化仅在独立train gate的经验分组收益下界为正时保留，否则维持父策略。历史工具以r=L-H重新治理前缀，在dirty已知段评价目标跨度；同原点H32与旧H32作为代理错配消融。冻结pi后在独立T_acq以其实际前后决策差减完整成本差训练单步获取器；STOP、适用性、总分支预算、血缘和最终真实TSFM输出一次贯通。

直接决策树与安全改进/动态信息获取相关思想借鉴SPO Trees、SPIBB、DIME；TATO输入变换、AegisTS清洗agent及下游奖励已存在，不能称为本项目原创。待验证增量是任务对齐证据、可拒绝细化与按真实部署价值取证的组合，必须由对应消融建立，经验gate不是理论安全保证。

## 实验预登记
固定三来源、26dev parent/156相关变体；110train parent四段隔离。比较固定五臂、旧HGB、dirty loss tree、同证据CART/flat loss tree、剪枝/不剪枝、固定/条件/random工具、新单步agent、全部调用及官方TATO短预算适配。第二独立TSFM优先TimesFM。共同origin、finite mask、source宏权重；离线生成/训练搜索/部署/最终预测费用分别报告。

<!-- GENERATED_RESULTS_BEGIN -->
| Chronos-Bolt共同策略 | MASE ↓ | 批量组件秒数 |
|---|---:|---:|
| FIXED_A0_NATIVE | 1.258454 | 0.0899 |
| FIXED_A2_SINGLE | 1.157005 | 0.1201 |
| OLD_DIRTY_HGB | 1.165414 | 0.1592 |
| OLD_LEARNED_HGB_COMMON_BUDGET | 1.190112 | 0.4766 |
| DIRTY_LOSS_TREE_D1 | 1.163685 | 0.1066 |
| DIRTY_LOSS_TREE_D2 | 1.200158 | 0.1117 |
| CART_target_horizon | 1.136486 | 0.6580 |
| FLAT_LOSS_TREE_target_horizon | 1.165232 | 0.6625 |
| ALL_d2_target_horizon_gated | 1.191788 | 0.6637 |
| ALL_d2_target_horizon_unpruned | 1.184872 | 0.6569 |
| AGENT_d2_target_horizon_gated_high | 1.200158 | 0.1122 |
| TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR | 1.685227 | 0.7032 |

完整共同表： [v431_main_table.md](v431_main_table.md)。 当前已完成 49 个模型/方法组合，缺项 [{"backend": "timesfm_tato", "backbone": "timesfm-2.5-200m", "policy": "TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR", "status": {"status": "running", "pid": 14594, "worker_python": "/home/vipuser/work2-envs/w2-chronos/bin/python", "request_sha256": "89bae9a35aaf88b249d0ce9f81f9e2b457d409ac156f3878fd316aa1e7930a98", "rows_done": 11, "future_labels_read": 0, "heldout_labels_read": 0, "elapsed_seconds": 16.030243392999637}}]。

本轮结果否定当前完整新agent优于强固定/CART对照的主张。新agent全部STOP，不能宣称主动获取贡献。普通CART使用dirty缺口与ridge遮挡误差，历史跨度变化未产生增量；因此证据细化不是已证实的独有突破。TATO为显式NaN桥接+8trial适配，非官方完整复现；跨家族结论以完整共同表为限。

条件source-parent bootstrap：{"CART_target_horizon": {"reference": "FIXED_A2_SINGLE", "gain_mase": 0.02051873866115983, "conditional_95_interval": [-0.012210532054364138, 0.0716598409204611]}, "AGENT_d2_target_horizon_gated_high": {"reference": "FIXED_A2_SINGLE", "gain_mase": -0.04315313707710855, "conditional_95_interval": [-0.07616418487538508, -0.016768135648880633]}, "ALL_d2_target_horizon_gated": {"reference": "FIXED_A2_SINGLE", "gain_mase": -0.034783537436829715, "conditional_95_interval": [-0.06829325221953789, -0.0095467652846367]}}。区间未校正连续parent残余相关、配置多重比较；USTS一个dev parent，仅开发诊断。

<!-- GENERATED_RESULTS_END -->

## 适用边界与待验证贡献
开发集已多轮使用，不是独立确认；USTS只有一个dev parent。主机制未胜过普通gating时保留相当/失败结论；获取全STOP不支持主动贡献。仅验证推理前治理，未证明TSFM参数适配或文本大模型训练收益。独立calibration/test在满足完整冻结条件前封存。
