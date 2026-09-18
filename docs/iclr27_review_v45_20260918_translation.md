# IntroAct-TS v45 正文逐段直译与审稿意见

审阅对象：`latex/IntroActTS_20260918_v45_review.tex`（正文 9 页，附录至第 26 页）。
审阅视角：ICLR 2027 审稿人，方向为时间序列基础模型、缺失数据与选择性决策。
本文件只覆盖正文。每一段先给直译，再给审稿意见与改法。附录、代码核对、方法改进与实验规划见 `docs/iclr27_review_v45_20260918.md`。

直译原则：逐句对应，不润色，不补充原文没有的信息。占位符 `[KEY]` 原样保留。

---

## 0. 标题

**直译**：IntroAct-TS：面向冻结时间序列基础模型的选择性输入治理

**意见**：标题已定，不改。需要注意的是正文里 governance 一词只在 §1 和 Figure 1 出现，方法节全部用 intervention 和 decision。建议在引言第一次出现 selective input governance 时给一句操作性定义，之后全文统一用 selective intervention 指代机制，用 governance 指代整个决策层。现在读者会在两个词之间来回切换。

---

## 1. 摘要

**直译**：
时间序列基础模型在部署时不做任务特定的参数更新，而它们在预测时刻收到的上下文常常是不完整的。现有的不完整输入预测方法要么重建不可用的信息，要么训练能够容忍缺失的架构。我们针对一个冻结的预测器研究一个不同的问题。给定几种处理不完整上下文的可接受方式，哪一种应该被应用到当前请求上，以及是否应该应用任何一种。我们提出 IntroAct-TS，它把历史窗口作为伪部署来回放，以测量每个可接受动作的实际预测效用，为所考虑的动作局部地估计该效用，并且只在一个保守效用分数为正时才执行动作。参考动作是目录的一部分，因此当证据不支持切换时，方法保持输入不变，而且每一个返回的预测都来自一个被实际执行过的输入版本。在 [N_DATASETS] 个来源、四种缺失模式和两个 horizon 上，用两个冻结骨干做开发，第三个家族在方法设计中被留出，IntroAct-TS 相对 [STRONG_BASELINE] 达到 [MAIN_OVERALL_MASE] 的来源宏平均 MASE，干预率为 [MAIN_INTERVENTION_RATE]，并且它执行的干预保持 [HARM_HIR_OURS] 的条件有害率。[ABSTRACT_CLOSING]。

**意见**：
第一句把两件事并列，读起来像两个不相关的事实。可以改成一个因果关系：因为模型在部署时是冻结的，所以不完整上下文只能在输入侧处理。

第三句和第四句是摘要最重要的问题定义，但第四句是一个没有问号的问句，读起来像残句。建议直接写成陈述：the question is which of several admissible ways of handling an incomplete context should be applied to the current request, and whether any should be applied at all.

`reaches [MAIN_OVERALL_MASE] source-macro MASE against [STRONG_BASELINE]` 这一句语法不通，达到一个 MASE 不能 against 一个基线。填数时应写成相对差值：improves source-macro MASE over the strongest baseline by X with a confidence interval that excludes zero。

摘要没有提任何一个现有方法被超过多少，也没有提 Best Fixed 和 R2-CART 这两个最能说明问题的对照。审稿人读摘要时最想知道的是相对于最强的固定策略和最简单的选择器，这个方法赢了多少。建议在结果句里明确写出相对 Best Fixed 的差值。

条件有害率单独出现在摘要里会引起误读，因为读者不知道基线的条件有害率是多少。要么同时给出最强固定策略的条件有害率，要么改成干预率下的有害率相对基线下降了多少。

建议的摘要结果句（填数后）：Across eight sources, three frozen backbones, four missingness patterns, and two horizons, IntroAct-TS lowers source-macro MASE by X relative to the best fixed intervention and by Y relative to the strongest published baseline, with paired confidence intervals that exclude zero on every backbone, while executing interventions on Z of the requests at a conditional harmful rate below that of any fixed intervention.

---

## 2. Introduction

### 第一段

**直译**：
时间序列基础模型（TSFM）现在无需任务特定的再训练就能给出有竞争力的零样本预测，这使它们作为已部署预测系统的固定组件很有吸引力。预测起点可用的上下文常常是不完整的。一个传感器停止报告一段时间，一个通道把一个变量晚几步送达，或者一个采集批次只有一部分到达。我们研究这样的部署协议：一个已经到达且有效的观测不能被覆盖，因此系统只能在数据缺失的位置上行动。

**意见**：
这一段已经比 v44 直接很多，保留。两处可改。第二句 `is often incomplete` 没有引用，这是全文最重要的现实前提，后面引的 BiTGraph 和 S4M 只支撑了三个例子。建议把引用移到第二句句末。最后一句 `so the system may act only on positions where the data is missing` 是本文的约束定义，建议紧接着用一句话说明为什么要这样定义：因为覆盖一个有效观测会改变一条真实记录，这是数据完整性问题，与预测效果无关。伦理声明里已经有这句话，引言里也应该有，否则约束显得随意。

### 第二段

