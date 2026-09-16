# 2026-09-16 23:00 计划关机前快照

## 截止与职责边界

- 用户通知服务器将在 2026-09-16 23:00（UTC+8）关机。
- 22:16 起不再接收新的重 GPU 任务，只进行状态核验、结果固化、同步和恢复说明整理。
- 助手不执行关机，也不终止其他用户进程；实际关机由外部安排。

## 22:17 服务器实测状态

- 项目：`/home/vipuser/work/work2`
- 分支：`codex/introactts-v43-bootstrap`
- HEAD 与 `origin/codex/introactts-v43-bootstrap`：`acd9f3f2dea880e542b7031ae5a9a30cf8ec7c30`
- tracked working tree：clean
- work2 tmux：无
- work2 Python/实验进程：无
- GPU：RTX 4090，15 MiB / 49140 MiB，利用率 0%，29°C
- `locks/gpu.lock`：可获取
- 内存：47 GiB 总量、约 44 GiB available；swap 未使用
- 磁盘：根分区 196 GiB，总计使用 79 GiB，可用 107 GiB

没有未保存的训练或推断进程，因此计划关机不会截断当前实验。GPU 空闲是因为已授权且预登记的 r5 补跑全部完成；不得为了占用资源在截止前临时启动未登记实验。

## 已固化结果

- 最终代码/结果提交：`b29ea6bfa92c06a111bd65a5e2cadba2a14e4478`
- 包索引发布提交：`acd9f3f2dea880e542b7031ae5a9a30cf8ec7c30`
- r5 回归测试：44 项通过
- TATO 审计：缩放场景 12/12、官方 96 单位场景 4/4 为 `audited_completed`
- 精简包：`results/v431-r5/review-b29ea6bfa92c.tar.gz`
- 精简包大小：1980814 字节
- 精简包 SHA256：`58604ed29f71e6aec07b5f10e84f877f045594f706fb5d8e6a618a6709f347c0`
- calibration/test 仍封存；r5 不晋升，历史失败和旧 partial 均保留。

关键报告、审计 JSON 和精简包已复制到 Windows 工作区 `F:\work\Time-research\work2`；大结果、数据集和权重没有提交 Git。

## 下次开机恢复顺序

1. 连接服务器后进入 `/home/vipuser/work/work2`，先读取 `AGENTS.md`、`docs/REMOTE_CODEX_HANDOFF.md`、`docs/new_server_execution_plan_20260914.md`、`docs/HANDOFF.md` 和本文件。
2. 显式执行 `source scripts/env_new_server.sh`，检查系统时间、Git HEAD/status、GPU、tmux、进程、磁盘和 `locks/gpu.lock`。
3. 核对本文件记录的发布 SHA；只允许 fast-forward，同步失败时不得重置或强推。
4. 不复用任何已过期 deadline，不原样重启旧队列；只从实际终态和最新预登记计划接续。
5. work2 周期巡检已因计划关机暂停；服务器恢复并完成上述检查后再恢复巡检。
