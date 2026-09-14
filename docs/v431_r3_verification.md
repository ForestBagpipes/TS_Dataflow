# v4.3.1-r3 独立增量验证

验证入口为 `scripts/v431_r3_verify.py`，仅CPU，不加载模型，不读 `targets.npz`、`task_labels.json`、`evaluator_metadata.json`。系统文件访问hook在所有阶段拒绝上述部署评价文件。验证产物写入 `results/v431-r3/verification/<UTC>-<phase>-<suite>/report.json`，每次独立保存，不覆盖生产输出或旧失败记录。

## 阶段与状态

`--phase probes` 独立用 NumPy 重建当前context内的历史输入、as-of mask、缺口复制及评分mask，不以调用生产 `prepare_probe` / `score_probe` 作为唯一验证。核原始TSFM分位数或TimesFM原生point、实际request/response身份、缓存数组、五臂有限观测保护、统一当前MASE尺度、成对响应及发票别名去重。

`--phase models` 核冻结文件/策略SHA、54/21/17/18/26个监督parent与episode原行读取范围隔离、独立重建source-parent权重、固定alpha集合、状态支持、自身无证据STOP、完整输入KEEP、获取价与LOPO。`label_provenance.json`须由模型冻结SHA绑定；逐行使用T_acq五臂损失、dirty快照与实际后状态重放同一终态，验证正负净价值。该检查不代表继承的source尺度也按内部折隔离，具体限制见下文。

模型审计还核 `proxy_target_pairs.json` 和训练状态投影费用的冻结绑定、TRAIN角色范围及原始历史MAE到当前尺度收益的数值对应；用已拟合系数与仅TRAIN尺度独立换算原始收益单位斜率/动作截距，核残差模型加回未标准化的d。获取树直接遍历实际节点，不只信任配置：T_acq仅18个parent而每叶至少16个，当前协议下无法形成支持两个叶子的分裂；若实物为常数根叶，将明确记录，不能将其称为复杂的逐窗条件学习。

`--phase online` 按 `online-bolt|timesfm` 的实际11case协议核7个自然请求与4个控制case；检查输出先于评价解封、真实worker request/raw输出、配对标签/尺度、自然正价值与完整预算准入、STOP原动作、已实测long后故障回退、热延迟及启动/进程开销分摊。没有真实产物仍返回pending，代码实现不等于运行验收。

`--phase current` 只读17个T_check新位置的context、metadata、真实服务输出及已落盘决策，独立核原raw输入到受控删除、原base_uid与原始未来行范围的路由、两家族五臂当前预测与实际发票。仍不打开target值，不将目标路由核验称为独立重算当前MASE。

退出码：0全部通过；1有失败；2缺少产物或尚未完成覆盖。正在写入的session和仅完成吞吐pilot都会标pending；成功原子结果仍可独立核查。不会删掉失败或unsupported窗口，也不把缺项填成零。

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" scripts/v431_r3_verify.py --self-test
"$W2_CORE_PY" scripts/v431_r3_verify.py --phase probes --suite main
# 仅CPU使用既有Chronos环境的torch，运行官方AST纯预处理，不加载GPU模型：
"$W2_CHRONOS_PY" scripts/v431_r3_verify.py --phase probes --suite main --backend-inputs
"$W2_CHRONOS_PY" scripts/v431_r3_verify.py --phase probes --suite financial --backend-inputs
# 新批次增量审计只指定该session，不把通过子集解释成全覆盖：
"$W2_CHRONOS_PY" scripts/v431_r3_verify.py --phase probes --suite main --backend-inputs \
  --session results/v431-r3/probes/main/sessions/20260914T172035.358067Z-bolt
