# IntroAct-TS 新服务器交接

交接日期：2026-09-14。项目位于 `/home/vipuser/work/work2`，日常使用 `vipuser`。本轮用户要求先完成环境准备、代码和资产上传，后续方法实现与实验由服务器上的 Codex 接管。

本轮完成的内容与待完成的研究工作须分开理解：代码资产迁移已通过逐文件 SHA-256 核验；三个环境 prefix 已创建，core 的 pip check 和 import 已通过；服务器 core 最小旧代码测试 **41 passed in 4.04s**。TS-ICL/Chronos 依赖、模型下载及 GPU 接口验收在本稿记录时仍为待完成。未实现 v4.3，未运行研究 pilot、正式实验或旧结果统计重算。最后一次运行状态请按下文状态文件核对，不把后台启动当作完成。

## 1. 接管入口与实际路径

先阅读本文件、`AGENTS.md`、完整方案 `docs/new_server_execution_plan_20260914.md`，然后读取 `docs/HANDOFF.md`、`docs/version_ledger.md`、`docs/CHANGELOG.md`。可直接给服务器 Codex 的对话提示词位于 `docs/REMOTE_CODEX_PROMPT.md`。

| 用途 | 实际路径 |
|---|---|
| 项目根目录 | `/home/vipuser/work/work2` |
| 环境根目录 | `/home/vipuser/work2-envs` |
| core 解释器 | `/home/vipuser/work2-envs/w2-core/bin/python` |
| TS-ICL 解释器 | `/home/vipuser/work2-envs/w2-tsicl/bin/python` |
| Chronos 解释器 | `/home/vipuser/work2-envs/w2-chronos/bin/python` |
| 项目缓存 | `/home/vipuser/work2-cache` |
| HF 缓存 | `/home/vipuser/work2-cache/huggingface` |
| bootstrap 暂存目录 | `/home/vipuser/work2-staging/bootstrap-20260914` |
| 环境激活配置 | `/home/vipuser/work/work2/scripts/env_new_server.sh` |
| 环境精确 lock/来源 | `/home/vipuser/work/work2/requirements/bootstrap-20260914` |
| 模型验收 manifest | `/home/vipuser/work/work2/configs/v43/model_manifest.bootstrap.json` |
| 项目 GPU 协调锁 | `/home/vipuser/work/work2/locks/gpu.lock` |

开始工作时执行：

```bash
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
git status --short
```

使用 `$W2_CORE_PY`、`$W2_TSICL_PY`、`$W2_CHRONOS_PY` 指定解释器；运行模型 worker 时保持跨进程隔离。脚本设置项目 PYTHONPATH、缓存、单线程 BLAS 和服务器本机代理 `127.0.0.1:17890`。不依赖本地电脑保持在线，也不需要修改全局 bashrc。旧文档中的 `/root/autodl-tmp/work2`、旧 SSH 端口、旧队列和旧模型 `available=true` 是历史记录，不能直接用于新机器。

## 2. 已核验的迁移范围

迁移源为本地 `F:/work/Time-research/work2` 的实际工作区，保留了大量未提交、未跟踪的新代码和结果。源仓库 HEAD 为 `23c131a06c664fafdbff1a3284c1470a831d529c`，该 SHA 仅作来源标识，不代表上传内容都已包含在此提交中。不要 checkout 这个旧 SHA 来“恢复”新服务器工作区。

- 上传 **1081 个文件，共 826134562 字节**。
- 解包后逐文件 SHA-256 全部匹配，**未覆盖已有文件**。
- 压缩包 SHA-256：`046cd6c80016e025097144d468898b3ca6e02a41d9d3967abf8aba4cabe8ac5d`。
- 包括源代码、实验脚本、测试、项目工具、文档、论文材料、数据、v3.3 至 v4.2 结果及模型 checkpoint。
- 未把本地 `.git`、历史连接工具 `remote.py`、凭据、代理配置正文、临时日志与缓存复制为项目代码。

服务器新增的交接文件、环境脚本、安装报告和后续官方模型源码不属于上述原始快照计数。服务器使用独立的 `codex/introactts-v43-bootstrap` 分支保存迁移基线，原仓库历史没有复制；来源HEAD和逐文件清单已保留。最终提交状态由接管时的 `git status` / `git log` 确认，详情见暂存目录 `git-baseline-result.json`。保留已存在的用户修改，后续在 `codex/` 分支提交代码、配置和文档，不将数据、权重或大中间产物提交进 Git。

