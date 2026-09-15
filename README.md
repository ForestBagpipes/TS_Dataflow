# IntroAct-TS

最新交付 **v4.3.1-r5**：共同开发与真实在线已完成，联合约束及主动机制未通过准入，calibration/test封存。完整结果见[报告](docs/v431_r5_report.md)、[主表](docs/v431_r5_main_table.md)、[机制](docs/v431_r5_mechanism_table.md)、[继续执行提示词](docs/v431_r5_next_prompt.md)。

面向时间序列基础模型的任务一致数据治理智能体。

历史候选为 **v4.3.1-r4-JOINT**。工程已实现并完成共同开发评估；尚未取得优于强简单对照和固定流程的证据，不宣称SOTA或金融有效性。响应和主动取证的旧负结果保留，calibration/test封存，PICS_joint_relabel为原协议历史incumbent。

## 阅读入口

- [最新执行报告](docs/v431_r4_report.md)、[共同主表](docs/v431_r4_main_table.md)、[描述性统计](docs/v431_r4_statistics.md)
- [实际代码映射](docs/v431_r4_code_map.md)、[预登记](docs/v431_r4_preregister.md)、[完整本轮提示词](docs/v431_r4_prompt.md)
- [论文草稿](docs/paper_v431_draft.md)、[创新归因](docs/novelty_matrix.md)、[金融费用审计](docs/v431_r4_financial_audit.md)
- [强基线协议](docs/v431_r4_baseline_protocol.md)、[模型许可与适配登记](docs/v431_r4_model_registry.md)
- [交接](docs/HANDOFF.md)、[版本台账](docs/version_ledger.md)

## 运行与审计

所有训练、推断、测试和统计在当前服务器执行，先读取AGENTS.md并source scripts/env_new_server.sh。复用core、TS-ICL、Chronos隔离环境。单GPU任务由项目锁协调，不重装或修改全局环境。

scripts/v431_r4_prepare.py构造合法尺度轨迹账本；scripts/v431_r4_run.py以--fit冻结有限策略，以--evaluate评估。冻结目录禁止覆盖，复现实验应使用独立输出路径。训练原始账本、模型、数据和大结果不入Git；configs/v431-r4/resolved.json保存实际冻结策略与身份。

scripts/v431_r4_statistics.py生成共同描述性统计，scripts/report_v431_r4.py由同一表更新报告与论文。成本保留冷/热归因及完整预测费用，缓存不构成免费证据。完整方法对照中信息不同的R2、旧r3和TATO不冒充同信息消融。

## 本机同步

经过检查的阶段运行codex-save-local提交并推送当前codex分支。Windows登录后，F:\work\Time-research\work2按既有约定fast-forward同步。远端推送成功不等于已经观察到本机落盘；冲突或未提交修改不得用强推/reset绕过。

精简审阅包：[下载](artifacts/reviews/v431-r4-review.tar.gz)，[代码提交与SHA](artifacts/reviews/v431-r4-review.json)。自然在线结果与逐位/数值复核界限见[在线验收](docs/v431_r4_online_verification.md)。
