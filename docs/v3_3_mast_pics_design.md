# v3.3 MAST-PICS design and pre-registration

Date: 2026-09-03. Status: pre-registered before any v3.3 code change or run.

IntroAct-TS is a risk-controlled data-governance agent over frozen TSFMs: it
receives candidates from an arbitrary proposer, executes them in a sandbox, and
decides commit / rollback / abstain from frozen-TSFM counterfactual behaviour,
structural evidence and finite-sample risk control, with full provenance. That
positioning is unchanged. v3.3 does not redesign operators and does not reopen
RESEGMENT.

## 0. Why v3.3 exists: three binding defects in v3.2 PICS

1. **Action-semantic label defect (IMPUTE).** The canonical uncentered
   finite-mask NMSE compares only positions where the difference is finite.
   For a window with missing points, `before_nmse` ignores the holes, while an
   IMPUTE candidate fills them, so the filled points enter `after_nmse` and a
   genuinely good repair can be labelled harmful. The frozen TSFM never reads
   NaN either: `probe.py` materialises the series with forward-fill before
   querying. The correct KEEP counterfactual for IMPUTE is the materialised
   input the TSFM actually sees, not the raw array with NaNs. This defect
   produced 13 of the 17 harmful commits in v3.2 (before_nmse = 0 blind spot).
2. **OOD gate defect.** PICS keys its support gate on cross-source ensemble
   spread. On synthetic OOD the source-exclusive members agree with each other
   precisely because the form is absent from training; agreement among the
   ignorant reads as support. v3.2 OOD edit rate: 0.321 against the 0.05 gate;
   v2_frozen's hard structural conjunction edits only 0.036.
3. **Joint-fusion responsibility confusion.** One score set was asked to carry
   both activity and safety. Measured on v3.2: statistical signals add coverage
   (bugfix-only bcov 0.207) while the TSFM-only head is the safer one
   (bcov 0.0909, CHR 0.070). v3.3 separates the duties asymmetrically.

## 0.1 Comparability ruling

Label-dependent metrics (true_loss, harmful, beneficial, beneficial_and_safe,
damage, CHR, conditional mean loss, bcov, repair gain, oracle headroom) are
**not comparable** between v3.2 and v3.3 because the labels changed. All v3.3
arms, including v2_frozen_relabel and PICS_*_relabel, are recomputed under the
new labels and compared only within v3.3. Label-independent metrics (protected
mis-edit, OOD edit rate, commit rate) remain comparable across versions. The
0.0055 protected-mis-edit figure from the v2 smoke350 slice belongs to a
different slice and protocol; in v3.3 it serves only as an absolute safety
target, never as a same-protocol v2 baseline.

## 1. New label definition (Phase 1)

`probe.py` exposes the materialisation the probe already performs as one public
function `materialize_for_probe(series)`; `_naive_fill` is kept as a
compatibility alias. The probe itself must call the same function, so the
label counterfactual and the deployed TSFM input are the same object
(verified by a value-level test).

For **DENOISE, DESPIKE**: labels are unchanged — canonical uncentered
finite-mask NMSE of the raw window against clean. A hard integrity gate
requires their labels to be bit-identical to the v3.2 table row by row.

For **IMPUTE** (covers both NaN gaps and finite frozen runs):

```
x_keep   = materialize_for_probe(original)   # what the TSFM would see unedited
x_action = outcome.series
before   = canonical_nmse(x_keep,   clean, ref_var)
after    = canonical_nmse(x_action, clean, ref_var)
repair_gain = before - after
beneficial  = repair_gain > 1e-9
worse       = after > before + 1e-9
loss        = damage(worse, discard_share)
safe        = loss <= 0.03
beneficial_and_safe = beneficial AND safe
```

For finite frozen runs (no NaN), `materialize_for_probe` is the identity, so
the definition reduces to the old one; only the NaN case changes.

New per-candidate action-semantic fields (evaluation namespace):