已保存源码基线 `005d48fb7cf33f7cdb4cb7f56499594a56193097`（346个文件）。提交前只读核验216个研究源文件，全部与原快照一致，提交后工作区干净。资产排除规则放在该服务器仓库的 `.git/info/exclude`；原 `.gitignore` 和旧研究文档保持原样。后续环境freeze及模型manifest会新增文件，需核验后正常提交，不能将这种变化误认成旧快照损坏。

## 3. 资源与持久化事实

本次服务器采集值如下，运行任务前仍须重新检查占用情况：

| 项目 | 观察值 |
|---|---|
| CPU | 16 个可见 CPU |
| 内存 | 约 47 GiB |
| Swap | 约 8 GiB |
| GPU 名称 | NVIDIA GeForce RTX 4090 |
| GPU 报告显存 | 49140 MiB |
| NVIDIA driver | 595.84 |
| 根文件系统 | ext4，约 196 GB，采集时约 154 GB 可用 |

GPU 名称与通常按商品型号推测的显存不一致，按实际可见信息与运行时检查配置批大小，不自行假设是 24 GB，也不据此断言物理卡形态或独占权。检查 compute process、利用率和剩余显存后再取得项目 `flock`，重 GPU 任务一次一个。项目锁只能协调本项目任务，仍须尊重其他用户进程。

已确认目录可读写和磁盘挂载，**没有平台控制台证据确认停机、重建、到期或销毁后的磁盘保留规则**。不要把 ext4 或 `/home/vipuser` 路径当作生命周期保证，也不要自行关机、释放资源或删除本地备份。

## 4. 后台环境准备：先查看，避免重复安装

本稿最后已知状态：`w2-core` 的 pip check/import 通过，`w2-core`、`w2-tsicl`、`w2-chronos` 三个 prefix 已创建；后台阶段为 `install-torch-w2-tsicl`。CUDA 依赖体积数 GB，测得下载吞吐约 0.55 MB/s，因此安装需要持续一段时间。TS-ICL/Chronos 的 prefix 存在不等于包安装和验收完成。

后台 tmux 会话：`work2-bootstrap-20260914`。

```bash
cat /home/vipuser/work2-staging/bootstrap-20260914/status.json
tail -n 40 /home/vipuser/work2-staging/bootstrap-20260914/logs/bootstrap.log
tmux list-sessions
```

项目另提供只读总览命令 `python3 scripts/bootstrap_status.py`，汇总环境准备与后续模型阶段。恢复工作时优先查看它的输出，再查对应详细日志。

`status.json` 是原子更新的环境状态，包含 `status`、`phase`、`pid`、`updated_at` 和 `environment_reports`：

- `running`：结合 PID、tmux 与日志判断仍在工作。已有下载或 pip 进程时不要重复启动 bootstrap、另起安装或改写相同 prefix。
- `failed`：先读取失败阶段、退出码及原始日志，检查该进程是否已退出，再按具体错误恢复。保留下载缓存和已通过的环境，不删除整个环境树重装。
- `completed`：环境脚本走到结束；再查看各环境 `.verification.json`、pip check 和精确 freeze。某环境报告中的 `gpu.status=deferred` 表示 GPU 基础验收尚未做，不能视为通过。

每个环境的报告位于暂存目录 `logs/`，包括 `<env>.verification.json`、`<env>.pip-check.txt`、`<env>.platform.txt`、`<env>.pip-inspect.json` 及安装解析报告。成功冻结后，`requirements/bootstrap-20260914/` 保存 `.freeze.txt`、`.conda-explicit.txt`、官方源码 commit、安装来源和 `SHA256SUMS`。未出现完整 freeze 时保持该阶段 pending。

core 使用 Python 3.11/NumPy 1 系；TS-ICL 使用 Python 3.12 及其官方所需科学栈；Chronos 使用 Python 3.11。两个 GPU 环境采用已选定的 torch 2.9.1 CUDA 12.6 wheel，按安装报告冻结真实解析结果。不要把旧 `requirements.txt` 宽范围依赖或旧 `tsicl==0.2.1 --no-deps` 做法套到这三个新环境，也不要执行旧 `setup_remote.sh` 或 `env_autodl.sh`。

