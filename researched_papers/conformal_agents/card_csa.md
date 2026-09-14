# Conformal selective acting, anytime valid risk control for RLVR trained models

arXiv 2605.20270, first public 2026-05-18. Khosravi, Huo. **Prior work relative
to a 2026-09-24 submission.**

## What it does

A wrapper around a locally deployed language model fine tuned with
reinforcement learning from verifiable rewards. It maintains a per round error
guarantee, controlling a selective risk of the form R_act <= alpha + O(N^-1/2),
using per threshold e processes evaluated against the training filtration with
a Bonferroni grid. The point is per deployment validity without averaging over
long runs or pooling across deployments.

Evaluated on eight specialist benchmarks, sixteen adversarial shift scenarios
and five live training cells across four base models.

## What it shares with this work

Two things. Selective action, meaning the system may decline to act rather than
being forced to choose among actions, and the insistence that a guarantee hold
at the scale a user actually experiences rather than in aggregate.

The anytime valid construction is stronger than what we use. Our calibration is
split conformal on a fixed calibration set, which is a weaker instrument that
suffices because our thresholds are fixed before deployment rather than updated
online.

## Where it differs

**Verifiable rewards are the premise.** The setting is defined by having a
reward that can be checked, and the risk signal inherits its reliability from
that verification. The paper assumes isotonic calibrated monotone risk and
predictable updates.

We have no verifiable reward. The closest available quantity is model utility,
and we show it is not merely noisy but inverted on the data that must be
protected. Where their signal is reliable by construction, ours is
unreliable by measurement, so the response cannot be a better calibration of
the same signal.

**Monotonicity.** They assume isotonic calibrated monotone risk. We verify
monotonicity per run rather than assuming it, and fall back to fixed sequence
testing when the calibration half is not monotone. This is a small point of
method but it is the same assumption seen from the other side.
