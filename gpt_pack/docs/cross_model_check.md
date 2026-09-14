# The level effect across four backends

Source `results/cross_model.json`. The same 600 windows from the 2x2 design,
perceived four times, once per backend, each in a single model pool.

The purpose was a falsifiable prediction. If the level sensitivity comes from
instance normalisation hiding the absolute level, then backends that normalise
differently should show it with different strength. That prediction is testable
and the result is that it failed, in a specific way worth writing down.

## What the repository can confirm about normalisation

Recorded as found, not as remembered.

| backend | status |
|---|---|
| surrogate | confirmed, `backends/surrogate.py` calls `instance_norm` on the context before every forward pass |
| timesfm | confirmed at the call site, `normalize_inputs=True` is passed to the forecast entry point, the internal scheme is the library's |
| chronos | not confirmed here, the adapter passes the raw context and any scaling happens inside the pipeline |
| moment | not confirmed here, not included in this run |

## The result

| backend | normalisation | walk minus anchored | walk vs ramp auc | p |
|---|---|---|---|---|
| chronos-bolt-base | unconfirmed | +0.172 | 0.785 | 3.4e-12 |
| chronos-bolt-small | unconfirmed | +0.267 | 0.890 | 1.7e-21 |
| timesfm-2.5-200m | confirmed at call site | **+0.489** | **0.901** | 1.0e-22 |
| surrogate | confirmed, explicit | **+0.097** | **0.656** | 1.3e-04 |

Per condition medians:

| backend | sine_anchored | sine_on_walk | sine_on_ramp | walk_only | noise_anchored | ett_real |
|---|---|---|---|---|---|---|
| chronos-bolt-base | -0.050 | +0.122 | -0.110 | +0.501 | +0.003 | +0.180 |
| chronos-bolt-small | -0.089 | +0.178 | -0.193 | +0.497 | +0.033 | +0.187 |
| timesfm-2.5-200m | -0.252 | +0.238 | -0.224 | +0.506 | +0.085 | +0.325 |
| surrogate | -0.031 | +0.066 | -0.059 | +0.438 | +0.062 | -0.004 |

## What replicates

The effect itself, in all four. Every backend places `sine_on_walk` above
`sine_anchored` and above `sine_on_ramp`, and the walk against ramp test is
significant in every case, weakest at p 1.3e-04. The effect is a property of
frozen forecasters as a class here, not an artefact of one checkpoint.

Two secondary patterns are just as consistent. `sine_on_ramp` sits below
`sine_anchored` in three of four backends, so a determined level change lowers
risk rather than raising it, and `walk_only` lands between +0.438 and +0.506 in
all four despite their medians differing elsewhere.

## What does not replicate, and is not explained away

The prediction was that confirmed instance normalisation would show the
strongest effect. The backend with explicit, verified instance normalisation
shows the weakest, +0.097 against timesfm's +0.489. **The prediction is
refuted.**

One confound cannot be ruled out with the backends available. The surrogate has
39,328 parameters and its medians are compressed across every condition, not
only the ones this experiment manipulates, which is what a low capacity model
producing muted responses everywhere would look like. Separating capacity from
normalisation scheme needs a large backend that does not instance normalise,
and the pool does not contain one. So the honest statement is that the
mechanism is neither confirmed nor cleanly refuted, and the correlation between
normalisation status and effect size runs the wrong way in the one comparison
that could be made.

## Measurement caveat

`model_disagree` is one of the fourteen behavioural signals and is identically
zero for a single model pool, so these runs use thirteen. That affects all four
backends equally and does not favour any of them, but it means these numbers
are not comparable with the multi backend runs elsewhere, including the 2x2
values in `docs/behavior_variable_identification.md`. The comparison that
matters here is between the four rows, which share the same handicap.

## What the paper should say

That the level effect replicates across four independent frozen forecasters
with p below 1e-3 in every case, which is worth stating and is not weakened by
anything above. Not that instance normalisation is the mechanism. That
explanation is plausible, it was tested, and the test did not support it.
