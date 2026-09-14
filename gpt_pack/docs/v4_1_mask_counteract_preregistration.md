# IntroAct-TS v4.1: MASK-COUNTERACT — 预注册文档

Mask-Conditional Counterfactual Risk Control for TSFM Data Governance

预注册时间：2026-09-04（服务器日期 22:36 CST），任何 v4.1 计算之前冻结。
状态：FROZEN。结果只能追加到 §11 post-hoc 区，不得改写 §0–§10。

## §0. 方法定位（不可变）

IntroAct-TS 是面向 TSFM 的数据治理 Agent：感知缺陷 → 用统计或 TSFM/TS-ICL proposer 生成治理动作 → 在不知道 clean target 与 true_kind 的部署条件下对动作做反事实风险控制 → 只提交收益足够且满足伤害、保护层与 OOD 约束的动作 → 目标是在同一 benchmark 与评价口径下超过近期顶会 baseline。本轮不得改变任务方向，不得退化为普通插补模型或单纯异常检测模型。

## §1. 本轮出发点（v4.0 的既有事实，全部可复核）

- `results/v40_frozen89_decision.json`：stat_only 在冻结 89 上 harmful AUROC **0.877**，full_COUNTERACT **0.529**。
- 部署规则为 `harm < τ_h AND q10 > δ AND prot < τ_p` 的合取，primary 臂只提交 16/89，**72/89 被 `q10 > δ` 一项拒绝**。
- bank 的 missing_block 平均缺口约 **24.5%T**，冻结部署窗口约 **8.9%T**；TS-ICL 实际增益中位数相差约 3.6 倍。
- 因此 v4.0 的失败被归因为 **q10 收益尺度的 mask-severity 分布错配**，而不是 harmful 风险排序失效。
- **headroom（仅作可行性证据）**：在 `results/v40_frozen89_decision.json` 的 `arms.stat_only.frontier` 中，只扫 harm 阈值不加 q10 门时，τ=0.5027 处为 57 commits / 55 B&S / 2 harmful / CHR 0.0351 / CP95 0.1064；τ=0.5186 处为 63 commits / 61 B&S / 2 harmful / CHR 0.0317。**该点由冻结标签扫出，只能作为 headroom，严禁用于选择部署阈值。**

## §2. v4.1 方法定义

1. **Proposer 不变**：TSICL_LONG 继续作为长缺口动作生成器，候选复用 `results/v40_phase3_pool.*` 与 v3.9 冻结候选，不重新调用 TSFM。
2. **Harm controller 为主控**：stat-only harmful risk model 作为唯一硬安全门。**取消 `q10 > δ` 对 TSICL_LONG 的硬 veto。**
3. **收益解耦**：先由 harmful risk 得到安全候选集，再在安全集内部用 q50（预测收益中位数）排序择一。q10 仅作消融或 tie-break，不再承担硬 veto。
4. **Mask-conditional calibration**：阈值选择在与部署缺口区间匹配的校准总体上进行。
5. **校准总体**：从 21,000 episode / 168,000 records 中筛选 `gap_frac ∈ [0.05, 0.12]` 的 TSICL_LONG 适用记录，并按 mask 特征做密度比加权以匹配冻结候选的 gap-position/run/anchor 分布。
6. **阈值规则**：每个 held-out source 的阈值只由其余来源的校准数据确定。

### §2.1 部署可得 mask 特征（冻结清单）

仅由受损窗口自身与算子声明导出，禁止读取 clean、true_kind 或冻结集标签：

`missing_frac`、`gap_frac`（最长 NaN run / T）、`n_runs`、`gap_center_rel`（最长 run 中心位置 / T）、`left_anchor_frac`、`right_anchor_frac`、`anchor_both`、`side_mean_diff`（缺口两侧均值差 / scale）、`side_std_ratio`、`series_scale`、`support_ratio`。

### §2.2 密度比与有效样本量

