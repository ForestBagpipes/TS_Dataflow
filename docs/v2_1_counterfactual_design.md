# v2.1 counterfactual design and pre-registration

This document fixes the evaluation population and the three-phase probe that
decides whether a v2.1 candidate exists. It is written **after** the first
diagnostic round showed that both a routing-only fix and a blind level-shift
operator fail off-target safety.

## 0. What the true evaluation population is

A candidate reaches the final committed set only if it passes **all** of the
following filters:

1. **Route**: `policy.propose_actions` offers the operator on this window.
2. **Candidate**: the operator's sandbox outcome is applicable (not NO_OP).
3. **Sandbox verification**: the shield's three conditions (structure, utility,
   risk) are satisfied and the action is accepted.

The evaluation population for any counterfactual is therefore

    routed windows  ∩  applicable candidates  ∩  accepted candidates.

The full-window stress test in `results/level_shift_probe.json` (applying the
operator to every window regardless of route) is **not** this population. It is
a worst-case leakage check: it asks "what would happen if the operator were
invoked everywhere?" A good operator must additionally show that, when the
existing proposer and shield are left in charge of *when* it runs, the net
effect on the routed-and-accepted set is safe and useful.

## 0.1 P0 integrity findings (added 2026-09-01)

Before any Phase B/C number is used to decide integration, the following
provenance issues must be acknowledged:

1. **Frozen corpus.** The seed-101 mixed corpus is frozen in
   `results/p0_corpus_manifest_a.json` (1599 windows, deterministic across two
   independent process builds). All future audits and replays must reference it
   by `sample_uid`; `window_id` is not a stable cross-run key.

2. **Inconsistent `_nmse` between Phase B scripts — RESOLVED 2026-09-02.**
   `experiments/metrics_common.py` now holds the single canonical uncentered
   finite-mask NMSE, and both level-shift scripts import it. On the 67 routed
   level-shift windows the two paths agree on operator output, offset,
   breakpoint, before/after NMSE and loss for every window
   (`results/p0_operator_path_audit_fixed.json`). With integrity restored, the
   oracle headroom table (`results/oracle_headroom.jsonl`) shows RESEGMENT's
   crop has zero beneficial-and-safe candidates under the canonical metric, so
   Phase B closes as a failed branch on the merits.

3. **Phase C sample imbalance.** The 50-sample TSFM counterfactual pilot
   contains only **one** true `level_shift` candidate; the rest are protected or
   off-target contaminated windows misrouted to RESEGMENT. Grouped AUROC is
   degenerate and the pilot is **inconclusive**, not evidence that TSFM signals
   fail.

## 1. Phase A — v2 veto attribution (no rerun)

Goal: explain why the coverage upper bound from the calibration pool
(`counterfactual_routing.json`, 0.4849) collapses to the deployed smoke350
coverage (0.0154). Decompose every candidate in the existing smoke350 trace by
veto reason.

### Metrics

Per `(family, stratum, true_kind)`:
- number of routed candidates
- number of NO_OP (operator declined before shield)
- number reaching utility check; share vetoed by utility
- number reaching structure check; share vetoed by structure
- number reaching risk/family threshold check; share vetoed by family threshold
- number accepted
- mean true damage and repair gain of accepted vs rejected candidates

### Grouping

- Family: DENOISE, DESPIKE, IMPUTE, RESEGMENT.
- Stratum: contaminated, clean, hard, rare_valid, changepoint, clean_ood.
- True kind: the injected defect kind, or `null` for protected strata.

### Thresholds

The existing thresholds from `results/conformal_family.json` are frozen for
this phase:
- DENOISE 0.10, DESPIKE 0.00, IMPUTE 0.02, RESEGMENT 0.40.

### Failure branches

- If family threshold is the binding veto for >80% of the candidates that the
  calibration upper bound counted as admitted, the gap is a calibration
  condition mismatch (structure/utility/risk interacting in deployment).
- If NO_OP dominates, the gap is in the operator itself (e.g. RESEGMENT
  discarding too much, or DESPIKE not applicable).
- If utility or risk veto dominates, the gap is in the shield signals, not in
  routing.

### Output

`results/v2_veto_attribution.json` with tables and a short textual root-cause
summary.

## 2. Phase B — route-conditioned shift replay

Goal: test the non-destructive level-shift operator **only on windows that the
existing proposer would route to RESEGMENT**, leaving the frozen TSFM, structure,
utility, risk and verify components unchanged. Do not modify `src/introact_ts`.

### Operator variants

- `resegment_crop`: current crop (baseline, from `actions.op_resegment`).
- `robust_offset_local`: full-length alignment by local medians around the
  detected break.
- `slope_preserving`: full-length alignment by matching linear fits at the
  breakpoint.
- `keep`: no action.

### Evaluation population

