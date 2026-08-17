# Downstream evidence, and what it does and does not support

Three supervised forecasters trained on what each method produced and scored on
pristine futures no method touched. Windows are split before any curation, so
no test window influences the model scored on it. Sources
`results/downstream_gated.json` for three seeds on the full corpus and
`results/downstream_scoped.json` for the affected subset at seed 42.

## Main result, defensive effectiveness

Paired aggregation: the improvement over `no_action` is computed within each
seed and then aggregated, so corpus sampling variation cancels in the
difference. The unpaired route was tried first and is reported below as a
methodological note.

| model | always_clean | always_clean_gated |
|---|---|---|
| **patchtst** | **-569.10%** | **-3.26%** |
| dlinear | -102.03% | -0.18% |
| ridge_ar | -95.89% | -0.15% |

**Without an execution time acceptance step, an aggressive curation pipeline
degrades downstream MSE by a factor of two to seven. With it, the same pipeline
returns to within noise of not curating at all.** Three independently trained
downstream models agree in direction and the effect is one to two orders of
magnitude above any noise floor in the experiment, so no significance argument
is needed.

The per seed values for `always_clean` on patchtst are -233.19, -1051.29 and
-422.82 percent. The spread is large and the mean is not a useful summary, so
the range is what should be reported: **degradation between two and eleven
fold, with the gate returning it to within a few percent.**

This is the downstream counterpart of the corpus level result in
`docs/gating_modularity.md`, where the same pipeline moves from repair -0.014
to +0.044. Two independent measurement routes, the same conclusion.

## Secondary result, no measurable difference for the conservative methods

| model | stat_only | stat_only_gated | introact_full | paired noise floor |
|---|---|---|---|---|
| dlinear | +0.41% | +0.38% | +0.28% | 0.28% |
| ridge_ar | +0.41% | +0.38% | +0.28% | 0.27% |
| patchtst | +0.61% | -2.88% | -0.15% | 2.99% |

Every one of these is at or below the noise floor of its own model. On dlinear
and ridge_ar `introact_full` is positive in all three seeds, +0.03, +0.34,
+0.46, with the smallest spread in the table, but the mean sits at roughly one
standard deviation and that is not a claim. On patchtst the signs are not even
stable across seeds. **Reported as no measurable difference.**

The cause is mechanical rather than a failure of the method. `introact_full`
edits 62 of 800 windows, **7.75 percent of the corpus**, and leaves the rest
byte identical to what `no_action` produces. A downstream model trained on 92
percent identical data cannot be expected to show a difference, and the
conservatism that produces that 7.75 percent is the same property that produces
the protection results.

Dilution is ruled out as the explanation. Evaluating only on the 515 windows
some method edited amplifies `stat_only` by 4.9x on patchtst and 6.4x on
ridge_ar, confirming that the mechanism is real, and leaves `introact_full`
unchanged at -0.09, +0.07 and +0.08 percent across the three models. Its 62
edited windows are all inside that subset, so the dilution is removed and the
effect is still zero.

## Limitations, stated rather than waited for

**The protocol conflates two sources of variation.** Changing the seed changes
both the corpus window sampling and the model initialisation, so an unpaired
aggregation attributes corpus variation to method differences. The unpaired
noise floor on the reference row is 33 to 34 percent, against 0.27 to 2.99
percent once paired. All numbers above are paired. This was found by us, not
raised in review, and the unpaired table is retained in the results file.

**The affected subset view is single seed and carries no standard deviation.**
It can rule out dilution as the explanation for a null result, which is what it
is used for, and it cannot establish significance on the subset.

## Why no foundation model fine tuning is reported

The role division matters here. A frozen TSFM is the **verifier** in this
method, not the object being curated: it appears in the behavioural probe and
in the judge strength experiments. Whether continued training of a foundation
model on a curated corpus helps is a different question and is **not
evaluated**.

The reason is the measurement above rather than cost. At the change volume this
method produces, under 8 percent of windows modified, the downstream protocol
in hand cannot resolve a difference on models that are far cheaper to train
than a foundation model. Spending foundation model compute to reach the same
inconclusive answer would not be informative. Establishing it needs either a
larger change volume or a protocol with a lower noise floor, and that is left
to future work.