- `target_mask`: outcome.touched unified to a boolean mask;
- `target_mask_nrmse_before/after/gain`: NMSE restricted to the touched mask;
- `observed_support_nrmse_before/after/drift`: NMSE restricted to the declared
  untouched support (IMPUTE must not move observed points);
- `missing_fraction`, `missing_recovery_rate`;
- `forward_fill_baseline_hash`: hash of `materialize_for_probe(original)`;
- `output_hash`: hash of the operator output (integrity anchor).

Metric naming repair: the v3.2 fields `n_harm / n_committed` are renamed
`conditional_harm_rate` (CHR). New fields `conditional_mean_loss`,
`conditional_loss_p90`, `conditional_loss_p95` report the actual loss
distribution over commits. The old names survive only as documented aliases.

## 2. Frozen assets and seeds

- Calibration corpus: `results/p0_corpus_manifest_a.json`, 1599 windows,
  seed 101, mixed — unchanged.
- Candidate pool: rebuilt as `results/v33_training_data.jsonl` from the same
  corpus, same proposer, same operator outputs; hard gate: `output_hash` equal
  to the v3.2 table on every shared key, and DENOISE/DESPIKE labels unchanged.
- Split: leave-one-real-dataset-out (LODO); fold assignment is deterministic
  in dataset name; sample_uids never straddle folds. Bootstrap seed 20260901,
  10000 paired resamples.
- Model: HistGradientBoostingClassifier, max_depth 3, max_iter 100,
  learning_rate 0.05, l2_regularization 1.0, random_state 20260901. No model
  or hyperparameter search this round.
- RESEGMENT: closed; diagnosis and oracle tables only, never committed.

### 2.1 Formal OOD stress set (new, frozen)

The 56-window OOD slice used in v3.2 is demoted to historical/development
stress. The formal v3.3 OOD set is built once with a fresh frozen seed:

- `build_corpus(CorpusSpec(n_clean_ood=64, n_real_ood=32, all others 0,
  seed=313, window_len=512))` → 16 windows per synthetic form
  (random_walk, staircase, pulse_train, sawtooth) plus 32 real cross-domain
  windows (exchange/solar via `sample_cross_domain_windows`).
- Content-identity disjointness checked against the calibration corpus and
  deployment seeds 0/1/2; manifest and hashes recorded in
  `results/v33_ood_manifest.json`.
- Candidates and features for these windows are produced by the same pipeline
  as the calibration pool, with labels computed (clean = identity) but used
  only for evaluation.
- Reported per form: proposal rate, candidate family mix, edit rate,
  proposal-conditioned accept rate, post-action variance change. Synthetic
  overall, each form, collision-free subset (random_walk + pulse_train), and
  real_ood are reported separately.

## 3. MAST-PICS: asymmetric dual-head shield (Phase 3)

New module `src/introact_ts/mast_pics.py`; `pics.py` is untouched so v3.2
stays replayable.

- **Benefit head** — joint feature set (statistical + structure + TSFM
  counterfactual, the v3.2 source-invariant PICS_JOINT set plus the new
  action-semantic deployable fields), target `beneficial`. Per family, with
  global fallback below `min_family_n`.
- **Harm head** — TSFM counterfactual + structure consequence features only
  (the v3.2 PICS_TSFM set), target `harmful`. Statistical features must not
  bypass the harm gate.
- Both heads are leave-one-source-out HGB ensembles over the training fold;
  the deployed score is pessimistic (min for benefit, max for harm).
- **Accept** iff: benefit pessimistic ≥ benefit threshold AND harm pessimistic
  ≤ harm cap AND the support–consequence certificate (§4) is not triggered AND
  the family is eligible AND the episode first-commit replay admits the commit.
- Blacklist: no true_kind, stratum, clean series/hash, true NMSE, true repair
  gain, or v2 verdict as a feature or deployment decision; no source ID in
  either head.

