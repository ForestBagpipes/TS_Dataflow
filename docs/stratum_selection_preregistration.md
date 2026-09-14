# Pre registration, selection criteria for the two protected strata

Written 2026-08-22, **before any selection was run and before any count was
seen**. The thresholds below are fixed here so that none of them can be widened
after looking at how many windows they return. This document is committed on
its own, ahead of the implementation, for that reason.

## Why the two strata change at all

Section 4.1.2 of the progress document states that the rare and the hard layers
are taken from the data itself rather than built, and gives the reason: if the
same procedure both designs the defects and designs the objects that must be
protected from them, the protection result is circular. Reviewing the code
against that sentence found it true of two of the four protected layers and
false of the other two.

| layer | how it is built today | matches 4.1.2 |
|---|---|---|
| clean | a real window, untouched | yes |
| hard | selected from real windows by a difficulty statistic | yes |
| rare_valid | a real window **plus a synthetic sinusoidal excursion** | no |
| changepoint | a real window whose tail is **modulated by a synthetic sinusoid** | no |

So the sentence in 4.1.2 is not supported by the corpus it describes. The two
constructed layers become selected layers here. The document is not changed,
because the claim it makes is the one worth having and the code was the part
that did not meet it.

## What is being selected, in physical terms

Both layers name a real event that a curation agent must leave alone.

| layer | industrial reading | financial reading |
|---|---|---|
| rare_valid | a load surge on a transformer | a volatility burst in a price series |
| changepoint | a device starting or stopping | a parallel shift of the rate curve |

## Channel statistics, defined once

Every criterion below is expressed against the channel the window came from,
never against a constant, because the corpus now spans quantities that differ by
three orders of magnitude inside one file.

For channel `c`, over its whole finite history:

    m_c   = median(x)
    s_c   = IQR(x), floored at 1e-12
    z_t   = (x_t - m_c) / s_c
    tail_c = the 99.5th percentile of |z| over the channel

`tail_c` is a per channel quantity, not a fixed number, so the criterion means
the same thing on a rate quoted in percent and on a price quoted in dollars.

## Criterion A, the rare valid layer

A window qualifies when all four hold.

| # | condition | threshold | why this value |
|---|---|---|---|
| A1 | it reaches the channel's own tail, `max_t abs(z_t) >= tail_c` | 99.5th percentile, per channel | self calibrating, introduces no cross channel constant |
| A2 | the excursion is brief, the share of points with `abs(z_t) >= tail_c` is at most `BRIEF_FRAC` | 0.05 | at 512 steps that is up to 26 points, an event rather than a regime |
| A3 | it returns to baseline, `abs(median(first quarter) - median(last quarter)) / s_c <= RETURN_TOL` | 0.5 | the two ends agree to within half an interquartile range, which is what separates an excursion from a step |
| A4 | the window is not in the pool any defect is injected into | exact | keeps the protected object independent of the defect design, which is the whole point of 4.1.2 |

## Criterion B, the legitimate changepoint layer

The split point is searched over the middle half of the window, so both sides
carry at least a quarter of it. Let `d` be the standardised mean difference at
the best split, `d = abs(mean(left) - mean(right)) / s_c`.

| # | condition | threshold | why this value |
|---|---|---|---|
| B1 | the segment means jump, `d >= JUMP_D` | 2.5 | see the note below, this is deliberately set to the bottom of the injected level shift range |
| B2 | the overall scale is preserved, `std(left) / std(right)` lies in `[1/SCALE_RATIO, SCALE_RATIO]` | 1.5 | a break in level, not in volatility |
| B3 | it is not also a tail excursion, that is A1 fails | exact | keeps the two layers disjoint |
| B4 | the window is not in the injection pool | exact | as A4 |

**Why `JUMP_D` is 2.5 and not lower.** The `level_shift` contamination adds
`uniform(2.5, 4.0)` times the window spread. Setting the selection threshold
below that range would produce a changepoint layer whose jumps are
systematically smaller than the injected ones, and the size of the jump would
then separate the two by itself. The threshold is set at the bottom of the
injection range so that the two overlap.

**A consequence, stated in advance.** Under B1 and B2 a selected changepoint and
an injected level shift have the same statistical signature: the level moves,
the scale does not. They are therefore not separable by the shape of the window
alone, and nothing in the corpus is arranged to make them separable. This is
intended. The progress document's thesis is that whether an edit is harmful
depends on the segment rather than on the edit, and a stratum pair that is
identical in shape and opposite in verdict is the sharpest possible statement of
it. What remains available to tell them apart is the peer context CDP builds and
the behavioural evidence, not the waveform.

The consequence is also a risk, and the measurement that checks it is
pre registered here: **the distribution of `d` is reported for the selected
changepoint layer and for the injected level shift windows, side by side.** If
the two distributions turn out to be well separated, the overlap this criterion
was meant to produce did not happen and the layer is not the test it claims to
be. That is reported whichever way it comes out.

## Assignment order, fixed here

A window can satisfy more than one criterion. The pool is assigned in this
order and no window enters two layers.

1. rare_valid, by criterion A
2. changepoint, by criterion B, from what is left
3. hard, by the existing difficulty statistic, from what is left
4. contaminated, clean and the synthetic probe layer, from the remainder

rare_valid goes first because criterion A is the most restrictive of the three,
so filling it first is what makes the other two feasible rather than the
reverse.

## Shortfall is reported, never repaired by widening

If a layer cannot be filled at the requested size, **the shortfall is reported
with its count and its cause, and no threshold is moved.** If a source yields no
window for a layer at all, that source is recorded as not providing that layer
rather than being made to provide one.

This is written down now because the temptation on seeing a small count is to
relax a threshold by a little, and a threshold relaxed after seeing the count is
not a criterion.

## The probe layer is unaffected

`clean_ood` stays synthetic and stays labelled as such. It serves experiment one,
where the question is what the behavioural signal does on clean data of an
unfamiliar shape, and a synthetic shape is the right instrument for that. It is
excluded from every per layer protection figure and from the protected mis edit
count.

## Constants, in one place for the implementation to import

    TAIL_PERCENTILE = 99.5
    BRIEF_FRAC      = 0.05
    RETURN_TOL      = 0.5
    JUMP_D          = 2.5
    SCALE_RATIO     = 1.5
    SPLIT_MARGIN    = 0.25
