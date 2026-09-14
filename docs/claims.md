> 2026-09-14 23:59 最终收口：共同表50个组合均已运行并独立复核；TimesFM固定五臂与TATO已完成，取代下文同步时的在途状态。全部三来源/26 dev parent/156变体，结果与费用以 [v431_sprint_report.md](v431_sprint_report.md) 为准。完整新agent未晋升，calibration/test封存。

> **2026-09-14 v4.3.1 当前主张边界。** 下文旧版本的正向结论不能转用于当前TSFM治理任务。本轮43本地策略与TATO/Bolt短预算适配已运行；普通同证据CART MASE1.136486、固定TS-ICL1.157005、新单步agent1.200158且全部STOP。该结果支持简单选择器具有开发价值，不支持证据细化或主动获取的额外贡献。TATO数值、成本和当前跨家族状态见[共同动态主表](v431_sprint_report.md)。TimesFM本条同步时仍在GPU队列，不能称已胜第二家族。22项新测试及原始输出、标签、分母、费用复核属于可信实现证据，不构成方法成功。确认集封存、PICS_joint_relabel不变；无SOTA、录用、正式安全保证或TSFM适配/文本大模型训练收益主张。并行调度替代旧H2/H3串行启动门槛，但不取消最终验收和冻结后确认。

> **2026-09-14 v4.3 当前边界。** 39项 CPU 契约测试通过、32个 train/dev origin 输入已校验，属于工程事实。真实 worker 和 pilot 尚待环境/模型就绪；没有 task gain、跨模型收益、适配收益、风险证书或 SOTA 证据。PICS_joint_relabel 保持历史 incumbent。TIME 原始日历和发布延迟未恢复，不宣称实时金融部署已通过 as-of 审计。详见 `v43_entrypoint_audit_20260914.md`。

# The claims, and the measurement behind each

> **2026-09-02 staleness notice.** This file predates the corrected damage
> definition and the v2/v3 line of experiments. Every number below that rests
> on the old centered `audit._nmse` or on v1's pre-correction damage is
> **stale** and must not be quoted without the reconciliation in
> `docs/version_ledger.md`. The training-dynamics triage claim is **blocked**
> (formal probe AUROC 0.5794, red). The v3-pre contextual shield is a
> **stopped candidate**: it failed its pre-registered gates, see
> `docs/v3_contextual_conformal_shield.md`.

Rewritten after the gating result. The previous version put our agent at the
centre; this one puts the acceptance layer there, because that is what the
evidence supports.

No `materials` directory exists in this repository, so terminology here is
drawn from the vocabulary already used across `src/introact_ts/` and `docs/`:
acceptance rule, execution time, structural distance, rollback, sandbox,
proposer, protected stratum, behavioural risk, statistical profile, model
utility. No new terms are coined and no borrowed method name appears.

## The one sentence claim

Acceptance of a data edit cannot rest on model utility alone, because utility
can be raised by flattening data as well as by repairing it. We give an
execution time acceptance rule that requires a utility improvement and
structural preservation together and rolls back on failure, and we show it is
independent of the proposing strategy: on a conservative statistical rule, on
an unconditional cleaner, and on our own search, it reduces damage to protected
data by roughly two orders of magnitude while retaining most of the repair.

## Contribution one, what the utility signal measures

Behavioural risk from a frozen forecaster measures predictability, not data
quality. It decomposes into two separable and roughly additive factors, level
positioning uncertainty at +0.203 and local shape unpredictability at +0.141,
established by a 2x2 with unit variance normalisation and a decisive pair that
holds local shape fixed, auc 0.716 at p 1.4e-07.

Consequences that were measured, not assumed:

- It fires on clean but structurally unpredictable windows. Four generators
  reproduce this independently at auc 0.705 to 0.760, and dropping the two
  whose structure resembles an injected defect leaves auc 0.715 at p 9.5e-13
  over 105 windows.
- It is silent on real cross domain windows, median -0.017 at auc 0.426, the
  calmest stratum in that corpus.
- It replicates across four frozen backends, weakest at p 1.3e-04.

Two candidate explanations were tested and refuted. Classical predictability
fails because white noise scores below the real data anchor and AR(0.95) scores
above AR(0.30). Structural familiarity fails because three of four
deterministic irregular forms score below the anchor.

## Contribution two, the acceptance layer and its independence of the proposer

This is the reordered claim. Source `docs/gating_modularity.md`.

The layer requires delta utility above epsilon, structural distance below tau,
and action risk below eta, applied to a sandbox copy with rollback on any
failure. It is placed around a proposer without modifying it.

| proposer | damage before | after | repair before | after |
|---|---|---|---|---|
| statistical rule | 0.0715 | 0.0016 | +0.366 | +0.255 |
| unconditional cleaner | 0.1919 | 0.0057 | -0.014 | **+0.044** |

The unconditional cleaner is the stronger case: it goes from net harmful to net
beneficial with no change to itself. Of its 1398 proposals, 725 were rejected
on structural distance against 452 on utility, so the structural term is the
principal gatekeeper.

**The gated statistical rule reaches damage 0.0016 against our full system at
0.0020.** A cruder proposer with the gate beats our own search on that axis.
This is the reason the claim is about the layer and not about our agent, and
our full system is presented as one instance of proposer plus gate.

## Contribution three, when the verification is worth its cost

Removing verification multiplies damage by 4.6 and doubles the edits for fifty
percent more repair. Peer calibration and abstention show no measurable effect
on this corpus and are reported as such. The structural threshold was selected
on a held out seed by a rule fixed in code before the numbers were seen, and
applied once: damage falls 75.2 percent for a repair cost of 0.012.

## What is deliberately not claimed

- Not that the method repairs better. `stat_only` repairs level shifts better
  at every contamination rate, up to +0.574 against +0.363.
- Not that behavioural signals beat statistical profiles at detection. They do
  not, except on defects with no local statistical trace.
- Not that the profile misfire generalises beyond our implementation. The
  detector cross check could not decide it, see `docs/detector_crossval.md`.
- Not that instance normalisation is the mechanism behind the level effect.
  That prediction was tested and refuted.

## Open, and honestly labelled

Downstream evidence that a gated corpus trains a better model is running and
unreported at the time of writing. AegisTS as a third proposer is blocked on a
missing module in its public repository. The pre registered prediction in
`docs/prediction_aegists.md` stands unverified and is not withdrawn.


2026-09-14 18:48 工程复核追加：修复残差PCA后附加缺失指示可能超过8维的问题，新增测试检查实际回归输入维度；最终CPU测试40项通过（0.96s），见 `logs/v43/contracts/20260914T104754.619288Z/`。旧39项日志保留；真实模型pilot仍待依赖，未产生方法晋升。


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
