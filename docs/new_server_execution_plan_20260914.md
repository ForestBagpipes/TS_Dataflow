# IntroActTS 新服务器完整执行方案

本文件交给本地执行 agent 使用，覆盖新服务器接入、项目迁移、环境隔离、方法实现、实验、诊断、文档同步和最终交付。以此文件为本轮入口，无须依赖此前聊天。已有代码仍需从本地 work2、旧服务器或上传项目包取得，本文件不是完整代码仓库。

状态为待执行规划。本轮没有在新服务器运行实验。文中的系统命令可在确认参数后执行，新增 v43 模块和 CLI 是要求执行 agent 实现的接口契约，不能误当成已有程序。

## 0 固定目标与执行原则

方向固定为面向时间序列基础模型 TSFM 的数据治理 agent，在 IntroAct-TS 现有工程上改进。目标是在相同基准、信息、监督和预算下超过近期强 baseline，争取 ICLR 2027 oral，同时形成数据治理岗位可展示的工程成果。不能改成普通插补、异常检测、从头训练基础模型或另一项合成数据项目。

建议题目为 **IntroAct-TS: Evidence-Seeking Data Governance for Time Series Foundation Models**。问题定义是在原始数据保留、当前修复目标真值不可见、验证计算有限时，如何取得有用证据并选择真正改善 TSFM 任务表现的治理动作。备份和回退属于已有系统能力，不承担核心创新。

执行约束：

1. 每阶段同步文档、代码、配置、原始结果与版本台账。旧预注册和 post-hoc 保留。
2. 实验、测试、统计重算、训练和模型下载全部在服务器运行。本地只阅读、编辑、SSH调度、同步和校验文件。
3. 实时检查资源，不终止、暂停、抢占他人任务，不升级共享服务器驱动或修改全机GPU设置。
4. 每个候选版争取提升，正式晋升必须有同协议证据。失败分支保留，不通过改测试集、指标或分母制造提升。
5. 所有结果回到具体代码、原始时间、mask、候选与hash。正向结果同样审计。
6. 不预先宣称SOTA，不保证oral，没有实际运行的baseline不能写成已经胜过。
7. 按本文自主推进已明确的迁移、配置、实现和验证，不在每个阶段反复询问是否继续。必要接入信息缺失时只询问阻塞项，同时推进独立工作。
8. 不代用户购买资源、调用未经授权的付费LLM API、投稿或发送材料。公开数据和模型正常下载属于环境配置，须遵守相应许可。

## 1 首次接管信息

参考配置为一张4090 24GB、8核CPU、16GB系统内存。建议内存至少32GB，64GB更充裕，磁盘有100至200GB可用空间。最终按实际分配资源运行，不假定用户已经升级。

| 参数                       | 来源                      | 缺失时                             |
| -------------------------- | ------------------------- | ---------------------------------- |
| 新服务器地址、端口、用户名 | 用户连接命令或本机SSH配置 | 取得后再连接，不猜测               |
| 认证                       | 已配置key或交互认证       | 不把密码或私钥写进代码、本文和日志 |
| 本地项目目录               | 用户本地work2或项目文件夹 | 优先定位最新仓库与未提交修改       |
| 旧服务器连接               | 用户已有配置，可选        | 不阻断新方法开发                   |
| 持久盘位置                 | 平台说明、挂载和磁盘查询  | 确认后设置路径                     |
| 实际GPU、CPU、内存、租期   | 新服务器与控制台          | 覆盖计划中的资源假设               |

首次读取最新 `docs/HANDOFF.md`、`docs/version_ledger.md`、`docs/CHANGELOG.md` 和 git 状态。如果已有比v4.2更新的结果，先合并其证据，不覆盖已有工作。

此前规划环境的 `/workspace/scratch/477a27e80c71` 不是用户电脑或新服务器路径，不能照搬。项目可默认放 `/root/autodl-tmp/work2`，仅当该盘确实符合持久化要求时采用。

## 2 SSH接入与迁移

### 2.1 本地SSH配置

添加独立Host，不覆盖其他配置。REPLACE字段先换成真实值：

```sshconfig
Host work2-new
    HostName REPLACE_WITH_HOST
    Port REPLACE_WITH_PORT
    User REPLACE_WITH_USER
    IdentityFile REPLACE_WITH_EXISTING_KEY_PATH
    ServerAliveInterval 30
    ServerAliveCountMax 6
```

交互认证可省略IdentityFile。首次host key按平台信息或已知指纹核验，不默认关闭检查。连接命令为 `ssh work2-new`。Windows可使用原生OpenSSH，rsync示例在WSL或已有rsync的终端执行。只有PowerShell时用scp传包，再在服务器解压。

### 2.2 服务器只读检查

```bash
date -Is
uname -a
cat /etc/os-release
nvidia-smi
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,driver_version --format=csv
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv
nproc
free -h
df -hT
findmnt
ps -eo user,pid,ppid,pcpu,pmem,etime,comm --sort=-pcpu
python3 --version
command -v conda
command -v tmux
command -v rsync
```

可选命令缺失时记录并继续。进程日志默认只记程序名，不保存可能带凭据的完整命令行。核查cgroup CPU配额、GPU是否独占及停机后磁盘保留规则。

### 2.3 服务器目录

确认持久盘后设置下列变量，挂载点不同时改第一行：

```bash
export W2_DATA_ROOT=/root/autodl-tmp
export W2_ROOT="$W2_DATA_ROOT/work2"
export W2_ENVS="$W2_DATA_ROOT/envs"
export W2_CACHE="$W2_DATA_ROOT/work2-cache"
mkdir -p "$W2_ROOT" "$W2_ENVS" "$W2_CACHE"
mkdir -p "$W2_ROOT"/{configs/v43,docs,results/v43,logs/v43,artifacts/v43,locks,requirements,third_party}
```

不修改HOME、CODEX_HOME，不写全局bashrc。路径都进入配置。目录约定：

| 路径，相对W2_ROOT      | 内容                         |
| ---------------------- | ---------------------------- |
| `src/introact_ts/`     | 旧代码                       |
| `src/introact_ts/v43/` | 新方法与统一CLI              |
| `configs/v43/`         | 配置、模型与策略冻结清单     |
| `data/raw/`            | 原始数据与来源记录           |
| `data/manifests/`      | 时间映射、切分和hash         |
| `data/v43/`            | 窗口索引和分片，避免重复展开 |
| `results/v43/`         | 每次独立run目录              |
| `artifacts/v43/`       | 模型、预测缓存索引、最终表   |
| `logs/v43/`            | 日志、PID和资源记录          |
| `requirements/`        | 各环境精确lock和安装报告     |

### 2.4 资产迁移顺序

先代码与数据，再候选和模型缓存，最后大中间表征：

1. 最新代码、未提交修改、docs、configs、依赖lock、模型manifest。
2. 六来源原始数据、真实timestamp与compact映射、split manifest。
3. v3.3至v4.2逐窗记录、候选、阈值和checkpoint。
4. 已验证TS-ICL、Chronos-Bolt、TimesFM2.5、MOMENT权重与revision。
5. 21k反事实bank、168k候选和确实需要的旧特征。

上传的 `eaee5fd5-2b21-46ce-ab25-13002b4bcf02.zip` 包含 `gpt_pack/`、代码、文档和部分 `results_selected/`，不是完整数据和模型备份。不能把results_selected直接改名results后假定旧入口全部可跑。

保留git历史或先做本地快照，不自动提交凭据、大数据或权重。Python环境优先导出lock和安装来源后重建，不把旧环境目录直接复制后就宣称可用。

本地传输示例，先替换路径：

```bash
rsync -a --partial --info=progress2 \
  --exclude='.env' --exclude='.ssh/' --exclude='*.pem' \
  --exclude='__pycache__/' --exclude='.venv/' \
  --exclude='tools/remote.py' \
  /REPLACE/LOCAL/work2/ work2-new:/root/autodl-tmp/work2/
```

不使用 `--delete`。旧tools/remote.py可能含旧接入配置，不作为启动新机的工具，应改为SSH alias或环境变量。传压缩包时先进入staging，检查成员，拒绝绝对路径、`..`越界和符号链接越界，解压后比较再合并，不直接覆盖根目录。

旧服务器不可用时建立 `docs/asset_inventory.md`，标记present、recoverable、missing。缺旧记录只BLOCK旧精确复现分支，新预测数据和方法开发继续。没有原始记录就不宣称复现旧数字。

## 3 环境隔离与安装

### 3.1 不直接运行旧all脚本

`scripts/setup_remote.sh` 实际将各家族装进同一解释器，不能隔离依赖。`env_autodl.sh`写死路径、镜像和8线程，也不能原样用于新机多进程。