两个官方源码checkout已固定：TS-ICL `349f3eae4f01f78536b16a6ea53c0837760166ec`，Chronos `4dbf163c2734c089cdf7da2b86fde48862ff9c6f`。共享pip缓存不保证所有CUDA wheel复用，部分官方NVIDIA响应禁止缓存；下载可能继续较长时间，不据小文件测速承诺总耗时。

已在服务器 core 环境执行 `tests/test_actions.py`、`tests/test_risk.py`：**41 passed in 4.04s**。日志与 JUnit 记录为 `logs/v43/install/core-smoke.log`、`logs/v43/install/core-smoke.xml`。这两组测试验证现有轻量动作与风险基础路径，不是 v43 语义测试或全项目测试通过的证明。

## 5. 模型准备与验收边界

依赖达到成功终态后，后续 after-env 阶段用于执行 `prepare-models.py`：解析并固定 Hugging Face snapshot SHA、记录官方源码与环境 lock、下载 TS-ICL 和 Chronos-Bolt，再在 GPU 空闲时做微型接口测试。**在 manifest 和真实日志证明结束前，这些项目均保持 pending。** 接管时先查暂存目录现有 after-env 流程与 tmux 状态，不与它并发下载或验收。

接续入口为暂存目录的 `after-env-bootstrap.py`，接续 tmux 会话名为 `work2-after-env-20260914`，独立状态文件为 `/home/vipuser/work2-staging/bootstrap-20260914/continuation-status.json`。2026-09-14 17:40（UTC+8）已启动，首次状态为 `waiting_for_environments`。它等待环境 bootstrap 成功终态后才进入模型阶段；环境失败或进程消失时停止并记录blocked，不自动反复重装。修复环境后如接续进程已经退出，需要重新运行该接续脚本；先确认没有现存进程。断开SSH不会停止tmux，但这些任务不会在服务器重启后自动恢复。

权威记录：

```bash
if test -f configs/v43/model_manifest.bootstrap.json; then
  cat configs/v43/model_manifest.bootstrap.json
else
  printf '%s\n' '模型准备尚未写出 manifest，保持 pending。'
fi
```

模型阶段细节保存在 `/home/vipuser/work2-staging/bootstrap-20260914/logs/models/`。解释模型状态时：

- `pending` / `pending_download`：元数据或下载尚未完成。
- `downloaded` / `downloaded_gpu_deferred`：文件已到位；GPU/接口验收未全通过。
- `ready` 且 `validation.status=passed`：该模型的 bootstrap 微型接口测试通过。
- manifest 总状态 `completed`：以其中 TS-ICL/Bolt 实际记录为依据；**Chronos-2 在首批仅固定元数据，不能声称权重或推断已验收**。
- `failed`：保留错误和已固定 revision，解决实际失败，不能通过换 checkpoint、关掉校验、填零或 surrogate 降级把它变成通过。

TS-ICL/Bolt 的微型验收只用于验证真实模型加载、NaN/变长输入和预测输出 shape 等基础接口。即使状态为 ready，仍不代表 v43 worker、时间读取边界、成本记录、任务标签或 32-origin pilot 已完成。正式 v43 适配器与语义测试继续由服务器 Codex 实现。

加载时使用 manifest 已记录的不可变 revision/snapshot 和 checkpoint 路径；保存模型卡、许可、权重 SHA-256、源码 commit、环境 lock hash 及真实通过的能力。TimesFM 2.5/3、MOMENT、OpenFIM 及其他 baseline 环境属于后续按需工作，首批没有全部安装。

## 6. 数据、历史资产与缺失项

本地上传数据目录含 11 个文件，共 39112263 字节：4 个 ETT CSV、exchange/solar 压缩文件、Crypto/Oil/USTS 三个 TIME NPZ、`time_export.json`、`valuation_xl.npz`。`time_export.json` 有历史通道、频率、起始时间描述。**上传完成不等于已经具备新协议的原始时间映射、split manifest 或全部来源原始文件**；`data/raw` 原本不存在，新建目录也不能消除这一缺口。

历史 `results` 共 369 个文件、673412115 字节，包含 v3.3 至 v4.2 冻结结果。`results/v40_critic_ckpt` 的 30 个非空 checkpoint 共 61860486 字节已经随快照上传。根目录原有同名 0 字节 `TSFM_latent_only__Crypto.pt` 已排除。

