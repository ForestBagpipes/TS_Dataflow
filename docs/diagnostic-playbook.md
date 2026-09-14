# Diagnostic playbook

What to do when a number comes back and does not look like it should. Written
after the fourth time the same three mistakes were made in a different costume.
Every tree below is a real investigation from this project, with the number it
started from and the number it ended at, so the tree can be checked rather than
believed.

The order matters and is the whole point.

    1. is it a configuration fault      did the run measure what you think
    2. is it an artefact                units, denominator, aggregation
    3. only then, is it the method      the interesting case, and the rarest

Every time this order was violated on this project it cost a GPU pass. Every
time it was followed the cause was found before any compute was spent.

## Step 0, before anything, go back to the code that produced the number

Not the result file, not the log line, the function. A result file records what
a function returned, and the question is almost always what the function meant.
Three of the four cases below were settled inside the function body and needed
no rerun at all.

The specific reading that pays: find the denominator, find what is excluded
from it, and find the aggregation. Those three lines carry most of the errors.

## Tree one, a column ranks the arms in an order that makes no sense

**The case.** Repair distance put SCREEN at 2109 against no action at 1382, so
a repair method looked worse than doing nothing.

    is the corpus of mixed provenance?
        yes -> is the quantity carrying units?
                   yes -> STOP. It is a units artefact, not a method result.
                          Normalise inside the homogeneous unit before
                          aggregating, then re read the column
        no  -> is one subgroup much larger in magnitude than the others?
                   yes -> STOP. It is a subgroup domination artefact.
                          Report by subgroup, and build any headline from a
                          weighted mean over the comparable ones

**How it was found.** The smoke test ran on `--source ett`, where every window
is transformer telemetry and the units are uniform, so the column looked fine.
The paper's corpus is `mixed` and spans a bitcoin price near 26000 beside a rate
near 3.4.

**The rule this produced.** A口径 change must be smoked on the corpus it will
run on, never on the convenient one.

**It recurred.** The same tree caught the repair nRMSD column three weeks later,
where level shift was 14 percent of the windows and 62 percent of the mean.
Same shape, different costume: the first was units across datasets, the second
was magnitude across contamination kinds. Both were fixed by refusing to
aggregate across the inhomogeneous axis.

## Tree two, two independent computations of the same column disagree

**The case.** The damage rate recomputed from the flushed traces disagreed with
the table by up to 0.32 on one arm, while every other column agreed to floating
point.

    do the two agree on the denominator?
        no  -> find which windows one includes and the other does not
        yes -> do the two use the same distance or loss function?
                   no -> read both function bodies side by side and list every
                         difference, then test each one separately
                   yes -> is one reading a stale file?

    for each difference found, ask: on which windows does it change the sign
    of the comparison? Group those windows and look at what they have in common.

**How it was found.** Both functions were read side by side. `audit._nmse`
subtracts each series' median and replaces a non finite point with the median.
`run_main._dist` does neither, it drops the non finite difference. Grouping the
disagreeing windows by contamination kind put 212 of them in the two missing
kinds, and measuring those on the untouched corpus gave a distance of exactly
zero: a window with a hole is at distance zero from the truth when the only
points that differ are the ones being dropped.

**Which one was right, and how that was settled without a GPU.** `L1_screen` is
deterministic and needs no model pool, so it was re run offline and reproduced
the table exactly, 329 edits and damage 0.6657. The table was right and the
trace field was the broken one.

**The rule this produced.** When two sources disagree, find a third that can be
computed cheaply and independently. Do not adjudicate between two by argument.

## Tree three, an ablation rung equals the reference row exactly

**The case.** Three of seven rungs came back identical to the full method in
every column, to the digit.

    is the switched component reaching the call site at all?
        Do not answer this by reading the call site alone. Get three
        independent readings:
          a. the code path, is the callback invoked and is the feedback closed
          b. the run's own instrumentation, does it report the component acting
             (counters, decision counts, injection counts)
          c. the per window traces, does the intermediate behaviour differ

        all three say it is running -> the component acts but does not change
                                       the outcome. Go find where its effect is
                                       absorbed
        any one says it is not      -> wiring fault, fix and rerun

    where an effect is absorbed:
        is there a downstream gate that is deterministic given the state?
            yes -> the component can only change the path, not the endpoint.
                   This is a property of the design, and it may be exactly what
                   a safety theorem claims. Measure the path difference and the
                   endpoint difference separately and report both

**How it was found.** The policy rungs reported `n_decisions_with_choice` of
423 and the traces differed from the fixed rule on 265 of 1986 windows in
action order, while final state was identical on all 1986. So the policy ran,
reordered, and the shield converged to the same acceptance set regardless.

**What it turned into.** Not a bug and not a failure of the run, but a fact that
had to change a claim: the policy cannot be sold as a quality gain on this
corpus, and the same measurement is direct evidence for the exploration safety
theorem.

**The rule this produced.** An identical number is a finding, not an error. The
question is never only whether the component ran, it is where its effect went.

## Tree four, a rate is out of range or the wrong side of a prediction

**The case.** Protected stratum retention was reported at 0.57 to 0.67 against a
predicted 0.52, and the pre registration was recorded as failing.

    write down the numerator and the denominator as sentences, not symbols
        "windows in stratum S that survived selection"
        "windows in stratum S that this method was able to score"
    are they over the same set?
        no -> that is the whole error. Two denominators that answer different
              questions must both be reported and never divided into each other
    are they over the same set, and the rate still looks wrong?
        -> is the baseline the nominal rate or the realised one?

**How it was found.** The numerator counted scored windows, the denominator
counted all windows, and the result was then divided by the pool rate. The
effective pool rate was 0.803, not 0.5. Split into a corpus level rate and a
pool level rate, both reported, neither divided into the other.

**The rule this produced.** State the numerator and denominator in words before
computing any ratio. A ratio whose two halves cannot be said in one sentence
each is wrong more often than not.

## The four checks every paper number passes

Kept here as well as in `number_selfchecks.md`, because this file is the one
that gets opened when something looks wrong.

1. **What is the denominator**, what is excluded from it, and is the exclusion
   correlated with the effect being measured
2. **Is it dominated by a subgroup**, and would it survive being reported by
   subgroup
3. **Is there another explanation** that produces the same number, and has it
   been ruled out by measurement rather than by argument
4. **Cross reconcile** against an independently computed source, and when the
   two disagree find a cheap third

## Things that are never the first hypothesis

Ranked by how often each was wrong on this project.

- the model is bad
- the method does not work
- the data is unusual

Each of these was proposed at least once and was wrong every time. The cause
was a hard coded corpus, a units mismatch, an aggregation over an inhomogeneous
axis, a denominator over the wrong set, and a metric that dropped the points it
was supposed to measure.

## Tree five, a condition that never fires

**The case.** Of 2766 RESEGMENT attempts the structural condition refused
exactly zero, and the reported distortion was identically 0.000000 on every one
of them, while the same condition refused 1139 of 2910 IMPUTE attempts.

    is the condition ever the binding one for this operator?
        count refusals attributed to it, per operator, not in aggregate
        zero refusals for one operator and thousands for another is the signal

    if zero: what does the measurement compare?
        find the alignment or preprocessing step between the raw inputs and the
        comparison. Ask what region of the input it removes
        if it removes exactly the region the operator acts on, the measurement
        is structurally incapable of seeing that operator, and the value it
        returns is not small, it is undefined and reported as zero

**The general shape, because this will recur.** A measurement that aligns two
objects before comparing them can align away the very difference it exists to
detect. Here `structure.align_for_action` sliced the original down to the span
the crop retained, and a crop rewrites nothing inside that span, so the two
inputs to the comparison were point wise identical by construction. Every
guard built on that number was inert.

**How to catch it early.** For each condition and each operator, report the
refusal count and the distribution of the quantity the condition tests. A
column of exact zeros with no variance is the tell. A condition that never
fires is not evidence that the operator is safe.

**What it cost here.** 180 commits inside protected strata, discarding a median
40 percent of the window, at a reported distortion of zero and a mean fidelity
gain of zero or below. That is the bulk of v1's protected mis edit rate.

## Tree six, an operator that is never accepted

**The case.** DENOISE, 416 attempts, zero accepted, 81.7 percent refused on
structural grounds.

    is the operator ever applicable?          if not, it is a routing problem
    is it applicable and always refused?      compare the distribution of the
                                              tested quantity against the
                                              threshold, at quantiles
        median within a factor of two of the threshold -> a calibration question
        median an order of magnitude above  -> the operator cannot pass this
                                              condition as posed, and the
                                              condition is wrong for its family
                                              rather than the operator being bad

