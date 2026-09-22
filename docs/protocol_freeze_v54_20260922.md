# v54 唯一协议冻结（2026-09-22）

本文件是自 v54 起唯一的协议事实源。v52 稿件及其结果封存为探索版本
（`archive/`，git 标签前历史），此后的方法定义、实现修复与全部实验数字
只能来自本冻结。任何与本文件冲突的旧文档（v44 三块划分、v44 protocol.py
的 bootstrap 次数等）以本文件为准。

机器可读副本：`configs/v54/protocol_freeze.json`。两者不一致时以本文件为准
并立即修正副本。

## 1. 数据切分

- 来源注册表：`src/introact_ts/v44/protocol.py` SOURCES，8 个来源，不得因
  结果剔除任何一个。
- 行段边界：`configs/v431-r5/main_protocol_v2.json` 的 `sources[].split_bounds`
  （ETTh1/ETTh2: train [0,10452) dev [10452,13065) calibration [13065,14807)
  test [14807,17420)；ETTm1/ETTm2: [0,41808)/[41808,52260)/[59228 段同结构]；
  Electricity/Exchange/Traffic/Weather 同文件）。
- TRAIN 区域 = train+dev 行段；TEST 区域 = calibration+test 行段
  （`src/introact_ts/v46/grid.py:4-8`）。calibration 行段并入 TEST 使用，
  不再作为独立调参区。
- TRAIN 内部划分：采用 v46/v47 的两块制 bank 0.80 / train_eval 0.20
  （`src/introact_ts/v46/grid.py:51,153-166`）。v44 `splits.py` 的
  replay_fit/gate/train_eval 60/20/20 三块制自本冻结起废弃，相关常量仅作
  历史保留。
- 时间审计不支持的 2 个 Weather 窗剔除规则保持不变
  （`src/introact_ts/v44/registry.py:47-53`）。

## 2. 父窗口与掩码

- CONTEXT=512，HORIZONS=(96,192)，PARENT_STRIDE=704，块间 purge≥704 行
  （`v44/protocol.py:25-31,88`，`v46/grid.py:169-198`）。
- 父窗口数：TRAIN 276（bank 223 + train_eval 53）；TEST 95
  （ETTh1 6、ETTh2 6、ETTm1 24、ETTm2 24、Electricity 9、Exchange 2、
  Traffic 6、Weather 18）。冻结后由 `grid.summary()` 生成显式 manifest 存
  `configs/v54/parent_manifest.json`。
- 掩码模式 P1_point/P2_target_block/P3_shared_block/P4_tail；种子 =
  SHA-256(source|parent|origin|horizon|pattern|seed)（`v44/protocol.py:137-150`），
  不依赖观测值。
- 评估块清单（episode 数 = parents×2 horizons×4 patterns×severities）：

  | block | 种子 | 严重度 | episodes | 角色 |
  |---|---|---|---|---|
  | bankx | 20260917 | 0.10/0.30/0.50 全枚举 | 5352 | 回放库（训练侧） |
  | bankx2 | 20260918 | 全枚举 | 5352 | 回放库稳健性 |
  | train_eval | 20260917 | 0.10 | 424 | 选参/冻结验证 |
  | test | 20260917 | 0.10 | 760 | 主评估（探索，见 §7） |
  | test30 | 20260917 | 0.30 | 760 | 严重度稳健性 |
  | test50 | 20260917 | 0.50 | 760 | 严重度稳健性 |
  | test_m2 | 20260918 | 0.10 | 760 | 掩码种子重复 2 |
  | test_m3 | 20260919 | 0.10 | 760 | 掩码种子重复 3 |

  bankx2 与 test_m2 共用种子 20260918 是历史事实，予以登记；二者角色不同
  （训练侧/评估侧）且掩码种子不依赖观测值，不构成泄漏。
