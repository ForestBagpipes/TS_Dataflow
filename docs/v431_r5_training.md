# r5 参考策略和收益学习：实际接口

实现：`src/introact_ts/v431_r5/scoring.py`。这里不读取任何结果文件，不加载 TSFM；调用方只向拟合函数提供 fit 标签。gate 只选择预先登记的 ridge alpha `{0.1,1,10}`，不能训练系数或选择参考冠军。开发/确认标签被 fit API 拒绝。

## 参考策略与交叉拟合

`FreeReference.fit(batch)` 是一个固定深度一的成本敏感免费树，阈值仅为 fit 的 25%、50%、75% 分位数，每个学习叶至少 16 个非完整输入独立 parent。不扩深度，不读工具证据或预测响应。终叶以 source/parent/variant 权重的任务损失选择五臂之一，平局优先 A2，再按稳定动作顺序。完整有效 target 直接 KEEP。fit 缺失元数据用 fit 中位数填补（全缺字段固定零），不是已取得的模型证据。

`crossfit_reference(batch)` 为每个 parent 单独构造同 source 的 forward 训练前缀，要求训练 parent 的**所有变体最大完整读取终点** `context_end+H` 不晚于验证 parent 最早 `raw_start`。不使用不可比较的不同 source 行号作为共同时间。当前前缀不足 16 parent 时，使用预先约定的 A2；这是协议回退而不是有监督学习所得冠军。逐 parent 记录训练 parent 清单、数量、验证起点、最大训练读取终点和回退状态。最终参考策略可在全部 fit 上训练，OOF 参考则不回填为全 fit 选择。

调用接口：`crossfit_reference(batch) -> (actions, audit)`；`FreeReference().fit(batch).predict(visible, fully_observed=False)`。主进程负责持久化 OOF 标签与审计清单。

## 当前响应和预查询先验

`response_features(p0, pa, S)` 只接受相同完整 H 的两条已执行预测及合法 origin 正尺度。令 `d=(pa-p0)/S`，七项依次为平均有符号差、平均绝对差、最大绝对差、前半绝对差、后半绝对差、在等距归一化 lead `[-0.5,0.5]` 上的 OLS 趋势斜率、最后 lead 差值。非有限预测直接拒绝。它不读取未来 mask 或标签。

`reference_features(p0,S)` 为先验提供同七项统计，但基于 `p0/S`（相对全零向量），只需已经付费执行的参考预测，不能接受候选预测。

`SharedRidge.fit(features, actions, targets, weights, alpha=..., roles=..., parents=...)` 使用共享斜率和五动作截距。所有字段的中位数填补、缺失指示、加权均值/方差只在 fit 拟合；目标单位为当前实际参考 MAE 减候选 MAE，再除 origin 合法 S。不是外层报告 MASE，也不是旧重建 gain。最小化归一化加权平方误差加 alpha 的系数平方惩罚，包括截距；没有在 gate 重新估计标准化。`.predict(features,actions)` 不接受标签参数。

`paired_training_rows` 是离线 TRAIN 展开器，必须由调用方传入 OOF 参考。它按 source/parent/variant 权重为每个非参考动作分配四分之一窗口权重。CURRENT 使用真实七项响应；PRIOR 使用仅 p0 七项；FREE 保留明确不存在的零特征块以保持相同设计宽度；HISTORY 需调用方提供七项真实历史信息与费用，缺失历史不伪装为实测零。参考自身收益必须由运行时固定为零，不能采用 ridge 的参考预测值。

## 本模块验收与边界

服务器定向测试 `tests/v431_r5/test_scoring.py`：6 项通过，涵盖七项单位/完整跨度、fit 角色拒绝、完整 parent purge 与自标签投毒不影响 OOF 动作、学习叶支持和完整 KEEP、fit-only 缺失处理、未查询预测投毒不影响先验输入。测试不证明研究增益；实际有效支持、alpha、模型哈希和开发效果由共同训练运行报告给出。

实际命令：`source scripts/env_new_server.sh` 后 `"$W2_CORE_PY" -m pytest -q tests/v431_r5/test_scoring.py`。

首次只读支持盘点：加载 `results/v431-r4/trajectory-final/main/{bolt,timesfm}.joblib` 并仅选 T_fit，两家族均为 54 parent、324 相关变体；同 source 完整区间 purge 的最大历史前缀为 28 parent，35/54 验证 parent 的前缀不足 16，19/54 有足够历史支持。此处使用原 r4 13 维免费特征，只用于核实支持，不替代主进程加入合法覆盖元数据后的最终 fit/freeze。没有读取 DEV。
