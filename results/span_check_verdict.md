# A  verdict on the span alignment hypothesis

**The hypothesis is wrong. Aligning the scored span does not rescue RESEGMENT,
it makes the decision worse. The refusals are real refusals, and the cause sits
one level deeper.**

## What was tested

The audit had located the entire negative return on refusals in one operator:
twelve RESEGMENT rejections on the heavy corpus, eight of them wrong, net
-37.64 against +27.75 for IMPUTE. The proposed cause was mechanical. RESEGMENT
is the only operator that changes the length of the window, so a 512 point
window cropped to 265 moves the scored segment from absolute index 480 to 512
down to 233 to 265, and the before and after utilities describe two different
forecasting problems.

That much is true. Six of eight sampled level_shift windows have no overlap at
all between the segment scored before and the segment scored after.

`probe_window` now takes a `region` argument that pins both measurements to one
absolute segment, the tail of the retained span, so the only remaining
difference between them is whether the discarded stretch was still in the
forecasting context. It is exactly backward compatible, `region=None` and
`region=(0, T)` produce identical vectors.

## What it showed

Offline surrogate, 69 windows where RESEGMENT applies, 31 of which would move
the window toward truth.

| utility definition | accepts | agrees with truth | wrongly refused | gain forgone | corr with truth |
|---|---|---|---|---|---|
| current, free span | 0.84 | 0.52 | 3 | 7.64 | **+0.778** |
| aligned span | 0.62 | 0.62 | 7 | 17.76 | +0.696 |

Alignment raises wrong refusals from three to seven, more than doubles the gain
thrown away, and lowers the correlation with truth. The free span definition is
the better of the two. The 37.64 is not a comparability artefact.

## What the audit had not checked, and should have

The claim that the utility recheck was doing the damage was asserted from the
fact that `ablate_no_reprobe` had net positive refusals. The cross tabulation
that would confirm it directly was never run. It has been now, on the real
model heavy traces:

| operator | UTILITY | STRUCTURE | RISK |
|---|---|---|---|
| IMPUTE | 91 | 47 | 0 |
| DENOISE | 0 | 3 | 0 |
| RESEGMENT | **12** | 0 | 0 |

Every single RESEGMENT rejection is a utility rejection. None was vetoed on
structure or risk. So that half of the diagnosis holds: the utility term is
what refuses this operator. What does not hold is the explanation for why.

## The explanation that survives

The same corpus, the same operator, the same acceptance threshold, and the two
backends disagree completely:

- offline surrogate, 84 percent of RESEGMENT candidates accepted, utility
  correlates with truth at +0.778
- real TSFMs, 12 of 12 RESEGMENT candidates refused, every one of them on
  utility

The difference is the model. A strong forecaster instance normalises its input
and models context well enough that a displaced segment earlier in the window
costs it very little on the held out tail. Removing that segment therefore buys
it almost nothing, the measured utility change is at or below the acceptance
threshold, and the edit is correctly refused **on the criterion the method
optimises**. The weak surrogate is hurt by the displacement, so removing it
registers as a gain.

This is the same shape as the noise finding from the previous round, where
action accuracy was 0.00 under real models against +0.182 under the surrogate.
Two contaminations, one mechanism: **where a strong model is robust to a
defect, behavioural evidence for repairing it does not exist.**

That is not a bug and it is on thesis rather than against it. The method
optimises data utility for a target model, and a defect the target model
shrugs off is, by that definition, not worth repairing. The tension is with the
*evaluation*, which scores distance to a pristine reference and therefore
counts these as missed repairs.

## What follows

1. **Do not widen epsilon and do not change the span.** Both were candidate
   fixes for a problem that turns out not to be a calibration error. The
   refusals are correct under the utility definition the paper argues for.
2. **The paper has to state its utility position explicitly.** Two defensible
   readings exist and they give different results here. Either curation serves
   the target model, in which case refusing to resegment a shift a strong model
   ignores is right and the evaluation needs a utility oriented metric beside
   the fidelity one, or curation serves fidelity, in which case the behavioural
   signal is insufficient on its own and the method needs evidence the current
   probe cannot see. This is now the central design question, not a loose end.
3. **One measurement is still missing and needs the GPU.** Whether the real
   model utility change on these twelve candidates is slightly negative or
   slightly below the threshold is not recorded. Traces stored only the window
   level utility. `GovernanceTrace.summary` now exports per step
   `delta_utility`, `struct_distortion`, `risk` and the operator parameters, so
   the next run will settle it and the offline audit will no longer have to
   infer parameters from the proposal order.

## Correction to the previous round

The previous summary stated that the deficit was one operator whose utility
recheck does not work, and offered the span mismatch as the plausible
mechanism. The first half stands, the second is now disproved. The operator is
refused on utility, but the refusal is a correct reading of a real absence of
utility gain, not a broken comparison.
