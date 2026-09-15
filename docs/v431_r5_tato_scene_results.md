# TATO TRAIN场景搜索：真实子集结果与审核

本表限预登记 target_block_10、H96/H192。ETTm1每场景29 fit/14 DEV parent；Solar22/11；USTS3/1。三来源合并每家族26 parent/52相关变体，与原156变体不同，所有对照按相同UID重算。未执行场景保留缺项。原生场景搜索不受五臂约束；使用冻结骨干、相同当前目标和原始评价mask。不是官方完整复现，不是新的确认集，不改原r5共同主表。

|场景|状态|成功/实际/登记trial|DEV成功/登记|TRAIN选择核验|
|---|---|---|---|---|
|bolt-h192|audited_completed|500/500/500|14/14|14500|
|bolt-h96|audited_completed|500/500/500|14/14|14500|
|timesfm-h192|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|
|timesfm-h96|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|
|solar-bolt-h192|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|
|solar-bolt-h96|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|
|solar-timesfm-h192|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|
|solar-timesfm-h96|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|
|us_term_structure-bolt-h192|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|
|us_term_structure-bolt-h96|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|
|us_term_structure-timesfm-h192|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|
|us_term_structure-timesfm-h96|pending_frozen_and_all_saved_deployment|未完成|未评分|待验证|

## 全部预登记来源共同子表

|家族|方法|完整窗/parent|已预测窗|完整分母MASE|成功子集MASE（诊断）|
|---|---|---|---|---:|---:|
|bolt|FIXED_A0_NATIVE_high|52/26|52|1.297844|1.297844|
|bolt|FIXED_A0_NATIVE_low|52/26|52|1.297844|1.297844|
|bolt|FIXED_A2_SINGLE_high|52/26|52|1.145283|1.145283|
|bolt|FIXED_A2_SINGLE_low|52/26|52|1.145283|1.145283|
|bolt|R2_EXISTING_CART_high|52/26|52|1.114892|1.114892|
|bolt|R2_EXISTING_CART_low|52/26|52|1.114892|1.114892|
|bolt|R5_high|52/26|52|1.131513|1.131513|
|bolt|R5_low|52/26|52|1.131513|1.131513|
|bolt|REFERENCE_FREE_high|52/26|52|1.131513|1.131513|
|bolt|REFERENCE_FREE_low|52/26|52|1.131513|1.131513|
|bolt|TATO_NATIVE_8_high|52/26|52|1.661713|1.661713|
|bolt|TATO_NATIVE_8_low|52/26|52|1.661713|1.661713|
|bolt|TATO_SCENE_high|52/26|28|缺项|1.140375|
|bolt|TATO_SCENE_low|52/26|28|缺项|1.140375|
|timesfm|FIXED_A0_NATIVE_high|52/26|52|1.198786|1.198786|
|timesfm|FIXED_A0_NATIVE_low|52/26|52|1.198786|1.198786|
|timesfm|FIXED_A2_SINGLE_high|52/26|52|1.133136|1.133136|
|timesfm|FIXED_A2_SINGLE_low|52/26|52|1.133136|1.133136|
|timesfm|R2_EXISTING_CART_high|52/26|52|1.052183|1.052183|
|timesfm|R2_EXISTING_CART_low|52/26|52|1.052183|1.052183|
|timesfm|R5_high|52/26|52|1.057130|1.057130|
|timesfm|R5_low|52/26|52|1.075062|1.075062|
|timesfm|REFERENCE_FREE_high|52/26|52|1.052925|1.052925|
|timesfm|REFERENCE_FREE_low|52/26|52|1.052925|1.052925|
|timesfm|TATO_NATIVE_8_high|52/26|52|1.506187|1.506187|
|timesfm|TATO_NATIVE_8_low|52/26|52|1.506187|1.506187|
|timesfm|TATO_SCENE_high|52/26|0|缺项|缺项|
|timesfm|TATO_SCENE_low|52/26|0|缺项|缺项|

## bolt-h192

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.052150|1.052150|0.097752|0|0|
|FIXED_A0_NATIVE_low|1.052150|1.052150|0.097752|0|0|
|FIXED_A2_SINGLE_high|1.135679|1.135679|0.128667|0|0|
|FIXED_A2_SINGLE_low|1.135679|1.135679|0.128667|0|0|
|R2_EXISTING_CART_high|1.052150|1.052150|0.852461|0|0|
|R2_EXISTING_CART_low|1.052150|1.052150|0.852461|0|14|
|R5_high|1.050338|1.050338|0.105036|0|0|
|R5_low|1.050338|1.050338|0.104935|0|0|
|REFERENCE_FREE_high|1.050338|1.050338|0.104921|0|0|
|REFERENCE_FREE_low|1.050338|1.050338|0.104920|0|0|
|TATO_NATIVE_8_high|1.664499|1.664499|0.802787|0|0|
|TATO_NATIVE_8_low|1.664499|1.664499|0.802787|0|0|
|TATO_SCENE_high|1.178885|1.178885|0.057689|0|0|
|TATO_SCENE_low|1.178885|1.178885|0.057689|0|0|

