# latex/ —— IntroAct-TS ICLR 2027 论文工程

本目录是论文的唯一 LaTeX 工作区。正文、附录、图源、参考文献都在这里维护，
不在仓库其他位置另存副本。

---

## 1. 目录结构

```
latex/
├── README.md                       # 本文件
├── iclr2027_conference.sty         # 官方 style，禁止修改
├── iclr2027_conference.bst         # 官方 bibstyle，禁止修改
├── fancyhdr.sty  natbib.sty  math_commands.tex   # 官方附带文件，禁止修改
├── references.bib                  # 唯一 bib 文件，只增量追加
├── introact_ts_iclr27_v44.tex      # 当前版本正文（v4.4-r2）
└── figure/
    ├── build_figures.py            # 单一几何定义，同时产出 .eps 与 .pptx
    ├── build_pdf.sh                # .eps -> .pdf（ghostscript）
    ├── build_all.sh                # 上面两步一起跑
    ├── preview.sh                  # 渲染 PNG 供人工核对
    ├── gsfonts/Fontmap             # Helvetica -> URW Nimbus 映射
    ├── fig1_selective_governance.{eps,pptx,pdf}
    ├── fig2_introact_architecture.{eps,pptx,pdf}
    ├── fig3_action_opportunity.{eps,pptx,pdf}
    ├── fig4_governance_diagnostics.{eps,pptx,pdf}
    └── fig5_robustness_missingness.{eps,pptx,pdf}
```

### 关于模板

`iclr-2027-style-files.zip` 由用户提供，已**原样解压使用，未作任何改动**。
不要替换成 ICLR 2026 或其他年份的 style，也不要"顺手修一下"这几个文件。
如果需要改版式（例如收紧浮动体间距），一律写在 `.tex` 的导言区，不改 `.sty`。

---

## 2. 编译

```bash
cd latex
pdflatex -interaction=nonstopmode introact_ts_iclr27_v44.tex
bibtex   introact_ts_iclr27_v44
pdflatex -interaction=nonstopmode introact_ts_iclr27_v44.tex
pdflatex -interaction=nonstopmode introact_ts_iclr27_v44.tex
```

- 首次编译或改了引用后，`.aux`/`.bbl` 需要重建，所以要跑完整四步。
- 只改正文文字时，两次 `pdflatex` 足够。
- **正文硬上限 9 页**（ICLR 2027 规定，initial submission）。
  AI use statement、Ethics statement、Reproducibility statement 与参考文献
  **不计入**页数。附录页数不限。
- 每次改完必须核对：
  - `grep "Output written" introact_ts_iclr27_v44.log` → 页数
  - `grep -c "Overfull" introact_ts_iclr27_v44.log` → 应为 0
  - `grep -oE "newlabel\{sec:conclusion\}\{\{[0-9]+\}\{[0-9]+\}" *.aux` → 结论必须在第 9 页
  - `grep -i undefined *.log` → 只应剩 `OT1/ptm/m/scit` 这条无害字体告警

---

## 3. 占位符规范（重要）

**任何尚未在服务器上真实跑出的数字，一律写成占位符，绝对不允许填估计值、
旧协议值或"看起来合理"的数。**

渲染形式：`\ph{KEY}` → 灰色等宽 `[KEY]`。填充时只替换 `KEY`，不要动 `\ph`。

### 命名规则（v4.4-r2 收窄后）

§36 任务书统一过的语义清晰的占位符 KEY，**填充时只替换 KEY，不要新增未列出的 KEY**：

| KEY | 含义 | 所属段 |
|---|---|---|
| `MAIN_OVERALL_MASE` | source-macro MASE 主表主指标 | Abstract / Main |
| `MAIN_GAIN_VS_BEST` | 相对最强已部署基线的差距 | Abstract |
| `MAIN_RANK` | 平均排名 | Main |
| `MAIN_INTERVENTION_RATE` | 介入率 | Abstract / Main |
| `NOOP_HARM` | no-op 层的 harmful loss | Abstract / §4.3 |
| `HIGHOP_GAIN` | high-opportunity 层 MASE | Abstract / §4.3 |
| `ROBUST_50` | 50% 缺失下的 MASE | §4.4 |
| `SUPPORT_25` | 25% replay 支持下的 MASE | §4.5 |
| `ABL_RANKING` | A1 (gain regression) 与 Full 的差 | §4.6 |
| `ABL_KEEP` | A5 (forced intervention) 与 Full 的差 | §4.6 |
| `LATENCY` | 请求延迟 | §4.2 / App. I |
| `CALLS` | 每请求模型调用数 | §4.2 / App. I |

正文里其它未列出的数字一律写成 `\<SCOPE>_<METHOD>_<METRIC>` 或
`\<METHOD>_<SEVERITY/PATTERN>_<METRIC>`。示例：

