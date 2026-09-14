# IntroAct-TS v3.8: FACT-IntroAct — 预注册文档

**Factual-defect and Ambiguity-aware Candidate Triage（事实缺陷与歧义缺陷感知的候选分诊）**

- 创建日期：2026-09-03
- 状态：PLANNED（预注册冻结后才允许开始计算）
- **§0–§10 预注册区**；**§11 起为 post-hoc 区**。不得因结果不好临时更换 primary、改门槛或无限网格搜索。

---

## §0. 定位（不可变）

IntroAct-TS 是面向 TSFM 的数据治理 Agent，闭环必须保留：感知数据状态 → 提出治理动作 → 判断动作后果与风险 → commit/abstain → 保存可审计轨迹。不是普通插补器或异常检测器。最终目标：相同基准和协议下超过最近顶会 baseline，形成可投 ICLR 的方法。本轮不做文献调研。

## §1. v3.7 结论纠正（本轮先行义务）

v3.7 只证明**冻结 PAIR 分数 + 全局阈值 + 专家凸组合**的可提取上限不足，不能写成"整个候选池 oracle 上限 bcov 0.18/gain 0.02"。v3.3 的 unrestricted `oracle_relabel` 为 bcov 0.6591、gain 0.1969、CHR 0、damage 0、pme 0。

Phase 0 必须在服务器精确回放（1e-9 容差）三者并逐 sample_uid 对齐解释两个 oracle 的候选集合、可用标签和约束差异：
1. v3.3 unrestricted candidate oracle；
2. v3.7 frozen-score constrained oracle；
3. PICS_joint_relabel incumbent。

复现失败 → 立即停止方法实验，先修完整性。

文档修正文案（version_ledger / playbook Tree 25 / HANDOFF）：
**"冻结 PAIR 排序/校准路线被排除；尚未排除重新定义候选语义和构造可识别高精度候选。"** 此步只是纠错，不更新 DOCX。

## §2. 方法定义

1. **事实缺陷层**：actual NaN 是部署时直接可见的事实缺陷。新建实验态算子 IMPUTE_EXPLICIT：touched mask 只能是原始输入的 `~isfinite(x)`；不得把有限 flatline、自然平台或推断冻结段加入 mask；不得修改任何原本 finite 的观测值。
2. **歧义缺陷层**：finite flatline、level shift、noise、spike 是解释性缺陷。DENOISE/DESPIKE 暂保留 PICS 判断；finite flatline 不再进入普通 IMPUTE；RESEGMENT 继续关闭；无充分证据 KEEP/abstain。
3. **证书层**（IMPUTE_EXPLICIT）：原始窗口至少一个 NaN；缺失段两侧均有有限锚点才允许插值；输出全部 finite；observed-support drift 严格为 0；touched mask 与 raw NaN mask 完全一致；不得用 clean/true_kind/held-out 标签做部署决策。

原始 NaN 信息必须从 raw corpus 保留，**不得使用 materialize_for_probe 后的 missing_fraction**（forward-fill 可能已擦除 NaN）。每条候选增加：`raw_nan_mask_hash`、`raw_nan_fraction`、`finite_flatline_mask_hash`、`mask_origin`、`gap_runs`、`anchor_geometry`。

## §3. Phase 0：候选与标签语义审计（15–20 min CPU）

从 raw corpus 重建所有 IMPUTE 候选，互斥分层：actual_nan_only / finite_flatline_only / mixed / neither/other。每层报告：candidate 数与 unique window 数；source、true corruption、rung、operator mode 分布；b&s rate；harmful rate；mean/median gain 与 loss；candidate oracle 的 bcov/gain；v3.6 harmful commits 落在哪层。

回归代码：`actions.py::missing_mask`、`actions.py::op_impute`、`experiments/corpus.py` 污染注入、`probe.py::materialize_for_probe`、v3.3 标签构建路径、PICS first-commit 逻辑。

必答四问：(1) missing_mask 候选中实际 NaN 与有限 flatline 各占多少；(2) v3.6 的 23 条 harmful IMPUTE 分层分布；(3) unrestricted oracle 的主要增益来自哪些 family/source/mask_origin；(4) PICS harmful IMPUTE 是否主要由 mask 语义混合导致。

输出：`results/v38_oracle_replay.json`、`results/v38_impute_mask_audit.json`、`results/v38_impute_mask_records.jsonl`、`results/v38_phase0_manifest.json`。