Windows where `propose_actions(..., PolicyConfig(enable_param_ladder=True))`
returns at least one RESEGMENT candidate. For each such window, run each
operator variant through the same sandbox stack as `run_conformal_family.py`:
`apply_action`, `probe_window`, `structure_distortion`, `_nmse`, family risk
threshold. The operator is only admitted if it clears the same three
conditions as the current RESEGMENT candidate would.

### Metrics

Per `(operator, route_source, stratum, true_kind, dataset)`:
- routed count, applicable count, accepted count
- protected mis-edit rate among accepted edits
- level_shift coverage = accepted level_shift windows / routed level_shift windows
- repair nRMSD on accepted level_shift windows vs KEEP on the same windows
- mean loss (`max(worse_binary, discard_share)`)

`route_source` is:
- `primary` when RESEGMENT is the dominant-defect operator,
- `secondary` when RESEGMENT is the secondary-defect operator.

### Grouping and leakage control

- Dev/test split by source dataset (leave-one-source-out).
- True kind is used **only** for evaluation, never for deciding whether to run
  the operator.

### Thresholds / green light

For an operator to be considered for integration:
- protected mis-edit rate among accepted edits ≤ 0.0055,
- level_shift coverage ≥ 0.15,
- repair nRMSD on level_shift windows improved over KEEP by ≥ 10%,
- the gain is not driven by a single dataset (max dataset contribution to
  coverage ≤ 60%).

If no operator clears all four, the result is a diagnostic branch only.

### Failure branches

- If coverage is high but protected mis-edit is high: the operator is fine but
  the route is unsafe; need a better shift signal before integration.
- If protected mis-edit is low but coverage is low: the shield rejects too
  many true level shifts; the operator is not distinguishable enough from KEEP.
- If both are low: the operator does not help under the current route/shield.

### Output

`results/route_conditioned_shift.json`.

## 3. Phase C — candidate-level TSFM counterfactual pilot

Goal: find a TSFM-based signal that improves the acceptance decision on the
routed pool, without claiming a final effect. This is a small-sample
implementation pilot.

### Sample

50 candidates from the routed pool, stratified by source dataset (≈5 per
source for the six real datasets; synthetic OOD sources pooled). The sample is
fixed and saved so the pilot is reproducible.

### Signals computed

For each candidate (window + operator + params):
1. **Masked reconstruction preference**: reconstruction error under a random
   input mask vs under a mask placed over the operator's touched region.
2. **Forecast/backcast agreement**: forward forecast vs backward forecast
   (forecast from the end of the window) consistency on the touched region.
3. **Mask/context stability**: change in model readout when the context length
   and mask pattern are perturbed.
4. **Cross-model agreement**: Pearson correlation of per-point errors between
   the curation-model pool (PatchTST and DLinear).
5. **Seam error**: discontinuity at the boundary of an edited region.
6. **Outside-support drift**: model error on untouched points after the edit.

### Comparison table

Each signal is reported alongside the existing shield signals for the same
candidate:
- `delta_utility`
- `structure_distortion`
- family risk / decision risk
- perception confidence and posterior entropy

### Grouped AUROC

The pilot reports grouped AUROC (leave-one-source-out) for separating two
binary questions:
- accepted vs rejected candidates (does the signal predict the shield?)
- level_shift vs protected among routed RESEGMENT candidates (does the signal
  predict the true class?)

### Thresholds / green light for expansion

The pilot is **not** a green light for integration. Expansion to the full pool
is allowed only if:
- implementation is correct (no true-kind leakage into feature computation),
- no single source drives the AUROC,
- grouped AUROC of the new signal exceeds the best existing signal by ≥ 0.05,
- combined recommendation score (existing + new signal) ≥ 0.75,
- unknown-source fallback exists if source-conditioned Mondrian calibration is
  used.

If these hold, the full-pool run becomes the next step. If not, the pilot is
recorded as a negative result.

### Output

`results/tsfm_counterfactual_pilot.json`.

## 4. Source-conditioned Mondrian rule (control only)

A per-source calibration may be reported as a **control arm**, but it must:
- have a fallback for source labels not seen during calibration
  (`unseen-source` bucket),
- report metrics separately for `known-source` and `unseen-source`,
- not be the primary claim.

The primary claim must hold on the grouped/leave-one-source-out evaluation.

## 5. Decision gate

A v2.1 candidate is formed only if one of the following is true:

- Phase B shows a route-conditioned non-destructive operator that clears all
  four thresholds, **or**
- Phase C shows a TSFM signal that clears the expansion thresholds and a
  re-run of Phase B with that signal clears the Phase B thresholds.

Otherwise both phases are recorded as diagnostic branches in
`docs/version_ledger.md` and `docs/diagnostic-playbook.md` and no smoke350 is
run.
