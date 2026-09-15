# r4 公开骨干版本与适配条件登记

核验日2026-09-16。只浏览官方说明并保存小型公开元数据/源码，**未下载权重、安装环境或执行TimesFM-3/Chronos-2实验**。r4主表仍是原冻结Bolt与TimesFM-2.5；新骨干不能用来掩盖治理方法无增量。

| 项目 | TimesFM-3 | Chronos-2 |
|---|---|---|
| 官方checkpoint | google/timesfm-3.0-pytorch | amazon/chronos-2 |
| 本次查询revision |43046b85ec22d584a13f8098c2ed39c889e129c2|29ec3766d36d6f73f0696f85560a422f50e8498c|
| 代码版本 |timesfm包3.0.2；仓库8cb0628371af142e16b8c232cc9fbf667ffb12f9|正式release v2.3.2（2026-09-08）；main的2.3.3.dev0不是正式release|
| 许可 |源码Apache-2.0；**3.0预训练权重单独非商业、非生产许可**|源码与权重Apache-2.0|
| 任务 |原生多变量/单变量、过去与已知未来协变量|原生多变量/单变量、过去与已知未来协变量；120M参数|
| 缺失 |高层API接受NaN，官方实现先裁前导NaN并线性插值；全NaN有填零分支，不可无提示沿用|context_mask默认由NaN构造，patch显式含mask；不可提供未知future covariates|
| 显存 |官方没有本项目L512/H96/H192/B1最小显存保证；未实测|官方示范A10G吞吐，不等于最小显存或4090单请求保证；未实测|

版本/许可依据：[TimesFM仓库](https://github.com/google-research/timesfm)、[TimesFM模型卡](https://huggingface.co/google/timesfm-3.0-pytorch)、[Chronos模型卡](https://huggingface.co/amazon/chronos-2)、[Chronos正式release](https://github.com/amazon-science/chronos-forecasting/releases/tag/v2.3.2)。权重版本由官方HF API只读查询，JSON保存在`results/v431-r4/baseline_audit/public_metadata/`；不从网页宣传排名推导本项目SOTA。

固定源码的TimesFM依赖为Python≥3.10、numpy≥1.26.4、huggingface_hub≥0.28、safetensors≥0.5.3、torch extra≥2.0；Chronos v2.3.2依赖按保存的`chronos_pyproject.toml`，主要为Python≥3.10、torch≥2.2<3、transformers≥4.41<6、accelerate≥1.1<2、numpy≥1.21<3、einops≥0.7<1、pandas≥2<4。[TimesFM依赖声明](https://github.com/google-research/timesfm/blob/8cb0628371af142e16b8c232cc9fbf667ffb12f9/pyproject.toml)、[Chronos依赖声明](https://github.com/amazon-science/chronos-forecasting/blob/v2.3.2/pyproject.toml)。本项目环境可能满足部分版本，但尚未声明新模型完整验收。

缺失实现定位：TimesFM `src/timesfm3/torch/timesfm3_forecaster.py:136`与`:512`；Chronos `src/chronos/chronos2/model.py`的`context_mask`接口及patch embedding。[固定TimesFM源码](https://github.com/google-research/timesfm/blob/8cb0628371af142e16b8c232cc9fbf667ffb12f9/src/timesfm3/torch/timesfm3_forecaster.py)、[Chronos源码](https://github.com/amazon-science/chronos-forecasting/blob/v2.3.2/src/chronos/chronos2/model.py)。TimesFM3的全NaN回零与本项目禁静默降级不兼容，后续wrapper必须显式unsupported；部分NaN的官方插值应以Native KEEP身份披露。使用known-future接口并不赋予未来市场变量读取权限。

若另轮实际验收：先固定许可、权重及代码SHA，在独立环境overlay核依赖，单GPU锁内B1、L512/H96/H192各执行完整/部分NaN/全NaN受控请求，记录input/mask、实际输入截断、原分位数与点预测、原生缺失行为、峰值allocated/reserved显存、cold/hot/process时间。通过后仍需冻结共同origin和五臂对照；不扩大本轮r4候选家族，不把Chronos-Bolt与Chronos-2算两个独立TSFM家族。