模型冷启动 3.582 秒；离线搜索 821.340 秒；DEV部署热请求累计 0.808 秒；worker阶段 826.118 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 500}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## bolt-h96

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|0.947742|0.947742|0.079006|0|0|
|FIXED_A0_NATIVE_low|0.947742|0.947742|0.079006|0|0|
|FIXED_A2_SINGLE_high|1.046562|1.046562|0.115779|0|0|
|FIXED_A2_SINGLE_low|1.046562|1.046562|0.115779|0|0|
|R2_EXISTING_CART_high|0.947742|0.947742|0.741099|0|0|
|R2_EXISTING_CART_low|0.947742|0.947742|0.741099|0|1|
|R5_high|0.938258|0.938258|0.082444|0|0|
|R5_low|0.938258|0.938258|0.082330|0|0|
|REFERENCE_FREE_high|0.938258|0.938258|0.082314|0|0|
|REFERENCE_FREE_low|0.938258|0.938258|0.082313|0|0|
|TATO_NATIVE_8_high|1.506111|1.506111|0.541453|0|0|
|TATO_NATIVE_8_low|1.506111|1.506111|0.541453|0|0|
|TATO_SCENE_high|1.101865|1.101865|0.038954|0|0|
|TATO_SCENE_low|1.101865|1.101865|0.038954|0|0|

模型冷启动 3.556 秒；离线搜索 527.936 秒；DEV部署热请求累计 0.545 秒；worker阶段 532.416 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 500}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## 官方96单位独立实验

以下采用官方patch/data/model单位96，seq_l=5..15原样保留。L512下大部分长度不支持，失败原样记录。与scaled-unit场景实验分别报告，不把两种协议混称官方完整复现。

|scene|状态|成功/实际/登记trial|新scene MASE（high）|完整子进程秒|
|---|---|---|---:|---:|
|bolt-h192|pending_frozen_and_all_saved_deployment|未完成|未评分|未完成|
|bolt-h96|pending_frozen_and_all_saved_deployment|未完成|未评分|未完成|
|timesfm-h192|pending_frozen_and_all_saved_deployment|未完成|未评分|未完成|
|timesfm-h96|pending_frozen_and_all_saved_deployment|未完成|未评分|未完成|

计时口径：首四scene的status.wall_seconds只涵盖worker阶段，前置import及部分hash检查未单独计时，不能称完整OS进程。extra v1队列wall_seconds从等mutex前开始，包含排队；v2由wall_scope明确标注锁后完整子进程时间，并单列queue_wait_seconds，按实际记录区分。official96的remaining_jobs job.seconds在锁后计时，才可作为完整子进程墙钟。未记录的开销保持未知，不补造0。

冻结选择只从完成的TRAIN trial按宏平均MSE取最小值，平局取最早trial；独立重算每个已保存TRAIN样本与最终DEV预测。只有冻结文件、完整部署manifest、最终预测归档及worker终态均存在才读取旧DEV目标。不存在的结果保持待运行；部分结果不填零，也不偷偷缩小完整表分母。

## TRAIN角色与时间输入代码审核

首批 prepare 和额外 prepare_extra 都先从已冻结免费参考的 training_parents 取T_fit父组，再按 source/H/target_block_10 选取独立parent。准备包只含全部请求的512点脏context，以及TRAIN请求的target/mask；DEV没有目标数组。独立审计检查包键集合严格相等，不允许额外标签或特征数组。各TRAIN请求完整context+H读取在原TRAIN边界内。

实际 forecast(row, params) 只把该row的context、H、当前trial参数交给 execute_frozen_scene；预测完成后才取TRAIN目标计算MSE/MAE，并向Optuna反馈。不存在把早期TRAIN origin之后的值追加到模型输入或作为归一化数据的接口。TRAIN标签影响离线搜索参数是有监督拟合，不是无偏训练性能，也不能作为该早期origin部署时已有的证据。最终DEV部署只使用冻结参数与该DEV context，不把TRAIN/DEV目标传入预测函数。该结论基于具体输入键、调用链与保存的模型输入，不声称通用形式化信息流证明。

额外resolved request仅允许登记运行时上限因剩余时间缩短；source、field、H、condition、UID、模型/代码hash、trial数与TRAIN监督角色必须与preregistered文件完全一致。USTS仅3个TRAIN parent和1个DEV parent，其支持局限必须保留。
