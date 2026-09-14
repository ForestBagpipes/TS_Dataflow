# v4.3 旧入口审计与首轮契约验收

日期：2026-09-14；运行位置 `/home/vipuser/work/work2`。本记录是 CPU 工程验收，非方法晋升。历史 incumbent 保持 **PICS_joint_relabel**。源码基于迁移后的当前工作区，未用旧 Git HEAD 覆盖。

## 静态审计结论

| 入口 | 实际代码依据 | v4.3 处理 |
|---|---|---|
| `experiments/v33_labels.py:compute_action_labels` | `before/after` 均针对 clean 重建，`gain=before-after` | 保留原实现；新增 `v43/task_labels.py`，比较同一原始 future 上的预测误差，repair 字段未知时为 null |
| `experiments/v41_mask_counteract.py:calibrate_tau` | `h/k` 和 CP 上界使用未加权计数，w 只乘 B&S coverage | 相同阈值仅说明该覆盖目标的实现行为，不能否定真正风险重加权；旧结果和失败结论保留 |
| `experiments/v42_portfolio_act.py:gain_lookup` | 仅收 `family == TSICL_LONG` 的 gain | 新任务路径每个请求必须有对应预测和标签；缺失不记 0 |
| `experiments/v42_portfolio_act.py:stage_phase0b` | 已在 `merged` 的 uid 直接跳过，无 gain 的候选也跳过 | 旧 integrated oracle 不能代表完整候选统一复核；完整新决策器尚待实现 |
| `experiments/v40_counterfactual_bank.py:isolation_report` | 检查 parent UID、内容 hash 和 UID split 交集 | 新 `audit_reads` 检查 source/panel 原始区间及 parent 跨 split；不同 hash、不同通道仍须同时间隔离 |
| `experiments/downstream.py:make_pairs` | `s=s[np.isfinite(s)]` 删除时间点后切窗 | 新路径不复用此切窗；先固定原始 context/future 区间，只治理 context |
| `src/introact_ts/backends/__init__.py:make_pool` | 部分后端失败时 `[skip]` 并返回剩余池 | 新 worker 固定两个真实模型身份，整批身份/shape/hash/单位失败即拒绝，不使用旧 pool |
| `src/introact_ts/backends/chronos.py:encode` | token 轴分成 `n_layers` 块，源码注明不是逐层状态 | 不将其称为真实逐层特征；v43 worker 不使用该代理表征 |
| `experiments/v40_action_critic.py:_moment_encoder` | 真实 `model.embed` 输出在中间轴平均池化 | 与前项区分；该池化 embedding 也不等同于真实逐层轨迹 |

这些是针对具体路径的静态结论，没有据此宣称全部旧实验泄漏，也没有重算旧数值。缺失旧节点三个缓存仍只阻断旧精确复现分支。

## 已实现与测试范围

`src/introact_ts/v43/` 已新增独立数据对象、原始行区间、延迟可见性、不可变数组、完整精度 hash、任务标签、严格响应校验、文件协议、嵌套残差、最小可见状态工具选择与适配 pair 完整性接口。

- Episode 不含 clean、future、污染类型或任意 metadata；timestamp、target、Z 和 availability 持有不可写 bytes 副本。插补仅写原始 dirty context 的 NaN，有限值与时间轴严格保持。
- development reader 在读取前拒绝 calibration/test。TIME NPZ 仅解码指定 train/dev 行；不加载含 object 的 channels 数组，不以 `allow_pickle=True` 读取数据。
- outer mask 先冻结；每个外层训练残差的基础插补同时遮挡外层块和当前内层块。局部输入缓存去重为 7 类；这个计数不等同 GPU kernel 数。真实基础模型成本由 worker 记录。
- 历史 as-of 使用当前 context 前缀，并重新应用该时刻的 availability；不补读 context 之前的数据。
- 模型原生 NaN 与公开固定 forward-fill 分开；不适用回 KEEP；模型失败单列且使比较无效，不改变 origin 分母。
- 未获取工具的 cache 不传给可见状态或第一步选择；此处只验收选择接口，工具价值模型尚未训练。
- 适配接口仅验证 pair ID、共同 Y 和固定测试输入 hash；没有执行训练，也没有声称完成分组 OOF 适配治理流程。

测试入口：`source scripts/env_new_server.sh` 后运行 `$W2_CORE_PY scripts/run_v43_contracts.py`。每次新建日志目录，保存 pytest 原始输出、JUnit、代码与测试 hash、resolved config、解释器、PID 和耗时。`results/v43/semantic_gate.json` 是最新报告的副本，原始运行报告保留。真实 pilot 拒绝过期的代码/config/test gate。

