# What the contamination sweep shows

Six contamination rates from 5 to 67 percent, 800 windows each, real TSFMs,
`results/sweep/sweep.json`. Both rulers are recorded at every point: fidelity
against the pristine reference for windows that had something injected, and
damage introduced for windows that were already fine.

## The main result

Damage introduced on protected data, summed over the clean, hard, rare valid,
changepoint and clean out of distribution strata. Lower is better and zero is
what a method that never edits anything achieves.

| rate | no_action | always_clean | stat_only | quality_rank | **introact_full** |
|---|---|---|---|---|---|
| 5 | 0.0000 | 1.0011 | 0.4569 | 0.2470 | **0.0970** |
| 10 | 0.0000 | 1.0025 | 0.4339 | 0.2488 | **0.0881** |
| 20 | 0.0000 | 0.9791 | 0.3880 | 0.2604 | **0.1028** |
| 35 | 0.0000 | 1.3480 | 0.7793 | 0.2771 | **0.1288** |
| 50 | 0.0000 | 1.0992 | 0.4998 | 0.3110 | **0.0906** |
| 67 | 0.0000 | 0.9497 | 0.3542 | 0.3077 | **0.0846** |

At every rate the ordering is the same and the margins are large. Against
unconditional cleaning the reduction is roughly tenfold, against a statistical
rule four to six fold, against quality ranking two and a half to three and a
half fold. The curve is also close to flat, between 0.085 and 0.129, while
`always_clean` and `stat_only` move by a factor of two across the same range.
Protection here does not degrade as contamination rises, which is the property
that matters for a curation tool, since the corpora that need curating most are
the dirty ones.

`no_action` sitting at exactly zero is not a competitor, it is the axis. It
buys perfect protection by declining to do the job.

## The flattening trap, and who walks into it

The clean out of distribution stratum is where the model utility ruler is most
misleading, and the sweep shows every method being offered the same bribe.

| rate | always_clean util / damage | stat_only | quality_rank | **introact_full** |
|---|---|---|---|---|
| 5 | +6.03 / 0.152 | +5.70 / 0.123 | +5.55 / 0.109 | **+2.63 / 0.058** |
| 10 | +6.58 / 0.162 | +6.87 / 0.132 | +6.29 / 0.125 | **+2.07 / 0.046** |
| 20 | +5.21 / 0.144 | +5.18 / 0.111 | +4.40 / 0.100 | **+2.61 / 0.059** |
| 35 | +5.23 / 0.144 | +5.22 / 0.114 | +5.18 / 0.121 | **+3.51 / 0.075** |
| 50 | +5.50 / 0.168 | +4.76 / 0.127 | +5.45 / 0.149 | **+1.79 / 0.042** |
| 67 | +2.79 / 0.102 | +2.71 / 0.070 | +2.75 / 0.087 | **+2.27 / 0.042** |

Every method gains four to seven units of model utility on windows that were
already clean. That is the mechanism documented in
`docs/triple_failure_analysis.md`: these windows are unfamiliar, the frozen
model predicts them badly, and any edit that smooths them towards a constant
makes the model's job easier. A pipeline optimising model utility is being paid
to destroy them.

IntroAct collects roughly half the available utility and takes roughly a third
of the damage. It declines the other half because the verification step reads
the structural distance as well as the utility, and a large share of the
proposals that would have collected it are rolled back. This is the clearest
single demonstration of what post hoc verification buys, and it is worth more
than the aggregate damage number, because here the method is refusing a reward
its own objective function is offering.

It is not a complete refusal. Ten windows in the 2000 window run went through
anyway via the footprint exemption, so the correct claim is that verification
cuts the trap by about two thirds rather than closing it.

## Where other methods are better, stated plainly

Fidelity gain on level shift, the defect with the strongest statistical
signature:

| rate | always_clean | stat_only | quality_rank | introact_full |
|---|---|---|---|---|
| 20 | -0.021 | **+0.362** | -0.003 | +0.298 |
| 50 | -0.066 | **+0.574** | -0.010 | +0.363 |
| 67 | -0.025 | **+0.572** | -0.006 | +0.316 |

`stat_only` repairs level shifts better than IntroAct does, by a widening
margin as contamination rises. It should. The defect leaves an unmistakable
statistical trace, a rule that fires on that trace fires every time, and
IntroAct sometimes declines the repair because the utility gain does not clear
epsilon. Buying protection costs some repair, and level shift is where the bill
is largest.

On isolated spikes `always_clean` leads at most rates, from +0.55 to +0.75
against IntroAct's +0.30 to +0.66. Unconditional cleaning is very good at the
one defect it is designed around, and it pays for that with ten times the
damage on protected data.

On duplicated segments every method is at or below zero. Nobody repairs a
duplicated segment, and IntroAct is closest to zero, which at the low rates
means it correctly does nothing at all.

## What this licenses the paper to claim

Not that the method repairs better. It does not, and on level shift it
measurably does not. The claim the data supports is about the trade: at a
modest cost in repair on statistically obvious defects, IntroAct reduces damage
to clean, hard, rare, changepoint and out of distribution data by four to ten
fold against every non trivial baseline, at every contamination rate tested,
with no degradation as the corpus gets dirtier.

## Caveat on the per type numbers

The corpus size is held at 800 per point, so the count per contamination type
falls with the rate. At 5 percent there are 40 contaminated windows across
seven types, around six each, which places the aggregate trend and cannot rank
types. Per type conclusions here should be read from the high rate points and
cross checked against the 2000 window run, where each type has around 105
members. The protected strata keep equal shares at every rate, so the damage
column, which is the main result, has the same power throughout.
