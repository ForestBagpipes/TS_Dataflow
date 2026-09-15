# IntroAct-TS: A Task-Consistent Data Governance Agent for Time Series Foundation Models

中文：面向时间序列基础模型的任务一致数据治理智能体

v4.3.1-r5开发论文草稿；研究未晋升，以下结果仅已反复使用DEV。金融为重点应用，不具备金融泛化证据。r4原稿保留归档。

## 问题与方法

在有效观测不覆盖、未来不可见、模型冻结的条件下，为不完整输入选择可执行版本及值得运行的候选。五臂保持Native、FFILL、单变量/多变量TS-ICL、context ridge；完整输入直接KEEP。免费参考先执行当前L512、H96/H192任务，轻量收益评分器读取已付费预测响应，联合几何约束评分，预算控制器最多运行三个版本，最终直接提交其中一个原生预测。没有融合输出、预测后修正或骨干训练。

参考策略采用fit内parent隔离向前交叉拟合，监督为真实未来MAE差除以origin合法S，未来标签只在TRAIN监督/独立离线评估出现。部署未知评分mask时使用全部lead折点共同凸包，不偷读未来非空位置。求解器记录FW gap与时间限制，失败保留上一次有效决策并支付费用。

对真实同任务收益向量g，精确欧氏投影保证整体向量平方误差不增；近似解有2gap余项。该性质不保证逐坐标改善、排序或最终MASE改善。当前实验恰好显示评分误差下降仍可能选择更差动作。

## 实验

| 家族 | 方法 | MASE ↓ | 账本秒/窗 | 超预算 |
| --- | --- | --- | --- | --- |
| bolt | FIXED_A0_NATIVE_high | 1.258454 | 0.089821 | 0 |
| bolt | FIXED_A2_SINGLE_high | 1.157005 | 0.116324 | 0 |
| bolt | FIXED_COUNT_2_high | 1.181290 | 0.183072 | 0 |
| bolt | FIXED_ORDER_3_high | 1.226845 | 0.253486 | 0 |
| bolt | LEGACY_CART_H_high | 1.168004 | 0.195538 | 0 |
| bolt | LEGACY_DIRECT_control_high | 1.146635 | 0.279529 | 0 |
| bolt | R2_EXISTING_CART_high | 1.136486 | 0.655479 | 0 |
| bolt | R4_FREE_COVERAGE_high | 1.152415 | 0.113136 | 0 |
| bolt | R4_JOINT_high | 1.154124 | 0.196145 | 0 |
| bolt | R5_RAW_high | 1.152415 | 0.114238 | 0 |
| bolt | R5_SINGLE_high | 1.152415 | 0.114236 | 0 |
| bolt | R5_high | 1.152415 | 0.114237 | 0 |
| bolt | TATO_NATIVE_8_high | 1.685227 | 0.676848 | 0 |
| bolt | TRAIN_BEST_FIXED_FLOW_high | 1.154554 | 0.198152 | 0 |
| timesfm | FIXED_A0_NATIVE_high | 1.139837 | 0.196681 | 0 |
| timesfm | FIXED_A2_SINGLE_high | 1.096135 | 0.222397 | 0 |
| timesfm | FIXED_COUNT_2_high | 1.083706 | 0.373463 | 0 |
| timesfm | FIXED_ORDER_3_high | 1.085207 | 0.535471 | 0 |
| timesfm | LEGACY_CART_H_high | 1.069398 | 0.580216 | 0 |
| timesfm | LEGACY_DIRECT_control_high | 1.095305 | 0.582770 | 0 |
| timesfm | R2_EXISTING_CART_high | 1.069086 | 1.066250 | 0 |
| timesfm | R4_FREE_COVERAGE_high | 1.069398 | 0.219311 | 0 |
| timesfm | R4_JOINT_high | 1.069398 | 0.580257 | 0 |
| timesfm | R5_RAW_high | 1.072391 | 0.374219 | 0 |
| timesfm | R5_SINGLE_high | 1.074180 | 0.386583 | 0 |
| timesfm | R5_high | 1.074244 | 0.386979 | 0 |
| timesfm | TATO_NATIVE_8_high | 1.529002 | 0.999094 | 0 |
| timesfm | TRAIN_BEST_FIXED_FLOW_high | 1.069398 | 0.580168 | 0 |

固定同查询机制：

| 家族 | 方法 | MASE ↓ | 账本秒/窗 | 超预算 |
| --- | --- | --- | --- | --- |
| bolt | MECH_CURRENT_FULL | 1.226845 | 0.253519 | 0 |
| bolt | MECH_CURRENT_PAIR | 1.228042 | 0.251720 | 0 |
| bolt | MECH_CURRENT_RAW | 1.228042 | 0.251026 | 0 |
| bolt | MECH_CURRENT_SINGLE | 1.228042 | 0.251056 | 0 |
| bolt | MECH_FREE_RAW | 1.412477 | 0.251027 | 0 |
| bolt | MECH_HISTORY_RAW | 1.179009 | 0.442365 | 0 |
| timesfm | MECH_CURRENT_FULL | 1.085207 | 0.535496 | 0 |
| timesfm | MECH_CURRENT_PAIR | 1.089609 | 0.526898 | 0 |
| timesfm | MECH_CURRENT_RAW | 1.084789 | 0.526191 | 0 |
| timesfm | MECH_CURRENT_SINGLE | 1.089609 | 0.526222 | 0 |
| timesfm | MECH_FREE_RAW | 1.077708 | 0.526193 | 0 |
| timesfm | MECH_HISTORY_RAW | 1.088962 | 0.888182 | 0 |

旧DEV26parent/156变体，不能当156个独立样本。R2信息不同；TATO8trial不等完整复现。主候选TimesFM弱于冻结TRAIN强简单流程；Bolt等免费参考。联合约束和主动调用贡献均未成立，主实验准入失败。金融仅2parent，Bolt KEEP比治理强；自然缺口缺项。确认集封存。

## 与已有研究的关系及局限

TATO、Task-oriented Time Series Imputation和TS-ICL已研究任务导向输入治理；Forecast with Forecasts等已使用预测输出信息；DIME、Amortized Bayesian Experimental Design for Decision-Making、Loss-Conditioned State Execution涉及决策证据与计算选择。凸投影、损失向量几何及Frank-Wolfe不是本文发明。文献逐项来源与边界见v431_r5_literature.md和novelty_matrix.md。

本轮新测量/约束的可实现性已验证，独有预测增量待验证且当前DEV不支持。不能将工程正确性、oracle空间、自然调用或评分误差性质包装为SOTA。不宣称零样本跨家族迁移、金融point-in-time或TSFM适配训练收益。
