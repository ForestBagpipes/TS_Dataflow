# IntroAct-TS v3.9: MIRAGE-TS — 预注册文档

预注册时间：2026-09-03（服务器日期），任何 v3.9 计算之前冻结。
状态：FROZEN。结果只能追加到 §11 post-hoc 区，不得改写 §0–§10。

## §0. 定位（不可变）

IntroAct-TS 是面向 TSFM 的数据治理 Agent：缺陷感知 → 候选治理动作 → 干预风险判断 → commit/abstain → 审计轨迹。v3.9 的插补模块只是 Agent 的一个动作族；最终评价仍是治理覆盖、下游 TSFM gain、条件危害、保护层误编辑和 OOD 安全。不得改成单纯插补论文、异常检测论文或新的通用 TSFM。本轮不做文献调研、不调用外部付费 API（API 预算 = 0；官方 checkpoint 下载不属于 API，但记录来源与 hash）。

## §1. v3.8 结论修正（口径纠正，不改红灯判定）

v3.8 红灯保持。追加精确说明：

- g1 = 76/177 = 0.429 是**窗口级有益覆盖**，不是执行动作的条件精度；
- 实际执行的 88 个 scattered 窗口中 76 B&S、12 harmful：**action-conditional B&S precision = 0.864，action-conditional CHR = 0.136**；
- 89 个 missing_block（gap 25–63）全部 abstain；
- 正确结论："**短缺口算子保留，长缺口适用性失败**"；不得写成整个 FACT 语义拆分无效。

自本轮起所有报告必须分开给出五个量：

1. proposal/applicability coverage；
2. action-conditional B&S precision；
3. action-conditional harmful rate / CHR；
4. beneficial coverage（bcov）；
5. abstention rate。

## §2. Phase 0：快速集成与目标缺口核算（10–15 min CPU，只读冻结结果）

回放臂（KEEP 占位保持 771 窗分母）：

- A. PICS_joint_relabel（incumbent）；
- B. PICS_non_IMPUTE；
- C. FACT_SHORT only；
- D. FACT_SHORT-first + PICS_non_IMPUTE；
- E. PICS_non_IMPUTE-first + FACT_SHORT；
- F. unrestricted oracle。

FACT_SHORT 定义：raw NaN run 长度 1–3；两侧有限锚点；线性插值；observed finite support 严格不变；raw NaN 优先于 materialize 后形态触发的 DESPIKE/DENOISE。

输出：PICS 151 commits 按 family/source/mask origin 分解；B 的 commits/B&S/harm/gain；FACT_SHORT 与 PICS 的重叠与 first-commit 冲突；D/E 完整指标；距正式目标所需新增 beneficial commits、可接受新增 harmful 上限、gain 缺口（target-label oracle 仅算 headroom，不进部署规则）。

输出文件：`results/v39_phase0_replay.json`、`results/v39_phase0_records.jsonl`、`results/v39_target_budget.json`、`results/v39_phase0_manifest.json`。

完整性门：incumbent 1e-9 内复现；771 窗分母固定（删动作必须 KEEP 占位）；v3.8 的 88/76/12 精确复现；两次独立进程输出 hash 一致。Phase 0 不因 D/E 未超 incumbent 而终止——目的在于算清长 block 模块的最小收益贡献。

## §3. Phase 1：长缺口 proposer 冻结探针（30–60 min）

新依赖放独立环境 `/root/autodl-tmp/envs/w2-v39-impute`，不得污染 `envs/w2`。

proposer 顺序：1. OpenFIM（ICLR 2025，正式优先）；2. TS-ICL（2026 预印本，安装与 checkpoint 可用才加入）；3. 现有 MOMENT reconstruction；4. linear/seasonal/forward-fill。模型权重只从官方仓库下载，记录 repository URL、commit/revision、checkpoint hash、license、体积。TS-ICL 安装失败则保留 OpenFIM 路线并如实报告失败原因，不得本地运行或改付费 API。