以下三个大件原本仅留在旧节点，本轮没有恢复；详见已上传的 `results/v40_sync_note.json`：

1. `results/v40_feature_cache.npz`。
2. `results/v40_rescue_bank_candidates.jsonl`。
3. `results/v40_rescue_bank_records.jsonl`。

相关 parents、单臂 rescue 候选与 hash 记录已保留，需要时在当前服务器按冻结代码和输入重建并核对。没有恢复前不能声称完成旧结果精确复现；这些缺失只阻断依赖它们的旧复现分支，其他 v43 数据与实现工作继续。

迁移源没有 `third_party/openfim` 及完整旧基础模型缓存。历史 `v39_model_manifest.json` 的模型可用标记与依赖组合仅说明旧环境。历史连接工具 `tools/remote.py` 因包含连接凭据未迁移；本轮按当前服务器的 manifest 与实际文件决定可用范围。

## 7. 研究现状与必须先审计的语义

历史状态截至 2026-09-05：v4.2 PORTFOLIO-ACT 在 Phase 0 红灯停止，未晋升。保留 **PICS_joint_relabel** 为 incumbent。`docs/HANDOFF.md` 开头更新和版本台账为主要依据；其下半部历史队列与 `docs/CHANGELOG.md` 的旧日期不足以判断当前完成状态。

完整方案第 6 节列出需要先审计的旧入口。本轮准备没有修复这些方法语义，服务器 Codex 需逐项处理并留证据：

- `v33_labels.compute_action_labels` 的 gain 是重建收益；保留旧定义，另建真实 TSFM task evaluator，不能用 repair gain 代替 task gain。
- `v41_mask_counteract.calibrate_tau` 旧权重没有加权风险约束；不能据旧相同阈值否定真正的风险重加权。
- `v42_portfolio_act.gain_lookup` 的非 TS-ICL gain 不完整，缺失不能当作 0；新旧候选统一产出任务标签。
- `v42_portfolio_act.stage_phase0b` 锁住已有 commit，新方案应对所有候选统一作最终决策。
- `v40_counterfactual_bank.isolation_report` 的 hash 隔离不能替代原始时间区间及同步组隔离。
- `downstream.make_pairs` 的删 NaN 点与治理后切窗路径不符合新协议；先固定原始 context/future，仅治理 context，保持时间索引和共同评价 mask。
- `backends.make_pool` 可能跳过失败后端；正式实验必须显式核验实际后端集合。
- token 分块或代理特征不能称为真实 TSFM 逐层状态。

这些是需要核验的静态风险，不构成“所有旧结果均泄漏”的结论。旧 manifest、失败分支、指标定义和 raw trace 应保留。

## 8. 服务器 Codex 接续范围

`src/introact_ts/v43/` 与完整方案中的统一 CLI 是**待实现契约**。不要直接尝试尚不存在的命令并把缺模块当成迁移损坏，也不要以准备阶段创建了目录为由标记方法实现完成。

在现有后台安装继续运行时，可以先做代码阅读、数据/时间映射盘点和不依赖 GPU 的实现。后续按完整方案自主推进：

1. 核对迁移、Git 与后台状态，复用通过验收的环境和模型；登记缺失资产。
2. 完成原始时间、NaN/mask、context/future、split/parent/sibling 通道边界、worker 身份、固定 revision 与缓存键契约；实现第 18 节必要语义测试。
3. 只在 train/dev 的 **32 个来源均衡 origin** 上做首轮 pilot，L512/H32；报告真实输出 shape、加载/推断耗时、峰值显存、失败样本与实际成本。H32 仅为接口 pilot，正式主任务仍为 H96/H192。
4. 接口和泄漏检查通过后，再推进 A0–A5 与上界，先判断跨通道新信息是否产生真实 TSFM 任务收益；再考虑更大评分器和主动工具策略。
5. 不提前读取 calibration/test 标签，不用旧 771/89 开发样本冒充独立终测。保留失败、共同评价分母、future 原始值与模型成本，不静默缩短正式 horizon。

所有测试、模型下载、实验、训练和统计重算均在当前服务器运行；长任务放独立 tmux 并保存状态、PID、日志和资源记录。每个研究阶段同步代码、配置、原始结果、环境/模型/数据 hash、版本台账和相应文档。当前准备不构成方法晋升或 baseline 胜出证据，不宣称 SOTA。

