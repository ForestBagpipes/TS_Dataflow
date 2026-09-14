# v4.3.1-r2 执行报告

本轮完成证据状态一致的候选和两家族共同开发评估；没有方法晋升。PICS_joint_relabel保持历史incumbent，calibration/test封存。所有训练、推断、统计及测试均在当前服务器，复用三个环境与两家族权重，GPU顺序执行。原26个DEV parent永久保留已使用身份，不因换方法而重新称独立确认。

## STOP退步的代码事实

旧v431完整agent的STOP动作来自自身D2基础树，实际156/156与强制STOP的D2完全一致，MASE1.200158。与固定TSICL不同不构成违约：旧实现从未约定STOP总是TSICL。相对TSICL，26个候选/预测真正改变，3改善23恶化；主要错误来自Solar。例699489…的shared窗口进入cov_missing高/scale低叶5选KEEP，MASE4.868631，对应TSICL及CART2.727376。完整UID、特征、叶路径、candidate/prediction hash见[逐窗审计](v431_r2_stop_audit.md)。

旧获取标签没有正收益：history108条全零，mask106零2负且来自同一Solar parent；lambda=0。未发现无证据调用全证据模型、未取得工具填零当已知、旧terminal hash、隐藏cache结果影响STOP或费用二次扣罚。18个获取parent限制可分裂能力，但标签本身无正收益才是此次全STOP的直接证据，不能泛泛归因于26个DEV太少。

## 本轮实现与冻结

`v431_r2/policy.py:StatePolicy`为none/mask/history/both建立明确状态。none采用各家族75个训练parent独立选出的固定TSICL参照，完整有限target强制KEEP。mask/history/both各自只训练和读取其已取得列；支持量、全缺列剔除和有效性flag均属于当前已取得工具。原五臂只填NaN，ridge不支持显式回KEEP；没有预测后残差修正。

普通CART沿用depth3/minleaf96/实际叶至少16parent/seed101，不搜索新深度。旧同证据CART保持原T_fit54作为对照；r2取消本轮不需要的gate配置搜索，合并T_fit54与T_gate21为75拟合parent，T_check17和T_acq18不变。状态集合hash与模型落盘之后，才产生648条同冻结策略前后真实任务损失/完整成本差标签，三种分支mask/history/both，后者是两工具而非一次免费组合。lambda原0/公式规则仅在T_acq LOPO选择，两家族均选0。

完整分支预算沿用low/high，无根据DEV降阈值。获取器每叶16parent，18父组仍只能根叶；TimesFM选择有正平均价值的mask，不能声称已学得丰富的逐窗取证边界。所有固定取证CART与r2共享终态、特征、监督、候选、预算；区别只在获取决策。允许成本替代的任务误差容忍预登记为0 MASE，不事后放宽。

## 真实训练支持与学习曲线

ETTm1/Solar/USTS原train独立704跨度parent为59/44/7，共110，全部已用；64上限未截断任何来源。此前TimesFM train真实预测为0，本轮补齐相同110父组的任务和历史输出，没有拿DEV选固定ridge。75是训练分区复用而非新增原始数据；ETTh与ETTm同步/降采样、Crypto过短DEV等未当独立新支持混入。

固定T_check17的嵌套18/37/75曲线如下，check及acq从未入任何拟合子集，始终使用100%作主候选，没有按检查成绩选择比例。

| 家族 | 拟合parent | 全证据检查MASE | 同子集固定参照 |
|---|---:|---:|---:|
| bolt | 18 | 1.390925 | 1.328637 |
| bolt | 37 | 1.390925 | 1.328637 |
| bolt | 75 | 1.334069 | 1.328637 |
| timesfm | 18 | 1.226401 | 1.162536 |
| timesfm | 37 | 1.226401 | 1.162536 |
| timesfm | 75 | 1.150880 | 1.162536 |

增加拟合支持改善两家族全证据检查损失，但Bolt仍未胜其固定参照；TimesFM有检查点估计改善。18/37阶段表现相同与实际叶支持有关。曲线不能证明继续加数据必然有效，更未解决获取训练仍18parent的问题。

## 原共同DEV效果与机制

