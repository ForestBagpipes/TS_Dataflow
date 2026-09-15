# v4.3.1-r5 同信息机制表

结论：固定查询轨迹下，FULL相对RAW在Bolt稍有改善，在TimesFM退步；收益向量平方误差改善不等价于排序或最终预测改善。联合约束的跨家族开发条件未满足。

CURRENT四臂严格共用同一窗口查询动作与raw scorer；FREE/HISTORY沿相同当前查询集合，但其ridge分别拟合，只有架构、监督和alpha搜索预算一致，并非同一冻结系数。HISTORY额外取得并支付历史H证据，不能称同成本比较。当前完整L512任务响应与历史416/320输入任务分开。 表中激活与排名改变比例按source→parent→variant宏平均，不等于简单窗数比例；平方误差为每窗收益向量坐标平方和再宏平均，未除以动作数。失败/unsupported不从主MASE分母删除，评分指标只在有效配对记录上计算。

## 旧DEV：固定轨迹，全部窗口

| 家族 | scorer/约束 | MASE | 秒/窗 | 向量平方误差 | 约束违反 | 投影激活比例 | 排名改变比例 | 切换收益 | 错切损失 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bolt | MECH_CURRENT_FULL | 1.226845 | 0.253519 | 5.12951 | 0 | 0.433983 | 0.00793651 | 0.010945 | 0.085375 |
| bolt | MECH_CURRENT_PAIR | 1.228042 | 0.251720 | 5.13011 | 0 | 0.0151515 | 0 | 0.009888 | 0.085515 |
| bolt | MECH_CURRENT_RAW | 1.228042 | 0.251026 | 5.13036 | 0.000767917 | 0 | 0 | 0.009888 | 0.085515 |
| bolt | MECH_CURRENT_SINGLE | 1.228042 | 0.251056 | 5.13011 | 0 | 0.0151515 | 0 | 0.009888 | 0.085515 |
| bolt | MECH_FREE_RAW | 1.412477 | 0.251027 | 5.46219 | 0 | 0 | 0 | 0.012176 | 0.272239 |
| bolt | MECH_HISTORY_RAW | 1.179009 | 0.442365 | 7.7878 | 0 | 0 | 0 | 0.020007 | 0.046601 |
| timesfm | MECH_CURRENT_FULL | 1.085207 | 0.535496 | 1.20355 | 0 | 0.568543 | 0.116162 | 0.022402 | 0.038211 |
| timesfm | MECH_CURRENT_PAIR | 1.089609 | 0.526898 | 1.20886 | 3.50324e-18 | 0.374459 | 0.181818 | 0.020770 | 0.040981 |
| timesfm | MECH_CURRENT_RAW | 1.084789 | 0.526191 | 1.21278 | 0.0227374 | 0 | 0 | 0.022445 | 0.037835 |
| timesfm | MECH_CURRENT_SINGLE | 1.089609 | 0.526222 | 1.20887 | 0.000395201 | 0.348485 | 0.171717 | 0.020770 | 0.040981 |
| timesfm | MECH_FREE_RAW | 1.077708 | 0.526193 | 1.01297 | 0.116014 | 0 | 0 | 0.027241 | 0.035550 |
| timesfm | MECH_HISTORY_RAW | 1.088962 | 0.888182 | 1.55445 | 0.00124737 | 0 | 0 | 0.012323 | 0.031887 |

### FULL配对差，负数更好

| 家族 | 相对方法 | 子集 | parent/窗 | MASE差 | 描述性90%区间 |
|---|---|---|---:|---:|---|
| bolt | MECH_CURRENT_RAW | all | 26/156 | -0.001196683 | [-0.003590048, 0.000000000] |
| bolt | MECH_CURRENT_RAW | three_distinct_predictions | 26/103 | -0.001795024 | [-0.005385072, 0.000000000] |
| bolt | MECH_CURRENT_SINGLE | all | 26/156 | -0.001196683 | [-0.003590048, 0.000000000] |
| bolt | MECH_CURRENT_SINGLE | three_distinct_predictions | 26/103 | -0.001795024 | [-0.005385072, 0.000000000] |
| bolt | MECH_CURRENT_PAIR | all | 26/156 | -0.001196683 | [-0.003590048, 0.000000000] |
| bolt | MECH_CURRENT_PAIR | three_distinct_predictions | 26/103 | -0.001795024 | [-0.005385072, 0.000000000] |
| timesfm | MECH_CURRENT_RAW | all | 26/156 | 0.000418047 | [0.000127726, 0.000926109] |
| timesfm | MECH_CURRENT_RAW | three_distinct_predictions | 25/102 | 0.000606756 | [0.000127726, 0.001564816] |
| timesfm | MECH_CURRENT_SINGLE | all | 26/156 | -0.004402584 | [-0.004402584, -0.004402584] |
| timesfm | MECH_CURRENT_SINGLE | three_distinct_predictions | 25/102 | -0.004402584 | [-0.004402584, -0.004402584] |
| timesfm | MECH_CURRENT_PAIR | all | 26/156 | -0.004402584 | [-0.004402584, -0.004402584] |
| timesfm | MECH_CURRENT_PAIR | three_distinct_predictions | 25/102 | -0.004402584 | [-0.004402584, -0.004402584] |