评估总体：89 个 gap length=25–63 的 missing_block 窗口。固定候选：KEEP/forward-fill、unrestricted explicit linear bridge、seasonal、current best IMPUTE、MOMENT reconstruction、OpenFIM、TS-ICL median、TS-ICL q10/q90（仅不确定性）、OpenFIM/TS-ICL 均值（二者都可用时）。

纪律：外部模型候选输出、hash、records 先冻结，再连接 clean/evaluation labels。所有候选只修改 raw NaN；observed-support drift=0；归一化只用 observed finite values；长度/时间索引严格对齐；不支持的窗口明确记 unsupported，禁止偷偷回退冒充模型输出。

报告：B&S、harmful、neutral、target-mask NRMSE、canonical gain、每 source、边界 seam、运行时间、显存。

候选 headroom 门（全部满足才进 Phase 2）：

- 至少一个新 proposer 在长 block 上 ≥15 个 B&S unique windows；或新 proposer union 相对当前 IMPUTE oracle 新增 ≥10 个 B&S；
- 短缺口＋长缺口＋PICS_non_IMPUTE 联合 oracle：bcov≥0.32、gain≥0.105、CHR=0；
- observed-support drift=0；
- ≥4/6 source 有有效输出。

联合 oracle 不达标 → 停止 selector 开发，登记"新 proposer 质量不足"。

输出：`results/v39_longgap_candidates.jsonl`、`results/v39_longgap_probe.json`、`results/v39_longgap_oracle.json`、`results/v39_model_manifest.json`。

## §4. Phase 2：BRIDGE 长缺口动作（仅 Phase 1 headroom 通过）

混合：z(j,η) = b + η·(m_j − b)，η ∈ {0, 0.25, 0.5, 0.75, 1.0}，只在 raw NaN mask 上混合。

部署可用风险信号（仅此五项）：

1. posterior_width：TS-ICL q90−q10，observed MAD 归一化；
2. cross_model_disagreement：OpenFIM 与 TS-ICL median 在 gap 上的归一化距离；
3. boundary_seam：缺口左右端点的值与一阶斜率不连续度；
4. bridge_deviation：FM proposal 相对 linear bridge 的归一化偏离；
5. unsupported/missing-view 标志。

禁止把 v3.4 shadow score 或 v3.5 prequential score 重新包装成主信号。主风险分数：各信号用训练 source 的 robust empirical CDF 归一化，R = max(width, disagreement, seam)。候选主输出：OpenFIM/TS-ICL 中央估计均值为 FM path；R 低保留大 η，R 高收缩至 linear；无可用 foundation imputer 时 KEEP。

阈值固定网格：risk quantile ∈ {0.2, 0.4, 0.6, 0.8} × η ∈ {0, 0.25, 0.5, 0.75, 1}。每个 LODO 折只用五个训练 source 选择满足校准 CHR 上界 ≤0.15 的最大覆盖工作点；held-out source 不参与归一化、选择或校准。

信号门：harmful AUROC≥0.70；AUPRC 相对 random prevalence 提升≥0.10；某 LODO 工作点在长 block 提交≥15 个；held-out CHR≤0.15；≥4/6 source 非劣；相对最佳单一 proposer，B&S 不降且 harmful 减少，或相同 harmful 下 B&S 增加。模型本身 harmful≤0.10 时仍需报告全部不确定性消融。

唯一条件分支：候选 oracle 通过但风险信号失败 → 训练轻量单调 logistic/isotonic risk head，输入仅五项新信号，source-group DRO，禁止 HGB/深网/旧 PICS 特征，只做一次预注册训练；仍失败则停止。

## §5. Phase 3：MIRAGE 集成

主策略固定：

```
if raw NaN exists:
    if all gap runs <= 3:  FACT_SHORT
    elif any gap run >= 25:  BRIDGE_LONG if risk gate passes else KEEP
    else:  KEEP
else:
    PICS over DENOISE/DESPIKE only
```

关闭：inherited IMPUTE、finite-flatline IMPUTE、RESEGMENT。