本轮核实TS-ICL主分支需要Python>=3.12、torch>=2.5.1且<2.10。Chronos需Python>=3.10、torch>=2.2且<3。TimesFM主分支已经3.x，旧2.5后端不能只换model_name就代表支持3。[1][2][3]

| 环境             | Python         | 用途与顺序                       |
| ---------------- | -------------- | -------------------------------- |
| w2-core          | 3.11           | 统计、数据、轻量模型和调度，先装 |
| w2-tsicl         | 3.12           | 当前官方TS-ICL独立worker，先装   |
| w2-chronos       | 3.11           | Bolt和Chronos2，先装             |
| w2-timesfm25     | 旧lock对应版本 | 旧复现和支持时的适配，有缓存优先 |
| w2-timesfm3      | 官方兼容Python | 第二家族完整复核，后装           |
| w2-moment        | 旧lock对应版本 | 重建，按需                       |
| w2-baseline-名称 | 官方要求       | TATO、T1、HELIX等，按需          |

先只创建前三个。核心进程通过文件协议调用不同环境worker，不在同一个进程import全部模型库。

### 3.2 创建环境

已有conda时用独立prefix，不执行conda init：

```bash
conda create -y -p "$W2_ENVS/w2-core" python=3.11 pip
conda create -y -p "$W2_ENVS/w2-tsicl" python=3.12 pip
conda create -y -p "$W2_ENVS/w2-chronos" python=3.11 pip
```

已有prefix先检查，不覆盖。无conda但存在对应Python时用venv。缺Python3.12时在持久盘安装官方独立环境管理器并核查来源，不修改系统Python，不降低TS-ICL元数据来绕过依赖。

### 3.3 核心依赖

优先旧精确lock。没有时以下作为启动候选，验收后精确冻结，不能称为已经测试的组合：

```bash
"$W2_ENVS/w2-core/bin/python" -m pip install --upgrade pip
"$W2_ENVS/w2-core/bin/python" -m pip install \
  'numpy==1.26.4' 'scipy>=1.11,<1.14' \
  'pandas>=2.0,<2.3' 'scikit-learn==1.5.2' \
  'statsmodels>=0.14,<0.15' 'ruptures>=1.1.8,<2' \
  'pytest>=8,<9' 'pyyaml>=6,<7' 'pyarrow>=15,<20' \
  'joblib>=1.3,<2' 'psutil>=5.9,<8' 'matplotlib>=3.8,<3.10'
"$W2_ENVS/w2-core/bin/python" -m pip check
```

范围只用于首次解析，之后保存 `pip freeze --all`、Python和平台版本、安装报告。不同NumPy或BLAS不保证旧bit-exact数值。有必要时另建legacy环境。项目根目录目前未确认有可安装的pyproject，不能直接假设 `pip install -e .` 可用，运行时显式设置PYTHONPATH指向src。

### 3.4 GPU环境

先检查云镜像与驱动。共享机不升级驱动，不源码编译CUDA。官方提供torch2.9.1的cu126/cu128 wheel，且2.9.1位于当前TS-ICL声明范围内。[4] 如果实际驱动兼容CUDA12.6运行时，启动候选为：

```bash
"$W2_ENVS/w2-tsicl/bin/python" -m pip install \
  'torch==2.9.1' --index-url https://download.pytorch.org/whl/cu126
"$W2_ENVS/w2-chronos/bin/python" -m pip install \
  'torch==2.9.1' --index-url https://download.pytorch.org/whl/cu126
```

驱动不兼容时按官方表选择受支持wheel及版本并记录依据，不强行更改系统来适配示例。不额外安装torchvision/torchaudio，除非依赖需要。

GPU环境服务器自检示例：

```bash
"$W2_ENVS/w2-tsicl/bin/python" - <<'PY'
import torch
print('torch', torch.__version__, 'runtime', torch.version.cuda)
assert torch.cuda.is_available(), 'CUDA unavailable'
print('gpu', torch.cuda.get_device_name(0))
print('bf16', torch.cuda.is_bf16_supported())
x = torch.ones((256, 256), device='cuda')
y = x @ x
torch.cuda.synchronize()
assert torch.isfinite(y).all()
print('peak_bytes', torch.cuda.max_memory_allocated())
PY
```

它只证明基础运算正常，不代替模型验收。

### 3.5 官方源码与锁定

已存在目录先检查remote与修改。首次拉取后立即记录commit，正式实验不再自动git pull：

```bash
git clone https://github.com/EDF-Lab/ts-icl.git "$W2_ROOT/third_party/ts-icl"
git -C "$W2_ROOT/third_party/ts-icl" rev-parse HEAD
git clone https://github.com/amazon-science/chronos-forecasting.git "$W2_ROOT/third_party/chronos-forecasting"
git -C "$W2_ROOT/third_party/chronos-forecasting" rev-parse HEAD
```

记录真实commit，核对该版本pyproject与示例。以下constraint必须与上一步实际选定torch一致：

```bash
mkdir -p "$W2_ROOT/logs/v43/install"
printf '%s\n' 'torch==2.9.1' > "$W2_ROOT/requirements/torch-bootstrap.txt"
"$W2_ENVS/w2-tsicl/bin/python" -m pip install --dry-run \
  -c "$W2_ROOT/requirements/torch-bootstrap.txt" "$W2_ROOT/third_party/ts-icl"
"$W2_ENVS/w2-tsicl/bin/python" -m pip install \
  -c "$W2_ROOT/requirements/torch-bootstrap.txt" \
  --report "$W2_ROOT/logs/v43/install/tsicl.json" "$W2_ROOT/third_party/ts-icl"
"$W2_ENVS/w2-chronos/bin/python" -m pip install --dry-run \
  -c "$W2_ROOT/requirements/torch-bootstrap.txt" "$W2_ROOT/third_party/chronos-forecasting"
"$W2_ENVS/w2-chronos/bin/python" -m pip install \
  -c "$W2_ROOT/requirements/torch-bootstrap.txt" \
  --report "$W2_ROOT/logs/v43/install/chronos.json" "$W2_ROOT/third_party/chronos-forecasting"
```

不要用--no-deps隐瞒冲突。安装后每个环境运行pip check并保存精确freeze。当前TS-ICL可要求NumPy2及更新scikit-learn，因此不能与core强行合并。旧tsicl==0.2.1复现和新官方版本分别记录。

```bash
for W2_ENV_NAME in w2-core w2-tsicl w2-chronos; do
  "$W2_ENVS/$W2_ENV_NAME/bin/python" -m pip check || break
  "$W2_ENVS/$W2_ENV_NAME/bin/python" -m pip freeze --all \
    > "$W2_ROOT/requirements/$W2_ENV_NAME.freeze.txt"
done
```

仅冻结已通过检查的环境，失败项必须修复后重跑；freeze文件还需配套Python版本和实际wheel来源。

## 4 模型、缓存与验收

优先TS-ICL、Chronos-Bolt，再Chronos2、独立TimesFM家族。MOMENT按重建用途复用。模型名称和能力不能混淆：

| 作用                      | 模型                                     |
| ------------------------- | ---------------------------------------- |
| 基础插补与covariate强对照 | TS-ICL旧验证revision和官方新revision分列 |
| 快速目标模型              | amazon/chronos-bolt-base                 |
| 近期目标模型              | amazon/chronos-2                         |
| 独立模型家族              | TimesFM2.5与TimesFM3各自明确注册         |
| 可选重建                  | AutonLab/MOMENT-1-large                  |

设置独立缓存，优先官方来源：

```bash
export HF_HOME="$W2_CACHE/huggingface"
export PIP_CACHE_DIR="$W2_CACHE/pip"
export HF_HUB_DOWNLOAD_TIMEOUT=120
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$PIP_CACHE_DIR"
```

不默认继承旧HF_ENDPOINT。网络受限时仅使用经确认的来源并核对revision/hash，不关闭TLS。下载所需权重和配置，不下载全部预训练语料。逐模型下载保留断点。

`model_manifest.json`至少含repo_id、真实revision、snapshot路径、权重hash、官方代码commit、环境lock hash、dtype、capabilities、license。首次解析revision后固定，不能把main当作复现版本。

附件已有验收命令，以下参数确实存在：

```bash
cd "$W2_ROOT"
PYTHONPATH="$W2_ROOT/src" "$W2_ENVS/w2-chronos/bin/python" \
  scripts/verify_backends.py --device cuda \
  --backends chronos:amazon/chronos-bolt-base \
  --out results/v43/backend_bolt.md
```

