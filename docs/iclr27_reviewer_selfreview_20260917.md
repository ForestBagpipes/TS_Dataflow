# ICLR 2027 自审稿：IntroAct-TS v4.4 LaTeX 稿

审稿日期：2026-09-17
审稿对象：`latex/introact_ts_iclr27_v44.tex`（20 页；正文 9 页 + 参考文献 1 页 + 附录 9 页）
审稿视角：ICLR 2027 匿名审稿人，按会议评审表打分

> **前置声明（必须放在最前，否则下面的分数没有意义）**
> 本稿目前**没有任何实验数字**：767 处全部是 `\ph{KEY}` 占位符。
> 因此下面这份评审是"**结构、论证、写作**"层面的评审，不是"结果"层面的评审。
> 真实投稿时，一个没有数字的稿子会被直接拒掉，所以下面第一节
> 就是"当前状态离可投稿还差什么"。

---

## 0. 一句话结论

**论证骨架和 claim 边界控制是这篇稿子最强的部分；致命短板只有一个——
没有结果。** 除此之外，最大的两个风险是
(1) "counterfactual" 这个词用得有争议，
(2) 方法层的新颖性没有和 contextual bandit / off-policy evaluation 这条线做切割。
这两点如果不处理，即使数字很好看，也会被一个熟悉 bandit 文献的审稿人打低分。

---

## 1. 当前状态与可投稿性的差距

| 项目 | 现状 | 投稿要求 | 差距 |
|---|---|---|---|
| 正文页数 | 9 页 | ≤9 页 | ✅ 达标 |
| 实验数字 | 0（767 处占位符） | 主表 + 4 个实验 + 消融全部有数 | ❌ **致命** |
| 图 | 3 张在正文（fig1/2/3），2 张下沉附录 | Figure 1/2 必须在正文 | ✅ 达标 |
| 表 | 6 张在正文 | 主表必在正文 | ✅ 达标 |
| 参考文献 | 35 条 | 通常 40–60 条 | ⚠️ 偏少 |
| 负结果 | 保留在 Appendix | 建议保留 | ✅ 达标 |
| claim 边界 | 未出现 SOTA / safe / robust | 必须 | ✅ 达标 |

**结论：这是一份"填数即用"的骨架，不是一份可投稿稿。**
在服务器把 `v44_*` 结果组跑出来之前，不要投。这一点稿子里没有掩饰，是对的。

---

## 2. 评分（ICLR 表）

| 维度 | 分数 | 说明 |
|---|---|---|
| Soundness | **2 / 4** | 协议设计严谨（TRAIN-only、$L+H$ purge、parent 为统计单元、Holm 校正、mask 不当作独立样本），但**无法验证**，且 replay bank 的分布偏移问题没有正面处理 |
| Presentation | **3 / 4** | 结构清楚，claim 边界自觉，占位符规范统一；扣分在文风过度防御、否定句密集、附录过载 |
| Contribution | **2 / 4** | "选择性治理"这个 framing 有价值，但技术组件（KNN + 保守门）本身不新，且未与 bandit/OPE 切割 |
| Rating | **3 / 10**（当前） | 纯因无结果。**若数字成立且补上 §7 的切割，可到 6–7** |
| Confidence | **4 / 5** | 时间序列 + 缺失 + TSFM 方向熟悉 |

---

## 3. Strengths

1. **问题 framing 是真的好。** 把"不完整输入怎么办"从"怎么补得更准"改成
   "这个样本该不该治理、用哪个动作、什么时候应该 abstain"，是一个干净的视角转换。
   摘要里 "a feasible intervention should not always be executed" 一句话就把动机立住了。

2. **claim 边界极其自觉，这是很多投稿做不到的。**
   - 明确写 "If the measured correlation turns out to be high, this conclusion must be
     rewritten rather than softened" —— 预先承诺不软化结论。
   - Oracle 只作诊断，明确 "excluded from ranks and from all claims"。
   - TATO 明确写成 "under our $L{=}512$ protocol, never as a full replication"。
   - 负结果留在 Appendix K，并显式声明"旧协议不可与本文任何表比较"。
   这种自律在审稿人眼里是加分项，因为它大幅降低了"作者在藏东西"的怀疑。

3. **统计协议写得比多数投稿细。** parent 为 primary unit、mask variant 不当作独立样本、
   paired cluster bootstrap、Holm 校正、average rank + won cells，这几条都写清楚了。

4. **效率被严格隔离。** "Efficiency is reported separately and never folded into an
   accuracy score"，并且冷启动单独成行。这是对的。

