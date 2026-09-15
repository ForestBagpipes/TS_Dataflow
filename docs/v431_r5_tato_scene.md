> 2026-09-16 04:23 执行状态更新：本页下文保留准备时的协议与预登记状态。实际执行已推进：四个ETTm1 TATO场景各500trial完成，追加来源部分搜索按截止保留partial；Chronos-2原生KEEP已完成旧DEV26parent/156变体，MASE0.957177。Weather文件、输入/mask及重叠审核已完成准备。最新完整状态以 [交付快照](v431_r5_final_snapshot.md)、[TATO实际结果](v431_r5_tato_scene_results.md)、[Chronos-2结果](v431_r5_chronos2_native_results.md) 和 [主矩阵准备](v431_r5_main_readiness.md) 为准。准备文中的“未运行”不覆盖后续真实记录；官方完整复现和r5主矩阵确认仍未完成。

# r5 TATO 场景级 TRAIN 搜索扩展

2026-09-16。已有 r5 checkpoint 后新增，独立于已冻结失败候选；不能利用基线结果反向调整 r5。截止计划：04:45停止实验、04:55归档、05:04:31服务器关机由用户安排，本脚本不关机。

## 实际已准备

入口 `scripts/v431_r5_tato_scene.py`。四场景为 Bolt/TimesFM2.5 × H96/H192，全部ETTm1、channel0/HUFL、target_block_10、当前完整L512。根据元数据预选，不按胜率选择。沿用r5冻结reference的T_fit parent清单，两家族清单一致。每场景实际29个独立TRAIN parent，14个旧DEV parent；不重复采样填足500，不读gate/check/acq/calibration/test标签。DEV仍是已使用开发子集，不能与全26parent主表绝对数字混比。

每场景已生成 `results/v431-r5/tato-scene/{bolt,timesfm}-h{96,192}/request.json`，绑定输入文件、worker、adapter和参考冻结文件hash。TRAIN准备仅读取选中uid的future数组及共同mask；DEV输入文件只有context，无future。四场景CPU准备已完成，真实GPU状态看对应status，不能将本页准备当运行结果。

## 离线与在线职责

- `--prepare`：生成合法TRAIN+DEV输入请求，严格核TRAIN完整读取区间、当前512输入、原parent身份。
- `--request ... --pilot-only`：常驻加载一个家族，20个TRAIN parent使用固定原生vanilla变换测吞吐；不计算损失，不据此选方法。首次惰性分支开销保留。
- `--request ...`：TATO原8类算子、已缩放长度单位的L512适配空间，seed101、最多500trial、每trial遍历真实29TRAIN实例，选TRAIN平均MSE最小的已完成trial。保存全部失败、部分trial、原生模型调用/预测、最终原网格训练预测和耗时。
- 首次freeze写出后，在14个旧DEV当前context部署固定管线；不在线搜索。每请求清空预测cache，保留模型驻留，完整物化/预测/预测文件输出计热费。DEV目标仅在全部预测保存、GPU锁释放后进入独立评分。

该适配按原8类算子和已缩放长度单位搜索，不限于我们的五臂，可变更观测值；必须明确其信息、动作空间和监督差异。与旧8trial历史416/320搜索不同，本轮TRAIN每输入512，trimmer最大480不再天然超过输入；其他变换形状或模型支持失败仍原样保留，不能提前宣称失败消失。

官方完整协议L1440、500采样、top16/Pareto/后续验证未复现；本脚本是**同骨干L512的TRAIN场景适配**。29parent不能写成500独立实例。外部报告MASE需用原冻结外层分母重算；脚本保存原MAE/MSE，原始预测足以回算共同mask。

## 队列与截止

工作进程内部独占 `locks/gpu.lock`。父队列只能用不同mutex，例如 `locks/r5-tato-queue.lock`，禁止再持gpu.lock导致父子死锁。默认每场景900秒，搜索在总截止前60秒停止，为冻结和部署留时；剩余不足保留not_run_deadline，不删窗口、不填零。

```bash
source scripts/env_new_server.sh
"$W2_CHRONOS_PY" scripts/v431_r5_tato_scene.py \
  --request results/v431-r5/tato-scene/bolt-h96/request.json --pilot-only
# 经root查看20个TRAIN实际耗时并排队后执行：
"$W2_CHRONOS_PY" scripts/v431_r5_tato_scene.py \
  --request results/v431-r5/tato-scene/bolt-h96/request.json
```