该命令只验旧Chronos接口。Chronos2、多变量、TimesFM3需新worker验收，不虚构旧脚本的--batch-size参数。旧make_pool会跳过失败后端，旧preset可能混入surrogate，正式路径必须检查与冻结manifest完全一致。surrogate仅作接口测试。

检查输出shape、单位、horizon、不同长度batch、NaN处理、covariate模式、固定种子复测和峰值。TimesFM应检查实际模型参数在GPU，而非仅检查torch.cuda可用。正弦上不如naive是诊断线索，不自动证明接口错误。

## 5 当前状态和方法增量

正式incumbent为PICS_joint_relabel，旧771窗记录bcov0.2727、repair gain0.0919、CHR0.2053、pme0.0091、damage0.0402。v4.2诊断集成bcov0.3205，但gain0.0945、CHR0.1019、pme0.0060、damage0.0208，未晋升。这些是附件记录，需原数据才能重算。

旧gain是治理序列相对clean的重建误差改善，不是TSFM实际预测收益。v4.2九个长缺口proposer覆盖81/89个安全窗口，只比TS-ICL多6。8个共同失败窗口中6个来自USTS，原候选未用同步通道。

本轮保留KEEP、FACT_SHORT、TSICL_LONG和PICS非插补提案，新增：跨通道严格OOF残差修正、真实task gain学习、有实际成本的工具价值选择、全部新旧提案统一复核。最多两轮额外工具获取，最终一次commit。

v3.4已做伪缺口验证，v3.5已做成对历史预测探针，v3.9不确定性门控失败，v4.0大型反事实critic迁移失败。新贡献是候选利用的新信息及其任务和成本增量，不能把旧probe换名。TATO、任务导向插补评价、ACO、CoRel已覆盖相邻思想，须设强对照。[5][6][7][8]

## 6 必须先处理的代码入口

| 入口                                     | 问题                                          | 要求                                                   |
| ---------------------------------------- | --------------------------------------------- | ------------------------------------------------------ |
| v33_labels.compute_action_labels         | gain是重建收益                                | 保留旧语义，另建task evaluator                         |
| v41_mask_counteract.calibrate_tau        | 权重只改单调覆盖目标，风险约束未加权          | 更正文档，不能据相同阈值否定真正风险重加权             |
| v42_portfolio_act.gain_lookup            | 非TS-ICL gain不全                             | 全候选统一标签，缺值不当0                              |
| v42_portfolio_act.stage_phase0b          | 旧commit锁死                                  | 新旧提案最后统一决策                                   |
| v40_counterfactual_bank.isolation_report | hash隔离未证明时间区间隔离                    | 增加原始区间与同步组检查                               |
| downstream.make_pairs                    | NaN删点压缩时间轴，旧流程可能治理后再切训练对 | v43禁止复用该切窗路径，先定context/future再治理context |
| backends.make_pool                       | 跳过失败后端                                  | 正式实验显式检查，不静默降级                           |
| 旧encoder/probe特征                      | 代理特征不一定是真层表征                      | 不把token分块称为真实TSFM层特征                        |

静态发现的是风险，不据此断言所有旧结果都泄漏。旧算子、label、trace和canonical metric可复用，新任务接口及切分单独实现。

## 7 数据获取、切分与缺陷

恢复ETTh1、ETTh2、ETTm1、Crypto、USTS、Oil的原始文件和时间映射。ETT按作者来源，TIME按官方仓库和原数据说明恢复。[9][10] 现有time_export.py有--root和--out，但先核对布局。新主任务保留真实时间或明确统一交易日索引，不能逐通道删除NaN。

新增来源优先Electricity、Weather、Traffic中的两个，记录身份、许可、时间和频率。ETTm2不算全新领域。不可用来源记录后继续其他数据，不用同名不同内容替代。

按 `source + panel + 原始时间区间` 先切分再产生窗口。重叠窗、同步通道、同parent污染及候选同组。没有官方split的新治理轨道默认时间顺序60% train、15% dev、10% calibration、15% test。全部读取范围必须落在同split。

默认context512、horizon96和192，不额外读取更长历史。最长完整读取范围704步，剔除跨边界窗口。以后加历史检索需扩大读取范围审计。train内部再按时间组70% scorer-fit、30% acquisition-fit，后者用于生成未被scorer直接拟合的工具价值标签。

dev用于方法选择，calibration只校准冻结策略族，test一次最终评价。LODO来源迁移与chronological主轨道分开。允许目标域已发生历史校准时不能称完全未见域zero-shot。旧771/89永久开发，换seed但重用parent不算独立终测。

先固定原始context与future，再只对context治理。future不用于通道选择、归一化、治理或选样。自然缺失future采用事先固定的共同评分mask并报告覆盖，或采用对所有方法一致的完整future轨道。不能按方法输出finite与否分别删样本。

| 缺陷条件      | 默认设置                                 | 目的                   |
| ------------- | ---------------------------------------- | ---------------------- |
| 原始输入      | 保留自然状态，不加污染                   | 原生模型与自然任务效果 |
| point missing | 历史观测中追加5%、10%缺失                | 短缺口                 |
| target block  | 目标通道单块，长度5%或10% context        | 长缺口                 |
| shared block  | 目标与部分/全部兄弟通道共同缺失          | 辅助证据失效           |
| spike         | 固定训练尺度和旧注入定义                 | 非插补治理             |
| valid event   | 不加污染的真实变化与极值，统一预定义规则 | 保护层                 |

30%重缺失为可选预注册stress，不看测试后临时加入有利分布。合成隐藏真值仅供标签，辅助通道也来自部署可见dirty输入。自然缺失没有clean，repair字段为null。

## 8 方法代码目录与接口

以下v43模块均待实现。core用文件协议调模型worker，每个worker分片内加载一次模型，不能每窗重载。

| 文件，位于src/introact_ts/v43 | 接口与职责                                                 |
| ----------------------------- | ---------------------------------------------------------- |
| schemas.py                    | Episode、Candidate、Evidence、Decision、ForecastResult     |
| data_contract.py              | build_panels、split_intervals、build_episodes、audit_reads |
| candidates.py                 | generate_base、residual_correct                            |
| workers/tsicl_worker.py       | 单变量与官方covariate impute                               |
| workers/chronos_worker.py     | Bolt、Chronos2显式forecast                                 |
| workers/timesfm_worker.py     | 2.5与3分别forecast                                         |
| worker_protocol.py            | submit_batch、verify_response、缓存与失败                  |
| task_labels.py                | evaluate_pair，唯一隐藏future读取层                        |
| features.py                   | extract_available_features                                 |
| scorer.py                     | fit_utility、fit_harm、score_actions                       |
| acquisition.py                | fit_tool_value、select_tool                                |
| policy.py                     | run_episode                                                |
| calibration.py                | calibrate_policies                                         |
| evaluation.py                 | aggregate、paired_compare                                  |
| adaptation.py                 | export_training_pairs、run_fixed_recipe                    |
| cli.py                        | 统一子命令、状态文件与重入                                 |

数据对象接口草案：

```python
@dataclass(frozen=True)
class Episode:
    uid: str
    parent_group: str
    split: str
    timestamps: np.ndarray       # [L]，递增
    target: np.ndarray           # [L]，允许NaN
    observed_mask: np.ndarray    # [L] bool
    covariates: np.ndarray       # [L,C]，允许NaN
    covariate_mask: np.ndarray   # [L,C] bool
    availability: np.ndarray    # 各输入真实可用时刻
    horizon: int
    context_end: int
    metadata: dict               # source仅审计，不作域ID学习特征

@dataclass(frozen=True)
class Candidate:
    episode_uid: str
    candidate_id: str
    family: str
    proposer: str
    target: np.ndarray
    touched_mask: np.ndarray
    applicable: bool
    reason: str | None
    provenance: dict

@dataclass(frozen=True)
class ForecastResult:
    episode_uid: str
    candidate_id: str
    prediction: np.ndarray      # [H]，原始单位
    quantiles: dict | None
    model_revision: str
    input_hash: str
    runtime_seconds: float
    peak_gpu_bytes: int
```

实现时补import和验证。Episode不放clean、future、true_kind、oracle。标签按uid另存，评价显式读取。NPZ用allow_pickle=False，JSON合法null，不传不明pickle。

请求含schema_version、request_id、模型revision、数组路径/hash、task、horizon、dtype、seed、covariate模式、batch size。响应返回同request_id/revision、shape、单位、hash、耗时和能力。

调度用subprocess参数数组与check=True，不拼shell字符串。重试只用于可确认的瞬时下载/IO故障，不失败后换checkpoint或返回全零。

