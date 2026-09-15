# Version ledger

One row per method version. A version enters this table only after both of the
following: the number was read out of the code that produces it, and an
independent script recomputed it from the raw traces and agreed. When the two
disagree, both are recorded and the row stays out until the disagreement is
resolved.

## The locked measurement conventions

Fixed 2026-08-27. Every row below uses these and nothing else, otherwise
versions cannot be compared.

| column | definition |
|---|---|
| damage rate | harmful commits over committed edits, harm = `max(worse_binary, discard_share)` (continuous loss that accounts for discarded data). The `v1-old` row below records the previous `audit._nmse`/Definition 1 metric and is kept only as an obsolete reference. |
| protected mis edit rate | edited windows in `clean`, `hard`, `rare_valid` and `changepoint`, over the size of those four strata. The synthetic probe layer `clean_ood` is excluded and reported separately |
| **nRMSD** | **window count weighted mean over the five sound contamination kinds only**, that is `duplicate`, `flatline`, `level_shift`, `noise`, `spike` |
| edits | committed edits over windows carrying a clean reference |

**Why the two missing kinds are excluded from nRMSD.** The distance drops non
finite differences, so a window with a hole sits at distance zero from the truth
and an arm that fills nothing scores perfectly on it. `missing_block` and
`missing_scattered` are 212 of 740 injected windows, 28.6 percent, and including
them rewards inaction on that share of the denominator. The full derivation and
the per kind table are in `docs/number_selfchecks.md` under the repair nRMSD
ruling.

**Consequence for older numbers.** The ablation table reports 1.0764 for
`f_full`. That is the plain mean over all seven kinds and is not this ledger's
convention. The same arm under this convention is 1.5080. Both are correct
readings of different quantities; only the second is comparable across versions
here.

## Versions

| version | damage rate | protected mis edit rate | nRMSD | edits | note |
|---|---|---|---|---|---|
| v1-old (obsolete) | 0.1306 +- 0.0084 | 0.0635 +- 0.0054 | 1.5080 | 161 +- 9 | old `audit._nmse`/Definition 1 metric; Phase 0 showed it underestimates crop damage; kept only as reference |
| v1-new | [0.6819, 0.6921] | 0.0635 +- 0.0054 | 1.5080 | 161 +- 9 | same commit `7e16b8c`, recomputed with `max(worse_binary, discard_share)`, source `results/damage_recount.json` |
| v2-smoke350 (diagnostic) | 0.8000 [0.3755, 0.9638] | 0.0055 | — | 5 | one seed, 350 windows, injected coverage 0.0154; safety line not judgeable due to only 5 edits; source `results/smoke_v2.json`, `logs/smoke350.log` |

### v1 provenance

Three seeds at xl on the mixed corpus, method layer code hash
`1f6d57bb1a15e4a0`, aggregated by `experiments/aggregate_ablations.py`. Damage
rate and mis edit rate were reconciled against the flushed traces by that
script, 12 of 12 combinations agreeing exactly. The nRMSD figure comes from
`experiments/aggregate_soft.py`'s sound kind reader over the same traces.

### What v1 is known to be wrong about, carried forward as the reason for v2

Phase 0, recorded in `docs/diagnostic-playbook.md`:

  the structural condition never judged RESEGMENT, distortion was identically
  zero on all 2766 attempts, because the alignment step discarded exactly the
  region the operator affects. 180 of v1's commits are protected layer crops
  that discarded a median 40 percent of the window at a reported distortion of
  zero and a mean fidelity gain of zero or below

  DENOISE was accepted zero times in 416 attempts, its median distortion 0.2085
  being ten times the global threshold, so one operator of four contributed
  nothing but consumed probe budget

**So v1's mis edit rate is inflated by a broken measurement and its edit count
contains repairs that repaired nothing.** A v2 that lowers both is correcting an
error rather than trading one metric for another, and the ledger's rule for v2
is stated before it runs: damage rate and protected mis edit rate must both
fall. A rise in nRMSD is admissible only with the injected layer's own repair
accuracy reported beside it, since removing false accepts removes their
contribution to the average as well.

### Diagnostic records (not formal versions)

