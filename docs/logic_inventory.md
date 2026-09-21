# 段落清点（logic inventory）— IntroActTS v52 底稿

清点时间：2026-09-21。底稿：`latex/IntroActTS_20260921_v52.tex`（提交 c9c22c5 状态）。
行号为清点时行号，重写后会漂移；以段落 ID 为准。
处置类别：保留 / 调整（段内重排改写）/ 拆分 / 合并 / 迁移（注明去向）。

## 引言（§1，行 88–143）

| ID | 位置 | 首句 | 回答的问题 | 混入主题 | 处置 |
|----|------|------|-----------|---------|------|
| I1 | 91–96 | Time-series foundation models support forecasting without task-specific retraining. | 部署场景与本文限定（固定预测器、不改写有效观测、修复与否的判断） | "whether doing so helps" 评价对象不明 | 调整：明确本文主动限定，判断对象=预测结果 |
| I2 | 98–105 | Imputation methods estimate missing values… | 已有工作与本文决策问题的关系 | 三句分类罗列缺句间联系；末两句重复 I1 的问题 | 调整：按"处理环节→评价目标→冻结预测器→请求级粒度"重排 |
| I3 | 107–113 | The answer depends on the request and the frozen backbone. | 效用为何不可在线测量、历史窗口为何能提供监督 | 缺"历史目标已观测"前提；末句两次跳跃 | 调整：补前提，段末留下"如何估计新请求效用" |
| I4 | 115–120 | INTROACT-TS implements this procedure through a fixed replay bank… | 方法按信息流做什么 | 离线/在线/决策压缩在一句；调用预算突入 | 调整：存什么→取什么→算什么→KEEP 分支→成本 |
| I5 | 122–131 | Our contribution is a formulation of selective input repair… | 贡献、验证范围、证据性质 | Compact 决策史（→§4.5）、来源集中（→§4.3）、逐项消融 | 拆分：保留三层贡献+一句 post-hoc 说明，其余迁移 |

## 相关工作（§2，行 145–184）

| ID | 位置 | 首句 | 回答的问题 | 混入主题 | 处置 |
|----|------|------|-----------|---------|------|
| R21 | 150–159 | Imputation reconstructs unavailable values… | 已有工作在哪个环节处理缺失，本文选择层的关系 | variable subset 与训练/冻结两个维度混在一句 | 调整：两维度分开陈述，结尾落在候选构造与选择 |
| R22 | 163–168 | TATO shows that a frozen TSFM can be adapted… | 历史任务表现如何用于数据侧适配 | TS-ICL 插入打断 TATO 叙述 | 调整：先完整写 TATO（含 R23），再写 TS-ICL 角色 |
| R23 | 170–171 | TATO adapts at the domain level. | 域级 vs 请求级 | 与 R22 重复 | 合并入 R22 |
| R24 | 175–184 | Selective prediction trades coverage for lower risk… | KEEP 与选择性预测/算法选择的关系，全动作反馈 | 结尾未落到本文形式化对象 | 调整：结尾引向 §3 的固定动作目录 |

## 方法（§3，行 186–367）