- `\ph{TOI_10}` = TOI 在 10% 缺失下的 MASE
- `\ph{CH2-OURS-RMSE}` = Chronos-2 上我们的 RMSE
- `\ph{OPPSENS_HALF_LOW}` = 机会分层敏感度（×0.5 边界，low 层 MASE）

`\ph` 的实现是 `\textsf{[\detokenize{#1}]}`，KEY 含下划线会被
`\detokenize` 转成普通字符，不会触发 math 下标错误。

表格里的其他约定：

- `\best{}` 加粗（可部署方法第一名），`\second{}` 下划线（第二名）。
- `\oracle{}` 灰色斜体，只给 Catalog Oracle（诊断用，不入排名、不入任何 claim）。
- ours 行加 `\rowcolor{bestgray}`。
- 宽表统一 `\setlength{\tabcolsep}{4pt}` + `\resizebox{\textwidth}{!}{...}`。
- 注意：`\resizebox` 到 `\textwidth` 后，表格高度由**内容比例**决定，
  改字号不会改变高度。想压高度只能减行数、减列数或改布局。

### 允许出现真实数字的唯一例外

Appendix "Negative Result from the Preceding Development Cycle"（`app:r5`）里的
6 个 MASE 值来自 v4.3.1-r5 冻结台账，是已独立审核的历史数字。该表必须保留
"旧协议、不可与本文任何表比较"的显式声明，不得删掉这句。

---

## 4. 图源维护（EPS + PPTX 双源）

图片源在 `figure/`，每张图有三份文件：

| 扩展名 | 用途 | 谁编辑 |
|---|---|---|
| `.pptx` | 可编辑源，方便手工微调 | 人 |
| `.eps` | 可编辑矢量源，脚本产出 | `build_figures.py` |
| `.pdf` | 供 `pdflatex` 直接插入 | `build_pdf.sh`（由 `.eps` 转出） |

### 工作流

```bash
cd latex/figure
bash build_all.sh      # 重新生成全部 .eps 和 .pdf
bash preview.sh        # 生成 _preview_*.png 人工核对
```

**约定：几何定义只有一处**，写在 `build_figures.py` 的 `Fig` 类里。
同一份定义同时输出 `.eps` 和 `.pptx`，两者内容必须一致。
不要手工改 `.eps` 后不回写脚本，否则下次重建会覆盖。

画布尺寸（pt）就是论文里的显示尺寸，图内字号就是真实字号（5.0–6.4pt）。
改图时先想清楚最终显示宽度，再定字号，不要靠 LaTeX 端缩放补救。

### 工具链依赖

- TeX Live 2025：`/d/texlive/2025/bin/windows/pdflatex`
- Ghostscript 10.04.0：`D:\texlive\2025\tlpkg\tlgs\bin\gswin64c.exe`
- `build_pdf.sh` 已处理三件容易踩的事：
  1. MSYS 会把 `/f/...` 错误转换，所以传参统一走 `cygpath -w`；
  2. `GS_LIB` 必须包含 `Resource/Init`、`lib`、`kanji`、`Resource/Font`、
     `Resource/CMap`、`Resource/Encoding`，且 `gsfonts` 要放在**最后**；
  3. 不要加 `-dSAFER`，否则加载不了自定义 Fontmap。
- 字体：tlgs 不带 Nimbus，`gsfonts/Fontmap` 把 `/Helvetica*` 映射到
  TeX Live 的 `uhv*8a.pfb`，配合 `GS_FONTPATH` 指向
  `texmf-dist/fonts/type1/urw/helvetic`。

### EPS 发射器的已知坑（改 `build_figures.py` 前务必读）

1. **每个图元前必须 `newpath`**。PostScript 路径会累积，漏掉 `newpath`
   会让后面的 `fill` 把前面所有图形一起重填，表现为颜色错位。
   正确顺序：`newpath → 路径 → fill → newpath → 路径 → stroke → newpath`。
2. 字体名必须带前导 `/`（`/Helvetica-Bold findfont`）。
3. 文字过程栈序是 `(string) x y PROC`，不是 `x y (string) PROC`。
4. `Lft/Ctr/Rgt` 过程内要先 `0 0 moveto` 再 `rmoveto`，否则报 `/nocurrentpoint`。
5. 不要用 Level-2 的 `rect` 算子，改用 `moveto/lineto/closepath`。
6. 图内文案只用纯 ASCII。不要写 `S$_a$`、`$^{a_0}$` 这类 LaTeX 残留，
   EPS 里不会渲染，会变成乱码或溢出。
7. 结果图（fig3–fig5）当前是**骨架**，坐标轴与面板已固定，
   数据点位置用占位符标注。等主实验产出 CSV 后再回填，不要凭印象画点。

---

## 4.5 当前正文浮动体配额（9 页硬约束下的取舍）

正文 9 页是硬上限，v4.4-r2 规划要求 6 表 + 5 图。实际收敛结果为
**正文 2 表 + 3 图**，其余下沉附录。这不是随意删减，每一条都有理由：

