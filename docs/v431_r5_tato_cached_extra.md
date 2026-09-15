# TATO追加场景离线原生预测缓存修订

2026-09-16 03:34前准备。仅作用于尚未启动的8个extra场景，原worker、原始请求、已完成结果不修改。r5候选和搜索超参数不变。

## 只读依据

| 完成的TRAIN场景 | 原模型调用 | 同parent唯一键 | 重复调用 | 比例 | 重复原生计算秒 | 原生point差异 |
|---|---:|---:|---:|---:|---:|---:|
| Bolt H96 |14500|10925|3575|24.655%|114.962|0|
| TimesFM H96 |14500|11261|3239|22.338%|361.112|0|

排除各场景最后14个DEV请求。所有14500 TRAIN原始NPZ均读取，重算输入dtype/shape/bytes哈希；全部重复原生point逐dtype/shape/bytes相等，不是仅凭key推测。没有读取DEV标签来决定优化。Bolt缓存point payload约3.1MB，含key及来源保守估约17.4MB。

## 实际代码与身份

- `scripts/v431_r5_tato_cached_scene.py`：复制独立runner；只在离线TRAIN跨trial保持原生缓存，各trial仍独立构建管线、治理与逆变换。原始worker SHA保持不变。
- `scripts/v431_r5_tato_parent_cache.py:ParentScopedForecast`：显式wrapper，不monkeypatch原方法。键包含parent、checkpoint identity hash、实际native config/数值协议hash、输入dtype/shape/bytes、H。同parent共享，跨parent不共享。
- 每个DEV请求先清wrapper及backend缓存，冻结模型仍驻留；不能把TRAIN缓存变成免费部署信息。
- 命中记录首次raw文件、SHA、首次调用索引与实付费用，命中原生计算秒为0但查找/复制实际耗时保留。miss保留真实原生计算秒和含raw落盘的实付墙钟。完整离线search墙钟另报，不清零已有历史计算。
- 缓存返回copy，保护后处理不能改写共享原生point。最终预测仍按各trial自己的逆变换生成，不缓存最终后处理结果冒充另一管线。

七项CPU fake-backend回归已实际通过：同parent命中、返回副本保护、跨parent不命中、H区分、dtype区分、部署逐请求清空、首次raw/费用溯源。该检查不是预测实验，结果在`results/v431-r5/tato-scene-extra-cached/cpu_cache_checks.json`。

新请求及队列位于`results/v431-r5/tato-scene-extra-cached/`。每个`cache_amendment`绑定旧request和旧worker SHA、新worker/module SHA、两家族只读审计SHA。输入文件直接引用旧不可变数组，500trial、600秒上限、source/H/缺口/T_fit监督和固定顺序不变。04:25截止不变。原extra请求与队列保留。

root仅替换尚未运行的CPU等待队列，worker参数为`--worker scripts/v431_r5_tato_cached_scene.py`，新queue参数指向cached目录。official96等待路径必须随队列转交显式更新；不能把旧未运行任务记为完成，也不能让其永久等旧路径。当前文档记录代码准备和CPU检查，真实cache命中/加速及最终baseline结果仍待新worker执行与独立审计。

### 持久化回归入口

最初交互式CPU检查已保存为`tests/v431_r5/test_tato_parent_cache.py`，仅复跑此文件，实际结果`7 passed in 0.04s`。命令：

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" -m pytest -q tests/v431_r5/test_tato_parent_cache.py \
  > logs/v431-r5/tato-parent-cache-tests.log 2>&1
```

本次只新增测试文件和日志，cached worker/module冻结hash不变，没有GPU调用。