- 三次掩码重复 = test / test_m2 / test_m3 三块配对，覆盖所有方法与全部
  三个骨干；只覆盖部分方法的重复不算完成。

## 3. 方法清单（比较行 roster）

目录动作（6 个，`v47_verified/protocol.py:50-57`）：KEEP（参考动作）、FFILL、
SINGLE_TSICL、MULTI_TSICL、CONTEXT_RIDGE、SAITS。外部阶段动作 =
SINGLE_TSICL/MULTI_TSICL/SAITS（候选由各自阶段归档提供，单一写者）。

比较行分三类，不得混为一谈：

1. **目录策略行**：NATIVE_KEEP、FIXED_SAITS、BEST_FIXED（train_eval 上
   source-macro MASE 最低的固定动作）、SOURCE_FIXED（留一来源固定策略）、
   FULL_INTROACT（完整方法）。
2. **简单选择器与消融**：R2_CART、A5_PARAMETRIC_RIDGE、A1_GLOBAL_UTILITY、
   A2_M（A2_WO_ACTION_COND，机制级）、A2_F（A2_WO_INTERVENTION，按 §5 新
   状态定义重算）、A3_WO_FORECAST、A4_ALWAYS_ACT、CATALOG_ORACLE（上限）。
3. **外部方法**：TATO（官方实现，48 trials×8 TRAIN 窗口搜索，先线性插值）。
   TOI/T1/SRDI/GIMCC/VIDA/BiTGraph/S4M/CTF 不运行，理由与检索日期写入附录
   availability 表（TOI 需要预测器梯度、与冻结推理管线设定不符；其余无公开
   实现或自训预测器超出冻结骨干契约）。
   **2026-09-22 决策登记（冻结变更）**：BRITS/CSDI 移出比较。原因：在与
   SAITS 等容量的冻结配置下，两者的训练成本（BRITS 单分片 35–50 分钟/epoch、
   全矩阵预估 10–30 GPU 小时）超出剩余预算，且既有 SAITS 已覆盖"训练型
   插补器"这一类外部方法。附录 availability 表按"已实现并部分运行、因
   预算移出比较"如实登记，不得写成从未尝试。主集分片产物
   （results/v54/replay/external/）封存备查，不进入任何表格。

## 4. 指标与统计

- 主指标 source-macro MASE：variant→parent→source→等权宏平均
  （`v46/select.py:276-292`）。
- 统计：parent 聚类配对 bootstrap，2000 次重采样，seed 101，95% CI
  （本冻结统一为 2000，v44/protocol.py 的 10000 作废）；多重比较 Holm 校正。
- harm cap：锚 = CONTEXT_RIDGE 在 bank 上的条件有害率；无可行 (k,β) 配置时
  选择器整体回退 KEEP-only 并记录（不得回退 max-β 而不再复核 cap）。
- 选参：LOPO over K_GRID×BETA_GRID，一倍标准误规则，平局取最少干预；
  每骨干一份 `results/v47/protocol/selection_{backbone}.json`，状态修复后
  全部重选。
- 决策行为指标：IR、条件 HIR、harmful loss、beneficial precision
  （`v46/select.py:252-273`）。

## 5. 状态定义修复（替代旧五维 intervention 块）

旧实现（`v44/state.py:197-228`）在缺失位置以 NaN 参考做差再 `nan_to_num`，
导致 mean_abs/max_abs/change_trend/near_origin 四维恒零（L-003）。冻结新
定义：

- 基线填充 `baseline = interpolate_gaps(reference_target)`（纯函数，只用
  可见参考，无模型、无未来标签）。
- 修复位置 = reference 为 NaN 且 candidate 有限的位置；delta =
  candidate − baseline（按 robust_scale 归一）。
- KEEP 的 candidate 即 reference，按定义修复位置为空，intervention 五维
  全零（含 fraction_changed=0）。
- fraction_changed = 修复位置数 / 窗口长度；其余四维在修复位置上计算，
  无修复位置时全零。