以逻辑回归在上述 mask 特征上区分「校准候选」与「冻结候选」，取 `w = p_target/(1-p_target)` 截断到 [0.05, 20] 作为校准样本权重。**该步只使用冻结候选的无标签 mask 特征，不接触其任何标签。** 报告加权后的有效样本量 `ESS = (Σw)² / Σw²`。若 ESS < 200 则判定加权不可靠，回退到 §2 第 5 条的区间筛选（不加权），并如实记录。

## §3. Phase 0：完整性与 mask-shift 审计（15–20 min，CPU，API 0）

**复核项**：冻结 89 标签精确为 75 B&S / 14 harmful；stat-only 分数与 v4.0 逐行一致；§1 的 frontier 点（57 commits = 55 B&S + 2 harmful，CHR 0.0351）可复现；21k rescue bank 与 168k records 的 manifest 与 hash 一致。

**审计项**：对训练库、低缺口子集、冻结 89 三个总体，输出 `gap_frac` 分位数、`n_runs`、`gap_center_rel`、左右 anchor 覆盖、source 分布、support overlap、密度比分布与 ESS。

**声明**：**frozen89 自本轮起只作为开发决定集，不得再作为论文最终测试集。** 最终 confirmatory benchmark 须另建（见 §5）。

输出：`results/v41_integrity.json`、`results/v41_mask_shift_audit.json`。

**硬停止**：score 或标签不能精确复现；低缺口 calibration 子集样本不足（applicable 记录 < 500）；关键 mask 特征存在 target-only 信息泄漏。

## §4. Phase 1：选择器实验（20–40 min，优先 CPU）

复用 v4.0 stat-only checkpoint 与特征缓存做推断，不训练新的 neural critic。

**六个固定比较臂**

| 臂 | 定义 |
|---|---|
| A `v40_stat_q10_frozen` | v4.0 原始 stat-only + `q10 > δ` 硬门（原样复现） |
| B `harm_only_unmatched` | 同一 stat-only harm 分数，仅去掉 q10 硬门；阈值仍取自未匹配的原校准总体 |
| C `harm_only_mask_restricted` | harm 分数 + `gap_frac ∈ [0.05,0.12]` 区间筛选后的校准 |
| D `MASK_COUNTERACT_primary` | harm 分数 + mask-conditional 密度比加权校准；安全集内部按 q50 排序 |
| E `MASK_COUNTERACT_no_benefit_rank` | 同 D，去掉第二阶段收益排序（安全集内任取/按 harm 升序） |
| F `oracle_frontier` | 冻结标签扫出的上界，**仅作参照，不参与任何阈值选择** |

**阈值搜索**：在每个 LODO fold 的训练/验证来源数据内完成，网格 `τ_h ∈ {0.02,…,0.98}`；目标为最大化校准集 B&S coverage，约束 (i) conditional harmful rate 的 CP95 上界 ≤ 0.15，(ii) protected edit = 0。不得以 frozen89 的 55/2 点反推阈值，不得使用 target source identity 作为输入。

**Phase 1 决定门（冻结 89 一次性评估，全部为 AND）**

1. B&S retained ≥ 55/75；
2. harmful commits ≤ 3/14；
3. CHR ≤ 0.06；
4. CHR CP95 上界 ≤ 0.15；
5. protected edits = 0；
6. 至少 4/6 source 不劣于 v4.0 stat-only；
7. 相对 raw TSICL_LONG 与 v4.0 stat-only 形成严格 Pareto 改善；
8. 覆盖率不得只依赖某一个 source。

**未过门时的唯一分支判断（三选一，各只执行一次）**

- 若 mask-restricted calibration 已明显改善但样本不足 → 允许在 21k bank 的 5%–12% 子集上重训一次 stat-only risk model（可用 GPU，显存上限 35%）；
- 若排序 AUROC 仍高但阈值跨 source 失效 → 允许做一次 mask-density weighted calibration；
- 若排序 AUROC 与 frontier 同时消失 → 立即停止，登记诊断分支。

**禁止**当场搜索新的网络结构、随机种子与门槛。

## §5. Phase 2：集成 v4.1-pre（仅 Phase 1 过门后执行）

