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
├── IntroActTS_20260918_v45_review.tex   # 当前版本正文（评审日志落地版）
├── introact_ts_iclr27_v44.tex      # 上一版，保留不动，仅作对照
└── figure/
    ├── build_figures.py            # 单一几何定义，同时产出 .eps 与 .pptx
    ├── build_pdf.sh                # .eps -> .pdf（ghostscript）
    ├── build_all.sh                # 上面两步一起跑
    ├── preview.sh                  # 渲染 PNG 供人工核对
    ├── fig1_stats.json             # Figure 1(a) 的真实统计输入，schema 见 §4
    ├── gsfonts/Fontmap             # Helvetica -> URW Nimbus 映射
    ├── fig1_selective_governance.{eps,pptx,pdf}    # 正文 Figure 1
    ├── fig2_introact_architecture.{eps,pptx,pdf}   # 正文 Figure 2
    ├── fig3_why_selective.{eps,pptx,pdf}           # 正文 Figure 3
    ├── fig4_governance_diagnostics.{eps,pptx,pdf}  # 附录 D
    └── fig5_robustness_missingness.{eps,pptx,pdf}  # 附录 C
```

### 关于模板

`iclr-2027-style-files.zip` 由用户提供，已**原样解压使用，未作任何改动**。
不要替换成 ICLR 2026 或其他年份的 style，也不要"顺手修一下"这几个文件。
如果需要改版式（例如收紧浮动体间距），一律写在 `.tex` 的导言区，不改 `.sty`。

官方模板 `iclr2027_conference.tex` 已确认：AI use statement、Ethics statement、
Reproducibility statement 三段均注明 **"does not count toward the page limit"**，
参考文献也不计入。因此页数核算口径是**从标题到 Conclusion 结束**。

---

## 2. 编译

```bash
cd latex
pdflatex -interaction=nonstopmode IntroActTS_20260918_v45_review.tex
bibtex   IntroActTS_20260918_v45_review
pdflatex -interaction=nonstopmode IntroActTS_20260918_v45_review.tex
pdflatex -interaction=nonstopmode IntroActTS_20260918_v45_review.tex
```

- 首次编译或改了引用后，`.aux`/`.bbl` 需要重建，所以要跑完整四步。
- 只改正文文字时，两次 `pdflatex` 足够。
- **正文硬上限 9 页**（ICLR 2027 规定，initial submission）。
- 每次改完必须核对：

```bash
grep "Output written" *.log                      # 页数
grep -c "Overfull"    *.log                      # 必须为 0
grep -i "undefined"   *.log                      # 必须为空
grep -oE "newlabel\{sec:conclusion\}\{\{[0-9]+\}\{[0-9]+\}" *.aux   # 结论必须 ≤ 第 9 页
grep -c "ph{" *.tex                              # 剩余占位符数量
```

- 常见报错 `I can't write on file '...out'` 是上一轮 pdflatex 的句柄未释放，
  等 2 秒重跑即可，不要删 `.aux`。

---

## 3. 占位符规范（重要）

**任何尚未在服务器上真实跑出的数字，一律写成占位符，绝对不允许填估计值、
旧协议值或"看起来合理"的数。**

渲染形式：`\ph{KEY}` → 灰色等宽 `[KEY]`。填充时只替换 `KEY`，不要动 `\ph`。
实现是 `\textsf{[\detokenize{#1}]}`，KEY 含下划线会被 `\detokenize` 转成普通字符，
不会触发 math 下标错误。

### 3.1 v46 的占位符家族

v46 共 **1111** 个唯一 KEY。完整清单见 `docs/v46_placeholder_keys.csv`
（两列 `key,family`，无 `other` 残留），实验侧的执行规划见
`docs/IntroActTS_20260918_v46_experiment_plan.md` §10。

主表 roster 已冻结为 `Native KEEP / Best Fixed / R2-CART / T1 / TOI / TATO / SRDI`
加 `IntroAct-TS`，`ChannelTokenFormer` 只作 **external forecasting reference**
（Overall 与成本，无 per-backbone 列，不入 rank），`Catalog Oracle` 只作灰色诊断。
附录 C 的 10/30/50 severity 表使用同一套七方法（不含 SRDI）。
`VIDA`、`GIMCC` 只出现在附录 B 的 extended comparison，`GIMCC` 不跑，
`VIDA` 因无官方实现完全不跑。

