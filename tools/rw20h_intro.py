# -*- coding: utf-8 -*-
"""Rebuild the introduction along the seven step chain.

The order is scope, definition, problem, survey, limitation, method,
contribution. What was missing before is the first two steps and the last one,
so the reader met an operator level dispute before being told what a good corpus
is supposed to look like, and met three contributions that answered nothing in
particular.

Table 1 returns in a different shape. The version deleted earlier listed one
method per row against seven attribute columns, which is a log. This one groups
by route so the reader carries away three ideas rather than ten names, and its
judgement time column is the axis the whole paper turns on.
"""
import copy
import sys
sys.path.insert(0, "tools")
import docx
from docx.oxml.ns import qn
from docx_rewrite import (count_math, delete_paragraph, find_paragraph,
                          insert_after, set_paragraph_md)

PATH = "docx/胡宏彬-进度文档-20260820.docx"

TABLE1 = [
    ("路线", "代表工作", "判定时刻", "判定依据", "判错之后"),
    ("修复式清洗", "SCREEN[5] IMR[6] MTCSC[8]", "执行之前", "先验约束或自回归残差", "原值已被覆盖"),
    ("打分式选择", "Data Shapley[9] Data-OOB[10]\nTimeInf[11] TSRating[12]",
     "不产生动作", "样本对模型的估计贡献", "整窗丢弃"),
    ("学习式编排", "清洗智能体[13]", "执行之前", "下游反馈的期望回报", "痕迹留在语料上"),
    ("本文", "IntroAct-TS", "执行之后", "模型效用与时序结构合取", "撤回且不留痕迹"),
]


def make_table(doc, anchor_par, rows):
    """Insert a table right after the anchor paragraph."""
    tb = doc.add_table(rows=len(rows), cols=len(rows[0]))
    try:
        tb.style = doc.tables[0].style
    except Exception:
        pass
    for r, vals in zip(tb.rows, rows):
        for cell, v in zip(r.cells, vals):
            p = cell.paragraphs[0]
            if p.runs:
                p.runs[0].text = v
            else:
                p.add_run(v)
    anchor_par._p.addnext(tb._tbl)
    return tb