5. **正文/附录分工合理。** 4.1–4.6 六节 + 附录 16 节，主表只放 10% severity，
   30/50% 进附录，符合"正文讲结论、附录讲证据"的分工。

---

## 4. Weaknesses

### 4.1 Major

**W1. 没有结果，因此所有贡献都无法验证。**
这是当前唯一但足够致命的问题。摘要里 "achieves `[RESULT-MAIN]` while reducing harmful
interventions by `[RESULT-HARMFUL]`" 现在等于什么都没说。
→ 必须先把主实验跑完再投，没有折中方案。

**W2. "Counterfactual" 用词会引起争议。**
题目和 3.2 节都叫 Counterfactual Replay。但你们做的是：在**历史 TRAIN 窗口**上注入缺失机制、
真实执行动作、记录真实收益 $g_{i,a}$。这是 **historical replay / offline evaluation**，
不是因果推断意义上的 counterfactual（因为同一个 $X_i$ 并没有"另一种反事实世界"，
你们只是在一个已知未来的窗口上做了一次实测）。

审稿人会问：
- 你对同一个窗口执行了动作 $a$，得到的 $g_{i,a}$ 是**实测值**，为什么叫 counterfactual？
- 你声称的 counterfactual 是哪一对 potential outcome？$Y(a_0)$ 和 $Y(a)$ 都在同一份历史数据上
  观测到了，这更像 factual replay。

→ **建议二选一**：
(a) 改名（例如 *Replay-Based Selective Governance* / *Historical Replay*），
(b) 保留名字但在 3.2 节开头用一段明确说明"我们使用 counterfactual 的宽松含义：
    在已知未来的历史窗口上评估未被执行的动作"，并引用因果/反事实评估的文献把边界划清。
    **不要什么都不说。** 这一条不改，一个懂因果的审稿人会直接质疑贡献的合法性。

**W3. 方法新颖性未与 contextual bandit / off-policy evaluation 切割。**
剥开看，你们的方法是：
- 候选臂集合固定且很小（5 个）；
- 用上下文特征做 per-arm KNN，估计每个臂的收益；
- 用 mean − β·std/√n 做保守选择，低于阈值就 abstain。

这就是 **contextual bandit 里的保守/悲观策略选择**，加上一个 **abstain 选项**（即 arm $a_0$ = KEEP）。
审稿人一定会问："这和
- *off-policy evaluation / policy selection*，
- *conservative bandit / pessimism principle*，
- *learning to defer*，
- *selective prediction*（你们已经引了 Chow / Geifman / Vovk）
到底差在哪？"

→ 现在 Related Work 只有 3 小节（Imputation / Task-Oriented / Data-Centric），
**完全没有 bandit 或 OPE 这条线**。这是最容易被拒的一个点。
必须新增一小节，明确说：
"我们的问题形式上接近 contextual bandit 的保守策略选择，但有三点不同：
(1) 臂的收益不是仿真奖励而是**真实执行冻结 TSFM 的预测损失**，
     因此没有 reward function 可写，只能靠 replay；
(2) 允许 abstain 且 abstain 是默认安全动作；
(3) 我们不做探索，只做历史证据的局部检索。"
把这三点讲清楚，新颖性才站得住。

**W4. Replay bank 的分布偏移没有正面处理。**
这是方法的内在威胁：bank 里的伪部署缺失机制是**你们自己注入的合成机制**，
而真实部署的缺失机制可能不同（不同传感器、不同延迟分布）。
$g_{i,a}$ 是在合成机制下测的，能不能迁移到真实机制？

→ 现在稿子里完全没有讨论。必须加一段 limitation：
- 明确说明 bank 覆盖的是四种模式 × 三种 severity 的**离散网格**；
- 说明部署期若落在网格外会发生什么（目前设计下会匹配到最近的网格点，可能失配）；
- 说明 Appendix I 的 finance case 是唯一接触"真实缺口"的地方，而且还没验证。

**W5. 目录只有 5 个臂，且包含 FFILL 这种弱动作。**
审稿人会问：为什么不把 BRITS/CSDI/T1 的输出也作为候选臂？
现在的回答是 "the contribution under test is governance, not imputer architecture"，
这个回答**不够**——因为如果目录本身不够强，那么"选择了最优臂"这件事价值有限，
CGC（catalog gap closed）也只在很弱的天花板下计算。
→ 建议补一个 Appendix：把 BRITS/CSDI/T1 的输出**也作为候选臂**跑一次，
证明"即使目录扩大，选择器仍然有效"，或者诚实地说明扩目录后 CGC 下降。
不补这一条，审稿人会认为 main table 的对比不公平。

