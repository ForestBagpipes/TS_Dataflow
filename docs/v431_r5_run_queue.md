# r5实际队列与资源

2026-09-16接管沿ac6aaa6；源码与模型哈希冻结后CPU拟合3.704531秒，共同DEV14.143840秒，金融0.914863秒。数据准备首个序列化失败保留，第二批成功。服务器GPU RTX4090，健康隔离环境复用，无安装/驱动/全局代理修改。

单GPU tmux socket v431-r5/session online：Bolt→TimesFM已完成，进程24.330024/31.187600秒，各44请求。外层locks/r5-online-queue.lock仅防重复队列；serve_v43_model.py:45-46每次调用持locks/gpu.lock，父进程不重持。沙箱GPU不可见时通过宿主机授权执行，不误判驱动损坏。

实际命令与PID/服务日志保留results/v431-r5/online-*/process_accounting.json及logs/v431-r5；进程已结束，不能把队列状态写成仍在运行。后续CPU审阅包/文档与数据元数据准备；无已启动主实验GPU任务。r5准入失败，确认集封存。

## 02:58 CST后续队列

TATO首批四个场景顺序执行（Bolt H96/H192→TimesFM H96/H192），tmux tato-search；随后tato-extra补Solar/USTS八场景。Chronos-2下载已完成且权重SHA256通过，chronos2队列等待GPU互斥，先1个TRAIN parent四条件验收，成功后执行旧DEV26parent/156变体原生预测；不重新拟合r5。official96队列在extra完成后执行四个官方96单位场景适配，L512不支持的配置如实失败。各队列04:45前停止新重任务，04:55前归档；不调用服务器关机。

primary的status.wall_seconds仅测worker主体阶段，未测初始导入开销，不能称完整OS进程；extra旧v1外层wall含等待互斥；未启动时修复的v2将queue_wait_seconds单列，wall_seconds测完整子进程；remaining_jobs的job.seconds在取得互斥后计时，可报告完整子进程墙钟。原始状态账本保留这些口径差异。

03:03 CST时间预算修订：归档尚未启动任何GPU子进程的extra v1等待状态；仅替换本项目CPU等待队列为tato-extra-v2，截止提前04:25，为official96预留最多20分钟。原运行worker、trial规则、来源与模型不变，时间修订不使用任务表现。新队列在取得互斥后复核剩余时间，防止等锁使分配预算过期。

03:35：extra v2仍无子任务时替换为tato-extra-cached，使用独立cached worker与extra-cached请求，--status仍写extra/queue.execution.json，供official96读取实际状态。旧请求/等待状态及cache_queue_handoff保留。Chronos2第一次记录异常和6.313467秒保留，03:25加入同输入重试，当前仍等待。

04:20 CST检查：r5主候选和88在线请求早已完成，未再拟合。Chronos-2同输入记录修复后已完成TRAIN/DEV原生检查，保留第一次失败。TATO四个ETTm1场景各500trial完成；H96 extras均保存完整部署，Solar TimesFM搜索247/500。Solar Bolt H192搜索455/500，后续场景在途。新结果逐批独立审核后写入final_snapshot；这些阶段记录以时间为准，最终队列状态另附。

## 2026-09-16T04:43:04.371223+08:00 r5最终计算收口：负结果保留，基线与TRAIN缓存完成

全部GPU队列已结束，r5开发准入仍失败，calibration/test封存。原旧DEV26parent/156变体：Bolt r5 1.152415等自身免费参考，TimesFM r5 1.074244弱于免费/固定流程1.069398；没有主动或联合约束的共同方法优势。旧R2信息差异、所有超时和金融负结果保留。

TATO缩放单位12场全部部署完成，4935实际trial=4933完整+2截止中断，5场搜索未满500。每家族26parent/52变体子表scene为1.416821/1.221407；官方96单位另表，每家族1000尝试/66成功/934长度失败，14parent/28变体MASE1.530679/1.452783。都不是官方完整复现。费用与失败详见v431_r5_final_snapshot及tato_scene_results。

Chronos-2原生KEEP旧DEV为0.957177，仅骨干敏感性，不是r5收益，ETTm1并非更优。八来源TRAIN接口64请求及原生预测库1840请求已全部运行并独立审核；预测库230parent，仅Native KEEP，未读未来目标/未计算MASE/未拟合r5，不能说r5训练支持扩到230。r5实际fit/gate仍54/21。主矩阵完整方法评分及独立确认未运行。

论文补齐准确投影界及排序退步反例，原生/受控缺口/金融自然缺口分别说明。已生成完整聊天交付和可独立执行接续提示词所需结果；代码/包SHA及远端同步以v431_r5_delivery和review_package.json为准。服务器原定05:04:31关机，助手没有执行关机；重启后不得原样复用过期队列截止。
