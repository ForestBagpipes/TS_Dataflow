# v4.3.1 当日冲刺冻结计划

启动2026-09-14 23:28:17 Asia/Shanghai，截止2026-09-15 00:00:00，T=1903秒（31分43秒）。时间分配190/1047/381/285秒是调度预算，不是完成承诺。47GiB内存、45GiB可用，RTX4090当前单卡，无他人GPU计算；三环境已可用，不重装。

工作区a48dfe3干净，无已开始的v431，复用完整v43缓存。54 T_fit /21 T_gate /17 T_check /18 T_acq /26 dev parent，各parent六变体，全部三来源保留。以父范围704为边界，r416/320历史在原context内；calibration/test封存。

manifest: configs/v431/sprint_manifest.json；结果results/v431/20260914-sprint；日志logs/v431/20260914-sprint。8终态配置提前登记，最大深度/支持不因dev结果改变。T_gate先选两个gated配置再hash冻结，T_acq标签后生成。各配置T_check可并行。

文件归属：A agent只写v431/decision_tree.py、terminal.py及test_terminal.py，后补独立verifier；B agent只写scripts/v431_baselines/、third_party/TATO、baseline_audit；C agent只写v431/acquisition.py及test_acquisition.py。root维护data/history/拟合整合、配置、统一GPU队列、共同表和论文。公共v43入口保持原样，避免破坏运行中的hash。

GPU顺序：目标跨度历史候选与H32/H96/H192增量→TATO官方全原生搜索空间短预算适配→TimesFM资产可用后的第二家族核心表。CPU终态/获取器构建、baseline依赖和论文骨架并行，无H2显著性等待门。未完成的第二模型/baseline有明确pending，不记被击败。

冻结前dev只整表一次，不因单臂输出反复调参。支持不足原样记入gate；18个T_acq父组不能拆成两叶各16，允许根叶/全部STOP。预算按完整分支费用准入，费用差仅用于价值标签。

23:58:54全部已登记GPU批次及独立复核结束；共同开发矩阵50组合完成。训练模型/配置冻结，但因未胜强固定/CART且全部STOP，研究方法未满足独立确认条件。详见最终共同表。
