# TATO TRAIN场景搜索：真实子集结果与审核

本表限预登记 target_block_10、H96/H192。ETTm1每场景29 fit/14 DEV parent；Solar22/11；USTS3/1。三来源合并每家族26 parent/52相关变体，与原156变体不同，所有对照按相同UID重算。未执行场景保留缺项。原生场景搜索不受五臂约束；使用冻结骨干、相同当前目标和原始评价mask。不是官方完整复现，不是新的确认集，不改原r5共同主表。

|场景|状态|成功/实际/登记trial|DEV成功/登记|TRAIN选择核验|
|---|---|---|---|---|
|bolt-h192|audited_completed|500/500/500|14/14|14500|
|bolt-h96|audited_completed|500/500/500|14/14|14500|
|timesfm-h192|audited_completed|500/500/500|14/14|14500|
|timesfm-h96|audited_completed|500/500/500|14/14|14500|
|solar-bolt-h192|audited_partial|455/455/500|11/11|10010|
|solar-bolt-h96|audited_completed|500/500/500|11/11|11000|
|solar-timesfm-h192|audited_partial|32/33/500|11/11|709|
|solar-timesfm-h96|audited_partial|247/247/500|11/11|5434|
|us_term_structure-bolt-h192|audited_partial|452/452/500|1/1|1356|
|us_term_structure-bolt-h96|audited_completed|500/500/500|1/1|1500|
|us_term_structure-timesfm-h192|audited_partial|247/248/500|1/1|743|
|us_term_structure-timesfm-h96|audited_completed|500/500/500|1/1|1500|

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
|bolt|TATO_SCENE_high|52/26|52|1.416821|1.416821|
|bolt|TATO_SCENE_low|52/26|52|1.416821|1.416821|
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
|timesfm|TATO_SCENE_high|52/26|52|1.221407|1.221407|
|timesfm|TATO_SCENE_low|52/26|52|1.221407|1.221407|

## 首四ETTm1共同子表

每家族14 parent、28个target_block_10变体；仅ETTm1，不代替三来源52变体完整表。以下为high预算同UID比较，完整原生方法的信息与搜索协议不同。

|家族|方法|MASE|完整窗/parent|费用秒/窗|超支|
|---|---|---:|---|---:|---:|
|bolt|FIXED_A0_NATIVE_high|0.999946|28/14|0.088379|0|
|bolt|FIXED_A2_SINGLE_high|1.091120|28/14|0.122223|0|
|bolt|R2_EXISTING_CART_high|0.999946|28/14|0.796780|0|
|bolt|R5_high|0.994298|28/14|0.093740|0|
|bolt|REFERENCE_FREE_high|0.994298|28/14|0.093617|0|
|bolt|TATO_NATIVE_8_high|1.585305|28/14|0.672120|0|
|bolt|TATO_SCENE_high|1.140375|28/14|0.048322|0|
|timesfm|FIXED_A0_NATIVE_high|1.274304|28/14|0.195255|0|
|timesfm|FIXED_A2_SINGLE_high|1.078010|28/14|0.227766|0|
|timesfm|R2_EXISTING_CART_high|0.993583|28/14|1.323637|0|
|timesfm|R5_high|1.065826|28/14|0.442281|0|
|timesfm|REFERENCE_FREE_high|0.993583|28/14|0.199960|0|
|timesfm|TATO_NATIVE_8_high|1.754685|28/14|0.988514|0|
|timesfm|TATO_SCENE_high|1.341847|28/14|0.113364|0|

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

## timesfm-h192

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.322749|1.322749|0.195152|0|0|
|FIXED_A0_NATIVE_low|1.322749|1.322749|0.195152|0|0|
|FIXED_A2_SINGLE_high|1.146009|1.146009|0.226689|0|0|
|FIXED_A2_SINGLE_low|1.146009|1.146009|0.226689|0|0|
|R2_EXISTING_CART_high|1.053253|1.053253|1.315703|0|0|
|R2_EXISTING_CART_low|1.053253|1.053253|1.315703|0|14|
|R5_high|1.133115|1.133115|0.457230|0|0|
|R5_low|1.131973|1.131973|0.452559|0|0|
|REFERENCE_FREE_high|1.053253|1.053253|0.199345|0|0|
|REFERENCE_FREE_low|1.053253|1.053253|0.199338|0|0|
|TATO_NATIVE_8_high|1.693810|1.693810|0.910790|0|0|
|TATO_NATIVE_8_low|1.693810|1.693810|0.910790|0|14|
|TATO_SCENE_high|1.345721|1.345721|0.112477|0|0|
|TATO_SCENE_low|1.345721|1.345721|0.112477|0|0|

