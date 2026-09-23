# IntroActTS 完整英文与逐段中文对照

唯一论文入口：`IntroActTS_20260923_v56.tex`。本文档是阅读对照附件，不是另一份论文入口。

标题直译：IntroAct-TS：冻结时间序列基础模型的选择性输入治理。作者：匿名作者，双盲审稿论文。

按当前源文件顺序覆盖正文、声明、附录、全部图表说明。英文保留 LaTeX 引文和交叉引用。公式和数值表为中英文共用，原样嵌入；表头、变体与说明文字在中文中译出。参考文献条目保留原始文献信息，不翻译论文题名。

源文件 SHA-256：`8e17c132c9f9fe5efced4b9f3509a28c6281c54433fd037e7bebf55760d8a7ed`

表内方法名、数据源名、指标缩写、参数符号与数字原样保留，以下给出数值表所用的完整中文读法。

Method/Row 为方法，Variant 为变体，Backbone 为骨干，Comparison 为比较对象，Difference/Δ 为差值，Overall/Macro 为总体或宏平均，Source 为数据源，Subset 为子集，Rule 为规则。Repair rate/Intervention rate/Int. rate 为修复或干预率，Conditional HIR/Cond. HIR 为条件有害干预率，Harmful loss 为伤害损失，Beneficial share 为有益比例，Beneficial precision 为有益精确率，Best share 为最优占比，Available episodes 为可用样例数，Episodes 为样例数，Parents 为父窗口数，Calls 为调用数，Candidates 为候选数。↑ 表示越高越好，↓ 表示越低越好。粗体为最优，下划线为次优，oracle 诊断不参与排序。n/a 为不适用或未定义，以对应图表说明为准。

Mean utility/Mean realised utility 为平均效用或平均已实现效用，Rec. MSE/Rec. MAE 为重建均方误差和平均绝对误差。95% interval 为 95% 区间，Nominal 为名义，p after Holm 为 Holm 校正后 p 值。Score bin 为得分分箱，Pairs 为配对数，lowest/highest score 为最低/最高得分，Penalty strength 为惩罚强度，All severities 为全部严重度。Winner agreement 为最优动作一致率，discordant rate 为排序不一致率，mean within-episode Spearman ρ 为样例内平均 Spearman 秩相关。

Neighbourhood/Local only 为仅局部邻域，Source mean only 为仅数据源均值，No retrieval 为无检索，Linear utility model 为线性效用模型，No action conditioning 为无动作条件，No execution gate 为无执行门控，No intervention state 为无干预状态，No reference forecast 为无参考预测特征，Full/FULL 为完整方法。Mean only 为仅均值，Linear 为线性，Random 为随机。identical by construction 为按构造相同。

P1 Point 为点缺失，P2 Target Block 为目标块缺失，P3 Shared Block 为共享块缺失，P4 Tail 为尾部缺失，Avg. Rank 为平均排名。all eight 为全部八源，without Exchange 为去除 Exchange，vs 为相对于，fixed 为固定策略。No-op 为不操作，Low/High opportunity 为低/高机会，Stratum 为层，Boundary factor 为边界倍数，Share of episodes 为样例占比，Median 为中位数，90th pct. 为第 90 百分位。

Bank fraction 为库保留比例，Mask realisation 为掩码实现，primary seed 为主种子，second/third realisation 为第二/第三实现，Spread over the three realisations 为三个实现的极差。Paired difference against IntroAct-TS 的方向以图注为准，为 IntroAct-TS 减对应方法。Target α 为目标 α，Realised harm 为实际伤害。

Offline work 为离线工作，Mean latency 为平均延迟，P95 为第 95 百分位延迟，Max/max 为最大值，median 为中位数，Calls/request 为每请求调用数，ms 为毫秒，s 为秒，min 为分钟。Mean stage time 为各阶段平均时间，Reference forecast 为参考预测，In-context candidates 为上下文候选，SAITS candidate 为 SAITS 候选，Cheap candidates 为低成本候选，Plausibility guard 为合理性检查，Retrieval and scoring 为检索与评分，Selected forecast 为所选预测。

## 对照 001

```latex
Missing observations can change how a frozen time-series foundation model responds to its
input. Filling a gap may improve reconstruction while increasing forecasting error, so a
serving system must decide both which repair to use and whether to repair at all.
We introduce \introact{}, which learns this decision from the forecasting utilities of
repairs executed on historical windows. It combines action-specific local estimates with
source-level utility means and executes a repair only when its penalised score exceeds a
threshold. On eight sources and three frozen backbones, it reaches 1.425 source-macro MASE
against 1.576 for unchanged input and 1.445 for the strongest fixed policy, while repairing
$55.2\%$ of requests. The aggregate error is lowest among the compared deployable methods,
although Source Fixed performs better on Bolt. Removing the execution gate lowers MASE to
1.414 and raises harmful loss from 0.0340 to 0.0515, identifying an accuracy and harm tradeoff.
An additional evaluation on two sources excluded from the current design cycle supports
improvement over unchanged input on two backbones, without establishing an advantage over
the best fixed repair. The main comparisons remain exploratory because earlier development
used the same TEST block.
```

**中文直译**

缺失观测会改变冻结时间序列基础模型对输入的响应。填补缺口可能提高重建精度，却增加预测误差，因此服务系统需要同时决定采用哪种修复以及是否修复。我们提出 IntroAct-TS，利用历史窗口上执行修复所产生的预测效用学习这一决策。该方法结合各动作的局部估计和数据源层面的效用均值，仅在惩罚后得分超过阈值时执行修复。在八个数据源和三个冻结骨干上，其数据源宏平均 MASE 为 1.425，保持输入不变为 1.576，最强固定策略为 1.445，同时修复 55.2% 的请求。其总体误差在所比较的可部署方法中最低，不过 Source Fixed 在 Bolt 上表现更好。移除执行门控使 MASE 降至 1.414，同时使伤害损失从 0.0340 升至 0.0515，体现了精度与伤害之间的权衡。在本轮设计排除的两个数据源上进行的额外评估，支持其在两个骨干上优于保持输入不变，但未确立相对于最佳固定修复的优势。由于早期开发使用过同一 TEST 块，主要比较仍属于探索性结果。

## 对照 002

```latex
\section{Introduction}
```

**中文直译**

引言

## 对照 003

```latex
Time-series foundation models learn temporal patterns from large collections of series and
use them to forecast new tasks without task-specific
retraining~\citep{ansari2024chronos,chronosbolt2025,das2024timesfm,woo2024moirai,chronos2_2025}.
In deployed forecasting systems, sensor outages and delayed measurements can leave gaps in
the context supplied to a model~\citep{chen2024bitgraph,peng2025s4m}. The system can pass
this context to the model's native input pipeline or fill the gaps first. These choices
can produce different forecasts even when the forecasting model remains unchanged.
```

**中文直译**

时间序列基础模型从大规模序列集合中学习时间模式，无需针对任务重新训练即可预测新任务。在实际部署的预测系统中，传感器故障和测量延迟可能使提供给模型的上下文出现缺口。系统可以将该上下文传入模型的原生输入流程，也可以先填补缺口。即使预测模型保持不变，这些选择也可能产生不同预测。

## 对照 004

```latex
We study how to choose an input repair for each incomplete forecasting request while keeping
the forecaster fixed. A useful repair must improve the forecast, preserve valid observations
and use only information available when the request arrives. Reconstruction accuracy alone
does not determine this benefit. A filled value may resemble the missing observation yet
change the model's forecast unfavourably. Keeping the input is therefore part of the decision,
alongside choosing among admissible repairs.
```

**中文直译**

我们研究如何在保持预测器固定的条件下，为每个不完整预测请求选择输入修复。有用的修复需要改善预测，保留有效观测，并且仅使用请求到达时可获得的信息。重建精度本身不能决定这种收益。填充值可能接近缺失观测，却使模型预测变差。因此，决策不仅要从可用修复中选择，也要包含保持输入不变这一选项。

## 对照 005

```latex
Existing methods address important parts of this problem. Imputation estimates missing
values from temporal and cross-channel structure~\citep{cao2018brits,tashiro2021csdi,du2023saits}.
Missingness-aware forecasting incorporates the observation pattern into a trained
predictor~\citep{chen2024bitgraph,peng2025s4m}. Task-oriented imputation assesses repairs
through downstream performance~\citep{wang2024taskoriented,hao2025toivsf,xu2026srdi}, and
TATO selects a transformation pipeline for a frozen forecaster at the domain
level~\citep{qiu2026tato}. Our question concerns the decision for an individual request,
including when the available repairs should be declined. Historical windows provide
supervision because their realised futures allow each repair to be compared with unchanged
input under the same forecasting model.
```

**中文直译**

现有方法解决了这一问题的重要部分。插补利用时间和跨通道结构估计缺失值。缺失感知预测将观测模式纳入训练后的预测器。面向任务的插补通过下游表现评价修复，TATO 则在领域层面为冻结预测器选择变换流程。我们关注单个请求的决策，包括何时应拒绝可用修复。历史窗口可以提供监督，因为其已经实现的未来允许在同一预测模型下，将每种修复与保持输入不变进行比较。

## 对照 006

```latex
\paragraph{Challenges.}
```

**中文直译**

挑战。

## 对照 007

```latex
Two difficulties remain when using historical outcomes for a new request. First, relevant
local examples may be scarce, while a source-wide average cannot distinguish requests within
that source. Utility estimation must account for both the relevance and the amount of
historical evidence. Second, reducing average error does not by itself limit damage from
unhelpful repairs. A decision rule must assess whether to execute its recommendation and
report the resulting accuracy and harm separately. The future target is unavailable at
decision time, so both choices must rely on observable request information.
```

**中文直译**

利用历史结果处理新请求仍有两个困难。第一，相关局部样本可能稀少，而数据源整体均值无法区分该源内部的请求。效用估计需要兼顾历史证据的相关性与数量。第二，降低平均误差本身不能限制无益修复造成的损害。决策规则需要判断是否执行其建议，并分别报告由此得到的精度与伤害。决策时无法获得未来目标，因此这两项选择都必须依赖可观测的请求信息。

## 对照 008

```latex
\paragraph{Contributions.}
```

**中文直译**

贡献。

## 对照 009

```latex
\item We introduce \introact{}, a decision layer that combines local and source-level
estimates of each repair's forecasting utility, then gates execution relative to unchanged input.
```

**中文直译**

我们提出 IntroAct-TS 决策层，结合每种修复的局部和数据源层面预测效用估计，再相对于保持输入不变决定是否执行。

## 对照 010

```latex
\item We formulate selective repair under a frozen forecaster and define paired utility
and harmful loss to distinguish prediction improvements from repair-induced degradation.
Historical full-action replay supplies supervision without using the new request's future.
```

**中文直译**

我们形式化冻结预测器下的选择性修复，并定义配对效用和伤害损失，以区分预测改善与修复导致的退化。历史全动作回放提供监督，无需使用新请求的未来。

## 对照 011

```latex
\item We evaluate the method on eight sources and three backbones, with nine deployable
comparisons and an additional two-source evaluation. The results support improvements over
unchanged input and identify an accuracy and harm tradeoff, with backbone-dependent differences
against fixed policies.
```

**中文直译**

我们在八个数据源和三个骨干上评价该方法，包含九个可部署对照以及额外的双数据源评估。结果支持其优于保持输入不变，并揭示精度与伤害的权衡，相对于固定策略的差异则取决于骨干。

## 对照 012

```latex
Figure~\ref{fig:concept} illustrates the decision and the historical evidence available to it.
```

**中文直译**

图 \ref{fig:concept} 展示了这一决策及其可用的历史证据。

## 对照 013

```latex
\caption{Selective repair for incomplete forecasting requests. The left panel illustrates
requests for which different actions may be appropriate. These examples are schematic.
Historical replay records the forecasting utility of each admissible action. Online
selection retrieves evidence for the current request and either executes a repair or
retains the reference forecast.}
```

**中文直译**

不完整预测请求的选择性修复。左图示意不同请求可能适合不同动作。这些是示意性例子。历史回放记录每个可用动作的预测效用。在线选择为当前请求检索证据，执行修复或保留参考预测。

## 对照 014

```latex
\paragraph{Related work.}
```

**中文直译**

相关工作。

## 对照 015

```latex
Appendix~\ref{sec:related} reviews incomplete-series modelling, input adaptation for frozen
forecasters and selective decision making. These directions motivate the repair catalog,
the forecasting-utility objective and the option to retain the original input.
```

**中文直译**

附录 \ref{sec:related} 回顾不完整序列建模、冻结预测器的输入适配和选择性决策。这些方向分别启发了修复目录、预测效用目标以及保留原始输入的选项。

## 对照 016

```latex
\section{Problem Formulation}
```

**中文直译**

问题定义

## 对照 017

```latex
Let $X\in\mathbb{R}^{C\times L}$ denote a context with $C$ channels and length $L$,
and let $M\in\{0,1\}^{C\times L}$ identify its observed entries. The future target
$Y\in\mathbb{R}^{C\times H}$ is unavailable when the decision is made. A fixed inference
pipeline $F$ includes the forecaster and its native preprocessing. Passing the incomplete
context through this pipeline defines the reference forecast.
```

**中文直译**

设 X∈ℝ^{C×L} 为具有 C 个通道、长度为 L 的上下文，M∈{0,1}^{C×L} 标识已观测项。决策时无法获得未来目标 Y∈ℝ^{C×H}。固定推理流程 F 包含预测器及其原生预处理。将不完整上下文传入该流程所得到的结果定义为参考预测。

## 对照 018

```latex
The system chooses from a fixed action catalog $\calA=\{a_0,a_1,\ldots,a_J\}$.
Action $a$ produces $X^a=T_a(X,M)$, and $a_0$ keeps the input unchanged.
Write $\calA^+=\calA\setminus\{a_0\}$ and let $\calA(X,M)\subseteq\calA$ contain
the actions admissible for the request. Write $\calA^+(X,M)=\calA(X,M)\setminus\{a_0\}$.
Every admissible repair preserves entries with
$M=1$. Repaired values must remain within the visible target range expanded by three robust
scales. An unsupported or failed repair is excluded, and $a_0$ remains available.
```

**中文直译**

系统从固定动作目录 A={a₀,a₁,…,aⱼ} 中选择。动作 a 产生 Xᵃ=Tₐ(X,M)，a₀ 保持输入不变。记 A⁺=A\{a₀}，令 A(X,M)⊆A 包含该请求可用的动作，并记 A⁺(X,M)=A(X,M)\{a₀}。所有可用修复都保留 M=1 的条目。修复值必须位于可见目标值域向外扩展三个稳健尺度后的范围内。不受支持或执行失败的修复被排除，a₀ 始终可用。

## 对照 019

```latex
Let $\loss$ denote episode-level MASE, for which lower is better. The utility of an action is
```

**中文直译**

令 ℓ 表示单个评估样例的 MASE，数值越低越好。动作效用定义如下。

**共用公式**

```latex
\begin{equation}
g_a=\loss\!\left(F(X^{a_0}),Y\right)-\loss\!\left(F(X^a),Y\right).
\label{eq:utility}
\end{equation}
```

## 对照 020

```latex
Positive utility indicates improvement over the reference. A policy $\pi$ chooses an
admissible action from the visible request and training history, without observing $Y$.
Its objective is to minimise expected forecasting loss,
```

**中文直译**

正效用表示相对于参考预测有所改善。策略 π 在不观测 Y 的前提下，根据可见请求和训练历史选择可用动作。其目标是最小化期望预测损失。

**共用公式**

```latex
\begin{equation}
\min_{\pi}\;\mathbb{E}_{(X,M,Y)\sim\mathcal D}
 \left[\loss\!\left(F(X^{\pi(X,M)}),Y\right)\right],
\qquad \pi(X,M)\in\calA(X,M).
\label{eq:objective}
\end{equation}
```

## 对照 021

```latex
Here $\mathcal D$ denotes the deployment request distribution. The returned output is the
forecast of the selected input. Before selection, the policy may obtain the reference
forecast but may not inspect repair-specific forecasts. Serving therefore uses at most two
forecasting-backbone calls. Candidate construction has a separate cost.
We also report harmful loss, $\max(0,-g_{\pi(X,M)})$, averaged over requests, to distinguish
net accuracy from degradation caused by executed repairs. Keeping the input has zero harm.
```

**中文直译**

这里 D 表示部署请求的分布。返回的输出是所选输入的预测。选择前，策略可以获得参考预测，但不能查看各修复对应的预测。因此，一次服务至多调用预测骨干两次。候选构造另计成本。我们还报告在请求上平均的伤害损失 max(0,−g_{π(X,M)})，以区分净精度与执行修复造成的退化。保持输入不变时伤害为零。

## 对照 022

```latex
\section{Method}
```

**中文直译**

方法

## 对照 023

```latex
\introact{} uses completed historical windows to estimate how each repair will affect a new
forecast. Replay pairs request states with realised action utilities. A local estimator then
combines nearby outcomes with the source's average utility for that action. An execution
gate uses this estimate and its dispersion to choose between the recommended repair and
the reference forecast. Figure~\ref{fig:arch} shows the information passed between these stages.
```

**中文直译**

IntroAct-TS 利用已完成的历史窗口估计每种修复对新预测的影响。回放将请求状态与已实现的动作效用配对。局部估计器随后结合邻近结果与该数据源中该动作的平均效用。执行门控利用这一估计及其离散程度，在建议修复与参考预测之间选择。图 \ref{fig:arch} 展示了这些阶段传递的信息。

## 对照 024

```latex
\caption{Architecture of \introact{}. Historical replay stores observable action states
and realised forecasting utilities. For a new request, the reference forecast and candidate
inputs supply the states used for same-action retrieval. Local utility estimates are
combined with source-level means before the execution gate selects a repair or returns
the reference forecast. Future targets are used only for historical supervision and
subsequent evaluation.}
```

**中文直译**

IntroAct-TS 架构。历史回放保存可观测的动作状态和已实现的预测效用。对于新请求，参考预测与候选输入提供同动作检索所需的状态。局部效用估计与数据源层面均值结合后，执行门控选择修复或返回参考预测。未来目标仅用于历史监督和后续评估。

## 对照 025

```latex
\subsection{Historical Full-Action Replay}
```

**中文直译**

历史全动作回放

## 对照 026

```latex
The quantity that decides the action, $g_a$, depends on $Y$ and is not observable online, but it
is computable for a historical window whose target is already part of the available history.
Take such a window $i$, inject the registered missingness protocol to obtain $(X_i, M_i)$,
materialise every action, and execute the frozen pipeline on each version. The realised utility
of action $a$ on window $i$ is
```

**中文直译**

决定动作的量 gₐ 依赖 Y，在线时无法观测，但对于目标已经属于可用历史的窗口，可以计算它。取这样的窗口 i，按照登记的缺失协议注入缺失，得到 (Xᵢ,Mᵢ)，构造每个动作的输入，并在各版本上执行冻结流程。窗口 i 上动作 a 的已实现效用如下。

**共用公式**

```latex
\begin{equation}
  g_{i,a} \;=\; \loss\!\left(F(T_{a_0}(X_i, M_i)),\, y_i\right)
  \;-\; \loss\!\left(F(T_{a}(X_i, M_i)),\, y_i\right).
  \label{eq:replay-gain}
\end{equation}
```

## 对照 027

```latex
Both forecasts are evaluated against the same realised future. Their loss difference records
the action's forecasting effect on that historical window.
```

**中文直译**

两个预测针对同一已实现未来进行评价。其损失差记录该动作在这一历史窗口上的预测效果。

## 对照 028

```latex
A utility label informs a new decision only if the historical window can be matched to the
deployment request, so each outcome is stored together with a retrieval state. The state is
action conditioned:
```

**中文直译**

只有历史窗口能够与部署请求匹配时，效用标签才能指导新决策，因此每个结果都与检索状态一起存储。该状态以动作为条件，定义如下。

**共用公式**

```latex
\begin{equation}
  z_{i,a} = \phi(X_i, M_i, X_i^{a}, p_i^{0}),
  \qquad p_i^{0} = F(X_i^{a_0}),
  \qquad X_i^{a} = T_a(X_i, M_i).
  \label{eq:state}
\end{equation}
```

## 对照 029

```latex
It may use the reference forecast $p_i^0$, which the
protocol already permits, and it never uses the forecast of a non-selected candidate. The
replay bank is $\calB = \{(z_{i,a}, a, g_{i,a})\}$, built once from TRAIN history and then
frozen. Deployment reads it and never writes to it.
```

**中文直译**

它可以使用协议允许的参考预测 pᵢ⁰，且从不使用未选候选的预测。回放库 B={(zᵢ,ₐ,a,gᵢ,ₐ)} 由 TRAIN 历史一次性构建并冻结。部署时只读取，不写入。

## 对照 030

```latex
Two properties of the bank set the scope of the method. A utility measured with one revision
of one model does not describe another, so the bank is built and held per frozen backbone
revision, and serving a new backbone family means rebuilding it. The bank also covers only the
missingness protocol registered in advance, which makes it a discrete grid over patterns and
severities.
Appendix~\ref{app:replay} reports what each restriction costs.
```

**中文直译**

回放库的两个属性限定了方法范围。某个模型版本上测得的效用不适用于另一版本，因此每个冻结骨干版本分别构建和保留回放库，服务新的骨干系列需要重建。回放库也仅覆盖预先登记的缺失协议，形成模式和严重度上的离散网格。附录 \ref{app:replay} 报告这两项限制的成本。

## 对照 031

```latex
Using these records for a new request rests on one assumption: nearby action-conditioned
states have sufficiently similar utilities to guide selection. Section~\ref{sec:exp-ablation}
examines this assumption through the estimation ablations. The estimator itself is defined next.
```

**中文直译**

将这些记录用于新请求依赖一个假设，即邻近的动作条件状态具有足够相似的效用，可以指导选择。第 \ref{sec:exp-ablation} 节通过估计消融检验这一假设。下面定义估计器。

## 对照 032

```latex
\subsection{Action-Conditioned Local Utility Estimation}
```

**中文直译**

动作条件局部效用估计

## 对照 033

```latex
The estimator is a weighted average of the recorded utilities of the same action on nearby
states, in a fixed standardised feature space. The state $z_a$ of \eqref{eq:state} carries
twenty-two numbers in four groups: how the request is incomplete, what the observed part of the
target channel looks like, how $X^{a}$ differs from a gap-interpolated baseline of the visible
reference at the positions the repair changes, and what the reference forecast
$p_0 = F(X^{a_0})$ looks like. The baseline is a pure function of the visible reference: it
uses no model and no future labels, so the third group varies across actions without leaking
target information. Retrieval is not
restricted to a source or a horizon. The neighbourhood is meant to match on the mask geometry,
the visible context and the reference forecast. Appendix~\ref{app:features} is the canonical
list, with the window lengths and the normalisation, which is fitted on the replay bank only.
```

**中文直译**

估计器在固定标准化特征空间中，对邻近状态下同一动作的已记录效用加权平均。公式 \eqref{eq:state} 中的状态 zₐ 包含四组共二十二个数值，描述请求的缺失情况、目标通道可见部分的形态、在修复改变的位置上 Xᵃ 与可见参考的缺口插值基线有何差异，以及参考预测 p₀=F(X^{a₀}) 的形态。该基线仅由可见参考决定，不使用模型或未来标签，因此第三组特征可以随动作变化而不泄露目标信息。检索不限制数据源或预测长度。邻域用于匹配掩码几何、可见上下文和参考预测。附录 \ref{app:features} 给出完整列表、窗口长度以及仅在回放库上拟合的标准化。

## 对照 034

```latex
Retrieval is performed separately for each action. For action $a$, the neighbourhood
$\calN_a$ contains the $k$ bank records whose recorded action is $a$ and whose states are
closest to $z_a$ in standardised Euclidean distance. Each neighbour receives the weight
```

**中文直译**

每个动作分别检索。对于动作 a，邻域 Nₐ 包含回放库中动作同为 a，且与 zₐ 的标准化欧氏距离最近的 k 条记录。每个邻居获得如下权重。

**共用公式**

```latex
\begin{equation}
  w_i \;=\; \exp\!\left(-d_i / h_a\right),
  \qquad
  h_a \;=\; \operatorname{median}_{i \in \calN_a} d_i \;+\; \epsilon ,
  \label{eq:weights}
\end{equation}
```

## 对照 035

```latex
so closer records contribute more, and the bandwidth comes from the query neighbourhood
itself. The constant $\epsilon$ handles zero distances. Records generated from the same
parent window share their context and are not independent evidence, so the neighbourhood
first collapses to one entry per distinct parent, whose utility is the mean of its entries and
whose distance is the smallest of theirs. Let $\calP_a$ be the set of those parents and
$\bar g_{p,a}$ the utility of parent $p$. Over them the estimator computes a local mean
utility, a local dispersion that measures how much the neighbouring outcomes disagree, and the
count of distinct parents that produced them,
```

**中文直译**

因而较近的记录贡献更大，带宽由查询邻域本身决定。常数 ε 处理零距离。同一父窗口生成的记录共享上下文，不构成独立证据，因此先将邻域合并为每个不同父窗口一条记录，其效用取所属记录均值，距离取最小值。令 Pₐ 为这些父窗口的集合，ḡₚ,ₐ 为父窗口 p 的效用。估计器由此计算局部平均效用、衡量邻近结果分歧的局部离散程度，以及产生这些结果的不同父窗口数量。

**共用公式**

```latex
\begin{equation}
  \hat\mu_a \;=\; \frac{\sum_{p \in \calP_a} w_p\, \bar g_{p,a}}{\sum_{p \in \calP_a} w_p},
  \qquad
  \hat\sigma_a^{2} \;=\; \frac{\sum_{p \in \calP_a} w_p\, (\bar g_{p,a} - \hat\mu_a)^{2}}{\sum_{p \in \calP_a} w_p},
  \qquad
  n_{\mathrm{eff},a} \;=\; \left| \calP_a \right| .
  \label{eq:local-moments}
\end{equation}
```

## 对照 036

```latex
The local mean can vary when its neighbourhood holds little independent evidence. The bank
also records how the same action performed across the request's source. This source estimate
uses more history but cannot distinguish requests within that source. Write $m_{s,a}$ for the
mean utility over the source's admissible replay records, matching the statistic used by the
Source Fixed comparison. The estimator combines the local and source estimates,
```

**中文直译**

当邻域包含的独立证据较少时，局部均值可能波动。回放库还记录同一动作在请求所属数据源上的表现。该源估计使用更多历史，但无法区分源内请求。记 mₛ,ₐ 为该源可用回放记录上的平均效用，与 Source Fixed 对照使用的统计量一致。估计器如下结合局部估计与数据源估计。

**共用公式**

```latex
\begin{equation}
  \tilde\mu_a \;=\; \frac{n_{\mathrm{eff},a}\,\hat\mu_a \;+\; \lambda\, m_{s,a}}
                          {n_{\mathrm{eff},a} \;+\; \lambda} ,
  \label{eq:pooled}
\end{equation}
```

## 对照 037

```latex
where $\lambda$ is the weight assigned to the source estimate relative to the distinct
parents in the neighbourhood. At $\lambda=0$ the estimate is local. At
$\lambda=\infty$ it is the source mean. The latter shares its utility statistic with
Source Fixed, while the two policies can still choose different actions when the fixed
action is unavailable on a request. Both estimator endpoints are in the registered search
grid, and \S\ref{sec:exp-ablation} measures their outcomes on TEST.
```

**中文直译**

λ 表示相对于邻域内不同父窗口，赋予数据源估计的权重。λ=0 时估计完全局部化，λ=∞ 时采用数据源均值。后者与 Source Fixed 使用相同效用统计量，但固定动作在某个请求上不可用时，两种策略仍可能选择不同动作。两个估计端点都包含在登记的搜索网格内，第 \ref{sec:exp-ablation} 节测量其 TEST 结果。

## 对照 038

```latex
The neighbourhood is defined by distance alone, and no threshold marks a request as outside the
replay support, so the estimator returns a value for every request it receives.
Section~\ref{sec:exp-robust} and Appendix~\ref{app:scope} treat the resulting scope as a
within-grid statement.
```

**中文直译**

邻域只由距离定义，没有阈值将请求标为回放支持范围之外，因此估计器对接收的每个请求都返回数值。第 \ref{sec:exp-robust} 节与附录 \ref{app:scope} 将相应结论限定在网格内部。

## 对照 039

```latex
\subsection{Conservative Act-or-Keep Decision}
```

**中文直译**

保守的执行或保持决策

## 对照 040

```latex
A positive estimate is not sufficient evidence for executing an action, because the
neighbourhood may be small or internally inconsistent. The decision therefore penalises
dispersion in proportion to how little evidence the estimate rests on,
```

**中文直译**

正估计不足以支持执行动作，因为邻域可能很小或内部不一致。因此，决策对离散程度施加惩罚，证据越少，惩罚越大。

**共用公式**

```latex
\begin{equation}
  S_a \;=\; \tilde\mu_a \;-\; \beta\, \frac{\hat\sigma_a}{\sqrt{n_{\mathrm{eff},a} + \lambda}},
  \qquad a \in \calA^{+}(X,M),
  \label{eq:score}
\end{equation}
```

## 对照 041

```latex
where $\beta$ controls the dispersion penalty. The denominator uses the distinct-parent
count and pooling weight from \eqref{eq:pooled}. This empirical score is not a calibrated
confidence bound. The highest-scoring admissible repair is executed when its score exceeds
$\tau$. Otherwise, including when no repair is admissible, $a^{\star}=a_0$. Because utility is
defined relative to the reference action in \eqref{eq:utility}, a repair displaces
\textsc{Keep} only when its penalised estimate clears $\tau$ on the same scale as the
forecasting error it is trying to reduce.
```

**中文直译**

β 控制离散惩罚。分母使用公式 \eqref{eq:pooled} 中的不同父窗口数和汇聚权重。该经验得分不是经过校准的置信界。当最高分的可用修复得分超过 τ 时执行该修复。否则，包括没有可用修复时，a*=a₀。由于公式 \eqref{eq:utility} 将效用定义为相对于参考动作的收益，修复只有在其惩罚后估计超过 τ 时才能替代 KEEP，且该得分与其试图降低的预测误差使用同一尺度。

## 对照 042

```latex
The main comparison uses $\tau=0$. A separate training-side calibration block selects
higher thresholds for specified clipped-harm tolerances. Its conformal interpretation
requires exchangeability, which is not established for these temporal blocks.
Appendix~\ref{app:layout-details} gives the calibration rule, fallback and assumptions.
```

**中文直译**

主比较采用 τ=0。独立的训练侧校准块为指定的截断伤害容忍度选择更高阈值。其保形解释要求可交换性，而这些时间块并未确立该条件。附录 \ref{app:layout-details} 给出校准规则、回退方式和假设。

## 对照 043

```latex
The hyperparameters are selected on the replay bank by leave-one-parent-out cross-validation.
A harmful-rate cap restricts admissible configurations, and a paired one-standard-error rule
chooses the least-intervening configuration near the minimum MASE. The full grid and fallback
are given in Appendix~\ref{app:layout-details}.
```

**中文直译**

超参数通过回放库上的留一父窗口交叉验证选择。伤害率上限限制可用配置，配对的一个标准误规则在接近最低 MASE 的配置中选择干预最少者。完整网格及回退规则见附录 \ref{app:layout-details}。

## 对照 044

```latex
The reference action is always available, so the rule always returns a forecast. It has no way
to detect that a request lies outside the replay support, so it applies to the registered
missingness grid and the results should not be read as out-of-grid generalisation.
```

**中文直译**

参考动作始终可用，因此该规则总能返回预测。它无法检测请求是否超出回放支持范围，因而适用范围是登记的缺失网格，不能将结果理解为网格外泛化。

## 对照 045

```latex
\subsection{Deployment Procedure and Cost}
```

**中文直译**

部署流程与成本

## 对照 046

```latex
A request is served in two stages. The first executes the reference action to obtain $p_0$,
materialises the candidate input versions and forms the states $z_a$. The second retrieves the
same-action neighbourhoods from the frozen bank, evaluates $S_a$ for each admissible repair,
executes $a^{\star}$ and returns its forecast, which is the reference forecast when
$a^{\star} = a_0$.
```

**中文直译**

请求服务分两个阶段。第一阶段执行参考动作得到 p₀，构造候选输入并形成状态 zₐ。第二阶段从冻结库中检索同动作邻域，对每个可用修复计算 Sₐ，执行 a* 并返回其预测。a*=a₀ 时返回参考预测。

## 对照 047

```latex
Each request uses one forecasting-backbone call for the reference action plus one more if an
intervention is executed, and the returned forecast is always one call of the unchanged $F$ on
one executed input version. Three of the five interventions build their candidate with a model
of their own, two by calling a frozen in-context imputation model and one by calling the
trained imputer, and all of that is paid before the decision.
Appendix~\ref{app:calls} keeps the one-off bank construction, candidate materialisation, the
backbone call and retrieval overhead in separate columns.
```

**中文直译**

每个请求为参考动作调用预测骨干一次，执行干预时再调用一次。返回的预测始终来自未改变的 F 对某个已执行输入版本的一次调用。五种干预中有三种使用自己的模型构建候选，其中两种调用冻结的上下文插补模型，一种调用训练后的插补器，这些成本均发生在决策之前。附录 \ref{app:calls} 分别列出一次性的回放库构建、候选构造、骨干调用和检索开销。

## 对照 048

```latex
\section{Experiments}
```

**中文直译**

实验

## 对照 049

```latex
\subsection{Evaluation Protocol}
```

**中文直译**

评估协议

## 对照 050

```latex
The recorded evaluation covers eight sources, ETTh1, ETTh2, ETTm1, ETTm2, Electricity,
Exchange, Traffic and Weather, with three frozen backbones. These are
Chronos-Bolt~\citep{chronosbolt2025}, TimesFM-2.5~\citep{das2024timesfm} and
Chronos-2~\citep{chronos2_2025}. A separate replay bank is built for each backbone using the
same selection procedure. Context length is $L=512$, with horizons $H \in \{96,192\}$.
The main comparison uses $10\%$ missingness across four deterministic patterns.
Additional evaluations use $30\%$ and $50\%$ missingness without retuning.
Appendix~\ref{app:data-protocol} defines the masks and metrics.
```

**中文直译**

已记录的评估覆盖 ETTh1、ETTh2、ETTm1、ETTm2、Electricity、Exchange、Traffic 和 Weather 八个数据源，以及 Chronos-Bolt、TimesFM-2.5 和 Chronos-2 三个冻结骨干。每个骨干使用同一选择流程构建独立回放库。上下文长度 L=512，预测长度 H∈{96,192}。主比较在四种确定性模式下采用 10% 缺失率。额外评估采用 30% 和 50% 缺失率，不重新调参。附录 \ref{app:data-protocol} 定义掩码与指标。

## 对照 051

