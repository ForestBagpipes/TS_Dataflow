# 用户截止时间与执行追加记录

用户明确：`2026-09-16 05:04:31`服务器将关机，要求充分利用资源执行已给规划。按用户时区Asia/Shanghai解释；02:23:32实测剩余2小时40分59秒。不由助手执行关机。

r5候选开发已失败准入，保持冻结；追加计算是强基线补齐与独立评估准备，不增加r5配置或解封calibration/test。

02:31左右单GPU顺序启动TATO四场景：Bolt H96/H192，TimesFM H96/H192。每场景ETTm1、HUFL、L512、target_block_10，29个与r5相同fit parent、最多500trial，冻结后14个旧DEV parent部署验收。先20个TRAIN吞吐请求，不查看其表现来选场景；根据实测登记Bolt每场景1200秒、TimesFM2100秒，原900秒request保留v1及SHA。包含60秒冻结/部署预留；未完成真实记partial。

队列按最坏上限约110分钟，目标04:25结束；04:45不再接入新重任务，04:55完成归档、Git同步和聊天完整交付。任何在途任务在截止前保存状态/PID/当前trial、失败和可续执行命令，不能把开始等同完成。

CPU同时准备Weather、八来源时间重叠与mask清单、成本信息对照、原生TATO边界/费用审计及最终独立统计。实际task状态以results下status与原始日志为准，不依据本文件计划宣称结果。

03:03实际修订：extra等待队列v2截至04:25，official96最多使用04:25–04:45，primary仍原冻结上限。归档queue.execution.v1_waiting_archived.json和time_reservation_amendment.json；未停止GPU或他人进程。
