# -*- coding: utf-8 -*-
"""Line C. Four findings that need a place in the document.

MTCSC's three level overlap goes into chapter 6 rather than the planning
chapter, written as a general practice for deciding whether two baselines are
the same method. The optimistic initialisation and RESEGMENT interaction goes
into 3.4 so the arm's absence early in learning is not read as a defect. The
clip percentile lower bound goes into 3.4 with the evidence for it. The code
hash mechanism goes into 6.3 as a reproducibility note.
"""
import sys
sys.path.insert(0, "tools")
import docx
from docx_rewrite import (count_math, find_paragraph, insert_after,
                          set_paragraph_md)

PATH = "docx/胡宏彬-进度文档-20260819.docx"


def main():
    d = docx.Document(PATH)
    before = count_math(d)

    # 一 乐观初始化与重分段的交互，接在暖启动段之后
    i = find_paragraph(d, "暖启动用固定规则策略的历史轨迹填充")
    insert_after(d, i, [
        "乐观初始化与重分段一列的取值之间存在一个需要说清的交互。"
        "重分段整列取全局均值 0.6095，而历史从未访问过的格子取乐观初值 1.0，"
        "后者高于前者，因此上置信界在学习早期会先去访问空格，重分段要到空格被填得差不多之后"
        "才可能被选中。这是乐观初始化按设计驱动探索的结果，"
        "配合阶段零已经证明重分段没有簇级结构，"
        "早期不访问它并不会损失可学的信息，也不构成实现缺陷。",
    ], template_idx=i)

    # 二 截断阈值下界依据，接在截断段之后
    j = find_paragraph(d, "接受奖励需要设上界")
    insert_after(d, j, [
        "分位数的下界有实测依据。取 90 与 95 与 99 三档重建价值表并比较策略在同一语料上选出的动作，"
        "95 与 99 两档选中同一动作的窗口比例为 0.9860，价值表全序的肯德尔相关系数为 0.9759，"
        "两档之间几乎没有差别。90 分位对应的截断值为 1.7014，"
        "该取值已经压到奖励分布的主体而不只是尾部，约一成窗口因此选中不同动作。"
        "据此把 95 分位作为下界，更低的取值改变的不再是极端值而是分布本身。",
    ], template_idx=j)

    # 三 MTCSC 三层重合，进第 6 章，写成一般性做法
    k = find_paragraph(d, "候选有害率的高值主要由语料构成决定")
    insert_after(d, k, [
        "判断两个基线是否为同一方法需要分层测量。"
        "SCREEN 与 MTCSC 的单变量分支同属速度约束修复，是否单列在实现之前先做了实测。"
        "在 2000 个窗口上给二者相同的速度约束，使差异只来自修复规则，"
        "分窗口、改动位置与修复取值三个层次比较。"
        "窗口层次上二者编辑了完全相同的 823 个窗口，杰卡德系数为 1.0000，六个分层无一例外。"
        "点层次上改动位置的杰卡德系数为 0.7021。"
        "值层次上，在二者都改动的 17790 个位置中，修复到相同数值的仅 67 个即 0.0038，"
        "两种修复的差距以窗口自身干净序列标准差为单位计，中位数为 0.4450 倍，"
        "只有百分之十三点五七的位置差距小于 0.1 倍标准差。",
        "三个层次给出方向相反的答案，只测窗口层次会得到完全重合的结论，"
        "而二者实际上定位相同的问题却给出实质不同的修复，中位差距接近半个标准差，"
        "落到损害与修复指标上必然是两个读数。据此判定单列，这也是同时列出 SCREEN 与 MTCSC 的理由。"
        "这一经验适用于任何同族基线的取舍，"
        "只在一个层次上测量重合度可能得出与另一个层次相反的结论。",
    ], template_idx=k)

    # 四 代码哈希机制，进 6.3 进度
    m = find_paragraph(d, "前三个模块的实现已经完成并通过测试")
    insert_after(d, m, [
        "长时间运行的实验统一经监控工具启动，它在进入主循环之前做前置断言，"
        "检查模型池大小、输出目录可写、磁盘余量与配置哈希，任一不满足即中止而不是继续。"
        "部署环境由文件同步得到，本身不携带版本库信息，"
        "因此版本标识改为对方法层源文件取组合哈希，缺失的文件记为 MISSING 而不是跳过，"
        "这样残缺部署与完整部署不会得到相同的哈希。"
        "运行过程中按固定间隔写心跳，其中带上最近一次落盘文件的修改时间，"
        "用以区分仍在推进与已经卡住。运行结束时把产出文件的摘要与行数写入清单并纳入版本管理，"
        "避免结果只留在容器内而没有入库。",
    ], template_idx=m)

    d.save(PATH)
    d2 = docx.Document(PATH)
    print(f"线 C 四处落地完成，段落 {len(d.paragraphs)} -> {len(d2.paragraphs)}，"
          f"公式 {before} -> {count_math(d2)}")


if __name__ == "__main__":
    main()