| item | value | source | note |
|---|---|---|---|
| trajectory probe run1 (obsolete) | combined AUROC 0.7028, amber | local `results/trajectory_probe/probe_run1_mlp_stale.json` | three-layer MLP, random five-fold CV; did not match registered design; replaced by run2 |
| trajectory probe run2 (formal) | combined AUROC 0.5794, **red** | `results/trajectory_probe/probe.json` | PatchTST proxy learner, CV grouped by source dataset; fails the 0.65 continuation threshold; training-dynamics triage stopped |
| per-family λ | DENOISE 0.10, DESPIKE 0.00, IMPUTE 0.02, RESEGMENT 0.40 | `results/conformal_family.json` | calibrated on routed candidates from seed-101 mixed corpus |
| v2.1 routing replay (diagnostic) | current coverage UB 0.4849; primary_only 0.2601; missing_primary 0.4849; ratio_gate 0.2601 | `results/counterfactual_routing.json` | DESPIKE λ=0 so suppressing it cannot raise coverage; primary_only/ratio_gate lose coverage; routing-only path to v2.1 fails |
| v2.1 level-shift full-window probe (diagnostic) | on-target mean loss 0.011 (98.9% ≤0.03), mean rmsd 4.47 vs KEEP 5.47; off-target protected mean loss 1.00 | `results/level_shift_probe.json` | full-window stress test, not the routed-and-accepted population; **loss numbers are artefacts of centered `audit._nmse` and are not comparable to the uncentered loss used by the deployment shield**; see P0-B below |
| v2 veto attribution (Phase A) | calibration coverage UB 0.4849 → smoke350 coverage 0.0154, gap 0.4695; RESEGMENT NO_OP 66% of contaminated candidates, IMPUTE 45% utility/44% structure veto, DESPIKE λ=0 structural veto 94% | `results/v2_veto_attribution.json` | explains the coverage collapse without rerunning smoke350; the binding conditions are operator NO_OP and family thresholds, not routing alone |
| v2.1 route-conditioned shift replay (Phase B) | `slope_preserving` coverage 16.4%, mis-edit 51.9%; `robust_offset_local` coverage 9.0%, mis-edit 56.2%; `resegment_crop_aggressive` coverage 6.0%, mis-edit 20.0%, repair RMSD 4.49 vs KEEP 5.50 | `results/route_conditioned_shift.json` | evaluated only on windows routed to RESEGMENT; no variant clears the pre-registered safety/coverage gate |
| v2.1 candidate-level TSFM counterfactual pilot (Phase C) | n=50, 48 unique windows; all 50 applicable; signals computed but no reliable AUROC; existing shield signals (struct_distortion/delta_utility) still dominate directionally | `results/tsfm_counterfactual_pilot.json` | 50-sample implementation check; TSFM signals computed; sample too small and source-stratified folds degenerate; full-pool expansion not warranted on this pilot alone |
| v2.1 decision | **not formed** | — | Phase B failed the safety/coverage gate; Phase C produced 50 valid records but the sample is too small for a non-degenerate grouped AUROC and no TSFM signal clearly beats the existing shield signals; no recalibration or smoke350 run |
| **P0-A corpus determinism** | — | `results/p0_corpus_determinism_report.json` | two independent process builds of seed-101 mixed corpus produce identical 1599 sample_uids; `build_calibration.py` mutates `SCALES[scale].seed` but does not break cross-process determinism |
| **P0-B operator-path audit** | — | `results/p0_operator_path_audit.json` | on 67 level-shift windows, `level_shift_operator_probe` and `route_conditioned_shift` produce identical operator outputs and identical repair RMSD, but **different before/after NMSE and loss** because the two scripts use different `_nmse` definitions; **resolved 2026-09-02** by `experiments/metrics_common.py`, see the P0-B resolved row |
| **P0-C result manifest audit** | — | `results/p0_result_manifest_audit.json` | all window-level records in `family_scores.jsonl`, `level_shift_probe.json`, `route_conditioned_shift.json`, `misroute_evidence.json` are metadata-verifiable against `results/p0_corpus_manifest_a.json`; pre-P0 files lack hashes and are hash-unverifiable; `resegment_noop.json` was run on a 350-window smoke slice (`slice_seed=202`) and is not comparable to the 1599-window calibration corpus |
| **P0-B resolved** | 67/67 windows identical on both paths | `results/p0_operator_path_audit_fixed.json` | `experiments/metrics_common.py` fixes the canonical uncentered finite-mask NMSE; both level-shift scripts now import it; operator output hash, offset, breakpoint, before/after NMSE and loss agree on all 67 windows; independent aggregation matches the summary |
| action-family oracle headroom | DENOISE 0.933, DESPIKE 0.811, IMPUTE 0.164, RESEGMENT 0.000 contaminated beneficial-and-safe rate | `results/oracle_headroom.jsonl` | 2414 candidates on the frozen corpus, labels under the canonical NMSE; RESEGMENT has zero safe headroom (all candidates discard > 0.03), an operator-level problem; zero protected candidates are beneficial-and-safe |
| v3.1-pre exact replay check | all six arm metrics reproduce to <1e-9 | `results/v31_replay_check.json` vs `results/v3_arms_compare.json` | the recorded v3.1-pre numbers are reproducible from the old table and the current code path; they remain implementation-invalid as method evidence (§0.1 of the v3.2 pre-registration) |
| v3.2 candidate rebuild (Phase 2) | 2414 candidates, 827 windows, labels/operator outputs identical to the v3 table on all 2414 shared keys | `results/v32_training_data.jsonl`, `results/v32_feature_sanity.json` | repaired features verified: `touched_fraction` now 103 distinct values in [0.002, 1], `seam_error` 834 distinct scale-normalised values, the three verification features carry real values; `outside_support_drift` is constant 0 because every mask-declaring operator in this pool is honest outside its support — a degenerate-but-correct feature |
| v3.2 PICS arms (Phase 3, diagnostic) | PICS_joint: commit 0.092, damage 0.0220, cond damage 0.239 (CI [0.145, 0.346]), pme 0.0030, bcov 0.1227, gain 0.0864, OOD edit 0.321 | `results/v32_arms_compare.json`, `results/v32_harmful_commits.json` | gates FAIL on beneficial coverage (0.1227 < 0.1455) and OOD edit (0.321 ≫ 0.05); pme, damage, gain, conditional damage and all fairness gates pass; bugfix-only arm reaches bcov 0.207 but pme 0.0181 and OOD edit 0.732; v2_frozen OOD edit is 0.036; residual PICS harm is 17 commits, 13 IMPUTE on missing windows where the finite-mask NMSE cannot see the pre-repair defect (before=0); **no smoke350 requested** |
| v3-pre arms comparison (Phase 4) | see `docs/v3_contextual_conformal_shield.md` | `results/v3_arms_compare.json` | five arms, leave-one-dataset-out, first-commit episode rule; joint_v3_pre fails the protected mis-edit, damage and statistical-increment gates; the single allowed v3.1-pre (dual beneficial-and-safe + harmful gate) improves all safety metrics significantly and still fails; **STOP_CANDIDATE, no smoke350 run**; full record in `docs/v3_contextual_conformal_shield.md`. **2026-09-02 downgrade: implementation-invalid/inconclusive** — the feature extractor had a constant `touched_fraction`, a broken `seam_error` (mask values used as indices), a pseudo `outside_support_drift`, and three constant-zero features (`improvement_consistency/depth`, `action_risk`), and its calibration counted per-candidate risk while deployment commits first-per-window; the numbers stand as a record of that code, not as method evidence; see `docs/v3_2_pics_preregistration.md` §0.1 |
| **v3.3 MAST-PICS (2026-09-03, diagnostic branch, gates FAIL)** | formal arm: commit 0.132, damage 0.0402, CHR 0.304 (CI [0.214, 0.398]), pme 0.0242, bcov 0.1614, OOD edit 0.000 | `results/v33_arms_compare.json`, `results/v33_harmful_commits.json`, `results/v33_label_flip_audit.json` | the IMPUTE label repair is confirmed (395 harmful->beneficial_and_safe flips, oracle IMPUTE b&s 0.164->0.640, 8 of 13 old harms were label artefacts) and is kept; the asymmetric fusion is refuted -- PICS_joint_relabel Pareto-dominates the MAST frontier (bcov 0.2727 vs 0.1614 at equal damage, paired bootstrap CI [-0.086, -0.042]); harm caps saturated at the 0.95 grid edge because corpus-level corrected risk does not control conditional harm; ETTh2 is the dominant failure fold (17/31 harmful commits); the OOD certificate scores 0/64 synthetic and 0/32 real edits on the frozen seed-313 set but is carried entirely by the structural consequence term (unstable=1.00 for all OOD candidates), so the support index is unproven; **no second tuning round, no smoke350**; full record in `docs/v3_3_mast_pics_design.md` post-hoc section |
| **v3.4 SCRC-PICS (2026-09-03, diagnostic branch, not formed)** | Phase 1: no feasible threshold at CHR≤0.10 on any calibration fold; oracle grid ceiling bcov 0.0614 (global) / 0.0932 (per-family) under CHR≤0.10 → **score ranking insufficient**. Phase 2: shadow certificate 3/4 signal gates FAIL (AUROC 0.351 vs ≥0.75; AUPRC +0.008 vs ≥+0.05; harmful recall 7.4% vs ≥70%; trial coverage 99.7% PASS) | `results/v34_conditional_risk_frontier.json`, `results/v34_shadow_certificate.json`, `results/v34_shadow_records.jsonl`, `results/v33_clean_rerun*.json` | pre-registered in `docs/v3_4_scrc_pics_preregistration.md`; Phase 0 clean rerun reproduced the v3.3 baseline exactly (all numbers <1e-9 diff, OOD stratum classification correct); both v3.4 components fail because the current deployable scores do not order candidates by true conditional risk; Phase 3 not run per preregistration; no smoke350, no API; incumbent remains **PICS_joint_relabel** |
| **v3.5 ACV (2026-09-03, diagnostic branch, RED LIGHT, not formed)** | Phase 1 ACV probe: all four signal gates FAIL on the pre-registered primary (prequential-only): harmful AUROC 0.623 (<0.75), AUPRC lift +0.008 (<+0.05), harmful recall 25.8% at 10% false-reject (<70%), LODO new-coverage 0, evidence coverage 57.6% (<90%); support-only ablation AUROC 0.708/AUPRC lift +0.210 (stronger but still below the AUROC bar, and the primary cannot be switched post-hoc). Phase 2 TSFM_RECONSTRUCT_IMPUTE: not_green — harmful rate 0.539→0.289 (−46.5% PASS) but b&s rate 0.460→0.172 (FAIL), oracle coverage +0.020 <0.03 (FAIL), 3/6 sources improve | `results/v35_acv_records.jsonl`, `results/v35_acv_probe.json`, `results/v35_tsfm_impute_records.jsonl`, `results/v35_tsfm_impute_probe.json`, `results/v35_acv_support_audit.json` | pre-registered in `docs/v3_5_acv_preregistration.md`; Phase 0 audit: 2414/2414 operator outputs bit-identical, anchor coverage 76.3% ≥1 (DENOISE structurally excluded, RESEGMENT tail-crop); per the execution order both red → Phase 3 not run, no smoke350, no API; incumbent remains **PICS_joint_relabel** |
| **v3.6 PAIR (2026-09-03, diagnostic branch, RED LIGHT, not formed)** | Phase 0 integrity 9/9 PASS (827 episodes, 5402 symmetric pairs). Phase 1 decision arm PAIR_episode_relative/HGB: pooled pairwise accuracy 0.6454 (<0.70), 4/6 sources >=0.60, deployment bcov 0.0909 / CHR 0.412 / gain 0.0074 / damage 0.0363 / pme 0.0514 vs PICS 0.2727/0.2053/0.0919/0.0402/0.0091 -> frontier not better than PICS or pointwise -> **red light** | `results/v36_pair_dataset.jsonl`, `results/v36_pair_integrity.json`, `results/v36_pair_probe.json`, `results/v36_pair_predictions.jsonl` | pre-registered in `docs/v3_6_pair_preregistration.md`; attribution traced to cross-source generalisation (ETT folds near-random held-out, all 68 commits and all 28 harmful commits land in ETT folds; Oil/Crypto/USTS AUROC 0.92-0.99 but zero commits pass the margin gate there); Phase 2/3 not run per the stop rule; no smoke350, no API, no DOCX; incumbent remains **PICS_joint_relabel** |
| **v3.7 SHIFT (2026-09-03, diagnostic branch, RED LIGHT at Phase 0, not formed)** | frozen-score reproduction bit-exact (max_abs_diff 0.0); target-label oracles under CHR<=0.10/pme<=0.0055/damage<=0.0402: global threshold oracle bcov 0.041/gain 0.022, expert-mixture oracle bcov 0.180/gain 0.023, both below the bcov>=0.30+gain>=0.10 bar -> **red light, Phase 1 never started** | `results/v37_shift_headroom.json`, `results/v37_calibration_transfer.json` | pre-registered in `docs/v3_7_shift_preregistration.md`; the binding ceiling of THAT route is coverage/gain magnitude, not safety (both oracles easily meet CHR/pme/damage); transfer matrix: ranking transfers (B&S AUROC >0.72 for most pairs) but thresholds do not (cross-source CHR up to 0.67 into ETTh2); 'similar sources calibrate better' refuted (r=-0.054); no smoke350, no API, no DOCX; incumbent remains **PICS_joint_relabel**. **2026-09-03 correction (v3.8 Phase 0 replay, `results/v38_oracle_replay.json`): the 0.041/0.180 numbers are the ceiling of the frozen-PAIR-ranking + grid-threshold route only, NOT of the candidate pool — the unrestricted candidate oracle replays bit-exactly at bcov 0.6591 / gain 0.1969 / CHR 0 (290 commits). Corrected statement: 冻结 PAIR 排序/校准路线被排除；尚未排除重新定义候选语义和构造可识别高精度候选。** |
| **v3.8 FACT-IntroAct (2026-09-03, diagnostic branch, RED LIGHT at Phase 1, not formed)** | Phase 0: all three oracle replays bit-exact (v3.7 correction delivered — unrestricted candidate oracle bcov 0.6591 / gain 0.1969 / CHR 0 vs frozen-PAIR-route ceiling 0.041/0.180); mask audit of 1,154 IMPUTE candidates: actual_nan_only 447 (b&s 0.812 / harmful 0.188), finite_flatline_only 623 (b&s 0.218 / harmful 0.782), mixed 84; v3.6-arm harmful IMPUTE 16/23 in flatline layer vs PICS harmful IMPUTE 19/27 in actual_nan_only layer — the two routes fail with different semantics. Phase 1: IMPUTE_EXPLICIT_LINEAR + frozen gap certificates (4/8/16): drift exactly 0, harmful 0.068 on actual-NaN windows, but b&s 0.429 (gate 0.80) and 0/6 source non-inferiority — all 25–63-length missing_block gaps abstain over the wide tier; FACT-pool oracle passes (bcov 0.3705 / gain 0.1760 / CHR 0) yet the frozen Phase 2B coverage-potential rule (wide b&s>=0.60) fails at 0.429 -> **operator retired, Phase 2A/2B not entered** | `results/v38_oracle_replay.json`, `results/v38_impute_mask_audit.json`, `results/v38_impute_mask_records.jsonl`, `results/v38_phase0_manifest.json`, `results/v38_explicit_impute_probe.json`, `results/v38_explicit_impute_records.jsonl` | pre-registered in `docs/v3_8_fact_preregistration.md` (post-hoc §11.1/§11.2 appended); failure is coverage, not precision (scattered windows it fills: b&s 0.864); tier widening after seeing results is pre-registration-barred; 11/11 operator tests passed, two-process determinism sha256 equal; no smoke350, no API, no DOCX; incumbent remains **PICS_joint_relabel**. **2026-09-03 metric-semantics correction (v3.9 §1): g1=76/177=0.429 is window-level beneficial COVERAGE, not action-conditional precision; over the 88 scattered windows actually filled, 76 B&S / 12 harmful give action-conditional B&S precision 0.864 and CHR 0.136, while all 89 missing_block windows (gap 25-63) abstained. Correct reading: 短缺口算子保留，长缺口适用性失败 — the FACT semantic split itself is NOT refuted. From v3.9 onward applicability coverage, action-conditional B&S precision, action-conditional CHR, bcov and abstention rate are reported separately.** |
| **v3.9 MIRAGE-TS (2026-09-03, diagnostic branch, RED LIGHT at Phase 2, not formed)** | Phase 0: six-arm replay all gates pass; budget baseline D (FACT_SHORT-first + PICS_non_IMPUTE) bcov 0.2659 / gain 0.0872 / act-cond CHR 0.1136; budget: +15 B&S windows and +5.632 gain-sum needed, CHR/pme need harm reduction not additions. Phase 1: 4/4 headroom gates pass — official OpenFIM (MIT) + TS-ICL (non-commercial) fetched; TS-ICL strongest long-gap proposer (75 B&S / 14 harmful of 89, tm-NRMSE 0.288), OpenFIM unusable alone (CHR 0.629, negative gain); joint oracle bcov 0.5545 / gain 0.195 / CHR 0. Phase 2: signal gates 2/6 — deployable signals predict OpenFIM harm (AUROC up to 0.757) but NOT TS-ICL harm (R AUROC 0.461, width reversed 0.325); all six LODO folds no_calibrated_point at CHR CP95<=0.15; eta shrinkage does not cut TS-ICL harm (75/14 at eta 0.5 and 1.0); single pre-registered isotonic+DRO rescue branch still fails (CHR 0.200) -> **stop_signal_quality_insufficient, Phase 3 not entered** | `results/v39_phase0_replay.json`, `results/v39_phase0_records.jsonl`, `results/v39_target_budget.json`, `results/v39_longgap_candidates.jsonl` (801 records), `results/v39_longgap_probe.json`, `results/v39_longgap_oracle.json`, `results/v39_model_manifest.json`, `results/v39_bridge_candidates.jsonl`, `results/v39_bridge_signals.jsonl`, `results/v39_bridge_probe.json`, `experiments/v39_phase0_replay.py`, `experiments/v39_longgap_probe.py`, `experiments/v39_bridge_probe.py` | pre-registered in `docs/v3_9_mirage_preregistration.md` (post-hoc §11.1-§11.5); one documented code fix (openfim dtype bug, probe.py hash -> 2ba76450fd8488c0, 13/13 tests); failure is per-window risk-evidence quality on the STRONG proposer, not candidate-pool value — playbook Tree 28; no smoke350, no API, no DOCX; incumbent remains **PICS_joint_relabel** |

