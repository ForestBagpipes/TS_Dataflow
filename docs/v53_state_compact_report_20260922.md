# v53 状态压缩(Compact-17)与诊断补全报告 — 2026-09-22

执行日期:2026-09-21(服务器)→ 2026-09-22(报告)。全部计算在服务器
(`/home/vipuser/work/work2`,`$W2_CORE_PY`,CPU only,未动 GPU、未重跑任何预测
骨干/修复器)完成,结果同步于服务器与本地 `results/v53_state_compact/`。

## 与任务书"已有代码事实"的偏差(以实际代码为准)

1. **选参/评估实际由 `introact_ts.v47.select` 产出,不是 `v47_verified.select`。**
   冻结文件 `results/v47/protocol/selection_*.json` 由 `scripts/v47_select.py`
   用 `introact_ts.v47.select` + `introact_ts.v44.catalog`(`REPLAY=results/v47/replay`,
   bank 块为 `bankx`)生成。两个模块的 `select.py` 实质不同(SHA-256 见下):
   - harm cap 锚:v47 取 bank 上**平均效用最高**的动作(CONTEXT_RIDGE);
     v47_verified 取 source-macro MASE 最低的固定动作。
   - LOPO 标准化:v47 用 bank 全局标准化;v47_verified 折内重拟合。
   - 不可行分支:v47 回退到 `beta==max(beta_grid)`;v47_verified 直接抛错。
   - bootstrap 宏聚合:v47 不做 cell 分层;v47_verified 按 (horizon,severity) 分层。
   为让"Full-22 重跑验证冻结一致性"成立,本批全部使用 v47 模块(与 v52 脚本一致)。
2. 任务书称 cap 锚为"MASE 最低固定动作",实际(v47)为平均效用最大;两定义在三个
   骨干上都选中 CONTEXT_RIDGE,数值 cap 与冻结文件一致。
3. 冻结 bootstrap 为 2000 次 seed 101(v47 版实现),本批沿用。

代码 SHA-256:
`scripts/v53_state_compact.py`=72cb9e81788d…, `v53_gate_controls2.py`=780bc3836548…,
`v53_source_fixed.py`=e6a916f0568e…, `v53_harmcap_proposal.py`=34f1e0b6830c…,
`v53_latency_audit.py`=3af81d09d5ca…, `v53_run_all.sh`=e2c0644df94c…;
`src/introact_ts/v47/select.py`=6f92048d3eac…, `v44/catalog.py`=ca5a4456531b…。

## 任务 1:Full-22 vs Compact-17 训练侧比较

命令:`$W2_CORE_PY scripts/v53_state_compact.py --backbone {bolt,timesfm,chronos2}`
(网格 6×4、LOPO parent 级排除、harm cap、平局规则全部复用库函数;选参阶段
`test_records_read=0`,由加载日志守卫)。

### 1a 选参结果(bank=bankx, 5352 episodes / 223 parents / 8 sources)

| backbone | 版本 | 状态维数 | 选定 (k,β) | cap | 可行设置数 | fallback | 锚 |
|---|---|---|---|---|---|---|---|
| bolt | Full-22 | 22 | (128, 0.5) | 0.4099 | 19 | 否 | CONTEXT_RIDGE |
| bolt | Compact-17 | 17 | (64, 0.5) | 0.4099 | 20 | 否 | CONTEXT_RIDGE |
| timesfm | Full-22 | 22 | (32, 1.64) | 0.3231 | 9 | 否 | CONTEXT_RIDGE |
| timesfm | Compact-17 | 17 | (16, 0.5) | 0.3231 | 9 | 否 | CONTEXT_RIDGE |
| chronos2 | Full-22 | 22 | (16, 0.5) | 0.4184 | 24 | 否 | CONTEXT_RIDGE |
| chronos2 | Compact-17 | 17 | (64, 0.5) | 0.4184 | 24 | 否 | CONTEXT_RIDGE |

**Full-22 重跑与冻结 JSON 完全一致**(三骨干 k、β、cap、锚、leader LOPO MASE 全部
match,`consistency_with_frozen_full22.consistent=true`)。cap 不随状态投影变化
(锚统计只用 utility/legality),两版本 cap 相同。注意 timesfm Compact-17 选出的
β=0.5 远小于 Full-22 的 1.64,直接导致其干预率大幅升高(见下)。

### 1b 各块评估(各自选定的 k,β;MASE/RMSSE 为 source-macro;IR=干预率;
HIR=条件有害率;HL=有害损失)

bolt:

