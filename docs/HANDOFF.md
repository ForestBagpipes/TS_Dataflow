## 2026-09-14 21:00 post-hoc：真实 P1 pilot 完成

32 origins（20 train / 12 dev）、L512/H32、64 次真实 TS-ICL 插补和 96 次 Bolt 预测全部完成；43 项 CPU gate 通过，独立原始结果重算通过，未读 calibration/test。运行 21.794 秒，最大 GPU 分配 710,672,896 字节。KEEP / SINGLE / COV 来源宏平均 MASE 为 1.322762 / 1.316489 / 1.228219；COV 宏平均 MAE 反而变差，两插补臂各 15/32 个 origin task harm，无 CI。仅为接口与开发诊断，正式 A0–A5/H96/H192 未运行，PICS_joint_relabel 不变。首轮导入失败和可选 Chronos-2 TLS 失败保留。证据与原始结果入口见 `docs/v43_pilot_report_20260914.md`、`docs/v43_pilot_evidence_20260914.json`；下一步补长来源、接正式强对照及 A5 静态规则。

### 2026-09-14 18:48 最终 CPU 复核

最终测试增至 **40 passed in 0.96s**，日志 `logs/v43/contracts/20260914T104754.619288Z/`。修复残差回归在 PCA 后附加缺失指示导致最终维度可能超过8的问题；现将缺失指示纳入训练支持内的缩放/PCA，最终维度上限8。旧39项日志保留。先前等待队列会因代码hash改变正常阻塞退出，新队列与当前代码绑定；实时状态仍查 `results/v43/pilot_queue_status.json`。真实模型实验仍未运行。

## 2026-09-14 新服务器 v4.3 接管更新

本轮已经实际完成旧入口静态审计与 CPU 契约实现，**39 passed in 0.95s**。日志：`logs/v43/contracts/20260914T104430.294322Z/`；最新 gate：`results/v43/semantic_gate.json`。这不是模型或方法验收。

最新数据输入 run：`results/v43/20260914T104433.076049Z-data/`。32 个不重叠 origin（20 train/12 dev），ETTh1/ETTh2/ETTm1/USTS 各6、Oil5、Crypto3。独立进程 origin/data/context 清单逐字节相同，记录 `results/v43/data_determinism.json`。future 标签读取数为0。TIME 明确采用 benchmark 共同原始行号，真实日历/发布延迟未恢复，不能将其称为已验证实时可用时间。

TS-ICL/Bolt worker 与真实 pilot 入口已实现但尚未真实验收。安装和模型准备复用原后台任务，未改写三个 prefix。一次性 pilot 队列使用 tmux `work2-v43-pilot-20260914`，socket `/tmp/tmux-1000/default`；入口 `scripts/launch_v43_pilot_queue.sh`；最新状态 `results/v43/pilot_queue_status.json`，其中记录本次目录、PID、代码/config hash 和错误。它在模型 ready 后重跑 CPU gate，然后执行真实32-origin pilot；如代码/config变化、模型失败或 GPU 契约失败则停止并留痕。队列启动不代表 pilot 完成。原环境任务与模型接续的 PID 在接管时为45580、47722。

复核入口：显式 `source scripts/env_new_server.sh` 后运行 `python3 scripts/bootstrap_status.py`，再读 pilot queue 状态。主机 GPU/PID/tmux 检查应在能看到主机进程的执行范围做，不能用沙箱不可见作死亡证据。不要重启或重复安装现有任务。

当前研究状态：PICS_joint_relabel 仍是 incumbent，v4.3 未晋升；A0–A5、正式 H96/H192、工具价值训练、calibration/test、适配和确认均未执行。完整范围见 `docs/v43_entrypoint_audit_20260914.md`、`docs/v43_experiment_matrix.md`。真实 pilot 完成后先核对身份、单位、shape、NaN、原始预测和成本，再按完整方案推进 A0–A5，不因接口通过更新 DOCX 中的已验证方法成果。

---

# Handoff, end of the experimental phase

State as of 2026-08-15. **This is a historical snapshot. For the current
project state see `docs/version_ledger.md` and `docs/diagnostic-playbook.md`.**
Major developments after this date include: the damage metric was corrected to
`max(worse_binary, discard_share)`, v1's main table numbers were recomputed,
per-family conformal calibration replaced the global threshold, v2-smoke350
showed near-zero coverage, the v3 training-dynamics triage probe returned
red (AUROC 0.5794) and was stopped, the v2.1 counterfactual probe
(veto attribution, route-conditioned shift replay, candidate-level TSFM pilot)
was run without forming a new version, and a 2026-09-01 P0 provenance audit
(`experiments/p0_*`) froze the calibration corpus and found that the two level-
shift evaluation scripts use inconsistent `_nmse` definitions, integrity-blocking
Phase B and making the full-window probe's loss numbers artefacts of the
centered metric.

2026-09-02 update, detailed in `docs/v3_contextual_conformal_shield.md`: the
`_nmse` split is resolved by the canonical `experiments/metrics_common.py`
implementation, with both level-shift paths agreeing on all 67 probe windows.
The v3-pre Action-Conditioned Conformal Governance Shield was trained,
calibrated and compared against four control arms under leave-one-dataset-out.
It fails the pre-registered Phase 4 gates (protected mis-edit 0.057 vs 0.0055,
damage 0.082 vs 0.05, no significant coverage increment over the statistical
arm). The single allowed v3.1-pre iteration (a dual beneficial-and-safe plus
harmful gate) significantly improved every safety metric and still fails; the
verdict is STOP_CANDIDATE and no smoke350 was run. A post-run code review then
found the v3-pre feature extractor was partly broken (constant
`touched_fraction`, broken `seam_error`, pseudo `outside_support_drift`, three
constant-zero features) and its calibration did not match the deployed
first-commit rule, so the v3-pre numbers are downgraded to
implementation-invalid/inconclusive. The v3.2 PICS loop is pre-registered in
`docs/v3_2_pics_preregistration.md`: repair the extractor, rebuild the
candidate table on the frozen corpus, and test a pessimistic cross-source
dual-head shield with episode-replay calibration against fixed gates. The
oracle headroom on the same candidate pool (coverage 0.33 at damage 0, all of
it in DENOISE/DESPIKE/IMPUTE) remains the empirical motivation.