**Phase 0 完整性门**：v3.3 oracle、v3.7 constrained oracle、PICS incumbent 均精确复现；1599 个 sample_uid 与输入 hash 一致；非 IMPUTE 候选输出无漂移；raw mask 两次独立进程构建 hash 一致。

## §4. Phase 1：显式缺失算子探针（20–40 min，只在 experiments/ 原型，不改正式 src）

比较：A. 当前 IMPUTE 输出；B. materialized KEEP/forward-fill；C. IMPUTE_EXPLICIT_LINEAR；D. IMPUTE_EXPLICIT 紧/中/宽三档 gap 证书（tight ≤4、medium ≤8、wide ≤16）；E. oracle candidate choice（仅上限）。

主算子固定线性插值。边界缺失、单侧无锚点、超长 gap 默认 abstain。不得看到 held-out 结果后修改三档。

新增诊断指标（只解释机制，不替换 canonical gain/damage/CHR/pme）：missing-support NMSE/NRMSE、observed-support drift、seam jump、filled fraction、downstream TSFM gain。

**算子集成门**：actual-NaN 窗口 b&s rate ≥0.80；harmful rate ≤0.10；observed-support drift=0；≥30 个 beneficial unique windows；≥4/6 source 方向不劣；加入现有池后 unrestricted oracle 达到 bcov≥0.30、gain≥0.10、CHR≤0.10、pme≤0.0055、damage≤0.0402。

候选级 headroom 不达标 → 不调 selector，直接转 Phase 2B adapter；达标 → Phase 2A 集成。

## §5. Phase 2A：FACT 集成臂（20–40 min；仅 Phase 1 过算子门）

冻结协议：LODO 六折、first-commit、sample_uid 配对 bootstrap（≥10000）。

比较臂：1. PICS_joint_relabel；2. PICS_non_impute_only；3. 当前 PICS 全部动作；4. FACT_explicit_only；5. **FACT + PICS 的 DENOISE/DESPIKE（正式主臂）**；6. FACT + 当前 IMPUTE（消融，证明语义拆分必要性）；7. unrestricted oracle。

主臂规则：inherited IMPUTE commit 全部关闭；actual NaN 只允许 IMPUTE_EXPLICIT；finite flatline 不得进入 IMPUTE_EXPLICIT；DENOISE/DESPIKE 走原 PICS；RESEGMENT 关闭。

**黄灯（最低正向条件）**：相对 PICS 严格 Pareto 改进；paired bootstrap 显示 bcov/gain 提升或 CHR 下降至少一项 95% CI 不跨 0；其余 headline 不显著退化；≥4/6 source 非劣；至少覆盖两个 action family。

**正式绿灯（全部满足）**：bcov ≥0.30；gain ≥0.10；CHR ≤0.10；CHR 置信上界 ≤0.15；conditional mean loss ≤0.10；pme ≤0.0055；damage ≤0.0402；synthetic OOD edit ≤0.05；real OOD edit ≤0.05；≥4/6 source 非劣；paired bootstrap 支持相对 PICS 的严格 Pareto 改进。

**红灯**：无 Pareto 改进 → 停止 FACT selector 调参，不运行 smoke350。

## §6. Phase 2B：Support-Local TSFM Residual Adapter（仅当显式线性算子有覆盖潜力但精度不足；45–90 min）

新 proposer/operator，不再增加冻结 verifier 视图。约束：冻结 MOMENT/现有 TSFM encoder，不微调基础模型；只训练轻量 residual MLP 或小型 TCN；输入=冻结 TSFM representation + raw mask + gap geometry + 局部锚点统计；输出 correction 只作用于 raw NaN support，observed support 上乘 mask 保证严格为 0；训练只用五个训练 source，held-out source 标签完全不可见；目标=missing-support Huber loss + seam/slope penalty + TSFM representation consistency；只允许 η={0.5, 0.75, 1.0} 三个固定 blend rung；不超过一次预注册超参数选择。

与 linear、当前 IMPUTE、v3.5 TSFM_RECONSTRUCT_IMPUTE 比较。adapter 集成门：b&s rate 相对 linear +≥0.10 或 missing-support error 降 ≥10%；harmful rate 不高于 linear；≥4/6 source 同方向；oracle union 新增 bcov 或 gain ≥0.03；observed-support drift=0。未过门立即淘汰，不用阈值补救。

## §7. 结果回归代码（预注册义务）