| 浮动体 | 位置 | 理由 |
|---|---|---|
| Figure 1 概念图 | 正文 p3 | §26 规划明确要求（三 episode + 决策流） |
| Figure 2 架构图 | 正文 p4 | §27 规划明确要求（offline/online 分隔线） |
| Figure 3 机会分层与改善 | 正文（→ Appendix E.4） | §28 优先给 §4.3；正文中以 prose 引导并指向 Appendix E.4 |
| Table 1 主结果 | 正文 p8 | §17 规划要求，核心表，含 Type 列 |
| Table 2 When Does Action Choice Matter? | 正文 p9 | §21 规划要求，按 $\Delta_i$ 分层 |
| Table 3 鲁棒性 | 正文 p9 | §22 规划要求，10/30/50% × worst pattern × avg rank |
| Table 4 历史支持效率 | → Appendix G | §23 规划要求作 Extra Experiment 3；表格下沉，§4.5 留 prose + 占位符 |
| Table 5 消融 | → Appendix H | §24 规划要求六行；表格下沉，§4.6 留 prose + 占位符 |
| Figure 4 治理诊断 | → Appendix F | 与 Table 2 同源，附录留图 |
| Figure 5 鲁棒性曲线 | → Appendix G | 与 Table 3 同源，附录留图 |

**v4.4-r2 正文基线固定为 5 个**：TOI（NeurIPS 2024）、TOI-VSF（TKDE 2025）、
GIMCC（KDD 2025）、SRDI（WWW 2026）、ChannelTokenFormer（ICLR 2026）。
VIDA（KDD 2025）只作 Appendix E.5 扩展对比，**不得静默替换任一正式 baseline**。
TATO 不再作为正文基线，仅留 Related Work + Appendix C 数据中心适应段。

**如果后续必须把某张图/表拉回正文**，就得从别处腾出等量空间。
可用的手段只有三个（按代价从小到大）：
1. 删正文里与附录重复的说明性段落；
2. 收图幅（当前 fig1 0.80 / fig2 0.62 / fig3 已下沉）；
3. 把某张正文表再下沉到附录。

注意 `\resizebox{\textwidth}{!}` 的表格改字号**不会**改变高度，见 §3。

---

## 5. 多版本维护

- 新版本另存为 `introact_ts_iclr27_v<N>.tex`，**不要覆盖**旧版本，
  这样出问题时能对照上一版。
- `references.bib` **从头到尾只有一个文件**，新文献增量追加，
  不新建 `references_v2.bib` 之类。
- 改 `references.bib` 时注意：中文注释里**不要出现以 `@` 开头的词**
  （例如 `@misc`、`@article`），bibtex 会把它们当成新条目开头并报
  `I was expecting a '{' or a '('`。
- 文件名里的 `v44` 对应规划版本，与 `docs/version_ledger.md` 的轮次对齐。

---

## 6. 写作约束（claim 边界）

这些是硬约束，不是风格建议：

- 在独立主实验完成前，正文**不得**出现 SOTA、significantly outperforms、
  safe、robust、generalizes 之类断言。
- 效率（时延、调用数）只能单独成表/成段，**不得**折进任何精度分数。
- Catalog Oracle 只作诊断上界，**不得**进入平均排名，**不得**写进 claim。
- 正文只保留 4.1 Setup / 4.2 Main / 4.3 Opportunity / 4.4 Robustness / 4.5 Historical Support / 4.6 Ablation 六节，每节的表格或图见 §4.5；其余全部进附录。
- 结果与失败一律保留，包括负结果；不得删掉不合意的配置。
- 正文提到的每个数字都必须能追溯到 `v44_*` 结果组中的一条记录，
  不允许手工转录。

---

## 7. 交付前自检清单

```bash
cd latex
pdflatex -interaction=nonstopmode introact_ts_iclr27_v44.tex
bibtex   introact_ts_iclr27_v44
pdflatex -interaction=nonstopmode introact_ts_iclr27_v44.tex
pdflatex -interaction=nonstopmode introact_ts_iclr27_v44.tex

grep "Output written"   introact_ts_iclr27_v44.log   # 页数
grep -c "Overfull"      introact_ts_iclr27_v44.log   # 必须为 0
grep -i "undefined"     introact_ts_iclr27_v44.log   # 只允许 scit 字体告警
grep -c "ph{"            introact_ts_iclr27_v44.tex   # 剩余占位符数量
```

- [ ] 结论（`sec:conclusion`）在第 9 页或更前
- [ ] `Overfull` 计数为 0
- [ ] 没有 `Reference ... undefined` / `Citation ... undefined`
- [ ] 没有残留的 `[RESULT_MAIN]` 式**假数字**（占位符 `\ph{}` 允许保留）
- [ ] Appendix `app:r5` 的旧协议免责声明仍在
- [ ] 新增文献已进 `references.bib` 且 bibtex 通过
