# Version ledger

One row per method version. A version enters this table only after both of the
following: the number was read out of the code that produces it, and an
independent script recomputed it from the raw traces and agreed. When the two
disagree, both are recorded and the row stays out until the disagreement is
resolved.

## The locked measurement conventions

Fixed 2026-08-27. Every row below uses these and nothing else, otherwise
versions cannot be compared.

| column | definition |
|---|---|
| damage rate | harmful commits over committed edits, harm measured by `audit._nmse` against the clean reference. Definition 1 of section 4.1.4 |
| protected mis edit rate | edited windows in `clean`, `hard`, `rare_valid` and `changepoint`, over the size of those four strata. The synthetic probe layer `clean_ood` is excluded and reported separately |
| **nRMSD** | **window count weighted mean over the five sound contamination kinds only**, that is `duplicate`, `flatline`, `level_shift`, `noise`, `spike` |
| edits | committed edits over windows carrying a clean reference |

**Why the two missing kinds are excluded from nRMSD.** The distance drops non
finite differences, so a window with a hole sits at distance zero from the truth
and an arm that fills nothing scores perfectly on it. `missing_block` and
`missing_scattered` are 212 of 740 injected windows, 28.6 percent, and including
them rewards inaction on that share of the denominator. The full derivation and
the per kind table are in `docs/number_selfchecks.md` under the repair nRMSD
ruling.

**Consequence for older numbers.** The ablation table reports 1.0764 for
`f_full`. That is the plain mean over all seven kinds and is not this ledger's
convention. The same arm under this convention is 1.5080. Both are correct
readings of different quantities; only the second is comparable across versions
here.

## Versions

| version | damage rate | protected mis edit rate | nRMSD | edits | note |
|---|---|---|---|---|---|
| v1 | 0.1306 +- 0.0084 | 0.0635 +- 0.0054 | 1.5080 | 161 +- 9 | the current main table's `f_full`, three seeds, `results/xl/`, commit `7e16b8c` |

### v1 provenance

Three seeds at xl on the mixed corpus, method layer code hash
`1f6d57bb1a15e4a0`, aggregated by `experiments/aggregate_ablations.py`. Damage
rate and mis edit rate were reconciled against the flushed traces by that
script, 12 of 12 combinations agreeing exactly. The nRMSD figure comes from
`experiments/aggregate_soft.py`'s sound kind reader over the same traces.

### What v1 is known to be wrong about, carried forward as the reason for v2

Phase 0, recorded in `docs/diagnostic-playbook.md`:

  the structural condition never judged RESEGMENT, distortion was identically
  zero on all 2766 attempts, because the alignment step discarded exactly the
  region the operator affects. 180 of v1's commits are protected layer crops
  that discarded a median 40 percent of the window at a reported distortion of
  zero and a mean fidelity gain of zero or below

  DENOISE was accepted zero times in 416 attempts, its median distortion 0.2085
  being ten times the global threshold, so one operator of four contributed
  nothing but consumed probe budget

**So v1's mis edit rate is inflated by a broken measurement and its edit count
contains repairs that repaired nothing.** A v2 that lowers both is correcting an
error rather than trading one metric for another, and the ledger's rule for v2
is stated before it runs: damage rate and protected mis edit rate must both
fall. A rise in nRMSD is admissible only with the injected layer's own repair
accuracy reported beside it, since removing false accepts removes their
contribution to the average as well.
