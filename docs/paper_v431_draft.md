# IntroAct-TS: A Task-Aware Data Governance Agent for Frozen Time Series Foundation Models

中文：面向冻结时间序列基础模型的任务感知数据治理智能体

v4.3.1-r4开发论文草稿。金融为重点应用，现有证据不支持金融领域有效性或SOTA。原r3论证及负结果保存在[旧稿](paper_v431_draft_r3_archived.md)。

## 背景与问题

冻结TSFM的输入可能存在观测覆盖缺口。治理改变模型可见信息，但修复误差下降不必然改善当前预测。真实跳变可以正确，完整有效输入允许KEEP。研究问题是在未来结果不可见且验证预算有限时，如何选择合法输入治理动作与必要的历史验证步骤。备份只提供恢复能力，不是方法创新。本工作不训练TSFM参数，不改变原目标变量或转向交易收益。

## 定义

请求包含当前可见512点输入及mask、合法协变量、H96/H192、固定模型revision和剩余预算。动作集为Native KEEP、FFILL、单变量TS-ICL、多变量TS-ICL、context ridge，有效观测不覆盖。工具H32、H、control按各历史origin先截断再生成候选，未得到的工具结果不是可见特征。训练监督为真实当前未来MAE除以当前origin可见尺度；部署状态不携带未来。报告使用另行冻结的外层TRAIN MASE尺度。路径费用包含取证、治理、最终预测、失败与决策，冷启动分开记录。

## 可运行方法

用source、parent、variant逐层配权的TRAIN最终任务损失和完整费用联合选择有限策略。语法最多一次免费特征二分，每支直接提交或调用一个预登记工具组合，取证后最多一次已得证据二分。每个可执行学习终叶至少16有效fit parent，阈值只来自fit分位点。gate只选免费二分与原lambda；平局低成本、少节点、固定参照。运行时decide只接受typed可见状态、实际证据和剩余预算，完整targetKEEP；预算不足、工具不支持/失败均明确回退。

该实现采用通用成本敏感有限策略搜索，不把通用联合树重命名为独有创新。原r3的κ/z响应作为负结果对照保留，不进入主候选。本文目前是有数据/费用审计的系统及经验性研究候选，尚非已证独有算法贡献。

## 实验与结果

同26个反复使用的DEV parent、156个相关变体，两家族独立TRAIN拟合，未宣称零样本迁移。外层MASE不变；变体不能当独立样本。高预算3.5秒，完整低预算表和条件/来源结果见[共同表](v431_r4_main_table.md)。成本为常驻组件实测归因，在线总墙钟另验。R2部分旧mask/history工具无法完全分离冷启动，保留保守原费，不称严格hot-only。