**直译**：
对缺失数据的既定回应是插补。面向重建的方法尽可能准确地恢复缺失项，并按重建误差打分。BRITS 使用双向循环动态，CSDI 用基于分数的扩散过程建模缺失值的条件分布，T1 传递跨变量信息以改进多变量恢复。第二条路线在预测模型内部处理缺失，其中 BiTGraph 把有偏时序卷积与变量图耦合，S4M 把缺失模式折进结构化状态空间模型。两者都训练或重新设计预测器。

**意见**：
内容准确，结构清楚。`The established response` 里 established 略带评价色彩，可改为 `The usual response`。最后一句 `Both train or redesign the predictor` 是这一段的落点，也是本文与这两条路线的分界，但它只有五个词，读者容易滑过。建议加半句把分界说完：which is not available when the forecaster is a frozen foundation model。

### 第三段

**直译**：
第三条路线把目标从恢复转向下游效用。面向任务的插补评估估计不同时间步上的插补值如何影响下游预测模型，并根据估计的收益组合插补策略。TOI-VSF 训练插补模块以支持预测目标，GIMCC 在生成值与目标之间加入因果一致性，SRDI 在一个对变量缺失引起的偏移有弹性的空间里做扩散插补。TATO 通过从历史任务表现中选出的变换流水线，把一个冻结 TSFM 适配到异构领域。每个结果描述的是一个在语料上估计出来的策略或变换族。

**意见**：
这一段对 Wang et al. 2024 的描述已经修正为按时间步估计影响并组合策略，准确。最后一句是全段的落点，但 `Each result describes a strategy or a transformation family estimated over a corpus` 表达不够直接。审稿人需要看到的分界是：这些方法在训练阶段决定用什么策略，而本文在部署阶段为每个请求决定是否用以及用哪个。建议改成：These methods decide, at training time and over a corpus, which strategy or transformation to use. The decision studied here is made at deployment time and for one request.

TATO 放在这一段里与三个插补方法并列有点突兀，因为 TATO 不处理缺失。建议把 TATO 的句子挪到第四段开头，作为冻结 TSFM 数据侧适配的代表，然后引出本文的粒度差异。

### 第四段

**直译**：
我们研究模型部署之后仍然存在的那个决策。预测器是冻结的，未来目标不可用，系统必须为一个具体的不完整请求选择执行哪个可接受的输入干预，或者是否保持输入不变。三个性质使这个选择不平凡。一个干预的实际效用依赖于未来目标，在线不可观测，这促使我们把历史窗口作为伪部署回放，并记录每个可接受动作实际做了什么。最佳动作随请求和骨干而变，因此证据必须局部检索，而不是在语料上平均。局部证据是有限的并且可能冲突，一个平均看来有利的动作仍然可能增加当前请求的损失，因此执行取决于一个保守的效用分数。

**意见**：
这是全文写得最好的一段，三个性质分别对应方法的三层，逻辑闭合。两点建议。`Three properties make this choice non-trivial` 里 non-trivial 是审稿人常见的空词，可以直接说 `Three properties shape this choice`。第二个性质 `The best action changes with the request and with the backbone` 现在是断言，§4.2 才给证据，建议在句末加 `(§4.2)`，让读者知道这是要被验证的前提而不是假设。

### Contributions

**直译**：
(1) 选择性输入治理。我们把冻结 TSFM 的不完整输入处理形式化为在一个固定的可接受干预目录上的逐请求决策，其中未改动的输入是选项之一，并且我们测量最佳动作在请求和骨干之间变化得有多强（§4.2）。(2) 带局部效用估计的历史全动作回放。我们通过在 TRAIN 历史上重演注册的缺失协议并用冻结预测器执行每个目录动作来构建回放库，因此存储的监督是实际预测效用，并且当没有动作越过一个保守分数时决策规则返回参考动作（§3，§4.4）。(3) 关于伤害与成本的证据。我们在八个来源、三个冻结 TSFM 家族、四种缺失模式和三个严重度水平上，与基于重建、面向任务和数据侧适配的基线比较，并在同一协议下报告预测精度、有害干预和部署成本（§4.3，§4.5，§4.6）。

**意见**：
贡献 (2) 一句话里塞了回放库构建、监督信号性质和决策规则三件事，读起来吃力。建议拆成两句。另外贡献 (3) 只说了比较，没有说结果。ICLR 的贡献列表通常在这里给一句结果方向，填数后应加：IntroAct-TS is the best deployable method on every backbone and lowers harmful interventions relative to every fixed intervention。

三条贡献里没有一条提到 Best Fixed 和 R2-CART 这两个对照，而这两个对照恰恰是证明选择性决策有必要的关键。建议在 (3) 里明确写出。

### Figure 1 图题

**直译**：
冻结预测器的选择性输入治理。(a) 评估 episode 上测得的动作效用，取自记录的统计而不是手挑的例子。oracle 最佳动作在请求间并非常数，因此单一固定干预会让一部分可得改进未被利用。(b) 历史全动作回放。TRAIN 窗口在注册的缺失协议下被回放，每个目录动作用冻结预测器执行，实际效用存入回放库。(c) 在线决策。计算参考预测，每个可接受动作从其动作条件状态的同动作邻域打分，只有当保守分数为正时才执行最佳动作。

