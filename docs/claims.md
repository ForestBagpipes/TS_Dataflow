# The claims, and the measurement behind each

Rewritten after the gating result. The previous version put our agent at the
centre; this one puts the acceptance layer there, because that is what the
evidence supports.

No `materials` directory exists in this repository, so terminology here is
drawn from the vocabulary already used across `src/introact_ts/` and `docs/`:
acceptance rule, execution time, structural distance, rollback, sandbox,
proposer, protected stratum, behavioural risk, statistical profile, model
utility. No new terms are coined and no borrowed method name appears.

## The one sentence claim

Acceptance of a data edit cannot rest on model utility alone, because utility
can be raised by flattening data as well as by repairing it. We give an
execution time acceptance rule that requires a utility improvement and
structural preservation together and rolls back on failure, and we show it is
independent of the proposing strategy: on a conservative statistical rule, on
an unconditional cleaner, and on our own search, it reduces damage to protected
data by roughly two orders of magnitude while retaining most of the repair.

## Contribution one, what the utility signal measures

Behavioural risk from a frozen forecaster measures predictability, not data
quality. It decomposes into two separable and roughly additive factors, level
positioning uncertainty at +0.203 and local shape unpredictability at +0.141,
established by a 2x2 with unit variance normalisation and a decisive pair that
holds local shape fixed, auc 0.716 at p 1.4e-07.

Consequences that were measured, not assumed:

- It fires on clean but structurally unpredictable windows. Four generators
  reproduce this independently at auc 0.705 to 0.760, and dropping the two
  whose structure resembles an injected defect leaves auc 0.715 at p 9.5e-13
  over 105 windows.
- It is silent on real cross domain windows, median -0.017 at auc 0.426, the
  calmest stratum in that corpus.
- It replicates across four frozen backends, weakest at p 1.3e-04.

Two candidate explanations were tested and refuted. Classical predictability
fails because white noise scores below the real data anchor and AR(0.95) scores
above AR(0.30). Structural familiarity fails because three of four
deterministic irregular forms score below the anchor.

## Contribution two, the acceptance layer and its independence of the proposer

This is the reordered claim. Source `docs/gating_modularity.md`.

The layer requires delta utility above epsilon, structural distance below tau,
and action risk below eta, applied to a sandbox copy with rollback on any
failure. It is placed around a proposer without modifying it.

| proposer | damage before | after | repair before | after |
|---|---|---|---|---|
| statistical rule | 0.0715 | 0.0016 | +0.366 | +0.255 |
| unconditional cleaner | 0.1919 | 0.0057 | -0.014 | **+0.044** |

The unconditional cleaner is the stronger case: it goes from net harmful to net
beneficial with no change to itself. Of its 1398 proposals, 725 were rejected
on structural distance against 452 on utility, so the structural term is the
principal gatekeeper.

**The gated statistical rule reaches damage 0.0016 against our full system at
0.0020.** A cruder proposer with the gate beats our own search on that axis.
This is the reason the claim is about the layer and not about our agent, and
our full system is presented as one instance of proposer plus gate.

## Contribution three, when the verification is worth its cost

Removing verification multiplies damage by 4.6 and doubles the edits for fifty
percent more repair. Peer calibration and abstention show no measurable effect
on this corpus and are reported as such. The structural threshold was selected
on a held out seed by a rule fixed in code before the numbers were seen, and
applied once: damage falls 75.2 percent for a repair cost of 0.012.

## What is deliberately not claimed

- Not that the method repairs better. `stat_only` repairs level shifts better
  at every contamination rate, up to +0.574 against +0.363.
- Not that behavioural signals beat statistical profiles at detection. They do
  not, except on defects with no local statistical trace.
- Not that the profile misfire generalises beyond our implementation. The
  detector cross check could not decide it, see `docs/detector_crossval.md`.
- Not that instance normalisation is the mechanism behind the level effect.
  That prediction was tested and refuted.

## Open, and honestly labelled

Downstream evidence that a gated corpus trains a better model is running and
unreported at the time of writing. AegisTS as a third proposer is blocked on a
missing module in its public repository. The pre registered prediction in
`docs/prediction_aegists.md` stands unverified and is not withdrawn.
