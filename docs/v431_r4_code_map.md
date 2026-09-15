# v4.3.1-r4 实际代码依赖与尺度修复

本轮保留 r3 冻结代码及预测，不重写治理工程。下述入口已存在；实验成绩另见本轮报告。

| 环节 | 实际文件及函数 | r4 处理 |
|---|---|---|
| 五臂身份 | `src/introact_ts/v43/agent_inputs.py:POOL`；`p2_candidates.py:ridge_candidate` | Native、FFILL、单变量 TS-ICL、多变量 TS-ICL、context ridge；无预测后残差臂 |
| 外层 MASE | `src/introact_ts/v43/p2.py:run_p2` 第 133 行起；`task_labels.py:mase_scale` | 整外层 TRAIN 冻结分母仍仅作报告。不能当作早期 train origin 当时已知尺度 |
| 原模型输入 | `scripts/v431_r3_collect.py:Collector`、`src/introact_ts/v431_r3/probe.py:prepare_probe` | 先截断再治理、canonical 输入去重；本轮不改变，真实原预测可复用 |
| 请求学习尺度 | `src/introact_ts/v431_r4/origin_scale.py:origin_scale` | 当前 dirty 输入最多 512 点，有限季节差分至少 16 对；否则 lag-1 至少 16 对；否则可见 MAD；最后固定 1e-8 下限。每窗存分支与支持 |
| 免费特征 | 同文件 `visible_features` / `FREE_NAMES` | 13 个固定可见字段；原 MAD normalizer 改为 origin scale。没有 source 名称、污染真类别、未来、未取证输出 |
| 原数据读取 | `src/introact_ts/v431_r2/data.py:R2Data`；`scripts/v431_r3_fit.py:ExternalEvaluationData` | 只作为已用缓存的离线评估器，不能传入在线策略。构造 R2Data 会读取已用 TRAIN/DEV 标签，`--train-only` 限制输出与统计，不伪称文件访问只包含 TRAIN |
| 轨迹账本 | `src/introact_ts/v431_r4/trajectory_dataset.py:build_batch` | 存 `losses=MAE/origin_scale` 与 `report_losses=既定外层 MASE`；特征、成本、监督分域。监督仅供训练/离线评估 |
| 已购证据 | 同文件 `evidence_features` | H32/H 分别由 h32/long 的原始 MAE、覆盖和支持重算；control 增加 short 和同起点 raw forecast std。主候选没有 κ 或 z。unsupported 有显式状态，矩阵 NaN 只作缺失编码，不能当实测零 |
| 真实费用 | `CostInvoice.merge`；`build_batch` | 按 charge key 去重原工具费用，保留原候选与最终预测费用，加新特征和证据投影 CPU 实测。原 cache 并不免费；冷启动另报告 |
| 支持核查 | `scripts/v431_r4_prepare.py` | CPU 生成各家族、各 role 的 parent/episode/有效工具支持；只输出真实数据。原 acq 改作冻结后回归，不自动变成独立确认 |
| r3 旧冻结比较 | 原 r3 decisions 与真实预测缓存 | 原始文件 hash 不变，但当前环境动态 `policy.frozen_hash` 有 3/6 不一致；不绕过后重跑并称冻结一致 |

## 受影响依赖与重算边界

外层整 TRAIN 尺度由 p2 评价器建立；r2 的 `L`、r3 原子 `current_scale/gain/psi`、终态目标及获取价值均继承该任务分母。**旧 dirty 特征本身调用的是可见 context MAD，不是直接读整 TRAIN 分母**，不能把所有旧特征笼统称为未来读取。r4 为符合统一单位契约，将请求尺度归一化的免费特征、历史 MAE/分歧、训练任务损失、终态及工具价值全部重新建立。学习器阈值只能由 fit 生成，gate 不能提供特征分位数。

尺度不进入冻结 TSFM 的候选输入和历史预测预处理，因此本次尺度修复不触发 GPU 预测重跑。新 batch 有尺度版本、代码 hash、每窗 input/mask hash、各工具 model/input hash 和原始费用来源；不以旧 `gain` 冒充新监督。旧数字保持原协议身份，不直接称作修复后重训结果。

主原协议共 110 TRAIN parent：fit 54、gate 21、check 17、acq 18；有效工具支持依次 51、20、16、16，control 可支持的相关变体更少。共同 DEV 仍为 26 parent。已查看的新位置 17 个 check parent 和金融 2 parent 是附表，不能增加独立训练 parent 数。

## 复用验收与已发现限制

- `results/v431-r4/r3_hash_compatibility.json` 保存原 models 文件字节核对及动态 hash 差异。序列化函数会重新计算原单位截距（包含浮点点积）；没有原始 `to_dict` 快照，尚不能确定具体 ULP 或 BLAS 成因。外部数据读取仅验证冻结资产及源码 hash，不加载策略作决定，并明确区别于策略验收。
- `results/v431-r4/current_candidate_support.json` 重新在 CPU 构造 context ridge，核对原候选数值并保存 unsupported 的真实原因/Native alias、实际动作、逐位 hash 是否相等。数值近似通过不写成逐位相等；原候选和预测不覆盖。
- 新 external 加载最初遭遇冻结动态 hash 断言，后续加入独立资产校验；A4 支持审计最初过严要求重算 hash 相等，后改为显式记录数值容忍及逐位差异。两者不改变已冻结输入或预测。
- `tests/v431_r4/test_origin_scale.py` 检验尺度支持/回退、512 上界、未得证据缺失、原始 MAE 换算及 parent 权重，不通过重复旧测试累加研究结论。

