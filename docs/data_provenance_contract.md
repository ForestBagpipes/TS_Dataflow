# Data provenance contract

Effective 2026-09-01. Every result file produced after this date must carry
enough identity to be re-linked to the corpus that produced it, without relying
on positional `window_id` alone. Window ids are reset by every `build_corpus`
call and are not stable across runs.

## Required identity fields

Every per-window or per-candidate record must contain:

| field | meaning |
|---|---|
| `sample_uid` | `dataset:stratum:true_kind:clean_hash:corrupted_hash` (SHA-256 of full series, rounded to 6 decimals) |
| `corrupted_hash` | SHA-256 of the corrupted/working series used as input |
| `clean_hash` | SHA-256 of the pristine reference, or `null` if none exists |
| `dataset` | source dataset label |
| `stratum` | corpus stratum |
| `true_kind` | injected defect kind or `null` for protected strata |
| `corpus_manifest_hash` | SHA-256 of the frozen corpus manifest JSON file |
| `code_commit` | git commit hash or, on the server, the code hash of `src/` and `experiments/` at run time |
| `config_hash` | SHA-256 of the configuration dict passed to the run |

## Manifest file

A corpus manifest must be produced by `experiments/p0_corpus_determinism.py` or
an equivalent deterministic builder and must contain:

- `schema_version`
- `generator` (script name)
- `records`: list of records with `sample_uid`, `window_id` (reference only),
  `dataset`, `stratum`, `true_kind`, `clean_hash`, `corrupted_hash`
- `diagnostics`: including `unique_uids`, `scales_mutated`, `dropped`
- `strata_counts`, `true_kind_counts`, `dataset_counts`

The manifest is frozen once two independent process builds produce identical
records. After freezing, the manifest is referenced by hash, not regenerated on
the fly.

## Cross-run association rule

Window ids may be used only inside a single run. For any comparison across runs,
including audits, replays, or aggregation, the association key is `sample_uid`.
Scripts that rely on `window_id` for cross-run linkage are not allowed and must
be rewritten.

## Determinism checks

New corpus builders must pass:

1. Two independent process builds with the same seed produce identical
   `sample_uid` sets.
2. Every window has a unique `sample_uid` within the corpus.
3. The same script/version produces the same manifest on the same machine.

`experiments/p0_corpus_determinism.py` implements this check.

## Backward compatibility

Result files produced before 2026-09-01 do not contain hashes. They are audited
by `window_id` against a frozen manifest and marked `metadata_verifiable` when
the metadata matches and `hash_unverifiable` because the hash cannot be checked.
Files that cannot be linked at window level are marked `aggregate_only`.

## Current frozen manifest

- File: `results/p0_corpus_manifest_a.json`
- Built: 2026-09-01
- Spec: `n=1600, seed=101, source=mixed`
- Actual windows: 1599 (rounding of stratum target counts)
- Deterministic across two independent process builds: yes
- Known issue: `build_calibration.py` mutates `SCALES[scale].seed`, but this does
  not affect cross-process determinism because each process starts with a fresh
  import. Same-process repeated calls must reset `SCALES` or use a copy.

## Contract-compliant result files

Produced after the contract took effect and carrying the full identity schema:

- `results/v3_training_data.jsonl` — 2414 candidates, per-record sample_uid,
  corrupted/clean hashes, manifest hash, code hashes, config hash
- `results/oracle_headroom.jsonl` — same schema, action-family labels
- `results/p0_operator_path_audit_fixed.json` — per-window identity fields
- `results/v3_arms_compare.json` / `results/v3_trained_shield.json` — aggregate
  files whose inputs are the compliant per-record files above
- `results/v32_training_data.jsonl` — 2414 rebuilt candidates, same schema,
  labels verified identical to the v3 table on all shared keys
- `results/v32_arms_compare.json`, `results/v32_harmful_commits.json`,
  `results/v32_feature_sanity.json`, `results/v31_replay_check.json` — v3.2
  loop outputs; the harmful-commit file carries per-commit sample_uid, route,
  family, features and before/after NMSE