### 4.2 Minor

**W6. $\tau$ 固定为 median($d_i$) + ε 且"不搜索"，缺少理由。**
"不搜索"本身是优点（防止调参），但需要解释为什么这个函数形式合理。
现在只有一句 "is never searched"，读起来像在回避问题。
→ 补一句直觉：median 让有效邻居数不随样本密度剧烈变化，ε 防止除零。

**W7. 主表的比较族没有说清。**
Holm 校正 "across baselines"，但主表有 source × backbone × horizon × pattern 很多格。
哪些格构成一个 family？是每张表一个 family，还是每个 backbone 一个？
→ 需要一句话明确，否则多重比较的严格性会被质疑。

**W8. 每请求最多 2 次冻结模型调用，但 bank 构建的离线成本被"amortised"一笔带过。**
审稿人会追问：bank 需要多少调用？在什么规模上摊薄？
→ Appendix J 已经有 offline 一行，但要给出量级，并说明"如果部署规模小，摊销不成立"。

**W9. Figure 4 和 Figure 5 被下沉到附录，导致 §4.4 和 §4.5 在正文里没有任何图。**
正文现在只剩 fig1/fig2/fig3 三张图，而 §4.4（治理诊断）和 §4.5（鲁棒性）是纯文字 + 表。
从审稿人角度，"Experiment 4（鲁棒性）"没有图会显得单薄。
→ 权衡建议：把 fig5（severity 曲线）拉回正文，把 Table 5 压成 3 行摘要进附录；
   或者把 fig4 的两个 panel 与 fig5 合成一张 3-panel 图放正文。

**W10. "Reconstruction Is Not Forecast Utility" 的结论并不新。**
TOI 那篇（`wang2024taskoriented`）已经展示了重建排名与任务效用排名可以不一致。
稿子在 Related Work 里承认了这一点，但在 §4.3 又把它当成一个 experiment 来讲，
读起来像在重新发现已有结论。
→ 建议把 §4.3 的定位改成"**在冻结 TSFM + 我们的目录下量化这个不一致**"，
   并明确写 "this is consistent with the task-oriented imputation finding, and we
   quantify its magnitude for frozen TSFMs"，而不是暗示这是新发现。

**W11. 参考文献偏少（35 条）。**
正文只引了 34 处。ICLR 同类论文通常 40–60 条。
除 W3 的 bandit/OPE 线外，还缺：
- 时间序列的 missing data 处理综述；
- TSFM 的 in-context / zero-shot 评估工作；
- 数据清洗 / data repair 的既有文献（"when to clean" 这条线其实有前作）。

**W12. Appendix 有 27 张表，其中大部分是空骨架。**
从"完整交付"角度是优点，从"审稿人翻阅体验"角度是负担。
→ 建议在附录开头加一个**索引表**（本稿已有 Table 27 列了 result groups，
   但那是按数据组列的，不是按"哪个附录回答哪个问题"列的）。
   加一个"附录导航"会让审稿人觉得组织得好。

---

## 5. 文字与叙述（你特别问的部分）

### 5.1 最大的文风问题：**否定句和防御性措辞过密**

统计（正文 + 附录）：

| 词 | 出现次数 | 评价 |
|---|---|---|
| `never` | 29 | **过多** |
| `not ` | 59 | **过多** |
| `deliberately` / `deliberate` | 7–8 | **过多，且重复** |
| `really executed` | 4 | 英文不自然 |

整篇稿子有很大一部分是**在用"我们不做什么"来定义自己**：
"never fine-tunes the backbone, never ensembles forecast outputs, never corrects the
forecaster's predictions"；"we do not claim"；"it is not a universal oracle gap and we
do not describe it as one"；"must be rewritten rather than softened"……

**这不是内容问题——这些边界声明都应该保留。** 问题是它们**分布得太均匀**，
导致读起来像作者在不停地自我辩护，而不是在陈述发现。

→ 建议：
- 把边界声明**集中**到两处：§1 末尾一段 + Reproducibility statement。
  正文其他地方遇到需要限定的地方，用一次简短的从句带过，不要每次都展开。
- 删掉重复的 `deliberately`。现在 "It is deliberately not enlarged"、
  "deliberately keep our selection rule simple"、"deliberately narrow"、
  "deliberately presented as a sign-agreement check"、
  "is deliberately not presented as" —— 同一个词撑了五处论证，
  审稿人会觉得是填充。每处换成具体理由。
- `really executed` → `actually executed`（或直接 `executed`）。
  英文里 "really" 在这个位置很别扭。4 处都要改。