同一场景pilot和run独立目录，拒绝覆盖。实际runtime/model cold/search/hot deployment分别保留。到deadline仅停止启动下一调用，不终止他人任务或修改模型/驱动。当前四场景最多约60分钟预算只是调度上限，真实完成trial数待日志。

## 实测TRAIN吞吐pilot

两家族H96均已运行20个合法TRAIN parent，0失败，不计算预测损失。

| 家族 | 冷加载秒 | pilot完整秒 | 热请求均值秒 | p95秒 | 最大/首次秒 | 峰值GPU allocated字节 |
|---|---:|---:|---:|---:|---:|---:|
| Bolt |4.109776|6.481547|0.089740|0.095071|1.074265|428322304|
| TimesFM2.5 |4.305983|7.576678|0.123077|0.129916|0.418405|941848064|

首次惰性开销未删除；除首次后常驻均值仅用于额外吞吐估计，分别约.0379和.1075秒。500trial×29parent的vanilla机械估算约550/1559秒（另加首次、离线优化、原生变换及日志），不是全变换空间完成保证。H192尚未实测。实际场景若到截止则保留partial，不能将未完成trial删掉后称500trial完成。

### 首次scene运行前的时间预算修订

仅根据上述TRAIN吞吐，未读取pilot损失（pilot不计算损失），四个scene在任何run目录创建前修改时间上限：Bolt H96/H192各1200秒、TimesFM H96/H192各2100秒。500trial和29parent支持等全部协议不变。原900秒request保存为`request.v1.json`，新旧SHA及理由保存于`time_budget_amendment.json`；worker代码hash不变。最坏四scene110分钟，按Bolt96→Bolt192→TimesFM96→TimesFM192单卡队列，仍不得越过04:45新任务截止。此修订覆盖本页先前900秒默认排程，不代表增加搜索网格或按性能调预算。

## 原生空间、模型上限与费用只读审计

本节不修改运行中的源码、参数或请求。

- 新scene调用 `v431_r5_prepare_main.execute_frozen_scene`，保留官方 `PipelineFactory` 的8类变换、infer0/infer1、clip_factor与sampler因子1/2，算子没有被限制为五臂，但长度单位不同于官方默认，不能称完整原生空间保留。初始化沿旧adapter的vanilla参数（trimmer15），并非声称逐行复制官方全部实验默认配置。
- 实际对象是NumPy输入。官方`sampler.py` NumPy分支按`ceil(length/factor)`缩短；Torch分支实现不同，但本路径不走Torch变换分支。`aligner`登记空间仅none/data_patch、edge_pad；不足patch倍数时左补当前边缘值。differentiator/warper/normalizer不引入未来观察。
- 原生管线先trimmer；Bolt patch16最大240，TimesFM patch32最大480。sampler只缩短，aligner向各自patch倍数补齐，因此登记空间推断Bolt输入不超过240、TimesFM不超过480。外部context仍512，不能把“提供了512”误写成各原生管线都实际使用512。
- pipeline factory按`ceil(H/factor/patch)*patch`选择内部预测跨度。Bolt H96的内部H为48或96；TimesFM H96为64或96；H192两者为96或192。后处理逆变换并回到原外部H和时间网格。外部评分不换目标或跨度。
- `baseline.TimesFM.forecast`本身没有手动slice；底层 `.cache/v431-timesfm-source/src/timesfm/timesfm_2p5/timesfm_2p5_base.py:178`确实包含原生`value[-context:]`。不足512时原生左侧zero+mask padding；大于512则原生裁尾。当前登记空间应不触及大于512的裁剪，必须用真实shape账本核验，不能仅据wrapper没有slice宣称无底层截断。
- wrapper请求`max_horizon=192`，但官方torch compile第401–408行按输出patch128向上调整，实际允许上限为256；`max_context=512`不变。`torch_compile=False`是模型载入参数，不表示没有调用官方`.compile(ForecastConfig)`。当前内部H均≤192，未利用256上限改变外部任务；此前将192称为实际硬上限的说法应收窄为“本项目登记最大H”。
- adapter显式以当前观测插值桥接NaN，全NaN拒绝；原生非有限输出替换已改为显式失败。它不是完全未经修改的官方实现，也不是保持有效观测的五臂算子。所有失败应保留，不用填零消失。
- 搜索每trial清理模型预测memo，允许同trial内相同输入命中，原始`calls.json`区分实际模型调用与命中；搜索完整墙钟与raw输出落盘费用保留。冻结部署每个请求重新清memo，模型权重仍常驻，输出npy在热请求时钟内保存。不得用离线缓存命中冒充线上免费预测。

