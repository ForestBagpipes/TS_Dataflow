# Offline audit, verdict and the next GPU batch

All CPU. Cached run artefacts plus the deterministically rebuilt corpus plus
offline ground truth. No model was loaded, nothing was trained, epsilon was not
touched, nothing was renamed.

The replay that everything below rests on reproduces the recorded repair number
of all ten methods to an absolute error of 0.0000, on both audited runs.

## Verdict on the 67 percent result

**It is not a defensible safety trade off, and it is also not a mis calibrated
epsilon. It is one operator whose utility recheck does not work.**

Refusing edits is worth doing overall. Split by operator, on the heavy corpus:

| operator | rejections | total gain forgone | total harm avoided | net of refusing |
|---|---|---|---|---|
| IMPUTE | 138 | 1.32 | 29.06 | **+27.75** |
| DENOISE | 3 | 0.87 | 0.20 | -0.67 |
| RESEGMENT | 12 | **37.67** | 0.03 | **-37.64** |
| all | 153 | 39.86 | 29.29 | -10.57 |

Refusing an IMPUTE saves twenty times what it costs. Refusing a RESEGMENT costs
more than a thousand times what it saves. The whole of the negative comes from
twelve decisions, eight of which were wrong, and the median gain thrown away on
one of them is 5.95, so this is systematic rather than a couple of outliers.

Three independent facts point at the same place.

1. `ablate_no_reprobe`, which is the configuration that never consults model
   utility after an edit, is the only variant whose refusals are net positive
   at 67 percent contamination, at +22.18 against -10.57 for the full agent. The
   utility recheck is what does the damage.
2. `level_shift` carries 78.2 percent of the total error in the corpus, and
   RESEGMENT is the operator that repairs it. A single stratum decides the
   corpus mean, and the mechanism meant to fix that stratum is the one being
   vetoed.
3. The same audit on the small corpus, where level_shift is a fifth as
   frequent, has the full agent's refusals net **positive** at +10.17. The rule
   is fine until the stratum it mishandles becomes common.

Why the recheck fails on this operator specifically is not established and was
not investigated this round. The plausible mechanism is that RESEGMENT is the
only operator that changes the length of the window, so the post edit probe
scores a different holdout span than the pre edit probe did, and the two
utilities are not comparable in the way the acceptance rule assumes. That is a
hypothesis, and it is testable offline in the next round by recomputing utility
on a fixed span.

**Do not widen epsilon.** It would buy back the RESEGMENT gains by also
accepting the IMPUTE edits that the audit shows are correctly refused, trading
+27.75 of avoided harm for +37.64 of recovered gain, at the cost of the
protection numbers that are the method's actual result.

## The commit side, for completeness

Of 61 committed edits on the heavy corpus, 34 improved the window, a precision
of 0.557. Mean gain on a good commit 1.89, mean loss on a bad one 0.12. The
commit side is strongly net positive. The problem is entirely on the refusal
side, and within it, entirely on one operator.

## What the corpus mean is actually measuring

| stratum | n | nmse before | share of total corpus error |
|---|---|---|---|
| level_shift | 20 | 7.6788 | **78.2%** |
| noise | 20 | 0.9366 | 9.5% |
| spike | 20 | 0.8186 | 8.3% |
| duplicate | 20 | 0.2102 | 2.1% |
| everything else | 130 | under 0.1 | under 2% combined |

Reporting a single net utility mean on this corpus is close to reporting the
level_shift repair rate under another name. Any headline built on it inherits
that. The per contamination ledgers in `audit_heavy_real.md` and
`audit_small_real.md` should be the primary presentation, with the mean shown
only alongside the decomposition that explains it.

## Pareto frontier, gain against windows worsened

| method | net corpus gain | windows worsened | over clean | damage |
|---|---|---|---|---|
| stat_only | +0.731 | 68 | 0.500 | 0.0961 |
| ablate_no_reprobe | +0.495 | 35 | 0.257 | 0.0583 |
| ablate_no_protection | +0.493 | 25 | 0.271 | 0.0297 |
| ablate_no_verify | +0.442 | 59 | 0.400 | 0.1181 |
| ablate_no_peer_calibration | +0.314 | 20 | 0.200 | 0.0254 |
| introact_full | +0.311 | 20 | 0.200 | 0.0254 |
| no_action | +0.000 | 0 | 0.000 | 0.0000 |
| quality_rank | -0.015 | 43 | 0.400 | 0.0947 |
| always_clean | -0.032 | 153 | 1.000 | 0.2085 |

The full agent holds the fewest damaged windows of any method that edits at all,
tied with its own peer calibration ablation, which sits 0.003 above it in gain.
That difference is noise and the two should be treated as one point. Formally
that leaves the full agent just off the frontier, which is worth stating plainly
rather than rounding away.

## Ablation ladder, real models, heavy corpus

| rung | configuration | status | net | repair | over clean | damage | worsened |
|---|---|---|---|---|---|---|---|
| a  score only, no action | no_action | done | +0.000 | 0.000 | 0.000 | 0.0000 | 0 |
| b  repair, no verification | ablate_no_verify | done | +0.442 | 0.484 | 0.400 | 0.1181 | 59 |
| c  repair plus structure, no utility recheck | ablate_no_reprobe | done | +0.495 | 0.516 | 0.257 | 0.0583 | 35 |
| d  full agent | introact_full | done | +0.311 | 0.320 | 0.200 | 0.0254 | 20 |

Two rungs are missing and both need a GPU run.

- No ABSTAIN only ablation. The refusal path cannot currently be credited or
  blamed separately. Needs `PolicyConfig(min_confidence=0.0)`.
- No rung separates rollback from veto. Rungs c and d differ by the utility
  recheck, not by whether a vetoed edit is retried with a different operator, so
  the value of retrying is unmeasured.

## Seed coverage

Every number produced so far is seed 42, single run. That includes all three the
argument leans on: repair 0.367 on small with real models, the 2.4x gap to
stat_only at 67 percent, and the collapse from 0.367 to 0.141 when the
structural veto is removed. None has an error bar. Not run this round by
instruction.

## Next GPU session, one batch

Ordered by what the argument depends on.

1. **Contamination sweep**, 5, 10, 20, 35, 50, 67 percent, all methods. The
   audit predicts the crossover against stat_only sits where level_shift stops
   dominating the error budget, and this is the experiment that either locates a
   regime where verified curation wins outright or shows there is not one. Three
   seeds at minimum on the sweep points that matter.
2. **Cross model transfer**, curate with one TSFM as judge, then evaluate on a
   different TSFM and on a classical model that took no part. This answers
   whether the method overfits its judge, which is the credibility question a
   reviewer asks first about a model in the loop method.
3. **A competitive cleaning baseline.** stat_only and always_clean are both
   strawmen by construction. TSRating is the obvious candidate and whether it
   runs at all has been open since the scorer era.
4. **The two missing ablation rungs**, ABSTAIN only and rollback separated from
   veto.
5. **Three seeds on the headline configurations**, small and heavy, full agent
   plus the ablations the argument cites.

One offline item to do before that batch, because it costs nothing and may
change what is worth running: test the fixed span utility hypothesis for
RESEGMENT by recomputing the post edit probe on the same holdout the pre edit
probe used. If that recovers the 37.64, the fix is local to the probe rather
than to the acceptance rule.
