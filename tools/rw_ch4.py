# -*- coding: utf-8 -*-
"""Chapter 4. Removes measured results from what is a planning chapter, thins
the dataset and baseline tables, and moves their content into prose."""
import sys
sys.path.insert(0, "tools")
import docx
from docx_rewrite import (count_math, delete_paragraph, find_paragraph,
                          insert_after, set_paragraph_md)

PATH = "docx/胡宏彬-进度文档-20260819.docx"


def thin_table(doc, table_idx, keep_cols):
    """Drop columns from a table, keeping the given zero based indices."""
    tb = doc.tables[table_idx]
    ncols = len(tb.columns)
    drop = [c for c in range(ncols) if c not in keep_cols]
    for row in tb.rows:
        cells = row.cells
        for c in sorted(drop, reverse=True):
            tc = cells[c]._tc
            tc.getparent().remove(tc)
    grid = tb._tbl.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblGrid")
    if grid is not None:
        cols = list(grid)
        for c in sorted(drop, reverse=True):
            if c < len(cols):
                grid.remove(cols[c])
    return len(drop)


def main():
    d = docx.Document(PATH)
    before = count_math(d)
    drop = []

    def rw(prefix, md):
        set_paragraph_md(d.paragraphs[find_paragraph(d, prefix)], md)

    def kill(prefix):
        drop.append(d.paragraphs[find_paragraph(d, prefix)])

    rw("本章给出后续实验的完整规划",
       "本章给出后续实验的规划。4.1 节说明数据、缺陷注入、基线、指标与超参数的设置，"
       "4.2 节按八组实验分别给出设计目标与具体配置。"
       "前四组衡量治理后的数据质量，后四组衡量智能体的决策质量本身。")

    # 4.1.1 数据集，表凝练为三列，其余进正文
    rw("计划使用的数据集见表 2",
       "计划使用的数据集见表 2。这几个数据集是长期时序预测的通用基准[23,24]，"
       "与时序基础模型的评测设定一致，便于与已有工作对照。"
       "ETTh1、ETTh2、ETTm1 与 ETTm2 取自 Informer[23]，采样频率分别为小时与十五分钟。"
       "Electricity、Traffic 与 Weather 取自 Autoformer[24]，"
       "覆盖电力、交通与气象，其中 Weather 为十分钟采样。"
       "采样频率从十分钟到日跨越三个量级，可以检验方法对时间粒度的敏感性。"
       "Exchange 同样取自 Autoformer[24]，为日频金融数据，趋势缓慢且季节性弱，"
       "与其余数据集的结构差异明显，因此不作主语料，只用作真实跨域的对照层。")

    # 4.1.3 基线，删掉两段实测判定
    kill("关于 MTCSC 是否单列的实测判定")
    kill("据此判定 MTCSC 单变量分支在全基线表中单独列出")
    rw("（2）修复式清洗",
       "（2）修复式清洗。SCREEN[5]基于速度约束做局部最优修复，"
       "IMR[6]通过自回归模型迭代修复，MTCSC[8]的单变量分支代表 2024 年的工作。"
       "MTCSC 与 SCREEN 同属速度约束修复，是否单列由二者在本文语料上的编辑重合度决定，"
       "重合度分窗口、改动位置与修复取值三个层次测量，"
       "只有三个层次都高度一致才合并为一行，否则各自单列。"
       "这一族在本文中同时承担两个角色，既作为独立方法参与对比，"
       "也作为提议者接入本文的屏蔽层，用以检验屏蔽与策略是否与具体的动作来源解耦。")

    rw("（4）策略与裁决方式对照",
       "（4）策略与裁决方式对照。为分离策略学习与屏蔽各自的作用，计划实现四种对照。"
       "固定规则策略配屏蔽代表本文的早期版本，随机策略配屏蔽给出策略学习收益的下界，"
       "学习策略不配屏蔽即把算子直接作用于原数据，代表已有强化学习清洗方案的做法，"
       "只对效用信号做共形标定的单信号屏蔽用于说明合取的必要性。")

    rw("（5）两套评测协议",
       "（5）两套评测协议。上述基线分属不同族，产出形式不同，"
       "因此采用两套协议以保证每一项都能参与比较。"
       "语料层协议下各方法产出整备后的语料，用同一下游模型训练并报同一组指标，"
       "打分族与清洗族在此层完全可比。"
       "候选层协议用于需要逐动作裁决的分析，例如接受率与撤销原因的拆解，"
       "参与者为清洗族与本文方法，打分族不产出逐动作决策，在此层标注为不适用。")

    rw("（6）全基线清单",
       "（6）全基线清单。非消融实验的表格一律列全以下各项，"
       "参照下界与上界、清洗族的 SCREEN 与 IMR 与 MTCSC 单变量分支、"
       "打分族的 Data Shapley 与 Data-OOB 与 TimeInf 与 TSRating、"
       "以及裁决方式对照的软惩罚与单信号屏蔽与规约式否决与无屏蔽。"
       "某方法若因协议不适用而缺项，在表中标注不适用并于表注说明理由，不得省略该行。"
       "消融实验只含本文方法的各档变体，不要求含基线。")

    # 4.1.4 指标，补下游模型引用
    rw("数据质量组包含四个维度",
       "数据质量组包含四个维度。安全性维度包括受保护层误编辑数、过度清洗率、编辑精度、"
       "被破坏窗口数与方差破坏比例。效用维度同时报告模型效用增益与对干净参考的保真度改善，"
       "两列在表中相邻放置，便于观察它们在特定缺陷上是否给出方向相反的结论。"
       "风险控制维度包括目标风险水平与实测损害率的对照、按受保护层拆分的达标情况"
       "以及可达风险下界。下游维度在治理后的语料上训练 PatchTST[25]与 DLinear[26]并报误差，"
       "两者分别代表基于注意力与基于线性映射的预测器，采用配对口径以隔离语料采样带来的方差。")

    # 4.1.6 删掉实测数字，只留设定
    rw("画像簇数 k 取 12",
       r"画像簇数 $k$ 的选取判据是占用率不低于 0.75 的最大取值，"
       "占用率指固定规则策略实际访问过的簇与算子组合占全部组合的比例，"
       "它决定了暖启动能够从历史填充的格子有多少。"
       "该判据只读取覆盖率，不读取任何显著性结果。"
       r"$k$ 的候选取值为 10、12、15 与 20，四者的完整结果全部保留作为敏感性分析。")
    rw("画像簇并非分层标签的重述",
       "画像簇是否只是分层标签的重述，用簇与分层标签的调整互信息检验。"
       "若两者高度一致，则接受率随簇变化这一现象只是接受率随分层变化的换一种说法，"
       "而分层信息 CDP 已经以缺陷假设的形式给出，策略学习不会带来新信息。"
       "该检验在策略学习开始之前完成。")
    rw("策略学习的训练语料与评测语料按窗口划分且不重叠",
       "策略学习的训练语料与评测语料按窗口划分且不重叠，划分随机种子在实验开始前写定，"
       "训练占四成评测占六成，按分层做分层抽样使两侧都按比例含全部六层。"
       "种子写定而非运行时选取，可以避免重跑落到更有利的划分上。"
       "评测集取较大的一半，所有主要指标都在其上报告。")

    for p in drop:
        delete_paragraph(p)

    # 表 2 数据集，九列压到三列
    n1 = thin_table(d, 6, keep_cols=[0, 2, 4])
    # 表 1 方法对比，去掉可由正文说明的三列
    n2 = thin_table(d, 0, keep_cols=[0, 1, 2, 3, 4, 5, 6])

    d.save(PATH)
    d2 = docx.Document(PATH)
    print(f"第 4 章前半完成，删段 {len(drop)}，表 2 去 {n1} 列，表 1 去 {n2} 列，"
          f"公式 {before} -> {count_math(d2)}")


if __name__ == "__main__":
    main()