```latex
The catalog contains \textsc{Keep} and five repairs. Best Fixed, Source Fixed and Fixed SAITS
test whether a fixed policy is sufficient. R2-CART selects an action for each request from
the same state features, testing a simpler alternative to utility estimation. TATO searches
for a transformation pipeline per domain. TimesNet, PSW-I and T1 apply trained imputers to
every request. These comparisons assess alternative ways to adapt the input under the
recorded training and search budgets.
Appendix~\ref{app:baseline-config} specifies their implementations, and the catalog oracle
reads future targets and serves only as a diagnostic.
```

**中文直译**

动作目录包含 KEEP 和五种修复。Best Fixed、Source Fixed 和 Fixed SAITS 检验固定策略是否足够。R2-CART 利用相同状态特征为每个请求选择动作，检验效用估计的一种更简单替代方案。TATO 为每个领域搜索变换流程。TimesNet、PSW-I 和 T1 对每个请求应用训练后的插补器。这些比较在已记录的训练和搜索预算下评价不同输入适配方式。附录 \ref{app:baseline-config} 说明其实现，目录 oracle 读取未来目标，仅用于诊断。

## 对照 052

```latex
Each source is split chronologically with an $L+H$ purge, and TRAIN is partitioned into the
replay bank and an internal evaluation block. The reported evaluation holds 95 parents and 760
episodes per backbone at each severity, MASE is averaged equally across sources with RMSSE as
a secondary metric, and paired bootstrap intervals cluster on parents.
Appendices~\ref{app:splits} and \ref{app:metric-conventions} give the partitions and the
aggregation.
```

**中文直译**

每个数据源按时间划分，并设置 L+H 的隔离间隔，TRAIN 进一步划分为回放库与内部评价块。在每种严重度下，每个骨干的评估包含 95 个父窗口和 760 个样例。MASE 按数据源等权平均，RMSSE 为次要指标，配对自助法区间按父窗口聚类。附录 \ref{app:splits} 和 \ref{app:metric-conventions} 说明划分与聚合。

## 对照 053

```latex
Earlier evaluations on this TEST block informed the current design, so these comparisons
are exploratory. The additional sources in \S\ref{sec:exp-main} were registered before their
current evaluation. Their TEST periods were excluded from decisions in this design cycle,
while their TRAIN periods supplied the replay banks and training-side selection.
```

**中文直译**

该 TEST 块的早期评估影响了当前设计，因此这些比较具有探索性。第 \ref{sec:exp-main} 节的额外数据源在本次评估之前登记。其 TEST 时段未用于本轮设计决策，而 TRAIN 时段用于回放库和训练侧选择。

## 对照 054

```latex
\subsection{Variation in Repair Utility}
```

**中文直译**

修复效用的变化

## 对照 055

```latex
Both the preferred repair and the value of repairing vary by request.
Figure~\ref{fig:utility}(a,b) reports oracle-best shares from $11.1\%$ to $24.8\%$, with KEEP
best on $19.3\%$ of episodes. The oracle reaches 1.258 MASE versus 1.576 for KEEP, showing
the available selection opportunity under the catalog. This oracle uses future outcomes.
On Bolt, reconstruction and forecasting winners agree on $19.3\%$ of episodes, with
$44.5\%$ pairwise rank disagreement and mean within-episode correlation 0.12.
These diagnostics motivate forecasting utility as supervision without establishing that
reconstruction information is unhelpful in every setting. Appendix~\ref{app:recutils}
reports the rankings, and Figure~\ref{fig:cases} gives retrospective examples.
```

**中文直译**

最合适的修复及修复价值均随请求变化。图 \ref{fig:utility}(a,b) 的 oracle 最优动作占比为 11.1% 至 24.8%，KEEP 在 19.3% 的样例上最佳。Oracle 的 MASE 为 1.258，KEEP 为 1.576，说明该目录提供了选择空间。该 oracle 使用未来结果。在 Bolt 上，重建与预测的最优动作仅在 19.3% 的样例上一致，两两排序不一致率为 44.5%，样例内平均相关系数为 0.12。这些诊断支持以预测效用作为监督，但不能说明重建信息在所有情形下都无用。附录 \ref{app:recutils} 报告排序，图 \ref{fig:cases} 给出回顾性案例。

## 对照 056

```latex
\caption{Repair utility, decision harm and severity sensitivity, all under frozen
configurations and recorded point estimates rather than intervals. (a) Oracle-best action
frequency, filled, against the share of admissible episodes the action improves, hatched.
(b) Mean utility relative to KEEP, positive meaning lower MASE. (c) Harmful loss, the error
repairs added, averaged over all requests. (d) Repair frequency, filled, against the harmful
share among executed repairs, hatched, which is undefined for KEEP. (e) Source-macro MASE at
10, 30 and 50\% missingness with nothing retuned. (f) Largest MASE increase over KEEP in any
pattern, backbone and severity cell. Action codes are K, F, S, M, R, A for KEEP, forward-fill,
single and multivariate TS-ICL, context ridge and SAITS. Method codes are K, BF, C, A, T, IA
for KEEP, Best Fixed, R2-CART, Fixed SAITS, TATO and IntroAct-TS. Panels (a--d) use 10\%
missingness and method-level means average three backbones, two horizons and four patterns with equal
source weight. Action shares and utilities use the available episodes for each action. Table~\ref{tab:heterogeneity} keeps the action values and
Appendices~\ref{app:gate-controls} and \ref{app:severity-full} the breakdowns.}
```

**中文直译**

修复效用、决策伤害与严重度敏感性，均采用冻结配置并展示已记录点估计，不是区间。(a) 实心柱为 oracle 最优动作频率，斜线柱为动作在可用样例上带来改善的比例。(b) 相对于 KEEP 的平均效用，正值表示 MASE 更低。(c) 伤害损失，即修复额外增加的误差，在全部请求上平均。(d) 实心柱为修复频率，斜线柱为已执行修复中的有害比例，KEEP 的后者未定义。(e) 不重新调参时，10%、30% 和 50% 缺失率下的数据源宏平均 MASE。(f) 任一模式、骨干和严重度单元中，相对于 KEEP 的最大 MASE 增幅。动作代码 K、F、S、M、R、A 分别表示 KEEP、前向填充、单变量 TS-ICL、多变量 TS-ICL、上下文岭回归和 SAITS。方法代码 K、BF、C、A、T、IA 分别表示 KEEP、Best Fixed、R2-CART、Fixed SAITS、TATO 和 IntroAct-TS。(a–d) 使用 10% 缺失率，方法均值覆盖三个骨干、两个预测长度和四种模式，数据源等权。动作占比和效用使用各动作可用的样例。表 \ref{tab:heterogeneity} 保留动作数值，附录 \ref{app:gate-controls} 和 \ref{app:severity-full} 给出细分。

## 对照 057

```latex
\subsection{Forecasting Performance}
```

**中文直译**

预测性能

## 对照 058

```latex
Table~\ref{tab:main} compares the methods at $10\%$ missingness. \introact{} reaches
1.425 source-macro MASE, the lowest aggregate among the deployable rows. KEEP gives 1.576,
Best Fixed 1.488 and Source Fixed 1.445. R2-CART and Fixed SAITS each give 1.459.
The full method repairs $55.2\%$ of requests. These averages favour selective repair,
although the best method differs across backbones.
```

**中文直译**

表 \ref{tab:main} 比较 10% 缺失率下的方法。IntroAct-TS 的数据源宏平均 MASE 为 1.425，是可部署方法中的最低总体值。KEEP 为 1.576，Best Fixed 为 1.488，Source Fixed 为 1.445。R2-CART 和 Fixed SAITS 均为 1.459。完整方法修复 55.2% 的请求。这些均值支持选择性修复，不过各骨干上的最佳方法不同。

## 对照 059

```latex
TATO, PSW-I, TimesNet and T1 reach 1.616, 1.612, 1.741 and 1.906 aggregate MASE,
respectively. Their higher aggregate errors than KEEP show that applying these repairs
throughout the tested protocol does not ensure better forecasts. PSW-I is slightly better
than KEEP on Chronos-2, so this pattern is not uniform across individual backbone results.
The comparisons concern the recorded implementations and budgets. They do not isolate
repair frequency from differences between the repair methods.
```

**中文直译**

TATO、PSW-I、TimesNet 和 T1 的总体 MASE 分别为 1.616、1.612、1.741 和 1.906。它们高于 KEEP 的总体误差说明，在测试协议中始终应用这些修复，并不保证预测更好。PSW-I 在 Chronos-2 上略优于 KEEP，因此该现象并不一致地适用于每个骨干结果。比较限于记录的实现和预算，未将修复频率的影响与修复方法间差异分离。

## 对照 060

```latex
FULL minus KEEP differences are $-0.0839$, $-0.1536$ and $-0.2144$ on Bolt, TimesFM
and Chronos-2, with nominal $95\%$ parent-bootstrap intervals
$[-0.1401,-0.0314]$, $[-0.2145,-0.0917]$ and $[-0.3159,-0.1134]$.
All exclude zero, and the corresponding Holm-adjusted tests remain below $0.05$.
Against Best Fixed, the Bolt difference is $-0.0454$ and its interval excludes zero.
The TimesFM and Chronos-2 intervals include zero. Source Fixed is better on Bolt by
0.0223, with interval $[0.0044,0.0432]$ for FULL minus Source Fixed. The corresponding
TimesFM and Chronos-2 intervals include zero. Thus, the evidence is stronger for improvement
over unchanged input than for a consistent advantage over fixed repair policies.
```

**中文直译**

Bolt、TimesFM 和 Chronos-2 上 FULL 减 KEEP 的差值分别为 −0.0839、−0.1536 和 −0.2144，名义 95% 父窗口自助法区间分别为 [−0.1401,−0.0314]、[−0.2145,−0.0917] 和 [−0.3159,−0.1134]。所有区间都不含零，相应 Holm 校正检验也仍低于 0.05。相对于 Best Fixed，Bolt 差值为 −0.0454，区间不含零，TimesFM 和 Chronos-2 区间含零。Source Fixed 在 Bolt 上更好，差值为 0.0223，FULL 减 Source Fixed 的区间为 [0.0044,0.0432]，TimesFM 和 Chronos-2 对应区间含零。因此，相对于保持输入不变的改善证据，比相对于固定修复策略的一致优势更强。

## 对照 061

```latex
The TATO comparison applies to the adaptation and search budget in Appendix~\ref{app:baseline-config}.
Trained imputers use the same TRAIN region and missingness protocol. Appendix~\ref{app:datasets}
gives source and pattern breakdowns, and Appendix~\ref{app:calls} reports cost accounting.
```

**中文直译**

TATO 比较适用于附录 \ref{app:baseline-config} 中的适配与搜索预算。训练后的插补器使用同一 TRAIN 区域和缺失协议。附录 \ref{app:datasets} 给出数据源及模式细分，附录 \ref{app:calls} 报告成本核算。

## 对照 062

```latex
\caption{Main comparison on TEST at $10\%$ missingness, source-macro averaged, lower is
better in the error columns. \best{Bold} and \second{underline} mark the lowest and second-lowest MASE
in each error column, excluding the oracle. Repair rate is the share of
the 760 requests on which the row executed a repair, averaged over the three backbones. The
oracle reads the future target and is a diagnostic. Each backbone uses its own TRAIN replay
bank and its own frozen configuration. The shaded row is the full method. Table~\ref{tab:app-roster} defines the rows.}
```

**中文直译**

TEST 上 10% 缺失率的主比较，按数据源宏平均，误差列越低越好。排除 oracle 后，每个误差列的最小和次小 MASE 分别加粗和加下划线。修复率为该行方法在 760 个请求中执行修复的比例，再对三个骨干平均。Oracle 读取未来目标，仅用于诊断。每个骨干使用自己的 TRAIN 回放库和冻结配置。底色行表示完整方法。表 \ref{tab:app-roster} 定义各行。

### 共用数值表 1

```latex
\begin{tabularx}{\textwidth}{@{}Xrrrrr@{}}
    \toprule
    Method & Bolt & TimesFM & Chronos-2 & Overall MASE & Repair rate \\
    \midrule
Native KEEP & 1.466 & 1.682 & 1.579 & 1.576 & 0.000 \\
    \midrule
Best Fixed & 1.428 & 1.579 & 1.456 & 1.488 & 0.745 \\
Source Fixed & \best{1.360} & \second{1.527} & 1.448 & \second{1.445} & 0.821 \\
Fixed SAITS & 1.469 & \best{1.465} & 1.441 & 1.459 & 0.983 \\
R2-CART & 1.406 & 1.594 & \second{1.377} & 1.459 & 0.987 \\
    \midrule
TATO & 1.620 & 1.614 & 1.614 & 1.616 & 1.000 \\
TimesNet & 1.722 & 1.740 & 1.762 & 1.741 & 1.000 \\
PSW-I & 1.578 & 1.685 & 1.574 & 1.612 & 1.000 \\
T1 & 1.954 & 1.849 & 1.914 & 1.906 & 1.000 \\
    \midrule
\rowcolor{bestgray}\textbf{\introact{}} & \second{1.383} & 1.528 & \best{1.365} & \best{1.425} & 0.552 \\
    \midrule
Catalog Oracle & \oracle{1.234} & \oracle{1.315} & \oracle{1.226} & \oracle{1.258} & \oracle{0.807} \\
    \bottomrule
  \end{tabularx}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 063

```latex
The gain over Best Fixed is concentrated across sources. Omitting Exchange reverses its
mean direction on every backbone, while the advantage over KEEP persists on every
seven-source subset. Thus, selective repair improves on unchanged input more consistently
than it improves on a fixed repair policy. Appendix~\ref{app:layout-details} retains
the complete source-level diagnostics.
```

**中文直译**

相对于 Best Fixed 的收益集中于部分数据源。移除 Exchange 后，所有骨干的平均差值方向都反转，而相对于 KEEP 的优势在每个七数据源子集上都保留。因此，选择性修复相对于保持输入不变的改善，比相对于固定修复策略更一致。附录 \ref{app:layout-details} 保留完整的数据源诊断。

## 对照 064

```latex
Earlier revisions used this TEST block during design. An additional evaluation applied
the frozen procedure once to Solar and US Term Structure, whose evaluation periods were
excluded from the present design cycle. Each source used its own TRAIN replay bank and
training-side configuration selection. Over 21 test parents, \introact{} gives 4.226 MASE
against 4.707 for KEEP. The Bolt and Chronos-2 paired intervals exclude zero, while the
TimesFM interval includes zero. Best Fixed gives 4.223, so this evaluation does not establish
an advantage over that control. These sources appeared in earlier development and are not
wholly unseen domains. Appendix~\ref{app:confirmatory} records the evaluation boundaries.
```

**中文直译**

早期版本在设计时使用过该 TEST 块。额外评估将冻结流程一次性应用于 Solar 和 US Term Structure，其评估时段被排除在当前设计周期之外。每个源使用自己的 TRAIN 回放库及训练侧配置选择。在 21 个测试父窗口上，IntroAct-TS 的 MASE 为 4.226，KEEP 为 4.707。Bolt 和 Chronos-2 的配对区间不含零，TimesFM 的区间含零。Best Fixed 为 4.223，因此该评估未确立相对于这一对照的优势。这些源曾出现在早期开发中，并非完全未见过的领域。附录 \ref{app:confirmatory} 记录评估边界。

## 对照 065

```latex
\subsection{Intervention Frequency and Harm}
```

**中文直译**

干预频率与伤害

## 对照 066

```latex
Harmful loss measures repair-induced increases in error, averaged over all requests.
Figure~\ref{fig:harm}(c,d) gives 0.0340 for \introact{} at a $55.2\%$ repair rate,
compared with 0.0513 at $74.5\%$ for Best Fixed and 0.0552 at $98.7\%$ for R2-CART.
These results show lower aggregate harm, but intervention frequency also differs.
```

**中文直译**

伤害损失衡量修复造成的误差增加，并在所有请求上平均。图 \ref{fig:harm}(c,d) 中，IntroAct-TS 在 55.2% 修复率下的伤害损失为 0.0340，Best Fixed 在 74.5% 修复率下为 0.0513，R2-CART 在 98.7% 修复率下为 0.0552。这些结果表明总体伤害更低，但干预频率也不同。

## 对照 067

```latex
To assess the use of request information, a random control retains the full rule's
recommended action and randomises execution. Its probability matches FULL's development
repair rate and is frozen for TEST. FULL minus random MASE is $-0.0534$, $-0.0142$ and
$-0.1126$ on the three backbones, with intervals $[-0.0751,-0.0336]$,
$[-0.0281,-0.0001]$ and $[-0.1818,-0.0448]$. These nominal intervals exclude zero.
The comparison supports informed gating over this random control. Actual TEST rates differ,
so it does not establish superiority at exactly equal intervention rates.
```

**中文直译**

为评价请求信息的作用，随机对照保留完整规则推荐的动作，只随机决定是否执行。其概率匹配 FULL 的开发块修复率，并在 TEST 上冻结。三个骨干上 FULL 减随机对照的 MASE 差值为 −0.0534、−0.0142、−0.1126，区间分别为 [−0.0751,−0.0336]、[−0.0281,−0.0001]、[−0.1818,−0.0448]。这些名义区间均不含零。比较支持利用信息的门控优于该随机对照。实际 TEST 频率不同，因此并未确立严格相同干预率下的优势。

## 对照 068

```latex
Alternative utility scores provide a stronger control. The mean-only and linear rules
rerank candidates and calibrate their own thresholds on the same internal block.
The mean-only intervals include zero on all three backbones. FULL improves on the linear
rule by 0.0418 on Bolt and 0.0234 on Chronos-2, with intervals
$[-0.0638,-0.0202]$ and $[-0.0412,-0.0057]$. The TimesFM interval includes zero.
Thus, informed selection improves on the tested random gate, while the evidence against
alternative utility scores depends on the score and backbone.
A threshold calibrated on the training side meets its clipped-harm target in all four
Chronos-2 cells and only at $\alpha=0.05$ on Bolt and TimesFM. The temporal blocks do
not establish the exchangeability assumed by the bound, so its guarantee cannot be applied
unconditionally to these results.
Appendices~\ref{app:gate-controls} and \ref{app:layout-details} give the control values, the
calibration procedure and the retrospective cross-fit table.
```

**中文直译**

替代效用得分提供更强对照。仅均值规则和线性规则重新排列候选，并在相同内部块上校准各自阈值。仅均值规则在三个骨干上的区间均含零。FULL 在 Bolt 和 Chronos-2 上相对于线性规则分别改善 0.0418 和 0.0234，区间为 [−0.0638,−0.0202] 和 [−0.0412,−0.0057]。TimesFM 区间含零。因此，利用信息的选择优于测试的随机门控，而相对于其他效用得分的证据取决于得分形式与骨干。训练侧校准阈值在 Chronos-2 的四个单元中都满足截断伤害目标，在 Bolt 和 TimesFM 上仅 α=0.05 时满足。这些时间块未确立界限所需的可交换性，因此不能无条件将保证应用于这些结果。附录 \ref{app:gate-controls} 和 \ref{app:layout-details} 给出对照数值、校准流程和回顾性交叉拟合表。

## 对照 069

```latex
\subsection{What the Estimator and the Gate Contribute}
```

**中文直译**

估计器与门控的作用

## 对照 070

```latex
Table~\ref{tab:ablation} varies one component of the decision layer at a time, holding the
catalog, the prediction cache and the frozen configuration fixed, so every row differs from
the full method only in how the recorded utilities become a decision. Both endpoints of the
pooling range are rows of that table. The full rule reaches 1.425 against 1.429 for the
neighbourhood endpoint $\lambda=0$ and 1.437 for the source-mean endpoint
$\lambda=\infty$, and it reaches that while repairing $55.2\%$ of requests against $97.9\%$
for the source-mean score. Cross-validation picks $\lambda=0$ on Bolt and Chronos-2 and
$\lambda=64$ on TimesFM, so only TimesFM carries a pooling difference, worth 0.0125 with an
interval $[-0.0386,+0.0135]$ that crosses zero, and the other two rules are identical to
their endpoint by construction. These choices describe the selected configurations. They do not independently measure
within-source heterogeneity or establish that pooling causes the Source Fixed comparison.
```

**中文直译**

表 \ref{tab:ablation} 每次改变决策层的一个组成部分，同时固定动作目录、预测缓存和冻结配置，因此各行仅在如何将已记录效用转为决策上不同。表中包括汇聚范围的两个端点。完整规则为 1.425，邻域端点 λ=0 为 1.429，数据源均值端点 λ=∞ 为 1.437。完整规则修复 55.2% 的请求，数据源均值得分修复 97.9%。交叉验证在 Bolt 和 Chronos-2 上选择 λ=0，在 TimesFM 上选择 λ=64，因此只有 TimesFM 存在汇聚差异，差额为 0.0125，区间 [−0.0386,+0.0135] 跨零，另外两个规则按构造与其端点相同。这些选择描述选定配置，既不独立测量源内异质性，也不能证明汇聚导致了与 Source Fixed 的比较结果。

## 对照 071

```latex
The remaining rows remove what the estimate rests on. Dropping retrieval and scoring every
request by each action's bank-wide mean gives 1.475 and 0.0697 harmful loss, a ridge model
fitted on the same states and labels gives 1.448, and removing action conditioning gives
1.509, the largest increase in the table. Appendix~\ref{app:estimation-analyses} reports the
per-backbone intervals and the two state-feature controls, which do not separate from the
full state at this sample size.
```

**中文直译**

其余行移除估计依据。取消检索、用各动作在整个回放库的均值为所有请求评分，得到 MASE 1.475 和伤害损失 0.0697。在同样状态和标签上拟合岭回归模型得到 1.448，去除动作条件得到 1.509，为表中最大增幅。附录 \ref{app:estimation-analyses} 报告分骨干区间及两个状态特征对照，在当前样本规模下，后两者与完整状态没有得到可区分的差异证据。

## 对照 072

```latex
The execution gate trades mean accuracy for lower repair harm. Removing it and repairing
every request gives 1.414 against 1.425 MASE while harmful loss rises from 0.0340 to 0.0515,
so the point estimate favours always acting while the gate cuts added harm by about a third.
Section~\ref{sec:exp-harm} gives the calibrated operating points for that tradeoff.
```

**中文直译**

执行门控以平均精度换取较低修复伤害。移除门控并修复每个请求时，MASE 为 1.414，完整方法为 1.425，伤害损失从 0.0340 升至 0.0515。因此，点估计支持始终执行，而门控将新增伤害减少约三分之一。第 \ref{sec:exp-harm} 节给出该权衡的校准工作点。

## 对照 073

```latex
\caption{One component changed at a time, aggregated over the three backbones at $10\%$
severity. Every row reads the same catalog prediction cache and the same frozen
configuration, so the rows differ only in how the stored utilities become a decision. Repair
rate is the share of requests a repair executed on, conditional HIR the share of those
repairs that increased error, and harmful loss that increase averaged over all requests.}
```

**中文直译**

每次改变一个组成部分，在 10% 严重度下对三个骨干聚合。各行读取同一目录预测缓存和同一冻结配置，仅在如何将存储效用转为决策上不同。修复率为执行修复的请求比例，条件 HIR 为这些修复中增加误差的比例，伤害损失为该增加量在所有请求上的平均。

### 共用数值表 2

```latex
\begin{tabularx}{\textwidth}{@{}Xrrrr@{}}
    \toprule
    Variant & MASE $\downarrow$ & Repair rate & Conditional HIR $\downarrow$ & Harmful loss $\downarrow$ \\
    \midrule
    Neighbourhood only ($\lambda=0$) & 1.429 & 41.8\% & \best{39.8\%} & \second{0.0347} \\
    Source mean only ($\lambda=\infty$) & 1.437 & 97.9\% & 41.5\% & 0.0485 \\
    No retrieval & 1.475 & 100.0\% & 43.9\% & 0.0697 \\
    Linear utility model & 1.448 & 87.4\% & 44.2\% & 0.0652 \\
    No action conditioning & 1.509 & 68.3\% & 44.8\% & 0.0394 \\
    \midrule
    No execution gate & \best{1.414} & 100.0\% & 42.9\% & 0.0515 \\
    \midrule
    \rowcolor{bestgray}\textbf{Full \introact{}} & \second{1.425} & 55.2\% & \second{40.1\%} & \best{0.0340} \\
\bottomrule
  \end{tabularx}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 074

```latex
\subsection{Where the Advantage Holds and Where It Stops}
```

**中文直译**

优势的适用范围与边界

## 对照 075

```latex
The main comparison fixes the severity at $10\%$, and the same frozen configuration was
applied unchanged at $30\%$ and $50\%$ without retuning anything. Figure~\ref{fig:robust}
panels (e,f) report mean error and the largest cell-level degradation. The advantage over the unchanged input survives at every level, reaching
1.692 against 1.794 at $30\%$ and 1.731 against 1.875 at $50\%$. Parent-clustered intervals
exclude zero on TimesFM and Chronos-2 at $30\%$ and on all three backbones at $50\%$. The
per-source fixed policy reaches 1.674 at $30\%$ and 1.709 at $50\%$. On Chronos-2 it
significantly outperforms the request-level rule at both higher severities.
```

**中文直译**

主比较固定为 10% 严重度，同一冻结配置未经调参应用于 30% 和 50%。图 \ref{fig:robust}(e,f) 报告平均误差和最大单元退化。相对于保持输入不变的优势在每个严重度上都保留，30% 时为 1.692 对 1.794，50% 时为 1.731 对 1.875。父窗口聚类区间在 30% 的 TimesFM 和 Chronos-2 上不含零，在 50% 的三个骨干上均不含零。分数据源固定策略在 30% 时为 1.674，在 50% 时为 1.709。它在 Chronos-2 的两个较高严重度上均显著优于请求级规则。

## 对照 076

```latex
Repair frequency increases from $55.2\%$ to $64.0\%$ and $71.9\%$ across the three
severities. This change accompanies a smaller advantage over fixed policies, but does not
by itself identify the cause. A threshold tuned for heavier missingness could yield a
different tradeoff and would require separate evaluation. All three severities occur in
replay construction, so the sweep measures sensitivity within the sampled grid.
Appendix~\ref{app:layout-details} retains the mask-sensitivity checks.
```

**中文直译**

三种严重度的修复频率从 55.2% 升至 64.0% 和 71.9%。这一变化伴随相对于固定策略的优势缩小，但本身不能确定原因。针对更严重缺失调节阈值可能产生不同权衡，需要单独评价。三种严重度均出现在回放构建中，因此该扫描测量采样网格内的敏感性。附录 \ref{app:layout-details} 保留掩码敏感性检查。

## 对照 077

```latex
\subsection{Deployment Cost}
```

**中文直译**

部署成本

## 对照 078

```latex
Under the batch-one serving measurement protocol in Appendix~\ref{app:calls-measured},
a request takes a median of 94 ms on
Chronos-2, 167 ms on Bolt and 288 ms on TimesFM, against 16, 54 and 115 ms for passing the
incomplete context through. Almost none of that gap is the decision, which takes 2.8 to
3.1 ms because the bank is frozen and retrieval is a distance computation. What the method
pays for is candidate construction, and the two in-context repairs alone take 77 ms on every
backbone. Dropping these actions could reduce construction cost, but would change the catalog and
requires a new accuracy evaluation. The measurement uses live SAITS timing with archived
SAITS candidate values. The appendix gives this limitation, the stages and cold start.
```

**中文直译**

按附录 \ref{app:calls-measured} 的批量一服务测量协议，单个请求中位延迟在 Chronos-2、Bolt 和 TimesFM 上分别为 94、167 和 288 毫秒，直接传入不完整上下文分别为 16、54 和 115 毫秒。决策仅需 2.8 至 3.1 毫秒，对差距贡献很小，因为回放库冻结，检索仅计算距离。方法主要支付候选构造成本，仅两种上下文修复在每个骨干上就需要 77 毫秒。删去这些动作可能降低构造成本，但会改变目录，需要新的精度评估。测量使用 SAITS 实时计时及已归档的 SAITS 候选值。附录说明这一限制、各阶段和冷启动。

## 对照 079

```latex
\section{Conclusion}
```

**中文直译**

结论

## 对照 080

```latex
We studied how to select a repair for an incomplete request to a frozen forecaster.
\introact{} estimates forecasting utility from historical action outcomes and gates execution
relative to unchanged input. The recorded evaluation gives the lowest aggregate MASE among
the compared deployable methods, with backbone-dependent results against fixed policies.
The gate reduces harmful loss while increasing mean error relative to always acting.
These findings support evaluating repairs by their forecasting effects and reporting accuracy
and harm together. The main TEST comparisons are exploratory. The additional two-source
evaluation supports improvement over KEEP on two backbones, without resolving the comparison
with Best Fixed.
```

**中文直译**

我们研究了如何为冻结预测器的不完整请求选择修复。IntroAct-TS 从历史动作结果估计预测效用，并相对于保持输入不变控制执行。在已记录评估中，其总体 MASE 是所比较可部署方法中的最低值，而与固定策略的比较取决于骨干。相对于始终执行，门控降低伤害损失，同时提高平均误差。这些发现支持按预测效果评价修复，并共同报告精度与伤害。主 TEST 比较具有探索性。额外双数据源评估支持在两个骨干上优于 KEEP，但未解决与 Best Fixed 的比较。

## 对照 081

```latex
\section*{AI Use Statement}
```

**中文直译**

AI 使用声明

## 对照 082

```latex
The authors used ChatGPT to assist with English language polishing, including the
Introduction and Related Work sections, literature search and reference checking.
Generative AI tools also assisted with code preparation and the production of figures
from recorded experimental data. All AI-assisted content was carefully reviewed,
substantively edited, and verified by the authors, who take full responsibility for
the final content and scientific validity of the publication. The numerical tables
and figures retain the recorded experimental results.
```

**中文直译**

作者使用 ChatGPT 辅助英文语言润色，包括引言与相关工作部分，以及文献检索和引用核查。生成式 AI 工具还辅助代码准备和基于已记录实验数据的图形制作。所有 AI 辅助内容均经作者认真审阅、实质性编辑和核验，作者对最终内容与发表成果的科学有效性承担全部责任。数值表格和图形保留已记录的实验结果。

## 对照 083

```latex
\subsubsection*{Ethics statement}
```

**中文直译**

伦理声明

## 对照 084

```latex
This work studies input governance for frozen forecasting models on public benchmark datasets.
It does not involve human subjects, personal data, or deployment decisions with direct
societal consequences. We impose an integrity constraint under which an admissible
intervention cannot overwrite an observation that is marked as valid and available, because
silently replacing a real measurement would be a data integrity problem regardless of its
forecasting effect. We do not claim safety, robustness, or generality beyond the measured
conditions.
```

**中文直译**

本研究在公共基准数据集上研究冻结预测模型的输入治理，不涉及人类受试者、个人数据或直接产生社会后果的部署决策。我们施加完整性约束，可用干预不能覆盖标记为有效且可用的观测，因为无论预测效果如何，静默替换真实测量都会造成数据完整性问题。我们不对测量条件之外的安全性、稳健性或普适性作出主张。

## 对照 085

```latex
\subsubsection*{Reproducibility statement}
```

**中文直译**

可复现性声明

## 对照 086

```latex
We provide the complete experimental protocol, the final TRAIN and TEST split with the
purging rule, the missingness generation procedure, the intervention catalog, the state
feature definitions, the hyperparameter search spaces, the failure policy, and the statistical
analysis in Appendix~\ref{app:data-protocol} and Appendix~\ref{app:splits}.
Appendix~\ref{app:reprodetails} specifies the result-record schema and the traceability checks.
All reported tables are generated from retained raw predictions and versioned configurations.
```

**中文直译**

附录 \ref{app:data-protocol} 和 \ref{app:splits} 提供完整实验协议、含隔离规则的最终 TRAIN 与 TEST 划分、缺失生成流程、干预目录、状态特征定义、超参数搜索空间、失败策略和统计分析。附录 \ref{app:reprodetails} 说明结果记录结构与可追溯检查。所有报告表格均由保留的原始预测和版本化配置生成。

## 对照 087

```latex
\section*{Appendix map}
```

**中文直译**

附录导航

## 对照 088

```latex
Table~\ref{tab:app-map} lists what each appendix section contains. The appendix is organised
by the question each part answers.
```

**中文直译**

表 \ref{tab:app-map} 列出各附录部分的内容。附录按各部分回答的问题组织。

## 对照 089

```latex
\caption{Appendix map. Sections are lettered in order of appearance.}
```

**中文直译**

附录导航。各节按出现顺序使用字母编号。

### 共用数值表 3

```latex
\adjustbox{max width=\textwidth}{\begin{tabular}{@{}p{.18\textwidth}p{.44\textwidth}p{.31\textwidth}@{}}
    \toprule
    Section & Contents & Question it answers \\
    \midrule
    A. Evaluation protocol & scope and assumptions, the TRAIN and TEST split with purging, the dataset and missingness protocol, baseline availability and configuration & what exactly was fixed before the evaluation ran? \\
    B. Method and implementation details & the intervention catalog, the state features, the off-policy positioning, replay construction, local utility estimation, the complete-input contract & how is the method defined, exactly as implemented? \\
    C. Forecasting results & action-utility values, reconstruction versus forecasting utility, per-source and per-pattern tables, the source-level fixed policy and leave-one-source-out & does the aggregate hold action by action, source by source, and pattern by pattern? \\
    D. Intervention frequency and harm & governance diagnostics, opportunity strata, gate controls & how often does each rule intervene, and is the full rule's frequency what carries its result? \\
    E. Estimation and state analyses & the full ablation vector, the mechanism and feature controls, the reduced-state selection check & which component carries the gain, and does the state representation survive its own selection? \\
    F. Sensitivity analyses & the severity sweep, replay-bank size, mask-realisation stability & does the result rest on one severity, one bank size, or one mask? \\
    G. Cost and reproducibility & the runtime and failure audit, the result-record schema and anchors, the development negative results & what does a request cost, and can every reported number be traced back to a stored artefact? \\
    Appendix~\ref{app:layout-details} & Supplementary comparisons and calibration & Related work, cases, source diagnostics and calibration details \\
\bottomrule
  \end{tabular}}
```

**中文表内文字**

列为章节、内容、回答的问题。
A 评估协议包括范围与假设、带隔离的 TRAIN/TEST 划分、数据及缺失协议、基线可用性和配置，回答评估前固定了什么。
B 方法与实现包括干预目录、状态、离策略定位、回放、局部效用和完整输入约定，回答实现中方法如何定义。
C 预测结果包括动作效用、重建与预测效用比较、分源分模式、源固定和留一源分析，回答总体结果是否在各动作、源和模式中成立。
D 干预频率与伤害包括治理诊断、机会分层和门控对照，回答干预频率及其对结果的贡献。
E 估计与状态包括完整消融、机制与特征对照、精简状态选择，回答哪个组件贡献收益及表示能否经受单独选择。
F 敏感性包括严重度、库规模和掩码稳定性，回答结果是否依赖单一严重度、规模或掩码。
G 成本与可复现性包括时间与失败审计、记录结构及依据、开发负面结果，回答请求成本及数值可追溯性。
补充比较与校准包括相关工作、案例、源诊断和校准细节。

## 对照 090

