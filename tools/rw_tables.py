# -*- coding: utf-8 -*-
"""Hyperparameter section and the symbol column of table 3.

Algorithm boxes keep plain monospace text. Turning pseudocode into equation
objects would break its alignment, and the reference paper keeps its algorithm
listings as text as well. Their spacing is tidied instead.
"""
import re
import sys
sys.path.insert(0, "tools")
import docx
from docx_rewrite import count_math, find_paragraph, set_paragraph_md

PATH = "docx/胡宏彬-进度文档-20260819.docx"

SYMBOLS = {
    "K": r"$K$",
    "ε": r"$\varepsilon$",
    "η": r"$\eta$",
    "α": r"$\alpha$",
    "c_u": r"$c_{u}$",
    "c₀": r"$c_{0}$",
    "T_cal": r"$T_{\mathrm{cal}}$",
    "M": r"$M$",
}


def tidy_pseudocode(text):
    """Collapse padding runs of spaces, keep single spaces and line breaks."""
    out = []
    for line in text.split("\n"):
        line = re.sub(r" {2,}", "  ", line.rstrip())
        line = line.replace(" ,", ",").replace("( ", "(").replace(" )", ")")
        out.append(line)
    return "\n".join(out)


def main():
    d = docx.Document(PATH)
    before = count_math(d)

    set_paragraph_md(d.paragraphs[find_paragraph(d, "方法涉及的超参数见表 3")],
        r"方法涉及的超参数见表 3。其中结构失真阈值 $\tau$ 由共形标定确定，"
        "不需要人工调节，其余需要设定初值。")

    set_paragraph_md(d.paragraphs[find_paragraph(d, "调节顺序上")],
        r"调节顺序上，先固定目标损害率 $\alpha$ 并完成一次共形标定得到 $\tau$，"
        r"再在此基础上调整邻域大小 $K$ 与风险上界 $\eta$，最后调探索系数 $c_{u}$。"
        r"这样安排是因为 $\tau$ 决定了屏蔽后动作集的大小，它变化时策略面对的问题也随之变化，"
        r"应当在策略参数之前确定。$\varepsilon$ 的设定可以借助代理模型，"
        "在代理模型上测量同一批窗口的效用读数波动，取其标准差的十分之一作为初值，"
        r"这样既能滤掉噪声也不至于挡住真实改善。$c_{u}$ 的调节参考收敛曲线，"
        r"价值估计若在语料前段就趋于稳定说明探索过度，可以调低。"
        r"$T_{\mathrm{cal}}$ 控制可交换性偏移的累积，策略更新越频繁，重新标定就应当越密。")

    # 表 3 的符号列
    tb = d.tables[7]
    n_sym = 0
    for row in tb.rows[1:]:
        cell = row.cells[0]
        raw = cell.text.strip()
        if raw in SYMBOLS:
            set_paragraph_md(cell.paragraphs[0], SYMBOLS[raw])
            n_sym += 1

    # 算法框空白整理
    n_alg = 0
    for ti in (3, 4, 5):
        for row in d.tables[ti].rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    if p.text and re.search(r" {3,}", p.text):
                        new = tidy_pseudocode(p.text)
                        if new != p.text:
                            for r in p.runs[1:]:
                                r._element.getparent().remove(r._element)
                            if p.runs:
                                p.runs[0].text = new
                            n_alg += 1

    d.save(PATH)
    d2 = docx.Document(PATH)
    print(f"超参数表 {n_sym} 个符号转公式，算法框 {n_alg} 段整理，"
          f"公式 {before} -> {count_math(d2)}")


if __name__ == "__main__":
    main()