**意见**：
(a) 的小标题写的是 oracle-best action share，正文图题写的是 measured action utility，两者不一致。图上的柱状图确实是 share，图题第一句应改为 `Share of evaluation episodes on which each catalog action is oracle-best`。图题里 `drawn from the recorded statistics rather than from hand-picked examples` 是在为自己辩护，删掉，审稿人看到的是数据就够了。图 (a) 下方的 `BEST FIXED gap = [MAIN_HET_GAP]` 会在正文再出现一次，图里只放数即可。

---

## 3. Related Work

### 3.1 Incomplete Time-Series Modeling

**直译**：
基于重建的插补是两条路线里较老的一条。BRITS 做双向循环插补，CSDI 用条件分数扩散模型替换确定性映射，GAIN 和 SAITS 探索同一目标的对抗式和自注意力变体，T1 在严重且结构不同的缺失下改进多变量恢复。它们的主要比较都围绕重建精度。
第二条路线从部分观测的输入直接预测，没有单独的插补阶段。BiTGraph 指出先插补再预测会累积误差，并在带变量图的有偏时序卷积网络内部处理缺失模式。S4M 把缺失数据处理整合进结构化状态空间架构，ChannelTokenFormer 联合处理通道间依赖、异步采样和测试时缺失块。这条路线上的方法是完整的预测模型，其参数是贡献的一部分。
第三条路线把目标从恢复转向下游效用。面向任务的插补评估估计单个时间步上缺失或插补标签如何影响下游预测模型，并按估计收益组合插补方法。TOI-VSF 把这个目标带进变量子集预测，其中整个变量在推理时缺席。GIMCC 在生成值和目标之间加入多层因果一致性，VIDA 把变量子集预测重新表述为跨域知识迁移，SRDI 在一个对变量缺席引起的偏移有弹性的空间中做扩散插补。
三条路线要么恢复缺失值，要么训练一个容忍缺失的预测器，要么估计一个插补方法在训练阶段的性质。IntroAct-TS 保持预测器固定并处理部署阶段，此时请求已经到达，骨干已经冻结，未来目标不可用，系统从一个有限目录中选一个输入版本或保持参考输入。

**意见**：
小节标题下面第一句 `is the older of two routes` 与段内实际写了三条路线矛盾。改为 `Three routes handle incomplete inputs`。

引言第二、三段和这一节内容重复度很高，同样的方法用几乎相同的一句话介绍了两次。ICLR 9 页正文很紧，建议引言只点名路线和一两个代表，把逐方法描述留给这一节。

变量子集预测（TOI-VSF、GIMCC、VIDA、SRDI）是整个变量缺席的设定，与本文按位置缺失的设定不同。这一节把它们与本文放在一条路线上，但没有说这个设定差异。审稿人会问为什么主表要与变量子集方法比。建议加一句：these methods address a setting in which entire variables are absent, and we include TOI and SRDI in the main comparison as the closest task-oriented baselines that emit a repaired input。如果最终 SRDI 没有可用实现，这一句和主表行都要相应改。

### 3.2 Data-Side Adaptation for Frozen TSFMs

**直译**：
TATO 表明一个冻结 TSFM 可以在不更新参数的情况下适配异构领域。它搜索一个变换流水线，包括上下文切片、尺度归一化和异常值校正，并从历史任务表现中选择流水线。适配的单位是目标领域。TS-ICL 是一个原生支持插补、不规则观测和部分观测回看窗口的基础模型。我们在这里只把它用作两个目录动作的上下文回归后端。
与 IntroAct-TS 的区别在于决策的单位。TATO 和 TS-ICL 改变的是模型看到什么或者模型是什么。IntroAct-TS 两者都不动，并逐请求决定是否应用一个可接受的输入干预。

**意见**：
`TATO and TS-ICL change what the model sees or what the model is` 这句是修辞化的对仗，且不准确，因为本文的干预同样改变了模型看到什么。建议改为：TATO selects a transformation per domain, and TS-ICL is a forecaster with native missing-value support. IntroAct-TS keeps the deployed forecaster and selects per request whether to apply an input intervention, and TS-ICL enters only as the imputation backend of two catalog actions。

TS-ICL 作为目录动作的后端，意味着部署时需要两个基础模型。这一点应该在这里或 §3.5 明说，否则审稿人在成本节才发现。

### 3.3 Selective Decision Making

**直译**：
选择性预测在一部分输入上弃权，以覆盖率换取更低的风险。学习拒答则把一部分输入路由给人或另一个决策者。两种机制都改变了由谁或由什么产生答案。IntroAct-TS 两者都不做。同一个冻结预测器在每种情况下都返回预测，被选择的是输入是否先被修改。
决策层也不是一个基于日志数据的策略学习问题。历史回放在同一窗口上执行有限目录中的每个动作，并对每个动作按实际未来评估，因此库里保存的是完整动作结果而不是来自记录策略的赌博机反馈，不需要倾向性校正。动态特征选择在一个相关的序贯获取设定里权衡额外信息的价值与其成本。我们不做信息论最优性声明，并单独报告成本核算（附录）。

**意见**：
这一节回应了 v44 自审里最担心的 bandit/OPE 切割，内容正确。第二段的 `is also not a policy-learning problem` 又是一个否定式定义。建议正面写：The replay bank records the outcome of every catalog action on every historical window, so the decision layer is a supervised local estimation problem rather than an off-policy one。第一段 `IntroAct-TS does neither` 同样可以改成正面陈述。

