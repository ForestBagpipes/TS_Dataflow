# r5 主实验准备与 TATO 职责审计

2026-09-16。状态：已完成元数据清单、边界登记和场景搜索/部署 API；**主矩阵和官方完整 TATO 尚未运行**。本轮不启动 GPU，不读取已有 calibration/test 数值标签。主实验执行仍受 r5 开发准入与既有解封规则约束。

## 已落地数据资产

入口 `scripts/v431_r5_prepare_main.py` 默认只读取文件字节作 hash、行数、列名、CSV 时间列，不解析观测值。产物为 `configs/v431-r5/main_protocol.json` 和 `results/v431-r5/main-preparation/manifest.json`。窗口清单只生成 train/dev 的元数据，不加载目标。所有模型任务仍为 L512、H96/H192、原 Bolt/TimesFM2.5。

| 来源 | 本地行×变量 | 非重叠704点TRAIN parent容量 | DEV容量 | 状态 |
|---|---:|---:|---:|---|
| ETTh1 |17420×7|14|3|已有CSV，时间列保留，时区未声明 |
| ETTh2 |17420×7|14|3|已有CSV，时间列保留，时区未声明 |
| ETTm1 |69680×7|59|14|已有旧数据；旧划分边界原样保留，不能变成独立确认 |
| ETTm2 |69680×7|59|14|已有CSV，时间列保留，时区未声明 |
| Electricity |26304×321|22|5|新隔离下载完成，仅元数据；小时聚合版本，精确时间映射待补 |
| Exchange |7588×8|6|1|已有压缩数据；原交易日索引/字段与vintage不足 |
| Traffic |17544×862|14|3|新隔离下载完成，仅元数据；时间映射待补 |
| Weather |缺文件|—|—|TSLib基准归档与原始提供方版本映射待补，未运行 |

以上188个TRAIN、43个DEV是几何容量，**不是有效工具、训练叶或获取器支持**。实际列身份、缺失支持、窗口重叠与模型能力验收后才计有效支持；新DEV首次评估不与旧26parent表绝对MASE直接比较。

ETTm1继续原60/15/10/15边界，其他来源按相同比例提前登记，完整包络704点不得跨段。主窗口相隔704点，两个H、完整/不完整轨道、同步通道属于同parent。旧研究可能已使用其他来源的区间，正式运行前还需全历史manifest重叠审计；不能仅因本轮未看标签就称新确认。

ETT目标保留旧v43的channel 0（HUFL），不是官方常见OT；新来源沿用channel 0预登记，实际提供者字段身份核验完成前不启动预测，不能按表现换列。缺口方案沿用冻结v43实现，运行前固化具体mask/input hash，不改变有效值。完整输入轨道按五臂契约KEEP，只报告一致性及成本。自然缺口单列，休市、停运或未知空值不能自动归为可修复自然缺失。

### 来源与许可

