# v4.3.1-r4 运行队列与实际用时

2026-09-16 Asia/Shanghai接管00:09。CPU与单GPU在线队列均已结束，无等待安装/下载，不自动关机。下表时间为UTC，换算北京时间加8小时。

| 阶段 | 状态 | 实际秒 | 日志 |
|---|---|---:|---|
| fit | completed | 50.929 | logs/v431-r4/cpu-fit-first.log |
| train-library | completed | 3.864 | logs/v431-r4/cpu-train-library-first.log |
| dev | completed | 2.448 | logs/v431-r4/cpu-dev-first.log |
| check | completed | 2.019 | logs/v431-r4/cpu-check-first.log |
| old-acq | completed | 2.064 | logs/v431-r4/cpu-old-acq-first.log |
| financial | completed | 0.922 | logs/v431-r4/cpu-financial-first.log |
| generalization | completed | 1.014 | logs/v431-r4/cpu-generalization-first.log |
| bolt | completed | 37.060 | logs/v431-r4/online-bolt-r1.log |
| timesfm | completed | 29.558 | logs/v431-r4/online-timesfm-r1.log |

CPU实际命令/PID/起止时间：results/v431-r4/cpu_queue_status.json；GPU成功队列：online_queue_status-r1.json。首次online_queue_status.json锁冲突失败保留，耗时1.364秒，未加载模型，不删除该次失败。
GPU由root唯一队列调度，外层r4_online_queue.lock防重复调度，各实际服务按原gpu.lock协调并核验非本项目进程。两个家族依次加载；没有终止他人任务、修改驱动或代理。
接管实测16可见CPU、47GiB内存、4090报告46068MiB，110GiB磁盘可用；BLAS线程均1。参考16GB预算不冒充实际机器资源。
本轮未再生成整套原预测；尺度仅改变学习/后处理，复用受hash约束的模型输入、原始MAE和预测。真实自然请求是新增GPU工作，其启动/热调用/完整进程另见online_verification。
当前未启动任务：TATO官方完整协议、TimesFM-3/Chronos-2新权重、独立来源确认、calibration/test；不填预计成绩。联合未胜强简单对照，按预登记不追加第五轮算法。
Git交付使用codex-save-local，审阅包身份见artifacts/reviews/v431-r4-review.json；远端核验另存results/v431-r4/git-sync.json。Windows登录后的本地同步不是服务器可直接观察的状态。
