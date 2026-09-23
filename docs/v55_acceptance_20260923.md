# v55 验收报告（2026-09-23 17:40）

本文件给出稿中每个数字的来源路径与核验状态。分三档：**已验收**表示有自动检查通过并留有记录；**已记录**表示结果完整且可追溯，但没有独立复核手段；**未验收**表示还缺一步。

服务器 `vipuser@223.109.239.30:23524`，工作目录 `/home/vipuser/work/work2`。本地同名相对路径下有同步副本（`tmp/v55_sync.tgz` 展开而来）。

---

## 一、结果目录总览

| 内容 | 路径 | 本地是否有副本 |
|---|---|---|
| 主评估（6 区块 × 3 骨干） | `results/v55/evaluation/{block}_{backbone}.json` | 有 |
| 最小值规则对照评估 | `results/v55/evaluation_minrule/` | 无（仅服务器） |
| 选参与保形校准 | `results/v55/protocol/selection_{bb}.json`、`conformal_{bb}.json` | 有 |
| 门控对照 | `results/v55/gate_controls/{bb}.json` | 有 |
| 回放库规模消融 | `results/v55/ablations/banksize_test_{bb}.json` | 有 |
| 确认集一次性评估 | `results/v55/confirmatory/{bb}.json` | 有 |
| 端到端延迟 | `results/v54/cost/e2e_latency.json`（原始分段在 `results/v54/cost/work/`） | 有 |
| 外部基线修复档案 | `results/v54/replay/external/{t1,pswi,timesnet}/` | 无（体积大） |
| 外部基线骨干预测 | `results/v47/baselines/{method}_{block}_{backbone}/records.json` | 无 |
| 确认集回放 | `results/v54/confirmatory/replay/` | 无 |

自动检查记录：

| 检查 | 记录文件 | 结论 |
|---|---|---|
| 外部基线逐请求预测覆盖 | `scripts/v55_forecast_coverage.py` 输出 | passed，36 个格子每格 760 条 |
| E3 动作合法性 | `results/v55/e3_validation.json` | passed，80 请求 0 处不一致 |
| 确认集流水线自检 | `results/v54/confirmatory/check_report.json` | `all_passed: true`，40 项全过 |
| 外部档案合并校验 | `results/v54/replay/external/*/merge_report.json` | 三方法四区块全 ok |
| 稿中数字回溯 | `scripts/v55_audit_numbers.py` | 64 / 64 命中 |
| 硬件复算比较 | `results/v55/hardware_compare.json` | 见第四节，逐位不等 |

---

## 二、已验收

**主实验 E0。** `results/v55/evaluation/test_{bb}.json` 等 18 个文件。九个对照行加本方法加 oracle，每个区块 760 集、95 个 parent、8 个来源。外部行的逐请求覆盖由 `v55_forecast_coverage.py` 核过，PSW-I、T1、TimesNet、TATO 在 test/test30/test50 三块三骨干共 36 个格子上都是 760 条，没有任何一行在更小的分母上取平均。合并校验显示三个外部方法在全部观测位置与原始输入一致（PSW-I 差 0，T1 与 TimesNet 差 2.93e-05，是 float32 舍入），隐藏位置无非有限值。

**E3 端到端延迟。** `results/v54/cost/e2e_latency.json`，17:00 前在空闲卡上重测，`results/v55/e3_validation.json` 记录 status passed。此前那一版 80 个请求里有 60 个的合法动作集与冻结目录不符，原因是测量时 GPU 被别的作业占满导致 MULTI_TSICL 显存不足，现在降到 0。测量条件写在 payload 的 `measurement_notes` 里：batch=1、每段前后 `torch.cuda.synchronize()`、worker 的内存缓存关闭、冷启动单列。

**确认集。** `results/v55/confirmatory/{bb}.json`，每个骨干一次性运行，脚本对已存在结果默认拒绝覆盖。上游数据由 `results/v54/confirmatory/check_report.json` 核过，`all_passed: true`。bank 1176 集 49 parent，评估 168 集 21 parent。

**稿中数字。** `scripts/v55_audit_numbers.py` 从 results 重建正文引用的 64 个值并在 tex 里逐个查找，全部命中。

---

## 三、已记录但无独立复核

