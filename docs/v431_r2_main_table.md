# v4.3.1-r2 共同DEV主表

原三来源、26独立parent、156相关变体；所有臂同origin/target/H96、H192/评分mask。MASE及秒数按source/parent宏平均。秒数是补全规划费用后的批量部署组件，冷在线另报。low=0.8140623268639832秒，high=3.5秒；TATO保留8trial原生能力，预算事后审计。

| 模型 | 策略 | MASE ↓ | 秒/窗 | 工具/窗 | parent |
|---|---|---:|---:|---:|---:|
| bolt | EXISTING_SAME_EVIDENCE_CART | 1.136486 | 0.657985 | 2.000 | 26 |
| bolt | FIXED_ACQUIRE_CART_high | 1.214872 | 0.472348 | 0.778 | 26 |
| bolt | FIXED_ACQUIRE_CART_low | 1.150865 | 0.226057 | 0.444 | 26 |
| bolt | FIXED_BOTH_CART_high | 1.150865 | 0.435573 | 0.889 | 26 |
| bolt | FIXED_BOTH_CART_low | 1.157005 | 0.122015 | 0.000 | 26 |
| bolt | FIXED_HISTORY_CART_high | 1.214872 | 0.472332 | 0.778 | 26 |
| bolt | FIXED_HISTORY_CART_low | 1.157005 | 0.122017 | 0.000 | 26 |
| bolt | FIXED_MASK_CART_high | 1.150865 | 0.226012 | 0.444 | 26 |
| bolt | FIXED_MASK_CART_low | 1.150865 | 0.226031 | 0.444 | 26 |
| bolt | FIXED_REFERENCE | 1.157005 | 0.120142 | 0.000 | 26 |
| bolt | FIXED_TSICL | 1.157005 | 0.120142 | 0.000 | 26 |
| bolt | FORCE_STOP_high | 1.157005 | 0.122022 | 0.000 | 26 |
| bolt | FORCE_STOP_low | 1.157005 | 0.122029 | 0.000 | 26 |
| bolt | KEEP | 1.258454 | 0.089880 | 0.000 | 26 |
| bolt | R2_AGENT_high | 1.157005 | 0.122043 | 0.000 | 26 |
| bolt | R2_AGENT_low | 1.157005 | 0.122157 | 0.000 | 26 |
| timesfm | EXISTING_SAME_EVIDENCE_CART | 1.069086 | 1.072156 | 2.000 | 26 |
| timesfm | FIXED_ACQUIRE_CART_high | 1.069398 | 0.340510 | 0.444 | 26 |
| timesfm | FIXED_ACQUIRE_CART_low | 1.069398 | 0.340527 | 0.444 | 26 |
| timesfm | FIXED_BOTH_CART_high | 1.069398 | 0.716272 | 0.889 | 26 |
| timesfm | FIXED_BOTH_CART_low | 1.096135 | 0.232037 | 0.000 | 26 |
| timesfm | FIXED_HISTORY_CART_high | 1.069086 | 0.867257 | 0.778 | 26 |
| timesfm | FIXED_HISTORY_CART_low | 1.096135 | 0.232039 | 0.000 | 26 |
| timesfm | FIXED_MASK_CART_high | 1.069398 | 0.340508 | 0.444 | 26 |
| timesfm | FIXED_MASK_CART_low | 1.069398 | 0.340513 | 0.444 | 26 |
| timesfm | FIXED_REFERENCE | 1.096135 | 0.230020 | 0.000 | 26 |
| timesfm | FIXED_TSICL | 1.096135 | 0.230020 | 0.000 | 26 |
| timesfm | FORCE_STOP_high | 1.096135 | 0.232040 | 0.000 | 26 |
| timesfm | FORCE_STOP_low | 1.096135 | 0.232051 | 0.000 | 26 |
| timesfm | KEEP | 1.139837 | 0.200703 | 0.000 | 26 |
| timesfm | R2_AGENT_high | 1.069398 | 0.340542 | 0.444 | 26 |
| timesfm | R2_AGENT_low | 1.069398 | 0.340662 | 0.444 | 26 |
| bolt | TATO_8_NATIVE_SPACE | 1.685227 | 0.703174 | 8.000 | 26 |
| timesfm | TATO_8_NATIVE_SPACE | 1.529002 | 1.023989 | 8.000 | 26 |

逐来源/跨度/条件配对表与区间：`results/v431-r2/metrics_by_source_horizon_condition.json`、`paired_comparisons.json`。金融观测索引附表使用新的目标事件索引/MASE分母，不能和本表横比。
