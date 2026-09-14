# Work2 研究蓝图与进展总结：IntroSpect-TS

> **状态：已被取代，保留作为研究记录。**
>
> 本文档写于评分器阶段，主张是对每个窗口给出质量分数并据此筛选。当前定位已改为
> IntroAct-TS，一个把每次数据处理都视为候选干预的治理智能体：动作先作用于沙箱副本，
> 随后重新探测冻结模型，只有当模型效用改善、时序结构保持且决策风险可接受时才提交，
> 否则回滚、改试其他动作或拒绝处理。
>
> 与本文档的关键差别在于，评分回答的是这条数据质量如何，而智能体回答的是执行这个动作
> 之后是否真的改善了数据对目标模型的效用且没有破坏原有结构，若没有是否应当撤销。
>
> 当前定位与实现见 `docs/code_overview.md`，当前进展与未决问题见 `docs/HANDOFF.md`，
> 论文侧的问题表述与贡献点见 `en/introspect_ts-20260609.tex`。
> 下文中关于统计画像、冻结模型行为探测与同类校准的部分仍然有效，它们构成了智能体的
> 感知层。关于质量分数、分层筛选与下游微调验证的部分已被动作空间、双重验证与回滚取代。


> **作者:** 胡宏彬  
> **日期:** 2026-07-01  
> **目标会议:** ICLR 2026  
> **方法名称:** IntroSpect-TS (Introspection-Guided Time Series Data Quality Assessment)

---

## 目录

