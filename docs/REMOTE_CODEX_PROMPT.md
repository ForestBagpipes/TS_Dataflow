你现在在新服务器上接管 IntroAct-TS，项目目录是 `/home/vipuser/work/work2`。请始终用简体中文交流。

先进入项目，读取 `AGENTS.md`、`docs/REMOTE_CODEX_HANDOFF.md`、`docs/new_server_execution_plan_20260914.md`、`docs/HANDOFF.md`、`docs/version_ledger.md` 和 `docs/CHANGELOG.md`，并检查 git 状态。完整方案已经保存在项目中，不需要我再粘贴。新服务器的路径、资产与环境状态以交接文件、精确 lock、模型 manifest 和实际检查为准；旧文档里的地址、缓存路径与 available 标记是历史状态。

本地 agent 已做代码和数据迁移、环境隔离及交接文件中明确列出的基础验收。先运行 `python3 scripts/bootstrap_status.py`：两个模型环境和权重可能仍在后台准备，prefix存在不代表验收通过。正在安装时不要启动重复安装或改写同一环境，可先推进CPU侧代码与语义测试；若失败，读日志修复具体阶段，并核对后续模型接续任务是否需要恢复。请核对后复用，不重装全部环境。执行前 `source scripts/env_new_server.sh`，分别使用 `$W2_CORE_PY`、`$W2_TSICL_PY`、`$W2_CHRONOS_PY`。全部实验、测试、统计重算、训练和模型下载都在当前服务器运行，保持三个环境隔离。模型从已固定的 snapshot/revision 加载，缺失的可选模型单独登记。

接下来由你实现和推进 v4.3。方案中的 `introact_ts.v43` 模块与CLI是待实现契约，不能当成现有程序。先按方案第6节审计旧入口，再完成数据、时间、mask、future、worker身份和缓存契约及最小语义测试；随后在32个来源均衡的train/dev origin上跑pilot，报告真实输出shape、耗时、显存、成本和失败案例。H32仅作pilot，正式H96/H192不随意缩短。只有接口和泄漏检查通过后才推进A0–A5，先判断新信息是否产生真实TSFM任务收益，再考虑更大的评分器和工具策略。

保留PICS_joint_relabel作为历史incumbent；v4.2没有晋升。旧repair gain与新task gain严格分开，原始时间轴、NaN、读取边界、评价分母和所有失败记录必须保留。不要提前读取calibration/test标签，不用surrogate或静默换checkpoint冒充真实后端。缺失旧节点专属缓存只阻断旧精确复现，不能因此停止其他可执行工作，也不能声称已复现旧数字。

遵守单卡资源限制：先看GPU和内存，重GPU任务一次一个，用项目flock，长任务放tmux并保存PID/状态/日志；不终止他人任务、不改驱动或全机GPU设置、不自行关机。每阶段同步代码、配置、原始结果、环境/模型/数据hash及文档台账，使用 `codex/` 分支提交，不提交凭据、数据和权重。已经明确的实施与验证自主推进，只询问真正阻塞的输入。

你的第一份回报应说明接管时的真实状态，以及数据/worker测试或32窗pilot的实际结果与具体阻塞，给出下一批预计成本；不要只复述方案或预告SOTA。