| 模型 | 方法 | MASE ↓ | 批量秒/窗 |
|---|---|---:|---:|
| bolt | EXISTING_SAME_EVIDENCE_CART | 1.136486 | 0.657985 |
| bolt | FIXED_ACQUIRE_CART_high | 1.214872 | 0.472348 |
| bolt | FIXED_REFERENCE | 1.157005 | 0.120142 |
| bolt | FIXED_TSICL | 1.157005 | 0.120142 |
| bolt | KEEP | 1.258454 | 0.089880 |
| bolt | R2_AGENT_high | 1.157005 | 0.122043 |
| timesfm | EXISTING_SAME_EVIDENCE_CART | 1.069086 | 1.072156 |
| timesfm | FIXED_ACQUIRE_CART_high | 1.069398 | 0.340510 |
| timesfm | FIXED_REFERENCE | 1.096135 | 0.230020 |
| timesfm | FIXED_TSICL | 1.096135 | 0.230020 |
| timesfm | KEEP | 1.139837 | 0.200703 |
| timesfm | R2_AGENT_high | 1.069398 | 0.340542 |
| bolt | TATO_8_NATIVE_SPACE | 1.685227 | 0.703174 |
| timesfm | TATO_8_NATIVE_SPACE | 1.529002 | 1.023989 |

Bolt r2全部STOP，与训练固定参照精确同预测1.157005；这是修复无证据策略退化的工程正确性，不是新增研究收益。TimesFM r2为1.069398，相对固定TSICL1.096135改善，但与修正后的固定mask CART完全相同。普通全证据CART1.069086还略优。因此没有证据支持主动获取超越同信息固定取证；其细微计时差不当作系统性成本优势。

相同窗口按source和相邻两个parent的时间块进行2000次配对bootstrap，所有六变体同组。详细点估计/区间：