| **v4.2 PORTFOLIO-ACT (2026-09-05, diagnostic branch, RED LIGHT at Phase 0, not formed)** | The round changed the degree of freedom -- from accepting or rejecting one TSICL_LONG candidate to picking among all applicable repair actions under a risk budget -- and Phase 0 stopped it on headroom before any selector was trained. Phase 0-A replayed v4.1 arm B into v3.9 D under the first-commit protocol with thresholds untouched: the baseline reads back from code as 132 commits / 117 B&S / 15 harmful / bcov 0.2659 / gain 0.0872 / CHR 0.1136 / pme 0.0060 / damage 0.0195, and the integration reaches 157 / **141** / 16 / bcov **0.3205** / gain 0.0945 / CHR 0.1019 / CP95 0.1507 / pme 0.0060 / damage 0.0208 with zero first-commit conflicts -- +24 B&S and bcov over the 0.30 bar, but gain-sum only +3.2194 against a required +5.6319, and harmful moving the wrong way (15 -> 16 against a <=14 target). Phase 0-B then measured the portfolio's actual headroom over the nine frozen long-gap proposers and returned 1 of 4 continuation gates: 81/89 windows carry at least one beneficial-and-safe action (bar 80, pass), but only **6 of 14** harmful TS-ICL windows have a safe alternative (bar 10), the portfolio recovers only **+6** beneficial windows over the best fixed proposer (81 vs TS-ICL's 75, bar +10), and the integrated oracle fails on pme alone at 0.0060 against 0.0055 -- a value identical to the v3.9 D baseline, because adding long-gap actions cannot remove an existing protected edit | `docs/v4_2_portfolio_act_preregistration.md` (§11.1 post-hoc), `results/v42_phase0a_integration.json`, `results/v42_phase0b_portfolio_oracle.json`, `experiments/v42_portfolio_act.py` | pre-registered before any v4.2 computation, with v4.1's two unreachable gates explicitly retired (a module-level 55/75 bar that did not match the integration target, and a strict-Pareto conjunction against two references that sit on opposite sides of every risk-controlled point) and replaced by incremental budget gates written before the run; the eight windows with no safe action are exactly the eight harmful-TS-ICL windows lacking an alternative, all `missing_block`, six of them in US Term Structure, so the binding limit is the candidate pool rather than the selector -- the nine proposers are mechanistically homogeneous (single-series interpolation or foundation-model infill) and succeed on the same windows; one measurement limitation is recorded, that the integrated-oracle row describes a TS-ICL-only oracle because `v40_phase3_pool.jsonl` pools gains for TSICL_LONG only and the six non-TS-ICL oracle picks were skipped for lack of a gain record; Phase 1 not entered per the stop rule, no smoke350, no API, no GPU, no DOCX; incumbent remains **PICS_joint_relabel** |

