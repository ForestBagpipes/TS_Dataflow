# r5 文献核对与贡献边界

核对日期2026-09-16，primary来源；这是相关工作准备，不是已运行基线。没有找到完全相同公式不构成原创证明。

| 工作与原始来源 | 已有先例 | r5应检验的边界 |
|---|---|---|
| [TATO官方代码](https://github.com/thulab/TATO)，ICLR2026页面本次遇browser verification | 冻结TSFM的输入变换与任务导向选择，原生空间离线搜索 | 五臂不覆盖有效观测是任务契约；必须胜完整原生方法公平适配后才谈强基线优势。原156变体表仅8trial；追加TRAIN场景结果见独立基线报告，长度单位与官方不同 |
| [Task-oriented Time Series Imputation Evaluation via Generalized Representers](https://arxiv.org/abs/2410.06652)，NeurIPS2024；[作者代码](https://github.com/hkuedl/Task-Oriented-Imputation) | 估计插补对下游任务的影响，并融合插补 | 任务收益监督本身不新；r5只在真实已执行版本中选一项，联合收益约束需单独消融 |
| [TS-ICL](https://arxiv.org/abs/2606.05878)，2026预印本 | 时间坐标回归统一插补/预测与协变量；缺失上下文能力 | 使用其插补能力不是新插补器；原生TS-ICL与治理后固定TSFM区别清楚 |
| [Forecast with Forecasts: Diversity Matters](https://arxiv.org/abs/2012.01643)，Kang等 | 从预测而非仅历史提取特征，利用预测多样性学习组合 | 当前预测差七特征不是首次使用预测作特征；最终不融合预测，但选择与组合差异不能替代实验证据 |
| [DIME / Estimating Conditional Mutual Information for Dynamic Feature Selection](https://openreview.net/pdf?id=Oju2Qu9jvn)，ICLR2024；[代码](https://github.com/suinleelab/DIME) | 判别式信息估计、顺序获取、可变预算和非均匀成本 | r5收益先验减当前收益/成本是启发式，非CMI最优性证明；固定流程具有相同复用权利 |
| [Amortized Bayesian Experimental Design for Decision-Making](https://proceedings.neurips.cc/paper_files/paper/2024/hash/c59f05d7ab3638b138cc61f32e1a7cd1-Abstract-Conference.html)，NeurIPS2024 | TNDP联合摊销实验设计与最终决策、最大化下游效用 | “取证服务决策”已有；r5低维收益先验不等于已实现TNDP或最优VOI |
| [Convex Optimization，Boyd/Vandenberghe](https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf)；[Jaggi2013 Frank-Wolfe](https://proceedings.mlr.press/v28/jaggi13.html) | 凸集、投影一阶最优条件、线性oracle及gap已有 | 绝对损失折点收益集合是本任务构造；凸投影/FW不可称发明。近似解报告gap，不将向量误差性质夸成排序/MASE安全 |
| [When Should a World Model Move? Loss-Conditioned State Execution](https://arxiv.org/abs/2609.15801)，2026-09-14 v1 | 固定可行提议与保留现状，独立calibration上的分组损失收益下界决定执行 | r5几何无需future标签，但不具有此文在i.i.d./有界损失/独立校准条件下的组级保证。不能把KEEP/拒绝更新/损失门控称首次 |

LCSE的确切身份已核实，是Jintao Xu等的2026-09-14预印本，不是本项目实现或已完成外部基线。r5不得借用其证书，也不得因此提前解封校准。

## r5理论表述

给定当前任务所有已查询版本的预测、同一正origin尺度和合法权重，构造绝对损失差向量的凸可行域。参考坐标为0，未知未来评分mask使用共同凸包而非读取mask后收紧。收益向量的投影改善界来自标准凸投影：精确解满足平方向量误差界；FW近似解增加 `2*gap` 余项。它不保证各坐标、排序或最终预测MASE改善。

## 本轮主张验收

| 待验证主张 | 必要证据 | 失败时结论 |
|---|---|---|
| 当前任务响应有决策信息 | 同raw critic的免费/历史/当前响应与完整成本 | 不胜强简单对照则停止加配置 |
| 联合约束有独立贡献 | 相同查询轨迹、相同critic的raw/单臂/成对/联合，至少3不同预测支持 | 仅两预测退化或仅向量MSE变好，不支持高阶预测机制 |
| 选择性执行有增量 | 同投影critic与复用能力的固定次序/数量/主动/全五臂 | 固定等效则不声称主动机制 |
| 完整方法值得主实验 | 两家族相对TRAIN强对照、真实在线成本和边界均过门槛 | 旧DEV点估计不等于独立确认；不开放保留集救开发 |

经典“loss-vector geometry”是相关概念类别而非用户给定的一篇确切论文；本轮引用可核实的凸优化基础，不虚构某个同名文献。尚未完成系统文献穷尽检索或所有外部方法复现，不声称不存在更近先例。
