# 新服务器首批环境依赖核验

核验日期：2026-09-14。范围仅为环境准备。本文作者只在本地阅读代码、官方文档并编写安装脚本，没有在本地运行测试、安装依赖或下载模型。实际可用状态以服务器安装报告为准。

## 官方约束与本轮选择

| 环境 | 选择 | 原因 |
|---|---|---|
| w2-core | Python 3.11；NumPy 1.26.4；SciPy 1.13.1；pandas 2.2.3；scikit-learn 1.5.2 | 保留附件要求的 NumPy 1 系科学栈，其他首批精确输入见 bootstrap 脚本 |
| w2-tsicl | Python 3.12；torch 2.9.1+cu126；NumPy >=2.1.3,<3；官方源码安装 | 官方现行元数据要求 Python >=3.12、NumPy >=2.1.3、sklearn >=1.8.0、torch >=2.5.1,<2.10、huggingface-hub >=1.19.0；不能与 core 合并 |
| w2-chronos | Python 3.11；torch 2.9.1+cu126；NumPy 1.26.4；官方源码安装 | 官方要求 Python >=3.10、torch >=2.2,<3、transformers >=4.41,<6、accelerate >=1.1,<2、NumPy >=1.21,<3 |

TS-ICL 按官方元数据解析其余依赖，安装成功后固定完整 freeze。Chronos 首批额外约束 transformers 4.57.1、accelerate 1.10.1、huggingface-hub 0.36.0，以维持明确的 transformers 4 系路径。这组输入位于官方声明范围内，当前官方 Chronos 源码保留 transformers 4/5 分支，但仍须由服务器 import 与实际模型验收确认，不能预先称已经测试。