Measured: DENOISE's distortion quantiles are 0.0000, 0.1096, 0.2085, 0.2590,
0.3688 against a threshold of 0.02. The median is ten times the threshold.
Savitzky Golay smoothing changes every point, so a point wise distortion is high
for it by construction, and a single global threshold calibrated on operators
that rewrite a handful of points cannot also govern one that rewrites all of
them.

**The rule.** A threshold calibrated on one family of transformations does not
transfer to another. Calibrate per family, on that family's own score
distribution, at the same target risk level.

## Tree seven, a signal that is small by design

**The case.** IMPUTE's acceptance rate on the two missing kinds is 0.003 and
0.016, and 51.6 percent of its refusals are on the utility condition, which is
its own target defect.

    before calling this a failure, read what the probe feeds the model
        `probe._naive_fill` carries the last valid observation forward
        so a gap arrives as a frozen plateau, not as a hole

**This one is not a defect.** The docstring states the reason: a zero fill would
leave the model unable to distinguish the candidate from the original, the
measured utility change would be exactly zero, and every fill would be refused
for failing to help. Forward filling reproduces what a model meets when nobody
curated the data.

**But it has a consequence that must be stated rather than discovered twice.**
IMPUTE competes against forward fill, not against a hole, so its utility gain is
the difference between two plausible reconstructions and is small by
construction. An operator in that position should not have its acceptance rest
mainly on the utility condition. This is the same conclusion tree six reaches
from the other direction, and both point at per family calibration.

## Tree eight, two numbers for one column

**The case.** `f_full`'s nRMSD is 1.0764 in the ablation table and 1.5080 in the
soft penalty table.

    are they the same quantity?
        list the denominator of each in words before comparing them
        here: all seven contamination kinds, against the five sound ones

Neither was wrong. They answered different questions and nothing recorded which
question each table asked. **The fix is a ledger with the convention written
down once**, `docs/version_ledger.md`, and every version measured under it. Two
readings of one column are not a discrepancy to resolve, they are a missing
definition to supply.

## Tree nine, a quantity established on one corpus does not transfer

**Four occurrences, same shape.** Each was found separately and each cost
something before it was found.

| what was established on `ett` | what happened on `mixed` |
|---|---|
| repair distance as a plain RMSD | SCREEN 2109 against no action 1382, a repair looked worse than doing nothing |
| the valuation family's selection basis | raw scores selected by magnitude, zero percent of Crypto and one hundred percent of one probe |
| shield conservatism, the replay | the injected layer moved 0.187 to 0.2855 and the operator ordering inverted |
| **the conformal calibration corpus** | **the calibration pool has no financial series at all while 44.6 percent of deployment is financial, so exchangeability never held and the deployed damage rate sat at four times the target** |

**The rule, stated once so it does not have to be rediscovered a fifth time.**
Any quantity calibrated, tuned or validated on `ett` is assumed not to transfer
to `mixed` until measured there. `ett` is three transformer telemetry sets with
one unit and one regime; `mixed` adds a bitcoin price, an oil price and a term
structure. A statistic that is stable within one is under no obligation to be
stable across both.

**The specific form the fourth one took, because it is the least visible.** A
calibration corpus is not a hyperparameter, so it does not get swept, and it is
not a metric, so it does not get reconciled. It sits in one line of the launcher
(`run_conformal.py:130`, `source="ett"`) and every guarantee downstream inherits
it silently. When a theorem's premise is a property of two datasets, check the
two datasets, not the theorem.

**How the fourth one was caught.** Not by suspicion of the calibration but by
asking why the deployed damage rate was four times the target level when the
theorem said it should be below. A guarantee that does not hold in deployment is
either a broken proof or a broken premise, and the premise is much cheaper to
check first.

## Tree ten, the local summary number is stale relative to the server run

**The case.** The trajectory probe was reported as amber with a combined AUROC
of 0.7028 in the local `results/trajectory_probe/probe.json`. The server had
already run the corrected protocol (PatchTST, grouped by source dataset) and
written a red verdict with AUROC 0.5794 to the same path.

    is the local file actually the same run as the server file?
        compare hashes, mtimes, and the fields the script would write
        here the local file lacked the `architecture` and `cv` fields that the
        current script always writes, so it was produced by an earlier version
        of the script

    is the earlier run the one the design document registered?
        no -> the earlier number is obsolete, not a "previous result"

    did the server run remove or overwrite the earlier result?
        check the launcher: it explicitly `rm -f` the curves file and rewrites
        the probe file, so the amber number was intentionally replaced

**How it was found.** The server `results/trajectory_probe/probe.json` was
read and showed `verdict: red`, while the local file still showed `verdict:
amber`. The local file has been archived as
`results/trajectory_probe/probe_run1_mlp_stale.json` and the server version is
now the local version.

**The rule this produced.** When a result file is both produced by a server run
and inspected locally, always sync before interpreting it. A number that is
valid somewhere else is not valid here until it has been copied and its hash
matches. Do not carry conclusions from stale local files into planning.

## Tree eleven, a routing fix does not raise coverage because the family threshold is already zero

**The case.** DESPIKE routed onto 23 gap windows, which looked like a source of
false candidates. A counterfactual replay suppressed DESPIKE on missing-primary
windows, routed only to the primary defect, and gated secondaries by evidence
ratio.

    does the suppressed family actually admit any candidates under its lambda?
        DESPIKE's per-family λ is 0.00; admitted count is 0 with or without the
        routing change
        -> removing off-target DESPIKE candidates changes the denominator but
           not the number of admitted repairs

    does the rule that keeps only primary defects preserve enough coverage?
        current coverage upper bound 0.4849, primary_only 0.2601
        -> the secondary slot carries a large share of the reachable coverage;
           the fix is worse than the disease

**How it was found.** The counterfactual replay (`results/counterfactual_routing.json`)
was run with dev/test splits by source dataset. Missing-primary suppression
changed overall protected-candidate rate from 0.3136 to 0.3177 and left
coverage unchanged; primary_only and ratio_gate both cut coverage roughly in
half.

**The rule this produced.** Before committing to a routing change, simulate its
effect on the *admitted* set, not on the candidate pool. A candidate that the
shield would reject anyway is not a coverage leak.

## Tree twelve, a non-destructive operator passes its target class but fails off-target safety

**The case.** A level-shift alignment operator was prototyped to replace the
cropping RESEGMENT. On true level_shift windows it achieved mean loss 0.011
(98.9% ≤ 0.03) and improved repair RMSD over KEEP (4.47 vs 5.47).

    what happens on windows the operator is *not* meant for?
        protected strata: mean loss 1.00
        other contamination kinds: mean loss 0.94-0.99
        -> the operator is effective precisely because it rewrites structure;
           on real structure that rewrite is damage

    can the shield catch the off-target cases?
        the off-target damage is structural, so the structural condition is the
        natural guard. But the new operator has no discard, so its structural
        distortion is small and it passes easily
        -> the operator outsources safety to the router, and the router still
           mislabels 58% of protected windows as contaminated

**How it was found.** The probe (`results/level_shift_probe.json`) ran the
operator on every calibration window and reported loss by stratum and true
kind. The on-target/off-target gap is two orders of magnitude.

**The rule this produced.** An operator that preserves all data is not safe by
construction. Safety depends on *when* it runs. If the routing signal that
triggers it cannot separate protected windows from the target defect, the
operator cannot be integrated, no matter how good its target-class numbers are.

## Tree thirteen, the coverage upper bound collapses in deployment

**The case.** The calibration pool says the routed candidate set could in
principle cover 48.49% of injected windows (`results/counterfactual_routing.json`),
but the v2 smoke350 run covers only 1.54%.

    is the gap in routing or in the acceptance layer?
        read the veto funnel per family from the existing smoke trace
        IMPUTE: 195 contaminated candidates, 5.6% NO_OP; of executed,
                45.1% utility veto, 43.5% structure veto, 0.0% accepted
        RESEGMENT: 189 contaminated candidates, 66.1% NO_OP; of executed,
                   50.0% utility veto, 48.4% structure veto, 1.6% accepted
        DESPIKE: 36 contaminated candidates, 0.0% NO_OP; of executed,
                 5.6% utility veto, 94.4% structure veto, 0.0% accepted
        DENOISE: 23 contaminated candidates, 13.0% NO_OP; of executed,
                 0.0% utility veto, 85.0% structure veto, 5.0% accepted
        -> the gap is not routing alone; the shield and operator applicability
           remove almost every candidate before acceptance

    which condition is binding?
        RESEGMENT: NO_OP (operator declines to act), then structure/utility
        IMPUTE: utility and structure vetoes, with lambda=0.02 as the binding gate
        DESPIKE: family threshold lambda=0.00 (calibrated), so the structural gate
                 admits nothing
        DENOISE: structural gate at tau=0.10