模型冷启动 4.044 秒；离线搜索 1695.897 秒；DEV部署热请求累计 1.575 秒；worker阶段 1702.426 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 500}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## timesfm-h96

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.225859|1.225859|0.195358|0|0|
|FIXED_A0_NATIVE_low|1.225859|1.225859|0.195358|0|0|
|FIXED_A2_SINGLE_high|1.010010|1.010010|0.228842|0|0|
|FIXED_A2_SINGLE_low|1.010010|1.010010|0.228842|0|0|
|R2_EXISTING_CART_high|0.933913|0.933913|1.331571|0|0|
|R2_EXISTING_CART_low|0.933913|0.933913|1.331571|0|14|
|R5_high|0.998537|0.998537|0.427331|0|0|
|R5_low|1.045354|1.045354|0.382196|0|0|
|REFERENCE_FREE_high|0.933913|0.933913|0.200575|0|0|
|REFERENCE_FREE_low|0.933913|0.933913|0.200574|0|0|
|TATO_NATIVE_8_high|1.815560|1.815560|1.066238|0|0|
|TATO_NATIVE_8_low|1.815560|1.815560|1.066238|0|14|
|TATO_SCENE_high|1.337974|1.337974|0.114251|0|0|
|TATO_SCENE_low|1.337974|1.337974|0.114251|0|0|

模型冷启动 4.303 秒；离线搜索 1747.216 秒；DEV部署热请求累计 1.600 秒；worker阶段 1754.038 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 500}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## solar-bolt-h192

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.624087|1.624087|0.109451|0|0|
|FIXED_A0_NATIVE_low|1.624087|1.624087|0.109451|0|0|
|FIXED_A2_SINGLE_high|1.291039|1.291039|0.131706|0|0|
|FIXED_A2_SINGLE_low|1.291039|1.291039|0.131706|0|0|
|R2_EXISTING_CART_high|1.291039|1.291039|1.023464|0|0|
|R2_EXISTING_CART_low|1.291039|1.291039|1.023464|0|11|
|R5_high|1.345606|1.345606|0.128364|0|0|
|R5_low|1.345606|1.345606|0.128263|0|0|
|REFERENCE_FREE_high|1.345606|1.345606|0.128250|0|0|
|REFERENCE_FREE_low|1.345606|1.345606|0.128250|0|0|
|TATO_NATIVE_8_high|2.615655|2.615655|0.807834|0|0|
|TATO_NATIVE_8_low|2.615655|2.615655|0.807834|0|3|
|TATO_SCENE_high|2.563880|2.563880|0.060686|0|0|
|TATO_SCENE_low|2.563880|2.563880|0.060686|0|0|

模型冷启动 3.828 秒；离线搜索 484.657 秒；DEV部署热请求累计 0.668 秒；worker阶段 489.743 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 455}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## solar-bolt-h96

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|2.123144|2.123144|0.078328|0|0|
|FIXED_A0_NATIVE_low|2.123144|2.123144|0.078328|0|0|
|FIXED_A2_SINGLE_high|1.407522|1.407522|0.111373|0|0|
|FIXED_A2_SINGLE_low|1.407522|1.407522|0.111373|0|0|
|R2_EXISTING_CART_high|1.407522|1.407522|0.889339|0|0|
|R2_EXISTING_CART_low|1.407522|1.407522|0.889339|0|11|
|R5_high|1.463979|1.463979|0.103254|0|0|
|R5_low|1.463979|1.463979|0.103157|0|0|
|REFERENCE_FREE_high|1.463979|1.463979|0.103142|0|0|
|REFERENCE_FREE_low|1.463979|1.463979|0.103142|0|0|
|TATO_NATIVE_8_high|2.310701|2.310701|0.543357|0|0|
|TATO_NATIVE_8_low|2.310701|2.310701|0.543357|0|0|
|TATO_SCENE_high|2.070091|2.070091|0.041433|0|0|
|TATO_SCENE_low|2.070091|2.070091|0.041433|0|0|

