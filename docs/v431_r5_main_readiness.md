> 2026-09-16T04:43:04.371223+08:00：元数据准备后的执行补记：8来源TRAIN-only接口已完成，两家族各32请求；进一步完成合法230TRAIN parent、每家族920个原生KEEP预测并通过独立审核。只保存输入/预测/费用，未读取未来目标、未计算MASE、未训练r5。下文“模型尚未执行”描述原准备阶段，完整方法主矩阵及独立确认仍未运行。详见main_train_bank_verification及final_snapshot。

# r5 主矩阵准备、历史暴露与时间契约

## 实际状态

主矩阵8来源的数据容器、TRAIN/DEV parent元数据及具体观测mask均已准备，**没有启动主矩阵TSFM实验，也没有解封calibration/test**。r5开发准入失败不阻断基线和数据准备，但不能把准备完成称为主实验完成。

原 `configs/v431-r5/main_protocol.json` 和首版manifest未改。新增 `configs/v431-r5/main_protocol_v2.json`、`results/v431-r5/main-preparation/audit-v2/manifest_v2.json`，仅按数据可用性、元数据和历史暴露更正。v2 SHA256为 `e9b8b281421c3f3d8a6919e005d827e05323b5ccd88c016b7d2113e554ab7010`。v2沿用的 `code_sha256` 是v1生成器身份；实际v2生成器hash记录在 `audit-v2/status.json`，这一继承字段区别也写入时间审计侧账，避免混淆。

实际CPU入口：`scripts/v431_r5_main_audit.py`，无参数执行区间/观测mask审计，`--temporal`只读时间列进行时间契约审计。日志分别为 `logs/v431-r5/main-audit-first.log` 和 `main-timestamp-audit.log`。首批生成耗时约5.83秒，无GPU或模型调用。

## 八来源容量与旧使用范围

每parent保持当前512行context及最多192行future的完整704行范围；H96/H192和三个既有condition共享parent。下表为parent数，不是独立于所有历史使用的样本数。

| 来源 | TRAIN parent | DEV parent | 与已知旧执行区间重叠 | 没有已知旧区间重叠 | 具体限制 |
|---|---:|---:|---:|---:|---|
| ETTh1 | 14 | 3 | 17 | 0 | 旧v40/rescue及同步ETTm1暴露 |
| ETTh2 | 14 | 3 | 17 | 0 | 旧v40/rescue暴露 |
| ETTm1 | 59 | 14 | 73 | 0 | 旧当前预测协议及旧v40暴露 |
| ETTm2 | 59 | 14 | 73 | 0 | 名称未用，但与旧ETTh2同站点时间重叠 |
| Electricity | 22 | 5 | 0 | 27 | 原始时间仅ordinal，许可范围仍需保留说明 |
| Exchange | 6 | 1 | 0 | 7 | 交易/报价日历与时间映射未解决 |
| Traffic | 14 | 3 | 0 | 17 | 时间映射与发布时点未解决 |
| Weather | 44 | 11 | 0 | 55 | 2个TRAIN parent有重复/不规则时间待处理 |
| 合计 | **232** | **54** | **180** | **106** | 不是286个全新独立样本 |

历史审计读取的都是元数据：旧v40及rescue的parent start/长度，旧v43实际episode manifest，以及旧p0 corpus的来源/hash登记。完整区间交集包括context与未来监督范围，不只比较parent名字。未定位旧p0窗口的来源暴露也保留，不以没匹配到名字推断无使用。