**How it was found.** `experiments/v2_veto_attribution.py` recomputed the funnel
from `results/smoke_v2.json` and cross-checked the per-family distributions
against `results/family_scores.jsonl`. The aggregate numbers agreed with the
smoke trace.

**The rule this produced.** When a coverage gap is this large, do not assume the
router is the problem. Decompose by `(family, NO_OP, utility veto, structure
veto, risk/family veto, accepted)` first. A condition that admits nothing, or an
operator that NO_OPs on two thirds of its target windows, explains the gap
without a routing rerun.

## Tree fourteen, a non-destructive operator still fails when evaluated on the routed population

**The case.** Tree twelve showed the new operator is dangerous on every window.
The fairer test is to run it only on windows the existing proposer already
routes to RESEGMENT, leaving the frozen TSFM, structure, utility and risk checks
in place.

    does any variant clear the pre-registered gate?
        slope_preserving:  coverage 16.4%, protected mis-edit 51.9%,
                           repair RMSD 5.64 vs KEEP 5.50 (worse)
        robust_offset_local: coverage 9.0%, protected mis-edit 56.2%,
                             repair RMSD 7.99 vs KEEP 5.50 (worse)
        resegment_crop_aggressive: coverage 6.0%, protected mis-edit 20.0%,
                                   repair RMSD 4.49 vs KEEP 5.50 (better)
        -> none satisfies coverage ≥15%, protected mis-edit ≤0.0055 and
           repair improvement ≥10% simultaneously

    why does the best on-target variant still destroy protected windows?
        the operator rewrites level structure; protected windows contain real
        changepoints that the router mislabels as level_shift
        the structural condition is the natural guard, but full-length alignment
        has no discard, so its structural distortion is small and it passes

**How it was found.** `experiments/route_conditioned_shift.py` replayed each
operator variant through the existing sandbox on the 773 windows that currently
receive a RESEGMENT candidate. True kind was used only for evaluation.

**The rule this produced.** A full-window stress test is a leakage check, not a
deployment claim. The only claim that matters is on `routed ∩ applicable ∩
accepted`. If the operator cannot pass there, it cannot be integrated, even when
its target-class numbers are excellent.

## Tree fifteen, candidate-level TSFM counterfactual pilot

**The case.** After routing and operator fixes failed, the remaining question is
whether the frozen TSFM itself can supply a signal that improves the acceptance
decision on the routed pool.

**Result.** `results/tsfm_counterfactual_pilot.json`, n=50 candidates from 48
unique windows, all applicable, stratified by source dataset, seed 42.

    did the implementation compute the six signals correctly?
        yes, after two bug fixes:
          1. `reconstruct_batch` returns can mismatch the requested span when a
             backend shortens its forecast; guard with length checks.
          2. RESEGMENT's runtime params (lo/hi) live in `outcome.params`, not in
             the ladder defaults; pass them to `structure_distortion`.
        the run now produces 50 unique records with no leakage of true_kind
        into feature computation

    do the TSFM signals separate the classes directionally?
        accepted vs rejected (by delta_utility > 0.005, base rate 0.72):
            masked_reconstruction_preference: -0.73 accepted, -0.53 rejected
            outside_support_drift: 1.09 accepted, 0.79 rejected
            mask_context_stability: 0.20 accepted, 0.18 rejected
        level_shift vs protected (n=10, base rate 0.10):
            existing struct_distortion: 0.976 vs 0.501
            existing delta_utility: 1.80 vs 0.15
            TSFM cross_model_agreement: 0.175 vs 0.073
            TSFM mask_context_stability: 0.141 vs 0.108
        -> the existing shield signals already separate as well or better;
           the TSFM signals show only weak directional trends

    is the sample large enough for grouped AUROC?
        leave-one-source-out folds are degenerate: only one source carries both
        level_shift and protected examples, so most folds cannot compute an AUROC
        -> the pre-registered expansion gate cannot be evaluated honestly at n=50

**The rule this produced.** A 50-sample pilot can check implementation and
rough direction, but it cannot decide integration. Without a non-degenerate
grouped AUROC, the honest conclusion is "not enough evidence to expand," not
"the signal is slightly promising." Full-pool expansion is not approved by this
pilot.

## Tree sixteen, a corpus cannot be reloaded by window id

**The case.** Every previous script used `window_id` to link results back to the
corpus, but `window_id` is a positional counter reset by every `build_corpus`
call. Two runs with the same seed can assign the same id to different data if
the builder changes, and the same data can receive different ids if the stratum
order changes.

    is the corpus builder deterministic across independent processes?
        run it twice with identical arguments in two fresh Python processes
        compare each window by content hash, not by window_id
        if they differ: find the global mutable state (random seed dicts,
        module-level counters, imported RNGs)

    does the manifest record enough to re-identify a window?
        required: dataset, stratum, true_kind, clean_hash, corrupted_hash
        not sufficient: window_id alone

**How it was found.** `experiments/p0_corpus_determinism.py` built the seed-101
mixed corpus twice in independent processes. Both produced 1599 windows with the
same set of `sample_uid`s, but `build_calibration.py` was found to mutate
`SCALES[scale].seed` while doing so. The mutation does not break cross-process
determinism because each process imports a fresh `SCALES`, but it would break
same-process repeated calls.

**The rule this produced.** A corpus manifest must be frozen by content hash and
referenced by hash in every downstream result. Window ids are for human reading
inside one run only. See `docs/data_provenance_contract.md`.

## Tree seventeen, two scripts compute the same column with different functions

**The case.** The full-window level-shift probe reported mean loss 0.011 and
98.9% of windows below the 0.03 gate, while the route-conditioned replay on the
same operator reported mean loss near 0.52 and a 48% below-threshold rate. Both
claim to measure `max(worse_binary, discard_share)` on the same repair.

    do the two scripts agree on the operator output?
        re-run both on the same window in the same process
        compare series hashes, offset, breakpoint
        if they agree, the difference is in the metric, not the operator

    do the two scripts use the same loss / distance function?
        read both `_nmse` bodies side by side
        here `level_shift_operator_probe` uses `audit._nmse` (centers + nan_to_num)
        and `route_conditioned_shift` uses its own `_nmse` (no centering, finite mask)

    on which windows does the difference flip the accept/reject verdict?
        compute loss under both definitions for every window
        count how often one calls a window repaired and the other damaged

**How it was found.** `experiments/p0_operator_path_audit.py` ran the same 67
level-shift windows through both evaluation paths in one process. Operator
outputs, offsets, breakpoints and repair RMSD matched perfectly, but
before/after NMSE disagreed on 66-67 of 67 windows and loss disagreed on 36 of
67 windows for `robust_offset_local`.

**The rule this produced.** Before comparing two numbers, compare the functions
that produced them. A column called `loss` in two files is not the same quantity
until the code paths are shown to be identical. Phase B is **integrity-blocked**
until one `_nmse` definition is adopted in both scripts.

## Tree eighteen, an old result file is metadata-verifiable but hash-unverifiable

**The case.** After freezing the corpus manifest, existing result files need to
be checked against it. Some files have window_ids, others are aggregate-only,
and none store the clean/corrupted hashes.

    does the result file have per-window records?
        yes -> look up each window_id in the manifest
               check dataset, stratum, true_kind match
               flag mismatches (e.g. JSON null vs string "null")
               report as metadata_verifiable; note hash cannot be checked
        no  -> compare aggregate counts (n_windows) to the manifest
               report as aggregate_only; do not use for per-window claims

    is the file even from the same corpus slice?
        `resegment_noop.json` reports n_windows=350 and slice_seed=202
        the frozen manifest has 1599 windows from seed 101
        -> not comparable; must be rebuilt or excluded

**How it was found.** `experiments/p0_result_manifest_audit.py` linked every
window-level record in `family_scores.jsonl`, `level_shift_probe.json`,
`route_conditioned_shift.json` and `misroute_evidence.json` to the manifest. All
metadata matched after normalising JSON null to "null". `resegment_noop.json`
could not be linked because it was built from a different 350-window smoke
slice.

**The rule this produced.** Pre-contract result files can be audited but not
promoted to a new version until they are rebuilt with hashes. A mismatch in
`n_windows` or `slice_seed` is enough to disqualify a file from quantitative
re-use, even if its content looks plausible.