### 5.2 重复的段落开头

"All five published baselines enter." 在 §4.4 和 §4.5 各出现一次，
另外 §4.3 也有 "All five published baselines enter"。
→ 这是模板化写作的痕迹。每节开头都是 "All five ... enter. We report ..."。
建议每节用不同的句子切入，或者在第一处声明一次、后面改为
"as in \S\ref{sec:exp-main}"。

### 5.3 每节开头的斜体问题句

"*Does better reconstruction imply better forecasting for a frozen TSFM?*"
这个模式在 §4.2–§4.6 一致使用，**这是好的**，保留。
但 §4.6（Ablation）没有这个问句，不一致。
→ 给 §4.6 也补一句问句（例如 "*Which component carries the gain?*"）。

### 5.4 摘要的措辞

> "These results suggest that reliable incomplete-input handling **requires** deciding
> when to act, rather than treating repair as a mandatory preprocessing step."

`requires` 太强了。你们只测了 5 个 baseline、3 个 backbone，
从"我们的方法这样做有效"推不出"可靠处理**必须**这样做"。
→ 改成 "can benefit from deciding when to act" 或
"a reliable system should be able to decide when not to act"。

摘要另外两处：
- "Across `[N-DATASETS]` datasets, `[N-BACKBONES]` frozen TSFM backbones, four
  missingness patterns, and two forecasting horizons" —— 填数时记得
  `N-BACKBONES` 是 3，但其中 Chronos-2 不参与方法设计，摘要里最好写成
  "two development backbones plus a held-out third family"，否则会显得在虚报规模。
- 摘要没有说 abstention 的代价。如果 abstain 率高，读者会怀疑方法"什么都没做"。
  建议在摘要里加一句 intervention rate 的量级。

### 5.5 术语一致性

- `\textsc{Keep}` / `Native KEEP` / `KEEP` —— 大写形式在表格和正文里混用
  （表格里是 `\textsc{Native Keep}`，公式里是 `L_{\textsc{Keep},i}`，
  §4.4 正文又写 `\textsc{Keep}`）。**统一成 `\textsc{Keep}`**，
  只有指"不做治理这一策略"时才用 `Native Keep`。
- `TS-ICL` 与 `\tsfm` 的排版：`\tsfm` 宏展开为纯大写 "TSFM"，
  但正文里也直接写了 `\tsfm{}s`，展开成 "TSFMs"。
  建议统一为 `TSFM` / `TSFMs`，不要混 `\tsfm{}s` 和手写。
- `oracle` 的小写与 `Catalog Oracle` 的写法混用。统一。

### 5.6 具体句子问题

| 位置 | 原文 | 问题 | 建议 |
|---|---|---|---|
| §1 | "there is no single repair that dominates everywhere" | 已被删掉，但同类表述仍在别处 | 保留即可 |
| §3.2 | "re-enacting the deployment missingness mechanism" | `re-enact` 偏文学 | `replaying` 或 `injecting` |
| §3.3 | "no learned metric and no deep encoder is used" | 否定句，且像在辩解 | 改正面："the distance is fixed and training-free" |
| §4.1 | "It is deliberately not enlarged" | 需要具体理由 | 见 W5 |
| §4.3 | "The claim this experiment can support is deliberately narrow" | `deliberately` 重复 | "The claim this experiment supports is narrow" |
| §4.6 | `\ph{ABLATION-READING}.` 单独成段 | 占位符单独成段排版难看 | 填数时并入前一段 |
| Appendix K | "reproduced below verbatim from the frozen ledger" | 好，保留 | — |

### 5.7 图表标题

- 表题普遍偏长（3 行）。ICLR 表题最好 1–2 行。
  当前 Table 1/5/6 的表题都到 3 行，占用正文空间。
  → 把"方法学解释"移到表下的正文或附录，表题只留"这张表是什么"。
- 图题普遍写得好（说清了 panel 含义），保留。
- `\oracle{}` 的灰色斜体在正文里指代 "the oracle row" 时容易和真正的
  oracle 混淆。建议正文里第一次出现时写全 "catalog oracle"。

### 5.8 拼写与细节

- 摘要 `\ph{N-DATASETS}` 填数时注意：主协议登记的是 **8** 个来源。
- `Appendix~\ref{app:r5}` 的标题是 "Negative Result from the Preceding Development
  Cycle"，但正文引用处写的是 "Appendix K"。附录重排后编号会变，
  **不要写死字母**，用 `\ref{}`。（本稿目前是用 `\ref`，没问题，保持。）