| **v4.1 MASK-COUNTERACT (2026-09-04, diagnostic branch, RED LIGHT at Phase 1, not formed)** | Phase 0 passes: frozen-89 labels replay 75/14, stat-only AUROC replays to 0.8771 bit-for-bit, and the headroom point (57 commits = 55 B&S + 2 harmful, CHR 0.0351) reproduces. The mask-shift audit confirms the v4.0 diagnosis quantitatively -- bank gap_frac median 0.221 against 0.090 on the frozen frame, and a 5-12% in-band subset (1,043 rows, ESS 958) that matches deployment geometry (0.084 vs 0.090). Phase 1 then fails 3/8 gates: dropping the q10 veto alone lifts retained B&S from 14 to 24 at CHR 0.040 (arm B), but mask-restricted and density-weighted recalibration make it *worse* (12 B&S), because three of six folds return no_calibrated_point and those folds hold 51 of the 75 B&S. Binding constraint located: on the deployment-matched calibration population the stat-only harm model ranks at AUROC 0.659-0.708 with harmful rate 0.217, so the achievable CHR CP95 floor is 0.130-0.154 and the pre-registered <=0.15 constraint is structurally unsatisfiable in ETTm1 / US Term Structure / Oil Price. The 0.877 seen on the frozen 89 is not small-sample luck (bootstrap CI95 [0.7647, 0.9640]) -- the two populations genuinely differ in harm separability despite matched gap geometry. Paired bootstrap: primary arm vs v4.0 stat-only mean -0.034, CI [-0.146, 0.079], p=0.26 | `docs/v4_1_mask_counteract_preregistration.md` (§11.1-§11.2 post-hoc), `results/v41_integrity.json`, `results/v41_mask_shift_audit.json`, `results/v41_selector_arms.json`, `results/v41_selector_rows.jsonl`, `results/v41_calibration.npz`, `results/v41_calibration_rows.jsonl`, `experiments/v41_mask_counteract.py` | pre-registered before any v4.1 computation; thresholds selected only on each fold's training sources, frozen-89 labels never used for calibration; the pre-registered branch whose condition actually matched (ranking high on the decision set, thresholds failing across sources) had its remedy -- density-weighted calibration -- executed as the primary arm and it returned thresholds identical to the unweighted variant; the retrain branch's precondition (insufficient samples) is false at 853-888 rows per fold, so it was not invoked; Phase 2 not entered, no smoke350, no API, no DOCX; GPU untouched (Phase 0/1 are CPU-only) while four other-user jobs held 18.3 GB; incumbent remains **PICS_joint_relabel** |

