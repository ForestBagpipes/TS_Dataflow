# r5 联合收益几何：实际实现与验收

本文件仅记录无标签几何模块，不代表治理预测收益成立。

## 真实入口

`src/introact_ts/v431_r5/geometry.py::project_scores(predictions, raw, scale, weights=None, mode='full', max_iter=2048, tolerance=1e-8, time_limit_seconds=0.05, previous_scores=None)`。

输入预测为 K×H 的原生预测，不接受 future 标签。参考严格为第 0 行，raw[0] 必须恰为 0。`weights=None` 明确表示未来评分位置/权重未知，此时距离使用 lead 最大差，完整集合使用所有 lead 折点收益向量的共同凸包。有预先固定的权重时，使用各 lead 凸包的加权 Minkowski 和。不得将未来有效 mask 传入 weights。

`ProjectionResult` 输出 scores、status、converged、gap、iterations、elapsed_seconds、objective、timed_out、reason，支持 `.to_dict()`。`completed` 为相应容差通过；`iteration_limit` 返回可行的 FW 近似结果和最终点 gap；`timeout` / `failed` 返回 previous_scores（未提供时为 raw），必须由调用方保留上一次有效动作并停止查询。失败输出不是已投影评分。

模式：raw 不校正；single 单臂截断；pair 全成对差约束 QP；full 完整联合凸集。pair 使用既有 SciPy SLSQP，并用独立线性规划计算一阶 gap 证书，检查约束残差，失败/超时不提交新评分。全部模式的计时含输入检查与首次导入等实际求解开销。

full 为 NumPy Frank-Wolfe，从 0 初始化，LMO 使用有限折点、精确线搜索。参考坐标始终为 0。返回前重新计算最终点 gap，不把前一步 gap 标到更新后的点。每次迭代检查时间，时间不是硬实时中断保证；已开始的一次 NumPy/优化库调用只能结束后检查，实际超出仍计入费用并回退。

## 理论边界

经典凸投影的精确结果满足整体收益向量平方误差不增加；近似结果保留 `2*gap` 余项。此性质不保证每坐标、排名、动作选择或最终 MASE 改善。凸组合只用于收益约束，最终预测不得混合。两个不同预测时完整几何可能退化为区间。Frank-Wolfe、绝对损失三角不等式、凸包和投影均为既有数学工具。

## 必要验收

服务器命令：

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" -m pytest -q tests/v431_r5/test_geometry.py
```

实际 10 项通过（2026-09-16）：0/1/2 解析例、重复预测、独立小型凸组合 QP 对照、任意已知 y 构造的真实收益可行性及 gap 余项、两动作区间、成对投影、未知未来 mask、非有限/非法参考拒绝、0 秒预算回退、最终迭代 gap。

初次测试有两项失败，均保留在执行历史：解析预期手算错误，正确投影为 `[0,0.6,1.2]`；另一项错误要求有限迭代 FW 达到更小 gap。修改为独立 QP 坐标对照及有效 gap 误差界，并明确该案例 20000 次迭代仍为近似解，未改动求解器以伪造收敛。生产参数仍为预登记的 2048 次、1e-8、0.05 秒。