## v3.3 outputs (produced 2026-09-03)

All carry the full identity schema; per-candidate files additionally carry
`forward_fill_baseline_hash`, `keep_input_hash` and `output_hash`:

- `results/v33_training_data.jsonl` — 2414 rebuilt candidates; integrity gates
  in `results/v33_metric_integrity.json` PASS (identical keys, hashes, and
  non-IMPUTE labels against the v3.2 table; observables identical within the
  documented NaN/fp-noise rules)
- `results/v33_ood_manifest.json` — frozen formal OOD stress set, seed 313,
  64 clean_ood (4 forms) + 32 real_ood, zero content-identity overlap with the
  calibration corpus and deployment seeds 0/1/2
- `results/v33_ood_candidates.jsonl` — 155 candidates on those 96 windows,
  with `var_ratio`
- `results/v33_label_flip_audit.json`, `results/v33_metric_integrity.json`,
  `results/v33_support_audit.json`, `results/v33_arms_compare.json`,
  `results/v33_harmful_commits.json`, `results/v33_ood_attribution.json`,
  `results/v33_risk_coverage.json`, `results/v33_feature_sanity.json`

## v3.4 outputs (produced 2026-09-03, diagnostic branch)

- `results/v33_clean_rerun.json`, `results/v33_clean_rerun_harmful.json`,
  `results/v33_clean_rerun_ood.json`, `results/v33_clean_rerun_frontier.json`,
  `results/v33_clean_rerun_support.json` — Phase 0 clean rerun of the v3.3
  arms on the corrected script; replaces the hand-patched v3.3 JSONs as the
  formal baseline (all numbers identical within 1e-9)
- `results/v33_clean_rerun_manifest.json` — sha256 of every input, code file
  and output of that rerun
- `results/v34_conditional_risk_frontier.json` — Phase 1 conditional-risk
  replay; includes the PICS replay selfcheck against the frozen v3.3 baseline
  (PASS at 1e-9), six selector working points with Clopper-Pearson /
  empirical-Bernstein bounds, the honest frontier, and the post-hoc oracle
  grid; no new labels, no new candidates
- `results/v34_shadow_records.jsonl` — 1154 per-candidate shadow certificate
  records, each carrying sample_uid, corrupted_hash, mask_hashes, per-trial
  operator output hashes, manifest_hash and formal_output_matches_table;
  shadow features live under `features`, evaluation-only fields under
  `eval_labels`
- `results/v34_shadow_certificate.json` — Phase 2 signal-gate evaluation on
  the 106 PICS-accepted IMPUTE commits; failure_samples list the 25 harmful
  commits the working point misses

## v3.5 outputs (produced 2026-09-03, diagnostic branch)

- `results/v35_acv_support_audit.json` + `results/v35_acv_support_records.jsonl`
  — Phase 0 structural audit; 2414 per-candidate support/anchor records
  (multi-horizon anchor rule primary, strict reading kept as
  `alt_multi_anchor_reading`); bit-identical across n_jobs
- `results/v35_acv_records.jsonl` — 2414 per-candidate ACV records; each
  carries sample_uid, changed_support_hash, anchor hashes, KEEP/APPLY
  prediction hashes, model checkpoint revisions, config hash; labels joined
  only after this file was frozen (records sha256 inside
  `results/v35_acv_probe.json`)
- `results/v35_acv_probe.json` — Phase 1 signal-gate evaluation (red light),
  including incumbent-consistency check (PICS bcov 0.272727 reproduced)
- `results/v35_tsfm_impute_records.jsonl` + `results/v35_tsfm_impute_probe.json`
  — Phase 2 operator probe (not_green); MOMENT-1-large proposer,
  chronos-bolt-base/timesfm-2.5 verifiers, revision hashes recorded;
  cross-model verification, single native-reconstruction backend

## v3.6 outputs (produced 2026-09-03, diagnostic branch)