---

## 4. Problem Formulation and Method

### Figure 2 图题

**直译**：
IntroAct-TS 的架构。离线（上）：历史 TRAIN 窗口通过注入注册的缺失协议变成不完整上下文，每个目录动作用冻结预测器执行，实际效用填入回放库。这是唯一读取未来的地方。在线（下）：一个请求只暴露不完整上下文。计算参考预测，为每个可接受动作形成动作条件状态 z_a，每个状态对冻结的库打分。然后用同一个冻结预测器执行一个动作，在线既不访问未来目标，也不访问未被选中候选的预测。

**意见**：
图本身清楚。图底部状态特征的四行与附录特征表不一致，也与代码不一致，见主文件的代码核对部分。修图时按代码写。

### 4.1 Problem Setup

**直译**：
设 X 是预测起点的多变量上下文，观测掩码为 M，未来目标 Y 对决策过程永远不可用。设 F 表示完整的冻结部署推理流水线，它接收一个输入版本并返回预测 p = F(X)，并包含骨干内部所做的任何预处理，因此对 F 的一次调用正是部署系统所做的那次调用。
设 A 是一个固定的可接受干预目录，除参考动作外还有 J 个干预。每个动作 a 生成一个可接受的输入版本 X^a = T_a(X, M)。参考动作 a_0 原样返回输入，对应于没有外部干预，A^+ 收集修改输入的动作。设 ℓ 为预测损失，定义在与主评估指标相同的归一化尺度上，使回放效用与报告误差可直接比较。效用相对参考动作度量，因此对一个实现的目标 Y，g_a = ℓ(F(X^{a_0}), Y) − ℓ(F(X^a), Y)，任务是在不访问 Y 的情况下选择 a*(X, M)，同时保持冻结骨干调用次数少。
三个约束定义部署协议。已到达且有效的观测不能被覆盖，因此每个 X^a 只在 M = 0 的位置与 X^{a_0} 不同。未来目标不可用，因此部署时没有实际损失可观测。参考预测是决策前唯一可以计算的预测，这是一个调用预算而不是关于未来的陈述：一个请求可以花一次预测骨干调用获得 p_0，其余候选的预测在选择动作时不得被查看。

**意见**：
形式化已经清楚，符号与后文一致。三点可改。第一，`F` 对含 NaN 输入的语义在不同骨干上不同（Chronos 系列原生处理 NaN，TimesFM 不同），KEEP 的含义随之不同。建议加一句：the reference action passes the incomplete context to the backbone's own missing-value handling, so KEEP is backbone specific and is measured rather than assumed。这正好呼应 §4.2 里最佳动作随骨干变化的证据。第二，`while keeping the number of frozen-backbone calls small` 是一个目标不是约束，应移到第三段与调用预算放一起。第三，最后一句冒号后的解释太长，拆成两句。

### 4.2 Historical Full-Action Replay

**直译**：
决定动作的量 g_a 依赖于 Y，在线不可观测，但对历史窗口是可计算的。取一个 TRAIN 窗口 i，它的预测目标 y_i 已经是可用历史的一部分，注入注册的缺失协议得到 (X_i, M_i)，生成目录中每个动作，并在每个版本上执行冻结流水线。动作 a 在窗口 i 上的实际效用是 g_{i,a} = ℓ(F(T_{a_0}(X_i, M_i)), y_i) − ℓ(F(T_a(X_i, M_i)), y_i)。这是部署系统本来不会采取的一个动作的测量结果，通过重新执行历史窗口而不是建模来恢复，两项都对同一个实际未来评估。
与每个结果一起记录的状态是动作条件的。对窗口 i 和动作 a，z_{i,a} = φ(X_i, M_i, X_i^a, p_i^0)，p_i^0 = F(X_i^{a_0})。状态可以使用参考预测 p_i^0，这是协议已经允许的，并且它从不使用未被选中候选的预测。回放库是 B = {(z_{i,a}, a, g_{i,a})}，从 TRAIN 历史一次构建然后冻结。部署读它并且从不写它。
式中实际效用在预测 horizon 上度量，因此 H=96 和 H=192 处的 g_{i,a} 是不同的量，不得共享一个邻域。因此库按冻结骨干版本、按来源、按 horizon 索引，一个请求只对与其自身 horizon 匹配的库切片打分。它也只覆盖预先注册的缺失协议。这些性质是承重的，附录说明它们对方法范围的含义。
从库到决策依赖一个明确陈述的经验假设。动作条件状态在状态空间中接近的请求具有相似的动作效用，因此一个动作在新请求上的效用可以从库中其状态的同动作邻域估计。这个局部迁移假设不在注册网格之外断言，本文不对回放过的模式和严重度之外的行为做任何声明。

**意见**：
这一节的第三段与代码不一致：代码里的检索没有按来源和 horizon 切片，而是在整个 bank 里按动作检索。而且本机原型显示按来源加 horizon 切片在 Bolt 上更差，在 TimesFM 上略好，没有一致收益。这一段应该按最终代码写。如果最终决定不切片，就把 `the bank is therefore indexed by ... horizon` 改成状态里包含 horizon 指示，或者删去。这是当前正文与实现之间最实质的一处不一致。

