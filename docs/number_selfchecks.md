# Self checks on every number that enters the paper

Standing rule from 2026-08-23. A number is not cleared for the paper by being
correct. It is cleared by being the number the sentence around it needs. This
project has produced several numbers that were arithmetically right and
argumentatively wrong: a normalisation scale inflated by a level displacement, a
structural measure with a second uncalibrated path, an edit count using the
permissive definition and therefore high, a candidate harm rate pushed up by the
protected layer's share. None of those is visible in the output file. All of
them are visible in the code that produced it.

So every number that reaches the paper is checked against the code that made it,
and against three questions.

| # | question |
|---|---|
| 1 | What is the denominator. Which samples is it computed over, which are excluded, and is the exclusion correlated with the effect being measured |
| 2 | Is a subgroup driving it. Split by stratum, by defect type and by dataset, does the conclusion survive |
| 3 | What else would produce this number. Name the competing explanation and say what rules it out |
| 4 | Cross reconcile. Make the number close arithmetically against a second number from an independent source. A wrong number is usually self consistent inside its own context, and only disagrees when set against another one |

Below, one entry per number, with what the checks removed.

## Order flip rate, reasoning disabled, 0.508

**Denominator.** 59 of 60 pair dimensions. The one dropped was an exact tie in
one order, excluded by a rule fixed before the run. Unscorable rate zero, so no
pair was silently lost.

**Subgroup.** Split by dimension: 0.467, 0.467, 0.733, 0.357. Every dimension is
far from zero, so no single dimension carries it.

**Competing explanation.** A flip rate near one half could mean the two windows
were genuinely equal rather than that the judgment was unstable. Ruled out by a
second measurement: 73.6 percent of votes went to whichever option came first,
median 76.0. If the pairs were ties the first position would not win three times
in four. Position bias produces both numbers, indifference produces only one.

## Order flip rate, reasoning enabled, 0.000, **rejected**

**Denominator.** 16 of 24 pair dimensions. **Unscorable rate 0.333.** This is
where the check bites: the exclusion is not random.

**Competing explanation, and it wins.** Zero flips could mean stable judgment or
it could mean the unstable cases were dropped. Reading the raw replies decides
it: a dropped generation returns `finish=length` with 2048 reasoning tokens and
empty content, while the same pair's other generation returns `finish=stop` with
416 reasoning tokens and a clean answer. Longer reasoning means harder pair, and
longer reasoning is what hits the ceiling. The survivors are the easy pairs.

**Conclusion.** The zero is survivorship bias and is not reported as stability.
Both numbers go into the paper together, never the flip rate alone.

## Blockable window share, **corrected**, first error this rule caught in the text

**The error.** 19 percent was written into section 4.1.3 as a property of the
valuation family. It is not. It is a property of one corpus.

**How check one found it.** The denominator question was asked of a different
number, the LTSV scored window count of 1246 against a corpus of 2000. The
arithmetic was required to close: 1788 blockable times 0.7 is 1251.6 against an
actual 1246, and 4984 training blocks over four blocks per window is exactly
1246. It closed, so there was no third source. But closing it required the
blockable count, and that count was 1788 of 2000, so **10.6 percent
unblockable, not 19**.

**The relation, which is what should have been reported.** Unblockable share
equals the contaminated stratum's share of the corpus times the fraction of
defect kinds that write NaN, which is two of seven.

| corpus | contaminated share | predicted | measured |
|---|---|---|---|
| heavy | 0.667 | 0.1905 | 0.1905 |
| xl | 0.3700 | 0.1057 | **0.1060** |

**What the paper says now.** The relation, with both measurements, rather than
either number alone. The argument it supports is unchanged and is in fact
stronger: the valuation family's blind spot grows with the corpus's missing data
content, which is predictable rather than incidental.

**Why this is recorded rather than quietly fixed.** It is the first time the
denominator check caught something already in the text. The number was
arithmetically correct on the corpus it came from and wrong for the sentence it
was placed in, which is the exact failure mode the rule exists for.

**And it is why check four exists.** The 19 percent was self consistent in its
own paragraph and would have stayed there indefinitely. It only broke when it
was required to close against an unrelated number, the LTSV scored window count,
which came from a different script in a different environment. Reconciliation
against an independent source is now a standing requirement rather than
something that happened once.

## Changepoint layer, 180 of 1600 under the rank criterion

**Denominator.** The pool after the rare valid layer is taken, since assignment
order is fixed and no window enters two layers.

**Subgroup.** Both families fill their quota with zero shortfall, 90 each,
against the previous criterion where four of six datasets returned nothing.

**Competing explanation.** A rank always returns something, so a full layer is
not evidence that the layer is meaningful. Not ruled out by the count, and
deliberately so. What settles it is the `t` distribution of the selected layer
beside the injected level shifts, which is reported rather than assumed.

## Hard layer, 210 windows, all industrial, **flagged**

**Subgroup, and it fails.** The hard layer under the mixed corpus contains zero
financial windows.

**Competing explanations, both still live.** Either financial windows are
genuinely easier, or `_difficulty` mismeasures them. The measurement favours the
second: financial difficulty has median 0.0105 against industrial 0.1905, and a
maximum of 0.3224 against 0.7759, an order of magnitude apart. The statistic is
`1 - 0.5 * seasonal - 0.5 * memory`, and a price series near a random walk has
short lag autocorrelation close to one and spectral power concentrated at the
lowest frequency, so both terms subtract and the window reads as easy. A random
walk is the canonical hard forecasting case, so reading it as easy is a defect
of the statistic rather than a property of the data.