## Tree nineteen, a learned shield fails on transfer, not on thresholds

**The case.** The v3-pre contextual shield (`docs/v3_contextual_conformal_shield.md`)
reaches 0.17 beneficial coverage against v2-frozen's 0.02, but its protected
mis-edit rate is 0.057 against a 0.0055 gate. The calibration worked exactly as
designed on its own fold; the failures appear on the held-out dataset.

    is the failure a calibration bug?
        recompute thresholds by hand from the calibration fold
        check the corrected-risk formula against conformal.calibrate
        here the formula was first written per-commit instead of
        corpus-level; fixing it changed the answer but not the verdict

    which candidates get committed on protected windows?
        group committed protected candidates by family, route, hypothesis
        joint shield: 13 of 19 are RESEGMENT on shift-primary routes
        a harmful-probability second gate removes RESEGMENT entirely

    what survives the second gate?
        6 commits, all on the held-out ETTh2 fold, DENOISE and IMPUTE
        -> not a threshold problem: the scores themselves do not transfer
           to a dataset the model never saw

    is there headroom at all?
        oracle on the same candidate pool: coverage 0.33 at damage 0
        yes -> the concept is not refuted; the feature/model/calibration
        stack under cross-dataset shift is what failed

**How it was found.** `experiments/v3_compare_arms.py` runs five arms over one
candidate table under one episode rule and dumps a per-family/route/hypothesis
breakdown of every commit. The protected-commit attribution localised the
failure twice: first to RESEGMENT (fixed by the v3.1-pre dual gate), then to
ETTh2-specific DENOISE/IMPUTE accepts (not fixable by calibration).

**The rule this produced.** When a learned gate fails only on held-out sources,
tightening the threshold on the calibration fold is the wrong tool: the gap is
exchangeability, and the bound never covered its absence. One pre-registered
iteration may target the dominant failure mode; a second tuning round is not
allowed, and the branch is recorded as stopped.

**2026-09-02 amendment.** This tree's quantitative details are downgraded to
implementation-invalid/inconclusive: the feature extractor it ran on had a
constant `touched_fraction`, a broken `seam_error`, a pseudo
`outside_support_drift`, three constant-zero features, and a calibration whose
risk object did not match the deployed first-commit rule. The qualitative
lesson above survives; the numbers do not. `docs/v3_2_pics_preregistration.md`
§0.1 lists the defects.

## Tree twenty, when the gate fails on two axes at once, read them separately

**The case.** v3.2 PICS passed every safety gate (protected mis-edit 0.0030
against 0.0181, damage 0.0220 against 0.0506, conditional damage CI
[0.145, 0.346] against 0.379) and failed the two liveness gates: beneficial
coverage 0.1227 against 0.1455, and OOD edit rate 0.321 against 0.05.

    is the coverage miss a calibration artefact?
        compare arms under one protocol: bugfix-only reaches 0.207 coverage
        at pme 0.0181; PICS trades coverage for the pme gain
        -> the pessimistic ensemble is doing exactly what it was built to do

    why does the support gate not catch OOD?
        the gate keys on cross-source ensemble spread
        OOD forms are absent from training, so every source-exclusive member
        agrees with the others; agreement among the ignorant reads as support
        -> spread measures source disagreement, not epistemic novelty

    what handles OOD instead?
        v2_frozen edits 2 of 56 OOD windows (0.036); the hard structural
        conjunction, not the learned score, is what respects alien data

    where is the residual harm?
        17 harmful commits under PICS_joint; 13 are IMPUTE on missing_block,
        12 of 17 on US Term Structure; before_nmse is 0.000 on these windows
        because the finite-mask NMSE cannot see a hole; any imperfect fill
        registers as damage
        -> a label-side blind spot on missing kinds, recorded in the ledger's
           nRMSD ruling, now visible on the accept path

**How it was found.** `experiments/v32_compare_arms.py` pooled arms table,
`results/v32_harmful_commits.json` per-window dump with sample_uid, route,
family, features and before/after NMSE, and a one-off replay of v2_frozen on
the OOD stress set.

**The rule this produced.** Pass/fail is read per gate, never averaged. A
shield that is safe enough but covers too little is a different next step
(operator and label work on missing kinds, an explicit novelty detector on the
support gate) than one that covers plenty but harms. Conflating the two would
have sent the next iteration in the wrong direction.

## Tree twenty-one, when the label itself is wrong, fix the label before the model

**Status 2026-09-03: opened, pre-registered, no results yet.** v3.3 MAST-PICS
(`docs/v3_3_mast_pics_design.md`) starts from three defects the v3.2 loop
exposed, all traced to code before any new model is trained:

    is a "harmful" IMPUTE commit actually harmful?
        canonical finite-mask NMSE ignores the holes in before_nmse and counts
        the filled points in after_nmse; the KEEP counterfactual the frozen
        TSFM actually queries is the forward-filled series, not the raw NaN
        array
        -> 13 of 17 v3.2 harmful commits are this label artefact; the fix is
           labelling, not thresholding

    does ensemble spread prove support?
        no: on unseen OOD forms the source-exclusive members agree with each
        other; agreement among the ignorant is not support
        -> replace with a support index (cosine kNN on training-fold profiles)
           conjoined with an action-consequence check

    should one score carry both activity and safety?
        v3.2 says no: statistical signals add coverage, TSFM signals carry
        safety; v3.3 fuses asymmetrically, joint features predict benefit,
        TSFM/structure features predict harm

**Rule this tree is opened to test.** When a metric and a model disagree,
recompute the label against the counterfactual the deployed system actually
faces before touching the model. Threshold tuning on top of a broken label
only moves the artefact around.

### Tree twenty-one outcome (2026-09-03)

The label fix landed exactly as diagnosed: 395 of 1154 IMPUTE candidates moved
from harmful to beneficial_and_safe, the IMPUTE oracle headroom quadrupled
(0.164 to 0.640), and 8 of the 13 old harmful commits were pure label
artefacts. The other two hypotheses did not survive contact:

    does the asymmetric fusion work?
        no -- with the benefit head predicting beneficial instead of
        beneficial_and_safe and the episode calibration free to pick a 0.95
        harm cap, harmful-but-improving edits pass at harm scores of 0.77-0.91
        -> corpus-level corrected risk bounds the AVERAGE window, not the
           COMMITTED ones; KEEP windows dilute harm out of the guarantee

    does the support-consequence certificate beat the spread gate on OOD?
        it scores zero OOD edits, but every OOD candidate already fails the
        frozen v2 structural threshold, so the support index never fired;
        credit goes to the structural conjunction
        -> a certificate whose second term is always true proves nothing
           about its first term; the support index remains unevaluated

**New rules.** (1) When a gate bounds an average, check the conditional
quantity it hides before claiming safety -- CHR and corpus damage diverged
0.304 vs 0.040 here. (2) A threshold search that is allowed to pick the grid
edge is telling you the constraint is slack; report edge-saturation
explicitly. (3) PICS_joint_relabel, with safety embedded in both heads, is
the strongest shield to date under correct labels (bcov 0.2727, damage 0.0402,
CHR 0.205) and still fails the absolute safety target (pme 0.0091 > 0.0055)
and the synthetic OOD gate (0.062 > 0.05, all four edits on
random_walk/pulse_train). The next iteration should bound conditional harm
directly, not remove safety from the benefit score.

## Tree twenty-two, when the certificate and the controller both fail, check whether the score ranking itself is the ceiling

**Status 2026-09-03: opened and closed in one loop, v3.4 SCRC-PICS diagnosed,
no formal version.** Pre-registration `docs/v3_4_scrc_pics_preregistration.md`;
two independent repairs were tested against the v3.3 failure modes:

    can a direct conditional-risk controller fix the diluted corpus-risk gate?
        no -- on frozen PICS scores, every calibration fold has NO feasible
        threshold at CHR<=0.10 with a Clopper-Pearson 95% upper bound <=0.10;
        an oracle post-hoc 99x99 grid directly on held-out tops out at
        bcov 0.0614 under CHR<=0.10, and oracle per-family coordinate ascent
        reaches only bcov 0.0932 / CHR 0.0889 with caps on the grid edge
        -> score ranking insufficient: the PICS scores themselves rank
           harmful candidates above beneficial-and-safe ones, so no threshold
           on these scores separates them; lenient gates that "work" on two
           folds do not transfer under LODO (held-out CHR 0.37-0.43)

    can a shadow intervention certificate see IMPUTE harm without the truth?
        no -- pseudo-gaps carved into the observed region give
        shadow_valid_trials>=2 on 99.7% of candidates, but harmful-vs-safe
        AUROC on PICS-accepted IMPUTE is 0.351, worse than the existing PICS
        harm score (AUPRC 0.206 vs 0.199), and harmful recall at a 10% false
        reject rate is 7.4%
        -> the error an imputation method makes on a fake gap in the observed
           region does not transfer to the real missing target; large shadow
           gain mostly marks windows where KEEP/ffill is terrible, not where
           the candidate is trustworthy