- `results/v36_pair_dataset.jsonl` — 5402 symmetric pair records over 827
  episodes; cand features copied in full, all truth fields under the `eval_`
  namespace; pair_id embeds episode_id; KEEP is the synthesised implicit
  action (true_loss=0, features={})
- `results/v36_pair_integrity.json` — Phase 0 integrity report (9/9 PASS),
  with corpus manifest hash, input/code hashes, pair/episode counts
- `results/v36_pair_predictions.jsonl` — 13200 per-fold per-candidate rows:
  p_vs_keep, mean_p_vs_others, tournament score, margin, veto state, final
  selection, eval-namespace truth
- `results/v36_pair_probe.json` — Phase 1 gate evaluation (RED), arms,
  per-fold learning and deployment metrics, attribution block

## v3.7 outputs (produced 2026-09-03, diagnostic branch, Phase 0 only)

- `results/v37_shift_headroom.json` — frozen-score reproduction
  (bit-exact vs v3.6, max_abs_diff 0.0), target-label oracle headroom
  (global + expert-mixture, with search grids and constraints), verdict
  block (light=RED, phase1_primary_arm=null)
- `results/v37_calibration_transfer.json` — 6x6 calibration transfer matrix
  (CHR/bcov/gain/pme/quantile-shift/separation/threshold/commit family),
  source fingerprint distances, transfer-correlation tests

## v3.8 outputs (produced 2026-09-03, diagnostic branch, Phase 0 + Phase 1)

- `results/v38_oracle_replay.json` — mandated v3.7 correction replay: v3.3
  unrestricted candidate oracle, v3.7 frozen-score constrained oracles, and
  the PICS incumbent, all bit-exact (max_abs_diff 0.0), with input/code
  hashes, per-sample_uid alignment and the candidate-set/label/constraint
  difference explanation
