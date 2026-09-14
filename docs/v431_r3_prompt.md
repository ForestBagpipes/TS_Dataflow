# v4.3.1-r3 用户执行要求（2026-09-15）

从6f0542b及最新工作区接续，保留r2，不重装、不覆盖他人修改，完成代码、服务器实验、论文及Git交付。calibration/test封存，PICS_joint_relabel历史incumbent不变。主题是固定TSFM的金融覆盖缺口治理，不是交易、合成、重新训练、预测器路由或备份创新。完整正确观测与真实跳变保留，五臂/两个模型家族/目标/L512/H96/H192/MASE不变。

## 审计和支持

先读AGENTS、HANDOFF、台账、最新共同表/sprint_report/paper与git修改。沿CLI核候选、历史、终态、获取、STOP、预测与成本。逐窗比较agent、自身基础强制STOP、固定TSICL；STOP不自动代表TSICL。查无证据全模型、隐藏特征填零、cache偷看、旧终态标签。26是DEV parent不是train；核pilot/max_origins/per_source与过滤，补合法遗漏，更多probe/扰动不增parent。复用v35_acv_probe/common、probe.py多长度、v36_pair_dataset动作对、v41_mask_counteract缺口描述。v40旧gain为clean重建NMSE不能改名为部署任务收益。核旧ACV先治理再截的顺序，最新历史必须先截再独立生成，不能未经核查断言最新泄漏。

## 模块一：有符号响应

保留普通Hq32和HqH历史，r=t-Hq、target末端不晚于t，无额外历史。L512时H96/H192历史输入最大416/320，不声称仅匹配H就完全匹配部署。同一起点、同H/标签/mask/checkpoint/尺度分别用Lq、Lq-64，同终点上下文。64固定，无网格。

当前缺口按距预测起点位置复制进历史。公共后缀同一缺口必须完整保留；短输入放不下则unsupported，不移动/裁掉。长短各自截断、拟合处理、生成候选和预测，禁止裁短已修序列；as-of协变量/归一化不读origin之后。历史评分只当前dirty中可见标签，不用被隐藏clean。覆盖规则预登记。

每家族train冻结固定参照b，共同当前任务既定正MASE尺度S_t（不依赖动作/未来）：

d_long(a)=[MAE_q(b,long)-MAE_q(a,long)]/S_t

d_short(a)=[MAE_q(b,short)-MAE_q(a,short)]/S_t

kappa(a)=d_long(a)-d_short(a)

每任务自身跨度平均误差；旧尺度显式换算。核模型截断/patch后长短实际输入不同，不因DEV结果另选长度。kappa是治理管线对更早观测的有符号响应，不是市场因果效应，不保证线性外推。

ProbeSpec记录parent/两个origin/L/H/长短长度/可读范围/mask/覆盖/model和inputhash。ProbeResult存历史预测/rawMAE/统一收益/kappa/支持/完整成本。ProxyTargetPair仅train，绑定历史测量和当前部署收益。

## 模块二：收益映射

独立train evaluator监督Delta_t(a)=[MAE_t(b)-MAE_t(a)]/S_t，与在线ProbeResult分离。

psi固定：输入长度/跨度比例；缺口位置和长度差；有效观测和协变量覆盖差；仅已观测稳健波动尺度差。禁source名、污染真类别、当前future、oracle动作。

z=((L-Lq)/64)*kappa。

Delta_hat(a)=beta0(a)+beta1*d_long(a)+beta2*z(a)+beta3*psi。

共享低维ridge向beta1=1其余0收缩；拟合Delta_t-d_long，再在原收益单位加回d_long，不能固定beta2=1或混标准化单位。alpha仅0.1/1/10，train内选择，标准化只fit，source/parent权重，两family分训。参照收益恒0，平局优先参照；无kappa用对应无响应状态，不伪造实测0；支持不足回固定参照。同输入容量/train/alpha预算的direct收益ridge和同新证据普通CART必须实现。残差表达非创新，通用方法同效用更简单实现。

## 模块三：获取

冻结收益映射、终态、支持后，独立T_acq计算v=当前终态loss-取证后新终态loss-lambda完整部署成本差；禁止oracle/旧scorer/历史自身增益代替，保留负值。复用获取器，最多一次决策，在H32、单H、长度控制H、STOP中选；组合实际调用逐次计费。正净值、整个分支预算可行才执行。原预算/价格不降低。未取得candidate/output不免费成为特征。

## 共同实验

两个family共用合法parents。主表KEEP、固定TSICL、train固定强参照、同证据CART、固定新证据终态、完整agent、TATO原生短预算适配。TATO非官方完整复现。

必要机制：H32对H；删kappa/换旧multiview分歧；同容量directridge/同证据CART；同origin长短与等成本额外普通回测；fixed/random-feasible/active。同成本普通回测用r和r-64两origin，登记跨度、长度、缺口可行性并完整计费；共同支持机制子集，全覆盖表保留失败回退。预测账本生成一次，消融CPU/cache不笛卡尔积。

报告历史/部署收益符号一致率、零值、排序错误损失、响应对真实选择增量、同预算MASE与完整成本及自然轨迹。只按metadata支持预登记一个train未见缺口位置×H组合，无看label挑组合。旧26parent永久已用DEV，新窗口合法登记且重算共同baseline，不比不同集合MASE。fit/gate/check/acq按parent/time隔离，heldout不因失败开封。

## 金融和在线

核资产/来源/价格字段/口径/时区/频率/日历/调整版本，不能凭Oil/USTS名认金融。分别完整、核实自然缺口、受控删除；无自然缺口则缺项，休市非缺失/as-of协变量/真实跳变保留。争取两金融系列并说明相关性，原target/H/MASE不偷换。完整五臂no-op报告一致预测/成本，不报提升。在线自然取证、STOP、预算不足、故障回退；强制调用只分支测试。

## 执行交付

只服务器计算，先资源检查，一重GPU，CPU按内存并发，不终止他人/驱动/购买。代码/支持/金融/基线/论文并行，价值labels等冻结。先约20合法trainparent测吞吐/内存，不据其表现选模型；再最大合法训练，学习曲线复用cache。首报代码差异/支持/长短治理收益四格/整批ETA，每小时或关键批次更新。

新增prompt/plan/report/main_table/novelty_matrix，同步HANDOFF/ledger/claims/实验矩阵/论文，保留负结果。novelty_matrix覆盖TATO、Task-oriented Imputation、CSDI、DIME、TNDP、ImputePilot和嵌套上下文工作，写旧代码/本次差异/必要消融/支持状态。精简包含actual commands/config/support/code/少量pair与自然trace/费用/commit和hash，无weights/credentials。响应不胜旧分歧/等成本回测则非已证创新，主动不胜固定则不称有效，仅修STOP不是研究成功。最终完整候选/共同结果/归因/金融/可支持主张/SHA/远端一致/缺项。