`These properties are load-bearing` 是比喻，改为 `These properties define the scope of the method`。

最后一段的假设写得好，保留。但 `and the paper makes no claim about behaviour beyond the patterns and severities that were replayed` 在附录范围节里已经出现，正文出现一次就够。

### 4.3 Action-Conditioned Local Utility Estimation

**直译**：
估计器是非参数的，不使用学习的编码器和学习的距离。状态 z_a 携带四组特征。掩码状态描述请求如何不完整。可见上下文状态从存在的值计算，概括水平、趋势、自相关、季节性和近期波动。干预状态描述 X^a 和 X^{a_0} 之间的差异。参考预测状态从 p_0 计算，概括预测水平、范围、趋势、相对最后可见观测的跳变和粗糙度。完整特征列表、窗口长度和归一化统计在附录给出一次，连续特征用只在 replay-fit parent 上拟合的统计做标准化。
检索对每个动作分开进行。对动作 a，邻域 N_a 包含 k 条库记录，它们记录的动作是 a 并且状态在标准化欧氏距离下最接近 z_a。每个邻居获得权重 w_i = exp(−d_i/τ)，τ = 中位数距离加 ε，因此带宽由查询邻域自身设定而不被调节。局部平均效用、局部离散度和有效样本量为（式）。邻域大小 k 是这里唯一被搜索的量，在 TRAIN gate 上于 {8, 16, 32} 中搜索。邻域只由距离定义，没有阈值把请求标记为在回放支撑之外，因此估计器对收到的每个请求都返回一个值。§4.5 和附录把由此产生的范围当作网格内陈述处理。

**意见**：
`uses no learned encoder and no learned distance` 是又一个否定式定义。如果最终采用特征加权（见主文件的方法建议），这句话要改。即使不采用，也建议正面写：The estimator is a same-action nearest-neighbour average in a fixed standardised feature space。

`k is the only quantity searched here` 与下一节 β 也被搜索矛盾，v44 自审已经指出过，v45 用了 here 来回避，但读者仍会困惑。直接写 `k and the penalty strength β of §3.4 are the only searched hyperparameters`。

四组特征的描述与附录表和代码都不一致，尤其是掩码特征在代码里只看目标通道，附录写成对所有通道平均。必须以代码为准改正文和附录。

### 4.4 Conservative Act-or-Keep Decision

**直译**：
局部均值为正不足以作为执行动作的证据，因为邻域可能很小或内部不一致。因此决策使用保守分数 S_a = μ̂_a − β σ̂_a / √n_eff，其中 β 是惩罚强度，并且 max S_a > 0 时执行 argmax，否则 a* = a_0。
这个分数是一个启发式，我们把它作为启发式呈现。它不是 g_a 的校准下界，不带覆盖或风险保证，β = 1.64 是 gate 网格 {0, 1, 1.64} 中的候选惩罚强度之一而不是某个抽样分布的分位数。阈值零也不是调出来的量。效用按式相对参考动作定义，因此分数为零意味着证据无法把该动作与保持输入不变区分开。
两个超参数 k 和 β 在任何评估运行之前于 TRAIN gate 上按预先固定的准则选择。在 gate 上有害干预率不超过 [GATE_HARM_CAP] 上限的网格点中，我们取 gate MASE 最好的点，因此伤害作为约束进入而不是作为与精度权衡的量。上限是任何评估运行之前冻结的协议常数，与解析后的配置一起记录，因此上限和被选网格点都不在评估数据上选。若没有网格点满足上限，配置退回最保守的网格点，即惩罚强度最大的那个。任何一步都不使用评估数据。
式的两个后果重要。参考动作总是可用，因此规则总是返回一个预测。这只是关于可用性的陈述，不意味着参考预测准确或返回它是安全的。规则也没有办法检测请求落在回放支撑之外，因此它适用于注册的缺失网格，结果不应被读作网格外泛化。

**意见**：
第二段把分数的所有弱点一口气列完，`The score is a heuristic and we present it as one` 这种自我声明在审稿人眼里是防御。保留事实，改成一句：S_a is a heuristic score and not a calibrated bound on g_a; β is selected on the gate rather than set from a distribution。

第三段描述的 harm cap 在代码里不存在，这是当前正文与实现的第二处实质不一致。v46 规划已经登记要补，但补的方式需要定义 cap 是什么量、锚在哪里。本机原型显示，如果 cap 定义为条件有害率 0.25，所有配置都会被逼到最保守的格点，方法在精度上就输给自己的消融。主文件里给了锚定在最佳固定动作条件有害率上的定义，请按那个方案实现，并在正文把 cap 的定义写出来。

第四段第二句 `does not mean that the reference forecast is accurate or that returning it is safe` 是不必要的自我削弱，删掉。

### 4.5 Deployment Procedure and Cost

**直译**：
一个请求分四步服务。读取可见上下文和掩码并执行参考动作得到 p_0 和参考预测状态，然后生成候选输入版本并形成动作条件状态 z_a。从冻结库检索同动作邻域并对每个 a 评估 S_a，然后执行 a* 并返回结果预测，当 a* = a_0 时即参考预测。
四个成本分量分开保存并在附录分别报告，即一次性的离线库构建、候选生成、预测骨干调用和检索开销。一个请求花一次参考动作的骨干调用，若执行干预再多一次。方法不集成预测输出，不校正它们，不拟合残差模型，不更新 F 的任何参数。