服务器 Codex 的第一份回报应是接管时的真实状态、已经实际运行的数据/worker 测试或 32-origin pilot 结果、明确的阻塞项及下一批成本估计，不只重复完整方案。用户已授权的实施与验证自主继续，仅询问真正缺失且阻断工作的输入。


## 2026-09-14 20:00 用户授权下载切线

work2已实际切到任务专用直连分段下载，保留约932MB已有数据。旧安装PID45580/61386退出，新bootstrap PID66506、下载PID66519；模型接续和pilot队列已恢复，监控PID59254保持。代理服务与Codex配置未改，端口切换前后可达。首次切线父进程已退出异常与分段重试全部留痕，详见 docs/download_switch_20260914.md 及机器证据；不能重启旧安装或同时改写prefix。真实pilot仍待验收。


## 2026-09-14 20:15 环境验收完成

三个独立环境全部完成安装、依赖检查和指定模块导入；TS-ICL与Chronos的CUDA256×256矩阵检查通过，RTX4090支持BF16，单次小测试峰值分配9,502,720字节。TS-ICL为Python3.12/NumPy2.5.3，core与Chronos为Python3.11/NumPy1.26.4，两GPU环境保持Torch2.9.1+cu126。25个恢复wheel整包官方哈希校验通过，环境freeze/conda-explicit与SHA256SUMS已落盘并逐项复核。

安装20:14:48结束，模型接续20:15:27开始；TS-ICL官方revision已锁为19c94031439fb31f36ce395088ee50a6762d3774，权重下载中。Bolt尚未下载，真实32-origin pilot仍未运行。此处是环境验收，不是模型worker或方法成功。证据见 docs/environment_acceptance_20260914.json；冻结记录见 requirements/bootstrap-20260914/。待两个模型接口验收通过后，队列重验CPU gate并运行真实pilot，calibration/test读取仍关闭。


## 2026-09-14 20:53 首轮真实pilot失败与入口修复

首个真实pilot于20:49启动，run results/v43/20260914T124856.762289Z-pilot；CPU gate40项通过后，TS-ICL worker在模块导入时因缺statsmodels失败，尚未执行预测或读取future标签。原因是introact_ts顶层入口提前加载旧Agent/profile依赖，而TS-ICL环境按官方依赖保持隔离。没有向TS-ICL环境补装core栈。

已将旧重依赖导出改为按需加载，保留原公共API，并将顶层__init__/types/verify三项必要入口依赖纳入worker代码hash。43项CPU测试通过（1.29秒），4项旧API判据回归通过，两个worker在各自冻结解释器的--help入口均通过。完整失败日志、测试和代码hash见 docs/worker_import_fix_20260914.json。新真实pilot仍须实际执行后验收，不把此修复记为方法成功。

Bolt镜像于20:46:09整包官方SHA256通过，20:46:52在旧传输进程退出和HF文件锁保护下接入同一官方revision缓存；保存旧335,236,791字节未完成文件。原验收器确认Bolt GPU接口通过，TS-ICL也通过。可选Chronos-2元数据TLS失败及一次独立重试失败保留，不阻塞只要求TS-ICL/Bolt的pilot。权重完整镜像耗时与HF缓存命中耗时分别保存，不能混算。


## 2026-09-14 21:00 post-hoc：真实 P1 pilot 完成

32 origins（20 train / 12 dev）、L512/H32、64 次真实 TS-ICL 插补和 96 次 Bolt 预测全部完成；43 项 CPU gate 通过，独立原始结果重算通过，未读 calibration/test。运行 21.794 秒，最大 GPU 分配 710,672,896 字节。KEEP / SINGLE / COV 来源宏平均 MASE 为 1.322762 / 1.316489 / 1.228219；COV 宏平均 MAE 反而变差，两插补臂各 15/32 个 origin task harm，无 CI。仅为接口与开发诊断，正式 A0–A5/H96/H192 未运行，PICS_joint_relabel 不变。首轮导入失败和可选 Chronos-2 TLS 失败保留。证据与原始结果入口见 `docs/v43_pilot_report_20260914.md`、`docs/v43_pilot_evidence_20260914.json`；下一步补长来源、接正式强对照及 A5 静态规则。


## 2026-09-14 P2 首批开发配置冻结（未运行结果）