**Not fixed here.** Changing `_difficulty` changes a selection criterion, which
requires pre registration before the counts under it are seen. The finding is
reported and the decision is open.


## Hard layer under the new criterion, 210 windows, 110 financial and 100 industrial

**Subgroup, and it now passes.** The old statistic gave zero financial windows.
The new one gives 110 of 210. The change was made because the statistic was
backwards on random walks, not to obtain this split, and the entry above on the
criterion records that ordering.

**Denominator.** The pool after rare_valid and changepoint are taken, since
assignment order is fixed and hard is third.

**Competing explanation.** A near even split could mean the criterion is
balanced, or it could mean the within family rank forces it. It is the second,
by construction, and that is stated rather than presented as a finding. The
quota is split in proportion to the pool, so any criterion would produce roughly
this split. What the criterion decides is *which* windows, not how many per
family, and the evidence for it being the right criterion is the control cases,
random walk 0.9684 against pure sine 0.0000, not the layer composition.

## Rare valid layer, 201 of 210, shortfall 9

**Denominator.** The over drawn base pool, not the corpus, since selection runs
before assembly.

**Subgroup, and it fails mildly.** Qualification rate runs 0.075 to 0.173 across
industrial datasets and 0.015 to 0.043 across financial ones. The largest pool,
720 windows, has the lowest rate at 0.015.

**Competing explanation, ruled out.** A shortfall usually means the quota
exceeded a small pool. Ruled out by the rate table: the biggest pool has the
worst rate, so it is the criterion's yield and not the pool's size. The
mechanism is criterion A3, which requires the window to return to baseline, and
financial series trend so their ends disagree more often. Reported, not
corrected.


## Valuation family scored window count, 1246, five methods

**Denominator.** The training split of the blockable windows of the xl corpus.
Identical for every method by construction, since all five read one exported
npz and score `wid[partition == 0]`.

**Subgroup.** Not applicable, the count is a set size rather than a rate.

**Competing explanation.** Five equal counts could mean the methods agree or it
could mean they were computed from one cached array and the equality is
trivial. It is closer to the second and that is the point: the columns of the
main table must share a denominator, so this number being trivially equal is the
requirement rather than a finding. What is checked is that no method silently
scores a subset.

**Cross reconciliation, check four.** Three independent routes had to close on
the same number.

| route | value |
|---|---|
| LTSV, an independent script in the curation environment | 1246 |
| TimeInf, Data-OOB, Data Shapley, KNN Shapley, in the dataval environment | 1246 each |
| 4984 training blocks divided by four blocks per window | 1246.0 |
| 1788 blockable windows times the 0.7 training fraction | 1251.6 |

The window id **sets** were compared, not only the counts, and all five are
identical. The fourth row differs by 5.6 because the split is drawn by window
rather than by proportion, which is the expected sampling difference and not a
fourth source.

## Selection arm returning zero, caught by a smoke run

Not a paper number, recorded because it is the failure mode the rules target. A
smoke run of the main table on the `small ett` corpus, against score files
computed on `xl mixed`, produced an LTSV row retaining zero windows with every
stratum retention at 0.000. No window id overlapped, so the arithmetic ran on an
empty set and returned a table of zeros rather than an error.

A row of zeros reads as a result. `run_main.py` now refuses to proceed when
fewer than five percent of the corpus carries a score, since the expected
overlap is the training fraction times the blockable share and is far above
that floor.


## Valuation family retention by layer, **first reported wrong, corrected**

**The error.** I reported that the protected layers were retained at 0.57 to
0.67 against a corpus share of 0.52 and concluded the protocol's prediction did
not hold. Both the numbers and the conclusion were wrong.

**Check one, which I skipped and should not have.** The selection fraction is
applied to the whole corpus, per `docs/valuation_family_protocol.md`, so windows
the family cannot score occupy the denominator without occupying a place. On xl
that is `round(0.5 * 1991) = 996` places drawn from a scored pool of 1240, an
effective rate of **0.803 rather than 0.5**. Measuring every layer against 0.5
reads all of them as preferred, which is what produced the first table.

**Corrected, against the effective rate.**

| method | contaminated | clean | hard | rare_valid | changepoint |
|---|---|---|---|---|---|
| TimeInf | 0.940 | 1.035 | 1.090 | **0.908** | 1.060 |
| Data-OOB | **0.797** | 1.144 | 1.107 | **0.878** | 1.197 |
| LTSV | 0.967 | 0.985 | 0.968 | **1.163** | 1.012 |

**Against the pre registration, item by item.** It predicted retention below the
selection rate on rare_valid and on hard.

Rare valid, holds for two of three. TimeInf 0.908 and Data-OOB 0.878 sit below
the line, LTSV at 1.163 goes the other way.

Hard, **does not hold**. All three are at or above the line. Reported as not
holding, which is the branch the protocol wrote down in advance.

Data-OOB's contaminated ratio of 0.797 is the lowest cell in the table. It drops
injected windows more than any other layer, which is what it should do and which
the protocol did not predict either way.

**What the code fix was.** `run_main.py` now reports `actual_rate` and a
`retention_ratio` normalised by it, so the baseline is computed rather than
assumed by whoever reads the table.

