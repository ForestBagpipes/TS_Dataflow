# v4.3 Evidence Governance 设计与证据

## 冻结设计来源

本轮完整设计以 `new_server_execution_plan_20260914.md` 为准，本文不改写其算法或晋升条件。实施配置见 `configs/v43/bootstrap.yaml`。目标是保留原始时间、NaN 和未来读取边界，以真实 TSFM task gain 验证治理价值。PICS_joint_relabel 是历史 incumbent。

首个接口 pilot 固定 L512/H32、32 个不重叠 train/dev origins、seed101、通道0、target block `[230,281)`、batch1。TIME 使用同步 benchmark 行号，真实日历和发布延迟尚未恢复。Crypto 数量不足时只取3个，其余来源轮转补足；不制造重叠“独立”样本。上述实现选择在真实 future 标签读取前冻结。完整机制实验仍使用 H96/H192，后续抽样、信息轨道、训练与强对照须另行冻结。

## 2026-09-14 post-hoc：CPU 工程验收

已实现和测试的范围、旧入口归因、数据缺口、日志入口见 `v43_entrypoint_audit_20260914.md`。40 项 CPU 测试通过；数据输入准备完成。两个真实 worker 已写入但尚未由真实模型验收。pilot 因现有后台环境/模型准备未结束而 blocked_dependency。

没有 v4.3 方法成功、风险证书、适配收益或 SOTA 证据；A0–A5 未运行。进度 DOCX 的已验证研究成果不因接口代码和测试更新。


## 2026-09-14 21:00 post-hoc：真实 P1 pilot 完成

32 origins（20 train / 12 dev）、L512/H32、64 次真实 TS-ICL 插补和 96 次 Bolt 预测全部完成；43 项 CPU gate 通过，独立原始结果重算通过，未读 calibration/test。运行 21.794 秒，最大 GPU 分配 710,672,896 字节。KEEP / SINGLE / COV 来源宏平均 MASE 为 1.322762 / 1.316489 / 1.228219；COV 宏平均 MAE 反而变差，两插补臂各 15/32 个 origin task harm，无 CI。仅为接口与开发诊断，正式 A0–A5/H96/H192 未运行，PICS_joint_relabel 不变。首轮导入失败和可选 Chronos-2 TLS 失败保留。证据与原始结果入口见 `docs/v43_pilot_report_20260914.md`、`docs/v43_pilot_evidence_20260914.json`；下一步补长来源、接正式强对照及 A5 静态规则。
