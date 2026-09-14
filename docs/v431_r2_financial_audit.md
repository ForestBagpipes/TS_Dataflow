# v4.3.1-r2 金融身份、原始日期与完整观测审计

审计时间：2026-09-15，Asia/Shanghai。本次只修改本文件、`scripts/v431_r2_finance.py` 与 `results/v431-r2/finance/`；不运行 GPU、不改旧 worker、不覆盖原数据。实验主入口与最终 manifest 由主执行 agent 冻结。

## 已核实的结论

已核实 **Oil 的能源现货报价**和 **USTS 的 Kim–Wright 利率模型估计量**两个金融来源。USTS 当前预测目标是 `FwdRate_Fitted_1Y`，不是可成交债券价格，也不是 `Yield_Fitted_1Y`。Crypto 当前作者版本来自 BitInfoCharts，其四币字段与本地 TRAIN 精确一致，但原协议 DEV 长度不足，不为凑窗口挪动保留集边界。

三份本地 NPZ 的全部 TRAIN 数值和 NaN，均与固定版本作者 CSV 经官方 Arrow 的 float32 转换后的结果逐元素一致；作者 CSV 日期与本地 start/freq 所对应的完整 D/B 网格逐行一致。**这证实保留快照的身份和日期映射，未证实其上游从未清洗、每个价格绝对正确或严格 point-in-time。** 本地未改写任何数值，大幅变化没有被本审计作为错误覆盖。

原 Oil/USTS 全缺失行尚无逐日、逐市场的原因标签；不得统称休市、缺失交易或自然观测缺口。普通业务日 B 只排除周末，不是某个市场的完整交易日历。原有 `experiments/datasets.py:168` 的 `compact=True` 按全字段有限删行，并称它们为 non-trading rows；这一历史解释没有自动获得本轮确认。

## 资产身份与报价口径

| 来源 | 实际字段和单位 | 快照范围、频率 | 时间与调整限制 |
|---|---|---|---|
| Crypto | BitcoinCash、Bitcoin、Ethereum、Litecoin；公开市场 USD 价格聚合，既有 target0 为 BitcoinCash | 2017-12-20—2025-09-30，2842×4，D | 日界时区、精确聚合规则、历史 vintage 未恢复；并非核实过的单一交易所 OHLC |
| Oil_Price | target0 `COP_Brent-Europe`，Brent 现货 USD/桶；WTI 同单位；汽油、柴油、取暖油、航煤、丙烷 USD/加仑；Henry Hub 天然气 USD/MMBtu | 2006-06-14—2025-09-30，5035×12，B | 日收盘现货报价；不同地区、品种未必同一休市和发布时间；不适用股票复权或期货换月调整，但历史修订未恢复 |
| US_Term_Structure | target0 `FwdRate_Fitted_1Y`；另有 1—10 年拟合远期利率、瞬时远期期限溢价、拟合零息收益率、期限溢价，共40列；百分点 | 1990-01-02—2025-09-30，9326×40，B | 模型输出，不是可成交价格；负期限溢价等不能自动当成错误。日期是估计所属日，历史发布版本未恢复 |

