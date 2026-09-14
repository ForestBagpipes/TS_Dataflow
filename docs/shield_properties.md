# What the shield guarantees, and what it costs

The acceptance layer sits outside the proposer, watches each proposed edit, and
vetoes the ones that would violate the specification. Two properties are asked
of such a layer and are reported here, one measured and one argued. A third
that is often listed alongside them turns out to be a consistency check rather
than a property, and it has been moved out.

Source `results/shield_properties.json`, from the 2000 window run at tau 0.12,
epsilon 0.005, eta 0.62.

## Minimal interference, partially satisfied and quantified

A shield that vetoes everything is trivially safe and useless. The question is
how much of what it blocks would have been beneficial, judged offline against
the pristine series, which is a ruler the shield itself has no access to.

| veto reason | blocked | would have helped | forgone rate |
|---|---|---|---|
| utility condition | 768 | 228 | **0.297** |
| structural condition | 386 | 76 | **0.197** |
| **all** | **1157** | **304 of 1154 replayable** | **0.263** |

**About a quarter of the vetoes sacrifice an edit that would have improved the
window.** This is reported as partial satisfaction with a number attached, not
as the property being met. Reducing it, and particularly reducing the utility
condition's 29.7 percent, is future work.

## Non blocking, a proposition rather than a sample

**Proposition.** In every state at least one action is admissible.

**Proof.** KEEP returns the working copy unchanged, so its utility delta is 0,
its structural distance is 0 and its cost is 0. It is therefore never rejected
by the structural or risk conditions, and the utility condition applies only to
mutating actions. KEEP is admissible in every state, so the admissible set is
never empty and the layer cannot deadlock. A window can always be returned
untouched.

This is structural. A single counterexample would refute it and no amount of
sampling can establish it, which is why it is argued rather than measured. As
consistency evidence, KEEP appears 1930 times across the traces and no trace
has an empty step list.

## The utility condition is the less accurate one, and that is the point

The ordering in the table above is the result worth carrying into the argument.
**The condition that does not consult the model, the structural one, misfires
on 19.7 percent of what it blocks. The one that does consult the model misfires
on 29.7 percent.**

That is a fourth independent line of evidence about the same signal, and the
four together are what answers the obvious question of why model utility is not
enough on its own:

1. Corpus AUROC of the behavioural signal is 0.468, with a bootstrap interval
   entirely below 0.5, so it is systematically inverted rather than merely weak.
2. Predictability is a separable confound inside it, accounting for 9.4 percent
   of its variance and the whole of its failure mode.
3. Removing that confound raises it only to 0.551, CI [0.524, 0.577].
4. On the veto side it is also the less accurate of the two conditions, 29.7
   percent against 19.7 percent.

The signal is weak at detection and more error prone at acceptance. A
structural condition that never consults the model is a necessary second source
rather than a supporting one.

## Two quantities that must not be used to corroborate each other

The tau sweep found that loosening the threshold from 0.02 to 0.12 buys no
repair at all, only damage. This document finds that 26 percent of vetoed edits
would individually have helped. **These are different measurements and neither
supports the other.**

The sweep measures aggregate repair reduction over the corpus. This measures
the counterfactual benefit of each blocked edit in isolation. Both are true at
once: individually beneficial edits are being blocked, and their aggregate
contribution is cancelled by damage from other edits admitted at the same
threshold. Reading either as confirmation of the other would be a mistake, and
the honest picture needs both stated side by side.

## Moved out of this table, implementation correctness

All 404 admitted edits satisfy the three acceptance conditions, a rate of
1.000000 with zero violations.

**This is not a property of the method and is not presented as one.** The
`verify` function is implemented as exactly those three conditions, so anything
it admits satisfies them by construction. The check is worth running and worth
reporting as an assertion test, because it establishes that no code path
bypasses verification, for instance through an operator that mutates the
working copy outside the sandbox. It belongs in implementation correctness, not
in a list of guarantees.
