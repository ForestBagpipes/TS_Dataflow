# v4.3.1-r4 描述性统计与诊断

状态：`completed`。输入缺失明确保留 pending，不伪造结果。

同 source 内按原始时间相邻两个 parent 分块，2000 次 bootstrap，seed=101。变体和跨度不拆 parent；source 等权。单一 USTS parent 与金融两个单来源 parent 的时间不确定性不可识别。旧 DEV 多次查看，区间不构成独立确认。

差值为 JOINT − 对照，负数更好。尾部退步、预测改变、超预算和 unsupported 分开保留。费用使用完整路径实测值；缺预算标志不视为合规。

## dev

状态：completed。

| 家族 | 对照 | 预算 | MASE 差 | 90% 描述区间 | JOINT 超支 / 对照超支 |
|---|---|---|---:|---|---:|
| bolt | FIXED_CONTROL_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | LEGACY_CART_H32_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | LEGACY_CART_H_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | LEGACY_CART_control_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | LEGACY_DIRECT_H32_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | LEGACY_DIRECT_H_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | LEGACY_DIRECT_control_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | R2_EXISTING_CART_low | low | 0.020519 | [-0.006628, 0.067864] | 0 / 51 |
| bolt | R3_FROZEN_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | R3_RETRAINED_STAGED_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | STAGED_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | TATO_NATIVE_8_low | low | -0.528223 | [-0.721831, -0.357669] | 0 / 17 |
| bolt | FIXED_CONTROL_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_high | high | -0.002880 | [-0.025061, 0.019077] | 0 / 0 |
| bolt | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_high | high | -0.002880 | [-0.025061, 0.019077] | 0 / 0 |
| bolt | FREE_ONLY_high | high | -0.002880 | [-0.025061, 0.019077] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_high | high | -0.019989 | [-0.068574, 0.018653] | 0 / 0 |
| bolt | LEGACY_CART_H32_high | high | -0.002880 | [-0.025061, 0.019077] | 0 / 0 |
| bolt | LEGACY_CART_H_high | high | -0.013880 | [-0.036840, 0.008327] | 0 / 0 |
| bolt | LEGACY_CART_control_high | high | -0.002880 | [-0.025061, 0.019077] | 0 / 0 |
| bolt | LEGACY_DIRECT_H32_high | high | -0.002880 | [-0.025061, 0.019077] | 0 / 0 |
| bolt | LEGACY_DIRECT_H_high | high | -0.003637 | [-0.007868, -0.000606] | 0 / 0 |
| bolt | LEGACY_DIRECT_control_high | high | 0.007489 | [-0.008932, 0.024196] | 0 / 0 |
| bolt | R2_EXISTING_CART_high | high | 0.017638 | [-0.013205, 0.051780] | 0 / 0 |
| bolt | R3_FROZEN_high | high | -0.002227 | [-0.014040, 0.010027] | 0 / 0 |
| bolt | R3_RETRAINED_STAGED_high | high | -0.002880 | [-0.025061, 0.019077] | 0 / 0 |
| bolt | STAGED_high | high | 0.003337 | [-0.005980, 0.013752] | 0 / 0 |
| bolt | TATO_NATIVE_8_high | high | -0.531103 | [-0.720937, -0.358693] | 0 / 0 |
| bolt | TRAIN_BEST_FIXED_FLOW_high | high | -0.000430 | [-0.011763, 0.011953] | 0 / 0 |
| timesfm | FIXED_CONTROL_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | FIXED_H32_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | FIXED_H_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | FIXED_REFERENCE_low | low | -0.009814 | [-0.042261, 0.021367] | 0 / 0 |
| timesfm | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_low | low | -0.001596 | [-0.018600, 0.014726] | 0 / 0 |
| timesfm | LEGACY_CART_H32_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | LEGACY_CART_H_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | LEGACY_CART_control_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | LEGACY_DIRECT_H32_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | LEGACY_DIRECT_H_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | LEGACY_DIRECT_control_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | R2_EXISTING_CART_low | low | 0.017235 | [0.006629, 0.030589] | 0 / 106 |
| timesfm | R3_FROZEN_low | low | -0.009814 | [-0.042261, 0.021367] | 0 / 0 |
| timesfm | R3_RETRAINED_STAGED_low | low | -0.004648 | [-0.021653, 0.011673] | 0 / 0 |
| timesfm | STAGED_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | TATO_NATIVE_8_low | low | -0.442681 | [-0.535587, -0.355704] | 0 / 156 |
| timesfm | TRAIN_BEST_FIXED_FLOW_low | low | -0.047034 | [-0.083874, -0.012499] | 0 / 0 |
| timesfm | FIXED_CONTROL_high | high | -0.017431 | [-0.040643, 0.002194] | 0 / 0 |
| timesfm | FIXED_H32_high | high | -0.026737 | [-0.059739, 0.003962] | 0 / 0 |
| timesfm | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | FIXED_REFERENCE_high | high | -0.026737 | [-0.059739, 0.003962] | 0 / 0 |
| timesfm | FREE_ONLY_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | LEGACY_CART_H32_high | high | -0.026737 | [-0.059739, 0.003962] | 0 / 0 |
| timesfm | LEGACY_CART_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | LEGACY_CART_control_high | high | -0.026737 | [-0.059739, 0.003962] | 0 / 0 |
| timesfm | LEGACY_DIRECT_H32_high | high | -0.026737 | [-0.059739, 0.003962] | 0 / 0 |
| timesfm | LEGACY_DIRECT_H_high | high | -0.003011 | [-0.010763, 0.002466] | 0 / 0 |
| timesfm | LEGACY_DIRECT_control_high | high | -0.025907 | [-0.057196, 0.003812] | 0 / 0 |
| timesfm | R2_EXISTING_CART_high | high | 0.000312 | [0.000312, 0.000312] | 0 / 0 |
| timesfm | R3_FROZEN_high | high | -0.033271 | [-0.079426, 0.005810] | 0 / 0 |
| timesfm | R3_RETRAINED_STAGED_high | high | -0.021571 | [-0.049179, -0.000455] | 0 / 0 |
| timesfm | STAGED_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | TATO_NATIVE_8_high | high | -0.459604 | [-0.550235, -0.372232] | 0 / 0 |
| timesfm | TRAIN_BEST_FIXED_FLOW_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |

