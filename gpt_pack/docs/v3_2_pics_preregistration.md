# v3.2 PICS pre-registration

Date: 2026-09-02. Author: execution agent, under the planning session's design.

This document pre-registers the v3.2 PICS (Pessimistic Invariant-Checked
Shield) closed loop **before** any of its code or numbers exist. Nothing in
`results/` may be cited for v3.2 unless it traces to this document.

## 0. Standing method position (unchanged)

IntroAct-TS is a risk-constrained governance agent around a frozen TSFM. It
takes governance candidates from any proposer, executes them in a sandbox, and
uses before/after TSFM behaviour plus structure evidence plus finite-sample
risk control to commit, roll back, or abstain, keeping full provenance. It is
not an anomaly detector, not a universal cleaner, not a data-value scorer. This
round does not change the method's subject; it repairs the v3-pre
implementation and tests one contextual-shield redesign.

## 0.1 Why v3-pre is downgraded from STOP_CANDIDATE to
implementation-invalid/inconclusive

Code review after the v3-pre run found defects that invalidate its numbers as
method evidence (they remain valid as a record of what that code did):

1. `touched_fraction` was `len(touched)/T`; `outcome.touched` is a full-length
   boolean mask (`actions.py:318,379`), so the feature was identically 1.0
   whenever a mask existed.
2. `seam_error` cast the boolean mask to int and took `min()`/`max()` of the
   *values* 0/1, not of point indices; it measured positions 0 and 1, never a
   seam, and was not normalised by the window scale.
3. `outside_support_drift` was `delta_utility/(1-touched_fraction)` — a global
   utility ratio, not a change measured outside the declared support.
4. `improvement_consistency`, `improvement_depth`, `action_risk` were computed
   by the data generator but never passed into `extract()`; all three features
   were constant 0.0 in every training row.
5. Calibration selected thresholds by per-candidate prefix risk, but deployment
   commits the first passing candidate per window and stops. The calibrated
   quantity and the deployed rule were different objects.

Consequence: the v3-pre/v3.1-pre pooled numbers in
`results/v3_arms_compare.json` describe a partly broken feature extractor and a
mismatched calibration. The qualitative attribution (RESEGMENT false accepts
removed by the harm gate; residual failure is cross-source transfer) is
retained as diagnosis only. The v3.2 gates below are therefore defined against
the v3.1-pre numbers **as recorded**, with the invalidity noted, and against
the oracle, not against v2-smoke350's 0.0055, which belongs to a different
slice and protocol and serves only as an absolute safety aspiration.

## 1. Phase 1 — implementation repair (before any new method)

In `src/introact_ts/contextual_shield.py` and the data generator:

1. Unify `outcome.touched`: a boolean mask stays a mask; index arrays are
   converted to masks; `None` means the operator declares the whole window.
2. `touched_fraction` = true touched count / T (0.0 when no mask declared... no:
   a whole-window declaration means fraction 1.0, recorded as such).
3. `seam_error` uses real touched indices and is normalised by the window's
   robust scale (`actions.robust_scale`).
4. `outside_support_drift` = mean absolute change on points **outside** the
   declared support, normalised by robust scale; 0.0 by definition for
   whole-window operators.
5. `improvement_consistency`, `improvement_depth`, `action_risk` are passed
   into `extract()` and written into the feature vector.
6. New server-side tests: finite-ness, variance sanity, mask handling, seam
   correctness, support drift correctness, episode-replay determinism.
7. Calibration replays candidates per `sample_uid` in proposer order with the
   first-commit rule and bounds corpus damage over windows; per-candidate
   prefix calibration is retired from the v3.2 line (it survives only in the
   v3.1-pre exact-replay control arm).

## 2. Phase 2 — candidate table rebuild

- Same frozen corpus: `results/p0_corpus_manifest_a.json`, 1599 windows,
  seed 101, source mixed. Same proposer, same operators, same sandbox.
- Labels and operator outputs are **not** redefined: same canonical uncentered
  finite-mask NMSE (`experiments/metrics_common.py`), same damage
  `max(worse_binary, discard_share)`, same beneficial/safe thresholds.
- Only the feature columns change (Phase 1 repairs).
- Output: `results/v32_training_data.jsonl` with the full provenance schema
  (sample_uid, corrupted/clean hash, manifest hash, code hashes, config hash)
  plus a feature sanity report (no constant features, finite rates, mask
  statistics) in `results/v32_feature_sanity.json`.
