# v4.3 Evidence Governance 设计与证据

## 冻结设计来源

本轮完整设计以 `new_server_execution_plan_20260914.md` 为准，本文不改写其算法或晋升条件。实施配置见 `configs/v43/bootstrap.yaml`。目标是保留原始时间、NaN 和未来读取边界，以真实 TSFM task gain 验证治理价值。PICS_joint_relabel 是历史 incumbent。

首个接口 pilot 固定 L512/H32、32 个不重叠 train/dev origins、seed101、通道0、target block `[230,281)`、batch1。TIME 使用同步 benchmark 行号，真实日历和发布延迟尚未恢复。Crypto 数量不足时只取3个，其余来源轮转补足；不制造重叠“独立”样本。上述实现选择在真实 future 标签读取前冻结。完整机制实验仍使用 H96/H192，后续抽样、信息轨道、训练与强对照须另行冻结。

## 2026-09-14 post-hoc：CPU 工程验收

已实现和测试的范围、旧入口归因、数据缺口、日志入口见 `v43_entrypoint_audit_20260914.md`。40 项 CPU 测试通过；数据输入准备完成。两个真实 worker 已写入但尚未由真实模型验收。pilot 因现有后台环境/模型准备未结束而 blocked_dependency。

没有 v4.3 方法成功、风险证书、适配收益或 SOTA 证据；A0–A5 未运行。进度 DOCX 的已验证研究成果不因接口代码和测试更新。


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