模型冷启动 3.790 秒；离线搜索 357.513 秒；DEV部署热请求累计 0.456 秒；worker阶段 362.313 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 500}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## solar-timesfm-h192

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.276459|1.276459|0.195105|0|0|
|FIXED_A0_NATIVE_low|1.276459|1.276459|0.195105|0|0|
|FIXED_A2_SINGLE_high|1.365243|1.365243|0.226679|0|0|
|FIXED_A2_SINGLE_low|1.365243|1.365243|0.226679|0|0|
|R2_EXISTING_CART_high|1.144236|1.144236|1.450481|0|0|
|R2_EXISTING_CART_low|1.144236|1.144236|1.450481|0|11|
|R5_high|1.111484|1.111484|0.404707|0|0|
|R5_low|1.111484|1.111484|0.404697|0|0|
|REFERENCE_FREE_high|1.144236|1.144236|0.221781|0|0|
|REFERENCE_FREE_low|1.144236|1.144236|0.221782|0|0|
|TATO_NATIVE_8_high|1.801689|1.801689|0.900882|0|0|
|TATO_NATIVE_8_low|1.801689|1.801689|0.900882|0|11|
|TATO_SCENE_high|1.322176|1.322176|0.116815|0|0|
|TATO_SCENE_low|1.322176|1.322176|0.116815|0|0|

模型冷启动 3.957 秒；离线搜索 81.961 秒；DEV部署热请求累计 1.285 秒；worker阶段 88.097 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 32, "partial": 1}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## solar-timesfm-h96

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.257698|1.257698|0.197447|0|0|
|FIXED_A0_NATIVE_low|1.257698|1.257698|0.197447|0|0|
|FIXED_A2_SINGLE_high|1.108198|1.108198|0.228603|0|0|
|FIXED_A2_SINGLE_low|1.108198|1.108198|0.228603|0|0|
|R2_EXISTING_CART_high|1.016792|1.016792|1.479492|0|0|
|R2_EXISTING_CART_low|1.016792|1.016792|1.479492|0|11|
|R5_high|0.961153|0.961153|0.441902|0|0|
|R5_low|1.023070|1.023070|0.364196|0|0|
|REFERENCE_FREE_high|1.016792|1.016792|0.221788|0|0|
|REFERENCE_FREE_low|1.016792|1.016792|0.221794|0|0|
|TATO_NATIVE_8_high|1.692568|1.692568|1.058846|0|0|
|TATO_NATIVE_8_low|1.692568|1.692568|1.058846|0|11|
|TATO_SCENE_high|1.241464|1.241464|0.110404|0|0|
|TATO_SCENE_low|1.241464|1.241464|0.110404|0|0|

模型冷启动 4.011 秒；离线搜索 535.283 秒；DEV部署热请求累计 1.214 秒；worker阶段 541.491 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 247}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## us_term_structure-bolt-h192

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|0.904596|0.904596|0.094804|0|0|
|FIXED_A0_NATIVE_low|0.904596|0.904596|0.094804|0|0|
|FIXED_A2_SINGLE_high|0.889001|0.889001|0.128872|0|0|
|FIXED_A2_SINGLE_low|0.889001|0.889001|0.128872|0|0|
|R2_EXISTING_CART_high|0.889001|0.889001|0.709582|0|0|
|R2_EXISTING_CART_low|0.889001|0.889001|0.709582|0|0|
|R5_high|0.889001|0.889001|0.130741|0|0|
|R5_low|0.889001|0.889001|0.130636|0|0|
|REFERENCE_FREE_high|0.889001|0.889001|0.130621|0|0|
|REFERENCE_FREE_low|0.889001|0.889001|0.130622|0|0|
|TATO_NATIVE_8_high|0.867272|0.867272|0.815280|0|0|
|TATO_NATIVE_8_low|0.867272|0.867272|0.815280|0|1|
|TATO_SCENE_high|0.819709|0.819709|0.057681|0|0|
|TATO_SCENE_low|0.819709|0.819709|0.057681|0|0|