**选参与一倍标准误规则。** `results/v55/protocol/selection_{bb}.json` 里 `selection.grid` 保留了全部 120 个配置的交叉验证结果，`min_rule_selected` 保留了最小值规则的选择，`one_se_band_size` 记录带内配置数。两套配置的完整评估都在（`evaluation/` 与 `evaluation_minrule/`）。需要说明的是：我是先用最小值规则跑了一遍 TEST、看到结果之后才改用一倍标准误规则的。该规则本身是本项目 v51 时期登记过的旧规则，改用它的理由（曲面平坦、误差随干预率缓慢下降）与 TEST 无关，但这个先后顺序必须在附录里如实写明，现在 `app:selection-rule` 已经写了两套配置和两套结果。

**保形门。** `results/v55/protocol/conformal_{bb}.json` 记录四个 α 档位的阈值、校准块经验损害与 CRC 上界；`evaluation/*.json` 的 `conformal_rows` 与 `crossfit_conformal_rows` 记录这些阈值在 TEST 上的实际损害。训练侧校准的阈值在 Bolt 与 TimesFM 上被突破，交叉校准版本 12 个格子中 9 个守住。这是可交换性假设在时间序列上不成立的直接证据，正文按"名义水平加实测校验"写，没有当成分布无关保证。

**门控对照与回放库规模。** `results/v55/gate_controls/{bb}.json` 与 `results/v55/ablations/banksize_test_{bb}.json`。门控对照的阈值在内部块上匹配全方法的干预率后冻结，TEST 上的实际干预率会偏移，payload 里两者都有。回放库规模用冻结配置在三个子采样比例上评估，25% 与 50% 各三次抽样取平均。

**确认集来源的历史。** 注册表 `configs/v54/confirmatory_registry.json` 里写的是"从未参与任何开发或选择"，这句话过强：`results/v43/20260914T141030.324186Z-agent/` 下的 decisions.json 出现过 Solar。正文与附录已改成准确口径，即本轮设计的任何决策都没有读过它们，注册表那一句还没改，建议一并更正。

---

## 四、未验收

**硬件事件的复算比较。** `results/v55/hardware_compare.json`，`all_bitwise_equal: false`。三对结果：

| 对 | 逐位一致 | 最大绝对差 | 读法 |
|---|---|---|---|
| PSW-I Exchange | 否 | 3.59e-05 | 确定性路径，差值在 float32 舍入量级，等同复现 |
| T1 ETTh1 | 否 | 6.84 | 复算是从随机初始化重训 300 轮，与旧卡的模型本就不同 |
| TimesNet ETTh1 | 否 | 2.53 | 同上 |

逐位比较对两个重训模型不适用，所以这一项目前只证明了确定性路径干净。要把它变成已验收，需要把两个 verify 分片送进三个骨干打分，比较 ETTh1 上的 MASE 是否落在配对区间内，约半小时 GPU 加十分钟改脚本。现在稿中没有依赖这项的结论，附录也还没写硬件事件，所以它不阻塞文字工作，但投稿前应该补上或如实登记为未完成。

支持"旧卡没有静默算错"的间接证据有两条，可以先写进附录：一是合并校验显示每个修复在全部观测位置与原始输入一致，显存位翻转会在这里暴露；二是所有失败都是显式报错中止（`AcceleratorError`），没有安静返回结果，这与不可纠正 ECC 的常见表现一致。

**E1 机会分层与 E2 精度-损害的独立产物。** 这两项的数值现在是从 `results/v55/evaluation/*.json` 的 `opportunity_strata` 与 `rows` 字段直接读出的，没有单独的 e1/e2 汇总文件（旧的 `results/v54/e1_e2/` 是 v54 配置下的，与现稿不一致，不要引用）。建议要么删掉旧目录避免误用，要么补一个 v55 版汇总。

**最小值规则那一套的附录数字。** `app:selection-rule` 里引用的 1.431 / 76.5% / 0.0430 来自 `results/v55/evaluation_minrule/`，这份只在服务器上，本地没有副本。要么同步下来，要么在附录里写明它只在服务器留存。

---

## 五、给文字工作的三条提示

第一，正文现在的九页是压到极限的，`sec:main-end` 落在第 9 页最后几行。任何增补都会溢出到第 10 页，改动时请留意 `pdftotext -f 10 -l 10` 的输出是否只剩致谢。

第二，`scripts/v55_audit_numbers.py` 可以随时重跑，它会报告哪些记录值在 tex 里找不到。改数字时先跑它。

第三，附录里还有少量按旧口径写的句子，检索关键词 `v52`、`per-request convention`、`Rank` 可以找到剩下的。严重度三张表的 Rank 列我已经删了，但 `tab:app-trend` 之前的引导句还提到过排名口径。
