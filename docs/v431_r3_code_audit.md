# v4.3.1-r3 入口、历史证据与费用审计

审计日期：2026-09-15，Asia/Shanghai。本文区分源码事实、已有运行复核和仍待运行的部分，不把代码存在或接口通过写成方法收益。旧版本和失败原始记录保留。

## 五臂的实际语义

当前集合固定为 `A0_NATIVE / A0_FFILL / A2_SINGLE / A3_COV / A4_RIDGE_CONTEXT`，由 [Collector.pools](../src/introact_ts/v43/agent_collect.py) 构造；五臂名称不等于每个窗口具有五个不同数值输出。

| 臂 | 实际代码与行为 | 支持与限制 |
|---|---|---|
| A0_NATIVE | 原 dirty target 直接进入该家族的正式预测后端 | 治理层保留 NaN；后端自己的原生预处理是模型定义的一部分，不能称所有家族内部输入处理相同 |
| A0_FFILL | [prepare_model_input](../src/introact_ts/v43/candidates.py)先用第一个可见值补前导缺失，再向前填充 | 全缺失输入明确报错；只使用传入 context 内的值 |
| A2_SINGLE | [tsicl_worker.predict](../src/introact_ts/v43/workers/tsicl_worker.py)调用真实固定 TS-ICL `impute`，不传 covariates | 已观测点在 adapter 边界用原始存储值还原，保证观测点逐字节不变；完整输入直接保留原值 |
| A3_COV | 同一正式 TS-ICL，加传当前视图的过去协变量 | 不是原生多变量 TSFM 预测器；历史视图先实施 as-of 可用性遮挡，不能带入历史 origin 后的 covariates |
| A4_RIDGE_CONTEXT | [ridge_candidate](../src/introact_ts/v43/p2_candidates.py)在该视图内拟合；最少 32 个有限 target，维度上限 8，alpha=1 | 缺口处协变量覆盖不足 0.5 或训练支持不足时，函数明确返回原 dirty 输入及 `unsupported/fallback=A0_NATIVE`；不读取旧 A4_FULL 的额外历史 |

[verify_impute](../src/introact_ts/v43/schemas.py)检查 UID、shape、dtype 及观测值不变。`Collector.forecasts` 对同请求相同候选输入保留 alias，并调用真实后端。Bolt 取正式分位输出中的中位数；TimesFM 保留官方原生 point，不能擅自改取 quantile median。当前代码没有将 Chronos2 当作第二家族。

**A4 支持元数据缺口：** `ridge_candidate` 本身返回明确原因，但旧 `Collector.pools` 使用 `ridge,_` 丢掉了 detail。于是候选数值和预测可能完全等于 native，缓存中却只有 A4 名称。本轮不修改正在运行的冻结 producer，通过 [v431_r3_ridge_support.py](../scripts/v431_r3_ridge_support.py)从冻结输入独立恢复原因并核对候选哈希。

首份[支持账本](../results/v431-r3/ridge_support/20260914T172409.431710Z.json)覆盖 main+financial 的 3380 条 lineage、2274 个独立 payload：714 个完成 ridge 拟合、650 个明确 unsupported 回 native、910 个无需修复。当时已完成的 879 个候选 cache 全部相符，另外 1395 个仍在生成；待生成不计为通过。这里的 native alias 不能作为“ridge 独立成功”或缺失值重建成功。

主集合与金融两家族 probe 完成后，[最终候选哈希复核](../results/v431-r3/ridge_support/20260914T174722.830882Z.json)用 1.162 秒核对了全部 2274 个 payload，均与真实候选缓存完全一致，待生成数量为 0。此次只复核既有候选数组、缓存 SHA 和冻结 ridge 源码，未重复拟合，也未读取部署 future 或 held-out 标签；650 个不支持记录及其 native 回退仍完整保留。

## 旧测量与新历史边界