### 求解状态

| 家族 | 约束 | 调用 | 状态 | 最大gap | 求解总秒 | 失败窗 |
|---|---|---:|---|---:|---:|---:|
| bolt | MECH_CURRENT_FULL | 156 | {'completed': 142, 'iteration_limit': 14} | 0.00253838 | 0.544334 | 0 |
| bolt | MECH_CURRENT_PAIR | 156 | {'completed': 156} | 7.95011e-19 | 0.097217 | 0 |
| bolt | MECH_CURRENT_RAW | 156 | {'completed': 156} | 0 | 0.001698 | 0 |
| bolt | MECH_CURRENT_SINGLE | 156 | {'completed': 156} | 0 | 0.006266 | 0 |
| bolt | MECH_FREE_RAW | 156 | {'completed': 156} | 0 | 0.001820 | 0 |
| bolt | MECH_HISTORY_RAW | 150 | {'completed': 150} | 0 | 0.001708 | 6 |
| timesfm | MECH_CURRENT_FULL | 156 | {'completed': 141, 'iteration_limit': 15} | 0.00446011 | 0.523733 | 0 |
| timesfm | MECH_CURRENT_PAIR | 156 | {'completed': 156} | 5.89724e-17 | 0.097767 | 0 |
| timesfm | MECH_CURRENT_RAW | 156 | {'completed': 156} | 0 | 0.001794 | 0 |
| timesfm | MECH_CURRENT_SINGLE | 156 | {'completed': 156} | 0 | 0.006356 | 0 |
| timesfm | MECH_FREE_RAW | 156 | {'completed': 156} | 0 | 0.001921 | 0 |
| timesfm | MECH_HISTORY_RAW | 150 | {'completed': 150} | 0 | 0.001785 | 6 |

实际真实gain投影余项核验：312窗，超过1e-8的违规0；这仅为数值几何核验，不是预测安全证书。

## 金融附表：固定轨迹，全部窗口

| 家族 | scorer/约束 | MASE | 秒/窗 | 向量平方误差 | 约束违反 | 投影激活比例 | 排名改变比例 | 切换收益 | 错切损失 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bolt | MECH_CURRENT_FULL | 3.089412 | 0.882493 | 0.194975 | 0 | 0.0833333 | 0 | 0.000000 | 0.046936 |
| bolt | MECH_CURRENT_PAIR | 3.089412 | 0.882704 | 0.194975 | 0 | 0 | 0 | 0.000000 | 0.046936 |
| bolt | MECH_CURRENT_RAW | 3.089412 | 0.882291 | 0.194975 | 0 | 0 | 0 | 0.000000 | 0.046936 |
| bolt | MECH_CURRENT_SINGLE | 3.089412 | 0.882315 | 0.194975 | 0 | 0 | 0 | 0.000000 | 0.046936 |
| bolt | MECH_FREE_RAW | 3.083740 | 0.882292 | 0.168646 | 0 | 0 | 0 | 0.000000 | 0.041264 |
| bolt | MECH_HISTORY_RAW | 2.983624 | 1.002161 | 0.198664 | 0 | 0 | 0 | 0.083652 | 0.024800 |
| timesfm | MECH_CURRENT_FULL | 4.896736 | 0.694621 | 0.735298 | 0 | 0.5 | 0.166667 | 0.001200 | 0.007699 |
| timesfm | MECH_CURRENT_PAIR | 4.896736 | 0.692413 | 0.73526 | 2.31296e-18 | 0.333333 | 0.166667 | 0.001200 | 0.007699 |
| timesfm | MECH_CURRENT_RAW | 4.896678 | 0.691781 | 0.744469 | 0.0232086 | 0 | 0 | 0.001178 | 0.007620 |
| timesfm | MECH_CURRENT_SINGLE | 4.896736 | 0.691808 | 0.735284 | 0.00144776 | 0.25 | 0.166667 | 0.001200 | 0.007699 |
| timesfm | MECH_FREE_RAW | 5.219400 | 0.691781 | 1.57996 | 0.102955 | 0 | 0 | 0.001178 | 0.330342 |
| timesfm | MECH_HISTORY_RAW | 5.205059 | 1.236340 | 1.7584 | 0.00745351 | 0 | 0 | 0.001178 | 0.316000 |

