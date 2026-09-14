# The acceptance rule works on proposers that are not ours

800 windows, real TSFM backends, tau 0.02 selected on a held out seed. Each
gated arm runs the same operators its ungated counterpart chose, in the same
order, with the same parameters. Only the accept or roll back decision differs,
so any difference is the gate and not a different search.

## Main table

| method | damage | repair | edits | protected edits | edit precision | windows worsened |
|---|---|---|---|---|---|---|
| *reference bound, does not curate* | | | | | | |
| *no_action* | *0.0000* | *+0.000* | *0* | *0* | | *0* |
| **methods that edit** | | | | | | |
| stat_only | 0.0715 | **+0.366** | 446 | 226 | 0.493 | 274 |
| **stat_only_gated** | **0.0016** | +0.255 | 77 | **33** | 0.571 | **22** |
| always_clean | 0.1919 | -0.014 | 800 | 520 | 0.350 | 691 |
| **always_clean_gated** | **0.0057** | **+0.044** | 198 | **125** | 0.369 | **146** |
| introact_full | 0.0020 | +0.181 | 71 | 26 | 0.634 | 29 |

## What the gate does

On the statistical rule: damage falls 97.8 percent, protected edits fall from
226 to 33, windows worsened fall from 274 to 22, and repair is retained at 70
percent of its ungated value.

On unconditional cleaning the result is stronger, because that method starts
below zero. Repair moves from **-0.014 to +0.044**: a pipeline that was doing
net harm becomes net beneficial without a single line of it changing. Damage
falls 97.0 percent at the same time.

The rollback reasons show which condition does the work. Of 1398 proposals from
unconditional cleaning, 725 were rejected on structural distance, 452 on
utility, 15 on risk, and 206 were admitted. **The structural term is the
principal gatekeeper**, which is the measurement behind the claim that model
utility cannot carry the acceptance decision alone.

## The result that reorders the contribution

`stat_only_gated` reaches damage 0.0016 against `introact_full` at 0.0020, at a
repair of +0.255 against +0.181. **A cruder proposer, gated, beats our own
complete system on the damage axis.**

This is stated rather than buried because it is the strongest evidence in the
table. If the gate only worked on our own proposals it would be an internal
component and the claim would be that our system performs well. It works on a
conservative statistical rule and on an unconditional cleaner, and with one of
them it outperforms our search, so the gate is a mechanism that stands
independently of the strategy that proposes edits.

The contribution is therefore not a better curation agent. It is an execution
time acceptance layer that can be placed around one, and our full system is one
instance of proposer plus gate rather than the centre of the claim.

## Protected edits landing on clean_ood, by form

| method | random_walk | pulse_train | staircase | sawtooth |
|---|---|---|---|---|
| stat_only | 9 | 9 | 5 | 6 |
| **stat_only_gated** | **2** | **2** | **1** | **2** |
| always_clean | 23 | 22 | 23 | 22 |
| **always_clean_gated** | **4** | **6** | **4** | **2** |
| introact_full | 2 | 1 | 0 | 2 |

**These two rows must be used for different purposes and the distinction is not
cosmetic.**

`stat_only` is the informative row. It has a criterion and chooses where to
act, and it still edits 9 of 53 random_walk windows and 9 of 52 pulse_train
windows, the two forms that share no structure with any injected defect. A
proposer driven by statistical judgement is being misled on clean data, which
is the mechanism the paper argues about.

`always_clean` may **not** be used to support that mechanism. It edits
everything unconditionally, so editing 22 or 23 of about 52 windows per form is
what it does everywhere and is not evidence of being misled. That row is
admissible for one purpose only: showing that even against a proposer that acts
on every window, the gate removes about 80 percent of the edits that would land
on protected data.

## What is not claimed

Nothing here says the gated corpus trains a better model. That is measured in
`results/downstream_gated.json` and is not prejudged. Nothing here involves
AegisTS, whose repository is missing the `Datasets` module all four of its core
modules import; the modularity claim rests on two external proposers without it.