| family | 数量 | 键模式 |
|---|---|---|
| `table1_per_source_cell` | 432 | `SRC_<BACK>_<METHOD>_<H>_<SRC>`，`<BACK>` ∈ `BOLT/TF/CH2`，`<METHOD>` ∈ `KEEP/BF/R2/T1/TOI/TATO/SRDI/OURS/ORACLE`，`<H>` ∈ `96/192`，`<SRC>` ∈ `ETTH1/ETTH2/ETTM1/ETTM2/ELEC/EXCH/TRAF/WEA` |
| `appendix_severity_table` | 109 | `SEV<10/30/50>-<METHOD>-<MASE/RMSE/MAE/MSE/RANK>` |
| `appendix_ablation` | 55 | `AF_<FULL/A1..A5/ORACLE>_<MASE/RMSE/MAE/MSE/CHIR/HL/IR/CALLS>` |
| `table2_harm` | 55 | `HARM_<IR/HIR/HL/BP/MO/MASE>[_<METHOD>]`、`HARM_RISKCURVE`、`HARM_READING` |
| `table1_per_source_macro` | 54 | `SRC_<BACK>_<METHOD>_<H>_MACRO` |
| `table1_ranked_cell` | 53 | `<METHOD>_<BOLT/TF/CH2/OVR/RMSSE/RANK>`，`<METHOD>` ∈ 上表八行 |
| `appendix_cost` | 47 | `CALLS_*`、`COST_*`、`<METHOD>_<CAND/CALLS/MEAN/MAX/P95/OFF>` |
| `table4_ablation` | 47 | `ABL_<FULL/A1..A5/ORACLE>_<MASE/HIR/HL/IR/CALLS/LAT>`、`ABL_READING` |
| `appendix_per_pattern` | 40 | `P<1..4>_<METHOD>`、`PR_<METHOD>` |
| `table3_robustness` | 40 | `RB_<METHOD>_<10/30/50/CH2/WORST>`、`ROBUST_*` |
| `appendix_mask_stability` | 25 | `SEED1..3_<MASE/DELTA/IR>`、`SEED_SPREAD_<BOLT/CH2>`、`SEED_IR_SPREAD_<BOLT/CH2>`、`SEED_MASK/ORDER/SELECTOR` |
| `appendix_operating_points` | 24 | `NOOP_<METHOD>`、`LOWOP_<METHOD>`、`HIGHOP_<METHOD>` |
| `narrative_sentence` | 22 | `MAIN_READING`、`HARM_READING`、`ABL_READING`、`ROBUST_READING`、`RANK_DISAGREE_STATS`、`DISCORDANT_RATE`、`CONCLUSION_CLOSING`、`CONCL_*`、`ABSTRACT_CLOSING`、`COLDSTART`、`STRONG_BASELINE` |
| `appendix_opportunity_strata` | 20 | `OVR_<METHOD>`、`STRATUM_<NOOP/LOW/HIGH>_<N/SHARE/MED/P90>` |
| `appendix_extended_comparison` | 18 | `TOIVSF_<BOLT/TF/CH2/OVR/RANK>`、`CTF_<OVR/RMSSE/OFF/CAND/CALLS/MEAN/P95/MAX>` |
| `appendix_reconstruction` | 17 | `REC_<T1/TOI/SRDI>_<MASE/MAE/MSE/GAIN>`、`RECON_ORACLE_MASE`、`RHO_<BOLT/TF/CH2>`、`DISCORDANT_RATE` |
| `appendix_replay_size` | 15 | `RS<25/50/100>_<MASE/IR/HIR/HL/CALLS>`（只跑 IntroAct-TS 自己的 bank） |
| `appendix_protocol_counts` | 14 | `TEST_*`、`FIT_*`、`GATE_*`、`EVAL_*` |
| `appendix_gate_grid` | 12 | `OPPSENS_<HALF/ONE/TWO>_<LOW/HIGH/NOOP/OVR>` |
| `appendix_reproducibility` | 11 | `REV_<BOLT/TF/CH2>`、`PYVERSION`、`NUMPYVERSION`、`PANDASVERSION`、`SKLEARNVERSION`、`TORCHVERSION`、`HARDWARE`、`PRECISION`、`PROTOCOL_COMMIT` |
| `doc_comment` | 1 | 文件头注释里的示例键，不是真实占位符 |

**已移除的 family（不要再为它们建键）**：`supplementary_finance`（`FIN*`）、
`appendix_baseline_roster`（`VIDA_*`）、`ABL_STAB_*` / `ABL_RANKFULL_*`（ordering
stability）、`SUPPORT<25/50/100>_<METHOD>`（全 baseline historical-support refit）、
`OFFLINE_<METHOD>`。这五类在 v45 里存在，在 v46 里已随实验一起删除。

### 3.2 填充纪律

1. **只替换 `KEY`**，不要顺手重写周围句子。句子已按「不用引号、破折号、分号」
   的文风写死，改句子会破坏全文一致性。