{
  "bolt": {
    "R2_AGENT_high__vs__FIXED_REFERENCE": {
      "reference": "FIXED_REFERENCE",
      "gain_mase": 0.0,
      "interval_95": [
        0.0,
        0.0
      ],
      "bootstrap_repeats": 2000,
      "seed": 101,
      "grouping": "source-stratified adjacent-two-parent time blocks; all six variants stay grouped",
      "sources": {
        "ETTm1": {
          "parent_count": 14,
          "time_blocks": 7,
          "mean_gain": 0.0
        },
        "Solar": {
          "parent_count": 11,
          "time_blocks": 6,
          "mean_gain": 0.0
        },
        "US_Term_Structure": {
          "parent_count": 1,
          "time_blocks": 1,
          "mean_gain": 0.0
        }
      },
      "interpretation": "exploratory repeatedly used DEV; one USTS block cannot estimate its sampling variation"
    },
    "R2_AGENT_high__vs__FIXED_ACQUIRE_CART_high": {
      "reference": "FIXED_ACQUIRE_CART_high",
      "gain_mase": 0.05786757457026559,
      "interval_95": [
        0.014807837571027707,
        0.10218650313853658
      ],
      "bootstrap_repeats": 2000,
      "seed": 101,
      "grouping": "source-stratified adjacent-two-parent time blocks; all six variants stay grouped",
      "sources": {
        "ETTm1": {
          "parent_count": 14,
          "time_blocks": 7,
          "mean_gain": 0.007095615546042449
        },
        "Solar": {
          "parent_count": 11,
          "time_blocks": 6,
          "mean_gain": 0.16728053533883824
        },
        "US_Term_Structure": {
          "parent_count": 1,
          "time_blocks": 1,
          "mean_gain": -0.0007734271740839257
        }
      },
      "interpretation": "exploratory repeatedly used DEV; one USTS block cannot estimate its sampling variation"
    },
    "EXISTING_SAME_EVIDENCE_CART__vs__FIXED_REFERENCE": {
      "reference": "FIXED_REFERENCE",
      "gain_mase": 0.020518738661159785,
      "interval_95": [
        -0.007849275830321897,
        0.07016467331805033
      ],
      "bootstrap_repeats": 2000,
      "seed": 101,
      "grouping": "source-stratified adjacent-two-parent time blocks; all six variants stay grouped",
      "sources": {
        "ETTm1": {
          "parent_count": 14,
          "time_blocks": 7,
          "mean_gain": 0.06078278880939543
        },
        "Solar": {
          "parent_count": 11,
          "time_blocks": 6,
          "mean_gain": 0.0
        },
        "US_Term_Structure": {
          "parent_count": 1,
          "time_blocks": 1,
          "mean_gain": 0.0007734271740839257
        }
      },
      "interpretation": "exploratory repeatedly used DEV; one USTS block cannot estimate its sampling variation"
    },
    "FIXED_ACQUIRE_CART_high__vs__FIXED_REFERENCE": {
      "reference": "FIXED_REFERENCE",
      "gain_mase": -0.05786757457026559,
      "interval_95": [
        -0.10218650313853658,
        -0.014807837571027752
      ],
      "bootstrap_repeats": 2000,
      "seed": 101,
      "grouping": "source-stratified adjacent-two-parent time blocks; all six variants stay grouped",
      "sources": {
        "ETTm1": {
          "parent_count": 14,
          "time_blocks": 7,
          "mean_gain": -0.007095615546042449
        },
        "Solar": {
          "parent_count": 11,
          "time_blocks": 6,
          "mean_gain": -0.16728053533883824
        },
        "US_Term_Structure": {
          "parent_count": 1,
          "time_blocks": 1,
          "mean_gain": 0.0007734271740839257
        }
      },
      "interpretation": "exploratory repeatedly used DEV; one USTS block cannot estimate its sampling variation"
    }
  },
  "timesfm": {
    "R2_AGENT_high__vs__FIXED_REFERENCE": {
      "reference": "FIXED_REFERENCE",
      "gain_mase": 0.02673700745741962,
      "interval_95": [
        -0.007460989983484029,
        0.06741750271240245
      ],
      "bootstrap_repeats": 2000,
      "seed": 101,
      "grouping": "source-stratified adjacent-two-parent time blocks; all six variants stay grouped",
      "sources": {
        "ETTm1": {
          "parent_count": 14,
          "time_blocks": 7,
          "mean_gain": 0.028142205371952975
        },
        "Solar": {
          "parent_count": 11,
          "time_blocks": 6,
          "mean_gain": 0.052068817000305884
        },
        "US_Term_Structure": {
          "parent_count": 1,
          "time_blocks": 1,
          "mean_gain": 0.0
        }
      },
      "interpretation": "exploratory repeatedly used DEV; one USTS block cannot estimate its sampling variation"
    },
    "R2_AGENT_high__vs__FIXED_ACQUIRE_CART_high": {
      "reference": "FIXED_ACQUIRE_CART_high",
      "gain_mase": 0.0,
      "interval_95": [
        0.0,
        0.0
      ],
      "bootstrap_repeats": 2000,
      "seed": 101,
      "grouping": "source-stratified adjacent-two-parent time blocks; all six variants stay grouped",
      "sources": {
        "ETTm1": {
          "parent_count": 14,
          "time_blocks": 7,
          "mean_gain": 0.0
        },
        "Solar": {
          "parent_count": 11,
          "time_blocks": 6,
          "mean_gain": 0.0
        },
        "US_Term_Structure": {
          "parent_count": 1,
          "time_blocks": 1,
          "mean_gain": 0.0
        }
      },
      "interpretation": "exploratory repeatedly used DEV; one USTS block cannot estimate its sampling variation"
    },
    "EXISTING_SAME_EVIDENCE_CART__vs__FIXED_REFERENCE": {
      "reference": "FIXED_REFERENCE",
      "gain_mase": 0.027048994210504915,
      "interval_95": [
        -0.007149003230398732,
        0.06772948946548775
      ],
      "bootstrap_repeats": 2000,
      "seed": 101,
      "grouping": "source-stratified adjacent-two-parent time blocks; all six variants stay grouped",
      "sources": {
        "ETTm1": {
          "parent_count": 14,
          "time_blocks": 7,
          "mean_gain": 0.028142205371952975
        },
        "Solar": {
          "parent_count": 11,
          "time_blocks": 6,
          "mean_gain": 0.052068817000305884
        },
        "US_Term_Structure": {
          "parent_count": 1,
          "time_blocks": 1,
          "mean_gain": 0.0009359602592558894
        }
      },
      "interpretation": "exploratory repeatedly used DEV; one USTS block cannot estimate its sampling variation"
    },
    "FIXED_ACQUIRE_CART_high__vs__FIXED_REFERENCE": {
      "reference": "FIXED_REFERENCE",
      "gain_mase": 0.02673700745741962,
      "interval_95": [
        -0.007460989983484029,
        0.06741750271240245
      ],
      "bootstrap_repeats": 2000,
      "seed": 101,
      "grouping": "source-stratified adjacent-two-parent time blocks; all six variants stay grouped",
      "sources": {
        "ETTm1": {
          "parent_count": 14,
          "time_blocks": 7,
          "mean_gain": 0.028142205371952975
        },
        "Solar": {
          "parent_count": 11,
          "time_blocks": 6,
          "mean_gain": 0.052068817000305884
        },
        "US_Term_Structure": {
          "parent_count": 1,
          "time_blocks": 1,
          "mean_gain": 0.0
        }
      },
      "interpretation": "exploratory repeatedly used DEV; one USTS block cannot estimate its sampling variation"
    }
  }
}

