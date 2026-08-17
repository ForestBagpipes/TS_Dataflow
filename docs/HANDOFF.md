# Handoff, end of the experimental phase

State as of 2026-08-15. Everything below is committed. The transition this
document marks is from running experiments to writing the paper: the evidence
for the central claims is in hand, three experiments are still queued, and
what is missing is known and bounded.

## The claim, as the evidence now supports it

Acceptance of a data edit cannot rest on model utility alone, because utility
rises when data is flattened as well as when it is repaired. The contribution
is an execution time acceptance layer that requires a utility improvement and
structural preservation together and rolls back on failure, and that is
independent of the strategy proposing the edits.

Our own agent is one instance of proposer plus layer, not the subject of the
claim. That reordering is forced by the measurement in the next section.

## Established, with the number and where it lives

**The acceptance layer works on proposers that are not ours.**
`docs/gating_modularity.md`, `results/gating.json`. On a statistical rule,
damage falls from 0.0715 to 0.0016 and repair is retained at 70 percent. On an
unconditional cleaner, repair moves from -0.014 to +0.044, so a pipeline doing
net harm becomes net beneficial without one line of it changing, while damage
falls 97.0 percent. Of that cleaner's 1398 proposals, 725 were rejected on
structural distance against 452 on utility, so the structural term is the
principal gatekeeper.

**The gated statistical rule beats our own system on damage**, 0.0016 against
0.0020, at repair +0.255 against +0.181. This is why the claim is about the
layer rather than about our search.

**Protection holds across contamination rates.** `docs/protection_sweep.md`,
`results/sweep/sweep.json`. Damage on protected data is 0.085 to 0.129 for the
full method against 0.95 to 1.35 for unconditional cleaning, 0.35 to 0.78 for
a statistical rule and 0.25 to 0.31 for quality ranking, at every rate from 5
to 67 percent, with a flat curve while the baselines move by a factor of two.

**The behavioural signal measures predictability, not data quality.**
`docs/behavior_variable_identification.md`, `results/level_2x2.json`,
`results/ladder.json`. It decomposes into level positioning uncertainty at
+0.203 and local shape unpredictability at +0.141, roughly additive, isolated
by a 2x2 whose decisive pair holds local shape fixed at auc 0.716, p 1.4e-07.
Two competing explanations were tested and refuted: classical predictability,
since white noise scores below the real data anchor and AR(0.95) above
AR(0.30); and structural familiarity, since three of four deterministic
irregular forms score below the anchor.

**The false alarm on clean unpredictable data survives dropping half the
evidence.** `docs/ood_form_split.md`. Four generator forms are elevated
independently at auc 0.705 to 0.760. Dropping the two whose structure resembles
an injected defect leaves auc 0.715 at p 9.5e-13 over 105 windows.

**It replicates across four frozen backends.** `docs/cross_model_check.md`,
`results/cross_model.json`. Weakest at p 1.3e-04.

**Verification is the component that matters.** `docs/ablation_ladder.md`.
Removing it multiplies damage by 4.6 and doubles the edits for fifty percent
more repair. Peer calibration and abstention show no measurable effect and are
reported as such.

**The threshold can be calibrated with a guarantee.**
`docs/conformal_threshold.md`, `results/conformal_samepool_stage1.json`. Under
a same pool split the guarantee holds at every reachable target: three alphas
lie below a 0.0088 floor set by the action space and grid, five hold, and one
isolated violation at alpha 0.040 overshoots by 0.0025 with both neighbours
holding. Hand set thresholds realise 0.0200, 0.1025 and 0.1562 with no
guarantee attached to any of them.

**Downstream, defensively.** `docs/downstream.md`. Without the acceptance step
an aggressive pipeline degrades downstream MSE by two to eleven fold, patchtst
per seed -233, -1051 and -423 percent; with it, the same pipeline returns to
within a few percent of not curating. Three independently trained models agree
in direction.

**Two shield properties.** `docs/shield_properties.md`. Non blocking is proved:
KEEP has zero utility delta, zero structural distance and zero cost, so it is
admissible in every state. Minimal interference is partially satisfied at a
forgone rate of 0.263.

## Not established, or established negatively