```latex
\section{Evaluation Protocol}
```

**中文直译**

评估协议

## 对照 091

```latex
This section fixes everything that was registered before the evaluation ran, and it
supports \S\ref{sec:exp-setup}.
```

**中文直译**

本节明确评估运行前登记的内容，为第 \ref{sec:exp-setup} 节提供支持。

## 对照 092

```latex
\subsection{Scope and Assumptions}
```

**中文直译**

范围与假设

## 对照 093

```latex
The replay bank samples four missingness patterns and three severities on the registered
sources. The estimator returns a score even when a request differs from this support, since
retrieval has no explicit support threshold. Results therefore apply to the sampled grid.
They do not establish performance on naturally missing streams or new missingness mechanisms.
```

**中文直译**

回放库在登记的数据源上采样四种缺失模式和三种严重度。检索没有显式支持范围阈值，即使请求偏离这一范围，估计器也返回得分。因此结果适用于采样网格，不能确立自然缺失数据流或新缺失机制上的表现。

## 对照 094

```latex
The catalog and backbone revision are fixed. Changing the revision requires rebuilding the
bank because each utility belongs to the model that produced it. Sensitivity to the mask
realisation is examined in Appendix~\ref{app:seeds}.
Table~\ref{tab:app-claims} summarises the scope of these measurements.
```

**中文直译**

目录与骨干版本固定。改变版本需要重建回放库，因为每个效用都属于产生它的模型。附录 \ref{app:seeds} 检查对掩码实现的敏感性。表 \ref{tab:app-claims} 总结这些测量的范围。

## 对照 095

```latex
\caption{What the evidence supports and what it does not. The scope follows from the evaluation protocol and the empirical decision rule.}
```

**中文直译**

证据支持与不支持的内容。范围由评估协议和经验决策规则决定。

### 共用数值表 4

```latex
\begin{tabular}{@{}p{0.46\textwidth} p{0.46\textwidth}@{}}
    \toprule
    Supported by the reported evidence & Not claimed anywhere \\
    \midrule
    Selective intervention inside the registered missingness grid, on the four patterns and three severities that were replayed & out-of-grid or out-of-distribution missingness generalisation \\
    Application of the same procedure to three backbones, each with a separate replay bank, in a post-hoc comparison & that the method can detect that its historical evidence is insufficient for the request in front of it \\
    A conservative score that orders actions and a threshold that decides whether any of them runs & any coverage or risk-control guarantee for that score \\
    Behaviour under controlled deletion from complete series & that the results extend to naturally incomplete deployment streams \\
    A broad-based margin over the unchanged input, and over random intervention with frequency matched on the development block & a uniform accuracy advantage over the stronger simple controls on every source or backbone \\
    \bottomrule
  \end{tabular}
```

**中文表内文字**

左列是证据支持的范围，右列是不作出的主张。逐行对应如下。
登记网格内四种回放模式、三个严重度的选择性干预，不主张网格外或分布外缺失泛化。
在各自独立回放库上将相同流程应用于三个骨干的事后比较，不主张方法能检测历史证据不足。
保守得分排列动作、阈值决定是否执行，不主张该得分具有覆盖率或风险控制保证。
从完整序列中受控删除时的行为，不主张可推广至自然不完整部署流。
相对于保持输入不变以及开发块匹配频率的随机干预的较广优势，不主张在每个源或骨干上均优于更强简单对照。

## 对照 096

```latex
\subsection{Splits, Purging, and the Final Evaluation Set}
```

**中文直译**

数据划分、隔离和最终评估集

## 对照 097

```latex
Each source is split chronologically into TRAIN and TEST with an $L+H$ purge.
The replay bank, feature normalisation and fitted selectors use TRAIN. Earlier results on
the same TEST block informed the current method design. The split separates fitting data
from evaluation data, while the present comparison remains post-hoc.
```

**中文直译**

每个数据源按时间划分为 TRAIN 和 TEST，并设置 L+H 的隔离间隔。回放库、特征标准化和拟合选择器使用 TRAIN。同一 TEST 块的早期结果影响过当前方法设计。划分分离拟合数据与评价数据，而当前比较仍属于事后比较。

## 对照 098

```latex
TRAIN is then partitioned at the parent level. Within each source the admissible TRAIN parents
are sorted by origin time and split at $80/20$ into the replay bank and TRAIN-eval. The bank is
the evidence used for utility estimation, and it is also where $k$, $\beta$ and $\lambda$ are chosen by
leave-one-parent-out cross-validation, so no separate selection block is held out for them.
TRAIN-eval supplies internal checks and the separate threshold calibration described in
Appendix~\ref{app:layout-details}. Main accuracy comparisons use TEST. Parents tile at $L + \max(H)$, so two
parents never share a raw row, and the gap between the last TRAIN window and the first TEST
window exceeds the purge on every source.
Table~\ref{tab:app-splits} records the realised sizes, including the TEST block.
Four further recorded blocks serve secondary analyses and select nothing: TEST-30 and
TEST-50 repeat the TEST parents at $30\%$ and $50\%$ severity
(Appendix~\ref{app:severity-full}), and TEST-M2 and TEST-M3 repeat them under two further
deterministic mask realisations (Appendix~\ref{app:seeds}). Two historical blocks of the
development line, a hash-sampled-severity bank variant and a second mask-seed bank, are
retained in the repository but enter no number in this paper.
```

**中文直译**

TRAIN 进一步在父窗口层面划分。在每个数据源内部，将可用 TRAIN 父窗口按起点时间排序，以 80/20 划分为回放库与 TRAIN-eval。回放库提供效用估计证据，k、β、λ 也通过该库上的留一父窗口交叉验证选择，因此未另外为其保留选择块。TRAIN-eval 提供内部检查及附录 \ref{app:layout-details} 中的独立阈值校准。主要精度比较使用 TEST。父窗口按 L+max(H) 平铺，因此任意两个父窗口不共享原始行，每个源的最后 TRAIN 窗口与首个 TEST 窗口间距均超过隔离长度。表 \ref{tab:app-splits} 记录实际规模，包括 TEST。另有四个记录块用于次要分析，不选择参数，TEST-30 和 TEST-50 在 30% 与 50% 严重度重复 TEST 父窗口，TEST-M2 和 TEST-M3 使用另外两种确定性掩码重复它们。开发线中的两个历史块，即哈希采样严重度回放库变体和第二掩码种子库，保留在仓库中，但不进入本文数值。

## 对照 099

```latex
\caption{Realised split sizes. Counts are of admissible parents and not of correlated mask
variants. A parent with several patterns or severities remains one cluster for resampling.
TEST is the evaluation population for every table in the main
text, and it is disjoint from both TRAIN blocks.}
```

**中文直译**

实际划分规模。计数单位为可用父窗口，不是相关掩码变体。具有多个模式或严重度的父窗口仍是重采样中的一个聚类。TEST 是正文各表的评估总体，与两个 TRAIN 块均不重叠。

### 共用数值表 5

```latex
\adjustbox{max width=\textwidth}{\begin{tabular}{@{}p{.14\textwidth}rrrp{.42\textwidth}@{}}
    \toprule
    Split & Parents & Episodes & Sources covered & Used for \\
    \midrule
    Replay bank  & 223   & 5352   & 8   & replay bank, feature normalisation, baseline training, selection of $k$, $\beta$ and $\lambda$ by cross-validation \\
    TRAIN-eval   & 53  & 424  & 8  & internal checks and threshold calibration \\
    \midrule
    TEST         & 95  & 760  & 8  & post-hoc evaluation in the main text \\
    \bottomrule
  \end{tabular}}
```

**中文表内文字**

列为划分、父窗口数、样例数、覆盖数据源数、用途。回放库为 223、5352、8，用于回放、特征标准化、基线训练以及交叉验证选择 k、β、λ。TRAIN-eval 为 53、424、8，用于内部检查与阈值校准。TEST 为 95、760、8，用于正文事后评价。

## 对照 100

```latex
\subsection{Dataset and Missingness Protocol}
```

**中文直译**

数据集与缺失协议

## 对照 101

```latex
The missingness mechanism is frozen before any method is run, and every mask is derived
deterministically from a key that identifies the parent and the pattern. This subsection fixes
the four patterns, the derivation rule, and the metric conventions that depend on the data.
```

**中文直译**

缺失机制在任何方法运行前冻结，每个掩码均由标识父窗口和模式的键确定性生成。本小节明确四种模式、生成规则以及依赖数据的指标约定。

## 对照 102

```latex
\subsubsection{Missingness Patterns}
```

**中文直译**

缺失模式

## 对照 103

```latex
Table~\ref{tab:app-patterns} defines the four deterministic patterns. Every mask is derived
by a deterministic hash of
\texttt{source + parent + origin + horizon + pattern + protocol\_seed} and is never moved
after forecasts are seen. The severity of an episode is not drawn from this key: the replay
bank enumerates all three registered severities $\{10\%, 30\%, 50\%\}$ on every parent,
pattern and horizon, and the severity only sets the deletion budget of the mask.
```

**中文直译**

表 \ref{tab:app-patterns} 定义四种确定性模式。每个掩码由 source + parent + origin + horizon + pattern + protocol_seed 的确定性哈希生成，查看预测后不再移动。样例严重度不从该键抽取，回放库在每个父窗口、模式和预测长度上枚举登记的三种严重度 {10%,30%,50%}，严重度只决定掩码的删除预算。

## 对照 104

```latex
\caption{The four registered missingness patterns. All four are applied to the same parents,
so pattern effects are measured on a common parent set rather than on different subsets of
the data.}
```

**中文直译**

四种登记的缺失模式。四者都应用于相同父窗口，因此在共同父窗口集上衡量模式效果，不使用不同数据子集。

### 共用数值表 6

```latex
\begin{tabular}{@{}l p{0.34\textwidth} p{0.40\textwidth}@{}}
    \toprule
    Pattern & What is removed & Why it is included \\
    \midrule
    P1 point missing    & scattered single positions & the classical random-missing regime \\
    P2 target block     & a contiguous block on the target variable & a sensor outage on the variable being forecast \\
    P3 shared block     & several visible variables over the same interval & a channel or acquisition outage affecting the whole panel \\
    P4 tail missing     & a block adjacent to the forecast origin & observations that have not arrived yet at request time \\
    \bottomrule
  \end{tabular}
```

**中文表内文字**

列为模式、删除内容、纳入原因。P1 点缺失删除分散单点，对应经典随机缺失。P2 目标块删除目标变量连续块，对应被预测变量的传感器故障。P3 共享块删除同一时段的多个可见变量，对应影响整个面板的通道或采集故障。P4 尾部缺失删除紧邻预测起点的块，对应请求时尚未到达的观测。

## 对照 105

```latex
\subsubsection{Metric Conventions}
```

**中文直译**

指标约定

## 对照 106

```latex
The statistical resampling unit is the parent. Paired cluster bootstrap with 2,000 resamples
over parent blocks gives 95\% confidence intervals on source-macro MASE differences against
each baseline, the source-macro aggregation is applied inside every resample, and Holm
correction~\citep{holm1979simple} is applied across the recorded baseline comparison family.
The family contains the nine comparisons of \introact{} against deployable baselines on
one backbone, and the ablations stay outside it because they are variants of this method rather
than competing claims. Table~\ref{tab:app-holm} records the current family using the saved v55 statistics.
Average rank and won cells are descriptive summaries only, and the headline claim rests on
paired differences with confidence intervals.
```

**中文直译**

统计重采样单位是父窗口。对父窗口块进行 2,000 次配对聚类自助重采样，获得相对于各基线的数据源宏平均 MASE 差值的 95% 置信区间。每次重采样内均执行数据源宏平均，并对记录的基线比较族应用 Holm 校正。每个骨干的比较族包含 IntroAct-TS 与九个可部署基线的比较，消融属于本方法变体，不纳入该比较族。表 \ref{tab:app-holm} 使用保存的 v55 统计量记录当前比较族。平均排名和胜出单元数仅为描述性汇总，主要主张依据配对差值及其置信区间。

## 对照 107

```latex
\caption{Paired differences against the deployable baselines with the Holm adjustment.
A negative difference favours \introact{}. The p-value is two sided and read off the same
bootstrap draws as the interval, so it cannot fall below one over the number of resamples.}
```

**中文直译**

相对于可部署基线的配对差值及 Holm 校正。负差值有利于 IntroAct-TS。双侧 p 值与区间读取相同自助抽样，因此其下限为重采样次数的倒数。

### 共用数值表 7

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrrr@{}}
    \toprule
    Backbone & Comparison & Difference & 95\% interval & $p$ & $p$ after Holm \\
    \midrule
Bolt & KEEP & -0.0839 & $[-0.1401,-0.0314]$ & 0.0005 & 0.0045 \\
Bolt & Best Fixed & -0.0454 & $[-0.0854,-0.0052]$ & 0.0140 & 0.0420 \\
Bolt & Source Fixed & +0.0223 & $[+0.0044,+0.0432]$ & 0.0100 & 0.0400 \\
Bolt & R2-CART & -0.0230 & $[-0.0441,-0.0019]$ & 0.0320 & 0.0640 \\
Bolt & Fixed SAITS & -0.0866 & $[-0.1996,+0.0236]$ & 0.2550 & 0.2550 \\
Bolt & TATO & -0.2375 & $[-0.3291,-0.1563]$ & 0.0005 & 0.0045 \\
Bolt & TimesNet & -0.3394 & $[-0.5356,-0.1430]$ & 0.0005 & 0.0045 \\
Bolt & PSW-I & -0.1954 & $[-0.2771,-0.1231]$ & 0.0005 & 0.0045 \\
Bolt & T1 & -0.5715 & $[-0.8768,-0.2656]$ & 0.0005 & 0.0045 \\
TimesFM & KEEP & -0.1536 & $[-0.2145,-0.0917]$ & 0.0005 & 0.0045 \\
TimesFM & Best Fixed & -0.0502 & $[-0.1042,+0.0033]$ & 0.0780 & 0.3900 \\
TimesFM & Source Fixed & +0.0017 & $[-0.0074,+0.0119]$ & 0.7640 & 1.0000 \\
TimesFM & R2-CART & -0.0659 & $[-0.1271,-0.0042]$ & 0.0030 & 0.0180 \\
TimesFM & Fixed SAITS & +0.0631 & $[-0.0551,+0.1822]$ & 0.4720 & 1.0000 \\
TimesFM & TATO & -0.0855 & $[-0.2774,+0.0965]$ & 0.4690 & 1.0000 \\
TimesFM & TimesNet & -0.2111 & $[-0.6640,+0.2424]$ & 0.5160 & 1.0000 \\
TimesFM & PSW-I & -0.1568 & $[-0.2328,-0.0894]$ & 0.0005 & 0.0045 \\
TimesFM & T1 & -0.3209 & $[-0.5592,-0.0836]$ & 0.0005 & 0.0045 \\
Chronos-2 & KEEP & -0.2144 & $[-0.3159,-0.1134]$ & 0.0005 & 0.0045 \\
Chronos-2 & Best Fixed & -0.0915 & $[-0.1950,+0.0134]$ & 0.2540 & 0.7620 \\
Chronos-2 & Source Fixed & -0.0834 & $[-0.1861,+0.0205]$ & 0.4220 & 0.8440 \\
Chronos-2 & R2-CART & -0.0123 & $[-0.0835,+0.0619]$ & 0.7080 & 0.8440 \\
Chronos-2 & Fixed SAITS & -0.0761 & $[-0.1130,-0.0381]$ & 0.0005 & 0.0045 \\
Chronos-2 & TATO & -0.2494 & $[-0.3584,-0.1467]$ & 0.0005 & 0.0045 \\
Chronos-2 & TimesNet & -0.3975 & $[-0.7264,-0.0660]$ & 0.0005 & 0.0045 \\
Chronos-2 & PSW-I & -0.2090 & $[-0.3005,-0.1291]$ & 0.0005 & 0.0045 \\
Chronos-2 & T1 & -0.5495 & $[-0.8309,-0.2738]$ & 0.0005 & 0.0045 \\
\bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 108

```latex
Mask variants of the same parent are never
treated as independent samples, and pattern, severity, and backbone breakdowns are secondary
analyses without cell-by-cell significance testing.
```

**中文直译**

同一父窗口的掩码变体不作为独立样本。模式、严重度和骨干细分属于次要分析，不逐单元进行显著性检验。

## 对照 109

```latex
MASE~\citep{hyndman2006mase} is the primary metric and RMSSE is the secondary metric. Both
scale the error of a source by its own seasonal naive error, computed on the TRAIN portion of
that source and therefore never on the evaluation block. With $y_t$ the target channel and $m$
the registered seasonal period of the source,
```

**中文直译**

MASE 是主要指标，RMSSE 是次要指标。两者均用数据源自身的季节朴素误差缩放其误差，缩放量在该源的 TRAIN 部分计算，从不使用评价块。记 yₜ 为目标通道，m 为该源登记的季节周期，公式如下。

**共用公式**

```latex
\begin{equation}
  \mathrm{MASE} = \frac{\mathrm{MAE}}{\frac{1}{T-m}\sum_{t} \lvert y_t - y_{t-m} \rvert},
  \qquad
  \mathrm{RMSSE} = \sqrt{\frac{\mathrm{MSE}}{\frac{1}{T-m}\sum_{t} (y_t - y_{t-m})^2}},
  \label{eq:metrics}
\end{equation}
```

## 对照 110

```latex
so the two metrics share the same seasonal naive difference series but not the same power of
it, and RMSSE is not the square root of MASE. The scaling constants are computed per channel
before any aggregation over channels, and the registered periods are listed in
Table~\ref{tab:app-seasonality}. A degenerate seasonal naive error, meaning a constant or
all-missing TRAIN series, leaves the metric undefined and is reported as unavailable. Aggregation is source-macro, first over parents within a source and then equally over
the eight sources, and the same order is applied inside every bootstrap resample. MAE and RMSE
are reported per source and are never averaged across sources, because the sources have
different scales and a cross-source average of a raw error has no common unit.
```

**中文直译**

两指标共享同一季节朴素差分序列，但使用不同幂次，RMSSE 不是 MASE 的平方根。缩放常数在通道聚合前逐通道计算，登记周期见表 \ref{tab:app-seasonality}。季节朴素误差退化时，即 TRAIN 序列恒定或全缺失时，指标未定义，报告为不可用。数据源宏平均先在源内对父窗口平均，再对八个源等权平均，每次自助重采样也使用该顺序。MAE 和 RMSE 按源报告，不跨源平均，因为数据源尺度不同，原始误差的跨源均值没有共同单位。

## 对照 111

```latex
\caption{Per-source seasonal periods and context conventions used by the metric
denominators. Context length is $L = 512$ for every source. The seasonal period is the
sampling-frequency period registered before any run, not a tuned quantity.}
```

**中文直译**

指标分母使用的各源季节周期及上下文约定。所有源的上下文长度均为 L=512。季节周期是运行前登记的采样频率周期，不是调参量。

### 共用数值表 8

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrr@{}}
    \toprule
    Source & Seasonal period $m$ & Channels & Scaling \\
    \midrule
    ETTh1 / ETTh2 & 24 & 7 & TRAIN seasonal naive error of the target channel \\
    ETTm1 / ETTm2 & 96 & 7 & TRAIN seasonal naive error of the target channel \\
    Electricity & 24 & 321 & TRAIN seasonal naive error of the target channel \\
    Exchange & 5 & 8 & TRAIN seasonal naive error of the target channel \\
    Traffic & 24 & 862 & TRAIN seasonal naive error of the target channel \\
    Weather & 144 & 21 & TRAIN seasonal naive error of the target channel \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

列为数据源、季节周期 m、通道数、缩放量。各行缩放量均为目标通道在 TRAIN 上的季节朴素误差。ETTh1/ETTh2 为 24、7，ETTm1/ETTm2 为 96、7，Electricity 为 24、321，Exchange 为 5、8，Traffic 为 24、862，Weather 为 144、21。

## 对照 112

```latex
\subsubsection{Diagnostic Conventions}
```

**中文直译**

诊断约定

## 对照 113

```latex
The diagnostics require explicit counting conventions, and
Table~\ref{tab:app-counting} specifies the rules used for the recorded evaluation.
```

**中文直译**

诊断需要明确计数口径，表 \ref{tab:app-counting} 给出本次记录评估采用的规则。

## 对照 114

```latex
\caption{The four counting rules used for the recorded evaluation. Each one is a
counting convention, and a different convention would change a reported number
without changing a single forecast.}
```

**中文直译**

已记录评估中的四项计数规则。它们都是计数约定，改变约定会改变报告值，即使任何预测都没有变化。

### 共用数值表 9

```latex
\begin{tabular}{@{}p{0.17\textwidth} p{0.40\textwidth} p{0.33\textwidth}@{}}
    \toprule
    Quantity & Rule & Boundary case \\
    \midrule
    Oracle-best action & the admissible action with the smallest realised loss & ties go to the first action in the frozen catalog order, so the shares sum to one. Unsupported, aliased and failed actions are excluded from the argmin \\
    Utility sign & harmful when $g_{i,a} < 0$ strictly, beneficial when $g_{i,a} > 0$ strictly & $g_{i,a} = 0$ enters neither numerator and remains in the executed-intervention denominator \\
    Beneficial precision & executed interventions with strictly positive utility, over executed interventions & undefined when nothing was executed, and reported as unavailable \\
    Opportunity strata & two pre-declared quantiles of $\Delta_i$ on the replay bank, applied unchanged to TEST & the same two values partition every method and no boundary is recomputed per method \\
    \bottomrule
  \end{tabular}
```

**中文表内文字**

列为统计量、规则、边界情形。Oracle 最优动作选择可用动作中已实现损失最小者，并列选目录最靠前者，比例和为一，不支持、等同和失败动作排除。效用严格小于零为有害，严格大于零为有益，零不进入分子但保留执行分母。有益精确率为正效用执行数除以执行数，无执行时未定义、报告不可用。机会分层使用库内 Δᵢ 的两个预定分位数，原样用于 TEST，各方法同边界、不重新计算。

## 对照 115

```latex
\emph{Oracle-best action.} The oracle-best action of an episode is the admissible action with
the smallest realised loss. Ties are broken by the frozen catalog order, so the first action in
that order wins and the reported shares of episodes on which each action is best sum to one. An
action that is unsupported, aliased, or failed is not admissible and is excluded from the
argmin.
```

**中文直译**

Oracle 最优动作。某样例的 oracle 最优动作是已实现损失最小的可用动作。并列按冻结目录顺序打破，顺序靠前者胜出，因此各动作最优的样例占比之和为一。不受支持、与其他动作等同或失败的动作不可用，不进入最小值选择。

## 对照 116

```latex
\emph{Utility sign.} Utility is defined relative to the reference action in
\eqref{eq:utility}, so $g_{i,a} = 0$ means the action and the reference are indistinguishable on
that episode. An intervention counts as harmful only when $g_{i,a} < 0$ strictly and as
beneficial only when $g_{i,a} > 0$ strictly, so the zero cases enter neither numerator but remain in the executed-intervention denominator and are reported as their own count.
```

**中文直译**

效用符号。公式 \eqref{eq:utility} 相对于参考动作定义效用，gᵢ,ₐ=0 表示该样例上动作与参考结果相同。只有严格 gᵢ,ₐ<0 才算有害干预，严格 gᵢ,ₐ>0 才算有益干预。零效用不进入两者分子，但保留在已执行干预的分母中，并单独计数。

## 对照 117

```latex
\emph{Beneficial precision.} It is the number of executed interventions with strictly positive
utility divided by the number of executed interventions, and it is undefined when nothing was
executed. It is reported as unavailable in that case.
```

**中文直译**

有益精确率。严格正效用的已执行干预数除以已执行干预总数。没有执行干预时，该指标未定义，报告为不可用。

## 对照 118

```latex
\emph{Opportunity strata.} The no-op boundary and the low-to-high boundary are the two
pre-declared quantiles of $\Delta_i$ computed on the replay bank, computed once and applied
unchanged to TEST. The same two values partition every method, and no boundary is recomputed
per method. Both values are recorded with the resolved configuration.
```

**中文直译**

机会分层。不操作边界和低到高边界是回放库上 Δᵢ 的两个预先指定分位数，计算一次后原样应用于 TEST。同一对值划分每种方法，不按方法重新计算边界。两个值均与解析后的配置一同记录。

## 对照 119

```latex
\subsection{Baseline Availability}
```

**中文直译**

基线可用性

## 对照 120

```latex
The comparison names more published methods in Section~\ref{sec:related} than it reports in
Table~\ref{tab:main}, and Table~\ref{tab:app-availability} records why method by method. A
method enters the tables when an official implementation exists, when it admits an incomplete
context of the shape this protocol produces, and when its own assumptions hold for a frozen
backbone. A reimplementation from a paper description would not be comparable with the numbers
that paper reports, so a method that fails any of the three is discussed and not tabulated.
```

**中文直译**

第 \ref{sec:related} 节讨论的已发表方法多于表 \ref{tab:main} 报告的方法，表 \ref{tab:app-availability} 逐项说明原因。方法进入表格需有官方实现，能够接收本协议产生形状的不完整上下文，并且其假设适用于冻结骨干。依据论文描述重新实现得到的结果不能直接等同于原文结果，因此不满足上述条件的方法仅讨论，不列数值。

## 对照 121

```latex
Some methods have incompatible task assumptions. Task-oriented imputation
evaluation~\citep{wang2024taskoriented} scores an imputation by the influence its values have
on the downstream forecaster, estimated with generalised representers, which requires gradients
of that forecaster with respect to its input. The setting of this paper is a forecaster served
as a fixed inference pipeline, which is what makes the decision an input-side one in the first
place, and such a pipeline exposes no gradients. Running the method would mean replacing the
frozen backbone by a differentiable surrogate, and the number that came out would describe the
surrogate. We therefore report the task-oriented idea in Section~\ref{sec:related} and carry
its objective, realised downstream utility, into our own replay, which measures the same
quantity by executing the action instead of differentiating through the model.
```

**中文直译**

部分方法的任务假设不兼容。面向任务的插补评价通过广义表示子估计插补值对下游预测器的影响，需要预测器对输入的梯度。本文设置将预测器作为固定推理流程提供服务，使决策位于输入侧，这类流程不暴露梯度。运行该方法需要用可微代理替换冻结骨干，所得数值将描述代理。因此，我们在第 \ref{sec:related} 节讨论其思想，并将已实现下游效用这一目标用于回放，通过执行动作测量，而非对模型求导。

## 对照 122

```latex
\caption{Published methods considered for the comparison. The last column states what the
method contributes here. Methods marked unavailable are discussed in
Section~\ref{sec:related} and carry no row in any table.}
```

**中文直译**

比较中考虑的已发表方法。最后一列说明该方法在本文中的作用。标为不可用的方法在第 \ref{sec:related} 节讨论，不在任何表格中列出结果行。

### 共用数值表 10

```latex
\adjustbox{max width=\textwidth}{\begin{tabular}{@{}l l p{0.28\textwidth} p{0.30\textwidth}@{}}
    \toprule
    Method & Venue & Implementation & Role here \\
    \midrule
    SAITS~\citep{du2023saits}       & ESWA 2023  & official, packaged~\citep{du2023pypots} & catalog action and fixed policy \\
    TATO~\citep{qiu2026tato}        & ICLR 2026  & official repository & data-side adaptation baseline \\
    TimesNet~\citep{wu2023timesnet} & ICLR 2023  & official, packaged~\citep{du2023pypots} & trained-imputation baseline \\
    PSW-I~\citep{wang2025pswi}      & ICLR 2025  & official repository & optimisation-based imputation baseline \\
    T1~\citep{park2026t1}           & ICLR 2026  & official repository & trained-imputation baseline \\
    \midrule
    TOI~\citep{wang2024taskoriented}& NeurIPS 2024 & official repository & needs gradients through the downstream forecaster \\
    BRITS~\citep{cao2018brits}      & NeurIPS 2018 & available & implemented. Measured training cost exceeds the remaining budget (registered decision, \S\ref{app:baseline-config}) \\
    CSDI~\citep{tashiro2021csdi}    & NeurIPS 2021 & available & implemented and partially run. Moved out for the same reason \\
    SRDI~\citep{xu2026srdi}         & WWW 2026   & no public release found & discussed only \\
    GIMCC~\citep{hao2025gimcc}      & KDD 2025   & no public release found & discussed only \\
    VIDA~\citep{liang2025vida}      & KDD 2025   & no public release found & discussed only \\
    \midrule
    BiTGraph~\citep{chen2024bitgraph}   & ICLR 2024 & available & trains its own forecaster, outside the frozen-backbone contract \\
    S4M~\citep{peng2025s4m}             & ICLR 2025 & available & the same \\
    ChannelTokenFormer~\citep{jang2026channeltokenformer} & ICLR 2026 & available & the same \\
    \bottomrule
  \end{tabular}}
```

**中文表内文字**

列为方法、发表场所、实现、本文角色。方法名和发表场所保持英文。
SAITS 使用官方打包实现，作为目录动作与固定策略。TATO 使用官方仓库，作为数据侧适配基线。TimesNet 使用官方打包实现，作为训练插补基线。PSW-I 使用官方仓库，作为优化式插补基线。T1 使用官方仓库，作为训练插补基线。
TOI 有官方仓库，但需要下游预测器梯度。BRITS 有可用实现，已实现，但实测训练成本超过剩余预算，属于登记决策。CSDI 可用，已实现且部分运行，因相同原因移出。SRDI、GIMCC、VIDA 未找到公开实现，仅讨论。
BiTGraph、S4M、ChannelTokenFormer 有可用实现，但训练自己的预测器，不属于冻结骨干约定。

## 对照 123

```latex
The last block is a different kind of exclusion. BiTGraph, S4M and ChannelTokenFormer are
complete forecasting models trained for missing inputs. They do not compose with a frozen
backbone, they have no reference action, and the harmful rate of an intervention is undefined
for them, so putting them in the same rank as a data-side adapter would compare two different
contracts. They belong to the setting this paper does not address, which is training a
forecaster of one's own.
```

**中文直译**

最后一组属于另一种排除情况。BiTGraph、S4M 和 ChannelTokenFormer 是针对缺失输入训练的完整预测模型，不能与冻结骨干组合，也没有参考动作，干预伤害率对它们未定义。因此，将它们与数据侧适配器放在同一排名中会比较两种不同约束。它们属于本文不处理的设置，即自行训练预测器。

## 对照 124

```latex
\caption{The comparison roster used for the recorded evaluation. Every row composes with
the same frozen backbone and is given the same evidence, which is the TRAIN region under the
registered missingness protocol including the realised futures of those windows. No row sees
a TEST window before its numbers are computed.}
```

**中文直译**

已记录评估使用的比较方法清单。各行组合相同冻结骨干，获得相同证据，即登记缺失协议下的 TRAIN 区域及这些窗口已实现的未来。参数拟合使用 TRAIN。早期 TEST 结果影响了方法开发，如前文所披露。

### 共用数值表 11

```latex
\begin{tabular}{@{}l p{0.76\textwidth}@{}}
    \toprule
    Row & What it does \\
    \midrule
    \textsc{Native Keep} & hands the incomplete context to the frozen backbone and never intervenes. Every other row is measured against it \\
    \textsc{Best Fixed} & applies to every request the single catalog action with the highest mean realised utility on the replay bank, which makes it the strongest policy that ignores the request \\
    Source Fixed & selects the highest-mean-utility catalog action separately for each source on TRAIN, with KEEP as fallback when that action is unavailable \\
    R2-CART & one depth-three classification tree per action over the same state features, each asking whether that action beats the reference. The most confident action runs when its probability exceeds one half \\
    Fixed SAITS & applies the trained imputer to every incomplete request. The imputer is one of the six catalog actions and its bank records are cross-fitted by parent, so the stored utility is out of sample \\
    TATO & searches one transformation pipeline per source against the realised futures of the same TRAIN windows the replay bank is built from \\
    TimesNet & applies the packaged TimesNet imputer, trained once per source on that source's TRAIN bank windows under the registered missingness protocol, to every incomplete request \\
    PSW-I & optimises the missing entries of each request independently by minimising the proximal spectrum Wasserstein discrepancy of that request's visible context, with no cross-request information \\
    T1 & applies the official T1 imputer, trained once per source on the same TRAIN bank windows, to every incomplete request \\
    \emph{Catalog Oracle} & reads the future target and takes the best catalog action in hindsight. Diagnostic only, excluded from every rank and every claim \\
    \bottomrule
  \end{tabular}
```

**中文表内文字**

列为方法行、行为。
Native KEEP 将不完整上下文交给冻结骨干，从不干预，其他行均相对于它测量。
Best Fixed 对每个请求应用回放库平均已实现效用最高的单一目录动作，为忽略请求信息的最强固定策略。
Source Fixed 在 TRAIN 上为每个源单独选择平均效用最高的目录动作，不可用时回退到 KEEP。
R2-CART 对每个动作在相同状态上训练深度三分类树，判断动作是否优于参考。置信度最高动作的概率超过一半时执行。
Fixed SAITS 对每个不完整请求应用训练插补器，它也是六个目录动作之一。回放记录按父窗口交叉拟合，因此存储效用为样本外结果。
TATO 在回放库所用 TRAIN 窗口的已实现未来上，为每个源搜索一条变换流程。
TimesNet 在每个源的 TRAIN 库窗口上按登记缺失协议训练一次，将打包插补器用于每个不完整请求。
PSW-I 通过最小化各请求可见上下文的近端谱 Wasserstein 差异，独立优化其缺失值，不使用跨请求信息。
T1 在同样 TRAIN 库窗口上每源训练一次，将官方插补器用于每个不完整请求。
目录 Oracle 读取未来目标，事后选最佳动作，只用于诊断，排除于所有排名与主张。

## 对照 125

```latex
\subsection{Baseline Configuration}
```

**中文直译**

基线配置

## 对照 126

```latex
Baseline fitting and replay construction use the TRAIN region and its historical targets.
The current comparison reuses an evaluation block examined during earlier development, as
disclosed in Appendix~\ref{app:splits}.
```

**中文直译**

基线拟合与回放构造使用 TRAIN 区域及其历史目标。当前比较复用早期开发检查过的评估块，这一点已在附录 \ref{app:splits} 披露。

## 对照 127

```latex
\caption{What each fitted row was given. Each reads the TRAIN region under the registered
missingness protocol, including the realised futures of those windows, and neither sees a
TEST window before its numbers are computed.}
```

**中文直译**

各拟合方法获得的内容。每个拟合方法读取登记缺失协议下的 TRAIN 区域，包括窗口已实现的未来，拟合不使用 TEST 目标。早期开发使用过同一 TEST 块。

### 共用数值表 12

