# 主张-证据对应表（2026-09-21，v53 收口后定稿）

| 论文主张 | 位置 | 对应实验/定义 | 证据来源 | 支持程度 | 最终措辞要点 |
|---|---|---|---|---|---|
| 冻结骨干+观测保留下的请求级修复选择问题成立（无单一动作处处最优） | §1, §4.2, tab:heterogeneity | oracle-best 份额 11.1–24.8%、KEEP best 19.3% | results/v47/evaluation/test_*.json oracle 行 | 强（描述性，post-hoc） | 陈述变异事实，不说"每个目录成员必要" |
| 重建质量不能替代预测效用 | §4.2, tab:app-recutils | winner agreement 19.3%、discordant 44.5%、ρ=0.12 | results/v47/diagnostics/reconstruction_test_bolt.json（Bolt-only，已声明） | 中（单骨干） | 限定 Bolt；"provides limited guidance" |
| 总体 MASE 优于 KEEP | §4.3, tab:main, tab:app-holm | 配对差 −0.0881/−0.1283/−0.2014，区间均不含零，Holm 后 <0.05 | results/v47/evaluation/test_*.json comparisons | 强（post-hoc 边界内） | "paired intervals support improvement over the unchanged input" |
| 不优于 Best Fixed / R2-CART | §4.3 | 区间含零 | 同上 | 已如实陈述 | "do not establish an accuracy advantage" |
| 有害损失低于固定修复与简单选择器 | §4.4 | 0.0375 vs 0.0513/0.0584 | 同上 | 描述性（无区间检验） | 保持描述性措辞 |
| dispersion 惩罚的价值 | §4.4, fig:gate-controls, tab:v52-gates | 优于随机门控（三骨干区间不含零）；对 mean-only/线性门控优势骨干依赖 | results/v52_ablation/gate_controls/ | 中 | 收窄为"优于频率匹配随机门控"，不主张不确定性识别 |
| action-conditioned 局部检索是必要组件 | §4.6, tab:v52-a2 | A2R 池化变差 1.4470 vs 1.4366，bolt 区间不含零 | results/v52_ablation/evaluation/ | 中（仅 bolt 显著） | "supports action-specific local estimation within the tested design" |
| intervention 特征块必要性 | §4.6, tab:app-ablation A2, tab:v53-compact | 冻结配置下删除更好（1.4185）；各自选参后 train_eval 混合（timesfm 显著退化、chronos2 改善、bolt HL 升）→ 保留 Full-22；L-003：四个幅度特征恒为 0 | results/v53_state_compact/ + state.py:197-228 | 不支持精简替换 | "stays competitive under the frozen configuration and is not adopted once given its own selection" |
| 频率 vs 选择 | §4.4, tab:v53-gates | FULL 对 BF-Random 三骨干区间均不含零（p≤0.0014）；对 R2-CART-M 仅 bolt 不含零 | results/v53_state_compact/gate_controls2_*.json | 中-强 | "comes from which requests are repaired rather than how many"（限随机门控）；对 R2-CART-M 不断言 |
| 跨来源一致性 | §4.5, tab:v53-loso | 对 KEEP/TATO 优势 8/8 同号；对 BF/R2 优势集中于 Exchange（留出后归零/反转） | results/v53_state_compact/source_fixed_*.json | 已如实收窄 | "broad-based against the unchanged input; rests largely on one source against the stronger controls" |
| 请求级选择价值 | §4.5, tab:v53-source-fixed | SOURCE_FIXED 在 bolt/timesfm 显著优于 FULL，chronos2 不显著劣 | 同上 | 反向证据已披露 | 不主张请求级选择优于来源级固定；证据落在 KEEP 边际与频率匹配对照 |
| KEEP 的作用 | §3.4, tab:ablation A4 | always-act 有害损失 0.0533 vs 0.0375 | results/v52_ablation/ | 强 | 保留 |
| 部署成本 | §4.6, app:calls | 1.65 calls/req；延迟为骨干调用记录+检索开销的合成口径（已标注） | results/v47/cost_audit/ | 中（合成口径已披露） | 不冒充端到端实测 |
| 跨 severity 稳健（网格内） | §4.5, app:severity-full | test30/test50 均优于 KEEP | results/v47/evaluation/ | 中（within-grid） | "within the sampled missingness grid" |
| 评估范围 | §4.1, app:splits | 8 来源 3 骨干 4 模式 2 horizon；TEST 参与过开发 = post-hoc | configs/v47-verified/ + 披露段 | 已如实披露 | 独立确认未完成，保留披露 |
| 统计口径 | app:metric-conventions, tab:app-holm | parent 聚类 bootstrap 2000 次 seed 101、Holm 族=5 比较/骨干 | select.py:351-408 | 已核验一致 | 保持 |
