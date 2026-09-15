> 历史r3原协议结果保留：响应和主动取证贡献未得到支持。最新尺度修复与联合策略见[v4.3.1-r4报告](v431_r4_report.md)，不回写本页旧数字。

# v4.3.1-r3 共同开发主表

同三来源、26 parent、156相关变体、共同目标与评分mask，source宏平均并按parent聚合。两个family不是两份独立数据。全表保留不支持、STOP与实际超预算；秒数为部署组件计费，完整冷在线墙钟另报。固定原生方法与TATO未执行同一预算准入时，其超支应按实际秒数另核，不能把缺少预算flag解读为预算内。8个TATO优化trial不同于agent工具调用。

| 家族 | 方法 | MASE ↓ | 秒/窗 | 工具/窗 | parent | 超预算窗 |
|---|---|---:|---:|---:|---:|---:|
| bolt | CART_H32_high | 1.210484 | 0.225270 | 0.444 | 26 | 0 |
| bolt | CART_H32_low | 1.210484 | 0.225289 | 0.444 | 26 | 0 |
| bolt | CART_H_high | 1.203353 | 0.305781 | 0.444 | 26 | 0 |
| bolt | CART_H_low | 1.203353 | 0.305787 | 0.444 | 26 | 0 |
| bolt | CART_control_high | 1.157005 | 0.283899 | 0.444 | 26 | 0 |
| bolt | CART_control_low | 1.157005 | 0.120519 | 0.000 | 26 | 0 |
| bolt | CART_disagreement_high | 1.157005 | 0.283997 | 0.444 | 26 | 0 |
| bolt | CART_disagreement_low | 1.157005 | 0.120518 | 0.000 | 26 | 0 |
| bolt | CART_equal-cost_high | 1.157005 | 0.283885 | 0.444 | 26 | 0 |
| bolt | CART_equal-cost_low | 1.157005 | 0.120518 | 0.000 | 26 | 0 |
| bolt | DIRECT_H32_high | 1.156824 | 0.235627 | 0.444 | 26 | 0 |
| bolt | DIRECT_H32_low | 1.156824 | 0.235629 | 0.444 | 26 | 0 |
| bolt | DIRECT_H_high | 1.154034 | 0.309628 | 0.444 | 26 | 0 |
| bolt | DIRECT_H_low | 1.154034 | 0.309625 | 0.444 | 26 | 0 |
| bolt | DIRECT_control_high | 1.146643 | 0.283285 | 0.444 | 26 | 0 |
| bolt | DIRECT_control_low | 1.157005 | 0.120517 | 0.000 | 26 | 0 |
| bolt | DIRECT_disagreement_high | 1.146762 | 0.282393 | 0.444 | 26 | 0 |
| bolt | DIRECT_disagreement_low | 1.157005 | 0.120518 | 0.000 | 26 | 0 |
| bolt | DIRECT_equal-cost_high | 1.149968 | 0.281374 | 0.444 | 26 | 0 |
| bolt | DIRECT_equal-cost_low | 1.157005 | 0.120518 | 0.000 | 26 | 0 |
| bolt | FIXED_A0_FFILL | 1.430629 | 0.090194 | 0.000 | 26 | 0 |
| bolt | FIXED_A3_COV | 1.313983 | 0.124236 | 0.000 | 26 | 0 |
| bolt | FIXED_A4_RIDGE_CONTEXT | 1.214538 | 0.092916 | 0.000 | 26 | 0 |
| bolt | FIXED_REFERENCE | 1.157005 | 0.120142 | 0.000 | 26 | 0 |
| bolt | FIXED_TSICL | 1.157005 | 0.120142 | 0.000 | 26 | 0 |
| bolt | FORCE_STOP | 1.157005 | 0.120499 | 0.000 | 26 | 0 |
| bolt | HISTORICAL_ARGMAX_H32_high | 1.201569 | 0.227264 | 0.444 | 26 | 0 |
| bolt | HISTORICAL_ARGMAX_H32_low | 1.201569 | 0.227262 | 0.444 | 26 | 0 |
| bolt | HISTORICAL_ARGMAX_H_high | 1.163871 | 0.307140 | 0.444 | 26 | 0 |
| bolt | HISTORICAL_ARGMAX_H_low | 1.163871 | 0.307138 | 0.444 | 26 | 0 |
| bolt | KEEP | 1.258454 | 0.089880 | 0.000 | 26 | 0 |
| bolt | R2_EXISTING_CART | 1.136486 | 0.657985 | 2.000 | 26 | 0 |
| bolt | R3_AGENT_high | 1.156351 | 0.284957 | 0.444 | 26 | 0 |
| bolt | R3_AGENT_low | 1.157005 | 0.122956 | 0.000 | 26 | 0 |
| bolt | R3_FIXED_TOOL_high | 1.156351 | 0.284946 | 0.444 | 26 | 0 |
| bolt | R3_FIXED_TOOL_low | 1.153110 | 0.314408 | 0.444 | 26 | 0 |
| bolt | R3_RANDOM_high | 1.168931 | 0.253947 | 0.367 | 26 | 0 |
| bolt | R3_RANDOM_low | 1.155963 | 0.222630 | 0.283 | 26 | 0 |
| bolt | RESIDUAL_H32_high | 1.204338 | 0.227810 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_H32_low | 1.204338 | 0.227821 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_H_high | 1.153110 | 0.310894 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_H_low | 1.153110 | 0.310875 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_control_high | 1.156351 | 0.281960 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_control_low | 1.157005 | 0.120512 | 0.000 | 26 | 0 |
| bolt | RESIDUAL_disagreement_high | 1.156327 | 0.282220 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_disagreement_low | 1.157005 | 0.120514 | 0.000 | 26 | 0 |
| bolt | RESIDUAL_equal-cost_high | 1.162748 | 0.279957 | 0.444 | 26 | 0 |
| bolt | RESIDUAL_equal-cost_low | 1.157005 | 0.120514 | 0.000 | 26 | 0 |
| bolt | TATO_8_NATIVE_SPACE | 1.685227 | 0.703174 | 8.000 | 26 | 0 |
| timesfm | CART_H32_high | 1.069398 | 0.596548 | 0.444 | 26 | 0 |
| timesfm | CART_H32_low | 1.096135 | 0.230555 | 0.000 | 26 | 0 |
| timesfm | CART_H_high | 1.069398 | 0.587328 | 0.444 | 26 | 0 |
| timesfm | CART_H_low | 1.096135 | 0.230554 | 0.000 | 26 | 0 |
| timesfm | CART_control_high | 1.096135 | 0.591610 | 0.444 | 26 | 0 |
| timesfm | CART_control_low | 1.096135 | 0.230554 | 0.000 | 26 | 0 |
| timesfm | CART_disagreement_high | 1.096135 | 0.591707 | 0.444 | 26 | 0 |
| timesfm | CART_disagreement_low | 1.096135 | 0.230554 | 0.000 | 26 | 0 |
| timesfm | CART_equal-cost_high | 1.096135 | 0.590879 | 0.444 | 26 | 0 |
| timesfm | CART_equal-cost_low | 1.096135 | 0.230555 | 0.000 | 26 | 0 |
| timesfm | DIRECT_H32_high | 1.092782 | 0.598348 | 0.444 | 26 | 0 |
| timesfm | DIRECT_H32_low | 1.096135 | 0.230555 | 0.000 | 26 | 0 |
| timesfm | DIRECT_H_high | 1.072139 | 0.585621 | 0.444 | 26 | 0 |
| timesfm | DIRECT_H_low | 1.096135 | 0.230554 | 0.000 | 26 | 0 |
| timesfm | DIRECT_control_high | 1.096564 | 0.589380 | 0.444 | 26 | 0 |
| timesfm | DIRECT_control_low | 1.096135 | 0.230554 | 0.000 | 26 | 0 |
| timesfm | DIRECT_disagreement_high | 1.091466 | 0.589082 | 0.444 | 26 | 0 |
| timesfm | DIRECT_disagreement_low | 1.096135 | 0.230554 | 0.000 | 26 | 0 |
| timesfm | DIRECT_equal-cost_high | 1.088631 | 0.586664 | 0.444 | 26 | 0 |
| timesfm | DIRECT_equal-cost_low | 1.096135 | 0.230554 | 0.000 | 26 | 0 |
| timesfm | FIXED_A0_FFILL | 1.181309 | 0.200212 | 0.000 | 26 | 0 |
| timesfm | FIXED_A3_COV | 1.136583 | 0.234099 | 0.000 | 26 | 0 |
| timesfm | FIXED_A4_RIDGE_CONTEXT | 1.090970 | 0.203695 | 0.000 | 26 | 0 |
| timesfm | FIXED_REFERENCE | 1.096135 | 0.230177 | 0.000 | 26 | 0 |
| timesfm | FIXED_TSICL | 1.096135 | 0.230020 | 0.000 | 26 | 0 |
| timesfm | FORCE_STOP | 1.096135 | 0.230536 | 0.000 | 26 | 0 |
| timesfm | HISTORICAL_ARGMAX_H32_high | 1.142717 | 0.596074 | 0.444 | 26 | 0 |
| timesfm | HISTORICAL_ARGMAX_H32_low | 1.096135 | 0.230567 | 0.000 | 26 | 0 |
| timesfm | HISTORICAL_ARGMAX_H_high | 1.077045 | 0.586008 | 0.444 | 26 | 0 |
| timesfm | HISTORICAL_ARGMAX_H_low | 1.096135 | 0.230565 | 0.000 | 26 | 0 |
| timesfm | KEEP | 1.139837 | 0.200703 | 0.000 | 26 | 0 |
| timesfm | R2_EXISTING_CART | 1.069086 | 1.072156 | 2.000 | 26 | 0 |
| timesfm | R3_AGENT_high | 1.102669 | 0.600939 | 0.444 | 26 | 0 |
| timesfm | R3_AGENT_low | 1.096135 | 0.232947 | 0.000 | 26 | 0 |
| timesfm | R3_FIXED_TOOL_high | 1.096019 | 0.592392 | 0.444 | 26 | 0 |
| timesfm | R3_FIXED_TOOL_low | 1.096135 | 0.232926 | 0.000 | 26 | 0 |
| timesfm | R3_RANDOM_high | 1.091977 | 0.530007 | 0.367 | 26 | 0 |
| timesfm | R3_RANDOM_low | 1.096135 | 0.232938 | 0.000 | 26 | 0 |
| timesfm | RESIDUAL_H32_high | 1.102669 | 0.597455 | 0.444 | 26 | 0 |
| timesfm | RESIDUAL_H32_low | 1.096135 | 0.230558 | 0.000 | 26 | 0 |
| timesfm | RESIDUAL_H_high | 1.085811 | 0.588517 | 0.444 | 26 | 0 |
| timesfm | RESIDUAL_H_low | 1.096135 | 0.230549 | 0.000 | 26 | 0 |
| timesfm | RESIDUAL_control_high | 1.096019 | 0.589449 | 0.444 | 26 | 0 |
| timesfm | RESIDUAL_control_low | 1.096135 | 0.230549 | 0.000 | 26 | 0 |
| timesfm | RESIDUAL_disagreement_high | 1.092599 | 0.589145 | 0.444 | 26 | 0 |
| timesfm | RESIDUAL_disagreement_low | 1.096135 | 0.230550 | 0.000 | 26 | 0 |
| timesfm | RESIDUAL_equal-cost_high | 1.091448 | 0.588512 | 0.444 | 26 | 0 |
| timesfm | RESIDUAL_equal-cost_low | 1.096135 | 0.230550 | 0.000 | 26 | 0 |
| timesfm | TATO_8_NATIVE_SPACE | 1.529002 | 1.023989 | 8.000 | 26 | 0 |

金融事件索引附表不同协议/分母，不与本表横比。配对统计、共同支持子集与实际适用性见r3报告及机器账本。