- RESEGMENT has zero oracle safe headroom (crop discards > 0.03 everywhere).
  This round RESEGMENT candidates are **diagnosis-only**: v3.2 arms never
  commit them. This is a pre-registered arm rule, not a learned decision.

## 3. Phase 3 — PICS design (fixed in advance)

PICS = per-family dual heads + pessimistic cross-source bounds + support gate +
episode-replay calibration.

1. **Source-invariant features.** Raw absolute-magnitude features that encode
   dataset scale are replaced by within-window normalised counterparts:
   `delta_utility_rel = delta_utility / max(|utility_before|, eps)`;
   probe-delta features divided by the before-probe vector's std; seam and
   support drift already robust-scale normalised. Categorical/structural/
   evidence features unchanged. No source ID is a feature.
2. **Per-family dual heads.** For each family with ≥ 30 training candidates, a
   beneficial-and-safe head and a harmful head, both the fixed HGB
   (max_depth 3, max_iter 100, lr 0.05, l2 1.0, seed 20260901). Smaller
   families fall back to a global pair with the action one-hot.
3. **Pessimistic bounds from cross-source disagreement.** Each head is trained
   as a leave-one-source-out ensemble over the training fold's source datasets;
   the deployed score is `min` over ensemble members for benefit (pessimistic
   lower bound) and `max` for harm (pessimistic upper bound). The ensemble
   spread is the support signal.
4. **OOD/low-support default KEEP.** A candidate is refused when its family's
   training support is below 30, or when the harm-head ensemble spread exceeds
   the 95th percentile of the calibration fold's spread (computed on the
   calibration fold only).
5. **Episode-replay calibration.** Per family, on the calibration fold: replay
   each window's candidates in proposer order, commit the first candidate with
   `P_bs ≥ t_bs AND P_harm ≤ t_h`, measure corpus damage risk over windows
   (KEEP = 0), corrected risk `(nR + B)/(n + 1) ≤ alpha = 0.03`. Both
   thresholds sweep a fixed grid 0.05..0.95 step 0.05. Among admissible pairs,
   choose the one with the highest calibration-fold beneficial coverage; if
   none is admissible, the family accepts nothing. Test data never
   participates. Multiplicity note: the guarantee applies per fixed threshold
   setting; selecting max coverage among admissible settings biases coverage
   upward, and this is stated rather than hidden.

## 4. Arms and protocol (offline, Phase 3 output)

Same candidate table (`results/v32_training_data.jsonl`), same
leave-one-real-dataset-out split (seed 20260901), same first-commit episode
rule, OOD rows excluded from training and used as the stress set:

1. `v2_frozen` — the shipped conjunction on the rebuilt table.
2. `v3.1_pre_exact_replay` — the recorded v3.1-pre arm, re-run from
   `results/v3_training_data.jsonl` with the old code path, as a reproducibility
   check against `results/v3_arms_compare.json`; compared only descriptively
   (implementation-invalid).
3. `v3.2_bugfix_only` — v3.1 method (single model, family as categorical, dual
   gate) with repaired features and episode-replay calibration.
4. `PICS_stat_only`, `PICS_TSFM_only`, `PICS_joint` — the PICS stack on the
   statistical / TSFM / full feature sets.
5. `oracle` — max-gain beneficial-and-safe commit per window.

## 5. v3.2 official gates (all must pass to request one-seed smoke350)

Evaluated on the PICS_joint arm, pooled over held-out folds, paired bootstrap
by `sample_uid` (10k resamples, seed 20260901):

- protected mis-edit < 0.0181 (strictly below recorded v3.1-pre);
- damage ≤ 0.0506;
- beneficial coverage ≥ 0.1455;
- contaminated mean gain ≥ 0.083;
- OOD edit rate ≤ 0.05;
- committed conditional damage (harmful / committed) with bootstrap CI upper
  bound significantly below 0.379.

Plus the standing fairness gates: coverage > v2_frozen, ≥ 10 beneficial
commits, max single-dataset share of beneficial commits ≤ 60%.

If the gates fail, the result is a diagnostic branch; no second tuning round is
performed today.

## 6. Resource and API plan

