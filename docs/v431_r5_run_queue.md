# r5实际队列与资源

2026-09-16接管沿ac6aaa6；源码与模型哈希冻结后CPU拟合3.704531秒，共同DEV14.143840秒，金融0.914863秒。数据准备首个序列化失败保留，第二批成功。服务器GPU RTX4090，健康隔离环境复用，无安装/驱动/全局代理修改。

单GPU tmux socket v431-r5/session online：Bolt→TimesFM已完成，进程24.330024/31.187600秒，各44请求。外层locks/r5-online-queue.lock仅防重复队列；serve_v43_model.py:45-46每次调用持locks/gpu.lock，父进程不重持。沙箱GPU不可见时通过宿主机授权执行，不误判驱动损坏。

实际命令与PID/服务日志保留results/v431-r5/online-*/process_accounting.json及logs/v431-r5；进程已结束，不能把队列状态写成仍在运行。后续CPU审阅包/文档与数据元数据准备；无已启动主实验GPU任务。r5准入失败，确认集封存。
