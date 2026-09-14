# v4.3.1-r2：旧版本 STOP 与真实训练支持审计

2026-09-15，服务器CPU只读重放。**旧全STOP结果与自己的基础D2策略完全一致；它原本没有承诺退回固定TS-ICL。退步来自基础D2在开发数据上的错误治理选择，停止逻辑没有额外改动动作。** 两个获取器的训练标签没有任何正收益，不能把全STOP主要归因于成本权重过高。

本报告诊断旧v4.3.1，不把随后r2的规则变更写成已验证收益。旧26个dev parent继续视为反复使用的开发数据；未读calibration/test数值。`PICS_joint_relabel`不变。

## 可复核运行与原始证据

执行命令：

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" scripts/v431_r2_audit.py
```

成功运行目录：`results/v431-r2/audit/20260914T163303.285156Z`；7.094秒完成。重新核验2,768份current真实原始分位数输出，按同一原始future评分mask重算4,080份五臂train/dev任务损失；重放两个冻结终态、两个预算的624条agent决策。

| 文件 | 内容 |
|---|---|
| `stop_window_audit.json` | 逐窗五种策略动作、完整candidate/prediction hash、MAE/MASE、13项可见特征、基础树路径、STOP原因与费用 |
| `stop_comparison.json` | 按来源及总体的动作变化、实际预测变化、损益与独立parent计数 |
| `acquisition_training_audit.json` | 432条获取标签的实际支持与正/零/负分布、冻结根叶值、lambda和gate记录 |
| `forced_stop_and_contracts.json` | 强制STOP与实际决策一致、未获取证据callback调用数、过期hash拒绝 |
| `base_policy_role_losses.json` | 固定A2及基础D1/D2在五个角色上的实际MASE |
| `support_inventory.json`、`legal_train_interval_candidates.json` | 元数据支持上限、已用区间、TimesFM训练缓存缺口、额外来源候选 |
| `source_identity.json`、`status.json` | 实际审计代码SHA与运行终态 |

首个审计尝试错误地把所有遮挡工具都设为适用，与原实现对少数窗口的dirty-only适用性检查不一致，断言失败。原失败保留在 `results/v431-r2/audit/status.json`；修正审计器为原 `mask_views` 条件后通过，没有修改策略、预测、标签或费用结果。

## STOP 的真实语义及退步

原入口 `scripts/v431_fit_evaluate.py:130` 先调用 `model.base_tree.predict`，把结果作为 `stop_arm` 传给 `execute_one_step`。`src/introact_ts/v431/acquisition.py:392` 仅在取得工具时替换这个动作。因此STOP意味着停止取证，基础动作可能是KEEP、A2或其他合法臂，不等同于固定A2。

| 开发来源 | agent/基础D2 MASE | 固定A2 MASE | 不同动作 | 不同候选及预测 | 改善/不变/变差 |
|---|---:|---:|---:|---:|---:|
| ETTm1：14 parent / 84变体 | 1.063942 | 1.058308 | 8 | 4 | 0 / 80 / 4 |
| Solar：11 parent / 66变体 | 1.517828 | 1.402176 | 28 | 20 | 3 / 46 / 17 |
| USTS：1 parent / 6变体 | 1.018704 | 1.010530 | 2 | 2 | 0 / 4 / 2 |
| 来源宏平均：26 parent / 156变体 | 1.200158 | 1.157005 | 38 | 26 | 3 / 130 / 23 |

156/156窗口的实际agent、强制STOP及基础D2动作、候选hash和真实预测损失一致。相对A2的38个动作差异中，12个没有改变输入或预测，不能当作有效治理切换。真实26次预测变化只有3次改善、23次变差。总体MASE差为+0.043153；Solar贡献主要退步。

具体失败窗口 `69948978609d03c9961437e0e28b636add9463b19915da352270852ca2fb648f`，Solar/H96/shared_block_10：

- 可见协变量缺失比例0.099609大于树阈值0.051758；进入右子树。
- `log_context_scale=0.000001`小于0.217970；进入基础叶5，训练支持17个parent，选择KEEP。
- agent和强制STOP候选hash均为 `11b2a66320da…`、预测hash为 `25d696372129…`，MASE4.868631。
- A2与CART候选hash均为 `b8e9a016c41e…`、预测hash为 `d4419ded287b…`，MASE2.727376；KEEP多损失2.141255 MASE。

同时保留有利切换，不能只挑失败：Solar/H192/target_block_10窗口 `e4399d34b121aeb0ce35bb165dc93aa65c7e7d2cb576f4835f8214cc88207c6a`，可见recent_level_shift为1.890909，高于0.129290，进入基础叶4选择KEEP；MASE2.389096优于A2/CART的3.016675，改善0.627579。两例完整输入/预测hash及逐节点值都在逐窗JSON中。

基础D2也不是在每个训练角色都稳健：T_fit中D2/A2为2.298952/2.376357；T_gate为1.365922/1.427442；T_check反而为1.350132/1.328637，T_acq为2.526080/2.317868。旧配置按T_gate全证据终态选择D2，检查集没有用于继续调参。这些开发差异解释了需要重新检验终态设计，不能用检查结果回填旧模型选择。

## 为什么没有继续取证

两个被选终态都只有一条通过gate的证据细化：基础叶4读取遮挡A2误差，决定维持KEEP或改A2。它们没有保留历史证据分裂，所以旧H32与目标H的获取标签都没有历史动作增量。

| 每个获取器的工具 | T_acq parent / 变体 | 正/零/负任务增益 | 加权均值 | 实际回归树 |
|---|---:|---:|---:|---|
| history | 18 / 108 | 0 / 108 / 0 | 0 | 根叶，输出0 |
| strict_mask | 18 / 108 | 0 / 106 / 2 | -0.000973289 | 根叶，输出该负均值 |

两个负遮挡标签都来自Solar父区间 `Solar:28864:29568`，UID分别为 `4628bad4ba6a5ed078c1fe65c5d6b80bbfed725e3f12541a99c3f84d4e4c6e57` 和 `af8f4f31722b039a513214b34d6b0474763d9a504869029a5b9659019b723ea4`，任务增益分别-0.086194和-0.036441。没有删掉这两条来制造正调用。

每训练叶至少16个独立parent，而获取器总共18个，`ParentRegressionTree.build`明确在少于32个parent时不分裂。它无法根据窗口区分工具价值。更关键的是，本批冻结终态在T_acq没有任何正工具任务收益，即使取消费用也不会出现正标签。两个lambda候选的LOPO得分都是0，按冻结平局规则选择lambda=0。

`make_value_labels`只扣一次 `lambda * (acquire_cost-stop_cost)`；`execute_one_step:377`读取已预测的净值，`:382`仅检查其严格大于0，没有再扣工具费用。STOP行没有tool收费，费用key无重复。gate是前置证据子树筛选，并非重复收取计算费用；不能把本次失败称作已证明“双重费用惩罚”。

## 信息、缓存与hash检查

- 无证据状态：原实现直接用dirty基础树；对完整冻结终态传入全NaN证据所得动作逐窗完全相同。`terminal.py:160`对所需证据非有限明确保留父动作，没有把未取得工具的NaN当0误路由。
- 普通CART旧主表属于全部取证对照，构造的是已取得全部证据向量。它的缺失值中位数处理另有有效性指示，并非失败标签填零。不能将该全证据CART直接当无证据部署模型；r2需要按合法状态分别训练。
- 本次学习/强制STOP重放的工具callback调用数均为0，`history=[]`、`evidence_hash=None`；过期terminal hash调用确实抛错。原终态JSON、checkpoint、获取器和标签hash一致。
- `SprintData.__init__`确实把全量候选、证据和train/dev evaluator缓存加载进离线进程，属于弱进程边界；本次逐函数数据流未发现这些隐藏值被无证据模型或获取前特征使用。这不等同于全面的运行时访问隔离证明。旧7例在线文件屏障只实际覆盖STOP，新r2仍须检验取证分支。
- 本审计只核验旧dev和已合法生成的train标签；未调用calibration/test数值解码器。原始观察是否有业务错误、金融point-in-time身份不由这些结果推出。

## 真实训练支持与扩展限制

| 来源 | 当前合法train parent上限 | 原T_fit/T_gate/T_check/T_acq | 64上限实际截断 | 未用独立区间 |
|---|---:|---:|---:|---:|
| ETTm1 | 59 | 29 / 12 / 9 / 9 | 0 | 0 |
| Solar | 44 | 22 / 8 / 7 / 7 | 0 | 0 |
| USTS | 7 | 3 / 1 / 1 / 2 | 0 | 0 |
| 合计 | 110 | 54 / 21 / 17 / 18 | 0 | 0 |

`agent_inputs.training_origins:14`使用 `[lo+512, hi-192]`、stride704后才取前64，三来源本来都不足64，所以没有被cap遗漏的当前协议独立train窗口。pilot的32-origin/H32输入也没有限制之后的110个正式train区间。增加seed、horizon、target siblings或重叠起点不能据此声称增加独立parent。

TimesFM实际已缓存的正式parent为dev26，T_fit/T_gate/T_check/T_acq全部为0。来源是 `scripts/v431_baselines/worker.py:42` 的 `if m['role']!='dev': continue`；旧TimesFM主表没有生成train五臂任务标签或历史/遮挡证据。因此必须补真实训练预测后才可按家族选择固定参照或拟合策略，不能照搬TimesFM dev最优ridge。

仅按未解码数值的在机元数据，可提出ETTm2 59、Exchange6、ETTh1/ETTh2各14、Crypto2、Oil4个名义704跨度train区间。它们尚未自动进入当前三来源协议：ETTh1与ETTm1、ETTh2与ETTm2需同步/降采样重复核验，不能直接相加；Exchange还缺现行原始时间/来源适配；Crypto的dev长度不足一个704跨度。金融身份与日历由独立核验决定，不能凭名称当作已核实金融数据。

## 对r2拟定训练分组的审核

原T_fit+T_gate合并为75个拟合parent，在本轮已取消gate筛参、规则预先固定且不再据T_check挑比例/超参时，没有新的parent泄漏。它复用了更多原train，**不是新增独立数据**。固定T_check17与T_acq18继续完整隔离。

25%/50%/100%的18/37/75个拟合parent应按预登记的来源内时间顺序形成嵌套UID子集，固定T_check不进入任何比例；固定强参照也只能用相同比例的训练损失选择。CART `min_samples_leaf=96`下，18parent的108个变体必为根叶，应按真实支持解释曲线。100%候选必须在生成T_acq工具价值标签之前冻结，学习曲线不能变成按检查结果挑比例的搜索。

T_acq仍只有18个parent，尚不能支撑每叶16的获取树分裂。扩大CART拟合支持与扩大获取器支持是两件事。如果后续需要预登记嵌套purged交叉拟合，基础参照、所有证据状态CART及其任何选择规则都必须整体位于相应外层验证父组之外；不能只重算获取标签而复用看过该父组的终态。
