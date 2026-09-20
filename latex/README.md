# IntroAct-TS 论文

当前唯一论文入口为 `IntroActTS_20260920_v48.tex`，编译结果为同名 PDF。后续版本统一采用 `IntroActTS_YYYYMMDD_v版本号`。`math_commands.tex` 是模板支持文件。

## 图表与构建

图1和图2保留作者更新的 BMP 与 PPTX，EPS 由 BMP 无损封装得到。它们仍是位图，不会因转换 EPS 自动变为矢量。实验图3至图5由 Python 直接读取 `figure/data/` 中的 CSV 生成矢量 EPS，不经过 PowerPoint。

`scripts/build_figures.py` 统一控制字体、配色、线条和导出尺寸。柱状图从零开始，实验图无背景网格。CSV 保留原论文表格的显示精度，来源表标签和源稿 SHA-256 在 `figure/data/provenance.json`。

在项目根目录运行：

```powershell
python latex/scripts/build_paper.py
```

依赖 Python、Pillow、NumPy、Matplotlib、TeX Live 与 Ghostscript。构建脚本先生成 EPS，再转换用于编译的 PDF，随后执行 LaTeX、BibTeX 和交叉引用编译。任一步失败即停止。辅助文件及预览统一位于 `build/`。

## 证据范围

v48 是基于已有 v47 数值的文字与图表修订。主表逐骨干 MASE 已核对现存 JSON，实验图保持原表格数值。本轮没有新训练、预测或统计重算。既往测试结果参与过设计，因此正文披露事后评估边界。独立修复线 `v47_verified` 不由本次编译验收。

旧稿、旧脚本、旧实验图和审稿资料移至 `../archive/paper_20260920/`。原始实验结果保留原位。当前 `figure/` 只保留五张被引用的 EPS、图1图2原始资产和实验图数据。
