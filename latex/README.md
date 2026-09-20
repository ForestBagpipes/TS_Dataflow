# IntroAct-TS 论文

当前唯一论文入口为 `IntroActTS_20260920_v51.tex`，编译结果为同名 PDF。后续版本统一采用 `IntroActTS_YYYYMMDD_v版本号`。`math_commands.tex` 是模板支持文件。

## 图表与构建

图1和图2保留作者更新的 BMP 与 PPTX，EPS 由 BMP 无损封装得到。它们仍是位图，不会因转换 EPS 自动变为矢量。实验图3至图6由 Python 直接读取 `figure/data/` 中的 CSV 生成矢量 EPS，不经过 PowerPoint。

`scripts/build_figures.py` 统一控制字体、配色、线条和导出尺寸。柱状图从零开始，实验图无背景网格。CSV 保留原论文表格的显示精度，来源表标签和源稿 SHA-256 在 `figure/data/provenance.json`。

在项目根目录运行：

```powershell
python latex/scripts/build_paper.py
```

依赖 Python、Pillow、NumPy、Matplotlib、TeX Live 与 Ghostscript。构建脚本先生成 EPS，再转换用于编译的 PDF，随后执行 LaTeX、BibTeX 和交叉引用编译。任一步失败即停止。辅助文件及预览统一位于 `build/`。

## 证据范围

v51 是基于已有 v47 数值的文字与图表修订。主表逐骨干 MASE 已核对现存 JSON，实验图保持原表格数值。本轮没有新训练、预测或统计重算。既往测试结果参与过设计，因此正文披露事后评估边界。独立修复线 `v47_verified` 不由本次编译验收。

旧稿、旧脚本、旧实验图和审稿资料移至 `../archive/paper_20260920/`。原始实验结果保留原位。当前 `figure/` 只保留六张被引用的 EPS、图1图2原始资产和实验图数据。

## 展示约定

主实验和消融必须使用正文表格，保留精确数值。其他正文实验使用冷色图形，柱状图一律竖向。图3在两个并排面板中展示动作频率与效用，图4并列展示有害损失与干预频率，图5展示缺失程度趋势与最坏单元退步，图6为附录排名热图。后续更新遵循这一约定。

正文结论在第9页，紧接独立的 AI Use Statement，披露语言润色、文献检索与检查、代码准备和图形制作用途。当前实际引用的40条文献已逐项核查，记录见 ../docs/reference_audit_v51_20260920.json。折线图和柱状图统一字号、绘图区、图例位置和冷色编码，小数指标在图中明确标注单位缩放。