| ID | 位置 | 首句 | 回答的问题 | 混入主题 | 处置 |
|----|------|------|-----------|---------|------|
| M11 | 204–213 | Let X denote a context… | 请求、掩码、目标、冻结流水线定义 | 三骨干 NaN 处理实现细节打断形式化 | 拆分：实现细节→附录 B/§4.1 |
| M12 | 215–227 | Let A be a fixed catalog… | 动作目录、KEEP、效用定义 | — | 保留（公式后补正负号解释） |
| M13 | 229–238 | Four constraints define the deployment protocol. | 部署协议约束 | — | 保留 |
| M21 | 242–253 | The quantity that decides the action… | 历史效用标签如何构造 | — | 保留 |
| M22 | 255–260 | The state recorded with each outcome is action conditioned | 标签与什么信息一起保存 | 状态用途未先说 | 调整：先用途（匹配部署请求）后记录定义 |
| M23 | 262–269 | Two properties of the bank set the scope… | 回放库适用范围 | 检索范围细节（→3.3） | 调整：检索范围句移至 3.3 |
| M24 | 271–274 | Local estimation assumes that nearby… | 局部估计假设 | 距离-误差诊断结果（→§4.5/附录） | 调整：保留假设一句话，诊断结果移出 |
| M31 | 278–283 | The estimator is a weighted average… | 估计器与状态概览 | 干预特征组描述需与恒零事实一致 | 调整：注明现目录下 4/5 干预坐标恒零 |
| M32 | 285–310 | Retrieval is performed separately for each action. | 邻域、权重、均值、离散度定义 | — | 保留（按"为什么出现"重排句序） |
| M41 | 314–329 | A positive local mean is not sufficient evidence… | 决策分数与两个分支 | "score at zero means evidence does not distinguish…" 无统计依据 | 调整：删除该解释句 |
| M42 | 331–347 | The two hyperparameters are selected once per backbone… | k、β 如何确定 | 实际行为与"本应怎么做"混在一句；末句 TEST 披露位置不当 | 调整：分离描述与规范注记；TEST 披露由 §4.1 承担 |
| M43 | 349–351 | The reference action is always available… | 规则总返回预测、范围限制 | — | 保留 |
| M51 | 355–359 | A request is served in two stages. | 在线执行顺序 | — | 保留 |
| M52 | 361–367 | A request costs one forecasting-backbone call… | 成本构成 | — | 保留 |

## 实验（§4，行 369–628）→ 重组为 7 小节

| ID | 位置 | 首句 | 回答的问题 | 混入主题 | 处置 |
|----|------|------|-----------|---------|------|
| E11 | 374–381 | The recorded evaluation covers eight sources… | 评估对象（数据/骨干/bank/上下文） | — | 保留 → 4.1 |
| E12 | 383–386 | The catalog contains KEEP and five repairs. | 对照方法 | 各对照检验什么未说明 | 调整 → 4.1：KEEP/固定/简单选择器各自的问题 |
| E13 | 388–393 | Each source is split chronologically… | 划分、聚合、统计单位 | — | 保留 → 4.1 |
| E14 | 395–399 | The current design incorporates observations… | 证据性质（post-hoc） | "separate implementation verification effort" 无可验证含义 | 调整 → 4.1：删该句 |
| E21 | 403–408 | The recorded diagnostics show that no single action is best… | 动作效用是否因请求而异 | 结论措辞需限于"存在潜在收益" | 调整 → 4.2，结尾架桥到 4.3 |
| E22 | 410–416 | Reconstruction quality provides limited guidance… | 重建质量能否替代预测效用 | — | 保留 → 4.2 |
| E23 | 425–426 | Appendix breaks the same episodes down… | 指针段 | 独立成段无内容 | 合并入 E21 末句 |
| E31 | 430–434 | Table compares the methods at 10% missingness. | 总体结果 | — | 保留 → 4.3 |
| E32 | 436–442 | Paired differences against KEEP… | 配对比较支持程度 | — | 保留 → 4.3 |
| E33 | 444–448 | The method also has the lowest mean rank… | 秩次与边界 | — | 保留 → 4.3 |
| E34 | 538–545 | A leave-one-source-out check recomputes… | 优势是否集中于单一来源 | 现置于 4.5，割裂主比较 | 迁移 → 4.3 |
| E35 | 547–556 | A related diagnostic asks whether the gain comes from… | 请求级 vs 来源级固定选择 | 同上 | 迁移 → 4.3（E34 之前） |
| E36 | — | （新）桥接句 | 引出干预频率问题 | — | 新增一句 → 4.3 末 |
| E41 | 481–483 | At the default operating point… | 默认工作点的频率/有害率/有害损失 | — | 保留 → 4.4 |
| E42 | 485–489 | To assess whether the rule does more than reduce… | 机制问题：是否只是少干预 | — | 保留 → 4.4 |
| E43 | 491–497 | The full rule improves MASE over random gating… | 门控对照结果 | 需先讲随机门控（动作不变）再讲其他 | 调整 → 4.4 |
| E44 | 499–511 | Two further controls match the comparison partners… | 频率匹配伙伴对照 | 不得写成 TEST 同预算 | 调整 → 4.4 |
| E51 | 526–536 | Figure compares the same configurations at three severities. | 缺失严重度下表现是否保持 | Chronos-2 bank 句与主表重复 | 调整 → 4.6（E61） |
| E61 | 567–570 | Table tests how the selector uses historical utility. | 消融设置 | — | 保留 → 4.5（效用估计段） |
| E62 | 572–576 | Pooling action utilities increases MASE… | pooling 对照 | A2 名称冲突 | 调整 → 4.5：改名 A2-M |
| E63 | 578–582 | The original A2 removed only intervention features… | 固定配置特征消融 | 与新 pooling 共用 A2 名 | 调整 → 4.5：改名 A2-F |
| E64 | 584–600 | That feature ablation reuses the full method's frozen… | 重新选参的 Compact 比较 | 过长，晋升报告腔 | 调整 → 4.5（E53 段）：收敛到结论，细节留附录 E |
| E65 | 602–604 | Always acting raises harmful loss… | KEEP 分支作用 + 调用数 | 两个主题混一段 | 拆分：always-act → 4.5 或 4.4；calls → 4.7 |
| E71 | — | （新）历史支持段 | bank 大小/选参稳定/掩码实现 | 现只在附录 | 新增概述段 → 4.6（E62），引用附录 F |
| E72 | — | （新）成本段 | 请求增加哪些计算 | — | 由 E65 拆分 + 附录 app:calls 概述 → 4.7 |