1. [v35_acv_probe.build_candidate_jobs](../experiments/v35_acv_probe.py)先对整个 `series` 调用 `rerun_operator`，得到完整治理输出 `y`，随后从 `y_q` 截取各 anchor 的 APPLY context。[v35_acv_common.rerun_operator](../experiments/v35_acv_common.py)确实接入正式 `apply_action`。其 anchor 标签取原输入有限值，具有标签字段白名单，但这一顺序没有证明“治理只看历史 anchor 之前”：使用全窗统计或右侧信息的算子可能受 anchor 后信息影响。因此不能直接把旧 ACV 数值当成 r3 的严格历史部署收益，也不能未经逐算子核查断言每一条旧测量都泄漏。
2. [旧 probe_window](../src/introact_ts/probe.py)先 `materialize_for_probe(series)`，再构造不同长度的后缀预测，已有 multi-view/context-length 操作。旧 `multiview_disagree` 是按时间平均的预测跨视图标准差除以固定尺度；它不是新有符号 `d_long-d_short`。r3 不能把“使用不同长度”本身宣称为全新模块。
3. [v431.aligned_views](../src/introact_ts/v431/data.py)先调用 `as_of(e,512-H,H)` 得到原 dirty 前缀，再由 [v431_collect_history.py](../scripts/v431_collect_history.py)独立生成治理候选。其同 origin H32 对照复用同一前缀治理输出，因为只改预测跨度。它不存在 v35 的“先治理整段再截历史”顺序；不能把该旧问题泛化到最新 r2。
4. r2 新 TimesFM 历史重用上述合法前缀的候选输入；独立复核已检查 416/320 输入边界、原始 mask、availability、checkpoint 与原生预测。r2 的归一化曾使用 `context_scale`（当前 dirty 的 MAD），它不是本轮正式 MASE 尺度；r3 通过 raw MAE 和原冻结正尺度 `S_t` 明确换算。
5. [r3.prepare_probe](../src/introact_ts/v431_r3/probe.py)先截原始 dirty/as-of 输入，再按距当前 origin 的固定 lag 复制各通道可见缺失，之后才送入 Collector 独立治理。原有 dirty 缺失不恢复，不读取 clean。长短有同 origin、同 H 和同一当前可见历史标签 mask；`availability<=当前末端时间` 与有限值共同决定评分资格，最少 `max(16,ceil(H/2))` 个点。

固定几何是 H96/H192 的 long 长度 416/320、short 长度 352/256；普通 H32 使用 origin 480；等费用普通回测另加 origin `512-H-64`。H192 中原 gap `[230,281)` 平移到 `[38,89)`，短窗口起点 64 放不下，必须 unsupported。17 个额外 check-only 变体使用 gap `[358,409)`，不增加独立 parent，不进入 fit/gate/acq；其当前五臂预测由独立 current 队列生成。

## 任务监督、旧 STOP 与新状态

[v36_pair_dataset](../experiments/v36_pair_dataset.py)提供动作对、相反方向配对和 evaluator 字段命名空间的工程经验；其 `eval_true_gain/true_loss` 来自旧 clean 目标，不能直接当作 r3 的当前 TSFM 部署收益。[v40_counterfactual_bank.stage_evaluate](../experiments/v40_counterfactual_bank.py)将 `compute_action_labels(...,clean)` 的 `true_repair_gain` 写为 `gain`，并保留 before/after NMSE；不能改名为本轮未来任务 MASE 改善。[v41_mask_counteract.mask_features](../experiments/v41_mask_counteract.py)提供仅 dirty 的缺口位置、长度和两侧支持描述，相关思想可复用，但旧 clean 监督与校准规则不进入当前 online 特征。

r3 的 `d=(MAE_ref-MAE_arm)/S_t`、`kappa=d_long-d_short`、`z=((512-Lq)/64)*kappa` 使用实际取得的历史测量与原冻结评分常数。`ProbeResult` 不含部署 future 标签；当前任务监督由 train evaluator 处理。ψ 的几何、覆盖和 MAD 差分子来自可见输入，没有 source 名称或真实污染类别；MAD 差的分母 `S_t` 具有下述范围限制，不能把整条归一化路径称为逐 origin 可见统计。

**`S_t` 的实际范围限制。** [run_p2](../src/introact_ts/v43/p2.py)在完整 `data_manifest.split_bounds.train=[lo,hi)` 上调用 `read_rows(...,'train')`，对 target channel 0 计算 [mase_scale](../src/introact_ts/v43/task_labels.py)的有限季节差绝对均值。[run_collect](../src/introact_ts/v43/agent_collect.py)直接复制 P2 的常数；[R2Data](../src/introact_ts/v431_r2/data.py)与 [r3 prepare](../scripts/v431_r3_collect.py)继续复用。三个实际常数如下，范围均为原始行号的半开区间：

