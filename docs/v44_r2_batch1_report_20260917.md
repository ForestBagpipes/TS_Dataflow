# IntroAct-TS v4.4-r2 -- Batch 1 + stage 2 execution report

Date: 2026-09-17 (server clock).  Server: `ubuntu24`, `/home/vipuser/work/work2`.
Start HEAD: `ae0a94173b5286c38d7de0561d6de874bf187f1e`.

The v4.4 result is preserved untouched: its replay banks, K/beta gate, TRAIN-Eval
table, ablation, canonical tables and commit chain were only ever **read**.  All
new work lives under `src/introact_ts/v44_r2/`, `scripts/v44_r2_*.py` and
`tests/v44_r2/`, and writes only under `results/v44_r2/` and `docs/`.

## 1. What ran

| step | script | wall clock | resource |
|---|---|---:|---|
| contracts | `pytest tests/v44 tests/v44_r2` | 2.2 s | CPU |
| stage-1 gate | `scripts/v44_r2_gate.py` | 64.2 s | 1 CPU, 254 MB |
| stage-1 eval | `scripts/v44_r2_eval.py` | 41.8 s | 1 CPU |
| stage-2 gate | `scripts/v44_r2_stage2_gate.py` | 27.0 s | 1 CPU |
| stage-2 eval | `scripts/v44_r2_stage2_eval.py` | 42.4 s | 1 CPU |
| tables | `scripts/v44_r2_tables.py` | < 1 s | CPU |

No GPU was used (the single RTX 4090 stayed at 0% / 15 MiB throughout), no TSFM
was called and no new replay was produced: every number is derived from the
frozen v4.4 artifacts under `results/v44/replay/`.

## 2. Defects found and fixed before any result was trusted

1. **The pairwise design erased the episode state (would have invalidated the
   whole batch).**  A preference model is trained on `f(x_a) - f(x_b)`.  Feeding
   it `x_a - x_b` makes the twelve episode-state features *exactly zero* for
   every pair, because the state belongs to the request, not the action.  Both
   the linear and the tree learner would therefore have been blind to the
   episode and could only recover one global action order -- the opposite of the
   stated goal.  Fixed by encoding the same three frozen information groups as
   an **action-conditional** design: `state (x) (onehot_a - onehot_b)` (60) +
   `onehot_a - onehot_b` (5) + `intervention_a - intervention_b` (2) = 67.  No
   information was added; the state is simply no longer multiplied by zero.
   Guarded by `test_a_plain_difference_would_erase_the_episode_state` and
   `test_the_pair_design_keeps_the_episode_state_action_conditionally`.
2. **`boundary_audit` treated a float as a dict** (`EV.macro_cells` returns
   `cell -> float`, the audit indexed `c["mase"]`).  It would have raised on the
   first eval run.  Fixed, and the audit was moved from the script into
   `evaluate.boundary_audit` so it is unit-tested rather than script-local.
3. **`evaluate.macro_cells` cell key dropped the severity**, so a 30% cell could
   overwrite the 10% cell of the same `(horizon, pattern)`.  Fixed; the key is
   now `h{H}|{pattern}|s{SS}`.
4. **The average-rank method field did not match the v4.4 report.**  v4.4 ranks
   every method except the oracle; the first r2 run ranked only eight.  R4 is a
   statement about that rank, so the field was aligned and both evals re-run.
   The gate payloads are write-once and were not touched, so **no decision
   changed** -- only the reporting field.
5. Operational: the tmux launcher expanded `$W2_CORE_PY` in the outer shell,
   before `env_new_server.sh` was sourced, so the first launch died with
   `-u: command not found`.  Replaced with a server-side launcher script.

Contracts: 63 tests pass (`tests/v44` 27 + `tests/v44_r2` 36).  The r2 suite
covers the pair set (no cross-episode pairs, weight = `|dL|`, KEEP as an
ordinary action), the veto (tie to KEEP, threshold behaviour), the design
invariances, the parent-fold cross-fit (a spy asserts no episode is ever scored
by a model that saw its parent), the lambda simplex, and the R6 audit.

## 3. Frozen selections

