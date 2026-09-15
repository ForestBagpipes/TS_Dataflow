> 2026-09-16 04:23 执行状态更新：本页下文保留准备时的协议与预登记状态。实际执行已推进：四个ETTm1 TATO场景各500trial完成，追加来源部分搜索按截止保留partial；Chronos-2原生KEEP已完成旧DEV26parent/156变体，MASE0.957177。Weather文件、输入/mask及重叠审核已完成准备。最新完整状态以 [交付快照](v431_r5_final_snapshot.md)、[TATO实际结果](v431_r5_tato_scene_results.md)、[Chronos-2结果](v431_r5_chronos2_native_results.md) 和 [主矩阵准备](v431_r5_main_readiness.md) 为准。准备文中的“未运行”不覆盖后续真实记录；官方完整复现和r5主矩阵确认仍未完成。

# 近期骨干元数据登记：未执行对手

2026-09-16按官方模型仓库实时核对。只下载公开README、LICENSE、config与模型元数据，没有下载新权重、安装依赖或调用模型。实际脚本为`scripts/v431_r5_backbone_registry.py`，原始来源与SHA保存在`results/v431-r5/backbone-registry/registry.json`。

| 项目 | TimesFM-3 | Chronos-2 |
|---|---|---|
| 官方仓库 | [google/timesfm-3.0-pytorch](https://huggingface.co/google/timesfm-3.0-pytorch) | [amazon/chronos-2](https://huggingface.co/amazon/chronos-2) |
| 本次固定revision | `43046b85ec22d584a13f8098c2ed39c889e129c2` | `29ec3766d36d6f73f0696f85560a422f50e8498c` |
| 权重文件字节 | 1,322,898,824 | 477,930,472 |
| 权重许可 | TimesFM Non-Commercial License v1.0，区别于源码Apache-2.0 | Apache-2.0 |
| 接口准备 | 官方`timesfm3.TimesFM3Evaluator`，不能直接替代2.5旧类 | `Chronos2Pipeline`，官方文档要求chronos-forecasting>=2.0 |
| 当前适配风险 | 32点输入patch、64点输出patch；独立配置与默认开关需要冻结 | 输入/输出patch16、原生context8192、最大1024预测；组内协变量可用性需明确 |
| 原生NaN验收 | 未运行，不以多变量能力推断缺口处理通过 | 未运行，不以模型卡能力替代当前as-of/mask测试 |
| 当前机器峰值显存 | 未测；文件字节不是运行峰值 | 未测；文件字节不是运行峰值 |

[TimesFM官方代码说明](https://github.com/google-research/timesfm)将3.0权重明确区分为非商业、非生产许可；当前研究实验与以后岗位展示/生产应用须保持用途边界，不能沿用2.5权重许可标签。本文只记录官方声明，不将代码开源等同权重用途相同。

两者均未进入r5比较表。只有后续独立协议明确、依赖隔离、真实输入与NaN/发布时间契约以及显存验收通过后才可运行。不同骨干自身提升必须与同骨干治理增量分开，不借更换骨干掩盖r5未晋升。