测试已实际达到 **40 passed**；确切最终运行时间与代码 hash 以 `results/v43/semantic_gate.json` 为准。包含真实 CPU 子进程文件往返、非零退出、payload 篡改测试；测试替身不作为模型验收证据。

## 原始数据及 pilot 输入

已在两个独立 core 进程生成原始索引清单和 context hash，未读取 future 标签。最新输入清单路径以 `docs/HANDOFF.md` 本轮追加记录为准。

| 来源 | origin 数 | 限制 |
|---|---:|---|
| ETTh1 | 6 | 原 CSV 时间戳，小时网格验证 |
| ETTh2 | 6 | 原 CSV 时间戳，小时网格验证 |
| ETTm1 | 6 | 原 CSV 时间戳，15 分钟网格验证 |
| Crypto | 3 | 60% train 仅容纳 3 个不重叠 L512/H32；15% dev 不足 544 行 |
| US Term Structure | 6 | TIME 保留的同步共同原始行号 |
| Oil Price | 5 | TIME 保留的同步共同原始行号 |

合计 32 个，20 train / 12 dev。同 panel 完整 context+future 区间互不重叠；没有靠切换通道或重叠窗凑数。所有 target 先固定为通道 0，只用于接口 pilot，不代表正式来源/通道抽样方案。

TIME 的源日历未恢复。这里明确采用 benchmark 同步共同 row index，未把 `start+freq` 重构称为真实交易日历。availability 暂声明为 benchmark 值在对应行时刻已可见，真实发布日期/修订延迟未恢复；不能据此宣称真实实时金融部署无泄漏。ETT 只验证 CSV 网格，同样不推断外部发布延迟。

真实模型 pilot 固定 51 点 target block `[230,281)`，只污染 context，原 future 不变；32 origins 均保留。冻结读取边界先于注入。首批实际 batch=1，TS-ICL 单变量与官方历史 covariates 插补各 32 次，Bolt 对 KEEP/单变量插补/多变量插补预测共 96 次。共 160 个模型请求，不含模型内部子调用；加载 3 个 worker 进程，各分片加载一次。正式 H96/H192 未改变。

这是历史辅助信息经治理进入单变量 Bolt 的系统扩展接口检查，不能作为严格单变量排名，也不能替代原生多变量 target 模型强对照。

## 当前门与后续

截至本次记录，安装 PID 45580 和接续 PID 47722 仍存活，TS-ICL CUDA 依赖下载进行中，模型 manifest 尚未产生。GPU 主机检查正常（49140 MiB 总显存，15 MiB 已用，利用率 0%），系统可用内存约 44 GiB。沙箱的 PID/GPU 不可见不能当成主机进程死亡；后来默认 tmux socket 检查异常，显式 `/tmp/tmux-1000/default` 可列出原安装会话，未重启它们。

`results/v43/20260914T103602.635168Z-pilot/status.json` 是实际依赖拦截记录：`blocked_dependency`、`forecast_status=not_run`。它不是失败填零，也不是模型实验结果。

一次性队列 `scripts/run_v43_pilot_queue.py` 只等待现有安装和模型验收，不安装任何包；代码/config 改变或依赖失败时记录阻塞并退出。就绪后重跑 CPU gate，再运行一个真实 pilot；GPU worker 使用 `locks/gpu.lock` 并拒绝已有 compute 进程。模型失败保存 response/log/原始数组，不自动换模型或反复重跑。队列不会自动进入 A0–A5。

真实 pilot 尚未运行，因此主指标、区间、推断耗时、峰值显存与每千 origin 成本暂无实测。不能用旧节点速度或下载速度替代。完成后先查 worker shape/单位/hash/有限值与失败样本，再检查实际 task headroom，随后推进 A0–A5；更大 scorer、A8、calibration、适配、确认均待后续证据门。

最终复核新增第40项：40通道+缺失指示的实际Ridge输入维度不超过8。原实现将指示列放在PCA之后，可能超出预算；现先拼接填充值和指示，再在当前训练支持内缩放/PCA。最终日志 `logs/v43/contracts/20260914T104754.619288Z/`，40 passed in 0.96s。旧39项日志与失效等待队列均保留。


2026-09-14 18:49 最新冻结：40 passed in 1.01s，日志 `logs/v43/contracts/20260914T104900.858201Z/`。显存账本补记模型加载峰值，最终峰值取加载与推断最大值。旧队列因代码hash变化正确停止，已确认旧PID退出后重新启动；当前PID 58448，状态 `waiting_for_models`。完整机器可读证据见 `docs/v43_cpu_stage_evidence_20260914.json`，实时状态见 `results/v43/pilot_queue_status.json`。模型/方法结果仍未产生。
