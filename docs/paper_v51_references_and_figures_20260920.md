# v51 引用核查、AI 声明与图形修订

当前入口为 `latex/IntroActTS_20260920_v51.tex`，PDF 同名。

## ICLR 2027 格式与声明

核对日期为 2026-09-20。[官方作者指南](https://iclr.cc/Conferences/2027/AuthorGuidelines)规定初次投稿正文不超过 9 页，参考文献及 AI use statement 不计入正文页数。正文结论在第 9 页，AI Use Statement 作为独立无编号章节紧接结论。

声明补充文献检索和参考文献检查，保留原稿已有的代码准备、图形制作用途。[作者 AI 政策](https://iclr.cc/Conferences/2027/AIPolicyForAuthors)要求真实披露。用户提供的 only language polishing 和 no technical content 与已有工作记录不一致，因此没有写入这一排他断言。作者审核和责任承诺依据用户提供的声明保留，不表示工具代替作者完成研究真实性验收。

## 参考文献

核查当前正文和附录实际引用的 40 条记录。完整来源、修改字段和文献库哈希见 `reference_audit_v51_20260920.json`。保留未被当前论文引用的历史条目，不将其计入本轮核查结果。

Google Scholar 已逐项查询。DBLP 使用可公开检索的记录及作者目录，API 返回反机器人页面，未把该页面当作元数据。没有匹配 DBLP 记录的条目转向原始会议论文集、期刊、出版社及作者页面，不声称每条文献都完成了双数据库验证。

主要修正如下。

- S4M 原标题中的 Missing Data 改为正式标题 Missing Values。DBLP 会议记录将首位作者写为 Peng Jing，ICLR 原始论文集和 arXiv 为 Jing Peng，保留后者。
- Chronos-2 改用正式预印本标题 From Univariate to Universal Forecasting、完整作者表和 arXiv:2510.15821。保留预印本属性。
- Chronos-Bolt 改引 2024 年 12 月 2 日 AWS 官方发布说明，使用真实标题和四名署名作者。它是发布说明，不是同行评审论文，未找到匹配的独立 Scholar 论文记录。
- Counterfactual Risk Minimization 原记录混用了 ICML 标题和错误的 JMLR 卷页。改为 ICML 2015，PMLR 37，814–823。
- Chronos 补全 arXiv v3 的作者列表，包括 Hao Wang。不同版本作者列表有差异，未直接采用旧 DBLP 预印本列表。
- 补全 TimesFM、Moirai、GAIN、GIMCC、VIDA 的出版页码，以及若干期刊论文的 DOI。GAIN 的 DBLP 页码与原始 PMLR 不同，采用 PMLR 的 5689–5698。
- Bandit Algorithms 的一个 Scholar 记录显示 2019，出版社实际出版时间为 2020，保留 2020。

## 图形

使用 `research-writing-assistant:figures-python` skill。参考本地 AlphaEdit 第 7 页和 Learning Dynamics of LLM Finetuning 第 8 页，采用紧凑并排面板和共享视觉编码。用户要求优先于参考图中的网格与暖色，继续使用冷色、无背景网格。

动作效用的三个指标合并为两个面板，左侧分组柱对照 oracle-best 与 beneficial share，右侧为平均效用。KEEP 的 beneficial share 不定义，图中不虚构零值。柱状图保持竖向，类别和数值横排。较小指标采用明确标注的十进制单位缩放，避免旋转数值及长小数拥挤。

折线图使用空心与实心标记、不同线型及冷色区分方法。三张正文实验图保持相同画布、绘图区高度、字号层级、图例和轴位置。主实验及消融仍为正文表格。EPS 是正式图资产，450 dpi PNG 和 SVG 预览留在忽略的 build 目录。

图表读取原 CSV，没有新增实验、模拟数据、重算统计或更改结果。编译、引用完整性、原图像素一致性、数据来源、正文页数均由构建后的审计报告记录。