```latex
\begin{tabular}{@{}p{0.17\textwidth} p{0.26\textwidth} p{0.47\textwidth}@{}}
    \toprule
    Row & Unit of fitting & Configuration \\
    \midrule
    Fixed SAITS, deployment model & one per source, on every bank parent & the packaged implementation, two layers, model width 128, four heads, feed-forward width 128, dropout $0.1$, batch size 16, at most 100 epochs with early stopping. Sources with more than 64 channels use the target channel plus the covariates most correlated with it on TRAIN \\
    Fixed SAITS, bank records & two per source, each on half the bank parents by origin time & the same configuration. A window is repaired only by the model that never saw its own parent, so the utility stored for this action is out of sample \\
    TATO & one pipeline per source and backbone & the official implementation over its eight transformation slots, 48 trials seeded with the identity pipeline, each scored by the mean absolute error against the realised futures of 8 TRAIN windows. Gaps are filled by linear interpolation first, which the official pipeline requires, and that step is part of what the row measures \\
    TimesNet & one deployment model per source, on every bank parent & the official Time-Series-Library imputation configuration: two layers, top\_k $=3$, six kernels, dropout $0.1$, batch size 16, learning rate $10^{-3}$, at most 10 epochs with early stopping (patience 3), seed 101. Width follows the official scripts: 16/32 for the ETT sources and Exchange, 64/64 for Electricity, Weather and Traffic. No cross-fitting: the same deployment model repairs the evaluation requests of every backbone \\
    \bottomrule
  \end{tabular}
```

**中文表内文字**

列为方法行、拟合单位、配置。
Fixed SAITS 部署模型每源一个，使用全部库内父窗口。打包实现，二层、模型宽度 128、四头、前馈宽度 128、dropout 0.1、批量 16、最多 100 轮及早停。超过 64 通道时使用目标及 TRAIN 上最相关协变量。
Fixed SAITS 回放模型每源两个，分别使用按起点顺序划分的一半父窗口。配置相同，窗口仅由未见过其父窗口的模型修复，效用为样本外。
TATO 每源每骨干一条流程。官方实现八个变换槽位，48 次试验，以恒等流程初始化，每次以 8 个 TRAIN 窗口已实现未来上的 MAE 评分。按官方要求先线性插值，该步骤计入结果。
TimesNet 每源一个部署模型，使用全部库内父窗口。官方 Time-Series-Library 插补配置，二层、top_k=3、六个核、dropout 0.1、批量 16、学习率 10⁻³、最多 10 轮，早停耐心 3、种子 101。ETT 和 Exchange 宽度为 16/32，Electricity、Weather、Traffic 为 64/64。不交叉拟合，同一部署模型修复所有骨干的评价请求。

## 对照 128

```latex
\paragraph{The trained imputer.} One imputer per source, trained on that source's TRAIN bank
```

**中文直译**

训练后的插补器。每个源训练一个插补器，训练数据为该源的 TRAIN 回放库窗口。

## 对照 129

```latex
windows after the missingness protocol has been injected, so the training distribution is the
one the evaluation produces. A deployment model and two cross-fitting models are used per source. The deployment model reads every
bank parent and repairs every evaluation request, and it is what the \textsc{Fixed SAITS} row
and the catalog action both call at serving time. The bank records come from two cross-fitted models: the parents of the source are split into two interleaved folds by origin order, each fold trains a model, and
that model repairs only the windows of the other fold. Without that split the utility stored
for this action would be the utility of repairing a window the model had already seen, and the
selector would learn to execute it more often than the evidence supports. The architecture is the packaged implementation~\citep{du2023pypots} with
two layers, model width 128, four heads, feed-forward width 128, dropout $0.1$, batch size 16
and at most 100 epochs with early stopping. Sources with more channels than
64 are imputed on the target channel plus the covariates most correlated with it
on TRAIN, which is a budget constant fixed before any run and recorded with the configuration.
The imputed panel is spliced back against the observation mask, so an entry that arrived and is
valid is returned unchanged and only the missing positions carry imputed values. That is the
same integrity constraint every catalog action obeys, and it is what makes the comparison a
comparison under a common observation mask.
```

**中文直译**

窗口先注入缺失协议，因此训练分布与评价生成的分布一致。每个源使用一个部署模型和两个交叉拟合模型。部署模型读取所有回放库父窗口，修复所有评价请求，服务时 Fixed SAITS 行和目录动作都调用它。回放记录来自两个交叉拟合模型，将该源父窗口按时间顺序交错分为两折，每折训练一个模型，仅修复另一折窗口。没有此划分，存储效用会描述模型已经见过的窗口上的修复，选择器可能据此过度执行。架构采用打包实现，二层、模型宽度 128、四头、前馈宽度 128、dropout 0.1、批量 16，最多 100 轮并早停。通道数超过 64 的源仅对目标通道及 TRAIN 上与其最相关的协变量插补，这是运行前固定并记录的预算常数。插补面板按观测掩码拼回，因此有效已到达条目原样返回，只有缺失位置写入插补值。这是所有目录动作共同遵守的完整性约束，使比较使用共同观测掩码。

## 对照 130

```latex
\paragraph{TATO.} One transformation pipeline per source and per backbone, searched with the
```

**中文直译**

TATO。每个源和每个骨干搜索一条变换流程，使用其官方实现。

## 对照 131

```latex
official implementation over its eight transformation slots. A candidate pipeline is scored by
the mean absolute error of the resulting forecast against the realised future of
8 TRAIN windows of that source, the same futures the replay bank is built from,
over 48 trials seeded with the identity pipeline. The selected pipeline is then
applied unchanged to every TEST request of that source, which is the domain-level unit of
adaptation the method is defined at. The official pipeline expects a context without gaps, so
the adapter fills them by linear interpolation before the pipeline runs, and that step is
part of what the row measures, and Section~\ref{sec:exp-main} reads the result with that in
mind. The upstream replacement of non-finite outputs is disabled, so a pipeline that diverges
is recorded as a failed trial instead of being silently repaired.
```

**中文直译**

搜索覆盖八个变换槽位。候选流程的评分，是该源 8 个 TRAIN 窗口的预测相对于已实现未来的平均绝对误差，这些未来也用于回放库。搜索进行 48 次试验，以恒等流程初始化。选定流程原样应用于该源所有 TEST 请求，这与方法定义的领域级适配单位一致。官方流程要求无缺口上下文，因此适配器先线性插值，再运行流程，该步骤属于测量内容，第 \ref{sec:exp-main} 节据此解释结果。上游替换非有限输出的机制被禁用，发散流程被记为失败试验，不静默修复。

## 对照 132

```latex
\section{Method and Implementation Details}
```

**中文直译**

方法与实现细节

## 对照 133

```latex
This section expands \S\ref{sec:method} with the implementation-level definitions of the
closed intervention catalog, the state features, the relation of the decision layer to
off-policy evaluation and selective prediction, the replay-bank construction, the local
utility estimator, and the complete-input contract. The state features are defined here
once, and the main text refers to this section for their detailed definitions.
```

**中文直译**

本节补充第 \ref{sec:method} 节，给出封闭干预目录、状态特征、决策层与离策略评价及选择性预测的关系、回放库构造、局部效用估计和完整输入约定的实现定义。状态特征仅在此完整定义一次，正文引用此节获取细节。

## 对照 134

```latex
\subsection{Intervention Catalog}
```

**中文直译**

干预目录

## 对照 135

```latex
Table~\ref{tab:app-catalog} defines \textsc{Keep} and five repairs. All preserve valid observed
entries by contract. SAITS requires training data, so replay supervision should use
out-of-fold repairs. The retained v47 implementation uses two folds. Four-fold cross-fitting
belongs to the separate verification revision and is not established by the results here.
```

**中文直译**

表 \ref{tab:app-catalog} 定义 KEEP 和五种修复。所有动作按约定保留有效观测。SAITS 需要训练数据，因此回放监督应使用折外修复。保留的 v47 实现采用两折，四折交叉拟合属于独立核验版本，本文结果没有确立其表现。

## 对照 136

```latex
\caption{The six admissible interventions. Observed entries are the entries that are
present and valid in the reference input $X^{a_0}$, and an action that modified them would
violate the integrity constraint of \S\ref{sec:method-problem}.}
```

**中文直译**

六种可用干预。已观测条目是参考输入 X^{a₀} 中存在且有效的条目，修改它们会违反第 \ref{sec:method-problem} 节的完整性约束。

### 共用数值表 13

```latex
\begin{tabularx}{\textwidth}{@{}lXrr@{}}
    \toprule
    Action & Input version produced & \shortstack[r]{Modify\\observations?} & \shortstack[r]{Extra\\calls} \\
    \midrule
    \textsc{Keep} $a_0$   & the incomplete context, unchanged & reference action & 0 \\
    \textsc{Ffill}        & forward-fill from the last valid value & no & 1 \\
    \textsc{Single TS-ICL}& univariate in-context regression on the target channel & no & 1 \\
    \textsc{Multi TS-ICL} & multivariate in-context regression using visible channels & no & 1 \\
    \textsc{Context Ridge}& ridge reconstruction from the visible context & no & 1 \\
    \textsc{SAITS}        & reconstruction by the trained imputer of the source & no & 1 \\
    \bottomrule
  \end{tabularx}
```

**中文表内文字**

列为动作、产生的输入版本、是否修改观测、额外调用。KEEP a₀ 保留不完整上下文，是参考动作，额外调用 0。FFILL 用最后有效值前向填充，Single TS-ICL 在目标通道做单变量上下文回归，Multi TS-ICL 利用可见通道做多变量上下文回归，Context Ridge 从可见上下文做岭回归重建，SAITS 使用该源训练插补器重建。后五者均不修改观测，额外预测骨干调用均为 1。

## 对照 137

```latex
A complete and valid input is always mapped to \textsc{Keep} and the reference forecast is
returned unchanged. Unsupported, aliased, and failed actions are recorded with an explicit
status, and they are never counted as successes. The required behaviour of the system in each
input regime is listed in \S\ref{app:contract}.
```

**中文直译**

完整且有效的输入总映射到 KEEP，原样返回参考预测。不受支持、别名等同和失败动作均显式记录状态，不计为成功。第 \ref{app:contract} 节列出各输入情形的系统要求。

## 对照 138

```latex
The reference action passes the incomplete context to the frozen pipeline unchanged.
Chronos-Bolt and Chronos-2 accept NaN entries under their native mask semantics, TimesFM-2.5's
official input pipeline interpolates within the context and strips NaN prefixes, and the adapter
adds no imputation of its own and records a non-finite output as a failure.
```

**中文直译**

参考动作将不完整上下文原样传入冻结流程。Chronos-Bolt 和 Chronos-2 按原生掩码语义接受 NaN，TimesFM-2.5 的官方输入流程在上下文内插值并去除 NaN 前缀。适配器不额外插补，非有限输出记为失败。

## 对照 139

```latex
\subsection{State Features}
```

**中文直译**

状态特征

## 对照 140

```latex
The state is action conditioned and is written $z_a$ for action $a$, with
```

**中文直译**

状态以动作为条件，动作 a 的状态记为 zₐ，定义如下。

**共用公式**

```latex
\begin{equation}
  z_a \;=\; \phi\!\left(X,\, M,\, X^{a},\, p_0\right),
  \qquad p_0 = F(X^{a_0}) .
  \label{eq:app-state}
\end{equation}
```

## 对照 141

```latex
It contains no future target information. It uses the reference forecast $p_0$, which the
call budget of \S\ref{sec:method-problem} already permits, and it never uses the forecast of a
non-selected candidate. Table~\ref{tab:app-features} is the canonical definition of the four
groups, including the window length, the channel aggregation, and the missing-value handling
of each feature. Continuous features are standardised with statistics fitted on the replay
bank only, and the normalisation is frozen with the rest of the configuration.
```

**中文直译**

状态不包含未来目标信息。它使用第 \ref{sec:method-problem} 节调用预算已允许的参考预测 p₀，从不使用未选候选的预测。表 \ref{tab:app-features} 是四组特征的完整定义，包括窗口长度、通道聚合和各特征的缺失处理。连续特征仅用回放库上拟合的统计量标准化，并与其余配置一同冻结。

## 对照 142

```latex
\caption{The action-conditioned state, as implemented. It has 22 dimensions: six describing
the mask, six describing the visible context, five describing the candidate intervention and
five describing the reference forecast. Every feature is computable from the request and the
reference forecast alone. The target channel is the forecast channel, and the only place the
other channels enter is the shared indicator. Features are divided by the robust scale $s$ of
the visible context where they carry a unit, and the state is then standardised with the mean
and standard deviation of the replay bank before distances are taken.}
```

**中文直译**

实现中的动作条件状态，共 22 维，六维描述掩码，六维描述可见上下文，五维描述候选干预，五维描述参考预测。每个特征都仅依靠请求与参考预测即可计算。目标通道是预测通道，其他通道只通过共享指示量进入。带单位的特征除以可见上下文的稳健尺度 s，计算距离前，再用回放库均值和标准差对状态标准化。

### 共用数值表 14

```latex
\adjustbox{max width=\textwidth}{\begin{tabular}{@{}l p{0.22\textwidth} p{0.42\textwidth} p{0.16\textwidth}@{}}
    \toprule
    Group & Feature & Definition & Scaling \\
    \midrule
    Mask state, 6 & missing ratio & share of target-channel positions with $M = 0$ & scale free \\
     & longest run & longest run of consecutive missing positions, as a share of $L$ & scale free \\
     & number of runs & count of maximal missing runs, divided by $L$ & scale free \\
     & distance to origin & steps from the end of the last missing run to the forecast origin, divided by $L$ & scale free \\
     & shared indicator & one if any other channel is also missing & binary \\
     & tail indicator & one if the last context position is missing & binary \\
    \midrule
    Visible-context state, 6 & robust scale $s$ & median over eight blocks of the interquartile range of the visible target values & the unit of the other context features \\
     & local trend & least-squares slope over the visible positions, divided by $s$ & scale free \\
     & lag-one autocorrelation & autocorrelation of the gap-interpolated target at lag one & scale free \\
     & seasonal autocorrelation & the same at the registered seasonal period $m$ & scale free \\
     & recent level shift & absolute difference between the means of the last and the preceding $W = 32$ steps, divided by $s$ & scale free \\
     & recent volatility & standard deviation of the first differences over the last $W$ steps, divided by $s$ & scale free \\
    \midrule
    Intervention state, 5, per action $a$ & mean absolute change & mean of $|X^{a} - \tilde{X}|$ over the repair positions, divided by $s$ & scale free \\
     & maximum change & largest absolute difference, divided by $s$ & scale free \\
     & changed fraction & share of window positions that are repair positions & scale free \\
     & change trend & least-squares slope of the difference over the repair positions, divided by $s$ & scale free \\
     & change near origin & mean absolute difference over the repair positions in the last $W$ steps, divided by $s$ & scale free \\
    \midrule
    Reference-forecast state, 5 & forecast level & mean of $p_0$ over the horizon, divided by $s$ & scale free \\
     & forecast range & range of $p_0$ over the horizon, divided by $s$ & scale free \\
     & forecast trend & least-squares slope of $p_0$, divided by $s$ & scale free \\
     & first-step jump & first step of $p_0$ minus the last visible value, divided by $s$ & scale free \\
     & roughness & mean absolute first difference of $p_0$, divided by $s$ & scale free \\
    \bottomrule
  \end{tabular}}
```

**中文表内文字**

列为组、特征、定义、缩放。除注明外，特征均无量纲。
掩码状态六维。缺失率是目标中 M=0 的位置比例。最长缺失段长度除以 L。缺失段数为极大连续缺失段计数除以 L。距起点距离是最后缺失段末端至预测起点的步数除以 L。共享指示量在任一其他通道也缺失时为一，是二值量。尾部指示量在最后上下文位置缺失时为一，是二值量。
可见上下文六维。稳健尺度 s 为八个块中可见目标四分位距的中位数，是其余上下文特征的单位。局部趋势为可见位置最小二乘斜率除以 s。一阶自相关为缺口插值目标的一阶自相关。季节自相关为相同序列在登记周期 m 处的自相关。近期水平偏移为最后 W=32 步与前 W 步均值差的绝对值除以 s。近期波动为最后 W 步一阶差分标准差除以 s。
每动作干预状态五维。平均绝对变化为修复位置 |Xᵃ−X̃| 的均值除以 s。最大变化为最大绝对差除以 s。改变比例为窗口中修复位置占比。变化趋势为修复位置差值的最小二乘斜率除以 s。近起点变化为最后 W 步修复位置绝对差的均值除以 s。
参考预测状态五维。预测水平为预测范围内 p₀ 均值除以 s。预测范围为 p₀ 极差除以 s。预测趋势为 p₀ 最小二乘斜率除以 s。首步跳跃为 p₀ 首步减最后可见值再除以 s。粗糙度为 p₀ 平均绝对一阶差分除以 s。

## 对照 143

```latex
The intervention group compares $X^{a}$ not with the raw reference but with a baseline
$\tilde{X}$ that gap-interpolates the visible reference target. The baseline is a pure
function of the visible values: it involves no model and no future labels. The repair
positions are the positions where the reference is missing and the candidate is finite, and
the difference $X^{a} - \tilde{X}$ is evaluated there, divided by the robust scale. For
\textsc{Keep} the candidate is the reference itself, so its repair set is empty by
definition and all five intervention features are zero, including a changed fraction of
zero. For any other action with an empty repair set the four magnitude features are also
zero. The features therefore vary across the catalog actions without ever reading the
target at a missing position.
```

**中文直译**

干预组将 Xᵃ 与可见参考目标经缺口插值后的基线 X̃ 比较，不直接与原始参考比较。该基线仅由可见值决定，不涉及模型或未来标签。修复位置是参考缺失而候选有限的位置，在这些位置计算 Xᵃ−X̃，并除以稳健尺度。KEEP 的候选即参考自身，修复集按定义为空，五个干预特征均为零，包括改变比例。其他动作若修复集为空，四个幅度特征也为零。因此，这些特征随目录动作变化，始终不读取缺失位置的目标值。

## 对照 144

```latex
\subsection{Relation to Off-Policy Evaluation and Selective Prediction}
```

**中文直译**

与离策略评价及选择性预测的关系

## 对照 145

```latex
The decision layer is related to conservative policy selection in contextual
bandits~\citep{abbasiyadkori2011improved,lattimore2020bandit} and to off-policy
evaluation~\citep{strehl2010learning,dudik2011doubly,swaminathan2015counterfactual,
jiang2016doubly,thomas2016data}, and the difference that matters is the structure of the
supervision. Off-policy evaluation estimates the value of a target policy from data collected
by a logging policy, with outcomes observed only for the selected actions. Estimation can
use outcome models, propensity weighting or both, under the corresponding assumptions. Historical replay gives full action outcomes for the finite catalog,
because every action is executed on the same window and evaluated against the same realised
future. There is therefore no partial-feedback problem to correct, and there is no online
exploration: no action is ever executed at deployment in order to learn.
```

**中文直译**

决策层与上下文老虎机中的保守策略选择及离策略评价有关，关键差异在于监督结构。离策略评价利用日志策略采集的数据估计目标策略价值，只能观察被选动作的结果，在相应假设下使用结果模型、倾向加权或二者结合。历史回放为有限目录提供全动作结果，因为每个动作都在同一窗口执行，针对同一已实现未来评价。因此无需校正部分反馈，也不存在在线探索，部署时不会为了学习而执行动作。

## 对照 146

```latex
\caption{Where the decision layer sits. The row that matters is the third column: what has to
be corrected for before the recorded outcomes can be used.}
```

**中文直译**

决策层的定位。关键是第三列，即使用记录结果前需要校正什么。

### 共用数值表 15

```latex
\begin{tabular}{@{}p{0.19\textwidth} p{0.33\textwidth} p{0.38\textwidth}@{}}
    \toprule
    Setting & What the record holds & What it needs \\
    \midrule
    Off-policy evaluation & the outcome of the logged action alone & outcome modeling or propensity-based adjustment for selectively observed feedback \\
    Selective prediction and learning to defer & the outcome of the answer that was produced & a second answerer, or an abstention, since what changes is who answers \\
    Historical full-action replay & the outcome of every catalog action on the same window against the same realised future & nothing of the kind. There is no partial feedback to correct and no online exploration, because no action is ever executed at deployment in order to learn \\
    \bottomrule
  \end{tabular}
```

**中文表内文字**

列为设置、记录包含的内容、所需处理。离策略评价仅含日志动作结果，需要结果建模或倾向校正以处理选择性反馈。选择性预测和学习转交包含实际生成答案的结果，需要第二回答者或弃权，因为改变的是谁回答。历史全动作回放包含同窗口、同已实现未来下所有目录动作结果，无需上述处理，没有部分反馈校正，也无在线探索，部署时不为学习而执行动作。

## 对照 147

```latex
Selective prediction abstains on part of the input in order to trade coverage for lower
risk~\citep{chow1970optimum,vovk2005algorithmic,geifman2017selective,lei2018distribution}, and
learning to defer routes part of the input to a human or to another decision
maker~\citep{madras2018predict,mozannar2020consistent}. Both change who or what produces the
answer. \introact{} changes neither. The same frozen forecaster returns a forecast in every
case, and what is selected is whether the input is modified first. Dynamic feature
selection~\citep{he2024dime} is a related sequential-acquisition setting in which the value of
additional information is weighed against its cost. We make no information-theoretic
optimality claim and report the cost accounting separately (Appendix~\ref{app:calls}).
```

**中文直译**

选择性预测在部分输入上弃权，以覆盖率换取较低风险，学习转交则将部分输入交给人或其他决策者。二者均改变答案的生成者。IntroAct-TS 在每种情形都由同一冻结预测器返回预测，只决定是否先修改输入。动态特征选择属于相关的顺序获取设置，权衡新增信息的价值与成本。我们不主张信息论最优性，并单独报告成本核算，见附录 \ref{app:calls}。

## 对照 148

```latex
\subsection{Replay Construction}
```

**中文直译**

回放构造

## 对照 149

```latex
Two properties of the bank carry the scope of the method. It is indexed by the frozen backbone
revision, since a utility measured with one revision of one model does not describe another.
The method therefore requires labelled history for the backbone it serves, which places it in
a setting with a frozen backbone and supervised historical data. The bank also
covers only the missingness protocol registered in advance, so it is a discrete grid over
patterns and severities.
```

**中文直译**

回放库的两个属性决定方法范围。其按冻结骨干版本建立索引，因为一个版本测得的效用不能描述另一版本。因此，本方法需要所服务骨干对应的带标签历史，属于冻结骨干加历史监督数据的设置。回放库仅覆盖预先登记的缺失协议，构成模式和严重度的离散网格。

## 对照 150

```latex
The split rule is fixed in Appendix~\ref{app:splits}. This subsection records how the replay bank is built. These definitions specify how the recorded results should be interpreted.
```

**中文直译**

划分规则固定于附录 \ref{app:splits}。本节记录回放库如何构建，这些定义明确已记录结果应如何解释。

## 对照 151

```latex
The replay bank is constructed as follows. For every bank parent we take the historical
window $(X_i, y_i)$ whose future is already available history, inject the registered
missingness protocol to obtain the incomplete version $X_i^{a_0}$, materialise every action
$a \in \calA$ into $X_i^{a}$, execute the frozen pipeline on each materialised version, and
store the realised utility
```

**中文直译**

回放库按以下方式构造。对于每个库内父窗口，取未来已属于可用历史的窗口 (Xᵢ,yᵢ)，注入登记缺失协议得到不完整版本 Xᵢ^{a₀}，构造每个动作 a∈A 对应的 Xᵢᵃ，在每个版本上执行冻结流程，并存储如下已实现效用。

**共用公式**

```latex
\begin{equation}
  g_{i,a} \;=\; \loss\big(F(T_{a_0}(X_i, M_i)),\, y_i\big) - \loss\big(F(T_{a}(X_i, M_i)),\, y_i\big),
  \label{eq:app-gain}
\end{equation}
```

## 对照 152

```latex
so that $g_{i,a} > 0$ means the action reduced the forecasting loss and $g_{i,a} < 0$ means it
increased it. The bank is
$\calB = \{(z_{i,a}, a, g_{i,a})\}$, where $z_{i,a}$ is the action-conditioned state defined
in Appendix~\ref{app:features}. Because a utility measured with one model revision does not describe another, the bank is
built per frozen backbone revision, and one bank serves every source and both horizons, so
retrieval is never restricted to the request's own source or horizon. Pseudo-deployment
severities enumerate
$\{10\%, 30\%, 50\%\}$ on every parent, pattern and horizon, so a request at any registered
severity has same-severity support and the method is not retuned per severity.
```

**中文直译**

gᵢ,ₐ>0 表示动作降低预测损失，gᵢ,ₐ<0 表示增加损失。回放库 B={(zᵢ,ₐ,a,gᵢ,ₐ)}，zᵢ,ₐ 是附录 \ref{app:features} 定义的动作条件状态。由于一个模型版本的效用不描述另一版本，回放库按冻结骨干版本构建。一套库服务全部源和两个预测长度，检索从不限制于请求所属源或长度。伪部署严重度在每个父窗口、模式和长度上枚举 {10%,30%,50%}，因此任一登记严重度的请求都有同严重度支持，方法不按严重度重新调参。

## 对照 153

```latex
Because the bank is built once from TRAIN and never rebuilt at deployment time, the offline
cost is paid once. Appendix~\ref{app:calls} separates it from the per-request online cost.
```

**中文直译**

回放库从 TRAIN 一次性构建，部署时不重建，因此离线成本只支付一次。附录 \ref{app:calls} 将其与逐请求在线成本分开。

## 对照 154

```latex
\subsection{Local Utility Estimation}
```

**中文直译**

局部效用估计

## 对照 155

```latex
The ablations of \S\ref{sec:exp-ablation} assess whether local estimates still produce
useful decisions. The source-fixed policy and the linear utility estimator are each
competitive in aggregate. The source-fixed policy is ahead of the full method on Bolt and
behind on Chronos-2, the linear estimator is ahead on TimesFM and behind on Bolt and
Chronos-2. And removing either state group leaves the aggregate within 0.012 of the full
method. Relaxing the decision rule (A5 and A6) raises intervention and harmful loss at
every severity without a consistent accuracy direction. The evidence supports evaluating
the decision rule directly and leaves the choice of state representation open.
```

**中文直译**

第 \ref{sec:exp-ablation} 节的消融评价局部估计是否仍能产生有用决策。源固定策略和线性效用估计器在总体上都有竞争力。源固定策略在 Bolt 上优于完整方法、在 Chronos-2 上较差，线性估计器在 TimesFM 上更好、在 Bolt 和 Chronos-2 上较差。移除任一状态组时，总体值与完整方法差距均在 0.012 内。放松决策规则 A5 和 A6 在每个严重度上提高干预和伤害损失，但精度变化方向不一致。证据支持直接评价决策规则，状态表示的选择仍未解决。

## 对照 156

```latex
\subsection{Complete-Input Contract}
```

**中文直译**

完整输入约定

## 对照 157

```latex
Under a complete and valid input, \introact{} must return \textsc{Keep}. No forecasting
improvement is claimed in this regime. The purpose of this subsection is to document the
required governance behaviour. Table~\ref{tab:app-complete} lists the
regimes and the required behaviour in each.
```

**中文直译**

输入完整有效时，IntroAct-TS 必须返回 KEEP，不主张此时能改善预测。本节记录所要求的治理行为。表 \ref{tab:app-complete} 列出各情形及要求。

## 对照 158

```latex
\caption{Governance contract by input regime. The complete-input rows are contract
statements and not accuracy results. The expected behaviour there is a no-op, and a non-no-op
would violate the input-preservation requirement.}
```

**中文直译**

不同输入情形的治理约定。完整输入行是约定陈述，不是精度结果。预期行为是不操作，其他行为会违反输入保留要求。

### 共用数值表 16

```latex
\adjustbox{max width=\textwidth}{\begin{tabular}{@{}p{.18\textwidth}p{.44\textwidth}p{.31\textwidth}@{}}
    \toprule
    Input regime & Required behaviour & Claim \\
    \midrule
    Complete and valid input            & return \textsc{Keep} and the reference forecast & no-op contract, no accuracy claim \\
    Complete input, malformed request   & reject with an explicit status & no claim \\
    Unsupported action requested        & reject the action, keep the catalog closed & no claim \\
    Incomplete input, no action scores above zero & return the reference action & the reference action is always available \\
    Incomplete input, one action scores above zero & execute exactly one action and return its forecast & evaluated in \S\ref{sec:exp-main} \\
    \bottomrule
  \end{tabular}}
```

**中文表内文字**

列为输入情形、要求行为、主张。完整有效输入返回 KEEP 和参考预测，属于不操作约定，不主张精度。完整但格式错误的请求显式拒绝，不作性能主张。不支持的动作被拒绝，目录保持封闭，不作性能主张。不完整输入且无得分大于零的动作时返回参考动作，参考动作始终可用。不完整输入且有动作超过零时恰好执行一个动作并返回预测，在第 \ref{sec:exp-main} 节评价。

## 对照 159

```latex
\section{Forecasting Results}
```

**中文直译**

预测结果

## 对照 160

```latex
This section collects the complete forecasting-result tables behind \S\ref{sec:exp-exists}
and \S\ref{sec:exp-main}.
```

**中文直译**

本节汇集第 \ref{sec:exp-exists} 和 \ref{sec:exp-main} 节背后的完整预测结果表。

## 对照 161

```latex
\subsection{Numerical Values for Action Utility}
```

**中文直译**

动作效用数值

## 对照 162

```latex
The following table preserves the values plotted in Figure~\ref{fig:utility}.
```

**中文直译**

下表保留图 \ref{fig:utility} 绘制的数值。

## 对照 163

```latex
\caption{Why the choice has to be made per request. The shares and mean utilities are
macro-averaged over the evaluation episodes of all three backbones. The episode counts are
per backbone and identical across backbones, because action availability does not depend on
the backbone. Oracle-best share is how often an action attains the lowest realised loss of the
catalog and the shares sum to one. The last two columns cover the episodes where the action
applies and are measured against \textsc{Keep}.}
```

**中文直译**

为何需要按请求选择。比例和平均效用在三个骨干的评价样例上宏平均。样例数按骨干统计，且各骨干一致，因为动作可用性不依赖骨干。Oracle 最优占比表示动作取得目录最低已实现损失的频率，占比之和为一。最后两列覆盖动作可用的样例，并相对于 KEEP 测量。

### 共用数值表 17

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrr@{}}
    \toprule
    Action & Best share & Available episodes & Beneficial share & Mean utility \\
    \midrule
    \textsc{Keep} $a_0$ & 19.3\% & 760 & n/a & 0.000 \\
    \textsc{Ffill} & 17.1\% & 760 & 42.1\% & -0.094 \\
    \textsc{Single TS-ICL} & 15.4\% & 760 & 53.3\% & +0.055 \\
    \textsc{Multi TS-ICL} & 12.3\% & 758 & 54.1\% & +0.076 \\
    \textsc{Context Ridge} & 11.1\% & 566 & 58.3\% & +0.112 \\
    \textsc{SAITS} & 24.8\% & 747 & 57.1\% & +0.101 \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 164

```latex
{\footnotesize Reconstruction accuracy does not order the repairs the way realised utility
  does. On the Bolt episodes, the most accurate reconstruction is the most useful repair on
  19.3\% of the
  episodes, 44.5\% of the ordered pairs disagree, and the mean within-episode
  rank correlation is 0.12. Appendix~\ref{app:recutils} reports both criteria per
  action.}
```

**中文直译**

重建精度对修复的排序与已实现效用不同。在 Bolt 样例上，最准确重建仅在 19.3% 的样例上也是最有用修复，44.5% 的有序对排序不一致，样例内平均秩相关为 0.12。附录 \ref{app:recutils} 逐动作报告两种标准。

## 对照 165

```latex
\subsection{Reconstruction versus Forecasting Utility}
```

**中文直译**

重建与预测效用的比较

## 对照 166

```latex
This subsection supports \S\ref{sec:exp-exists}. Reconstruction error is defined only where a
method emits an explicit estimate of the hidden positions, which all five catalog interventions
do. Running the comparison on the catalog keeps both criteria on one protocol and
one set of episodes: the same window, the same mask, the same frozen backbone, and the same
realised future. \textsc{Keep} does not enter, because it estimates nothing, and \introact{}
is evaluated through its selected forecast.
```

**中文直译**

本节支持第 \ref{sec:exp-exists} 节。仅当方法显式估计隐藏位置时才定义重建误差，目录的五种干预均满足。以同一目录比较，使两项标准基于相同协议和样例，即同一窗口、掩码、冻结骨干和已实现未来。KEEP 不作估计，故不纳入。IntroAct-TS 通过所选预测评价。

## 对照 167

```latex
Reconstruction error is measured on the artificially hidden positions of the target channel,
which are known because the mask is synthetic. Realised utility is the change in forecasting
loss the same action produced on the same episode. Both rankings are formed inside an episode
and then compared, because episodes differ in scale and in difficulty and pooling them would
let a few large-scale sources decide the answer. Table~\ref{tab:app-recutils} gives the
per-action averages and the two rank statistics.
```

**中文直译**

重建误差在目标通道人工隐藏的位置上测量，因为掩码为合成，这些真值已知。已实现效用是同一动作在同一样例上造成的预测损失变化。两种排序先在样例内建立，再比较，因为各样例尺度和难度不同，混合它们可能让少数大尺度数据源主导结论。表 \ref{tab:app-recutils} 给出逐动作平均及两个排序统计量。

## 对照 168

```latex
\caption{Within-episode reconstruction rank against forecasting-utility rank for the five repairs. Each row is normalised to $100\%$ up to rounding. Concentration away from the diagonal shows disagreement between the criteria. Cells reproduce the recorded table percentages.}
```

**中文直译**

五种修复的样例内重建排序与预测效用排序对照。各行除舍入外归一化到 100%。质量集中于对角线之外说明两标准不一致。单元复现记录表中的百分比。

## 对照 169

```latex
\caption{Reconstruction quality against realised forecasting utility, over the five catalog
interventions on the reused evaluation episodes of the Bolt backbone. Reconstruction error is measured on the
hidden positions and realised utility against \textsc{Keep} on the same backbone. Winner
agreement is the share of episodes on which the most accurate reconstruction is also the most
useful intervention, and the discordant rate is the share of ordered pairs whose two rankings
disagree.}
```

**中文直译**

Bolt 骨干复用评价样例上，五种目录干预的重建质量与已实现预测效用。重建误差在隐藏位置测量，效用在同骨干上相对于 KEEP 计算。优胜动作一致率是最准确重建也最有用的样例比例，排序不一致率是两个排序不一致的有序对比例。

### 共用数值表 18

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrr@{}}
    \toprule
    Intervention & Rec.\ MSE $\downarrow$ & Rec.\ MAE $\downarrow$
                 & Mean realised utility $\uparrow$ & Episodes \\
    \midrule
    \textsc{Ffill}         & 77.47  & 4.08  & -0.139  & 760 \\
    \textsc{Single TS-ICL} & 29.61 & 2.03 & +0.013 & 760 \\
    \textsc{Multi TS-ICL}  & 29.59  & 1.85  & +0.029  & 758 \\
    \textsc{Context Ridge} & 30.39  & 1.48  & +0.043  & 566 \\
    \textsc{SAITS}         & 68.25  & 3.10  & +0.037  & 747 \\
    \midrule
    \multicolumn{5}{l}{\footnotesize Winner agreement 19.3\%, discordant rate
    44.5\%, mean within-episode Spearman $\rho$ 0.12} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 170