[ETDataset作者仓库](https://github.com/zhouhaoyi/ETDataset)给出两站变压器负载与油温，数据许可实核为 [CC BY-ND 4.0](https://raw.githubusercontent.com/zhouhaoyi/ETDataset/main/LICENSE)，不是MIT。原始和变更数据不放Git或公开审阅包；研究内处理与对外分发区别记录。

[LSTNet作者数据仓库](https://github.com/laiguokun/multivariate-time-series-data)说明Electricity由UCI 15分钟数据转成小时、去2011年，Exchange为8国日汇率，Traffic为加州道路占用。作者README中Traffic“48 months (2015–2016)”自相矛盾；本轮不猜具体起始时间，保留ordinal索引与未知状态。仓库声明研究用途可用，不等于已核明确再分发授权。Weather的[TSLib入口](https://github.com/thuml/Time-Series-Library)只是基准归档入口，不能据代码MIT推导原始气象数据许可。

本次下载仅Electricity与Traffic，路径 `data/r5-public/`，原始失败与网络重试分别保存在 `downloads.json` / `downloads-network.json`。Electricity 17,993,794字节、35.99秒；Traffic 29,310,512字节、55.63秒。没有模型下载、环境重装或标签性能选源。SHA：

- Electricity：`3c4c069588198c1fcc95cace7bb69c99922129edfd673b7286661dad20badefa`
- Traffic：`c7be5a00519d344a5ec0eabdbfec5ea0c7dd1eed5f9b1a3843a93bb88086a56d`

## TATO 历史失败的实际调用链

官方固定commit仍为 `402bbc8998c49e2f33d9afbcc42140347a6b8c36`。

| 入口/函数 | 职责 | 事实 |
|---|---|---|
| `scripts/v431_baselines/tato_adapter.py:adapt_window` | 每请求在512−H处切历史并进行8trial搜索 | 416/320输入，历史MAE，最后512当前预测；不是场景级离线训练 |
| `timesfm_tato_worker.py:native_timesfm_pipeline` | 构造原生patch32管线 | trimmer保留5…15，未缩空间 |
| `third_party/TATO/transformation/library/trimmer.py:Transformation.pre_process` | 检查并裁输入 | `seq_l*32 > input_length` 先assert失败，未进入模型 |
| `scripts/v431_baselines/worker.py:TimesFM.__init__` | 固定骨干配置 | `torch_compile=False`，ForecastConfig max_context512/max_horizon192；该上限不是546次失败原因 |
| `worker.py:TimesFM.forecast` | 实际模型调用、原始输出与计时 | 变换成功后的shape与H记录，失败不填零 |

旧TimesFM共1248trial中546失败：480对H96/H192各156，448各78，384对H192另78。输入不足由**变换要求**导致，不应“修复”为补历史、未来padding或偷偷减少空间。当前完整L512的场景级训练可容纳480，但sampler/aligner产生的形状仍需实际验收，不能预称失败消失。

官方 `experiment/run.py` 默认500 TRAIN样本、500trial、top16、L1440；先训练搜索，再训练段验证/Pareto重排，最后test。官方上下文与本项目L512、监督/指标/模型均不同。旧8trial不是改成500就等于官方完整复现。

## 本轮新增的可执行准备

`scripts/v431_r5_prepare_main.py` 提供：

- `validate_train_samples`：拒绝非TRAIN、跨界、不匹配L/H和重复UID；已在服务器通过5个输入契约检查，未当作模型试验。
- `scene_search(model, samples, output, family=..., trials=500)`：使用官方8类变换空间、真实冻结模型接口，最多500个不重复合法TRAIN样本，按source/parent宏平均MSE搜索；失败逐trial保留，全部失败报错。每个scene单H，模型由统一GPU队列常驻提供。
- `execute_frozen_scene(model, context, horizon, params, family)`：线上只接当前dirty输入和冻结参数，无future或重新搜索接口，返回原网格预测、shape、hash和费用。

这是**同骨干、同L的TRAIN场景适配API**，尚未运行500trial，也没有实现官方完整Pareto/top16验证过程，因此明确不能称官方完整复现。样本调用方须从已冻结TRAIN manifest读取器提供数组；当前验证器检查范围与角色，不是恶意调用方的认证边界。GPU负责人应将冻结manifest hash及训练样本来源纳入最终请求，不能只手填role冒充权限。

实际准备命令：

```bash
source scripts/env_new_server.sh
"$W2_CORE_PY" scripts/v431_r5_prepare_main.py
```

GPU队列登记但未启动：先少量合法TRAIN请求测每family/变换shape吞吐，随后再估算500trial×实际TRAIN样本的成本；无实测前不给整矩阵完成时间。baseline离线搜索、冷加载、热部署和历史生成分别计费。

## 主实验推进条件和缺项

继续准备不等机制逐项显著。r5若满足双家族胜各自TRAIN冻结强简单对照、联合约束同信息至少一家族增益且另一不退步、关键在线与边界通过，再冻结并按原协议推进独立确认。否则现有calibration/test封存，完成负结果及基线准备。

当前仍缺：Weather确切基准文件、全部新来源时间/字段身份与历史重叠审核、具体mask/input hash实例化、TATO新场景500trial真实预测与完整官方对照、新矩阵GPU吞吐、自然缺口版本元数据。TimesFM-3/Chronos-2仍只为已登记的未来适配，不计已运行对手。
