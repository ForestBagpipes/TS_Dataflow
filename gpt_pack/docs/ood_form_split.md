# Is the clean_ood stratum one phenomenon or four unrelated shapes

The characterisation rests on this stratum and two of its four generators
collide with injected contamination by construction. A staircase is a sequence
of discrete level jumps and the level_shift defect is a discrete level jump. A
sawtooth is a repeating sharp transition and a spike is a sharp transition. If
the elevation came from those two, the stratum would be measuring undeclared
contamination and the evaluation set would need rebuilding.

It does not. The answer is neither of the two readings that were posed, and the
difference matters, so it is set out with the numbers rather than summarised.

## Every form is elevated, and by nearly the same amount

From the 2000 window run, `results/xl/`. Behavioural risk against the
contaminated stratum, whose median is +0.063 over 740 windows.

| form | n | p25 | median | p75 | IQR | auc vs contaminated | p | edited | via DESPIKE |
|---|---|---|---|---|---|---|---|---|---|
| random_walk | 53 | +0.104 | +0.389 | +2.867 | 2.763 | **0.725** | 4.3e-08 | 4 | 4 |
| staircase | 53 | +0.025 | +0.535 | +3.849 | 3.824 | **0.716** | 1.5e-07 | 10 | 6 |
| pulse_train | 52 | +0.060 | +0.326 | +3.884 | 3.824 | **0.705** | 7.8e-07 | 0 | 0 |
| sawtooth | 52 | +0.176 | +0.492 | +2.918 | 2.741 | **0.760** | 3.7e-10 | 6 | 3 |

The four effect sizes span 0.705 to 0.760. The medians look more spread than
that, from +0.326 to +0.535, but the interquartile ranges are 2.7 to 3.8 wide,
so ranking these forms by median is reading noise. The rank sum statistic is
the quantity to use and it says the four forms are elevated to within 0.055 of
each other, each at p below 1e-6.

## Removing the colliding forms changes almost nothing

| subset | median | auc vs contaminated | p |
|---|---|---|---|
| all four forms | +0.473 | 0.726 | |
| **random_walk and pulse_train only**, no collision | +0.355 | **0.715** | 9.5e-13 |
| staircase and sawtooth only, colliding | +0.525 | 0.737 | 3.2e-15 |

**This is the decisive line.** Drop both forms that could be mistaken for
injected contamination and the effect size falls from 0.726 to 0.715, a change
of 0.011, still significant at 9.5e-13 over 105 windows. The elevation does not
depend on the collision. A random walk has no corresponding injected defect and
a pulse train has none either, and those two alone reproduce the finding.

So the reading is neither of the two posed. It is not that random_walk carries
it while the others are artefacts, and it is not that the colliding forms carry
it. **All four carry it independently**, which is a stronger result than either,
because the characterisation now rests on four generators rather than one and
survives dropping the two that could be attacked.

The stratum should not be scoped out or rebuilt. It should be reported by form,
with the collision free subset given as the robustness check.

## What the statistical profile does to these windows, all of them

| form | shift | noise | spike | none |
|---|---|---|---|---|
| random_walk | 18 | 14 | 3 | **18** |
| staircase | 26 | 13 | 1 | **13** |
| pulse_train | 28 | 11 | 3 | **10** |
| sawtooth | 25 | 10 | 3 | **14** |

Between 65 and 81 percent of these clean windows are assigned a defect. The
earlier hypothesis was that this is a collision effect on staircase and
sawtooth. It is not: random_walk, which collides with nothing, is assigned a
defect in 35 of 53 windows and a level shift in 18 of them. Pulse train, which
collides with nothing either, is the worst at 42 of 52.

The misreporting is general, not specific to the colliding forms. That makes it
a property of the statistical profile rather than of the evaluation set.

## shift_strength cannot be repaired the way I proposed

The proposal was to teach `shift_strength` to tell a determined staircase from
a random displacement by counting jumps. It cannot.

| group | n | jumps p25 | median | p75 | median max step |
|---|---|---|---|---|---|
| staircase | 53 | 0.0 | 2.0 | 3.0 | 2.40 |
| sawtooth | 52 | 0.0 | 1.5 | 3.0 | 1.30 |
| random_walk | 53 | 0.0 | 2.0 | 3.0 | 1.30 |
| level_shift, injected | 105 | 1.0 | 1.0 | 1.0 | 3.81 |

Staircase against injected level_shift on jump count gives auc 0.536 at p 0.41.
That is a coin flip. The generated staircases place their edges at random and
the changepoint detector finds a median of two of them, against a median of one
for the injected defect, and the distributions overlap almost entirely.

**Not separable by jump count, so the repair I proposed is not available.**

One caveat on the negative. The `max_step` column does differ, 3.81 for the
injected defect against 2.40 and 1.30 for the generated shapes, and this
experiment did not test that dimension for significance. So the honest
statement is that the specific repair proposed, counting jumps, is dead, and a
different repair keyed on step magnitude is untested rather than ruled out.
Under the freeze it stays untested.

## Consequences

The characterisation is finalised and does not need the evaluation set changed.
Report by form and include the collision free subset.

The statistical profile assigning defects to 65 to 81 percent of clean
unpredictable windows is a real limitation, it is general rather than an
artefact of two generators, and it goes to `docs/known_limitations.md` unfixed
under the freeze.