**M4 predictability decorrelation is partial.**
`docs/predictability_decorrelation.md`. It raises corpus AUROC from 0.468 to
0.551, paired difference +0.083 CI [+0.060, +0.108], and removes the false
alarm on all four OOD forms, 0.705 to 0.760 down to 0.504 to 0.527. It costs
level_shift, flatline and duplicate detection, -0.119, -0.113 and -0.072. Both
directions are the same root cause: unpredictability from a displaced level and
from the structure itself are one quantity to this signal. Fully corrected it
still reaches only 0.551. Whether it enters the acceptance path is decided by
the queued integration test.

**Minimal interference is violated 26.3 percent of the time.** 304 of 1154
replayable vetoes would have improved the window. The utility condition
misfires on 29.7 percent of what it blocks and the structural condition on 19.7
percent, which is a fourth line of evidence that the model consulting condition
is the weaker one.

**No positive downstream gain from conservative curation.** Every effect for
stat_only, stat_only_gated and introact_full sits at or below its own model's
paired noise floor of 0.27 to 2.99 percent. The cause is mechanical:
introact_full edits 71 of 800 windows and leaves 91 percent of the corpus byte
identical. Dilution was ruled out, not assumed, by evaluating on the 515 edited
windows only.

**TSFM fine tuning skipped, by a pre committed criterion.** The criterion
required a paired noise floor under 3 percent and a decidable direction on the
affected subset. The first held, the second did not. A frozen TSFM is the
verifier in this method, not the object being curated, and that role division
is what the paper states.

**The profile misfire is not shown to generalise.** `docs/detector_crossval.md`.
Four of five standard detectors cannot separate contaminated from clean windows
on this corpus, contaminated lift 0.83 to 1.00, so they are not a valid control.
The fifth is silent on the stratum in question. Confirmed for our
implementation only.

**AegisTS cannot be run as published, and the authors confirmed it.** The
repository is missing the `Datasets` module that all four core modules import,
and `.gitignore` excludes it. **The authors were contacted and replied that the
data loading module cannot be located and cannot be supplied.** That exchange is
the basis for the reproducibility statement in the paper, which should record
both the request and the answer rather than only the absence.

A three day timeboxed faithful reproduction is now under way, reconstructing the
loader from the call sites. See `docs/aegists_reproduction.md` for the
acceptance criterion, the reconstruction evidence and the stop rule. It runs
outside the main queue and does not take priority over M2 or the soft against
hard comparison. The modularity claim does not depend on it, since two external
proposers already support it.

**M3 invariant specification not done.** Deferred. The structural distance
weights remain hand set, and that must appear in the limitations section as
stated rather than as a detail.

## Component three, settled

**Reading one.** The structural condition has measurable discriminative power on
the calibrated local operator path and none on the uncalibrated global path, and
the difference between them is significant. Three seeds, merged.

| path | n | odds ratio | accepted harm rate | rejected harm rate | vs blind |
|---|---|---|---|---|---|
| local | 2220 | **2.971** | **0.283** | 0.541 | p 1.0e-20 |
| global | 1283 | 0.954 | 0.560 | 0.548 | p 0.641 |

Interaction: log odds difference +1.136, CI [+0.711, +1.562], Wald p 1.6e-07,
Breslow Day p below 1e-16. The local baseline harm rate is 0.496, so the layer
takes the accepted side from 0.496 down to 0.283. On the global path the
accepted side is dirtier than the rejected side.

**Two tests are reported together and the disagreement is explained.** The
binomial test on veto precision gives p 0.0051 and 0.0030 for the two local
proposers at three seeds, and gave 0.092 and 0.054 at one seed. The association
test gives 1.0e-20. They differ because the binomial test reads only the
rejected side, which at an 84 percent rejection rate is forced towards the base
rate whatever the policy, while the association test reads both sides. The
rationale is in `docs/component3_verdict_criteria.md` and belongs in the paper
rather than being left for a reader to rediscover.

**Protected stratum recall is not significant** for any proposer, p 0.10 to
0.13. Safety on that stratum comes from rejecting a lot rather than from
rejecting selectively, and that is reported alongside the discriminative result
rather than instead of it.

**A withdrawn claim.** The earlier reading that the layer rejects a lot but not
accurately is wrong. Discriminative power is hidden on the rejected side by the
high rejection rate and is visible on the accepted side.

## Queued right now

Running under `setsid` on the box, so an SSH drop will not kill it. Sequence:

0. **global_path_fix**, running at shutdown time. Tests whether the whole
   series rewriters discriminate once they declare their actual changed point
   set as a footprint and travel the calibrated local path. The prediction is
   recorded in the script: the odds ratio should move from 0.954 towards 2.971
   if the uncalibrated path account is right, and if it does not move the
   account is wrong. Results land in `results/global_path_fix.json`.

1. **nested stability**, NOT started. Three hours did not fit before shutdown
   and it was removed from the queue rather than started and killed. The design
   is implemented and verified in `experiments/nested_stability.py`: nesting is
   exact, 10/10, 20/20, 40/40, 70/70 and 100/100 at each step, with the clean
   batch constant and the corpus size fixed. It replaces the first stability
   table, whose corpora shared only 22 to 43 percent of their windows and which
   therefore could not attribute a difference to the contamination rate.

2. **conformal rerun**, for `results/conformal_losses.npz` and to exercise the
   fixed sequence fallback. The stage 1 numbers already in hand are valid and
   are preserved at `results/conformal_samepool_stage1.json`; this rerun adds
   raw per window losses so any alpha or selection rule can be recomputed on
   CPU. Also produces the stability table across six contamination rates, which
   was interrupted twice and is currently missing.
2. **soft_vs_hard**, the highest value remaining experiment. It is the only
   controlled evidence for the mechanism difference against the closest
   competing design: a soft penalty sweep over mu against a hard veto sweep
   over tau, same proposer, same operators, plotted as a repair versus damage
   frontier. E3 depends on it.
3. **gating_m4**, the integration test. Criterion fixed before the run:
   protected edits must fall and repair must not drop more than 10 percent
   relative, otherwise M4 stays diagnostic.

Then, not yet queued: oracle upper bound and a random proposer, to complete the
main table.

## For the writing phase

**Method chapter, four modules.** M1 behavioural probe and what it measures,
evidence complete. M2 conformal acceptance threshold, evidence complete. M3
invariant specification, deferred, weights hand set. M4 predictability
decorrelation, diagnostic, integration pending.

**Experiments and what each carries.** E1 main table, the modularity claim,
needs oracle and random rows. E2 calibration curve, the guarantee. E3 soft
against hard, the architectural claim, queued. E4 decorrelation AUROC table,
done. E5 downstream, defensive only.

**Limitations to write, each with its number.** Structural weights hand set,
M3 deferred. Minimal interference forgone rate 0.263 and the utility condition
being the worse of the two at 29.7 percent. Behavioural risk is a within corpus
quantity, see `docs/scope_and_comparability.md`, and the same staircase scored
+0.535 in one corpus and -0.087 in another. No positive downstream gain at
under 9 percent change volume. The reachable risk floor of 0.0088. The profile
misfire not shown to generalise. Exchangeability required by the guarantee, with
the measured cost of violating it at 20 to 50 percent relative.

**Do not reintroduce.** Clean out of distribution data alarms the model more
than contamination, withdrawn, real cross domain windows score -0.017 against
contaminated at +0.090. Any ordering read off a median column without a
significance test. Instance normalisation as the mechanism behind the level
effect, tested and refuted. Pulse trains as the flattened windows, they were
edited 0 times of 52.

## Machine and environment

Box is `ssh -p 24509 root@connect.bjb2.seetacloud.com`. **The port changes when
the container is reassigned**, it has changed twice already, and the hostname
changing is the signal that running processes were lost. Work2 lives at
`/root/autodl-tmp/work2`, isolated from work1 by directory and conda
environment, interpreter at `/root/autodl-tmp/envs/w2`.

The SSH helper is at `~/.w2tools/remote.py`, moved out of the shared temp
directory because a script named `inspect.py` belonging to the other project
sits there and shadows the standard library. Do not add the temp directory to
`sys.path`.

Long jobs must be started with `setsid` and a queue script, or they die with
the SSH session. Two runs were lost this way before that was fixed.

Disk was at 12 GB free and is now 405 GB. **That was never the reason foundation
model fine tuning was skipped and it is no longer a constraint at all.** The
reason is and remains the protocol: the method modifies 8.9 percent of the
corpus, and while the paired noise floor is under 3 percent the direction on the
affected subset is not decidable, so the downstream protocol cannot resolve a
difference on models far cheaper to train than a foundation model. If that step
is reconsidered, what has to be solved is the change volume, not the hardware.

This distinction matters under review. Asked why no foundation model was fine
tuned, the answer is a measurement limit, not a resource limit.