TIME 作者在 2026-05-20 记录 Crypto/D 替换为 BitInfoCharts 公开聚合；本地 TRAIN 与该作者 CSV 匹配。[TIME 数据卡](https://huggingface.co/datasets/Real-TSF/TIME)、[BitInfoCharts 价格口径](https://bitinfocharts.com/comparison/bitcoin-price.html)

EIA 列出原油和成品油的地区报价及单位；其说明将现货定义为即时交付交易报价，石油数据源为 Refinitiv/LSEG，日数据为 closing spot prices。Henry Hub 单独使用美元/百万 Btu。[EIA 石油现货](https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm)、[EIA 定义与来源](https://www.eia.gov/dnav/pet/TblDefs/pet_pri_spt_tbldef2.asp)、[EIA Henry Hub 单位](https://www.eia.gov/dnav/ng/hist/rngwhhda.htm)

美联储官方说明 USTS 是 Kim–Wright 三因子模型，通常周二更新至上周五，存在延迟、修订和方法改变；新旧模型使用过不同的参数估计样本。因此把同一行所有协变量设为 `available_at=row_time` 只能是旧快照基准假设，不能写成真实历史可用性。[美联储模型、发布频率与修订说明](https://www.federalreserve.gov/data/three-factor-nominal-term-structure-model.htm)

官方 Fed CSV 头部提供 `THREEFFxx00.B`、`THREEFFTPxx00.B`、`THREEFYxx00.B`、`THREEFYTPxx00.B` 对应四组字段，声明单位为百分点。本地列按字符串排序，故每组为 1Y、10Y、2Y…9Y，脚本按期限数字显式映射，不依赖位置猜测。[官方 CSV](https://www.federalreserve.gov/data/yield-curve-tables/feds200533.csv)

全部逐字段身份、单位、官方 mnemonic 见 `results/v431-r2/finance/audit.json` 的 `fields`。CSV 源字段 `RGBFOB(P_RegularGasoline_LosAngeles` 的不完整括号按原文件保留，不擅自改名。

## 原始文件、上游变换与核对范围

| 本地文件 | SHA256 |
|---|---|
| `data/time_Crypto.npz` | `a905547fdfa832758539f3a14443d60b1c1cff9991f35ad964b7896dcf410375` |
| `data/time_Oil_Price.npz` | `da8ac6fc14a454071a6aadc210d8f8c1a86fe4266ea3611e56532bd31a118186` |
| `data/time_US_Term_Structure.npz` | `7496e780f67da7da90073e0d7dcee5b445a4d54d9b568ef58f9938bbf6f76511` |

作者 CSV 固定为 `Real-TSF/TIME-ProcessedCSV@683bb21b470f5a26586e1ab2295f0a2a1529ef0f`；作者 Arrow 库元数据固定为 `Real-TSF/TIME@83e3d0b3be28d11c7182bffcc1892d19b36c4da1`。三个 CSV 全文件 SHA256 分别为：

- Crypto：`7587fb7e312656ff2f649087e55c99721fd4f45972354a05b05eeeaa581423f7`。
- Oil：`75d64cd1cc5a3cfdd88a0ccbbcafb637904f4cf3caeb024e4fcb1bb2b96f55f8`。
- USTS：`2b0c3f743779c8a4029eafbe13f87329a012545e9d1ebdf03d1b99298cf30215`。

作者代码固定为 `zqiao11/TIME@c11ed82c3eaf39e42e081e5995e7880a76f86cb9`，仅克隆读取，未运行其预处理。`dataset_builder.py:181` 将原矩阵转成 float32；项目 `experiments/time_export.py` 再转 float64，审计复现该精度链。作者 `docs/PREPROCESS.md:19` 提供极端 IQR 异常替换前值等功能，但本地没有这三个来源的逐点处理日志；不能宣称这些动作一定发生过，也不能宣称没有发生过。[TIME 官方代码](https://github.com/zqiao11/TIME)

本次下载美联储当前 CSV 的 SHA256 为 `b6d31dfd98ae4287a8b057f3e7e474a145fff6d4bfb10a552b27ce2335cbab67`。只转换与 USTS TRAIN 同日期的5595行：NaN模式一致，223800个单元中1479个有限值有差，最大绝对差 `0.00010013580322265625` 个百分点。该差异可能来自历史修订、舍入或上游处理，当前不能唯一归因；未替换保留数据。它也说明不能把当前 provider 快照自动等同于当年实际可见版本。

原始来源的首次采集文件和历史 vintage 未在旧导出中保留，故上表哈希的“原始”是本项目保留输入字节，不是宣称获得了供应商首次发布字节。TIME 主数据卡与 processed CSV 卡的许可标注当前也不一致，原样保留元数据，不据此推导新的使用权限。

## TRAIN 实际支持与未覆盖观测

| 来源 | TRAIN 行边界 | 所有字段有限行 | 所有字段缺失行 | 部分字段缺失行 | 原网格 train/dev 704行 parent 容量 |
|---|---:|---:|---:|---:|---:|
| Crypto | [0,1705) | 1705 | 0 | 0 | 2 / 0 |
| USTS | [0,5595) | 5347 | 248 | 0 | 7 / 1 |
| Oil | [0,3021) | 2888 | 133 | 0 | 4 / 1 |

以上是数据支持盘点，不是已运行新方法成绩。所有 TRAIN 有限值与作者快照精确一致；脚本只读且没有治理动作。`audit.json` 保存 target 相邻有限点最大五次变化的原行号/日期/变化量，例如 Oil 2008-06-05→06-06 的约 +10.45 USD/桶、USTS 2008-09-18→09-19 的约 +0.3917 个百分点。这些观测未被替换，且只标为 observed change，不把大幅变化标成错误或经济事件真标签。完整候选是否覆盖有效值由主执行 agent 的候选不变量检查另行验证。

两个已核实来源的完整日期范围重叠为 2006-06-14—2025-09-30。仅在各自 TRAIN 的交集 2006-06-14—2011-06-13 上，1242个配对有限 target 日的水平 Pearson 为 -0.142379；共同日期网格相邻变化有1186对，相关系数0.153620。这是描述性依赖统计，不表示独立，未进入策略特征或来源选择。Crypto/Oil 仅12个配对TRAIN日期，不足支撑稳定相关性结论；Crypto/USTS 无共同TRAIN日期。

各来源按旧比例单独划分，真实日历区间并非全局隔离：例如 Oil TRAIN 的后半段与 USTS DEV 的日期重叠。当前不引入跨来源协变量，也不宣称跨来源完全独立；同面板所有列、跨度、相关变体必须共享 parent。后续统计应保留来源和时间依赖限制，不能靠列数或变体扩充独立样本数。

## 原 B 网格：可执行 Oil 记录与封存状态

`Oil_Price-record.json` 保留 target0、原 NPZ 路径/hash、原始行号及 [0,3021)/[3021,3776)/[3776,4279)/[4279,5035) 四段边界。`Oil_Price-time-map.csv` 只包含 row_id、civil_date、split、同面板同步标识，没有测量值；完整作者日期逐行匹配，不虚构 UTC 收盘时刻。

原 B 网格新增 Oil DEV parent 为 `[3021,3725)`，512行 context 截止3533；context 日期2018-01-11—2019-12-27，H192评价日期2019-12-30—2020-09-22。它可作为单独新增 DEV 快照对照，首次结果应保存，不能与旧26 parent的1.157005直接混比。本审计没有解码 Oil DEV context 或 future 浮点数值。

Crypto DEV 只有426行，L512+H96/H192不能放入；不能移动 calibration/test 边界或补读前段 context 凑出合法 DEV parent。

## 独立完整案例附表：financial-observation-index-r1

主执行 agent 在本轮明确提出：为区分已有有限观测与受控删除，另建完整案例的观测事件索引；所有方法和两个模型家族在相同新集合重新计算，旧 B 网格表保留。本审计完成可用性准备，**最终协议和候选冻结由主执行 agent负责**。

选择规则在新结果前固定：每个来源、每个原 train/dev 段独立按作者 civil date 顺序，仅选择所有原字段均有限的记录；不改变值、单位和 target。完整原始行映射与排除行清单保存。被排除行只叫“快照中至少一字段非有限”，不称休市、丢失交易或错误报价。这是条件完整案例子集，不是证明来源从来没有自然缺口。

| 来源 | TRAIN 完整案例行 / 原行 | TRAIN 704事件 parent | DEV 完整案例行 / 原行 | DEV 704事件 parent |
|---|---:|---:|---:|---:|
| USTS | 5347 / 5595 | 7 | 1342 / 1399 | 1 |
| Oil | 2888 / 3021 | 4 | 717 / 755 | 1 |

附表的 H96/H192 是未来96/192条**记录事件**，不同于旧 B 网格的96/192行。未知缺失原因意味着未来事件具体日期也不是预测时点已知的完整交易日历：未来 row/date 映射仅供 evaluator 使用，不得进入 agent 特征。不能将此附表写成固定96/192工作日的严格实时预测。

USTS 日期仍是所属观测日，不是实际发布日期；“作者快照中有记录”不等于“当日已公开”。Oil same-panel 辅助报价的实际时区/发布顺序也未核实。两来源均保持 `strict_point_in_time=false`，不开跨来源协变量，不将回顾性条件表扩大为严格 PIT 验证。

三种条件分别登记：

1. **完整已有记录**：在本附表选定子集上保留全部原始有限值。允许检验候选 no-op 和完整成本，但不能预填 no-op 已通过或效果改善。
2. **真实应有观测缺口**：尚无经过逐日来源/市场核实的分类集合，当前缺项；不能用 excluded rows 冒充。
3. **受控删除**：由主执行 agent 在同一完整案例 context 的原有限点上按冻结规则删除，保留原值和 mask，所有对照共用；自然缺失不被改写成受控真值。

准备文件为 `observation-index-r1.json`、`Oil_Price-observation-index-r1.csv` 与 `US_Term_Structure-observation-index-r1.csv`。JSON 中每个 parent 给出 exact `raw_context_rows`、`raw_future_rows_H96/H192`、原始完整读取包络、日期和同步组。新 parent 与旧 USTS DEV 有原时间重叠，不能额外宣称为此前未使用的独立新 DEV；新增 Oil 首次结果单独保留。

## 读取账本、命令与验收

默认审计仅将三个来源原 TRAIN 段转换为浮点数值；作者文件/NPZ全字节 hash 与全文件日期扫描不用于估计、归一化或目标选择。下载时的 `numerical_values_read=false` 仅描述下载阶段，之后授权的 TRAIN 对比记录在 `audit.json` 的 read_ledger，不混写为从未读过训练数据。

附表可用性审计单独授权检查 train/dev 的缺失模式：作者 CSV 只匹配空值/NaN/Inf/数字语法，NPZ只把 IEEE 指数位转换为 finite mask，两者逐元素一致，不将 DEV bit pattern 转成浮点标签。calibration/test 连存在 mask 都未检查。该 mask 用于预登记完整案例集合，未来 mask/日期不属于 agent 的可见状态。

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" scripts/v431_r2_finance.py --self-test
"$W2_CORE_PY" scripts/v431_r2_finance.py
"$W2_CORE_PY" scripts/v431_r2_finance.py --prepare-observation-index
```

日志：`results/v431-r2/finance/semantic-test.log`、`audit-run.log`、`observation-index-run.log`。本轮相关检查通过：时间字段单独读取、毒化 DEV 数字不被 train reader 解析、NaN 保持、calibration/test 和跨段数值读取拒绝、CSV presence 与 IEEE有限位一致、保留集 presence 读取拒绝。不重复原58项无关测试。

代码归因：`timestamp_fields` 只读日期；`train_csv_values` 只转换原TRAIN；`audit` 校验源hash/列名/日期及训练值；`compare_fed_train` 限定官方CSV对比日期；`presence_fields` 与 `retained_finite_bits` 做明确的缺失模式审计；`prepare_observation_index` 导出新完整案例行映射。大结果、下载CSV与模型权重不入Git；本审计未改变主报告、incumbent或方法晋升状态。

## 附表输入已准备，真实 GPU 收集由统一队列执行

终态冻结文件已经存在后，`scripts/v431_r2_financial_inputs.py` 实际准备了2来源×2跨度×3条件共12个 episode、2个 parent，结果位于 `results/v431-r2/financial-observation-index-r1/`。MASE分母仅使用既有TRAIN、全字段有限事件目标的lag5差：USTS为 `0.10750568831895273`，Oil为 `2.666378768830923`。这些分母与旧B网格不同，不混合旧表比较。

`contexts.npz` 仅含 target/covariates/timestamps/availability；`episode_manifest.json` 仅给原始 context 映射。真实civil date以无时区日末ns编码，availability同日末，这是明确的快照假设，不是恢复了实际发布时刻。所有 future 行号、日期及原记录路径单独进入 `evaluator_metadata.json`，在线禁止读取。输入准备只解码TRAIN及选中DEV context的原始包络，future数值读取0。完整已有观测和target/shared 51事件删除的不变量自测通过。

新增 `scripts/v431_r2_financial_collect.py` 只复用旧 `Collector.pools` 和 `Collector.forecasts`，不调用会读取标签的 `run_collect`。本脚本由主执行agent统一GPU队列运行；本审计子任务只实现并执行CPU自测。它准备完整五臂、36个strict mask视图、12个exclusive cutoff `r=512-H` 的历史视图；保留 dirty 前缀、不截取当前治理结果、不读context前历史。真实预测完成后才可由独立 evaluator 读取future。

Collector保存当前与历史候选/预测、模型原始响应、发票、别名、mask证据及完整工具费用；原始完整输入五臂是否同KEEP，由真实生成后的 `complete_raw_noop.json` 记录，不能在尚未执行时当作实验结论。完成后只生成下一队列的四类请求：TATO/Bolt、TimesFM当前五臂、TimesFM历史五臂、TATO/TimesFM，复用原冻结官方TATO八类变换和8trial配置，不下载、不改旧adapter、不自动并发GPU。

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" scripts/v431_r2_financial_inputs.py --self-test
"$W2_CORE_PY" scripts/v431_r2_financial_inputs.py
"$W2_CORE_PY" scripts/v431_r2_financial_collect.py --self-test
# 下一行仅由统一GPU队列在资源空闲时运行：
"$W2_CORE_PY" scripts/v431_r2_financial_collect.py
```

输入是不可覆盖的准备产物，重复运行会拒绝已存在的 `contexts.npz`；Collector已有 `inputs/` 时也拒绝重启覆盖。失败保留原始日志，重试须另登记目录。原始审计、准备及收集日志分别见 `financial-inputs-semantic-test.log`、`financial-inputs-run.log`、`financial-collect-semantic-test.log` 和主执行agent的队列日志；本文件截至此处仅确认输入/代码CPU检查，GPU完成状态以实际 `status.json` 为准。

## 首次附表结果与实际费用（2026-09-15 完成）

主执行agent的金融Collector及四个后续GPU worker均已完成。`scripts/v431_r2_financial_score.py` 先验证所有预测、请求和冻结终态/获取模型SHA，并复核Collector原始分位数与TimesFM历史原输出，再首次读取评价映射。仅解码两个parent各192个DEV target0值，共384个元素；H96与所有变体共用对应前缀，future辅助通道、排除行数值和calibration/test均未解码。

首个CPU评分尝试因core解释器缺TATO依赖`tqdm`失败，保留`financial-score-first-run.log`；没有改环境。随后改用既有Chronos解释器执行旧TATO/TimesFM独立CPU验证，复用已冻结target文件完成评分，日志`financial-score-resume-run.log`。该失败没有触发模型替代、失败填零或再次读取原future。

下表为**新观测事件协议、2个parent/12个episode**的来源宏平均MASE；不是旧26parent表，也不是独立确认成绩。费用为本次小批次中含加载/IPC分摊与原工具的完整组件费用，不是金融线上冷启动延迟。

| 方法 | Bolt MASE | TimesFM MASE |
|---|---:|---:|
| native KEEP | 2.820959 | 5.225872 |
| 固定TS-ICL / 原train冻结强参照 | 3.069683 | 5.212728 |
| 原同证据CART | 3.088108 | 4.890237 |
| 固定取证CART，高预算 | 3.069683 | 4.890237 |
| v4.3.1-r2，高预算 | 3.069683 | 4.890237 |
| 原生TATO空间，8trial适配 | 4.698655 | 4.980245 |

两家族的原完整context共4个episode×5臂×2家族=40次输入和预测逐元素相等，记录`complete_raw_cross_family_noop.json`；原始完整条件不能写成治理带来的预测提升。TATO保留其原生变换能力，不声明它满足五臂的有效观测保护约束。

金融新数据没有参与重新训练。冻结策略在这批离线回放中，Bolt12/12 STOP、无切换；TimesFM8/12选择mask获取，但仅4/12相对固定参照换臂，任务效果与固定取证CART相同。因此这里仍没有主动选择取证优于固定流程的证据。这8次是有真实预计算工具结果支撑的**离线部署策略回放**，不冒充已执行8次金融在线按需请求。

条件划分显示TimesFM的收益集中在target-only受控删除：固定TS-ICL5.526062降到agent/固定取证4.558586；shared删除没有对应增量，均为5.526062。Bolt两种删除下KEEP2.757896优于agent/TS-ICL3.130982。真实应有自然观测缺口仍无可靠分类集合，保持缺项。

高预算agent完整分摊均费：Bolt1.186296秒、TimesFM1.575274秒。低预算0.8140623268639832秒下，agent分别10/12、8/12超支；Bolt固定取证在3.5秒高预算下8/12超支，未删窗口。大部分费用受12窗小批次模型加载分摊影响，但不能为压低费用而扣除已经发生的代价。

未执行预算准入的固定方法、旧CART和TATO，主行原始`budget_overruns`不能解释为其全部满足预算。另存`budget_flag_audit.json`，对每行`total_seconds`与冻结low/high预算比较：旧CART的高预算超支为Bolt10/12、TimesFM8/12；固定TS-ICL低预算分别10/12、8/12；两TATO低预算均12/12、高预算均0。该派生审计只补清预算字段含义，未改预测、损失、已发生费用或首次结果。

共同18行结果及逐窗归因：`common_financial_table.json`、`common_financial_decisions.json`、`common_financial_by_source.json`、`common_financial_by_condition.json`。本地五臂机制表保留`financial_table.json`系列，原生TATO并列在共同表；工具数量字段中TATO的8是优化trial数，不等同于agent历史/mask工具次数。

首次冻结文件：`first_dev_results.json`，SHA256为 `a3fdffd88bab5ccdb6f38497581bc3ed6c985f3fabaf727319de89810ab16204`。一来源仅一个parent，未生成无依据的分组bootstrap置信区间；USTS仍与旧DEV重叠，Oil首次附表结果单独保留。无方法晋升、无严格PIT结论、无自然缺口有效性结论。

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" scripts/v431_r2_financial_score.py --self-test
"$W2_CORE_PY" scripts/v431_r2_financial_score.py --precheck
"$W2_CORE_PY" scripts/v431_r2_financial_score.py
```

最后一行仅首次评分或无最终表时的受控恢复可用，已有首次表即拒绝覆盖。新增相关自测确认未完成worker会在读取评价映射之前失败、只读所选target元素、DEV外或逆序行被拒绝。自然按需在线覆盖的总体结果由主执行agent单独报告，不与本金融离线附表混写。

## r3 接续时补充：相关性与历史暴露更正（2026-09-15）

原始记录 `results/v431-r2/finance/dependence.json` 已完成，只使用原 TRAIN 数值与 DEV 原行/日期元数据；本段不读取任何新 future。Oil 与 USTS 原 TRAIN 在2006-06-14—2011-06-13有1304个共同日期，其中1242对目标同时有限。原层级 Pearson 为 `-0.1423787574630594`，Spearman 为 `-0.17902432212302996`；目标分别是美元/桶的 Brent现货报价和百分点的一年拟合远期利率。未转收益率，也未使用忽略自相关的 IID p值，不能凭相关性较低宣称两个独立金融机制。

两 DEV parent 的实际时间不同：Oil context为2018-01-11—2020-02-05，H96/H192未来至2020-06-25/2020-11-11；USTS context为2011-06-14—2013-06-28，未来至2013-11-15/2014-04-07。两来源的context/future日期分别不相交，但每个parent的两个跨度共享前96个未来目标，三条件和新增probe也仍属同一parent。

**更正此前“Oil首次结果”的解释范围**：Oil 新附表的H96/H192均有4个未来点（原row3561—3564，2020-02-06—2020-02-11）已作为旧32origin真实pilot标签读取，另有26个当前context点曾是旧pilot标签。USTS新H96全部96个未来点、新H192的161个未来点与旧agent26的DEV标签重叠；旧pilot另与其未来标签重叠9点。因此两来源均不是此前完全未使用的独立DEV或确认集。`first_dev_results.json`只表示本观测事件协议的首个结果，不表示历史首次看见全部标签；保留原文件与SHA，不改结果。

r3只复用该2parent/12episode金融附表，新增探针不扩大独立样本数，不移动train/dev/calibration/test边界，不重新把DEV拟合成TRAIN。`strict_point_in_time=false`、自然应有缺口未核实、原层级目标及事件lag5分母的限制继续生效。具体长短probe适用范围见 [r3相关工作与金融条件](v431_r3_related_work.md#金融附表的-r3-适用范围)。
