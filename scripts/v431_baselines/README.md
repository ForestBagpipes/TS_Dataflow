# v4.3.1 原生 baseline 适配入口

先 `source scripts/env_new_server.sh`，全部实际执行使用 `$W2_CHRONOS_PY`。源码及搜索限制见 [审计文档](../../docs/v431_baseline_audit.md)。GPU 入口必须由主执行 agent 的统一队列调用；worker 内仍检查项目 flock 和其他 GPU 进程。

CPU 小例：

```bash
CUDA_VISIBLE_DEVICES='' "$W2_CHRONOS_PY" scripts/v431_baselines/tato_smoke.py
```

该小例只有 shape-only 测试替身，不生产可引用的模型成绩。

CPU 预备不读目标，只复制共同 dev 的 dirty context 或冻结候选：

```bash
"$W2_CHRONOS_PY" scripts/v431_baselines/worker.py --prepare RUN --output OUT --backend tato
"$W2_CHRONOS_PY" scripts/v431_baselines/worker.py --prepare RUN --output OUT --backend timesfm
"$W2_CHRONOS_PY" scripts/v431_baselines/timesfm_tato_worker.py --prepare RUN --output OUT
```

每个 `OUT` 必须是新目录，生成逐窗输入身份和不可变 `request.json`；首次 prepare 后改源文件会被拒绝。TimesFM TATO 是独立入口，因为模型 patch size 与 Bolt 不同，不能把原模板静默替换。

统一队列执行：

```bash
"$W2_CHRONOS_PY" scripts/v431_baselines/worker.py --request OUT/request.json
"$W2_CHRONOS_PY" scripts/v431_baselines/timesfm_tato_worker.py --request OUT/request.json
```

普通 worker 按 request 选择 Bolt/TATO 或 TimesFM 五固定臂；专门 TimesFM TATO 使用第二条。原始预测、分位数、模型输入、trial 明细、费用和失败状态保留在 `OUT`。

独立复核及共同 dev 评价：

```bash
CUDA_VISIBLE_DEVICES='' "$W2_CHRONOS_PY" scripts/v431_baselines/verify_and_score.py OUT
CUDA_VISIBLE_DEVICES='' "$W2_CHRONOS_PY" scripts/v431_baselines/timesfm_tato_worker.py --verify OUT
```

只有 worker 已完成且全部原始预测/选择重放验证后才读取冻结 dev 的 target/mask；不读 calibration/test。TimesFM TATO 评价要求兄弟目录 `timesfm/scored_rows.json` 已生成，供同一 backbone 的 native KEEP 风险参照。

产物 `baseline_table.json` 直接进入共同主表；`scored_rows.json` 是逐窗证据；`summary.json` 区分真实实验费用和跨行缓存补计后的独立部署估计。`independent_replay.json` 记录复核脚本及 request SHA。

环境准备：仅将 `task-target-requirements.txt` 的包以 `--target .cache/v431-baseline-deps --no-deps` 安装到任务 overlay；已有 Chronos 环境提供兼容的 Torch、NumPy、scipy、sklearn、statsmodels、huggingface-hub 和 safetensors。不得重复安装/升级三个已验收环境。官方源 commit 与 TimesFM 权重、许可均必须符合审计中的不可变身份。