- All compute on `/root/autodl-tmp/work2`; local side edits and reads only.
- Phase 0–4: zero external API calls.
- GPU: the candidate rebuild re-probes with the frozen pool (cached weights,
  offline env); the comparison itself is CPU.
- Only if every gate passes: report the budget and ask the user before
  launching a single-seed smoke350.

---

## Appendix (post-hoc, written after the run): outcome against the gates

Recorded the same day, after execution. The sections above were written before
any v3.2 code or numbers existed and are unchanged.

**Phase 1**: all repairs landed in `src/introact_ts/contextual_shield.py`;
13 contract tests pass on the server (`tests/test_contextual_shield.py`).

**Phase 2**: `results/v32_training_data.jsonl` — 2414 candidates over 827
windows; all label and operator-output fields are identical to the v3 table on
all 2414 shared keys (checked field by field). Sanity:
`results/v32_feature_sanity.json` — no non-finite features; the three repaired
verification features are no longer constant; `outside_support_drift` is
constant 0 because every mask-declaring operator in this pool is honest
outside its declared support (degenerate but correct; kept as a deployment
leak detector).

**Phase 3 arms** (pooled over six held-out datasets, first-commit rule):

| arm | commit | damage | cond dmg | pme | bcov | b. commits | gain |
|---|---|---|---|---|---|---|---|
| v2_frozen | 0.035 | 0.0226 | 0.741 | 0.0272 | 0.0205 | 7 | -0.053 |
| v3_2_bugfix_only | 0.154 | 0.0363 | 0.235 | 0.0181 | 0.2068 | 91 | +0.161 |
| PICS_stat_only | 0.066 | 0.0143 | 0.216 | 0.0181 | 0.0909 | 40 | +0.077 |
| PICS_TSFM_only | 0.056 | 0.0039 | 0.070 | 0.0060 | 0.0909 | 40 | +0.085 |
| PICS_joint | 0.092 | 0.0220 | 0.239 | 0.0030 | 0.1227 | 54 | +0.086 |
| oracle | 0.188 | 0.0000 | 0.000 | 0.0000 | 0.3295 | 145 | +0.184 |

v3.1-pre exact replay: all six arms reproduce the recorded numbers to <1e-9
(`results/v31_replay_check.json`).

**Gate verdict for PICS_joint: FAIL.**

| gate | value | verdict |
|---|---|---|
| protected mis-edit < 0.0181 | 0.0030 | PASS |
| damage ≤ 0.0506 | 0.0220 | PASS |
| beneficial coverage ≥ 0.1455 | 0.1227 | **FAIL** |
| contaminated mean gain ≥ 0.083 | 0.0864 | PASS |
| OOD edit ≤ 0.05 | 0.321 | **FAIL** |
| cond damage CI upper < 0.379 | 0.346 | PASS |
| coverage > v2_frozen; ≥10 beneficial commits; max dataset share ≤ 60% | yes | PASS |

Paired bootstrap (by sample_uid): PICS − bugfix coverage -0.048
[-0.066, -0.030]; PICS − bugfix damage -0.014 [-0.027, -0.001]; PICS − bugfix
pme -0.0065 [-0.013, -0.001]; PICS − stat coverage +0.018 [+0.008, +0.030];
PICS − TSFM coverage +0.018 [+0.009, +0.029]; PICS − v2 coverage +0.058
[+0.039, +0.079].

**Harm attribution** (`results/v32_harmful_commits.json`): 17 harmful commits
under PICS_joint — 13 IMPUTE + 4 DESPIKE; 12 of 17 on US Term Structure; 16 of
17 on contaminated strata; the IMPUTE harm sits on missing_block/missing_
scattered windows whose before_nmse is 0.000 because the finite-mask NMSE
cannot see a hole, so any imperfect fill registers as damage. This is the
label-side blind spot the ledger's nRMSD ruling already records, now appearing
on the accept path.

**OOD failure mechanism**: the support gate keys on cross-source ensemble
spread, but OOD forms are absent from training, so all source-exclusive members
agree with each other; agreement among the ignorant reads as support. The hard
structural conjunction (v2_frozen, 0.036 OOD edit) is what currently respects
alien data.

Per §5 and §6: diagnostic branch, no smoke350 requested, no second tuning
round. The result and its analysis are synced to `docs/version_ledger.md`,
`docs/diagnostic-playbook.md` (tree twenty) and `docs/HANDOFF.md`.