"$W2_CORE_PY" scripts/v431_r3_verify.py --phase models
"$W2_CORE_PY" scripts/v431_r3_verify.py --phase current
"$W2_CORE_PY" scripts/v431_r3_verify.py --phase online
```

`--backend-inputs` 使用 `src/introact_ts/v431_r3/backend_inputs.py` 提取已安装官方纯预处理AST：Bolt的InstanceNorm/16步Patch，以及TimesFM实际插值、左填充和mask。每个实际长短五臂候选均保存模型输入形状、值/mask hash和官方代码SHA。若模型看到的信息相同，写 `response_invalid_same_actual_information`，不改64、不补未来，也不将形式上的长度不同当有效测量。

## 待生产输出后的必要核对

canonical candidate/forecast缓存schema冻结后，需要核原子探针ID与物理缓存ID分离：相同输入的共享预测可节省离线计算，但部署发票必须支付原始实际费用，不能用cache查询耗时冒充。`raw_worker_session`须追溯实际request输入和原始point；五臂相同输入只计一份预测。

终态和获取标签阶段必须核：TRAIN reference来源、fit/gate/check/acq parent隔离、source宏平均/parent权重、固定alpha集合、无证据状态不读隐藏测量、同冻结终态前后真实损失差、负值标签保留、模型更新使旧标签失效。

在线阶段必须核：自然获取与强制分支测试区分、取证前可见状态、完整分支预算、STOP自身基础动作、故障发票及显式回退、最终实物预测与原始worker一致、无预计算证据偷读。修正隐藏证据或STOP错误仅属于实现修复，不单独构成研究成功。

截至接口建立，本文件不声明真实probe、训练模型或自然在线验证已经通过；结果以各次不可覆盖的report为准。只补本轮触及的检查，不机械重跑r2整套测试。

## 已完成的真实检查（2026-09-15 01:25后）

金融准备审计 `verification/20260914T172316.162745Z-probes-financial/report.json`：48个历史规格/数组、4个冻结文件及parent隔离通过，失败0；当时还没有96个两家族原子预测，整体pending。该报告没有读取金融future。

首次主集合审计 `verification/20260914T172321.814522Z-probes-main/report.json` 保留252项失败。原因是**验证器初版误把所有非KEEP候选都要求为有限填补**；旧冻结A4本来允许在协变量/训练支持不足时精确回退A0_NATIVE。该约束不适用于A4，不能据此说模型失败。修正后的独立审计只在明确的上下文支持不足且输出与Native逐元素相等时接受该回退，并在 `explicit_ridge_fallbacks` 保存原因；其它非有限输出继续失败。

生产Collector丢弃了ridge返回的status/reason，不能把数组相等当成成功修复。本次由独立支持重建补回归因，不修改冻结producer。主执行另有 `scripts/v431_r3_ridge_support.py` 补遗用于全量缓存核对，费用仍保留已发生的ridge尝试。

Bolt20parent真实pilot的显式session审计 `verification/20260914T172554.571572Z-probes-main/report.json` 已通过：484个原子规格与记录（包括落在所选parent中的check-only新位置），其中280真实completed；56个有效长短对、280个五臂官方预处理比较，`actual_preprocessing_identical` 为0。历史MAE、当前统一尺度下的收益、原始分位数/point、request-response/model环境身份、候选与预测cache和发票去重均通过，失败0，pending0。

该通过仅覆盖指定Bolt20parent session。主集合完整两家族的6664条原子记录、金融真实预测、冻结终态与自然在线仍需各自审计，不能从吞吐pilot推断方法收益或全量通过。`--session`按新批次核验，旧报告保持；同一实际长短输入对的官方纯预处理在一次审计内复用计算，逐臂hash仍分别记录。

随后Bolt完整主账本审计 `verification/20260914T173158.736092Z-probes-main/report.json` 通过：3332规格/记录、2624真实completed、708unsupported、528组长短配对、2640逐臂官方预处理比较。两份原始worker session（包括合法复用pilot）原始输出和费用均核实；仍只是Bolt家族的全覆盖验证。

TimesFM20parent增量审计 `verification/20260914T173620.440390Z-probes-main/report.json` 通过：484记录、280真实completed、56配对、280逐臂官方预处理比较，模型实际输入相同0。验证直接读取原生TimesFM point/input/quantiles，并核对跨请求cache hit使用原始非hit发票计价。最大TimesFM账本、金融实物输出与终态/在线仍按后续report更新。

冻结模型实物审计 `verification/20260914T174655.995647Z-models-main/report.json` 通过：两家族共6个冻结终态、5580条TRAIN历史证据/当前损失配对、512条净价值标签及512次同冻结策略前后动作重放，失败0、pending0。配对分母按每家族T_fit1620、T_gate630、T_acq540记录，包含各个预登记证据状态，不能视作独立样本。训练投影开销分别为Bolt0.591183秒、TimesFM0.520701秒，且由冻结文件绑定。

获取器实物每工具只有16个有效T_acq parent，全部是常数根叶：Bolt的H32/H/control值分别为−0.078488/−0.007704/+0.007354；TimesFM为+0.058152/+0.030881/+0.003284。Bolt256条标签含30正、199零、27负，TimesFM256条含43正、179零、34负；没有删除零/负标签。此时合法支持和预算决定逐窗可调用性，尚无学得逐窗树分裂；自然在线是否真实调用及任务收益仍须单独报告。

TimesFM完整主账本审计 `verification/20260914T174634.848861Z-probes-main/report.json` 通过：3332规格/记录、2624真实completed、708unsupported、528组长短配对、2640逐臂官方预处理比较。4个实际worker服务目录涵盖两个家族pilot与最大任务的合法复用；缓存的原始模型输出、原非hit发票及实际模型文件SHA通过。至此Bolt与TimesFM主集合均完成各自全量语义验证；此结论不代表下游方法收益成立。

金融两家族实物审计 `verification/20260914T174733.355988Z-probes-financial/report.json` 通过：48个独立context几何、96条两家族原子记录、16组有效长短对、80逐臂官方预处理比较、2个真实服务目录。主集合与金融此次实际预处理输入相同均为0。金融仍只有2个独立parent，H192中因复制缺口越界而unsupported的组合保留；验证没有读取金融future，也不扩大独立确认支持。

17个新位置的当前预测审计 `verification/20260914T175438.302763Z-current-main/report.json` 通过：17条原T_check raw到`[358,409)`受控删除的独立重建、原base_uid及`[context_end,context_end+192)`目标路由、2个真实服务目录、170条五臂原始预测/费用、1598条已评价决策hash绑定。没有改变原未来、评分mask或parent，也没有重新读取target值；此审计不代替主统计脚本的MASE重算。

真实在线初版审计 `verification/20260914T175143.956295Z-online-main/report.json` 保留1项失败：验证器将完整raw的运行模式也机械要求为预登记入口`learned`，而生产按明确no-op契约转为`stop`。修正只允许独立核实完整target时的该模式转换，未改生产代码或输出。

两家族在线实物审计 `verification/20260914T175232.000267Z-online-main/report.json` 通过：22个case中自然14个、控制8个；真实候选/TSFM原始point、历史mask/尺度、同冻结策略、隐藏文件屏障、工具后故障费用、零预算与总进程费用均通过。Bolt自然7次请求中6次control共12原子，TimesFM6次H32共6原子；各自自然热请求及11请求分摊后完整费用的超预算数均为0，受控零预算各1例超支保留。

**延迟范围须区分。** Bolt/TimesFM完整11请求验证进程分别26.271817/27.357047秒；实际模型启动分别9.057486/9.410971秒，另有进程开销7.144850/6.708854秒。`total_seconds`把启动与其余开销分摊给11请求；自然请求热耗时范围Bolt0.170853–2.015578秒、TimesFM0.258983–1.705230秒。该分摊账单可核完整费用，但不是单个冷请求延迟：模型启动本身已超过3.5秒，不能声称单请求冷启动满足预算。

## 继承的尺度范围限制

独立源码审计发现，本轮`S_t`来自原source完整TRAIN范围，包含较早train origin之后的原始数值，也包含内部T_gate/T_check/T_acq段；r3将其用于d、κ、预测分歧和ψ的MAD差分母。因此上述通过只确认**固定评分单位一致、监督parent与模型拟合/获取边界一致**，不确认所有内部预处理均purged或逐origin point-in-time。旧DEV位于整个TRAIN之后，calibration/test未参与该尺度；也不能误报为DEV未来泄漏。详见[实际尺度来源与范围](v431_r3_code_audit.md)。本轮不据结果改动冻结分母或重拟合，保留该限制。

## 新位置当前任务误差独立复算

另用 `scripts/v431_r3_verify_current_loss.py` 在冻结模型、170份真实预测及评估全部完成后，独立重算原17个T_check parent已经使用过的raw/H192目标：170组MAE/MASE与1598条决策全部一致，报告 `verification/20260914T175839.373259Z-current-loss-main/report.json`。这个单独离线评估器明确解码既有TRAIN目标34次（两家族），不读取新源未来，不解码calibration/test；不能与主无标签语义验证器的读取范围混淆。

## CPU 定向回归及初次失败

本轮 probe 9项、response/acquisition 17项定向测试通过，未机械重跑旧58项。response首次14通过/1失败是测试把不在五臂中的A1_LINEAR当成“另一合法参照”，期待错误消息与实际“未知身份”不一致；修正测试使用五臂内另一身份，生产身份检查没有放宽。首次日志保留 `logs/v431-r3/response-tests-first-failed.log`，最终17项为 `response-tests.log/xml`。
