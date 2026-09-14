# v4.3 P1 真实模型 pilot：完成，方法尚未晋升

2026-09-14 20:55:03–20:55:24（UTC+8），32 个 origin（20 train / 12 dev）完成 L512/H32 接口诊断。43 项 CPU 语义测试通过后，使用冻结官方 TS-ICL / Chronos-Bolt 权重完成 64 次插补与 96 次预测。独立复核从保存的原始预测、quantiles 和 targets 重算，身份、形状、共同分母、MASE train 尺度及 64 个插补的观测位置逐字节不变均通过。未读取 calibration/test 标签；独立复核未新增 future 读取。

| 臂 | 来源宏平均 MASE | 来源宏平均 MAE | 比 KEEP 退步的 origin |
|---|---:|---:|---:|
| KEEP | 1.322762 | 8.863374 | 0/32 |
| TSICL_SINGLE | 1.316489 | 8.718427 | 15/32 |
| TSICL_COV | 1.228219 | 9.317810 | 15/32 |

单变量 MASE 相对改善约 0.47%，协变量约 7.15%，但协变量宏平均 MAE 变差。协变量在 Crypto 和 ETTm1 的来源 MASE 退步；Crypto 只有 3 个 train origin。原单位差异与极小来源支持限制了整体解释。这里没有置信区间，是混合 train/dev 的 H32 接口诊断，不能当正式 dev 表或跨来源方法成功。历史兄弟通道用于治理后输入单变量 Bolt；严格单变量与额外信息轨道须分开解释，原生多变量对照尚缺。

总运行 21.794 秒；三次 worker 墙钟合计 20.550 秒。TS-ICL 单变量 / cov 推断合计 1.078 / 1.143 秒，Bolt 96 次合计 2.539 秒；最大 GPU 分配 710,672,896 字节。相同 H32 三臂的每千 origin 外推含 20% 余量约 771 秒，不代表 H96/H192、七种嵌套遮挡或完整 A0–A5 的成本。

首次 20:49 pilot 在 worker 导入处失败：根包提前加载旧 statsmodels 依赖。该 run 的预测与 future 标签读取均为零；失败完整保留。修复按需导入并扩展代码 hash 后，本次真实重跑完成。可选 Chronos-2 元数据仍 TLS 失败，manifest 总状态仍 failed；本阶段必需的 TS-ICL/Bolt 均 ready/passed，不替换模型，不影响本次已声明的必需模型集合。

原始结果：`results/v43/20260914T125500.992800Z-pilot/`。独立重算入口：`scripts/verify_v43_pilot.py`。可提交证据及原始文件 SHA256：`docs/v43_pilot_evidence_20260914.json`。队列日志：`logs/v43/20260914T125500.992800Z-pilot-queue/`。原安装和 pilot 监控已随 pilot 完成退出；后续实验另建独立任务与监控。

下一步推进 P2：补较长的异机制公开来源并核验时间、只读 train/dev 适配；冻结 H96/H192 dev 矩阵，接 A0 双 KEEP、A2/A3、A4 局部及全合法历史 ridge、A5 七种遮挡缓存和支持不足回 A2。A1 原始可复现性单独审计，不用旧缺失缓存阻断其他臂。未完成这些强对照、开发上界及来源支持前，不进入大型 scorer/主动工具训练。PICS_joint_relabel 保持 incumbent；不更新 DOCX 的已验证研究成果。