| **v4.0 COUNTERACT-TS (2026-09-04, diagnostic branch, RED LIGHT at Phase 2, not formed)** | Phase 2 decision gate on the frozen 89 TS-ICL long-gap windows **fails**: primary arm `full_COUNTERACT` retains only 16 of 75 B&S (bar 55) with harmful AUROC 0.529 (bar 0.75); `stat_only` — 13 deployment-available structural scalars, 68k params — is the only arm to clear the AUROC bar at 0.877 but retains just 14/75. Harm side is clean everywhere (0–2 harmful commits of 14). On the bank's own held-out sources all five arms reach AUROC 0.865–0.902, so the failure is transfer, not learnability. Root cause traced to a pre-registered design choice: `SEVERITY_RANGES["missing_block"]` spans 5–50% of the window while the frozen evaluation injector writes 5–12%, so bank gaps average 24.5% of T against 8.9% on the frozen 89, TS-ICL's gain is ~3.6x larger in the bank, the q10 head's scale does not transfer and `q10 > delta` abstains on 72 of 89 windows. Group-DRO did **not** beat ERM (held-out AUROC 0.8993 vs 0.9021). The one pre-registered rescue was triggered (bank val 0.9287 >= 0.80 and frozen-89 0.529 < 0.75) and its 21,000-episode bank was built and verified, but the retrain did not run before the node was shut down | `docs/v4_0_counteract_preregistration.md` (§11.1–§11.5 post-hoc), `results/v40_integrity.json`, `results/v40_target_budget.json`, `results/v40_label_audit.json`, `results/v40_group_support.json`, `results/v40_feature_manifest.json`, `results/v40_critic_lodo.json`, `results/v40_critic_ablation.json`, `results/v40_critic_training_diagnostics.json`, `results/v40_critic_checkpoints.json` (30 checkpoints), `results/v40_frozen89_decision.json`, `results/v40_frozen89_rows.jsonl`, `results/v40_phase3_pool.jsonl`, `results/v40_rescue_bank_*`, `experiments/v40_action_critic.py`, `experiments/v40_compare_arms.py`, `tests/test_v40_action_critic.py` (38 passing) | pre-registered in `docs/v4_0_counteract_preregistration.md`; implementation frozen in §11.3 (F1–F12) before any Phase 2 computation; feature cache verified **bit-identical across two independent processes** including the GPU MOMENT embeddings; frozen-89 labels opened only after all 30 checkpoints re-verified by sha256; no threshold was tuned on the 89; four implementation bugs found and fixed in flight (parent dedup, dropped gated-out tsicl_long rows, tuple-unpack in the label join, NaN-carrying KEEP/DESPIKE candidates reaching the encoders and MOMENT); UCI/Zenodo are reachable from the node (the earlier "unreachable" finding was specific to the GitHub raw mirror) but UCI throughput ~40 KB/s made a 260 MB fetch infeasible in-round; Phase 3 not entered, no smoke350, no API, no DOCX; incumbent remains **PICS_joint_relabel** |

| **v4.0 COUNTERACT-TS (2026-09-03, Phase 0+1 complete, superseded by the row above)** | Phase 0: integrity all_pass=true (0 hash mismatch, 771/89 eval frame, 1599 corpus, PICS_joint_relabel 5/5 spot-check); budget carried over from v3.9 without drift (+15 B&S, +5.632 gain, -1 protected edit, harmful<15); public-data fetch (laiguokun mirror) fails at the DNS/connect layer on this node, honest fallback to the 6 development sources per pre-registration. Phase 1: 4200-episode pilot bank (7 mechanisms x 3 severities x 150 + 630 mixed + 420 clean) x 8 actions = 33600 labeled records via the frozen `compute_action_labels` path; parents isolation 2100/2100 pass (zero intersection with the 1599 corpus / 771 eval frame / itself); freeze-before-label digest verified, max fill drift 0.0; long-gap (648 missing_block-family episodes) TSICL_LONG: 644 applicable, 524 B&S (81.4%), 120 harmful (18.6%), directionally consistent with the frozen 89-window 75/14 finding. Three implementation bugs found and fixed during execution (parent dedup, gated-out tsicl_long records silently dropped, tuple-unpack mismatch in evaluate) -- none touch frozen labels/metrics/gates | `docs/v4_0_counteract_preregistration.md` (§11.1-§11.2 post-hoc), `results/v40_integrity.json`, `results/v40_target_budget.json`, `results/v40_counterfactual_bank_manifest.json`, `results/v40_data_registry.json`, `results/v40_bank_isolation.json`, `results/v40_bank_freeze.json`, `results/v40_bank_report.json`, `results/v40_bank_records.jsonl`, `experiments/v40_counterfactual_bank.py`, `tests/test_v40_counterfactual_bank.py` (58 passing) | pre-registered before any v4.0 computation: counterfactual action bank (4-6k pilot episodes, train windows UID-isolated from the frozen evaluation frame, 7 corruption mechanisms + mixed, missing_block 5-50% lengths) -> lightweight (<5M) action-delta critic (Siamese 1D encoder + action token; heads: gain q10/q50/q90 pinball + harmful BCE + protected BCE + action-vs-KEEP ranking; source x family x severity Group-DRO) -> full-family integration over v3.9 D baseline; first decision gate on the frozen 89 TS-ICL long-gap windows (harmful AUROC>=0.75, retain >=55/75 B&S, harmful<=3, CHR CP95<=0.15); one pre-registered rescue (bank -> 20k episodes) only; forbidden: v3.9 signal family, same-TSFM error views, source_id/true_kind/clean/sample_uid as features, tuning on the 89 frozen windows; Phase 2 (action-delta critic) not yet started; incumbent PICS_joint_relabel |

### P0 findings that change how prior diagnostics are read

**Phase B was integrity-blocked, and the block is now lifted.** The
route-conditioned shift replay (`results/route_conditioned_shift.json`) and the
full-window level-shift probe (`results/level_shift_probe.json`) used two
different `_nmse` implementations. On 2026-09-02 both scripts were moved to the
canonical uncentered finite-mask NMSE in `experiments/metrics_common.py`; on the
67 routed level-shift windows the two paths then agreed on operator output hash,
offset, breakpoint, before/after NMSE and loss for every window
(`results/p0_operator_path_audit_fixed.json`). Under the canonical metric the
full-window probe's old `mean_loss 0.011` claim is withdrawn, and the oracle
headroom table shows RESEGMENT's crop has zero beneficial-and-safe candidates
on the frozen corpus, so Phase B closes as a failed branch on the merits, not
on integrity.