- 状态版本号 STATE_VERSION 自 "v44-full22" 升为 "v54-full22"，新旧状态
  不得混入同一回放库；回放库状态、检索索引与全部选择器结果重算，预测
  缓存（只依赖候选输入）按版本与哈希验证后复用。

## 6. 评分与支持（修复 M-001）

- 邻域打分改为 parent 聚类：同一 parent 的多个变体先合并为 parent 级均值，
  μ/σ 在 parent 级计算，n_eff = 邻域内不同 parent 数。分数公式
  s = μ − β·σ/√n_eff 不变，但 n_eff 不再被同一 parent 的重复变体放大。
- 邻域为空、parent 数不足、全部候选不可用、零距离邻域（tau 取
  median+TAU_EPSILON）、并列最高分（取最少干预、再按冻结动作序）五个分支
  的语义写入方法附录并有契约测试覆盖；任何分支不满足前置计算即回 KEEP。
- 结论限定在回放库支持范围内（E-005）：严重度三档与四模式均在支持中出
  现，不声称对未见缺失机制的泛化。

## 7. 污染登记与确认性评估

- 已参与开发、只能作探索用途的数据：8 来源 TEST 区域的全部五个评估块
  （v46 起反复读取，含 Chronos-2 的观察；E-001）。v52/v53 的全部 TEST
  数字封存为探索结果。
- 确认性评估：方法与选参冻结后，对**从未参与任何方法选择**的数据做
  一次性评估，过程中禁止回看、禁止改参。
- 数据审计结论（2026-09-22，`data/` 实测）：确认集 = **Solar**
  （52560×137，无原始时间戳，按 10 分钟频率登记 seasonal=144；TEST 区约
  13140 行 ≈ 18 父窗口）与 **US_Term_Structure**（9326×40，工作日频率
  seasonal=5，finite_fraction≈0.957，原生缺失按数据契约保留；TEST 区约
  2331 行 ≈ 3 父窗口，达到主集 Exchange 2 父窗口的先例下限）。
  **排除** Oil_Price（5035 行 → TEST 仅 1 父窗口）与 Crypto（2842 行 →
  1 父窗口），理由：TEST 区不足 2 个父窗口，聚类 bootstrap 无意义。
- 确认集来源的切分比例、stride、掩码模式/种子规则、指标与统计与主集完全
  相同；其 bank 同样按 0.8/0.2 划分并交叉拟合外部阶段动作。
- 重新生成同一批父窗口的掩码、换种子、重算区间均不把已污染 TEST 变为
  独立测试。

## 8. 失败处理与记账

- 可信度守卫：修复写入位置超出可见目标范围 ±3 鲁棒尺度 → unsupported，
  不执行、不入库（KEEP 显式豁免，参考输入允许含 NaN）。
- 完整输入（目标无缺失）只有 KEEP 合法，选择器必须弃权。
- 预测缺失、记录缺失：报错并逐原因计数，禁止填零、禁止静默换模型、禁止
  surrogate 降级。heldout_labels_read 记账保持 0。
- 成本口径：只报"请求级选择增加了哪些计算"与端到端实测（独立服务流程、
  batch=1、冷启动与热请求分列）；禁止用缓存重放速度冒充在线延迟，禁止把
  不同组件分位数拼成请求分位数。

## 9. 封存与版本

- v52 LaTeX 封存：`archive/paper_v52_20260922/`（复制自 `latex/`），正文在
  源文件上直接修订。
- 产生论文数字的选择器模块：`src/introact_ts/v47/select.py`
  （SHA-256 6f92048d…，修复后以新哈希登记）；v47_verified 语义差异四条
  （cap 锚/LOPO 标准化/不可行分支/bootstrap 分层）登记保留，不再混用。
- 本冻结的任何修改只能以"登记偏差 + 全体重算"方式进行，禁止局部打补丁
  后与旧数字混排。