缓存key覆盖治理输入、raw mask、辅助通道、cutoff、参数、model revision、代码/环境hash、horizon、dtype、归一化。schema变化即失效。下载缓存与实验预测缓存分开。

## 9 跨通道残差候选的具体算法

### 9.1 输入和默认参数

记目标dirty context为x，真实缺失位置为M，同期可用兄弟通道为Z。任何available_at晚于当前origin的值按缺失处理，不能从clean parent恢复辅助通道。默认选择3个不重叠、目标值有限的伪缺口块B1、B2、B3，长度与当前长缺口等级匹配，选择规则只依赖时间、mask与固定seed，不扫描隐藏标签挑容易窗口。

首版ridge固定alpha=1.0，eta候选为0、0.5、1。eta=0与原TS-ICL候选去重。每个外层训练至少32个有效残差点，辅助特征维度最多8。通道多于8时，在当前外层训练支持上做不使用目标标签的标准化与PCA，维度为min(8、可用通道数、训练样本数整除8)，不足1维则不适用。

辅助缺失采用当前训练支持的逐列median填充并附missing indicator，PCA/scaler也只能fit训练支持。实际缺口处基础辅助通道可观测比例默认至少50%，不满足时此工具不适用。以上是首轮工程参数，不是理论成立条件；可以在dev内有据调整一次，随后冻结，不能以test选择。

### 9.2 严格嵌套遮挡

评估外层块Bk时，其他训练残差的基础预测也必须看不到Bk。只在ridge训练表中删除Bk，仍可能泄漏，因为基础插补器可能已读取其值。

对每个k：

1. 创建目标mask为M并上Bk的只读视图，任何生成步骤不可读取x[Bk]。
2. 对每个i不等于k，使用mask `M ∪ Bk ∪ Bi` 调基础单变量插补器，训练残差为 `x[Bi] - base[Bi]`。
3. 只在这些训练残差点上fit辅助通道预处理和ridge。外层所有目标归一化同样排除Bk。
4. 使用mask `M ∪ Bk` 产生外层基础预测，在Bk同期Z上预测残差，得到修正预测。
5. 先冻结该外层输出，再读x[Bk]计算验证MAE、误差改善、折间差异和支持量。

伪代码：

```python
for k in range(3):
    train_blocks = [i for i in range(3) if i != k]
    residual_rows = []
    for i in train_blocks:
        masked = mask_target(view, M | B[k] | B[i])
        base = imputer(masked)
        residual_rows.append((Z[B[i]], x[B[i]] - base[B[i]]))
    transform, ridge = fit_on_training_rows(residual_rows)
    base_k = imputer(mask_target(view, M | B[k]))
    pred_k = base_k[B[k]] + eta * ridge.predict(transform(Z[B[k]]))
    freeze_prediction(pred_k)
    evidence[k] = evaluate_observed_block(pred_k, x[B[k]])
```

代码必须把mask表示成布尔数组或集合，不能让 `|` 对整数索引产生错误位运算。实现中的x[Bk]仅在评分函数持有，policy得到的是有限标量证据，不得到其他隐藏真值。

最终实际缺口候选用单块mask `M ∪ Bi` 得到三个OOF残差，再fit最终ridge，以原实际缺口基础预测m生成：

\[
\tilde x_t=m_t+\eta\hat h(Z_t),\quad t\in M.
\]

缺口外逐点保持x不变。3个单块、3个无序双块、1个实际缺口输入，最多7种基础输入，可在模型、输入和归一化完全相同时复用缓存。7种输入不等于7个GPU kernel，内部调用和模型加载成本仍实测记录。

伪块验证只是在当前已观测位置的证据，不自动等于真实缺失处正确性。双块与实际缺口的信息量不同，需报告mask差异，不用它产生无条件安全证书。支持不足返回unsupported并保留其他候选。

### 9.3 强对照

直接跨通道ridge使用相同Z、mask和正则化预算，直接预测target。另做一个直接ridge使用所有合法已观测历史的强版本，避免因刻意限制训练支持而低估简单方法。

TS-ICL官方covariates使用相同全部合法通道，按真实官方API实现，不猜参数名。对照不得只接收单变量输入。若原生多变量或简单ridge已解释全部提升，残差方法独立贡献未成立，不能拿候选oracle增加作为算法胜利。

## 10 真实TSFM效用与历史验证

### 10.1 评价标签

每个origin的所有方法预测同一未来y，任务收益定义为：

\[
\Delta_{task}(a)=\ell(F(x_{KEEP}),y)-\ell(F(x_a),y).
\]

新主指标为MASE，辅助MAE、MSE及支持时的WQL。MASE尺度只由声明的原始train历史计算，对同序列所有臂相同。季节周期来自数据频率和冻结配置。分母退化时标记MASE不适用，单列MAE，并对所有方法采用相同集合，不能偷偷置1后仍称标准MASE。

先序列和origin平均，再按horizon/缺陷固定权重汇总，最后source等权宏平均。额外报告ETT家族合并结果，避免相近来源重复放大。不得用KEEP误差接近0的逐窗百分比做主聚合。

每条记录分开保存repair_gain、repair_harm、task_gain、task_harm、protected_edit。旧repair定义原样保留。新task_harm默认表示原始单位MAE比同origin KEEP增加超过数值容差，报告发生比例与幅度，不直接照搬旧CHR<=0.10当成未来预测风险必达目标。

候选不适用和策略拒绝时走KEEP，仍计入完整分母。模型接口故障属于实验失败，不能悄悄当KEEP或删除失败窗口。所有请求必须有一一对应响应。

### 10.2 KEEP和输入信息

KEEP表示治理identity。模型原生支持NaN时直接按官方接口传入；不支持时所有方法共享固定、公开的预处理。旧forward-fill KEEP另列回归，不强迫原生强模型使用较弱占位方式。

主评估声明单变量或多变量信息模式。多变量轨道所有治理方法和适用backbone接收相同历史Z。单变量轨道不能让ours独享Z。若研究让单变量backbone借助治理吸收Z，单独标记为系统扩展，并纳入原生多变量KEEP对照，不与严格单变量表混称胜利。

治理产生的标准化或逆变换必须正确恢复原始单位。模型内部官方normalization可保留。外部scaler若使用，应从固定train或同origin raw context拟合，不能让每个方法通过改变评估尺度获得优势。

### 10.3 历史预测验证工具

工具最多选两个历史原点r，满足 `r + H <= 当前origin`，其评价段已实际发生。对每个r重新构造as-of-r视图、按当时可用数据重新生成候选和预测，再读后续H步作为工具证据。

不能将当前完整context已经修好的序列裁到r后做验证。当前修复器可能读过r之后的值，那样会泄漏历史验证目标。发布延迟同样按r处理。

历史origin默认H=32作廉价验证，当前主任务仍H=96/192。这个proxy与真实任务的关系必须由train/dev学习并单独消融，不能把H32验证直接当H192真实收益。

读取边界固定在当前context内部。用当前数组的exclusive cutoff索引表示，两个r为L-64和L-32；每次模型输入仅为当前dirty数组 `X[:r]`，验证段为 `X[r:r+32]`。L512时历史输入长度分别448和480，不能为了补足512而读取当前context之前的值。最短前缀支持设为256；不足或当前已知验证标签太少时返回unsupported。后端若需固定长度，只按官方规则做无新信息的padding并记mask；不支持时该工具对该后端不适用。验证标签使用当下已知的dirty历史及共同有效mask，不读取合成clean。历史输入更短和可能含污染属于proxy局限，单独记录。

## 11 轻量动作评分和主动工具选择

### 11.1 动作评分器

首版采用单一模型族HistGradientBoosting：utility regressor拟合task_gain，harm classifier拟合可获得的修复危害标签。支持不足或单类标签时明确退化为常数先验，不当作已学到风险分辨能力。

启动参数固定max_iter=100、max_leaf_nodes=7、learning_rate=0.05、min_samples_leaf=20、l2_regularization=1、early_stopping=False。不要使用随机拆行early stopping，因为同parent的候选和状态高度相关。调整只在dev进行一次并留痕，不能多族多seed无界搜索。

输入白名单包含dirty统计、raw mask、动作族、候选相对原输入变化、已经取得的残差验证/历史验证证据、支持量和missing-evidence indicator。禁止source ID、uid、文件路径、真实污染类别、seed、clean、future和实际task_gain进入特征。预测的模型输出变化可以用，但运行该预测的成本必须记账。

按parent加权，避免一个窗口因候选多或可达状态多而重复扩权。最初终态策略为在通过结构契约和预定义风险门的候选中选择预测task_gain最大且大于0的动作，否则KEEP。