进度shape审计快照：Bolt H96前194个trial均完成，5626次训练样本调用；原生输入长度40…240，H只有48/96，大于512的输入与大于192的内部H均0。这只是运行中快照，不是四scene最终验收，最终shape/失败统计由独立审计脚本更新。

## 按元数据登记的追加场景（尚未运行）

`v431_r5_tato_prepare_extra.py`已准备8个追加请求，保存在`results/v431-r5/tato-scene-extra/`，复用未修改的worker `6efa7e082b4e810c37a86a1aaf8f77a496d27c9bf8f5eeae556e7ac8e5fec625`。只在首四ETTm1场景完成、04:45前仍有时间时运行。没有据候选结果选源或改r5配置。

| 来源 | 实际目标字段/channel0 | 每scene真实T_fit parent | 旧DEV parent | 场景 |
|---|---|---:|---:|---|
| Solar |pv_0|22|11|两家族×H96/H192，target_block_10 |
| US_Term_Structure |FwdRate_Fitted_1Y|3|1|两家族×H96/H192，target_block_10 |

USTS的3个训练parent是极弱场景监督，不能灌水到500，也不能用1个DEV parent说明金融泛化。它是Kim–Wright拟合1年远期利率，不是HUFL或成交价格。

队列顺序固定：Solar/Bolt/H96→Solar/TimesFM/H96→USTS/Bolt/H96→USTS/TimesFM/H96，然后同源家族顺序H192。每scene最多500trial，预登记时间上限600秒；root在实际启动前仅按剩余墙钟缩短max_seconds，保留`request.preregistered.json`和新的resolved request/hash，不按损失决定时间。来不及则明确not_run，不强行开启或越过截止。准备仅读取所选TRAIN目标键，DEV只有context，heldout未读。

## 官方patch单位的进一步纠正（不改正在运行的实验）

**本轮准确名称是“TATO原8类算子、已缩放长度单位的L512场景适配”，不是完整官方原生空间。** 搜索500trial不能补偿已改变的长度单位。先前“未缩空间”的表述仅核对了离散枚举5…15，忽略其物理长度单位，现明确纠正。

| 项目 | 官方`experiment/run.py`默认 | 当前Bolt适配 | 当前TimesFM适配 |
|---|---|---|---|
| CLI `--patch_len`/pipeline `patch_len` |96|16|32|
| pipeline `data_patch_len` |96|16|32|
| pipeline `model_patch_len` |96|16|32|
| trimmer枚举 |5…15|5…15|5…15|
| trimmer实际长度 |480…1440|80…240|160…480|
| sampler后的长度/内部H取整单位 |96|16|32|
| aligner补齐单位 |96|16|32|
| 原始context |1440|512|512|
| 入队初始trimmer参数 |7（672点）|15（240点）|15（480点）|

真实代码证据：

1. `third_party/TATO/experiment/run.py:58`取`args.patch_len`，第72–75行将`patch_len`、`data_patch_len`、`model_patch_len`全部设为它；第245行CLI默认96。因此官方这个入口没有自动从骨干的`model.patch_len`推导这三个值，也不是本入口将data/model两个patch单位独立设置。
2. `third_party/TATO/model/model_factory.py:258`的旧`Chronos.patch_len=512`是模型对象属性，但上述官方CLI构造configs没有读取它。不能用此属性推导官方trimmer5×512…15×512。
3. `pipeline_factory.py:16–28`读取configs.patch_len，并按`ceil(H/factor/patch_len)*patch_len`改变内部H；`trimmer.py:23`同样将seq_l乘该单位。因此枚举相同不代表变换相同。
4. 当前`v431_r5_prepare_main.py:execute_frozen_scene`显式给三个字段16或32，这是旧适配继承的选择，不是官方实验默认96。`TunerFactory.build_search_space`虽接收patch_len，但离散分布主要来自算子类search_space；实际单位在管线构造时生效。
5. H96、sampler2时官方单位96得到内部H96，而当前Bolt得到48、TimesFM64；这不仅是输入截取长度变化，还影响模型内部任务。外部仍逆变换回同H96，但不能把两者视作完全相同原生候选。

