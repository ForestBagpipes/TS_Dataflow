# v4.3.1 当日并行冲刺交付

本轮交付的是完整可执行方法和真实共同开发表；新方法没有晋升。用户时区Asia/Shanghai，启动2026-09-14 23:28:17，截止24:00，T=1903秒。三线按文件归属并行推进，无等待H2显著性才启动的串行门。所有计算均在当前服务器，三个环境未重装，GPU始终按root统一队列串行；代理/Codex服务未更改。

## 共同结果

| Chronos-Bolt共同策略 | MASE ↓ | 批量组件秒数 |
|---|---:|---:|
| FIXED_A0_NATIVE | 1.258454 | 0.0899 |
| FIXED_A2_SINGLE | 1.157005 | 0.1201 |
| OLD_DIRTY_HGB | 1.165414 | 0.1592 |
| OLD_LEARNED_HGB_COMMON_BUDGET | 1.190112 | 0.4766 |
| DIRTY_LOSS_TREE_D1 | 1.163685 | 0.1066 |
| DIRTY_LOSS_TREE_D2 | 1.200158 | 0.1117 |
| CART_target_horizon | 1.136486 | 0.6580 |
| FLAT_LOSS_TREE_target_horizon | 1.165232 | 0.6625 |
| ALL_d2_target_horizon_gated | 1.191788 | 0.6637 |
| ALL_d2_target_horizon_unpruned | 1.184872 | 0.6569 |
| AGENT_d2_target_horizon_gated_high | 1.200158 | 0.1122 |
| TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR | 1.685227 | 0.7032 |

完整表包含所有已完成策略，见[v431_main_table.md](v431_main_table.md)和机器可读[v431_main_table.csv](v431_main_table.csv)，由同一 `scripts/v431_report.py` 同时填入本报告和论文草稿。新旧方法在同一156变体/26父组重算；没有按成绩删来源。原五臂oracle仅作诊断，不进入方法排名。

新单步agent在dev全部STOP，MASE1.200158，落后于固定TS-ICL1.157005；主动获取贡献未成立。普通CART为1.136486，比当前新方法好，不能把普通gating能达到的收益写成我们证据层的独有突破。其实际两个分裂特征是dirty最长缺口比例（索引2）与已取得ridge伪块误差（拼接索引25），三个历史配置均未用历史特征，因而动作一致；它仍按预登记全部调用收费，没有看结果后削减预算来美化。

目标跨度证据也没有带来本轮核心增益：三种历史配置的d2剪枝策略均为1.191788，不剪枝目标跨度为1.184872，都未优于固定TS-ICL。H1选择空间仍存在；H2有普通遮挡gating的开发信号，但提出的任务树/细化没有额外优势；H3未成立。普通CART对固定TSICL的条件配对gain区间见机器证据，不能当作独立确认或ICLR/SOTA声明。

## 终态、获取与信息契约

固定五臂，dirty基础特征13项，不含候选输出、source名字、路径、真实缺陷类或future。按source原始时间拆54 T_fit/21 T_gate/17 T_check/18 T_acq，完整704跨度同组。8个预登记终态配置；基础depth1/2、每训练叶>=16独立parent、最多16训练切点，细化最多一层。独立gate至少8parent且经验90%分组收益下界>0保留；不剪枝两项消融原样报告。

T_gate选出d2_target_horizon_gated和d2_old32_gated后，先写terminal hash与模型JSON，再生成T_acq的432条工具值标签。两端均是同一个冻结pi，正/零/负值保留；完整分支费用差包括最终动作/预测改变和共享组件。每工具depth2回归树受18个parent限制不能拆为两个各16的叶，实际是根叶；lambda只在T_acq内部LOPO选择，两配置均选择0。没有为避免全STOP而放宽支持或改阈值。

准入用完整分支预估费用，非DeltaC，统一low=0.814062327秒、high=3.5秒，由T_fit/T_gate成本冻结。实际超支保留；固定全部证据和外部TATO为原生工具计划，超支作事后审计，不能称硬wall-clock保证。候选输出在当前策略决定后才生成和计费；旧HGB使用候选值特征，因此保留全池生成成本。

## 历史增量与来源审计

L512、extra_history0、H96/H192。新origin exclusive r=416/320，使用dirty前缀重新生成五臂，验证同一dirty中r之后已发生的32步或目标H步。没有裁切最终治理后的context、补读context之前或读clean。新增1,120次真实TSICL插补和5,536次Bolt预测，生成816 episode的两种新跨度证据；执行体389.808秒。两个新条件共享相同历史候选，部署费用分别计。

历史生产进程因复用SprintData曾打开已读train/dev标签档案，但这些标签未进入工具公式或worker，原始future新读取0，heldout0；这一点已单独记录，不能把该离线生产器称为完全不打开evaluator的部署入口。其实际源文件副本和SHA保存于history/producer_source。真正在线入口另用文件访问屏障封存9档案。所有时间/量纲/availability/原始预测已独立核对。

## 近期baseline与第二家族

TATO立即接入官方八类变换及原生流水线，未限制为我们五臂。缺失context采用显式observed-linear桥接，原生无桥接NaN失败保留；8trial在dirty内部r=L-H验证，最终future不进入优化。Bolt实际156窗、1,248成功trial、837次唯一真实预测，独立重放全部原始quantile、正逆变换和选择通过；MASE1.685227是短预算本地适配结果，不能称击败官方论文完整复现。低预算68/156超支，高预算0，费用已补计跨窗cache命中，不能把他窗先算出的预测当免费。

