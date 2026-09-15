# IntroAct-TS

最新交付 **v4.3.1-r5**：共同开发与真实在线已完成，联合约束及主动机制未通过准入，calibration/test封存。完整结果见[报告](docs/v431_r5_report.md)、[主表](docs/v431_r5_main_table.md)、[机制](docs/v431_r5_mechanism_table.md)、[继续执行提示词](docs/v431_r5_next_prompt.md)。

面向时间序列基础模型的任务一致数据治理智能体。

历史候选为 **v4.3.1-r4-JOINT**。工程已实现并完成共同开发评估；尚未取得优于强简单对照和固定流程的证据，不宣称SOTA或金融有效性。响应和主动取证的旧负结果保留，calibration/test封存，PICS_joint_relabel为原协议历史incumbent。

## 阅读入口

- [最新执行报告](docs/v431_r5_report.md)、[共同主表](docs/v431_r5_main_table.md)、[机制和统计](docs/v431_r5_mechanism_table.md)
- [实际代码审计](docs/v431_r5_code_audit.md)、[预登记](docs/v431_r5_plan.md)、[完整本轮提示词](docs/v431_r5_prompt.md)
- [论文草稿](docs/paper_v431_draft.md)、[创新归因](docs/novelty_matrix.md)、[金融费用审计](docs/v431_r4_financial_audit.md)
- [TATO场景实际结果](docs/v431_r5_tato_scene_results.md)、[官方96单位边界](docs/v431_r5_tato_official96.md)、[主矩阵准备](docs/v431_r5_main_readiness.md)、[模型版本登记](docs/v431_r5_backbone_registry.md)
- [截止前快照](docs/v431_r5_final_snapshot.md)、[冻结与费用一致性复核](docs/v431_r5_final_consistency.md)、[Chronos-2原生结果](docs/v431_r5_chronos2_native_results.md)
- [交接](docs/HANDOFF.md)、[版本台账](docs/version_ledger.md)

## 运行与审计

所有训练、推断、测试和统计在当前服务器执行，先读取AGENTS.md并source scripts/env_new_server.sh。复用core、TS-ICL、Chronos隔离环境。单GPU任务由项目锁协调，不重装或修改全局环境。

`scripts/v431_r5_prepare.py`逐项核验当前任务五臂预测与费用缓存，生成合法学习账本；`scripts/v431_r5_run.py --fit`训练冻结参考、评分和先验，`--evaluate --suite main --role dev`只运行已登记开发评估。既有冻结目录不得覆盖，不因缺模型文件而静默重训。配置、源码与策略身份见`configs/v431-r5/resolved.json`及结果manifest。完整数据和模型权重不入Git。

`scripts/v431_r5_common.py`生成共同表，`scripts/v431_r5_statistics.py`及`v431_r5_online_audit.py`独立复核统计、预测与费用，`v431_r5_report.py`从账本生成报告和论文。`v431_r5_online.py --family bolt|timesfm`执行真实模型在线验收，仍须通过统一队列调度。R2/TATO的信息和动作空间差异单列，不冒充同信息消融。

r5未达到开发准入，因此主实验候选确认没有启动。新增TATO TRAIN场景搜索、Chronos-2原生检查和公开数据准备属于基线/协议补齐，不能转写为r5方法晋升。旧r4入口和负结果继续保留。

## 本机同步

经过检查的阶段运行codex-save-local提交并推送当前codex分支。Windows登录后，F:\work\Time-research\work2按既有约定fast-forward同步。远端推送成功不等于已经观察到本机落盘；冲突或未提交修改不得用强推/reset绕过。

精简审阅包与代码SHA见[交付记录](docs/v431_r5_delivery.md)，首个已上传[r5代码/结果包](results/v431-r5/review-81f9ccbc2f4e.tar.gz)。后续基线增量包以交付记录为准。真实在线结果见[在线审计](docs/v431_r5_online.md)，完整聊天报告不能被路径链接替代。