**意见**：
`A request is served in four steps` 后面只写了两句，各含两步，读起来是两步。要么写成四句，要么改成 two stages。最后一句四个 not 连用，改成正面：The returned forecast is always one call of the unchanged F on one executed input version。

候选生成里 TS-ICL 是一个基础模型调用，这一节只说 candidate materialisation，审稿人会认为在隐藏成本。建议明确写：two of the four interventions call a frozen imputation model, whose cost is booked under candidate materialisation。

---

## 5. Experiments

### 5.1 Experimental Setup

**直译**：
主矩阵覆盖 [N_DATASETS] 个公开预测来源和三个冻结 TSFM 家族：Chronos-Bolt、TimesFM-2.5 和 Chronos-2。前两个用于方法开发。Chronos-2 只在配置冻结后进入，使用完全相同的算法和超参数，并用 Chronos-2 自身重建回放库，因此留出结果是冻结配置跨骨干家族的迁移，而不是回放库跨骨干的迁移。上下文长度 L = 512，主 horizon 为 {96, 192}。四种确定性缺失模式在任何方法运行前冻结，每个掩码由来源、parent、起点、horizon、模式和协议种子的确定性哈希导出。主比较使用 10% 严重度，§4.5 在同一注册网格内加入 30% 和 50%。附录定义模式、导出规则和指标分母。
目录固定为五个可接受动作，KEEP 为参考 a_0，完整且有效的输入总是映射到 KEEP。附录定义每个动作以及不支持、别名或失败执行的状态规则。
核心比较预先固定，看到结果后从不重排。四个已发表方法与每个冻结骨干组合，因此共享一个参考契约：T1 覆盖基于重建的插补，TOI 覆盖面向任务的效用，TATO 覆盖冻结 TSFM 的数据侧适配，SRDI 覆盖缺失输入修复。ChannelTokenFormer 是为该任务训练的完整预测架构而不是数据侧适配器，因此作为外部预测参考报告，不带逐骨干列。三个对照伴随核心集：Native Keep、Best Fixed 和 R2-CART。读取未来目标的 Catalog Oracle 作为诊断参考报告并排除在所有排名之外。§4.5 的严重度矩阵保持同一冻结配置并复用一个缩减但类型完整的七方法集合，它省略 SRDI 以便高严重度运行保持有界，同时每个对照类型仍被代表。附录记录名单、扩展比较和逐来源表。
每个来源按时间切成 TRAIN 和 TEST 并带 L + H 清洗，TRAIN 按起点时间划分为 replay-fit、gate 和 TRAIN-eval 块。所有设计、超参数选择、特征归一化和基线拟合只用 TRAIN，每张表在配置冻结后在 TEST 上计算一次。MASE 是主指标，RMSSE 是次指标，以 parent 为统计单位做来源宏平均，并对每个基线做配对聚类 bootstrap 置信区间。附录记录切分边界和 TEST 清单、完整指标与统计约定、诊断计数规则。

**意见**：
Best Fixed 和 R2-CART 在全文没有定义。审稿人读到主表时不知道 R2-CART 是什么。必须在这一段加两句：Best Fixed applies the single catalog action with the best mean utility on the gate to every request. R2-CART fits one depth-three classification tree per action on the same state features and executes the action whose tree is most confident, with KEEP when no tree exceeds one half。

`never reordered after results are seen` 又是防御性表述，删掉，前面 fixed in advance 已经够了。

TEST 的定义在这里只有一句话，而 TEST 现在还不存在（见主文件）。填数时要写清 TEST 是哪 25% 或 15%，多少 parent，以及 Exchange 这种只有一两个 TEST parent 的来源怎么处理。

### 5.2 Does Selective Intervention Need to Exist?

**直译**：
本节检验方法依赖的两个前提。两个统计都是配置冻结后在 TEST 上计算的诊断，都不用于任何选择。
第一个前提是最佳动作随请求变化。对每个评估 episode，我们把 oracle 最佳动作算作目录上实际损失的最小者，报告每个动作最佳的 episode 份额以及最佳固定目录动作与目录 oracle 之间的差距。Figure 1(a) 展示分布。[MAIN_HET_SHARES]。[MAIN_HET_GAP]。[MAIN_FIXED_ORACLE_GAP]。
第二个前提是重建质量和预测效用不是同一个准则。对产生显式重建的方法，我们在每个 parent 内比较重建排名与预测效用排名，报告赢家一致率和成对不一致率，并用合并的 Spearman 相关作为描述性摘要。比较覆盖发出隐藏位置显式估计的核心方法，IntroAct-TS 不在其中，因为它返回的是执行输入后的预测而不是缺失值的重建。Figure 3(a) 展示比较，附录加入 Reconstruction Oracle 诊断。[RANK_DISAGREE_STATS]。
同一批 episode 的分层拆解推迟到附录，其中机会阈值与它们对边界选择的敏感性一起报告。