**Phase C is inconclusive, not a TSFM-signal failure.** The candidate-level TSFM
counterfactual pilot sampled 50 routed candidates stratified by source dataset.
Only **one** of those candidates came from a true `level_shift` window; the rest
were protected or off-target contaminated windows that the router mislabelled as
RESEGMENT candidates. With one positive example, grouped leave-one-source-out
AUROC is degenerate and the pilot cannot decide whether TSFM signals improve the
acceptance decision. The correct conclusion is "sample too small and too
imbalanced to evaluate," not "TSFM signals do not work."


## 2026-09-14 v4.3 工程接管记录（不进入正式方法版本表）

历史 incumbent 保持 **PICS_joint_relabel**，v4.2 RED 记录保留。v4.3 已有39项 CPU 契约测试通过和32个 train/dev origin 输入清单；真实模型 pilot 尚未执行，A0–A5 未运行，不能形成方法晋升行。测试日志 `logs/v43/contracts/20260914T104430.294322Z/`，数据运行 `results/v43/20260914T104433.076049Z-data/`，独立进程清单一致性 `results/v43/data_determinism.json`。task gain/置信区间/真实GPU成本均暂无数值。

解释修正：旧 v41 `calibrate_tau` 的密度权重只影响 coverage 目标，CHR 和 CP 风险约束未加权。因此相同阈值不能排除真正风险重加权；旧实验数字不变。旧 v42 integrated oracle 的非TS-ICL gain 缺失、已有提交锁定限制仍保留，不将其当完整统一复核上界。详见本轮旧入口审计文档。


2026-09-14 18:48 工程复核追加：修复残差PCA后附加缺失指示可能超过8维的问题，新增测试检查实际回归输入维度；最终CPU测试40项通过（0.96s），见 `logs/v43/contracts/20260914T104754.619288Z/`。旧39项日志保留；真实模型pilot仍待依赖，未产生方法晋升。


### 2026-09-14 下载链路诊断（非方法版本）

直连/代理/国内镜像只读实测已完成，详见 docs/download_routes_20260914.md。未重新安装或运行真实模型，不新增方法结果行；PICS_joint_relabel仍为incumbent，v4.3真实pilot待依赖与模型就绪。


### 2026-09-14 20:11 依赖下载恢复（非方法版本）

用户授权后仅切换work2下载任务线路，保留932,113,925字节旧下载；25个Torch/CUDA wheel已全部通过完整官方SHA256校验，Chronos Torch已安装，其他依赖安装/验收继续。固定下载清单见 requirements/bootstrap-20260914/torch-cp311-direct-downloads.json，切线记录见 docs/download_switch_20260914.md。代理/Codex配置未修改，真实pilot尚未运行；incumbent不变。切线代码本地提交1b02b501dc903804fad83e1eb1acb46b3f33b109，远端认证仍待恢复。


## 2026-09-14 20:15 环境验收完成

三个独立环境全部完成安装、依赖检查和指定模块导入；TS-ICL与Chronos的CUDA256×256矩阵检查通过，RTX4090支持BF16，单次小测试峰值分配9,502,720字节。TS-ICL为Python3.12/NumPy2.5.3，core与Chronos为Python3.11/NumPy1.26.4，两GPU环境保持Torch2.9.1+cu126。25个恢复wheel整包官方哈希校验通过，环境freeze/conda-explicit与SHA256SUMS已落盘并逐项复核。

安装20:14:48结束，模型接续20:15:27开始；TS-ICL官方revision已锁为19c94031439fb31f36ce395088ee50a6762d3774，权重下载中。Bolt尚未下载，真实32-origin pilot仍未运行。此处是环境验收，不是模型worker或方法成功。证据见 docs/environment_acceptance_20260914.json；冻结记录见 requirements/bootstrap-20260914/。待两个模型接口验收通过后，队列重验CPU gate并运行真实pilot，calibration/test读取仍关闭。


## 2026-09-14 20:53 首轮真实pilot失败与入口修复

首个真实pilot于20:49启动，run results/v43/20260914T124856.762289Z-pilot；CPU gate40项通过后，TS-ICL worker在模块导入时因缺statsmodels失败，尚未执行预测或读取future标签。原因是introact_ts顶层入口提前加载旧Agent/profile依赖，而TS-ICL环境按官方依赖保持隔离。没有向TS-ICL环境补装core栈。

已将旧重依赖导出改为按需加载，保留原公共API，并将顶层__init__/types/verify三项必要入口依赖纳入worker代码hash。43项CPU测试通过（1.29秒），4项旧API判据回归通过，两个worker在各自冻结解释器的--help入口均通过。完整失败日志、测试和代码hash见 docs/worker_import_fix_20260914.json。新真实pilot仍须实际执行后验收，不把此修复记为方法成功。

Bolt镜像于20:46:09整包官方SHA256通过，20:46:52在旧传输进程退出和HF文件锁保护下接入同一官方revision缓存；保存旧335,236,791字节未完成文件。原验收器确认Bolt GPU接口通过，TS-ICL也通过。可选Chronos-2元数据TLS失败及一次独立重试失败保留，不阻塞只要求TS-ICL/Bolt的pilot。权重完整镜像耗时与HF缓存命中耗时分别保存，不能混算。


## 2026-09-14 21:00 post-hoc：真实 P1 pilot 完成

32 origins（20 train / 12 dev）、L512/H32、64 次真实 TS-ICL 插补和 96 次 Bolt 预测全部完成；43 项 CPU gate 通过，独立原始结果重算通过，未读 calibration/test。运行 21.794 秒，最大 GPU 分配 710,672,896 字节。KEEP / SINGLE / COV 来源宏平均 MASE 为 1.322762 / 1.316489 / 1.228219；COV 宏平均 MAE 反而变差，两插补臂各 15/32 个 origin task harm，无 CI。仅为接口与开发诊断，正式 A0–A5/H96/H192 未运行，PICS_joint_relabel 不变。首轮导入失败和可选 Chronos-2 TLS 失败保留。证据与原始结果入口见 `docs/v43_pilot_report_20260914.md`、`docs/v43_pilot_evidence_20260914.json`；下一步补长来源、接正式强对照及 A5 静态规则。


## 2026-09-14 P2 首批开发配置冻结（未运行结果）

P1 已完成且独立复核通过后，新增 `configs/v43/p2_first_dev.yaml`、`cli p2` 与 A4/A5 正式接线。只取 ETTm1 / Solar / USTS 的 dev 原始区间，分别 14 / 11 / 1 个不重叠基础 parent；两个 horizon 96/192 及 raw、target block 10%、全部 siblings shared block 10% 共 156 个 episode。这些变体不是 156 个独立样本；全历史 ridge 读取区间在 dev 内重叠，正式推断还须按更大依赖块处理。

Solar 复用本机文件，与论文作者仓库 Git blob 完全一致。只按原行号保留同步时间；来源说明为 2006 年 Alabama 137 路 10 分钟光伏，压缩文本无原始时间戳，不能伪称已恢复绝对日历或发布延迟。库存只统计行宽，不解码 heldout 数值。来源证据见 `docs/v43_p2_source_provenance_20260914.json`。