## Selection basis, within dataset rank

**Competing explanation, ruled out by measurement.** A global z score was the
obvious alternative and it changes nothing: it is monotone, selection depends
only on the order, and the two produce byte identical selections. Measured on
all three methods rather than argued.

**What the raw order does.** Data-OOB's raw top half takes 0.000 of Crypto and
1.000 of the staircase probe; LTSV's takes 0.000 of Crypto and 0.797 of ETTh1.
Overlap with the rank basis is 0.632 and 0.779. TimeInf is barely affected at
0.956, so the problem is not universal to the family.

**Check on the fix itself.** Every dataset's ranks span 0.000 to 1.000
separately, verified per dataset, which a global rank would not produce.


## Repair accuracy, RMSD to normalised RMSD, **caught on the second seed**

**The error.** The matrix changed repair from a ratio to a distance, and a plain
root mean square distance carries the data's units. On the mixed corpus that put
SCREEN at 2109 against no action at 1382, which reads as SCREEN being worse than
doing nothing.

**How it survived the smoke test.** The smoke ran `--source ett`, where every
window is transformer telemetry and the units are uniform, so the column looked
fine. The corpus the paper uses is `mixed` and spans a bitcoin price near 26000
beside a rate near 3.4. **A口径 change has to be smoked on the corpus it will
run on, not on the convenient one.**

**The fix, and why it is the same fix as twice before.** Each window's distance
is divided by that window's own blockwise robust scale before averaging. This is
the third time on this project that a quantity carrying units had to be made
scale free before aggregation: the changepoint criterion, the valuation family's
selection basis, and now this. The common cause is the corpus being of mixed
provenance, and the common fix is to normalise or rank inside the homogeneous
unit before merging.

**Verified on the corpus it will run on.**

| row | nRMSD | old RMSD |
|---|---|---|
| oracle | **0.0000** | not run |
| MTCSC | 1.2174 | 797.71 |
| SCREEN | 1.2498 | 2109.31 |
| no action | 1.2671 | 1381.99 |
| IMR | 1.3114 | 392.01 |

The inversion is gone. IMR still sits above no action and that one is real: it
edits almost every window and its damage rate is 0.8587 with a mis edit rate of
0.9600.

**Aggregation also changed.** Per window normalisation then a mean over windows,
rather than pooling squared error over points. Pooling would weight a long
window more, and RESEGMENT produces windows of unequal length. Same reason the
valuation family's window score is a mean and not a sum.

## The three seed main table, and two things the reconciliation found

Run 2026-08-26 over seeds 0, 1 and 2 at xl on the mixed corpus, code hash
`1f6d57bb1a15e4a0`. Aggregated by `experiments/aggregate_seeds.py`, reconciled
against the flushed per window traces by `experiments/reconcile_traces.py`,
and the two arm comparison tested by `experiments/arm_significance.py`.

### Check four, the cross reconciliation, and what it caught

Every column recomputed from the JSONL agrees with the table to floating point
**except the damage rate**, which disagreed by up to 0.32 on `spec_veto`. That
is far too large to be rounding, so it was traced rather than explained away.

**The cause.** The table measures damage with `audit._nmse`, the traces store
`run_main._dist`. The two differ in how they treat a non finite point. `_nmse`
replaces it with the series median before measuring, `_dist` drops the
difference. Under a missing kind of contamination that difference is not
cosmetic. Measured on the untouched corpus:

| contamination | n | median `_dist` to clean | share exactly zero |
|---|---|---|---|
| missing_block | 106 | 0.00000 | **1.000** |
| missing_scattered | 106 | 0.00000 | **1.000** |
| level_shift | 105 | 2.32943 | 0.000 |
| noise | 106 | 0.69106 | 0.000 |
| duplicate | 105 | 0.37619 | 0.000 |
| spike | 106 | 0.35411 | 0.000 |
| flatline | 106 | 0.08765 | 0.009 |

A window with a hole in it is at distance zero from the truth under `_dist`,
because the only points where it differs are the ones being dropped. So **every
imputation is damage** under that reading, and the 212 missing windows make
`spec_veto` look like it damages 0.4627 of its edits rather than 0.1465. The
accepted operators on the windows the two readings disagree about are 120
IMPUTE out of 180, which is the same fact counted a second way.

**The verdict. The table is right and the trace field is wrong.** Confirmed on
`L1_screen`, which reproduces exactly offline with no GPU: 329 edits and damage
0.6657, matching the table to the digit. On that arm the two readings disagree
on 21 of 329 windows and the cause there is level shift rather than missing,
since SCREEN imputes little.

**Consequence for the JSONL.** `dist_before`, `dist_after` and `nrmsd_after`
must not be used to recompute damage. They were added so a metric change would
not need a GPU, and for the damage column they do not deliver that. Recorded
here rather than quietly fixed, because the affected numbers are already in the
table and the fix costs a rerun.

### Check one and check two, on the repair nRMSD column

The same decomposition, applied to the column itself rather than to the
disagreement, says the column is not measuring what its name suggests.