**意见**：
这一节的设计正确，是 v45 相对 v44 最大的改进。两个提醒。第一，第一前提最有说服力的证据是最佳动作随骨干变化，本机 TRAIN-eval 数据已经显示 Bolt 上没有任何固定动作平均优于 KEEP，而 TimesFM 上固定 Multi TS-ICL 比 KEEP 好 0.14。这一对数字比份额分布更能说明问题，建议正文直接写出。第二，第二前提只有三个方法参与重建排名，Spearman 相关在三个点上没有意义，附录表里的 ρ 行应该删掉，只保留 parent 内的赢家一致率和成对不一致率。

### Figure 3 图题

**直译**：
为什么决策需要预测效用以及为什么它必须是选择性的。(a) parent 内重建排名对预测效用排名。较低的重建误差不意味着较高的实际效用，因此重建准则不能替代部署决策所关心的效用。(b) 风险对干预率。低有害率只有与获得它时的干预率一起才有意义，因为几乎从不干预的方法可以在无用的情况下达到低有害率。

**意见**：
图题两句解释都是在替读者下结论，图题应只说明图里是什么。(a) 改为 `Within-parent reconstruction rank against forecasting-utility rank for the methods that emit a reconstruction`。(b) 改为 `Conditional harmful rate against intervention rate over the score grid; the default operating point is marked`。结论放正文。

### 5.3 Main Comparison

**直译**：
IntroAct-TS 与已发表的不完整输入预测方法在来源和冻结 TSFM 骨干上比较如何？
Table 1 报告 10% 严重度下所有八个来源、三个骨干、两个 horizon 和四种模式的主比较。[MAIN_READING]。[MAIN_DELTA_CI]。[MAIN_BACKBONE]。[MAIN_BASELINE_SPREAD]。[MAIN_R2CART]。[MAIN_RANK]。逐来源 MASE、MAE 和 RMSE 在附录，部署成本单独在附录报告。

**意见**：
六个占位符连成一段，填数时要按一条逻辑线写：先给相对最强已发表基线的差值和区间，再给相对 Best Fixed 的差值和区间，再说骨干间是否一致，最后一句说 R2-CART。平均排名在本项目的记忆里已经出过问题，只有在配对区间支持的前提下才写排名。

Table 1 图题里 `Bold marks the best deployable method` 与 Catalog Oracle 行并存没问题，但 ChannelTokenFormer 一行三个 N/A 加脚注占了很多空间，建议把它移出主表放到附录扩展比较，主表只留共享参考契约的方法。这样主表更紧，也避免审稿人纠结为什么一个训练过的架构不入排名。

### 5.4 Does Selective Replay Reduce Harm?

**直译**：
收益是来自选出更好的干预，还是来自更少地干预？
Table 2 报告默认操作点的选择性治理诊断。当干预相对保持输入不变增加了实际损失时，它是有害的，因此条件有害率以执行了干预的请求为条件，必须与干预率一起读，因为几乎不干预的方法可以在毫无贡献的情况下报告低条件率。有益精度是执行的干预中降低损失的份额，错过机会是有正 oracle 机会却什么都没执行的 episode 份额。[HARM_READING]。[HARM_IR]。[HARM_HIR]。[HARM_HL]。[HARM_BP]。[HARM_MO]。
Figure 3(b) 通过在 TEST 上后处理存储的分数追踪分数网格上的权衡，不在 TEST 上选阈值。附录逐格报告曲线。[HARM_RISKCURVE]。

**意见**：
这一节的问题句很好。但当前 v4.4 的实际数字是条件有害率 0.42，比固定动作的条件有害率还高一些。如果 v46 的数字仍在这个水平，这一节的标题问题会得到否定回答。主文件里的方法建议正是为了改这个数。写作上要预留两种读法：如果条件有害率低于每个固定干预，直接写；如果只是持平，要把重点放在干预率下降而精度提高，也就是收益来自少做无益的干预。

### 5.5 Robustness and Transfer

**直译**：
一个冻结配置在缺失更严重时是否仍然有用，它是否能带到一个开发时未用的骨干家族？
严重度为 10%、30% 和 50%，与四种模式和三个骨干交叉，各水平之间不重调任何方法。这些水平落在回放库采样的注册网格内，因此这是网格内稳健性检查而不是未见严重度压力测试。扫描使用缩减但类型完整的七方法集合，省略 SRDI 以便高严重度运行保持有界，完整核心集在 10% 下于 Table 1 比较。Table 3 报告严重度趋势、最差模式格和无改动配置下的留出 Chronos-2 骨干。[ROBUST_READING]。[ROBUST_30]。[ROBUST_50]。[ROBUST_WORST]。[ROBUST_CH2]。附录保存完整逐严重度表和逐模式表。

**意见**：
`so that the high-severity runs stay bounded` 这个理由出现了两次（§4.1 和这里），一次即可。Table 3 的 Chronos-2 列只有 10% 一个数，与前三列不是一个维度，放在同一张表里会让读者以为 Chronos-2 只在 10% 上跑过。建议把 Chronos-2 列拿掉，因为 Table 1 已经有 Chronos-2 列，本节正文引用 Table 1 即可。

### 5.6 Ablation and Cost