主臂每条 harmful commit 逐条台账：sample_uid、source、true corruption（仅审计）、proposed family、mask_origin、gap_runs、operator mode、PICS scores、certificate result、before/after、gain、loss、first-commit order。归因顺序：raw NaN provenance 丢失 → mask 混入 finite flatline → operator 修改 observed support → 标签/materialize 路径不一致 → certificate 误放行 → PICS non-IMPUTE 覆盖 explicit action → LODO/first-commit 实现错误 → 剩余才归跨 source 泛化。所有 aggregate 结论必须能回到 sample_uid 记录和具体代码路径。

## §8. 服务器与 API 纪律

只在 /root/autodl-tmp/work2 执行；本地只编辑/查看/同步，不运行实验或统计脚本。开始前检查 nvidia-smi、CPU/内存、磁盘、本项目及他租户进程。GPU 空闲时 adapter 阶段可用 RTX 5090；有他人任务则限显存并发。CPU 初始 n_jobs≤16，最多 24。每阶段结束清理残留进程。外部 API 预算 0。

## §9. 文档与 DOCX

每阶段同步五个文档；本地与服务器逐文件 sha256。DOCX：纯计划/纠错/红灯不更新；yellow（统计显著 Pareto 改进）或正式 green 才更新；基于 docx/ 最新进度文档生成新文件不覆盖旧的；日期用服务器实际日期，同日用 -v02/-v03；只改框架/方法/技术路线/创新点/已验证进展；服务器生成并逐页渲染检查后同步本地并核 hash；yellow 只能写"已验证的中间正向结果"，不得写成正式 SOTA。

## §10. smoke350

只有正式 v3.8 全部门控通过才允许申请；未过门不运行三 seed、不消耗 API。通过后先汇报门控表、paired bootstrap、OOD、harmful 台账，等用户确认再启动。

---

## §11. Post-hoc 结果区（逐阶段追加）

（每阶段记录：结论、耗时、资源、结果文件 hash。以下内容为结果产生后追加，不改动 §0–§10 的预注册部分。）

### §11.1 Phase 0 post-hoc（2026-09-03，服务器 CPU，150.1 s，API 0）

**完整性门：全部通过。** 三个 oracle 回放逐 sample_uid 对齐、全部 bit-exact（max abs diff = 0.0），1599 个 sample_uid 与输入 hash 一致；非 IMPUTE 候选无漂移；raw mask 两次独立进程构建 hash 一致。

**两类 oracle 纠正结果（§1 义务完成）：**

| 回放臂 | bcov | gain | CHR | damage | pme | commits |
|---|---|---|---|---|---|---|
| R1 v3.3 unrestricted oracle | 0.6591 | 0.1969 | 0 | 0 | 0 | 290 |
| R2a v3.7 oracle_target_threshold_global | 0.0409 | — | 受约束 | — | — | 18 |
| R2b v3.7 oracle_target_expert_mixture | 0.1795 | — | 受约束 | — | — | 83 |
| R3 PICS_joint_relabel incumbent | 0.2727 | 0.0919 | 0.2053 | 0.0402 | 0.0091 | 151 |

- oracle 总 gain mass 86.65；v3.7 global 未捕获 81.1%，mixture 未捕获 80.9%。
- 结论（纠错文案）：R1 与 R2 的 0.6591 vs 0.04/0.18 差距是"冻结 PAIR 排序 + 仅让标签调阈值/专家权重"这条路线的上限，不是候选池上限。**冻结 PAIR 排序/校准路线被排除；尚未排除重新定义候选语义和构造可识别高精度候选。**

**IMPUTE mask 分层审计（1154 个 IMPUTE 候选，互斥四层）：**

| 层 | 候选数 | unique 窗 | B&S rate | harmful rate | mean gain | 层内 oracle bcov / gain |
|---|---|---|---|---|---|---|
| actual_nan_only | 447 | 149 | 0.812 | 0.188 | +0.0202 | 0.8456 / 0.0281 |
| finite_flatline_only | 623 | 268 | 0.218 | 0.782 | −0.0960 | 0.4874 / 0.0292 |
| mixed | 84 | 28 | 0.381 | 0.607 | −0.0653 | 0.6786 / 0.0614 |
| neither | 0 | 0 | — | — | — | — |

**四个审计问题的答案：**