| contamination | no action | SCREEN | spec_veto | introact | oracle |
|---|---|---|---|---|---|
| level_shift | 4.9092 | 4.8732 | 4.5432 | 4.9672 | 0.0000 |
| spike | 1.2520 | 1.0653 | 0.9138 | 0.9252 | 0.0000 |
| duplicate | 0.7469 | 0.8425 | 0.7379 | 0.7578 | 0.0000 |
| noise | 0.6391 | 0.6142 | 0.6389 | 0.6392 | 0.0000 |
| flatline | 0.3056 | 0.3670 | 0.2863 | 0.2987 | 0.0000 |
| missing_block | **0.0000** | 0.0667 | 0.0073 | 0.0029 | 0.0000 |
| missing_scattered | **0.0000** | 0.0340 | 0.0356 | 0.0006 | 0.0000 |
| **the reported mean** | 1.1172 | 1.1186 | 1.0189 | 1.0797 | 0.0000 |

**Check two, subgroup domination.** Level shift is 105 of 740 windows, 14
percent, and contributes 4.9092 times 105 over 740, which is 0.70 of the 1.1172
mean. **Sixty two percent of the column is one contamination kind.** The column
ranks arms by their level shift behaviour and reports it under a general name.

**Check one, the denominator and what it excludes.** The two missing kinds
score exactly zero for the arm that does nothing, for the reason above. An arm
is charged for the error of the values it filled in and an arm that filled
nothing is charged nothing. **The column rewards inaction on 28.6 percent of
its own denominator.**

### The introact against spec_veto comparison, tested rather than eyeballed

Three seeds are three points and a mean over them cannot establish an ordering.
The windows are the unit of evidence and both arms ran on the same windows, so
the comparison is paired window by window.

**Mis edits, exact McNemar over the four protected strata.** In all three seeds
the windows `introact` mis edits are a **strict subset** of the ones
`spec_veto` mis edits: the discordant counts are 0 against 72, 0 against 80 and
0 against 69, giving p of 4.2e-22, 1.7e-24 and 3.4e-21. This is measured, not
constructed. Nothing in the design forces it, since a refusal changes the
proposals that follow.

**Repair nRMSD, Wilcoxon signed rank, and it points both ways.**

| set | n pooled | median difference | p | reading |
|---|---|---|---|---|
| all contaminated | 456 | -0.0217 | 1.9e-13 | introact better |
| excluding the two missing kinds | 183 | +0.0067 | 0.0193 | spec_veto better |
| the reported mean | 740 per seed | +0.0453 | not tested | spec_veto better |

The sign flips with the subset, and the subset that flips it is exactly the one
check one identified as broken. **No ordering on this column may be stated in
the paper until the口径 is decided.** The mean and the median already disagree
in direction, which the level shift domination explains on its own.

## The repair nRMSD ruling, report by kind rather than as one mean

Decided 2026-08-26. The column stays, the aggregation changes. A single mean
over the injected layer is dominated by one contamination kind, and that is a
fact about the aggregation rather than about the metric, so the fix is to stop
aggregating that way. Produced by `experiments/nrmsd_by_contamination.py` from
the three seeds' flushed traces, no rerun.

| kind | n | no action | SCREEN | IMR | MTCSC | Learn2Clean | utility_only | spec_veto | introact | oracle |
|---|---|---|---|---|---|---|---|---|---|---|
| duplicate | 315 | 0.7162 | 0.7518 | 0.7842 | 0.7188 | 0.7191 | 0.6750 | 0.6729 | 0.6760 | 0.0000 |
| flatline | 318 | 0.2828 | 0.3253 | 0.5019 | 0.2876 | 0.2893 | 0.2370 | 0.2641 | 0.2722 | 0.0000 |
| level_shift | 315 | 5.0498 | 4.9905 | 4.8626 | 5.0509 | 4.9289 | 5.0695 | 4.7690 | 5.0557 | 0.0000 |
| noise | 318 | 0.6344 | 0.6142 | 0.6358 | 0.6077 | 0.5881 | 0.5681 | 0.6336 | 0.6345 | 0.0000 |
| spike | 318 | 1.4211 | 1.2688 | 0.2992 | 1.0133 | 1.2304 | 0.6949 | 0.8641 | 0.9209 | 0.0000 |
| missing_block \* | 318 | 0.0000 | 0.0488 | 0.3682 | 0.0215 | 0.0217 | 0.1646 | 0.0054 | 0.0017 | 0.0000 |
| missing_scattered \* | 318 | 0.0000 | 0.0864 | 0.3122 | 0.0223 | 0.0119 | 0.0379 | 0.0341 | 0.0009 | 0.0000 |
| **headline, sound kinds** | 1584 | 1.6161 | 1.5853 | **1.4114** | 1.5306 | 1.5463 | 1.4435 | 1.4359 | 1.5067 | 0.0000 |

Spreads are the sample standard deviation over the three seeds and are in
`results/nrmsd_by_contamination.json`. The two starred kinds are excluded from
the headline and are never ranked, for the reason in the section above: the
distance drops non finite differences, so a window with a hole sits at zero and
the arm that fills nothing wins by default.

**The headline is a window count weighted mean over the five sound kinds**,
which on this corpus is the plain mean over those 528 windows per seed. Table
note must carry the exclusion and the reason.

### The trap this column sets, and it has to be defused in the text

**The best headline nRMSD belongs to IMR at 1.4114, and IMR mis edits 0.9885 of
the protected layers and damages 0.8646 of what it commits.** It reaches that
number by rewriting almost every point, which flattens a spike to 0.2992
against no action's 1.4211 and destroys everything else on the way. A reader who
takes this column alone concludes IMR is the best repairer. The column is a
repair accuracy measured only where a defect was injected, so it says nothing
about what an arm did elsewhere, and it must never be read without the mis edit
and damage columns beside it.