TimesFM是独立家族，模型与官方来源revision另冻结。当前完成范围由下方动态记录给出；未完成项不填预计数字，Chronos2不冒充第二家族。TimesFM原生NaN处理、patch32、不同trimmer支持和TATO失败trial全部单列。

{
  "tato": {
    "table_sha256": "8490adb7374d4491bff9520011e88d61fed7d135a37025f147811ae82e232219",
    "status": {
      "status": "completed",
      "pid": 10157,
      "worker_python": "/home/vipuser/work2-envs/w2-chronos/bin/python",
      "request_sha256": "54949d7055cd9b2f16f0e8fb6a13f7f9f974bd610bd6d76cf594c624235259ee",
      "rows_done": 156,
      "future_labels_read": 0,
      "heldout_labels_read": 0,
      "elapsed_seconds": 79.89861163,
      "model_load_seconds": 4.106744997000078,
      "total_wall_seconds": 79.90672176599992,
      "prediction_file_sha256": "24244f92bed9153f5b34727330ebafb16ccba807f4932545162b61cb5655f2cb",
      "actual_model_calls": 837,
      "peak_gpu_bytes": 429876224,
      "all_row_wall_seconds": 52.36885990600081,
      "process_overhead_seconds": 27.53786185999911
    }
  },
  "timesfm": {
    "table_sha256": "1891a98cbc2a523fb1fb26de98dec167aff79b2b26a3b346b049eca44d50e9b2",
    "status": {
      "status": "completed",
      "pid": 13992,
      "worker_python": "/home/vipuser/work2-envs/w2-chronos/bin/python",
      "request_sha256": "0e371c52527e0c648ae1ffdf6f5e54bdaf9b4872e4db9958218a26d295d38a7a",
      "rows_done": 780,
      "future_labels_read": 0,
      "heldout_labels_read": 0,
      "elapsed_seconds": 71.45795860599992,
      "model_load_seconds": 3.350128885000231,
      "total_wall_seconds": 71.49136769000006,
      "prediction_file_sha256": "c982b3bc5c4c1e2e77b14c44de2f8ace3066b5aa8e099ff8e776056bdcad68f1",
      "actual_model_calls": 370,
      "peak_gpu_bytes": 941848064,
      "all_row_wall_seconds": 56.953198895005244,
      "process_overhead_seconds": 14.538168794994817
    }
  }
}

未完成或在途：
[
  {
    "backend": "timesfm_tato",
    "backbone": "timesfm-2.5-200m",
    "policy": "TATO_8_OFFICIAL_SPACE_OBSERVED_LINEAR",
    "status": {
      "status": "running",
      "pid": 14594,
      "worker_python": "/home/vipuser/work2-envs/w2-chronos/bin/python",
      "request_sha256": "89bae9a35aaf88b249d0ce9f81f9e2b457d409ac156f3878fd316aa1e7930a98",
      "rows_done": 11,
      "future_labels_read": 0,
      "heldout_labels_read": 0,
      "elapsed_seconds": 16.030243392999637
    }
  }
]

## 成本与在线执行

训练搜索/开发评价记录12.418秒；历史离线执行体389.808秒；TATO/Bolt记录worker wall79.907秒。离线pipeline初始化与未包住的解释器导入不能伪装为已精确测得的完整进程时间。组件表按原实测治理/工具/预测计费，后续单次dirty诊断补计保留为派生账本，不覆盖原冻结记录；共享诊断同时加到STOP和获取，DeltaC和训练value严格不变。

7例完整新agent在线回放只读上下文，封存9个evaluator/候选/工具档案，最终预测全部写盘后解封复核。实际全部STOP，仍真实生成所选治理和最终TSFM输出；没有先免费生成全池。动作、轨迹、候选和预测7/7一致。热请求合计1.864326秒，模型服务启动8.703547秒，其余初始化与退出1.968878秒；完整进程12.536751秒，平均1.790964秒，热/冷均无本次观察超支。此回放没有触发在线取证分支，不把离线证据生成称为agent实际在线取证。

## 通过、失败与冻结状态

22项本轮触及的语义测试通过，未机械重跑旧58项。历史6,656原始输出及主表6,708决策/2,768当前原始预测、8终态hash、2获取器与432条价值标签、LOPO隔离独立复核通过。首次history测试夹具availability少一列导致失败，修正夹具后通过；verifier先后漏识别新增计时key的失败保留，未改模型输出或填零。

源码实现和开发配置已冻结可复运行；不满足方法晋升和独立确认条件，calibration/test继续封存。只证明当前受控缺失治理协议，不证明真实valid-event识别、TSFM参数适配或文本LLM训练改善。完整方法执行而无增益仍是本轮真实交付，PICS_joint_relabel保持历史incumbent。

入口：`scripts/v431_fit_evaluate.py`（拒覆盖冻结模型）、`scripts/v431_online.py`（重复需新output-name）、`scripts/v431_verify.py`、baseline worker/verify、`scripts/v431_report.py`。全部逐窗值、原始预测、invoice、模型和训练manifest保留在 `results/v431/20260914-sprint`，大缓存与权重不进入Git。