| 块 | FULL MASE | COMP MASE | FULL RMSSE | COMP RMSSE | FULL IR | COMP IR | FULL HIR | COMP HIR | FULL HL | COMP HL |
|---|---|---|---|---|---|---|---|---|---|---|
| train_eval | 1.1046 | 1.1235 | 1.0406 | 1.0490 | 0.741 | 0.703 | 0.382 | 0.389 | 0.0279 | 0.0408 |
| test | 1.3783 | 1.3692 | 1.1766 | 1.1700 | 0.746 | 0.749 | 0.422 | 0.415 | 0.0377 | 0.0343 |
| test30 | 1.6628 | 1.6615 | 1.3308 | 1.3296 | 0.887 | 0.850 | 0.436 | 0.447 | 0.0763 | 0.0728 |
| test50 | 1.6641 | 1.6922 | 1.3456 | 1.3616 | 0.939 | 0.875 | 0.430 | 0.417 | 0.0778 | 0.0850 |
| test_m2 | 1.3806 | 1.3761 | 1.1780 | 1.1753 | 0.761 | 0.747 | 0.419 | 0.407 | 0.0388 | 0.0397 |
| test_m3 | 1.3762 | 1.3742 | 1.1760 | 1.1751 | 0.759 | 0.768 | 0.456 | 0.464 | 0.0410 | 0.0399 |

timesfm:

| 块 | FULL MASE | COMP MASE | FULL RMSSE | COMP RMSSE | FULL IR | COMP IR | FULL HIR | COMP HIR | FULL HL | COMP HL |
|---|---|---|---|---|---|---|---|---|---|---|
| train_eval | 1.0952 | 1.1182 | 1.0345 | 1.0484 | 0.467 | 0.816 | 0.263 | 0.390 | 0.0111 | 0.0351 |
| test | 1.5537 | 1.5605 | 1.3082 | 1.3152 | 0.524 | 0.805 | 0.387 | 0.407 | 0.0370 | 0.0473 |
| test30 | 1.7429 | 1.7318 | 1.4071 | 1.4011 | 0.772 | 0.913 | 0.356 | 0.386 | 0.0781 | 0.0927 |
| test50 | 1.8032 | 1.7460 | 1.4486 | 1.4097 | 0.809 | 0.914 | 0.384 | 0.404 | 0.0914 | 0.1013 |
| test_m2 | 1.5592 | 1.5575 | 1.3150 | 1.3133 | 0.518 | 0.793 | 0.396 | 0.431 | 0.0431 | 0.0514 |
| test_m3 | 1.5275 | 1.6008 | 1.2968 | 1.3429 | 0.512 | 0.812 | 0.396 | 0.438 | 0.0317 | 0.0577 |

chronos2:

| 块 | FULL MASE | COMP MASE | FULL RMSSE | COMP RMSSE | FULL IR | COMP IR | FULL HIR | COMP HIR | FULL HL | COMP HL |
|---|---|---|---|---|---|---|---|---|---|---|
| train_eval | 1.1365 | 1.1131 | 1.0700 | 1.0520 | 0.705 | 0.743 | 0.505 | 0.479 | 0.0726 | 0.0485 |
| test | 1.3779 | 1.3542 | 1.2136 | 1.1913 | 0.691 | 0.709 | 0.396 | 0.401 | 0.0379 | 0.0361 |
| test30 | 1.6868 | 1.6960 | 1.3799 | 1.3805 | 0.711 | 0.701 | 0.446 | 0.430 | 0.0549 | 0.0521 |
| test50 | 1.7385 | 1.7134 | 1.4198 | 1.3972 | 0.709 | 0.726 | 0.410 | 0.402 | 0.0618 | 0.0672 |
| test_m2 | 1.3728 | 1.3555 | 1.2112 | 1.1930 | 0.682 | 0.729 | 0.432 | 0.448 | 0.0430 | 0.0429 |
| test_m3 | 1.3805 | 1.3518 | 1.2127 | 1.1868 | 0.691 | 0.736 | 0.430 | 0.408 | 0.0513 | 0.0404 |

### 1c FULL−COMPACT parent 聚类配对 bootstrap(2000 次,seed 101;正值=Compact 更好)

| backbone | 块 | 差值 | 95% CI | p | CI 排除 0 |
|---|---|---|---|---|---|
| bolt | train_eval | −0.0189 | [−0.0574, 0.0065] | 0.2972 | 否 |
| bolt | test | +0.0091 | [0.0019, 0.0161] | 0.0134 | 是 |
| timesfm | train_eval | −0.0230 | [−0.0581, −0.0012] | 0.0236 | 是(Compact 更差) |
| timesfm | test | −0.0068 | [−0.0149, 0.0009] | 0.0860 | 否 |
| chronos2 | train_eval | +0.0235 | [0.0035, 0.0477] | 0.0138 | 是 |
| chronos2 | test | +0.0238 | [0.0120, 0.0373] | 0.0001(下限) | 是 |