复用 `results/v40_phase3_pool.*`，禁止重新生成相同 TSFM 候选。集成逻辑：保留 v3.9 组合 D 的已验证动作；用 MASK_COUNTERACT 选择新增长缺口动作；first-commit 协议不变；受保护窗口使用冻结的结构性 veto；不得为改善指标改变标签定义、分母或样本总体。

**固定比较**：PICS_joint_relabel incumbent、v3.9 combination D、raw TSICL_LONG、v4.0 stat_only、v4.1 standalone、v4.1 integrated、oracle。

**v4.1-pre 正式门**：integrated CHR ≤ 0.10；CHR CP95 明显下降并完整报告；B&S coverage > v3.9 D；contaminated gain ≥ 0.10；damage ≤ 0.0195 且不得显著差于 v3.9 D；pme ≤ 0.0055；protected edits 相对 v3.9 D 至少减少 1；beneficial commits 相对 v3.9 D 至少增加 15；paired bootstrap 给出 coverage/gain 的 CI；risk–coverage frontier 严格改善；增益不得由单一数据集独占。

**预期不是结论**：v3.9 D 的 117 B&S / 15 harmful 叠加约 55/2，理论上约 172 B&S / 17 harmful、CHR≈0.09。此为预期，**不得写成实验结论**。

**过门后才进行**：登记 v4.1-pre → 正式 OOD 压力测试 → 再决定是否 smoke350 → 另建全新 untouched confirmatory benchmark（新 corruption seed、新父窗口、尽可能增加外部公开来源，frozen89 不作最终测试集）。后续正式比较须至少包含 PICS、TS-ICL、TATO、SHoTClean 及适用的数据修复/插补 baseline，且在相同数据、缺陷、预算、first-commit 与指标口径下比较。

## §6. 结果必须回归代码

任何 FAIL 或异常数字依次核查：sample_uid / manifest / checkpoint hash → mask 特征计算位置 → calibration split 与 LODO source → density ratio 与 ESS → threshold 是否只用 calibration 标签 → q10 gate 是否已按设计移除 → first-commit 与 KEEP 逻辑 → harmful commits 逐条回放 → source/family/mask-severity 分层 → 绑定到具体文件、函数与行号。**禁止只用「模型泛化差」「数据不足」作结论。**

## §7. 服务器与资源纪律

所有计算只在 `/root/autodl-tmp/work2`；本地只编辑、查看、同步。启动前检查 GPU/显存/CPU/内存/磁盘与他人进程；不杀、不停、不抢占。优先复用已有 score、checkpoint、pool 与 168k 记录。Phase 0/1 优先 CPU，只有低缺口 stat-only 重训分支使用 GPU，显存上限约为可用显存的 35%。API 调用默认 0。每阶段结束清理本项目残留进程并报告资源使用。

## §8. 文档与 DOCX

同步 `docs/v4_1_mask_counteract_preregistration.md`、`docs/version_ledger.md`、`docs/diagnostic-playbook.md`、`docs/HANDOFF.md`、`docs/data_provenance_contract.md`；预注册区与 post-hoc 区分离，执行后不得回改门槛。

DOCX：RED 或诊断结果不更新；只有 Phase 2 过门并形成 v4.1-pre 才更新，以 `docx/` 中最新进度文档为基础，日期用 2026-09-04，不覆盖已有文件，同日新建 `-v02`/`-v03`，同日期旧版本必须保留；只修改框架、方法、技术路线、创新点与已验证方法进展；生成、渲染与逐页检查在服务器执行，完成后同步本地并核对 sha256。

## §9. 提升纪律

v4.1 只有严格超过 incumbent / v3.9 D 才能成为正式版本；未过门只登记诊断分支；不得用改指标、改总体、改标签或事后选门槛制造提升；每一项提升必须能回溯到 sample_uid、原始记录、代码与哈希；没有正向改进时不运行 smoke350、不更新 DOCX。

## §10. 最终汇报格式

总门控；mask-shift 审计；各臂 B&S/harm/CHR/CP95/coverage/gain/damage/pme；LODO/source/family/mask 分层；risk–coverage 与 paired bootstrap；harmful commit 逐条代码归因；OOD（若触发）；资源/API；代码、结果、文档路径；本地—服务器 sha256；DOCX 是否触发；smoke350 是否允许；残留进程与关机状态。