## 本轮唯一后续使用账本

最终固定为 `results/v431-r4/trajectory-final/{main,generalization,financial}/{bolt,timesfm}.joblib`，三套均已完成；`producer/` 保存执行源码，`files_sha256.json` 保存全部文件身份。较早 `trajectory-train/`、`trajectory/` 是开发准备快照，不能在不同方法之间混用其微小 CPU 计时差异。费用分类的后续审计应作为该最终账本的明确修正层，不能重跑全部准备来无意换成本。

`origin_scale(target, period)` 返回 `OriginScale`，`visible_features(episode, period, scale=None)` 返回固定 13 维可见字段。`TrajectoryBatch.subset(indices, reweight=True)` 用于完整角色重配 source/parent/variant 权重；策略内部切枝必须保持原训练权重（`reweight=False`），否则不再优化同一个总体目标。

## 修复后 r3 与分阶段强对照

新增 `src/introact_ts/v431_r4/legacy_retrain.py` / `scripts/v431_r4_legacy.py`，原 r3 文件不改。`build_legacy_evidence` 从原始 MAE 重建新 origin 单位的收益，只有 PSI 的可见 MAD 差按旧尺度/新尺度换算；κ/z 仅保留在旧响应负对照中，不进入 JOINT。

完整 legacy 终态使用原 fit54/gate21，固定 residual/direct/CART 的 H32、H、control、equal-cost、disagreement 状态。分阶段对照只在原 fit 内按来源及原始时间前 2/3（35 parent）拟合终态、后 1/3（19 parent）监督获取；有效获取 parent18，LOPO17，旧 acq 仅回归。获取器每叶16要求仍无法形成两个合法叶，不把击败它称作击败充分支持的非平凡获取器。

终态先在 `results/v431-r4/legacy/terminal_freeze.json` 冻结。费用审计完成后，通过 `v431_r4_run.load_batch` 载入原输入及明确 hot/cold 修正，`finalize_legacy_acquisition` 校验终态文件与 hash 后生成 `results/v431-r4/legacy-final/`。两家族均有288条合法工具价值标签：Bolt正27/零211/负50；TimesFM正41/零189/负58，λ均为0。这些是内部 TRAIN 监督，不是 DEV 方法收益。

复现入口（输出必须使用新目录，拒绝覆盖冻结产物）：

```bash
source scripts/env_new_server.sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$W2_CORE_PY" scripts/v431_r4_legacy.py --terminal-only --output <new-terminal-directory>
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$W2_CORE_PY" scripts/v431_r4_legacy.py --acquisition-only --terminal-root <new-terminal-directory> --output <new-acquisition-directory>
```

本轮获取实际调用的是相同 Python `finalize_legacy_acquisition` API，参数与成本/输入/终态 hash 保存在 `legacy-final/execution.json`，输出日志在 `logs/v431-r4/legacy-final.log`。在线获取只接 visible13、工具名和 terminal hash；取得证据后才调用对应终态。主表由统一 root 调度评分，legacy 拟合脚本不评分 DEV。

## 共同表汇总入口

`scripts/v431_r4_common.py` 先在原 T_fit 内冻结 `common_fixed_freeze.json`：固定五臂及三种修复后 legacy 终态 × H32/H/control 中按训练任务损失选最强整覆盖预算可行固定流程。高预算 Bolt 选择 residual H，TimesFM 选择 CART H；Bolt 低预算没有整覆盖可行候选，明确标为未获得，不能产生一个假“最佳流程”。

随后在已用 DEV 与金融集执行完整 legacy 决策，预算检查统一使用 `BranchCost` 的 TRAIN 测量与 horizon 分桶，未购证据不传入 `ResponsePolicy.choose` 或获取器。冻结 r3 与 R2 行复用原预测，TATO 校验原预测文件 SHA 与逐窗 forecast hash，保留其原生空间及 8-trial 身份。`external_hot_costs.json` 的 R2 部分只能精确分离候选/最终预测加载，历史和遮挡工具的未知冷启动费用仍全额保留，因此不能声称其费用已严格净化为 hot-only。

结果写入 `evaluation/dev` 与 `evaluation/financial` 的 `common_decisions.json`、`common_table.json`、`common_sources.json` 和 `common_status.json`。分别为16692/1284行，各107组；文件数量仅表示比较覆盖，非研究成功。`common_completeness.json` 记录唯一缺组、真实分支与费用限制。两个修复后 staged legacy 在 DEV 都156/156无取证；主 JOINT 并未胜过强简单对照，最终配对统计和论文结论以统一报告为准。
