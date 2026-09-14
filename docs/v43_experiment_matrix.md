> 2026-09-14 23:59 最终收口：共同表50个组合均已运行并独立复核；TimesFM固定五臂与TATO已完成，取代下文同步时的在途状态。全部三来源/26 dev parent/156变体，结果与费用以 [v431_sprint_report.md](v431_sprint_report.md) 为准。完整新agent未晋升，calibration/test封存。

## 2026-09-14 v4.3.1 当前矩阵（旧矩阵留作历史）

| 项目 | 本条同步时实际状态 | 共同证据/限制 |
|---|---|---|
| 五固定臂、旧HGB、dirty任务损失树、同证据CART/flat树 | 已运行 | 本地43策略共同26parent/156变体；非独立确认 |
| 8终态配置、独立gate拒绝、不剪枝消融 | 已冻结并运行 | 最大深度3、parent支持、train内部隔离；未晋升 |
| 2获取器、单步工具、STOP、固定/条件/随机/全部调用 | 已运行 | 新agent全部STOP，MASE1.200158；固定TS-ICL1.157005、同证据CART1.136486 |
| 旧H32、同原点H32、目标H96/H192历史证据 | 已运行并独立复核 | 6,656份新增raw输出，原始cutoff416/320，不读当前future作证据 |
| TATO官方实现短预算Bolt适配 | 已运行 | 数值与真实预算见共同报告；不称官方完整复现，不限制为本项目五臂 |
| 第二独立家族TimesFM | 统一GPU队列在途 | 本条不预填数字；以共同报告/实际状态更新 |
| 当前成本与共同主表 | 已产出并复核 | accounted_table.json；dirty诊断补费，初始化/离线/在线分列 |
| 本轮回归与标签身份 | 22项新测试、独立复核通过 | 8终态/2获取器/432标签、6,708决策；不构成方法成功 |
| calibration/test、方法晋升 | 继续封存/未晋升 | PICS_joint_relabel不变，无SOTA或确认成功声明 |

[当日共同动态主表与缺项](v431_sprint_report.md)、[预登记计划](v431_sprint_plan.md)、[论文论证草稿](paper_v431_draft.md)。本轮以A/B/C线并行组织；旧文档“先H2/H3通过再开始强baseline/第二家族”仅为历史调度，当前已取消该启动门槛，真实依赖与最终验收保持。

# v4.3 实验矩阵

2026-09-14 创建。完成状态以原始 run/status 为准，不把 CLI 存在当作验收。

| 阶段/臂 | 当前状态 | 证据/依赖 |
|---|---|---|
| 接管与旧入口审计 | completed（静态） | `v43_entrypoint_audit_20260914.md` |
| CPU 数据/worker 语义 | completed（已列测试范围） | P2为51、最小agent为58 passed；`results/v43/p2_semantic_gate.json` 指向原日志 |
| 32 origin 原始输入准备 | completed | 20 train/12 dev；future labels read=0 |
| 真实 TS-ICL/Bolt worker | completed（已验接口范围） | 两必需模型 ready/passed，真实 pilot 通过 |
| L512/H32 真实 pilot | completed（接口诊断） | 32 origins、64 插补、96 预测；独立复核通过 |
| A0 native KEEP / legacy forward fill | first_dev_tranche_completed | H96/H192首批dev三条件已运行；完整污染矩阵待扩展 |
| A1 PICS / v3.9 D | blocked_adapter | 旧771-parent重放依赖已审计，新区间可部署适配待完成 |
| A2 TS-ICL 单变量 | first_dev_tranche_completed | 首批已运行；整体改善但ETTm1退步 |
| A3 官方 covariates | first_dev_tranche_completed | 官方全部合法covariates已运行；首批整体差于native KEEP |
| A4 direct ridge 与全历史强版本 | first_dev_tranche_completed | 同split全部合法历史和context两个版本已运行 |
| A5 nested OOF residual / static eta | first_dev_tranche_completed_increment_not_established | 七类真实遮挡接线已运行；加入简单强候选集的oracle增量为0 |
| A9 oracle | available_arms_dev_upper_bound_completed | 仅已执行臂的完整任务标签；不把缺失A1/其他模型当0 |
| A6–A8 工具策略 | minimal_agent_dev_completed_RED | 19策略、train拟合/dev评价和7例在线完成；H2/H3未通过，完整风险/确认协议未完成 |
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


## 2026-09-14 21:20 post-hoc：P2首批真实实验完成

