# The valuation family baselines, protocol fixed before any of them runs

Written 2026-08-18, before any valuation score has been computed. Every rule
below is fixed here so that no choice among them can be made after seeing which
choice is more favourable.

## Why this family is in the paper at all

Work on time series data quality splits into two families that do different
things.

**The valuation family** assigns a quality score to each sample and then selects
a subset by score. It never modifies data. Members include Data Shapley,
KNN Shapley, Data-OOB, TimeInf and TSRating.

**The cleaning family** modifies data in place. Members include SCREEN, IMR and
the classic constraint repair line.

This paper is in the cleaning family. Its target setting, corpus preparation for
time series foundation models, is the setting the valuation family addresses.
Covering only the cleaning family would leave the comparison incomplete on the
axis that the target setting is actually judged on. So both families appear.

The specific selection is not ours. TSRating compares against Data Shapley,
KNN Shapley, Data-OOB and TimeInf. TSQAgent compares against Data Shapley,
Data-OOB, TimeInf and TSRating. Implementing the first three puts this paper in
the same comparison setting those two use.

## Implementation route per method, with the reason

| method | venue | route | reason |
|---|---|---|---|
| TimeInf | 2024 | `yzhang511/TimeInf`, direct | `timeinf/linear_influence.py` is 58 lines of pure numpy. The heavy requirements serve the blackbox and transformer paths only. |
| Data Shapley | ICML 2019 | `opendataval`, not the original | `amiratag/DataShapley` imports tensorflow at module level and is TF1 era code. The node runs python 3.11 where TF1 does not install. |
| Data-OOB | ICML 2023 | `opendataval`, not the original | `ykwon0407/dataoob` forks sklearn private API including `_get_n_samples_bootstrap` and `_parallel_build_trees`. The node runs sklearn 1.9.0 against that repository's 1.3 era assumptions. It also ships no license file. |

`opendataval` is NeurIPS 2023, MIT licensed, and carries both methods plus
KNN Shapley. Using it for both is one adapter rather than two.

**It needs its own environment.** Its `pyproject.toml` pins `numpy~=1.26.4`,
`torch~=2.2.2` and `scikit-learn~=1.3`, against the node's 2.4.6, 2.11.0 and
1.9.0. Scores are computed in that environment and written to a file. Selection
and downstream evaluation read the file in the main environment. Per
`docs/environment_preflight.md`, the scoring launcher asserts the interpreter
path and the three pinned versions before it starts.

## The window level score, the rule that must be fixed in advance

These methods score a supervised sample. This corpus is organised in windows.
The two units do not coincide and the mapping changes the result, so it is fixed
here.

**TimeInf** blocks a series and scores each block. `utils.block_time_series`
takes the block length directly. One window is one block. No aggregation.

**Data Shapley and Data-OOB** score an `(X, y)` pair. A window is expanded by
autoregressive featurisation, so one window of length L with lag order p yields
L minus p supervised samples, each of which receives its own value.

**The window score is the arithmetic mean of its samples' values, not the sum.**
The reason is that RESEGMENT produces windows of unequal length, and a sum would
rank a long window above a short one for length alone. The mean is invariant to
that. This is a decision about a confound, not a preference, and it is recorded
before any score exists.

## Selection

Selection keeps the top fraction by score. Two fractions are reported, **50
percent and 75 percent**. Both are reported for every method. Neither is
selected after the fact as the better one.

The valuation family produces a smaller corpus. Our method produces a corpus of
the same size with some windows rewritten. The comparison is therefore at equal
selection budget for the valuation arms against each other, and against our
method at its own natural output, with the size difference stated in the table
rather than normalised away.

## The shared corpus protocol

One contaminated corpus. Each method produces its own prepared corpus from it.
One downstream setup consumes all of them.

| item | value |
|---|---|
| split | 7:2:1 train, validation, test |
| downstream models | PatchTST and a CNN |
| task | long term forecasting |
| metric | RMSE |

The split happens before any curation or selection, so no test window influences
the model scored on it. This matches the existing downstream protocol in
`docs/downstream.md`, including its finding that comparisons must be paired
within seed.

## The safety metric the valuation family does not measure

Every method above reports accuracy on the downstream task. None reports what it
discarded.

**Retention rate on protected strata, reported separately for hard, rare_valid,
changepoint and clean_ood.** The fraction of each stratum's windows that survive
into the prepared corpus.

This is the direct measurement of the failure mode a selection method has and a
repair method does not. Data that is rare, difficult or unusual but entirely
correct scores low under a quality model, and selection then deletes it. Our
method cannot delete it, because its action space rewrites windows and does not
drop them.

Fixed before the runs, so that it counts as a prediction:

- The valuation arms will show retention below the selection fraction on
  `rare_valid` and `hard`, since those strata are what a quality score is
  expected to penalise.
- If they instead retain those strata at or above the selection fraction, the
  claimed differentiation does not hold and will be reported as not holding.

The second branch is written down deliberately. It is the outcome that costs us
the argument, and it is stated in advance at the same level of detail as the
first.

## What is not claimed

Estimation accuracy of the valuation methods is not re-verified. They are used
as published, on this corpus, and the comparison is at the level of the prepared
corpus and its downstream effect. Whether their scores correlate with any
intrinsic notion of quality is their claim and not tested here.
