# r4 TATO 实际完成范围与独立评估协议

2026-09-16。本轮审计不启动GPU、不下载权重、不解封任何保留集。官方checkout `third_party/TATO` 保持提交 `402bbc8998c49e2f33d9afbcc42140347a6b8c36`，原adapter会拒绝HEAD变化或脏源码。许可MIT。[官方仓库](https://github.com/thulab/TATO)

## 已实际运行的直接对照

真实入口是 `scripts/v431_baselines/worker.py --request <request.json>`（Bolt）和`timesfm_tato_worker.py --request <request.json>`（TimesFM2.5），不是原官方整实验入口。已有共同DEV各156窗/26parent；金融各12窗/2parent，旧结果和所有失败继续保留。核心调用`adapt_window`只接受当前dirty context：先截到512−H，以其余可见H步作为历史验证，8个Optuna trial按MAE选参，最后在当前512输入做一次目标预测。未接收当前future参数。

| 范围 | Bolt | TimesFM2.5 |
|---|---:|---:|
| 共同DEV MASE |1.685227|1.529002|
| 主表完整摊销秒/窗 |0.703174|1.023989|
| 原始worker完整进程秒 |79.906722|110.175571|
| 原始模型加载秒 |4.106745|3.883725|
| 实际实验模型调用 |837|552|
| trial记录总数 |1248|1248|
| 失败trial |0|546|

费用来源：`results/v431/20260914-sprint/{tato,timesfm_tato}/{summary,status,calls,decisions}.json`；主表另补完整进程余量，不能拿早期summary的0.526649/0.902798冒充完整费用。原始进程调用数经过cache去重，不能拿它直接当156个独立请求所需总调用。每窗8优化trial不是8个agent历史工具；失败和最终治理/预测费用都保留。

TimesFM的546次失败全部有明确不支持原因：历史长度416或320小于trimmer要求。`timesfm_tato_worker.py:12`按模型原生patch32构造管线，保留官方trimmer5…15；选480时H96/H192各156失败，选448时各78失败，选384时H192另78失败。没有偷偷补额外context、改变future或填零。Bolt按patch16构造，其相同5…15在两长度可容纳；因此本适配的两家族有效原生搜索空间不完全相同，必须报支持率。

原生空间保留8类：trimmer、inputer、denoiser、warper、differentiator、normalizer、sampler、aligner，以及inference_mode/clip_factor；不是五臂选择器。原生管线可改变已观测值、内部长度及采样，外部预测仍逆变换回同H与时间网格。NaN用显式observed-only线性桥接，allmissing拒绝；官方非有限输出替换被adapter改为失败，不能声称完全无修改官方复现。完整原始输入上TATO也可能有动作，不能用五臂no-op约束限制它。

## 与官方实验协议的差别

以本地固定官方代码为准，`experiment/run.py:92/152/199`使用1440context；默认`train_trials=500`、`num_samples=500`、`top_k=16`，训练与其validation阶段都从dataset的train段采样；训练上报MSE，之后Pareto及加权排序，test评估原配置和候选。官方README示例100trial不是默认完整配置；不能任选其中数字描述已经完成。

| 维度 | 当前受限治理协议 | 官方入口协议 |
|---|---|---|
| 输入 |L512，单请求历史416/320，无额外历史|L1440，多TRAIN样本|
| 搜索监督 |当前context末H的可见值，MAE|TRAIN目标、多指标/MSE搜索|
| 搜索 |8trial，seed101，每窗重选|默认500trial、500样本、top16，多阶段|
| 模型 |冻结Bolt、TimesFM2.5本地wrapper|配置表Timer/Moirai/Chronos-tiny/Sundial等|
| 指标 |共同mask，source/parent权重MASE|原代码MSE/MAE/RMSE/MAPE/MSPE|
| 预算 |逐窗完整费用核对0.8140623268639832/3.5秒|官方未定义本项目同一单请求预算|

R2_EXISTING_CART的mask+历史信息不同于r3/r4 H/control，保留完整方法行，不能称同证据消融。仅胜此短预算TATO不等于胜官方完整方法，不复制官方排名到共同表。

## 真实可执行入口与未完成项

旧产物已经齐全，应先hash验证再复用，不为改尺度重跑输入未变的预测。两个worker `--prepare`、`--request`入口真实存在；准备输出必须新目录，不能覆盖旧首次结果。使用现有Chronos解释器，保留core/TSICL隔离。固定adapter所需Optuna/scipy等从项目已有`.cache/v431-baseline-deps`读取，不重装。

官方完整实验代码真实存在，但当前其`DATASET/`和`CKPT/`未准备为官方期望布局，默认模型也不是本轮冻结骨干，**官方完整实验未执行**。不要直接运行旧setup脚本；尤其不能直接启动其test阶段而绕过本项目封存。未来官方协议必须单独目录与独立来源manifest，与本项目封存集名称/文件完全隔离。

原官方最小命令形态（**登记，未执行；CKPT/DATASET及许可验收后才可运行**）为：

```bash
# 独立协议，不读取本项目 calibration/test；不可在当前未准备布局上直接启动。
python experiment/run.py --device cuda:0 --dataset ETTh2 --model Chronos-tiny \
  --pred_len 96 --train_trials 500 --num_samples 500 --top_k 16 \
  --save_dir <independent-official-protocol-output>
```

该命令是官方模型/官方指标表，不能称同骨干主表。若同本项目骨干适配官方TRAIN搜索，则需新wrapper显式register Bolt/TF2.5和本项目fit/gate读取器，按TRAIN搜索、gate冻结，再在旧DEV并列；代码尚未实现，不能把8trial脚本改参数便称整协议完成。

## 仅凭元数据登记独立评估候选

首选候选来源为官方TATO支持的**ETTh2与Exchange**：分别覆盖未用变压器小时序列和汇率日序列，理由是任务机制/频率及官方入口覆盖，不来自r4胜率。它们只是待审核候选，不预先宣称已合法下载或具备授权；需单独记录原始提供者、数据许可/版本、列含义、时区、频率、预处理和既有模型预训练重叠。

选窗规则先冻结再接触标签：每来源按官方原时间顺序及split，用不重叠最大包络L+Hmax为parent（受限主协议L512、Hmax192；官方表L1440），同步通道及H共享parent；按时间分配fit/gate/development/未来确认，边界两侧完整读取范围不跨段。现有26 DEV、旧check/acq/新位置/金融表均不充当此确认。登记阶段不读候选性能，若许可或元数据不充分保留缺项，不按性能替换。

现有Crypto因原DEV仅426行，放不下L512+H96，不移动边界凑样本。原金融2parent不足以金融有效性立论；先解决日历、vintage与真实支持，不能靠新扰动数量扩大独立样本。

完整官方表与受限治理表各自报告全失败、预算范围、来源权重、指标单位及训练费用；只有在共同信息/监督/预算条件满足时才形成跨方法结论。当前真正执行的近期外部直接对照仍只有**TATO两家族8trial短预算适配**。
