# v47 实验 2 修正执行记录（2026-09-19）

## 范围与证据边界

依据用户附件的 M1–M3 实施：SAITS 第六动作、四折 parent OOF、三严重度与两个 bank mask 种子、受有害率约束的 LOPO 最小化、仅修复值的稳健尺度守卫、部署行独立排名。M4 暂不实施。旧 v46/v47 文件及失败结果保留。

本轮版本称为 `v47_verified`，名称表示独立修复工作线，不表示研究结果已验收。新代码在 `src/introact_ts/v47_verified/` 与 `scripts/*verified*.py`，结果写入独立目录。所有实验、测试、统计和编译均在服务器运行。

v47 设计已受到 v46 TEST 和 Chronos-2 结果启发，因此同一测试集的再次评估不能称为新的独立确认。当前入口明确禁止 TEST，先做训练侧接口及开发验收；论文保留未运行结果占位符。

## 已确认旧实现的问题

- v47 forecast 对 KEEP 应用全有限修复守卫，导致合法 NaN 参考动作被拒绝。
- SAITS 旧实现为两折，与规划四折不符；每个评估块重新训练，未共享同一个部署模型。
- SAITS 从 float32 panel 拼回 observed 值，不能保证原始 float64 观测逐值不变；通道选择发生在排除 OOF parent 之前。
- TS-ICL/SAITS 原输入迭代器会实际解析 future，尽管调用方把变量命名为 `_future`。
- 旧队列按模型分锁、文件存在即跳过、部分失败后仍继续；不符合统一 GPU 锁与完整性验收要求。
- TimesFM 旧队列的 Git 所有权检查失败；当前已核对其源码 SHA 为 `8cb0628371af142e16b8c232cc9fbf667ffb12f9`。
- 旧共享 v44/v46 模块已有未提交修改，不能用历史 HEAD 覆盖。本轮通过新包隔离。

## 运行阶段

1. 在 `w2-core` 环境运行有针对性的契约测试。
2. `results/v47_verified_pilot`：跨八来源选32个完整训练 parent，保留全部严重度、模式与 horizon 变体。SAITS 两个 epoch 只用于真实接口、OOF 和资源验收，不能作为正式方法结果。
3. 通过 pilot 后，`results/v47_verified` 使用完整 bankx/bankx2、四折100 epoch SAITS及 TRAIN-eval，三个骨干串行取得 `locks/gpu.lock`；CPU 统计、代码审计、论文修订并行。
4. 训练侧准入与统计完成后再冻结结果解释，不把队列启动或接口成功写成方法晋升。

运行日志保存到 `logs/v47_verified/`，阶段命令、PID、代码 hash、退出码和耗时保存到各运行目录的 `run_status.json`。具体完成状态以服务器状态文件为准。

## 论文

原稿保留。修订稿为 `latex/IntroActTS_20260919_v47_revised.tex`，明确 post-hoc 边界并修正逻辑语言。旧 `_dummy_v47` 是排版样稿，禁止作为真实结果交付。安全回填不得使用旧脚本中的无条件胜利句。