```latex
Reconstruction and forecasting utility favour different actions in these diagnostics.
The weak rank agreement motivates direct evaluation of forecasting utility when selecting
repairs. It does not establish that reconstruction quality is uninformative in every setting.
```

**中文直译**

这些诊断中，重建与预测效用偏好不同动作。较弱的排序一致性支持选择修复时直接评价预测效用，但不能说明重建质量在所有设置下都没有信息。

## 对照 171

```latex
\subsection{Where an Action's Utility Comes From}
```

**中文直译**

动作效用的来源

## 对照 172

```latex
Table~\ref{tab:app-utility-severity} reports the mean realised utility of each catalog action
on the replay bank, once over the whole bank and once within each registered severity. It
selects nothing and is computed after the configuration was frozen. Two things in it matter for
reading the main tables.
```

**中文直译**

表 \ref{tab:app-utility-severity} 报告回放库中各目录动作的平均已实现效用，分别在全库和各登记严重度内统计。它不选择参数，在配置冻结后计算。其中两点有助于理解主表。

## 对照 173

```latex
The recorded action utilities vary with both backbone and severity. Several repairs become
more useful as missingness increases on TimesFM, while the Chronos-2 values change less.
This variation motivates reporting each backbone separately and assessing severity sensitivity.
```

**中文直译**

已记录动作效用随骨干和严重度变化。TimesFM 上若干修复随缺失增加而更有用，Chronos-2 的变化较小。这支持分骨干报告并评价严重度敏感性。

## 对照 174

```latex
For Bolt, the recorded mean utility of \textsc{Context Ridge} is $+0.073$ across the bank
and $+0.036$ at $10\%$ missingness. These summaries use different severity mixtures.
Their difference alone does not identify an outlier or establish its causal contribution.
Raw outcomes must be retained when examining the effect of extreme repairs.
```

**中文直译**

Bolt 上 Context Ridge 的记录平均效用在全库为 +0.073，在 10% 缺失率为 +0.036。这些汇总采用不同严重度混合，其差异本身不能识别异常值或确立其因果贡献。检验极端修复的影响时必须保留原始结果。

## 对照 175

```latex
\caption{Mean realised utility of each action on the replay bank, overall and within each
registered severity. Positive means the action lowered the forecasting loss relative to
leaving the input unchanged. Utility is measured per episode, so it is not on the same
aggregation as the source-macro MASE of the main tables and the two are not directly
comparable in magnitude.}
```

**中文直译**

回放库中每个动作在总体及各登记严重度内的平均已实现效用。正值表示相对于保持输入不变降低预测损失。效用按样例测量，与主表数据源宏平均 MASE 的聚合方式不同，幅度不能直接比较。

### 共用数值表 19

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrrr@{}}
    \toprule
    Backbone & Action & All severities & $10\%$ & $30\%$ & $50\%$ \\
    \midrule
    \multirow{4}{*}{Bolt}
      & \textsc{Ffill}         & -0.167  & -0.130  & -0.162  & -0.209 \\
      & \textsc{Single TS-ICL} & +0.018 & +0.002 & +0.006 & +0.045 \\
      & \textsc{Multi TS-ICL}  & +0.035  & +0.013  & +0.036  & +0.057 \\
      & \textsc{Context Ridge} & +0.073  & +0.036  & +0.052  & +0.136 \\
    \midrule
    \multirow{4}{*}{TimesFM}
      & \textsc{Ffill}         & -0.022  & -0.013  & -0.025  & -0.029 \\
      & \textsc{Single TS-ICL} & +0.191 & +0.131 & +0.187 & +0.254 \\
      & \textsc{Multi TS-ICL}  & +0.205  & +0.145  & +0.210  & +0.261 \\
      & \textsc{Context Ridge} & +0.310  & +0.216  & +0.304  & +0.419 \\
    \midrule
    \multirow{4}{*}{Chronos-2}
      & \textsc{Ffill}         & -0.180  & -0.120  & -0.177  & -0.242 \\
      & \textsc{Single TS-ICL} & -0.002 & -0.007 & -0.001 & +0.002 \\
      & \textsc{Multi TS-ICL}  & +0.026  & +0.012  & +0.038  & +0.029 \\
      & \textsc{Context Ridge} & +0.096  & +0.068  & +0.095  & +0.128 \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 176

```latex
\subsection{Per-Source Results}
```

**中文直译**

分数据源结果

## 对照 177

```latex
Each table below reports one frozen backbone at $10\%$ severity, one horizon, and
all eight sources, with one row per method. MASE is reported in every cell so that a
reader can recompute the source-macro aggregate of Table~\ref{tab:main} directly from
these tables. The \emph{macro} column is the equal-weight average over the eight sources
for that horizon. Averaging both horizons gives the main-table quantity. Rows are generated from the recorded result
group using the same aggregation as the main table.
MAE and RMSE are reported per source and are not averaged across sources.
```

**中文直译**

下列各表报告一个冻结骨干在 10% 严重度、一个预测长度、全部八个源上的结果，每种方法一行。每格报告 MASE，可由这些表重建表 \ref{tab:main} 的数据源宏平均。macro 列是该预测长度内八个源的等权均值，再平均两个预测长度即可得到主表量。各行从已记录结果组生成，聚合口径与主表一致。MAE 和 RMSE 按源报告，不跨源平均。

## 对照 178

```latex
\caption{Per-source MASE on Bolt at $10\%$ severity, $H=96$. The macro column is the
equal-weight average over the eight sources for this horizon. The main table additionally averages both horizons. Lower is better everywhere.}
```

**中文直译**

Bolt 在 10% 严重度、H=96 下的分源 MASE。macro 列为该预测长度内八个源的等权均值，主表还平均两个预测长度。所有数值越低越好。

### 共用数值表 20

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}
    \toprule
    Method & ETTh1 & ETTh2 & ETTm1 & ETTm2 & Electricity & Exchange & Traffic & Weather & Macro $\downarrow$ \\
    \midrule
    Native KEEP & 0.967 & 1.444 & 1.370 & 1.035 & 0.957 & 2.761 & 0.980 & 0.645 & 1.270 \\
    Best Fixed & 0.877 & 1.293 & 1.321 & 1.015 & 0.951 & 2.784 & 0.955 & 0.651 & 1.231 \\
    R2-CART & 0.886 & 1.319 & 1.312 & 1.002 & 0.911 & 2.535 & 0.908 & 0.633 & 1.188 \\
    Fixed SAITS & 0.878 & 1.280 & 1.306 & 0.993 & 0.998 & 3.418 & 0.887 & 0.638 & 1.300 \\
    TATO & 1.421 & 1.364 & 1.713 & 1.120 & 0.892 & 2.385 & 1.485 & 0.672 & 1.382 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 0.881 & 1.283 & 1.318 & 1.009 & 0.921 & 2.404 & 0.917 & 0.653 & 1.173 \\
    \midrule
    Catalog Oracle & \oracle{0.830} & \oracle{1.170} & \oracle{1.196} & \oracle{0.926} & \oracle{0.712} & \oracle{2.288} & \oracle{0.836} & \oracle{0.454} & \oracle{1.052} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 179

```latex
\caption{Per-source MASE on Bolt at $10\%$ severity, $H=192$. The macro column is the
equal-weight average over the eight sources for this horizon. The main table additionally averages both horizons. Lower is better everywhere.}
```

**中文直译**

Bolt 在 10% 严重度、H=192 下的分源 MASE。macro 列为该预测长度内八个源的等权均值，主表还平均两个预测长度。所有数值越低越好。

### 共用数值表 21

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}
    \toprule
    Method & ETTh1 & ETTh2 & ETTm1 & ETTm2 & Electricity & Exchange & Traffic & Weather & Macro $\downarrow$ \\
    \midrule
    Native KEEP & 1.082 & 1.447 & 1.415 & 1.239 & 0.870 & 5.071 & 1.018 & 1.162 & 1.663 \\
    Best Fixed & 1.031 & 1.348 & 1.385 & 1.217 & 0.878 & 5.019 & 0.997 & 1.125 & 1.625 \\
    R2-CART & 1.037 & 1.352 & 1.389 & 1.215 & 0.895 & 4.910 & 0.986 & 1.145 & 1.616 \\
    Fixed SAITS & 1.025 & 1.333 & 1.384 & 1.187 & 0.968 & 5.165 & 0.971 & 1.075 & 1.638 \\
    TATO & 1.510 & 1.528 & 1.682 & 1.310 & 0.898 & 5.074 & 1.590 & 1.278 & 1.859 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.031 & 1.341 & 1.378 & 1.208 & 0.906 & 4.690 & 0.983 & 1.131 & 1.583 \\
    \midrule
    Catalog Oracle & \oracle{0.994} & \oracle{1.248} & \oracle{1.286} & \oracle{1.130} & \oracle{0.685} & \oracle{4.191} & \oracle{0.920} & \oracle{0.882} & \oracle{1.417} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 180

```latex
\caption{Per-source MASE on TimesFM at $10\%$ severity, $H=96$. The macro column is the
equal-weight average over the eight sources for this horizon. The main table additionally averages both horizons. Lower is better everywhere.}
```

**中文直译**

TimesFM 在 10% 严重度、H=96 下的分源 MASE。macro 列为该预测长度内八个源的等权均值，主表还平均两个预测长度。所有数值越低越好。

### 共用数值表 22

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}
    \toprule
    Method & ETTh1 & ETTh2 & ETTm1 & ETTm2 & Electricity & Exchange & Traffic & Weather & Macro $\downarrow$ \\
    \midrule
    Native KEEP & 1.235 & 1.363 & 1.568 & 1.155 & 0.963 & 3.330 & 1.199 & 0.628 & 1.430 \\
    Best Fixed & 0.979 & 1.229 & 1.133 & 1.017 & 0.831 & 3.607 & 0.908 & 0.661 & 1.296 \\
    R2-CART & 0.998 & 1.264 & 1.149 & 1.002 & 0.885 & 3.579 & 0.901 & 0.621 & 1.300 \\
    Fixed SAITS & 0.970 & 1.244 & 1.117 & 0.992 & 0.870 & 2.996 & 0.906 & 0.629 & 1.216 \\
    TATO & 1.359 & 1.226 & 1.692 & 1.175 & 1.102 & 2.740 & 1.249 & 0.710 & 1.407 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.012 & 1.218 & 1.142 & 1.008 & 0.934 & 3.187 & 0.908 & 0.630 & 1.255 \\
    \midrule
    Catalog Oracle & \oracle{0.896} & \oracle{1.144} & \oracle{1.041} & \oracle{0.944} & \oracle{0.633} & \oracle{2.568} & \oracle{0.860} & \oracle{0.463} & \oracle{1.069} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 181

```latex
\caption{Per-source MASE on TimesFM at $10\%$ severity, $H=192$. The macro column is the
equal-weight average over the eight sources for this horizon. The main table additionally averages both horizons. Lower is better everywhere.}
```

**中文直译**

TimesFM 在 10% 严重度、H=192 下的分源 MASE。macro 列为该预测长度内八个源的等权均值，主表还平均两个预测长度。所有数值越低越好。

### 共用数值表 23

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}
    \toprule
    Method & ETTh1 & ETTh2 & ETTm1 & ETTm2 & Electricity & Exchange & Traffic & Weather & Macro $\downarrow$ \\
    \midrule
    Native KEEP & 1.232 & 1.391 & 1.688 & 1.332 & 1.021 & 6.475 & 1.197 & 1.135 & 1.934 \\
    Best Fixed & 1.110 & 1.304 & 1.294 & 1.217 & 0.905 & 6.914 & 0.996 & 1.152 & 1.862 \\
    R2-CART & 1.106 & 1.334 & 1.299 & 1.206 & 0.898 & 7.044 & 1.007 & 1.123 & 1.877 \\
    Fixed SAITS & 1.098 & 1.327 & 1.285 & 1.193 & 0.926 & 5.769 & 0.990 & 1.133 & 1.715 \\
    TATO & 1.367 & 1.303 & 1.784 & 1.342 & 1.228 & 5.063 & 1.273 & 1.208 & 1.821 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.132 & 1.268 & 1.295 & 1.214 & 0.976 & 6.803 & 0.995 & 1.137 & 1.853 \\
    \midrule
    Catalog Oracle & \oracle{1.040} & \oracle{1.198} & \oracle{1.229} & \oracle{1.122} & \oracle{0.761} & \oracle{5.304} & \oracle{0.960} & \oracle{0.883} & \oracle{1.562} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 182

```latex
\caption{Per-source MASE on Chronos-2 at $10\%$ severity, $H=96$. The macro column is the
equal-weight average over the eight sources for this horizon. The main table additionally averages both horizons. Lower is better everywhere.}
```

**中文直译**

Chronos-2 在 10% 严重度、H=96 下的分源 MASE。macro 列为该预测长度内八个源的等权均值，主表还平均两个预测长度。所有数值越低越好。

### 共用数值表 24

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}
    \toprule
    Method & ETTh1 & ETTh2 & ETTm1 & ETTm2 & Electricity & Exchange & Traffic & Weather & Macro $\downarrow$ \\
    \midrule
    Native KEEP & 1.083 & 1.238 & 1.288 & 1.016 & 0.768 & 3.272 & 0.857 & 0.668 & 1.274 \\
    Best Fixed & 1.020 & 1.120 & 1.192 & 1.007 & 0.795 & 2.781 & 0.836 & 0.651 & 1.175 \\
    R2-CART & 1.016 & 1.114 & 1.195 & 1.003 & 0.773 & 2.380 & 0.836 & 0.637 & 1.119 \\
    Fixed SAITS & 1.021 & 1.134 & 1.191 & 0.977 & 0.852 & 2.722 & 0.825 & 0.634 & 1.170 \\
    TATO & 1.438 & 1.649 & 1.617 & 1.183 & 1.028 & 2.641 & 1.284 & 0.650 & 1.436 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.019 & 1.210 & 1.221 & 0.985 & 0.833 & 2.152 & 0.822 & 0.643 & 1.111 \\
    \midrule
    Catalog Oracle & \oracle{0.936} & \oracle{1.017} & \oracle{1.082} & \oracle{0.921} & \oracle{0.590} & \oracle{1.992} & \oracle{0.790} & \oracle{0.461} & \oracle{0.974} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 183

```latex
\caption{Per-source MASE on Chronos-2 at $10\%$ severity, $H=192$. The macro column is the
equal-weight average over the eight sources for this horizon. The main table additionally averages both horizons. Lower is better everywhere.}
```

**中文直译**

Chronos-2 在 10% 严重度、H=192 下的分源 MASE。macro 列为该预测长度内八个源的等权均值，主表还平均两个预测长度。所有数值越低越好。

### 共用数值表 25

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}
    \toprule
    Method & ETTh1 & ETTh2 & ETTm1 & ETTm2 & Electricity & Exchange & Traffic & Weather & Macro $\downarrow$ \\
    \midrule
    Native KEEP & 1.175 & 1.298 & 1.362 & 1.221 & 0.842 & 6.940 & 0.966 & 1.275 & 1.885 \\
    Best Fixed & 1.133 & 1.323 & 1.299 & 1.233 & 0.857 & 5.862 & 0.956 & 1.238 & 1.738 \\
    R2-CART & 1.131 & 1.345 & 1.298 & 1.229 & 0.857 & 5.195 & 0.944 & 1.200 & 1.650 \\
    Fixed SAITS & 1.116 & 1.286 & 1.305 & 1.200 & 0.936 & 5.748 & 0.949 & 1.161 & 1.713 \\
    TATO & 1.457 & 1.908 & 1.656 & 1.349 & 1.086 & 4.493 & 1.253 & 1.138 & 1.792 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.150 & 1.312 & 1.309 & 1.189 & 0.887 & 5.132 & 0.954 & 1.230 & 1.645 \\
    \midrule
    Catalog Oracle & \oracle{1.048} & \oracle{1.152} & \oracle{1.210} & \oracle{1.107} & \oracle{0.699} & \oracle{4.744} & \oracle{0.915} & \oracle{0.948} & \oracle{1.478} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 184

```latex
\subsection{Per-Pattern Results}
```

**中文直译**

分模式结果

## 对照 185

```latex
Table~\ref{tab:app-pattern-res} separates the four patterns. Point missing is expected to
be the easiest regime and tail missing the hardest, because the missing block is adjacent
to the forecast origin and therefore removes exactly the observations a forecaster would
rely on most. Any claim about a pattern is a claim about this table, not about the pooled
main table.
```

**中文直译**

表 \ref{tab:app-pattern-res} 分开报告四种模式。预期点缺失最容易、尾部缺失最难，因为缺失块紧邻预测起点，移除了预测器最依赖的观测。关于某种模式的主张应依据此表，而非混合的主表。

## 对照 186

```latex
\caption{Per-pattern MASE at $10\%$ severity, source-macro averaged over the three
backbones and both horizons. The last column ranks the deployable methods per request
within each pattern and macro-averages those ranks over the four patterns. Because every
pattern holds the same number of requests, this equals the per-request average rank for this roster. The main table reports MASE, not rank.}
```

**中文直译**

10% 严重度的分模式 MASE，在三个骨干和两个预测长度上按数据源宏平均。最后一列在每个模式内逐请求排列可部署方法，再对四种模式的排名宏平均。由于各模式请求数相同，它等于此方法清单的逐请求平均排名。主表报告 MASE，不报告排名。

### 共用数值表 26

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrr@{}}
    \toprule
    Method & P1 Point & P2 Target Block & P3 Shared Block & P4 Tail & Avg.\ Rank $\downarrow$ \\
    \midrule
    \textsc{Native Keep} & 1.436 & 1.379 & 1.400 & 2.088 & 3.36 \\
    \textsc{Best Fixed}  & 1.412   & 1.393   & 1.400   & 1.746   & 2.94 \\
    R2-CART              & 1.409   & 1.439   & 1.425   & 1.561   & 2.97 \\
    Fixed SAITS & 1.318 & 1.425 & 1.549 & 1.543 & 2.98 \\
    TATO & 1.336 & 1.371 & 1.317 & 2.441 & 4.10 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.376 & 1.381 & 1.386 & 1.604 & 2.79 \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 187

```latex
\subsection{Source-Level Fixed Policy and Leave-One-Source-Out}
```

**中文直译**

数据源级固定策略与留一数据源分析

## 对照 188

```latex
This subsection supports the source-attribution question of \S\ref{sec:exp-main}. The
checks were run on the retained prediction cache with selection confined to the TRAIN
side, and all TEST numbers remain post-hoc comparisons on the previously examined block.
Intervals are the recorded 2,000-resample paired parent-bootstrap intervals (seed 101),
nominal and without multiple-comparison adjustment.
```

**中文直译**

本节支持第 \ref{sec:exp-main} 节的数据源归因问题。检查使用保留的预测缓存，选择限定于 TRAIN 侧，所有 TEST 数值仍是对早已检查过的数据块的事后比较。区间是记录的 2,000 次配对父窗口自助法区间，种子 101，为名义区间，未作多重比较校正。

## 对照 189

```latex
The source-level fixed policy applies, per source, the single catalog action with the
highest mean realised utility on the replay bank, with \textsc{Keep} as the registered
fallback where that action is unsupported (fallback counts are recorded with the result. The largest is 48 of 190 requests on ETTm1 and ETTm2, whose chosen action is Context
Ridge). The chosen action varies by source and backbone. Context Ridge dominates (16 of
the 24 source-backbone pairs), with Multi TS-ICL, Single TS-ICL, FFILL and SAITS each
selected somewhere. So the policy tests whether
source identity alone carries the gain.
```

**中文直译**

数据源级固定策略对每个源使用回放库平均已实现效用最高的单一目录动作。不支持该动作时按登记规则回退到 KEEP，回退次数与结果一起记录。最大值为 ETTm1 和 ETTm2 的 190 个请求中 48 次，其选定动作是 Context Ridge。选定动作随源和骨干变化，Context Ridge 最多，占 24 个源与骨干组合的 16 个，Multi TS-ICL、Single TS-ICL、FFILL 和 SAITS 也各有被选情形。因此，该策略检验仅凭数据源身份是否足以取得收益。

## 对照 190

```latex
\caption{Source-level fixed policy on TEST against the full rule. The difference is FULL
minus the source-level fixed policy, so a positive value favours the fixed policy.}
```

**中文直译**

TEST 上数据源级固定策略与完整规则比较。差值为 FULL 减数据源级固定策略，正值有利于固定策略。

### 共用数值表 27

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrl@{}}
\toprule
Backbone & FULL MASE & Source-fixed MASE & Intervention rate & FULL$-$fixed [interval] \\
\midrule
Bolt & 1.3826 & 1.3602 & 82.6\% & $+0.0223$ [$+0.0044$, $+0.0432$] \\
TimesFM & 1.5284 & 1.5268 & 80.3\% & $+0.0017$ [$-0.0074$, $+0.0119$] \\
Chronos-2 & 1.3650 & 1.4484 & 83.4\% & $-0.0834$ [$-0.1861$, $+0.0205$] \\
\bottomrule
\end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 191

```latex
\caption{Leave-one-source-out on TEST: the FULL-minus-control difference in source-macro
MASE with each source removed in turn. Only the full set and the Exchange-excluded subset
are printed. The other leave-one-source-out values are stored in
\texttt{results/v55/source\_diagnostics.json}. A negative value favours FULL.}
```

**中文直译**

TEST 上留一数据源分析，依次移除各源后，报告数据源宏平均 MASE 的 FULL 减对照差值。只打印全体和排除 Exchange 的子集，其余值保存在 results/v55/source_diagnostics.json。负值有利于 FULL。

### 共用数值表 28

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrrrr@{}}
\toprule
Backbone & Subset & vs KEEP & vs Best Fixed & vs Source Fixed & vs R2-CART & vs TATO \\
\midrule
Bolt & all eight & $-0.0839$ & $-0.0454$ & $+0.0223$ & $-0.0230$ & $-0.2375$ \\
Bolt & without Exchange & $-0.0232$ & $+0.0187$ & $+0.0269$ & $+0.0215$ & $-0.2255$ \\
TimesFM & all eight & $-0.1536$ & $-0.0502$ & $+0.0017$ & $-0.0659$ & $-0.0855$ \\
TimesFM & without Exchange & $-0.1679$ & $+0.0015$ & $+0.0019$ & $-0.0093$ & $-0.2330$ \\
Chronos-2 & all eight & $-0.2144$ & $-0.0915$ & $-0.0834$ & $-0.0123$ & $-0.2494$ \\
Chronos-2 & without Exchange & $-0.0207$ & $+0.0077$ & $+0.0169$ & $+0.0108$ & $-0.2806$ \\
\bottomrule
\end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 192

```latex
The margin over the unchanged input keeps its sign on all eight subsets of every backbone,
although on Chronos-2 it too is concentrated in Exchange. The margins over Best Fixed
reverse without Exchange on all three backbones. Together with
Table~\ref{tab:v53-source-fixed}, this bounds the claim the evaluation supports: selective
repair improves on leaving the input unchanged across sources, but its advantage over the
stronger simple controls is carried substantially by one source. Source Fixed is significantly
better on Bolt, while the paired intervals include zero on the other two backbones.
```

**中文直译**

相对于保持输入不变的差值，在各骨干的全部八个子集中保留方向，不过 Chronos-2 的收益同样集中于 Exchange。去除 Exchange 后，三个骨干相对于 Best Fixed 的差值都反转。结合表 \ref{tab:v53-source-fixed}，证据范围是选择性修复在不同源子集上优于保持输入不变，但相对于更强简单对照的优势很大程度由一个源贡献。Source Fixed 在 Bolt 上显著更好，另外两个骨干的配对区间含零。

## 对照 193

```latex
\section{Intervention Frequency and Harm}
```

**中文直译**

干预频率与伤害

## 对照 194

```latex
This section supports \S\ref{sec:exp-harm}. It collects the default operating point, the
action-opportunity strata, and the complete tables of every frequency comparison.
```

**中文直译**

本节支持第 \ref{sec:exp-harm} 节，汇集默认工作点、动作机会分层以及频率比较的完整表格。

## 对照 195

```latex
\subsection{Historical Governance Diagnostics}
```

**中文直译**

历史治理诊断

## 对照 196

```latex
Tables~\ref{tab:app-operating} and \ref{tab:app-scorebins} retain diagnostics from the earlier selector, not the current v55 configuration. The first reports operating points across the penalty grid and
Table~\ref{tab:app-scorebins} checks that the order the score induces agrees with the sign of
the realised utility. The score is used only to order actions, and its magnitude is not claimed
to be calibrated against the utility scale. Over 10773 admissible pairs the sign of the score and the sign of the realised utility agree on 54\% of them, and the mean realised utility is +0.197 where the score is positive against -0.031 where it is negative, so the score shows limited directional agreement and is not a calibrated utility estimate.
```

**中文直译**

表 \ref{tab:app-operating} 和 \ref{tab:app-scorebins} 保留早期选择器的诊断，不是当前 v55 配置。第一张表报告惩罚网格上的工作点，第二张表检查得分顺序是否与已实现效用符号一致。得分用于排列动作，不主张其数值已对效用尺度校准。10,773 个可用配对中，得分与效用符号在 54% 上一致。正得分处平均效用为 +0.197，负得分处为 −0.031。因此得分只有有限方向一致性，不是校准后的效用估计。

## 对照 197

```latex
\caption{Historical operating points over the penalty grid, with the neighbourhood size frozen at the
selected value on each backbone. Intervention rate is the share of requests on which a
non-reference action ran, and conditional HIR is the share of those that raised the loss.
Raising the penalty moves the rate and leaves the conditional rate close to where it was, so
the largest change is in intervention frequency.}
```

**中文直译**

历史惩罚网格上的工作点，各骨干邻域大小固定为选定值。干预率是执行非参考动作的请求比例，条件 HIR 是其中增加损失的比例。提高惩罚改变干预率，而条件伤害率变化较小，因此最大变化发生在干预频率。

### 共用数值表 29

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrr@{}}
    \toprule
     & \multicolumn{2}{c}{Bolt} & \multicolumn{2}{c}{TimesFM} & \multicolumn{2}{c}{Chronos-2} \\
    \cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}
    Penalty strength & Int.\ rate & Cond.\ HIR & Int.\ rate & Cond.\ HIR & Int.\ rate & Cond.\ HIR \\
    \midrule
    $\beta = 0$ & 87.2\% & 42.2\% & 92.2\% & 42.7\% & 78.9\% & 40.2\% \\
    $\beta = 0.5$ & 74.6\% & 42.2\% & 84.7\% & 40.7\% & 69.1\% & 39.6\% \\
    $\beta = 1$ & 64.6\% & 43.0\% & 69.3\% & 41.4\% & 54.6\% & 37.3\% \\
    $\beta = 1.64$ & 48.2\% & 42.9\% & 52.4\% & 38.7\% & 36.6\% & 41.0\% \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 198

```latex
\caption{Historical realised utility against the quantile bin of the conservative score, pooled over the
three backbones and every admissible action. The score orders actions and its magnitude is
not claimed to be calibrated, so what this table checks is whether the order it induces
agrees with the sign of the utility. Intervals resample parents.}
```

**中文直译**

历史保守得分分位箱与已实现效用，汇总三个骨干的每个可用动作。得分排列动作，不主张其幅度已校准，因此该表检查得分排序是否与效用符号一致。区间按父窗口重采样。

### 共用数值表 30

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrr@{}}
    \toprule
    Score bin & Pairs & Mean realised utility & 95\% interval \\
    \midrule
    1 (lowest score) & 2,157 & -0.105 & [-0.250, +0.047] \\
    2 & 2,154 & +0.007 & [-0.009, +0.032] \\
    3 & 2,154 & +0.008 & [-0.033, +0.035] \\
    4 & 2,154 & +0.017 & [-0.007, +0.052] \\
    5 (highest score) & 2,154 & +0.304 & [+0.058, +0.788] \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 199

```latex
\subsection{Action-Opportunity Strata}
```

**中文直译**

动作机会分层

## 对照 200

```latex
This subsection supports \S\ref{sec:exp-exists}. For an evaluation episode $i$ the oracle
opportunity is the improvement the best admissible action could have produced over the
reference input,
```

**中文直译**

本节支持第 \ref{sec:exp-exists} 节。评价样例 i 的 oracle 机会，是最佳可用动作相对于参考输入本可产生的改善量，定义如下。

**共用公式**

```latex
\begin{equation}
  \Delta_i \;=\; \loss\!\left(F(T_{a_0}(X_i, M_i)),\, y_i\right) - \min_{a \in \calA} \loss\!\left(F(T_{a}(X_i, M_i)),\, y_i\right),
  \label{eq:opportunity}
\end{equation}
```

## 对照 201

```latex
which uses the realised target and is therefore a retrospective diagnostic. Episodes are partitioned into a \emph{no-op} stratum, where the reference input is
already best up to a tolerance, a \emph{low-opportunity} stratum, and a
\emph{high-opportunity} stratum. The two boundaries are fitted on the replay bank and applied
unchanged to TEST, so no evaluation episode participates in choosing them.
Table~\ref{tab:app-opp-sizes} records the realised stratum sizes,
Table~\ref{tab:app-opportunity} reports source-macro MASE within each stratum under the
identical partition for every method, and Table~\ref{tab:app-opp-sens} repeats the
historical stratum-level MASE under alternative boundaries. These two tables retain the earlier selector results and do not evaluate the current v55 rule.
```

**中文直译**

该量使用已实现目标，因此是回顾性诊断。样例划分为不操作、低机会和高机会层，不操作层指在容忍度范围内参考输入已最佳。两个边界在回放库上拟合，原样应用于 TEST，没有评价样例参与选择。表 \ref{tab:app-opp-sizes} 记录实际层规模。表 \ref{tab:app-opportunity} 在所有方法共同分层下报告层内数据源宏平均 MASE，表 \ref{tab:app-opp-sens} 用其他边界重复历史层内 MASE。后两表保留早期选择器结果，不评价当前 v55 规则。

## 对照 202

```latex
\caption{Action-opportunity strata on TEST. Boundaries are the bank thresholds, applied
unchanged. Counts are of parents and not of mask variants.}
```

**中文直译**

TEST 上的动作机会分层。边界采用回放库阈值，原样应用。计数按父窗口，不按掩码变体。

### 共用数值表 31

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrr@{}}
    \toprule
    Stratum & Parents & Share of episodes & Median $\Delta_i$ & 90th pct.\ $\Delta_i$ \\
    \midrule
    No-op             & 68  & 19.3\%  & 0.000  & 0.000 \\
    Low opportunity   & 91   & 47.1\%   & 0.038   & 0.100 \\
    High opportunity  & 79  & 33.5\%  & 0.352  & 1.293 \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 203

```latex
\caption{Historical stratum-level MASE under the identical partition, retained from the earlier selector. The FULL aggregate here is not the current main result. The no-op stratum is where an
intervention can only lose, so a method that is better only in the high-opportunity stratum
while degrading the no-op stratum has not solved the selection problem. Lower is better.}
```

**中文直译**

保留的早期选择器在相同分层下的历史 MASE，此处 FULL 总体值不是当前主结果。在不操作层中，干预只会带来损失，因此若方法仅在高机会层更好，却使不操作层退化，就未解决选择问题。数值越低越好。

### 共用数值表 32

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrr@{}}
    \toprule
    Method & No-op MASE $\downarrow$ & Low opportunity $\downarrow$ & High opportunity $\downarrow$ & Overall $\downarrow$ \\
    \midrule
    Native KEEP        & 1.287    & 1.166    & 2.039    & 1.576 \\
    Best Fixed         & 1.401      & 1.181      & 1.689      & 1.488 \\
    R2-CART            & 1.490      & 1.197      & 1.588      & 1.458 \\
    Fixed SAITS           & 1.565      & 1.225      & 1.554      & 1.459 \\
    TATO               & 1.444    & 1.245    & 2.177    & 1.616 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.389 & 1.170 & 1.652 & 1.437 \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 204

```latex
\caption{Historical stratum-boundary sensitivity for the same earlier selector. The no-op tolerance and the low and high boundary are
shifted by the indicated factor of the bank threshold, and every other setting is unchanged.
MASE is source-macro averaged within the resulting strata.}
```

**中文直译**

同一早期选择器的历史分层边界敏感性。不操作容忍度及低高机会边界按所示回放库阈值倍数移动，其余设置不变。MASE 在所得层内按数据源宏平均。

### 共用数值表 33

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrr@{}}
    \toprule
    Boundary factor & No-op MASE $\downarrow$ & Low MASE $\downarrow$ & High MASE $\downarrow$ & Overall MASE $\downarrow$ \\
    \midrule
    $\times 0.5$ & 1.389  & 1.056  & 1.513  & 1.437 \\
    $\times 1.0$ & 1.389   & 1.170   & 1.652   & 1.437 \\
    $\times 2.0$ & 1.389   & 1.433   & 2.707   & 1.437 \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 205

```latex
\subsection{Gate Controls}
```

**中文直译**

门控对照

## 对照 206

```latex
Table~\ref{tab:v52-gates} compares the frozen gate against post-hoc controls on TEST.
These controls were run after reviewing the earlier TEST results. They use the retained
prediction cache and the frozen full-method settings, and they do not constitute an
independent confirmation set. All intervals in this subsection are the recorded
2,000-resample paired parent-bootstrap intervals (seed 101) and are nominal, without
multiple-comparison adjustment.
```

**中文直译**

表 \ref{tab:v52-gates} 在 TEST 上比较冻结门控与事后对照。这些对照在查看早期 TEST 结果后运行，使用保留的预测缓存和完整方法冻结设置，不构成独立确认集。本节所有区间均为记录的 2,000 次配对父窗口自助法区间，种子 101，为名义区间，未作多重比较校正。

## 对照 207

```latex
\caption{Gate controls on TEST. Thresholds and random acceptance probabilities were
calibrated on the development block. HIR is conditional on an intervention.}
```

**中文直译**

TEST 上的门控对照。阈值和随机接受概率在开发块校准。HIR 以已发生干预为条件。

### 共用数值表 34

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrrr@{}}
\toprule
Backbone & Rule & MASE & Intervention (\%) & HIR (\%) & Harmful loss \\
\midrule
Bolt & FULL & 1.3826 & 36.45 & 40.43 & 0.03568 \\
Bolt & Mean only & 1.3844 & 36.97 & 43.06 & 0.04167 \\
Bolt & Linear & 1.4244 & 30.00 & 43.86 & 0.02493 \\
Bolt & Random & 1.4360 & 31.58 & 42.92 & 0.01826 \\
TimesFM & FULL & 1.5284 & 92.89 & 40.93 & 0.03935 \\
TimesFM & Mean only & 1.5136 & 93.55 & 42.48 & 0.05415 \\
TimesFM & Linear & 1.4642 & 92.63 & 42.76 & 0.06711 \\
TimesFM & Random & 1.5426 & 95.00 & 41.41 & 0.03937 \\
Chronos-2 & FULL & 1.3650 & 36.18 & 38.91 & 0.02700 \\
Chronos-2 & Mean only & 1.3845 & 37.37 & 38.73 & 0.03750 \\
Chronos-2 & Linear & 1.3883 & 35.79 & 44.12 & 0.02188 \\
Chronos-2 & Random & 1.4776 & 40.66 & 41.10 & 0.01991 \\
\bottomrule
\end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 208