### 1d 收口判定:**不通过(FAIL)**

统一训练侧(train_eval)上:Compact-17 仅在 chronos2 显著降低 MASE(+0.0235,
p=0.014);bolt 点估计为负且不显著;**timesfm 显著退化**(−0.0230,p=0.024),且其
有害损失从 0.0111 升至 0.0351(约 3.2 倍)、干预率从 0.467 跳到 0.816(因其 Compact
选参 β 从 1.64 降到 0.5)。bolt 训练侧有害损失也上升(0.0279→0.0408)。存在明显单
骨干退化,且三骨干方向不一致,Compact-17 不能作为统一训练侧状态替代 Full-22。
test 块仅记录:bolt/chronos2 上 Compact 略优,timesfm 上较差,方向同样不一致。

## 任务 2:诊断A补全(频率匹配对照)

命令:`$W2_CORE_PY scripts/v53_gate_controls2.py --backbone <b>`。
校准只在 train_eval:θ 为 R2-CART 最高后验概率的 (1−dev_rate) 分位数;
BEST_FIXED_RANDOM 概率 p=dev FULL 干预率,按 `sha256("v53-best-fixed-random-keep"|episode)`
确定性哈希 firing。重算的 R2_CART(0.5 阈值)与 BEST_FIXED 同
`results/v47/evaluation/{train_eval,test}_<b>.json` 已发布数值**逐项完全一致**
(mase 与干预率 match,六处全对)。

| backbone | dev FULL IR | θ(冻结) | p_random | BEST_FIXED |
|---|---|---|---|---|
| bolt | 0.7406 | 0.5901 | 0.7406 | CONTEXT_RIDGE |
| timesfm | 0.4670 | 0.6578 | 0.4670 | CONTEXT_RIDGE |
| chronos2 | 0.7052 | 0.6173 | 0.7052 | CONTEXT_RIDGE |

test 块关键数值(实际达到的干预率,不二次匹配):

| backbone | 方法 | test MASE | test IR | test HIR | test HL |
|---|---|---|---|---|---|
| bolt | FULL | 1.3783 | 0.746 | 0.422 | 0.0377 |
| bolt | R2_CART_T05 | 1.4022 | 1.000 | 0.437 | 0.0478 |
| bolt | R2_CART_MATCHED | 1.4035 | 0.728 | 0.412 | 0.0358 |
| bolt | BEST_FIXED | 1.4280 | 0.745 | 0.415 | 0.0445 |
| bolt | BEST_FIXED_RANDOM | 1.4423 | 0.522 | 0.423 | 0.0337 |
| timesfm | FULL | 1.5537 | 0.524 | 0.387 | 0.0370 |
| timesfm | R2_CART_T05 | 1.5885 | 0.992 | 0.414 | 0.0666 |
| timesfm | R2_CART_MATCHED | 1.5899 | 0.429 | 0.353 | 0.0323 |
| timesfm | BEST_FIXED | 1.5786 | 0.745 | 0.408 | 0.0624 |
| timesfm | BEST_FIXED_RANDOM | 1.6389 | 0.337 | 0.402 | 0.0291 |
| chronos2 | FULL | 1.3779 | 0.691 | 0.396 | 0.0379 |
| chronos2 | R2_CART_T05 | 1.3846 | 0.989 | 0.441 | 0.0609 |
| chronos2 | R2_CART_MATCHED | 1.4121 | 0.461 | 0.411 | 0.0296 |
| chronos2 | BEST_FIXED | 1.4564 | 0.745 | 0.428 | 0.0470 |
| chronos2 | BEST_FIXED_RANDOM | 1.4963 | 0.496 | 0.430 | 0.0315 |

两点如实标注:
- **R2-CART 概率高度离散**(深度3树叶子少),分位数处有大量并列值,严格 `>` 使实际
  干预率低于目标:train_eval 上 bolt 0.698/目标 0.741,timesfm 0.429/0.467,
  chronos2 0.476/0.705。chronos2 的"匹配"覆盖明显偏低,解释其对照结果时需注意。
