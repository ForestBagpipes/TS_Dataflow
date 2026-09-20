# IntroAct-TS v52 消融修正实验报告（2026-09-21 凌晨）

执行背景：`docs/IntroActTS_v51_tool_review_20260920.md`（Finding E-002/E-003/R-002）与
`docs/IntroActTS_v51_independent_review_and_plan_20260920.md`（规划 E0–E6）。
本轮只做实验修正与重算，未修改论文文稿。所有新结果在 `results/v52_ablation/`，
未覆盖 `results/v47/`、`results/v47_verified/` 的任何文件。

## 1. A2 消融的正当性修正（E-002 / 规划 E4）

### 问题

v51 表2 的 A2（`use_intervention=False`）只从检索键删去 5 维 intervention 特征，
仍保留同动作邻域的局部效用估计。它没有消融论文标题级贡献"逐请求、逐动作的
action-conditioned 局部效用检索"这一机制本身，且报告值（mean MASE 1.4185）反而
优于 FULL（1.4366），使消融梯子不支持核心贡献。

### 修正设计（A2_WO_ACTION_COND）

机制级消融：邻域在**全部非参考动作上合并检索**（动作盲），状态为动作无关的
17 维（mask+context+forecast），局部加权效用不再按候选动作区分；动作间仅靠
bank 全局平均效用先验区分：

`s_i(a) = μ_w(i) + (ḡ_a − ḡ_all) − β·σ_w(i)/√n_eff(i)`

使用与各骨干**冻结相同的 (k, β)**（bolt 128/0.5，timesfm 32/1.64，chronos2 16/0.5），
新变体无任何搜索或调参。原 A2 行以相同语义重算并并列保留，两个数字都如实报告。
实现：`scripts/v52_ablation_action_cond.py`（SHA-256 fd33960f…，服务器与本地一致；
v47 select.py 405d4ac2…、v44/v47_verified catalog 与产出论文数字的管线逐位一致，
bolt/test 上 8 个共有方法行与原 `results/v47/evaluation/test_bolt.json` 全部
match=True）。

### 结果（block=test，source-macro MASE，三骨干均值）

| 方法 | bolt | timesfm | chronos2 | 均值 |
|---|---|---|---|---|
| FULL_INTROACT | 1.3783 | 1.5537 | 1.3779 | **1.4366** |
| A2 原（删 intervention 特征） | 1.3623 | 1.5179 | 1.3752 | 1.4185 |
| **A2_WO_ACTION_COND（新）** | 1.4035 | 1.5555 | 1.3819 | **1.4470** |
| A3 / A4 / A5 | 1.3703 / 1.3731 / 1.3969 | 1.5922 / 1.5854 / 1.5417 | 1.3749 / 1.3811 / 1.3644 | 1.4458 / 1.4465 / 1.4343 |

配对 parent-cluster bootstrap（10000 次，FULL−变体，负值=FULL 更优）：

- bolt：FULL−A2R = −0.0252，CI [−0.0478, −0.0025]，**不含零**，p=0.028
- timesfm：−0.0018，CI [−0.0335, +0.0310]，p=0.898
- chronos2：−0.0040，CI [−0.0337, +0.0265]，p=0.825

开发块（train_eval，未参与选参之外的决策）均值：FULL 1.1121 < 原A2 1.1255 <
A2R 1.1437 < A5 1.1612 —— 新消融的排序在开发侧同样成立，该替换决定可由开发证据支持。

严重度/种子块均值（FULL vs A2R）：test30 1.6975 vs 1.7235；test50 1.7353 vs 1.7784；
test_m2 1.4375 vs 1.4437；test_m3 1.4280 vs 1.4625 —— 全部 6 个 block 上 A2R 均不优于 FULL。

辅助诊断：A2R 干预率 0.826（FULL 0.654）、条件伤害率 0.444（FULL 0.402）、
harmful loss 0.0478（FULL 0.0375）——去掉动作条件后选择器更频繁且更不准地干预，
符合机制解释。

### 必须保留的诚实边界

- 原 A2（删 5 特征）在 test 均值上仍优于 FULL。机制消融支持"action-conditioned
  局部效用"是必要组件，但"22 维状态中的 intervention 特征块"仍未被消融支持。
  论文若替换 A2 行，应同时披露原特征删除结果（可移附录）。
- 三骨干中只有 bolt 的区间不含零；均值与开发侧一致，但不能说逐骨干显著。
- TEST 历史上参与过开发（E-001 未解决），本轮数字不能当作独立确认。

## 2. 同干预率门控对照（E-003 / 规划 E3）