```latex
The random control uses a single recorded seed, 101. Its intervals resample parents and
do not include variability over random-gate seeds. The mean-only and linear controls change
both recommendations and acceptance scores, so their comparisons do not isolate the penalty
alone. All three frozen configurations use $\beta=1.64$. The mean-only control sets it to
zero and matches a threshold on TRAIN. No TEST outcome is used to rematch realised intervention
frequencies.
```

**中文直译**

随机对照仅使用记录的种子 101。其区间按父窗口重采样，不包含随机门控种子间的变异。仅均值和线性对照同时改变推荐动作与接受得分，因此未单独分离惩罚的作用。三个冻结配置均采用 β=1.64。仅均值对照将其设为零，并在 TRAIN 上匹配阈值。不使用 TEST 结果重新匹配实际干预频率。

## 对照 209

```latex
\section{Estimation and State Analyses}
```

**中文直译**

估计与状态分析

## 对照 210

```latex
This section supports \S\ref{sec:exp-ablation} and separates the fixed-configuration
ablations from the representation comparisons that re-run selection.
```

**中文直译**

本节支持第 \ref{sec:exp-ablation} 节，区分固定配置消融与重新选择参数的表示比较。

## 对照 211

```latex
\subsection{Ablation Details}
```

**中文直译**

消融细节

## 对照 212

```latex
This section supports \S\ref{sec:exp-ablation}. Every variant reads the same catalog
prediction cache, so the rows differ only in how the stored utilities are summarised and
thresholded. Table~\ref{tab:app-ablation} reports the full outcome vector behind the compact
Table~\ref{tab:ablation}. The variant definitions follow \S\ref{sec:exp-ablation} exactly.
```

**中文直译**

本节支持第 \ref{sec:exp-ablation} 节。各变体读取同一目录预测缓存，仅在如何汇总存储效用及应用阈值上不同。表 \ref{tab:app-ablation} 报告简表 \ref{tab:ablation} 背后的完整结果向量。变体定义严格遵循第 \ref{sec:exp-ablation} 节。

## 对照 213

```latex
\caption{Ablation, full outcome vector in the two scaled metrics. Raw errors are not
averaged across sources anywhere in this paper, so they are not shown here either. Calls
counts forecasting-backbone calls per request and harmful loss is relative to
\textsc{Keep}.}
```

**中文直译**

消融在两个缩放指标上的完整结果向量。本文从不跨源平均原始误差，此处也不展示该均值。Calls 是每个请求的预测骨干调用数，伤害损失相对于 KEEP 计算。

### 共用数值表 35

```latex
\begin{tabularx}{\textwidth}{@{}Xrrrrrr@{}}
    \toprule
    Variant & MASE $\downarrow$ & RMSSE $\downarrow$ & \shortstack[r]{Repair\\rate} & \shortstack[r]{Conditional\\HIR $\downarrow$} & \shortstack[r]{Harmful\\loss $\downarrow$} & Calls $\downarrow$ \\
    \midrule
    Full \introact{} & 1.425 & 1.221 & 55.2\% & 40.1\% & 0.0340 & 1.55 \\
    Neighbourhood only ($\lambda=0$) & 1.429 & 1.224 & 41.8\% & 39.8\% & 0.0347 & 1.42 \\
    Source mean only ($\lambda=\infty$) & 1.437 & 1.231 & 97.9\% & 41.5\% & 0.0485 & 1.98 \\
    No retrieval & 1.475 & 1.256 & 100.0\% & 43.9\% & 0.0697 & 2.00 \\
    Linear utility model & 1.448 & 1.242 & 87.4\% & 44.2\% & 0.0652 & 1.87 \\
    No action conditioning & 1.509 & 1.282 & 68.3\% & 44.8\% & 0.0394 & 1.68 \\
    No execution gate & 1.414 & 1.212 & 100.0\% & 42.9\% & 0.0515 & 2.00 \\
    Without intervention state & 1.426 & 1.223 & 55.1\% & 39.6\% & 0.0286 & 1.55 \\
    Without reference forecast state & 1.425 & 1.221 & 56.9\% & 40.4\% & 0.0348 & 1.57 \\
    \midrule
    \bottomrule
  \end{tabularx}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 214

```latex
\subsection{Mechanism and Feature Controls}
```

**中文直译**

机制与特征对照

## 对照 215

```latex
These controls were run after reviewing the earlier TEST results. They use the retained
prediction cache and the frozen full-method settings, and they do not constitute an
independent confirmation set. All intervals in this subsection are the recorded
2,000-resample paired parent-bootstrap intervals and are nominal, without
multiple-comparison adjustment.
```

**中文直译**

这些对照在查看早期 TEST 结果后运行，使用保留预测缓存和完整方法的冻结设置，不构成独立确认集。本节区间均为记录的 2,000 次配对父窗口自助法名义区间，未作多重比较校正。

## 对照 216

```latex
Table~\ref{tab:v52-a2} reports the per-backbone outcome and paired difference for six
variants. Differences are FULL minus the named variant, so negative values favour FULL.
Two rows vary the pooling endpoint, one removes retrieval, one removes each of two feature
groups, and one removes the execution gate.
```

**中文直译**

表 \ref{tab:v52-a2} 报告六个变体的分骨干结果及配对差值。差值为 FULL 减该变体，负值有利于 FULL。两行改变汇聚端点，一行取消检索，两行分别去掉两个特征组，一行取消执行门控。

## 对照 217

```latex
\caption{Per-backbone ablation outcomes at $10\%$ severity. Differences are FULL minus the
named variant. Negative values favour FULL.}
```

**中文直译**

10% 严重度的分骨干消融结果。差值为 FULL 减指定变体，负值有利于 FULL。

### 共用数值表 36

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrl@{}}
\toprule
Backbone & Variant & MASE & Difference & Nominal 95\% interval \\
\midrule
Bolt & Local only & 1.3826 & $0$ & identical by construction \\
Bolt & Source mean only & 1.3570 & $+0.0256$ & $[+0.0063,+0.0476]$ \\
Bolt & No retrieval & 1.4493 & $-0.0668$ & $[-0.1284,-0.0048]$ \\
Bolt & No intervention state & 1.3778 & $+0.0048$ & $[-0.0091,+0.0230]$ \\
Bolt & No forecast state & 1.3843 & $-0.0017$ & $[-0.0081,+0.0046]$ \\
Bolt & No execution gate & 1.3710 & $+0.0116$ & $[-0.0007,+0.0235]$ \\
TimesFM & Local only & 1.5409 & $-0.0125$ & $[-0.0386,+0.0135]$ \\
TimesFM & Source mean only & 1.5292 & $-0.0007$ & $[-0.0059,+0.0044]$ \\
TimesFM & No retrieval & 1.5953 & $-0.0668$ & $[-0.1315,-0.0028]$ \\
TimesFM & No intervention state & 1.5280 & $+0.0004$ & $[-0.0082,+0.0069]$ \\
TimesFM & No forecast state & 1.5262 & $+0.0022$ & $[+0.0004,+0.0043]$ \\
TimesFM & No execution gate & 1.5290 & $-0.0006$ & $[-0.0017,+0.0005]$ \\
Chronos-2 & Local only & 1.3650 & $0$ & identical by construction \\
Chronos-2 & Source mean only & 1.4261 & $-0.0611$ & $[-0.1471,+0.0259]$ \\
Chronos-2 & No retrieval & 1.3805 & $-0.0155$ & $[-0.0493,+0.0181]$ \\
Chronos-2 & No intervention state & 1.3706 & $-0.0056$ & $[-0.0260,+0.0153]$ \\
Chronos-2 & No forecast state & 1.3637 & $+0.0013$ & $[-0.0119,+0.0152]$ \\
Chronos-2 & No execution gate & 1.3429 & $+0.0221$ & $[+0.0051,+0.0394]$ \\
\bottomrule
\end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 218

```latex
The two feature-group removals are close to FULL on most backbones. On TimesFM, omitting the
reference-forecast features is slightly more accurate, with a narrow paired interval that
excludes zero. Thus the data do not show that every state feature contributes. Two additional
mask realisations give FULL aggregates of 1.4089 and 1.4271 against 1.4253 on the primary
mask, with \textsc{Keep} at 1.5700 and 1.5770 against 1.5759. These reuse the same sources
and parent sets and are sensitivity checks rather than independent samples.
```

**中文直译**

两个特征组移除实验在多数骨干上接近 FULL。在 TimesFM 上，去掉参考预测特征略提高精度，其较窄配对区间不含零。因此数据未表明每个状态特征都有贡献。另两种掩码实现的 FULL 总体值为 1.4089 和 1.4271，主掩码为 1.4253，KEEP 对应 1.5700、1.5770 和 1.5759。它们复用相同数据源和父窗口集，是敏感性检查，不是独立样本。

## 对照 219

```latex
\subsection{The Reduced State Given Its Own Selection}
```

**中文直译**

为精简状态单独选择参数

## 对照 220

```latex
The feature-group controls reuse the full selector's frozen hyperparameters. Retuning a
reduced state would be a different model-selection exercise and has not been run under the
present protocol. Earlier reduced-state tests belong to the historical development record
and are not pooled with the ablation table above.
```

**中文直译**

特征组对照复用完整选择器冻结的超参数。重新调节精简状态属于另一项模型选择实验，当前协议下尚未运行。早期精简状态测试属于历史开发记录，不与上面的消融表混合。

## 对照 221

```latex
\section{Sensitivity Analyses}
```

**中文直译**

敏感性分析

## 对照 222

```latex
This section supports \S\ref{sec:exp-robust}. It varies the severity, the historical
support, the selected parameters, and the mask realisation in turn.
```

**中文直译**

本节支持第 \ref{sec:exp-robust} 节，依次改变严重度、历史支持、选定参数和掩码实现。

## 对照 223

```latex
\subsection{Full Severity Results}
```

**中文直译**

完整严重度结果

## 对照 224

```latex
\subsubsection{Severity Tables}
```

**中文直译**

严重度表

## 对照 225

```latex
Tables~\ref{tab:app-sev10}--\ref{tab:app-sev50} give the full severity sweep over the roster of
Table~\ref{tab:main}. No method is retuned
between severities. \introact{} reuses the $k$, $\beta$ and $\lambda$ frozen on the bank, and every
baseline reuses the models and rules fixed on TRAIN. The $10\%$ column is the main-text
condition. The $30\%$ and $50\%$ columns test whether one frozen configuration holds across
the registered severity grid, and they are not a generalisation test to unseen severity,
because the replay bank already samples from the same three levels.\begin{table}[htbp]
```

**中文直译**

表 \ref{tab:app-sev10} 至 \ref{tab:app-sev50} 给出表 \ref{tab:main} 方法清单的完整严重度扫描。方法均不在严重度间重新调参。IntroAct-TS 复用回放库上冻结的 k、β、λ，各基线复用 TRAIN 上固定的模型和规则。10% 对应正文条件，30% 与 50% 检验同一冻结配置是否适用于登记的严重度网格。因为回放库已经采样相同三级，它们不是对未见严重度的泛化测试。

## 对照 226

```latex
\caption{Complete results at $10\%$ severity, source-macro averaged in the two scaled metrics. This is the roster Figure~\ref{fig:robust} summarises, computed from the same records.}
```

**中文直译**

10% 严重度下的完整结果，两项缩放指标均按数据源宏平均。该方法清单由图 \ref{fig:robust} 汇总，使用相同记录计算。

### 共用数值表 37

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrr@{}}
    \toprule
    Method & MASE $\downarrow$ & RMSSE $\downarrow$ \\
    \midrule
    \textsc{Native Keep} & 1.576 & 1.325 \\
    \textsc{Best Fixed} & 1.488 & 1.262 \\
    Source Fixed & 1.445 & 1.235 \\
    R2-CART & 1.459 & 1.243 \\
    Fixed SAITS & 1.459 & 1.245 \\
    TATO & 1.616 & 1.333 \\
    TimesNet & 1.741 & 1.467 \\
    PSW-I & 1.612 & 1.344 \\
    T1 & 1.906 & 1.562 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.425 & 1.221 \\
    \midrule
    \oracle{Catalog Oracle (diagnostic)} & \oracle{1.258} & \oracle{1.099} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 227

```latex
\caption{Complete results at $30\%$ severity for the same roster, source-macro averaged in the two scaled metrics. The configuration is identical to the $10\%$ table and nothing is retuned.}
```

**中文直译**

同一方法清单在 30% 严重度的完整结果，两项缩放指标均按数据源宏平均。配置与 10% 表相同，不重新调参。

### 共用数值表 38

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrr@{}}
    \toprule
    Method & MASE $\downarrow$ & RMSSE $\downarrow$ \\
    \midrule
    \textsc{Native Keep} & 1.794 & 1.439 \\
    \textsc{Best Fixed} & 1.702 & 1.378 \\
    Source Fixed & 1.674 & 1.360 \\
    R2-CART & 1.694 & 1.374 \\
    Fixed SAITS & 1.738 & 1.400 \\
    TATO & 1.941 & 1.526 \\
    TimesNet & 1.867 & 1.541 \\
    PSW-I & 1.793 & 1.434 \\
    T1 & 1.992 & 1.600 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.692 & 1.373 \\
    \midrule
    \oracle{Catalog Oracle (diagnostic)} & \oracle{1.421} & \oracle{1.181} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 228

```latex
\caption{Complete results at $50\%$ severity for the same roster. This level is inside the registered grid the replay bank samples from, so the rows show within-grid robustness of one frozen configuration and not behaviour on unseen severity.}
```

**中文直译**

同一方法清单在 50% 严重度的完整结果。该水平位于回放库采样的登记网格内部，因此各行描述一个冻结配置的网格内稳健性，不描述未见严重度上的行为。

### 共用数值表 39

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrr@{}}
    \toprule
    Method & MASE $\downarrow$ & RMSSE $\downarrow$ \\
    \midrule
    \textsc{Native Keep} & 1.875 & 1.486 \\
    \textsc{Best Fixed} & 1.738 & 1.397 \\
    Source Fixed & 1.709 & 1.377 \\
    R2-CART & 1.757 & 1.412 \\
    Fixed SAITS & 1.763 & 1.409 \\
    TATO & 2.036 & 1.574 \\
    TimesNet & 1.964 & 1.605 \\
    PSW-I & 1.877 & 1.470 \\
    T1 & 2.083 & 1.652 \\
    \midrule
    \rowcolor{bestgray}\introact{} & 1.731 & 1.400 \\
    \midrule
    \oracle{Catalog Oracle (diagnostic)} & \oracle{1.475} & \oracle{1.212} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 229

```latex
\subsubsection{Severity Trend by Backbone}
```

**中文直译**

分骨干严重度趋势

## 对照 230

```latex
Figure~\ref{fig:robust} averages the severity sweep over the backbones, and
Table~\ref{tab:app-trend} separates them, because a configuration that holds on average may
still be carried by one family. Every row reuses the models and rules frozen on TRAIN and
nothing is retuned per severity.
```

**中文直译**

图 \ref{fig:robust} 对骨干平均严重度扫描，表 \ref{tab:app-trend} 则分开报告，因为平均有效的配置仍可能主要由某一系列贡献。各行复用 TRAIN 上冻结的模型和规则，不按严重度调参。

## 对照 231

```latex
\caption{Source-macro MASE at each registered severity, one block of columns per frozen
backbone. The evaluation set, the roster and the frozen configuration are the ones of
Table~\ref{tab:main}.}
```

**中文直译**

各登记严重度的数据源宏平均 MASE，每个冻结骨干一组列。评估集、方法清单和冻结配置与表 \ref{tab:main} 相同。

### 共用数值表 40

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}
    \toprule
     & \multicolumn{3}{c}{Bolt} & \multicolumn{3}{c}{TimesFM} & \multicolumn{3}{c}{Chronos-2} \\
    \cmidrule(lr){2-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}
    Method & $10\%$ & $30\%$ & $50\%$ & $10\%$ & $30\%$ & $50\%$ & $10\%$ & $30\%$ & $50\%$ \\
    \midrule
    \textsc{Native Keep} & 1.466 & 1.684 & 1.792 & 1.682 & 1.864 & 1.947 & 1.579 & 1.833 & 1.887 \\
    \textsc{Best Fixed} & 1.428 & 1.675 & 1.695 & 1.579 & 1.729 & 1.835 & 1.456 & 1.703 & 1.683 \\
    Source Fixed & 1.360 & 1.668 & 1.678 & 1.527 & 1.677 & 1.783 & 1.448 & 1.678 & 1.667 \\
    R2-CART & 1.406 & 1.674 & 1.719 & 1.594 & 1.724 & 1.827 & 1.377 & 1.684 & 1.726 \\
    Fixed SAITS & 1.469 & 1.706 & 1.740 & 1.465 & 1.821 & 1.841 & 1.441 & 1.687 & 1.708 \\
    TATO & 1.620 & 1.986 & 2.027 & 1.614 & 1.873 & 1.988 & 1.614 & 1.963 & 2.091 \\
    TimesNet & 1.722 & 1.709 & 1.826 & 1.740 & 1.844 & 1.951 & 1.762 & 2.047 & 2.115 \\
    PSW-I & 1.578 & 1.741 & 1.824 & 1.685 & 1.780 & 1.897 & 1.574 & 1.857 & 1.909 \\
    T1 & 1.954 & 1.936 & 2.038 & 1.849 & 2.043 & 2.093 & 1.914 & 1.998 & 2.118 \\
    \midrule
    \introact{} & 1.383 & 1.657 & 1.714 & 1.528 & 1.698 & 1.779 & 1.365 & 1.721 & 1.700 \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 232

```latex
\subsection{Replay Bank Size}
```

**中文直译**

回放库规模

## 对照 233

```latex
Parent-level subsamples holding $25\%$, $50\%$ and $100\%$ of the bank measure how much
historical support the pooled estimate needs, with the frozen $(k,\beta,\lambda)$ left
unchanged so the subsample is the only thing that varies. The two smaller fractions average
three parent-level draws. Error falls as support grows, from 1.459 at a quarter of the bank to
1.437 at a half and 1.425 at the whole, and the repair rate falls with it, so a thinner bank
makes the recorded rule less accurate and less selective in aggregate. Subsampling changes
the available neighbours and, when $\lambda>0$, their weight relative to the source mean.
The aggregate trend does not isolate these effects. Three points do not
establish a scaling law, and the comparison holds the configuration fixed rather than
reselecting it at each size.
```

**中文直译**

在父窗口层面保留 25%、50% 和 100% 回放库，测量汇聚估计所需历史支持。冻结的 (k,β,λ) 不变，因此仅子样本变化。两个较小比例各平均三次父窗口抽样。支持增加时，误差由四分之一库的 1.459 降至一半库的 1.437 和全库的 1.425，修复率也下降，因此较小库使记录规则在总体上精度更低、选择性更弱。子采样改变可用邻居，并在 λ>0 时改变其相对于数据源均值的权重。总体趋势未分离这些影响。三个点不能建立缩放定律，比较固定配置，不在各规模重新选择。

## 对照 234

```latex
\caption{Replay-bank size ablation. The bank is subsampled by parent, keeping
every action and severity per retained parent, so the subsample changes the amount of
historical support at fixed settings.}
```

**中文直译**

回放库规模消融。按父窗口子采样，每个保留父窗口的所有动作和严重度都保留，因此只在固定设置下改变历史支持量。

### 共用数值表 41

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrr@{}}
    \toprule
    Bank fraction & MASE $\downarrow$ & Repair rate & HIR $\downarrow$ & Harmful Loss $\downarrow$ & Calls $\downarrow$ \\
    \midrule
    $25\%$  & 1.459 & 58.7\% & 40.4\% & 0.0334 & 1.59 \\
    $50\%$  & 1.437 & 58.6\% & 41.2\% & 0.0350 & 1.59 \\
    $100\%$ & 1.425 & 55.2\% & 40.1\% & 0.0340 & 1.55 \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 235

```latex
\subsection{Mask-Realisation Stability}
```

**中文直译**

掩码实现稳定性

## 对照 236

```latex
The main experiment uses one deterministic mask per parent. This appendix repeats the
comparison under two further deterministic mask realisations of the same parents, so that a
reader can see whether a conclusion depends on one particular realisation of the deletion
pattern. The three realisations are fixed before the run and are never treated as three
independent samples of parents: the statistical unit stays the parent, and the three
realisations are read as a stability check on the same parent set. Significance testing is
never performed across them.
```

**中文直译**

主实验每个父窗口使用一种确定性掩码。本附录在同一父窗口上采用另两种确定性掩码重复比较，检查结论是否依赖特定删除模式实现。三种实现在运行前固定，不视为三个独立父窗口样本。统计单位仍是父窗口，三种实现仅作为同一父窗口集的稳定性检查，不跨实现进行显著性检验。

## 对照 237

```latex
The recorded subset comprises all eight sources, patterns P1 to P4, $10\%$ severity,
$H \in \{96,192\}$, on all three backbones. Table~\ref{tab:app-seeds} carries \introact{}
against \textsc{Keep} on each realisation. The full rule moves by at most 0.032 source-macro
MASE on any backbone across the three realisations, and its margin over the unchanged input
keeps both its sign and its rough size on every one of them. Reporting the spread over three
realisations is a stability diagnostic and is not an additional estimate of variance. The
external baselines added in this revision cycle (TimesNet, PSW-I and T1) are scored on the
primary realisation only, so the table reports the selection method and the unchanged
input, the two rows every realisation shares.
```

**中文直译**

记录子集覆盖八个源、P1 至 P4、10% 严重度、H∈{96,192} 及三个骨干。表 \ref{tab:app-seeds} 在每种实现上比较 IntroAct-TS 与 KEEP。三个实现中任一骨干的完整规则数据源宏平均 MASE 最大变化为 0.032，相对于保持输入不变的差值方向及大致幅度均保留。三种实现的极差是稳定性诊断，不是额外方差估计。本轮新增外部基线 TimesNet、PSW-I、T1 仅在主实现评分，因此该表仅报告所有实现共有的选择方法和保持输入不变两行。

## 对照 238

```latex
\caption{Mask-realisation stability. Each row is one deterministic mask realisation on the
recorded dual-horizon subset. $\Delta$ is \introact{} minus \textsc{Keep}, so a negative
value favours \introact{}. The spread across realisations is a stability diagnostic and is not
an additional sample of parents.}
```

**中文直译**

掩码实现稳定性。每行是在记录的双预测长度子集上的一种确定性掩码实现。Δ 为 IntroAct-TS 减 KEEP，负值有利于 IntroAct-TS。实现间极差是稳定性诊断，不是额外父窗口样本。

### 共用数值表 42

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrr@{}}
    \toprule
    Backbone & Mask realisation & MASE $\downarrow$ & $\Delta$ vs \textsc{Keep} & Intervention rate \\
    \midrule
    Bolt      & primary seed        & 1.383 & $-0.084$ & 36.4\% \\
    Bolt      & second realisation  & 1.370 & $-0.091$ & 35.0\% \\
    Bolt      & third realisation   & 1.394 & $-0.069$ & 35.7\% \\
    \midrule
    TimesFM   & primary seed        & 1.528 & $-0.154$ & 92.9\% \\
    TimesFM   & second realisation  & 1.497 & $-0.175$ & 93.2\% \\
    TimesFM   & third realisation   & 1.507 & $-0.159$ & 92.9\% \\
    \midrule
    Chronos-2 & primary seed        & 1.365 & $-0.214$ & 36.2\% \\
    Chronos-2 & second realisation  & 1.360 & $-0.217$ & 35.0\% \\
    Chronos-2 & third realisation   & 1.381 & $-0.222$ & 37.4\% \\
    \midrule
    \multicolumn{2}{l}{Spread over the three realisations (Bolt)}      & 0.024 & n/a & 1.4\% \\
    \multicolumn{2}{l}{Spread over the three realisations (TimesFM)}   & 0.032 & n/a & 0.3\% \\
    \multicolumn{2}{l}{Spread over the three realisations (Chronos-2)} & 0.021 & n/a & 2.4\% \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 239

```latex
The mask-stability table aggregates both horizons, 96 and 192.
The horizon-96-only MASE values of \introact{} are 1.1989, 1.1865 and 1.2093 for Bolt,
1.2368, 1.2466 and 1.2107 for TimesFM, and 1.1120, 1.0879 and 1.1368 for Chronos-2, in the
primary, second and third realisation order.
```

**中文直译**

掩码稳定性表聚合 96 和 192 两个预测长度。仅 H=96 时，IntroAct-TS 在主、第二、第三实现上的 MASE 分别为 Bolt 的 1.1989、1.1865、1.2093，TimesFM 的 1.2368、1.2466、1.2107，以及 Chronos-2 的 1.1120、1.0879、1.1368。

## 对照 240

```latex
\section{Confirmatory Evaluation}
```

**中文直译**

确认性评估

## 对照 241

```latex
Earlier revisions used the main TEST block, so its comparisons cannot exclude adaptation
of the design to that block. The additional evaluation covers Solar, with 137 channels at
ten-minute resolution, and US Term Structure, with 40 daily yield-curve series and about
$4.3\%$ native missingness preserved by the data contract. Both sources appeared in earlier
development under a different protocol. Their current TEST periods were registered before
the additional run and excluded from decisions in the present design cycle. This evaluation
tests the frozen procedure with new training-side banks and selections, rather than a claim
of transfer to wholly unseen sources.
```

**中文直译**

早期版本使用过主 TEST 块，因此比较不能排除设计适应了该块。额外评价覆盖 Solar 和 US Term Structure，前者含 137 个通道、十分钟分辨率，后者含 40 条日频收益率曲线，数据约定保留约 4.3% 的原生缺失。两源曾在早期不同协议下的开发中出现。当前 TEST 时段在额外运行前登记，并排除于本轮设计决策。该评估使用新的训练侧回放库及选择，检验冻结流程，不主张迁移到完全未见过的数据源。

## 对照 242

```latex
The confirmatory run repeats the whole pipeline on those two sources with nothing carried over
from the main set except the code. Their replay bank is built from their own TRAIN region at
the same context length, stride and purge, their own $(k,\beta,\lambda)$ is selected by
leave-one-parent-out under the same harm cap and the same one standard error rule, and their
execution threshold is calibrated on their own internal block. The bank holds 1176 episodes
over 49 parents and the evaluation holds 168 episodes over 21 parents. The evaluation was run
once. Table~\ref{tab:confirmatory} is that run.
```

**中文直译**

确认运行在这两个源上重复完整流程，除了代码，不从主集继承其他内容。回放库由自身 TRAIN 区域以相同上下文长度、步长和隔离规则构建，自身 (k,β,λ) 按相同伤害上限和一个标准误规则进行留一父窗口选择，执行阈值在自身内部块校准。回放库包含 49 个父窗口、1,176 个样例，评价包含 21 个父窗口、168 个样例。评估仅运行一次，表 \ref{tab:confirmatory} 即该次结果。

## 对照 243

```latex
\caption{Confirmatory evaluation on Solar and US Term Structure, source-macro MASE at
$10\%$ missingness over 21 test parents. The evaluated periods did not enter the present design cycle. Both sources appeared in earlier development.
The paired difference is \introact{} minus the row, so a negative value favours
\introact{}, and an asterisk marks a Holm-adjusted $p<0.05$ within the backbone.
Bold and underline mark the lowest and second-lowest error, excluding the oracle.}
```

**中文直译**

Solar 与 US Term Structure 的确认性评估，在 21 个测试父窗口、10% 缺失率下报告数据源宏平均 MASE。所评价时段未进入本轮设计，两源曾出现在早期开发。配对差值为 IntroAct-TS 减对应行，负值有利于 IntroAct-TS。星号表示骨干内 Holm 校正后 p<0.05。排除 oracle 后，最小和次小误差分别加粗及加下划线。

### 共用数值表 43

```latex
\adjustbox{max width=\textwidth}{\begin{tabular}{lccccccc}
    \toprule
    Method & Bolt & TimesFM & Chronos-2 & Overall & \multicolumn{3}{c}{Paired difference against \introact{}} \\
    \cmidrule(lr){6-8}
    & & & & & Bolt & TimesFM & Chronos-2 \\
    \midrule
    Native KEEP & 5.108 & 4.488 & 4.523 & 4.707 & $-0.837^{*}$ & $-0.296$ & $-0.309^{*}$ \\
    Best Fixed & \second{4.409} & \second{3.917} & 4.344 & \best{4.223} & $-0.137^{*}$ & $+0.275$ & $-0.129^{*}$ \\
    Source Fixed & 5.022 & \best{3.831} & \best{4.036} & 4.296 & $-0.750^{*}$ & $+0.361^{*}$ & $+0.178$ \\
    Fixed SAITS & 5.095 & 4.324 & 4.588 & 4.669 & $-0.824^{*}$ & $-0.133$ & $-0.373^{*}$ \\
    R2-CART & 4.870 & 4.279 & \second{4.172} & 4.440 & $-0.599$ & $-0.087$ & $+0.043$ \\
    \midrule
    \rowcolor{bestgray}\introact{} & \best{4.271} & 4.191 & 4.215 & \second{4.226} & -- & -- & -- \\
    \midrule
    Catalog Oracle & \oracle{3.747} & \oracle{3.264} & \oracle{3.623} & \oracle{3.544} & \oracle{--} & \oracle{--} & \oracle{--} \\
    \bottomrule
  \end{tabular}}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 244

```latex
The additional evaluation supports improvement over KEEP on Bolt and Chronos-2, with paired
intervals excluding zero. Against Best Fixed, the aggregate values are 4.226 and 4.223.
FULL is better on Bolt and Chronos-2, where the Holm-adjusted tests are significant, while
Best Fixed is numerically better on TimesFM. These directions do not support a consistent
advantage over Best Fixed, and the near-equal aggregate does not establish equivalence.
Training-side selection chooses pooling weights of zero on Bolt and TimesFM and 64 on
Chronos-2. This is a record of procedure transfer, with configuration selection repeated
using the additional sources' TRAIN data.
```

**中文直译**

额外评价支持在 Bolt 和 Chronos-2 上优于 KEEP，配对区间不含零。相对于 Best Fixed，总体值为 4.226 对 4.223。FULL 在 Bolt 和 Chronos-2 上更好，Holm 校正检验显著，Best Fixed 在 TimesFM 上数值更好。这些方向不支持相对于 Best Fixed 的一致优势，近似相等的总体值也不能确立等效性。训练侧选择在 Bolt 和 TimesFM 上采用零汇聚权重，在 Chronos-2 上采用 64。这记录了流程迁移，配置选择使用额外源的 TRAIN 数据重新进行。

## 对照 245

```latex
\section{Selection Rule and Historical Configuration Record}
```

**中文直译**

选择规则与历史配置记录

## 对照 246

```latex
The saved selection records contain eleven, six and twenty-nine admissible settings within
one paired standard error of the lowest cross-validated source-macro error on Bolt, TimesFM
and Chronos-2, respectively. The selected rule chooses the least-intervening setting in this
band, breaking remaining ties by the smaller neighbourhood. This criterion favours fewer
repairs among configurations with similar cross-validated error. It does not establish that
the strict minimum overfits.
```

**中文直译**

保存的选择记录中，Bolt、TimesFM 和 Chronos-2 分别有十一、六和二十九个可用设置，位于最低交叉验证数据源宏平均误差的一个配对标准误内。选定规则在此范围内选择干预最少者，仍并列时选择较小邻域。这一标准在交叉验证误差相近的配置中偏好较少修复，不能证明严格最小值过拟合。

## 对照 247

```latex
The strict-minimum configurations are $(8,1.0,0)$, $(32,1.0,64)$ and $(16,0,0)$ on Bolt,
TimesFM and Chronos-2. The current one-standard-error configurations are $(256,1.64,0)$,
$(32,1.64,64)$ and $(64,1.64,0)$. The minimum rule gives 1.431 aggregate MASE, a $76.5\%$
repair rate and 0.0430 harmful loss, compared with 1.425, $55.2\%$ and 0.0340 for the
current rule. Both evaluations are retained. The minimum-rule results were inspected on
TEST before the one-standard-error rule was adopted. Although the latter rule had been
registered in an earlier development revision, this sequence prevents treating the current
TEST comparison as an independent confirmation. The minimum-rule records are retained in
the server evaluation archive and its local synchronisation bundle.
```

**中文直译**

Bolt、TimesFM 和 Chronos-2 的严格最小值配置分别为 (8,1.0,0)、(32,1.0,64)、(16,0,0)，当前一个标准误配置分别为 (256,1.64,0)、(32,1.64,64)、(64,1.64,0)。最小值规则总体 MASE 为 1.431，修复率为 76.5%，伤害损失为 0.0430，当前规则对应 1.425、55.2%、0.0340。两套评价均保留。在采用一个标准误规则之前，已经查看过最小值规则的 TEST 结果。虽然前者曾在较早开发版本登记，这一顺序使当前 TEST 比较不能作为独立确认。最小值规则记录保留于服务器评价档案及其本地同步包。

## 对照 248

```latex
\section{Cost and Reproducibility}
```

**中文直译**

成本与可复现性

## 对照 249

```latex
This section supports \S\ref{sec:exp-cost} and records the artefact traceability and the
development record that the main text relies on.
```

**中文直译**

本节支持第 \ref{sec:exp-cost} 节，并记录正文依赖的产物可追溯性和开发历史。

## 对照 250

```latex
\subsection{Runtime and Failure Audit}
```

**中文直译**

运行时间与失败审计

## 对照 251

```latex
Tables~\ref{tab:app-efficiency} and \ref{tab:app-calls} retain historical cost accounting
from the earlier operating point. They do not describe the current $55.2\%$ repair rate.
Current measurements appear in Appendix~\ref{app:calls-measured}. Offline cost and online cost are kept in separate columns because
they are not directly comparable: the offline replay bank is built once per backbone revision,
per source, and per horizon, whereas the online columns are per request. Within each column a
lower value is better, and the two columns are read separately. The recorded per-request
latency covers the forecasting-backbone call and, for \introact{}, the measured retrieval
overhead. Method-side serving computation was not separately instrumented in the recorded
runs, so the latency cells are labelled accordingly in the table. Cold start is
reported on its own line. Candidate materialisation is a separate line because it is paid
before the decision is made and is not a forecasting-backbone call.
```

**中文直译**

表 \ref{tab:app-efficiency} 和 \ref{tab:app-calls} 保留早期工作点的历史成本核算，不描述当前 55.2% 修复率。当前测量见附录 \ref{app:calls-measured}。离线与在线成本分列，因为不能直接比较。离线回放库按骨干版本、源和预测长度构建一次，在线列按请求计。各列越低越好，应分别解读。记录的请求延迟包含预测骨干调用，以及 IntroAct-TS 的检索测量开销。记录运行未单独测量方法侧服务计算，因此表中延迟格据此标注。冷启动单列，候选构造也单列，因为在决策前支付，不属于预测骨干调用。

