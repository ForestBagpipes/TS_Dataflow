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

## Blockable window share, 19 percent unblockable

**Denominator.** 210 windows of the heavy corpus, 40 unblockable. The exclusion
is precisely correlated with the effect, which is the point rather than a fault:
the unblockable windows are the ones with injected gaps, which is what the
valuation family cannot consume and what IMPUTE exists for.

**Competing explanation.** The 40 could be an artefact of the block length
rather than of missingness. Ruled out by construction: the export drops a window
only when the block contains a non finite value, and the only source of non
finite values in this corpus is the gap injection.

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