实现：`scripts/v52_gate_controls.py`。阈值/概率全部在 train_eval 上按 FULL 的
开发干预率匹配后冻结，再原样用于 test；test 覆盖率为实际值，不再二次匹配。

| 骨干 | 对照 | test MASE | 实际IR | FULL−对照 [CI] | 不含零 |
|---|---|---|---|---|---|
| bolt | mean-only 门控 | 1.3765 | 0.757 | +0.0018 [−0.0014,+0.0050] | 否 |
| bolt | 线性效用门控 | 1.4046 | 0.713 | −0.0263 [−0.0526,−0.0003] | 是 |
| bolt | 随机门控 | 1.4075 | 0.751 | −0.0292 [−0.0504,−0.0081] | 是 |
| timesfm | mean-only 门控 | 1.6078 | 0.521 | −0.0541 [−0.1035,−0.0056] | 是 |
| timesfm | 线性效用门控 | 1.5389 | 0.515 | +0.0148 [−0.0050,+0.0346] | 否 |
| timesfm | 随机门控 | 1.6719 | 0.474 | −0.1182 [−0.1628,−0.0753] | 是 |
| chronos2 | mean-only 门控 | 1.3753 | 0.688 | +0.0026 [−0.0028,+0.0100] | 否 |
| chronos2 | 线性效用门控 | 1.3706 | 0.696 | +0.0074 [−0.0243,+0.0390] | 否 |
| chronos2 | 随机门控 | 1.4462 | 0.716 | −0.0682 [−0.0959,−0.0416] | 是 |

解读：在匹配覆盖率下，dispersion 惩罚**在三骨干上一致且显著优于随机门控**
（动作选择与少干预两种效应可分，E-003 的核心疑问得到肯定回答）；但对
mean-only 阈值和线性门控的优势是骨干依赖的（timesfm 显著优于 mean-only，
bolt/chronos2 持平）。论文应把惩罚的贡献表述收窄为"优于频率匹配的随机门控与
线性门控（部分骨干）"，不能笼统主张惩罚识别了更准的不确定性。

## 3. R-002 数字身份修正（静态重算，无需重跑）

`app:seeds` 稳定性表的 6 个 MASE 逐位来自 `results/v47/evaluation/{test,test_m2,test_m3}_{bolt,chronos2}.json`
的 `FULL_INTROACT.mase`，但那是 **h96+h192 双 horizon 汇总**，与段落声称的
"$H=96$"不符。正确的 H=96-only 实现值（各文件 `per_source_horizon_mase` 的
8 个 `h96|*` 源均值）：

| realisation | Bolt | Chronos-2 |
|---|---|---|
| primary | 1.1731 | 1.1106 |
| second | 1.1699 | 1.1148 |
| third | 1.1861 | 1.1109 |

修复路径二选一：把表格数字换成上表（Δ vs Keep 与 IR 列需标注仍为双 horizon 口径
或另行重算），或把段落文字改为双 horizon 子集。Bolt/Chronos-2 primary 同为 1.378
是 1.37831/1.37793 的舍入巧合，非复制错误。

## 4. 文件位置

本地（F:\work\Time-research\work2）与服务器（/home/vipuser/work/work2）路径一致：

- `results/v52_ablation/evaluation/{block}_{backbone}.json` — 18 份，6 block × 3 骨干，
  含完整消融梯子、逐源/逐 horizon 分解、配对 bootstrap、bank 支持数与冻结配置
- `results/v52_ablation/gate_controls/{backbone}.json` — 3 份门控对照（含开发侧校准量）
- `results/v52_ablation/logs/` — 每轮原始 stdout 日志与 status.txt（全部 exit=0）
- `scripts/v52_ablation_action_cond.py`、`scripts/v52_gate_controls.py`、
  `scripts/v52_aggregate.py`（本地汇总）、`tools/ssh_v52.py`（连接辅助）
- 服务器打包备份：`/tmp/v52_ablation_results.tgz`（SHA-256 cc8a1a2e…），
  本地已校验一致后解入 `results/v52_ablation/`

复算入口：`python scripts/v52_aggregate.py`（只读 v52_ablation 与 v47，不写盘）。

## 5. 未做事项（如实登记）

- E-001 独立确认集：未建立，需要未接触的新数据窗口，本轮无此资源。
- E4 的 parent 聚合邻域变体（M-001 相关）：未实现，登记为后续项。
- L-003（intervention 特征 NaN→0）：本轮只读追踪确认静态代码路径存在，
  未做运行级影响重算。
- R-001 逐表运行身份、R-003 延迟/计数映射：未在本轮范围。