2026-09-02 second update, v3.2 PICS closed loop
(`docs/v3_2_pics_preregistration.md`): the extractor repairs are in and tested
(13 contract tests), the candidate table was rebuilt with byte-identical labels
and operator outputs (`results/v32_training_data.jsonl`, sanity
`results/v32_feature_sanity.json`), and the seven-arm offline comparison is in
`results/v32_arms_compare.json`. PICS_joint passes every safety gate
(protected mis-edit 0.0030 vs 0.0181, damage 0.0220 vs 0.0506, conditional
damage CI [0.145, 0.346] vs 0.379) and fails both liveness gates: beneficial
coverage 0.1227 vs 0.1455 and OOD edit 0.321 vs 0.05 (v2_frozen edits 0.036 of
OOD). Verdict: gates not passed, diagnostic branch, no smoke350 requested, no
second tuning round run. Residual harm is concentrated in IMPUTE on missing
kinds, where the finite-mask NMSE cannot see the pre-repair hole.

2026-09-03 update, v3.3 MAST-PICS pre-registered
(`docs/v3_3_mast_pics_design.md`): three defects, all code-traced, are the
agenda. (1) The IMPUTE label is wrong: the canonical finite-mask NMSE cannot
see a hole in `before_nmse`, so 13 of 17 v3.2 harmful commits are a label
artefact; the KEEP counterfactual becomes the forward-filled series the probe
actually queries, exposed as `materialize_for_probe`. (2) The ensemble-spread
OOD gate measures source disagreement, not novelty; it is replaced by a
support–consequence certificate (cosine kNN K=20 on training-fold profiles,
hazard = low_support AND structural instability). (3) The heads split
asymmetrically: joint features predict benefit, TSFM/structure features
predict harm. All v3.2 label-dependent metrics are non-comparable and every
arm is recomputed under the new labels; the formal OOD set moves to a new
frozen seed with sawtooth and real_ood; RESEGMENT stays closed.

2026-09-03 second update, v3.3 closed as a diagnostic branch: the label repair
(IMPUTE's KEEP counterfactual is now the probe-materialised series, one public
`materialize_for_probe`) is confirmed and kept — 395 of 1154 IMPUTE candidates
flipped harmful→beneficial_and_safe, oracle IMPUTE headroom 0.164→0.640, and 8
of the 13 v3.2 harmful commits were label artefacts. The asymmetric fusion is
refuted: MAST_support_consequence fails 7 of 14 gates (pme 0.0242, CHR 0.304,
bcov 0.1614 vs PICS's 0.2727 at equal damage, paired bootstrap CI
[-0.086, -0.042]) because the episode calibration saturated the harm cap at
the 0.95 grid edge — corpus-level corrected risk does not control conditional
harm. The support–consequence certificate scores zero OOD edits on the frozen
seed-313 set (64 synthetic + 32 real) but is carried entirely by the
structural term, so the support index remains unproven. No second tuning
round, no smoke350. Full record in `docs/v3_3_mast_pics_design.md`.

2026-09-03 third update, v3.4 SCRC-PICS closed as a diagnostic branch
(`docs/v3_4_scrc_pics_preregistration.md`): Phase 0 clean-ran the corrected
v3.3 arms script and reproduced the baseline exactly (every number within
1e-9; the hand-patched OOD classification is now produced by code), so the
incumbent PICS_joint_relabel (bcov 0.2727, CHR 0.2053, pme 0.0091, gain
0.0919, damage 0.0402) stands on a clean pipeline. Phase 1 answered the
conditional-risk question negatively: on frozen PICS scores no calibration
fold has any threshold meeting CHR≤0.10 with a Clopper-Pearson 95% UB≤0.10,
and even an oracle post-hoc grid directly on held-out tops out at bcov 0.0614
(per-family 0.0932) under CHR≤0.10 — recorded as "score ranking insufficient".
Phase 2 tested the shadow intervention certificate (pseudo-gaps in the
observed region, 3 deterministic masks per sample_uid, integrity hard-checks
all passed: 1154/1154 operator outputs bit-identical to the frozen table) and
failed 3 of 4 pre-registered signal gates: harmful AUROC 0.351, AUPRC gain
over the PICS harm score +0.008, harmful recall 7.4% at a 10% false-reject
point; only trial coverage passed (99.7%). Per the pre-registration Phase 3
was not run: no SCRC_PICS arm, no smoke350, no API calls. The joint
conclusion: the current deployable score set does not order candidates by
true conditional risk — neither a new selector on the same scores nor a
self-supervised operator certificate fixes that. The next iteration needs a
better candidate-level signal or operator family, not another threshold
scheme.

2026-09-03 fourth update, v3.5 ACV closed as a diagnostic branch
(`docs/v3_5_acv_preregistration.md`): the action-conditioned verification
idea — score a candidate by whether APPLY beats KEEP at forecasting real
observed blocks AFTER the changed support, plus a masked support-conformity
view — red-lit on its pre-registered primary: harmful AUROC 0.623, recall
25.8% at a 10% false-reject point, zero newly-accepted candidates under LODO
thresholds, realised evidence coverage 57.6% (vs 89% audit estimate; DENOISE
is structurally unverifiable because it rewrites the whole window). The
support-conformity ablation was directionally stronger (AUROC 0.708, AUPRC
lift +0.210) but under the 0.75 bar and not switchable post-hoc. The
TSFM_RECONSTRUCT_IMPUTE operator (MOMENT-1-large proposes, chronos/timesfm
verify) halved IMPUTE's harmful rate (0.539→0.289) but collapsed its
beneficial-and-safe rate (0.460→0.172) and added only +0.020 oracle coverage
— a conservative neutraliser, not a repairer; not_green. Phase 3 was not
run, no smoke350, no API. Three failed evidence lines (corpus scores, shadow
gaps, action-aligned outcomes) now point at the same ceiling: the frozen
TSFM error surface does not carry enough conditional-risk signal at
candidate granularity. Next direction belongs to the planning session.

