# v3-pre: Action-Conditioned Conformal Governance Shield

Status 2026-09-02: **STOP_CANDIDATE.** The pre-registered Phase 4 gates were not
met, the single allowed v3.1-pre iteration was spent, and no smoke350 was run.
This document records the design, the evidence, and the root-cause attribution
so the next step starts from verified numbers rather than from memory.

Primary sources: `results/v3_training_data.jsonl`,
`results/v3_arms_compare.json`, `results/oracle_headroom.jsonl`,
`results/p0_operator_path_audit_fixed.json`. Code:
`src/introact_ts/contextual_shield.py`, `experiments/v3_training_data.py`,
`experiments/v3_train.py`, `experiments/v3_compare_arms.py`,
`experiments/oracle_headroom.py`, `experiments/metrics_common.py`.

## 1. What v3-pre is

IntroAct-TS remains a risk-constrained governance agent around arbitrary
proposers: candidates are executed in a sandbox, and a shield decides commit,
rollback or abstain. v3-pre replaces the fixed three-condition conjunction
(utility AND structure AND risk) with a **learned, action-conditioned shield**:
a classifier scores each candidate for being *beneficial and safe*, and a
per-family conformal calibration turns the score into an acceptance threshold
with a bounded corpus-level damage risk (alpha = 0.03, the project's corrected
risk `(nR + B)/(n + 1)`).

Fixed model (pre-registered, no search):
`HistGradientBoostingClassifier(max_depth=3, max_iter=100, learning_rate=0.05,
l2_regularization=1.0, random_state=20260901)`.

Training target is `beneficial_and_safe`, not the v2 verdict. Labels derive
from the canonical uncentered finite-mask NMSE (`experiments/metrics_common.py`)
and the formal damage definition `max(worse_binary, discard_share)`.

## 2. Feature contract

Whitelist (deployment-available): state hypothesis/confidence, dominant and
secondary defect evidence, evidence ratio, route source, action family, rung,
cost, applicable, touched fraction, output length ratio, discard share,
structure aggregate and parts, probe vector deltas, delta utility, the
forecast/reconstruction/sensitivity/representation dynamics deltas, cross-model
disagreement, seam error, outside-support drift.

Blacklist (evaluation namespace only): true_kind, stratum, clean series/hash,
true before/after NMSE, true repair gain, v2 verdict. These never enter the
feature vector.

## 3. Protocol

- Corpus: the frozen P0-A corpus, 1599 windows, seed 101, source mixed,
  referenced by `results/p0_corpus_manifest_a.json`. All 2414 candidate records
  carry `sample_uid`, corrupted/clean hashes, manifest hash, code hashes and
  config hash per `docs/data_provenance_contract.md`.
- Split: leave-one-real-dataset-out (6 outer folds). All candidates of a
  window stay in one split. The test dataset never touches training,
  normalisation, or calibration. Within each fold the remaining windows are
  split 80/20 into train/calibration at seed 20260901.
- Synthetic OOD rows are excluded from training and reported as a stress test
  only.
- Calibration: per action family, candidates sorted by descending score; the
  largest prefix whose corrected corpus risk clears alpha = 0.03 sets the
  threshold. Families with fewer than 30 calibration candidates use the global
  fallback; an unmet global bound accepts nothing (KEEP/ABSTAIN). Thresholds
  are never chosen on test data.
- Execution semantics (identical for every arm): candidates in proposer order,
  first accepted candidate commits, the rest are discarded, otherwise KEEP.
  Multi-commit episodes cannot be replayed offline because the candidate table
  holds step-0 proposals on the original series only.

## 4. Arms compared (Phase 4)

Same candidate table, same corpus, same episode rule:

| arm | rule |
|---|---|
| v2_frozen | shipped verify(): dU > 0.005 AND distortion < per-family tau (DENOISE 0.10, DESPIKE 0.00, IMPUTE 0.02, RESEGMENT 0.40) AND risk < 0.5 |
| statistical_only | shield trained without TSFM-behaviour features |
| TSFM_only | shield trained on TSFM-behaviour features only |
| joint_v3_pre | shield on the full whitelist |
| oracle | per window, the max-gain beneficial_and_safe candidate commits |

## 5. Results (window-pooled over the six held-out folds)

| arm | commit | damage | dmg/commit | protected mis-edit | beneficial coverage | beneficial commits | mean gain (cont.) |
|---|---|---|---|---|---|---|---|
| v2_frozen | 0.035 | 0.0226 | 0.741 | 0.0272 | 0.0205 | 7 | -0.053 |
| statistical_only | 0.191 | 0.0842 | 0.558 | 0.0725 | 0.1591 | 65 | -0.011 |
| TSFM_only | 0.126 | 0.0435 | 0.402 | 0.0725 | 0.1341 | 58 | +0.128 |
| joint_v3_pre | 0.192 | 0.0821 | 0.507 | 0.0574 | 0.1705 | 73 | +0.093 |
| v3_1_pre (dual gate) | 0.134 | 0.0506 | 0.379 | 0.0181 | 0.1455 | 64 | +0.083 |
| oracle | 0.188 | 0.0000 | 0.000 | 0.0000 | 0.3295 | 145 | +0.184 |

