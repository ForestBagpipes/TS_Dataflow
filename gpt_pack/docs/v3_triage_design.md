# v3, window level triage learned from training dynamics

Design document, **halted 2026-09-01**. The trajectory probe was run under the
registered protocol (PatchTST proxy learner, CV grouped by source dataset) and
returned a combined AUROC of 0.5794, below the pre-registered 0.65 stop
threshold. The earlier 0.7028/amber run used a three-layer MLP and random folds
and is marked obsolete. No training-dynamics triage layer is being built; the
rest of this document is kept as the failed pre-registration record.

## Why the signal has to come from somewhere else

Three independent attempts to separate a mis perceived protected window from a
genuinely contaminated one, all on the shield's own signals, all measured:

| signal | can it separate | evidence |
|---|---|---|
| structural distortion | no | the two distributions overlap; DESPIKE's own family threshold calibrates to zero because 40.2 percent of its candidates carry a loss of one by construction |
| utility gain | no, and it is worse than neutral | 93.2 percent of DESPIKE's candidates clear it, and on the synthetic probe layer the mean gain is 30.2 against 1.83 on genuinely contaminated windows |
| decision risk | no, and on two families it runs backwards | IMPUTE refuses 0.6341 of protected candidates against 0.9522 of contaminated ones; RESEGMENT 0.1767 against 0.2827 |

And the perception layer's own confidence cannot do it either: fourteen
thresholds were swept against a pre registered criterion and none met it,
because the mislabelled windows have median confidence 0.5413 against 0.6121 for
the correct ones.

**The reason is structural, not a matter of picking better features.** The
injected contaminations are built to imitate the shape of real anomalies, and
the protected strata are by construction the windows that look anomalous while
being real. On any static snapshot the two classes intersect. A different
static space, whether an optimal transport geometry or a sparse autoencoder
basis, can shrink the overlap but cannot remove a class boundary that does not
exist in that space.

Training dynamics ask a different question: **not what this window looks like,
but how it behaves under learning pressure.** An injected segment has no
generative relationship with the rest of its window, so a learner fitting it
shows conflict, it is learned late, forgotten easily, and unstable across seeds.
A genuinely rare window shares its generating process with the rest of the
corpus, so it is learned slowly but stably. That axis is orthogonal to the
snapshot.

## Whose training dynamics

The time series foundation models are frozen and stay frozen. The trajectory
comes from a **proxy learner already in the evaluation pipeline**: PatchTST or
DLinear trained on the curated corpus, with per window loss logged each epoch.
The marginal cost is the logging plus running three seeds instead of one.

A second, complementary axis needs no training at all: sweeping the context
length and the mask pattern against the frozen foundation models and reading how
stable the readout is under those conditions. That is a probing trajectory
rather than a learning trajectory, and it is the fallback if the proxy learner's
signal is not strong enough on its own.

## The signature the probe has to find

Stated before the probe runs, so it can fail.

| stratum | expected trajectory |
|---|---|
| clean | learned fast, no forgetting, low seed variance |
| contaminated | high residual error, dense forgetting events, high seed variance |
| hard | learned slowly but monotonically, low forgetting |
| rare_valid | like hard, slower still |
| clean_ood | persistently high error but **stable**, few forgetting events, low seed variance |

The last row is the one that matters most for the failure this is meant to fix.
A model failing to fit a window is not evidence the window is corrupt, and the
static utility readout cannot tell the two apart, which is exactly why it prefers
the probe layer by a factor of sixteen. Triage should abstain on windows that are
persistently hard and stable, and act on windows that are unstable.

## Where triage sits, and what it is not allowed to do

After perception, before `propose_actions`. Its action space is

    abstain            the window is not offered to the proposer at all
    release            the proposer runs as it does now
    probe further      spend more budget on perception before deciding

**It gates, it does not generate.** Triage never constructs a candidate and
never bypasses `propose_actions`. Everything that reaches the shield still comes
from the proposer and is still judged by its family's calibrated threshold, so
the guarantees in theorems 2, 4 and 5 carry over unchanged. That is a design
constraint, not a convenience: a triage layer that could inject its own
candidates would sit outside the calibrated population and void the conformal
argument.

## State, reward, and the degenerate solution to avoid

**State.** The perception profile, the trajectory signature, the family
posterior, and the hypothesis confidence. The confidence stays in even though it
cannot separate the classes on its own, because a feature that is useless alone
can be useful in combination.

**Reward.** Realised utility change minus the corrected damage, the one that
counts discarded data.

**The degenerate solution.** Abstaining everywhere earns zero damage and zero
utility, and if abstention is free that is the optimum. So abstention is shaped:
a small negative on a window that carried a defect, a small positive on a window
that did not. This makes triage a classification problem with asymmetric costs
rather than a switch that can be left off. The shaping constants are the one
place a new hyperparameter enters, and they have to be reported with a
sensitivity sweep rather than tuned quietly.

**Value table.** The rung dimension added for v2 stays; triage adds a decision
dimension above it. The rule that every adjudicated candidate updates its own
slot, refusals included, is unchanged.

## The calibration constraint, written down before it is violated

The calibration population for the family thresholds is currently the routed
candidate set. With triage in front of the proposer it becomes **routed and
released**, and that population moves as the policy learns. Calibrating on one
population and deploying on another is the mistake this project has now made
five times: the corpus, the candidate generator, the conditioning set, the
smoke bed and the loss definition.

So the constraint is fixed here, and one of the two must hold:

  **frozen policy** the triage policy is frozen, the thresholds are calibrated
  under that snapshot, and both ship together

  **rolling recalibration** the thresholds are recalibrated on a sliding window
  of recent decisions, at a stated interval, and theorem 6's decay bound covers
  the gap

The first is simpler and is the default for the paper. The second is the honest
form for a deployed system and is what the discussion should say. Silence on
this point is not an option.

## Ablations, fixed now

  without the trajectory features, static state only
  without RL, the same features under a fixed threshold rule
  without the risk condition, since its behaviour on protected candidates runs
  backwards and it may be a liability rather than an asset
  routed against unrouted proposals, using the indiscriminate calibration data
  already on disk

The second is the one that decides whether RL is earning its place. If a fixed
rule on the same features does as well, the honest conclusion is that the
signal was the contribution and the policy was not.

## The gate, and what fails it

The probe is described in the task brief. Its criterion is an AUROC of at least
0.80 for separating mis perceived protected windows from genuinely contaminated
ones, using the trajectory features under five fold cross validation with the
test fold excluded from feature selection and threshold choice. Between 0.65 and
0.80, the frozen model probing axis is added and it is measured once more.
Below 0.65, this design is not built.

**Result.** PatchTST, grouped by source dataset: combined AUROC 0.5794
(random-split optimistic AUROC 0.6787); clean_ood vs contaminated 0.3004. This
fails even the 0.65 continuation threshold, so the training-dynamics branch is
stopped. The 0.7028 amber run (three-layer MLP, random folds) is obsolete and
must not be cited.

## Relation to influence functions

TimeInf and the valuation family estimate a sample's value offline, once, from a
trained model. The trajectory features here are a state signal inside an agent's
loop, read while the decision is being made and fed to a policy that acts on it.
The two answer different questions and the paper has to say so plainly, because
a reviewer who has read the valuation literature will otherwise assume this is
that with more steps.