2026-09-03 fifth update, v3.6 PAIR closed as a diagnostic branch
(`docs/v3_6_pair_preregistration.md`): within-window pairwise
action-improvement ranking (symmetric pairs over KEEP + all candidates,
episode-relative features, source-balanced LODO) was built cleanly — Phase 0
integrity 9/9 PASS, 827 episodes, 5402 pairs — but the Phase 1 decision arm
red-lit: pairwise accuracy 0.6454, deployment bcov 0.0909 / CHR 0.412 / pme
0.0514 against PICS 0.2727 / 0.2053 / 0.0091, no frontier improvement over
either PICS or the pointwise twin. Attribution without touching thresholds:
construction, pair direction and leakage are excluded by assertion; the
binding failure is cross-source generalisation — held-out ranking is strong
on Oil/Crypto/USTS (AUROC 0.92-0.99) yet the margin gate commits nothing
there, while every commit and all 28 harmful commits land in the ETT folds
where held-out ranking is near-random (ETTh1 0.497). Within-window
relativisation removes window difficulty, not source-specific harm sign.
Phase 2 latent and Phase 3 were not run per the stop rule; no smoke350, no
API, no DOCX (red light is not positive method progress). Incumbent remains
PICS_joint_relabel.


2026-09-03 sixth update, v3.7 SHIFT closed at Phase 0 (red light)
(`docs/v3_7_shift_preregistration.md`): before building the specialist
router and importance-weighted controller, two target-label oracles measured
the ceiling of perfect calibration on the frozen PAIR_absolute/logreg
ranking. Both fail: global threshold oracle bcov 0.041 / gain 0.022,
expert-mixture oracle bcov 0.180 / gain 0.023, against the bcov>=0.30 +
gain>=0.10 bar — while safety constraints are trivially met (CHR 0.00-0.05,
pme 0). The bottleneck is therefore not calibration but the value
extractable from the frozen candidate pool x ranking. The transfer matrix
adds: ranking transfers across sources (AUROC >0.72, 0.99 on Oil) but
thresholds do not (CHR up to 0.67 into ETTh2); fingerprint similarity does
not predict transferability (r=-0.054). Phase 1/2 not run, no smoke350, no
API, no DOCX. Incumbent remains PICS_joint_relabel. Cumulative verdict after
v3.2-v3.7 (corrected 2026-09-03 by the v3.8 Phase 0 replay,
`results/v38_oracle_replay.json`, bit-exact): 冻结 PAIR 排序/校准路线被排除
— no threshold/mixture calibration on the frozen PAIR ranking exceeds bcov
0.18; 尚未排除重新定义候选语义和构造可识别高精度候选 — the unrestricted
candidate oracle over the pool is bcov 0.6591 / gain 0.1969 / CHR 0, so the
pool contains the value; the open question is whether deployable evidence can
identify it.

2026-09-03 seventh update, v3.8 FACT-IntroAct closed at Phase 1 (red light,
`docs/v3_8_fact_preregistration.md`). Phase 0 delivered the mandated v3.7
correction (all three oracle replays bit-exact) and the mask-semantics audit:
1,154 IMPUTE candidates split into actual_nan_only (447, b&s 0.812, harmful
0.188), finite_flatline_only (623, b&s 0.218, harmful 0.782), mixed (84). The
two failure routes have different semantics: 16 of v3.6's 23 harmful IMPUTE
commits sit in the flatline layer, but 19 of PICS's 27 sit in actual_nan_only
— "filled a real NaN and still harmed". Phase 1 built IMPUTE_EXPLICIT_LINEAR
with frozen gap certificates (tight 4 / medium 8 / wide 16): observed-support
drift exactly 0 and harmful 0.068 on actual-NaN windows, but b&s only 0.429
(gate 0.80) and 0/6 sources candidate-level non-inferior, because every
missing_block injection (length 25-63, `experiments/corpus.py:107`) exceeds
the wide tier and abstains; on the scattered windows it does fill, b&s is
0.864. The FACT-pool unrestricted oracle passes (bcov 0.3705 / gain 0.1760 /
CHR 0), so the headroom exists, but the frozen coverage-potential rule for
the Phase 2B adapter (wide b&s >= 0.60) fails at 0.429 — the deficit is
coverage, not precision, and the pre-registration forbids widening the tiers
after seeing results. Operator retired per the frozen decision tree; Phase
2A/2B not entered; no smoke350, no API, no DOCX. Incumbent remains
PICS_joint_relabel. Open route: the value is in the pool (oracle bcov
0.6591), the certificate operator is safe but starved of long-gap coverage —
any rescue of this line needs a new pre-registered long-gap proposer, not a
tier adjustment.

2026-09-03 eighth update, v3.8 metric-semantics correction and v3.9 MIRAGE-TS
pre-registered (`docs/v3_9_mirage_preregistration.md`). Correction: the v3.8
gate number g1 = 0.429 is window-level beneficial coverage, not
action-conditional precision — over the 88 scattered windows actually filled,
precision is 0.864 and CHR 0.136; the correct v3.8 reading is 短缺口算子保留，
长缺口适用性失败. From v3.9 onward applicability coverage, action-conditional
B&S precision, action-conditional CHR, bcov and abstention rate are always
reported separately (playbook Tree 27). v3.9 keeps FACT_SHORT for gap runs
1-3 and adds BRIDGE_LONG: frozen foundation imputers (OpenFIM primary,
TS-ICL if installable, MOMENT reconstruction baseline) propose long-gap
(25-63) fills, shrunk toward the linear bridge by a frozen 3-signal max-risk
gate; PICS remains for DENOISE/DESPIKE only. Correction step only — no DOCX.