---

## §11. Post-hoc 结果区（逐阶段追加）

（待填。每阶段记录：结论、耗时、资源、结果文件 hash。）

### §11.1 Phase 0 结果（2026-09-04，通过）

**完整性**（`results/v41_integrity.json`）：`all_pass=true`。冻结 89 标签精确复现 75 B&S / 14 harmful；stat-only harm AUROC 重算 0.8771 与 v4.0 逐位一致；§1 引用的 headroom 点复现为 57 commits / 55 B&S / 2 harmful / CHR 0.0351 / CP95 0.1064。

**实现更正（我的读库错误，非预注册问题）**：审计初版从 4,200 episode 的 pilot bank 取校准总体，其 TSICL_LONG 仅 649 行，in-band 219 行 < 500，触发硬停止。预注册 §2.5 指定的总体是 21,000 episode 的 rescue bank；改读后 applicable 候选 3,153 条，逐行复核 dirty 与 candidate 哈希全部通过。

**mask-shift 审计**（`results/v41_mask_shift_audit.json`）：

| | bank 全体 (3,153) | in-band (1,043) | frozen89 (89) |
|---|---|---|---|
| gap_frac p10/p50/p90 | 0.068 / **0.221** / 0.455 | 0.057 / 0.084 / 0.111 | 0.057 / **0.090** / 0.118 |
| missing_frac p50 | 0.227 | 0.086 | 0.090 |
| support_ratio p50 | 0.773 | 0.914 | 0.910 |
| gap_center_rel p50 | 0.495 | 0.497 | 0.549 |
| left_anchor_frac p50 | 0.332 | 0.434 | 0.506 |
| side_mean_diff p50 | 1.088 | 0.940 | 1.073 |

in-band 子集在缺口尺度上与部署域基本重合（0.084 vs 0.090），全体 bank 高出约 2.5 倍，v4.0 的 q10 尺度失配由此定量确认。残余差异集中在 anchor 长度与缺口位置。密度比：ESS **958.1**（≥200，可靠），可分性 AUROC 0.612，权重截断 [0.05, 20]。in-band 占全体 33.1%，三个总体的 `n_runs` 中位数均为 1、`anchor_both` 覆盖率均为 1.0。**声明：frozen89 自本轮起只作开发决定集，不再作为论文最终测试集。**

耗时约 3 分钟，纯 CPU，API 0。

### §11.2 Phase 1 结果（2026-09-04，决定门 **未通过**，3/8）

`results/v41_selector_arms.json`、`results/v41_selector_rows.jsonl`。阈值全部只在各折的训练来源上选取，未使用 frozen89 标签。

| 臂 | commits | B&S/75 | harmful/14 | CHR | CHR CP95 |
|---|---|---|---|---|---|
| A `v40_stat_q10_frozen` | 14 | 14 | 0 | 0.0000 | 0.1926 |
| B `harm_only_unmatched` | 25 | **24** | 1 | 0.0400 | 0.1761 |
| C `harm_only_mask_restricted` | 13 | 12 | 1 | 0.0769 | 0.3163 |
| D `MASK_COUNTERACT_primary` | 13 | 12 | 1 | 0.0769 | 0.3163 |
| E `no_benefit_rank` | 13 | 12 | 1 | 0.0769 | 0.3163 |
| F `oracle_frontier`（仅上界） | 63 | 61 | 2 | 0.0317 | — |

A 精确复现 v4.0（14/14/0），构成本轮的回放校验。**E 在冻结 89 上与 D 完全相同，因为每个窗口只有一个 TSICL_LONG 候选，安全集内部没有可排序对象；该消融只有在 Phase 2 集成中才会激活。**

**门控**：g1 B&S≥55 **FAIL**（12）；g2 harmful≤3 PASS（1）；g3 CHR≤0.06 **FAIL**（0.0769）；g4 CP95≤0.15 **FAIL**（0.3163）；g5 protected edits=0 PASS；g6 ≥4/6 source 不劣 **FAIL**（3）；g7 严格 Pareto **FAIL**（两个参照分居任何风险受控工作点的两侧，单点几何上无法同时严格支配，已在输出中注明）；g8 非单一来源 PASS（最大来源占 B&S 的 50%）。