后续原协议可行范围：在L512且禁止额外历史的受限协议下，保持官方单位96会使trimmer只有seq_l=5（480点）可直接容纳；6…15应明确unsupported，不能偷偷裁去而称官方全空间。若要完整覆盖官方480…1440长度，必须单列L1440协议及合法TRAIN/DEV窗口，并核冻结骨干实际context能力（当前TimesFM max_context512会原生裁尾，不能只把输入数组加长）。原官方模型、L1440、OT目标、500样本/top16/Pareto、标准化评价也应另外复现，不能混入本项目HUFL/L512/MASE表。当前队列不修改任何输入、参数、模型或搜索空间，保留作为已缩放空间适配的真实结果。

## 适合聊天交付的协议对照

| 比较项 | 旧8-trial适配 | 本轮TRAIN场景缩放单位 | 官方96单位L512审计 | 官方完整入口协议 |
|---|---|---|---|---|
| 算子 |官方8类算子代码|同8类|同8类|原官方管线|
| 长度单位 |Bolt16 / TF32|Bolt16 / TF32|全部96|CLI默认96|
| trimmer实际范围 |80–240 / 160–480|80–240 / 160–480|480–1440；L512下仅480合法|480–1440|
| context |历史416/320选参，当前512输出|TRAIN和部署输入512|TRAIN和部署输入512|1440|
| 搜索监督 |每请求context内可见历史MAE|r5 T_fit真实当前未来MSE|同r5 T_fit监督|TRAIN多样本MSE及多指标后续排序|
| 搜索量 |每请求8trial|每scene最多500；实际独立parent29/22/3|每scene最多500，ETTm1 29parent|默认500采样/500trial、top16/Pareto与验证|
| 在线职责 |每请求搜索再预测|直接执行TRAIN冻结管线|直接执行TRAIN冻结管线|官方选定管线后test|
| 不支持 |TF已知546/1248历史长度失败|保留形状/数值/时间失败|seq_l6–15明确失败，不裁空间|按官方骨干与布局|
| 成本 |搜索、加载、最终预测都计费|离线搜索/冷启动/热部署分列|同左，失败费用保留|须独立完整核算，不能借用本项目成绩|
| 可声称范围 |短预算请求适配|8类原算子+已缩放长度单位的场景适配|保留官方单位的L512受限协议审计|本项目尚未完整复现|

任何一列完成500trial都不自动成为最后一列；不同单位、L、目标字段、监督和top16流程必须分表。

## 截止队列审计快照

03:01:31北京时间：至04:25约83.5分钟，至04:45约103.5分钟。TF H96约134trial/468秒，以实际吞吐估剩余约21分钟；随后TF H192上限35分钟，primary保守约03:58完成。extras8×600秒不可能全部用满，必须保留partial/未运行，并给official96四个300秒场景预留20分钟。

原extra CPU队列已将deadline载入局部变量，单改磁盘文档不会改变进程。最安全操作是核实等待队列无子worker后，仅替换自建CPU等待队列，保留原状态，重新指定04:25；绝不终止在跑GPU。另需将截止复核和max_seconds分配放到取得队列mutex之后，防止排队等待让原分配过期。此为只读审核建议；实际变更以root新队列与归档状态为准，不在本页假称已执行。

## 只读TRAIN跨trial重复预测审计

已完成Bolt H96的500trial×29TRAIN模型调用共14500次，排除最后14次DEV部署。按**同parent、同实际模型输入hash、同H**分组：10925个唯一键，3575次重复（24.655%）；仅跨parent产生的额外重复为0。旧worker每trial清cache，所以这些都是再次物理计算。

逐一读取14500个原始TRAIN NPZ，重新计算输入dtype/shape/bytes hash；3575个重复原生point的dtype、shape和bytes全部相同，0不一致。没有读取目标标签。记录模型总耗时416.870秒，其中重复调用114.962秒，占27.6%；相对完整离线搜索527.936秒约21.8%。原生point缓存payload约3.10MB，含key/provenance的保守内存估计约17.4MB。

这支持未来独立worker进行有限离线缓存优化，但本次只读审计没有改任何运行worker或原请求。安全要求：仅同parent及同模型revision/数值配置/原生输入hash/H共享模型原始point；各trial仍独立治理与逆变换，不缓存最终后处理预测冒充别的管线；记录首次raw来源和实付费用、后续命中/查找成本。部署前完全清空，且每个部署请求继续清空，不能将训练缓存变成免费在线信息。旧历史计算费用不消失，新的实际节省与等价未缓存费用分别报告。

审计原始结果：`results/v431-r5/tato-scene/train_cache_reuse_audit.json`。是否实现由root按剩余时间决定，尚未将潜在节省记为实际成果。