2026-09-03 ninth update, v3.9 MIRAGE-TS closed at Phase 2 (red light).
Phase 0 gave the six-arm replay and target budget (baseline D
FACT_SHORT-first: bcov 0.2659 / gain 0.0872 / act-cond CHR 0.1136; needs
+15 B&S windows and +5.63 gain-sum, with CHR/pme requiring harm reduction,
not additions). Phase 1 fetched two official foundation imputers (OpenFIM
MIT; TS-ICL non-commercial) and passed all four headroom gates: TS-ICL is
the strongest long-gap proposer (75 B&S / 14 harmful of 89), OpenFIM is
unusable alone (CHR 0.629, negative gain), and the joint oracle reaches
bcov 0.5545 / gain 0.195 / CHR 0. Phase 2 then failed on signal quality:
the deployable risk signals predict OpenFIM's harm (AUROC up to 0.757) but
not TS-ICL's (R AUROC 0.461), all six LODO folds have no calibrated point
at CHR CP95 <= 0.15, eta shrinkage does not reduce TS-ICL harm (75/14 at
both eta 0.5 and 1.0), and the single pre-registered isotonic+DRO rescue
branch still failed (CHR 0.200). Verdict: stop_signal_quality_insufficient
— the long-gap value exists in the pool; what is missing is
deployment-available per-window risk evidence for the strong proposer's
failures. Phase 3 not entered; no smoke350, no API, no DOCX. Incumbent
remains PICS_joint_relabel. Playbook Tree 28 records the mechanism.

2026-09-03 tenth update, v4.0 COUNTERACT-TS Phase 0+1 complete, not yet
formed (`docs/v4_0_counteract_preregistration.md` §11.1-§11.2). Phase 0:
integrity all-pass (0 hash mismatch), v3.9 budget carried over without
drift, public-data fetch from the laiguokun GitHub mirror fails at the
DNS/connect layer on this node (confirmed twice; honest fallback to the 6
development sources, matching the pre-registered contingency). Phase 1: a
4200-episode counterfactual action bank (7 corruption mechanisms + mixed +
clean control, x 8 actions = 33600 labeled records via the frozen
`compute_action_labels` path) passed parent/eval-frame/corpus isolation and
freeze-before-label hash re-verification (max fill drift 0.0). On the 648
missing_block-family episodes, TSICL_LONG scores 524 B&S / 120 harmful of
644 applicable (81.4%/18.6%), directionally consistent with the frozen
89-window 75/14 finding from v3.9 — the pilot bank looks usable as Phase 2
training material. Three implementation bugs were found and fixed while
running the pipeline (parent-window dedup, gated-out tsicl_long records
silently dropped before freeze, a tuple-unpack mismatch in the label-join
step); none touch the frozen labels, metrics or pre-registered gates. GPU
used only for the TS-ICL candidate stage (`w2-v39-impute` env, 251 MB peak,
14s); no processes left running afterward. Phase 2 (action-delta critic
training) has not started; awaiting review before proceeding.

2026-09-04 eleventh update, v4.0 COUNTERACT-TS closed at Phase 2 as a
diagnostic branch (red light; `docs/v4_0_counteract_preregistration.md`
§11.3–§11.5). The implementation was frozen in §11.3 (F1–F12) before any
Phase 2 computation. Phase 2.0's five hard checks pass; the feature cache is
bit-identical across two independent processes, GPU MOMENT embeddings
included; the frozen-89 labels were opened only after all 30 checkpoints
re-verified by sha256. On the bank's own held-out sources all five arms
reach harmful AUROC 0.865–0.902 with fewer than 1M parameters. On the frozen
89 the primary arm collapses: `full_COUNTERACT` retains 16 of 75
beneficial-and-safe windows (bar 55) at harmful AUROC 0.529, and the only
arm to clear the AUROC bar is `stat_only` (0.877) — thirteen
deployment-available structural scalars, 68k parameters — which still
retains just 14/75. The harm side is clean throughout (0–2 harmful commits
of 14), so this is an over-abstention and discrimination-transfer failure,
not a safety failure.

The cause is traced to a pre-registered design choice rather than to a bug:
the bank's `missing_block` severities span 5–50% of the window while the
frozen evaluation injector writes 5–12%, so bank gaps average 24.5% of T
against 8.9% on the frozen 89, TS-ICL's realised gain is ~3.6x larger in the
bank, and the q10 head's learned gain scale does not transfer — `q10 > delta`
abstains on 72 of the 89 windows, making the gain quantile, not the harm
probability, the binding constraint. Group-DRO did not beat ERM (held-out
AUROC 0.8993 vs 0.9021), so the Zhai et al. caution applies in the plain
direction: there was no worst-group gain to trade on. The single
pre-registered rescue was triggered on its stated condition and its
21,000-episode bank was built and verified (168,000 records, drift 0.0), but
the retrain had not run when the node was shut down; §11.5 records the exact
resume commands.

One provenance correction worth carrying forward: the Phase 0 finding that
public data was unreachable is specific to the `raw.githubusercontent.com`
mirror. `archive.ics.uci.edu` and `zenodo.org` both answer in under three
seconds from this node. UCI dataset 321 was left unfetched only because its
throughput measured ~40 KB/s, which puts a 260 MB archive at ~1.8 hours.

2026-09-04 twelfth update, v4.1 MASK-COUNTERACT closed at Phase 1 as a
diagnostic branch (red light; `docs/v4_1_mask_counteract_preregistration.md`
§11.1-§11.2). The round tested one hypothesis: that v4.0 failed because the
gain-quantile clause of the commit rule inherited a scale from a training
bank whose gaps average 24.5% of the window while deployment sees 8.9%, and
that keeping the harm ranking while re-calibrating on a gap-matched
population would recover the coverage. Phase 0 confirmed the shift
quantitatively and built the matched population: 1,043 in-band candidates
(gap_frac 5-12%) whose median gap 0.084 sits on top of the frozen frame's
0.090, with density-ratio ESS 958.

The hypothesis is half right and the half that fails is the informative one.
Removing the q10 veto while leaving everything else alone lifts retained
beneficial windows from 14 to 24 at CHR 0.040 -- the mechanism diagnosis was
correct. But re-calibrating on the gap-matched population makes it worse, not
better: 12 retained, and three of six folds return no calibrated point at
all. Those three folds hold 51 of the 75 beneficial windows. The reason is
measurable and is not threshold transfer: on the matched population the
stat-only harm model ranks at AUROC 0.659-0.708 against a harmful rate of
0.217, which puts the achievable CHR CP95 floor at 0.130-0.154, above the
pre-registered 0.15 bar for those folds by construction.