ETTh/ETTm分别是相同两站点的小时/15分钟版本；官方数据说明明确这一关系。因此审计先将小时区间乘4映射至同站点15分钟时间轴，ETTm2的73个窗口均与旧ETTh2窗口相交，不能称为新确认来源。[ETDataset官方说明](https://github.com/zhouhaoyi/ETDataset)

106个“无已知旧重叠”parent中，86为TRAIN、20为DEV；扣除Weather两个时间契约待定parent后，暂有104个元数据上未发现已知暴露且没有当前已识别时间异常的parent（84 TRAIN、20 DEV）。这个状态只覆盖已审计manifest范围，不保证TSFM预训练未见过这些公开数据，也不自动授权将其命名为独立确认集。旧DEV和旧check/acq身份不改变。

## Weather实际补齐

已从TS-Library官方Hugging Face数据仓库下载固定revision：

- revision：`2b66e59ee19dac8f6f19fb5d4997f289fdfea357`
- 文件：`data/r5-public/weather.csv`，7,235,425字节；本次下载17.03秒。
- SHA256：`34ee981d07313e51da2a50bb600072c8ae4a69cb4b0651f4cb93a069d7a2ba63`
- 52,696条记录、21个变量，2020-01-01 00:10:00至2021-01-01 00:00:00。
- 本项目按既有第一通道规则选择 `p (mbar)` 气压；没有偷偷改为温度或常见论文的OT目标。
- 官方HF数据卡标CC-BY-4.0；MPI-Jena原始气象下载页也标CC-BY-4.0。保留来源归属；不将TS-Library代码许可证代替数据许可证。[TS-Library官方数据](https://huggingface.co/datasets/thuml/Time-Series-Library/tree/main/weather)、[MPI-Jena原始数据许可](https://weather.bgc-jena.mpg.de/weather_data.html)

下载只进行了容器字节保存、hash和元数据检查，未使用目标表现选择文件或时间段。

## 实际时间异常，没有静默修复

ETT四文件时间列严格分别以3600/900秒递增。Weather的相邻时间差为600秒52,693次、0秒1次、6000秒1次：

| Weather行号（0起） | 之前时间 | 当前时间 | 问题 | 受影响TRAIN parent |
|---:|---|---|---|---|
| 19044 | 2020-05-12 06:00:00 | 2020-05-12 06:00:00 | 重复时间戳 | Weather:19008:19712 |
| 21514 | 2020-05-29 09:30:00 | 2020-05-29 11:10:00 | 100分钟跨度 | Weather:21120:21824 |

这两窗标为 `unsupported_pending_explicit_time_contract`，保留在登记和失败分母中，不自动去重、移位、补齐或删除。现有mask侧账是按原始行顺序生成的准备产物；将来模型入口必须首先读取 `timestamp_audit.json` 的阻塞状态，不能仅因存在mask文件而运行它们。时区、实际发布延迟及历史vintage没有被补造成已知。

Weather时间缺口不等于已验证自然NaN，更不等于金融市场缺口。

## 具体mask及读取范围

实际生成1716条逐任务契约：286 parent × H96/H192 × raw/target_block_10/shared_block_10。每条包含data hash、origin、L/H、原始target与辅助输入hash、mask hash、暴露状态及数值读取范围。

只把各TRAIN/DEV parent的 `[read_start, origin)` 512行转为数值。各窗口future段以及calibration/test数值均未解析；顺序读取CSV/GZIP时跳过的行仅作为字节/字符串通过，不提取其观测值。完整文件hash和时间列metadata不作为在线未来特征。

沿原v43固定缺口 `[230,281)`、seed101，不增加污染seed或动作。raw不修改；target_block只删目标；shared_block同时删目标与辅助。对未删除的有限观测执行精确相等检查。每来源/role保存一个实际mask NPZ样例，NPZ仅布尔观测状态，不保存未来目标。

在这286个已解析context中，没有发现任何原始非有限观测。**这不是证明数据无错误**：特殊有限哨兵值、数据修订和真实测量问题尚未完成独立核验。因此当前主矩阵准备覆盖完整有限输入与受控删除输入；可验证自然缺口轨道仍缺。完整输入按KEEP契约不会产生治理预测提升。

## 下一步真正未完成的事项

1. r5未满足开发准入，仍不得进入独立确认或以主矩阵搜索新胜例。
2. 主矩阵模型预测、完整MASE评分、训练尺度拟合和共同预算结果尚未执行；本页不是实验成绩。
3. 同站点跨频率同步组的内部fit/gate/check/acq purge必须在下一轮训练前显式冻结，不能按来源名随机分组。
4. Weather两窗时间契约、Electricity/Traffic原始时钟、Exchange日历和真实发布时间尚未解决。
5. 近期强基线的独立scene搜索由统一GPU队列负责；本审计没有运行TATO或更换骨干。
6. 当前输入target选择分别为ETT的HUFL、Weather气压及其他数据第一通道，不是官方统一OT或多变量排行榜任务；官方协议成绩必须另表。

审计产物：`audit-v2/overlap.json`、`support.json`、`legacy_inventory.json`、`mask_contract.json`、`mask-samples/`、`timestamp_audit.json`、`status.json`。原v1协议和所有历史负结果完整保留。
