# v4.3.1 近期 baseline 与第二 TSFM 家族审计

2026-09-14，Asia/Shanghai。当日冲刺固定全部 26 个 dev parent、156 个变体，不按新结果选择来源。所有模型预测在本服务器，统一 GPU 队列由主执行 agent 调度。本文件保留短预算适配与完整论文复现之间的边界。

## 官方 TATO

官方仓库为 [thulab/TATO](https://github.com/thulab/TATO)，当前本地不可变 commit 为 `402bbc8998c49e2f33d9afbcc42140347a6b8c36`。官方源码位于 `third_party/TATO`，MIT 许可、逐 Python 文件 SHA 保存于实际任务 `identity.json`；不修改该 checkout。

本次调用官方 `PipelineFactory`、八类 `Transformation` 和 `TunerFactory`。保留 trimmer、inputer、denoiser、warper、differentiator、normalizer、sampler、aligner 的全部官方搜索维度，以及两种原生排列。不限制为 IntroAct-TS 的五个动作。

已冻结的短预算协议：每个当前 dirty context 独立运行 8 trials，seed=101，第一项为最长原生 trimmer 的其余无变换配置，之后由官方 Optuna tuner 采样。默认 TPE 的启动随机期为 10，因此这个 8-trial 预算没有进入 TPE 后续自适应采样阶段，不能描述为完整贝叶斯搜索验收。正式标签为 **TATO 官方八变换空间 + observed-linear bridge，8-trial 回看适配**，不能称为官方论文完整 domain-level train/validation 复现。

Chronos-Bolt 使用与主表相同的 checkpoint：`amazon/chronos-bolt-base` revision `5d9f166d69f47aef3401367a7b842e78fe97b121`，bfloat16，中位数预测。采用其真实 input patch size=16；官方 trimmer 的 5–15 patch 对应 80–240 步历史。这个最长候选仍不是完整 512 点的 KEEP。模型内部 sampler/aligner 的时间变换经原生逆变换恢复输出，最终评价始终为原始外部 H96/H192 时间网格，不重采样真实目标。

验证 origin 固定为 exclusive cutoff `r=512-H`，输入为 dirty `X[:r]`，验证仅使用当前 context 中已知的 dirty `X[r:r+H]` 的共同有限 mask。每次重新生成变换，选中后再从完整当前 dirty context 重新生成最终变换。worker 输入协议只有 context 和元数据，不接受也不打开 future、clean、calibration/test 文件。

原生 `Inputer` 是离群值检测与替换，不会填充已经存在的 NaN；`normalizer`、`warper` 等会传播这些非有限值。这里明确增加仅使用当前可见输入的 linear interpolation bridge：内部缺口取同一可见 context 的观测插值，边界取最近已观测点，原始值、mask 与时间戳保持在外部存档；原始无 NaN 时不执行 bridge。该步骤及其费用逐窗记录，不能冒充官方默认。全 NaN 输入明确拒绝。

官方 `my_clip` 可把非有限输出替换为区间值，这与本项目契约不兼容。适配层仅对这种情况抛出可见失败，保留官方有限输出的裁剪行为。失败 trial 在 ledger 留存，不填零、不删除评价窗口；全部 trial 失败时 worker 整体失败，不改选其他模型。未发现的潜在 upstream 失败路径不能由 CPU 小例宣称已经全面覆盖。

CPU 小例以显式 shape-only 假预测器验证变换合同，不作为研究预测：H96/H192 各 8/8 trial 完成、原始观测不变、原始时间长度不变、prefix/suffix 读取隔离、全 NaN 拒绝、无 bridge 时非有限传播。原始依赖失败日志和第一次把缺口放在被 trimmer 丢弃范围导致的错误测试预期均保留，最终记录在 `logs/v431/baselines/tato-cpu-smoke.json`。真实模型结果来自统一 GPU worker，绝不使用此测试替身。

依赖只装到项目 `.cache/v431-baseline-deps`；完整 pinned 列表为 `scripts/v431_baselines/task-target-requirements.txt`。三个已验收环境不变，没有混入 core 的 site-packages。官方代码 eager import 依赖的 httpx、matplotlib 也在此独立 target。

## 费用与共同评价

`scripts/v431_baselines/worker.py` 先冻结独立 context NPZ、逐窗 hash、脚本 hash，再接受统一 GPU 调度；每次真实推断保存输入、全部分位数、point、时长、峰值显存和文件 SHA。单模型驻留并按模型输入 hash 复用结果。实际运行失败不替换为其他预测。

独立 `verify_and_score.py` 先重放全部成功 trial 的变换、验证误差、选优和最终逆变换，并检查 raw Bolt point 确为 0.5 分位数；这些步骤通过后才打开冻结 dev 的目标与原有评分 mask，按相同 source/horizon/condition 权重重算 MASE。26 个 parent 是独立单位，156 不是独立样本数。

跨 origin、跨比较臂的缓存只节省本次实验的运行时间，不能给独立部署行计作免费模型输出。汇总以同 hash 首次真实 inference 时间补计这部分费用；TATO 同窗内不同 trial 的共享计算合法去重。报告同时保留实际实验 wall、推断次数、补计后的独立请求估计、模型加载、全部进程余项。TimesFM 五固定臂另计各自实际治理候选生成费。补计是缓存复用下的部署估计，不能称为每一窗重新冷启动实测。

TATO 冻结的是 8 次搜索次数预算，不是运行中强制 wall-clock 截断；对主策略已冻结 low/high 秒数预算仅做实际费用复核，超过者标出，不能宣称通过了硬预算准入。在主表中保留 TATO 而不删慢方法。

## TimesFM 独立家族

启动审计发现三个现有环境均无 `timesfm`，当前模型缓存没有 TimesFM 权重。旧 `src/introact_ts/backends/timesfm.py` 存在不等于验收通过。

已读取 [TimesFM 官方源码](https://github.com/google-research/timesfm) 与 [2.5 模型卡](https://huggingface.co/google/timesfm-2.5-200m-pytorch)，固定代码 commit `8cb0628371af142e16b8c232cc9fbf667ffb12f9`，模型 revision `1d952420fba87f3c6dee4f240de0f1a0fbc790e3`。官方权重 925,181,104 bytes，SHA256 `2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8`，模型卡 Apache-2.0。

源码仅通过本任务 source overlay 使用，现有 Chronos 环境已成功 import 其官方 Torch 类，无须安装/替换 Torch 或 NumPy。加载仅限固定本地 snapshot，关闭 torch_compile，不替代家族。真实 GPU 小例必须先通过内部 NaN、H96、H192，然后在共同 156 dev 上运行冻结五臂，共 780 条请求；此状态以运行记录为准，不能把 import 或下载视为方法结果。

官方 TimesFM 本身对 context 中缺失值做观测内插值，并可能剥离前导 NaN。这是该 backend 的 native 输入约定，外部原始时间与目标仍不变；全 NaN 输入预先明确拒绝，不能触发官方全缺失填零分支。

下载仅对当前下载进程切线：先测官方 4 MiB Range，直连 14.21 秒、现代理 11.68 秒；首个低速下载进程经 owner/cmdline/start_ticks 核验后停止，退出 143 及残片保留。之后用独立 tmux `work2-timesfm-download-20260914` 的 8 路直连分片，每段验证 Content-Range 与长度，最后核对完整 SHA。未修改代理服务、Codex 或系统环境。下载状态为 `logs/v431/baselines/timesfm-range-status.json`；尚未通过权重校验时队列不得加载。

23:53 更新：部分大分片出现长尾慢连接，已核验并停止该自有下载进程，复用所有完成分片及已核对 Range 的 partial 前缀，用独立 `work2-timesfm-tail-20260914` 会话补齐15个至多4MiB尾段。完整925,181,104 bytes已经两次核对官方SHA通过，最终状态为 `logs/v431/baselines/timesfm-tail-status.json` completed；原分片状态明确标为 superseded，不误称原进程自然完成。下载准备 ready 尚不是模型GPU或方法验收。

TATO 与 TimesFM 结果由实际 `baseline_table.json` 填入共同表；尚未完成项不得填写预计数字。第二家族固定臂完成也不等于完整 agent 跨家族证据。

23:48 前已新增独立 `timesfm_tato_worker.py`，不改已冻结 Bolt worker/adapter。它使用 TimesFM 原生 patch=32，全 trimmer5–15 空间仍保留，太长的候选在320/416历史前缀上明确失败并计成本，不读取额外历史或补未来。CPU H96 成功5/8、失败3/8；H192成功4/8、失败4/8，记录 `logs/v431/baselines/timesfm-tato-cpu-smoke.json`。真实预测须另经统一队列，专用 `--verify` 入口按patch32做独立回放，不能借用Bolt逆变换配置。

## 当日实际 TATO/Bolt 结果

全156窗完成，实际进程79.9067秒，837份去重的真实Bolt原始输出。独立验证重放1248个成功trial及156个最终预测，逐trial原始有限值mask、历史误差、选优与逆变换全部一致，原始文件SHA和0.5分位数检查通过。`results/v431/20260914-sprint/tato/baseline_table.json` 与 `scored_rows.json` 是汇总来源。

MASE=1.685227229；ETTm1=1.507982237，Solar=2.556695553，US_Term_Structure=0.991003899。加入跨窗缓存推断补计及全部进程余项分摊后，source宏平均费用0.703174秒；固定8trial费用事后超过已冻结low=0.814062秒预算68/156次，high=3.5秒预算0次。这个短预算TATO适配在当前开发集退步；不能据此宣称击败官方完整方法或SOTA。