1. 候选来源：`missing_mask`（`src/introact_ts/actions.py:82-119`，NaN 在 line 99，frozen-run 检测 100-119，`MIN_FLATLINE_RUN=16` line 25）把实际 NaN 与有限 flatline 混入同一 IMPUTE 候选空间；`op_impute`（`actions.py:262-329`）不加区分地填充。actual-NaN 层 447 候选、flatline 层 623 候选、mixed 84。
2. v3.6 的 23 条 harmful IMPUTE：16 条 finite_flatline_only、4 条 mixed、仅 3 条 actual_nan_only（mask_origin：16 finite_flatline / 7 raw_nan）。**v3.6 PAIR 臂的 IMPUTE 危害主要由 mask 语义混合导致。**
3. unrestricted oracle 的 gain mass 按 family：DENOISE 41.6%、DESPIKE 47.6%、IMPUTE 10.8%（203 commits 但 gain 份额最小）；按 source 以 US Term Structure 最大。oracle 的主要增益在 DENOISE/DESPIKE，IMPUTE 的贡献是覆盖而非增益。
4. PICS 的 27 条 harmful IMPUTE：**19 条在 actual_nan_only 层**（missing_block 12 + missing_scattered 13），4 mixed、4 flatline；仅 7/27 的 touched mask 超出 raw NaN，4/27 所在窗口完全没有 raw NaN。**PICS 的 IMPUTE 危害不是主要由 mask 混合导致——"填了真 NaN 仍有害"是 PICS 路线的主要失败语义，与 v3.6 臂不同。** 这直接支撑 FACT 的语义拆分：显式 NaN 层用证书算子（IMPUTE 层内 B&S 率 0.812、层内 oracle bcov 0.8456，是可识别高精度候选的候选空间），flatline 层退出 IMPUTE。

**materialize 擦除证据：** 531 个候选 raw 序列含 NaN，materialize_for_probe 后全部 1154 个候选的 materialized 序列 NaN 数为 0；530 个 touched mask 在 materialized 序列上不一致，275 个 raw-NaN 候选被完全擦除。证实 raw NaN provenance 必须从 raw corpus 保留，不能使用 materialized missing_fraction。

**产物（sha256 前 16 位，本地与服务器一致）：**

- `results/v38_oracle_replay.json` — `21d2126adde772dd`
- `results/v38_impute_mask_audit.json` — `a2b2586bfb84ef8e`
- `results/v38_impute_mask_records.jsonl` — `6d1a56c1986d0d92`
- `results/v38_phase0_manifest.json` — `ea0c46c7bbdf5025`

### §11.2 Phase 1 post-hoc（2026-09-03，服务器 CPU，主运行 85.6 s，API 0）

**总判定：operator_retired — 算子淘汰，Phase 2A/2B 均未进入，v3.8 红灯，登记为诊断分支。**

完整性前置门全部通过：Phase 0 replay pass=True；1599 窗 manifest hash 校验 pass；touched mask mismatch = 0；两进程 records digest sha256 相同（`4e9839b2…`）；`tests/test_v38_explicit_impute.py` 11/11 passed（mask 逐位=raw NaN、observed 逐值不变、drift 严格 0、边界/无锚点/超长 abstain、4/8/16 档边界、abstain 输出=materialized KEEP、与 v33_labels 对拍逐键相等）。

**六门逐项（主变体 = wide 档；门 1/2/4/5 群体 = 177 个 actual-NaN 窗口 = actual_nan_only 149 + mixed 28）：**

| 门 | 规则 | 数值 | 结果 |
|---|---|---|---|
| g1 | actual-NaN b&s ≥0.80 | 0.4294 (76/177) | FAIL |
| g2 | harmful ≤0.10 | 0.0678 (12/177) | PASS |
| g3 | observed-support drift=0（全部 1335 个 EXPLICIT 候选） | max drift 0.0 | PASS |
| g4 | beneficial unique windows ≥30 | 76 | PASS |
| g5 | ≥4/6 source 非劣（候选级 bs_wide≥bs_IMPUTE 且 harm_wide≤harm_IMPUTE） | 0/6 | FAIL |
| g6 | FACT 池 unrestricted oracle 达标 | bcov 0.3705 / gain 0.1760 / CHR 0 / pme 0 / damage 0 | PASS |

g5 的"方向不劣"在看到结果前固定为严格 AND 规则，保持不变。post-hoc 敏感性记录（非门变更）：宽松 OR 规则下 g5 为 6/6——harmful 在 6/6 source 改善，b&s 在 0/6 不劣。

**五臂对比（445 个有 IMPUTE 候选窗口；bcov/gain 为 296 个 contaminated 窗上的窗级 oracle）：**

