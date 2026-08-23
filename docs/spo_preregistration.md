# SPO pre registration

Written 2026-08-18, before any SPO code was run. Everything below is fixed here
so that no choice among these can be made after seeing which choice is more
favourable. Stage zero has run and its results are cited, nothing else has.

## The cluster count k

**k is 12.**

Criterion, stated so it can be checked: **the largest k whose cell occupancy is
at least 0.75.** Occupancy is the fraction of cluster crossed with operator
cells that the fixed policy actually visited, which is what warm starting can
fill from history.

From `results/spo_feasibility.json`:

| k | occupied | total | occupancy |
|---|---|---|---|
| 10 | 30 | 40 | 0.750 |
| 12 | 36 | 48 | **0.750** |
| 15 | 39 | 60 | 0.650 |
| 20 | 49 | 80 | 0.613 |

10 and 12 tie at 0.750, so the larger is taken, which is 12.

**This criterion is independent of any significance result.** It reads only the
occupancy column. It does not read the chi square or the permutation p, and it
would return the same k if every one of those tests had come back flat.

**When it was formed, stated plainly.** After the stage zero coverage table
existed and before any SPO run. It is not a blind pre registration. The reason
it is still worth recording is that occupancy and significance are separate
columns, and the tie break rule takes the larger k, which is the one where
IMPUTE's permutation p is *worse* than at k equal to 10, namely 0.0043 against
0.0031. Choosing on significance would have picked k equal to 10.

All four values of k are retained as a sensitivity analysis. Every stage zero
number for k in 10, 15 and 20 stays in the result file and in the paper's
appendix. No k is dropped.

## Corpus split for policy learning

Training and evaluation corpora do not overlap. The split is by window, drawn
once, and its seed is fixed here.

| item | value |
|---|---|
| split seed | 20260818 |
| training fraction | 0.40 |
| evaluation fraction | 0.60 |
| split unit | window |
| stratification | by stratum, so both halves carry all six layers in proportion |

The seed is written here rather than chosen at run time so that a rerun cannot
quietly land on a friendlier partition. Evaluation is the larger half because
every headline number is reported on it.

## Pre registered read outs

These three are fixed before their experiments run. Each names the outcome that
costs us the claim, at the same level of detail as the outcome that supports it.

**Experiment four, policy learning gain.** The improvement of the learned policy
over the fixed rule counts as established only if it exceeds the seed to seed
spread. That spread is measured first, on the fixed rule alone across multiple
seeds, and it is measured before the learned policy is run. If the improvement
falls inside the spread it is reported as not established, not as a trend.

**Experiment two, reward shaping.** If the flattening action proposal frequency
curves of the two policies do not differ significantly, the reward shaping claim
does not hold, and it is rewritten as no effect of this mechanism was observed
under the present setting. It is not rewritten as a smaller effect or as
directionally consistent.

**Experiment three, exploration safety.** If cumulative damage under the sandbox
arm grows with interaction count, that indicates an implementation fault rather
than a fault in theorem three. The implementation is checked first and the
finding is not reported as evidence against the theorem until the implementation
has been cleared.

## Expected shape of the result, recorded so it can be wrong

Stage zero found IMPUTE's admission rate ranges from 0.000 to 0.222 across
clusters at k equal to 12. Even the best cluster admits about two in nine.

The consequence for experiment four is that **the main gain available to policy
learning is suppressing hopeless proposals rather than raising repair volume.**
Damage and repair should improve only modestly. The larger separation should
appear in experiment five, on budget efficiency, because avoided proposals are
avoided probe calls.

This is written down now so that a modest damage and repair result is read as
the predicted outcome rather than as a disappointment, and equally so that a
large one is read as contradicting the stated expectation.

## What stage zero does and does not license

Licensed. There is cluster level structure in admission for IMPUTE, which
carries 1215 of 1561 adjudicated candidates. Its permutation p is below 0.05 at
all four k and below the Bonferroni threshold of 0.0125 at k equal to 10, 12 and
15.

Not licensed. **RESEGMENT has no cluster level structure**, permutation p from
0.81 to 0.96 at every k. DESPIKE loses significance as k rises, 0.0202 at k
equal to 10 up to 0.2226 at k equal to 20, which reads as insufficient
resolution rather than as structure. DENOISE is below 0.05 at every k but
carries only 71 candidates with 8 to 10 cells below the expected count rule, so
it is not treated as independent evidence.

The clustering is not a restatement of the stratum label. Adjusted mutual
information between cluster and stratum is 0.1502, 0.1473, 0.1417 and 0.1384 at
k equal to 10, 12, 15 and 20.

## Learning loop configuration, fixed before the first run

Written 2026-08-19, before any policy learning run. The monitor asserts this
hash at startup and aborts if it differs, so a run that reports these settings
cannot have used others.

**Configuration hash: `3b38ecf2a2f5a51f`**

The hash covers every key in `monitor.LEARN_CONFIG_KEYS`, and a test
checks that list against this table so a new hyperparameter cannot be
added to the code without appearing here. Two earlier values are
superseded, `fea464c049f8c5ad` which predates the injection parameter and
`669ce2f1341ed6ca` which predates `t_cal`. `t_cal` was added on 2026-08-22
when theorem 6's instrumentation landed. It is a recording interval and no
decision reads it, but it sets the T_cal term of the theorem's own bound, so
a run must not be able to report that bound under an interval it did not use.

