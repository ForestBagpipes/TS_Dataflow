# r5 当前任务试运行在线验收

状态：两家族真实prepare-only已通过，GPU运行结果待填；不能把本页计划当作已执行。

真实入口 `scripts/v431_r5_online.py --family bolt|timesfm --root results/v431-r5`。`--prepare-only`只加载冻结轻量模型、当前context与元数据，不启动GPU；常规模式由root唯一GPU队列持锁，子worker不再次持锁。

每家族提前选定44个case：3个合法TRAIN parent只测吞吐，旧7个DEV请求与12个金融请求各运行low/high预算，共38自然请求；另完整KEEP、零预算、真实候选执行后注入故障3个受控case。来源、H96和缺口条件按旧元数据选，不依据新损失选择。自然请求表示策略自然决策，不表示自然缺口。训练pilot及故障case采用固定查询次序，只作执行与吞吐检查，不能归入主动收益。

`features`从当前origin可见输入计算13维r4特征及已知历史协变量覆盖。覆盖只执行历史前缀准备和描述，不调用模型。未支持覆盖为NaN，后续固定训练填补参数由模型处理，不伪造实测历史预测。

`CurrentTrials.trial`真实生成查询的五臂之一：原生、FFILL、单变量/多变量TS-ICL或context ridge。每次验证有效观测不变。新版本按候选输入hash、H和实际模型identity在单请求内去重；两个不同动作如果输入相同，仍收取其实际物化成本，第二次预测直接复用。请求之间清空预测memo；TimesFM继承r4已验收的服务cache清理，不清模型权重。

收益评分器和先验只收到免费特征、已支付参考预测及已查询响应。`TrialResult`没有future、loss或未查询预测。Controller选择动作后直接保存其已执行预测，不再运行最终forecast，且记录原生dtype与缓存身份。

预算准入用冻结TRAIN成本 `action_estimate + .051秒`，其中.05为几何求解上限、.001为评分/账本预留，输出另留.001。实际热请求覆盖免费诊断、治理、模型、决策、几何与响应JSON保存；controller估计总耗时与真实外层墙钟分别保留，超时不从账本删除。模型startup与完整worker进程另计。预算连参考输出都不足时仍执行参考并标预算未满足，不提供填零输出。

所有在线最终数组保存前，审计hook拒绝打开future标签、离线预测账本及历史probe结果。最后才开启已用DEV/金融离线核验；TRAINpilot只核选中版本的预测一致性，不输出其表现用于方法筛选。完整结果保存 `decisions.json`、`live_arrays.npz`、每请求response、`train_timing.json`、服务原始请求响应、`visibility_barrier.json`、`process_accounting.json`。这些文件存在且status完成后才报告通过。

两家族prepare-only各44个case通过冻结模型、manifest、源码与免费字段顺序检查；各5个隐藏档案拒读，非预期读取0。只做CPU准备，进程分别0.906093秒（Bolt）、0.898671秒（TimesFM）。日志在 `results/v431-r5/preflight-{family}/`，未执行模型。

待真实记录：自然non-STOP数、低/高预算分位数/最大值与超支、首次惰性开销、故障回退、同动作缓存一致性、金融条件表。当前没有新GPU运行数字。