- BEST_FIXED_RANDOM 实际 IR = p × 动作合法率(CONTEXT_RIDGE 合法率约 0.7),故
  bolt 0.522、timesfm 0.337、chronos2 0.496,均低于 p;这是按任务书"以 FULL 干预率
  为 firing 概率"的字面语义,覆盖率匹配版会因 p>1(bolt)退化为 BEST_FIXED 本身。

FULL vs 各对照的 bootstrap(test):FULL 对 R2_CART_MATCHED 在 bolt 显著更好
(−0.0252 [−0.0495,−0.0011],p=0.034),timesfm/chronos2 不显著;对
BEST_FIXED_RANDOM 三骨干均显著更好(p≤0.0014–0.0001)。结论:在可比或更低干预
频率下,FULL 不劣于且多数情况下优于频率匹配的 R2-CART;随机执行固定动作显著更差,
说明收益来自选择而非频率。

## 任务 3:诊断B

命令:`$W2_CORE_PY scripts/v53_source_fixed.py --backbone <b>`(test 块)。

### 3a 来源级固定策略(bank 上该来源平均效用最优动作,不可用回退 KEEP)

- bolt 策略:ETTh1/ETTh2/ETTm1/ETTm2/Traffic=CONTEXT_RIDGE,Electricity=SINGLE_TSICL,
  Exchange=MULTI_TSICL,Weather=FFILL;test 回退统计 ETTm1/ETTm2 各 48、ETTh1/ETTh2/
  Traffic 各 12。
- timesfm:除 Exchange=MULTI_TSICL、Weather=FFILL 外全 CONTEXT_RIDGE;回退 ETTm1/2
  各 48、Electricity 18、ETTh1/2、Traffic 各 12。
- chronos2:CONTEXT_RIDGE(ETTh1/2、ETTm1/2、Exchange)、SINGLE_TSICL(Electricity、
  Weather)、SAITS(Traffic);回退 ETTm1/2 各 48、ETTh1/2 各 12、Exchange 6。

test source-macro MASE 对比:

| backbone | FULL | SOURCE_FIXED | BEST_FIXED | NATIVE_KEEP | R2_CART | FIXED_SAITS | TATO |
|---|---|---|---|---|---|---|---|
| bolt | 1.3783 | **1.3602** | 1.4280 | 1.4664 | 1.4022 | 1.4691 | 1.6201 |
| timesfm | 1.5537 | **1.5268** | 1.5786 | 1.6820 | 1.5885 | 1.4653 | 1.6139 |
| chronos2 | **1.3779** | 1.4484 | 1.4564 | 1.5793 | 1.3846 | 1.4411 | 1.6144 |

FULL−SOURCE_FIXED bootstrap:bolt +0.0181 [0.0061, 0.0296] p=0.0022(SOURCE_FIXED
显著更好);timesfm +0.0269 [0.0035, 0.0526] p=0.0172(同);chronos2 −0.0704
[−0.1558, 0.0156] p=0.2992(FULL 点估计更好但不显著)。**来源级固定策略在 2/3 骨干
上击败 FULL**,是 FULL 收益来源的重要反证,需要写进讨论。

### 3b 留一来源敏感性(test,FULL−对照,负值=FULL 更好;每格 8 行略,全表见 JSON)

| 留出 | bolt vs BEST_FIXED | timesfm vs BEST_FIXED | chronos2 vs BEST_FIXED | bolt vs R2_CART | chronos2 vs FIXED_SAITS |
|---|---|---|---|---|---|
| ETTh1 | −0.0570 | −0.0325 | −0.0908 | −0.0265 | −0.0744 |
| ETTh2 | −0.0556 | −0.0251 | −0.0953 | −0.0239 | −0.0794 |
| ETTm1 | −0.0560 | −0.0292 | −0.0925 | −0.0269 | −0.0746 |
| ETTm2 | −0.0556 | −0.0277 | −0.0850 | −0.0273 | −0.0719 |
| Electricity | −0.0566 | −0.0409 | −0.0946 | −0.0288 | −0.0673 |
| **Exchange** | **−0.0061** | **+0.0095** | **+0.0073** | **−0.0023** | **+0.0125** |
| Traffic | −0.0530 | −0.0285 | −0.0885 | −0.0277 | −0.0722 |
| Weather | −0.0573 | −0.0252 | −0.0887 | −0.0277 | −0.0777 |

结论:**FULL 对 BEST_FIXED / R2_CART 的优势高度集中于 Exchange**——留出 Exchange
后差值归零甚至反转(三骨干一致);对 NATIVE_KEEP 与 TATO 的优势则是广谱的(8/8 行
同号,timesfm 对 TATO 留出 ETTm1 时 +0.0054 为例外)。FIXED_SAITS 在 timesfm 上整体
优于 FULL(−0.0884→此处符号为 FULL−SAITS=+0.0884),8/8 行 FULL 更差。

