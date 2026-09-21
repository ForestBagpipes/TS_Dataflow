# IntroActTS v52 主文三次连贯性通读报告

- 对象：`latex/IntroActTS_20260921_v52.tex` 主文（摘要 L63–81 至结论 `\label{sec:main-end}` L689），附录不查。
- 配套逐句审计：`docs/sentence_logic_audit.csv`（248 句，48 段，全覆盖）。
- 检查日期：2026-09-22；tex 未做任何修改。

## 第一次通读：只读每段首句

把 AB、I1–I6、R21–R23、M11–M52、E11–E71、C1 共 48 段的首句连读，可以得到完整的缩略论文链条：部署场景（AB s1/I1）→研究问题（I1 s4）→已有工作定位（I2、R21–R23）→效用不可见与历史监督（I3）→方法信息流（I4、M11–M52）→三层贡献（I5）→评估边界（I6、E14）→协议（E11–E13）→动机证据（E21–E23）→主结果（E31–E33）→来源诊断（E34–E35）→干预与损害（E41–E44）→估计与状态（E51–E53）→敏感性（E61–E62）→成本（E71）→结论（C1）。

发现：

1. E12 s1（MINOR，衔接）：§4.1 第二段主题是比较伙伴，首句却是"The catalog contains Keep and five repairs"，回到目录构成，与段内其余句子（各对照回答什么问题）不直接相关。建议删除该句或并入 E11，以"每个比较伙伴回答一个不同问题"开篇。
2. 其余段落首句均与前段末句或全文线索相接，无跳跃。I4→I5（成本细节→贡献清单）、I6→R21（评估边界→相关工作）、E44→E51、E53→E61、E62→E71 为常规节级过渡，可读。

结论：第一次通读**通过**（1 处 MINOR）。

## 第二次通读：只读每段末句与下一段首句

逐对检查 47 个段落衔接点。绝大多数论述对象延续：I3 s5（估计任务）→I4 s1（用标签决策）、M24 s2（估计器下文定义）→M31 s1（估计器是……）、E36（过渡到干预与损害）→E41 s1、E23 s2→E31 s1 等均成立。

发现：

1. E22 s6（MINOR，衔接）：段末"Figure 1 illustrates how historical forecasting outcomes can inform selection"是悬挂引用——前一句是附录指针（app:recutils），图 1 引用归属不清，且内容属于方法动机而非本段（重构 vs 效用诊断）的收尾。建议移到段首、移到 §3 或删除。
2. R22 s4→R23 s1（MINOR，观察级）：TS-ICL 后端说明紧接 selective prediction 小节首句，属小节切换的可接受突变，不构成断裂。
3. E11 s7→E12 s1：与第一次通读发现 1 同源，目录句与协议末句（附录定义掩码与指标）之间话题回落。

结论：第二次通读**通过**（2 处 MINOR，无换题断裂）。

## 第三次通读：逐句读完整主文

对 248 句逐句判断承接对象、关系类型、定义先后与证据边界（明细见 audit CSV）。发现：

### CRITICAL

1. **M22 s2 / M31 s2（tex L267、L286）——`\label{eq:state}` 位置错误导致交叉引用渲染错误。** 状态定义 `z_{i,a}=φ(...)` 写在正文行内，`\label{eq:state}` 紧随其后但不在 `equation` 环境中，因此 `\eqref{eq:state}` 锚定的是最近编号的计数器（小节 3.2），编译后 M31 s2 的"The state $z_a$ of \eqref{eq:state}"会显示为"(3.2)"而非公式号。这是编译产物中可见的引用错误。建议方向：把状态定义放入 `equation` 环境，或去掉 `\eqref` 改用文字引用（如"the state defined in §3.2"）。

### MAJOR

2. **M11 s4（tex L216–217）——交叉引用目标不含所声称的度量。** 该句称参考动作的缺失处理"differs across backbones, as measured in §4.2"，但 §4.2（sec:exp-exists）报告的是 oracle-best 份额与重构-效用排序诊断，并未给出逐骨干原生缺失处理差异的度量；逐骨干 Keep 差异实际见于表 1（§4.3）及附录。属引用超出目标内容。建议方向：把引用指向实际量化逐骨干 Keep 行为差异的表或附录小节。
3. **M42 s1（tex L346）及 E13 s3/s5、E62 s4——"parent" 主文未定义先用。** leave-one-parent-out 是核心选择程序，E13 又以 parent 报告样本量与 bootstrap 聚类单位，但"parent"（历史监督单位）在主文从无定义，仅在附录（L802、L876）说明。建议方向：首次出现处（M42 s1 或 E13）补一句定义。
4. **M13 s3（tex L239）——"visible target" 与 M11 s2 的未来目标 Y 字面冲突。** M11 s2 刚声明 Y 不可得，M13 s3 即说修复取值限于"the range of the visible target"，细读会与不可得目标矛盾（实际指上下文中目标通道的可见部分，附录 L1228 使用该义）。建议方向：改为"visible part of the target channel in the context"或首次出现处加注。

### MINOR