**New rules.** (1) Before designing a controller, run the oracle-grid
feasibility check: if even post-hoc optimal thresholds on the same scores
cannot reach the gate, the bottleneck is the signal, not the selector.
(2) A certificate that replays the operator on self-made gaps measures
operator smoothness on observed structure, not reliability on the real
defect; the two decorrelate exactly where the defect is worst.
(3) Both v3.4 components failed for the same underlying reason: the current
deployable feature set does not order candidates by true conditional risk.
The next iteration needs a better candidate-level signal or operator family,
not another threshold scheme on the same scores.

### Tree twenty-two outcome (2026-09-03)

v3.4 SCRC-PICS closed as a diagnostic branch: Phase 0 clean rerun reproduced
the v3.3 baseline exactly (all numbers within 1e-9, OOD stratum classification
corrected in code); Phase 1 recorded "score ranking insufficient"; Phase 2
failed 3 of 4 pre-registered signal gates; Phase 3 was not run, per the
pre-registration. Incumbent remains PICS_joint_relabel (bcov 0.2727, CHR
0.2053, pme 0.0091, gain 0.0919, damage 0.0402). Results:
`results/v34_conditional_risk_frontier.json`, `results/v34_shadow_certificate.json`,
`results/v34_shadow_records.jsonl`, `results/v33_clean_rerun*.json`.

## Tree twenty-three, when the verifier is aligned to the action and still fails, the frozen model's error signal itself is the ceiling

**Status 2026-09-03: opened and closed in one loop, v3.5 ACV diagnosed, no
formal version.** Pre-registration `docs/v3_5_acv_preregistration.md`. v3.4's
shadow certificate failed because its pseudo-gaps were not aligned with the
real action support; v3.5 aligned the verification exactly to the action:

    does post-action real-observation predictability separate harm?
        no -- prequential gain (KEEP vs APPLY forecasting the same real
        observed block after the changed support) gives harmful AUROC 0.623
        on PICS-accepted commits, recall 25.8% at a 10% false-reject point
        -> the frozen TSFM's forecast error on real future observations does
           not rank a harmful edit below a beneficial one

    does support conformity (masked reconstruction of the changed support)
    do better?
        directionally yes (AUROC 0.708, AUPRC lift +0.210 over the PICS harm
        score) but still under the 0.75 bar, and the pre-registered primary
        was prequential, so no post-hoc switch is allowed
        -> the gap between 0.71 and 0.75 is exactly where the label noise
           and model bias live; record it, do not chase it

    does a TSFM reconstruction operator fix IMPUTE?
        halves the harmful rate (0.539 -> 0.289) but collapses the
        beneficial-and-safe rate (0.460 -> 0.172): MOMENT's reconstruction
        neutralises instead of repairing, and on Crypto/Oil/US Term Structure
        it moves in the WRONG direction
        -> a conservative neutraliser is not a repairer; median true loss 0
           is not evidence of benefit

**New rules.** (1) Three failed evidence lines now bound the same quantity
from different sides: corpus scores (v3.4), self-made gaps (v3.4 shadow),
action-aligned real outcomes (v3.5) -- the frozen foundation model's error
surface does not carry enough conditional-risk information at this candidate
granularity; stop adding verification views on the same models.
(2) Structural applicability is a first-class result: DENOISE rewrites the
whole window so no post-action anchor exists (99.3% excluded) -- an operator
whose support is the whole window cannot be prequentially verified by
construction; report the boundary, do not impute features for it.
(3) Audit-estimated coverage (89%) and realised coverage (57.6%) diverged
because the audit's conformity criterion was looser than the implemented
one -- freeze the implemented criterion before quoting coverage numbers.

### Tree twenty-three outcome (2026-09-03)

v3.5 ACV closed as a diagnostic branch: Phase 0 structural audit passed
integrity (2414/2414 operator outputs bit-identical) but recorded anchor
coverage limits; Phase 1 red-lit on gates A and B (and C, D); Phase 2's
TSFM_RECONSTRUCT_IMPUTE was not_green (harm halved, benefit collapsed).
Phase 3 not run. Incumbent remains PICS_joint_relabel (bcov 0.2727, CHR
0.2053, pme 0.0091, gain 0.0919, damage 0.0402). Results:
`results/v35_acv_records.jsonl`, `results/v35_acv_probe.json`,
`results/v35_tsfm_impute_records.jsonl`, `results/v35_tsfm_impute_probe.json`,
`results/v35_acv_support_audit.json`.

## Tree twenty-four, when within-window ranking fails, check whether the harm sign itself is source-specific

**Status 2026-09-03: opened and closed in one loop, v3.6 PAIR diagnosed, no
formal version.** Pre-registration `docs/v3_6_pair_preregistration.md`. The
hypothesis: absolute feature scales drift across sources, so within-episode
pairwise differences should wash out window difficulty and source shift.

    does pairwise preference learning beat the pointwise shield?
        no -- PAIR_episode_relative: held-out pairwise accuracy 0.645,
        deployment bcov 0.0909 / CHR 0.412 vs PICS 0.2727 / 0.205; the
        pointwise twin on identical features is no better (0.059 / 0.447)
        -> relativisation inside the window does not fix what is wrong
           BETWEEN windows across sources

    is it a data-construction artefact?
        no -- label/episode integrity, pair symmetry, LODO leakage all
        excluded by assertion before any threshold was touched; the binding
        failure is cross-source generalisation: held-out AUROC 0.92-0.99 on
        Oil/Crypto/USTS but 0.50-0.67 on ETT, every commit and every harmful
        commit lands in the ETT folds, and regret concentrates on noise and
        spike -- exactly the families where DESPIKE/DENOISE should win

**New rules.** (1) Within-window differences remove window difficulty, not
source-specific harm SIGN: the same operator can help on one source and hurt
on another, and no per-window feature transform fixes a label whose direction
flips with the source. (2) When the margin gate silently kills all commits on
exactly the sources where the model ranks well, the deployment metric and the
learning metric are measuring different failures -- report both, always.
(3) Logistic beating HGB here (0.721 vs 0.645) while both miss the gate says
the bottleneck is signal, not capacity -- again.

### Tree twenty-four outcome (2026-09-03)

v3.6 PAIR closed as a diagnostic branch: Phase 0 integrity 9/9 PASS; Phase 1
red light (accuracy 0.6454, no frontier improvement); Phase 2/3 not run.
Incumbent remains PICS_joint_relabel. Results: `results/v36_pair_probe.json`,
`results/v36_pair_predictions.jsonl`, `results/v36_pair_dataset.jsonl`,
`results/v36_pair_integrity.json`.

## Tree twenty-five, before building the fix, measure the ceiling: oracle the intervention first

**Status 2026-09-03: opened and closed at Phase 0, v3.7 SHIFT diagnosed, no
formal version.** Pre-registration `docs/v3_7_shift_preregistration.md`. The
plan was target-domain-aware calibration (specialist router + importance
weighting) on top of the frozen PAIR score. Before building any of it, two
target-label oracles measured what perfect calibration could ever deliver:

    can perfect target calibration rescue the frozen ranking?
        no -- with held-out labels choosing per-family thresholds, the global
        oracle reaches only bcov 0.041 under CHR<=0.10 (18 commits, all
        DENOISE); allowing held-out labels to pick a convex mixture of source
        experts reaches bcov 0.180 / gain 0.023
        -> both far below bcov>=0.30 and gain>=0.10; safety constraints are
           NOT the binding side (both oracles sit at CHR 0.00-0.05, pme 0);
           the ceiling is the value extractable from the candidate pool x
           the frozen ranking itself

    does calibration transfer between similar sources?
        ranking transfers (B&S AUROC >0.72 on most pairs, 0.99 on Oil) but
        thresholds do not (cross-source CHR up to 0.67 into ETTh2);
        fingerprint similarity does not predict transfer (r=-0.054) -- and
        the fingerprint itself collapsed to one dimension (Crypto
        missingness, z~8200)