首版动作门明确为结构合法、候选适用、预测repair-harm概率不超过tau且预测task_gain大于0，tau初值0.10；它是评分阈值，不能等同于真实CHR保证。完整风险校准前固定tau候选族 `[0.0, 0.05, 0.10, 0.20, 0.50, 1.0]`，各成员的动作门、获取策略和预算规则都先在train/dev建立并冻结，再在calibration重跑完整轨迹，不能只改终态阈值却沿用另一策略的证据。自然缺失的repair标签为null，不混入无害负例；对应风险主张只覆盖有有效标签的评价总体。非插补动作按旧算子允许写入区域校验，零写入违例不表示禁止所有合法有限值修复。

### 11.2 工具集与状态

首版工具固定三项：

| 工具ID        | 输出                       | 主要成本                     |
| ------------- | -------------------------- | ---------------------------- |
| residual      | 跨通道残差候选和OOF证据    | 最多7类基础输入推断、CPU回归 |
| tsicl_cov     | 官方多变量候选             | 多变量TS-ICL推断             |
| history_probe | 两个历史原点的成对验证证据 | 按as-of重建及目标TSFM调用    |

原始Z读取是基础输入，不能人为收费。ToolSpec声明前置条件、可读状态键、输出键、最大调用次数、成本估计、缓存key和超时。最多两轮、同key不重复，没取得工具时其候选、置信度和输出均不能提前暴露。

### 11.3 工具训练标签

在train内对完整工具集收集离线ledger。动作评分器先在scorer-fit parents拟合，再在未使用的acquisition-fit parents构造状态。正式扩展可用分组OOF评分器获得更充分训练行。

固定评分器g对状态s和取得工具q后的状态各选一个动作，工具标签为：

\[
v(s,q)=L(g(s),y)-L(g(s\oplus q),y)-\lambda c(q\mid s).
\]

标签允许为负。不能把知道真值的逐样本最优动作oracle用作g，再报告模仿精度证明工具价值。构造所有合法的有序工具轨迹状态，不按真实收益挑状态。特征只能来自获取前s。

工具集相同不代表状态相同：history_probe先于residual时不能包含后来才取得的残差候选证据。state保存有序history，历史工具key包含当时可见candidate IDs和hash、历史原点、horizon及as-of输入hash。后来新增候选保留missing-evidence，不回填免费验证。每个工具首版最多调用一次；三工具两轮的路径最多为1个空路径、3个单步和6个有序双步，按前置条件和预算剪枝。不限预算全工具对照可独立运行三步，必须标明额外成本与轮数。

用同一浅层回归模型学习条件平均工具价值。选择正预测价值最大的适用工具，若无正值、预算耗尽或无适用工具则停止。该首版为最多两轮的局部策略，不声称全局最优RL。

lambda在dev上选，默认候选为0、0.1、1乘以训练集task_gain中位绝对值/工具成本中位数，尺度与样本清单冻结。若中位值退化则记录并改用预定义IQR尺度，不借测试调单位。

同一工具集比较固定顺序、随机、简单不确定性、全工具、学习获取。离线模拟可复用test工具ledger，但必须隔离未取得结果并计入其实际生成成本，正式至少做一次真实在线按需调用回放，验证模拟与真实决策一致。

### 11.4 Agent循环

```python
def run_episode(view, policy, budget):
    state = initialize(view, base_candidates(view))
    for _ in range(2):
        q = policy.best_positive_tool(state, budget)
        if q is None:
            break
        result = execute_tool(q, state)
        budget.charge(result.actual_cost)
        state = state.with_result(q, result)
    decision = policy.choose_action_or_keep(state)
    verify_write_contract(view, decision)
    return commit_once(decision), state.trace
```

执行工具前按预估成本检查预算，运行中遇超限应在安全边界停止或记录overrun，不能把超过预算的结果当同预算完成。旧PICS提案不提前commit，全部最终复核，才有可能减少既有误改。

这里的budget默认表示额外工具预算B_extra。初始化也计时，单独记录C_base，选择器计算记录C_selection，端到端治理成本为 `C_total=C_base+C_tools+C_selection`，基础TS-ICL/PICS推断不免费。声称同总预算时启用B_total模式，在取得下一工具前扣除已发生基础与选择成本；起始阶段已超预算的策略记infeasible，不进入该预算层的完成排名。评价指标所需的共同未来预测成本另列；若预测同时被策略当证据使用，其相应调用还须计入治理成本且不能重复扣费。

## 12 统一配置和CLI契约

### 12.1 初始YAML

执行agent创建 `configs/v43/bootstrap.yaml`。以下是明确起点，真实路径和revision先解析并写入manifest，不能保留占位值进入正式run：

```yaml
schema_version: 1
experiment: introact_ts_v43
mode: development
seed: 101
runtime:
  device: cuda:0
  heavy_gpu_jobs: 1
  cpu_jobs: 1
  blas_threads_per_job: 1
  dataloader_workers: 0
  inference_batch_size: 4
  shard_origins: 32
  label_access: train_dev_only
data:
  context: 512
  horizons: [96, 192]
  extra_history: 0
  split_ratio: [0.60, 0.15, 0.10, 0.15]
  train_scorer_fraction: 0.70
  split_unit: source_panel_raw_interval
  future_covariate_values: false
  corruption_seeds: [101, 313, 727]
  mase_degenerate: report_mae_separately
method:
  base: [KEEP, FACT_SHORT, TSICL_LONG, PICS_NON_IMPUTE]
  residual_blocks: 3
  residual_alpha: 1.0
  residual_eta: [0.0, 0.5, 1.0]
  residual_min_fit_rows: 32
  residual_max_features: 8
  covariate_min_observed_fraction: 0.50
  scorer_family: hist_gradient_boosting
  scorer_max_iter: 100
  scorer_max_leaf_nodes: 7
  scorer_early_stopping: false
  tools: [residual, tsicl_cov, history_probe]
  max_tool_rounds: 2
  history_probe_origins: 2
  history_probe_horizon: 32
  history_probe_min_context: 256
  harm_score_tau: 0.10
  harm_score_tau_family: [0.0, 0.05, 0.10, 0.20, 0.50, 1.0]
  budget_mode: extra
evaluation:
  primary: source_macro_mase
  secondary: [mae, mse, repair_gain, repair_chr, pme, damage, task_harm]
  keep_modes: [native, legacy_forward_fill]
  bootstrap_unit: source_raw_time_block
  bootstrap_repeats: 2000
  confirm_bootstrap_repeats: 10000
  risk_mode: empirical_grouped
promotion:
  dev_min_relative_primary_gain: 0.01
  min_nonfamily_sources_positive: 2
  protected_mase_relative_tolerance: 0.02
  observed_write_violations: 0
  confirm_method_frozen: true
```

1%提升和保护层2%容忍是本轮工程起点，不是ICLR标准，也不是已达成结果。第一轮pilot后如需调整，要在新dev主实验和确认集打开前登记理由与配置版本。没有显著性或来源支持时不能单凭1%晋升。

模型清单、数据集列表、日期边界、季节周期、输入信息轨道和工具预算秒数分别放manifest。所有必需字段缺失时CLI拒绝正式freeze。不要在YAML中把环境变量字符串当成已经展开的路径，解析器须显式解析并保存最终resolved config。

### 12.2 统一命令

以下是待实现CLI。先写 `python -m introact_ts.v43.cli --help` 和对应子命令，再运行，不能直接拿文档中的命令冒充已经可用。

```bash
cd "$W2_ROOT"
export PYTHONPATH="$W2_ROOT/src"
export W2_CORE_PY="$W2_ENVS/w2-core/bin/python"
export W2_CONFIG="$W2_ROOT/configs/v43/bootstrap.yaml"

"$W2_CORE_PY" -m introact_ts.v43.cli preflight --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli inventory --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli data --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli verify-adapters --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli pilot --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli candidates --config "$W2_CONFIG" --split train,dev
"$W2_CORE_PY" -m introact_ts.v43.cli task-labels --config "$W2_CONFIG" --split train,dev
"$W2_CORE_PY" -m introact_ts.v43.cli train-scorer --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli build-tool-ledger --config "$W2_CONFIG" --split train,dev
"$W2_CORE_PY" -m introact_ts.v43.cli train-acquisition --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli evaluate --config "$W2_CONFIG" --split dev
```

这些不是无条件顺序全部执行的shell脚本。每阶段检查依赖和继续门后再运行下一步。正式后续契约：

