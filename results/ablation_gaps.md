# D  the two missing ablation rungs, defined but not run

Definitions only. Neither was run this round.

The ladder currently has four rungs with real model numbers on the heavy
corpus. Two mechanisms the paper claims credit for are not separable from what
is already measured.

## Rung one, ABSTAIN in isolation

**Claim it tests.** That refusing to act on insufficient evidence is worth
having as a distinct outcome, rather than being equivalent to proposing
something and having it vetoed.

**Why it is not covered.** Every current configuration keeps the refusal path.
`ablate_no_verify` disables the three acceptance conditions but leaves
`PolicyConfig.min_confidence` at 0.32, so windows with a flat posterior still
return ABSTAIN before any candidate is generated. Nothing measures what
happens if the agent is forced to always name an action.

**Configuration.** `AgentConfig(policy=PolicyConfig(min_confidence=0.0))`,
everything else at the full agent settings. With the floor at zero the
insufficient evidence branch is unreachable and the policy always falls through
to the defect routing.

**What to read.** Abstain rate falls to zero by construction, so the numbers
that matter are over cleaning and damage on the protected strata, and the edit
precision. If they barely move, ABSTAIN is decorative and the paper should stop
claiming it. On the heavy corpus the full agent currently abstains on 3.3
percent of windows, which is small enough that this is a real possibility.

**Cost.** One curation pass over the corpus, no new perception. Perception is
shared across configurations in `run_agent.py`, so this is the cheapest
addition available.

## Rung two, rollback separated from veto

**Claim it tests.** That retrying with a different operator after a rejection
is worth more than simply declining and moving on. This is the reversible part
of the method rather than the verified part.

**Why it is not covered.** Rungs c and d differ by whether model utility is
consulted after the edit, not by what happens once a candidate is refused. In
every current configuration a rejected candidate falls through to the next
proposal in the same step, so veto and retry are always on together.

**Configuration.** A policy that returns at most one mutating candidate per
window, so a rejection ends the episode instead of advancing to the next
proposal. That is not exposed as a flag today. The smallest change that
expresses it is a `max_candidates` field on `PolicyConfig`, defaulting to
unlimited, consumed in `propose_actions` where the ordered candidate list is
assembled.

**What to read.** The gap between this and the full agent is the value of
retrying. On the heavy corpus the full agent attempts 2.02 probes per window
against 1.0 for a single shot policy, so the retry budget is real and its
payoff should be visible in repair without a matching rise in damage.

**Cost.** One curation pass, plus the small policy change above. The change
touches the policy layer, so it needs the usual test pass before it is used to
produce a number.

## Both belong in the next batch

They are the two cheapest items on the list, they share perception with
everything else in the same run, and each one closes a claim the paper
currently makes without evidence.