## 对照 252

```latex
\caption{Historical deployment-cost accounting, offline and online kept
separate. Latency percentiles are per request and exclude cold start, reported on its own
line. Backbone calls counts forecasting-backbone calls per request and excludes candidate
materialisation, which is reported in its own column. The latency cells of Fixed SAITS and
TATO record only the forecasting-backbone call, macro-averaged over the three backbones. Their method-side serving computation (the imputation pass or the pipeline application) was
not separately instrumented in the recorded runs. The \introact{} latency is synthesised
from the recorded backbone-call percentiles and the measured retrieval overhead
($2.3$~ms per request), at the recorded mean of $1.65$ calls for the mean column and two
calls for the tail columns. It is an accounting estimate, not a single timed serving pass.}
```

**中文直译**

历史部署成本核算，离线与在线分开。延迟分位数按请求计，不含单列的冷启动。骨干调用数按请求计，不含单列的候选构造。Fixed SAITS 和 TATO 延迟仅记录预测骨干调用，再对三个骨干宏平均，其方法侧插补或流程应用计算未单独测量。IntroAct-TS 延迟由记录的骨干调用分位数与每请求 2.3 毫秒检索开销合成，均值列采用记录的平均 1.65 次调用，尾部列按两次调用。这是核算估计，不是一次服务过程的完整计时。

### 共用数值表 44

```latex
\begin{tabularx}{\textwidth}{@{}lXXrrrr@{}}
    \toprule
    Method & Offline work & Candidates & \shortstack[r]{Calls/\\request} & \shortstack[r]{Mean\\latency} & P95 $\downarrow$ & Max $\downarrow$ \\
    \midrule
    Fixed SAITS           & 8 deployment imputers and 16 cross-fitted ones, 247 min total     & 1 per request     & 1.00     & 56 ms     & 62 ms     & 388 ms \\
    TATO               & 3,072 calls, once per backbone   & 1 per request   & 1.00   & 56 ms   & 62 ms   & 388 ms \\
    \rowcolor{bestgray}\introact{} & 30,160 calls, once per backbone & 5 per request & 1.65 & 95 ms & 127 ms & 781 ms \\
    \midrule
    \multicolumn{7}{p{0.97\textwidth}}{\footnotesize Cold start: one-time backbone load of 3.7--7.3 s per process (recorded across the three backbones) \quad
    Failure/timeout share: 0.00\%} \\
    \bottomrule
  \end{tabularx}
```

**中文表内文字**

列为方法、离线工作、候选数、每请求调用数、平均延迟、P95、最大值。Fixed SAITS 为 8 个部署插补器和 16 个交叉拟合模型，共 247 分钟，每请求 1 个候选、1.00 次调用，56、62、388 毫秒。TATO 每骨干一次 3,072 次离线调用，每请求 1 个候选、1.00 次调用，56、62、388 毫秒。IntroAct-TS 每骨干一次 30,160 次离线调用，每请求 5 个候选、1.65 次调用，95、127、781 毫秒。三个骨干记录的每进程一次冷启动为 3.7–7.3 秒，失败或超时占比 0.00%。这是历史核算，不是当前工作点。

## 对照 253

```latex
Table~\ref{tab:app-calls} separates offline from online cost and separates successes from
failures. Failures and timeouts are never counted as successes and are never dropped from the
denominator. A request that fails to produce a forecast is reported with its failure status and incurred cost. Each request uses one forecasting-backbone call for the reference action
and, when an intervention is executed, one further call for the selected action, so the online
count is between one and two backbone calls. When the decision returns \textsc{Keep} the input
is left untouched and the reference call is the returned forecast. Candidate materialisation
and scoring are booked on their own line because they are paid before the decision and do not
touch the backbone.
```

**中文直译**

表 \ref{tab:app-calls} 区分离线与在线、成功与失败。失败和超时不计为成功，也不从分母移除。无法产生预测的请求报告失败状态和已发生成本。每个请求为参考动作调用骨干一次，执行干预时为所选动作再调用一次，因此在线计数为一至两次。返回 KEEP 时输入不变，返回参考调用的预测。候选构造和评分在决策前支付，不调用骨干，单独核算。

## 对照 254

```latex
\caption{Historical backbone-call accounting at the earlier $65.4\%$ repair rate.
These counts are not the current main-table operating point. Latency is reported per request and excludes cold start,
which is reported on its own line. The offline replay-bank build and the one-off selector fit
are amortised and reported separately. Candidate materialisation and scoring are booked on
their own line and are not forecasting-backbone calls.}
```

**中文直译**

早期 65.4% 修复率下的历史骨干调用核算。这些计数不对应当前主表工作点。延迟按请求报告，不含单列的冷启动。离线回放库构建和一次性选择器拟合为摊销成本，单独报告。候选构造及评分单列，不属于预测骨干调用。

### 共用数值表 45

```latex
\begin{tabularx}{\textwidth}{@{}XrrX@{}}
    \toprule
    Outcome & Requests & Share & Backbone calls per request \\
    \midrule
    \textsc{Keep} returned (input untouched)   & 263    & 34.6\%    & 1 \\
    Intervention executed (input changed)      & 497     & 65.4\%     & 2 \\
    Failed before any forecast                 & 0    & 0.00\%    & 0 \\
    Timed out after the forecast               & 0 & 0.00\% & 0 \\
    \midrule
    Candidate materialisation and scoring (per request) & 3,800 & n/a & 0 \\
    Offline replay-bank build (amortised)      & n/a & n/a & 30,160 calls, once per backbone \\
    Offline selector configuration (amortised)  & n/a & n/a & no parametric fit. Bank-fitted feature scaling and a one-time $(k,\beta)$ grid selection \\
    Cold start (backbone load, once per process) & 3 backbones & n/a & 3.7--7.3 s recorded load time \\
    \bottomrule
  \end{tabularx}
```

**中文表内文字**

历史调用表列为结果、请求数、比例、每请求骨干调用。返回 KEEP 且输入不变为 263、34.6%、1。执行干预且输入改变为 497、65.4%、2。预测前失败和预测后超时均为 0。每请求候选构造与评分记录 3,800、不适用、0。离线回放构建一次每骨干 30,160 次调用。离线选择器配置无参数化拟合，包含库拟合的特征缩放及一次 (k,β) 网格选择。冷启动为三个骨干，每进程一次，记录加载时间 3.7–7.3 秒。

## 对照 255

```latex
\subsection{Measured Serving Cost}
```

**中文直译**

实测服务成本

## 对照 256

```latex
Every number here is a wall clock measurement of a served request on a GPU with nothing else
on it, at batch one, with the worker caches that a deployment does not have switched off and
with a CUDA synchronisation around each stage. The request set is the first ten episodes of
each source in the main evaluation block, eighty requests per backbone, and the same set is
timed for every row. The legality check that compares the freshly constructed action set with
the frozen catalog passes on all eighty requests. SAITS timing comes from a live batch-one
forward of a refitted deployment model, but the chain uses archived SAITS candidate values.
The original run retained no SAITS checkpoints, and refitting cannot reproduce its exact
guard outcomes. Thus the measurement preserves the frozen decisions while measuring live
computation, but is not a fresh end-to-end reproduction of the original SAITS outputs.
```

**中文直译**

此处每个值都是批量一、无其他任务占用 GPU 时，服务请求的实际时钟测量。关闭部署时不存在的工作进程缓存，每个阶段前后 CUDA 同步。请求集取主评价块每个源前十个样例，每骨干八十个请求，各行计时使用同一集合。重新构造动作集与冻结目录的合法性检查在八十个请求上全部通过。SAITS 计时来自重新拟合部署模型的实时批量一前向，但服务链使用归档的 SAITS 候选值。原始运行没有保留 SAITS 检查点，重新拟合无法复现精确约束检查结果。因此，测量在保留冻结决策的同时计时真实计算，但不是重新端到端复现原始 SAITS 输出。

## 对照 257

```latex
\caption{Serving cost per request, measured at batch one on an idle card. The upper block
gives the median and the maximum of the end-to-end request time of each row. The lower block
splits the full method's mean request time by stage. Cold start is excluded and reported
separately below.}
```

**中文直译**

空闲显卡、批量一的逐请求服务成本。上半部分给出各行端到端请求时间的中位数和最大值，下半部分按阶段细分完整方法的平均请求时间。不包含冷启动，冷启动在下文单独报告。

### 共用数值表 46

```latex
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrr@{}}
    \toprule
    & \multicolumn{2}{c}{Bolt} & \multicolumn{2}{c}{TimesFM} & \multicolumn{2}{c}{Chronos-2} \\
    \cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}
    Row & median & max & median & max & median & max \\
    \midrule
    Native KEEP & 53.9 & 59.6 & 114.5 & 179.9 & 16.0 & 19.5 \\
    Best Fixed & 57.0 & 185.7 & 116.8 & 251.7 & 18.8 & 142.1 \\
    Fixed SAITS & 58.5 & 76.0 & 120.3 & 149.3 & 20.7 & 38.3 \\
    TATO & 40.2 & 61.3 & 115.2 & 180.2 & 16.9 & 22.2 \\
    \rowcolor{bestgray}\introact{} & 166.6 & 526.2 & 287.5 & 662.5 & 93.8 & 452.7 \\
    \midrule
    \multicolumn{7}{l}{Mean stage time of \introact{}, in milliseconds} \\
    Reference forecast & \multicolumn{2}{c}{47.9} & \multicolumn{2}{c}{115.1} & \multicolumn{2}{c}{16.3} \\
    In-context candidates & \multicolumn{2}{c}{77.5} & \multicolumn{2}{c}{77.5} & \multicolumn{2}{c}{77.5} \\
    SAITS candidate & \multicolumn{2}{c}{5.4} & \multicolumn{2}{c}{5.4} & \multicolumn{2}{c}{5.4} \\
    Arithmetic candidates & \multicolumn{2}{c}{21.2} & \multicolumn{2}{c}{21.5} & \multicolumn{2}{c}{21.2} \\
    Plausibility guard & \multicolumn{2}{c}{2.1} & \multicolumn{2}{c}{2.0} & \multicolumn{2}{c}{2.0} \\
    State features & \multicolumn{2}{c}{9.2} & \multicolumn{2}{c}{9.0} & \multicolumn{2}{c}{9.2} \\
    Retrieval and decision & \multicolumn{2}{c}{2.9} & \multicolumn{2}{c}{3.1} & \multicolumn{2}{c}{2.8} \\
    Selected-action forecast & \multicolumn{2}{c}{32.0} & \multicolumn{2}{c}{64.8} & \multicolumn{2}{c}{13.8} \\
    \bottomrule
  \end{tabular*}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 258

```latex
Three readings follow from the table. The decision layer proper, which is retrieval and
scoring against the frozen bank, costs under 3.1 ms on every backbone and is the smallest
stage except the plausibility guard. What the method actually pays for is candidate
construction, and within that the two in-context repairs alone account for 77 ms, more than
the reference forecast on two of the three backbones. The maxima are three to five times the
medians. Candidate construction depends on admissibility, and requests with complete targets
require none. The timings alone do not isolate every cause of this variation.
```

**中文直译**

表中有三点。决策层本身，即对冻结回放库检索和评分，在每个骨干上都不足 3.1 毫秒，除合理性检查外是最小阶段。主要成本是候选构造，其中仅两个上下文修复就占 77 毫秒，在三个骨干中的两个上超过参考预测。最大值为中位数的三至五倍。候选构造取决于动作可用性，目标完整的请求不需要构造候选。计时本身未分离这些变化的所有原因。

## 对照 259

```latex
Cold start is separate and is paid once per process. Loading a frozen backbone takes 3.2 to
3.8 s, loading the in-context model takes 1.8 s, and bringing the whole service up, which
includes reading the replay bank and standardising it, takes 68 to 71 s. The replay bank
itself is built offline once per backbone revision and is not part of serving.
```

**中文直译**

冷启动单独核算，每个进程支付一次。加载冻结骨干需要 3.2 至 3.8 秒，加载上下文模型需要 1.8 秒，启动整个服务需要 68 至 71 秒，包含读取回放库和标准化。回放库本身按骨干版本离线构建一次，不属于服务过程。

## 对照 260

```latex
\subsection{Reproducibility Details}
```

**中文直译**

可复现性细节

## 对照 261

```latex
Each record in the result files contains: source, parent, origin, horizon, pattern,
severity, mask hash, backbone, backbone revision, method, action, input hash, prediction
hash, forecast, target reference id, MASE, MSE, MAE, RMSE, reconstruction MSE where
applicable, runtime components, failure, fallback, code SHA, and the resolved configuration.
Results are written to the logical result groups listed in Table~\ref{tab:app-groups}, each in
CSV, JSON, and Markdown form, with raw predictions retained alongside the aggregates. The
group names describe the stage that produced them and do not encode a version number, so that
a later revision of the protocol cannot be confused with the present one.
```

**中文直译**

结果文件的每条记录包含数据源、父窗口、起点、预测长度、模式、严重度、掩码哈希、骨干及版本、方法、动作、输入哈希、预测哈希、预测、目标引用标识、MASE、MSE、MAE、RMSE、适用时的重建 MSE、运行时间组成、失败、回退、代码 SHA 和解析后配置。结果写入表 \ref{tab:app-groups} 的逻辑结果组，提供 CSV、JSON 和 Markdown，并与聚合结果一起保留原始预测。组名描述生成阶段，不编码版本号，以免混淆后续协议与当前协议。

## 对照 262

```latex
\caption{Result groups written by the pipeline. Every number in the main text and in the
appendices is generated from one of these groups and nothing is transcribed by hand.}
```

**中文直译**

流程写出的结果组。正文与附录的每个数值均由这些组之一生成，不手工转录。

### 共用数值表 47

```latex
\adjustbox{max width=\textwidth}{\begin{tabular}{@{}p{.18\textwidth}p{.44\textwidth}p{.31\textwidth}@{}}
    \toprule
    Result group & Contents & Consumed by \\
    \midrule
    \texttt{protocol}       & frozen protocol, source manifests, split boundaries, TEST manifest & Appendix~\ref{app:splits} \\
    \texttt{replay\_bank}   & replay records $(z_{i,a}, a, g_{i,a})$ with input and prediction hashes & \S\ref{sec:method-replay} \\
    \texttt{baselines}      & baseline training runs, resolved hyperparameters, checkpoints & \S\ref{sec:exp-main} \\
    \texttt{train\_eval}    & TRAIN-eval acceptance check before freezing & Appendix~\ref{app:splits} \\
    \texttt{main\_results}  & main matrix rows, all methods, all cells & Tables~\ref{tab:main}, \ref{tab:app-src-bolt-96}--\ref{tab:app-src-ch2-192} \\
    \texttt{ablations}      & the six ablation variants and the catalog oracle diagnostic & Table~\ref{tab:ablation}, \ref{tab:app-ablation} \\
    \texttt{robustness}     & severity, pattern, and mask-realisation sweeps & Figure~\ref{fig:robust}, Tables~ \ref{tab:app-sev10}--\ref{tab:app-sev50}, \ref{tab:app-seeds} \\
    \texttt{diagnostics}    & reconstruction and utility diagnostics, rank agreement & Appendix~\ref{app:recutils} \\
    \texttt{cost\_audit}    & call counts, latency, failures, timeouts, memory & Table~\ref{tab:app-efficiency}, Appendix~\ref{app:calls} \\
    \bottomrule
  \end{tabular}}
```

**中文表内文字**

列为结果组、内容、使用位置。protocol 保存冻结协议、源清单、划分边界、TEST 清单，供附录划分使用。replay_bank 保存 (zᵢ,ₐ,a,gᵢ,ₐ) 及输入与预测哈希，供方法回放部分使用。baselines 保存训练运行、解析超参数、检查点，供主结果使用。train_eval 保存冻结前内部验收。main_results 保存所有方法及单元的主矩阵行，供主表及分源表使用。ablations 保存六个消融变体和目录 oracle，供消融表使用。robustness 保存严重度、模式、掩码扫描，供稳健图及各敏感性表使用。diagnostics 保存重建、效用和排名一致性，供相关诊断附录使用。cost_audit 保存调用数、延迟、失败、超时、内存，供成本表与附录使用。

## 对照 263

```latex
Each evaluation configuration should identify the catalog, masks, split boundaries, feature
definitions and failure policy. A change to any of these requires a new identifier.
The current revision retains historical summaries alongside the v55 results and discloses the reuse of TEST
observations during design. It does not report completion of the separate verified pipeline.
A hardware-incident check reproduced the deterministic PSW-I path to float32 rounding scale.
T1 and TimesNet checks retrained models from new initialisations, so their non-identical
outputs do not verify the original checkpoints. Forecast-level validation remains incomplete.
```

**中文直译**

每个评价配置应标识目录、掩码、划分边界、特征定义和失败策略，任何变化都需要新标识。当前版本在 v55 结果旁保留历史汇总，并披露设计时复用 TEST 观测。不报告独立核验流程已完成。硬件事件检查将确定性的 PSW-I 路径复现到 float32 舍入量级。T1 和 TimesNet 检查从新的随机初始化重新训练，因此非相同输出并不能核验原始检查点。预测层面的验证仍未完成。

## 对照 264

```latex
\paragraph{Software and hardware.} Forecasts are produced with the released checkpoints of
```

**中文直译**

软件与硬件。预测由发布的 Chronos-Bolt、TimesFM 和 Chronos-2 检查点产生。

## 对照 265

```latex
Chronos-Bolt, TimesFM, and Chronos-2 at the revisions listed in Table~\ref{tab:app-repro}.
The surrounding code is Python 3.11.16 with NumPy 1.26.4, pandas
2.2.3, scikit-learn 1.5.2, and PyTorch 2.9.1+cu126. Runs are
executed on one NVIDIA RTX 4090 in bfloat16 for Chronos-Bolt, float32 for TimesFM and Chronos-2. The development-cycle numbers of
Appendix~\ref{app:development} were produced on a different machine and are not mixed with the
present results.
```

**中文直译**

具体版本列于表 \ref{tab:app-repro}。周边代码使用 Python 3.11.16、NumPy 1.26.4、pandas 2.2.3、scikit-learn 1.5.2、PyTorch 2.9.1+cu126。运行使用一张 NVIDIA RTX 4090，Chronos-Bolt 为 bfloat16，TimesFM 与 Chronos-2 为 float32。附录 \ref{app:development} 的开发周期数值在另一台机器产生，不与当前结果混合。

## 对照 266

```latex
\caption{Reproducibility anchors. Backbone revisions are the exact released checkpoints used
for every forecast in this paper. Seeds are the deterministic seeds that fix the mask
derivation, the replay-record ordering, and the selector fit.}
```

**中文直译**

可复现性依据。骨干版本为本文各预测使用的确切发布检查点。种子固定掩码生成、回放记录顺序和选择器拟合。

### 共用数值表 48

```latex
\begin{tabular}{@{}l p{0.70\textwidth}@{}}
    \toprule
    Item & Value \\
    \midrule
    Chronos-Bolt revision   & amazon/chronos-bolt-base at 5d9f166d69f47aef3401367a7b842e78fe97b121 \\
    TimesFM revision        & TimesFM-2.5-200M, local snapshot pinned in the run ledger \\
    Chronos-2 revision      & amazon/chronos-2 at 29ec3766d36d6f73f0696f85560a422f50e8498c \\
    Python and libraries    & 3.11.16, NumPy 1.26.4, pandas 2.2.3, scikit-learn 1.5.2, PyTorch 2.9.1+cu126 \\
    Hardware and precision  & one NVIDIA RTX 4090, bfloat16 for Chronos-Bolt, float32 for TimesFM and Chronos-2 \\
    Mask derivation seed    & 20260917, a fixed protocol seed \\
    Replay-record order seed & 101 \\
    Selector seed             & 101. No parametric utility model is trained, and feature-scaling statistics and $(k,\beta)$ are fixed by the TRAIN-side procedure of \S\ref{sec:method-decision} \\
    Protocol commit         & recorded with the run, in the released artefact ledger \\
    TEST manifest           & the TEST parents and origins listed in the evaluation records under results/v47/evaluation \\
    \bottomrule
  \end{tabular}
```

**中文表内文字**

列为项目、值。检查点标识和版本哈希原样保留。TimesFM 本地快照固定于运行台账。Python 与库版本及硬件精度按原表，Chronos-Bolt 使用 bfloat16，TimesFM 与 Chronos-2 使用 float32。掩码生成种子为固定协议种子 20260917，回放记录顺序种子 101，选择器种子 101。不训练参数化效用模型，特征缩放及 (k,β) 按 TRAIN 侧流程固定。协议提交保存在发布产物台账的运行记录中，TEST 清单记录 results/v47/evaluation 的父窗口与起点。

## 对照 267

```latex
The TEST manifest is the authoritative record of which parents and origins were held out. It
is written once, before any result is computed, and every table in this paper is generated
against that manifest.
```

**中文直译**

TEST 清单是保留哪些父窗口和起点的权威记录，在任何结果计算前写入一次，本文各表均依据该清单生成。

## 对照 268

```latex
\subsection{Development Negative Results}
```

**中文直译**

开发阶段负面结果

## 对照 269

```latex
This section records what was tried earlier in this line of work and rejected. It is included
because the final formulation is easier to read against the alternatives it replaced, and
because omitting it would misrepresent how the method was reached. Nothing here is independent
confirmation of any method, and these historical values must not be pooled with the main results.
```

**中文直译**

本节记录此前尝试并放弃的方案。保留这些记录有助于通过被替代方案理解最终形式，也避免歪曲方法的形成过程。这里没有任何独立确认，历史值不能与主结果混合。

## 对照 270

```latex
\caption{What was tried before the present formulation and why it was dropped. The
measurements behind these decisions come from an earlier protocol with a smaller development
split and different budget accounting, so they are recorded in the released ledger and are
not comparable with any table in this paper.}
```

**中文直译**

当前形式之前尝试的方案及放弃原因。相关测量来自较小开发划分和不同预算核算的早期协议，保留在发布台账中，不能与本文任何表格比较。

### 共用数值表 49

```latex
\begin{tabular}{@{}p{0.19\textwidth} p{0.35\textwidth} p{0.36\textwidth}@{}}
    \toprule
    Tried & What happened & What it changed here \\
    \midrule
    Projecting the estimated utility vector onto a convex feasible set before thresholding & the squared error of the estimated vector fell and the forecasting metric did not follow, and on one backbone it got worse & actions are ranked by a local mean and a dispersion penalty and a single threshold is applied, instead of calibrating a continuous score \\
    Underestimating the simple selector & it was competitive with the more elaborate candidate of that cycle and better than it on one backbone & R2-CART is a mandatory control in every main-text table \\
    Judging the gate by forecasting accuracy alone & reducing estimation error on a continuous score did not improve the discrete selection & the gate is evaluated on harmful intervention rate and harmful loss as well as on MASE \\
    \bottomrule
  \end{tabular}
```

**中文表内文字**

列为尝试、发生的结果、对本文的影响。阈值前投影效用向量到凸可行集，降低向量平方误差但未改善预测，一个骨干反而更差，因此改为局部均值、离散惩罚和单阈值。低估简单选择器时，它与复杂候选具有竞争力且在一个骨干更好，因此 R2-CART 成为正文必要对照。仅用预测精度评价门控时，连续得分估计误差减少未改善离散选择，因此门控同时评价有害干预率、伤害损失与 MASE。

## 对照 271

```latex
An earlier configuration tried to improve the action ranking by projecting estimated utility
vectors onto a convex feasible set before thresholding them. The projection reduced the squared
error of the estimated vector while failing to improve the final forecasting metric, and on one
backbone it degraded it. That outcome is the reason the present method ranks actions with a
local mean and a dispersion penalty and applies a threshold to select an action.
```

**中文直译**

早期配置尝试在阈值处理前，将估计效用向量投影到凸可行集，以改善动作排名。投影降低了估计向量平方误差，却未改善最终预测指标，并在一个骨干上造成退化。因此当前方法以局部均值和离散惩罚排序，再以阈值选择动作。

## 对照 272

```latex
Two consequences of that cycle carry into the present paper. The strongest simple selector
available at the time, which is R2-CART in the present terminology, was competitive with the
more elaborate candidate, and on one backbone better than it, which is why R2-CART is carried
forward as a mandatory control in every main-text table. Reducing estimation error on a
continuous score was also not sufficient to improve discrete selection, which is why the
conservative gate is evaluated directly on harmful intervention rate and harmful loss rather
than on MASE alone.
```

**中文直译**

该周期有两个影响延续至本文。当时最强简单选择器，即当前称为 R2-CART 的方法，与更复杂候选具有竞争力，在一个骨干上更好，因此成为正文各主表的必要对照。降低连续得分估计误差也不足以改善离散选择，因此保守门控直接通过有害干预率和伤害损失评价，不仅看 MASE。

## 对照 273

```latex
The measurements behind that decision come from a different protocol, with a smaller
development split, fewer sources, and different budget accounting, so they are not reproduced
here as numbers. They are recorded in the released artefact ledger and must not be compared
numerically with any table in this paper.
```

**中文直译**

该决策背后的测量来自不同协议，开发划分更小、数据源更少、预算核算不同，因此不在此重列数值。它们保留于发布产物台账，不能与本文各表进行数值比较。

## 对照 274

```latex
These statements describe the earlier development stage. The present revision includes
parent-aggregated retrieval, the additional evaluation in Appendix~\ref{app:confirmatory}
and the measured serving costs in Appendix~\ref{app:calls-measured}. Reduced-state retuning
remains outside the current fixed-configuration ablations.
```

**中文直译**

这些陈述描述早期开发阶段。当前版本包含父窗口聚合检索、附录 \ref{app:confirmatory} 的额外评价，以及附录 \ref{app:calls-measured} 的实测服务成本。精简状态重新调参仍不属于当前固定配置消融。

## 对照 275

```latex
\section{Supplementary Comparisons and Calibration}
```

**中文直译**

补充比较与校准

## 对照 276

```latex
\subsection{Full Related Work}
```

**中文直译**

完整相关工作

## 对照 277

```latex
\subsection{Incomplete Time-Series Modeling}
```

**中文直译**

不完整时间序列建模

## 对照 278

```latex
Imputation reconstructs unavailable values using temporal or cross-channel
structure~\citep{cao2018brits,tashiro2021csdi,yoon2018gain,wu2023timesnet,du2023saits,wang2025pswi,park2026t1}.
Missingness-aware forecasting instead incorporates the observation pattern into a trained
predictor~\citep{chen2024bitgraph,peng2025s4m,jang2026channeltokenformer}.
Task-oriented methods connect imputation to a downstream
objective~\citep{wang2024taskoriented,hao2025toivsf,hao2025gimcc,liang2025vida,xu2026srdi}.
Two distinctions locate the present setting against this work. On the input side, variable
subset forecasting removes entire variables at inference, whereas our requests contain gaps
inside the context. On the model side, missingness-aware forecasting requires control over
the predictor's training, whereas our predictor stays frozen. A trained imputer can therefore
supply a candidate repair here, while the decision layer determines whether that repair
should be used for the current request.
```

**中文直译**

插补利用时间或跨通道结构重建不可用值。缺失感知预测将观测模式纳入训练后的预测器。面向任务的方法将插补连接到下游目标。两点差异界定本文设置。在输入侧，变量子集预测在推理时移除整个变量，而本文请求在上下文内部包含缺口。在模型侧，缺失感知预测需要控制预测器训练，而本文保持预测器冻结。因此，训练后的插补器可以提供候选修复，决策层再决定当前请求是否应使用它。

## 对照 279

```latex
\subsection{Data-Side Adaptation for Frozen \tsfm{}s}
```

**中文直译**

冻结时间序列基础模型的数据侧适配

## 对照 280

```latex
TATO~\citep{qiu2026tato} shows that a frozen \tsfm{} can be adapted to heterogeneous domains
without parameter updates, by searching a transformation pipeline and selecting it from
historical task performance. Its unit of adaptation is a target domain: one pipeline serves
many requests. \introact{} makes a separate decision for each request over a fixed catalog,
using forecasting outcomes recorded for that backbone. TS-ICL~\citep{tsicl2026} is a
foundation model that natively supports imputation and partially observed look-back windows,
and it appears here only as the in-context regression backend of two catalog actions.
```

**中文直译**

TATO 表明，可以根据历史任务表现搜索并选择变换流程，在不更新参数的情况下适配冻结时间序列基础模型到异质领域。其适配单位是目标领域，一条流程服务多个请求。IntroAct-TS 在固定目录上为每个请求单独决策，使用该骨干记录的预测结果。TS-ICL 是原生支持插补和部分观测回看窗口的基础模型，本文仅将其作为两个目录动作的上下文回归后端。

## 对照 281

```latex
\subsection{Selective Decision Making}
```

**中文直译**

选择性决策

## 对照 282

```latex
Selective prediction trades coverage for lower
risk~\citep{chow1970optimum,vovk2005algorithmic,geifman2017selective,lei2018distribution},
and learning to defer routes a request to another decision
maker~\citep{madras2018predict,mozannar2020consistent}. \introact{} retains the same forecaster
for every request and selects whether to modify its input. Keeping the input still returns a
forecast. It is not a refusal to answer. This is a form of per-instance
algorithm selection~\citep{rice1976algorithm,xu2008satzilla}, supervised by the forecasting
utility of each repair. What makes that supervision available here is that a historical window
can be replayed under every admissible action, which gives full action feedback where
off-policy evaluation would observe the outcome of the logged action
alone~\citep{dudik2011doubly,swaminathan2015counterfactual}.
Appendix~\ref{app:ope-positioning} details the relationship. Section~\ref{sec:method}
defines the decision layer using these records.
```

**中文直译**

选择性预测以覆盖率换取较低风险，学习转交将请求路由给另一决策者。IntroAct-TS 为每个请求保留同一预测器，只选择是否修改输入。保持输入不变仍返回预测，并不是拒答。这是一种逐实例算法选择，以各修复的预测效用监督。历史窗口可以在每个可用动作下回放，从而提供全动作反馈，而离策略评价只能观测日志动作结果。附录 \ref{app:ope-positioning} 详述该关系，第 \ref{sec:method} 节用这些记录定义决策层。

## 对照 283

```latex
\subsection{Illustrative Requests}
```

**中文直译**

请求案例

## 对照 284

```latex
\caption{Two actual Bolt TEST requests with a tail gap and horizon 96. The upper request
favors KEEP, while the lower favors SAITS among the six catalog actions. For each winner we
selected the eligible request nearest the 75th percentile of its KEEP versus SAITS MASE
margin. The plot shows the final 128 context steps and the future target. Selection used
TEST outcomes only for this retrospective illustration. The exact episode IDs and selection
rule are recorded in \texttt{results/v55/case\_figure.json}.}
```

**中文直译**

两个真实 Bolt TEST 请求，均为尾部缺口、预测长度 96。六个目录动作中，上方请求偏好 KEEP，下方偏好 SAITS。对每个优胜动作，选择 KEEP 与 SAITS 的 MASE 差距最接近其第 75 百分位的合格请求。图中展示最后 128 个上下文步和未来目标。TEST 结果仅用于这一回顾性示例选择。确切样例标识和选择规则见 results/v55/case_figure.json。

## 对照 285

```latex
Two source-level diagnostics locate where this advantage comes from. The first asks whether
the gain comes from identifying which repair suits a source rather than which repair suits a
request. A source-level fixed policy applies, per source, the single action with the highest
mean realised utility on the replay bank, with \textsc{Keep} as the registered fallback where
that action is unsupported, all fixed on TRAIN. It reaches 1.360, 1.527 and 1.448 source-macro
MASE: better than the full rule on Bolt ($+0.0223$, $[+0.0044,+0.0432]$),
a $+0.0017$ difference on TimesFM whose interval includes zero, and numerically worse on
Chronos-2 ($-0.0834$, $[-0.1861,+0.0205]$). The aggregate values are 1.445 for Source Fixed
and 1.425 for \introact{}. The comparison supports a consistent advantage over leaving the
input unchanged, but not a consistent advantage over choosing one repair per source.
```

**中文直译**

两个数据源诊断定位优势来源。第一个检验收益是否来自识别适合数据源的修复，而非适合单个请求的修复。数据源级固定策略对每个源应用回放库平均已实现效用最高的单一动作，不支持时按登记规则回退到 KEEP，全部在 TRAIN 上固定。其数据源宏平均 MASE 为 1.360、1.527、1.448，在 Bolt 上优于完整规则，FULL 减该策略为 +0.0223，区间 [+0.0044,+0.0432]。TimesFM 差值为 +0.0017，区间含零。Chronos-2 数值较差，差值 −0.0834，区间 [−0.1861,+0.0205]。总体值为 Source Fixed 的 1.445 与 IntroAct-TS 的 1.425。比较支持相对于保持输入不变的一致优势，但不支持相对于每源选择单一修复的一致优势。

## 对照 286

```latex
Leaving out one source at a time preserves the margin over the unchanged input on every
seven-source subset of each backbone. The stronger comparisons are more concentrated: when
Exchange is omitted, the difference against Best Fixed changes from $-0.0454$ to $+0.0187$
on Bolt, from $-0.0502$ to $+0.0015$ on TimesFM, and from $-0.0915$ to $+0.0077$ on
Chronos-2. Thus the mean advantage over Best Fixed is not broad across sources, even though
the advantage over the unchanged input is. The complete sensitivity table is recorded
in the evaluation archive.
```

**中文直译**

每次移除一个源后，各骨干每个七源子集上相对于保持输入不变的差值仍保留。更强对照的比较更集中，排除 Exchange 后，相对于 Best Fixed 的差值在 Bolt 从 −0.0454 变为 +0.0187，在 TimesFM 从 −0.0502 变为 +0.0015，在 Chronos-2 从 −0.0915 变为 +0.0077。因此，尽管相对于保持输入不变的优势较广，相对于 Best Fixed 的平均优势并未广泛分布于数据源。完整敏感性表保留在评价档案中。

## 对照 287

```latex
The threshold itself can be set to a stated level of clipped harm. Calibrating it on the
internal evaluation block and applying it unchanged to TEST respects the stated target in
all four Chronos-2 cells, but only at $\alpha=0.05$ on Bolt and TimesFM. At $\alpha=0.01$,
realised clipped harm is 0.0165 and 0.0260, respectively. The conformal guarantee requires
exchangeability between calibration and future requests. These temporal blocks do not
establish it. A retrospective cross-fit within TEST reaches the target in eight of twelve
cells, but uses labels from other TEST parents and is not a prospective guarantee. On
Chronos-2 the internally calibrated $\alpha=0.01$ rule repairs $4.7\%$ of TEST requests and
the $\alpha=0.05$ rule repairs $36.2\%$, illustrating the operating curve. The main
\introact{} row uses a zero threshold. These calibrated rows are secondary analyses.
```

**中文直译**

阈值可设为指定的截断伤害水平。在内部评价块校准后原样用于 TEST，Chronos-2 的四个单元均满足目标，Bolt 和 TimesFM 仅 α=0.05 时满足。α=0.01 时，后二者实际截断伤害分别为 0.0165、0.0260。保形保证要求校准与未来请求可交换，这些时间块未确立该条件。TEST 内回顾性交叉拟合在十二个单元中的八个满足目标，但使用其他 TEST 父窗口的标签，不是前瞻性保证。Chronos-2 上内部校准的 α=0.01 规则修复 4.7% TEST 请求，α=0.05 修复 36.2%，展示工作曲线。主 IntroAct-TS 行阈值为零，校准行属于次要分析。

## 对照 288

```latex
\caption{Retrospective TEST cross-fit of the execution threshold: each half of the parents
supplies completed-request labels to calibrate the other half. These rows are not an
independent prospective test. Target is clipped harmful loss, realised is the empirical
clipped value, and repair rate is the executed share.}
```

**中文直译**

执行阈值的回顾性 TEST 交叉拟合。每半父窗口提供已完成请求标签，校准另一半。这些行不是独立前瞻测试。Target 为截断伤害损失目标，realised 为经验截断值，repair rate 为执行比例。

### 共用数值表 50

```latex
\adjustbox{max width=\textwidth}{\begin{tabular}{lcccccccccccc}
    \toprule
    & \multicolumn{4}{c}{Bolt} & \multicolumn{4}{c}{TimesFM} & \multicolumn{4}{c}{Chronos-2} \\
    \cmidrule(lr){2-5}\cmidrule(lr){6-9}\cmidrule(lr){10-13}
    Target $\alpha$ & 0.01 & 0.02 & 0.03 & 0.05 & 0.01 & 0.02 & 0.03 & 0.05 & 0.01 & 0.02 & 0.03 & 0.05 \\
    \midrule
    Realised harm & 0.009 & 0.020 & 0.028 & 0.031 & 0.016 & 0.024 & 0.026 & 0.038 & 0.010 & 0.016 & 0.025 & 0.025 \\
    Repair rate & 5.5\% & 16.7\% & 28.7\% & 36.4\% & 23.2\% & 44.3\% & 58.4\% & 92.4\% & 8.0\% & 17.6\% & 36.1\% & 36.2\% \\
    MASE & 1.471 & 1.400 & 1.391 & 1.383 & 1.605 & 1.582 & 1.565 & 1.529 & 1.428 & 1.375 & 1.365 & 1.365 \\
    \bottomrule
  \end{tabular}}