### The introact against spec_veto ordering, by kind

Wilcoxon signed rank on the paired difference, pooled over the three seeds.
`n discordant` counts only the windows where the two arms produced different
results, since a window neither touched carries no evidence.

| kind | n paired | n discordant | median difference | introact better | p |
|---|---|---|---|---|---|
| duplicate | 315 | 15 | -0.1030 | 14 of 15 | 0.0106 |
| flatline | 318 | 15 | -0.0164 | 8 of 15 | 0.233 |
| level_shift | 315 | 77 | -0.5683 | 39 of 77 | 0.00258 |
| noise | 318 | 35 | +0.0075 | 13 of 35 | 0.0423 |
| spike | 318 | 41 | +0.3715 | 14 of 41 | 0.00093 |
| missing_scattered \* | 318 | 266 | -0.0241 | 266 of 266 | <1e-15 |
| missing_block \* | 318 | 7 | not tested | | too few |
| **all sound kinds** | 1584 | 183 | +0.0067 | 88 of 183 | 0.0193 |

The single aggregate hides a real split. **introact repairs level shift and
duplicate better than spec_veto and repairs spike worse**, and the pooled number
is the residue of those cancelling. The spike gap is the largest and is the one
the discussion has to account for, since a spike is what the shield's structural
condition is most likely to read as a genuine feature and refuse to remove.

Only the sound kinds are averaged into the paper's ordering, and no ordering is
stated for the two starred ones.

## The ablation ladder, seed 0, and the policy rungs collapsing onto the reference

Run 2026-08-26 by `experiments/run_ablations.py` on the main table's corpus, in
the main table's columns. Seed 0, 1986 windows, tau 0.02.

| rung | matrix | edits | mis edit rate | damage rate | nRMSD |
|---|---|---|---|---|---|
| a_no_shield | A1 | 816 | 0.2654 | 0.3958 | 1.0180 |
| b_no_structural | A2 | 305 | 0.0927 | 0.3508 | 1.0636 |
| g_no_conformal | A4 | 244 | 0.0811 | 0.2172 | 1.0646 |
| c_no_policy | A5 | 164 | 0.0695 | 0.1402 | 1.0797 |
| d_no_injection | A6 | 164 | 0.0695 | 0.1402 | 1.0797 |
| e_raw_reward | A3 | 164 | 0.0695 | 0.1402 | 1.0797 |
| f_full | reference | 164 | 0.0695 | 0.1402 | 1.0797 |

The three shield rungs separate cleanly. **The three policy rungs are identical
to the reference row in every column, to the digit.**

### Check three, is there another explanation that produces the same number

The first candidate explanation is a wiring fault, that the policy is never
reaching `curate_window`. It is ruled out by three independent readings rather
than by inspecting the call site alone.

`agent.py` line 201 calls `policy.order` and line 263 calls `policy.observe`, so
the loop is closed. The rung's own report carries
`n_decisions_with_choice` of 423, so 423 decisions had at least two feasible
arms and the upper confidence bound actually chose between them. And the
per window traces disagree with the fixed rule on **265 of 1986 windows in
action order** and on 37 in step count. The policy is running and it is
changing what gets tried.

What it does not change is where the episode ends. Comparing final state window
by window against `c_no_policy`:

| quantity | value |
|---|---|
| windows compared | 1986 |
| identical final state | **1986** |
| different final state | **0** |
| probe calls, fixed rule against full | 3404 against 3388 |
| total steps | 4099 against 4083 |

### Where the injected candidates went

Injection is the only mechanism that can change the acceptance set, since
reordering can only permute a fixed candidate list. It fired 20 times across
1986 windows. Following the 25 actions that appear in `f_full` and not in the
fixed rule:

| outcome | n |
|---|---|
| NO_OP, the operator did not apply at all | 17 |
| ROLLED_BACK_UTILITY | 4 |
| ROLLED_BACK_STRUCTURE | 2 |
| ROLLED_BACK_RISK | 2 |
| **ACCEPTED** | **0** |

Not one injected candidate was committed. Two thirds of them were not even
applicable.

**Why injection is this sparse, from `SPOPolicy.inject`.** An arm is eligible
only if it is unvisited for that table and cluster, not already tried in this
window, and not already in the candidate list, and only then does the 0.05
probability apply. The unvisited set empties as learning proceeds, so the
opportunities disappear early. And an arm the proposer never offers is usually
one that does not apply to the window, which is what the 17 NO_OPs are.

### What this does and does not license

It does not license the sentence that the policy improves curation quality. On
this corpus, in these four columns, **the gain is exactly zero**, and the
efficiency gain is 16 probes and 16 steps, 0.47 percent.

It is direct evidence for theorem 4, exploration structural safety. The
strongest form of that claim is that no amount of exploration can commit
something the shield would refuse, and here the exploration reordered 265
windows and injected 20 operators the proposer never offers, and the committed
set did not move by one window. That is the theorem holding under a genuine
attempt to break it rather than an assumption.

The ladder's own conclusion is unaffected and is the one the paper needs: **the
shield carries the result.** Removing it entirely multiplies damage by 2.8 and
mis edits by 3.8, removing the structural half alone still multiplies damage by
2.5, and replacing the calibrated threshold with the hand set constant it
superseded multiplies damage by 1.5.

