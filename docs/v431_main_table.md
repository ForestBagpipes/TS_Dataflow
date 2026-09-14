# v4.3.1 共同开发主表（全部已完成比较臂）

同26个dev parent/156变体；MASE为source×horizon×condition等权宏平均。秒数为批量测量/重计部署组件；完整冷启动与热请求单独列在冲刺报告。TATO为8trial适配，预算仅事后审计。

| Backbone / 策略 | MASE ↓ | 治理+最终预测秒数 | 工具均次 | parent |
|---|---:|---:|---:|---:|
| chronos-bolt-base / AGENT_d2_old32_gated_high | 1.200158 | 0.1122 | 0.00 | 26 |
| chronos-bolt-base / AGENT_d2_old32_gated_low | 1.200158 | 0.1122 | 0.00 | 26 |
| chronos-bolt-base / AGENT_d2_target_horizon_gated_high | 1.200158 | 0.1122 | 0.00 | 26 |
| chronos-bolt-base / AGENT_d2_target_horizon_gated_low | 1.200158 | 0.1122 | 0.00 | 26 |
| chronos-bolt-base / ALL_d1_old32_gated | 1.163685 | 0.5849 | 2.00 | 26 |
| chronos-bolt-base / ALL_d1_same_origin32_gated | 1.163685 | 0.4902 | 2.00 | 26 |
| chronos-bolt-base / ALL_d1_target_horizon_gated | 1.157283 | 0.6620 | 2.00 | 26 |
| chronos-bolt-base / ALL_d1_target_horizon_unpruned | 1.163335 | 0.6591 | 2.00 | 26 |
| chronos-bolt-base / ALL_d2_old32_gated | 1.191788 | 0.5914 | 2.00 | 26 |
| chronos-bolt-base / ALL_d2_same_origin32_gated | 1.191788 | 0.4967 | 2.00 | 26 |
| chronos-bolt-base / ALL_d2_target_horizon_gated | 1.191788 | 0.6637 | 2.00 | 26 |
| chronos-bolt-base / ALL_d2_target_horizon_unpruned | 1.184872 | 0.6569 | 2.00 | 26 |
| chronos-bolt-base / CART_old32 | 1.136486 | 0.5858 | 2.00 | 26 |
| chronos-bolt-base / CART_same_origin32 | 1.136486 | 0.4911 | 2.00 | 26 |
| chronos-bolt-base / CART_target_horizon | 1.136486 | 0.6580 | 2.00 | 26 |
| chronos-bolt-base / DIRTY_LOSS_TREE_D1 | 1.163685 | 0.1066 | 0.00 | 26 |
| chronos-bolt-base / DIRTY_LOSS_TREE_D2 | 1.200158 | 0.1117 | 0.00 | 26 |
| chronos-bolt-base / FIXED_A0_FFILL | 1.430629 | 0.0902 | 0.00 | 26 |
| chronos-bolt-base / FIXED_A0_NATIVE | 1.258454 | 0.0899 | 0.00 | 26 |
| chronos-bolt-base / FIXED_A2_SINGLE | 1.157005 | 0.1201 | 0.00 | 26 |
| chronos-bolt-base / FIXED_A3_COV | 1.313983 | 0.1242 | 0.00 | 26 |
| chronos-bolt-base / FIXED_A4_RIDGE_CONTEXT | 1.214538 | 0.0929 | 0.00 | 26 |
| chronos-bolt-base / FIXED_HISTORY_d2_old32_gated_high | 1.200158 | 0.4200 | 1.00 | 26 |
| chronos-bolt-base / FIXED_HISTORY_d2_old32_gated_low | 1.200158 | 0.4201 | 1.00 | 26 |
| chronos-bolt-base / FIXED_HISTORY_d2_target_horizon_gated_high | 1.200158 | 0.4922 | 1.00 | 26 |
| chronos-bolt-base / FIXED_HISTORY_d2_target_horizon_gated_low | 1.200158 | 0.4923 | 1.00 | 26 |
| chronos-bolt-base / FIXED_MASK_d2_old32_gated_high | 1.191788 | 0.2849 | 0.67 | 26 |
| chronos-bolt-base / FIXED_MASK_d2_old32_gated_low | 1.191788 | 0.2849 | 0.67 | 26 |
| chronos-bolt-base / FIXED_MASK_d2_target_horizon_gated_high | 1.191788 | 0.2849 | 0.67 | 26 |
| chronos-bolt-base / FIXED_MASK_d2_target_horizon_gated_low | 1.191788 | 0.2849 | 0.67 | 26 |
| chronos-bolt-base / FLAT_LOSS_TREE_old32 | 1.187960 | 0.5866 | 2.00 | 26 |
| chronos-bolt-base / FLAT_LOSS_TREE_same_origin32 | 1.165232 | 0.4956 | 2.00 | 26 |
| chronos-bolt-base / FLAT_LOSS_TREE_target_horizon | 1.165232 | 0.6625 | 2.00 | 26 |
| chronos-bolt-base / OLD_DIRTY_HGB | 1.165414 | 0.1592 | 0.00 | 26 |
| chronos-bolt-base / OLD_LEARNED_HGB_COMMON_BUDGET | 1.190112 | 0.4766 | 1.38 | 26 |
| chronos-bolt-base / RANDOM_d2_old32_gated_high | 1.196996 | 0.2866 | 0.60 | 26 |
| chronos-bolt-base / RANDOM_d2_old32_gated_low | 1.196996 | 0.2866 | 0.60 | 26 |
| chronos-bolt-base / RANDOM_d2_target_horizon_gated_high | 1.196996 | 0.3176 | 0.60 | 26 |
| chronos-bolt-base / RANDOM_d2_target_horizon_gated_low | 1.196996 | 0.3176 | 0.60 | 26 |
| chronos-bolt-base / VISIBLE_CONDITION_d2_old32_gated_high | 1.200158 | 0.2516 | 0.33 | 26 |
| chronos-bolt-base / VISIBLE_CONDITION_d2_old32_gated_low | 1.200158 | 0.2516 | 0.33 | 26 |
| chronos-bolt-base / VISIBLE_CONDITION_d2_target_horizon_gated_high | 1.200158 | 0.2844 | 0.33 | 26 |
| chronos-bolt-base / VISIBLE_CONDITION_d2_target_horizon_gated_low | 1.200158 | 0.2844 | 0.33 | 26 |
| chronos-bolt-base / TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR | 1.685227 | 0.7032 | 8.00 | 26 |
| timesfm-2.5-200m-pytorch / TIMESFM_FIXED_A0_FFILL | 1.181309 | 0.2002 | 0.00 | 26 |
| timesfm-2.5-200m-pytorch / TIMESFM_FIXED_A0_NATIVE | 1.139837 | 0.2007 | 0.00 | 26 |
| timesfm-2.5-200m-pytorch / TIMESFM_FIXED_A2_SINGLE | 1.096135 | 0.2300 | 0.00 | 26 |
| timesfm-2.5-200m-pytorch / TIMESFM_FIXED_A3_COV | 1.136583 | 0.2341 | 0.00 | 26 |
| timesfm-2.5-200m-pytorch / TIMESFM_FIXED_A4_RIDGE_CONTEXT | 1.090970 | 0.2037 | 0.00 | 26 |
| timesfm-2.5-200m-pytorch / TIMESFM_TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR | 1.529002 | 1.0240 | 8.00 | 26 |

未完成项：[]