## 任务 4:harm cap 不可行分支审计

当前行为(`src/introact_ts/v47/select.py:449-451`,产生冻结文件的模块):
可行集为空时 `feasible = [r for r in rows if r["beta"] == max(beta_grid)]`,即**取最大
惩罚 β=1.64 的所有设置中 LOPO MASE 最低者,且不再复核 cap**——确实可能带着违规的
条件有害率被冻结(`fallback_to_most_conservative=true` 仅为标记,无约束)。
`v47_verified` 版本则直接 `raise ValueError("…freeze refused")`。

触发审计(`scripts/v53_harmcap_proposal.py`,结果 `harmcap_audit.json`):
三个冻结选参与本批六个选参(Full/Compact × 三骨干)**均未触发**该分支
(feasible 9–24 个),所有选定设置的条件有害率均 ≤ cap。**ever_triggered=false**。

代码提案(未改动任何库):`scripts/v53_harmcap_proposal.py` 中
`select_on_infeasible_keep(grid_rows, cap)`——可行集为空时返回
`status="infeasible", selected=None, decision="abstain: intervention disabled, every
request KEEP"` 并登记 `min_conditional_hir`,即"禁用干预、全 KEEP、登记不可行",
替代现有的 max-β 回退。

## 任务 5:计时核查

已有(`results/v47/cost_audit/latency_test_*.json` + forecast `status.json`,本批仅
汇总为 `latency_audit.json`,未补跑):

| 分项 | 状态 | 数值/出处 |
|---|---|---|
| 参考预测 | 已记录 | test 每次调用 mean/p95/max:bolt 45.4/54.5/474.1 ms,timesfm 103.9/110.2/321.7 ms,chronos2 19.5/21.6/368.6 ms(n=4351 唯一预测) |
| 候选构造 | **部分** | 只有阶段级 runtime(inputs test 23.5 s/760 episodes;tsicl test 100.4 s;saits 按 fold 725–3161 s);无每请求计时 |
| 特征检索 | 已记录 | 每请求 mean/p95/max ≈ 2.3/2.4/3.7 ms(三骨干一致,n=760,部署形态逐请求) |
| 所选动作预测 | 阶段级已记录 | 部署路径只对所选动作调骨干,单次调用时间同上;per_action 调用计数在 status.json |
| 端到端 | **缺失(UNFINISHED)** | 没有任何计时器跨"参考预测+候选构造+检索+所选动作预测"的单请求全程;现有分项定义与需求匹配,但缺候选构造的每请求计时,无法在不重跑的情况下合成真实端到端 |
| 调用计数 | 已记录 | test:unique_inputs 3784、unique_predictions 4351、per_action 566–760 |

**UNFINISHED:端到端每请求延迟**。缺口=候选构造(FFILL/CONTEXT_RIDGE 纯函数、
TSICL/SAITS 模型阶段)无每请求计时;要补齐需在候选构造路径加计时并重放 test 请求
(不重跑骨干,但需加载 TSICL/SAITS 候选归档),估计超过 30 分钟安全窗口,故标记
UNFINISHED 而非估算。

## 产物清单(服务器与本地一致)

- `results/v53_state_compact/selection_{bolt,timesfm,chronos2}.json`(任务1选参+一致性)
- `results/v53_state_compact/evaluation_{bolt,timesfm,chronos2}.json`(任务1评估+bootstrap)
- `results/v53_state_compact/gate_controls2_{bolt,timesfm,chronos2}.json`(任务2)
- `results/v53_state_compact/source_fixed_{bolt,timesfm,chronos2}.json`(任务3)
- `results/v53_state_compact/harmcap_audit.json`(任务4)
- `results/v53_state_compact/latency_audit.json`(任务5)
- `results/v53_state_compact/logs/`(全部原始日志,含 run_all.log,所有步骤 exit=0)
- 脚本:`scripts/v53_state_compact.py`、`v53_gate_controls2.py`、`v53_source_fixed.py`、
  `v53_harmcap_proposal.py`、`v53_latency_audit.py`、`v53_run_all.sh`(本地与服务器一致)
- 本报告:`docs/v53_state_compact_report_20260922.md`(本地+服务器)

无 BLOCKED 项;唯一 UNFINISHED 为任务5端到端计时(缺口见上)。未改动
`src/`、冻结协议或任何 v47/v52 结果;未触碰服务器未提交修改。