模型冷启动 3.818 秒；离线搜索 81.952 秒；DEV部署热请求累计 0.058 秒；worker阶段 86.142 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 452}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## us_term_structure-bolt-h96

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.135344|1.135344|0.079400|0|0|
|FIXED_A0_NATIVE_low|1.135344|1.135344|0.079400|0|0|
|FIXED_A2_SINGLE_high|1.101897|1.101897|0.113028|0|0|
|FIXED_A2_SINGLE_low|1.101897|1.101897|0.113028|0|0|
|R2_EXISTING_CART_high|1.101897|1.101897|0.556205|0|0|
|R2_EXISTING_CART_low|1.101897|1.101897|0.556205|0|0|
|R5_high|1.101897|1.101897|0.114667|0|0|
|R5_low|1.101897|1.101897|0.114579|0|0|
|REFERENCE_FREE_high|1.101897|1.101897|0.114560|0|0|
|REFERENCE_FREE_low|1.101897|1.101897|0.114560|0|0|
|TATO_NATIVE_8_high|1.006039|1.006039|0.520719|0|0|
|TATO_NATIVE_8_low|1.006039|1.006039|0.520719|0|0|
|TATO_SCENE_high|0.766494|0.766494|0.042954|0|0|
|TATO_SCENE_low|0.766494|0.766494|0.042954|0|0|

模型冷启动 3.751 秒；离线搜索 69.853 秒；DEV部署热请求累计 0.043 秒；worker阶段 73.988 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 500}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## us_term_structure-timesfm-h192

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|0.973870|0.973870|0.195724|0|0|
|FIXED_A0_NATIVE_low|0.973870|0.973870|0.195724|0|0|
|FIXED_A2_SINGLE_high|1.003261|1.003261|0.227269|0|0|
|FIXED_A2_SINGLE_low|1.003261|1.003261|0.227269|0|0|
|R2_EXISTING_CART_high|1.002407|1.002407|1.113451|0|0|
|R2_EXISTING_CART_low|1.002407|1.002407|1.113451|0|1|
|R5_high|1.002407|1.002407|0.623975|0|0|
|R5_low|1.002407|1.002407|0.623913|0|0|
|REFERENCE_FREE_high|1.003261|1.003261|0.228859|0|0|
|REFERENCE_FREE_low|1.003261|1.003261|0.228860|0|0|
|TATO_NATIVE_8_high|0.922200|0.922200|0.949440|0|0|
|TATO_NATIVE_8_low|0.922200|0.922200|0.949440|0|1|
|TATO_SCENE_high|0.930269|0.930269|0.103637|0|0|
|TATO_SCENE_low|0.930269|0.930269|0.103637|0|0|

模型冷启动 3.446 秒；离线搜索 83.006 秒；DEV部署热请求累计 0.104 秒；worker阶段 87.511 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 247, "partial": 1}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## us_term_structure-timesfm-h96

|方法|完整分母MASE|成功窗MASE（仅诊断）|费用秒/窗|失败未跑|low/high预算实际超支|
|---|---:|---:|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.136082|1.136082|0.194875|0|0|
|FIXED_A0_NATIVE_low|1.136082|1.136082|0.194875|0|0|
|FIXED_A2_SINGLE_high|1.166095|1.166095|0.242927|0|0|
|FIXED_A2_SINGLE_low|1.166095|1.166095|0.242927|0|0|
|R2_EXISTING_CART_high|1.162498|1.162498|1.138596|0|0|
|R2_EXISTING_CART_low|1.162498|1.162498|1.138596|0|1|
|R5_high|1.136082|1.136082|0.439550|0|0|
|R5_low|1.136082|1.136082|0.439463|0|0|
|REFERENCE_FREE_high|1.166095|1.166095|0.244440|0|0|
|REFERENCE_FREE_low|1.166095|1.166095|0.244440|0|0|
|TATO_NATIVE_8_high|1.111292|1.111292|1.112264|0|0|
|TATO_NATIVE_8_low|1.111292|1.111292|1.112264|0|1|
|TATO_SCENE_high|1.150837|1.150837|0.115517|0|0|
|TATO_SCENE_low|1.150837|1.150837|0.115517|0|0|

