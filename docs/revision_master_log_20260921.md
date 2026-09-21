# IntroAct-TS 论文修订总记录（2026-09-21）

执行依据：作者完整修订执行任务书（本轮）。目标稿件 `latex/IntroActTS_20260921_v52.tex`（2291 行，基线可编译）。
服务器：`ssh introact`（223.109.239.30:25220，vipuser，密钥），项目 `/home/vipuser/work/work2`，A100-40GB 空闲，磁盘 103G 可用。
状态枚举：TODO / RUNNING / VERIFIED / BLOCKED / UNFINISHED。

## 阶段 0 版本关系（已确认）

- 本地 git：HEAD=29833b7（codex/introactts-paper-v45-review 分支），含 v52 文稿修订；v52 实验脚本与 docs 为未跟踪文件。
- 服务器 git：HEAD=e78f206（v52 消融修正实验），有未提交修改（src/introact_ts/v44/*、v46/grid.py）——**保留，不覆盖**。
- 两边历史已分叉，不执行合并/强推；按 AGENTS.md 约定暂停自动同步属预期。
- 方法代码：`src/introact_ts/v47_verified/select.py`（选择器/选参/统计）、`v44/state.py`（22 维状态）、`v44/matching.py`。
- 冻结配置：`configs/v47-verified/protocol.json`；冻结选参 `results/v47/protocol/selection_{bolt,timesfm,chronos2}.json`（bolt 128/0.5、timesfm 32/1.64、chronos2 16/0.5）。
- 结果：`results/v47/`（主评估）、`results/v52_ablation/`（A2 机制消融+门控对照，服务器与本地一致）。
- 已有披露：TEST 参与过前期开发，当前评估为 post-hoc；独立确认（E-001）无合格新数据资源。

## 任务登记

| 编号 | 问题位置 | 内容 | 证据来源 | 是否改预测 | 是否重算 | 状态 |
|---|---|---|---|---|---|---|
| R1 | §4.6/Table 2、app:ablation | Full-22 vs Compact-17 训练侧（各自选 k,β）一次收口比较 | results/v53_state_compact/（scripts/v53_state_compact.py，服务器运行，全 exit=0） | 否（缓存离线） | 是（选择器重算） | VERIFIED：**收口 FAIL，保留 Full-22**。Compact 自选 (64,.5)/(16,.5)/(64,.5)；train_eval 上 timesfm 显著退化（p=0.024，HL 0.011→0.035）、bolt HL 上升、chronos2 显著改善 → 混合权衡，按预登记规则保留 Full-22。tex §4.6 与 app:v53 已写入。偏差记录：冻结选参实际由 introact_ts.v47 模块产出（锚=bank 平均效用最高动作、LOPO 用 bank 全局标准化），与 v47_verified 语义有差异，v53 全批用 v47 保持一致 |
| R2 | §4.4、app:v53 | 诊断A补全：R2-CART 原始/阈值匹配（θ=.590/.658/.617）、Best Fixed 随机 KEEP | results/v53_state_compact/gate_controls2_*.json | 否 | 是（离线） | VERIFIED：FULL 对 BF-Random 三骨干全部显著（p≤0.0014，"收益来自选择而非频率"）；对 R2-CART-M 仅 bolt 显著。已入 §4.4 与 tab:v53-gates |
| R3 | §4.5、app:v53 | 诊断B：来源级固定策略、留一来源敏感性 | results/v53_state_compact/source_fixed_*.json | 否 | 是（离线） | VERIFIED：SOURCE_FIXED 在 bolt(+0.0181,p=.0022)/timesfm(+0.0269,p=.017) 显著优于 FULL；对 BF/R2 的优势集中于 Exchange（留出后归零或反转）；对 KEEP/TATO 广谱。已入 §4.5 与 tab:v53-source-fixed/tab:v53-loso，摘要/引言/结论同步收窄 |
| R4 | §3.4 harm cap 回退 | 无可行配置时的分支审计与措辞修正 | select.py:413-507 + 9 份选参记录（harmcap_audit.json） | 否 | 否 | VERIFIED：生产 v47 模块回退 max-β 且不复核 cap（不能称"约束保证"）；v47_verified 抛错拒绝冻结；全部 9 份选参记录该分支从未触发；tex §3.4 已如实描述两者并给出 KEEP 保底提案（scripts/v53_harmcap_proposal.py，未改库） |
| R20 | tab:app-calls / tab:app-repro | "no fit" 表述改为"无参数效用模型，标准化统计与 (k,β) 由训练侧程序确定" | select.py + 任务书 | 否 | 否 | VERIFIED（tex 两处已改） |
| R21 | tests/v47_verified/ | 最小测试集合补齐：无正分KEEP、非法动作不选、决策确定性、打分不改 bank、完整输入只 KEEP、调用计数恒等 | 新增 test_deployment_contracts.py，本地+服务器 18 项全过 | 否 | 否 | VERIFIED |
| R22 | tab:app-repro 硬件行 | 记录运行时为 RTX 4090（2026-09-14 交接文档），当前服务器已换 A100；新计时不能与旧数字混口径 | REMOTE_CODEX_HANDOFF.md:61 vs nvidia-smi | — | — | VERIFIED（保留 4090 表述，新计时需单独标注） |
| R5 | Table 41（tab:app-efficiency） | SAITS/TATO 延迟雷同：确认两行均为骨干调用计时宏平均，方法侧服务耗时未测；IntroAct 行为合成口径 | cost_audit、status.json（agent-2 核查） | 否 | 否 | VERIFIED（表注+正文已改如实标注；cold start 改为实测 3.7–7.3 s） |
| R6 | §3.2/A.4/Table 11 | 邻域距离-误差单调性 | transfer_test_*.json 与表逐位一致，v52 文本已是非单调表述 | 否 | 否 | VERIFIED（无需改动） |
| R7 | E.3/Table 40 | H=96 vs 双horizon | R-002 修复已落实 | 否 | 否 | VERIFIED |
| R8 | Table 34/46 | T34 整表 Bolt-only 未声明；T46 宏平均数值配单骨干计数 | reconstruction_test_bolt.json、evaluation（agent-2） | 否 | 否 | VERIFIED（caption 与 §4.2 已声明口径） |
| R9 | Table 13 | bootstrap/Holm 一致性 | select.py:351-408 与 test_*.json 逐位一致 | 否 | 否 | VERIFIED（无需改动） |
| R10 | Table 6 | X^a−X^{a_0} 缺失位置 nan_to_num→0，四个幅度特征恒为 0（L-003） | v44/state.py:197-228 | 否 | 否 | VERIFIED（附录 A.2 已补准确描述） |
| R11 | §3.1 | KEEP 各骨干缺失处理：Bolt/Chronos-2 原生 NaN 掩码，TimesFM 官方插值+前缀剥离 | 适配器与 status.json | 否 | 否 | VERIFIED（§3.1 已补骨干级说明） |
| R12 | A.3.1/A.5.1 | 缺失率：实际为 bankx 枚举三级 severity，哈希抽样属未使用的 v44 bank 块 | grid.py:53-70 | 否 | 否 | VERIFIED（A.5.1 已改写） |
| R13 | Table 1/29/30-32 | 排名口径：逐 episode 竞争排名、1e-12 容差、NaN 逐 episode 剔除 | 服务器 v47_evaluate.py | 否 | 否 | VERIFIED（Table 1/29/31/32 caption 已统一口径） |
| R14 | P0-3 | SAITS 交叉拟合：真 out-of-fold、2 折交错分配、fit 于 bankx | scripts/v47_saits.py、report_*.json | 否 | 否 | VERIFIED（"两半"措辞已改为交错折） |
| R15 | 全文 | 文稿写作修订 | 本记录+各核查结果 | — | — | VERIFIED（摘要/引言/§3.1/§3.4/§4.2–4.6/结论/附录 A.2/A.3/A.5、app:scope、app:v52、新增 app:v53 已改；编译无错误、无未定义引用） |
| R16 | 全文 | 主张-证据对应表 | docs/claim_evidence_map_20260921.md | — | — | VERIFIED |
| R17 | app:calls | 分项计时补齐 | results/v53_state_compact/latency_audit.json | 否 | 否 | UNFINISHED（骨干调用与检索开销有记录；候选构造仅阶段级、端到端每请求延迟缺失，插桩重放超出本轮窗口；tex 已如实标注合成口径） |
| R18 | 服务器 | 磁盘冗余清理 | 服务器检查 2026-09-21 | — | — | VERIFIED（无安全可删项：旧结果按规则保留，/tmp 与 conda 缓存无可清理项，103G 可用） |
| R23 | app:splits | 数据用途说明补入辅助块（test30/50/m2/m3）与未使用块（bank/bankx2） | grid.py + p0_audit §11 | 否 | 否 | VERIFIED（tex 已补） |
| R24 | app:v52 结尾 | L-003 运行级影响由 v53 精简状态比较覆盖；独立确认与 parent 聚合检索仍为未决项 | v53 结果 | 否 | 是 | VERIFIED（结尾段已更新） |
| R19 | E-001 独立确认 | 无合格新数据窗口 → 如实报告缺少独立确认 | v52 报告 §5 | — | — | VERIFIED（确认为不可行，保留披露） |

## 收口规则（预先登记，来自任务书）

- 若 Compact-17 在统一训练侧比较（train_eval，各自选参）降低总体 MASE、不增加总体有害损失、无明显骨干退化 → 推荐采用精简版并相应修订论文。
- 若存在明显权衡 → 保留 Full-22，删除干预特征必要性强主张。
- 原 TEST 上 A2 结果只作为提出候选的动机，不作为选择依据；该方向受旧评估启发需如实记录。
- 方法变更在隔离分支交付，作者审阅，不自动合并。

## 第二轮：全文结构重写与附录重组（2026-09-21 晚，作者规划执行）

执行依据：作者"论文修订执行"规划（段落职责→反向提纲→方法→实验→引言→相关工作→结论→摘要→附录的写作顺序；三次连贯性通读；逐句依赖审计）。本轮不改任何数值、不新增实验、不生成新图。

| 编号 | 问题位置 | 内容 | 证据来源 | 是否改预测 | 是否重算 | 状态 |
|---|---|---|---|---|---|---|
| R25 | 全文 | 段落清点与反向提纲 | docs/logic_inventory.md、docs/logic_outline.md | — | — | VERIFIED |
| R26 | §1/§2/§5/摘要 | 引言重写为 6 段（场景→已有工作→困难→方法信息流→三层贡献→评估边界）；相关工作三小节内部重排（TATO 叙述连续、KEEP≠拒绝回答、结尾引向 §3）；结论压缩为四步逻辑；摘要按 A1–A8 重写（删除 Compact 选参史、逐项消融与门控机制归因，预测/风险优势分别限定比较对象） | 作者规划 | 否 | 否 | VERIFIED |
| R27 | §3 | M11 骨干适配器细节移附录 B；M22 先用途后定义；M24 诊断结果移出；M31 补四个恒零干预坐标注记；M41 删除"零分=证据不可区分"的无据解释；M42 分离记录行为与规范注记、删段末 TEST 披露；状态定义移入正式公式环境（修 eq:state 引用返回小节号的 CRITICAL） | coherence_pass_report | 否 | 否 | VERIFIED |
| R28 | §4 | 重组为 7 小节：4.1 Evaluation Protocol（删"separate implementation verification"内部状态句；对照各自检验的问题）；4.2 结尾架桥；4.3 Forecasting Performance（迁入来源固定策略+留一来源，结尾引出干预问题）；4.4 四段（默认工作点→机制问题与三类对照区分→结果→准确率-损害权衡；harmful loss/HIR 补定义）；4.5 Effects of Utility Estimation and State Representation（A2-M/A2-F 改名消除同名冲突；固定配置消融与重新选参表示比较分段）；4.6 Sensitivity（严重度+历史支持三类检查，声明非独立泛化）；4.7 Deployment Cost（只答"增加哪些计算"，不报延迟分位数） | 作者规划 | 否 | 否 | VERIFIED |
| R29 | 附录 | 按问题重组为 A Evaluation Protocol / B Method and Implementation Details / C Forecasting Results / D Intervention Frequency and Harm / E Estimation and State Analyses / F Sensitivity Analyses / G Cost and Reproducibility；app:v52/app:v53 节解散、内容迁入 D/E/C/F，表 label 保留，附录地图重写；新标签 app:source-diagnostics/app:gate-controls/app:matched-partners/app:compact-selection/app:estimation-analyses | 作者规划+子代理执行（约 30 块移动） | 否 | 否 | VERIFIED |
| R30 | 全文 | 三次连贯性通读+逐句依赖审计：docs/sentence_logic_audit.csv（248 句）、docs/coherence_pass_report.md；1 CRITICAL+3 MAJOR+8 MINOR 全部修复闭环（见报告末尾） | 子代理审计+主代理修复 | 否 | 否 | VERIFIED |
| R31 | 编译核验 | latexmk 零错误、零未定义引用、38 页；PDF 已刷新至 latex/ 顶层 | build 日志 | — | — | VERIFIED |

未解决登记（保持不变）：E-001 独立确认无合格数据（BLOCKED，保留披露）；R17 端到端每请求延迟未实测（UNFINISHED，tex 已如实标注合成口径）；留一来源全行见附录 C 表注与结果文件。