比较臂（编号固定，TS-ICL 不可用则该行写 unsupported，不得删除改号）：

1. KEEP；2. PICS_joint_relabel；3. PICS_non_IMPUTE；4. FACT_SHORT + PICS_non_IMPUTE；5. unrestricted long linear + FACT_SHORT + PICS_non_IMPUTE；6. OpenFIM direct + FACT_SHORT + PICS_non_IMPUTE；7. TS-ICL direct + FACT_SHORT + PICS_non_IMPUTE；8. MIRAGE w/o uncertainty shrinkage；9. **MIRAGE-TS 完整主臂（primary）**；10. unrestricted oracle。

协议：frozen 771-window evaluation frame；LODO 六折；first-commit；sample_uid 配对 bootstrap ≥10000；seed-313 OOD；先冻结策略输出再连接标签。

## §6. 两级成功标准

**v3.9-pre（已验证中间正向版本）**：bcov≥0.2727；gain≥0.0919；CHR<0.2053；pme≤0.0091；damage≤0.0402；risk-coverage 不被 PICS 支配；至少一项改善的 paired 95% CI 不跨 0；≥4/6 source 非劣；DENOISE/DESPIKE/IMPUTE 中至少两个 family 有真实提交。可登记"已验证中间正向版本"，不得称 SOTA。

**正式 v3.9**：bcov≥0.30；gain≥0.10；CHR≤0.10；CHR CP95 upper≤0.15；conditional mean loss≤0.10；pme≤0.0055；damage≤0.0402；synthetic/real OOD edit≤0.05；≥4/6 source 非劣；相对 PICS 严格 Pareto 改进且 bootstrap 支持。只有正式 v3.9 才允许申请 smoke350。

## §7. 结果回归代码（预注册义务）

全部 harmful commits 与 rejected beneficial 逐条台账：sample_uid、source、gap length、mask hash、proposer、η、posterior width、cross-model disagreement、seam、risk score、threshold、candidate outputs、first-commit action、before/after/gain/loss。

排查顺序：1. raw mask 是否 materialize 前保存；2. 时间索引/归一化/反归一化错位；3. FM 输出插回位置；4. observed finite 是否被修改；5. FIM/TS-ICL 是否在某些 source 方向反转；6. η shrinkage 是否实际生效；7. risk threshold 是否用了 held-out 信息；8. first-commit 是否被其他 family 抢占；9. 分母是否因无候选窗口被删除；10. 最后才归因模型跨域泛化。每个 aggregate 结论必须能回到具体 JSONL 行和函数。

## §8. 服务器与资源纪律

所有实验/统计/测试/模型下载/DOCX 生成渲染只在 `/root/autodl-tmp/work2`。本地只编辑、查看、同步。启动前检查 GPU/CPU/内存/磁盘/其他租户进程；有他人 GPU 任务时限制显存、不得抢占或终止他人进程；CPU 初始 n_jobs≤16，空闲后最多 24。长任务 setsid + 日志；每阶段结束清理本项目残留进程。预计：Phase 0 15 min；环境及下载 20–40 min；89 窗 foundation imputer 15–30 min GPU；BRIDGE probe 20–30 min；集成 20–30 min。

## §9. 文档与 DOCX

每阶段同步：`docs/v3_9_mirage_preregistration.md`、`docs/version_ledger.md`、`docs/diagnostic-playbook.md`、`docs/HANDOFF.md`、`docs/data_provenance_contract.md`；服务器与本地逐文件 sha256 一致。

DOCX：red 不更新；v3.9-pre 或正式 v3.9 才更新；母版 `docx/【work2】胡宏彬-进度文档-20260825.docx`；日期用服务器实际日期（2026-09-03 且无同日文件则新建 `docx/【work2】胡宏彬-进度文档-20260903.docx`，已存在则 -v02/-v03）；只改框架、方法、技术路线、创新点和已验证方法进展；不写红灯诊断流水账；服务器逐页渲染检查后同步本地并核对 hash。

## §10. smoke350

