# 主张-证据对应表（2026-09-21，v53 收口后定稿；同日晚间结构重写后更新位置）

结构重写（R25–R31）只改变段落位置与章节组织，不改变任何数值与证据本身。下表位置列已按新结构更新：主文 §4.1 Evaluation Protocol / §4.2 Variation in Repair Utility / §4.3 Forecasting Performance / §4.4 Intervention Frequency and Harm / §4.5 Effects of Utility Estimation and State Representation / §4.6 Sensitivity to Missingness and Replay Support / §4.7 Deployment Cost；附录 A–G 按问题重组（app:v52/app:v53 节已解散，表 label 保留）。

| 论文主张 | 位置 | 对应实验/定义 | 证据来源 | 支持程度 | 最终措辞要点 |
|---|---|---|---|---|---|
| 冻结骨干+观测保留下的请求级修复选择问题成立（无单一动作处处最优） | §1, §4.2, tab:heterogeneity（附录 C） | oracle-best 份额 11.1–24.8%（跨目录动作）、KEEP best 19.3% | results/v47/evaluation/test_*.json oracle 行 | 强（描述性，post-hoc） | 陈述变异事实，只说"潜在收益存在"，不说"每个目录成员必要" |
| 重建质量不能替代预测效用 | §4.2, app:recutils（附录 C） | winner agreement 19.3%、discordant 44.5%、ρ=0.12 | results/v47/diagnostics/reconstruction_test_bolt.json（Bolt-only，已声明） | 中（单骨干） | 限定 Bolt；"provides limited guidance"；已注明与 KEEP best share 同值系巧合 |
| 总体 MASE 优于 KEEP | §4.3, tab:main, tab:app-holm | 配对差 −0.0881/−0.1283/−0.2014，区间均不含零，Holm 后 <0.05 | results/v47/evaluation/test_*.json comparisons | 强（post-hoc 边界内） | "paired intervals support improvement over the unchanged input" |
| 不优于 Best Fixed / R2-CART | §4.3 | 区间含零 | 同上 | 已如实陈述 | "do not establish an accuracy advantage" |
| 请求级选择不优于来源级固定策略 | §4.3, app:source-diagnostics（tab:v53-source-fixed） | SOURCE_FIXED 在 bolt(+0.0181)/timesfm(+0.0269) 显著优于 FULL，chronos2 不显著劣，聚合 1.445 vs 1.437 | results/v53_state_compact/source_fixed_*.json | 反向证据已披露 | 不主张请求级选择优于来源级固定；证据落在 KEEP 边际与频率匹配对照 |
| 跨来源一致性 | §4.3, app:source-diagnostics（tab:v53-loso） | 对 KEEP/TATO 优势 8/8 同号；对 BF/R2 优势集中于 Exchange（留出后归零/反转） | 同上 | 已如实收窄 | "broad-based against the unchanged input; rests largely on one source against the stronger controls" |
| 有害损失低于固定修复与简单选择器 | §4.4（已补 harmful loss 定义，代码口径 select.py:295） | 0.0375 vs 0.0513/0.0584 | results/v47/evaluation/ | 描述性（无区间检验） | 保持描述性措辞 |
| 频率 vs 选择（门控对照） | §4.4, app:gate-controls（tab:v52-gates）、app:matched-partners（tab:v53-gates） | 对随机门控三骨干误差区间不含零；对 mean-only/线性仅单骨干；对 BF-Random 三骨干不含零；对 R2-CART-M 仅 bolt；随机门控有害损失三骨干更低；匹配伙伴实际 TEST 频率低于开发目标 | results/v52_ablation/gate_controls/ + results/v53_state_compact/gate_controls2_*.json | 中-强（非严格同预算） | 三类对照分开陈述；结论落在"准确率-损害权衡"，不写"收益来自选择哪些请求"的机制归因，不写安全保证 |
| action-conditioned 局部检索（A2-M pooling） | §4.5, tab:ablation, app:estimation-analyses（tab:v52-a2） | pooling 变差 1.4470 vs 1.4366，bolt 区间不含零；同时改变局部/先验平衡，非单因素消融 | results/v52_ablation/evaluation/ | 中（仅 bolt 显著） | "supports action-specific local estimation within the tested design"；A1 全局均值 1.475/HL 0.0697 已入正文 |
| intervention 特征块（A2-F 固定配置；Compact 重新选参） | §4.5, app:estimation-analyses, app:compact-selection（tab:v53-selection/tab:v53-compact） | 冻结配置下删除更好（1.4185）；各自选参后 DEV 混合（timesfm 退化 [0.0012,0.0581]、chronos2 改善 [0.0035,0.0477]、bolt HL 升）→ 按采用规则保留 Full-22；L-003：四个幅度特征恒为 0 | results/v53_state_compact/ + state.py:197-228 | 不支持精简替换 | 固定配置消融与表示选择分开陈述；TEST 1.4280 仅备案 |
| KEEP 的作用（A4） | §4.5, tab:ablation | always-act 有害损失 0.0533 vs 0.0375 | results/v52_ablation/ | 强 | 保留 |
| 跨 severity 稳健（网格内） | §4.6, app:severity-full（附录 F） | test30/test50 均优于 KEEP；R2-CART 高严重度反超 | results/v47/evaluation/ | 中（within-grid） | "within the sampled missingness grid" |
| 历史支持敏感性 | §4.6, app:replaysize/app:selstability/app:seeds（附录 F） | bank 大小、选参稳定、掩码实现三类检查分别变化不同对象 | results/v47/ | 中 | 明确三类均非独立泛化验证 |
| 部署成本 | §4.7, app:calls（附录 G） | 1.65 calls/req；候选构造选择前支付；延迟为合成口径（已标注），端到端未实测 | results/v47/cost_audit/ | 中（合成口径已披露） | 只回答"请求级选择增加哪些计算"，不报延迟分位数 |
| 评估范围 | §4.1, app:splits（附录 A） | 8 来源 3 骨干 4 模式 2 horizon；TEST 参与过开发 = post-hoc | configs/v47-verified/ + 披露段 | 已如实披露 | 独立确认未完成，保留披露 |
| 统计口径 | app:metric-conventions（附录 A）, tab:app-holm | parent 聚类 bootstrap 2000 次 seed 101、Holm 族=5 比较/骨干 | select.py:351-408 | 已核验一致 | 保持 |
