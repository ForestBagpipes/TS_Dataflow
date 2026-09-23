# v55 已核实事实与待验收项（2026-09-23）

本页供论文和交接引用。主集 TEST 曾参与早期设计，以下主集比较均属探索性结果。数字来自完成 D-01/D-02 修正后的 18 份 `results/v55/evaluation/*.json`，不得与早期 v52/v54 表格混用。

## 已核实的主集结果

| 骨干 | 选中 λ | IntroAct MASE | Source Fixed MASE | Native KEEP MASE |
| --- | ---: | ---: | ---: | ---: |
| Bolt | 0 | 1.382575 | 1.360247 | 1.466430 |
| TimesFM | 64 | 1.528443 | 1.526775 | 1.682034 |
| Chronos-2 | 0 | 1.364959 | 1.448380 | 1.579342 |
| 三骨干平均 | — | 1.425326 | 1.445134 | 1.575935 |

每骨干均优于 Native KEEP，配对 parent 区间不含零。对 Source Fixed，Bolt 的差值（IntroAct 减对照）为 +0.022328，95% 区间 [+0.004429,+0.043174]；TimesFM 为 +0.001668，Chronos-2 为 −0.083421，后两者区间均跨零。规划中的“三骨干都不输给 Source Fixed”未实现。只有 TimesFM 选中非零有限池化，且 Full 对 λ=0 的配对差 −0.012457，区间 [−0.038625,+0.013504]。λ=∞ 共用 Source Fixed 的来源均值，但完整策略并不相同，见 `v55_deviation_20260923.md`。

Full 干预率 55.2%，harmful loss 0.0340；去掉执行门后 MASE 为 1.4143，harmful loss 0.0515，干预率 100%。因此执行门换取较低伤害，平均误差点估计反而更高。校准到 α=0.01、0.02、0.03 时，Bolt 与 TimesFM 的独立 TEST 阈值常超过目标；α=0.05 三骨干均达到目标。TEST 内交叉校准利用另半 parent 已知标签，只是回顾性诊断。

去掉 Exchange 来源后，Full 对 Best Fixed 的差值在 Bolt/TimesFM/Chronos-2 分别变为 +0.0187、+0.0015、+0.0077。对 Native KEEP 的差值仍全为负。来源敏感性全部数值见 `results/v55/source_diagnostics.json`。

## 外部基线与确认集边界

PSW-I 八来源修复已通过合并内容检查：`train_eval` 424 条，`test`、`test30`、`test50` 各 760 条；主 TEST 129 条不满足合理性约束，修复仍留档且分母不变。已建立 2704 个基线预测候选。T1 的 Electricity、Weather 与确认集原队列仍在 GPU 上运行；PSW-I 和 T1 的三骨干预测尚未完成，主表不可填这两行，也不能宣称胜过全部九个对照。

Solar 和 US Term Structure 在 v43 开发阶段出现过。可用尚未进入 v55 选参的确认 TEST 时间区间做额外验证，但不能称为“从未参与开发的两个新来源”。原 v54 确认集 SAITS 每来源按四块重复拟合；v55 隔离队列会改成每来源一次拟合。确认集冻结、TEST 审计、评价均未完成，不得写成独立复现。

## 验证与运行记录

`tests/v55` 加 `tests/v54` 共 29 项通过；18 份 v55 评估文件的选择器代码 SHA-256 一致。服务器分支 `codex/introactts-v43-bootstrap` 上相关代码与图表已推送至 `c9cbbefdf7caef80551c2a9b48e630930f4985cd`。后台 GPU 收尾顺序为原确认集预测、抽样硬件复算、E3 真实延迟，之后再验收 T1/PSW-I 外部行并运行隔离的单模型确认集。远端提交成功不表示 Windows 工作区已经快进同步。
