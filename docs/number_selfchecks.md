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
