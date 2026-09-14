# CORA, conformal risk controlled agents for mobile GUI automation

arXiv 2604.09155, first public 2026-04-10. Feng, Du, Wang, Ma, Niu, Matsuo,
Feng, Yu. **Prior work relative to a 2026-09-24 submission.**

## What it does

A vision language model agent proposes GUI actions on a phone. A separate
Guardian model estimates an action conditional risk for each proposed step.
Conformal risk control calibrates an execute or abstain threshold on that risk
so that the rate of harmful executed actions respects a user specified budget.

Harm is defined by step level labels in real mobile contexts, covering
financial, privacy and social harm. Evaluated on a benchmark the paper
introduces plus public ones.

## What it shares with this work

The shape of the mechanism. A proposer emits candidate actions, a separate
component scores each one before it takes effect, and a calibrated threshold
turns that score into execute or abstain with a distribution free guarantee on
a bounded risk. The abstain option plays the role our identity action plays.

## Where it differs, and it is the premise not the machinery

**The Guardian's risk estimate is taken as a proxy for harm.** The calibration
makes the proxy's error rate controlled; it does not ask whether the proxy
points the right way. That assumption is reasonable in their setting, where a
harmful GUI action is harmful independently of how any model feels about it,
and the Guardian is trained on labels of exactly that harm.

Our setting breaks it. The natural verifier for a data edit is whether a model
does better on the result, and a model does better on data that has been
flattened. We measure the resulting signal at a corpus AUROC of 0.468 with a
bootstrap interval entirely below 0.5, meaning it ranks harm as safety over a
region we can characterise. Calibrating that signal to a budget would deliver
the budget and not deliver safety.

**Consequence for the design.** They calibrate one signal. We calibrate a
condition that does not consult the model at all, and the calibration sits on
the structural distance rather than on the model's opinion.