## T_check

状态：completed。

| 家族 | 对照 | 预算 | MASE 差 | 90% 描述区间 | JOINT 超支 / 对照超支 |
|---|---|---|---:|---|---:|
| bolt | FIXED_CONTROL_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | STAGED_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_CONTROL_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_high | high | -0.010791 | [-0.020100, 0.000752] | 0 / 0 |
| bolt | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_high | high | -0.010791 | [-0.020100, 0.000752] | 0 / 0 |
| bolt | FREE_ONLY_high | high | -0.010791 | [-0.020100, 0.000752] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_high | high | -0.021978 | [-0.043500, 0.003539] | 0 / 0 |
| bolt | STAGED_high | high | -0.004640 | [-0.010503, -0.000263] | 0 / 0 |
| timesfm | FIXED_CONTROL_low | low | -0.030443 | [-0.051609, -0.006562] | 0 / 0 |
| timesfm | FIXED_H32_low | low | -0.030443 | [-0.051609, -0.006562] | 0 / 0 |
| timesfm | FIXED_H_low | low | -0.030443 | [-0.051609, -0.006562] | 0 / 0 |
| timesfm | FIXED_REFERENCE_low | low | 0.026921 | [0.009088, 0.044060] | 0 / 0 |
| timesfm | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_low | low | -0.023676 | [-0.030010, -0.016456] | 0 / 0 |
| timesfm | STAGED_low | low | -0.030443 | [-0.051609, -0.006562] | 0 / 0 |
| timesfm | FIXED_CONTROL_high | high | -0.006322 | [-0.013466, 0.001543] | 0 / 0 |
| timesfm | FIXED_H32_high | high | -0.011656 | [-0.032391, 0.005089] | 0 / 0 |
| timesfm | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | FIXED_REFERENCE_high | high | -0.011656 | [-0.032391, 0.005089] | 0 / 0 |
| timesfm | FREE_ONLY_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | STAGED_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |

## T_acq

状态：completed。

| 家族 | 对照 | 预算 | MASE 差 | 90% 描述区间 | JOINT 超支 / 对照超支 |
|---|---|---|---:|---|---:|
| bolt | FIXED_CONTROL_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | STAGED_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_CONTROL_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_high | high | -0.009888 | [-0.021668, 0.004392] | 0 / 0 |
| bolt | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_high | high | -0.009888 | [-0.021668, 0.004392] | 0 / 0 |
| bolt | FREE_ONLY_high | high | -0.009888 | [-0.021668, 0.004392] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_high | high | -0.010375 | [-0.023538, 0.002837] | 0 / 0 |
| bolt | STAGED_high | high | 0.002733 | [-0.001125, 0.006324] | 0 / 0 |
| timesfm | FIXED_CONTROL_low | low | -0.030704 | [-0.048301, -0.005736] | 0 / 0 |
| timesfm | FIXED_H32_low | low | -0.030704 | [-0.048301, -0.005736] | 0 / 0 |
| timesfm | FIXED_H_low | low | -0.030704 | [-0.048301, -0.005736] | 0 / 0 |
| timesfm | FIXED_REFERENCE_low | low | -0.004657 | [-0.039970, 0.023869] | 0 / 0 |
| timesfm | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_low | low | -0.005820 | [-0.025472, 0.021323] | 0 / 0 |
| timesfm | STAGED_low | low | -0.030704 | [-0.048301, -0.005736] | 0 / 0 |
| timesfm | FIXED_CONTROL_high | high | -0.018092 | [-0.040187, 0.001088] | 0 / 0 |
| timesfm | FIXED_H32_high | high | -0.022939 | [-0.047986, 0.002972] | 0 / 0 |
| timesfm | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | FIXED_REFERENCE_high | high | -0.022939 | [-0.047986, 0.002972] | 0 / 0 |
| timesfm | FREE_ONLY_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | STAGED_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |

## T_fit

状态：completed。

| 家族 | 对照 | 预算 | MASE 差 | 90% 描述区间 | JOINT 超支 / 对照超支 |
|---|---|---|---:|---|---:|
| bolt | FIXED_CONTROL_low | low | 0.000000 | [0.000000, 0.000000] | 2 / 2 |
| bolt | FIXED_H32_low | low | 0.000000 | [0.000000, 0.000000] | 2 / 2 |
| bolt | FIXED_H_low | low | 0.000000 | [0.000000, 0.000000] | 2 / 2 |
| bolt | FIXED_REFERENCE_low | low | 0.000000 | [0.000000, 0.000000] | 2 / 2 |
| bolt | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 2 / 2 |
| bolt | JOINT_CLASSIFICATION_low | low | 0.000000 | [0.000000, 0.000000] | 2 / 2 |
| bolt | STAGED_low | low | 0.000000 | [0.000000, 0.000000] | 2 / 2 |
| bolt | FIXED_CONTROL_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_high | high | -0.004961 | [-0.010559, 0.000303] | 0 / 0 |
| bolt | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_high | high | -0.004961 | [-0.010559, 0.000303] | 0 / 0 |
| bolt | FREE_ONLY_high | high | -0.004961 | [-0.010559, 0.000303] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_high | high | -0.009402 | [-0.023734, 0.002382] | 0 / 0 |
| bolt | STAGED_high | high | 0.001812 | [-0.000237, 0.004338] | 0 / 0 |
| timesfm | FIXED_CONTROL_low | low | -0.025337 | [-0.040377, -0.012107] | 0 / 0 |
| timesfm | FIXED_H32_low | low | -0.025337 | [-0.040377, -0.012107] | 0 / 0 |
| timesfm | FIXED_H_low | low | -0.025337 | [-0.040377, -0.012107] | 0 / 0 |
| timesfm | FIXED_REFERENCE_low | low | -0.025609 | [-0.051021, -0.000511] | 0 / 1 |
| timesfm | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_low | low | 0.002803 | [-0.004863, 0.008654] | 0 / 0 |
| timesfm | STAGED_low | low | -0.025337 | [-0.040377, -0.012107] | 0 / 0 |
| timesfm | FIXED_CONTROL_high | high | -0.007474 | [-0.013588, -0.002023] | 0 / 0 |
| timesfm | FIXED_H32_high | high | -0.022532 | [-0.041455, -0.004870] | 0 / 0 |
| timesfm | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | FIXED_REFERENCE_high | high | -0.022532 | [-0.041455, -0.004870] | 0 / 0 |
| timesfm | FREE_ONLY_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | STAGED_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |

