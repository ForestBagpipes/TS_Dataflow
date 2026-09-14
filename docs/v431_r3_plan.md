# v4.3.1-r3 预登记执行计划

登记于2026-09-15 Asia/Shanghai，01:03接续；没有新增明确截止时刻。r2已提交9d31106并同步origin。r3未读取新的DEV探针结果前固定以下方案。服务器16 CPU/47GiB RAM/4090可见49140MiB，单重GPU、BLAS1、两轻量CPU并行，既有三环境不变。

## 协议和真实支持

旧三来源最大合法非重叠704跨度为110 train parent（ETTm1 59/Solar44/USTS7），54 fit/21 gate/17 check/18 acq，DEV26 parent/156变体永久已用。原每来源64上限没有遗漏；不凭156变体、多probe扩充parent。原五臂、目标、L512/H96/H192、source宏平均/parent聚合/共同futuremask和checkpoint均不改。

reference在fit+gate75内按任务损失选各family固定臂，state模型fit54、alpha由gate21选择，check17不选配置；终态集合先落盘hash，再在18 acq生成新工具价值labels。先前r2模型和labels不作为r3获取监督。fit-only scaler，alpha仅0.1/1/10，两family分别训练。

## 固定探针

| 原子 | 当前t | 历史exclusive origin | 起点 | horizon | 输入长度 |
|---|---:|---:|---:|---:|---:|
| h32 |512|480|0|32|480|
| long |512|512-H|0|H|416/320|
| short |512|512-H|64|H|352/256|
| second |512|448-H|0|H|352/256|

长短只差更早64步，同origin/标签/评分mask/model。等次数普通回测为long+second，second的origin早64步，非同future；按实测成本报告，不能声称两probe自然完全等秒数。所有分支先截原dirty、按当前缺失距t偏移复制gap、再独立拟合/治理；不裁长分支已修数据。target及cov缺失都留身份，as-of可用性遵守原契约。任何映射缺口落出历史输入则unsupported；control需要两分支均支持且同一公共gap，不能移动或裁掉。

历史评分只dirty当前可见值，有效数量至少max(16,ceil(.5*Hq))，每臂共同mask。无支持留明确reason、全覆盖策略回参照，不填零标签。原始[230,281)缺口H192平移为[38,89)，短输入从64起，故control应不支持；这是预先已知几何结果，不是新DEV效果选择。

统一既有当前source MASE尺度S_t。保存raw MAE，d=(MAEref-MAEarm)/S_t，kappa=dlong-dshort，z=((512-Lq)/64)*kappa，无clip。旧MAD归一化缓存显式换算，不能混分母。核后端原始input、trimmer、leadingNaN和patch；长短实际模型信息相同则标无效，不根据DEV另选64。

## 冻结模型和机制比较

共享低维ridge输入：arm截距、dlong、z、psi；拟合Delta-dlong并在原收益单位加回dlong。psi固定为长度/跨度比、缺口相对位置及长度差、target/cov覆盖差、已观察稳健波动尺度差。无source/path/真实污染类别/部署future/oracle。参照gain0，平局参照，完整有效target直接KEEP。

同输入容量直接ridge拟合Delta；同新增证据普通CART沿depth3/minleaf96/实际16parent，不另搜深度。状态H32、H、control、equal-cost、old-disagreement分别训练；无kappa的主消融=单H状态，未获得响应不伪装成实测0。旧multiview分歧严格对应 `src/introact_ts/probe.py` 的原始预测统计，应用于已取得的同一long/short两视图：extra(a)=mean_t std_view(pred_long(a),pred_short(a),ddof=0)/S_t，不乘长度factor，使用共同完整预测H；该统计不读取目标真值。输入、工具费用、维度、监督和alpha预算与响应模型相同。不是std(d_long,d_short)=abs(kappa)/2；后者仅可作原始诊断，取消该学习配置。旧v43缓存gain_std只有Bolt来源，亦不能冒作TimesFM。两次源码概念核查更正的原计划字节/SHA另存；本次在已见20parent训练测量后、任何r3终态拟合和DEV策略评估前完成，不依据模型成绩选择。

完整agent最多一次决策，候选STOP/H32/H/control；equal-cost与old-disagreement为固定机制对照，不扩获取器动作空间。获取器复用depth2/min16parent，lambda仅0/旧train尺度公式，在T_acq parent LOPO选择；费用为同冻结终态前后完整部署差，budget准入检查获取整个分支，原low0.8140623268639832秒/high3.5秒不改。预计净值>0才调用，不降低阈值。固定、随机可行、主动同state/信息/监督/预算；误差容忍沿r2为0 MASE。

主表保留所有26 DEV parent/156变体及KEEP/固定TSICL/train固定参照/同证据CART/固定新证据/完整agent/TATO；机制表另取工具共同支持子集但不删除主表失败。TATO原生8trial短预算身份不变，已共同origin缓存合法复用。表中budget事后超支保留，训练搜索/离线账本/部署工具和最终推断/冷启动分列。

## 未见位置×跨度检查与金融

仅按metadata登记T_check17个parent的额外target-only [358,409)×H192变体，从其raw已观察快照构建。fit/gate/acq均没有该位置，原[230,281)条件不移除；新17变体不增独立parent，当前future沿同parent/H192缓存。其模型及阈值不得用check结果调整。该检查能保留长短公共缺口，仍报告自然NaN导致的不支持。

金融复用r2两核实来源（Brent spot与Kim–Wright fitted forward rate）的12episode和financial-observation-index-r1协议。两个DEV日期不重叠，TRAIN1242共同有限日期水平相关−0.142379；已有future与旧DEV/pilot重叠，非独立确认。完整、受控target/shared删除分报；没有核实自然缺口集，不宣称严格PIT。H按观测事件、S_t取其独立train lag5尺度，不与旧B网格表横比。r3冻结后只迁移评估，不用其表现调参。

## 队列与交付

先CPU必要测试/prepare全量context-only账本，再20合法train parent（按source/time固定，无label选择）实测GPU吞吐和内存。顺序Bolt20→最大Bolt→TimesFM20→最大TimesFM；hash有效的候选两family共享，实际部署仍计成本。GPU模型输入按hash分批常驻；每批记录PID、raw、code/model/inputhash、资源和失败；tmux断线继续，无自动关机。

CPU并行完成收益映射、获取器、统计、旧代码与相关工作审计。冻结后运行r3两family在线：7自然窗口/完整KEEP/零预算/真实工具后故障；强制调用只受控分支，不充当策略收益。在线屏障封存未来、训练监督及未取得工具缓存，最终预测保存后才评分。

交付report/main table、逐source/H/缺陷配对、独立parent/time块区间、四格原始MAE与gain、符号一致/零收益/排序选择错误损失、正确错误切换、获取数/费用/失败。独立复核只本轮相关路径，不机械重跑58项。论文和novelty_matrix标明未支持主张；自然缺口/响应优越性/主动增量/SOTA无证据即缺项。calibration/test继续封存，PICS_joint_relabel不变。精简review bundle和正常commit/push，保留r2与更早负结果。