只有正式 v3.9 全部门过才允许申请；未过门不运行三 seed、不消耗 API。通过后先汇报门控表、paired bootstrap、OOD、harmful 台账，等用户确认再启动。

---

## §11. Post-hoc 结果区（逐阶段追加）

（待填。每阶段记录：结论、耗时、资源、结果文件 hash。）

### §11.1 Phase 0 post-hoc（2026-09-03，服务器 CPU，约 8.5 分钟墙钟，API 0，GPU 0）

**完整性门全部通过。** A 臂对冻结 v3.3 全字段逐域比较 max_abs_diff = 0.0；771 窗分母固定（KEEP 占位：B 69 个、C 594 个、D/E 69 个）；FACT_SHORT 与 v3.8 wide 精确等价（445 窗输出 hash 0 不匹配；88 填充 / 76 B&S / 12 harmful 精确复现——本语料 gap 长度只有 {1,2,3}∪{25..63}，cap 3 与 cap 16 认证同一批 run）；两次独立进程 digest 一致（`419b46b5454d2f…`）。`tests/test_v39_phase0.py` 12/12 passed。

**六臂五量表（数字以 `results/v39_phase0_replay.json` 为准）：**

| 臂 | proposal cov | B&S precision | act-cond CHR | bcov | abstention | gain | pme | damage | commits (B&S/harm) |
|---|---|---|---|---|---|---|---|---|---|
| A PICS_joint_relabel | 0.693 | 0.7947 | 0.2053 | 0.2727 | 0.804 | 0.0919 | 0.0091 | 0.0402 | 151 (120/31) |
| B PICS_non_IMPUTE | 0.576 | 0.8913 | 0.1087 | 0.0932 | 0.940 | 0.0864 | 0.0060 | 0.0065 | 46 (41/5) |
| C FACT_SHORT only | 0.230 (appl 0.114) | 0.8636 | 0.1364 | 0.1727 | 0.886 | 0.0003 | 0.0 | 0.0156 | 88 (76/12) |
| D FACT_SHORT-first | 0.751 | 0.8864 | 0.1136 | 0.2659 | 0.829 | 0.0872 | 0.0060 | 0.0195 | 132 (117/15) |
| E PICS_non_IMPUTE-first | 0.751 | 0.8712 | 0.1288 | 0.2614 | 0.829 | 0.0866 | 0.0060 | 0.0220 | 132 (115/17) |
| F unrestricted oracle | 1.0 | 1.0 | 0.0 | 0.6614 | 0.623 | 0.1969 | 0.0 | 0.0 | 291 (291/0) |

（执行子代理的口头汇总表中 damage 列有误，以结果 JSON 为准并已核对：A 0.0402 与冻结 incumbent 一致，D 0.0195、E 0.0220。差异已记录。）

**D vs E**：仅 2 个窗决策不同；两个冲突窗上 FACT_SHORT 的选取都是 B&S、PICS_non_IMPUTE 的选取都是 harmful → D 全胜（Δbcov +0.0045、ΔCHR −0.0152、harmful −2）。**D 为预算基线**（规则：bcov→gain→低 CHR）。B 的 46 个 commit 全部是 DESPIKE（DENOISE 在校准阈值下无提交）。

**PICS 151 commits 分解**：IMPUTE 106 + DESPIKE 45（无 DENOISE）；source：USTS 89、ETTm1 33、ETTh2 13、Oil 7、ETTh1 5、Crypto 4；IMPUTE commits 的 mask origin：raw_nan 87、finite_flatline 15、混合 4；harmful 31 = IMPUTE 27 + DESPIKE 4（harmful IMPUTE 中 20 个 mask 纯 raw_nan）。FACT_SHORT 88 个适用窗中 56 个与 A 的 commit 重叠（55 个是被退役的 inherited IMPUTE）。

**目标预算（`results/v39_target_budget.json`，基线 D，n_cont=440）：**