## financial

状态：completed。

| 家族 | 对照 | 预算 | MASE 差 | 90% 描述区间 | JOINT 超支 / 对照超支 |
|---|---|---|---:|---|---:|
| bolt | FIXED_CONTROL_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | FIXED_H32_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | FIXED_H_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | FIXED_REFERENCE_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | JOINT_CLASSIFICATION_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | LEGACY_CART_H32_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | LEGACY_CART_H_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | LEGACY_CART_control_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | LEGACY_DIRECT_H32_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | LEGACY_DIRECT_H_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | LEGACY_DIRECT_control_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | R2_EXISTING_CART_low | low | -0.018425 | [-0.018425, -0.018425] | 10 / 12 |
| bolt | R3_FROZEN_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | R3_RETRAINED_STAGED_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | STAGED_low | low | 0.000000 | [0.000000, 0.000000] | 10 / 10 |
| bolt | TATO_NATIVE_8_low | low | -1.628972 | [-1.628972, -1.628972] | 10 / 1 |
| bolt | FIXED_CONTROL_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| bolt | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| bolt | FREE_ONLY_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| bolt | LEGACY_CART_H32_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| bolt | LEGACY_CART_H_high | high | -0.093047 | [-0.093047, -0.093047] | 0 / 0 |
| bolt | LEGACY_CART_control_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| bolt | LEGACY_DIRECT_H32_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| bolt | LEGACY_DIRECT_H_high | high | -0.041264 | [-0.041264, -0.041264] | 0 / 0 |
| bolt | LEGACY_DIRECT_control_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| bolt | R2_EXISTING_CART_high | high | -0.046164 | [-0.046164, -0.046164] | 0 / 10 |
| bolt | R3_FROZEN_high | high | -0.061555 | [-0.061555, -0.061555] | 0 / 0 |
| bolt | R3_RETRAINED_STAGED_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| bolt | STAGED_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | TATO_NATIVE_8_high | high | -1.656711 | [-1.656711, -1.656711] | 0 / 0 |
| bolt | TRAIN_BEST_FIXED_FLOW_high | high | -0.027739 | [-0.027739, -0.027739] | 0 / 0 |
| timesfm | FIXED_CONTROL_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | FIXED_H32_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | FIXED_H_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | FIXED_REFERENCE_low | low | -0.315809 | [-0.315809, -0.315809] | 2 / 8 |
| timesfm | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 2 / 2 |
| timesfm | JOINT_CLASSIFICATION_low | low | 0.000111 | [0.000111, 0.000111] | 2 / 0 |
| timesfm | LEGACY_CART_H32_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | LEGACY_CART_H_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | LEGACY_CART_control_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | LEGACY_DIRECT_H32_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | LEGACY_DIRECT_H_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | LEGACY_DIRECT_control_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | R2_EXISTING_CART_low | low | 0.006683 | [0.006683, 0.006683] | 2 / 12 |
| timesfm | R3_FROZEN_low | low | -0.315809 | [-0.315809, -0.315809] | 2 / 8 |
| timesfm | R3_RETRAINED_STAGED_low | low | 0.000111 | [0.000111, 0.000111] | 2 / 0 |
| timesfm | STAGED_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | TATO_NATIVE_8_low | low | -0.083325 | [-0.083325, -0.083325] | 2 / 12 |
| timesfm | TRAIN_BEST_FIXED_FLOW_low | low | -0.329175 | [-0.329175, -0.329175] | 2 / 4 |
| timesfm | FIXED_CONTROL_high | high | -0.186086 | [-0.186086, -0.186086] | 0 / 0 |
| timesfm | FIXED_H32_high | high | -0.322492 | [-0.322492, -0.322492] | 0 / 0 |
| timesfm | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | FIXED_REFERENCE_high | high | -0.322492 | [-0.322492, -0.322492] | 0 / 0 |
| timesfm | FREE_ONLY_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | LEGACY_CART_H32_high | high | -0.322492 | [-0.322492, -0.322492] | 0 / 0 |
| timesfm | LEGACY_CART_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | LEGACY_CART_control_high | high | -0.322492 | [-0.322492, -0.322492] | 0 / 0 |
| timesfm | LEGACY_DIRECT_H32_high | high | -0.322492 | [-0.322492, -0.322492] | 0 / 0 |
| timesfm | LEGACY_DIRECT_H_high | high | -0.145060 | [-0.145060, -0.145060] | 0 / 0 |
| timesfm | LEGACY_DIRECT_control_high | high | -0.322492 | [-0.322492, -0.322492] | 0 / 0 |
| timesfm | R2_EXISTING_CART_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 8 |
| timesfm | R3_FROZEN_high | high | -0.030395 | [-0.030395, -0.030395] | 0 / 0 |
| timesfm | R3_RETRAINED_STAGED_high | high | -0.006572 | [-0.006572, -0.006572] | 0 / 0 |
| timesfm | STAGED_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | TATO_NATIVE_8_high | high | -0.090008 | [-0.090008, -0.090008] | 0 / 0 |
| timesfm | TRAIN_BEST_FIXED_FLOW_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |

