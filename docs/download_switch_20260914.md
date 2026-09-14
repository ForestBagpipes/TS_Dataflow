# 2026-09-14 work2 下载实际切线

用户明确要求切线且不能影响 Codex 与代理。19:58 至 20:00 完成 work2 下载任务接续；只向核验过属主、PID、启动时间、命令和父子关系的项目进程发信号，未修改代理服务、全局网络配置、Codex配置或系统/base Python。

旧 bootstrap PID45580、Chronos pip PID61386 已退出。保留932,113,925字节：cuDNN及3个CUDA小包完整校验通过，cublas部分文件按原字节前缀续传。原配置、状态、日志和切换失败记录全部保存于 logs/v43/direct-switch-20260914/。代理127.0.0.1:17890切换前后TCP连通。

首次切线程序在旧pip退出后再次向已自动退出的父进程发TERM，得到NoSuchProcess；未强杀或吞掉此错误。已修复“进程已退出视为停止成功”的检查；核实全部旧安装进程退出后，启动独立tmux work2-bootstrap-direct-20260914，安装父PID66506、直连下载PID66519。停止期间旧模型接续与pilot等待任务按失败保护退出，原状态保留后以新会话恢复。持续监控PID59254保持运行。

新入口 scripts/resume-bootstrap-envs.sh 只续接未完成阶段，复用core与TS-ICL的Torch安装；不再次创建prefix或运行已完成的安装。其命令包含bootstrap-envs.sh，符合已有模型接续器的进程身份检查。25个Torch依赖版本来自原TS-ICL安装报告，仅Python ABI对应cp311；所有新wheel依据官方索引SHA256锁定。报告中Jinja2/MarkupSafe未含hash，已从官方索引补全，不因缺hash跳过检查。

scripts/download_bootstrap_wheels.py 通过官方NVIDIA/国内镜像直连分段下载，wheel任务最多4个连接、每连接2 MiB/s；16 MiB一段，最多同源重试3次，完整文件与官方SHA256一致后才允许离线hash安装。部分包续传不填零，不跳过损坏段。两段Torch发生early EOF，第二次重试成功；全部原始错误和成功段都留在日志中。

后续Python依赖通过任务专用清华镜像安装；模型权重继续使用官方固定revision和原独立环境，不换模型。Hugging Face 1 MiB直连/代理探测均可读，小样本受握手与重定向影响，尚不能据此确定整包速度。模型文件总计约1.04GB。

完整切线证据：docs/download_switch_evidence_20260914.json；下载原始清单和验证记录：logs/v43/direct-switch-20260914/；实际安装日志：/home/vipuser/work2-staging/bootstrap-20260914/logs/bootstrap-direct-resume.log。scripts/bootstrap_status.py 根据当前安装PID选择新日志，避免展示已停止的旧下载日志。

截至20:00依赖下载继续推进，真实pilot尚未运行。20:30–20:45启动pilot只是条件估计，必须以完整依赖、模型验收和CPU gate实际通过为准；A0–A5仍需pilot先通过。PICS_joint_relabel保留为incumbent。本阶段是工程恢复，不更新DOCX为方法成功。

Git仍在codex/introactts-v43-bootstrap本地正常提交；上次实际push因缺HTTPS认证失败，尚未恢复，不标为已上传。