## Theorem 6's decay bound, evaluated rather than quoted

Experiment two's calibration decay row needs no new run. `theorem6_report`
already writes its three terms into every result file whose rung carries a
policy, so `experiments/calibration_decay.py` collects and evaluates them.
Seed 0, the three policy rungs.

| rung | intervals | decisions with a choice | gamma q00 | gamma q05 | gamma median | tie share | n_min |
|---|---|---|---|---|---|---|---|
| d_no_injection | 3 | 414 | 0.0000 | 0.0647 | 1.0814 | 0.0362 | 1 |
| e_raw_reward | 3 | 422 | 0.0000 | 0.0835 | 1.2994 | 0.0190 | 1 |
| f_full | 3 | 423 | 0.0000 | 0.0476 | 1.0848 | 0.0378 | 1 |

The bound is 2 q T_cal / (gamma n_min), with q the reward clip 5.8867 and T_cal
500.

| rung | bound at gamma q00 | at q05 | at median gamma |
|---|---|---|---|
| d_no_injection | inf | 9.10e4 | 5444 |
| e_raw_reward | inf | 7.05e4 | 4531 |
| f_full | inf | 1.24e5 | 5426 |

**The bound is vacuous and this has to be said outright.** It bounds a total
variation distance, which is at most 1 by definition, and the smallest value it
takes anywhere in this table is 4531. It constrains nothing.

**Why, and it is not the gamma tail.** The tail is real, 1.9 to 3.8 percent of
decisions have the top two bounds tied so gamma is zero there, and that alone
sends the infimum form to infinity. But the median gamma is around 1.08, which
is healthy, and the bound is still four thousand. The term that destroys it is
**n_min of 1**: in every calibration interval there is some visited cell that
was reached exactly once, and the bound is inversely proportional to that count.
With 45 or 46 cells touched per interval and 500 updates to spread over them,
a singly visited cell is not an accident of this run, it is what happens when
the cell count and the update budget are of the same order.

**Consequence.** The theorem is not wrong, its bound is simply not informative
at this corpus size and this cell count. Two honest options: report it as
measured and state that it is vacuous here, saying what would make it bite
(fewer cells, or a longer interval, both of which change the method), or drop
the quantitative claim and keep only the qualitative statement. Either way the
paper must not print the theorem and stay silent about its measured value.

This matters for how the policy module is positioned, because it removes the
second of its two supports. The first, that learning improves the four columns,
measured exactly zero on this corpus. What survives is theorem 4, exploration
structural safety, and that one is measured strongly: 265 windows reordered, 20
operators injected that the proposer never offers, and the committed set
identical on all 1986 windows.

### The policy did learn a different strategy, and the shield undid it

The strongest reading of the collapsed rungs, added after the first three
checks. Seed 0, `f_full` against `c_no_policy`, over the 1986 shared windows.

**What the policy changed.** The first operator tried in each window:

| operator | fixed rule | full method |
|---|---|---|
| RESEGMENT | 737 | **890** |
| IMPUTE | 437 | **225** |
| DESPIKE | 31 | 71 |
| DENOISE | 25 | 48 |
| KEEP | 689 | 685 |
| ABSTAIN | 67 | 67 |

263 of 1986 windows open with a different operator. The bound did not nudge the
ordering, it learned a visibly different preference: imputation as an opening
move falls by half and resegmentation rises by a fifth.

**What the shield did to it.** The operators actually committed:

| operator | fixed rule | full method |
|---|---|---|
| RESEGMENT | 129 | 129 |
| IMPUTE | 9 | 9 |
| DESPIKE | 27 | 27 |

Identical, operator by operator, to the count. Two policies that open
differently on 263 windows commit exactly the same 165 edits.

**The three remaining explanations, each ruled out by reading the code.**

  the tables never update      `observe` calls `tables.update`, which is the
                               standard incremental mean, and `agent.py` line
                               263 calls `observe` on every adjudicated
                               candidate. The method is named `observe` rather
                               than `update`, which is why a grep for the latter
                               finds nothing
  exploration is too weak      `c_u` is 1.0 and the width is
                               `c_u sqrt(2 log t / n)`, so it varies with the
                               round and the visit count. An unvisited cell
                               enters at `optimistic_init` 1.0, deliberately
                               above any plausible real value
  the clustering degenerated   a single cluster could touch at most 3 tables
                               times 7 arms, so 21 cells. The runs report 45
                               and 46 cells touched per calibration interval,
                               so at least three clusters are in use

So the policy runs, learns, and acts on what it learned, and the acceptance set
does not move. That is the design working as specified rather than a defect.

## Shield conservatism on the paper's corpus, and why the ett numbers were void

Section 4.2's experiment two. `experiments/shield_replay.py` re executes every
rolled back candidate on its window and measures the distance to the clean
reference before and after, so whether refusing it cost a real repair is
measured rather than modelled.

**The earlier numbers cannot be used.** The first run of this measurement was on
`--source ett`, seed 42, and that corpus is entirely transformer telemetry while
the paper's table is on `mixed`. Recomputed on the corpus the section actually
reports, the headline moves and the operator ordering inverts:

| quantity | ett seed 42 | mixed, three seeds |
|---|---|---|
| contaminated layer | 0.187 | **0.2855 +- 0.0106** |
| DENOISE | 0.075 | **0.4197 +- 0.0361** |
| DESPIKE | 0.000 | **0.3711 +- 0.0355** |
| IMPUTE | 0.136 | 0.1280 +- 0.0014 |
| RESEGMENT | 0.278 | 0.1820 +- 0.0133 |