| 家族 | 方法 | MASE ↓ | 常驻组件秒/窗 | 工具/窗 | parent/变体 | 超预算 |
|---|---|---:|---:|---:|---:|---:|
| bolt | FIXED_A0_FFILL_high | 1.430629 | 0.090133 | 0.000 | 26/156 | 0 |
| bolt | FIXED_A0_NATIVE_high | 1.258454 | 0.089821 | 0.000 | 26/156 | 0 |
| bolt | FIXED_A2_SINGLE_high | 1.157005 | 0.116324 | 0.000 | 26/156 | 0 |
| bolt | FIXED_A3_COV_high | 1.313983 | 0.120132 | 0.000 | 26/156 | 0 |
| bolt | FIXED_A4_RIDGE_CONTEXT_high | 1.214538 | 0.092854 | 0.000 | 26/156 | 0 |
| bolt | FIXED_CONTROL_high | 1.154124 | 0.277194 | 0.444 | 26/156 | 0 |
| bolt | FIXED_H32_high | 1.157005 | 0.116444 | 0.000 | 26/156 | 0 |
| bolt | FIXED_H_high | 1.154124 | 0.196143 | 0.222 | 26/156 | 0 |
| bolt | FIXED_REFERENCE_high | 1.157005 | 0.116324 | 0.000 | 26/156 | 0 |
| bolt | FREE_ONLY_high | 1.157005 | 0.116397 | 0.000 | 26/156 | 0 |
| bolt | JOINT_CLASSIFICATION_high | 1.174113 | 0.276022 | 0.444 | 26/156 | 0 |
| bolt | JOINT_high | 1.154124 | 0.196145 | 0.222 | 26/156 | 0 |
| bolt | LEGACY_CART_H32_high | 1.157005 | 0.116334 | 0.000 | 26/156 | 0 |
| bolt | LEGACY_CART_H_high | 1.168004 | 0.195538 | 0.222 | 26/156 | 0 |
| bolt | LEGACY_CART_control_high | 1.157005 | 0.279688 | 0.444 | 26/156 | 0 |
| bolt | LEGACY_DIRECT_H32_high | 1.157005 | 0.116333 | 0.000 | 26/156 | 0 |
| bolt | LEGACY_DIRECT_H_high | 1.157762 | 0.196222 | 0.222 | 26/156 | 0 |
| bolt | LEGACY_DIRECT_control_high | 1.146635 | 0.279529 | 0.444 | 26/156 | 0 |
| bolt | LEGACY_RESIDUAL_H32_high | 1.157005 | 0.116333 | 0.000 | 26/156 | 0 |
| bolt | LEGACY_RESIDUAL_H_high | 1.154554 | 0.198154 | 0.222 | 26/156 | 0 |
| bolt | LEGACY_RESIDUAL_control_high | 1.154158 | 0.279407 | 0.444 | 26/156 | 0 |
| bolt | R2_EXISTING_CART_high | 1.136486 | 0.655479 | 2.000 | 26/156 | 0 |
| bolt | R3_FROZEN_high | 1.156351 | 0.281227 | 0.444 | 26/156 | 0 |
| bolt | R3_RETRAINED_STAGED_high | 1.157005 | 0.116833 | 0.000 | 26/156 | 0 |
| bolt | STAGED_high | 1.150787 | 0.168910 | 0.144 | 26/156 | 0 |
| bolt | TATO_NATIVE_8_high | 1.685227 | 0.676848 | 8.000 | 26/156 | 0 |
| bolt | TRAIN_BEST_FIXED_FLOW_high | 1.154554 | 0.198152 | 0.222 | 26/156 | 0 |
| timesfm | FIXED_A0_FFILL_high | 1.181309 | 0.196340 | 0.000 | 26/156 | 0 |
| timesfm | FIXED_A0_NATIVE_high | 1.139837 | 0.196681 | 0.000 | 26/156 | 0 |
| timesfm | FIXED_A2_SINGLE_high | 1.096135 | 0.222397 | 0.000 | 26/156 | 0 |
| timesfm | FIXED_A3_COV_high | 1.136583 | 0.226188 | 0.000 | 26/156 | 0 |
| timesfm | FIXED_A4_RIDGE_CONTEXT_high | 1.090970 | 0.199827 | 0.000 | 26/156 | 0 |
| timesfm | FIXED_CONTROL_high | 1.086830 | 0.581292 | 0.444 | 26/156 | 0 |
| timesfm | FIXED_H32_high | 1.096135 | 0.222518 | 0.000 | 26/156 | 0 |
| timesfm | FIXED_H_high | 1.069398 | 0.580258 | 0.444 | 26/156 | 0 |
| timesfm | FIXED_REFERENCE_high | 1.096135 | 0.222397 | 0.000 | 26/156 | 0 |
| timesfm | FREE_ONLY_high | 1.069398 | 0.218154 | 0.000 | 26/156 | 0 |
| timesfm | JOINT_CLASSIFICATION_high | 1.069398 | 0.580257 | 0.444 | 26/156 | 0 |
| timesfm | JOINT_high | 1.069398 | 0.580257 | 0.444 | 26/156 | 0 |
| timesfm | LEGACY_CART_H32_high | 1.096135 | 0.222406 | 0.000 | 26/156 | 0 |
| timesfm | LEGACY_CART_H_high | 1.069398 | 0.580216 | 0.444 | 26/156 | 0 |
| timesfm | LEGACY_CART_control_high | 1.096135 | 0.583435 | 0.444 | 26/156 | 0 |
| timesfm | LEGACY_DIRECT_H32_high | 1.096135 | 0.222406 | 0.000 | 26/156 | 0 |
| timesfm | LEGACY_DIRECT_H_high | 1.072409 | 0.580112 | 0.444 | 26/156 | 0 |
| timesfm | LEGACY_DIRECT_control_high | 1.095305 | 0.582770 | 0.444 | 26/156 | 0 |
| timesfm | LEGACY_RESIDUAL_H32_high | 1.096135 | 0.222406 | 0.000 | 26/156 | 0 |
| timesfm | LEGACY_RESIDUAL_H_high | 1.079364 | 0.583565 | 0.444 | 26/156 | 0 |
| timesfm | LEGACY_RESIDUAL_control_high | 1.095664 | 0.582944 | 0.444 | 26/156 | 0 |
| timesfm | R2_EXISTING_CART_high | 1.069086 | 1.066250 | 2.000 | 26/156 | 0 |
| timesfm | R3_FROZEN_high | 1.102669 | 0.593774 | 0.444 | 26/156 | 0 |
| timesfm | R3_RETRAINED_STAGED_high | 1.090970 | 0.200598 | 0.000 | 26/156 | 0 |
| timesfm | STAGED_high | 1.069398 | 0.580267 | 0.444 | 26/156 | 0 |
| timesfm | TATO_NATIVE_8_high | 1.529002 | 0.999094 | 8.000 | 26/156 | 0 |
| timesfm | TRAIN_BEST_FIXED_FLOW_high | 1.069398 | 0.580168 | 0.444 | 26/156 | 0 |

