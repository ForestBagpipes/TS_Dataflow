# Theorem revisions required by the per family calibration

Three statements refer to a single global structural threshold. After the
calibration is done per operator family there is one threshold per family and
the statements have to say so. Each entry below records what the current text
says, what has to change, whether the proof survives, and which line of the
proof was the load bearing one.

The proofs were read line by line before any of this was written. Where a proof
is unaffected that is asserted with the reason, not assumed.

## Theorem 4, exploration structural safety

**Current statement.** For any policy and any exploration strength, every
committed edit satisfies `D_struct < tau`, so the structural distortion of the
curated corpus is bounded independently of the policy.

**Change.** `D_struct(a) < lambda_{f(a)}`, with `f(a)` the operator family of
the committed action. The corpus level bound becomes `max_f lambda_f` rather
than a single `tau`.

**Does the proof survive.** Yes, unchanged. Its two load bearing facts are that
the action is applied to a copy and that the working copy is updated only when
all three conditions hold simultaneously. Neither mentions what the structural
threshold is or whether there is one of them or four. The proof never opens the
threshold.

**What is actually strengthened.** The old statement was vacuous for one family.
RESEGMENT's measured distortion was identically zero on all 2766 attempts
because the alignment step removed the region the operator acts on, so
`D_struct < tau` held trivially for every crop no matter how much it discarded.
A bound that holds by construction bounds nothing. With the discard term in the
measure and a family threshold calibrated on that measure, the same sentence
now constrains crops for the first time.

## Theorem 5, risk control

**Current statement.** Given exchangeable calibration and deployment data and a
bounded risk function monotone in the threshold, the threshold selected by
conformal risk control at level alpha satisfies: the expected damage rate of
committed edits on deployment data is at most alpha.

**Three changes.**

*One.* The boundedness sentence in the proof reads "the risk function takes
definition 1's zero one indicator, valued in [0,1], so boundedness is
automatic". Damage is now `max(worse, discard_share)`, continuous on [0,1].
Replace with "the risk function takes definition 1, valued in [0,1], so
boundedness follows from the definition". **The proof survives**, and this is
the only line in it that mentions the indicator. Conformal risk control is
stated for bounded losses in general; the old wording narrowed it to the binary
special case for no reason.

*Two.* The guarantee is now per family, so the statement quantifies over
families: for each family f, the threshold `lambda_f` selected at level alpha
controls the expected damage of the candidates that family's threshold admits.

*Three, and this one is a genuine weakening that has to be stated rather than
hidden.* The calibration is at the candidate level, not the window level. It
controls the expected damage of an admitted candidate. A window that commits
more than one edit is not directly covered, and the candidate level bound is
the conservative side there. A remark says so.

**A fourth change that is not about the loss.** The premise is exchangeability
between calibration and deployment. That premise was false: the calibration
corpus was built on `ett` and deployment runs on `mixed`, and `ett` contains no
financial series while 44.6 percent of `mixed` is financial. This is why the
deployed damage rate sat at four times alpha. The corpus has been rebuilt on
`mixed` at deployment's stratum shares with zero content overlap. The theorem
did not need changing for this; the experiment did.

## Theorem 2, the soft penalty's damage lower bound

**No change. Not one word.**

Read line by line. The proof is algebraic: acceptance holds exactly when
`dU / D_struct >= mu`; on the class of windows where a harmful action's ratio is
at least `c`, the criterion holds identically for `mu <= c`, so those actions
all enter the acceptance set and their damage does not vanish under any choice
of the parameter. **Nowhere does it use the indicator property of damage.** It
argues about which actions are accepted, never about how much each contributes.

Under a continuous loss the conclusion reads "the expected damage has a positive
lower bound independent of the threshold" instead of "the damage rate has", and
the argument is untouched. The continuous loss makes the theorem's empirical
side stronger rather than weaker: a harmful crop used to contribute zero and now
contributes its discard share, so the lower bound has more substance.

## Theorem 6, calibration decay

Unaffected by the per family change; its terms are the reward clip, the
calibration interval and the visit counts, none of which is the structural
threshold. It has a separate problem recorded in `docs/number_selfchecks.md`:
the bound evaluates to between 4531 and 5426 at the median gamma, on a quantity
bounded by 1 by definition, so it is vacuous at this corpus size and cell count.
The cause is `n_min` of 1 rather than the gamma tail. That is reported as
measured; no revision to the statement is proposed here.

## What still has to be checked before these go into the document

The per family thresholds are being calibrated now. Two of the revisions above
assume the calibration produces a usable threshold per family. If a family's
sample is too small for its own calibration, its statement has to say what was
done instead, and silently falling back to a global value is not an option.


## What triage does not change, and the one condition on that

v3 puts a gate between perception and the proposer. It decides whether a window
is offered to `propose_actions` at all; it never builds a candidate and never
hands one to the shield directly. Everything reaching the three conditions still
comes from the proposer and is still judged against its family's calibrated
threshold.

**So theorems 2, 4 and 5 carry over unchanged**, each for its own reason.

Theorem 2 is about which actions a weighted sum accepts among those offered. A
gate upstream changes what is offered, not how the rule ranks them.

Theorem 4's proof uses two facts: the action is applied to a copy, and the
working copy is updated only when all three conditions hold. Neither is touched
by a gate that runs before any candidate exists.

Theorem 5 is the one with a condition attached. Its guarantee is over the
population the thresholds were calibrated on, and with triage in front the
deployed population becomes routed and released rather than routed. The theorem
holds on the deployed population only if the calibration was done on that same
population.

**The constraint, therefore, and it is not optional.** Either the triage policy
is frozen and the thresholds are calibrated under that snapshot, so the two ship
as a pair; or the thresholds are recalibrated on a rolling window of recent
decisions at a stated interval, with theorem 6's decay bound covering the gap.
`docs/v3_triage_design.md` records which was chosen. A learning triage policy
deployed against thresholds calibrated before it started learning would be the
sixth instance of the calibration and deployment populations differing, and the
first five each cost a rerun or a retracted claim.
