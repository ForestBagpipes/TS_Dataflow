# v4.4-r2 Batch 1 + stage 2 -- claim boundaries

Every number below comes from a frozen payload under `results/v44_r2/`.
Calibration and test were never opened (`heldout_labels_read = 0`,
`calibration_test_touched = false` in all four payloads).

## What the r2 candidate may be claimed to do

* Frozen stage-1 selection: `L3_LINEAR_TREE_ENSEMBLE[a=0.75]`, tau = 0.55.
* Frozen stage-2 selection: lambda = [0.75, 0.25, 0.0], tau = 0.55.
* The candidate is a **decision-regret ranker over counterfactual replay**, deployed through a single confidence veto; KEEP is one of the five ranked actions and is never a post-hoc fallback.
* It is significantly better than `NATIVE_KEEP`, `BEST_FIXED`, `R2_CART` and `FULL_INTROACT` on **both** development backbones (paired cluster bootstrap, parent as unit, 95% CI excludes zero).
* It is **not** significantly different from `A4_WO_GATE` or from `A5_PARAMETRIC_RIDGE` on either backbone.

## What it may NOT be claimed to do

* It does **not** clear the R1-R6 ladder: R2, R3 and R4 fail.  R2 fails because `A5_PARAMETRIC_CART` on TimesFM is lower; R3 fails because `A4_WO_GATE` on TimesFM is lower by 0.00065 MASE; R4 fails because its average rank (7.027 stage 1, 7.984 stage 2) is worse than both parametric selectors in a 12-method field.
* It is not SOTA and must not be written as SOTA.  `CATALOG_ORACLE` is an oracle and is excluded from every ranking; it is reported as a diagnostic only.
* The average-rank failure and the mean-MASE success are the **same fact**: the method wins on the average by taking large gains in high-opportunity windows while intervening on ~99% of TimesFM windows, with a 38% harmful-intervention rate against v4.4 Full's 8.4%.  Neither half may be quoted without the other.
* Stage 2 was used **once**, as the plan permits.  Its gate-selected lambda improved the gate objective by 0.004256 but did not transfer: it helped Bolt by 0.004799 and changed TimesFM by +0.000110, while making the average rank worse (7.027 -> 7.984).  No further search is permitted.

## Data-quality finding that must travel with the result

* One `replay_fit` row on Bolt, `Weather|Weather:7040:7744|h96|P2_target_block|s30`, has `CONTEXT_RIDGE` MASE = 614.232 against a best action of 0.125 (MSE 3.917e7 vs KEEP 1.862).  It is a real execution of the action, not a metric defect, and it is **absent from the gate and TRAIN-Eval blocks**, so it does not enter any reported metric.
* It does enter the fits: it is 1 row in 5168 and contributes about 35% of the Bolt mean regret, inflating the `CONTEXT_RIDGE` ridge residual from ~0.5 to 21.37.  This is why the stage-2 ridge component is fragile and why its gain did not transfer.  It was **not** winsorised: the protocol forbids silent transformation, and a third method change is not permitted.

## Boundary audit (R6)

* stage1 / bolt: 368 records for 368 episodes, 46 parents, 8 cells, parents outside TRAIN-Eval = none, headline equals cell mean = True.
* stage1 / timesfm: 368 records for 368 episodes, 46 parents, 8 cells, parents outside TRAIN-Eval = none, headline equals cell mean = True.
* stage2 / bolt: 368 records for 368 episodes, 46 parents, 8 cells, parents outside TRAIN-Eval = none, headline equals cell mean = True.
* stage2 / timesfm: 368 records for 368 episodes, 46 parents, 8 cells, parents outside TRAIN-Eval = none, headline equals cell mean = True.

## Global verdicts

* stage 1: `all_six` = not recorded (R1-R6 recorded individually)
* stage 2: `all_six` = False

The r2 method line is therefore **closed as a negative result** with the replay information shown to be real and the selector still unable to convert it into a competitive decision rule.
