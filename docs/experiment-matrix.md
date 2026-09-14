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

# Experiment matrix, frozen

Frozen 2026-08-24 for the ICLR submission. Four tables: baselines, metrics,
experiment groups, ablation rungs. Anything not in these tables does not go in
the paper, and anything in them that cannot be produced is reported as not
applicable with a reason rather than dropped.

Two numbering registers exist and neither retires the other. **L** numbers
baselines, below. **B** numbers work items and appears in `docs/CHANGELOG.md`,
where B4 is the forced candidate injection change and not a baseline.

## Table 1, baselines

| id | method | venue | family | status |
|---|---|---|---|---|
| L0 | no action | reference | none | runs |
| L1 | SCREEN | SIGMOD 2015 | repair | runs |
| L2 | IMR | VLDB 2017 | repair | runs |
| L3 | MTCSC | PACMMOD 2(6), 2024, presented at SIGMOD 2025 | repair | runs |
| L4 | Data-OOB | ICML 2023 | valuation | runs |
| L5 | TimeInf | ICLR 2025 | valuation | runs |
| L6 | LTSV | DASFAA 2026 | valuation | runs |
| L7 | Learn2Clean | WWW 2019 | learning | runs |
| L8 | TSRating | ICLR 2026 | valuation | **not applicable** |

Plus the upper reference `oracle`, which knows the clean series and is a bound
rather than a method.

**Three changes from the previous list, each with its reason.**

`no_shield` leaves the baseline list. It alters one component of this paper's
method rather than being an independently published work, so it belongs with the
ablation ladder and with experiment two's contrast. Carrying it as a baseline
overstated the count.

**L7 Learn2Clean is new and it is the arm the paper's central claim is measured
against.** Q learning selects operators, the reward is a downstream metric, and
the selected operator is applied immediately with no sandbox and no shield. It is
ported to this paper's seven operators so that the two differ by mechanism rather
than by vocabulary. Its reward is the reduction in distance to the clean
reference, which is an oracle signal it would not have in deployment, given
deliberately: a baseline weakened by a poor reward proves nothing.

**L8 TSRating carries a row and no numbers.** Rechecked 2026-08-24. The
repository was last pushed 2025-05-27, has zero releases and ships no weight
file, and its README states the annotations were not uploaded. The rater is a
distillation of LLM pairwise judgments and has no existence without them, so the
judgments have to be generated. Three backend configurations were tried:

| configuration | order flip rate | unscorable rate |
|---|---|---|
| deepseek-v4-pro, reasoning off | 0.508 | 0.000 |
| deepseek-v4-pro, reasoning on | 0.000 | 0.333 |
| deepseek-v4-flash, reasoning off | 0.833 | 0.000 |

The middle row is not a pass. Its zero is survivorship bias, the unscorable
generations are the ones whose reasoning hit the token ceiling and those are the
harder pairs. Position bias is therefore a property of this API family on this
task rather than of one model. The table note carries all three.

## Table 2, metrics

Five, and the two the budget mechanism needs.

| metric | definition | change |
|---|---|---|
| downstream error | PatchTST and DLinear on the prepared corpus, **reported per stratum across the four layers** | was a corpus mean, which diluted differences that live in one layer |
| repair accuracy | root mean square distance to the clean reference on the injected layer | was repair gain, a ratio; the repair family's home ground is a distance |
| protected mis edit **rate** | edits in the protected layers divided by the protected layer total | was a count, which cannot be read across corpus sizes |
| damage rate | harmful commits over committed edits, harm = `max(worse_binary, discard_share)` (counts discarded data) | changed 2026-08-30; old Definition 1 value is in `docs/version_ledger.md` as `v1-old (obsolete)` |
| compute cost | seconds and accelerator occupancy to prepare the corpus | unchanged |
| probes saved | probes avoided by skipping settled windows | reported only beside the next row |
| missed windows | of those skipped, how many carried a defect | never omitted |

## Table 3, experiment groups

| group | content | baselines |
|---|---|---|
| main | all rows, corpus protocol | all |
| one, criterion validity | three sub tables: signal failure, soft penalty sweep, target damage rate attainment | all |
| two, structural safety of exploration | cumulative damage against interaction count, sweeping the exploration coefficient, verifying theorem 4 | all as reference rows |
| three, policy learning gain | four arms, random, fixed rule, learned, oracle policy | all |
| ablation and sensitivity | this paper's variants only | none |

## Table 4, ablation rungs

Six, with the full method as the reference row rather than a rung.

| id | rung | what it removes |
|---|---|---|
| A1 | no shield | all three acceptance conditions |
| A2 | no structural condition | the model independent half of the conjunction |
| A3 | raw utility as reward | the shield's role as a reward shaper |
| A4 | no conformal calibration | the threshold is a hand set constant instead |
| A5 | no policy learning | back to the fixed rule |
| A6 | no candidate injection | the policy can only reorder what the proposer offers |

Three rungs of the earlier eight are gone and the reasons are measured rather
than budgetary. Removing the utility condition left an acceptance set close to no
shield at all, since it vetoed 769 candidates against the structural condition's
616. Budget allocation's effect already appears in the main table's cost column
and its two probe columns. Peer calibration showed no detectable difference in
discriminative power against global standardisation in an earlier measurement,
which stays in section 6.1.

`f_single_step` and `g_no_abstain` are removed outright. Neither appears in
section 4.2 and neither isolates a component the method claims.


### 2026-09-14 执行结果回填

本轮三项任务已经执行并独立复核，结果为H1选择空间存在、当前H2/H3未成立。19策略及7例真实在线、完整费用、A5遗漏强度和保留失败见[v43_agent_report_20260914.md](v43_agent_report_20260914.md)。未进入独立确认，不推进方法晋升；下一步train内机制诊断先行。


## 2026-09-15 v4.3.1-r2 实际交付；r3接续开发

r2保留旧STOP负结果并实现证据状态一致固定参照：Bolt 1.157005；TimesFM 1.069398，与固定mask CART相同，主动机制未成立。主表34行、26 DEV parent/156变体；train110 parent，75拟合/17检查/18获取，支持曲线18/37/75已完成。真实TimesFM补3504唯一预测，648同冻结终态价值标签、4992决策及费用独立复核通过。

两家族真实在线结束：TimesFM自然7窗中6次mask，Bolt自然7窗全STOP，另有预算与失败受控分支。金融已核实Brent报价和Kim–Wright拟合远期利率，2 parent/12相关变体的18行附表已完成；完整观测40次输入/预测no-op一致。金融TimesFM 4.890237仍等固定取证，Bolt 3.069683未胜KEEP。附表按观测事件计H，与旧网格不可横比；自然缺口身份/严格PIT未解决，未来部分重叠旧DEV/pilot，非确认。

报告：[r2报告](v431_r2_report.md)、[共同表](v431_r2_main_table.md)、[逐窗审计](v431_r2_stop_audit.md)、[独立复核](v431_r2_verification.md)、[金融身份](v431_r2_financial_audit.md)。incumbent不变，calibration/test封存；RED不写入DOCX已验证成果。新用户r3已授权长短上下文响应与任务收益映射，尚未产生r3成绩，见其预登记计划。