51项CPU测试通过，H96/H192、三个dev来源、26个基础parent/156变体，512次真实插补、580次去重预测、1092份任务标签全部完成，独立原始结果复核通过；耗时251.386秒，峰值GPU分配1.90GB。KEEP/A2/A5来源宏平均MASE为1.258454/1.157005/1.157187，无可靠确认性CI。A5仅4个ETTm1 parent产生8个修正变体，未来任务2好6坏；其真缺口重建6好2坏。加入A5后，相对已含简单跨通道强对照的oracle增量为0，不能晋升残差方法或进入更大A8训练。A1与原生多变量对照待适配，其他污染条件/来源尚未覆盖；calibration/test读取仍为0，PICS_joint_relabel不变。全部状态、误差分歧与成本见docs/v43_p2_report_20260914.md和docs/v43_p2_evidence_20260914.json。


## 2026-09-14 22:00用户新验收与A5遗漏候选诊断

用户明确将验收聚焦于因数据而异治理、合法证据的任务判别能力、主动获取相对固定流程的收益。TS-ICL的8.06%保留为基线收益，不归于agent；A5静态失败不能推断完整agent无效。优先级从补算子/A1转为现有固定候选池的最小agent对照，见docs/v43_agent_acceptance_20260914.md。附件第24节原文件当前不可见，本机第24节仅为本轮消息的明确要求摘要。

复用全部已有TS-ICL遮挡输出，为未选择的eta强度补92次真实Bolt预测（20.16秒，未新增future读取），50个受支持episode中发现26个变体/14个parent有静态规则错过的更优任务强度。相对固定五臂强候选池，全部eta的开发oracle仅从MASE1.094080降至1.093753，增量约0.000327；新增胜出变体ETTm1有4个、Solar有5个。此前“加入A5的oracle增量为0”仅适用于静态选择后的候选，不适用于所有eta。保留两种口径和原始失败，不将新oracle作为部署成绩。证据见docs/v43_a5_extended_diagnostic_20260914.json。

最小agent配置configs/v43/agent_minimal.yaml已冻结：110个train parent按时间拆75 scorer-fit / 35 acquisition-fit，dev维持26 parent。固定五臂初始池，strict_mask/history_probe两个验证工具，最多两轮；比较全体固定臂、train最佳固定、dirty简单选择、mask/history规则、全部证据、两种固定顺序及学习获取停止。同一浅层HGB模型族，source/uid/seed/真实缺陷类型/future不得进特征。费用计入基础候选、验证、选择、最终预测与分片加载/IPC，固定臂仅计实际所需候选；真实在线按需核验在离线评估后执行。尚未运行得出的agent结果均为pending，不作ICLR或晋升声明。


## 2026-09-14 最小 agent 开发验收：H1 有选择空间，H2/H3 未通过

已完成固定五臂、两个验证工具、19组策略：110 train parent按时间拆75动作评分/35工具获取，dev为26 parent/156变体。58项CPU gate、16,272份真实模型输出和2,964条决策/费用独立复核通过。五臂oracle MASE1.094080、train最佳固定TS-ICL1.157005、dirty简单选择1.165414、学习获取停止1.190112、全部调用1.204589；当前agent没有超越强固定/简单策略。173次实际工具步骤中156次任务误差不变、6次改善、11次恶化，mask证据未改变当前评分器动作，历史证据在Solar造成明显退步。

A5补全诊断证明100个非零eta候选均改变真实预测；相对静态有26个更优替代，其中20个为遗漏非零修正、6个应回eta0，不能全称作有效修正被拒绝。对强五臂池的oracle增量仅0.000327。A5新增92份预测、150标签及三种oracle池已独立复核；首次复核未解析旧预测alias而失败，修正映射后通过，保留失败。原P2“54个shared”纠正为52 shared + 2 USTS raw。

低预算学习和history-first各1/156变体超支，未删样本或截费用。初版在线过早加载离线标签档案、1例冷调用轨迹不同均保留；修正后文件访问屏障封锁6个evaluator/缓存档案，7例动作/证据/最终预测一致。完整在线进程24.661710秒，7请求摊销3.523101秒，含初始化/退出；137份在线模型输出与7条实际费用轨迹独立复核通过。批量0.4703秒的学习策略含最终预测费用不是冷在线成本。

PICS_joint_relabel不变；TS-ICL约8.06%是基线收益，非agent。calibration/test读取0；无ICLR/SOTA/安全保证。下一步只在train内注册证据状态独立评分、H32→H96/H192收益排序迁移、无增益工具停止和真实成本预算诊断，先满足H2/H3再扩强baseline/第二TSFM/独立确认。RED不写入DOCX已验证成果。

完整报告与代码证据：[v43_agent_report_20260914.md](v43_agent_report_20260914.md)，机器记录：[v43_agent_evidence_20260914.json](v43_agent_evidence_20260914.json)。原始run `results/v43/20260914T141030.324186Z-agent`；最新阶段状态 `results/v43/agent_stage_acceptance.json`。运行Git HEAD为c92eab5上的未提交工作区，先按内容hash冻结，随后9f5f49f保存了完全一致的代码；不以旧HEAD覆盖快照。