- bcov≥0.30 需 132/440 → 现有 117，**还需 15 个新 B&S 窗**；
- gain 缺口和 **5.632**（若全靠 15 个新 commit，平均每个需 gain≈0.375）；
- CHR≤0.10 **不能只靠添加**：零新增 harmful 时也需 18 个新 safe commits 稀释，或净削减 harmful；
- pme headroom **−1**（预算 1 次 protected edit，D 有 2 次）——必须移除 1 次 protected edit；
- damage 宽裕（headroom +15.99）；
- F oracle：bcov 0.6614 / gain 0.1969 / CHR 0 → 池子上限远高于正式目标，缺口在 selector/动作族。

**Phase 1 长 block 模块（89 窗）的最小贡献要求**：≥15 个新 B&S 窗且几乎零新增 harmful，并需连带化解 1 次 protected edit 与净 harmful 削减——这与 §3 headroom 门（≥15 B&S 窗、联合 oracle bcov≥0.32/gain≥0.105/CHR=0）一致。

**产物（sha256 前 16 位，本地与服务器一致）：**

- `experiments/v39_phase0_replay.py` — `fc50bfa98e87267b`
- `tests/test_v39_phase0.py` — `43c9eac6e090ebe4`
- `results/v39_phase0_replay.json` — `48e02de69f0538cd`
- `results/v39_phase0_records.jsonl`（4626 行 = 771 窗 × 6 臂）— `50b4606840f4c9db`
- `results/v39_target_budget.json` — `5ec5e719c2875c3c`
- `results/v39_phase0_manifest.json` — `b3354043fa094ab0`

### §11.2 Phase 1 中断断点（2026-09-03，服务器关机）

**状态：Phase 1 进行中中断，未出判定，可续跑。** 因用户关闭服务器而中止，非实验失败。

断点时已固化（本地与服务器 sha256 一致）：

- `experiments/v39_longgap_probe.py`（`a4839db7dc847526`）、`tests/test_v39_longgap_probe.py`（`0d7fa0eecf80ba05`）；
- 6 个 proposer 阶段的候选 records 与 stage 摘要：keep / linear_bridge / seasonal_existing / impute_default / impute_conservative / moment（MOMENT 已完成 GPU 推理）；
- 独立环境 `/root/autodl-tmp/envs/w2-v39-impute` 已创建（关机时仍有 torch/cudnn 依赖在 pip 安装，已随中断停止，续跑时先完成安装）；
- TS-ICL 官方 checkpoint 已下载并校验通过（`tsicl-v1.ckpt: OK`、`model.safetensors: OK`，见 `/tmp/v39_ckpt.log`），OpenFIM 状态待续跑确认；
- 已下载模型缓存在 `/root/autodl-tmp/work2/.cache/hf`（3.3GB，随数据盘保留）。

**标签纪律保持**：已冻结的候选输出均未连接 clean/evaluation labels；探针汇总（`v39_longgap_probe.json`）、oracle（`v39_longgap_oracle.json`）、model manifest（`v39_model_manifest.json`）尚未生成。续跑入口：恢复子代理 agent-13（Phase 1 任务上下文保留），或按 §3 从已冻结 candidates 续算。关机前本项目残留进程已清理（NO_RESIDUAL_V39_PROCS）。

### §11.3 Phase 1 post-hoc（2026-09-03，服务器，openfim CPU 52.5s / tsicl CUDA 17.5s（峰值显存 250MB）/ fm_mean 11.9s / moment（前序）25.2s / freeze+evaluate 14.2s，API 0）

**总判定：candidate_headroom_reached — 4/4 门全过，触发 Phase 2。**

断点校验：6 个已冻结候选文件与脚本 sha256 与 §11.2 记录全部一致。一处留痕的代码修复：`gen_openfim` 输入张量笔误（float64 且未上卡），修复为 float32+CPU 运行（`experiments/v39_longgap_probe.py:420-424`），脚本 hash `a4839db7…`→`2ba76450fd8488c0`，13/13 单测通过，probe 输出 code_hashes 已记录新 hash。