* **Stage 1** (28 candidates = 7 model configs x 4 taus), selected on TRAIN-Gate:
  `L3_LINEAR_TREE_ENSEMBLE[a=0.75]`, `tau = 0.55`.
  Gate objective 1.888235 (Bolt 1.964826 / TimesFM 1.811645).
* **Stage 2** (60 candidates = 15 lambda simplex points x 4 taus), selected on
  TRAIN-Gate: `lambda = (0.75, 0.25, 0.00)`, `tau = 0.55`.
  Gate objective 1.883979 -- an improvement of 0.004256 over stage 1.
  The tree regret component received zero weight.

Both backbones share one architecture, one alpha and one tau; the fitted
coefficients differ because each backbone has its own replay.  Chronos-2 inherits
the same frozen triple unchanged.

## 4. TRAIN-Eval results (source-macro MASE, equal-weight over condition cells)

| method | Bolt | TimesFM | KEEP rate (B/T) | HIR (B/T) |
|---|---:|---:|---:|---:|
| NATIVE_KEEP | 1.179735 | 1.242208 | 1.00 / 1.00 | 0.000 / 0.000 |
| BEST_FIXED | 1.179735 | 1.103034 | 1.00 / 0.25 | 0.000 / 0.283 |
| R2_CART | 1.178209 | 1.146845 | 0.880 / 0.728 | 0.049 / 0.079 |
| FULL_INTROACT | 1.165800 | 1.101261 | 0.802 / 0.546 | 0.084 / 0.188 |
| A4_WO_GATE | 1.142909 | 1.085381 | 0.293 / 0.125 | 0.274 / 0.340 |
| A5_PARAMETRIC_RIDGE | 1.140129 | 1.088242 | 0.198 / 0.193 | 0.291 / 0.291 |
| A5_PARAMETRIC_CART | 1.153831 | **1.080967** | 0.351 / 0.090 | 0.296 / 0.334 |
| **R2 stage 1** | 1.140577 | 1.085921 | 0.109 / 0.011 | 0.378 / 0.380 |
| **R2 stage 2** | **1.135778** | 1.086031 | 0.117 / 0.011 | 0.356 / 0.380 |
| CATALOG_ORACLE (diagnostic) | 1.056632 | 1.016391 | -- | 0.000 / 0.000 |

Paired cluster bootstrap, parent as unit, 10 000 resamples, 95% CI
(`docs/v44_r2_comparisons.csv`).  Stage 2 versus reference, negative = stage 2
better:

* vs `NATIVE_KEEP` Bolt -0.043957 [-0.064872, -0.024160], TimesFM -0.156177
  [-0.224223, -0.097049] -- significant.
* vs `BEST_FIXED` Bolt -0.043957, TimesFM -0.017003 -- significant.
* vs `R2_CART` Bolt -0.042431, TimesFM -0.060813 -- significant.
* vs `FULL_INTROACT` Bolt -0.030022 [-0.048922, -0.012257], TimesFM -0.015230
  [-0.028398, -0.002542] -- significant on both.
* vs `A5_PARAMETRIC_RIDGE` Bolt -0.004351 [-0.017598, +0.008016], TimesFM
  -0.002210 [-0.009029, +0.004453] -- **not established**.
* vs `A5_PARAMETRIC_CART` Bolt -0.018053 (significant), TimesFM +0.005064
  [-0.002323, +0.011934] -- not established.
* vs `A4_WO_GATE` Bolt -0.007131, TimesFM +0.000650 -- not established.
* vs stage 1 Bolt -0.004799 [-0.012354, +0.002099], TimesFM +0.000110 -- not
  established.

## 5. Admission verdicts (R1-R6)

| | stage 1 | stage 2 |
|---|---|---|
| R1 beats FULL_INTROACT, both backbones | pass | pass |
| R2 reaches the best internal selector | **fail** (Bolt +0.00045, TimesFM +0.00495) | **fail** (TimesFM +0.00506; Bolt passes at -0.00435) |
| R3 not worse than A4 no-gate | **fail** (TimesFM +0.00054) | **fail** (TimesFM +0.00065) |
| R4 average rank beats the parametric pair | **fail** (7.027 vs 6.283 / 6.454) | **fail** (7.984) |
| R5 KEEP non-degenerate | pass (0.109 / 0.011) | pass (0.117 / 0.011) |
| R6 no leakage / cache / split / aggregation defect | pass | pass |