The 0.877 that motivated the round is not small-sample luck -- its bootstrap
CI95 is [0.7647, 0.9640], comfortably above the calibration population's
range. So the two populations differ in how separable TS-ICL's harm is even
after their gap geometry is matched. The lesson to carry forward: matching
the mask geometry of a calibration corpus to deployment is necessary but not
sufficient, because geometric similarity does not imply risk separability.
Playbook Tree 30 records it. Phase 2 not entered, no smoke350, no API, no
DOCX; incumbent remains PICS_joint_relabel.

2026-09-05 thirteenth update, v4.2 PORTFOLIO-ACT closed at Phase 0 as a
diagnostic branch (red light; `docs/v4_2_portfolio_act_preregistration.md`
§11.1). The round's premise was that the previous two failures came from
asking a single question -- accept this one TSICL_LONG candidate or not --
and that letting the agent choose among all applicable repair actions under
a risk budget would open the coverage that single-action gating could not.
Phase 0 tested that premise before training anything, and it does not hold
on the current candidate pool.

Two numbers carry the verdict. Only 6 of the 14 windows where TS-ICL is
harmful have any safe alternative among the nine frozen proposers, and the
portfolio's beneficial-and-safe union is 81 windows against TS-ICL's 75 --
six more, where the gate asked for ten. The oracle's own choices show why:
it picks TS-ICL 75 times and everything else 6 times between them. The nine
proposers are mechanistically homogeneous -- single-series interpolation or
foundation-model infill -- so they succeed and fail on the same windows, and
a portfolio over them is close to a portfolio of one. The eight windows that
no action can repair are exactly the eight harmful-TS-ICL windows without an
alternative, all `missing_block`, six of them in US Term Structure, a
40-channel coupled rate curve whose sibling channels no proposer reads.

Phase 0-A is worth carrying forward on its own. Replaying v4.1's arm B into
v3.9 D under the first-commit protocol, thresholds untouched, adds 24
beneficial-and-safe windows with zero conflicts and lifts beneficial
coverage from 0.2659 to 0.3205, over the 0.30 bar. It still fails the round's
budget gates: the gain sum rises only 3.2194 against a required 5.6319, and
harmful commits move from 15 to 16 when the target was 14 or fewer. The
protected-edit constraint is untouched by construction -- pme stays at the
baseline 0.0060 because adding long-gap actions cannot remove an edit that
already exists, which restates the frozen v3.9 finding that the protected
budget has no headroom.

The next round's work is candidate generation, not selection: a repair
mechanism that reads information outside the single series is the one
direction the current pool has never covered. Playbook Tree 31 records it.
No smoke350, no API, no GPU, no DOCX; incumbent remains PICS_joint_relabel.

Everything below was committed as of 2026-08-15. The transition this document
marks is from running experiments to writing the paper: the evidence for the
central claims was in hand, three experiments were still queued, and what was
missing was known and bounded.

## The claim, as the evidence now supports it

Acceptance of a data edit cannot rest on model utility alone, because utility
rises when data is flattened as well as when it is repaired. The contribution
is an execution time acceptance layer that requires a utility improvement and
structural preservation together and rolls back on failure, and that is
independent of the strategy proposing the edits.

Our own agent is one instance of proposer plus layer, not the subject of the
claim. That reordering is forced by the measurement in the next section.

## Established, with the number and where it lives

**The acceptance layer works on proposers that are not ours.**
`docs/gating_modularity.md`, `results/gating.json`. On a statistical rule,
damage falls from 0.0715 to 0.0016 and repair is retained at 70 percent. On an
unconditional cleaner, repair moves from -0.014 to +0.044, so a pipeline doing
net harm becomes net beneficial without one line of it changing, while damage
falls 97.0 percent. Of that cleaner's 1398 proposals, 725 were rejected on
structural distance against 452 on utility, so the structural term is the
principal gatekeeper.

**The gated statistical rule beats our own system on damage**, 0.0016 against
0.0020, at repair +0.255 against +0.181. This is why the claim is about the
layer rather than about our search.

**Protection holds across contamination rates.** `docs/protection_sweep.md`,
`results/sweep/sweep.json`. Damage on protected data is 0.085 to 0.129 for the
full method against 0.95 to 1.35 for unconditional cleaning, 0.35 to 0.78 for
a statistical rule and 0.25 to 0.31 for quality ranking, at every rate from 5
to 67 percent, with a flat curve while the baselines move by a factor of two.

**The behavioural signal measures predictability, not data quality.**
`docs/behavior_variable_identification.md`, `results/level_2x2.json`,
`results/ladder.json`. It decomposes into level positioning uncertainty at
+0.203 and local shape unpredictability at +0.141, roughly additive, isolated
by a 2x2 whose decisive pair holds local shape fixed at auc 0.716, p 1.4e-07.
Two competing explanations were tested and refuted: classical predictability,
since white noise scores below the real data anchor and AR(0.95) above
AR(0.30); and structural familiarity, since three of four deterministic
irregular forms score below the anchor.

**The false alarm on clean unpredictable data survives dropping half the
evidence.** `docs/ood_form_split.md`. Four generator forms are elevated
independently at auc 0.705 to 0.760. Dropping the two whose structure resembles
an injected defect leaves auc 0.715 at p 9.5e-13 over 105 windows.

**It replicates across four frozen backends.** `docs/cross_model_check.md`,
`results/cross_model.json`. Weakest at p 1.3e-04.

**Verification is the component that matters.** `docs/ablation_ladder.md`.
Removing it multiplies damage by 4.6 and doubles the edits for fifty percent
more repair. Peer calibration and abstention show no measurable effect and are
reported as such.

**The threshold can be calibrated with a guarantee.**
`docs/conformal_threshold.md`, `results/conformal_samepool_stage1.json`. Under
a same pool split the guarantee holds at every reachable target: three alphas
lie below a 0.0088 floor set by the action space and grid, five hold, and one
isolated violation at alpha 0.040 overshoots by 0.0025 with both neighbours
holding. Hand set thresholds realise 0.0200, 0.1025 and 0.1562 with no
guarantee attached to any of them.