**模型获取明细（官方来源，API=0）：** OpenFIM fim-imp-pointwise-base（github.com/FIM4Science/OpenFIM + HF rev e00537a9…，code commit cee2bb53…，ckpt sha256 `390ba4c13f24e8f0`，80.9MB，MIT，89/89 supported）；TS-ICL tsicl-v1（pypi tsicl==0.2.1 + HF taharnbl/TS-ICL rev 19c94031…，ckpt sha256 `a67ae9f694c2a8`，219.2MB，TS-ICL Non-Commercial v1.0 学术研究允许，89/89）；MOMENT-1-large 对照（HF rev ca58581b…，1.39GB，MIT）。

**标签纪律核验：** freeze（801 条，digest `1d68297be8bbc7f2`）先于 evaluate；evaluate 从 fill_values 重放全部 output hash 零失败；observed-support drift=0.0（801 条最大）；237 条现有 IMPUTE 标签与冻结表 1e-9 一致；KEEP gain=0 断言通过；无 unsupported 回退。

**各 proposer 指标（89 窗总体，五量口径）：**

| proposer | app_cov | B&S prec | act-cond CHR | n_bs | n_harm | gain(app) | tm-NRMSE | seam_max |
|---|---|---|---|---|---|---|---|---|
| tsicl | 1.00 | 0.843 | 0.157 | 75 | 14 | 0.087 | 0.288 | 1.04 |
| linear_bridge | 1.00 | 0.775 | 0.213 | 69 | 19 | 0.056 | 0.593 | 0.11 |
| fm_mean | 1.00 | 0.640 | 0.360 | 57 | 32 | 0.062 | 0.570 | 6.61 |
| moment（对照） | 1.00 | 0.517 | 0.483 | 46 | 43 | 0.050 | 0.693 | 4.78 |
| openfim | 1.00 | 0.371 | 0.629 | 33 | 56 | −0.028 | 1.571 | 13.2 |
| seasonal_existing | 0.843 | 0.680 | 0.320 | 51 | 24 | 0.022 | 0.756 | 5.37 |
| keep | 0.00 | — | — | 0 | 0 | — | — | — |

**headroom 门：** G1 过（tsicl 75≥15；union 81 B&S，相对当前 IMPUTE oracle 69 新增 12≥10）；G2 过（771 窗联合 oracle bcov 0.5545≥0.32、gain 0.195≥0.105、CHR=0；commits 244：BRIDGE_LONG 81（tsicl 40/linear 21/moment 9/fm_mean 7/openfim 4）+ FACT_SHORT 76 + DESPIKE 46 + DENOISE 41）；G3 过（drift=0）；G4 过（6/6 source 有效输出，要求≥4）。

**关键机制事实（供 Phase 2/论文）：** OpenFIM 单独在长缺口不可用（CHR 0.629、负 gain、seam 13.2，Oil 0/7 全有害），但 union 仍贡献 4 个 oracle commit；TS-ICL 是最强单 proposer 但自身 CHR 0.157（14 harmful），部署不能无条件 commit——Phase 2 的 cross_model_disagreement 与 posterior_width 是区分其好坏窗口的关键信号；TS-ICL q90−q10 宽度 median 1.79，但 mean 被近零 MAD 窗口拉爆（max 1.4e12），posterior_width 归一化须用截尾/稳健口径。

**产物（sha256 前 16 位，本地与服务器一致）：** `results/v39_longgap_candidates.jsonl` `44a0327ecdd136b1`（801 条）、`v39_longgap_candidates_freeze.json` `8aaa9b223b01a1ca`、`v39_longgap_probe.json` `53cfd4908f959e44`、`v39_longgap_oracle.json` `f687d2c8bc4d1a49`、`v39_model_manifest.json` `a57cb5f05660fbf5`、新 stage cand_openfim/cand_tsicl/cand_fm_mean（`abd47af680b7aa43`/`b4e1ae6119bde10c`/`d5aae2eec4e98f6d`）。

### §11.4 Phase 2 post-hoc（2026-09-03，服务器 CPU-only：candidates 13.0s + freeze <1s + evaluate 14.1s，GPU 0，API 0）

