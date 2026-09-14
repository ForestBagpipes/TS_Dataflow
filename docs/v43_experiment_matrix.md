# v4.3 实验矩阵

2026-09-14 创建。完成状态以原始 run/status 为准，不把 CLI 存在当作验收。

| 阶段/臂 | 当前状态 | 证据/依赖 |
|---|---|---|
| 接管与旧入口审计 | completed（静态） | `v43_entrypoint_audit_20260914.md` |
| CPU 数据/worker 语义 | completed（已列测试范围） | 40 passed；`results/v43/semantic_gate.json` 指向原日志 |
| 32 origin 原始输入准备 | completed | 20 train/12 dev；future labels read=0 |
| 真实 TS-ICL/Bolt worker | pending_validation | 源码接口已对接，模型验收 manifest 尚缺 |
| L512/H32 真实 pilot | blocked_dependency / queued | 一次性队列只在依赖和 CPU gate 通过后执行 |
| A0 native KEEP / legacy forward fill | not_run | pilot KEEP 不等于正式 A0 表 |
| A1 PICS / v3.9 D | not_run | 保留历史参照；新协议适配待审计 |
| A2 TS-ICL 单变量 | not_run | 等 pilot 通过再运行正式 H96/H192 |
| A3 官方 covariates | not_run | 同信息强对照，不能当严格单变量 |
| A4 direct ridge 与全历史强版本 | not_implemented / not_run | 真实模型 pilot 后推进 |
| A5 nested OOF residual / static eta | CPU_impl_tested / not_run | 外层遮挡毒化通过，真实 proposer 尚未接入完整候选实验 |
| A9 oracle | not_run | 全候选必须有完整真实任务标签，不填缺失 gain |
| A6–A8 工具策略 | pending | 可见状态/选择接口通过测试，工具 ledger 与模型尚未训练 |
| calibration / adaptation / confirm | pending | 读取权限仍关闭；适配仅 pair hash 接口已测试 |

首批队列预算为 TS-ICL 64 个插补请求 + Bolt 96 个预测请求，32 origins，3 个 worker 加载。内部调用次数、加载/推断耗时、峰值显存和每千 origin 成本待真实 pilot，当前不提供伪造时间或租费估计。正式实验矩阵预算在 pilot 后按相同协议实测外推，保留20%余量。