| key | value | source |
|---|---|---|
| k | 12 | occupancy criterion above |
| split_seed | 20260818 | this document |
| corpus_seed | 42 | the corpus every earlier result used |
| scale | xl | 2000 windows |
| reward_clip | 5.886732284690514 | 95th percentile of training rewards |
| alpha | 0.02 | table 3 of the progress document |
| c_u | 1.0 | table 3 |
| c0 | 0.01 | table 3 |
| optimistic_init | 1.0 | above any warm started value |
| warm_start_cap | 20 | pseudo visits ceiling |
| tail_floor | 5 | minimum cluster size |
| p_inject | 0.05 | injection probability, see below |
| t_cal | 500 | decisions between recalibrations, table 3 |

## The two blind spot cells, and what either outcome means

Cluster 1 and cluster 11 hold 212 and 180 windows, 392 together, which is 19.6
percent of the corpus. The fixed policy proposed DENOISE on neither, so both
cells enter learning at the optimistic value with no history behind them.

**This result is reported from the first run, whichever way it comes out.** No
rerun, no configuration change, no second look. Recorded here because the two
outcomes point in opposite directions for the paper and the temptation to prefer
one of them is exactly what a pre registration is for.

If the admission rate on these cells is meaningfully above zero, the fixed
policy was leaving real repairs on the table, and the case for learning is
stronger than the aggregate numbers suggest, because the aggregate is dominated
by cells the fixed policy already visited.

If it is near zero, the blind spot was not a loss. The fixed policy declined to
propose DENOISE there for a reason the policy itself never articulated, and the
optimistic initialisation will have spent probes confirming it. That is a cost
of exploration and it is reported as one, with the probe count attached.


## Forced candidate injection

The first xl learning run visited clusters 1 and 11 on DENOISE **zero times**.
Not a low admission rate, no observations at all. The cause is a layer mismatch.
Optimistic initialisation raises the value of an unvisited cell so the bound
will select it, but the bound only ever chooses among candidates the proposer
emitted, and the proposer derives its candidate set from the dominant defect
field, which on those 392 windows is never noise. Nothing the selection layer
does can reach a cell the proposal layer never offers.

Injection addresses it at the layer the problem is on. When a cluster and
operator pair has no observation, that operator is forced into the candidate set
with probability **p_inject = 0.05**, and the injected candidate then goes
through the sandbox and the full shield exactly like a proposed one.

**Theorem 3 is unaffected.** Its proof turns on where the operator is applied and
what gate the commit passes, not on where the candidate came from. An injected
candidate is applied to the sandbox copy and committed only if the structural
condition holds, so the bound on committed structural distortion holds for any
candidate source. This is stated in section 3.3 of the progress document.

Injected candidates use the most conservative parameter each operator offers,
because an injection is a probe into a cell nothing is known about and should
not also carry an aggressive setting.

### The three outcomes, fixed before the rerun

**Admission rate meaningfully above zero.** Both the fixed rule and the pure
reordering policy were leaving real repairs unclaimed on a fifth of the corpus.
This is the strongest case for policy learning available in this work, because
it is a gain no reordering of the existing candidate set could produce.

**Admission rate near zero.** The proposal layer was right to withhold DENOISE
there. The blind spot was not a loss, and the probes injection spent are the
price of establishing that. The probe count is reported alongside.

**Still zero visits.** The injection did not fire, which is an implementation
fault rather than a finding. The implementation is checked before anything is
concluded.

### Sensitivity

p_inject is swept over 0.02, 0.05 and 0.10. Reported per level: visits to the
two blind spot cells, total probe cost, and the headline damage and repair. The
sweep establishes whether the conclusion depends on the injection rate.


## Injection parameters corrected, 2026-08-23

**What changed.** `INJECT_PARAMS` in `src/introact_ts/spo.py`.

| operator | before | after | operator default |
|---|---|---|---|
| IMPUTE | `method=linear` | unchanged | `seasonal` |
| DENOISE | `strength=light` | unchanged | `medium` |
| DESPIKE | `{}` | `n_sigma=6.0, max_width=1` | `n_sigma=4.0, max_width=3` |
| RESEGMENT | `{}` | `min_keep_frac=0.9` | `min_keep_frac=0.5` |

**Why this is a correction and not a tuning.** Section 3.4 states that an
injected candidate takes the operator's least aggressive setting, on the ground
that it is probing a cell with no information behind it and should not also
carry an aggressive configuration. An empty dict does not do that. It falls back
to the operator's own default, which is its ordinary working point rather than
its conservative end. So the stated design held for DENOISE and IMPUTE and was
silently absent for the other two. The change makes the code do what the
document already said.

Nothing here was chosen after seeing a result. The direction of each parameter
is fixed by the operator's own signature: a higher `n_sigma` flags fewer points,
a smaller `max_width` touches only the narrowest excursions, a higher
`min_keep_frac` discards less of the window.

**Verified rather than asserted.** On a window carrying one two point spike and
one single point spike, the injected DESPIKE configuration changes 1 point and
the default changes 3.

**Wording in 3.4.** From most conservative to least aggressive. IMPUTE's
conservatism is in not assuming a period while the others' is in a magnitude,
and one phrase could not cover both axes honestly.

**Code hash.** The method layer hash moves from `6741ded339e5a8df` to
`fcd7ba0bf05d5277`. `spo.py` is in `monitor.CODE_FILES`, so a run started
against the old expected hash aborts rather than silently using the new
parameters.

**Effect on the blind spot cells.** Clusters 1 and 11 were reported from the
first run under the pre registration's no rerun rule. That rule protects a
result from being rerun until it is favourable. It does not freeze an
implementation defect. The two versions are therefore reported side by side,
never the corrected one alone, and the comparison is run on one corpus under one
clustering. The protected layers have been rebuilt twice since that first run, so
cluster identity is matched by profile centroid rather than by cluster index, and
the matching is stated with the result.
