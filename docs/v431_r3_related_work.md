# v4.3.1-r3 相关工作核对与金融附表适用条件

检索和只读核对日期：2026-09-15，Asia/Shanghai。使用论文作者、正式会议、arXiv 与论文给出的官方代码作为依据；搜索聚合页仅用于找原始链接，不采用其自动生成的方法摘要。以下实验建议是本项目推论，不是被引论文的主张。创新判断矩阵见 [novelty_matrix.md](novelty_matrix.md)。

## 原始来源、版本与准确指代

| 工作 | 首发/所核版本、会议 | 原始论文与官方实现 | 核对状态 |
|---|---|---|---|
| **Adapt Data to Model: Adaptive Transformation Optimization for Domain-shared Time Series Foundation Models (TATO)**，Qiu 等 | arXiv v1 2026-02-28；ICLR 2026 | [arXiv 2603.00629](https://arxiv.org/abs/2603.00629)、[ICLR](https://openreview.net/forum?id=uTK1SNgi1N)、[thulab/TATO](https://github.com/thulab/TATO) | 本地官方源 commit `402bbc8998c49e2f33d9afbcc42140347a6b8c36` 已用于 r2。冻结模型下变换搜索与历史验证已核；本地是8 trial短预算适配。 |
| **Task-oriented Time Series Imputation Evaluation via Generalized Representers**，Zhixian Wang 等 | arXiv v1 2024-10-09；NeurIPS 2024 | [arXiv 2410.06652](https://arxiv.org/abs/2410.06652)、[正式论文](https://proceedings.neurips.cc/paper_files/paper/2024/file/f88264fcc54775ee1706116e90fe351a-Paper-Conference.pdf)、[hkuedl/Task-Oriented-Imputation](https://github.com/hkuedl/Task-Oriented-Imputation) | 原文摘要与官方代码接口已核。其 generalized representer 估计下游影响并融合插补，不把“任务导向插补”当本项目首次提出。 |
| **Is Precise Recovery Necessary? A Task-Oriented Imputation Approach for Time Series Forecasting on Variable Subset (TOI-VSF)**，Qi Hao 等 | arXiv v1 2024-11-15 | [arXiv 2411.09928](https://arxiv.org/abs/2411.09928) | 与上一条是不同论文。研究预测变量子集、插补与预测学习，不能因相近标题混同作者、监督或官方代码。 |
| **CSDI: Conditional Score-based Diffusion Models for Probabilistic Time Series Imputation**，Tashiro 等 | arXiv v1 2021-07-07；NeurIPS 2021 | [arXiv 2107.03502](https://arxiv.org/abs/2107.03502)、[ermongroup/CSDI](https://github.com/ermongroup/CSDI) | 条件扩散概率插补；仓库有训练、预训练插补及 forecasting 入口。不是证据获取策略的同义词，本项目未运行官方 CSDI。 |
| **Estimating Conditional Mutual Information for Dynamic Feature Selection (DIME)**，Gadgil、Covert、Lee | arXiv v1 2023-06-05，v3 2024-09-08；ICLR 2024 | [arXiv 2306.03301v3](https://arxiv.org/abs/2306.03301v3)、[官方会议论文](https://proceedings.iclr.cc/paper_files/paper/2024/file/9682490bedc064aba8aac1ab3f703507-Paper-Conference.pdf)、[suinleelab/DIME](https://github.com/suinleelab/DIME) | 此处 DIME 为判别式互信息估计，不是其它同缩写插补器。特征获取、非均匀成本、可变预算均有先例。 |
| **Amortized Bayesian Experimental Design for Decision-Making (TNDP)**，Huang、Guo、Acerbi、Kaski | arXiv v1 2024-11-04，v2 2025-01-02；NeurIPS 2024 | [arXiv 2411.02064v2](https://arxiv.org/abs/2411.02064v2)、[官方实现](https://github.com/huangdaolang/amortized-decision-aware-bed) | TNDP 展开为 Transformer Neural Decision Process；决策效用驱动实验设计已核。与交通网络设计同缩写无关；本轮没有复现其网络。 |
| **ImputePilot: A Graphical Model Selection Toolkit for Time Series Imputation**，Yao、Jin、Chen、Tung、Khayati | PVLDB 19(12):4742–4745，2026；会议 2026-08-31 至09-04 | [正式4页论文](https://www.vldb.org/pvldb/vol19/p4742-chen.pdf)、[官方会议程序](https://vldb.org/2026/program.html)、[论文给出的仓库](https://github.com/Marblue0609/ImputePilot/) | 正确PDF文件名是 `p4742-chen.pdf`；全文/DOI `10.14778/3827998.3828111` 已核。仓库访问在本轮工具中返回 Internal Error，未验证可运行，不解释成仓库不存在。 |
| **RAVEN: A Regime-Aware Variable-context Expert Network for Financial Time Series Forecasting**，Cheng He 等 | arXiv v1 2026-06-23；所核为预印本 | [arXiv 2606.24062](https://arxiv.org/abs/2606.24062) | 原摘要明确嵌套连续窗口与尺度专家。用户未提供“嵌套上下文”全名，本条仅为确认的相关近邻；不能宣称已经唯一识别用户指代或穷尽相关文献。 |
| **AegisTS: A Hierarchical Agentic AI System with Reinforcement Learning for Multivariate Time Series Data Cleaning**，Shi 等 | arXiv v1 2026-05-06，v6 2026-08-24 | [arXiv 2605.04902v6](https://arxiv.org/abs/2605.04902v6) | 原文明确分层清洗 agent、清洗顺序/模型选择与清洗和下游双阶段奖励。原生工程复现尚未完成。 |

## 对论文叙述的具体约束

TATO 的直接相关性最高：它也在固定 TSFM 下改变输入，并用历史任务表现选管线。因此，论文需要把新候选集中在 **历史治理收益向当前任务迁移时的测量失配**：固定相同历史终点、目标、mask 和参照，独立重建长短管线，判断相对收益的有符号变化是否能减少错误选择。这个机制比“多看一段历史”多出的价值必须与等成本普通回测比较。[TATO 原论文](https://openreview.net/forum?id=uTK1SNgi1N)

Generalized Representers 已经从任务而非重建质量评价插补。与它比较时应说明本项目可调用的冻结 TSFM 接口、训练标签权限与费用，不能只说其“未考虑下游”。官方代码出现 `train_label/test_label` 参数并不能单独证明标签泄漏；要按其原协议和本项目适配契约核查。[NeurIPS 2024 论文](https://proceedings.neurips.cc/paper_files/paper/2024/file/f88264fcc54775ee1706116e90fe351a-Paper-Conference.pdf)

ImputePilot 是 A-DARTS 推荐引擎的交互系统：ModelRace 选择分类 pipeline，结合统计/拓扑特征，以 F1、Recall@3 和运行时间作评分，并展示上游和下游影响。因此，普通特征选择器、公平计算的推荐方法以及端到端执行日志都不能单独成为我们的独特突破。它的原生系统是否能在冻结 TSFM 协议中形成强对照，仍需要实际适配，不把未运行写为落后。[ImputePilot 正式论文](https://www.vldb.org/pvldb/vol19/p4742-chen.pdf)

DIME 与 TNDP 使“获取证据应服务预测/末端决策，并考虑成本”成为明确先例。r3 可主张的最多是该原则在特定治理任务中的可核验实现及实证增量：同冻结终态生成正、零、负价值标签；没有工具输出时不能读输出特征；预算检查整个分支。单步树和经验回退没有自动获得这些论文的理论保证。[DIME](https://arxiv.org/abs/2306.03301v3)、[TNDP](https://arxiv.org/abs/2411.02064v2)

RAVEN 学习多尺度专家并在金融等预测任务中选择上下文；r3 固定预测器、使用同终点嵌套输入作为测量。两者确有对象差别，但嵌套或自适应窗口本身并非创新。若 `kappa` 不胜旧 `multiview_disagree`、等成本额外回测或直接收益 ridge，则保留“响应未提供增量”的结论。`kappa` 不是市场因果效应，预测价格层级的附表也不能写成收益率交易验证。[RAVEN 预印本](https://arxiv.org/abs/2606.24062)

CSDI 可作为概率插补先例，AegisTS 是已有清洗 agent 先例。当前 r3 不扩散生成数据、不训练 TSFM、不做清洗顺序的大型组合搜索；因此这些边界必须体现在方法和实验中，而不是在题目里回避最接近工作。[CSDI](https://arxiv.org/abs/2107.03502)、[AegisTS](https://arxiv.org/abs/2605.04902v6)

可直接用于草稿的谨慎表述：**我们检验一种面向冻结 TSFM 缺口治理的证据机制：在相同历史预测任务上控制较早上下文的可见范围，测量治理动作的相对任务收益变化，再学习它与当前部署收益的关系；在明确的信息和预算边界下选择取证或停止。该机制是否优于普通回测、同信息预测器和固定取证，取决于共同实验。** 当前不能加“首次”“保证无害”“SOTA”或“已证明主动性”。

## 金融附表的 r3 适用范围

只复用 r2 `financial-observation-index-r1` 的2个 parent、12个 episode。两目标为 Oil 的 `COP_Brent-Europe`（USD/barrel）和 USTS 的 `FwdRate_Fitted_1Y`（模型拟合名义一年远期利率，百分点；不是成交价格）。H96/H192 为记录事件数，仍不同于旧 B 网格。新增 probe 不增加 parent，也不制造独立确认集。[金融来源审计](v431_r2_financial_audit.md)

冻结条件保持 raw、`target_block_10`、`shared_block_10`，受控删除为事件 `[230,281)`，沿用 seed101。raw 原有限观测全部保留；r2 40例跨家族五臂输入和预测 no-op 已完成，不能推导尚未执行的 r3 历史 probe 自动通过。自然应有观测缺口没有可靠逐日分类，仍为缺项，跳过的原始行不等于休市，也不等于丢失报价。

准备阶段在服务器只调用 `load_episodes` 与 `prepare_probe`，读取冻结 `contexts.npz`、context manifest 和既有 TRAIN MASE 尺度；没有读取 `evaluator_metadata.json`、targets 或新 future，没有模型调用。正式尺度为 USTS `0.10750568831895273`、Oil `2.666378768830923`；只是检查几何/可观测支持，没有生成预测、计算收益或挑选结果。

| H/条件（每格含2个来源） | H32：origin480/输入480 | long：origin512-H | short：同origin、start64 | second：origin512-H-64 | 配对用途 |
|---|---|---|---|---|---|
| H96，raw | prepared | 输入416，prepared | 输入352，prepared | 输入352，prepared | 完整输入负控 |
| H96，target/shared受控删除 | prepared | prepared | prepared | prepared | 4个受控episode，可比较响应/等成本回测 |
| H192，raw | prepared | 输入320，prepared | 输入256，prepared | 输入256，prepared | 完整输入负控 |
| H192，target/shared受控删除 | prepared | prepared | **unsupported** | **unsupported** | 4个episode保留在全覆盖表，以合法无响应状态/STOP回退 |

越界理由只由冻结几何决定：H96长短复制缺口至 `[134,185)`，公共后缀容纳完整缺口；H192复制至 `[38,89)`，短输入起点64使缺口前26点无法保留。H192第二原点256把缺口复制为 `[-26,25)`，也越界。不能移动/裁掉缺口或看结果改64。第二原点H192验证区虽有167/192个 dirty 可见标签，仍无法修复上述输入越界。

共48个规格检查，40 prepared、8 unsupported；按工具是 H32和long各12/12，short和second各8/12。响应与等成本回测的共同支持是8个episode，其中4个raw负控，受控治理机制仅4个episode/2个parent。随后两家族实际GPU记录和CPU独立审计已完成：96原子记录、16长短对、80逐臂官方预处理核验通过，实际长短信息相同为0。该语义通过不代表预算可行或方法收益成立，实际金融预算失败见下文。

复核时的 `probe.py` SHA256 为 `ff9567d79bdaf193c16f531c2084060766be8de75b830e057f5a10a4b37b87c3`，`contexts.npz` SHA256 为 `a828834a46ecd7a5027107dda28f258be684836212030e515a1a8cfc3581d0d2`。可复核的只读命令如下；不要调用旧 Collector 的 `run_collect`：

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from v431_r2_financial_collect import load_episodes
from introact_ts.v431_r3.probe import registered_specs, prepare_probe
root = Path('results/v431-r2/financial-observation-index-r1')
episodes, meta = load_episodes(root)
scales = json.loads((root / 'mase_scales.json').read_text())
for episode in episodes:
    for name, spec in registered_specs(episode.horizon).items():
        p = prepare_probe(episode, spec, scales[episode.source])
        print(episode.source, episode.horizon, meta[episode.uid]['condition'],
              name, p.status, p.reason, int(p.scoring_mask.sum()))
PY
```

## 金融依赖、信息权限与报告建议

`results/v431-r2/finance/dependence.json` 仅用原 TRAIN 数值和 DEV 日期/原行映射核对。Oil 与 USTS 原 TRAIN 同日有限目标1242对，2006-06-14—2011-06-13：原层级 Pearson `-0.1423787574630594`、Spearman `-0.17902432212302996`。不转收益率、不计算错误的 IID 显著性；这两个相关系数不能证明来源独立或足够覆盖金融机制。

两 DEV 的未来时期分别为 Oil 2020年、USTS 2013—2014年，没有相同 future 日期；但 **Oil H96/H192 各4个未来点已在旧pilot作为标签读取，USTS H96全部96点、H192的161点与旧agent DEV标签重叠**。USTS旧pilot也暴露9个未来标签。r2 的 `first_dev_results.json` 是本协议首次附表，不是历史上所有元素首次使用。r3 继续按已使用 DEV 诊断，不能拿新 UID 宣称确认。

具体执行边界：保留真实 context 日期与原行映射；长短各自截断后拟合尺度/候选，复制缺口以记录事件相对位置计算。既有数据只支持 snapshot as-of 假设：USTS观测日不是历史发布日期，Oil同panel发布时区/顺序未恢复；保持 `strict_point_in_time=false`。不引跨来源协变量，不向 agent 传未来事件日期、评价mask或辅助 future。

金融结果应同时给12窗全覆盖表、8窗共同支持机制表、两来源/跨度/三条件及实际成本。两来源各仅1个parent，H96/H192共用前96目标，变体和探针不能扩权；不从2个parent构造强显著性主张。金融附表不能训练收益映射、选alpha/64/缺口位置、改变参照或获取价格。全部参数沿合法 TRAIN 冻结，新probe仅复用当前可见 context；r2 原始结果与首次SHA保持。

本次只读审计不解除 calibration/test 封存。近期强基线、响应、主动获取或严格PIT证据缺项都应继续保留，不能用金融子集或新探针掩盖缺项。


## r3 实际结果对相关工作主张的约束

四套完整结果已生成，数值与source-parent配对统计见[创新边界矩阵](novelty_matrix.md#四套共同结果与当前主张状态)。主DEV两家族高预算agent分别为Bolt1.156351、TimesFM1.102669；固定取证分别为1.156351、1.096019。Bolt与固定取证逐窗预测完全相同，TimesFM主动点估计更差，不能将DIME/TNDP已有的信息价值原则写成本项目已经获得的主动优势。

有符号响应相对无kappa在相同实际支持50窗/25parent上，Bolt差+0.004163而TimesFM−0.037489；相对旧原始预测分歧，两家族均无可靠额外收益。相对direct ridge、CART及等次数普通回测也没有跨家族稳定优势。因此，与TATO/嵌套上下文近邻的“测量差异”仍只是实现和可检验设计差异，不能写成已证优越机制。任务跨度对齐在Bolt优于H32的局部结果必须单独归因，不能替响应或主动性背书。

17个T_check新缺口位置的结果已出：Bolt高预算agent1.190724与固定取证同效；TimesFM1.260234优于固定取证1.288577的点估计，仍只是既有17parent的新组合检查。金融附表两家族agent分别为3.103498和4.920632；TimesFM看似改善但8/12窗超3.5秒，Bolt与固定取证同效且比固定参照差。该金融条件不能主张预算内获胜，更不能用两个已使用DEV parent论证独立金融泛化。

原生TATO保留已有8trial限制；Generalized Representers、CSDI、DIME、TNDP、ImputePilot、AegisTS官方完整适配尚未执行。以上方法的文献先例继续限制原创叙述，未运行不等于被击败。当前论文可以呈现可运行方法、真实测量与负结果诊断，尚不支持响应/主动增量或SOTA结论。

还需限制内部可观测性表述：旧source MASE尺度`S_t`使用完整TRAIN，包含内部origin之后及T_check/T_acq的原始数值；r3把它用于收益/响应/分歧与ψ的归一化。监督与模型parent隔离已核，不代表全部预处理逐origin可见。DEV在整个TRAIN之后、calibration/test未读，这与未来标签泄漏不是同一结论；保持冻结分母并如实记录，不用新结果后换尺度制造改进。详见[实际范围审计](v431_r3_code_audit.md)。
