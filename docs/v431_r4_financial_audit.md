# r4 金融逐窗与费用审计

2026-09-16；只读取 r2/r3 已查看的账本，未读取原始新 future 或 calibration/test，未执行模型。身份核验沿用 r2，不计作新的金融有效性进展。

实际入口：`source scripts/env_new_server.sh` 后用 `$W2_CORE_PY scripts/v431_r4_financial_audit.py`。结果为 `results/v431-r4/baseline_audit/financial_audit.json`，保存12组完整UID、候选/预测hash、动作、发票、原worker响应路径和加载费用。脚本验证唯一收费key、费用求和及共同UID。

## 同 MASE 不同费用的实际原因

TimesFM 的 CART_H32_high 和 CART_H_high **12/12 最终动作、候选hash、预测hash、逐窗损失均相同**：4个完整输入用KEEP、4个target-only缺口用ridge、4个shared缺口用A2。MASE同为4.890237确实对应同预测，而不是只比较均值。两策略取得的历史输入、长度、目标跨度和模型调用仍不同；完整平均费用分别2.599254和1.128813秒，高预算超支为6/12和0/12。

| 原始UID前缀 | 来源/条件/H | H32秒 | H秒 | 最终动作 |
|---|---|---:|---:|---|
| ab96b6a5 | USTS target /96 | 3.711236 | 1.173758 | ridge |
| eaf4dd48 | USTS target /192 | 3.711 | 1.157 | ridge |
| 6336ac6f | USTS shared /96 | 3.975 | 1.978 | A2 |
| d8034d7b | USTS shared /192 | 4.001 | 1.994 | A2 |
| c813b6a6 | Oil target /96 | 3.425530 | 1.131571 | ridge |
| 27451111 | Oil target /192 | 3.430 | 1.158 | ridge |
| 74049f9f | Oil shared /96 | 3.954 | 1.955 | A2 |
| a1c62ae2 | Oil shared /192 | 3.985 | 1.999 | A2 |

以ab96b6a5为例，两路径最终candidate/forecast同为0.011056/0.243467秒。差异在历史候选生成1.172754对0.077511秒、历史预测2.260536对0.821040秒；准备0.022203对0.019530秒。选择器微秒开销不是主要原因。

更深的归因是**首次分片初始化费用分摊不均**。`Collector.model_call`（`src/introact_ts/v43/agent_collect.py:27`）把整次call减去行推理后的余量分摊到该分片。金融collector未提前`services.load`，H32先执行：

| 服务/分片 | 请求数 | 实际响应模型加载秒 | 每请求分摊余量秒 | 非cache调用/命中 |
|---|---:|---:|---:|---:|
| TS-ICL H32 single | 4 | 1.089584 | 0.839518 | 4/0 |
| TS-ICL H96 single | 12 | 0 | 0.005588 | 12/0 |
| TimesFM H32 | 20 | 3.362985 | 0.297129 | 14/6 |
| TimesFM H96 | 60 | 0 | 0.003348 | 42/18 |
| TimesFM H192 | 24 | 0 | 0.003816 | 18/6 |

原始路径：`results/v431-r3/probes/financial/sessions/20260914T174607.390882Z-bolt`与`20260914T174626.955635Z-timesfm`中的`model_invoices.json`及`*.response.json`。`Services.call`（`scripts/online_v43_agent.py:75`）在摘要cost_ledger中硬写load_seconds=0，但完整response保存非零`service_initial_load_seconds`；完整wall收费已含加载，故这是**成本分类字段不准确，不是加载费用丢失**。TS-ICL生成费用跨家族复用也保留首次实际成本。r3 collector会将跨输入cache命中重新按原推理价计费，不能把6个cache命中当免费部署调用。

旧表不改数、不扣掉已经发生的初始化来制造预算胜出；它的“0/6”是原小批次完整组件账，不是驻留模型单请求H32天然比H慢的证明。r4应将cold/init与hot单独登记，费用模型只拟合TRAIN；自然单请求验收决定新表预算可行性。没有本次金融自然在线时，不把旧离线12窗费用称为新线上实测。

## 金融条件与强对照

Bolt KEEP **2.820959**优于固定A2 **3.069683**及r3 agent **3.103498**；不允许只选A2作金融参照。TimesFM r3 agent **4.920632**虽低于A2 **5.212728**，有**8/12高预算超支**，不能称同预算改善。完整条件五臂预测一致；该no-op只验证保护有效观测，不是准确率贡献。

两parent分别为Brent Europe现货报价（美元/桶）与Kim–Wright拟合一年远期利率（百分点），后者不是成交价格。身份、文件hash和变换未知项见[v431_r2_financial_audit.md](v431_r2_financial_audit.md)。两个来源原TRAIN有限日期重叠1242、水平Pearson −0.142379；两个DEV parent时间不重合，但各与旧pilot/DEV有标签重叠，不是新确认。