为使训练依赖闭合，`candidates`在train/dev收集基础候选及合法有序轨迹的工具输出cache，包括历史验证的as-of结果，不能只生成终态数组。`task-labels`补齐候选真实future误差；`train-scorer`只在scorer-fit parents枚举这些轨迹的可见特征拟合，其他结果遮蔽。之后`build-tool-ledger`使用已固定评分器，在acquisition-fit parents对同一缓存计算前后部署动作的真实效用差。物理cache可先收全，策略视图必须按状态隔离；它不意味着推理时可以免费读取全工具。

```bash
"$W2_CORE_PY" -m introact_ts.v43.cli freeze-method --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli calibrate --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli adapt --config "$W2_CONFIG" --split train,dev
"$W2_CORE_PY" -m introact_ts.v43.cli freeze-confirm --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli confirm --config "$W2_CONFIG"
"$W2_CORE_PY" -m introact_ts.v43.cli report --config "$W2_CONFIG"
```

`freeze-method`固定全部方法、校准策略族和适配recipe，`freeze-confirm`固定校准结果与适配checkpoint后才允许test。不要使用同一个可变config覆盖旧run。CLI产生唯一run_id与resolved config，追加运行显式--resume RUN_ID且全部hash相同。

## 13 分阶段实验

### P0 迁移与环境

产物为asset_inventory、environment_report、模型manifest和精确lock。完成core、TS-ICL、一个真实forecast backend即可进入接口开发。可选模型失败不阻塞其他分支。

### P1 数据和模型接口

实现数据对象、时间契约、worker及第18节语义测试。先使用train/dev中32个来源均衡origin，L512、H32检查接口和峰值。H32只是pilot，正式主实验仍按H96/192。不接触calibration/test标签。

### P2 新候选机制

先3个不同机制来源，每源最多64个合法dev origin。若USTS、Oil可用区间太短，不强凑独立窗口数量，报告真实数量，补长公开来源。禁止高度重叠窗口假装独立样本。单一seed101起步。

固定臂：

| 臂   | 内容                                | 归因                     |
| ---- | ----------------------------------- | ------------------------ |
| A0   | native KEEP与旧forward-fill KEEP    | 基础输入处理             |
| A1   | PICS与v3.9 D，原始实现可得时        | 历史参照                 |
| A2   | TS-ICL单变量                        | 基础proposer             |
| A3   | TS-ICL官方covariates                | 同信息强基线             |
| A4   | 直接跨通道ridge，含全合法历史强版本 | 简单关系能否解释提升     |
| A5   | 严格OOF残差候选，统一静态选择       | 新候选最低实现           |
| A6   | 同工具全部调用                      | 完整效果与成本           |
| A7   | 固定顺序、相同预算                  | 主动策略参照             |
| A8   | 条件价值工具选择                    | 完整方法                 |
| A9   | 标签oracle                          | 仅开发上界，不作部署排名 |

P2先完成A0–A5和上界，不先训练A8。不同信息轨道分别评估。保存所有候选原始预测和真实future误差，不只汇总表。

A5在学习scorer之前采用明确静态规则：在eta=0、0.5、1上比较三个外层伪块的等块平均MAE，严格优于eta=0才采用修正，平局选更小eta，支持不足退回基础TS-ICL。该规则只读取可见伪块证据，不按真实future选择eta；单列这个静态臂与后续task scorer版本，避免实现时悄悄换选择规则。

继续条件为新信息存在真实task headroom，且至少两个非同族来源有正向线索。若新候选oracle都无正向空间，先检查候选、mask、单位和模型接口，不继续堆选择器。oracle有提升但简单强基线同样实现时，必须如实归因。

### P3 可部署选择器与预算

扩到全部可用train/dev来源。拟合一个scorer、完整工具ledger、固定顺序策略，确认可部署静态选择已有价值，再训练工具获取。先seed101，再对有希望版本跑313和727配对复核，不同时搜索大量种子。

工具预算采用实测基准：令C0为train pilot一次完整TS-ICL单变量处理的中位成本，以额外预算B_extra=4C0、8C0两个层为起点，完整工具方案另报不限预算成本。全部报告含基础阶段的C_total；同总预算主张另外按统一B_total运行，不能用相同额外预算掩盖不同基础成本。如果某工具最小成本就超过8C0，应在dev协议冻结前调整可比较层，不把无法调用该工具的预算当它效果差。

调用轮数上限与时间预算同时报告。多变量、历史验证和候选内部所有调用都计成本，不将7类残差输入算成一份零成本证据。

### P4 近期强baseline和跨模型

优先跑以下对照，每个baseline保存官方commit、许可证、适配差异及失败记录：