### FULL配对差，负数更好

| 家族 | 相对方法 | 子集 | parent/窗 | MASE差 | 描述性90%区间 |
|---|---|---|---:|---:|---|
| bolt | MECH_CURRENT_RAW | all | 2/12 | 0.000000000 | [0.000000000, 0.000000000] |
| bolt | MECH_CURRENT_RAW | three_distinct_predictions | 2/2 | 0.000000000 | [0.000000000, 0.000000000] |
| bolt | MECH_CURRENT_SINGLE | all | 2/12 | 0.000000000 | [0.000000000, 0.000000000] |
| bolt | MECH_CURRENT_SINGLE | three_distinct_predictions | 2/2 | 0.000000000 | [0.000000000, 0.000000000] |
| bolt | MECH_CURRENT_PAIR | all | 2/12 | 0.000000000 | [0.000000000, 0.000000000] |
| bolt | MECH_CURRENT_PAIR | three_distinct_predictions | 2/2 | 0.000000000 | [0.000000000, 0.000000000] |
| timesfm | MECH_CURRENT_RAW | all | 2/12 | 0.000058078 | [0.000058078, 0.000058078] |
| timesfm | MECH_CURRENT_RAW | three_distinct_predictions | 2/8 | 0.000087117 | [0.000087117, 0.000087117] |
| timesfm | MECH_CURRENT_SINGLE | all | 2/12 | 0.000000000 | [0.000000000, 0.000000000] |
| timesfm | MECH_CURRENT_SINGLE | three_distinct_predictions | 2/8 | 0.000000000 | [0.000000000, 0.000000000] |
| timesfm | MECH_CURRENT_PAIR | all | 2/12 | 0.000000000 | [0.000000000, 0.000000000] |
| timesfm | MECH_CURRENT_PAIR | three_distinct_predictions | 2/8 | 0.000000000 | [0.000000000, 0.000000000] |

### 求解状态

| 家族 | 约束 | 调用 | 状态 | 最大gap | 求解总秒 | 失败窗 |
|---|---|---:|---|---:|---:|---:|
| bolt | MECH_CURRENT_FULL | 12 | {'completed': 12} | 7.43655e-09 | 0.002547 | 0 |
| bolt | MECH_CURRENT_PAIR | 12 | {'completed': 12} | 0 | 0.005083 | 0 |
| bolt | MECH_CURRENT_RAW | 12 | {'completed': 12} | 0 | 0.000126 | 0 |
| bolt | MECH_CURRENT_SINGLE | 12 | {'completed': 12} | 0 | 0.000416 | 0 |
| bolt | MECH_FREE_RAW | 12 | {'completed': 12} | 0 | 0.000134 | 0 |
| bolt | MECH_HISTORY_RAW | 12 | {'completed': 12} | 0 | 0.000129 | 0 |
| timesfm | MECH_CURRENT_FULL | 12 | {'completed': 12} | 9.99165e-09 | 0.034237 | 0 |
| timesfm | MECH_CURRENT_PAIR | 12 | {'completed': 12} | 2.11873e-18 | 0.007741 | 0 |
| timesfm | MECH_CURRENT_RAW | 12 | {'completed': 12} | 0 | 0.000147 | 0 |
| timesfm | MECH_CURRENT_SINGLE | 12 | {'completed': 12} | 0 | 0.000480 | 0 |
| timesfm | MECH_FREE_RAW | 12 | {'completed': 12} | 0 | 0.000149 | 0 |
| timesfm | MECH_HISTORY_RAW | 12 | {'completed': 12} | 0 | 0.000137 | 0 |

实际真实gain投影余项核验：24窗，超过1e-8的违规0；这仅为数值几何核验，不是预测安全证书。

## 归因范围

- source固定、parent按相邻时间块处理，2000次bootstrap、seed101；所有区间仅描述反复使用的开发数据。
- 至少3个数值不同预测的子集单列；完整分母包含KEEP、预算STOP、unsupported及失败回退。两个不同预测的退化区间不作为高阶结构证据。
- iteration_limit不是精确投影；以实际gap和带2gap余项性质报告，不将未收敛改称完成。
- 机制费用含同一基础固定轨迹执行及额外离线终态评分/求解；它是共同机制账本，不能冒充真实在线请求延迟。
- 选择性、固定数量、固定顺序、预算约束全部调用和真正五臂执行的完整MASE/费用见共同主表。真正全部五臂为更高成本对照，不能归入最多三个版本方法。

生成依据：statistics/report.json和各suite机制原始记录；脚本v431_r5_common.py --docs。