RESEGMENT was the worst operator on ett and is now the second best; DESPIKE was
perfect there and is now second worst. **This is the third time a number
measured on ett failed to transfer to mixed**, after the repair distance and the
selection basis. The rule stands and has to be applied without exception: a
number is measured on the corpus the section reports.

### The result, three seeds on mixed

Overall wrongly refused 0.1739 +- 0.0055, over 1251 to 1299 replayable
candidates per seed. Replay coverage is essentially total: 2 to 3 candidates
per seed are superseded by an earlier accepted edit and **zero fail**, against
449 superseded and 39 failed on the ett run, so the limitation the module
docstring warns about is not binding here.

| stratum | n per seed | wrongly refused |
|---|---|---|
| clean | 147 | **0.0000** |
| hard | 46 | **0.0000** |
| rare_valid | 116 | **0.0000** |
| changepoint | 106 | **0.0000** |
| clean_ood, the probe layer | 83 | **0.0000** |
| contaminated | 776 | 0.2855 +- 0.0106 |

**Every protected layer is exactly zero in all three seeds, and so is the probe
layer.** Of the candidates the shield refused, not one would have improved a
window it was supposed to protect. The entire cost of the shield's caution falls
on the injected layer, which is where a refused repair is a repair forgone
rather than a protection earned.

The median distance change on the protected layers is between +0.15 and +0.54,
so the refused candidates there were not marginal: committing them would have
moved those windows substantially away from the truth.

### Which operators the caution falls on

| operator | n per seed | wrongly refused |
|---|---|---|
| DENOISE | 123 | 0.4197 +- 0.0361 |
| DESPIKE | 68 | 0.3711 +- 0.0355 |
| RESEGMENT | 111 | 0.1820 +- 0.0133 |
| IMPUTE | 972 | 0.1280 +- 0.0014 |

The two smoothing operators are where the shield is most often wrong, and they
are also the two whose effect is hardest to distinguish from removing genuine
structure, which is what the structural condition exists to prevent. IMPUTE
carries 78 percent of the refusals and is the most reliably correct refusal.
This is the split the discussion needs when it explains why introact repairs
spike worse than spec_veto: a spike is exactly the case where DESPIKE and
DENOISE look like structure removal.

## The ablation ladder, three seeds, and the two questions it answers differently

Complete 2026-08-27. Seven rungs on three seeds, `--source mixed --scale xl
--tau 0.02`, aggregated by `experiments/aggregate_ablations.py`.

| rung | id | edits | mis edit rate | damage rate | nRMSD |
|---|---|---|---|---|---|
| a_no_shield | A1 | 813 +- 20 | 0.2602 +- 0.0118 | 0.4130 +- 0.0179 | 1.0280 +- 0.0486 |
| b_no_structural | A2 | 315 +- 12 | 0.0991 +- 0.0056 | 0.3745 +- 0.0250 | 1.0535 +- 0.0496 |
| g_no_conformal | A4 | 251 +- 8 | 0.0861 +- 0.0043 | 0.2613 +- 0.0421 | 1.0537 +- 0.0498 |
| c_no_policy | A5 | 161 +- 9 | 0.0635 +- 0.0054 | 0.1287 +- 0.0107 | 1.0754 +- 0.0458 |
| d_no_injection | A6 | 161 +- 9 | 0.0635 +- 0.0054 | 0.1306 +- 0.0084 | 1.0764 +- 0.0472 |
| e_raw_reward | A3 | 161 +- 9 | 0.0635 +- 0.0054 | 0.1306 +- 0.0084 | 1.0764 +- 0.0472 |
| **f_full** | reference | 161 +- 9 | 0.0635 +- 0.0054 | 0.1306 +- 0.0084 | 1.0764 +- 0.0472 |

Ratio to the reference row:

| rung | damage | mis edits |
|---|---|---|
| a_no_shield | **3.16x** | **4.10x** |
| b_no_structural | **2.87x** | 1.56x |
| g_no_conformal | **2.00x** | 1.36x |
| the three policy rungs | 0.98 to 1.00x | 1.00x |

### The two questions need different evidence and get it

**How far a shield rung falls.** Far enough that three seed means settle it.
Removing the shield triples damage and quadruples mis edits. Removing only the
structural half still nearly triples damage, and note that it does so while
editing a third as often as no shield at all, so the structural condition is not
merely reducing the edit count. Replacing the calibrated threshold with the hand
set 0.12 doubles damage, which is the clearest evidence the paper has that the
conformal procedure earned its place.

**Whether a policy rung differs at all.** Three seed means cannot settle this
and no test on three points would either. Counted window by window instead,
which is exact:

| rung | seed | windows | different endpoint | different action order |
|---|---|---|---|---|
| c_no_policy | 0 | 1986 | **0** | 265 |
| c_no_policy | 1 | 2000 | **7** | 292 |
| c_no_policy | 2 | 2000 | **3** | 281 |
| d_no_injection | 0, 1, 2 | 5986 | **0, 0, 0** | 23, 34, 19 |
| e_raw_reward | 0, 1, 2 | 5986 | **0, 0, 1** | 31, 48, 47 |