## 自然NaN元数据：仍不能把休市当缺失

| 来源 | 既有TRAIN全字段缺失行/总行 | 观测/发布口径 | 本轮分类状态 |
|---|---:|---|---|
| Oil |133/3021|EIA现货closing报价；原作者工作日网格|原始provider逐日报价是否应存在、当地假期、时区及发布顺序未恢复；全部原因保持unknown|
| USTS |248/5595|每日收益率输入推导出的研究模型系列；通常周二更新至上周五|不具有保证的每日同步发布；休市、未产出、延迟或上游处理未逐点区分；unknown|

EIA将现货价格描述为特定交付的交易报价口径，不能推导所有工作日均应发布或把无报价设为零。[EIA定义](https://www.eia.gov/dnav/pet/TblDefs/pet_pri_spt_tbldef2.asp)。Fed明确该研究产品可延迟、修订及变更方法，通常每周发布；当前观测日期不是历史available_at。[Fed官方说明](https://www.federalreserve.gov/data/three-factor-nominal-term-structure-model.htm)。缺历史vintage时，两者继续`strict_point_in_time=false`。没有可靠的自然应有观测缺口集合，**自然缺口方法结果缺项**；零成交也不能从价格表NaN反推。

本轮保留完整记录、受控删除、自然缺口缺项三类；不对真实跳变治理，不改交易日历、目标变量或外层分母。若后续恢复官方日历/发布时间，需新协议、原行映射和全对照，不在旧表上补节假日后称同任务。

## r4 已执行的 cold / hot 分类修复

新增 `scripts/v431_r4_hot_costs.py` 和 `scripts/v431_r4_hot_cost_adapter.py`，只读保存原始费用。第一入口生成`results/v431-r4/baseline_audit/hot_costs.json`，逐项记录19,497个实际费用key，其中9,464项包含明确的model-load分摊。第二入口将其映射到`results/v431-r4/hot_costs.json`，覆盖主账本816窗×2家族、金融12窗×2家族及检查17窗×2家族，供r4训练前费用层使用。没有改动旧r3预测、首次结果或预算。

只扣原worker响应或status中实测的model-load：Collector按该分片request数分摊；原TimesFM train缓存按其原费用公式的unique-call数分摊；旧独立baseline按原完整process余量的record数分摊。命中缓存通过raw_native_file找到原非命中行及其价格；动作别名通过真实输入hash映射。每项都验证扣除非负、不超过原价及cold+hot=原总；其余IPC、输入准备、导入、warmup与未单独归因的余量**全部保留**，不粗暴抹去首次分片余量。

扫描过的唯一原始source账本显式模型load合计68.936773秒，包含历史已执行的旧mask/history等分片与独立load调用，**不是本轮新增模型时间，也不是完整离线总成本**。每个counterfactual复用同一加载摊价，因而不能把所有候选的扣除相加当实际加载总量。物理load按原响应路径去重，完整清单单列于sidecar；原总费用仍可恢复。

| 旧冻结金融策略 | 原完整组件秒/窗 | 仅剥离显式load后秒/窗 | 原 / 修复后 high超支 |
|---|---:|---:|---:|
| TimesFM CART_H32 |2.599254|1.764402|6 / 0|
| TimesFM CART_H |1.128813|0.980006|0 / 0|
| TimesFM r3 agent |2.769635|1.888309|8 / 0|
| Bolt CART_H32 |2.749388|2.310684|7 / 2|
| Bolt KEEP |0.475021|0.457037|0 / 0|

这里只是**相同旧冻结决策的费用分类诊断**，不是重跑新策略或金融自然线上实测；旧r3的8/12超支结论仍属其原完整组件口径，不回写为0。r4新表统一使用这套费用版本后再独立报告自然单请求，不能混两种口径比较。

Bolt TRAIN剩余极值亦已核：UID `5c912698e292f55cbc8041064d41178871c48de63ed42d54a015c2cb0b8452b5`（ETTm1:0:704、H192、raw）Native与别名臂共享原`final-h192-bolt`首行预测。原推理2.859619秒、分摊余量0.011911秒；对应完整FFILL备选价格2.898564，load只可扣0.000348，余2.898216秒。不能将其余慢推理假设为load删掉；其是否warmup需单独实测，不能为改善预算数字逆向估计。

复现命令（第二次不会覆盖既有sidecar）：

```bash
source scripts/env_new_server.sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$W2_CORE_PY" scripts/v431_r4_hot_costs.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$W2_CORE_PY" scripts/v431_r4_hot_cost_adapter.py
```

金融120个策略/窗口发票的费用分解核验见`baseline_audit/hot_costs_financial_check.json`；只使用已查看DEV账本，不读新标签。审阅包应收精简清单/代表发票及源hash，不必打包22MB完整冗余sidecar。