5. AB s7 / E41 s2 / M42 s3：harmful loss 与 conditional harmful rate（HIR）在主文使用而无定义，仅在附录图表注（L754、L1845、L2065）解释。建议首次主文出现处各补一句定义。
6. M13 s4："the bank" 在 §3.2 定义回放库之前出现。建议写"§3.2 构建的回放库"或调整语序。
7. E21 s2："oracle-best shares from 11.1% to 24.8%"未说明范围沿哪个维度（动作？骨干？）取值。建议补一句说明。
8. E22 s2 与 E21 s2：两个不同的 19.3%（Keep 最优份额；重构-效用一致比例）相邻出现，同值易误读为同一统计量。建议强调分母与统计量不同。
9. E51 s8：结论"comparisons support action-specific local estimation"的最直接证据是 A1（全局均值），但正文只讨论了 A2-M 与 A5 的数字，A1 结果（1.475、100% 干预）仅见表 2。建议补一句 A1 结果支撑该结论。
10. E52 s3：A2-F 在正文有结果讨论（1.4185、Bolt 区间支持缩减状态）却不在表 2 中，读者无法在表中对照。建议表 2 增行或在表注指明数值出处。
11. E53 s4："degrades TimesFM significantly"的"significantly"无检验或区间支撑。建议改描述性措辞或补配对区间。

### 已核实无问题项（防止误报）

- 禁忌表述六项全部处理正确：R23 s3 明确 Keep 不是拒绝回答；M41 s8 明确零阈值是决策约定而非显著性陈述；主文未声称测试集严格同预算比较；M31 s3 对四个恒零特征的表述方向正确（不承载修复幅度信息）；E71 s5 明确不声称端到端延迟分位数；utility/score 术语分工一致，evidence 仅作普通名词使用。
- E43 s5 与 E51 s6 的配对差同为 -0.0252：已核对为两次不同实验的真实记录（FULL−R2_CART_MATCHED 见 `docs/v53_state_compact_report_20260922.md` L151；FULL−A2R 见 `docs/IntroActTS_v52_ablation_correction_20260921.md` L43），区间不同，非复制错误。
- E41 s3 所称 fig:harm 在附录：已核实（标签在 L755，附录内）。
- 数值一致性抽查通过：摘要 1.437/1.576/0.0375/0.0513、E32 三个配对差与区间、E34 来源级固定策略数值（+0.0181/+0.0269/−0.0704、聚合 1.445）、E41 65.4%/40.2%、E51 1.4366→1.4470/82.6%/A5 1.4343、E61 严重度序列，均与表 1/表 2 及记录文档一致。
- M42 s2 的 1.64≈单侧 95% 正态分位数表述正确且限定为网格值。

## 总结论

- 第一次通读：**通过**（1 MINOR）。
- 第二次通读：**通过**（2 MINOR）。
- 第三次通读：**不通过**，存在 1 CRITICAL + 3 MAJOR，必须先修。

必须修的问题清单（按优先级）：

1. CRITICAL：M22 s2/M31 s2，`\label{eq:state}` 不在公式环境，`\eqref` 渲染为小节号——改公式环境或文字引用。
2. MAJOR：M11 s4，"as measured in §4.2"引用目标不含逐骨干原生缺失处理度量——改指表 1 或附录。
3. MAJOR：M42 s1（及 E13 s3/s5、E62 s4），parent 主文未定义先用——首次出现处补定义。
4. MAJOR：M13 s3，"visible target" 与不可得未来目标 Y 字面冲突——改写为目标通道可见部分或加注。

MINOR 共 8 项（摘要/正文术语定义、悬挂引用、范围维度、同值混淆、A1 证据、A2-F 表内缺失、significantly 措辞、the bank 前指），不阻断但建议同批处理；逐句修改方向见 audit CSV 的 revision 列。

---

## 修复闭环（2026-09-21，主代理执行）

全部 CRITICAL/MAJOR 与 8 项 MINOR 已在 tex 中修复并重新编译（38 页、0 错误、0 警告）：

1. CRITICAL eq:state：状态定义移入 equation 环境并保留 label，`\eqref{eq:state}` 现指向真实公式号。
2. MAJOR M11 s4：改指 `Table~\ref{tab:main}` 的 KEEP 行 + app:method-details。
3. MAJOR parent：§3.4 首次出现处补定义（非重叠 origin 窗口，指 app:splits）。
4. MAJOR M13 s3："visible target" 改为 "the visible part of the target channel in the context"。
5. MINOR harmful loss/HIR：§4.4 首用处补定义（代码口径核实：src/introact_ts/v47_verified/select.py:295，有害干预损失增量对全部请求平均）；§3.4 补 HIR 简释。
6. MINOR "the bank" 前指：改为 "the historical replay bank of \S\ref{sec:method-replay}"。
7. MINOR E21 s2：补 "across the catalog actions"。
8. MINOR 两个 19.3%：E22 补 "(a value that coincidentally matches the KEEP best share above)"。
9. MINOR A1 证据：§4.5 补 A1 结果句（1.475、100% 干预、HL 0.0697）。
10. MINOR A2-F 表外：补指针句至 app:estimation-analyses（含逐骨干区间）。
11. MINOR significantly：改回描述性措辞并补配对区间 [0.0012,0.0581] 与 [0.0035,0.0477]。
12. 悬挂引用：fig:concept 引用移至引言 I4 末尾（原 §4.2 句删除）。