| 方法                                  | 角色                                  | 官方入口                                                     |
| ------------------------------------- | ------------------------------------- | ------------------------------------------------------------ |
| TATO，ICLR2026                        | 冻结TSFM变换优化，主要直接对照        | [官方代码](https://github.com/thulab/TATO)                   |
| AegisTS，公开论文                     | 完整清洗agent，正式发表状态按当时记录 | [论文](https://arxiv.org/abs/2605.04902)                     |
| SHoTClean，SIGMOD2026                 | 多变量约束清洗                        | [官方代码](https://github.com/ZJU-DAILY/SHoTClean)           |
| EDITOR，ICDE2026                      | 检测定位修复                          | [官方代码](https://github.com/lcy-lucky/Editor)              |
| T1，ICLR2026                          | 多变量插补                            | [官方代码](https://github.com/Oppenheimerdinger/T1)          |
| HELIX，ICML2026                       | 新近多变量插补                        | [官方代码](https://github.com/milaogou/HELIX)                |
| TimeLAVA，ICML2026                    | 数据估值与适配轨道                    | [官方代码](https://github.com/lww28/TimeLAVA)                |
| Task-oriented Imputation，NeurIPS2024 | 下游效用评价/组合                     | [官方代码](https://github.com/hkuedl/Task-Oriented-Imputation) |

表中入口用于取官方实现，不能直接把评分器当完整repair agent。完整原生方法与共享候选池下的选择模块比较分成两张表，分别回答系统效果和方法组件效果。

baseline先在其官方小例验证，再迁入相同split、输入、checkpoint和指标。训练过的插补器与零样本模型分列监督和训练预算。需要参考干净数据的方法必须获得清楚匹配的参考数据，不能暗中少给或多给。

第一阶段用Bolt，第二阶段至少增加一个TimesFM家族。Chronos2与TimesFM3用于近期能力复核。避免所有方法×所有模型×所有数据×所有种子的笛卡尔积。先两主干核心表，再对最终方法和最强少数baseline扩展transfer。

GIFT-Eval、fev、TIME可作外部协议，但加了人工缺陷或只跑子集时应写治理扩展/子集，不能宣称原榜单SOTA。[10][11][12]

### P5 风险校准

冻结完整策略族，包含获取、停止、动作排序、结构检查与KEEP，再在独立calibration运行。首版默认 `empirical_grouped`，提供按来源/时间块风险及区间，不承诺任意时间依赖或OOD上的有限样本保证。

若研究严格证书，在独立可交换episode及有效标签的条件下另做Learn then Test。对固定策略π可令 `Z=I(commit)*(I(harm)-alpha)`，提交概率非0时E[Z]<=0等价于CHR<=alpha。对预定K个策略使用同时有效的检验或置信界，不搜索几百阈值后报告赢家未校正CP95。[13]

例如在独立、有界Z条件下可用Hoeffding上界 `mean(Z)+sqrt(log(K/delta)/(2*n))`。该界可能很保守，样本不足导致无策略通过时，报告无证书，不修改标签或调低置信度假装通过。真实相关时序若不满足前提不能套该公式。

v41旧权重只改coverage的实现不能复用为真正风险加权。校准不通过只影响相应风险主张或版本晋升，不能抹去已观察的任务结果。

### P6 真实TSFM适配

选择一个官方确实支持训练的后端。优先已核实的Chronos或TimesFM适配示例，不能猜 `.fit`、LoRA target_modules或层名。先一个来源验证一个训练步和checkpoint加载，再两个来源完整试验。

固定train pair索引为 `X_raw, X_governed, Y_common`，只治理X。Y_common保持原始future字节一致。用于产生训练X_governed的策略采用独立policy-fit parents或分组OOF输出，不能用同一pair的future标签训练策略后再选动作。

起步recipe为microbatch1、effective batch16、最多200个optimizer steps、一个dev冻结学习率。若官方LoRA兼容，可用rank8/alpha16作为候选起点，但必须依据真实模块名实现。先在train/dev决定recipe，再给所有方法同样初始checkpoint、步数、样本/token、优化器、seed与早停规则。没有官方LoRA时选择明确支持的轻量适配方式，另记参数量，不能伪造LoRA调用。

对照至少raw、强baseline治理、ours治理三组，第一轮seed101，正式有资源再[101,313,727]成对三seed。评估输入也冻结：主表仅改变训练X，所有适配模型用相同原始测试context。若研究推理治理，另做train治理有无×test治理有无的2×2，避免训练与推理混合归因。

仅输入治理有效时，论文限定为推理前治理。只有真实适配收益成立，才称改善TSFM训练数据效用。

### P7 确认性评估

冻结代码、数据时间范围、模型revision、策略、阈值、适配checkpoint、指标和完整臂清单，写confirm_freeze.json与hash。一次运行全部已注册确认臂，不按test结果删臂或新增有利子组。

若发现代码bug，保留失效结果与原因，修复版本不能偷偷覆盖旧确认。旧测试已被看过，应明确其开发身份，并安排新的确认时间块。没有足够新数据时承认限制，不重新贴上untouched标签。

## 14 必做消融与公平条件

最小消融集合：

1. 基础候选 vs 加残差候选，区分候选信息增量。
2. 残差修正 vs 同信息直接ridge和官方多变量TS-ICL。
3. 固定工具顺序、随机工具、不确定性工具、全工具、学习工具价值，同工具集同预算。
4. 全部动作统一复核 vs 仅新动作复核，验证旧误改可被减少。
5. repair-gain scorer vs task-gain scorer，检验目标错位影响。
6. 有无历史probe，证明旧模块在新目标下的增量，不重写其旧失败。
7. 单通道缺失、共同缺失、错误辅助通道、未污染真实变化，检验依赖条件。

禁止使用有泄漏OOF实现作为合法训练主臂。可做污染测试展示泄漏会怎样影响结果，但必须显式标记invalid diagnostic，不能参与方法排名。

公平预算至少同时报告治理训练成本、工具推断成本、目标模型评估成本、适配成本。开发搜索成本与最终每窗推理成本分开，不能只报缓存命中速度。免费读取Z对所有方法一致。

## 15 统计、成功与停止

主表为source macro MASE及绝对MAE/MSE，来源与时间块配对bootstrap。dev2000次、confirm10000次在服务器CPU运行，使用轻量聚合输入，不能把候选、种子、重叠horizon都当独立样本。报告每来源差值、家族合并结果、任务危害幅度和p50/p95成本。

| 情形                                        | 下一步                                     |
| ------------------------------------------- | ------------------------------------------ |
| 时间、未来、mask、单位、缓存或label契约失败 | 停相关分支修代码，其他独立任务可继续       |
| 新候选oracle无真实任务空间                  | 停选择器扩张，回候选与输入信息             |
| oracle有空间、部署选择器无增益              | 看排序与证据，不再堆无依据大critic         |
| 只有USTS好、其他来源无效                    | 不能称通用治理，检查依赖条件及跨域表示     |
| 只有repair改善、task不变或更差              | 不能晋升为TSFM效用成果                     |
| simple ridge/原生covariate已同样好          | 候选独有贡献未成立，检验统一复核和成本增量 |
| 全工具便宜且最好                            | 主动获取主张未成立，不人为造费用           |
| 风险校准无通过点                            | 报告无证书，检查风险对象和样本支持         |

开发晋升默认要求较上一可比版本宏平均主指标改善至少1%、至少两个非同族来源正向、保护事件子集MASE恶化不超过预注册2%、写入契约零违例，并检查成对区间。旧repair指标完整报告，新旧输入信息不同则不直接称严格支配。

正式论文版本须在独立确认集上超过预先指定的强对照，并有跨两个真实模型家族的证据。若对多个baseline作显著性主张，对预定义比较作Holm等多重比较处理。SOTA只描述实际可比且完整运行的集合。1%或任何单阈值都不是oral标准。

## 16 单卡资源与调度

| 资源项             | 16GB系统内存 | 32GB    | 64GB                |
| ------------------ | ------------ | ------- | ------------------- |
| 重GPU任务          | 1            | 1       | 1，默认不并行大模型 |
| CPU辅助进程        | 1            | 1–2     | 2，按实际CPU增加    |
| DataLoader workers | 0起步        | 1–2     | 2–4但仍看8核限制    |
| BLAS线程           | 每进程1      | 每进程1 | 每进程1–2           |
| 推断batch起点      | 4            | 4–8     | 8，仍受24GB显存限制 |
| 适配microbatch     | 1            | 1–2     | 1–2，实测后增加     |

8核机器保留约2核余量，单独CPU任务必要时可设4线程，但不同时让多个进程各开4或8线程。大矩阵用分片与索引，不把全部滑窗和候选表征一次复制进DataFrame。系统内存与显存不能相加当作统一容量。

默认项目激活变量：

```bash
export PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false
```

只有GPU为本项目独占且实时空闲时才增加batch以提高利用率，显存保留约2–3GB余量。共享任务存在时采用更保守上限，显存空闲不证明计算带宽不冲突，观察到他人任务变慢就下调或暂停本项目GPU工作。

使用本项目flock限制自己的GPU任务，它不能约束别人。长任务放tmux或已有调度器，不用SSH连接存活维持实验。tmux示例为系统操作：

```bash
tmux new-session -s work2-v43
```

若同名session存在先attach，不再建重复任务。进入后显式source本项目环境变量，使用完整解释器路径运行已实现CLI。每个run记录PID、启动时间、程序路径和owner。不要执行全局pkill python、killall、GPU reset或自动关机。

每30秒记录GPU使用、显存和本项目RSS，每100个origin记录进度、缓存命中和估计剩余时间。OOM时保存失败分片、降低batch并登记变更，不缩短context/horizon来掩盖超限。仅清理明确属于本项目、可再生且未被结果引用的临时文件。

## 17 工时和租费预算

首批32个origin后估算，不用旧单次预测速度估整个新流程：

\[
T\approx\sum_m N_{unique,m}t_m+T_{CPU}+T_{load}+T_{adapt}+20\%\text{余量}.
\]

分别计数候选生成的单块/双块请求、每个candidate的目标TSFM预测、horizon、历史验证、模型加载及适配。第一次pilot输出每千origin估计和总矩阵估计，再裁掉低价值重复组合，保留关键强对照与机制实验。

截图历史价格为1.57元每小时，连续24小时37.68元、11天414.48元，仅算示例，不包含升级、磁盘等未知费用。实际费用以新租实例计费为准。不能承诺11天一定跑完完整矩阵。

建议相对时间：

| 时段      | 目标                                      |
| --------- | ----------------------------------------- |
| T0至2小时 | 接入、资产、core及首个GPU环境             |
| 2至6小时  | 数据契约、模型worker、最小语义测试与pilot |
| 6至12小时 | A0–A5机制、同信息强对照和成本估计         |
| 第2至3天  | scorer、工具策略、全部dev来源与两个主干   |
| 第4至7天  | 近期baseline、关键消融与适配              |
| 第8天以后 | 冻结、校准、确认、全文结果审计            |

以上为优先级窗口，不是速度保证。ICLR2027当前官方北京时间摘要截止9月19日19:59、正文9月26日19:59，执行当天再次核验官方页并倒排。[14] 未到达实验证据门时不在摘要或正文填预计效果。

## 18 必要验收测试

只写能够抓住具体实现风险的测试，不为低风险文档修改扩大全库测试。测试都在服务器。

| 测试                  | 输入设计                                  | 验收                                      |
| --------------------- | ----------------------------------------- | ----------------------------------------- |
| observed write        | 含NaN与真实极值的上下文                   | 残差IMPUTE只写raw NaN，有限值和时间戳不变 |
| outer-mask poison     | 先冻结Bk位置，再改变其中真实值            | 外层预测在评分前不变，抓基础模型间接泄漏  |
| as-of poison          | 改动历史r之后的target与非合法协变量       | r时刻生成的候选/预测不变                  |
| split overlap         | 人工同时间跨通道、重叠窗和污染副本        | 跨split被拒绝，非重复hash也能抓到         |
| native KEEP           | 用有无原生NaN能力的两个adapter stub       | 预处理一致，KEEP对自身task gain为0        |
| worker identity       | 故意错request_id、revision、horizon和单位 | 整批拒绝，不丢行或填0                     |
| hidden-tool poison    | 改尚未取得工具的缓存输出                  | 获取前特征与第一步决策不变                |
| aggregate denominator | 某候选不适用、某策略全KEEP                | origin集合不变，不适用回KEEP，故障单列    |
| adaptation targets    | raw与治理后train pairs                    | Y_common hash、pair IDs和测试输入完全一致 |

outer-mask测试先冻结mask计划，避免值变化改变选块规则从而混淆检查。硬件数值允许预定义精度容差，语义、ID、hash和时间边界严格检查。

示例命令仅在agent创建对应测试后可用：

```bash
PYTHONPATH="$W2_ROOT/src" "$W2_ENVS/w2-core/bin/python" -m pytest \
  tests/v43/test_data_contract.py \
  tests/v43/test_residual_leakage.py \
  tests/v43/test_policy_visibility.py \
  tests/v43/test_task_aggregation.py -q
```

模型实际输出验收在模型环境另跑，不用CPU mock替代真实后端检查。与旧代码共享指标函数被修改时再跑相关旧测试，不默认所有几百项全量重跑。

## 19 结果文件、断点与日志

每个run输出以下最小集合：

```text
run_id/
  status.json
  resolved_config.yaml
  code_manifest.json
  environment_manifest.json
  data_manifest.json
  model_manifest.json
  candidates.parquet
  predictions.parquet
  task_labels.parquet
  decisions.parquet
  trajectories.jsonl
  cost_ledger.parquet
  metrics_by_source.csv
  comparison.json
  harmful_cases.parquet
  summary.md
```

数组可外置分片，表中保存引用和hash。status包含pending、running、blocked_dependency、failed、completed、diagnostic、promoted，说明依赖和错误。所有分片先写临时文件，校验后原子重命名，不在共享文件上多进程append数组。

--resume只复用同代码/config/data/model/hash的已完成分片。不能用mtime或文件存在作为唯一完成证据。旧hash若四舍五入保留为legacy字段，新完整性hash还需覆盖shape、dtype、标准NaN表示与原始字节。

每个异常或改善案例记录source、parent时间范围、target channel、mask、输入/候选hash、工具获取顺序、风险/收益预测、选择动作、真实预测与误差。保存全部harmful及beneficial-rejected案例，方便回到代码。

## 20 分析时回归代码

固定顺序为原始时间和available_at、窗口切分、mask、候选适用性、算子写入范围、模型输入与逆变换、未来标签、最终决策、分母与统计。

| 现象                  | 首先检查                                           |
| --------------------- | -------------------------------------------------- |
| 结果突然大幅提高      | future/covariate泄漏、时间删点、目标改写、重复test |
| 残差OOF极好但真缺口差 | 外层二阶泄漏、mask几何差、支持与共缺失             |
| 只有某个后端好        | 单位/轴、native NaN、真实device、score耦合         |
| 所有方法预测一样      | 缓存key漏candidate hash、worker没用治理输入        |
| CHR下降但收益也消失   | 全KEEP稀释、分母/覆盖改变、阈值过保守              |
| pme始终不变           | 旧commit是否仍被锁死                               |
| oracle异常低          | 候选缺task label、错误跳过非TS-ICL、指标路径不统一 |
| GPU空闲却很慢         | 模型反复加载、CPU超订阅、同步IO、小batch、下载等待 |
| 适配提升异常巨大      | Y被治理、测试context不一致、训练pair泄漏           |

每条归因绑定文件、函数、代码commit、输入记录。没有排除这些实现原因前，不用泛化差或数据不足结束分析。

## 21 文档同步与交付

每阶段更新：

- `docs/v4_3_evidence_governance_design.md`，设计区冻结，结果只追加post-hoc。
- `docs/version_ledger.md`，incumbent、candidate、diagnostic分开。
- `docs/HANDOFF.md`，当前入口、完成内容、阻塞和下一动作。
- `docs/data_provenance_contract.md`，新时间与标签契约。
- `docs/diagnostic-playbook.md`，新增问题与代码定位。
- `docs/CHANGELOG.md`，代码、配置、指标和依赖变更。
- `docs/claims.md`，只写有证据的主张。
- `docs/v43_experiment_matrix.md`，所有臂和预算的完成状态。

保留旧日期和旧结果，不覆盖失败。仅规划或RED分支不更新进度DOCX中的已验证成果，形成正式进展后再按项目原规则生成并在服务器渲染核验。

每个阶段结束向用户报告一句总判定、主指标与区间、资源/耗时、主要失败代码位置、已保存路径和下一步。不要只报模型AUROC而遗漏最终TSFM效果。同步回本地时传代码、配置、文档和关键结果，不自动回传全部多GB缓存。

同git仓库代码正常提交到项目分支，不提交数据与凭据。同步不能使用破坏式--delete覆盖他人工作。至少每日同步本项目成果，停机前确保数据、模型manifest和结果在持久盘并有本地可恢复副本。关闭或释放付费实例仍由用户决定，不自行关机。

最终可复现包应包含环境lock、数据来源与split、代码commit、模型revision、所有配置、原始预测、指标入口、资源账本与失败样本。就业展示聚焦数据契约、质量与任务价值区分、工具调度、血缘、风险和TSFM适配收益，不虚构文本大模型预训练经验。

## 22 本地agent收到文件后的第一轮任务

按此顺序开始，不先跑全量模型：

1. 取得新机连接和本地项目位置，读取最新版本状态，创建本轮分支或快照。
2. 登录新机只读检查，确认持久盘，建立目录和资源预算。
3. 迁移代码、文档及原始数据，列明缺失缓存与旧记录。
4. 隔离安装core、TS-ICL、Chronos，锁定依赖和模型revision。
5. 实现v43数据与worker协议，先通过时间、mask、future和模型接口测试。
6. 实现严格嵌套残差候选及直接ridge、官方TS-ICL-cov强对照。
7. 在train/dev的32个origin跑pilot，记录真实峰值与成本，按原始时间生成真实task标签。
8. 扩A0–A5，先判断新信息是否有任务价值，再训练scorer和工具获取。
9. 逐阶段完成强baseline、跨模型、校准、适配与独立确认，不跳过文档同步和代码归因。

第一份回报应是服务器和资产清单、已装环境、已通过接口、32窗pilot结果或具体阻塞、下一批预计成本。不是泛泛的计划确认，也不是未经实验的SOTA声明。

## 23 官方来源与实施核验

以下链接支撑环境约束、方法对照和评价规范。动态依赖在首次安装时按真实commit再次核验，随后固定。

[1] EDF TS-ICL [官方pyproject](https://github.com/EDF-Lab/ts-icl/blob/main/pyproject.toml)，[官方代码](https://github.com/EDF-Lab/ts-icl)。当前Python>=3.12及torch范围依据。

[2] Amazon Chronos [官方pyproject](https://github.com/amazon-science/chronos-forecasting/blob/main/pyproject.toml)，[Chronos2模型卡](https://huggingface.co/amazon/chronos-2)。

[3] Google TimesFM [官方源码及版本说明](https://github.com/google-research/timesfm)，[pyproject](https://github.com/google-research/timesfm/blob/master/pyproject.toml)。

[4] PyTorch [官方历史版本安装命令](https://pytorch.org/get-started/previous-versions/)，[当前安装指南](https://pytorch.org/get-started/locally/)。示例wheel不是未知驱动上的兼容承诺。

[5] TATO，ICLR2026，[正式记录](https://openreview.net/forum?id=uTK1SNgi1N)，[代码](https://github.com/thulab/TATO)。

[6] Task-oriented Time Series Imputation Evaluation via Generalized Representers，NeurIPS2024，[正式论文](https://proceedings.neurips.cc/paper_files/paper/2024/hash/f88264fcc54775ee1706116e90fe351a-Abstract-Conference.html)。

[7] Acquisition Conditioned Oracle for Nongreedy Active Feature Acquisition，ICML2024，[正式论文](https://proceedings.mlr.press/v235/valancius24a.html)。

[8] Relational Conformal Prediction for Correlated Time Series，ICML2025，[正式论文](https://proceedings.mlr.press/v267/cini25a.html)。

[9] ETT [作者数据仓库](https://github.com/zhouhaoyi/ETDataset)。

[10] TIME [官方仓库](https://github.com/zqiao11/TIME)，[论文](https://arxiv.org/abs/2602.12147)。

[11] GIFT-Eval [官方基准](https://github.com/SalesforceAIResearch/gift-eval)。

[12] fev [官方框架](https://github.com/autogluon/fev)。

[13] Learn then Test [开放论文](https://arxiv.org/abs/2110.01052)。完整策略校准需满足对应假设。

[14] ICLR2027 [官方征稿页](https://iclr.cc/Conferences/2027/CallForPapers)，[作者指南](https://iclr.cc/Conferences/2027/AuthorGuidelines)。

旧状态依据项目附件中的version_ledger、v40/v41/v42 post-hoc以及本文点名的代码函数。新方案的有效性、运行耗时和完整环境兼容性均由服务器执行结果确认。

