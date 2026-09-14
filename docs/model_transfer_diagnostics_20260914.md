# 2026-09-14 模型传输诊断与镜像接续

TS-ICL官方权重219,150,987字节在397.90秒内下载并通过LFS SHA256核验；20:22:11完成三项真实GPU合成接口验收，证据见 docs/tsicl_bootstrap_acceptance_20260914.json。未运行真实数据pilot。

Xet会缓冲再写文件，不能用.incomplete长度长时间为0判定传输完全停止。本次进一步只读核对本项目进程的TCP已接收字节和RSS，确认TS-ICL持续传输。普通官方HTTP同文件8 MiB样本：代理0.135 MiB/s，直连0.035 MiB/s；因此没有关闭官方权重下载的代理，也没有禁用Xet。Hugging Face路径与NVIDIA/国内PyPI路径分别按实测选择，未改变共享代理服务或Codex配置。

Bolt固定官方revision为5d9f166d69f47aef3401367a7b842e78fe97b121。HF-Mirror的同版本样本在15秒内未下完1 MiB，转到了cas-bridge.xethub.hf.co，未见加速。ModelScope的amazon/chronos-bolt-base文件清单提供821,203,576字节、SHA256 31f875483a3215bc6880a0837ea608a13ce55f88ad90538c3cdd0b29aeb60b36，与HF官方一致；镜像文件revision为00f02a9ecea896c254ed1315c0596e52f3e144ce。其身份是字节副本，不将镜像账户名视为官方背书。

ModelScope首1 MiB探测约1.36 MB/s，长连接随后下降至约0.3 MB/s。保留原官方下载，在独立目录新增镜像下载；确认4 MiB非首段约3.15秒后，仅停止新增镜像curl任务，保留121,991,168字节前缀，改用4路4 MiB分段（每路上限1 MiB/s）。原始失败状态与切换记录全部保留。镜像完整SHA256未通过前不写HF缓存，不将小样本测速标成整包成功。

入口：scripts/fetch_bolt_mirror.py、scripts/fetch_bolt_mirror_chunks.py；实时状态 results/v43/bolt_mirror_status.json，日志 logs/v43/bolt-mirror-20260914/。scripts/adopt_bolt_mirror.py要求完整SHA256通过且原任务仍处于Bolt下载阶段，再核验项目进程身份、暂停等待队列、保留旧未完成文件、停止旧传输进程并确认退出，取得已有HF对应文件锁后写入同一官方hash的blob和snapshot指针，最后重启原模型验收队列。如果原官方下载先完成，则不替换。此接续脚本目前已准备，是否执行以adoption.json为准。

冻结模型身份和配置始终以HF官方metadata为准，最终校验仍运行原prepare-models.py。原文件、两条线路和接续的全部成本分别记录，不能把后续HF缓存命中时间当作模型权重实际下载总耗时。未重新安装环境、未换成小模型、未读取calibration/test标签。

公开来源：[HF官方Bolt文件及SHA256](https://huggingface.co/amazon/chronos-bolt-base/blob/main/model.safetensors)、[ModelScope副本](https://modelscope.cn/models/amazon/chronos-bolt-base)、[HF-Mirror说明](https://hf-mirror.com/)。完整服务器探测记录见 docs/model_transfer_diagnostics_20260914.json。
