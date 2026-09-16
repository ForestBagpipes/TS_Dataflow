# TATO 截止中断场景的确定性重跑设计

## 目标与边界

补完 2026-09-16 旧关机截止造成的 5 个 TATO 场景级搜索 partial 记录。该批次只补强基线，不修改 r5 模型、特征、预算策略或开发结论，不读取 calibration/test，也不把场景适配写成 TATO 官方完整复现。

## 备选方案

1. **确定性从零重跑（采用）**：在新目录重新执行同一 500-trial 搜索，放宽单场景墙钟上限。旧 partial 目录保持只读，通过参数序列、已完成 TRAIN 分数和预测哈希核对重跑前缀。优点是 Optuna 状态与输出账本完整，缺点是重复一部分 GPU 计算。
2. **重放 Optuna 状态后续跑**：从旧 `trials.json` 恢复 sampler，再从中断 trial 继续。计算更少，但需要同时恢复 sampler、原生预测缓存、调用索引和 raw 文件血缘，错误面过大。
3. **接受 partial**：不新增计算。最稳妥但无法补齐预登记 500 trial，TATO 强基线继续缺项。

## 数据流

准备器只选择 `status=partial`、`actual_trials < requested_trials` 的缓存场景。它复制请求的研究身份字段，改写新输出目录和 `max_seconds=1200`，并写入原 request/status/frozen 文件的路径与 SHA-256。运行器在独立队列锁内依次调用现有 `v431_r5_tato_cached_scene.py`；worker 继续独占 `locks/gpu.lock`，队列不关机、不终止其他进程。

审核器将新目录替代共同表中的同名 partial 目录，但保留旧目录及 superseded 记录。它必须验证：

- source、parent、UID、H、condition、输入、TRAIN 监督、seed、500 trial、模型和代码身份不变；
- 新上限不超过预登记的 1200 秒，唯一变更是旧截止后重新给予完整运行窗口；
- 新搜索从 trial 0 开始，旧 partial 的全部参数前缀一致；旧 completed trial 的 TRAIN 分数和逐样本预测哈希一致；
- 只有完整冻结和保存全部 DEV 预测后才读取旧 DEV 目标；
- 原 partial、失败、费用和新重复计算费用全部保留，不相互抵消。

## 失败处理与验收

任何身份/hash/前缀不一致立即使审核失败，不自动换模型、缩空间或跳过场景。单场景失败不删除其他场景结果，队列终态记录实际退出码。验收为针对性 CPU 测试通过、5 个 worker 终态落盘、独立审核通过、共同子表按完整分母更新；否则维持 partial，不改变 r5 负结果。
