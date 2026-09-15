# TATO官方96单位在L512下的独立审计对照

2026-09-16。该对照用于纠正单位缩放后的可比性，不改变既有缩放版本，不按DEV结果挑单位。

实际入口：`scripts/v431_r5_tato_official96_scene.py`，显式调用独立`v431_r5_tato_official96_adapter.py`。未monkeypatch任何旧adapter或在跑worker。

四个预登记场景为ETTm1/HUFL/channel0、target_block_10、29个r5 T_fit parent、14个旧DEV parent，两家族×H96/H192。输入context仍512，pipeline patch_len/data_patch_len/model_patch_len全部96；seq_l仍完整5…15。官方初始参数seq_l=7沿用，因此首次trial在L512下为672>512，明确失败；其他初始参数与run.py原ori_param一致。不将无效长度移除、缩短或替换。只有seq_l5可生成480点截取，其后原算子仍按官方96单位运行。

最多500trial，先登记每scene300秒总预算，保留60秒冻结部署。root可按04:45前余时缩短但须保留原request/hash；来不及则not_run。它仍不是官方L1440、OT、500独立训练样本、top16/Pareto完整复现。

CPU检查已经实际完成：两个H×11个seq_l×两个sampler×两个infer模式×两个align模式，共176配置。其中16种合法准备，160种按预期报unsupported；合法变换输入长度240/288/480，内部H96/192。断言搜索空间上下界5和15以及初始seq_l7；torch.cuda未初始化，没有执行任何模型或评价损失。结果在`results/v431-r5/tato-official96/cpu_unit_checks.json`，日志`logs/v431-r5/tato-official96-cpu.log`。

GPU结果尚未运行时不能标完成。启动命令：

```bash
source scripts/env_new_server.sh
"$W2_CHRONOS_PY" scripts/v431_r5_tato_official96_scene.py \
  --request results/v431-r5/tato-official96/bolt-h96/request.json
```

工作进程自行持gpu.lock，父队列只用独立mutex。无需运行vanilla pilot，因为官方初始seq_l7在此受限L下已由CPU确定unsupported，不能用失败pilot当吞吐估计。

部署和评价职责同scene适配：在TRAIN完成trial中选平均MSE最小者并先freeze，DEV输入不含目标，全部最终预测保存后才能评价旧DEV。无成功trial时报告失败，不造fallback预测。原始失败、超时partial、计算费用与可用覆盖全部保留。缩放单位与96单位独立表格并列，不能看到哪种DEV更好再宣称它代表唯一“原版TATO”。