联合策略未胜强简单方法：Bolt弱于分阶段同语法对照；TimesFM与仅免费特征同预测、但取证费用更高。两家族相对参照的描述性区间均跨零。r4与固定H同效，不支持选择性取证增量。不能把旧R2不同证据的CART当作同信息消融，也不能把未充分支持的旧获取器作为唯一强对照。

金融附表仅2个parent：Bolt JOINT3.041944弱于KEEP2.820959；TimesFM JOINT4.890237与免费策略同效。旧TimesFM H32/H相同预测但不同费用，由原始加载归因解释；修正费用分类不提供预测收益。自然缺口和历史vintage核实缺项，完整输入no-op不算预测改善。

## 相关工作与必要证据

TATO输入变换搜索、Task-oriented Imputation下游任务导向、CSDI条件插补、DIME/TNDP效用与成本敏感获取、ImputePilot以及嵌套上下文研究均需明确归因，见[创新矩阵](novelty_matrix.md)。普通cost-sensitive策略是必要对照，与本实现相同则合并。主动机制必须超过固定流程，响应测量必须超过通用分歧与等成本回测；目前这两项均未获支持。TATO只有两家族短预算适配，不是官方完整复现，不据此宣称SOTA。

## 限制与后续检验

单一USTS parent、反复DEV、小金融支持、相关变体、部分自然缺失原因未知及成本跨域尾部限制结论。TRAIN oracle仅诊断，不是在线策略分数；真实自然取证也只说明执行了分支。校准与test保持封存。按预登记停止扩展本轮算法，优先补齐强基线和独立评估协议；本稿不保证ICLR录用，不将工程正确性当方法成功。

## 真实在线验收与最终交付

下列自然请求指冻结策略自行决定是否取证，不表示已核实自然缺口。每家族主表7个预选请求、金融12个请求，另3个受控案例。两家族按GPU队列串行，模型常驻；TimesFM清除跨请求预测缓存，保留请求内canonical去重。

| 家族 | 自然请求 | 实际原子probe | STOP | 热请求均秒 | 最大秒 | 热超预算 | 模型启动秒 | 完整进程秒 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bolt | 19 | 10 | 9 | 0.437593 | 3.688580 | 1 | 22.357758 | 37.006293 |
| timesfm | 19 | 14 | 5 | 0.717568 | 1.569336 | 0 | 9.522779 | 29.499199 |

首次在线因父队列与子服务重复持有同一GPU锁，在加载前失败。保留原日志和源码，后续仅外层改独立队列锁，原GPU服务锁不改；同时准入和取证后的剩余预算扣除全部已发生墙钟时间。重试新目录online-bolt-r1/online-timesfm-r1均完成。

Bolt首次自然历史H探针约3.557446秒，最终请求3.688580秒，超出3.5秒；完整记录回退和总预算未满足，不删除首调用尾部。金融12请求每家族实际high均0超支，不能据此把旧low金融超支或未知自然缺口验证改成通过。两家族均覆盖受控完整KEEP、预算不足、实际probe后注入失败回退；受控结果不当作策略收益。

全部44个最终预测与各自所选动作对应缓存通过预登记数值容忍复核，不能说hash逐位一致：Bolt候选15/22、预测22/22逐位一致；TimesFM候选12/22、预测0/22逐位一致。TF仅保存dtype不同（在线float64、旧缓存float32），44个预测相对各自所选动作缓存的数值最大绝对差均为0；候选最大差约2.35e-13。模型身份、读取barrier与费用审计详见[v431_r4_online_verification.md](v431_r4_online_verification.md)。19个自然动作与离线JOINT_high一致数为Bolt18/19、TimesFM19/19；Bolt首次超时使原ridge改为预算回退A2，这是实际延迟触发的合法分支，不将其单窗收益当方法成绩，也不说自然部署动作全部等同账本主表。所有final落盘前禁止读取评价标签/隐藏证据，六类封存文件探测被拒绝、无意外访问；calibration/test未读。

[完整费用分类](v431_r4_cost_summary.md)保留各原始SHA：本轮联合CPU搜索进程50.929471秒、legacy终态5.213832秒、获取监督拟合3.046058秒；历史r3探针6job完整进程1574.471400秒仍保留，不因本轮复用清零。这不是穷尽全部历史研发费用。模型加载、历史离线推断、TRAIN搜索、部署治理及最终预测分别保留。完整进程包含受控测试与启动/退出，不把其摊销值冒充热请求。probe数不是TSFM forward数，实际原始调用见service响应与验收。

精简审阅包发布到artifacts/reviews/v431-r4-review.tar.gz，包含源代码、配置、角色/支持、原始配对预测样例、失败/成本及自然轨迹；身份见同目录JSON。它绑定代码提交，随后发布包的提交不改变该代码身份。经检查以codex-save-local推送当前codex分支；Windows同步以实际登录与本机快进状态为准，服务器不能宣称已观察到F盘落盘。
