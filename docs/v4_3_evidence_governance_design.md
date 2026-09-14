# v4.3 Evidence Governance 设计与证据

## 冻结设计来源

本轮完整设计以 `new_server_execution_plan_20260914.md` 为准，本文不改写其算法或晋升条件。实施配置见 `configs/v43/bootstrap.yaml`。目标是保留原始时间、NaN 和未来读取边界，以真实 TSFM task gain 验证治理价值。PICS_joint_relabel 是历史 incumbent。

首个接口 pilot 固定 L512/H32、32 个不重叠 train/dev origins、seed101、通道0、target block `[230,281)`、batch1。TIME 使用同步 benchmark 行号，真实日历和发布延迟尚未恢复。Crypto 数量不足时只取3个，其余来源轮转补足；不制造重叠“独立”样本。上述实现选择在真实 future 标签读取前冻结。完整机制实验仍使用 H96/H192，后续抽样、信息轨道、训练与强对照须另行冻结。

## 2026-09-14 post-hoc：CPU 工程验收

已实现和测试的范围、旧入口归因、数据缺口、日志入口见 `v43_entrypoint_audit_20260914.md`。40 项 CPU 测试通过；数据输入准备完成。两个真实 worker 已写入但尚未由真实模型验收。pilot 因现有后台环境/模型准备未结束而 blocked_dependency。

没有 v4.3 方法成功、风险证书、适配收益或 SOTA 证据；A0–A5 未运行。进度 DOCX 的已验证研究成果不因接口代码和测试更新。