- `\ph{APP-SEVERITY-NOTE}` 这类"结构性占位符"和"数字占位符"混在一起，
  填充时要区分：前者是要写一段说明文字，后者是填数。README 里已分开命名，OK。

---

## 6. 如果我是审稿人，我会问的问题

1. 你说的 counterfactual 具体是哪一对 potential outcome？两个都在历史数据上观测到了，
   为什么不是 factual replay？
2. 你的方法和一个上下文 bandit 上的悲观策略选择有什么区别？
   如果区别只是"奖励来自真实模型损失"，那这是一个 application，不是一个 method。
3. Replay bank 用合成缺失机制构建，部署期机制不同怎么办？有没有做过机制失配实验？
4. 目录只有 5 个臂且含 FFILL，为什么不做"把 BRITS/CSDI/T1 也放进目录"的版本？
   如果放进去，CGC 还剩多少？
5. Abstain 率是多少？如果 abstain 率很高，方法是不是退化成 KEEP？
6. $g_{i,a}$ 是单窗口的实测差，噪声很大。KNN 平均能压掉多少？
   有没有报告 $g$ 的方差随 $K$ 的变化？
7. 每请求 2 次调用，但 bank 构建要多少调用？在什么部署规模下摊销才成立？
8. 你的 $\tau$ 用 median 是事后选的还是事先定的？有没有敏感性分析？
9. §4.3 的结论和 TOI 那篇有什么不同？
10. Figure 1(a) 说"三个 episode 有相同缺口但最优动作不同"——这是真实测量还是示意？
    如果是示意，必须标注。

---

## 7. 按优先级的修改清单

### P0（不解决不能投）
1. **跑出所有结果**，把 767 处占位符替换成真实数字。主表、4 个实验、消融、效率表。
2. **处理 "counterfactual" 的用词问题**（W2）：改名，或在 §3.2 开头加一段边界说明。
3. **新增 Related Work 一小节**，与 contextual bandit / off-policy evaluation /
   learning-to-defer 做切割（W3）。

### P1（显著影响评分）
4. 补 replay bank 分布偏移的 limitation 讨论（W4）。
5. 补"扩大目录"的附录实验（W5）。
6. 把 fig5 拉回正文，或合并 fig4+fig5（W9）。
7. 参考文献从 35 条补到 45+ 条（W11）。
8. 摘要去掉 `requires`，补 abstain 率与 backbone 的准确表述（§5.4）。

### P2（写作质量）
9. 系统清理否定句密度与 `deliberately` 重复（§5.1）。
10. 每节开头去模板化（§5.2）；给 §4.6 补斜体问句（§5.3）。
11. 统一 `Keep` / `TSFM` / `oracle` 的术语与排版（§5.5）。
12. 表题压到 1–2 行（§5.7）。
13. 附录加一个"导航表"（W12）。
14. 明确多重比较的 family 定义（W7）；给 $\tau$ 的固定形式补一句理由（W6）。

---

## 8. 给作者的实话

这份稿子现在**不能投，但值得投**。

- 结构、协议、claim 边界、统计口径，这四样已经做到了很多投稿做不到的水平，
  而且是那种"审稿人一眼能看出来作者是认真的"的水平。
- 真正的风险不在执行，在**定位**：
  "counterfactual" 这个词和"没有和 bandit 切割"这两件事，
  会让一个较真的审稿人认为这是"用新词包装了一个标准的离线策略选择问题"。
  这两件事**在跑实验之前就应该改掉**，因为改完之后 Related Work 和
  §3.2 的写法会影响你怎么讲结果。
- 一个具体的建议：**先把 W2 和 W3 处理掉，再去填数**。
  如果等数字出来再改，很可能会发现需要重跑一部分实验来支撑新的表述。

---

## 9. 对 LaTeX 工程本身的评价（非论文内容）

- 正文 9 页硬上限达标（结论落在第 9 页），`Overfull` 为 0，无 undefined 引用，
  唯一告警是 `OT1/ptm/m/scit` 无害字体形状警告（`\textsc` 作用于宏导致）。
- 占位符方案（`\ph{KEY}` → 灰色 `[KEY]`）配合 `latex/README.md` 的命名规范，
  是这套工程最实用的设计：填充时可以 `grep` 逐条核对，不会漏也不会串。
- 图源 EPS + PPTX 双份，且**几何定义只有一处**，避免了"改了 eps 忘了改 pptx"的经典问题。
- 附录从"一段话占位"扩写成 16 节、27 张表的完整结构，填充工作量清晰可见。

**建议：把这份评审的第 7 节（优先级清单）直接当作接下来的 TODO 列表。**
