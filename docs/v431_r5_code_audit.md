# v4.3.1-r5 真实代码与缓存审计

## 当前部署任务与历史试验分开

| 环节 | 实际入口 | 输入和输出 | 费用与边界 |
|---|---|---|---|
| r4 最终账本 | `scripts/v431_r4_run.py:load_batch` | 原 TrajectoryBatch 加原始 response 支持的热/冷修正 | 外层报告尺度与 origin 学习尺度保持分别存储 |
| 当前五臂原生预测 | `src/introact_ts/v431_r4/trajectory_dataset.py:load_data` → `R2Data` / `ExternalEvaluationData` | 当前 L512、H96/H192、原五个合法输入版本的真实点预测 | 复用已发生的治理及最终预测费用，不重新执行 TSFM |
| r5 离线桥接 | `src/introact_ts/v431_r5/dataset.py:load` | 逐版本核验 input hash、预测 dtype/hash，导出当前预测和各组件费用 | 数据容器含 TRAIN/旧 DEV 监督，**禁止部署端加载** |
| 免费历史覆盖 | `dataset.py:free_history_coverage` → `prepare_probe` → `visible_descriptor` | 仅当前已观测 input、mask、availability、历史前缀几何，输出协变量覆盖 | 不调用 TSFM；CPU 准备时间仍计入请求费用 |
| 历史对照预测 | `scripts/v431_r3_fit.py:load_probe_ledger` 的 long atom | 历史输入416/320，历史H96/H192真实预测 | 与当前完整512点任务不同；历史模型费用按原H工具收费 |
| 当前响应 | `scoring.py:response_features` | 已查询 p0、pa 和 origin S，输出固定七项 | 不读取未来评分 mask、未来目标或未查询预测 |
| 训练收益 | `scoring.py:paired_training_rows` | 当前参考 MAE/S 减当前候选 MAE/S | 只用于合法 TRAIN；不是重建 NMSE |
| 费用拆分 | `scripts/v431_r4_hot_costs.py:reprice_invoice` | 原 candidate / forecast 逐条 charge 及显式加载映射 | cold+hot严格守恒，逐条分类，不按总冷费用猜测分配 |

五臂保持 Native KEEP、FFILL、单变量 TS-ICL、多变量 TS-ICL、context ridge。没有预测后残差臂。账本记录请求动作、实际动作、alias、unsupported 原因；最终有效观测保护沿旧候选保持。r5没有改变原模型输入，因此本轮尺度/几何/评分加工无需重算原生预测。

## 已确认：r4 历史覆盖本身不需要调用历史模型

r4 `JointPolicy` 中使用的 `long:covariate_coverage`，来源是 `visible_descriptor(prepared.view)` 对历史前缀当前可得协变量 mask 的统计。r5在调用任何模型之前由同一 `prepare_probe` 重新构造该前缀；历史截断、按当前缺口相对位置复制、as-of availability 遮挡均不改变。

真实账本复核：main每家族816窗，其中768个支持的历史视图覆盖值与旧long descriptor逐窗相同，48个原本不支持的视图保留NaN与具体原因。金融每家族12窗全部支持且一致。这个**覆盖统计**已归为第14项免费输入 `known_history_covariate_coverage`；历史预测误差和模型响应仍必须付费取得。这里确认的是信息来源与可避免的模型执行，不宣称修复后预测提升。

## 旧接口与旧标签不等同于当前任务

`src/introact_ts/probe.py:probe_window` 在传入序列内部选取预测/评分区域，旧注释已讨论尾部H点与裁剪后时间位置变化。`experiments/tsfm_counterfactual_pilot.py:compute_tsfm_signals` 也包含遮挡重建与内部历史信号。两者都没有被当作本轮当前完整任务预测入口。

`experiments/v33_labels.py` 以 `canonical_nmse(original, clean)` 减 `canonical_nmse(edited, clean)` 定义 `true_repair_gain`。该字段确属重建监督，r5训练路径完全不调用它。本轮原始MAE来自原当前目标评价记录；不同动作共用当前目标、评分mask及目标H。收益监督用origin可见尺度，报告MASE仍用外层TRAIN冻结尺度。

## 缓存身份和数值协议

每个版本的 `cache_metadata` 保留：source、parent、raw_start、origin、L/H、目标mask hash、辅助mask hash、时间索引hash、availability hash、输入版本hash、骨干repo/revision、native设置及执行适配代码hash、原预测dtype/hash、候选dtype、实际动作和alias、完整热charge与显式cold费用。记录组合身份的 `cache_key`，不以动作名或窗口编号单独复用。

Bolt：原 Chronos-Bolt 原生中位分位点预测，模型bfloat16、输入float32。TimesFM：原2.5-200M原生point输出，max_context512/max_horizon192，完整编译配置由冻结 `scripts/v431_baselines/worker.py` 的代码hash绑定。模型版本沿原实际identity，并未使用TimesFM-3或Chronos-2替代。

本次main每家族4080个、金融每家族60个预测及对应candidate hash全部精确核验，未以宽松误差代替缓存身份。新增覆盖和学习特征不进入原模型输入。未来有效评分mask不作为部署特征；几何主模式使用unknown权重可行域，由运行时只接收已查询预测。

## 实际生成和失败记录

产物：`results/v431-r5/data/{main,financial}/{bolt,timesfm}.joblib`，同目录包含支持表、覆盖审核及总status/file hashes。main角色保持fit54/324、gate21/126、check17/102、acq18/108、旧DEV26/156（parent/相关变体）。金融2/12，不是独立确认。

实际命令：先 `source scripts/env_new_server.sh`，再 `"$W2_CORE_PY" scripts/v431_r5_prepare.py`。最终完成日志为 `logs/v431-r5/prepare-second.log`。首次输出support JSON时发生 NumPy int64不可序列化错误；修正为Python int，原尝试和日志保存在 `data-attempt1-serialization-failed` 与 `prepare-first.log`，未覆盖。首次没有运行模型或使用新标签进行方法选择。

调用方费用注意：r5每请求只收一次 `feature_seconds`，每个实际查询版本再收 `governance_costs` 与 `forecast_costs`（同输入原生推断复用须按实际身份去重）。不能额外叠加已含旧feature费用的 `batch.action_costs`，也不能因为原结果已经缓存而将试运行费用设零。

本审计只证明这些代码与账本边界，r5几何收益、选择性执行及最终预测优势仍以共同开发表和真实在线结果为准。
