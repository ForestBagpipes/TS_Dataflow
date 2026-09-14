# IntroAct-TS 服务器工作规则

始终使用简体中文。

本机就是新服务器，项目根目录是 `/home/vipuser/work/work2`。首先阅读 `docs/REMOTE_CODEX_HANDOFF.md` 与 `docs/new_server_execution_plan_20260914.md`，再读 `docs/HANDOFF.md`、`docs/version_ledger.md` 和 `docs/CHANGELOG.md`。新服务器路径与状态以交接文件和实际机器检查为准；旧文档中的机器地址、路径、队列和模型 available 标记属于历史记录。

所有实验、测试、统计重算、训练和模型下载在当前服务器执行。开始前显式 `source scripts/env_new_server.sh`，用指定环境解释器。core、TS-ICL、Chronos保持隔离，不修改系统Python或共享Conda base，不直接运行旧 setup_remote.sh/env_autodl.sh。

先检查GPU和内存，重GPU任务一次只运行一个，用 `locks/gpu.lock` 协调本项目任务。不得终止他人进程、升级驱动、GPU reset或擅自关机。长任务使用独立tmux会话并记录状态、PID、原始日志和资源。

用户方案中的v43模块与CLI是待实现契约，不是现有程序。没有实现、运行并验收的内容不得标成完成。先数据/worker语义测试，再32个train/dev origin的pilot；不提前读取calibration/test标签。保持原始时间、NaN、future与辅助通道的读取边界，禁止静默换模型、surrogate降级、失败填零或改变分母。

保留历史失败和旧结果，incumbent以台账为准。环境迁移或接口测试不构成方法晋升，不宣称SOTA。方法改动遵守项目原有进度DOCX同步规则，但不要把规划或RED结果写成已验证研究成果。

在 `codex/` 项目分支正常提交代码、配置和文档，不提交凭据、数据、权重、大结果或缓存。源码来自保留未提交修改的当前工作区快照，不能用旧Git HEAD覆盖。日常先检查git状态，保留用户或其他任务的改动。

上游仓库为 `https://github.com/ForestBagpipes/TS_Dataflow.git`，remote 名为 `origin`。每个完成阶段及时 commit 并 push 当前 `codex/` 分支，记录本地和远端提交 SHA；不能只留本机提交。默认不直接更新 `master`，不 force push。认证或网络失败时保留本地提交、记录实际错误并继续不依赖上传的任务，认证恢复后补推；不得将失败上传记为同步完成。

已经明确授权的实施和验证自主推进；缺失旧缓存只阻断旧精确复现分支，其他工作继续。只询问真正阻塞的输入。不调用未经授权的付费LLM API，不投稿、不发送材料、不购买或释放资源。