区间只为重复使用DEV的开发诊断，USTS只有一个parent/一个时间块，无法估计其独立抽样变异；两个模型家族也不是两份独立数据。没有确认性SOTA或显著性晋升。TATO沿用两家族8trial原生空间短预算适配，低预算超支和不支持trial均保留，不能称官方完整复现。

## 金融身份、完整观测与缺口

身份以作者固定CSV和原供应方为证据，本地train数值与作者float32处理语义逐元素匹配。Oil目标0是Europe Brent spot，USD/barrel；USTS目标0是FwdRate_Fitted_1Y/THREEFF0100.B，百分点，为Kim–Wright拟合远期利率而非成交价格。USTS常在下周发布并可能回改，作者快照缺历史vintage；金融结果均不声称严格PIT或预测时点原始版本可恢复。详见[金融审计](v431_r2_financial_audit.md)。

旧工作日网格的原生NaN没有可靠“应有观测缺失”分类，不能把节假日算丢失交易。独立financial-observation-index-r1附表只选择作者快照中全字段有记录的日期，保留原日期/原始行映射/原值，完全在旧train/dev原始边界内；这不是声称当日实际发布。两来源各1个DEV parent，H96/H192为未来96/192条记录事件，MASE为train事件序列lag5，新预处理协议和分母均明确登记，不能与旧B网格MASE横比。

未来记录存在模式由回顾性快照定义，仅evaluator持有future日期/原始行映射，不进入agent。完整有效观测子集上的五臂应全为KEEP同输入/预测，治理额外计算仍计费；受控删除只用于检验缺口处理，不能把该完整案例选择说成来源本身无缺口。无可靠自然缺口/休市分类数据时，自然缺口结果明确缺项；原始大幅变化保持不覆盖。

| 家族 | 方法 | 条件/范围 | MASE ↓ | 秒/窗 |
|---|---|---|---:|---:|
| bolt | EXISTING_SAME_EVIDENCE_CART | 全部 | 3.088108 | 5.145917 |
| bolt | FIXED_ACQUIRE_CART_high | 全部 | 3.069683 | 3.733802 |
| bolt | FIXED_ACQUIRE_CART_low | 全部 | 2.820959 | 1.466814 |
| bolt | FIXED_REFERENCE | 全部 | 3.069683 | 1.184308 |
| bolt | FIXED_TSICL | 全部 | 3.069683 | 1.184308 |
| bolt | KEEP | 全部 | 2.820959 | 0.475021 |
| bolt | R2_AGENT_high | 全部 | 3.069683 | 1.186296 |
| bolt | R2_AGENT_low | 全部 | 3.069683 | 1.186422 |
| bolt | TATO_NATIVE_8TRIALS_OBSERVED_LINEAR | 全部 | 4.698655 | 1.034955 |
| timesfm | EXISTING_SAME_EVIDENCE_CART | 全部 | 4.890237 | 4.347875 |
| timesfm | FIXED_ACQUIRE_CART_high | 全部 | 4.890237 | 1.575240 |
| timesfm | FIXED_ACQUIRE_CART_low | 全部 | 4.890237 | 1.575307 |
| timesfm | FIXED_REFERENCE | 全部 | 5.212728 | 0.956247 |
| timesfm | FIXED_TSICL | 全部 | 5.212728 | 0.956247 |
| timesfm | KEEP | 全部 | 5.225872 | 0.247486 |
| timesfm | R2_AGENT_high | 全部 | 4.890237 | 1.575274 |
| timesfm | R2_AGENT_low | 全部 | 4.890237 | 1.575391 |
| timesfm | TATO_NATIVE_8TRIALS_OBSERVED_LINEAR | 全部 | 4.980245 | 1.396753 |