**Downstream, defensively.** `docs/downstream.md`. Without the acceptance step
an aggressive pipeline degrades downstream MSE by two to eleven fold, patchtst
per seed -233, -1051 and -423 percent; with it, the same pipeline returns to
within a few percent of not curating. Three independently trained models agree
in direction.

**Two shield properties.** `docs/shield_properties.md`. Non blocking is proved:
KEEP has zero utility delta, zero structural distance and zero cost, so it is
admissible in every state. Minimal interference is partially satisfied at a
forgone rate of 0.263.

## Not established, or established negatively

**M4 predictability decorrelation is partial.**
`docs/predictability_decorrelation.md`. It raises corpus AUROC from 0.468 to
0.551, paired difference +0.083 CI [+0.060, +0.108], and removes the false
alarm on all four OOD forms, 0.705 to 0.760 down to 0.504 to 0.527. It costs
level_shift, flatline and duplicate detection, -0.119, -0.113 and -0.072. Both
directions are the same root cause: unpredictability from a displaced level and
from the structure itself are one quantity to this signal. Fully corrected it
still reaches only 0.551. Whether it enters the acceptance path is decided by
the queued integration test.

**Minimal interference is violated 26.3 percent of the time.** 304 of 1154
replayable vetoes would have improved the window. The utility condition
misfires on 29.7 percent of what it blocks and the structural condition on 19.7
percent, which is a fourth line of evidence that the model consulting condition
is the weaker one.

**No positive downstream gain from conservative curation.** Every effect for
stat_only, stat_only_gated and introact_full sits at or below its own model's
paired noise floor of 0.27 to 2.99 percent. The cause is mechanical:
introact_full edits 62 of 800 windows and leaves 92 percent of the corpus byte
identical. Dilution was ruled out, not assumed, by evaluating on the 515 edited
windows only.

**TSFM fine tuning skipped, by a pre committed criterion.** The criterion
required a paired noise floor under 3 percent and a decidable direction on the
affected subset. The first held, the second did not. A frozen TSFM is the
verifier in this method, not the object being curated, and that role division
is what the paper states.

**The profile misfire is not shown to generalise.** `docs/detector_crossval.md`.
Four of five standard detectors cannot separate contaminated from clean windows
on this corpus, contaminated lift 0.83 to 1.00, so they are not a valid control.
The fifth is silent on the stratum in question. Confirmed for our
implementation only.

**AegisTS cannot be run as published, and the authors confirmed it.** The
repository is missing the `Datasets` module that all four core modules import,
and `.gitignore` excludes it. **The authors were contacted and replied that the
data loading module cannot be located and cannot be supplied.** That exchange is
the basis for the reproducibility statement in the paper, which should record
both the request and the answer rather than only the absence.

A three day timeboxed faithful reproduction is now under way, reconstructing the
loader from the call sites. See `docs/aegists_reproduction.md` for the
acceptance criterion, the reconstruction evidence and the stop rule. It runs
outside the main queue and does not take priority over M2 or the soft against
hard comparison. The modularity claim does not depend on it, since two external
proposers already support it.

**M3 invariant specification not done.** Deferred. The structural distance
weights remain hand set, and that must appear in the limitations section as
stated rather than as a detail.

## Component three, settled

**Reading one.** The structural condition has measurable discriminative power on
the calibrated local operator path and none on the uncalibrated global path, and
the difference between them is significant. Three seeds, merged.

| path | n | odds ratio | accepted harm rate | rejected harm rate | vs blind |
|---|---|---|---|---|---|
| local | 2220 | **2.971** | **0.283** | 0.541 | p 1.0e-20 |
| global | 1283 | 0.954 | 0.560 | 0.548 | p 0.641 |

Interaction: log odds difference +1.136, CI [+0.711, +1.562], Wald p 1.6e-07,
Breslow Day p below 1e-16. The local baseline harm rate is 0.496, so the layer
takes the accepted side from 0.496 down to 0.283. On the global path the
accepted side is dirtier than the rejected side.

**Two tests are reported together and the disagreement is explained.** The
binomial test on veto precision gives p 0.0051 and 0.0030 for the two local
proposers at three seeds, and gave 0.092 and 0.054 at one seed. The association
test gives 1.0e-20. They differ because the binomial test reads only the
rejected side, which at an 84 percent rejection rate is forced towards the base
rate whatever the policy, while the association test reads both sides. The
rationale is in `docs/component3_verdict_criteria.md` and belongs in the paper
rather than being left for a reader to rediscover.

**Protected stratum recall is not significant** for any proposer, p 0.10 to
0.13. Safety on that stratum comes from rejecting a lot rather than from
rejecting selectively, and that is reported alongside the discriminative result
rather than instead of it.

**A withdrawn claim.** The earlier reading that the layer rejects a lot but not
accurately is wrong. Discriminative power is hidden on the rejected side by the
high rejection rate and is visible on the accepted side.

## Queued right now

Running under `setsid` on the box, so an SSH drop will not kill it. Sequence:

0. **global_path_fix**, running at shutdown time. Tests whether the whole
   series rewriters discriminate once they declare their actual changed point
   set as a footprint and travel the calibrated local path. The prediction is
   recorded in the script: the odds ratio should move from 0.954 towards 2.971
   if the uncalibrated path account is right, and if it does not move the
   account is wrong. Results land in `results/global_path_fix.json`.

1. **nested stability**, NOT started. Three hours did not fit before shutdown
   and it was removed from the queue rather than started and killed. The design
   is implemented and verified in `experiments/nested_stability.py`: nesting is
   exact, 10/10, 20/20, 40/40, 70/70 and 100/100 at each step, with the clean
   batch constant and the corpus size fixed. It replaces the first stability
   table, whose corpora shared only 22 to 43 percent of their windows and which
   therefore could not attribute a difference to the contamination rate.