**New rules.** (1) Run the target-label oracle BEFORE building any
calibration machinery: if perfect cheating cannot reach the gate, the
mechanism cannot either, and the phase costs 10 seconds instead of a day.
(2) When oracles pass safety trivially but fail liveness, the bottleneck is
the candidate pool and its ordering, not the risk controller -- stop
designing verifiers. (3) Five closed branches (v3.2-v3.7: threshold
reselection, shadow certificates, action-conditioned outcomes, within-window
pairwise ranking, target-domain calibration) exclude the SELECTION and
CALIBRATION routes on frozen scores. **Correction 2026-09-03 (v3.8 Phase 0,
`results/v38_oracle_replay.json`, all three replays bit-exact): the earlier
wording "the candidate-pool oracle ceiling is bcov 0.18 / gain 0.02" was
wrong — that is only the ceiling of the frozen PAIR ranking plus grid
thresholds. The unrestricted candidate oracle over the pool is bcov 0.6591 /
gain 0.1969 / CHR 0 (290 commits). Corrected statement: 冻结 PAIR
排序/校准路线被排除；尚未排除重新定义候选语义和构造可识别高精度候选。**

### Tree twenty-five outcome (2026-09-03)

v3.7 SHIFT closed at Phase 0 as a diagnostic branch: red light, Phase 1/2
not run, no smoke350, no API, no DOCX. Incumbent remains PICS_joint_relabel
(bcov 0.2727, CHR 0.2053, pme 0.0091, gain 0.0919, damage 0.0402). Results:
`results/v37_shift_headroom.json`, `results/v37_calibration_transfer.json`.

## Tree twenty-six, when two defect semantics share one mask, split the candidate semantics before scoring

**Symptom.** The same operator family is harmful under one proposer and
beneficial under another, and no threshold on either side fixes it. For
IMPUTE the mask mixed two different defects: actual NaN (a deployment-visible
fact) and finite flatline (an interpretation). The audit that separates them
(`results/v38_impute_mask_audit.json`) shows they are different populations:
actual_nan_only candidates are b&s 0.812 / harmful 0.188, finite_flatline
candidates are b&s 0.218 / harmful 0.782. The v3.6 PAIR arm's harmful IMPUTE
commits sit 16/23 in the flatline layer — mask mixing drove them — while
PICS's harmful IMPUTE commits sit 19/27 in the actual-NaN layer: filling a
real NaN can still harm, so the two routes do not share a failure cause and
neither's fix transfers to the other.

**Probe order.** (1) Rebuild masks from the raw corrupted series, never from
the materialized probe series — materialize_for_probe forward-fills and
erases the very NaN provenance being audited (531 raw-NaN candidates, 275
fully erased after materialization). (2) Stratify candidates into mutually
exclusive mask-origin layers before reading any metric. (3) Attribute the
harmful ledger of every arm to layers before proposing a fix. (4) If a
certificate operator is the fix, freeze its coverage tiers before seeing
labels, and measure a coverage-potential rule for any rescue branch at the
same time.

**New rules.** (1) A certificate can buy safety without buying coverage:
IMPUTE_EXPLICIT with frozen gap tiers (4/8/16) achieved observed drift
exactly 0 and harmful 0.068 on actual-NaN windows, but b&s only 0.429,
because every 25–63-length injected block abstains — the failure was
coverage, not precision (on the scattered windows it does fill, b&s is
0.864). (2) When the abstain distribution is bimodal (gap lengths {1,2,3}
vs {25..63}, nothing in 5–16), tiered certificates degenerate to one tier —
check the gap-length histogram before designing tiers. (3) A pool-level
oracle passing (FACT pool bcov 0.3705 / gain 0.1760 / CHR 0) does not rescue
an operator whose deployable coverage is structurally absent; headroom is
necessary, not sufficient. (4) When deleting a family from the pool, keep the
affected windows in the evaluation frame as no-commit placeholders — dropping
them silently shrinks the denominator and inflates bcov (0.449 -> 0.370 here).

### Tree twenty-six outcome (2026-09-03)

v3.8 FACT-IntroAct closed at Phase 1 as a diagnostic branch: red light,
operator retired, Phase 2A/2B not entered, no smoke350, no API, no DOCX.
Incumbent remains PICS_joint_relabel. Results:
`results/v38_explicit_impute_probe.json`,
`results/v38_explicit_impute_records.jsonl`,
`results/v38_oracle_replay.json`, `results/v38_impute_mask_audit.json`.

## Tree twenty-seven, when a gate number mixes coverage with precision, split the metric before reading the verdict

**Symptom.** A single rate is quoted as the verdict on an operator, but the
denominator mixes windows where the operator acted with windows where it
abstained. In v3.8 the gate number g1 = 76/177 = 0.429 read as if the
certificate operator were imprecise; in fact it is window-level beneficial
COVERAGE. Over the 88 scattered windows where IMPUTE_EXPLICIT actually
filled, 76 were B&S and 12 harmful: action-conditional B&S precision 0.864,
action-conditional CHR 0.136. The 89 missing_block windows (gap 25-63) all
abstained. "b&s 0.429" and "precision 0.864" are both true and answer
different questions.

**Probe order.** (1) For any operator verdict, first partition windows into
acted / abstained / not-applicable. (2) Quote precision and CHR only over
acted windows; quote coverage over applicable windows; never let one number
carry both. (3) When an operator fails, state which axis failed: v3.8's
correct reading is 短缺口算子保留，长缺口适用性失败 — an applicability
failure, not a precision failure, and not a refutation of the FACT semantic
split. (4) A rescue branch must target the failing axis: long-gap coverage
needs a long-gap proposer (v3.9 BRIDGE), not a precision fix.

**New rules.** Every operator report from v3.9 onward carries five separate
quantities: proposal/applicability coverage; action-conditional B&S
precision; action-conditional harmful rate/CHR; beneficial coverage (bcov);
abstention rate. An abstention-heavy operator can be simultaneously safe,
precise, and useless — check all five before retiring or rescuing it.

### Tree twenty-seven outcome (2026-09-03)

Metric-semantics correction only; the v3.8 red-light verdict stands
unchanged. Recorded in `docs/v3_9_mirage_preregistration.md` §1 and the
v3.8 row of `docs/version_ledger.md`. No DOCX update (not a positive
method result).

## Tree twenty-eight, when the risk signal predicts the bad model's harm but not the good model's, the signal is the ceiling

**Symptom.** A candidate pool has real value (joint oracle bcov 0.5545 / gain
0.195 / CHR 0), a strong proposer exists (TS-ICL: 75 B&S of 89 long-gap
windows), and a cheap risk score separates the harmful outputs of the WEAK
proposer (OpenFIM: seam AUROC 0.757) — yet every calibration fold reports
no_calibrated_point and the gate fails. Diagnosis: the deployable signals
(posterior width, cross-model disagreement, boundary seam, bridge deviation)
predict harm only where the model is grossly wrong (OpenFIM CHR 0.629); on
the strong proposer whose harm rate is already low (TS-ICL CHR 0.157) the
same signals are at or below chance (R AUROC 0.461, width reversed at
0.325). The 14 harmful TS-ICL windows are invisible to every
deployment-available view.

**Probe order.** (1) Report signal AUROC PER PROPOSER, never only pooled —
pooled discrimination can be carried entirely by the worst model. (2) Test
whether shrinkage fixes harm before blaming the gate: eta 0.5 vs 1.0 on
TS-ICL leaves 75/14 unchanged, only gain drops — the mixture operator was
never the problem. (3) Check calibration feasibility directly: if no grid
point on the training sources reaches the CHR upper bound, no threshold
search on the same signals can rescue the deployment rule. (4) "The model
whose harm is predictable has no value; the model with value has
unpredictable harm" is a terminal diagnosis for that signal family — stop,
do not tune.

**New rules.** (1) A proposer with CHR 0.157 cannot be deployed ungated
against a CHR<=0.15 bar, and cannot be gated by signals that do not see its
failures. (2) Headroom in the candidate pool (Phase 1 G2 passing) plus
signal failure (Phase 2) means the open route is a NEW source of per-window
risk evidence, not more thresholds, more mixture weights, or more
uncertainty views of the same models. (3) One pre-registered rescue branch
(isotonic head + source-group DRO, one training) is enough to confirm the
signal family is exhausted — v3.9 used it and stopped.

### Tree twenty-eight outcome (2026-09-03)

v3.9 MIRAGE-TS closed at Phase 2 as a diagnostic branch: red light, Phase 3
not entered, no smoke350, no API, no DOCX. Incumbent remains
PICS_joint_relabel. Results: `results/v39_longgap_probe.json`,
`results/v39_longgap_oracle.json`, `results/v39_bridge_probe.json`.