## 结论（§5，行 631–647）

| ID | 位置 | 首句 | 回答的问题 | 混入主题 | 处置 |
|----|------|------|-----------|---------|------|
| C1 | 633–646 | We formulated incomplete-input handling as a choice… | 全文结论 | 逐项消融复述、门控机制归因过强 | 重写：四步逻辑（问题→方法→核实发现→证据边界） |

## 摘要（行 63–86）

逐项消融总结、pooling、Compact 选参经过、门控机制归因全部堆在结果后。处置：按 A1–A8 功能重写，删版本史，预测优势与风险优势分别限定比较对象。

## 附录（行 679–2564）→ 重组为 A–G

| 现位置 | label | 去向 |
|--------|-------|------|
| Appendix map (683) | app:map | 重写为 A–G 地图 |
| §Protocol: Scope and Assumptions | app:scope | A（评估范围部分） |
| Full Method Details: catalog / features / OPE | app:catalog, app:features, app:ope-positioning | B |
| Replay Construction（核心+splits） | app:replay, app:splits | splits→A；replay 核心→B |
| Replay Bank Size | app:replaysize | F |
| Local Utility Estimation（transfer） | app:transfer | B |
| Dataset and Missingness Protocol | app:data-protocol（patterns/metric/diagnostic） | A |
| Complete-Input Contract | app:contract | B |
| Full Per-Source/Per-Pattern Results | app:full-results（baseline-availability→A；baseline-config→A；datasets、pattern） | availability/config→A；其余→C |
| Action-Opportunity Strata | app:opportunity | D |
| Full Severity Results | app:severity-full, app:robust-fig | F |
| Reconstruction/Utility Diagnostics | app:recutils, app:utility-by-severity | C（支撑 4.2）；governance→D |
| Governance Diagnostics | app:governance-fig | D |
| Ablations and Stability | app:ablation-details→E；app:selstability→F；app:seeds→F | E/F |
| Cost, Failures, Memory | app:cost-full | G |
| Reproducibility | app:repro-full | G |
| Supplementary（development） | app:development | G（必要开发记录） |
| Numerical Values for Action Utility | app:main-values | C |
| app:v52（机制/特征控制表 tab:v52-a2 → E；门控表 tab:v52-gates → D；掩码更正注记 → F） | app:v52 | 拆入 E/D/F，节标题去版本号 |
| app:v53（compact 选参 → E；频率匹配伙伴 tab:v53-gates → D；source-fixed/LOSO → C） | app:v53 | 拆入 E/D/C，节标题去版本号 |

表/图 label 全部保留原名，避免引用断裂；表注中加 "run set v52/v53" 来源说明。