2. **conformal rerun**, for `results/conformal_losses.npz` and to exercise the
   fixed sequence fallback. The stage 1 numbers already in hand are valid and
   are preserved at `results/conformal_samepool_stage1.json`; this rerun adds
   raw per window losses so any alpha or selection rule can be recomputed on
   CPU. Also produces the stability table across six contamination rates, which
   was interrupted twice and is currently missing.
2. **soft_vs_hard**, the highest value remaining experiment. It is the only
   controlled evidence for the mechanism difference against the closest
   competing design: a soft penalty sweep over mu against a hard veto sweep
   over tau, same proposer, same operators, plotted as a repair versus damage
   frontier. E3 depends on it.
3. **gating_m4**, the integration test. Criterion fixed before the run:
   protected edits must fall and repair must not drop more than 10 percent
   relative, otherwise M4 stays diagnostic.

Then, not yet queued: oracle upper bound and a random proposer, to complete the
main table.

## For the writing phase

**Method chapter, four modules.** M1 behavioural probe and what it measures,
evidence complete. M2 conformal acceptance threshold, evidence complete. M3
invariant specification, deferred, weights hand set. M4 predictability
decorrelation, diagnostic, integration pending.

**Experiments and what each carries.** E1 main table, the modularity claim,
needs oracle and random rows. E2 calibration curve, the guarantee. E3 soft
against hard, the architectural claim, queued. E4 decorrelation AUROC table,
done. E5 downstream, defensive only.

**Limitations to write, each with its number.** Structural weights hand set,
M3 deferred. Minimal interference forgone rate 0.263 and the utility condition
being the worse of the two at 29.7 percent. Behavioural risk is a within corpus
quantity, see `docs/scope_and_comparability.md`, and the same staircase scored
+0.535 in one corpus and -0.087 in another. No positive downstream gain at
under 9 percent change volume. The reachable risk floor of 0.0088. The profile
misfire not shown to generalise. Exchangeability required by the guarantee, with
the measured cost of violating it at 20 to 50 percent relative.

**Do not reintroduce.** Clean out of distribution data alarms the model more
than contamination, withdrawn, real cross domain windows score -0.017 against
contaminated at +0.090. Any ordering read off a median column without a
significance test. Instance normalisation as the mechanism behind the level
effect, tested and refuted. Pulse trains as the flattened windows, they were
edited 0 times of 52.

## Machine and environment

Box is `ssh -p 24509 root@connect.bjb2.seetacloud.com`. **The port changes when
the container is reassigned**, it has changed twice already, and the hostname
changing is the signal that running processes were lost. Work2 lives at
`/root/autodl-tmp/work2`, isolated from work1 by directory and conda
environment, interpreter at `/root/autodl-tmp/envs/w2`.

**2026-09-03 correction:** port is now `22499` (same hostname, container
reassigned again; no processes were lost this time -- checked before and
after the v4.0 Phase 0/1 run). The SSH helper has moved into the repo at
`tools/remote.py` (password-based `paramiko`, same connect/run/launch/tail/
get/put API); the `~/.w2tools/remote.py` copy below is stale.

The SSH helper is at `~/.w2tools/remote.py`, moved out of the shared temp
directory because a script named `inspect.py` belonging to the other project
sits there and shadows the standard library. Do not add the temp directory to
`sys.path`.

Long jobs must be started with `setsid` and a queue script, or they die with
the SSH session. Two runs were lost this way before that was fixed.

Disk was at 12 GB free and is now 405 GB. **That was never the reason foundation
model fine tuning was skipped and it is no longer a constraint at all.** The
reason is and remains the protocol: the method modifies 7.75 percent of the
corpus, and while the paired noise floor is under 3 percent the direction on the
affected subset is not decidable, so the downstream protocol cannot resolve a
difference on models far cheaper to train than a foundation model. If that step
is reconsidered, what has to be solved is the change volume, not the hardware.

This distinction matters under review. Asked why no foundation model was fine
tuned, the answer is a measurement limit, not a resource limit.


2026-09-14 18:49 最新冻结：40 passed in 1.01s，日志 `logs/v43/contracts/20260914T104900.858201Z/`。显存账本补记模型加载峰值，最终峰值取加载与推断最大值。旧队列因代码hash变化正确停止，已确认旧PID退出后重新启动；当前PID 58448，状态 `waiting_for_models`。完整机器可读证据见 `docs/v43_cpu_stage_evidence_20260914.json`，实时状态见 `results/v43/pilot_queue_status.json`。模型/方法结果仍未产生。


## 2026-09-14 持续监控

用户要求持续监控后，启动独立 tmux `work2-v43-monitor-20260914`（socket `/tmp/tmux-1000/default`），监控PID 59254。每30秒只读采集原安装、模型接续和pilot进程树的I/O、打开的wheel/incomplete文件大小、GPU、可用内存、磁盘和错误；不采集命令行，不安装、重启或终止任何进程。连续15分钟安装phase/I/O不变时记录告警。监控持续至pilot完成或24小时窗口结束。

最新快照 `results/v43/monitor_status.json`，完整采样 `/home/vipuser/work/work2/logs/v43/20260914T105516.706494Z-monitor/samples.jsonl`，监控入口 `scripts/launch_v43_monitor.sh`。`python3 scripts/bootstrap_status.py` 已纳入pilot与监控状态；PID不可见时提示先核对主机命名空间。报告写盘不等同于自动发送聊天通知。

18:55确认依赖下载仍推进：nvshmem 124.7MB已完成，开始nvjitlink 19.7MB；真实pilot仍未开始，模型manifest尚缺。


## 2026-09-14 原仓库同步

原仓库 `https://github.com/ForestBagpipes/TS_Dataflow.git` 已设为origin，当前 `codex/introactts-v43-bootstrap` 已连接远端初始master历史，合并前后工作树完全相同。阶段commit/push规则已写入AGENTS.md。首次实际push因缺GitHub写入认证失败；待认证后补推HEAD，详情 `docs/git_sync.md`。这只阻断上传，不阻断本机安装/模型/pilot/监控。


## 2026-09-14 下载链路实测