**The r2 method does not clear the ladder.**  R2, R3 and R4 fail; stage 2 used
the single enhancement the plan permits and did not change the verdict.

## 6. The one finding that explains everything

The average-rank failure and the mean-MASE success are the same fact.  The
decision-regret ranker intervenes on 88-99% of windows and reaches a **higher
harmful-intervention rate (0.356-0.380) than any other selective method** on both
backbones, while `A4_WO_GATE` and `A5_PARAMETRIC_CART` reach the same or better
mean with far fewer interventions (A4 TimesFM: 1.085381 at KEEP rate 0.125; A5
CART TimesFM: 1.080967 at KEEP rate 0.090, against r2's 1.085921 at 0.011).

So the replay information is real -- the candidate beats KEEP, BEST_FIXED,
R2_CART and FULL_INTROACT significantly on both backbones -- but the selector
converts it into a rule that is right on average and wrong most of the time.
The single confidence veto at `tau = 0.55` is not strong enough to fix that, and
the gate prefers the aggressive end of the tau grid on both blocks.

## 7. Data-quality finding that must travel with the result

One `replay_fit` row on Bolt, `Weather|Weather:7040:7744|h96|P2_target_block|s30`,
has `CONTEXT_RIDGE` MASE = **614.232** against a best action of 0.125
(MSE 3.917e7 versus KEEP's 1.862; MAE 3827; RMSSE 841).  It is a real execution
of the action -- a ridge extrapolation that diverged -- not a metric defect, and
the same episode on TimesFM gives 3.840.

It is **absent from the gate and TRAIN-Eval blocks**, so it enters no reported
metric.  It does enter the fits: it is 1 row in 5168 and contributes about 35% of
the Bolt mean regret, inflating the `CONTEXT_RIDGE` ridge residual from ~0.5 to
21.37 while the other four actions stay at 0.42-0.58.  That is why the stage-2
ridge component is fragile and why its gate gain did not transfer.  It was
**not** winsorised: the protocol forbids silent transformation and a third method
change is not permitted.

## 8. Canonical outputs

`docs/v44_r2_gate.csv` (28 rows), `docs/v44_r2_stage2_gate.csv` (60 rows),
`docs/v44_r2_train_eval.csv` (26 rows), `docs/v44_r2_comparisons.csv` (16 rows),
`docs/v44_r2_verdicts.csv` (4 rows), `docs/v44_r2_claims.md`.
Payloads: `results/v44_r2/gate/gate_sweep.json`, `.../stage2_sweep.json`,
`results/v44_r2/evaluation/train_eval.json`, `.../stage2_eval.json`.

## 9. Next

Per the plan, the r2 method line is now **closed as a negative result**.  The
next work is the part that does not depend on it:

* Batch 3 -- vendor and audit the six published baselines (TOI, TOI-VSF, GIMCC,
  VIDA, SRDI, ChannelTokenFormer) into `third_party/<method>`, keeping
  `official_core` separate from the common-protocol adapter.
* Batch 4-8 -- Bolt + TimesFM main 10%, Chronos-2 inheritance, 30/50
  robustness, support efficiency, statistics and the canonical tables.
* The three extra body experiments (action opportunity, missingness robustness,
  historical support efficiency) and the six-row ablation.

Calibration and test remain sealed.

## 10. Open item for the user

The repository convention (`docx/` rule in `.gitignore`) says a code change that
touches a method definition, a module behaviour or a hyperparameter must update
the progress document in the same commit.  This batch adds a **new selector
family** with new frozen hyper-parameters (`TAU_GRID`, `ALPHA_GRID`,
`LAMBDA_GRID`, the 67-dim pair design), so the rule arguably applies.

It was **not** applied here, deliberately, for two reasons: the frozen v4.4
protocol -- context, horizons, patterns, severities, splits, action pool,
reference action, aggregation, statistics, future-access contract -- is
**unchanged**, and the r2 revision produced a negative result that the project
rules forbid writing up as a verified research finding.  Flagging rather than
guessing: if the intent is that every new selector family gets a progress-document
entry even when it fails, say so and the entry will be added.

