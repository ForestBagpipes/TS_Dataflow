# What each component is actually worth

Eight rungs plus a threshold sweep, `results/ablations/ablations.json`. Run at
the heavy scale, 210 windows, so this is a relative comparison between rungs
rather than a source of absolute numbers. Damage is the mean over protected
windows and repair reduction is the NMSE improvement on contaminated ones.

| rung | damage | over clean rate | repair | net | rollback rate | windows edited |
|---|---|---|---|---|---|---|
| a_no_action | 0.0000 | 0.00 | +0.000 | +0.000 | 0.00 | 0 |
| **b_no_verification** | **0.1181** | 0.40 | +0.484 | +0.442 | 0.00 | 119 |
| c_no_utility_recheck | 0.0583 | 0.26 | +0.516 | +0.495 | 0.49 | 89 |
| d_no_structural_veto | 0.0282 | 0.26 | +0.304 | +0.294 | 0.52 | 76 |
| e_no_peer_calibration | 0.0254 | 0.20 | +0.323 | +0.314 | 0.72 | 57 |
| f_single_step | 0.0182 | 0.07 | +0.312 | +0.306 | 0.70 | 34 |
| g_no_abstain | 0.0254 | 0.20 | +0.327 | +0.318 | 0.71 | 58 |
| **h_full** | 0.0254 | 0.20 | +0.320 | +0.311 | 0.71 | 57 |

## Verification is the component

Removing it multiplies damage by 4.6 and doubles the number of windows edited,
from 57 to 119. What it buys in exchange is a repair reduction of +0.484
against +0.320. So twice the edits return about fifty percent more repair while
costing nearly five times the damage. That trade is the paper's argument stated
as an ablation: the marginal edit that verification blocks is worth far less
than the harm it does.

The over clean rate makes the same point more directly. Without verification,
40 percent of protected windows come out worse than they went in. With it, 20
percent.

## The recheck is worth more than the veto

`c_no_utility_recheck` keeps the structural veto but never re measures utility
after the edit, and damage goes to 0.0583, more than double the full method.
`d_no_structural_veto` keeps the utility recheck and drops the structure test,
and damage goes to 0.0282, only eleven percent above full.

Note that `c` has the highest repair reduction on the ladder at +0.516. It
edits 89 windows and repairs well. It is also the second most damaging rung.
Repair quality and protection are separate axes and this rung is where they
separate most visibly.

## Two components do not pay for themselves at this scale

`e_no_peer_calibration` and `g_no_abstain` both land at damage 0.0254, the same
as the full method to four decimals. Peer calibration shifts repair from +0.320
to +0.323 and abstention shifts it to +0.327, differences well inside what 210
windows can resolve.

This should be reported as measured. Peer calibration is well motivated, it is
the thing that makes the behavioural signal comparable across profiles, and the
separate measurement in `docs/signal_increment.md` found its AUROC
indistinguishable from global standardisation as well, 0.468 against 0.467.
Two independent measurements now say the same thing, and the honest position is
that peer calibration has no measurable effect on this corpus and its value is
a hypothesis awaiting a corpus with more profile heterogeneity.

Abstention costing nothing is a different and more benign result. An abstain
and a keep produce the same series, so they differ only in what the trace
records. The abstain rate is 3.3 percent, and the finding is that those seven
windows would not have been damaged anyway.

## Single step is not obviously worse

`f_single_step` allows one candidate per window and has the lowest damage of
any acting rung, 0.0182, with an over clean rate of 0.07 against the full
method's 0.20. It repairs slightly less, +0.312 against +0.320, and edits 34
windows against 57.

Multi step curation is therefore not free. It buys a small amount of repair and
pays for it in protection. The case for it rests on windows carrying more than
one defect, which the corpus generates but does not concentrate on, so this
ladder is not the experiment that settles it.

## The structural threshold is set too loose

| tau | damage | repair | net | edited |
|---|---|---|---|---|
| 0.04 | **0.0040** | +0.316 | +0.314 | 41 |
| 0.08 | 0.0097 | +0.316 | +0.313 | 52 |
| **0.12 (current)** | 0.0254 | +0.320 | +0.311 | 57 |
| 0.20 | 0.0276 | +0.316 | +0.306 | 72 |
| 0.30 | 0.0282 | +0.304 | +0.294 | 76 |

Damage rises by a factor of six from tau 0.04 to tau 0.12 while repair moves by
0.004, which is nothing. The current value is not on the efficient frontier and
was set by hand, as admitted in the code.

This connects directly to the flattening failure in
`docs/triple_failure_analysis.md`. The ten edits that destroyed clean out of
distribution windows scored a median structural distance of 0.0373. A threshold
at 0.04 would have caught part of that population and one at 0.03 would have
caught all of it, at a repair cost of 0.004.

The tempting conclusion is to set tau to 0.04 and claim the improvement. That
is not what this table licenses. The sweep was run on 210 windows at one seed,
tau was chosen after seeing the failure it would have prevented, and tuning a
threshold against the test corpus is the thing this paper is supposed to be
arguing against. The correct move is to select tau on held out data and report
the sweep as evidence that the method is not sensitive to getting it exactly
right, since every value from 0.04 to 0.30 repairs within 0.016 of every other.

## Caveat

210 windows means each protected stratum has ten to twenty members, so per
stratum breakdowns from this ladder are not reliable and are not quoted here.
The rung ordering on the aggregate damage column is what this experiment
supports. The 2000 window run and the six point contamination sweep carry the
per stratum claims.
