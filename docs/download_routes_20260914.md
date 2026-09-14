# 2026-09-14 当前服务器下载链路诊断

用户询问镜像及不走代理是否更快后，使用 core 环境在当前服务器比较相同固定 wheel。每路最多读取8 MiB，最多2个探测并发；原 Chronos 安装同时进行，因此这些数值只表示当时的小样本链路速度，不能当作完整下载速度或预计完成时间。

| 安装包与来源 | 直连 MiB/s | 原代理 MiB/s |
|---|---:|---:|
| cuDNN 9.10.2.21，NVIDIA官方 | 2.944 | 0.191 |
| 同版cuDNN，清华镜像 | 2.916 | 0.256 |
| Torch 2.9.1+cu126 / cp311，交大镜像 | 0.733 | 0.326 |

NVIDIA官方直连自动重定向至 pypi.nvidia.cn；经代理请求仍在 pypi.nvidia.com，响应明确含 no-cache/no-store。这解释了这次直连更快，以及共享 pip cache 仍可能重复下载同版 NVIDIA 依赖。不能推广为所有站点或未来时段都应关闭代理。

Torch官方索引可读，但索引中的 download-r2.pytorch.org 固定 cp311 wheel 在本次 urllib Range 探测中直连和代理均返回403；不能据此断言现有 pip 完整下载必然失败。交大镜像返回206、ZIP文件头有效，索引SHA256与官方一致；清华cuDNN同样与官方哈希一致。只比对了索引哈希，没有下载整包，未宣称整包已校验。

官方镜像说明：[SJTUG pytorch-wheels](https://mirrors.sjtug.sjtu.edu.cn/docs/pytorch-wheels)，[清华 PyPI](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)。冻结版本没有变更。

## 当前执行状态与配置

原 bootstrap、模型接续、pilot队列和监控未被重启；未向三个prefix并发安装。当前正在运行的pip已继承原代理，修改另一个shell的变量不会使它切线。保留当前下载进度。

新增 scripts/env_download_routes.sh，仅供后续新启动的下载进程在 source scripts/env_new_server.sh 后显式source使用。它将已测试的NVIDIA/国内镜像域名加入NO_PROXY，并提供清华PyPI和交大cu126镜像变量；其他域名保留原代理。当前bootstrap的硬编码配置不会自动读取此文件，因此不得报告现有安装已切换或已加速。未修改全局pip、代理服务、base或现有环境。

重用或恢复安装必须先确认原进程结束，保留已有完整包，按冻结版本与官方整包SHA256验收；不可通过切源换版本或静默降级。Hugging Face权重下载仍遵循已有官方端点与不可变revision约束，本次未测试它的直连速度。

## 原始证据与复核

诊断入口：scripts/probe_download_mirrors.py。原始两轮结果分别为 logs/v43/download_routes_20260914.json 和 logs/v43/download_routes_20260914_confirm.json。首轮NVIDIA索引未匹配到目标链接，记录为查找失败；复测改用PyTorch官方依赖索引定位到同一NVIDIA包，不把首轮查找失败当作网络失败。

精简可上传证据：docs/download_routes_evidence_20260914.json（含最终原始结果、路径与SHA256）。语法及按域名代理检查通过；没有运行安装、训练或读取任何数据标签。CPU语义gate仍为40项通过，真实pilot未运行，PICS_joint_relabel仍为incumbent。

Git：本阶段在codex/introactts-v43-bootstrap正常本地提交；上次实际push因缺HTTPS认证失败，尚未恢复，远端尚未同步，详见docs/git_sync.md。