2. **数字格式统一**：MASE / RMSSE / MAE / RMSE / MSE 保留 3 位小数；
   百分比保留 1 位小数；call count 用整数；延迟用毫秒整数。
3. **不要新增表格行**。Table 1–4 的行集合已冻结，增行会破坏 9 页预算。
4. **一致性断言**：`SRC_*_MACRO` 必须等于对应 `SRC_*_<SRC>` 的 source-macro 聚合；
   `<METHOD>_OVR` 必须与 `SRC_*_<METHOD>_*_MACRO` 的聚合一致。回填脚本里加断言。
5. **不要新增未列出的 KEY**。若确实需要，先更新本文 §3.1 与
   `docs/v46_placeholder_keys.csv`，再在 `.tex` 里使用。

表格里的其他约定：

- `\best{}` 加粗（可部署方法第一名），`\second{}` 下划线（第二名）。
- `\oracle{}` 灰色斜体，只给 Catalog Oracle（诊断用，不入排名、不入任何 claim）。
- ours 行加 `\rowcolor{bestgray}`。
- 宽表统一 `\setlength{\tabcolsep}{4pt}` + `\resizebox{\textwidth}{!}{...}`。
- 注意：`\resizebox` 到 `\textwidth` 后，表格高度由**内容比例**决定，
  改字号不会改变高度。想压高度只能减行数、减列数或改布局。

### 3.3 允许出现真实数字的唯一例外

补遗里的 Development Negative Results 保留了上一轮的负结果数值，那是已经跑出的真实
记录，可以留。**Financial Case Study 在 v46 里已从 LaTeX 隐藏**：这一版没有现成的
natural-missingness 结果，重新跑要新增数据集，因此整节与 `tab:app-finance` 一并删除，
`FIN*` 占位符清零。若将来补上 verified natural-missingness 结果再恢复该节，
必须同时保留「case study only，不可与主表比较」的显式声明。

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

### `fig1_stats.json`（Figure 1(a) 的真实统计输入）

Figure 1(a) 直接读这个文件；**文件缺失时脚本画虚线占位，绝不造数**。

```json
{
  "best_action_share": {
    "KEEP": 0.0,
    "FFILL": 0.0,
    "SINGLE_TSICL": 0.0,
    "MULTI_TSICL": 0.0,
    "CONTEXT_RIDGE": 0.0
  },
  "best_fixed_gap": 0.0,
  "n_episodes": 0,
  "protocol_seed": 0
}
```

- 五个键就是 `src/introact_ts/v44/protocol.py` 里的 `ACTIONS`，顺序即 frozen catalog
  order。不要再用 `MEAN_IMPUTE / LOCF / CHANNEL_MEDIAN / INTERP`，那套名字在代码里
  不存在。
- `best_action_share`：每个 catalog action 成为 oracle-best 的 episode 占比，五键和为 1。
  打平按 frozen catalog order 取第一个，与附录 A 的 diagnostic conventions 一致。
- `best_fixed_gap`：best fixed catalog action 与 catalog oracle 的 source-macro MASE 差距；
- `n_episodes`：参与统计的 evaluation episode 数；
- 生成后重跑 `build_figures.py` 重出 `.eps/.pdf/.pptx`。

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
- `python-pptx` 装在隔离环境里，用
  `C:\Users\lzfd\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe` 跑脚本。

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

## 5. 正文浮动体配额（9 页硬约束下的取舍）

正文 9 页是硬上限。v45 的收敛结果为**正文 3 图 + 4 表**，附录收敛为 A–G 七块
加一个无编号 supplementary。

| 浮动体 | 位置 | 内容 |
|---|---|---|
| Figure 1 | 正文 §1 | 真实 TEST 统计（a）+ Replay → Match → Act/Keep 方法概览（b, c） |
| Figure 2 架构图 | 正文 §3 | **必须留在正文**，offline / online 双路径 |
| Figure 3 | 正文 §4.2 | (a) reconstruction rank vs utility rank；(b) risk–intervention curve |
| Table 1 主比较 | 正文 §4.3 | 10% severity，5 published + KEEP + BEST FIXED + R2-CART + Ours + Oracle diagnostic |
| Table 2 harm | 正文 §4.4 | MASE / IR / Conditional HIR / HL / BP / MO |
| Table 3 robustness | 正文 §4.5 | 10/30/50 severity + Chronos-2 configuration transfer |
| Table 4 ablation + cost | 正文 §4.6 | Full / A1–A5 + Reconstruction Oracle diagnostic |
| Figure 4 | 附录 D | 治理诊断曲线 |
| Figure 5 | 附录 C | 鲁棒性趋势 |

**如果后续必须把某张图/表拉回正文**，就得从别处腾出等量空间。可用的手段只有
三个（按代价从小到大）：