模型冷启动 5.299 秒；离线搜索 173.885 秒；DEV部署热请求累计 0.116 秒；worker阶段 180.184 秒（不含此前imports/部分hash检查）。训练样本预测、失败trial与全部模型调用仍收费，不将离线搜索均摊后冒充部署费。

失败trial状态：{"completed": 500}。详细失败、逐窗输入/评分mask/revision、变换后形状与预测跨度见 audit JSON。

## 官方96单位独立实验

以下采用官方patch/data/model单位96，seq_l=5..15原样保留。L512下大部分长度不支持，失败原样记录。与scaled-unit场景实验分别报告，不把两种协议混称官方完整复现。

|scene|状态|成功/实际/登记trial|新scene MASE（high）|完整子进程秒|
|---|---|---|---:|---:|
|bolt-h192|audited_completed|33/500/500|1.806359|75.201|

|官方96同UID方法|MASE完整分母|部署费用秒/窗|超预算|
|---|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.052150|0.097752|0|
|FIXED_A0_NATIVE_low|1.052150|0.097752|0|
|FIXED_A2_SINGLE_high|1.135679|0.128667|0|
|FIXED_A2_SINGLE_low|1.135679|0.128667|0|
|R2_EXISTING_CART_high|1.052150|0.852461|0|
|R2_EXISTING_CART_low|1.052150|0.852461|14|
|R5_high|1.050338|0.105036|0|
|R5_low|1.050338|0.104935|0|
|REFERENCE_FREE_high|1.050338|0.104921|0|
|REFERENCE_FREE_low|1.050338|0.104920|0|
|TATO_NATIVE_8_high|1.664499|0.802787|0|
|TATO_NATIVE_8_low|1.664499|0.802787|0|
|TATO_SCENE_high|1.806359|0.058575|0|
|TATO_SCENE_low|1.806359|0.058575|0|
|bolt-h96|audited_completed|33/500/500|1.254998|67.172|

|官方96同UID方法|MASE完整分母|部署费用秒/窗|超预算|
|---|---:|---:|---:|
|FIXED_A0_NATIVE_high|0.947742|0.079006|0|
|FIXED_A0_NATIVE_low|0.947742|0.079006|0|
|FIXED_A2_SINGLE_high|1.046562|0.115779|0|
|FIXED_A2_SINGLE_low|1.046562|0.115779|0|
|R2_EXISTING_CART_high|0.947742|0.741099|0|
|R2_EXISTING_CART_low|0.947742|0.741099|1|
|R5_high|0.938258|0.082444|0|
|R5_low|0.938258|0.082330|0|
|REFERENCE_FREE_high|0.938258|0.082314|0|
|REFERENCE_FREE_low|0.938258|0.082313|0|
|TATO_NATIVE_8_high|1.506111|0.541453|0|
|TATO_NATIVE_8_low|1.506111|0.541453|0|
|TATO_SCENE_high|1.254998|0.039426|0|
|TATO_SCENE_low|1.254998|0.039426|0|
|timesfm-h192|audited_completed|33/500/500|1.497541|136.854|

|官方96同UID方法|MASE完整分母|部署费用秒/窗|超预算|
|---|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.322749|0.195152|0|
|FIXED_A0_NATIVE_low|1.322749|0.195152|0|
|FIXED_A2_SINGLE_high|1.146009|0.226689|0|
|FIXED_A2_SINGLE_low|1.146009|0.226689|0|
|R2_EXISTING_CART_high|1.053253|1.315703|0|
|R2_EXISTING_CART_low|1.053253|1.315703|14|
|R5_high|1.133115|0.457230|0|
|R5_low|1.131973|0.452559|0|
|REFERENCE_FREE_high|1.053253|0.199345|0|
|REFERENCE_FREE_low|1.053253|0.199338|0|
|TATO_NATIVE_8_high|1.693810|0.910790|0|
|TATO_NATIVE_8_low|1.693810|0.910790|14|
|TATO_SCENE_high|1.497541|0.112943|0|
|TATO_SCENE_low|1.497541|0.112943|0|
|timesfm-h96|audited_completed|33/500/500|1.408024|138.186|