首批重点检验长缺口的新信息收益，以及原始/共享缺失的保护与负对照；5%/点缺失/spike/valid-event 标注和其他来源为后续矩阵，不能把首批当完整污染实验。固定通道0、seed101、L512、缺口[230,281)、不按标签挑窗口。只要求 TS-ICL/Bolt 两个已通过模型，保持 batch1/GPU单任务。

执行臂为 A0 native/ffill、A2 single、A3 官方全合法covariates、A4当前context及同split全合法历史ridge、A5严格嵌套OOF静态eta。A4历史只读 dev 起点到当前context起点，再拼当前dirty输入，不重新打开当前gap真值；这是额外历史信息轨道。A5保存七类真实遮挡输入，支持不足明确回到同origin已验证A2，真实worker缺行/失败仍报错；eta平局取0。候选去重只在同episode、同horizon、完整输入hash下进行并保存alias，所有候选完成真实预测后才读future。

A1仍为blocked_adapter：`experiments/v39_phase0_replay.py:321` 强依赖771个冻结parents，`:450`按历史候选标签拟合LODO PICS并重放；源码存在不等于可对本次新时间区间部署。该参照待合法适配，不把旧分数贴到新UID，也不把缺失参照填0。原生多变量任务模型尚未运行。A9只对本轮完整已执行候选集生成开发上界，名称明确为A9_ORACLE_AVAILABLE，不冒充全候选上界。

新增测试覆盖gzip越界标签不可解码、父区间共享、shared辅助遮挡、全历史不重读gap、A5不适用回A2、漏真实预测报错、ridge观测值不变及eta平局0。运行以新配置绑定的CPU gate为前提，结果产出前不作方法成功结论。PICS_joint_relabel不变，不将规划写入DOCX成果。


## 2026-09-14 21:20 post-hoc：P2首批真实实验完成

51项CPU测试通过，H96/H192、三个dev来源、26个基础parent/156变体，512次真实插补、580次去重预测、1092份任务标签全部完成，独立原始结果复核通过；耗时251.386秒，峰值GPU分配1.90GB。KEEP/A2/A5来源宏平均MASE为1.258454/1.157005/1.157187，无可靠确认性CI。A5仅4个ETTm1 parent产生8个修正变体，未来任务2好6坏；其真缺口重建6好2坏。加入A5后，相对已含简单跨通道强对照的oracle增量为0，不能晋升残差方法或进入更大A8训练。A1与原生多变量对照待适配，其他污染条件/来源尚未覆盖；calibration/test读取仍为0，PICS_joint_relabel不变。全部状态、误差分歧与成本见docs/v43_p2_report_20260914.md和docs/v43_p2_evidence_20260914.json。


## 2026-09-14 22:00用户新验收与A5遗漏候选诊断

用户明确将验收聚焦于因数据而异治理、合法证据的任务判别能力、主动获取相对固定流程的收益。TS-ICL的8.06%保留为基线收益，不归于agent；A5静态失败不能推断完整agent无效。优先级从补算子/A1转为现有固定候选池的最小agent对照，见docs/v43_agent_acceptance_20260914.md。附件第24节原文件当前不可见，本机第24节仅为本轮消息的明确要求摘要。

复用全部已有TS-ICL遮挡输出，为未选择的eta强度补92次真实Bolt预测（20.16秒，未新增future读取），50个受支持episode中发现26个变体/14个parent有静态规则错过的更优任务强度。相对固定五臂强候选池，全部eta的开发oracle仅从MASE1.094080降至1.093753，增量约0.000327；新增胜出变体ETTm1有4个、Solar有5个。此前“加入A5的oracle增量为0”仅适用于静态选择后的候选，不适用于所有eta。保留两种口径和原始失败，不将新oracle作为部署成绩。证据见docs/v43_a5_extended_diagnostic_20260914.json。

最小agent配置configs/v43/agent_minimal.yaml已冻结：110个train parent按时间拆75 scorer-fit / 35 acquisition-fit，dev维持26 parent。固定五臂初始池，strict_mask/history_probe两个验证工具，最多两轮；比较全体固定臂、train最佳固定、dirty简单选择、mask/history规则、全部证据、两种固定顺序及学习获取停止。同一浅层HGB模型族，source/uid/seed/真实缺陷类型/future不得进特征。费用计入基础候选、验证、选择、最终预测与分片加载/IPC，固定臂仅计实际所需候选；真实在线按需核验在离线评估后执行。尚未运行得出的agent结果均为pending，不作ICLR或晋升声明。


## 2026-09-14 最小 agent 开发验收：H1 有选择空间，H2/H3 未通过

已完成固定五臂、两个验证工具、19组策略：110 train parent按时间拆75动作评分/35工具获取，dev为26 parent/156变体。58项CPU gate、16,272份真实模型输出和2,964条决策/费用独立复核通过。五臂oracle MASE1.094080、train最佳固定TS-ICL1.157005、dirty简单选择1.165414、学习获取停止1.190112、全部调用1.204589；当前agent没有超越强固定/简单策略。173次实际工具步骤中156次任务误差不变、6次改善、11次恶化，mask证据未改变当前评分器动作，历史证据在Solar造成明显退步。

A5补全诊断证明100个非零eta候选均改变真实预测；相对静态有26个更优替代，其中20个为遗漏非零修正、6个应回eta0，不能全称作有效修正被拒绝。对强五臂池的oracle增量仅0.000327。A5新增92份预测、150标签及三种oracle池已独立复核；首次复核未解析旧预测alias而失败，修正映射后通过，保留失败。原P2“54个shared”纠正为52 shared + 2 USTS raw。

低预算学习和history-first各1/156变体超支，未删样本或截费用。初版在线过早加载离线标签档案、1例冷调用轨迹不同均保留；修正后文件访问屏障封锁6个evaluator/缓存档案，7例动作/证据/最终预测一致。完整在线进程24.661710秒，7请求摊销3.523101秒，含初始化/退出；137份在线模型输出与7条实际费用轨迹独立复核通过。批量0.4703秒的学习策略含最终预测费用不是冷在线成本。

PICS_joint_relabel不变；TS-ICL约8.06%是基线收益，非agent。calibration/test读取0；无ICLR/SOTA/安全保证。下一步只在train内注册证据状态独立评分、H32→H96/H192收益排序迁移、无增益工具停止和真实成本预算诊断，先满足H2/H3再扩强baseline/第二TSFM/独立确认。RED不写入DOCX已验证成果。

完整报告与代码证据：[v43_agent_report_20260914.md](v43_agent_report_20260914.md)，机器记录：[v43_agent_evidence_20260914.json](v43_agent_evidence_20260914.json)。原始run `results/v43/20260914T141030.324186Z-agent`；最新阶段状态 `results/v43/agent_stage_acceptance.json`。运行Git HEAD为c92eab5上的未提交工作区，先按内容hash冻结，随后9f5f49f保存了完全一致的代码；不以旧HEAD覆盖快照。