## generalization

状态：completed。

| 家族 | 对照 | 预算 | MASE 差 | 90% 描述区间 | JOINT 超支 / 对照超支 |
|---|---|---|---:|---|---:|
| bolt | FIXED_CONTROL_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | STAGED_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_CONTROL_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H32_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FIXED_REFERENCE_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | FREE_ONLY_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | JOINT_CLASSIFICATION_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| bolt | STAGED_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | FIXED_CONTROL_low | low | -0.035866 | [-0.078650, -0.010681] | 0 / 0 |
| timesfm | FIXED_H32_low | low | -0.035866 | [-0.078650, -0.010681] | 0 / 0 |
| timesfm | FIXED_H_low | low | -0.035866 | [-0.078650, -0.010681] | 0 / 0 |
| timesfm | FIXED_REFERENCE_low | low | -0.035866 | [-0.078650, -0.010681] | 0 / 0 |
| timesfm | FREE_ONLY_low | low | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_low | low | -0.000606 | [-0.000606, -0.000606] | 0 / 0 |
| timesfm | STAGED_low | low | -0.035866 | [-0.078650, -0.010681] | 0 / 0 |
| timesfm | FIXED_CONTROL_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | FIXED_H32_high | high | -0.035866 | [-0.078650, -0.010681] | 0 / 0 |
| timesfm | FIXED_H_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | FIXED_REFERENCE_high | high | -0.035866 | [-0.078650, -0.010681] | 0 / 0 |
| timesfm | FREE_ONLY_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | JOINT_CLASSIFICATION_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |
| timesfm | STAGED_high | high | 0.000000 | [0.000000, 0.000000] | 0 / 0 |

## Oracle 解释

TRAIN 诊断状态：`completed`。

合法独特动作按真实输入与预测 hash 合并，Native alias 记录理由与费用。动作预算 oracle 只在实际最终费用可行的动作内选；完整路径 oracle 只在已经冻结并实际评估的整条策略路径内选，包含工具与最终费用。它们使用 TRAIN 未来监督，因此绝不能部署或记为方法成绩。

分解在共同可行子集上进行，排除计数保留。策略库表示及证据误差、路径选择误差属于诊断上界，不能无额外对照直接归因成纯证据或纯主动获取因果贡献。完整覆盖表不删不可行窗口。
