# r5实际队列与资源

2026-09-16接管沿ac6aaa6；源码与模型哈希冻结后CPU拟合3.704531秒，共同DEV14.143840秒，金融0.914863秒。数据准备首个序列化失败保留，第二批成功。服务器GPU RTX4090，健康隔离环境复用，无安装/驱动/全局代理修改。

单GPU tmux socket v431-r5/session online：Bolt→TimesFM已完成，进程24.330024/31.187600秒，各44请求。外层locks/r5-online-queue.lock仅防重复队列；serve_v43_model.py:45-46每次调用持locks/gpu.lock，父进程不重持。沙箱GPU不可见时通过宿主机授权执行，不误判驱动损坏。

实际命令与PID/服务日志保留results/v431-r5/online-*/process_accounting.json及logs/v431-r5；进程已结束，不能把队列状态写成仍在运行。后续CPU审阅包/文档与数据元数据准备；无已启动主实验GPU任务。r5准入失败，确认集封存。

## 02:58 CST后续队列

TATO首批四个场景顺序执行（Bolt H96/H192→TimesFM H96/H192），tmux tato-search；随后tato-extra补Solar/USTS八场景。Chronos-2下载已完成且权重SHA256通过，chronos2队列等待GPU互斥，先1个TRAIN parent四条件验收，成功后执行旧DEV26parent/156变体原生预测；不重新拟合r5。official96队列在extra完成后执行四个官方96单位场景适配，L512不支持的配置如实失败。各队列04:45前停止新重任务，04:55前归档；不调用服务器关机。

primary的status.wall_seconds仅测worker主体阶段，未测初始导入开销，不能称完整OS进程；extra旧v1外层wall含等待互斥；未启动时修复的v2将queue_wait_seconds单列，wall_seconds测完整子进程；remaining_jobs的job.seconds在取得互斥后计时，可报告完整子进程墙钟。原始状态账本保留这些口径差异。

03:03 CST时间预算修订：归档尚未启动任何GPU子进程的extra v1等待状态；仅替换本项目CPU等待队列为tato-extra-v2，截止提前04:25，为official96预留最多20分钟。原运行worker、trial规则、来源与模型不变，时间修订不使用任务表现。新队列在取得互斥后复核剩余时间，防止等锁使分配预算过期。

03:35：extra v2仍无子任务时替换为tato-extra-cached，使用独立cached worker与extra-cached请求，--status仍写extra/queue.execution.json，供official96读取实际状态。旧请求/等待状态及cache_queue_handoff保留。Chronos2第一次记录异常和6.313467秒保留，03:25加入同输入重试，当前仍等待。