1. 把正文里的说明性段落继续下沉到附录（**首选**，用户已明确允许）；
2. 收图幅；
3. 把某张正文表再下沉到附录。

**禁止把架构图（Figure 2）移到附录。** 这是用户的明确要求。

附录结构固定为 A–G：

| 附录 | 内容 |
|---|---|
| A | Protocol、最终 TEST split、action catalog、features、missingness、metric conventions、diagnostic counting rules、replay bank 构造与 size |
| B | full per-source / per-pattern 结果、opportunity strata、extended comparison（TOI-VSF / GIMCC） |
| C | robustness core set 的 full severity 结果 |
| D | reconstruction / utility 诊断与 Reconstruction Oracle |
| E | full ablations、$k/\beta$ gate grid、3-mask stability |
| F | cost、failures、latency、memory |
| G | reproducibility / manifests / code and model revisions |

---

## 6. 多版本维护

**版本化命名约定**（用户 2026-09-18 明确要求）：

```
<项目名>_<YYYYMMDD>_v<NN>_<阶段名>.tex
例：IntroActTS_20260918_v45_review.tex
```

- **每次改动新建一个版本文件，不要覆盖旧版本。** 这样出问题时能对照上一版。
- `introact_ts_iclr27_v44.tex` 是 v44，已提交状态，**保留不动**，仅作对照。
- `references.bib` **从头到尾只有一个文件**，新文献增量追加，
  不新建 `references_v2.bib` 之类。
- 改 `references.bib` 时注意：中文注释里**不要出现以 `@` 开头的词**
  （例如 `@misc`、`@article`），bibtex 会把它们当成新条目开头并报
  `I was expecting a '{' or a '('`。
- 交付前清理临时文件（例如页面渲染用的 `*pg-*.png`），不要留在目录里。

---

## 7. 写作约束（claim 边界）

这些是硬约束，不是风格建议：

- 在独立主实验完成前，正文**不得**出现 SOTA、significantly outperforms、
  safe、robust、generalizes 之类断言。
- **文风**：自然、凝练、直白。不用比喻修辞；不用引号、破折号、分号；
  不要公式化；少用"不是……而是……"式转折；不要罗列名词。
- 效率（时延、调用数）只能单独成表/成段，**不得**折进任何精度分数。
- Catalog Oracle 只作诊断上界，**不得**进入平均排名，**不得**写进 claim。
- ChannelTokenFormer 只作 **external forecasting reference**：只报 Overall 与成本，
  不给 per-backbone 列，不进 rank，不进 Table 2（它没有 frozen backbone 上的 reference
  forecast，harm 的定义对它不成立）。
- Reconstruction 表只收真正输出 hidden-position 重建的方法（T1 / TOI / SRDI）。
  IntroAct-TS 不进该排名，它返回的是执行输入后的预测，不是重建。
- Chronos-2 只能称 **configuration transfer**，不能称 replay-bank transfer。
- 30/50 severity 只能称 **within-grid robustness**，不能声称 50% unseen，
  且必须与 Table 3 使用同一套七方法。
- 结果与失败一律保留，包括负结果；不得删掉不合意的配置。
- 正文提到的每个数字都必须能追溯到结果组中的一条记录，不允许手工转录。

---

## 8. 交付前自检清单

```bash
cd latex
pdflatex -interaction=nonstopmode IntroActTS_20260918_v45_review.tex
bibtex   IntroActTS_20260918_v45_review
pdflatex -interaction=nonstopmode IntroActTS_20260918_v45_review.tex
pdflatex -interaction=nonstopmode IntroActTS_20260918_v45_review.tex

grep "Output written" *.log    # 页数
grep -c "Overfull"    *.log    # 必须为 0
grep -i "undefined"   *.log    # 必须为空
grep -c "ph{"         *.tex    # 剩余占位符数量
```

- [ ] 结论（`sec:conclusion`）在第 9 页或更前
- [ ] `Overfull` 计数为 0
- [ ] 没有 `Reference ... undefined` / `Citation ... undefined`
- [ ] 没有重复 `\label`
- [ ] 没有残留的假数字（占位符 `\ph{}` 允许保留）
- [ ] 架构图（Figure 2）仍在正文
- [ ] 没有 v46 已删除 family 的残留键（`FIN*`、`VIDA_*`、`SUPPORT*`、`ABL_STAB_*`、`OFFLINE_*`）
- [ ] `fig1_stats.json` 的五个 action 键是 `KEEP/FFILL/SINGLE_TSICL/MULTI_TSICL/CONTEXT_RIDGE`
- [ ] 新增文献已进 `references.bib` 且 bibtex 通过
- [ ] 临时文件已清理