**paired bootstrap**（D vs v4.0 stat_only，每窗口效用 ±1）：mean −0.0337，CI95 [−0.1461, 0.0787]，P(>0)=0.255 —— 主臂相对 v4.0 **没有改善**。

**回归代码的归因（§6 逐项，已排除后才下结论）**

已核对：sample_uid 与 manifest 一致、30 个 checkpoint 的 sha256 逐个复核、mask 特征由 `v41_mask_counteract.py::mask_features` 单一实现同时作用于两个总体、calibration split 按 LODO source 排除、密度比与 ESS 已报告、阈值只用校准标签、`q10` 门已按设计移除（arm B/C/D 的 `evaluate_on_frozen89(use_q10=False)`）、first-commit 与 KEEP 逻辑未改。

定位到的绑定约束是**校准总体上的排序质量，而非阈值传递**：

| fold | in-band 校准量 | harmful 率 | in-band harm AUROC | 可达最小 CHR CP95 |
|---|---|---|---|---|
| ETTh1 | 853 | 0.2356 | 0.7083 | 0.1300 |
| ETTh2 | 884 | 0.2195 | 0.6851 | 0.1427 |
| ETTm1 | 855 | 0.2234 | 0.6940 | **0.1514** |
| Crypto | 872 | 0.2064 | 0.6877 | 0.1490 |
| US Term Structure | 863 | 0.2039 | **0.6590** | **0.1538** |
| Oil Price | 888 | 0.2117 | 0.6756 | **0.1544** |

三折（ETTm1、USTS、Oil Price）的可达最小 CP95 上界本身就 >0.15，因此 `calibrate_tau` 结构性地返回 `no_calibrated_point`，这三折在冻结 89 上提交 0 个；而它们恰好持有 75 个 B&S 中的 **51 个**。这是主臂只拿到 12 的直接原因，代码位置 `v41_mask_counteract.py::calibrate_tau` 的 `cp <= CHR_CALIB_UPPER` 分支与 `stage_select` 中 `tau_C/tau_D` 为 None 时的跳过逻辑。

**该差距不是小样本噪声。** frozen89 上 AUROC 0.8771 的 bootstrap CI95 为 **[0.7647, 0.9640]**，P(AUROC≤0.71)=0.004，其下界仍显著高于校准总体的 0.659–0.708。同时两个总体的 harmful 率不同（0.157 vs 0.217）。因此结论是：**把校准总体的缺口几何对齐到部署域是必要的，但不充分——对齐后的总体在 harm 可分性上仍系统性更难，mask 特征所刻画的几何相似并不蕴含风险可分性相似。**

**分支判定**：§4 的三个分支中，与实测条件相符的是分支二（决定集上排序仍高、阈值跨 source 失效），其预注册补救即 mask-density weighted calibration，已作为主臂 D 执行完毕，六折得到的阈值与未加权的 C 完全相同，无改善。分支一的前置条件（样本不足）**不成立**（各折 853–888 条、ESS≈780），因此不得据其重训。据 §4 与 §9，**本轮到此停止，登记诊断分支，不再训练更大的 critic、不搜索结构与种子。**

**唯一的正向发现**：arm B 表明 v4.0 的机制诊断是对的——仅移除 `q10 > δ` 硬门、其余不变，即把保留的 B&S 从 14 提升到 24、harmful 仅 1、CHR 0.040。它同样未过门（24 < 55，CP95 0.176 > 0.15），但方向明确，且不依赖任何新的校准总体。

耗时约 6 分钟（审计 3 + 选择器 3），纯 CPU，API 0。GPU 全程未使用；期间服务器上有他人任务（`run_esa_panorama.py` / `run_epc_panorama.py`，4 进程共 18.3 GB 显存），未杀、未停、未抢占。

**Phase 2 未执行**（§5 要求 Phase 1 过门）。**不触发 DOCX**（RED/诊断）。**不允许 smoke350**。incumbent 仍为 PICS_joint_relabel。