P1 已完成且独立复核通过后，新增 `configs/v43/p2_first_dev.yaml`、`cli p2` 与 A4/A5 正式接线。只取 ETTm1 / Solar / USTS 的 dev 原始区间，分别 14 / 11 / 1 个不重叠基础 parent；两个 horizon 96/192 及 raw、target block 10%、全部 siblings shared block 10% 共 156 个 episode。这些变体不是 156 个独立样本；全历史 ridge 读取区间在 dev 内重叠，正式推断还须按更大依赖块处理。

Solar 复用本机文件，与论文作者仓库 Git blob 完全一致。只按原行号保留同步时间；来源说明为 2006 年 Alabama 137 路 10 分钟光伏，压缩文本无原始时间戳，不能伪称已恢复绝对日历或发布延迟。库存只统计行宽，不解码 heldout 数值。来源证据见 `docs/v43_p2_source_provenance_20260914.json`。

首批重点检验长缺口的新信息收益，以及原始/共享缺失的保护与负对照；5%/点缺失/spike/valid-event 标注和其他来源为后续矩阵，不能把首批当完整污染实验。固定通道0、seed101、L512、缺口[230,281)、不按标签挑窗口。只要求 TS-ICL/Bolt 两个已通过模型，保持 batch1/GPU单任务。

执行臂为 A0 native/ffill、A2 single、A3 官方全合法covariates、A4当前context及同split全合法历史ridge、A5严格嵌套OOF静态eta。A4历史只读 dev 起点到当前context起点，再拼当前dirty输入，不重新打开当前gap真值；这是额外历史信息轨道。A5保存七类真实遮挡输入，支持不足明确回到同origin已验证A2，真实worker缺行/失败仍报错；eta平局取0。候选去重只在同episode、同horizon、完整输入hash下进行并保存alias，所有候选完成真实预测后才读future。

A1仍为blocked_adapter：`experiments/v39_phase0_replay.py:321` 强依赖771个冻结parents，`:450`按历史候选标签拟合LODO PICS并重放；源码存在不等于可对本次新时间区间部署。该参照待合法适配，不把旧分数贴到新UID，也不把缺失参照填0。原生多变量任务模型尚未运行。A9只对本轮完整已执行候选集生成开发上界，名称明确为A9_ORACLE_AVAILABLE，不冒充全候选上界。

新增测试覆盖gzip越界标签不可解码、父区间共享、shared辅助遮挡、全历史不重读gap、A5不适用回A2、漏真实预测报错、ridge观测值不变及eta平局0。运行以新配置绑定的CPU gate为前提，结果产出前不作方法成功结论。PICS_joint_relabel不变，不将规划写入DOCX成果。


### 2026-09-14 21:20 可选模型元数据恢复

仅对可选 Chronos-2 元数据使用子进程 `NO_PROXY=*` 直连，3.27秒成功固定 revision `29ec3766d36d6f73f0696f85560a422f50e8498c`；未下载权重，模型仍metadata-only/pending。当前bootstrap manifest为completed，TS-ICL/Bolt保持ready；旧orchestrator退出码1和两次TLS失败不改写。完整旧record/manifest及新恢复状态保存于logs/v43/chronos2-metadata-direct-20260914，摘要见docs/chronos2_metadata_recovery_20260914.json。代理服务和Codex配置未改，P2使用运行开始时冻结的必需模型manifest。


## 2026-09-14 21:20 post-hoc：P2首批真实实验完成

51项CPU测试通过，H96/H192、三个dev来源、26个基础parent/156变体，512次真实插补、580次去重预测、1092份任务标签全部完成，独立原始结果复核通过；耗时251.386秒，峰值GPU分配1.90GB。KEEP/A2/A5来源宏平均MASE为1.258454/1.157005/1.157187，无可靠确认性CI。A5仅4个ETTm1 parent产生8个修正变体，未来任务2好6坏；其真缺口重建6好2坏。加入A5后，相对已含简单跨通道强对照的oracle增量为0，不能晋升残差方法或进入更大A8训练。A1与原生多变量对照待适配，其他污染条件/来源尚未覆盖；calibration/test读取仍为0，PICS_joint_relabel不变。全部状态、误差分歧与成本见docs/v43_p2_report_20260914.md和docs/v43_p2_evidence_20260914.json。