## Tree twenty-nine: the training-distribution extension that cost the evaluation domain

**Symptom.** A learned per-window risk model scores 0.865–0.902 harmful
AUROC on held-out *sources* of its own training corpus, then collapses to
0.529 — chance — on the frozen evaluation windows, while the simplest arm in
the ablation (thirteen hand-specified structural scalars, 68k parameters)
holds at 0.877 on the same frozen windows. Coverage collapses with it: 16 of
75 beneficial windows retained against a bar of 55.

**What it is not.** Leave-one-source-out already passes, so this is not
cross-source generalisation in the v3.6 sense. The harm side is clean (0–2
harmful commits of 14), so it is not a safety failure. The bigger model
contains the smaller model's features, so it is not capacity. Rule these out
by checking, in this order: checkpoint-to-fold correspondence, freeze order,
label and hash replay, support drift, the normalisation call sites, split
keying, and the metric denominators. In v4.0 all seven came back clean and
the frozen labels replayed exactly (75/14), which is what forced the search
onto the input distribution.

**What it is.** Compare the *training* corruption parameters against the
*evaluation* corpus's injector, not against each other's summary statistics.
v4.0's bank drew `missing_block` gaps spanning 5–50% of the window because
the pre-registration deliberately widened the training distribution "to
teach the critic about gaps far longer than anything the evaluation corpus
contains". The frozen injector writes 5–12%. Two thirds of the bank's
long-gap mass therefore sat outside the evaluation domain: mean gap 24.5% of
T against 8.9%, and the proposer's realised gain ~3.6x larger. The gain
quantile head learned the wrong scale, so the deployment rule's `q10 > delta`
clause — not the harm probability — abstained on 72 of 89 windows, and the
sequence/TSFM/delta branches, fitted on large-gap structure, drowned out the
structural scalars they were supposed to augment.

**Diagnostic move that localises it in one query.** Take the evaluation
population and the closest analogue cell of the training corpus, and print
the per-feature means side by side together with the label's distribution
(p10/median/p90 of the realised gain). A monotone shift across every
gap-derived feature plus a shifted gain scale is the signature. If instead
the features match and only the model's outputs differ, the problem is the
model, not the corpus.

**New rules.** (1) A deliberate training-distribution extension is a
testable design decision, not a free hedge: report the overlap between the
training corruption parameters and the evaluation injector's *before*
training, and keep an in-domain stratum large enough to calibrate on. (2)
When an ablation's simplest arm survives a distribution shift that the full
arm fails, read it as evidence about the representation, not about capacity
— explicit low-dimensional features carry their own domain, learned
high-dimensional ones inherit the training corpus's. (3) A quantile head
that predicts a *scale* transfers only as far as the scale does; a rule
thresholded at `q10 > 0` inherits every bias in that scale, so report which
clause of a multi-clause gate is binding before blaming the classifier.
(4) Expanding the corpus along the axis that is already mismatched does not
address a mismatch — state that prediction before spending the rescue, and
record it either way.

### Tree twenty-nine outcome (2026-09-04)

v4.0 COUNTERACT-TS closed at the Phase 2 decision gate as a diagnostic
branch: red light, Phase 3 not entered, no smoke350, no API, no DOCX.
Incumbent remains PICS_joint_relabel. The single pre-registered rescue was
triggered on its stated condition and its 21,000-episode bank was built and
verified, but the retrain did not run before the node was shut down; the
prediction recorded before building it is that more data drawn from the same
mismatched distribution will not close the gap. Results:
`results/v40_frozen89_decision.json`, `results/v40_critic_lodo.json`,
`results/v40_critic_ablation.json`.

## Tree thirty: matched mask geometry does not buy matched risk separability

**Symptom.** A risk model scores AUROC 0.877 on the frozen decision set and
0.66-0.71 on a calibration corpus that was deliberately re-selected to match
that decision set's gap geometry. Thresholds calibrated on the matched
corpus are *more* conservative than the ones calibrated on the unmatched
corpus, and several leave-one-source-out folds return no calibrated point at
all.

**Why the instinct is wrong.** Tree 29 ended with the rule that a training
distribution has to overlap the evaluation domain, and the obvious next move
is to re-select the corpus until the mask statistics line up. v4.1 did
exactly that and the alignment is genuine: median gap fraction 0.084 against
the frozen frame's 0.090, support ratio 0.914 against 0.910, one run per
window and both anchors present in every case, density-ratio ESS 958 out of
1,043 rows. On every mask descriptor the two populations are the same
population. The harm rate is not: 0.217 against 0.157, and the ranking
AUROC falls by about 0.19.

**The arithmetic that turns this into a hard stop.** A conditional-harm bound
of the Clopper-Pearson form has a floor set jointly by the base rate and the
ranking. At harmful rate 0.217 and AUROC ~0.68 over ~860 calibration rows,
the lowest reachable CP95 upper bound is 0.130-0.154 depending on the fold.
A pre-registered constraint of 0.15 is therefore satisfiable in three folds
and structurally unsatisfiable in the other three -- and in v4.1 those three
held 51 of the 75 beneficial windows. The selector was not mis-tuned; it was
asked for a point that does not exist in its feasible set.

**Rule out the cheap explanation first.** Before concluding that two matched
populations really differ, bootstrap the decision set's AUROC. v4.1's
frozen-89 estimate rests on 14 positives, which is exactly the regime where
a flattering number is expected; the bootstrap CI95 came back
[0.7647, 0.9640], with P(AUROC <= 0.71) = 0.004. Only because the lower
bound cleared the calibration range could the difference be called real. Had
the interval overlapped, the correct reading would have been that the 0.877
was noise and the whole premise of the round was unfounded.

**Diagnostic move.** Report, per fold, four numbers together: calibration
size, base harm rate, ranking AUROC on the calibration population, and the
minimum achievable CP95 upper bound over the threshold grid. The last column
tells you immediately whether a fold's failure is a tuning problem or an
infeasibility, and no amount of re-weighting changes an infeasibility.

**New rules.** (1) Covariate matching on mask geometry is necessary but not
sufficient; state separability, not just geometry, as the transfer claim
being tested. (2) Before spending a pre-registered rescue branch, check that
its stated precondition actually holds -- v4.1's retrain branch was
conditioned on insufficient samples, and the samples were ample, so invoking
it would have been a search dressed as a plan. (3) A risk-controlled
operating point cannot strictly dominate both an ungated proposer and an
over-abstaining one on the (coverage, harm) plane: they sit on opposite
sides of every feasible point, so write the Pareto gate against the frontier
or against one named reference, not against both as a conjunction.
(4) An oracle sweep over an 89-window decision set with 14 positives will
always display an attractive frontier point; it bounds what is achievable
only if some deployment-legal calibration can reach it, and in v4.1 none
could.

### Tree thirty outcome (2026-09-04)

v4.1 MASK-COUNTERACT closed at Phase 1 as a diagnostic branch: 3 of 8 gates,
Phase 2 not entered, no smoke350, no API, no DOCX. The one positive finding
is that removing the gain-quantile veto alone -- changing nothing else --
lifts retained beneficial windows from 14 to 24 at CHR 0.040, confirming
v4.0's mechanism diagnosis while leaving the coverage bar far away.
Incumbent remains PICS_joint_relabel. Results:
`results/v41_selector_arms.json`, `results/v41_mask_shift_audit.json`.

## Tree thirty-one: a portfolio of homogeneous proposers is a portfolio of one

**Symptom.** Two rounds of single-action gating have failed, and the natural
next move is to widen the action set: let the agent choose among every
applicable repair rather than accept or reject one. The candidate pool
already holds nine long-gap proposers, so the headroom looks free.

**Measure it before training anything.** The question is not whether a
selector can rank actions, it is whether the pool contains a better action
to rank to. Three set-arithmetic counts answer it, and none of them needs a
model: how many windows carry at least one beneficial-and-safe action; how
many of the windows where the best fixed proposer *harms* have a safe
alternative; and how far the union of beneficial windows exceeds the best
single proposer. In v4.2 those came back 81/89, **6 of 14**, and **+6** over
TS-ICL's 75 -- against pre-registered bars of 80, 10 and +10.

**Read the oracle's own choices.** When an oracle free to pick any action
picks the incumbent 75 times and everything else 6 times between them, the
alternatives are not alternatives. v4.2's nine proposers are all
single-series interpolation or foundation-model infill; they read the same
information, so they succeed and fail on the same windows. Diversity of
implementation is not diversity of mechanism, and only the second one buys
portfolio headroom.