Across all three seeds the fixed rule ends somewhere different from the full
method on **10 windows out of 5986, 0.17 percent**, while opening with a
different operator on 838 of them, 14 percent. Removing injection alone changes
no endpoint at all in any seed. Learning from the raw utility rather than the
shielded reward changes one.

Exact McNemar on the paired mis edit outcome is p = 1 for every rung and seed:
the discordant counts are 0 against 0. **No window is mis edited by one and not
the other, ever.**

### Check four, the cross reconciliation

Edits and mis edit rate recomputed from each rung's own flushed traces and
compared to its result file, 12 of 12 agree exactly. The damage rate is not
reconciled this way and the reason is recorded above: the trace stores a
distance that drops non finite differences while the table's definition fills
them, so on the missing kinds the two are different quantities by construction.

### What the ladder licenses

**The shield carries the result and the ladder shows it three ways.** All three
shield rungs degrade substantially and monotonically in the order the design
predicts.

**The policy changes the path and not the destination, and that is now measured
at three seeds rather than one.** The seed 0 result where every policy rung was
identical to the reference row was not an identity, seeds 1 and 2 differ on 7
and 3 windows. The effect is real and it is 0.17 percent. No claim of a repair
or safety gain from learning survives this table, and the exploration safety
claim is what it supports instead.

## The soft penalty sweep, and why theorem 2 cannot be stated as a strict claim

Experiment one's second sub table, complete 2026-08-27. Ten weights across four
orders of magnitude, three seeds, produced by `experiments/run_soft_sweep.py`
and aggregated by `experiments/aggregate_soft.py`. The arm runs through the same
`agent_traces` as ours with `VerifyConfig.soft_mu` set, so it differs from our
row in the decision rule and in nothing else.

| mu | edits | mis edit rate | damage rate | nRMSD, sound kinds |
|---|---|---|---|---|
| 0 | 556 +- 19 | 0.1716 | 0.4203 +- 0.0210 | 1.4435 |
| 0.1 | 534 +- 17 | 0.1601 | 0.4022 +- 0.0206 | 1.4428 |
| 0.5 | 477 +- 14 | 0.1384 | 0.3723 +- 0.0288 | **1.4425** |
| 1 | 434 +- 21 | 0.1272 | 0.3566 +- 0.0336 | 1.4433 |
| 2 | 382 +- 18 | 0.1138 | 0.3350 +- 0.0242 | 1.4455 |
| 5 | 293 +- 15 | 0.0931 | 0.2907 +- 0.0207 | 1.4557 |
| 10 | 254 +- 13 | 0.0829 | 0.2432 +- 0.0237 | 1.4590 |
| 25 | 225 +- 20 | 0.0753 | 0.1956 +- 0.0116 | 1.4645 |
| 50 | 210 +- 16 | 0.0721 | 0.1700 +- 0.0199 | 1.4726 |
| 100 | 192 +- 19 | 0.0711 | 0.1531 +- 0.0227 | 1.4932 |
| **f_full** | **161 +- 9** | **0.0635** | **0.1306 +- 0.0084** | 1.5080 |

The nRMSD column is the window count weighted mean over the five sound
contamination kinds, for the reason recorded above: the plain mean is 62 percent
one subgroup and the two missing kinds score an arm that repairs nothing at
zero, so a frontier read off the plain mean would reward the high weight end for
not repairing.

**Wiring check.** At mu 0 the soft rule degenerates to the utility condition
alone, and all three seeds reproduce the main table's `utility_only` row to the
digit. Cross reconciliation of edits and mis edit rate against each weight's own
traces agrees 30 of 30.

### What the sweep actually shows, which is not what was expected

**The soft arm repairs better than ours at every weight**, 1.4425 to 1.4932
against our 1.5080, and pays for it in edits and damage. Ours is not uniformly
better; the two designs sit at different points of the same trade off.

**No weight reaches our damage rate.** The lowest the sweep gets is 0.1531 at mu
100, against 0.1306. The direction is consistent across all three seeds,
+0.0322, +0.0031 and +0.0322.

**But that difference is not significant and the paper must not claim it is.**

| test | result |
|---|---|
| sign test, three seeds, all one direction | p = 0.250 |
| two proportion, pooled windows, 88/576 against 63/482 | z = 1.022, **p = 0.307** |

The intervals overlap as well, 0.1531 +- 0.0227 against 0.1306 +- 0.0084.
Writing that the soft penalty cannot reach the veto's damage level is a claim
this data does not support, and it is the kind of sentence a reviewer refutes in
one line.

### What can be claimed, and it is about the shape rather than a point

The repair column bottoms out at mu 0.5 with 1.4425 and degrades monotonically
from there to 1.4932 at mu 100, while the damage rate is still falling and still
above ours at the end of the sweep. So **past mu 0.5 the design is paying repair
for damage reduction and has still not bought its way down to the conjunction's
damage level by the end of four orders of magnitude**. That is the shape theorem
2 predicts, and it is a statement about the frontier rather than about a
significant gap at one point.

The honest form of the theorem's empirical support is therefore: within the
swept range, raising the penalty begins to cost repair before it reaches the
veto's damage rate. The strict lower bound claim stays a theoretical statement
and is not asserted as measured.

**What would settle it.** The damage rate's spread across seeds is about 0.02
and the gap is 0.022, so roughly ten or more seeds would be needed, about eight
GPU hours. Recorded here so the choice is visible rather than implied by
silence.