Damage is the corpus-level mean window loss (KEEP = 0); dmg/commit is the
per-commit harm rate. Beneficial coverage is the share of contaminated windows
whose committed edit improved NMSE.

Paired bootstrap (window-level, 10k resamples):

- joint − statistical coverage: +0.0065, CI [-0.004, +0.017] — not significant
- joint − TSFM coverage: +0.0208, CI [+0.005, +0.036] — significant
- v3.1 − joint damage: -0.0315, CI [-0.044, -0.020] — significant improvement
- v3.1 − joint protected mis-edit: -0.0169, CI [-0.026, -0.008] — significant
- v3.1 − joint coverage: -0.0143, CI [-0.026, -0.004] — significant loss

OOD stress test (synthetic sources, joint shield): 18/56 windows edited
(0.321) — far above the protected edit rate, so the shield does not recognise
unseen generator forms as hands-off either.

## 6. Gate evaluation

Pre-registered Phase 4 gates for entering smoke350:

| gate | joint_v3_pre | v3_1_pre |
|---|---|---|
| protected mis-edit ≤ 0.0055 | **0.0574 FAIL** | **0.0181 FAIL** |
| damage ≤ 0.05 | **0.0821 FAIL** | **0.0506 FAIL** |
| contaminated coverage ≥ 0.08 | 0.1705 PASS | 0.1455 PASS |
| ≥ 10 beneficial commits | 73 PASS | 64 PASS |
| coverage > v2_frozen | PASS | PASS |
| coverage ≥ statistical + 10% rel at no more risk | **FAIL** | **FAIL** |
| max single-dataset share ≤ 60% | PASS | PASS |

Neither arm enters smoke350.

## 7. Root-cause attribution

Oracle headroom (`results/oracle_headroom.jsonl`, candidate-level):

| family | routed | contaminated b&s rate | protected b&s |
|---|---|---|---|
| DENOISE | 267 | 126/135 = 0.933 | 0/9 |
| DESPIKE | 235 | 133/164 = 0.811 | 0/24 |
| IMPUTE | 1154 | 136/830 = 0.164 | 0/324 |
| RESEGMENT | 758 | 0/314 = 0.000 | 0/400 |

- The headroom is real and large (oracle: coverage 0.33 at zero damage), and it
  sits entirely in DENOISE/DESPIKE/IMPUTE on contaminated windows. RESEGMENT's
  crop has **zero** beneficial-and-safe candidates anywhere — an operator-level
  problem a shield cannot fix, confirming the routing-purity diagnosis.
- Every protected commit under every learned arm is harmful (protected windows
  are uncontaminated, so any content change is damage). The 0.0055 mis-edit
  gate therefore requires near-perfect rejection of protected candidates.
- joint_v3_pre's 19 protected commits are 13 RESEGMENT (mostly dominant-defect
  shift, primary route), concentrated on Crypto (7) and ETTh2 (9).
- The v3.1-pre dual gate (P(beneficial_and_safe) ≥ threshold AND P(harmful) ≤
  cap, both chosen on the calibration fold from a fixed grid) removed
  RESEGMENT commits entirely and cut protected commits 19 → 6. The residual 6
  are all on the held-out ETTh2 fold (DENOISE 3, IMPUTE 3): a cross-dataset
  transfer failure, not a threshold-tightness problem. On the dataset a model
  never saw, the feature distribution shifts and calibration-fold thresholds
  do not transfer; the conformal bound assumes exchangeability that
  leave-one-dataset-out deliberately violates.
- TSFM features carry the repair-quality signal (TSFM_only mean gain +0.128 vs
  statistical -0.011, damage 0.044 vs 0.084), but they do not add coverage over
  the statistical arm, so the pre-registered incremental-value gate fails.

## 8. What this does and does not mean

- It does not refute the shield concept: the oracle shows a perfect shield
  would deliver coverage 0.33 at damage 0 on the same candidate pool.
- It does show the current whitelist, model class, and calibration do not
  separate protected false alarms from true contamination on unseen datasets
  tightly enough for the 0.0055 mis-edit gate.
- The v2-frozen conjunction remains the safest deployed rule (offline
  same-protocol pme 0.0272, damage 0.0226, near-zero coverage), and v3-pre is
  not a successor. No formal version row is added for v3-pre or v3.1-pre.

## 9. One allowed iteration, spent

Per the pre-registration, the first failure permitted exactly one v3.1-pre
rooted in the dominant failure mode (protected false accepts →
calibration/abstention change). That iteration is the dual gate above. It
improved every safety metric significantly and still missed the gates, so the
branch closes here. No second tuning round was run.
