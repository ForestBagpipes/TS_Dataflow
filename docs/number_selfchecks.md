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
