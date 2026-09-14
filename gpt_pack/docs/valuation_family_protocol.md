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

## The route changed after reading TSRating's own baseline code

`scoring/baseline_annotate.py` in `clsr1008/TSRating` implements all four
valuation baselines in one function, on one `DataFetcher`, with the
hyperparameters that paper published:

| method | source of the implementation | hyperparameters as published |
|---|---|---|
| Data-OOB | `opendataval.dataval.DataOob` | `num_models=1000` |
| Data Shapley | `opendataval.dataval.DataShapley` | `gr_threshold=1.1, max_mc_epochs=100, min_models=100` |
| KNN Shapley | `opendataval.dataval.KNNShapley` | `k_neighbors=0.1 * len(X_train)` |
| TimeInf | `calc_linear_time_inf`, vendored | mean influence on the validation blocks |
| shared utility model | `RegressionSkLearnWrapper(LinearRegression)` | |

**This is the route taken.** Reimplementing the adapters ourselves would have
meant choosing those hyperparameters by guess, and the comparison would then be
against our reading of the methods rather than against the configuration a
published paper ran them in. Using their file puts all four on the same fetcher,
the same utility model and the same block set, which is what makes them
comparable to each other as well as to us.

KNN Shapley falls out of the same call at no extra cost. It is not on the
required list but it is in TSRating's comparison table, so it is reported.

**A usage error avoided, recorded because it was nearly made.** TimeInf's own
repository uses self influence, `calc_linear_time_inf(i, i, ...)`, wrapped in
`scale_influence` which takes the absolute deviation from the mean. That is the
anomaly detection reading and it is the wrong one here. For data valuation
TSRating uses influence of training block `i` averaged over the validation
blocks, which is signed and ranks blocks by how much they help. Taking the
anomaly detection path would have scored deviation rather than value.

## Block construction and scale

| item | value | reason |
|---|---|---|
| block length | 128 | TSRating's default and the value in their example |
| features and target | first 127 points predict the 128th | their `X = block[:, :-1]`, `Y = block[:, -1]` |
| blocks per window | non overlapping, so 4 per 512 point window | see scale note below |
| corpus scale | 800 windows | see scale note below |

**Scale note.** TSRating slices one continuous series of 4000 points, giving
about 2673 training blocks. This corpus is 800 or 2000 independent windows of
512 points each. Fully overlapping blocks at step 1 would give 385 blocks per
window, so 2000 windows would produce 770000 blocks, which the Data Shapley
Monte Carlo cannot run at. Non overlapping blocks on 800 windows give 3200
blocks, the same order as their 2673. The change is from step 1 to step 128 and
it is made for tractability, stated rather than hidden.

Train, validation and test are split **by window, not by time point**, so every
block of a window lands in the same split and no window contributes to both the
model and its own valuation.

**A split discrepancy to note.** The instruction for this work says 7:2:1.
TSRating's `main` uses 0.7 train, 0.1 validation, and the remaining 0.2 test,
namely 7:1:2. The 7:2:1 given here is followed, and the difference from
TSRating's own split is recorded so it is not mistaken for a transcription of
theirs.

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
splits a series of length L at block length p into L minus p overlapping blocks,
each of which receives its own influence value. A window here is 512 points, so
one window yields hundreds of blocks.

**Data Shapley and Data-OOB** score an `(X, y)` pair. A window is expanded by
autoregressive featurisation, so one window of length L with lag order p yields
L minus p supervised samples, each of which receives its own value.

The two are the same shape. Both produce many per position values inside one
window, and both need the same rule to reach a window score.

**The window score is the arithmetic mean of its per position values, not the
sum.** The reason is that RESEGMENT produces windows of unequal length, and a
sum would rank a long window above a short one for length alone. The mean is
invariant to that. This is a decision about a confound, not a preference, and it
is recorded before any score exists.

A correction to this section, made on the same day and before any score was
computed. It first read that one window is one TimeInf block and needs no
aggregation. That was wrong on a checkable fact, `CorpusSpec.window_len` is 512
in `experiments/corpus.py`, so a window is far longer than any block length this
method uses. The corrected rule is the one above and it is now identical across
all three methods, which is the simpler arrangement anyway. The original wording
is recorded here rather than silently replaced.

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

## Windows the valuation family cannot consume, found on export

Measured while writing the exporter, on the `small` scale: **10 of 95 windows
carry non finite values and cannot be turned into supervised blocks at all.**
Those are exactly the windows with an injected gap, `missing_block`,
`missing_scattered` and the flatline variant, since the injection writes NaN.

This is not a detail of the file format. It decides whether the comparison is
fair, and in the direction that flatters the baselines.

An `(X, y)` regression sample cannot hold a NaN, so a valuation method never
sees the windows that IMPUTE exists to repair. If those windows are simply
dropped from the export the valuation arms are scored on an easier corpus than
the cleaning arms, and their protected stratum retention is computed over a
denominator that excludes the hardest cases.

**The rule, fixed here before any score is computed.** Windows that cannot be
blocked are not dropped from the comparison. They are carried into the prepared
corpus of every valuation arm as **not selected**, that is, treated as if the
method had scored them at the bottom and its selection had discarded them. This
is the behaviour the family actually has on such data: a scorer that cannot
score a window cannot keep it.

The count of such windows is reported in every table that involves the valuation
family, next to the selection fraction, so that a reader can see how much of the
corpus was decided by this rule rather than by a score.

Imputing them before export was rejected. It would hand the valuation arms a
repaired corpus produced by our own operator, so their input would already
contain the intervention under test.

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