金融两parent的DEV日期不重叠，TRAIN共同有限日期1242个，水平Pearson为−0.142379。Oil未来4行已见于旧pilot，USTS H192未来161行已见于旧DEV，不能称未访问或独立确认。小样本及拟合利率与商品报价口径差异限制外推。该附表是冻结策略迁移诊断，不是金融任务上独立重新开发或确认。金融8次mask为离线策略回放，尚非金融按需在线执行。40个跨家族完整观测输入和预测no-op检查通过。固定方法未执行预算门不表示预算内；完整超预算审计见金融目录budget_flag_audit.json，所有失败及低预算超支保留。

## 在线与完整成本

{
  "bolt": {
    "status": "completed",
    "exit_code": 0,
    "worker_pid": 22773,
    "process_wall_seconds": 14.532727478999732,
    "scope": "entire validation worker, including natural and controlled cases, startup and exit",
    "finished_at": "2026-09-14T16:44:27.604239+00:00",
    "requests": 12,
    "hot_request_seconds": 3.8881743689998984,
    "model_startup_seconds": 8.602828151000722,
    "remaining_process_overhead_seconds": 2.0417249589991115,
    "natural_requests": 7,
    "controlled_requests": 5,
    "natural_hot_seconds": 1.961042516998532,
    "natural_actual_tool_calls": 0,
    "controlled_actual_tool_calls": 4,
    "natural_complete_budget_overruns": 0,
    "controlled_complete_budget_overruns": 1,
    "allocation_limit": "Complete per-case allocation includes this controlled validation workload; not standalone natural-only cold latency"
  },
  "timesfm": {
    "status": "completed",
    "exit_code": 0,
    "worker_pid": 23022,
    "process_wall_seconds": 15.639779476999138,
    "scope": "entire validation worker, including natural and controlled cases, startup and exit",
    "finished_at": "2026-09-14T16:44:43.296852+00:00",
    "requests": 10,
    "hot_request_seconds": 4.841731962999802,
    "model_startup_seconds": 8.904448494001372,
    "remaining_process_overhead_seconds": 1.8935990199979642,
    "natural_requests": 7,
    "controlled_requests": 3,
    "natural_hot_seconds": 4.028969099000278,
    "natural_actual_tool_calls": 6,
    "controlled_actual_tool_calls": 1,
    "natural_complete_budget_overruns": 0,
    "controlled_complete_budget_overruns": 1,
    "allocation_limit": "Complete per-case allocation includes this controlled validation workload; not standalone natural-only cold latency"
  }
}

TimesFM自然7窗真实调用6次mask，Bolt自然7窗全STOP；另有完整raw STOP、B0拒取证、真实工具执行后故障回退，以及必要受控mask/both。受控调用不算自然策略收益。失败耗费及最终回退真实预测全部记录；B0仍需最终预测，明确超支，不声称硬wallclock零成本。

主表补计初始选择/适用性和旧CART推断的实测费用到accounted派生账本，原模型/标签/预测SHA不变。训练搜索、旧缓存生成、TimesFM新增3504唯一真实调用/5010请求577.032秒、在线模型启动/热请求/完整验证worker分别列账；缓存省重复实验时间，不抹掉已发生生成成本。在线冷启动分摊包含受控case，不能冒称natural-only冷延迟。

## 交付、限制和下一步

可执行入口：`v431_r2_predict.py`、`v431_r2_fit.py`、`v431_r2_online.py`、金融inputs/collect/score、独立verify、account和report。状态模型、标签、分区、逐窗输入/预测/特征、成本和原始失败保留在`results/v431-r2/`。只运行本轮相关测试；真实输出复核状态以verification和两online独立报告为准。精简审阅包包含实际命令、resolved config、支持清单、代码、少量原始轨迹和SHA，不含权重或凭据。

当前允许的主张：固定TSFM的缺口治理存在任务差异；证据状态和无证据固定参照可正确实现；TimesFM遮挡CART有开发点估计收益；自然在线取证已实际执行。不能声称主动决策优于同信息固定取证、完整无缺口输入获得预测提升、自然金融缺口已验证、严格PIT、TSFM训练适配或交易盈利。下一步必须针对证据分辨力与独立获取支持注册明确方案；本轮没有打开calibration/test寻找翻盘，也不晋升incumbent。