**总判定：stop_signal_quality_insufficient — 信号门 2/6 过，预注册唯一条件分支（isotonic risk head + source-group DRO，仅训练一次）执行后仍失败，按 §4 停止规则终止，Phase 3 未进入。**

实现与完整性：`experiments/v39_bridge_probe.py`（`5cf79b919d26f37e`）三阶段 candidates→freeze→evaluate；z(j,η)=b+η·(m_j−b) 只在 raw NaN mask 上混合，1780 条逐条断言 drift=0；η=0/1 端点 output hash 与 Phase 1 逐窗精确相等；标签在 freeze 后同路径重放，η=1 的 B&S/harmful 集合与 Phase 1 逐集合精确相等（tsicl 75/14、openfim 33/56、fm_mean 57/32、moment 46/43、linear_bridge 69/19）；13/13 单测两端通过；候选混合 oracle 通过（83/89 窗存在 B&S 混合）。

**五信号判别力（LODO 归一化 AUROC / AUPRC，标签=η=1 commit 是否 harmful）关键事实：** 信号能预测 OpenFIM 的危害（boundary_seam AUROC 0.757），但**不能预测最强 proposer TS-ICL 的危害**（R AUROC 0.461，posterior_width 反向 0.325）——TS-ICL 的 14 个坏窗无法被任何部署可用信号分离。

**信号门逐项（最终/分支后口径）：** g1 harmful AUROC 0.616 <0.70 FAIL；g2 AUPRC lift 0.148 ≥0.10 PASS（prevalence 0.360）；g3 LODO 工作点 pooled 提交 70 ≥15 PASS；g4 held-out CHR 0.200（CP95 上界 0.295）>0.15 FAIL；g5 source 非劣 2/6（Crypto、Oil）<4 FAIL；g6 对 tsicl 的 Pareto 改进 FAIL（分支后 55 B&S/14 harm vs tsicl 75/14，B&S 下降）。校准事实：六个 LODO 折全部 no_calibrated_point——没有任何网格点在训练 source 上达到 CHR CP95 上界≤0.15。

**机制结论：** η 收缩对 tsicl 不减 harmful（η=0.5 与 η=1 同为 75/14，仅 gain 降）——失败不在混合算子而在信号质量；OpenFIM 的危害可预测但 OpenFIM 本身不可用（CHR 0.629），可预测危害的模型没有价值，有价值的模型的危害不可预测。

**产物（sha256 前 16 位，两端一致）：** `results/v39_bridge_candidates.jsonl`（1780 条）`b2fd2c15ffdea17f`、`v39_bridge_signals.jsonl` `46c4c48a3269fb63`、`v39_bridge_probe.json` `ef7b90222a4962c3`、`v39_bridge_manifest.json` `412ea15318d7b5e2`、`v39_bridge_freeze.json` `ae661bfcb5513a34`、`experiments/v39_bridge_probe.py` `5cf79b919d26f37e`、`tests/test_v39_bridge_probe.py` `25e93e4d895d6ce2`。

### §11.5 v3.9 总判定（post-hoc）

**红灯，诊断分支，不形成正式 v3.9（也未达 v3.9-pre）。** Phase 0 完成（D 臂基线与目标预算）；Phase 1 完成（长缺口候选 headroom 存在，联合 oracle bcov 0.5545/gain 0.195/CHR 0）；Phase 2 证明部署可用的不确定性/一致性信号不足以把 TS-ICL 的 CHR 0.157 压到 0.15 以下。不运行 smoke350，不调用 API，不更新 DOCX。正式 incumbent 仍为 PICS_joint_relabel（bcov 0.2727 / CHR 0.2053 / pme 0.0091 / gain 0.0919 / damage 0.0402）。仍开放的事实：长缺口价值在候选池中存在且体量充足（TS-ICL 75 B&S 窗），缺的是部署可得的逐窗风险证据；任何后续路线需要新的风险证据来源，而不是继续调阈值或换混合权重。