1. [研究动机与问题](#1-研究动机与问题)
2. [核心洞察与设计哲学](#2-核心洞察与设计哲学)
3. [与已发表工作的精确定位](#3-与已发表工作的精确定位)
4. [方法详解：四个阶段](#4-方法详解四个阶段)
5. [形式化理论](#5-形式化理论)
6. [代码实现思路](#6-代码实现思路)
7. [实验设计](#7-实验设计)
8. [论文写作（LaTeX）](#8-论文写作latex)
9. [迭代历史](#9-迭代历史)
10. [待完成工作](#10-待完成工作)

---

## 1. 研究动机与问题

### 1.1 背景

时序基础模型（TSFM）已成为预测领域的主导范式。TimesFM、MOIRAI、Chronos、MOMENT、Timer等架构在跨能源、交通、天气、金融、医疗等领域的大规模时序语料库（数百亿至数千亿时间点）上预训练。

当前TSFM语料构建遵循"可用即包含"原则——把能获取的所有数据直接汇入训练池。但这带来三大成本：
1. **噪声污染**：传感器故障、缺失片段、记录伪影等低质量数据浪费计算并可能引入虚假相关性
2. **冗余膨胀**：相似模式的大量窗口贡献递减的边际信息增益
3. **稀缺模式淹没**：间歇需求、结构突变等罕见但关键的模式被常见平稳/周期模式淹没

### 1.2 核心研究问题

> **给定时序窗口语料库 D = {S₁, ..., S_N} 和冻结预训练 TSFM Φ，能否在无辅助模型训练、无参数更新、无外部评估器的情况下，为每个窗口 Sᵢ 评估其对 TSFM 训练的质量价值？**

### 1.3 为什么是零训练（Training-Free）

一个自然应对是训练有监督质量分类器。但TSFM预训练语料库通常缺乏质量标注——对100B+时间点中的极小部分进行标注都不可行。零训练方法不是便利选择，而是部署在真实TSFM语料库上的必要条件。

### 1.4 三个子问题（SP1-SP3）

| 子问题 | 内容 | 对应方法阶段 |
|--------|------|-------------|
| **SP1：信号提取** | TSFM前向传播中哪些行为信号携带输入质量信息？如何高效收集？ | Phase 1 |
| **SP2：领域-质量解缠** | 如何将真正低质量数据与仅对TSFM分布外（但干净）的数据分开？ | Phase 2（核心） |
| **SP3：因果验证** | 如何验证质量分数因果改善下游训练，而非仅仅与启发式相关？ | Phase 4 |

---

## 2. 核心洞察与设计哲学

### 2.1 第一性原理

> **预训练的TSFM本身就是一个隐式的数据质量oracle。** 它在预训练中接触了数百万条时序，已经学会了什么是"正常"的时序模式。当面对干净、结构良好的数据时，TSFM表现出专注的注意力和平稳的预测；当面对噪声或异常数据时，表现出分散的注意力和不稳定的行为。**质量评估归结为"这个样本是否符合学习到的分布？"——TSFM在每次前向传播中隐式回答这个问题。**

### 2.2 为什么不用LLM（与TSRating的根本区分）

TSRating（ICLR 2026）证明了外部LLM可以作为TS质量裁判——但代价是大量LLM API调用和元学习训练。我们的洞察更激进：**TSFM自己知道的比任何外部LLM都多。** 外部LLM在TS数据理解上本就有困难（TSQAgent实证发现），而TSFM已经内化了训练分布的统计规律——它是更知情、更高效的"裁判"。

### 2.3 领域混淆问题（方法的核心挑战）

TSFM的预测误差可能来自两个不同的原因：
- **(a) 数据质量差**（噪声高、有异常）→ 应该过滤
- **(b) 数据太特殊**（TSFM没学过这个领域，但数据本身干净）→ 不应该过滤，反而应该保留以增加多样性

问题：**仅凭原始预测误差无法区分(a)和(b)**——一条干净的金融时序和一条噪声电力时序可能产生相同的预测损失。

### 2.4 解决方法：画像条件同类校准

**核心思想：** 用统计画像（趋势强度、季节性、平稳性等12维特征）将时序分组。在画像相似的同类群体内：
- 如果某样本的预测误差远高于同类中位数 → 很可能是质量差（同类都是干净数据，你却是噪声多的那个）
- 如果整个同类的预测误差都高 → 很可能只是领域难（大家都来自TSFM没怎么学过的领域）

这本质上是用统计画像实现后门调整准则：$\mathbf{p}_i$阻塞了"领域→行为"的后门路径，使"质量→行为"的直接效应能在每个画像层内被识别。

### 2.5 设计哲学对标 work1

| | work1 (ForecastCore) | work2 (IntroSpect-TS) |
|---|---|---|
| 核心洞察 | 模式向量替换领域标签作为分组标准 | TSFM推理行为作为隐式质量oracle |
| 关键挑战 | 领域标签对预测难度无因果信息 | 领域混淆（质量 vs 难度） |
| 核心机制 | 模式分组→代理效用→次模选择 | 行为信号→画像校准→同类z-score |
| 复杂度 | O(N) | O(N) |
| 就业对标 | 时序AI | 模型内省 + LLM数据治理 + AI Infra |

---

## 3. 与已发表工作的精确定位

### 3.1 文献全景表

| 论文 | 发表 | 质量oracle | 需训练？ | LLM调用？ | 领域混淆处理？ |
|------|------|----------|---------|----------|-------------|
| Wen et al. | NeurIPS WS 2024 | 对比准确率 | 是 | 否 | 否 |
| **TSRating** | **ICLR 2026全文** | **LLM pairwise** | **是（MAML+TSTrater）** | **大量** | **否** |
| TSQAgent | arxiv 2026 | LLM agentic | 否 | 大量 | 否 |
| TSFMAudit | arxiv 2026 | Probe dynamics | 是 | 否 | 参考模型校准 |
| IGDS | NeurIPS 2026 | LLM SAE特征 | 是（SAE训练） | 否 | 否 |
| LTSV | arxiv 2025 | in-context finetuning | 是 | 否 | 否 |
| **IntroSpect-TS** | **ours** | **TSFM行为信号** | **零** | **零** | **是（画像同类校准）** |

### 3.2 TSRating vs IntroSpect-TS 核心区分

> **TSRating = 外部LLM当裁判 + 元学习训练评分器**
> **IntroSpect-TS = TSFM自己当裁判 + 零训练同类校准**
>
> 两者不是"谁更好"，而是**根本不同的范式**：从外部oracle（LLM）到自省oracle（TSFM）。我们的三个独有优势：
> 1. **零API成本**：不需要GPT-4o调用
> 2. **零训练**：不需要MAML + TSRater训练
> 3. **区分难vs脏**：同类校准处理领域混淆——TSRating没有这个能力

---

## 4. 方法详解：四个阶段

### Phase 1: 多信号行为探测（Multi-Signal Behavior Probing）

**操作：** 对每条时序Sᵢ，通过冻结TSFM Φ做一次前向传播，收集4类行为信号。

#### 信号1：输出级——逐位置预测误差轨迹（3维）

```
e_{i,t} = (y_{i,t} - ŷ_{i,t})²  对每个时间步t

汇总为3个鲁棒统计量:
  - median(e_{i,t})    → 中心难度
  - IQR(e_{i,t})       → 稳定性（低IQR=均匀困难，高IQR=局部异常）
  - p90(e_{i,t})        → 最坏情况

输出: Ē_i ∈ ℝ³
```

**为什么不用均值？** 两个相同均方误差的样本可能误差分布完全不同——一个是均匀的中等误差，另一个是大部分低误差+偶发极高误差（传感器故障）。均值掩盖了这种差异。

#### 信号2：注意力级——逐层注意力熵（L维）

```
对每层l:
  H_i^(l) = -(1/(H·T)) Σ_h Σ_t α_t^(l,h) log α_t^(l,h)   (α: 注意力分布)

直觉:
  - 低熵 → "我知道该看哪里" → 数据干净、模式熟悉
  - 高熵 → "我不确定该看哪里" → 数据噪声大或不规则

输出: H_i ∈ ℝ^L
```

**为什么正交于输出误差？** 一条时序可能预测损失中等，但TSFM的注意力路由非常困难——揭示内隐的质量问题。

#### 信号3：表示级——层间表示变化（L-1维）

```
对每对相邻层(l, l+1):
  z^(l) = mean_pool(hidden_states^(l))       # 池化隐藏状态
  Δ_i^(l) = 1 - cos(z^(l), z^(l+1))           # 余弦距离

直觉:
  - 小变化 → 表示稳定，数据结构良好
  - 大变化 → 表示突变，TSFM在"挣扎"

输出: Δ_i ∈ ℝ^(L-1)
```

**为什么与注意力熵互补？** 一个捕捉"关注哪里"，一个捕捉"在计算什么"。

#### 信号4：整体——预测损失（1维）

```
L_i = (1/T) Σ_t e_{i,t}
```

#### 完整行为签名

```
B_i = [Ē_i; H_i; Δ_i; L_i] ∈ ℝ^{D_B}

D_B = 3 + L + (L-1) + 1 = 2L + 4

对典型TSFM (L=12~20层): D_B = 28~44维
```

**计算成本：** N次前向传播。对10^5窗口、200M参数TSFM → 约3 A100 GPU-hour（预训练成本的千分之一量级）。

---

### Phase 2: 画像条件行为校准（核心算法）

#### 步骤1：提取统计画像（12维）

对每条时序Sᵢ，提取12维统计特征向量pᵢ：

| # | 特征 | 计算方式 | 物理含义 |
|---|------|---------|---------|
| 1 | 趋势强度 | OLS拟合 R² | 趋势成分解释了多少方差 |
| 2 | 趋势线性度 | 线性vs二次拟合比 | 趋势是否接近直线 |
| 3 | 季节性强度 | FFT主导频率能量比 | 周期性有多强 |
| 4 | 季节性稳定性 | 滑动窗口季节相关方差 | 周期性规律是否稳定 |
| 5 | 平稳性 | ADF检验 p-value | 统计特性是否随时间变化 |
| 6 | 样本熵 | 近似熵/样本熵 | 序列复杂度 |
| 7 | 变点密度 | PELT检测的变点数/T | 有多少结构断点 |
| 8 | 平均变点幅度 | 变点前后的均值差均值 | 断点有多剧烈 |
| 9 | 残差自相关(滞后1) | Ljung-Box Q 滞后1 | 去除趋势/季节后是否仍有近期依赖 |
| 10 | 残差自相关(滞后7) | Ljung-Box Q 滞后7 | 去除趋势/季节后是否仍有周周期依赖 |
| 11 | 信噪比(SNR) | 信号方差/噪声方差 | 数据的干净程度 |
| 12 | 异常密度 | IQR离群点比例 | 有多少异常值 |

**重要设计选择：** SNR和异常密度是"部分质量指示"的特征——将它们纳入画像意味着从行为偏差中识别质量时**排除了SNR和异常率已经能解释的部分**。这使校准更保守但更可靠。

#### 步骤2：画像空间KNN同类分组

```
对每个样本i:
  在画像空间中找到K=50个最近邻（余弦相似度，L2归一化向量）
  得到同类集合 N(i) = {j₁, ..., j_K}
```

**为什么选KNN而不是聚类？** KNN保证每个样本的同类是"它自己的最近邻"，而聚类强制簇内所有样本互为同类。KNN更灵活——邻域大小固定（K=50），不受数据分布不均影响。

#### 步骤3：组内z-score归一化

```
对每个行为维度d和每个样本i:
  z_{i,d} = (B_{i,d} - median_{j∈N(i)}(B_{j,d})) / (IQR_{j∈N(i)}(B_{j,d}) + ε)
```

**为什么用IQR而不是标准差？** 同类群体中可能存在噪声样本——它们不应扭曲参考分布。IQR对离群值具有鲁棒性。

**物理含义：**
- z_{i,d} > 0 → 样本i在维度d上的行为比同类"更差"（误差更高/注意力更散/表示变化更大）
- z_{i,d} < 0 → 样本i在维度d上的行为比同类"更好"
- z_{i,d} ≈ 0 → 样本i在维度d上与同类无显著差异

#### 步骤4：多信号融合

```
q_i = -Σ_d w_d · z_{i,d}    (w_d ≥ 0, Σ_d w_d = 1)

默认均匀权重: w_d = 1/D_B  (最大熵原则)
```

**取负号：** 使q_i > 0表示高质量（行为优于同类），q_i < 0表示低质量。

---

### Phase 3: 质量引导的数据分层

```
按q_i分位数分层（默认α=0.25）:
  - Top-25%:    q_i ≥ τ_high   → 高质量，直接用于训练
  - Mid-50%:    τ_low ≤ q_i < τ_high  → 正常质量
  - Bottom-25%: q_i < τ_low     → 低质量，供清洗或排除
```

**可选LLM辅助：** 对边界样本（|q_i| < δ），可选用LLM进行成对比较。但这是严格可选的——IntroSpect-TS在没有LLM的情况下是完整方法。

---

### Phase 4: 下游TSFM验证

通过受控数据选择协议因果验证质量分数：

```
对不同标准选择的数据子集:
  - IntroSpect-TS Top-25%
  - IntroSpect-TS Bottom-25%
  - Random-25%
  - Raw Loss-25%  (最低原始预测误差)
  - SNR-based-25%
  - Anomaly-rate-25%
  - Learned Scorer (XGBoost on profiles, 监督上界)
  - Full data (上界)

对每个子集微调TSFM → 测量下游预测MSE/MAE
```

---

## 5. 形式化理论

### 命题1: 条件质量可识别性

```
假设:
  (A1) 领域难度由画像决定: D_i = f(p_i) + η_i, E[η_i|p_i] = 0
  (A2) 行为可加性分离质量和难度: B_{i,d} = g_d(Q_i) + h_d(D_i) + ε_{i,d}, E[ε_{i,d}|Q_i,D_i] = 0

结论:
  对任意 p_i = p_j:
    E[B_{i,d} - B_{j,d} | p_i = p_j] = g_d(Q_i) - g_d(Q_j)

即: 等画像条件下，行为差异识别了独立于领域难度的质量差异。
```

**证明（3行）：**
1. (A1) → p_i=p_j时 D_i-D_j = η_i-η_j → E[D_i-D_j|p_i=p_j] = 0
2. (A2) → E[B_{i,d}-B_{j,d}|p_i=p_j] = g_d(Q_i)-g_d(Q_j) + E[h_d(D_i)-h_d(D_j)|p_i=p_j]
3. 第二项因 E[D_i|p_i]=E[D_j|p_j] 当 p_i=p_j 时消失 → 得证

**定位：** 这是后门调整准则（Pearl, 2009）的直接应用。画像作为调整集。不是理论创新，而是方法论透明性工具——明确列出校准有效所需的条件假设，让读者知道在什么情况下方法会失效。

---

## 6. 代码实现思路

### 6.1 项目结构

```
work2/
├── introspect_ts/
│   ├── __init__.py
│   ├── profiling.py          # 统计画像提取（Phase 1 profile）
│   ├── behavior.py           # TSFM行为信号提取（Phase 1 behavior）
│   ├── calibration.py        # 画像条件同类校准（Phase 2核心算法）
│   ├── stratification.py     # 质量分层（Phase 3）
│   ├── validation.py         # 下游TSFM验证（Phase 4）
│   ├── baselines.py          # 基线方法（Raw Loss, SNR, Learned Scorer等）
│   ├── datasets.py           # 数据集加载和窗口生成
│   ├── utils.py              # 工具函数
│   └── config.py             # 超参数配置
│
├── experiments/
│   ├── run_main.py           # 主实验
│   ├── run_ablation.py       # 消融实验
│   ├── run_hard_vs_dirty.py  # HBC vs EBD 实验
│   └── run_analysis.py       # 额外分析（分布/相关/跨架构）
│
└── notebooks/
    └── exploratory.ipynb     # 探索性分析
```

### 6.2 Phase 1 核心函数

```python
# profiling.py
def extract_statistical_profile(series: np.ndarray) -> np.ndarray:
    """
    输入: 单变量时序 (T,)
    输出: 12维统计画像
    
    实现:
      1. STL分解 → 趋势/季节/残差
      2. OLS拟合 → 趋势强度(R²), 趋势线性度
      3. FFT → 季节强度, 主导频率
      4. statsmodels ADF → 平稳性p值
      5. nolds → 样本熵
      6. ruptures PELT → 变点密度, 幅度
      7. statsmodels Ljung-Box → 残差自相关(lag1, lag7)
      8. 信号方差/噪声方差 → SNR
      9. IQR离群点比例 → 异常密度
    """
    pass

# behavior.py
def extract_behavior_signature(tsfm, series, horizon=96):
    """
    输入: 冻结TSFM模型, 时序, 预测视界
    输出: B_i ∈ ℝ^{2L+4}
    
    实现:
      1. tsfm.forward(series) → predictions, attention_maps, hidden_states
      2. 逐位置误差: e_t = (y_t - ŷ_t)² → [median, IQR, p90]
      3. 逐层注意力熵: 对每层l, 每头h, 每位置t计算 -Σα log α → 层均值
      4. 层间表示变化: 对每相邻层, mean_pool → cos距离
      5. 整体损失: mean(e_t)
    返回: concatenated vector
    """
    pass
```

### 6.3 Phase 2 核心函数（算法核心）

```python
# calibration.py
def profile_conditioned_calibration(
    behavior_signatures: np.ndarray,  # (N, D_B)
    profiles: np.ndarray,              # (N, 12)
    K: int = 50,
    weights: np.ndarray = None
) -> np.ndarray:
    """
    输入:
      behavior_signatures: N个样本的行为签名 B_i
      profiles: N个样本的统计画像 p_i
      K: KNN近邻数
      weights: 融合权重 (None=均匀)
    
    输出:
      quality_scores: N个质量分数 q_i
    
    步骤:
      1. L2归一化画像 → cosine相似度矩阵
      2. 构建KNN图 (scikit-learn NearestNeighbors)
      3. 对每个样本i:
         a. 取K个近邻索引 N(i)
         b. 对每个行为维度d:
            median = np.median(behavior_signatures[N(i), d])
            iqr = np.subtract(*np.percentile(behavior_signatures[N(i), d], [75, 25]))
            z[i, d] = (behavior_signatures[i, d] - median) / (iqr + eps)
      4. 融合: q_i = -Σ_d weights[d] * z[i, d]
    
    时间复杂度:
      - 画像KNN: O(N²D_P) 朴素 / O(N log N) with FAISS
      - z-score计算: O(N·K·D_B)  ← 主导项
      - 融合: O(N·D_B)
      - 总体: O(N·K·D_B)，线性于N
    """
    pass
```

### 6.4 Phase 4 验证函数

```python
# validation.py
def validate_quality_scores(
    tsfm,
    dataset,
    quality_scores: np.ndarray,
    alpha: float = 0.25
) -> dict:
    """
    输入:
      tsfm: 目标TSFM
      dataset: 微调数据
      quality_scores: IntroSpect-TS质量分数
      alpha: 选择比例
    
    输出:
      results: {method: MSE}
    
    步骤:
      1. 按q_i排序 → 取top/bottom α%
      2. 按L_i排序 → 取lowest α%
      3. 按SNR排序 → 取highest α%
      4. 按异常率排序 → 取lowest α%
      5. 随机选α%
      6. 全量数据
      
      对每种选择:
        - 微调TSFM (AdamW, lr=1e-5, 10 epochs)
        - 评估下游MSE/MAE
    """
    pass
```

### 6.5 依赖库

| 库 | 用途 |
|----|------|
| `torch` + `transformers` | TSFM模型加载与推理 |
| `statsmodels` | STL分解、ADF检验、Ljung-Box检验 |
| `scipy` | FFT、信号处理 |
| `scikit-learn` | KNN、标准化、度量 |
| `ruptures` | PELT变点检测 |
| `nolds` | 样本熵计算 |
| `xgboost` | Learned Scorer基线 |
| `FAISS` (可选) | 大规模KNN加速 |

---

## 7. 实验设计

### 7.1 架构和数据集

| 架构 | 参数量 | 模型类型 |
|------|--------|---------|
| TimesFM | 200M | Decoder-only patched transformer |
| MOIRAI | 311M | Masked encoder with multi-patch |
| MOMENT | 40M | T5-style encoder-decoder |

| 数据集 | 序列数 | 频率 | 窗口数（约） |
|--------|--------|------|-------------|
| Electricity | 321 | 每小时 | 15,000 |
| Traffic | 862 | 每小时 | 30,000 |
| Weather | 21 | 10分钟 | 20,000 |
| ETTh1/ETTh2 | 各7 | 每小时 | 各4,000 |
| ETTm1 | 7 | 15分钟 | 15,000 |
| Exchange | 8 | 每日 | 3,000 |
| ILI | 7 | 每周 | 600 |

窗口长度512，步长128，总计约85,000个窗口。

### 7.2 核心实验矩阵

| 实验 | 目的 | 关键假设 |
|------|------|---------|
| **主结果** | Top-25% vs Bottom-25% vs 8基线 | IntroSpect-TS筛选数据优于所有基线 |
| **消融** | 逐组件移除 | 移除peer calibration导致最大退化 |
| **难vs脏 (HBC/EBD)** | Exchange汇率 vs 电力+噪声 | raw loss无法区分，IntroSpect-TS能区分 |
| **有监督学习对比** | XGBoost vs IntroSpect-TS | 行为信号超越静态画像 |
| **跨架构泛化** | TimesFM分数→MOIRAI | 自评分优于跨评分 |

### 7.3 当前状态

⚠️ **实验尚未运行。** 所有表格数值为投影值（†），基于试点分析。论文明确标注"实验设计、基线描述和消融假设是最终的，不会改变"。

---

## 8. 论文写作（LaTeX）

### 8.1 文件清单

```
work2/
├── en/
│   ├── introspect_ts-20260609.tex    # 英文论文 (398行, 47KB)
│   ├── references.bib                # 参考文献 (30条)
│   ├── math_commands.tex             # 数学宏
│   └── iclr2026_conference.sty       # ICLR 2026 样式
│
├── zh/
│   ├── introspect_ts_zh-20260609.tex # 中英双语论文 (21KB)
│   ├── references.bib                # 同 en/
│   └── math_commands.tex + .sty      # 同 en/
│
└── work2_summary.md                  # 本文件
```

### 8.2 章节结构

```
§1 Introduction         (6段，TSFM背景→LLM局限→TSRating/Wen/TSQAgent/TSFMAudit gap
                            → 三子问题→IntroSpect-TS→三大贡献)
§2 Related Work         (§2.1 数据质量 + TSRating对比表 + 文献全景表
                            §2.2 模型内省 §2.3 时序模式表征)
§3 Problem Formulation  (形式化定义 + SP1/SP2/SP3)
§4 Method               (Algorithm 1 + §4.1设计理念(表) + §4.2-4.5 四阶段)
§5 Experiments          (投影方案 + 8基线 + 消融 + HBC/EBD + 额外分析)
§6 Discussion           (为什么有效 + IGDS/TSRating三方对比 + LLM数据治理 + 局限)
§7 Conclusion
```

### 8.3 论文中表格清单

| 表 | 内容 | 大小 |
|----|------|------|
| Tab 1a | IntroSpect-TS vs TSRating 对比（8×3） | §2.1 |
| Tab 1b | 相关文献全景（8×3） | §2.1 |
| Tab 2 | 关键挑战与设计选择（5×3） | §4.1 |
| Tab 3 | 投影主结果（8列×6行） | §5.2 |
| Tab 4 | 投影消融（7行） | §5.3 |
| Tab 5 | 投影HBC vs EBD（5行） | §5.4 |
| Alg 1 | IntroSpect-TS 伪代码 | §4 |
| Fig 1 | 框架总览（占位） | §4.3 |

### 8.4 编译方法

```bash
# 英文版
cd work2/en
pdflatex introspect_ts-20260609.tex
bibtex introspect_ts-20260609
pdflatex introspect_ts-20260609.tex
pdflatex introspect_ts-20260609.tex

# 中文版
cd work2/zh
xelatex introspect_ts_zh-20260609.tex
bibtex introspect_ts_zh-20260609
xelatex introspect_ts_zh-20260609.tex
xelatex introspect_ts_zh-20260609.tex
```

---

## 9. 迭代历史

| 循环 | 类型 | 关键改动 |
|------|------|---------|
| — | 方向探索 | deep-research + ccf-idea-optimizer 确定方向 |
| V1→V3 | 方法收敛 | "TS-DataFlow框架" → "IntroSpect-TS方法" |
| C1 | 审稿 | Proposition + LLM implications + references.bib |
| C2 | 审稿（对标work1） | 表1+表2, §4.1总体思路, 子问题分解 |
| C3 | 审稿 | label/abstract/algorithm/rebalance/figure |
| C4 | 审稿（精修） | 动词/命名/实验状态/证明符号/复现声明 |
| C5 | 审稿（去重） | §6.1重写为元层次, HBC-EBD参数论证 |
| C6 | 审稿（专业化） | Proposition降级 + Learned Scorer + 画像维度论证 |
| C7 | 审稿（细修） | Proposition一致性, 维度讨论, §2.3扩展 |
| C8 | 审稿（极端严格） | 全文Proposition统一, 删除src-pos, Anomaly列 |
| C9 | 文献更新 | Wen et al., TSFMAudit 引用 |
| C10 | 文献更新（重大） | **TSRating (ICLR 2026)** 核心竞争者引用 |
| C11 | 审稿 | 去冗余, Learned Scorer标注 |
| C12 | 审稿+评分 | **TSRating对比表**, gap声明尖锐化 |
| C13 | 表述优化 | Design Rationale含TSRating, HBC/EBD分段, 单变量假设 |
| C14 | 汇总清理 | 删除DataFlow, 创建本摘要 |

---

## 10. 待完成工作

| 优先级 | 任务 | 说明 |
|--------|------|------|
| 🔴 P0 | 运行全部实验 | 3 TSFM × 7 datasets × 8 baselines × 5 experiments |
| 🔴 P0 | 替换投影值 | 所有 $\dagger$ → 真实MSE/MAE |
| 🟡 P1 | 制作Figure 1 | 框架总览图（4 Phase可视化） |
| 🟡 P1 | 制作分析图 | 分数分布直方图, HBC/EBD对比图 |
| 🟡 P1 | 完善references | ForecastCore等占位引用的作者信息 |
| 🟢 P2 | 中文版同步 | zh文件滞后于en约1-2个修订周期 |
| 🟢 P2 | 致谢填入 | 真实资助信息 |
| 🟢 P2 | 代码实现 | `introspect_ts/` 包的4个核心模块 |