| 臂 | n候选 | b&s | harmful | mean gain | bcov | oracle gain |
|---|---|---|---|---|---|---|
| A 当前 IMPUTE | 1154 | 0.460 | 0.539 | −0.0487 | 0.686 | 0.0317 |
| B materialized KEEP | 445 | 0 | 0 | 0 | 0 | 0 |
| C EXPLICIT_LINEAR（=wide） | 445 | 0.171 | 0.027 | +0.0003 | 0.257 | 0.00057 |
| D tight/medium/wide | 445×3 | 0.171 | 0.027 | +0.0003 | 0.257 | 0.00057 |
| E oracle（A∪C∪D，上限） | 2934 | — | — | — | 0.689 | 0.0317 |

**关键机制事实：**

- 三档数值完全相同：语料 gap 长度分布只有 {1,2,3}（scattered，1126 段）与 {25…63}（block，89 段，`experiments/corpus.py:107` 注入 25–63），5–16 区间没有任何 gap，证书分档退化为单档。
- 失败是覆盖而非精度：missing_block 89 窗全部因 overlong_gap abstain；在算子实际填充的 missing_scattered 88 窗上 b&s=0.864 / harm=0.136 / mean gain +0.0015。abstain 原因：overlong_gap×89、no_raw_nan×268（flatline 层，符合设计）、full_fill×88；boundary/one_sided/no_anchor 均为 0。
- E 相对 A 只多覆盖 1 窗（204 vs 203）：EXPLICIT 在短内部 gap 上与 linear IMPUTE 逐值相同，其价值全在安全性（harmful 0.539→0.027）。
- FACT 池构成：1046 条非 IMPUTE 现有候选 + 531 条 EXPLICIT + 192 条 KEEP 占位（只有 IMPUTE 候选的窗口作为 no-commit 留在冻结的 771 窗分母内——修正了一处分母 bug，修正前后 bcov 0.449→0.370；门阈未动，两次运行 g6 均 PASS，verdict 不变）。oracle 163 commits：IMPUTE_EXPLICIT 76 / DESPIKE 46 / DENOISE 41。对照 xcheck：同一代码路径在原始池复现冻结 v3.3 oracle（bcov 0.6591 / gain 0.1969 / CHR=pme=damage=0），1e-9 内全过。
- 诊断指标（不进 canonical）：missing-support NMSE 0.670→0.645（KEEP→wide）；seam jump mean 0.088 / max 1.974；filled fraction 0.497；downstream TSFM gain 子集（judge-only chronos-bolt-base，21 窗）mean −0.0074，38% 为正——冻结 judge 平均不奖励这些填充。

**决策树执行：** g1（0.429 < 0.80，差距巨大）与 g5（0/6）失败 → 不满足 §5 "仅 Phase 1 过算子门"的 Phase 2A 前提。Phase 2B 触发条件"有覆盖潜力但精度不足"不满足：执行规范在见结果前冻结的定量覆盖潜力规则为 wide b&s ≥0.60 且 harmful ≤0.25，实际 b&s=0.429——缺口在覆盖（超长 block 全 abstain），不在精度（填充窗口 b&s 0.864），adapter 救的是精度，不覆盖该缺口；且 §4 禁止在看到 held-out 结果后修改三档。按冻结规则：算子淘汰，两条后续路径均不进入。

**产物（sha256 前 16 位，本地与服务器一致）：**

- `experiments/v38_explicit_impute_probe.py` — `94815dfb643d654c`
- `tests/test_v38_explicit_impute.py` — `7bdc488cdc11a5b4`
- `results/v38_explicit_impute_records.jsonl`（1780 条）— `78e733696298352b`
- `results/v38_explicit_impute_probe.json` — `99b6ddba4da7eec5`

### §11.3 v3.8 总判定（post-hoc）

**红灯，诊断分支，不形成正式 v3.8。** Phase 0 完成 v3.7 纠错义务（三类回放 bit-exact）并给出 mask 语义分层事实；Phase 1 证明证书算子可以买到安全（drift=0、harmful 0.068）但买不到覆盖（block 注入长度 25–63 全部超出 wide 档）。不运行 smoke350，不调用 API，不更新 DOCX。正式 incumbent 仍为 PICS_joint_relabel（bcov 0.2727 / CHR 0.2053 / pme 0.0091 / gain 0.0919 / damage 0.0402）。仍开放的路线：候选池有价值（unrestricted oracle bcov 0.6591），证书算子安全但缺乏长 gap 覆盖——任何 rescue 需要新的预注册长 gap proposer，而不是事后调档。