| 来源 | 生成范围 | 季节周期 | 冻结 `S_t` | train 当前 cutoff 最小/最大 |
|---|---|---:|---:|---:|
| ETTm1 | `[0,41808)` | 96 | 2.5160591666407006 | 512 / 41344 |
| Solar | `[0,31536)` | 144 | 5.013664309378185 | 512 / 30784 |
| US_Term_Structure | `[0,5595)` | 5 | 0.1046207248188459 | 512 / 4736 |

因此全部 110 个 train parent、660 个原 episode 的 `S_t` 都包含各自当前 cutoff 之后的 TRAIN 行，也包含 T_gate/T_check/T_acq 段的原始数值。原 P2 只将其作为 benchmark 评分分母，r3 又将其用于 probe gain、κ、原始预测分歧和 ψ 的 MAD 差归一化；本轮不具备严格逐 origin 的尺度估计或内部折间隔离的预处理，内部 check 不能被描述为连尺度预处理也完全隔离。原 DEV 的所有 context 均晚于这整个 TRAIN 范围，calibration/test 未参与该常数，不能把这一限制误述为 DEV/calibration/test future 被模型读取。

[范围及源码哈希审计](../results/v431-r3/verification/scale_scope_20260914T175514.508951Z.json)确认三个常数在 P2→agent→r3 间完全相同，生成函数源码仍与 P2 producer SHA 一致，并复用已有独立原始值复核；此次没有再解码任何源数据数值。正的 source 常数不改变同一 episode 的原始 gain 符号、历史 argmax 或 κ 符号，但不能据此声称跨 source 的学习、正则化与阈值选择完全不受影响。当前分母和冻结模型保留，结果必须连同这一协议限制报告；若另行验证严格 as-of 尺度，需要独立登记实验，不能覆盖本轮结果。

已完成的 r2 复核见 [v431_r2_verification.md](v431_r2_verification.md)：冻结先于 648 条获取标签，75/17/18 parent 分离，8160 个实际任务误差和 4992 个共同决策相符。旧 v4.3.1 全 STOP 路径等于其 dirty 树，不等于 TS-ICL；[逐窗审计](v431_r2_stop_audit.md)已定位差异，不能把旧退步归因于 STOP 指令本身。r2 修正后的 Bolt 每预算 156 行全部 STOP，与固定 TS-ICL 的真实输入和预测一致。修正 STOP 只解决实现行为，不证明获取方法有效。

对新 [state_from_results](../src/introact_ts/v431_r3/response.py)的初次审读确认：只读取请求工具的原子结果，缺失 short 不填实测零。发现初稿 disagreement 使用收益标准差，即两点时的 `abs(kappa)/2`，与旧 raw prediction multi-view 统计不同；已反馈该文件 owner，最终表必须按最终实现和冻结记录命名，不能混称旧分歧复现。

owner 随后已修正并经再次源码核对：disagreement 使用同一 long/short 的真实 `raw_predictions`，对每臂计算全跨度平均的两视图预测标准差再除以 `S_t`，同时检查原始预测哈希。这复用了旧统计形式，但视图几何改为本轮固定长度对照，应称同新测量上的旧分歧统计对照，而非完整旧 ACV 复现；control 仍独立使用有符号 κ 与原定长度因子。

## 缓存、在线与费用

`p.input_hash` 保留 base UID、spec 和输入血缘；独立 `canonical_view_hash` 使用实际 target/raw mask/covariates/timestamps/availability/H。缓存再绑定模型、环境和源码身份。同片先去重再 alias 回原 UID；H96/H192 下相同 H32 payload 不重复推断，两家族复用真实 TS-ICL 候选。仅成功且哈希匹配的 cache 可用；中断孤立文件保留，新尝试写新文件，不覆盖失败或填预测零。

TimesFM 内部跨请求命中重计原始唯一调用的实际预测费用，不能把 lookup 时间当部署模型费用。每条 probe 账单保留准备、候选、去重预测和评分费用；unsupported 仍记录实际准备费用。训练生成的全集是 evaluator 账本，不代表在线免费取得候选或证据。

