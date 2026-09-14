# Where this risk measure applies, and what may not be compared with what

Two experiments in this project produced behavioural risk values with opposite
signs for what looks like the same kind of window. Staircase and sawtooth
shapes scored +0.535 and +0.492 as part of the clean_ood stratum in the 2000
window run, and -0.087 and +0.028 as rungs of the controlled ladder. Both
numbers are real and neither is a bug. The reason they differ is structural and
it defines the scope of the method.

## Behavioural risk is relative by construction

`calibrate()` computes `z = (behaviours - centers) / spreads`, where the
centres and spreads come from a peer group of windows matched in profile space,
and the risk is `z @ w`. Nothing in that path is absolute. The same window
placed in a different corpus draws a different peer group and receives a
different risk.

This is a design decision, not an oversight. A window is being asked to be
unusual relative to something, and the alternative, an absolute threshold on
raw behavioural signals, is exactly what failed on real ETT data early in this
project and prompted the corpus adaptive references.

The consequence has to be stated in the paper: **behavioural risk is a within
corpus quantity and carries no meaning across corpora.**

## The two specific reasons those numbers differ

**Different generators.** The shapes are not the same shapes. `corpus.py` builds
a staircase with step sizes drawn from `randn() * 2.0` and adds 0.05 observation
noise, while `ladder.py` uses `uniform(-2, 2)` and no noise. Its sawtooth has
0.05 noise and the ladder's has none, and the two pulse train implementations
differ in both amplitude, 3 to 6 against a fixed 1, and in width, bound to the
period against fixed. These are different populations that happen to share a
name.

**Different peer groups.** In the 2000 window run those shapes sit in a corpus
that is mostly real ETT windows, so their peers are real data and they are
scored as the outliers they are. In the ladder every window is generated and a
staircase is scored against other synthetic shapes, several of which are
stranger than it is. The reference moved.

Both effects push in the same direction and neither is separable from the other
after the fact.

## The rule this implies

Comparisons are valid **within** one corpus and invalid **across** corpora.
Concretely, for this project:

- The 2000 window run, the six point contamination sweep and the ablation
  ladder each support internal comparisons between strata, rungs and methods.
- The controlled ladder supports internal comparisons between its own rungs.
- The 2x2 level experiment supports internal comparisons between its cells.
- No number from any one of these should be set beside a number from another
  and read as the same quantity. In particular the ladder does not replicate,
  contradict or corroborate the clean_ood values, it measures a different
  arrangement.

Every table in the paper needs to make clear which corpus it came from.

## When the method is applicable at all

The peer calibration assumes a corpus with a dominant structure and a minority
of windows that depart from it. That is the setting the method was built for
and it describes real pretraining corpora, which are large collections of
mostly ordinary series with some fraction of defective ones.

It does not describe a homogeneous synthetic set. If every window is drawn from
the same generator, the peer group is the population, the z scores are measuring
sampling noise, and the risk ranking is close to arbitrary. The controlled
ladder is deliberately in this regime, which is fine because it is only used
for between rung comparisons where every rung is equally affected, but it would
be the wrong place to read an absolute risk from.

The boundary condition to state: **the corpus must have a majority structure
for a minority to be measured against.**

## What this does not undermine

The protection results do not depend on any of this. Damage introduced is
measured against the pristine reference series in the same run, not against a
peer group, so the sweep numbers and the ablation ladder numbers are unaffected.
The same is true of fidelity gain, repair reduction and the edit counts. Only
`behav_risk` and quantities derived from it carry the within corpus restriction.