来源：[TS-ICL pyproject](https://github.com/EDF-Lab/ts-icl/blob/main/pyproject.toml)、[Chronos pyproject](https://github.com/amazon-science/chronos-forecasting/blob/main/pyproject.toml)、[Chronos 的版本兼容分支](https://github.com/amazon-science/chronos-forecasting/blob/main/src/chronos/chronos2/model.py)、[transformers 4.57.1 元数据](https://pypi.org/pypi/transformers/4.57.1/json)、[accelerate 1.10.1 元数据](https://pypi.org/pypi/accelerate/1.10.1/json)。

官方提供 torch 2.9.1 的 CUDA 12.6 wheel。给定服务器 NVIDIA 驱动 595.84，CUDA 12.x 程序可依赖较新驱动的向后兼容；不需要升级驱动或安装系统 CUDA toolkit。GPU 名称、可见显存和实际资源以服务器采集为准，不从“4090”名称反推 24GB。[PyTorch 安装记录](https://pytorch.org/get-started/previous-versions/)、[NVIDIA CUDA 兼容表](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)。

## 本地旧接口发现

- 根 requirements.txt 只有宽范围科学栈，没有精确历史 lock；未发现根 pyproject.toml。运行项目时使用 `PYTHONPATH="$W2_ROOT/src"`。
- `src/introact_ts/backends/chronos.py` 使用 `BaseChronosPipeline.from_pretrained(...)`，旧预测调用为 `pipeline.predict(chunk, horizon)`，其轴处理针对 T5 与 Bolt。不能据能加载 Chronos-2 就认定该类具有正确的 Chronos-2 多变量语义。
- 导入 `introact_ts.backends` 会先执行 `introact_ts/__init__.py`。后者导入 scipy、sklearn、statsmodels、ruptures 等，因此 Chronos 环境也必须装这些科学依赖，不能只装 torch 和 chronos。
- 本次在本地 `src/` 与 `scripts/` 搜索未找到 tsicl 的 Python import；TS-ICL 的新独立 worker 仍需实现或从旧服务器恢复。
- `scripts/verify_backends.py` 确认支持 `--device`、`--backends`、`--preset`、`--out`，不支持 `--batch-size`。指定 Bolt 单个后端以免触发尚未安装家族。
- 旧 `make_pool` 会跳过加载失败模型；正式多模型协议不能依赖这种静默缩减。旧 encode 将 token 拆块，不能将其称为真实逐层状态。

## 首批脚本与验收界限

同目录的 `bootstrap-envs.sh` 与 `verify-bootstrap-envs.py` 只运行于服务器，固定：

```text
W2_ROOT=/home/vipuser/work/work2
W2_ENVS=/home/vipuser/work2-envs
W2_CACHE=/home/vipuser/work2-cache
W2_BOOTSTRAP=/home/vipuser/work2-staging/bootstrap-20260914
Conda=/home/vipuser/miniconda3/bin/conda
HTTP/HTTPS 代理=http://127.0.0.1:17890
```

使用现有 conda 的可执行文件，包缓存写入本项目目录；每次创建明确 `--override-channels -c conda-forge`，不修改系统 Python、全局 channels 或 shell 初始化文件。现有 prefix 先核对 Python 次版本；已有第三方 checkout 只接受对应官方 origin 且工作区干净，不 pull、不覆盖。

将两个脚本上传到同一服务器目录后，由主执行 agent 在服务器先检查脚本，再放 tmux 运行。例：

```bash
cd /home/vipuser/work2-staging/bootstrap-20260914
bash -n bootstrap-envs.sh
python3 -m py_compile verify-bootstrap-envs.py
tmux new-session -d -s work2-bootstrap-20260914 \
  'bash /home/vipuser/work2-staging/bootstrap-20260914/bootstrap-envs.sh'
cat /home/vipuser/work2-staging/bootstrap-20260914/status.json
tail -n 40 /home/vipuser/work2-staging/bootstrap-20260914/logs/bootstrap.log
```

先检查同名 tmux session 是否已存在，存在时查看并接续，不能重复启动。脚本另有项目 flock 排他锁。

验收内容包括各环境包 import、Python/NumPy 分代、torch 版本/CUDA runtime、TS-ICL forecast/impute 属性，以及 Chronos/Bolt/Chronos2 类入口。仅在 GPU 无 compute process、利用率低且显存占用很少时执行一次 256×256 tensor 运算；忙时标记 `gpu.status=deferred`。这只能证明环境与 CUDA 基础路径，**不代表模型推断或科学实验已通过**。

产物：

- 原子状态：`$W2_BOOTSTRAP/status.json`，`status` 为 running、failed 或 completed，附每环境验收状态。
- 日志与 pip install reports：`$W2_BOOTSTRAP/logs/`。
- 每环境 `.verification.json`、`.pip-check.txt`、`.platform.txt`、`.pip-inspect.json`。
- 精确 freeze、conda explicit、源码 commit、输入约束、SHA256：`$W2_ROOT/requirements/bootstrap-20260914/`。
- 无模型、无数据集下载；无训练或正式实验。GPU tensor deferred 时保留此状态，之后有空闲再验收。

## 模型 revision 的后续固定办法

首先读取官方源码的模型说明。当前 TS-ICL 官方仓库链接的模型 repo 是 `taharnbl/TS-ICL`，不能按作者组织名猜一个不存在的模型 ID。该模型为非商业许可，许可文本应随 manifest 保存。[官方模型入口](https://github.com/EDF-Lab/ts-icl)、[模型卡](https://huggingface.co/taharnbl/TS-ICL)。Chronos-Bolt 为 `amazon/chronos-bolt-base`，Chronos-2 为 `amazon/chronos-2`；后者具有单独的多变量/协变量接口。[Chronos-2 模型卡](https://huggingface.co/amazon/chronos-2)。

下面是**后续在服务器运行**的 metadata 获取方式，只获取 repo metadata，不下载权重：

```python
from huggingface_hub import HfApi
api = HfApi(endpoint="https://huggingface.co", token=False)
for repo_id in ("taharnbl/TS-ICL", "amazon/chronos-bolt-base", "amazon/chronos-2"):
    info = api.model_info(repo_id, revision="main", files_metadata=True)
    assert info.sha and len(info.sha) == 40
    print(repo_id, info.sha)
    for f in info.siblings or []:
        print(f.rfilename, f.size, f.lfs)
```

将真实 `info.sha` 写进模型 manifest，再给 `snapshot_download(repo_id=..., revision=已记录的SHA, allow_patterns=核对后文件清单)`。不将 `main` 留为最终版本，不一次下载全部仓库历史或预训练数据。保留官方模型卡与许可；计算实际权重 SHA256，并记录 snapshot 路径、官方源码 commit、环境 lock hash、dtype 和验收通过的能力。下载和推断都在服务器。[HF metadata API](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api)、[按 revision 下载](https://huggingface.co/docs/huggingface_hub/guides/download)。

旧 Bolt 脚本验收示例：

```bash
cd "$W2_ROOT"
PYTHONPATH="$W2_ROOT/src" "$W2_ENVS/w2-chronos/bin/python" \
  scripts/verify_backends.py --device cuda \
  --backends chronos:amazon/chronos-bolt-base \
  --out results/v43/backend_bolt.md
```

该旧 adapter 没有 revision 参数。正式运行前应让它从已经固定的 snapshot 路径加载，或由新的 worker 显式传递 revision；不能先下载一个 revision，再让未固定的 repo ID 自动解析新 main。Chronos-2 与 TS-ICL 要分别按其实际官方 API 新建 worker 验收，不能把旧 Bolt 检查当作替代。