- `results/v38_impute_mask_audit.json` + `results/v38_impute_mask_records.jsonl`
  — mask-semantics audit of all 1,154 IMPUTE candidates rebuilt from the raw
  corpus; per-candidate schema adds raw_nan_mask_hash, raw_nan_fraction,
  finite_flatline_mask_hash, mask_origin, gap_runs, anchor_geometry; masks
  always derive from the raw corrupted series, never the materialized probe
  series (materialize_for_probe forward-fill erasure documented in the
  audit's materialization_erasure_evidence block)
- `results/v38_phase0_manifest.json` — Phase 0 integrity manifest (1599
  sample_uids, hash checks, two-process mask rebuild determinism)
- `results/v38_explicit_impute_records.jsonl` — 1,780 Phase 1 records
  (KEEP + tight/medium/wide IMPUTE_EXPLICIT x 445 IMPUTE windows) with raw
  mask provenance fields, certificate verdicts, abstain reasons, labels
  joined only after output freeze; two-process digest sha256
  4e9839b2cb401215999f5e917df80d4547186984f4b7c49c585a4476dda12f63
- `results/v38_explicit_impute_probe.json` — Phase 1 gate evaluation
  (verdict operator_retired): six operator gates, five-arm comparison,
  stratification, abstain-reason distribution, FACT-pool unrestricted oracle
  (with KEEP-placeholder denominator fix), downstream TSFM gain subset
  diagnostics, output_sha256 self-hash

## v3.8 metric-semantics correction + v3.9 plan (2026-09-03)

- v3.8 result files unchanged; the correction is interpretive only: g1
  (76/177 = 0.429) is window-level beneficial coverage, not
  action-conditional precision; over the 88 acted scattered windows the
  action-conditional figures are precision 0.864 / CHR 0.136 (76 B&S, 12
  harmful), with all 89 missing_block windows abstained. From v3.9 every
  operator report carries applicability coverage, action-conditional B&S
  precision, action-conditional CHR, bcov and abstention rate separately.
- v3.9 MIRAGE-TS pre-registered in `docs/v3_9_mirage_preregistration.md`
  before any v3.9 computation; planned new artifacts:
  `results/v39_phase0_replay.json`, `results/v39_phase0_records.jsonl`,
  `results/v39_target_budget.json`, `results/v39_phase0_manifest.json`,
  `results/v39_longgap_candidates.jsonl`, `results/v39_longgap_probe.json`,
  `results/v39_longgap_oracle.json`, `results/v39_model_manifest.json`
  (model manifest must record repository URL, commit/revision, checkpoint
  hash, license and download size for every external imputer).

## v3.9 outputs (produced 2026-09-03, diagnostic branch, Phase 0-2)

- `results/v39_phase0_replay.json` + `results/v39_phase0_records.jsonl`
  (4626 rows = 771 windows x 6 arms) + `results/v39_target_budget.json` +
  `results/v39_phase0_manifest.json` — six-arm replay on the frozen frame
  with KEEP placeholders; incumbent reproduced bit-exact; FACT_SHORT ==
  v3.8 wide exactly (88 filled / 76 B&S / 12 harmful); target budget from
  baseline arm D
- `results/v39_longgap_candidates.jsonl` (801 records, 9 proposers x 89
  long-block windows) + `results/v39_longgap_candidates_freeze.json` —
  candidate outputs frozen (digest 1d68297be8bbc7f2) BEFORE evaluation
  labels were joined; observed-support drift 0.0 on all 801
- `results/v39_longgap_probe.json` + `results/v39_longgap_oracle.json` —
  per-proposer five-quantity metrics, 4/4 headroom gates, joint oracle
- `results/v39_model_manifest.json` — OpenFIM (github.com/FIM4Science/
  OpenFIM, HF rev e00537a9, ckpt sha256 390ba4c13f24e8f0, 80.9MB, MIT),
  TS-ICL (pypi tsicl==0.2.1, HF taharnbl/TS-ICL rev 19c94031, ckpt sha256
  a67ae9f694c2a8, 219.2MB, TS-ICL Non-Commercial v1.0), MOMENT-1-large
  (HF rev ca58581b, MIT); zero paid API calls
- `results/v39_bridge_candidates.jsonl` (1780 eta-mixture records) +
  `results/v39_bridge_signals.jsonl` (five deployment-available signals) +
  `results/v39_bridge_probe.json` + `results/v39_bridge_manifest.json` +
  `results/v39_bridge_freeze.json` — BRIDGE Phase 2: eta endpoints hash-
  equal to Phase 1 outputs, labels replayed after freeze, signal gates 2/6,
  verdict stop_signal_quality_insufficient
- code: `experiments/v39_phase0_replay.py`, `experiments/v39_longgap_probe.py`
  (hash changed to 2ba76450fd8488c0 after a documented float64->float32
  dtype fix in gen_openfim), `experiments/v39_bridge_probe.py`; tests
  `tests/test_v39_phase0.py` (12), `tests/test_v39_longgap_probe.py` (13),
  `tests/test_v39_bridge_probe.py` (13), all passing

## v4.0 COUNTERACT-TS Phase 0-1 outputs (produced 2026-09-03)

- Public training-source fetch attempted per the v4.0 pre-registration
  (`docs/v4_0_counteract_preregistration.md` §3): `pub:electricity`
  (raw.githubusercontent.com/laiguokun/multivariate-time-series-data/
  master/electricity/electricity.txt.gz, origin UCI
  ElectricityLoadDiagrams20112014, CC BY 4.0 at the UCI origin, mirror repo
  carries no explicit license) and `pub:traffic` (same repo, traffic/
  traffic.txt.gz, origin Caltrans PeMS, public data). Mirror commit
  `7f402f185cc2435b5e66aed13a3b560ed142e023` (via the GitHub commits API,
  which IS reachable). **Both file downloads fail** at the DNS/connect
  layer from this node (confirmed twice: an unbounded hang past the 600s
  budget, then a clean failure under a 35s hard timeout) -- 0/2 obtained,
  0 bytes retained, nothing to hash. Registered as attempted-and-failed
  per contract; `results/v40_data_registry.json`. No paid API involved
  (raw GitHub content, unauthenticated). Pilot bank falls back to the 6
  frozen development sources (ETTh1/ETTh2/ETTm1/Crypto/US Term
  Structure/Oil Price), same provenance as v3.x, re-sampled with fresh
  UID-isolated windows.
- TS-ICL reused from v3.9 with no re-download: `taharnbl/TS-ICL` HF rev
  `19c94031`, checkpoint sha256 `a67ae9f694c2a83cfc8e7ec41745ff4f41a4a76ee2b17172ec3430d8d29da431`
  (re-verified before GPU inference), TS-ICL Non-Commercial License v1.0.
  Inference env `w2-v39-impute` (`tsicl==0.2.1`), separate from the
  default `w2` env used for the CPU stages.
- `results/v40_bank_records.jsonl` (33600 labeled records, 4200 episodes x
  8 actions), `results/v40_bank_parents.npz` + `.jsonl` (2100 parent
  windows, isolation-verified against the 1599-window corpus and 771-
  window evaluation frame), `results/v40_bank_report.json`,
  `results/v40_counterfactual_bank_manifest.json`. Zero paid API calls.

## v4.0 Phase 2 + rescue outputs (produced 2026-09-04)

- **Public-source correction to the §v4.0 Phase 0 entry above.** The
  unreachability recorded there is specific to the
  `raw.githubusercontent.com` mirror. Measured from this node on
  2026-09-04: `archive.ics.uci.edu` HTTP 200 in 1.9 s, `zenodo.org` HTTP 200
  in 2.4 s, `https://archive.ics.uci.edu/static/public/321/electricityloaddiagrams20112014.zip`
  HTTP 200. The UCI ElectricityLoadDiagrams20112014 archive (dataset 321,
  CC BY 4.0, ~260 MB) was started and abandoned at 24.8 MB after ~10 minutes
  — sustained throughput ~40 KB/s, projecting ~1.8 h — and the partial file
  was deleted. Correct status is **reachable-but-throughput-limited**, not
  external-data-blocked; the source remains usable for a round that can
  afford the download window. Registered in
  `results/v40_rescue_data_registry.json`. No paid API involved.
- Frozen TSFM for the critic's conditioning inputs: MOMENT-1-large,
  HF snapshot `ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc` (the same revision
  v3.9 registered, MIT), read offline from the node's HF cache, weights
  never updated. Pooling is the mean over the patch axis of
  `embed(..., reduction="none")`; the input is the materialised dirty window
  or candidate at raw scale. TS-ICL was reused from v3.9 with no
  re-download (checkpoint sha256 `a67ae9f6…`, TS-ICL Non-Commercial v1.0).
- `results/v40_feature_cache.npz` + `results/v40_feature_cache_rows.jsonl` +
  `results/v40_feature_manifest.json` — 16,227 applicable bank rows; every
  candidate hash re-verified before any feature was built; **array digests
  bit-identical across two independent processes**, GPU embeddings included.
- `results/v40_critic_checkpoints.json` + `results/v40_critic_ckpt/*.pt` —
  30 checkpoints (5 arms x 6 LODO folds, seed 20260904), each registered
  with its sha256 and its fold-calibrated thresholds; re-verified before the
  frozen-89 labels were opened.
- `results/v40_frozen89_decision.json` + `results/v40_frozen89_rows.jsonl` —
  the one-shot decision. The 89 windows were rebuilt from the frozen corpus
  and reproduce their input and output hashes; the frozen labels replay
  exactly as 75 beneficial-and-safe / 14 harmful.
- `results/v40_phase3_pool.jsonl` (1,833 candidates) — built but not scored,
  since Phase 3 is gated on Phase 2 passing. Its independent recomputation
  of the TS-ICL labels on the canonical `compute_action_labels` path returns
  exactly 75/14, and FACT_SHORT returns 76/12, both matching the frozen v3.9
  tables.
- `results/v40_rescue_bank_*` — the one pre-registered rescue's
  21,000-episode bank (168,000 records, 5,250 parents over the same six
  development sources, freeze digest `366eb376…`, max fill drift 0.0). Same
  mechanisms, severities, action set and label path as the pilot; only the
  episode count and episodes-per-parent differ. Written to `v40_rescue_*`
  paths so the pilot's artifacts and hashes are untouched.
- Three large derived artifacts were left on the node when it was shut down,
  with digests recorded in `results/v40_sync_note.json`:
  `v40_feature_cache.npz` (`d403a93f…`),
  `v40_rescue_bank_candidates.jsonl` (`44cd46d8…`),
  `v40_rescue_bank_records.jsonl` (`1621d8c7…`). All three are deterministic
  functions of the committed code plus the frozen inputs. Everything else,
  including all 30 checkpoints, was pulled to the workstation and verified
  file-by-file.

## v4.1 outputs (produced 2026-09-04, diagnostic branch, Phase 0-1)

- `results/v41_integrity.json` — replay gate: frozen-89 labels 75/14,
  stat-only harm AUROC 0.8771 reproduced bit-for-bit against
  `results/v40_frozen89_decision.json`, and the headroom frontier point
  (57 commits = 55 B&S + 2 harmful, CHR 0.0351) recomputed from the same
  scores. Records the sha256 of every consumed artifact.
- `results/v41_mask_shift_audit.json` + `results/v41_calibration.npz` +
  `results/v41_calibration_rows.jsonl` — the calibration population is the
  21,000-episode rescue bank's 3,153 applicable TSICL_LONG candidates, each
  re-derived from `results/v40_rescue_bank_parents.npz` and
  `results/v40_rescue_bank_cand_tsicl_long.jsonl` with its dirty-window and
  candidate hashes asserted against `results/v40_rescue_bank_records.jsonl`.
  No TSFM was invoked: stat_only reads only the 13 structural scalars, so
  the features are recomputed by operator replay alone.
- Mask descriptors are deployment-available by construction — they are
  functions of the corrupted window and the operator's touched mask only.
  The density-ratio step uses the frozen candidates' *unlabelled* mask
  features and never their labels; this is recorded in the audit as
  `uses_target_labels: false`.
- `results/v41_selector_arms.json` + `results/v41_selector_rows.jsonl` —
  six-arm comparison. Thresholds come only from each fold's training
  sources; arm A reproduces the v4.0 operating point exactly (14 commits,
  14 B&S, 0 harmful), which is the round's replay check.
- Reused without modification: the 30 stat-only checkpoints in
  `results/v40_critic_ckpt/` (sha256 re-verified before inference),
  `results/v40_feature_cache_rows.jsonl`, `results/v39_longgap_candidates.jsonl`
  and `results/v39_longgap_probe.json`. Zero paid API calls; GPU not used
  (Phase 0/1 are CPU-only).
- **Frozen-89 status change:** from v4.1 onward the 89-window frame is a
  development decision set only and is disqualified as the paper's final
  test set. A confirmatory benchmark with fresh corruption seeds, fresh
  parent windows and additional public sources has to be built before any
  external comparison is reported.

## v4.2 outputs (produced 2026-09-05, diagnostic branch, Phase 0 only)

- `results/v42_phase0a_integration.json` — replay of v4.1 arm B into the
  v3.9 D arm under the first-commit protocol. The D baseline is re-read from
  `results/v39_phase0_records.jsonl` through the canonical
  `v33_compare_arms._episode_metrics` rather than quoted from an earlier
  report, and reproduces 132 commits / 117 B&S / 15 harmful / bcov 0.2659 /
  damage 0.0195. Records the sha256 of every consumed artifact.
- `results/v42_phase0b_portfolio_oracle.json` — per-window applicable-action
  sets and beneficial/harmful labels for the nine frozen long-gap proposers,
  taken from `results/v39_longgap_probe.json`'s per-proposer `bs_uids` /
  `harmful_uids`, joined to the candidates in
  `results/v39_longgap_candidates.jsonl`. Pure set arithmetic over frozen
  labels: no model, no TSFM, no GPU.
- **Declared limitation.** The integrated-oracle metrics in that file use
  per-window gains from `results/v40_phase3_pool.jsonl`, which pooled the
  TSICL_LONG family only. Six of the oracle's picks are non-TS-ICL and carry
  no gain record, so they were skipped during integration
  (`n_added_from_portfolio: 74`, `added_without_gain_record: 6`) and the
  integrated row describes a TS-ICL-only oracle. The two gates that decided
  the round (safe-alternative coverage and portfolio-over-best-fixed) are
  label set operations and are unaffected. A true portfolio integration
  requires pooling the non-TS-ICL proposers' per-window gains first.
- Reused unchanged and re-hashed at read time:
  `results/v39_phase0_records.jsonl`, `results/v39_longgap_candidates.jsonl`,
  `results/v39_longgap_probe.json`, `results/v40_phase3_pool.jsonl`,
  `results/v41_selector_rows.jsonl`. Zero paid API calls; GPU not used.
- v4.1's records remain closed and were not modified by this round.


## 2026-09-14 v4.3 追加契约（独立于旧 repair 轨道）

使用 `source+panel+原始完整读取区间` 切分，默认60/15/10/15；context+future 必须位于同 split。同步通道、parent及其污染副本同组。新 hash 覆盖 shape、dtype、规范 NaN 和未舍入原始值；旧舍入 hash 仅保留历史含义。

Episode 仅有可见 context；future 由 `v43.task_labels.read_target` 在split权限检查后读取。当前 reader 只开放 train/dev，calibration/test 未启用。候选不适用回 KEEP，模型故障为实验失败。共同 future mask 从原值冻结，失败预测不能改变评分集合。MASE 尺度由指定原始 train 和冻结周期计算，退化时 null，不暗置1。

ETT 保留CSV原timestamp，检查递增和等间隔；TIME 不解码 object channels，按导出清单绑定二维原始数组及共同 row index，不逐通道删除NaN。真实 TIME 日历/发布延迟仍未恢复，benchmark 行时刻可用性属于显式假设。此声明不等同真实线上 available_at 证据。

32-origin pilot 输入清单已独立进程逐字节复核，`results/v43/data_determinism.json`。抽样只用长度和时间边界，未用future有限性或误差筛选；Crypto dev太短而不取，train只取3个，其余来源轮转补足。真实模型请求包含原输入、mask、协变量、availability、timestamp、cutoff、参数、horizon、代码/env/model revision；整批一一对应验证后才开放任务标签。


2026-09-14 18:48 工程复核追加：修复残差PCA后附加缺失指示可能超过8维的问题，新增测试检查实际回归输入维度；最终CPU测试40项通过（0.96s），见 `logs/v43/contracts/20260914T104754.619288Z/`。旧39项日志保留；真实模型pilot仍待依赖，未产生方法晋升。


## 2026-09-14 21:00 post-hoc：真实 P1 pilot 完成

32 origins（20 train / 12 dev）、L512/H32、64 次真实 TS-ICL 插补和 96 次 Bolt 预测全部完成；43 项 CPU gate 通过，独立原始结果重算通过，未读 calibration/test。运行 21.794 秒，最大 GPU 分配 710,672,896 字节。KEEP / SINGLE / COV 来源宏平均 MASE 为 1.322762 / 1.316489 / 1.228219；COV 宏平均 MAE 反而变差，两插补臂各 15/32 个 origin task harm，无 CI。仅为接口与开发诊断，正式 A0–A5/H96/H192 未运行，PICS_joint_relabel 不变。首轮导入失败和可选 Chronos-2 TLS 失败保留。证据与原始结果入口见 `docs/v43_pilot_report_20260914.md`、`docs/v43_pilot_evidence_20260914.json`；下一步补长来源、接正式强对照及 A5 静态规则。

所有 32 份 train/dev future 只在全部 worker 输出通过后读取，独立复核只重用已保存的 targets。


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