## 2026-09-14 v4.3.1 并行冲刺诊断登记（未晋升）

新任务协议来源宏平均MASE与上方历史治理nRMSD台账不能混算。固定五臂，train在原始时间内拆54/21/17/18个parent用于fit/gate/check/acq，dev保持26parent/156变体。已完成43本地策略、TATO官方实现短预算Bolt适配；共同主表及原始证据见[v431_sprint_report.md](v431_sprint_report.md)。同证据普通CART为1.136486、固定TS-ICL1.157005、冻结单步agent1.200158且全部STOP。终态拒绝层及主动获取没有超越简单强对照，不晋升v4.3.1。TATO数值只引用动态主表；TimesFM本条同步时在统一队列，不登记未运行成绩。

22项本轮测试通过；6,656份新增历史raw输出、2,768份current raw预测、6,708条策略决策和432条同冻结pi获取标签独立复核通过。诊断补费生成accounted派生表，原决策、模型、标签及其SHA保持不变；完整成本不得混淆批量摊销与冷在线墙钟。原标签档案被history准备进程打开但未用于历史证据公式的限制、首次审计失败及其他阴性记录保留。

PICS_joint_relabel继续作为原协议incumbent，calibration/test仍封存。新并行调度已生效，不再以H2显著通过作为接强baseline/第二家族的启动条件；方法晋升仍须公平共同表与完整确认支持。

> 2026-09-14 23:59 最终收口：共同表50个组合均已运行并独立复核；TimesFM固定五臂与TATO已完成，取代下文同步时的在途状态。全部三来源/26 dev parent/156变体，结果与费用以 [v431_sprint_report.md](v431_sprint_report.md) 为准。完整新agent未晋升，calibration/test封存。


## 2026-09-15 v4.3.1-r2 实际交付；r3接续开发

r2保留旧STOP负结果并实现证据状态一致固定参照：Bolt 1.157005；TimesFM 1.069398，与固定mask CART相同，主动机制未成立。主表34行、26 DEV parent/156变体；train110 parent，75拟合/17检查/18获取，支持曲线18/37/75已完成。真实TimesFM补3504唯一预测，648同冻结终态价值标签、4992决策及费用独立复核通过。

两家族真实在线结束：TimesFM自然7窗中6次mask，Bolt自然7窗全STOP，另有预算与失败受控分支。金融已核实Brent报价和Kim–Wright拟合远期利率，2 parent/12相关变体的18行附表已完成；完整观测40次输入/预测no-op一致。金融TimesFM 4.890237仍等固定取证，Bolt 3.069683未胜KEEP。附表按观测事件计H，与旧网格不可横比；自然缺口身份/严格PIT未解决，未来部分重叠旧DEV/pilot，非确认。

报告：[r2报告](v431_r2_report.md)、[共同表](v431_r2_main_table.md)、[逐窗审计](v431_r2_stop_audit.md)、[独立复核](v431_r2_verification.md)、[金融身份](v431_r2_financial_audit.md)。incumbent不变，calibration/test封存；RED不写入DOCX已验证成果。新用户r3已授权长短上下文响应与任务收益映射，尚未产生r3成绩，见其预登记计划。


## 2026-09-15 v4.3.1-r3 完成交付，研究未晋升

从r2提交9d31106接续，未重装环境或改五臂/模型家族。实现同origin长短64步治理响应、真实任务收益ridge及同容量direct/CART、冻结终态后的单步取证、真实在线与完整费用账本。主表98组（含继承原生TATO与旧CART），共同DEV26 parent/156相关变体；四套新评估376组/26,978条记录、144项配对比较独立重算一致。

高预算Bolt：固定TSICL1.157005、r3 agent1.156351、固定取证1.156351；TimesFM：固定TSICL1.096135、agent1.102669、固定取证1.096019。主动未成立，响应未稳定胜旧分歧/等次数回测/direct/CART。训练110 parent分54/21/17/18，主状态有效fit51/gate20/acq16；学习曲线没有一致支持“加数据即改善”。获取树常数根，LOPO15<16而全STOP，lambda0是平局，不是价格选择成功。

两家族各7个自然在线：Bolt6次control/12个真实probe，TimesFM6次H32/6个probe；其余各1次STOP。另各4受控case覆盖完整输入、B0、真实工具后故障及长短对。22case原始输出/隐藏屏障/费用通过；自然热请求无超预算，启动各约9秒，不能称单冷请求满足3.5秒。金融2parent附表TimesFM agent4.920632，但8/12真实超预算；Bolt3.103498差于固定参照3.069683；自然缺口与严格历史vintage仍缺项。完整观测保持no-op，不冒称预测提升。

冻结的source整TRAIN MASE常数用于r3证据归一化，包含早train origin之后和内部check/acq观测；不能称所有训练预处理严格逐origin隔离。DEV时该TRAIN均已过去，calibration/test未参与。保留既定共同分母与所有负结果；候选文件冻结供复核，不满足研究晋升/独立确认条件。PICS_joint_relabel仍为历史incumbent，不宣称SOTA，不把RED写成DOCX已验证成果。

入口：[r3报告](v431_r3_report.md)、[共同主表](v431_r3_main_table.md)、[金融附表](v431_r3_financial_table.md)、[代码审计](v431_r3_code_audit.md)、[独立验证](v431_r3_verification.md)、[创新矩阵](novelty_matrix.md)、[论文](paper_v431_draft.md)。真实命令/配置/预测/支持/成本在results/v431-r3；最终提交和远端一致性见logs/v431-r3/git-sync.json，精简审阅包见results/v431-r3/review_package.json。同步失败不得标完成。


## 2026-09-16 v4.3.1-r4：尺度修复与联合有限策略

最新入口为[执行报告](v431_r4_report.md)、[共同表](v431_r4_main_table.md)、[冻结配置](../configs/v431-r4/resolved.json)。r4使用当前origin学习尺度，外层MASE不变；保留旧输入、原始预测、r3响应及主动负结果。主JOINT与通用cost-sensitive联合树合并为一方法，无原创名称拆分。两家族高预算均选固定H后coverage分支，Bolt1.154124弱于分阶段1.150787，TimesFM1.069398与免费策略同效而成本更高；区间跨零。当前不晋升，不打开确认集，不展开第五轮特征。金融仅2parent，BoltKEEP2.820959仍更强；自然缺口与严格PIT缺项。新原生基线只保留实际已执行TATO8trial，官方完整复现和独立评估协议仍待完成。

CPU拟合与六套回归队列已完成，真实命令/PID/用时位于results/v431-r4/cpu_queue_status.json；在线真实分支和Git最终交付另见本轮报告，不以队列启动代替完成。


r4实际在线：两家族各19自然+3受控完成；数值预测复核通过，TF非逐位相等。Bolt自然1/19超预算、TimesFM0/19，金融各0/12。完整墙钟、cold/hot与首次锁失败见v431_r4_online_verification.md和报告，不作为方法晋升。
