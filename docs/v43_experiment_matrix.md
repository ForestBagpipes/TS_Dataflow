# v4.3 实验矩阵

2026-09-14 创建。完成状态以原始 run/status 为准，不把 CLI 存在当作验收。

| 阶段/臂 | 当前状态 | 证据/依赖 |
|---|---|---|
| 接管与旧入口审计 | completed（静态） | `v43_entrypoint_audit_20260914.md` |
| CPU 数据/worker 语义 | completed（已列测试范围） | 43 passed；`results/v43/semantic_gate.json` 指向原日志 |
| 32 origin 原始输入准备 | completed | 20 train/12 dev；future labels read=0 |
| 真实 TS-ICL/Bolt worker | completed（已验接口范围） | 两必需模型 ready/passed，真实 pilot 通过 |
| L512/H32 真实 pilot | completed（接口诊断） | 32 origins、64 插补、96 预测；独立复核通过 |
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


## 2026-09-14 21:00 post-hoc：真实 P1 pilot 完成

32 origins（20 train / 12 dev）、L512/H32、64 次真实 TS-ICL 插补和 96 次 Bolt 预测全部完成；43 项 CPU gate 通过，独立原始结果重算通过，未读 calibration/test。运行 21.794 秒，最大 GPU 分配 710,672,896 字节。KEEP / SINGLE / COV 来源宏平均 MASE 为 1.322762 / 1.316489 / 1.228219；COV 宏平均 MAE 反而变差，两插补臂各 15/32 个 origin task harm，无 CI。仅为接口与开发诊断，正式 A0–A5/H96/H192 未运行，PICS_joint_relabel 不变。首轮导入失败和可选 Chronos-2 TLS 失败保留。证据与原始结果入口见 `docs/v43_pilot_report_20260914.md`、`docs/v43_pilot_evidence_20260914.json`；下一步补长来源、接正式强对照及 A5 静态规则。


## 2026-09-14 P2 首批开发配置冻结（未运行结果）

P1 已完成且独立复核通过后，新增 `configs/v43/p2_first_dev.yaml`、`cli p2` 与 A4/A5 正式接线。只取 ETTm1 / Solar / USTS 的 dev 原始区间，分别 14 / 11 / 1 个不重叠基础 parent；两个 horizon 96/192 及 raw、target block 10%、全部 siblings shared block 10% 共 156 个 episode。这些变体不是 156 个独立样本；全历史 ridge 读取区间在 dev 内重叠，正式推断还须按更大依赖块处理。

Solar 复用本机文件，与论文作者仓库 Git blob 完全一致。只按原行号保留同步时间；来源说明为 2006 年 Alabama 137 路 10 分钟光伏，压缩文本无原始时间戳，不能伪称已恢复绝对日历或发布延迟。库存只统计行宽，不解码 heldout 数值。来源证据见 `docs/v43_p2_source_provenance_20260914.json`。

首批重点检验长缺口的新信息收益，以及原始/共享缺失的保护与负对照；5%/点缺失/spike/valid-event 标注和其他来源为后续矩阵，不能把首批当完整污染实验。固定通道0、seed101、L512、缺口[230,281)、不按标签挑窗口。只要求 TS-ICL/Bolt 两个已通过模型，保持 batch1/GPU单任务。

执行臂为 A0 native/ffill、A2 single、A3 官方全合法covariates、A4当前context及同split全合法历史ridge、A5严格嵌套OOF静态eta。A4历史只读 dev 起点到当前context起点，再拼当前dirty输入，不重新打开当前gap真值；这是额外历史信息轨道。A5保存七类真实遮挡输入，支持不足明确回到同origin已验证A2，真实worker缺行/失败仍报错；eta平局取0。候选去重只在同episode、同horizon、完整输入hash下进行并保存alias，所有候选完成真实预测后才读future。

A1仍为blocked_adapter：`experiments/v39_phase0_replay.py:321` 强依赖771个冻结parents，`:450`按历史候选标签拟合LODO PICS并重放；源码存在不等于可对本次新时间区间部署。该参照待合法适配，不把旧分数贴到新UID，也不把缺失参照填0。原生多变量任务模型尚未运行。A9只对本轮完整已执行候选集生成开发上界，名称明确为A9_ORACLE_AVAILABLE，不冒充全候选上界。

新增测试覆盖gzip越界标签不可解码、父区间共享、shared辅助遮挡、全历史不重读gap、A5不适用回A2、漏真实预测报错、ridge观测值不变及eta平局0。运行以新配置绑定的CPU gate为前提，结果产出前不作方法成功结论。PICS_joint_relabel不变，不将规划写入DOCX成果。