## 4. Support–consequence certificate (Phase 4)

- **Support index.** Pre-action window profile (the same profile vector the
  agent's perceive step computes and `ood_scores` consumes), cosine kNN with
  K=20, fitted only on the current LODO fold's training windows. Query score
  is the mean cosine distance to the K nearest training profiles. The
  threshold is the 95th percentile of support distances on the fold's ID
  calibration windows. No held-out or OOD window enters the index or the
  threshold.
- **Action consequence.** Deployable post-action quantities:
  struct_distortion, seam_error, output_length_ratio/discard_share, variance
  ratio, TSFM trajectory instability.
- **Fixed hazard rule.**

  ```
  low_support     = support_distance > ID calibration q95
  unstable_action = candidate fails its frozen v2 family structural threshold
  OOD_HAZARD      = low_support AND unstable_action
  ```

  Only OOD_HAZARD forces KEEP for OOD reasons. Unfamiliar-but-valid data with
  a structurally tame action is not refused.
- **Fixed OOD ablations** (no post-hoc changes to K, q95, or family
  thresholds): `ensemble_spread_only`, `support_only`,
  `frozen_v2_structure_only`, `support_AND_consequence` (the formal arm),
  `support_AND_consequence + frozen_v2_hard_gate`.

## 5. Arms (Phase 5), all recomputed under the new labels

1. `v2_frozen_relabel`
2. `v3_2_bugfix_relabel`
3. `PICS_joint_relabel`
4. `PICS_TSFM_relabel`
5. `MAST_no_support`
6. `MAST_support_consequence` — the formal v3.3 arm
7. `MAST_v2_hard_structure`
8. `oracle_relabel`

Same candidate pool, same RESEGMENT closure, same fixed HGB, LODO,
first-commit episode replay, sample_uid-paired bootstrap (10000), every fold
reported individually in addition to the pooled table.

## 6. Formal gates for MAST_support_consequence

Safety:

- protected mis-edit ≤ 0.0055 (absolute target);
- synthetic OOD edit ≤ 0.05 and real OOD edit ≤ 0.05;
- CHR ≤ 0.10;
- conditional mean loss < PICS_joint_relabel;
- no single dataset contributes > 50% of beneficial commits;
- no protected stratum worse than PICS_joint_relabel.

Liveness:

- beneficial coverage ≥ 1.10 × PICS_joint_relabel;
- beneficial commits ≥ 10;
- contaminated mean repair gain ≥ PICS_joint_relabel;
- coverage > v2_frozen_relabel.

Pareto: at matched risk, coverage significantly above PICS, or at matched
coverage, CHR / conditional mean loss significantly below PICS; the paired
bootstrap 95% CI must support at least one strict improvement.

OOD: at least three synthetic forms with edit ≤ 0.05, collision-free subset
≤ 0.05, and proposal-conditioned accept rate reported alongside (a zero
proposal rate does not count as safety).

## 7. Failure branches

- Any gate fails → v3.3 is a diagnostic branch only: no second tuning round,
  no smoke350; the first binding root cause is localised by label, family,
  source and OOD form back to the code path.
- Integrity hard-gate failure (operator output hash drift, or any unexpected
  DENOISE/DESPIKE label change) → stop immediately and audit code before any
  further run.
- All gates pass → still no smoke350: report projected API calls (0 for
  offline), GPU time and the single-seed plan, and wait for user
  authorisation.

## 8. Required outputs

`results/v33_training_data.jsonl`, `results/v33_label_flip_audit.json`,
`results/v33_metric_integrity.json`, `results/v33_support_audit.json`,
`results/v33_ood_manifest.json`, `results/v33_arms_compare.json`,
`results/v33_harmful_commits.json`, `results/v33_ood_attribution.json`,
`results/v33_risk_coverage.json`. Every committed/harmful/OOD record carries
sample_uid, dataset, stratum, true_kind (evaluation only), family/rung/params,
original/mask/output hashes, forward-fill baseline hash, before/after NMSE,
target-mask gain, observed-support drift, TSFM utility delta, benefit score,
harm score, support distance and q95, structure consequence, selected
threshold, episode candidate order, and the final verdict with its concrete
reason.

---

## Post-hoc results (2026-09-03) — diagnostic branch, gates FAIL

Everything below is post-hoc. The pre-registered part ends at §8.

### Label repair (Phases 1-2), integrity gates PASS

`materialize_for_probe` is now the single public materialisation in
`probe.py` (`_naive_fill`/`_nan_safe` alias it); the probe calls it, so the
IMPUTE KEEP counterfactual is value-identical to what the frozen TSFM sees
(test: probe output on the raw gapped series equals probe output on the
materialised one). New table `results/v33_training_data.jsonl`: 2414
candidates on the same 827 proposal windows. Hard integrity gates all pass
(`results/v33_metric_integrity.json`): identical key sets, identity hashes,
bit-identical DENOISE/DESPIKE/RESEGMENT labels, observables identical (74
rows carry bit-identical NaNs; 5 windows show ≤1.5e-14 fp noise in the
window-level `confidence`/`ood` features from threaded-BLAS nondeterminism,
immaterial against 1e-2-scale thresholds).

Label flips (`results/v33_label_flip_audit.json`): of 1154 shared IMPUTE
candidates, 395 moved harmful → beneficial_and_safe, 1 harmful → safe only,
622 remain harmful, 136 were and remain beneficial_and_safe. `before_nmse`
median moved 0 → 0.0038 (the hole is now visible); `after_nmse` is unchanged.
Oracle headroom under the corrected labels: IMPUTE beneficial-and-safe rate on
contaminated candidates 0.164 → **0.640**, oracle window coverage DENOISE
0.095 / DESPIKE 0.105 / IMPUTE 0.461, RESEGMENT still 0. Of the 13 v3.2
missing-kind harmful commits, **8 were pure label artefacts** (now
beneficial_and_safe, loss 0.000) and 5 are genuinely harmful (3 missing_block
fills slightly worse than the forward-fill baseline, 2 finite flatlines whose
labels are unchanged by design).

### Eight-arm LODO comparison (Phase 5), `results/v33_arms_compare.json`

| arm | commit | damage | CHR | cond mean loss | pme | bcov | bcom | gain |
|---|---|---|---|---|---|---|---|---|
| v2_frozen_relabel | 0.035 | 0.0200 | 0.667 | 0.571 | 0.0272 | 0.0250 | 9 | -0.053 |
| v3_2_bugfix_relabel | 0.213 | 0.0584 | 0.274 | 0.274 | 0.0423 | 0.2705 | 119 | 0.136 |
| PICS_joint_relabel | 0.196 | 0.0402 | 0.205 | 0.205 | 0.0091 | 0.2727 | 120 | 0.092 |
| PICS_TSFM_relabel | 0.078 | 0.0130 | 0.167 | 0.167 | 0.0121 | 0.1136 | 50 | 0.087 |
| MAST_no_support | 0.156 | 0.0454 | 0.292 | 0.292 | 0.0211 | 0.1932 | 85 | 0.098 |
| **MAST_support_consequence (formal)** | 0.132 | 0.0402 | 0.304 | 0.304 | 0.0242 | 0.1614 | 71 | 0.073 |
| MAST_v2_hard_structure | 0.000 | 0.000 | — | — | 0.0000 | 0.0000 | 0 | 0.000 |
| oracle_relabel | 0.376 | 0.0000 | 0.000 | 0.000 | 0.0000 | 0.6591 | 290 | 0.197 |

Gates: 7 of 14 pass. The formal arm passes all OOD gates (0 edits on the
frozen seed-313 set, synthetic 0/64, real 0/32, collision-free 0/32), the
dataset-share gate (0.394 ≤ 0.50), beneficial commits (71 ≥ 10) and
coverage > v2_frozen. It fails pme (0.0242 > 0.0055), CHR (0.304 > 0.10, CI
[0.214, 0.398]), conditional mean loss (0.304 ≥ PICS 0.205), protected-strata
parity, bcov ≥ 1.10×PICS (0.1614 vs required 0.300), contaminated mean gain
(0.073 < 0.092) and the Pareto gate: the paired bootstrap shows MAST strictly
*below* PICS on coverage (diff -0.064, 95% CI [-0.086, -0.042]) at equal
damage. **Verdict: gates FAIL — v3.3 is recorded as a diagnostic branch; no
second tuning round, no smoke350.**

### Root causes (back to the per-commit records, `results/v33_harmful_commits.json`)

1. **Harm-cap saturation.** The episode-replay calibration chose harm caps at
   the grid edge (0.95) for DESPIKE and IMPUTE: the corrected *corpus-level*
   risk stays ≤ 0.03 because KEEP windows dilute the commits, while the
   conditional harm rate among commits explodes. Candidates with harm
   pessimistic scores of 0.77–0.91 were accepted against a 0.95 cap.
2. **Asymmetric split removed safety from the benefit score.** With the
   benefit head predicting `beneficial` rather than `beneficial_and_safe`,
   nothing downstream of a saturated harm cap stops a harmful-but-improving
   edit. PICS's joint head embeds safety in both scores and dominates the
   MAST frontier at every operating point (`results/v33_risk_coverage.json`).
3. **ETTh2 is the dominant failure fold** (pme 0.1509, CHR 0.586; 17 of 31
   harmful commits, 10 of them DESPIKE) — a cross-source transfer failure,
   not a global one.
4. **The OOD certificate works but is carried by its consequence term.** On
   the frozen OOD set *every* proposed candidate fails the frozen v2 family
   structural threshold (unstable = 1.00 for all forms), so the support index
   never gets to decide anything; hazard rate equals the low-support rate
   (pulse_train 0.61, staircase 0.22, others ~0). The certificate's perfect
   OOD score is therefore evidence for the structural conjunction, not yet
   for the support index. Also note: sawtooth draws zero proposals and
   PICS_joint_relabel edits 4/64 synthetic windows (0.062 > 0.05), all on
   random_walk/pulse_train; all arms edit 0/32 real OOD windows.
5. **Full v2 hard gate collapses activity to zero** — MAST_v2_hard_structure
   commits nothing, confirming the v2 conjunction and any learned gate are
   near-disjoint.

### Process corrections made during the run

- The OOD synthetic/real split must key on `stratum`, not the dataset prefix:
  cross-domain windows are named `ood:exchange`/`ood:solar`. The first run's
  JSON misclassified real_ood as synthetic (n=96 vs 64); decisions were
  unaffected. `experiments/v33_compare_arms.py` fixed and rerun.
- The integrity audit's first pass false-alarmed on 74 rows of bit-identical
  NaNs (`NaN != NaN`) and 5 windows of ≤1.5e-14 BLAS fp noise; the gate now
  uses NaN-aware exact equality for scalars and a 1e-12 tolerance for feature
  vectors, documented in `v33_label_flip_audit.py`.

### What this rules in / out

- The label repair is correct, tested, and material: it more than doubles the
  measured oracle headroom and clears 8 of 13 phantom harms. Keep it.
- The asymmetric fusion (§3) is refuted as implemented: removing safety from
  the benefit score is strictly worse along the whole frontier.
- Corpus-level corrected-risk calibration does not control conditional harm;
  any next iteration must bound CHR directly (or cap the harm score away from
  the grid edge) rather than relying on corpus dilution.
- The support index is untested as an OOD mechanism; the structural
  conjunction alone drove the OOD result. A support-only claim would need a
  stress set whose candidates pass the v2 structural thresholds.
