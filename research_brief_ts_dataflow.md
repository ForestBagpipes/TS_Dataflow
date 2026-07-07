# Work2 研究简报：TS-DataFlow

## LLM引导的时序基础模型自动数据制备系统

**作者：** 胡宏彬  
**日期：** 2026-06-08  
**与work1关系：** work1解决"训什么数据"（pattern-based offline data selection），work2解决"数据怎么来的"（agent-driven data preparation pipeline）  
**对标框架：** DataFlow (Wentao Zhang @ PKU / OpenDCAI)  
**论文暂定名：** *TS-DataFlow: LLM-Guided Automatic Data Preparation for Time Series Foundation Models*

---

## 目錄

1. [核心理念](#1-核心理念)
2. [DataFlow 架构速览](#2-dataflow-架构速览)
3. [Gap分析：为什么现有DataFlow不能直接处理时序数据](#3-gap分析)
4. [TS-DataFlow 系统架构设计](#4-ts-dataflow-系统架构设计)
5. [Phase 1: 时序特化算子设计](#5-phase-1-时序特化算子设计)
6. [Phase 2: LLM引导的时序质量评估机制](#6-phase-2-llm引导的时序质量评估机制)
7. [Phase 3: 端到端TSFM数据制备Pipeline](#7-phase-3-端到端tsfm数据制备pipeline)
8. [Phase 4: Agent集成方案](#8-phase-4-agent集成方案)
9. [Phase 5: TSFM训练验证](#9-phase-5-tsfm训练验证)
10. [论文大纲](#10-论文大纲)
11. [实施路线图](#11-实施路线图)

---

## 1. 核心理念

### 1.1 一句话总结

将LLM社区极度成熟的 **agent-based data preparation 范式**（DataFlow/DataJuicer）系统性地迁移到时序基础模型（TSFM）领域，构建首个 **LLM引导的时序数据自动制备系统**。

### 1.2 为什么是蓝海

```
LLM数据制备生态：                     TSFM数据制备生态：
━━━━━━━━━━━━━━━━━━━━━━━              ━━━━━━━━━━━━━━━━━━━━━━━
Data Juicer (ICLR 2024) ✓            数据制备系统：✗ (完全空白)
NeMo Curator (NVIDIA)  ✓             LLM引导质量评估：✗
DataFlow (Wentao Zhang)✓             Agent编排时序pipeline：✗
Multi-Actor (ACL 2025)  ✓            时序专有operator库：✗
LANCE (EMNLP 2025)     ✓            端到端制备→训练验证：✗
200+ Operators          ✓
6 Domain Pipelines      ✓
Agent自动编排           ✓
━━━━━━━━━━━━━━━━━━━━━━━              ━━━━━━━━━━━━━━━━━━━━━━━
极度成熟 ←────────────────→ 几乎空白（仅LTSV做data valuation）
```

### 1.3 与work1的互补关系

| 维度 | work1 (ForecastCore) | work2 (TS-DataFlow) |
|------|---------------------|---------------------|
| 核心问题 | 选什么数据训练 | 数据怎么制备 |
| 时机 | 训练前离线选择 | 训练前数据准备全链路 |
| 方法 | 模式聚类+代理模型+次模选择 | Agent系统+LLM评估+算子库 |
| 产出 | 高质量数据子集 | 高质量制备后的完整数据集 |
| 就业 | 时序AI | LLM数据管线 + Agent + AI Infra |

---

## 2. DataFlow 架构速览

> 完整源码已clone至 `work2/DataFlow/`

### 2.1 核心抽象三层

```
┌──────────────────────────────────────────────────┐
│                 Pipeline Layer                     │
│  PipelineABC → compile() → forward()              │
│  AutoOP wrapper 捕获 run() 调用                   │
│  OperatorNode + KeyNode 构成DAG                  │
└──────────────────────────────────────────────────┘
                        │
┌──────────────────────────────────────────────────┐
│                 Operator Layer                     │
│  @OPERATOR_REGISTRY.register() 装饰器注册         │
│  OperatorABC → run(storage, input_key, output_key) │
│  分类：generate / filter / eval / refine / dedup  │
└──────────────────────────────────────────────────┘
                        │
┌──────────────────────────────────────────────────┐
│                 Storage Layer                      │
│  DataFlowStorage (ABC)                            │
│  └─ FileStorage: step-based JSONL/JSON/Parquet   │
│  └─ LazyFileStorage: 内存缓冲+原子写入            │
│  └─ MyScaleDBStorage: ClickHouse持久化           │
│  key-tracking: 自动追踪列名流转                   │
└──────────────────────────────────────────────────┘
```

### 2.2 算子设计模式（核心）

```python
@OPERATOR_REGISTRY.register()
class MyOperator(OperatorABC):
    def __init__(self, llm_serving: LLMServingABC, **config):
        # 构造函数：依赖注入（LLM Serving, 阈值等）
        pass

    def run(self, storage: DataFlowStorage,
            input_key: str = "raw_content",
            output_key: str = "result"):
        dataframe = storage.read('dataframe')   # 读取前一步输出
        # ... 处理数据 ...
        storage.write(processed_dataframe)       # 写回缓存
        return output_key                        # 返回key供后续引用
```

### 2.3 Pipeline编排模式

```python
class MyPipeline(PipelineABC):
    def __init__(self):
        self.storage = FileStorage(first_entry_file_name="input.jsonl")
        self.llm_serving = APILLMServing_request(api_url="...")
        self.op1 = MyOperator(llm_serving=self.llm_serving)
        self.op2 = AnotherOperator(...)

    def forward(self):
        self.op1.run(storage=self.storage.step(), input_key="x", output_key="y")
        self.op2.run(storage=self.storage.step(), input_key="y", output_key="z")

pipeline = MyPipeline()
pipeline.compile()   # 构建OperatorNode DAG，验证key chain
pipeline.forward()   # 顺序执行
```

### 2.4 关键特性清单

| 特性 | DataFlow实现 | 对TS-DataFlow的启示 |
|------|-------------|-------------------|
| 算子注册 | `@OPERATOR_REGISTRY.register()` 装饰器 | 直接复用 |
| 数据流转 | `storage.step()` 递增步骤，`storage.read/write` | 需要扩展为TS格式 |
| Key追踪 | 自动验证`input_key`/`output_key`链 | 直接复用 |
| LLM Serving | `APILLMServing_request`, vLLM, SGLang | 直接复用（调用LLM做TS质量评估） |
| Prompt系统 | `PromptABC` + f-string模板 | 需要设计TS质量评估专用prompt |
| Agent编排 | 自然语言→workflow DAG | 核心创新点 |
| Ray加速 | `RayAcceleratedOperator` | 可用于大规模TS并行处理 |
| WebUI | 可视化pipeline编辑 | 长期目标 |

---

## 3. Gap分析

### 为什么现有DataFlow不能直接处理时序数据

| Gap | 详细说明 | 需要的TS特化 |
|-----|---------|-------------|
| **数据格式** | DataFlow只处理text/JSONL，key-value对 | 需要支持time-indexed multivariate数据 |
| **数据存储** | FileStorage按行存储，无时间索引 | 需要TS-aware存储（时间窗口缓存） |
| **算子语义** | 算子处理文本：质量评分、去重、改写 | 算子需要处理数值/时序：异常检测、季节性分解、插补 |
| **LLM理解** | LLM直接理解文本语义 | LLM无法直接理解数值时序 → 需要统计画像bridge |
| **去重机制** | MinHash/Jaccard for text | 时序去重需要DTW/交叉相关性 |
| **质量维度** | 语言流畅度、事实准确性、教育价值 | 时序质量：平稳性、噪声水平、缺失模式、异常密度 |
| **数据增强** | 同义词替换、回译 | 时序增强：时间扭曲、幅度缩放、频率掩码 |
| **评估benchmark** | 文本QA评估 | TSFM forecasting/imputation/classification评估 |

### 核心挑战（Root Challenge）

> **LLM如何理解并评估纯数值时序数据的质量？**

解决方案：**时序统计画像（TS Statistical Profiling）作为LLM与数值时序之间的语义桥梁**。

---

## 4. TS-DataFlow 系统架构设计

### 4.1 整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                     TS-DataFlow System                                │
│                                                                       │
│  ┌───────────────┐    ┌──────────────────┐    ┌───────────────────┐  │
│  │  TS DataLake   │───▶│ TS-DataFlow Agent │───▶│ Prepared TS Data  │  │
│  │  (raw series)  │    │ (自动编排pipeline) │    │ (训练就绪)        │  │
│  └───────────────┘    └──────────────────┘    └───────────────────┘  │
│                              │                                        │
│         NL instruction:     │    Composes:                            │
│   "清理这批电力数据，去掉  │    Dedup → AnomalyDetect →              │
│    异常点，评估整体质量"   │    QualityFilter → TSFM Train           │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    TS Operator Library                          │    │
│  │                                                                │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐    │    │
│  │  │Profiling │ │ Cleaning │ │ Filter   │ │ Augmentation  │    │    │
│  │  │算子(5)   │ │算子(4)   │ │算子(3)   │ │算子(3)         │    │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘    │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐              │    │
│  │  │Dedup     │ │Alignment │ │ LLM Quality Judge │              │    │
│  │  │算子(2)   │ │算子(2)   │ │ (核心创新算子)    │              │    │
│  │  └──────────┘ └──────────┘ └──────────────────┘              │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                   TS Storage Layer                              │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                      │    │
│  │  │ TSFileStorage    │  │ TSDataFrame      │                      │    │
│  │  │ (time-indexed    │  │ (pandas DataFrame │                      │    │
│  │  │  step caching)   │  │  with datetime idx)│                     │    │
│  │  └─────────────────┘  └─────────────────┘                      │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 代码目录结构

```
work2/ts_dataflow/
├── __init__.py
├── version.py
│
├── core/                          # 核心基类
│   ├── __init__.py
│   ├── ts_operator.py            # TSOperatorABC extends OperatorABC
│   ├── ts_storage.py             # TSFileStorage extends DataFlowStorage
│   └── ts_profiler.py            # 统计画像引擎
│
├── operators/                     # 时序特化算子库
│   ├── __init__.py
│   ├── profiling/                 # Phase 1: 时序画像
│   │   ├── ts_statistical_profiler.py    # 多维统计特征提取
│   │   └── ts_profile_aggregator.py      # 画像聚合
│   ├── cleaning/                  # Phase 2: 数据清洗
│   │   ├── ts_deduplication.py           # MinHash+DTW去重
│   │   ├── ts_anomaly_detector.py        # 异常检测与标记
│   │   ├── ts_imputation.py              # 缺失值插补
│   │   └── ts_noise_filter.py            # 噪声过滤
│   ├── quality/                   # Phase 3: 质量评估（核心创新）
│   │   ├── ts_llm_quality_judge.py       # LLM引导质量评分
│   │   └── ts_quality_filter.py          # 基于质量评分的数据筛选
│   ├── augmentation/              # Phase 4: 数据增强
│   │   ├── ts_time_warping.py            # 时间扭曲
│   │   ├── ts_magnitude_scaling.py       # 幅度缩放
│   │   └── ts_frequency_masking.py       # 频率掩码
│   ├── alignment/                 # Phase 5: 多源对齐
│   │   ├── ts_resampling.py              # 重采样对齐
│   │   └── ts_temporal_merging.py        # 时序合并
│   └── evaluation/                # Phase 6: 数据集评估
│       └── ts_dataset_statistics.py      # 数据集统计报告
│
├── pipelines/                     # 预定义pipeline
│   ├── ts_cleaning_pipeline.py           # 标准清洗pipeline
│   ├── ts_quality_pipeline.py            # 质量评估pipeline
│   └── ts_full_preparation_pipeline.py   # 全链路制备pipeline
│
├── prompts/                       # TS专用LLM prompt
│   ├── ts_quality_eval.py                # 时序质量评估prompt
│   └── ts_profile_description.py         # 画像→自然语言转换
│
├── serving/                       # 扩展的LLM Serving
│   └── ts_llm_judge_serving.py          # LLM质量评估专用serving
│
├── utils/                         # 工具函数
│   ├── ts_metrics.py                     # 时序质量指标计算
│   ├── ts_patterns.py                    # 模式提取（来自work1的Phase 0）
│   └── ts_visualization.py               # 画像可视化
│
└── tests/                         # 测试
    ├── test_ts_operators.py
    ├── test_ts_pipelines.py
    └── test_llm_quality_judge.py
```

---

## 5. Phase 1: 时序特化算子设计

### 5.1 算子总表（~20 operators）

| 类别 | 算子名 | 功能 | 输入 | 输出 | 复杂度 |
|------|--------|------|------|------|--------|
| **Profiling** | `TSStatisticalProfiler` | 提取10+维统计特征 | raw series | feature columns | O(N) |
| | `TSProfileAggregator` | 样本级画像聚合 | block features | sample scores | O(1) |
| **Cleaning** | `TSAnomalyDetector` | 基于IQR/IsolationForest的异常检测 | series | anomaly flags | O(N log N) |
| | `TSImputation` | 缺失值插补（线性/样条/KNN） | series w/ NaN | filled series | O(N) |
| | `TSNoiseFilter` | 基于移动窗口的噪声平滑 | series | denoised series | O(N) |
| | `TSSamplingAligner` | 重采样到统一频率 | irregular series | regular series | O(N) |
| **Dedup** | `TSMinHashDeduplicator` | MinHash预筛选相似时间窗口 | series windows | dedup candidates | O(N·W) |
| | `TSDTWDeduplicator` | DTW精确匹配去重 | candidates | deduped windows | O(N²) |
| **Quality** | **`TSLLMQualityJudge`** ⭐ | LLM引导多维质量评分 | profiles + metadata | quality scores | O(N) per LLM call |
| | `TSQualityFilter` | 基于质量分数的过滤 | series + scores | high-quality subset | O(N) |
| | `TSStatisticalFilter` | 统计规则过滤（长度/缺失率/异常比） | series | filtered subset | O(N) |
| **Augmentation** | `TSTimeWarping` | 时间轴随机扭曲 | series | augmented series | O(N) |
| | `TSMagnitudeScaling` | 幅度随机缩放 | series | augmented series | O(N) |
| | `TSFrequencyMasking` | 频域随机掩码 | series | augmented series | O(N log N) |
| **Alignment** | `TSTemporalMerger` | 多源时序对齐合并 | multi-source series | aligned dataset | O(N·M) |
| **Evaluation** | `TSDatasetStatistics` | 数据集整体统计报告 | prepared dataset | stats report | O(N) |
| | `TSQualityReport` | 质量评估报告生成 | quality scores | Markdown report | O(1) |

### 5.2 核心算子详细设计

#### A. TSStatisticalProfiler（时序统计画像算子）

```python
@OPERATOR_REGISTRY.register()
class TSStatisticalProfiler(OperatorABC):
    """
    对每条时序样本提取多维统计特征，构建"时序画像"。
    输出特征作为LLM质量评估和下游过滤的输入。

    提取的特征（10维，可扩展）：
    ┌──────────────────────┬─────────────────────────────────┐
    │ 特征                 │ 计算方式                         │
    ├──────────────────────┼─────────────────────────────────┤
    │ trend_strength       │ OLS拟合R²                       │
    │ trend_linearity      │ 线性vs二次曲线拟合的相对效果     │
    │ seasonality_strength │ FFT主频能量占比                  │
    │ seasonality_stability│ 滑动窗口季节相关性的方差         │
    │ stationarity         │ ADF检验p-value                   │
    │ sample_entropy       │ 样本熵（复杂度度量）             │
    │ changepoint_density  │ PELT检测的变点密度               │
    │ changepoint_magnitude│ 变点幅度均值                     │
    │ residual_autocorr    │ 残差Ljung-Box Q统计量            │
    │ anomaly_density      │ IQR异常点比例                    │
    │ missing_rate         │ 缺失值比例                       │
    │ noise_level          │ 信号-噪声比（SNR）               │
    └──────────────────────┴─────────────────────────────────┘
    """
    def __init__(self, features: List[str] = None,
                 window_size: int = 168,  # 默认一周（小时级）
                 overlap: float = 0.5):
        self.features = features or DEFAULT_TS_FEATURES
        self.window_size = window_size
        self.overlap = overlap

    def run(self, storage: DataFlowStorage,
            input_key: str = "series_values",
            time_key: str = "datetime",
            output_key: str = "ts_profile"):
        df = storage.read('dataframe')
        profiles = []
        for _, row in df.iterrows():
            series = np.array(row[input_key])
            profile = self._extract_profile(series)
            profiles.append(profile)
        df[output_key] = profiles
        # 同时将各维度展开放入独立列
        for i, feat_name in enumerate(self.features):
            df[f"{output_key}_{feat_name}"] = [p[i] for p in profiles]
        storage.write(df)
        return output_key
```

#### B. TSDeduplicationOperator（时序去重算子）

```python
@OPERATOR_REGISTRY.register()
class TSTemporalDeduplicator(OperatorABC):
    """
    两阶段时序去重：
    Stage 1 (Fast): MinHash over feature vectors → 候选对
    Stage 2 (Precise): DTW on raw series → 确认重复

    区别于LLM文本去重：
    - 文本用MinHash+Jaccard
    - 时序用MinHash(feature)+DTW(raw)
    """
    def __init__(self, hash_size: int = 128,
                 dtw_threshold: float = 0.1,
                 num_bands: int = 16):
        self.hash_size = hash_size
        self.dtw_threshold = dtw_threshold
        self.num_bands = num_bands

    def run(self, storage: DataFlowStorage,
            input_key: str = "series_values",
            profile_key: str = "ts_profile",
            output_key: str = "is_duplicate"):
        df = storage.read('dataframe')

        # Stage 1: MinHash LSH
        from datasketch import MinHash, MinHashLSH
        lsh = MinHashLSH(threshold=0.5, num_perm=self.hash_size)
        minhashes = []
        for i, row in df.iterrows():
            m = MinHash(num_perm=self.hash_size)
            profile = row[profile_key]
            for val in profile:
                m.update(str(val).encode('utf8'))
            lsh.insert(i, m)
            minhashes.append(m)

        # Stage 2: DTW verification
        duplicates = set()
        for i, m in enumerate(minhashes):
            candidates = lsh.query(m)
            for j in candidates:
                if j <= i:
                    continue
                dtw_dist = fastdtw(df.iloc[i][input_key],
                                   df.iloc[j][input_key])[0]
                if dtw_dist < self.dtw_threshold:
                    duplicates.add(j)  # mark j as duplicate of i

        df[output_key] = [1 if i in duplicates else 0
                          for i in range(len(df))]
        storage.write(df)
        return output_key
```

#### C. TSLLMQualityJudge（LLM引导时序质量评估）⭐核心创新

```python
@OPERATOR_REGISTRY.register()
class TSLLMQualityJudge(OperatorABC):
    """
    LLM引导的时序数据质量多维评估。

    核心机制：统计画像 → 自然语言描述 → LLM评分
    这是LLM理解数值时序的语义桥梁（bridge mechanism）。

    评估维度：
    1. Cleanliness（清洁度）：缺失值、异常点情况
    2. Informativeness（信息量）：统计熵、变点丰富度
    3. Normality（规范性）：平稳性、季节性是否合理
    4. Temporal Coherency（时序一致性）：自相关性是否正常
    5. Domain Relevance（领域适配度）：是否符合该领域的典型模式
    """
    def __init__(self, llm_serving: LLMServingABC,
                 system_prompt: str = None,
                 quality_dimensions: List[str] = None,
                 score_range: Tuple[int, int] = (1, 5)):
        self.llm_serving = llm_serving
        self.system_prompt = system_prompt or DEFAULT_TS_QUALITY_PROMPT
        self.dimensions = quality_dimensions or DEFAULT_QUALITY_DIMENSIONS
        self.score_range = score_range

        # 画像到自然语言的转换模板
        self.profile_to_text = TSProfileToText()

    def run(self, storage: DataFlowStorage,
            profile_prefix: str = "ts_profile",
            output_key: str = "llm_quality_score"):
        df = storage.read('dataframe')

        # Step 1: 构建每个样本的自然语言画像
        nl_descriptions = []
        for _, row in df.iterrows():
            profile = self._extract_profile(row, profile_prefix)
            metadata = self._extract_metadata(row)
            nl_desc = self.profile_to_text(profile, metadata)
            nl_descriptions.append(nl_desc)

        # Step 2: 批量发送给LLM评分
        # 每批最多 batch_size 个样本，减少API调用
        llm_inputs = []
        for desc in nl_descriptions:
            prompt = (f"{self.system_prompt}\n\n"
                      f"【时序数据画像】\n{desc}\n\n"
                      f"请从以下{len(self.dimensions)}个维度逐一评分"
                      f"(1-{self.score_range[1]})：\n"
                      + "\n".join(f"{i+1}. {d}"
                                  for i, d in enumerate(self.dimensions))
                      + "\n\n请输出JSON格式的评分。")
            llm_inputs.append(prompt)

        # 使用 json_schema 约束输出格式
        json_schema = {
            "type": "object",
            "properties": {
                dim: {"type": "integer",
                      "minimum": self.score_range[0],
                      "maximum": self.score_range[1]}
                for dim in self.dimensions
            },
            "required": self.dimensions
        }

        outputs = self.llm_serving.generate_from_input(
            user_inputs=llm_inputs,
            system_prompt=self.system_prompt,
            json_schema=json_schema
        )

        # Step 3: 解析LLM输出
        df[output_key] = self._parse_quality_scores(outputs)
        for i, dim in enumerate(self.dimensions):
            df[f"{output_key}_{dim}"] = [s[dim] for s in outputs]

        storage.write(df)
        return output_key
```

---

## 6. Phase 2: LLM引导的时序质量评估机制

### 6.1 Bridge Mechanism 设计

这是整个工作的**核心科学贡献**：

```
┌───────────────────────────────────────────────────────────────┐
│                    Bridge Mechanism                             │
│                                                                │
│  Raw TS Data ──▶ Statistical Profiler ──▶ Numeric Profile     │
│     (float[])          (10+ features)                          │
│                                                                │
│                              │                                 │
│                              ▼                                 │
│  TSProfileToText ──▶ Natural Language Description             │
│                                                                │
│  Example:                                                      │
│  "这是一个电力负荷时序，长度720点，采样频率1小时。            │
│   趋势强度=0.82（强上升趋势），季节性强度=0.91                │
│   （24小时周期显著），异常点占比=3.2%（轻度），                │
│   缺失率=0%（完整），变点密度=0.05/点，                        │
│   信噪比=18.3dB（较干净）。平稳性检验通过。                   │
│   时序整体清洁，周期性规律明显，适合用作训练数据。"           │
│                              │                                 │
│                              ▼                                 │
│  LLM Quality Judge ──▶ Quality Scores (JSON)                   │
│                                                                │
│  {                                                             │
│    "cleanliness": 5,                                           │
│    "informativeness": 4,                                       │
│    "normality": 4,                                             │
│    "temporal_coherency": 5,                                    │
│    "domain_fitness": 4                                         │
│  }                                                             │
└───────────────────────────────────────────────────────────────┘
```

### 6.2 Profile-to-Text 转换器设计

```python
class TSProfileToText:
    """将统计画像转换为LLM可理解的自然语言描述"""

    def __init__(self, lang: str = "zh"):
        self.lang = lang

    def __call__(self, profile: Dict, metadata: Dict) -> str:
        """profile: {feature_name: value}, metadata: {domain, freq, length}"""
        segments = []

        # 1. 概况描述
        segments.append(self._describe_overview(metadata))

        # 2. 趋势分析
        segments.append(self._describe_trend(profile))

        # 3. 季节性分析
        segments.append(self._describe_seasonality(profile))

        # 4. 质量指标
        segments.append(self._describe_quality(profile))

        # 5. 数据完整性
        segments.append(self._describe_completeness(profile))

        # 6. 变化特征
        segments.append(self._describe_changes(profile))

        return "\n".join(segments)

    def _describe_quality(self, profile):
        snr = profile.get('noise_level', 0)
        entropy = profile.get('sample_entropy', 0)

        snr_desc = ("信号质量优秀" if snr > 20 else
                    "信号质量良好" if snr > 10 else
                    "存在一定噪声干扰")
        entropy_desc = ("信息量丰富" if entropy > 1.5 else
                        "信息量适中" if entropy > 0.5 else
                        "信息量较低，模式简单")

        return (f"质量指标：{snr_desc}（SNR={snr:.1f}dB），"
                f"{entropy_desc}（样本熵={entropy:.3f}）。")

    # ... 其他描述方法
```

### 6.3 LLM Quality Prompt 设计

```python
TS_QUALITY_SYSTEM_PROMPT = """
你是一个时序数据质量评估专家。你将收到时序数据的统计画像（描述性文本）和元数据，
请从以下维度对该时序进行1-5分的质量评分：

1. **清洁度 (cleanliness)**：数据是否干净，异常点和噪声程度。
   5分=几乎无异常/噪声，1分=严重污染无法使用。

2. **信息量 (informativeness)**：模式的复杂度和多样性。
   5分=包含丰富模式（趋势变化/季节转换/异常事件），
   1分=模式过于简单（恒值/纯白噪声）。

3. **规范性 (normality)**：是否符合典型时序的统计特征。
   5分=平稳性/季节性/自相关等统计指标正常合理，
   1分=统计特征异常（如自相关全部为0或1）。

4. **时序一致性 (temporal_coherency)**：相邻时间点的关系是否合理。
   5分=时序连续性好，自相关衰减正常，
   1分=跳跃严重或不连续。

5. **领域适配度 (domain_fitness)**：是否适合用作该领域的训练数据。
   5分=高度代表性的典型样本，1分=与该领域无关或误导性数据。

请以严格但公正的标准评分，并给出简要理由。
"""
```

### 6.4 人类标注对齐实验设计

证明LLM质量评估有效性的关键实验：

| 实验 | 描述 | 指标 |
|------|------|------|
| **Inter-rater agreement** | LLM评分 vs 3位人类专家的评分一致性 | Cohen's Kappa, ICC |
| **Score calibration** | LLM能否区分k已知质量等级的样本 | Rank correlation |
| **Downstream validation** | 高评分数据是否确实训练出更好的TSFM | MSE/MAE improvement |
| **Ablation** | 去掉profile某个维度对LLM评分准确性的影响 | Score deviation |

---

## 7. Phase 3: 端到端TSFM数据制备Pipeline

### 7.1 标准清洗Pipeline

```python
class TSCleaningPipeline(PipelineABC):
    """TSFM数据标准清洗流水线"""

    def __init__(self, input_path: str, llm_api_url: str = None):
        super().__init__()
        self.storage = FileStorage(
            first_entry_file_name=input_path,
            cache_path="./cache/ts_cleaning",
            file_name_prefix="ts_dataflow_cleaning",
            cache_type="parquet"  # 时序数据推荐parquet
        )

        # 统计/规则算子（不需要LLM）
        self.profiler = TSStatisticalProfiler(
            window_size=168, overlap=0.5
        )
        self.anomaly_detector = TSAnomalyDetector()
        self.imputation = TSImputation(method='linear')
        self.stat_filter = TSStatisticalFilter(
            min_length=168,
            max_missing_rate=0.3,
            max_anomaly_rate=0.1
        )

        # LLM引导算子（需要LLM Serving）
        if llm_api_url:
            self.llm_serving = APILLMServing_request(
                api_url=llm_api_url,
                model_name="gpt-4o",
                max_workers=50
            )
            self.quality_judge = TSLLMQualityJudge(
                llm_serving=self.llm_serving
            )
            self.quality_filter = TSQualityFilter(
                min_score=3
            )

        # 去重算子
        self.deduplicator = TSTemporalDeduplicator(
            hash_size=128, dtw_threshold=0.1
        )

        # 评估算子
        self.dataset_stats = TSDatasetStatistics()

    def forward(self):
        # Step 1: 时序画像
        self.profiler.run(
            storage=self.storage.step(),
            input_key="series_values",
            time_key="datetime",
            output_key="profile"
        )

        # Step 2: 异常检测与标记
        self.anomaly_detector.run(
            storage=self.storage.step(),
            input_key="series_values",
            output_key="anomaly_flags"
        )

        # Step 3: 缺失值插补
        self.imputation.run(
            storage=self.storage.step(),
            input_key="series_values",
            output_key="imputed_values"
        )

        # Step 4: 统计过滤（长度、缺失率、异常率）
        self.stat_filter.run(
            storage=self.storage.step(),
            series_key="imputed_values",
            output_key="stat_pass"
        )

        # Step 5: LLM质量评估（如果有LLM serving）
        if hasattr(self, 'quality_judge'):
            self.quality_judge.run(
                storage=self.storage.step(),
                profile_prefix="profile",
                output_key="quality_score"
            )

            # Step 6: 质量过滤
            self.quality_filter.run(
                storage=self.storage.step(),
                score_key="quality_score",
                output_key="quality_pass"
            )

        # Step 7: 时序去重
        self.deduplicator.run(
            storage=self.storage.step(),
            input_key="imputed_values",
            profile_key="profile",
            output_key="is_duplicate"
        )

        # Step 8: 数据统计报告
        self.dataset_stats.run(
            storage=self.storage.step(),
            output_key="dataset_report"
        )
```

### 7.2 Pipeline执行后的数据流追踪

```
Step 0: storage.read()
  → input.jsonl (raw series)
  Keys: [series_values, datetime, domain, ...]

Step 1: profiler.run()
  → 新增: profile, profile_trend_strength, profile_seasonality_strength, ...

Step 2: anomaly_detector.run()
  → 新增: anomaly_flags

Step 3: imputation.run()
  → 新增: imputed_values

Step 4: stat_filter.run()
  → 过滤低质量样本
  → 新增: stat_pass (Boolean mask)

Step 5: quality_judge.run()  [LLM]
  → 新增: quality_score, quality_score_cleanliness, ...

Step 6: quality_filter.run()
  → 过滤低评分样本
  → 新增: quality_pass

Step 7: deduplicator.run()
  → 新增: is_duplicate

Step 8: dataset_stats.run()
  → 新增: dataset_report

Final Output:
  → ts_dataflow_cleaning_step8.parquet
  → 包含所有中间列 + 最终清洁后的数据
```

---

## 8. Phase 4: Agent集成方案

### 8.1 TS-DataFlow Agent设计

```
User: "帮我准备一批电力负荷数据的TSFM训练集，
      需要去重、去异常、评估质量，最后输出统计报告。"

TS-DataFlow Agent:
┌──────────────────────────────────────────────────┐
│  1. Intent Recognition                           │
│     ├─ Domain: time series, electricity          │
│     ├─ Tasks: dedup, anomaly removal, quality    │
│     └─ Output: cleaned dataset + report          │
│                                                  │
│  2. Operator Retrieval                           │
│     ├─ TSStatisticalProfiler ✓                   │
│     ├─ TSAnomalyDetector ✓                       │
│     ├─ TSMinHashDeduplicator ✓                   │
│     ├─ TSLLMQualityJudge ✓                       │
│     └─ TSDatasetStatistics ✓                     │
│                                                  │
│  3. Workflow Composition                         │
│     Profiler → Anomaly → Dedup → Quality → Stats │
│                                                  │
│  4. Validation                                   │
│     ├─ Auto: key chain check                     │
│     └─ Human: review & confirm                   │
│                                                  │
│  5. Execution                                    │
│     pipeline.compile() → pipeline.forward()      │
└──────────────────────────────────────────────────┘
```

### 8.2 与DataFlow-Agent的对接

DataFlow已有DataFlow-Agent子系统（`github.com/OpenDCAI/DataFlow-Agent`），TS-DataFlow的agent可以直接在此框架上扩展：

1. **注册TS算子元数据**：为每个TS算子提供 `get_desc()` 方法，描述功能、输入输出、约束
2. **扩展Agent技能库**：添加TS领域的skill（时序数据理解、TS质量概念、TS pipeline误区）
3. **扩展Prompt模板**：TS数据准备专用的自然语言→pipeline映射prompt

---

## 9. Phase 5: TSFM训练验证

### 9.1 实验方案

```
控制变量实验：
┌──────────────────┬──────────────────┬───────────────────────┐
│  Group A (raw)    │  Group B (baseline) │  Group C (TS-DataFlow)│
├──────────────────┼──────────────────┼───────────────────────┤
│ 原始未处理数据     │ 简单规则清洗        │ TS-DataFlow全链路制备 │
│ (仅去除明显坏数据) │ (去重+异常去除)     │ (画像+LLM评估+清洗)  │
└──────────────────┴──────────────────┴───────────────────────┘
                    │                  │
                    ▼                  ▼
            ┌──────────────────────────────────────┐
            │       TSFM Fine-tuning               │
            │  TimesFM (200M) / MOIRAI (311M)      │
            │  MOMENT (40M)                        │
            └──────────────────────────────────────┘
                    │
                    ▼
            ┌──────────────────────────────────────┐
            │       Benchmark Evaluation            │
            │  ETTh1/ETTh2, ETTm1, Weather,        │
            │  Electricity, Traffic, Exchange, ILI  │
            │  Metrics: MSE, MAE                    │
            └──────────────────────────────────────┘
```

### 9.2 关键实验

| 实验 | 假设 | 验证方式 |
|------|------|---------|
| **Main Result** | TS-DataFlow制备的数据训练效果优于原始数据 | 3组对比，多backbone，多benchmark |
| **LLM Judge有效性** | LLM评分与人类专家一致 | Kappa/ICC agreement |
| **LLM Judge必要性** | LLM评分比纯统计规则更好 | Ablation: 去掉LLM judge, 只用stat filter |
| **去重消融** | MinHash+DTW > 纯MinHash > 不去重 | 逐阶段去掉去重 |
| **画像维度消融** | 更多画像维度 → LLM评分更准 | 逐步增加/减少画像维度 |
| **跨域泛化** | 一域制备的pipeline可迁移到其他域 | Electricity pipeline → Weather domain |
| **效率分析** | 端到端时间复杂度O(N) | profiling + statistics |

---

## 10. 论文大纲

### 暂定标题

*TS-DataFlow: LLM-Guided Automatic Data Preparation for Time Series Foundation Models*

### Section 1: Introduction (引言)
- 时序基础模型（TSFM）正在scaling up，但数据制备仍靠手工脚本
- LLM领域已经建立了成熟的agent-based数据制备范式（DataFlow/DataJuicer/NeMo Curator）
- 核心挑战：LLM如何理解和评估纯数值时序数据
- 核心方案：统计画像bridge + operator库 + agent编排
- 贡献：首次系统化TSFM数据制备、LLM-guide TS质量评估、TS operator库、开源系统

### Section 2: Related Work (相关工作)
- **2.1** LLM数据制备（Data Juicer, DataFlow, NeMo Curator, Multi-Actor）
- **2.2** TSFM预训练语料（MOMENT, Timer, TimesFM, Moirai, BLAST）
- **2.3** 时序数据质量（LTSV, TimeInf, 异常检测, 数据增强）
- **2.4** Agent系统（Data Agent, Auto-Data-Preparation）

### Section 3: Problem Formulation (问题定义)
- TSFM数据制备管线的形式化定义
- 质量维度定义：cleanliness, informativeness, normality, coherency, domain fitness
- 优化目标：最大化制备后数据训练的TSFM性能

### Section 4: TS-DataFlow System (系统设计)
- **4.1** 系统概览：三层架构
- **4.2** TS Operator Library：算子分类与设计
- **4.3** LLM-Guided Quality Assessment：bridge mechanism
- **4.4** TS-Aware Storage：时序数据存储优化
- **4.5** Agent-Driven Pipeline：自然语言驱动的自动编排

### Section 5: LLM-Guided TS Quality Assessment (核心方法)
- **5.1** Statistical Profiling：时序统计画像提取
- **5.2** Profile-to-Text Bridge：画像到自然语言的语义转换
- **5.3** Multi-Dimensional Quality Judgment：LLM多维质量评分
- **5.4** Human Alignment：与人类专家的对齐验证

### Section 6: Experiments (实验)
- **6.1** Setup：数据集、TSFM backbones、baselines
- **6.2** Main Results：数据制备对TSFM性能的影响
- **6.3** LLM Judge Ablation：LLM质量评估的必要性和有效性
- **6.4** Operator Ablation：各算子组件的贡献
- **6.5** Human Alignment：LLM评分与人类标注的一致性
- **6.6** Cross-Domain Generalization：pipeline跨域泛化
- **6.7** Efficiency Analysis：端到端效率

### Section 7: Discussion & Conclusion (讨论与结论)
- 局限：LLM调用成本、时序类型覆盖有限
- 未来方向：多模态数据制备、在线质量评估、自动化闭环优化

---

## 11. 实施路线图

### 11.1 时间线

```
Week 1-2: 基础设施搭建
├── 创建 ts_dataflow 包结构
├── 实现 TSFileStorage（parquet based, time-indexed）
├── 实现 TSStatisticalProfiler（复用work1 Phase 0代码）
├── 实现数据加载工具（支持常见TS格式）
└── 跑通5个标准TS dataset的加载→画像

Week 3-4: 核心算子开发
├── 实现 TSAnomalyDetector + TSImputation + TSNoiseFilter
├── 实现 TSTemporalDeduplicator（MinHash + fastdtw）
├── 实现 TSProfileToText 转换器
├── 实现 TSLLMQualityJudge（核心创新算子）
└── 单元测试覆盖

Week 5-6: Pipeline + Agent
├── 实现 TSCleaningPipeline
├── 实现 TSQualityPipeline
├── 实现 TSFullPreparationPipeline
├── Agent集成（skill定义 + NL→pipeline映射）
└── Pipeline集成测试

Week 7-8: 标注数据 + LLM验证
├── 构建TS质量人工标注数据集（200-500条）
├── LLM质量评估 vs 人类标注的agreement实验
├── Profile维度消融实验
├── Prompt工程优化
└── 统计分析

Week 9-10: TSFM训练验证
├── 在3个TSFM backbone上fine-tune
├── 3组数据对比（raw / baseline / TS-DataFlow）
├── 7个benchmark评估
├── Operator消融实验
└── 效率分析

Week 11-12: 论文写作
├── Introduction + Related Work
├── Method Section
├── Experiment Section
├── 图表制作
└── 内部review + 修改
```

### 11.2 依赖关系

```
TSFileStorage ──→ TSStatisticalProfiler ──→ TSProfileToText ──→ TSLLMQualityJudge
                                 │                                      │
                                 └──→ TSDeduplicator ←──┘              │
                                 │                                      │
                                 └──→ TSAnomalyDetector ←──┘           │
                                        TSImputation                    │
                                        TSNoiseFilter                   │
                                        │                               │
                                        └──→ TSQualityFilter ←─────────┘
                                               │
                                        TSCleaningPipeline
                                               │
                                        TSFM Training Validation
```

### 11.3 技术栈

| 层级 | 技术选型 |
|------|---------|
| 框架基础 | DataFlow (operator + pipeline + registry) |
| 时序处理 | pandas, numpy, scipy, statsmodels |
| 去重 | datasketch (MinHash LSH), fastdtw |
| 异常检测 | sklearn (IsolationForest), statsmodels (STL) |
| LLM调用 | DataFlow APILLMServing (OpenAI/GPT-4o) |
| 存储 | Parquet (via pandas/pyarrow) |
| 可视化 | matplotlib, seaborn |
| TSFM | TimesFM, MOIRAI, MOMENT (huggingface) |
| 评估 | gluonts, sktime |

### 11.4 最低可行产品（MVP）

第一版MVP只需实现以下核心组件即可验证idea：

```
MVP = TSStatisticalProfiler
    + TSProfileToText
    + TSLLMQualityJudge  ←── 最大创新点
    + TSCleaningPipeline
    + 在2个TSFM + 3个dataset上的对比实验
```

---

## 附录A: 与work1代码复用

| work1 模块 | 复用到 work2 |
|-----------|-------------|
| `forecastcore/patterns.py` (Phase 0特征提取) | → `ts_statistical_profiler.py` 的核心特征计算 |
| `forecastcore/selection.py` (次模选择) | → 可以作为可选的质量优先采样子模块 |
| `forecastcore/training.py` (TSFM训练接口) | → TSFM validation阶段直接复用 |
| `forecastcore/data.py` (数据集加载) | → TS data loading utilities |

## 附录B: 关键参考文献

| 论文 | 与本工作的关系 |
|------|--------------|
| **Liang et al. (2026) "Towards Next-Generation LLM Training: Data-Centric Perspective"** | DataFlow框架的理论基础论文 |
| **Liang et al. (2025) "DataFlow: LLM-Driven Framework for Unified Data Preparation"** | DataFlow技术报告 (arXiv:2512.16676) |
| **Bai et al. (2025) "Efficient Pretraining Data Selection for LMs via Multi-Actor Collaboration"** | Multi-Actor数据选择方法 (ACL 2025) |
| **Wu et al. (2025) "Lightweight TS Data Valuation on TSFMs via In-Context Finetuning"** | 唯一的TSFM数据估值工作 |
| **MOMENT (Goswami et al. 2024)** | TSFM + Time Series Pile 语料构建 |
| **Data Juicer (Chen et al. 2024)** | LLM数据制备框架 (ICLR 2024) |
| **It's TIME Benchmark (2025)** | TSFM benchmark数据质量审计 |

---

> **下一步：** 创建 `work2/ts_dataflow/` 包结构，实现MVP核心算子（Profiler → ProfileToText → LLM Judge），验证bridge mechanism的可行性。