[LiveRuntime.final](../src/introact_ts/v431_r3/runtime.py)按已选 arm 分支生成：A2/A3 仅调用所选插补模式，A4 保留实际 support detail，随后只预测所选候选。该接口没有在 STOP 前无条件生成当前五臂。`LiveRuntime.probe` 则在工具真正调用后对自己的前缀独立构造五臂、取得实际历史预测，墙钟覆盖工具准备、治理、预测、评分和 ψ，不能再重复添加这些组件。

初次审读还发现 offline 的 `model_identity_hash` 含 cache producer，而 online 使用模型记录哈希，两者不是同一身份空间；已反馈 root，应分别记录 checkpoint 与 measurement producer，并用实际 revision、原始输入和预测数值核验等价，不能假装二者 hash 相同。长短经过官方截断/patch 后是否保持不同有效输入、完整 online 的读取屏障/自然调用/故障费用与回退，仍须对应实测或独立复核，本文不先填通过。

对 [v431_r3_online.py](../scripts/v431_r3_online.py)的进一步源码检查：7 个自然请求加 4 个控制请求先完成实际最终预测并写 `live_arrays.npz`，随后关闭服务，最后才开放 evaluator，`R2Data` 的首次导入和读取位于开放之后。自然 STOP 使用 `policy.choose(x,None)` 的固定参照，完整输入选择 KEEP。故障分支的已付工具费用与一次实际 fallback 相加；最终热请求费用重新按 initial、各实际工具、一次 final 和剩余开销重构，没有再次叠加 guarded-fetch 总账单。外层进程再独立分摊加载和其余生命周期费用，控制请求不得算作自然策略收益。

以上是源码路径检查，尚不是在线运行通过。已要求 root 在最终验收中同时比较实际候选与预测的严格哈希及数值容差，单独报告两者；模型/终态/获取器 manifest 接口待拟合产物冻结后精确核查。真实服务失败后若备用实际预测也无法完成，必须保留失败记录，不能制造 fallback 结果。

root 随后已补 `checkpoint_record_hash` 与测量 producer 的独立身份说明，并在 evaluator 比较阶段补上候选数组、候选哈希、预测数组和预测哈希的独立字段。字段存在不等于实际通过，最终以真实在线产物为准。

## 已完成与待完成

9 项本轮定向 CPU 测试通过，含复制缺口、短输入不支持、availability、统一尺度、同 hash 配对、canonical 去重和完整 cache resume。main 已准备 816 原 episode +17 check-only、3332 个原子 probe（2624 prepared、708 unsupported），保持 110 train/26 dev parent。金融附表 12 episode/2 parent、48 probe（40 prepared、8 unsupported）。额外变体与探针均不增加独立样本。

首次 20-parent Bolt 吞吐进程实际完成 **74.030 秒**，484 个原子记录中 280 完成、204 unsupported；包含所选 parent 的一个额外 check 变体，因此不是 480 条。此批用于吞吐与接口验证，不用于按表现选择模型。后续整批、TimesFM、金融及 check-current 按 [统一队列状态](../results/v431-r3/queue_status.json)执行，方法效果、共同主表与在线验收以最终独立报告为准。calibration/test 继续封存，PICS_joint_relabel 不变。

[独立统计脚本](../scripts/v431_r3_statistics.py)已完成 main、原 T_check、新缺口组合、金融四套核对；[最终不可变快照](../results/v431-r3/statistics_runs/20260914T175020.329898Z/statistics.json)包含 376 个方法与 family 组合、26978 条逐窗记录的来源/parent 宏权重重算，另有 144 项配对比较。机制对照显式保留共同支持范围及终态回退，完整主表不删除不支持窗口。新增 17 个检查变体与原检查复用 parent，不是新增独立样本。各来源时间相邻 2-parent block bootstrap 为描述性分析；金融仅 2 个 parent、区间退化，不能解读为显著性。金融 TimesFM 高预算 agent 的 8 条实际超预算记录保留在表内，不能将其收益称为同预算优势。此阶段不包含尚待实际执行的在线验收。