def main():
    d = docx.Document(PATH)
    before = count_math(d)
    drop = []

    def rw(prefix, md):
        set_paragraph_md(d.paragraphs[find_paragraph(d, prefix)], md)

    # 第一步 宏大，把场景与语料具象化
    rw("时序基础模型在大规模多来源语料上预训练",
       "设备状态监测、电力负荷调度与金融风险评估正在把预测任务交给同一类模型。"
       "时序基础模型在大规模多来源语料上预训练，"
       "再迁移到预测、分类与插补等下游任务[1-4]，"
       "一套权重覆盖了此前需要逐个场景单独建模的工作。"
       "随着模型结构收敛到少数几种成熟设计，能力的上限不再由架构决定。"
       "决定它的是投喂进去的语料，"
       "也就是从传感器、交易系统与监测终端持续采集下来的原始时序记录，"
       "这些记录规模巨大且未经整理。")

    # 第二步 定义，先给判断标准
    i = find_paragraph(d, "设备状态监测、电力负荷调度与金融风险评估")
    insert_after(d, i, [
        "一份可用于预训练的时序语料应当同时满足两个条件。"
        "一是结构完备，语料要覆盖设备或市场实际出现过的各种运行模态，"
        "既包括常规工况，也包括状态切换与罕见但真实发生的极端事件，"
        "模型只有在训练中见过这些形态，部署时才可能认得出来。"
        "二是信噪可控，传感器故障、通信丢包与记录错误带来的失真应当尽量少，"
        "这类失真一旦留在语料里就会被模型当作规律学习。"
        "原始采集在这两个条件上都没有保证，"
        "而两者还会彼此纠缠，因为削掉失真的动作同样会削掉极端事件。",
    ], template_idx=i)

    # 第三步 问题
    j = find_paragraph(d, "一份可用于预训练的时序语料应当同时满足两个条件")
    insert_after(d, j, [
        "把这两个条件同时做到，难点在于判断某一次具体的修改该不该做。"
        "以电力变压器监测语料为例，设备检修期间的一段水平漂移应当处理，"
        "它会让模型把异常水平当作正常基线，"
        "在随后的正常时段给出系统性偏高的预测，误差可以持续到漂移结束很久之后。"
        "而一次真实发生的负荷突增在波形上与故障尖峰几乎一致，"
        "它却正是结构完备性所依赖的那部分数据，削掉它等于删去模型最需要学习的稀有模态。"
        "两者的区别不在算子也不在参数，"
        "同一个去尖峰算子带同样的参数施加下去，前者是修复，后者是破坏，"
        "结果取决于那段数据里原本承载着什么。"
        "有害与否因此无法在动作执行之前判定，"
        "这是本文要处理的核心困难。",
    ], template_idx=j)

    # 第四步 梳理，先总说再分路线，表 1 统领
    rw("面对这一困难，已有工作分两条路线",
       "围绕这一困难，已有工作沿三条路线展开，各自的判定时刻与判错后果见表 1。")

    k = find_paragraph(d, "围绕这一困难，已有工作沿三条路线展开")
    par = d.paragraphs[k]
    # 表题在表格之前
    insert_after(d, k, ["表 1 面向时序数据的治理与选择方法对比"], template_idx=k)
    title = d.paragraphs[find_paragraph(d, "表 1 面向时序数据的治理与选择方法对比")]
    make_table(d, title, TABLE1)

    rw("（1）SCREEN[5]假设相邻时间步的取值变化存在上下界",
       "修复式清洗依靠先验规则定生死。"
       "SCREEN[5]假设相邻时间步的取值变化存在上下界，把违反约束的点拉回最近的合法取值，"
       "IMR[6]改用自回归模型逐点估计并迭代收敛，"
       "MTCSC[8]把速度约束与聚类结合以利用维度之间的相关性。"
       "这条路线的判定发生在选定算子的那一刻，"
       "规则一旦给出，改写就直接作用在原值上。")
    rw("（5）Data Shapley[9]用合作博弈中的 Shapley 值刻画样本价值",
       "打分式选择只估值不动手。"
       "Data Shapley[9]用合作博弈中的 Shapley 值刻画样本对模型的贡献，"
       "Data-OOB[10]借助袋外估计把这一估计的开销降到可接受范围，"
       "TimeInf[11]把影响函数定义在时间块上以保留时序结构，"
       "TSRating[12]则用大模型的成对比较蒸馏出轻量评分器。"
       "这条路线产出的是分数与排序，语料按分数取舍而不被改写。")
    rw("（9）近期出现的清洗智能体",
       "学习式编排让策略从反馈中改进。"
       "清洗智能体[13]用分层策略决定在什么窗口上调用哪个清洗算子，"
       "并把下游误差的变化作为回报。"
       "策略确实可以随训练变好，代价是算子在训练过程中立即生效。")

    # 第五步 局限，写成对立
    rw("两条路线在同一处停下",
       "三条路线各有代价，而代价的形状恰好互补。"
       "修复式清洗动了手，判定时刻与执行时刻却重合在一起，选错就是破坏，没有回头的余地。"
       "打分式选择留住了安全，因为它根本不动手，"
       "代价是面对一段只在局部含有尖峰的窗口只能整体丢弃，尖峰之外完好的部分一并舍去。"
       "学习式编排试图兼得，让策略从错误中学习，"
       "可它的每一次错误探索都真实地落在语料上，学得越多损坏越多。"
       "三者共同的盲区在于都把判定放在了执行之前，"
       "而一次编辑是否有害，答案写在执行之后的效果里。")

    d.save(PATH)
    for p in drop:
        delete_paragraph(p)
    d.save(PATH)
    d2 = docx.Document(PATH)
    print(f"引言前五步完成，表格 {len(d.tables)} -> {len(d2.tables)}，"
          f"公式 {before} -> {count_math(d2)}")


if __name__ == "__main__":
    main()