同版8 MiB样本：NVIDIA官方cuDNN直连2.944 / 代理0.191 MiB/s，清华同包直连2.916 / 代理0.256 MiB/s，交大Torch直连0.733 / 代理0.326 MiB/s。新增只读探测脚本及后续下载进程专用的按域名直连配置；原安装仍用原线路，未重启或并发改写环境。完整限制、403探测失败与原始证据见 docs/download_routes_20260914.md。真实pilot仍未运行；本地提交待GitHub认证恢复后补推。


## 2026-09-14 20:00 用户授权下载切线

work2已实际切到任务专用直连分段下载，保留约932MB已有数据。旧安装PID45580/61386退出，新bootstrap PID66506、下载PID66519；模型接续和pilot队列已恢复，监控PID59254保持。代理服务与Codex配置未改，端口切换前后可达。首次切线父进程已退出异常与分段重试全部留痕，详见 docs/download_switch_20260914.md 及机器证据；不能重启旧安装或同时改写prefix。真实pilot仍待验收。


## 2026-09-14 20:15 环境验收完成

三个独立环境全部完成安装、依赖检查和指定模块导入；TS-ICL与Chronos的CUDA256×256矩阵检查通过，RTX4090支持BF16，单次小测试峰值分配9,502,720字节。TS-ICL为Python3.12/NumPy2.5.3，core与Chronos为Python3.11/NumPy1.26.4，两GPU环境保持Torch2.9.1+cu126。25个恢复wheel整包官方哈希校验通过，环境freeze/conda-explicit与SHA256SUMS已落盘并逐项复核。

安装20:14:48结束，模型接续20:15:27开始；TS-ICL官方revision已锁为19c94031439fb31f36ce395088ee50a6762d3774，权重下载中。Bolt尚未下载，真实32-origin pilot仍未运行。此处是环境验收，不是模型worker或方法成功。证据见 docs/environment_acceptance_20260914.json；冻结记录见 requirements/bootstrap-20260914/。待两个模型接口验收通过后，队列重验CPU gate并运行真实pilot，calibration/test读取仍关闭。


## 2026-09-14 20:53 首轮真实pilot失败与入口修复

首个真实pilot于20:49启动，run results/v43/20260914T124856.762289Z-pilot；CPU gate40项通过后，TS-ICL worker在模块导入时因缺statsmodels失败，尚未执行预测或读取future标签。原因是introact_ts顶层入口提前加载旧Agent/profile依赖，而TS-ICL环境按官方依赖保持隔离。没有向TS-ICL环境补装core栈。

已将旧重依赖导出改为按需加载，保留原公共API，并将顶层__init__/types/verify三项必要入口依赖纳入worker代码hash。43项CPU测试通过（1.29秒），4项旧API判据回归通过，两个worker在各自冻结解释器的--help入口均通过。完整失败日志、测试和代码hash见 docs/worker_import_fix_20260914.json。新真实pilot仍须实际执行后验收，不把此修复记为方法成功。

Bolt镜像于20:46:09整包官方SHA256通过，20:46:52在旧传输进程退出和HF文件锁保护下接入同一官方revision缓存；保存旧335,236,791字节未完成文件。原验收器确认Bolt GPU接口通过，TS-ICL也通过。可选Chronos-2元数据TLS失败及一次独立重试失败保留，不阻塞只要求TS-ICL/Bolt的pilot。权重完整镜像耗时与HF缓存命中耗时分别保存，不能混算。


## 2026-09-14 P2 首批开发配置冻结（未运行结果）

P1 已完成且独立复核通过后，新增 `configs/v43/p2_first_dev.yaml`、`cli p2` 与 A4/A5 正式接线。只取 ETTm1 / Solar / USTS 的 dev 原始区间，分别 14 / 11 / 1 个不重叠基础 parent；两个 horizon 96/192 及 raw、target block 10%、全部 siblings shared block 10% 共 156 个 episode。这些变体不是 156 个独立样本；全历史 ridge 读取区间在 dev 内重叠，正式推断还须按更大依赖块处理。

Solar 复用本机文件，与论文作者仓库 Git blob 完全一致。只按原行号保留同步时间；来源说明为 2006 年 Alabama 137 路 10 分钟光伏，压缩文本无原始时间戳，不能伪称已恢复绝对日历或发布延迟。库存只统计行宽，不解码 heldout 数值。来源证据见 `docs/v43_p2_source_provenance_20260914.json`。

首批重点检验长缺口的新信息收益，以及原始/共享缺失的保护与负对照；5%/点缺失/spike/valid-event 标注和其他来源为后续矩阵，不能把首批当完整污染实验。固定通道0、seed101、L512、缺口[230,281)、不按标签挑窗口。只要求 TS-ICL/Bolt 两个已通过模型，保持 batch1/GPU单任务。

执行臂为 A0 native/ffill、A2 single、A3 官方全合法covariates、A4当前context及同split全合法历史ridge、A5严格嵌套OOF静态eta。A4历史只读 dev 起点到当前context起点，再拼当前dirty输入，不重新打开当前gap真值；这是额外历史信息轨道。A5保存七类真实遮挡输入，支持不足明确回到同origin已验证A2，真实worker缺行/失败仍报错；eta平局取0。候选去重只在同episode、同horizon、完整输入hash下进行并保存alias，所有候选完成真实预测后才读future。

A1仍为blocked_adapter：`experiments/v39_phase0_replay.py:321` 强依赖771个冻结parents，`:450`按历史候选标签拟合LODO PICS并重放；源码存在不等于可对本次新时间区间部署。该参照待合法适配，不把旧分数贴到新UID，也不把缺失参照填0。原生多变量任务模型尚未运行。A9只对本轮完整已执行候选集生成开发上界，名称明确为A9_ORACLE_AVAILABLE，不冒充全候选上界。

新增测试覆盖gzip越界标签不可解码、父区间共享、shared辅助遮挡、全历史不重读gap、A5不适用回A2、漏真实预测报错、ridge观测值不变及eta平局0。运行以新配置绑定的CPU gate为前提，结果产出前不作方法成功结论。PICS_joint_relabel不变，不将规划写入DOCX成果。