```

**中文表内文字**

本表为数值结果表，表头、动作名与变体名按文首词汇对应表读取，全部数值、公式、排序标记及分组原样保留。对应图表说明的中文直译紧邻本表。

## 对照 289

```latex
The threshold $\tau$ sets the execution operating point. The primary accuracy comparison
uses $\tau=0$. We also calibrate higher thresholds to stated harm tolerances on a separate
training-side block. Define the harm of a served request as the
forecasting error the executed repair added, which is $\max(0, -g_{a^{\star}})$ capped at a
registered bound $B$, and zero whenever the rule keeps the input. Raising $\tau$ can only
withdraw an execution, so the average harm is monotone in $\tau$ and conformal risk
control applies~\citep{angelopoulos2024conformal}. Given a tolerated
level $\alpha$ and $n$ calibration requests, the rule takes
```

**中文直译**

阈值 τ 决定执行工作点。主要精度比较使用 τ=0。我们还在独立训练侧数据块上，为指定伤害容忍度校准更高阈值。服务请求的伤害定义为执行修复增加的预测误差，即 max(0,−gₐ*) 并截断于登记上界 B，保持输入时为零。提高 τ 只会撤销执行，因此平均伤害关于 τ 单调，可以应用保形风险控制。给定容忍水平 α 和 n 个校准请求，规则如下。

**共用公式**

```latex
\begin{equation}
  \hat\tau(\alpha) \;=\; \inf\left\{ \tau \;:\;
    \frac{n\, \hat{R}_n(\tau) + B}{n+1} \;\le\; \alpha \right\},
  \qquad
  \hat{R}_n(\tau) \;=\; \frac{1}{n}\sum_{i=1}^{n} \min\!\left(B,\, \max(0, -g_{i,a^{\star}(\tau)})\right),
  \label{eq:crc}
\end{equation}
```

## 对照 290

```latex
which bounds expected clipped harm for an exchangeable further request by $\alpha$ under
the conformal risk control assumptions. The calibration block does not participate in
selecting $k$, $\beta$ or $\lambda$. Time ordered forecasting requests need not satisfy
exchangeability, and clipping leaves harm above $B$ outside the bound. We therefore report
both clipped and unbounded realised harm on TEST in \S\ref{sec:exp-harm}. If no finite
threshold meets a tolerance, the rule uses $\tau=\infty$ and keeps every input.
```

**中文直译**

在保形风险控制假设下，该规则使可交换后续请求的期望截断伤害不超过 α。校准块不参与 k、β、λ 的选择。按时间排序的预测请求未必满足可交换性，超过 B 的伤害也不在截断界限内。因此，第 \ref{sec:exp-harm} 节同时报告 TEST 上截断和未截断的实际伤害。若没有有限阈值满足容忍度，规则采用 τ=∞，保持每个输入不变。

## 对照 291

```latex
\subsection{Selection, Sensitivity, and Cost Details}
```

**中文直译**

选择、敏感性与成本细节

## 对照 292

```latex
The three hyperparameters are selected once per backbone on the replay bank by
leave-one-parent-out cross-validation, so every bank episode is scored against a bank with all
records of its own parent removed. A parent is a non-overlapping origin window from which the
episodes are generated. Appendix~\ref{app:splits} gives the tiling rule. The grid is
$k \in \{8,16,32,64,128,256\}$, $\beta \in \{0,0.5,1,1.64\}$ and
$\lambda \in \{0,4,16,64,\infty\}$. The cap is the bank's conditional harmful rate for
the fixed repair with the highest mean utility. A configuration is admissible when its
leave-one-parent-out harmful rate does not exceed this cap. We find the admissible
configuration with the lowest source-macro MASE, then apply the one standard error rule:
among configurations whose paired difference from that minimum is within its estimated
standard error, we choose the one that intervenes least. If none is admissible, the entire
selector returns \textsc{Keep}. The anchor, cap, selected configuration and any fallback
are saved with each run.
```

**中文直译**

每个骨干在回放库上通过留一父窗口交叉验证选择一次三个超参数，因此每个库内样例评分时，都从库中移除其父窗口的所有记录。父窗口是不重叠的起点窗口，由其生成样例。附录 \ref{app:splits} 给出平铺规则。网格为 k∈{8,16,32,64,128,256}，β∈{0,0.5,1,1.64}，λ∈{0,4,16,64,∞}。上限取回放库平均效用最高的固定修复的条件伤害率。留一父窗口伤害率不超过上限的配置可用。先找数据源宏平均 MASE 最低的可用配置，再采用一个标准误规则，在与该最小值的配对差位于估计标准误内的配置中，选择干预最少者。若无可用配置，整个选择器返回 KEEP。每次运行保存基准、上限、选定配置与回退情况。

## 对照 293

```latex
Repair frequency rises from $55.2\%$ to $64.0\%$ and $71.9\%$ as missingness increases.
At the higher severities, Source Fixed has lower aggregate MASE than the full rule.
These observations identify a limitation of the selected operating point, but they do not
show that more requests require repair or isolate why the relative performance changes.
Recalibrating for heavier missingness would require a separate evaluation.
```

**中文直译**

随缺失增加，修复频率从 55.2% 升至 64.0% 和 71.9%。较高严重度下，Source Fixed 总体 MASE 低于完整规则。这些观测识别了所选工作点的限制，但不能说明更多请求需要修复，也不能分离相对表现变化的原因。针对更重缺失重新校准需要独立评价。

## 对照 294

```latex
Two further checks vary the evidence the rule stands on rather than the requests it serves.
Subsampling the replay bank by parent measures how much history the pooled estimate needs, and
regenerating the masks of the same parents under two further seeds measures how much the
result owes to one mask realisation. Source-macro error is 1.425, 1.409 and 1.427 across
the three seeds against 1.576, 1.570 and 1.577 for the unchanged input.
Both reuse the same sources and parent sets, so they bound sensitivity and do not extend the
scope. Appendices~\ref{app:severity-full}, \ref{app:pattern}, \ref{app:replaysize} and
\ref{app:seeds} report the complete breakdowns.
```

**中文直译**

另外两项检查改变规则依据的证据，而不改变所服务请求。按父窗口对子采样回放库，测量汇聚估计需要多少历史。用另两个种子重建同一父窗口掩码，衡量结果对特定掩码的依赖。三个种子的数据源宏平均误差为 1.425、1.409、1.427，保持输入不变为 1.576、1.570、1.577。二者均复用相同源和父窗口集，因此限定敏感性，不扩展适用范围。附录 \ref{app:severity-full}、\ref{app:pattern}、\ref{app:replaysize}、\ref{app:seeds} 给出完整细分。

## 参考文献原始条目

```bibtex
% ===========================================================================
% IntroAct-TS / ICLR 2027 —— 全项目唯一参考文献文件
% ---------------------------------------------------------------------------
% 约定（见 latex/README.md）：
%   1. 全项目只维护这一个 .bib，所有版本（v4.4、v4.5 ...）的 .tex 共用它。
%   2. 只增量追加，不因某版论文不引用就删除条目；被引用的条目由 bibtex 自动筛选。
%   3. 每条都要有可核验来源（DOI / arXiv / OpenReview / 官方仓库 URL）。
%      无法核实作者全名的条目一律写 `and others`，绝不编造作者或页码。
%   4. 预印本用 misc 或 article + note 标注版本日期，不冒充已正式发表。
%      注意：本文件是给 bibtex 读的，注释里不要出现 at 符号开头的词，否则会被当成新条目。
% ===========================================================================

% ---------------------------------------------------------------- 正式 baseline
@inproceedings{cao2018brits,
  title        = {{BRITS}: Bidirectional Recurrent Imputation for Time Series},
  author       = {Cao, Wei and Wang, Dong and Li, Jian and Zhou, Hao and Li, Lei and Li, Yitan},
  booktitle    = {Advances in Neural Information Processing Systems},
  year         = {2018},
  url          = {https://proceedings.neurips.cc/paper_files/paper/2018/hash/734e6bfcd358e25ac1db0a4241b95651-Abstract.html}
}

@inproceedings{tashiro2021csdi,
  title        = {{CSDI}: Conditional Score-based Diffusion Models for Probabilistic Time Series Imputation},
  author       = {Tashiro, Yusuke and Song, Jiaming and Song, Yang and Ermon, Stefano},
  booktitle    = {Advances in Neural Information Processing Systems},
  year         = {2021},
  url          = {https://arxiv.org/abs/2107.03502}
}

% BiTGraph —— ICLR 2024。直接研究缺失值下的多变量预测，并讨论先插补再预测的误差累积。
@inproceedings{chen2024bitgraph,
  title        = {Biased Temporal Convolution Graph Network for Time Series Forecasting with Missing Values},
  author       = {Chen, Xiaodan and Li, Xiucheng and Liu, Bo and Li, Zhijun},
  booktitle    = {International Conference on Learning Representations},
  year         = {2024},
  url          = {https://openreview.net/forum?id=O9nZCwdGcG}
}

% S4M —— ICLR 2025。把缺失模式直接整合进预测模型，面向 block missing。
@inproceedings{peng2025s4m,
  title        = {{S4M}: S4 for Multivariate Time Series Forecasting with Missing Values},
  author       = {Peng, Jing and Yang, Meiqi and Zhang, Qiong and Li, Xiaoxiao},
  booktitle    = {International Conference on Learning Representations},
  year         = {2025},
  url          = {https://proceedings.iclr.cc/paper_files/paper/2025/hash/7b2f0758334389b8ad0665a9bd165463-Abstract-Conference.html}
}

% TOI —— 正文五个核心同定位 baseline 之一。作者列表取自 arXiv:2410.06652（NeurIPS 2024）。
@inproceedings{wang2024taskoriented,
  title        = {Task-oriented Time Series Imputation Evaluation via Generalized Representers},
  author       = {Wang, Zhixian and Yang, Linxiao and Sun, Liang and Wen, Qingsong and Wang, Yi},
  booktitle    = {Advances in Neural Information Processing Systems},
  year         = {2024},
  url          = {https://arxiv.org/abs/2410.06652}
}

% TOI-VSF —— 期刊版为 IEEE TKDE 37(11):6464-6477, 2025。作者取自 arXiv:2411.09928。
@article{hao2025toivsf,
  title        = {Is Precise Recovery Necessary? A Task-Oriented Imputation Approach for Time Series Forecasting on Variable Subset},
  author       = {Hao, Qi and Liang, Runchang and Gao, Yue and Dong, Hao and Fan, Wei and Jiang, Lu and Wang, Pengyang},
  journal      = {IEEE Transactions on Knowledge and Data Engineering},
  volume       = {37},
  number       = {11},
  pages        = {6464--6477},
  year         = {2025},
  doi          = {10.1109/TKDE.2025.3594032},
  url          = {https://arxiv.org/abs/2411.09928}
}

% GIMCC —— KDD 2025。作者与 DOI 经 Semantic Scholar（DBLP key conf/kdd/00010L0W25）核验。
@inproceedings{hao2025gimcc,
  title        = {Generative Imputation with Multi-level Causal Consistency for Variable Subset Forecasting},
  author       = {Hao, Qi and Gao, Yue and Liang, Runchang and Zhang, Yunhe and Wang, Pengyang},
  booktitle    = {Proceedings of the 31st ACM SIGKDD Conference on Knowledge Discovery and Data Mining},
  year         = {2025},
  doi          = {10.1145/3711896.3736980},
  pages        = {838--849}
}

% SRDI —— WWW 2026, pages 7366-7377。作者经 researchr（key XuHZZQJWZW26）核验。
@inproceedings{xu2026srdi,
  title        = {Shift-Resilient Diffusive Imputation for Variable Subset Forecasting},
  author       = {Xu, Haihua and Hao, Qi and Zhang, He and Zhao, Jianpeng and Qiao, Ziyue and Jiang, Lu and Wang, Pengfei and Zhou, Yingjie and Wang, Pengyang},
  booktitle    = {Proceedings of the ACM Web Conference 2026},
  pages        = {7366--7377},
  year         = {2026},
  doi          = {10.1145/3774904.3792511}
}

% ChannelTokenFormer —— ICLR 2026（arXiv:2506.08660 的 comments 字段确认接收）。
@inproceedings{jang2026channeltokenformer,
  title        = {Towards Robust Real-World Multivariate Time Series Forecasting: A Unified Framework for Dependency, Asynchrony, and Missingness},
  author       = {Jang, Jinkwan and Park, Hyungjin and Choi, Jinmyeong and Kim, Taesup},
  booktitle    = {International Conference on Learning Representations},
  year         = {2026},
  url          = {https://arxiv.org/abs/2506.08660}
}

% VIDA —— KDD 2025。作者与 DOI 经 Semantic Scholar（DBLP key conf/kdd/Liang0000WY25）核验。
% 仅用于 Related Work 与附录扩展比较，不进正文五个核心 baseline 集合。
@inproceedings{liang2025vida,
  title        = {Imputation via Domain Adaptation: Rethinking Variable Subset Forecasting from Knowledge Transfer},
  author       = {Liang, Runchang and Hao, Qi and Gao, Yue and Liu, Kunpeng and Jiang, Lu and Wang, Pengyang and Yin, Minghao},
  booktitle    = {Proceedings of the 31st ACM SIGKDD Conference on Knowledge Discovery and Data Mining},
  year         = {2025},
  doi          = {10.1145/3711896.3737007},
  pages        = {1683--1694}
}

@inproceedings{park2026t1,
  title        = {{T1}: One-to-One Channel-Head Binding for Multivariate Time-Series Imputation},
  author       = {Park, Dongik and Ryu, Hyunwoo and Bae, Suahn and Park, Keondo and Kim, Hyung-Sin},
  booktitle    = {International Conference on Learning Representations},
  year         = {2026},
  url          = {https://openreview.net/forum?id=IAnIlFsPEW}
}

@inproceedings{qiu2026tato,
  title        = {Adapt Data to Model: Adaptive Transformation Optimization for Domain-shared Time Series Foundation Models},
  author       = {Qiu, Yunzhong and Cen, Zhiyao and Pei, Zhongyi and Wang, Chen and Wang, Jianmin},
  booktitle    = {International Conference on Learning Representations},
  year         = {2026},
  url          = {https://openreview.net/forum?id=uTK1SNgi1N}
}

% ------------------------------------------------------------------- 基础模型
@article{ansari2024chronos,
  title        = {Chronos: Learning the Language of Time Series},
  author       = {Ansari, Abdul Fatir and Stella, Lorenzo and Turkmen, Caner and Zhang, Xiyuan and Mercado, Pedro and Shen, Huibin and Shchur, Oleksandr and Rangapuram, Syama Sundar and Pineda Arango, Sebastian and Kapoor, Shubham and Zschiegner, Jasper and Maddix, Danielle C. and Wang, Hao and Mahoney, Michael W. and Torkkola, Kari and Wilson, Andrew Gordon and Bohlke-Schneider, Michael and Wang, Yuyang},
  journal      = {Transactions on Machine Learning Research},
  year         = {2024},
  url          = {https://openreview.net/forum?id=gerNCVqqtR}
}

@misc{chronosbolt2025,
  title        = {Fast and Accurate Zero-Shot Forecasting with {Chronos-Bolt} and {AutoGluon}},
  author       = {Ansari, Abdul Fatir and Turkmen, Caner and Shchur, Oleksandr and Stella, Lorenzo},
  year         = {2024},
  howpublished = {AWS Machine Learning Blog},
  note         = {Model release announcement, December 2},
  url          = {https://aws.amazon.com/blogs/machine-learning/fast-and-accurate-zero-shot-forecasting-with-chronos-bolt-and-autogluon/}
}

@inproceedings{das2024timesfm,
  title        = {A Decoder-only Foundation Model for Time-series Forecasting},
  author       = {Das, Abhimanyu and Kong, Weihao and Sen, Rajat and Zhou, Yichen},
  booktitle    = {International Conference on Machine Learning},
  year         = {2024},
  url          = {https://proceedings.mlr.press/v235/das24c.html},
  pages        = {10148--10167},
  volume       = {235},
  series       = {Proceedings of Machine Learning Research}
}

@misc{chronos2_2025,
  title        = {{Chronos-2}: From Univariate to Universal Forecasting},
  author       = {Ansari, Abdul Fatir and Shchur, Oleksandr and K{\"u}ken, Jaris and Auer, Andreas and Han, Boran and Mercado, Pedro and Rangapuram, Syama Sundar and Shen, Huibin and Stella, Lorenzo and Zhang, Xiyuan and Goswami, Mononito and Kapoor, Shubham and Maddix, Danielle C. and Guerron, Pablo and Hu, Tony and Yin, Junming and Erickson, Nick and Desai, Prateek Mutalik and Wang, Hao and Rangwala, Huzefa and Karypis, George and Wang, Yuyang and Bohlke-Schneider, Michael},
  year         = {2025},
  howpublished = {arXiv preprint arXiv:2510.15821},
  url          = {https://arxiv.org/abs/2510.15821}
}

@inproceedings{woo2024moirai,
  title        = {Unified Training of Universal Time Series Forecasting Transformers},
  author       = {Woo, Gerald and Liu, Chenghao and Kumar, Akshat and Xiong, Caiming and Savarese, Silvio and Sahoo, Doyen},
  booktitle    = {International Conference on Machine Learning},
  year         = {2024},
  url          = {https://proceedings.mlr.press/v235/woo24a.html},
  pages        = {53140--53164},
  volume       = {235},
  series       = {Proceedings of Machine Learning Research}
}

@article{rasul2023lagllama,
  title   = {Lag-Llama: Towards Foundation Models for Probabilistic Time Series Forecasting},
  author  = {Rasul, Kashif and Ashok, Arjun and Williams, Andrew Robert and Ghonia, Hena and Bhagwatkar, Rishika and others},
  journal = {arXiv preprint arXiv:2310.08278},
  year    = {2023}
}

@misc{tsicl2026,
  title        = {{TS-ICL}: A Flexible Time-Indexed Foundation Model for Time Series via In-Context Learning},
  author       = {Le Naour, Etienne and Nabil, Tahar and Petralia, Adrien},
  year         = {2026},
  howpublished = {arXiv preprint arXiv:2606.05878},
  url          = {https://arxiv.org/abs/2606.05878}
}

% ------------------------------------------------------------- 相关插补 / 预测
@inproceedings{yoon2018gain,
  title        = {{GAIN}: Missing Data Imputation using Generative Adversarial Nets},
  author       = {Yoon, Jinsung and Jordon, James and van der Schaar, Mihaela},
  booktitle    = {International Conference on Machine Learning},
  year         = {2018},
  url          = {https://proceedings.mlr.press/v80/yoon18a.html},
  pages        = {5689--5698},
  volume       = {80},
  series       = {Proceedings of Machine Learning Research}
}

@article{du2023saits,
  title        = {{SAITS}: Self-attention-based imputation for time series},
  author       = {Du, Wenjie and C{\^o}t{\'e}, David and Liu, Yan},
  journal      = {Expert Systems with Applications},
  volume       = {219},
  pages        = {119619},
  year         = {2023},
  doi          = {10.1016/j.eswa.2023.119619}
}

@inproceedings{wu2023timesnet,
  title        = {{TimesNet}: Temporal 2{D}-variation modeling for general time series analysis},
  author       = {Wu, Haixu and Xu, Jiehui and Wang, Jianmin and Long, Mingsheng},
  booktitle    = {International Conference on Learning Representations},
  year         = {2023},
  url          = {https://openreview.net/forum?id=ju_Uqw384Oq}
}

@inproceedings{wang2025pswi,
  title        = {Optimal Transport for Time Series Imputation},
  author       = {Wang, Hao and Li, Zhengnan and Li, Haoxuan and Chen, Xu and Gong, Mingming and Chen, Bin and Chen, Zhichao},
  booktitle    = {International Conference on Learning Representations},
  year         = {2025},
  url          = {https://openreview.net/forum?id=xPTzjpIQNp}
}

@inproceedings{zhou2021informer,
  title     = {Informer: Beyond Efficient Transformer for Long Sequence Time-Series Forecasting},
  author    = {Zhou, Haoyi and Zhang, Shanghang and Peng, Jieqi and Zhang, Shuai and Li, Jianxin and Xiong, Hui and Zhang, Wancai},
  booktitle = {AAAI Conference on Artificial Intelligence},
  year      = {2021}
}

@inproceedings{wu2021autoformer,
  title     = {Autoformer: Decomposition Transformers with Auto-Correlation for Long-Term Series Forecasting},
  author    = {Wu, Haixu and Xu, Jiehui and Wang, Jianmin and Long, Mingsheng},
  booktitle = {Advances in Neural Information Processing Systems},
  year      = {2021}
}

@inproceedings{nie2023patchtst,
  title     = {A Time Series is Worth 64 Words: Long-term Forecasting with Transformers},
  author    = {Nie, Yuqi and Nguyen, Nam H. and Sinthong, Phanwadee and Kalagnanam, Jayant},
  booktitle = {International Conference on Learning Representations},
  year      = {2023}
}

@inproceedings{liu2024itransformer,
  title     = {{iTransformer}: Inverted Transformers Are Effective for Time Series Forecasting},
  author    = {Liu, Yong and Hu, Tengge and Zhang, Haoran and Wu, Haixu and Wang, Shiyu and Ma, Lintao and Long, Mingsheng},
  booktitle = {International Conference on Learning Representations},
  year      = {2024}
}

@inproceedings{lai2018lstnet,
  title     = {Modeling Long- and Short-Term Temporal Patterns with Deep Neural Networks},
  author    = {Lai, Guokun and Chang, Wei-Cheng and Yang, Yiming and Liu, Hanxiao},
  booktitle = {ACM SIGIR Conference on Research and Development in Information Retrieval},
  year      = {2018}
}

@misc{uci_electricity,
  title        = {{ElectricityLoadDiagrams20112014} Data Set},
  author       = {{UCI Machine Learning Repository}},
  howpublished = {\url{https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014}},
  year         = {2015}
}

@misc{pems,
  title        = {{PeMS}: Caltrans Performance Measurement System},
  author       = {{California Department of Transportation}},
  howpublished = {\url{https://pems.dot.ca.gov/}},
  year         = {2024}
}

% ------------------------------------------------------- 选择性预测 / 弃权
@article{chow1970optimum,
  title        = {On Optimum Recognition Error and Reject Tradeoff},
  author       = {Chow, C. K.},
  journal      = {IEEE Transactions on Information Theory},
  volume       = {16},
  number       = {1},
  pages        = {41--46},
  year         = {1970},
  doi          = {10.1109/TIT.1970.1054406}
}

@inproceedings{geifman2017selective,
  title        = {Selective Classification for Deep Neural Networks},
  author       = {Geifman, Yonatan and El-Yaniv, Ran},
  booktitle    = {Advances in Neural Information Processing Systems},
  year         = {2017},
  url          = {https://proceedings.neurips.cc/paper_files/paper/7073-selective-classification-for-deep-neural-networks}
}

@book{vovk2005algorithmic,
  title        = {Algorithmic Learning in a Random World},
  author       = {Vovk, Vladimir and Gammerman, Alexander and Shafer, Glenn},
  publisher    = {Springer},
  year         = {2005},
  url          = {https://link.springer.com/book/10.1007/b106715}
}

@article{lei2018distribution,
  title        = {Distribution-Free Predictive Inference for Regression},
  author       = {Lei, Jing and G'Sell, Max and Rinaldo, Alessandro and Tibshirani, Ryan J. and Wasserman, Larry},
  journal      = {Journal of the American Statistical Association},
  volume       = {113},
  number       = {523},
  pages        = {1094--1111},
  year         = {2018},
  doi          = {10.1080/01621459.2017.1307116}
}

% ------------------------------------------------- 动态特征选择（相关，仅作边界说明）
@inproceedings{he2024dime,
  title        = {Estimating Conditional Mutual Information for Dynamic Feature Selection},
  author       = {Gadgil, Soham and Covert, Ian and Lee, Su-In},
  booktitle    = {International Conference on Learning Representations},
  year         = {2024},
  url          = {https://openreview.net/forum?id=Oju2Qu9jvn}
}

% --------------------------------------------------------- 方法学 / 统计工具
@article{hyndman2006mase,
  title        = {Another Look at Measures of Forecast Accuracy},
  author       = {Hyndman, Rob J. and Koehler, Anne B.},
  journal      = {International Journal of Forecasting},
  volume       = {22},
  number       = {4},
  pages        = {679--688},
  year         = {2006},
  doi          = {10.1016/j.ijforecast.2006.03.001}
}

@book{breiman1984cart,
  title     = {Classification and Regression Trees},
  author    = {Breiman, Leo and Friedman, Jerome H. and Olshen, Richard A. and Stone, Charles J.},
  publisher = {Wadsworth},
  year      = {1984}
}

@book{boyd2004convex,
  title     = {Convex Optimization},
  author    = {Boyd, Stephen and Vandenberghe, Lieven},
  publisher = {Cambridge University Press},
  year      = {2004}
}

@inproceedings{jaggi2013revisiting,
  title     = {Revisiting Frank-Wolfe: Projection-Free Sparse Convex Optimization},
  author    = {Jaggi, Martin},
  booktitle = {International Conference on Machine Learning},
  year    = {2013}
}

@article{cameron2008bootstrap,
  title   = {Bootstrap-Based Improvements for Inference with Clustered Errors},
  author  = {Cameron, A. Colin and Gelbach, Jonah B. and Miller, Douglas L.},
  journal = {Review of Economics and Statistics},
  volume  = {90},
  number  = {3},
  pages   = {414--427},
  year    = {2008}
}

@article{holm1979simple,
  title        = {A Simple Sequentially Rejective Multiple Test Procedure},
  author       = {Holm, Sture},
  journal      = {Scandinavian Journal of Statistics},
  volume       = {6},
  number       = {2},
  pages        = {65--70},
  year         = {1979},
  url          = {https://www.jstor.org/stable/4615733}
}

@article{spearman1904proof,
  title   = {The Proof and Measurement of Association between Two Things},
  author  = {Spearman, C.},
  journal = {American Journal of Psychology},
  volume  = {15},
  number  = {1},
  pages   = {72--101},
  year    = {1904}
}

@book{hyndman2021forecasting,
  title     = {Forecasting: Principles and Practice},
  author    = {Hyndman, Rob J. and Athanasopoulos, George},
  edition   = {3},
  publisher = {OTexts},
  year      = {2021}
}

% ---------------------------------------------------------------------------
% 策略选择 / 离策略评估 / 选择性预测 这条线（用于与 contextual bandit 切割）
% 注意：注释里不要出现以 at 符号开头的词，否则 bibtex 会误当成新条目。
% ---------------------------------------------------------------------------

@inproceedings{dudik2011doubly,
  title        = {Doubly Robust Policy Evaluation and Learning},
  author       = {Dud{\'i}k, Miroslav and Langford, John and Li, Lihong},
  booktitle    = {Proceedings of the 28th International Conference on Machine Learning},
  year         = {2011},
  url          = {https://dblp.org/rec/conf/icml/DudikLL11}
}

@inproceedings{swaminathan2015counterfactual,
  title        = {Counterfactual Risk Minimization: Learning from Logged Bandit Feedback},
  author       = {Swaminathan, Adith and Joachims, Thorsten},
  volume       = {37},
  pages        = {814--823},
  year         = {2015},
  booktitle    = {Proceedings of the 32nd International Conference on Machine Learning},
  series       = {Proceedings of Machine Learning Research},
  url          = {https://proceedings.mlr.press/v37/swaminathan15.html}
}

@inproceedings{strehl2010learning,
  title        = {Learning from Logged Implicit Exploration Data},
  author       = {Strehl, Alex and Langford, John and Li, Lihong and Kakade, Sham M.},
  booktitle    = {Advances in Neural Information Processing Systems},
  year         = {2010},
  url          = {https://proceedings.neurips.cc/paper_files/paper/3977-learning-from-logged-implicit-exploration-data}
}

@inproceedings{jiang2016doubly,
  title        = {Doubly Robust Off-policy Value Evaluation for Reinforcement Learning},
  author       = {Jiang, Nan and Li, Lihong},
  booktitle    = {Proceedings of the 33rd International Conference on Machine Learning},
  year         = {2016},
  url          = {https://proceedings.mlr.press/v48/jiang16.html}
}

@inproceedings{thomas2016data,
  title        = {Data-Efficient Off-Policy Policy Evaluation for Reinforcement Learning},
  author       = {Thomas, Philip S. and Brunskill, Emma},
  booktitle    = {Proceedings of the 33rd International Conference on Machine Learning},
  year         = {2016},
  url          = {https://proceedings.mlr.press/v48/thomasa16.html}
}

@inproceedings{abbasiyadkori2011improved,
  title        = {Improved Algorithms for Linear Stochastic Bandits},
  author       = {Abbasi-Yadkori, Yasin and P{\'a}l, D{\'a}vid and Szepesv{\'a}ri, Csaba},
  booktitle    = {Advances in Neural Information Processing Systems},
  year         = {2011},
  url          = {https://proceedings.neurips.cc/paper_files/paper/4417-improved-algorithms-for-linear-stochastic-bandits}
}

@book{lattimore2020bandit,
  title        = {Bandit Algorithms},
  author       = {Lattimore, Tor and Szepesv{\'a}ri, Csaba},
  publisher    = {Cambridge University Press},
  year         = {2020},
  url          = {https://www.cambridge.org/core/books/bandit-algorithms/8E39FD004E6CE036680F90DD0C6F09FC}
}

@inproceedings{mozannar2020consistent,
  title        = {Consistent Estimators for Learning to Defer to an Expert},
  author       = {Mozannar, Hussein and Sontag, David},
  booktitle    = {Proceedings of the 37th International Conference on Machine Learning},
  year         = {2020},
  url          = {https://proceedings.mlr.press/v119/mozannar20b.html}
}

@inproceedings{madras2018predict,
  title        = {Predict Responsibly: Improving Fairness and Accuracy by Learning to Defer},
  author       = {Madras, David and Pitassi, Toniann and Zemel, Richard},
  booktitle    = {Advances in Neural Information Processing Systems},
  year         = {2018},
  url          = {https://proceedings.neurips.cc/paper/2018/hash/09d37c08f7b129e96277388757530c72-Abstract.html}
}

@inproceedings{krishnan2016activeclean,
  title     = {ActiveClean: Interactive Data Cleaning for Statistical Modeling},
  author    = {Krishnan, Sanjay and Wang, Jiannan and Franklin, Michael J. and Goldberg, Ken and Kraska, Tim},
  booktitle = {Proceedings of the VLDB Endowment},
  volume    = {9},
  number    = {12},
  pages     = {948--959},
  year      = {2016}
}

@book{little2019statistical,
  title     = {Statistical Analysis with Missing Data},
  author    = {Little, Roderick J. A. and Rubin, Donald B.},
  edition   = {3},
  publisher = {Wiley},
  year      = {2019}
}

@book{vanbuuren2018flexible,
  title     = {Flexible Imputation of Missing Data},
  author    = {van Buuren, Stef},
  edition   = {2},
  publisher = {Chapman and Hall/CRC},
  year      = {2018}
}

% PyPOTS —— SAITS 的官方工具箱，主表 reconstruction baseline 由它提供实现。
@article{du2023pypots,
  title        = {{PyPOTS}: A Python Toolbox for Data Mining on Partially-Observed Time Series},
  author       = {Du, Wenjie},
  journal      = {arXiv preprint arXiv:2305.18811},
  year         = {2023},
  url          = {https://arxiv.org/abs/2305.18811}
}

% Conformal risk control: the framework the execution threshold is calibrated in.
@inproceedings{angelopoulos2024conformal,
  title        = {Conformal Risk Control},
  author       = {Angelopoulos, Anastasios N. and Bates, Stephen and Fisch, Adam and Lei, Lihua and Schuster, Tal},
  booktitle    = {International Conference on Learning Representations},
  year         = {2024},
  url          = {https://arxiv.org/abs/2208.02814}
}

@article{rice1976algorithm,
  title        = {The Algorithm Selection Problem},
  author       = {Rice, John R.},
  journal      = {Advances in Computers},
  volume       = {15},
  pages        = {65--118},
  year         = {1976},
  doi          = {10.1016/S0065-2458(08)60520-3}
}

@article{xu2008satzilla,
  title        = {{SATzilla}: Portfolio-Based Algorithm Selection for {SAT}},
  author       = {Xu, Lin and Hutter, Frank and Hoos, Holger H. and Leyton-Brown, Kevin},
  journal      = {Journal of Artificial Intelligence Research},
  volume       = {32},
  pages        = {565--606},
  year         = {2008},
  doi          = {10.1613/jair.2490}
}

```
