# -*- coding: utf-8 -*-
"""Cut the baselines to seven and add the heterogeneity experiment.

Thirteen entries was too many to run on every non ablation table. Seven are kept
on three criteria, each has a locatable publication, together they cover both
families the problem sits between, and each one isolates something the others do
not. The scoring family keeps two of four because the four differ in estimator
rather than in what they produce, and the paper compares at the level of the
prepared corpus.
"""
import sys
sys.path.insert(0, "tools")
import docx
from docx_rewrite import (count_math, delete_paragraph, find_paragraph,
                          insert_after, set_paragraph_md)

PATH = "docx/胡宏彬-进度文档-20260820.docx"


def main():
    d = docx.Document(PATH)
    before = count_math(d)
    drop = []

    def rw(prefix, md):
        set_paragraph_md(d.paragraphs[find_paragraph(d, prefix)], md)

    rw("基线覆盖三条路线并包含参照下界与上界",
       "基线的选取有三条标准。每一项都有可查证的正式发表出处，"
       "全部基线合起来覆盖问题所处的两个方法族，"
       "每一项都隔离出其余各项不涉及的一个变量。"
       "按这三条筛选后保留七项，"
       "非消融实验的表格一律列全这七项，"
       "某项若因协议不适用而缺列，在表中标注不适用并于表注说明理由，不得省略该行。")
    rw("（6）Data Shapley[9]与（7）Data-OOB[10]代表通用数据估值",
       "（1）不治理，作为参照下界，其损害恒为零，"
       "用于确认任何非零损害都来自方法本身而不是评测流程。"
       "（2）SCREEN[5]，速度约束下的局部最优修复，代表约束驱动的清洗路线，"
       "隔离的变量是修复规则完全由领域约束给定时能走到哪里。"
       "（3）IMR[6]，自回归模型迭代修复，代表统计建模驱动的清洗路线，"
       "隔离的变量是把修复依据从人工约束换成数据自身的统计结构。"
       "（4）MTCSC[8]的单变量分支，2024 年的速度约束工作，"
       "它与 SCREEN 的编辑重合度分窗口、改动位置与修复取值三个层次实测，"
       "三个层次都高度一致才合并为一行，否则各自单列。")
    rw("为分离策略学习与屏蔽各自的作用，另设四种对照",
       "（5）TimeInf[11]，把影响函数定义在时间块上再聚合到时间点，"
       "代表打分式选择路线中面向时序设计的一支。"
       "打分族的四项工作在产出形式上一致，都给样本分数再按分数取舍，"
       "彼此的差别在估值器而不在产出，"
       "而本文的比较发生在整备后语料这一层，"
       "因此保留面向时序的 TimeInf 与通用估值中开销最低的 Data-OOB[10]两项，"
       "（6）Data-OOB 用袋外估计给出样本价值，"
       "隔离的变量是估值方法忽略时间依赖时会损失什么。"
       "Data Shapley 与 TSRating 不单列，前者与 Data-OOB 同属博弈论估值而开销高出一个量级，"
       "后者依赖外部大模型判断，其可得性不由本文控制。"
       "（7）学习策略不配屏蔽，即把算子直接作用于原数据，"
       "代表同期强化学习清洗方案的做法，隔离的变量是屏蔽本身的有无。")
    drop.append("（10）固定规则策略配屏蔽代表本文的早期版本")
    rw("非消融实验的表格一律列全上述十三项",
       "软惩罚、单信号屏蔽与随机策略三种对照只在针对裁决方式与策略来源的两组实验中出现，"
       "它们改变的是本文方法内部的一个环节而不是一个独立的已发表方法，"
       "因此不计入基线清单，在对应实验中作为本文方法的变体列出。"
       "消融实验只含本文方法的各档变体，不要求含基线。")

    # 新增异质性实验
    i = find_paragraph(d, "实验八量化各模块的边际贡献")
    set_paragraph_md(d.paragraphs[i],
       "实验八检验同类校准与弃权的生效条件。"
       "3.1 节指出同类校准的收益依赖语料存在结构异质性，在同质语料上应当趋于零，"
       "这一点给出了可检验的预测。"
       "构造异质性递增的语料序列，从单一工业来源开始逐步混入金融场景的窗口，"
       "异质性用画像空间中窗口两两距离的分散程度度量，度量方式在实验开始前定死。"
       "在每个异质性水平上比较同类校准与全局标准化两种做法的损害与修复，"
       "并统计弃权的触发次数。"
       "若收益随异质性单调上升则该解释成立，"
       "若在任何异质性水平下都没有差别，则这两个模块在本文设定下不必要，"
       "应当如实报告并考虑简化方法。")
    insert_after(d, i, [
        "实验九量化各模块的边际贡献并检验方法对超参数的稳健性。"
        "消融包含无屏蔽、无效用条件、无结构条件、无同类校准、无策略学习、"
        "无预算分配、无候选注入与完整方法八档，每档报告损害与修复两栏，"
        "并额外报告每次编辑的平均损害与平均修复，以消除编辑数差异的干扰。"
        r"敏感性部分扫描目标损害率 $\alpha$、探索系数 $c_{u}$、注入概率 $p_{\mathrm{inj}}$ "
        r"与标定间隔 $T_{\mathrm{cal}}$，"
        "其中标定间隔一档用于检验定理 6 给出的退化上界与实测退化是否吻合，"
        "并统计各状态下置信上界间隔的经验分布，"
        "以判断该定理所需的间隔条件在本文设定中是否成立。",
    ], template_idx=i)

    rw("本章给出后续实验的规划",
       "本章给出后续实验的规划，先说明数据、噪声注入、基线、指标与超参数的设置，"
       "再按九组实验说明各自的目标与配置。"
       "前四组衡量治理后的数据质量，后五组衡量智能体的决策质量本身。")

    for prefix in drop:
        try:
            delete_paragraph(d.paragraphs[find_paragraph(d, prefix)])
        except LookupError:
            print("  未找到:", prefix[:24])

    d.save(PATH)
    d2 = docx.Document(PATH)
    print(f"基线收敛与实验补充完成，公式 {before} -> {count_math(d2)}")


if __name__ == "__main__":
    main()