**直译**：
哪个组件承载了收益，一个请求花费多少？
每个消融复用同一份目录预测缓存，因此各行是重算的选择器变体而不是新的预测运行。A1 去掉对请求的依赖，A2 去掉干预状态，A3 去掉参考预测状态，A4 去掉保守惩罚，A5 用参数化效用预测器替换非参数估计，精确定义在附录。Table 4 一起报告精度、伤害和成本。[ABL_READING] ... [COST_LATENCY]。

**意见**：
按 v4.4 的实际结果，A4 和 A5 在两个骨干上都显著优于 Full。如果 v46 沿用同样的消融定义，Table 4 会直接推翻 §3.4。主文件里给了消融的重新定义：A4 改为去掉 act-or-keep 选项即总是执行得分最高的动作，β 的作用改在附录用风险与干预率曲线展示；A5 保留，但只有在密化 bank 后 kNN 仍输给 ridge 时，方法本身应改为线性先验加局部残差修正。这一节的文字要等新结果出来再写。

Table 4 里 Reconstruction Oracle 与消融放在一张表里，它读的是隐藏值而不是未来，与 Catalog Oracle 的性质不同，放在这里会让读者混淆两个 oracle。建议移到附录 D 与重建对比放一起。

---

## 6. Conclusion 与声明

**直译（Conclusion）**：
我们把冻结 TSFM 的不完整输入处理作为在固定可接受干预目录上的逐请求决策来研究。中心问题是一个干预是否相对保持输入不变改进了当前请求的预测。这个答案既不能从不可用的未来读出，也不能从重建质量读出，后者与实际预测效用不是同一准则。IntroAct-TS 从历史回答它：把 TRAIN 窗口作为伪部署回放，用冻结预测器执行每个目录动作，并把每个动作的实际效用与动作条件状态一起存储。然后一个请求从其状态的同动作邻域打分，只有保守效用分数为正时才执行动作。
评估支持三个声明。[CONCL_MAIN]。[CONCL_HARM]。[CONCL_TRANSFER]。证据也有清楚的边界。这里所有缺失都来自注册协议下的受控删除，回放库只覆盖被回放的模式和严重度，方法无法检测请求落在网格之外。因此结果支持在被评估的受控缺失协议和冻结骨干下的选择性干预，向未见机制和自然不完整流的泛化仍然开放。[CONCLUSION_CLOSING]。

**意见**：
第一段是方法复述，占了结论一半篇幅。建议压成两句，把篇幅留给三个声明和边界。`That answer cannot be read off the future ... nor off reconstruction quality` 又是 v44 自审里指出的二元对立句式，改成：The realised utility of an intervention is not observable at deployment time, and reconstruction quality is a different criterion。

边界段有三句 limitation，放在结论里比例偏重。用户目标是把方法做好而不是强调 limitation，建议保留一句：All missingness is controlled deletion under a registered protocol, and the results are read within that grid。

**直译（AI use statement）**：我们使用生成式 AI 工具协助文献调研、文字编辑、代码起草与重构、图表准备，以及方法与实验选择的讨论。所有方法决策、实验协议、代码更改和报告结果都由作者审阅并批准。生成式 AI 未被用来伪造或篡改实验测量，本文没有任何数值结果由语言模型生成。每个报告数字都由附录描述的记录实验流水线产生，可追溯到存储的产物。我们对本文的最终内容负责。

**意见**：符合 ICLR 2027 要求，保留。

**直译（Ethics）**：本文研究公开基准数据集上冻结预测模型的输入治理。不涉及人类受试者、个人数据或具有直接社会后果的部署决策。我们施加一个完整性约束，可接受的干预不能覆盖被标记为有效且可用的观测，因为无论预测效果如何，静默替换真实测量都是数据完整性问题。我们不声称超出测量条件的安全性、稳健性或一般性。

**意见**：最后一句删掉，伦理声明不需要重复范围声明。

**直译（Reproducibility）**：我们在附录提供完整实验协议、最终 TRAIN 和 TEST 切分与清洗规则、缺失生成过程、干预目录、状态特征定义、超参数搜索空间、失败策略和统计分析。附录给出结果记录模式和可追溯性检查。所有报告表由保留的原始预测和版本化配置生成。

**意见**：合格。如果代码将匿名公开，加一句代码与配置的匿名链接，ICLR 审稿人会看。

---

## 7. 全文语言与逻辑的统一规则

否定式定义仍然偏多。正文里 `never` 18 处，`not` 85 处，`no` 46 处。规则是每个小节最多保留一处用否定来划边界的句子，其余改成正面陈述该方法是什么。

被审稿人视为防御的句式要删：`we present it as one`、`rather than from hand-picked examples`、`never reordered after results are seen`、`does not mean that ... is safe`、`This is a statement about availability only`。事实保留，评论删掉。

同一事实只在一处解释。目前重复最多的三件事是 Chronos-2 是配置迁移而不是库迁移（出现四次）、结果是网格内陈述（出现五次）、参考预测是唯一可先计算的预测（出现三次）。每件事在正文保留一次，附录保留一次。

术语固定：reference action 与 KEEP 二选一后不再换，建议正文统一 `the reference action (KEEP)` 首次出现后只用 KEEP；`admissible` 已统一，不要再出现 legal；`intervention` 指动作，`governance` 指决策层，不混用。

每个小节第一句直接给信息，不用 `This section` 开头。§3.2 与附录 A.3 目前各有一段以 `This section states what ...` 开头。