**The unrepairable set is the diagnosis, not the residue.** The eight windows
where no action is beneficial-and-safe turned out to be exactly the eight
harmful-TS-ICL windows lacking an alternative -- all `missing_block`, six of
them in a 40-channel coupled rate curve whose sibling channels no proposer
reads. Characterise that set by source and defect kind before writing any
conclusion: it names the mechanism the pool is missing, which is the actual
deliverable of a failed headroom check.

**Budget constraints that no new action can touch.** v4.2's integrated
oracle failed exactly one metric, protected mis-edit, at a value *identical*
to the baseline's. Adding actions on contaminated windows cannot remove an
edit the incumbent already made on a protected one. Before spending a round
on additions, separate the gates into those an addition can move and those
that require removing or re-deciding existing commits; v3.9's frozen budget
had already said the protected term has negative headroom, and v4.2
rediscovered it the expensive way.

**New rules.** (1) A portfolio round must pass a mechanism-diversity check
before a selection round is funded: report the oracle's per-action pick
counts and the marginal beneficial windows each proposer contributes over
the best fixed one. (2) When integrating candidates whose gains live in
different pools, assert that every oracle pick has a gain record; v4.2's
integrated numbers silently describe a TS-ICL-only oracle because six picks
had none, and the limitation had to be declared rather than discovered
later. (3) An incremental gate set must be split by reachability: adding
actions moves coverage and gain, and cannot move protected mis-edits at all.

### Tree thirty-one outcome (2026-09-05)

v4.2 PORTFOLIO-ACT closed at Phase 0 with 1 of 4 continuation gates; Phase 1
never started, per the pre-registered stop rule. The carried-forward result
is Phase 0-A: replaying v4.1 arm B into v3.9 D under the first-commit
protocol adds 24 beneficial-and-safe windows with zero conflicts and lifts
beneficial coverage to 0.3205, while still missing the gain-sum and harmful
targets. Incumbent remains PICS_joint_relabel. Results:
`results/v42_phase0a_integration.json`,
`results/v42_phase0b_portfolio_oracle.json`.


## 2026-09-14 v4.3：时间与 worker 审计入口

先看 `docs/v43_entrypoint_audit_20260914.md`。新增检查顺序：原始row/time -> split完整读取区间 -> delayed availability -> NaN/共同mask -> candidate写入 -> worker实际输入hash/单位/revision -> future ->完整分母。旧 `downstream.make_pairs` 会删除NaN，不作为v43入口。

若 residual 外层证据异常好，先冻结块位置，用 `test_residual_leakage.py` 对外层真值毒化，验证每个内层基础预测都看不到外层块。若历史验证异常好，检查as-of前缀重建和协变量晚发布遮挡，不能裁剪当前已修复结果。若所有候选预测相同，检查请求input hash与candidate ID；缺行、错单位、NaN输出整批失败，不回KEEP假装成功。

若沙箱里bootstrap PID缺失或nvidia-smi失败，先在主机可见范围只读检查。2026-09-14主机PID和GPU均正常；默认tmux socket一度报server exited，显式 `/tmp/tmux-1000/default` 能看到原会话。这类可见范围错误不能触发重装或driver操作。

如果pilot queue blocked，读 `results/v43/pilot_queue_status.json` 及其queue_directory中的原始日志；如代码/config变化，重新审计并重跑gate后新建队列，不绕过hash检查。已写出的失败run保持不变。


2026-09-14 18:48 工程复核追加：修复残差PCA后附加缺失指示可能超过8维的问题，新增测试检查实际回归输入维度；最终CPU测试40项通过（0.96s），见 `logs/v43/contracts/20260914T104754.619288Z/`。旧39项日志保留；真实模型pilot仍待依赖，未产生方法晋升。


## 2026-09-14 21:00 post-hoc：真实 P1 pilot 完成

32 origins（20 train / 12 dev）、L512/H32、64 次真实 TS-ICL 插补和 96 次 Bolt 预测全部完成；43 项 CPU gate 通过，独立原始结果重算通过，未读 calibration/test。运行 21.794 秒，最大 GPU 分配 710,672,896 字节。KEEP / SINGLE / COV 来源宏平均 MASE 为 1.322762 / 1.316489 / 1.228219；COV 宏平均 MAE 反而变差，两插补臂各 15/32 个 origin task harm，无 CI。仅为接口与开发诊断，正式 A0–A5/H96/H192 未运行，PICS_joint_relabel 不变。首轮导入失败和可选 Chronos-2 TLS 失败保留。证据与原始结果入口见 `docs/v43_pilot_report_20260914.md`、`docs/v43_pilot_evidence_20260914.json`；下一步补长来源、接正式强对照及 A5 静态规则。

入口隔离排障：src/introact_ts/__init__.py 的旧 Agent/Profile eager import 会把 core statsmodels 带入官方 TS-ICL 环境；应按需导出并把必要根入口纳入 worker hash，不能向模型环境硬补 core 栈。


## 2026-09-14 P2 首批开发配置冻结（未运行结果）

P1 已完成且独立复核通过后，新增 `configs/v43/p2_first_dev.yaml`、`cli p2` 与 A4/A5 正式接线。只取 ETTm1 / Solar / USTS 的 dev 原始区间，分别 14 / 11 / 1 个不重叠基础 parent；两个 horizon 96/192 及 raw、target block 10%、全部 siblings shared block 10% 共 156 个 episode。这些变体不是 156 个独立样本；全历史 ridge 读取区间在 dev 内重叠，正式推断还须按更大依赖块处理。

Solar 复用本机文件，与论文作者仓库 Git blob 完全一致。只按原行号保留同步时间；来源说明为 2006 年 Alabama 137 路 10 分钟光伏，压缩文本无原始时间戳，不能伪称已恢复绝对日历或发布延迟。库存只统计行宽，不解码 heldout 数值。来源证据见 `docs/v43_p2_source_provenance_20260914.json`。

首批重点检验长缺口的新信息收益，以及原始/共享缺失的保护与负对照；5%/点缺失/spike/valid-event 标注和其他来源为后续矩阵，不能把首批当完整污染实验。固定通道0、seed101、L512、缺口[230,281)、不按标签挑窗口。只要求 TS-ICL/Bolt 两个已通过模型，保持 batch1/GPU单任务。

执行臂为 A0 native/ffill、A2 single、A3 官方全合法covariates、A4当前context及同split全合法历史ridge、A5严格嵌套OOF静态eta。A4历史只读 dev 起点到当前context起点，再拼当前dirty输入，不重新打开当前gap真值；这是额外历史信息轨道。A5保存七类真实遮挡输入，支持不足明确回到同origin已验证A2，真实worker缺行/失败仍报错；eta平局取0。候选去重只在同episode、同horizon、完整输入hash下进行并保存alias，所有候选完成真实预测后才读future。

A1仍为blocked_adapter：`experiments/v39_phase0_replay.py:321` 强依赖771个冻结parents，`:450`按历史候选标签拟合LODO PICS并重放；源码存在不等于可对本次新时间区间部署。该参照待合法适配，不把旧分数贴到新UID，也不把缺失参照填0。原生多变量任务模型尚未运行。A9只对本轮完整已执行候选集生成开发上界，名称明确为A9_ORACLE_AVAILABLE，不冒充全候选上界。

新增测试覆盖gzip越界标签不可解码、父区间共享、shared辅助遮挡、全历史不重读gap、A5不适用回A2、漏真实预测报错、ridge观测值不变及eta平局0。运行以新配置绑定的CPU gate为前提，结果产出前不作方法成功结论。PICS_joint_relabel不变，不将规划写入DOCX成果。


## 2026-09-14 21:20 post-hoc：P2首批真实实验完成

51项CPU测试通过，H96/H192、三个dev来源、26个基础parent/156变体，512次真实插补、580次去重预测、1092份任务标签全部完成，独立原始结果复核通过；耗时251.386秒，峰值GPU分配1.90GB。KEEP/A2/A5来源宏平均MASE为1.258454/1.157005/1.157187，无可靠确认性CI。A5仅4个ETTm1 parent产生8个修正变体，未来任务2好6坏；其真缺口重建6好2坏。加入A5后，相对已含简单跨通道强对照的oracle增量为0，不能晋升残差方法或进入更大A8训练。A1与原生多变量对照待适配，其他污染条件/来源尚未覆盖；calibration/test读取仍为0，PICS_joint_relabel不变。全部状态、误差分歧与成本见docs/v43_p2_report_20260914.md和docs/v43_p2_evidence_20260914.json。
