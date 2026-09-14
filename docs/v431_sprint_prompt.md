# v4.3.1 当日并行冲刺执行提示词（2026-09-14）

本文件记录本轮用户独立执行指令的完整实施约束，取代上一轮“H2通过后才启动下一项”的调度顺序；旧隔离、真实依赖和结果审计继续有效。

主题：IntroAct-TS: Evidence-Seeking Data Governance for Time Series Foundation Models。目标是同数据、信息、监督和预算下的真实治理收益与可展示完整系统，ICLR2027 oral是研究目标，不是已取得结果。保持PICS_joint_relabel历史incumbent，TS-ICL是新任务强参照；不改为纯插补/预测模型选择或合成项目。

三线并行：A CPU缓存拟合终态及简单对照；B 单GPU补历史证据、TATO与独立第二TSFM；C 完整agent/STOP/回放/共同表/论文。明确文件归属，root独占GPU队列。终态hash冻结后才能生成对应工具值标签；其余准备并行，H2/H3失败也交付整版。

时间：默认Asia/Shanghai，记录启动、当日截止及剩余T；按10%核对/55%并行构建/20%验证/15%交付安排，不保证未知运行时间，不自动关机。全部计算在本服务器，复用三个隔离环境，每进程1 BLAS线程，单重GPU；内存足够时最多2个轻量CPU作业。按完整模型/输入身份复用缓存，成本保留。

五臂固定KEEP/FFILL/TSICL-single/TSICL-cov/context-ridge，不再扩eta/插补器/大型critic。candidate类型已知不代表输出已得，依赖值的特征须生成计费。链路必须包含dirty诊断、目录、基础决策、按需合法证据、更新、STOP/提交、最终TSFM、血缘和成本。

终态树：叶选择argmin sum(w L)，split优化J(parent)-J(left)-J(right)，不是只学oracle分类。source宏权重和parent聚合保持；同parent变体不扩权。depth1/2基础、最多加1层证据，总depth<=3/leaves<=8；每fit叶>=16独立parent，连续feature<=16训练分位切点，平局TSICL。base只看dirty/mask/asofcov/频率/horizon，不看source名称/路径/真实污染类/未来/未获取结果。证据子树默认维持父策略；fit提案、独立gate审核；>=8gate parent且经验90%parent-bootstrap收益下界>0才保留。保留不剪枝消融，非安全证书。终态新配置<=8提前manifest；普通CART、平面成本敏感树、旧HGB对照保留。

历史：L512/extra0/H96,H192。exclusive r=L-H，输入X[:r]、验证dirty X[r:r+H]；对应416/320输入。登记旧H32、同r用H32、同r用目标H三个条件。后两者共享输入候选但费用分别列，只有一个目标跨度原点。每origin重新治理asof前缀，不截当前已治理序列、不读context之前、不用clean，协变量/尺度/发布延迟严格asof。不支持变长则unsupported，不改跨度/填未来。Solar只作诊断，不按source禁工具。

train隔离：沿用合法v431，否则源内同步原始时间50/20/15/15拆T_fit/T_gate/T_check/T_acq，完整读取范围不跨段、parent相关变体同组。fit树、gate剪枝和小配置选择、check完整冻结、acq生成工具标签。支持不足可预声明purged嵌套交叉拟合，不偷降门槛。dev统一整矩阵评价，不逐臂调参。calibration/test封存。终态更新使旧获取标签失效。

获取：冻结同一pi上v=L(pi(s))-L(pi(s+e))-lambda DeltaC；DeltaC为获取与STOP完整部署费用差，含最终治理和预测变化、共享去重；准入检查获取分支总费用而非差。零负标签保留，无oracle，预特征不含e。lambda仅0和0.1*train任务差中位绝对值/正工具成本中位数，退化只0；仅T_acq分组选择。首轮最多1工具，depth2回归每叶>=16parent；值>0、适用、预算准入才调用，其他STOP。最多两个预选终态训练获取器。全STOP可运行但主动贡献未成立。

共同表登记：nativeKEEP；固定五臂；旧简单/旧获取；dirty loss tree；同证据CART和平面loss tree；可拒绝细化；固定单工具/简单条件/同预算random；新完整单步agent；全调用；官方TATO适配。主表比完整原生，模块表控制同池同信息。TATO保持官方动作空间，不限五臂，统一外部原始时间、future、checkpoint、标签权限和预算。立即适配验收，不等H2；具体依赖阻塞保留，未运行不能当击败；短预算明确非完整官方复现。

独立第二家族优先已缓存验收TimesFM；ChronosBolt/Chronos2不是两个家族。先冻结候选、固定强方法和TATO核心表；按数据可用性提前登记子集，不能按成绩删来源，增加独立parent优先seed。共同来源保持原定全部可用，跨模型子集注明。分别报告训练搜索、离线证据、部署治理、最终预测、批量/冷/热延迟；缓存省重算不抹训练费。

评价：同origin、权重、finite评分mask，source宏MASE、source/horizon/条件配对差、parent数、切换收益/错切损失、调用数和总费用。故障不填零/不删窗。新集合不能直接比旧1.157005，必须重算共同对照。只有预登记选择成立、完整方法/比较臂/revision/数据/预算/统计冻结并数据契约通过才进入独立calibration，随后一次test；确认不反调开发。baseline或跨域不全交真实开发表及缺项。

论文立即建立：背景备份不等于当前治理选择、定义可观测/工具/动作/预算/损失、算法、已有SPO Trees/SPIBB/DIME借鉴与增量、共同表/消融/失败/成本/条件。贡献对应实测，无结果标待验证，gating相当不称独有、主动无优势保留失败，不把推理治理说成TSFM适配或文本LLM训练收益。

至少更新prompt/plan/report/paper草稿/HANDOFF/ledger/claims/矩阵。保存原始结果、旧RED/失效在线、冻结配置，正常codex分支commit/push不force、不覆盖他人。不机械重跑58旧测试，仅触及的新隐藏证据/asof/source权重/parent/cache/低预算回归。截止交完整可运行系统、共同表、机制对照、冻结状态、论文与逐窗代码证据；未完成和在途如实列出。
