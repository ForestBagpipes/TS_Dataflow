# Handoff, state as of 2026-08-11

Everything below is committed. One job is still running on the GPU box, see the
last section before shutting anything down.

## The one thing to read first

This session changed what the paper claims. The old contribution one was that
clean out of distribution data alarms a frozen forecaster more than
contamination does. **That claim is withdrawn.** It was tested against real
cross domain data and against generated ladders and it does not survive either.

What replaced it is stronger, because it comes from controlled experiments
rather than from a stratum that happened to be in the corpus. Behavioural risk
measures how hard a window is for a frozen forecaster to locate and continue,
and it decomposes into two separable, roughly additive factors: level
positioning uncertainty, worth +0.203, and local shape unpredictability, worth
+0.141. See `docs/behavior_variable_identification.md` for the full argument.

## What ran this session

All on the GPU box, real TSFM backends, multi-family preset unless stated.

| job | scale | wall clock | result file |
|---|---|---|---|
| contamination sweep, 6 rates | 800 windows each | 4600s | `results/sweep/sweep.json` |
| ablation ladder, 8 rungs plus tau sweep | 210 windows | 800s | `results/ablations/ablations.json` |
| real cross domain perception | 1150 windows | 299s | `results/ood_check.json` |
| real cross domain curation | 1150 windows | 315s | `results/ood_curate.json` |
| controlled ladder, 12 rungs | 1200 windows | 181s | `results/ladder.json` |
| level 2x2 plus phi sweep | 1300 windows | 369s | `results/level_2x2.json` |
| cross model comparison | 600 windows | in progress | `results/cross_model.json` |

## The results that matter

**Protection, six contamination rates, `docs/protection_sweep.md`.** Damage on
protected data is 0.085 to 0.129 for the full method against 0.95 to 1.35 for
unconditional cleaning, 0.35 to 0.78 for the statistical rule and 0.25 to 0.31
for quality ranking. Same ordering at every rate, and the curve is flat while
the baselines move by a factor of two. This is the main table.

**Verification is the component, `docs/ablation_ladder.md`.** Removing it
multiplies damage by 4.6 and doubles the edits, for fifty percent more repair.
Peer calibration and abstention show no measurable effect and are written down
that way.

**Real cross domain windows are never edited.** 150 of them, zero accepted
edits, against 20 of 150 on the synthetic shapes with a minimum variance ratio
of 0.032. The practical argument holds: on multi domain corpora the method
neither misfires nor mis-edits.

**The flattening failure, `docs/triple_failure_analysis.md`.** Ten synthetic
clean windows had nine percent of their points edited and ninety six percent of
their variance removed, all landing on the same final utility near -2.0. The
structural guard missed them at a distance of 0.037 against a threshold of
0.12, because a local operator is judged outside the footprint it declares and
the damage happens inside it.

## What is still open, in priority order

1. **cross_model, running now.** Two of four backends reported. Both chronos
   variants show the level effect more strongly than the multi backend pool,
   walk against ramp auc 0.785 and 0.890. timesfm and surrogate are pending.
   The surrogate is the one with confirmed explicit instance normalisation, so
   it is the informative one for the mechanism.

2. **tau is off the efficient frontier and has not been moved.** The sweep
   shows damage rising sixfold from tau 0.04 to 0.12 while repair moves 0.004.
   Not changed, because the value would be chosen after seeing the failure it
   prevents, which is tuning against the test corpus. Needs held out selection.

3. **Two prepared repairs, neither applied.** A variance preservation term in
   the structural distance for local operators, which separates the ten
   destructive edits at ratio 0.03 from the three benign ones at 0.99 to 1.00.
   And a reachable OOD threshold, since 1e-3 on the 85th percentile of a
   normalised profile cosine distance admits nothing and fired 0 times in 210.
   Both change the acceptance rule and invalidate every run above.

4. **clean_ood edit economics not yet written up.** The numbers are in hand:
   20 edits at mean delta utility +25.81 against contaminated at +0.54, a
   factor of 48, with a minimum variance ratio of 0.032. This is the E3 figure.

5. **Posterior probabilities still not exported**, so a like for like AUROC of
   the combined signal against the profile remains deferred.

6. **Do not put the risk coverage curve in the paper** until `action_risk`
   stops consuming the class posterior, which is anti correlated with edit
   success and carries weight 0.45.

## Withdrawn claims, do not reintroduce

- Clean out of distribution data alarms the model more than contamination.
  Real cross domain windows score -0.017 against contaminated at +0.090.
- rare_valid and changepoint sit above contaminated. Their medians are higher
  and neither clears significance, p 0.13 and p 0.51.
- The behavioural signal measures predictability. White noise scores below the
  real data anchor and AR(0.95) scores above AR(0.30).
- The behavioural signal measures structural familiarity. Three of four
  deterministic irregular shapes score below the anchor.
- Pulse trains were the windows being flattened. They were edited 0 times of
  52. It was sawtooth, staircase and random walk.

## Naming and comparability, both deliberate

`real_ood` keeps its identifier in code so existing result files stay readable,
but every description now says cross domain. Exchange rate and solar power are
public benchmarks that may sit inside the backends' pretraining corpora and
membership could not be verified, so they are not strict out of distribution
evidence. See the comment block in `experiments/datasets.py`.

Behavioural risk is a within corpus quantity because peer calibration is
relative. The same staircase scored +0.535 in one corpus and -0.087 in another,
and both are correct. Never place a number from one run beside a number from
another. `docs/scope_and_comparability.md` has the rule and the two causes.

## Before shutting down

The box is `ssh -p 53677 root@connect.bjb2.seetacloud.com`, work2 lives at
`/root/autodl-tmp/work2` and is isolated from work1 by directory and by conda
environment. `cross_model.py` is still running there and writes
`results/cross_model.json` when it finishes. Nothing else is queued.

To collect it next session:

    python -c "import sys,tempfile,os; sys.path.insert(0,tempfile.gettempdir()); \
      os.environ.setdefault('W2_PASS','...'); from remote import client; \
      c=client(); s=c.open_sftp(); \
      s.get('/root/autodl-tmp/work2/results/cross_model.json','results/cross_model.json')"

The GPU bills while the instance is up. If the cross model result is not needed
immediately, stopping the instance is safe, the job can be rerun in about four
minutes.