|官方96同UID方法|MASE完整分母|部署费用秒/窗|超预算|
|---|---:|---:|---:|
|FIXED_A0_NATIVE_high|1.225859|0.195358|0|
|FIXED_A0_NATIVE_low|1.225859|0.195358|0|
|FIXED_A2_SINGLE_high|1.010010|0.228842|0|
|FIXED_A2_SINGLE_low|1.010010|0.228842|0|
|R2_EXISTING_CART_high|0.933913|1.331571|0|
|R2_EXISTING_CART_low|0.933913|1.331571|14|
|R5_high|0.998537|0.427331|0|
|R5_low|1.045354|0.382196|0|
|REFERENCE_FREE_high|0.933913|0.200575|0|
|REFERENCE_FREE_low|0.933913|0.200574|0|
|TATO_NATIVE_8_high|1.815560|1.066238|0|
|TATO_NATIVE_8_low|1.815560|1.066238|14|
|TATO_SCENE_high|1.408024|0.105296|0|
|TATO_SCENE_low|1.408024|0.105296|0|

计时口径：首四scene的status.wall_seconds只涵盖worker阶段，前置import及部分hash检查未单独计时，不能称完整OS进程。extra v1队列wall_seconds从等mutex前开始，包含排队；v2由wall_scope明确标注锁后完整子进程时间，并单列queue_wait_seconds，按实际记录区分。official96的remaining_jobs job.seconds在锁后计时，才可作为完整子进程墙钟。未记录的开销保持未知，不补造0。

冻结选择只从完成的TRAIN trial按宏平均MSE取最小值，平局取最早trial；独立重算每个已保存TRAIN样本与最终DEV预测。只有冻结文件、完整部署manifest、最终预测归档及worker终态均存在才读取旧DEV目标。不存在的结果保持待运行；部分结果不填零，也不偷偷缩小完整表分母。

## TRAIN角色与时间输入代码审核

首批 prepare 和额外 prepare_extra 都先从已冻结免费参考的 training_parents 取T_fit父组，再按 source/H/target_block_10 选取独立parent。准备包只含全部请求的512点脏context，以及TRAIN请求的target/mask；DEV没有目标数组。独立审计检查包键集合严格相等，不允许额外标签或特征数组。各TRAIN请求完整context+H读取在原TRAIN边界内。

实际 forecast(row, params) 只把该row的context、H、当前trial参数交给 execute_frozen_scene；预测完成后才取TRAIN目标计算MSE/MAE，并向Optuna反馈。不存在把早期TRAIN origin之后的值追加到模型输入或作为归一化数据的接口。TRAIN标签影响离线搜索参数是有监督拟合，不是无偏训练性能，也不能作为该早期origin部署时已有的证据。最终DEV部署只使用冻结参数与该DEV context，不把TRAIN/DEV目标传入预测函数。该结论基于具体输入键、调用链与保存的模型输入，不声称通用形式化信息流证明。

额外resolved request仅允许登记运行时上限因剩余时间缩短；source、field、H、condition、UID、trial数与TRAIN监督角色必须与preregistered文件完全一致。缓存修订使用独立worker并绑定cache_amendment：原request/worker与新worker/module SHA分别保留，只替代尚未执行extra，不双计16个scene。原输入、参数、500trial与600秒上限保持不变。每次TRAIN缓存命中校验相同parent、checkpoint、native config、dtype、实际输入及H、首次raw文件/point/hash与首次真实费用；lookup+copy另收费，部署每请求清缓存。USTS仅3个TRAIN parent和1个DEV parent，其支持局限必须保留。
