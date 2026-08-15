# Reconstructing the AegisTS data loader, timeboxed

## Status of the request

The public repository at `github.com/Syh517/AegisTS` is missing the `Datasets`
package. All four core modules import from it:

- `Error_Cleaner/RLclean.py:26`
- `Error_Detection/Detector.py:28` and `:30`
- `Error_Cleaner/tools/missing.py:139`
- `Error_Cleaner/tools/anomaly.py:151`
- `Error_Cleaner/tools/constraints.py:85`

and `.gitignore` contains `Datasets/` and `*.csv`. **The authors were contacted
and replied that the module cannot be located and cannot be supplied.** The
paper's reproducibility statement records the request and that answer.

## What is being attempted, and the rule for stopping

Reconstruct `load_single_dataset`, `sample_data_by_rate` and
`convert_to_unix_timestamp` from their call sites, run the published pipeline on
ETTh1, and compare against the paper's own reported row.

**Acceptance criterion, fixed here before the attempt:**

| metric | target from the paper |
|---|---|
| F1 | 0.6758 |
| NMSE | 0.0040 |
| RRA | 0.7966 |
| delta Perf | +0.0442 |

Matching in magnitude with a consistent trend is enough. Exact agreement is not
expected from a reconstructed loader and is not required.

**If it matches**, the AegisTS row is usable as a proposer in the gating
experiment and the paper states that faithfulness was verified against the
published numbers.

**If it does not match, the line stops.** The comparison falls back to the
mechanism level contrast in related work, which needs no code from them. No
parameter is adjusted to close a gap, because a reconstructed loader tuned until
the numbers agree would produce a comparison whose credibility is lower than
having no comparison at all.

**Three working days from the start of the reconstruction.** Not extended on the
grounds of effort already spent.

## Reconstruction evidence, in priority order

**1. The return contract at the four call sites.** The strongest evidence, since
it is the code that has to work. `RLclean.py` main takes `dirty_data` and
optional `label`, and calls `DataManager(data, task_type=...)` after
`np.expand_dims(data, axis=0)` when `len(data.shape) == 2`, so
`load_single_dataset` returns a 2D array for forecasting and a 3D one plus
labels for classification. `sample_data_by_rate(data, label, rate)` returns the
pair, so it subsamples along the instance axis.

**2. The dataset table in the paper.** Gives the shapes to hit: ETTh1 length
17420 with 7 features for forecasting, IDF_OilTemp 1024 by 4 for forecasting,
Libras 360 samples 15 classes, Handwriting 1000 samples 26 classes.

**3. The `rate` argument.** The paper states the contamination injection follows
MTSClean's protocol, so the semantics of `rate` should be read from MTSClean's
implementation rather than guessed. That is the reference to consult before
writing anything for this argument.

**4. `convert_to_unix_timestamp`.** The paper describes estimating the sampling
interval as the mode of consecutive time differences and aligning to a regular
grid. The function should implement that, not a general parser.

## Where this sits

Outside the main queue. It does not delay M2, the soft against hard comparison,
the M4 integration test, or the oracle and random proposers. Those are the
critical path; this is an addition to it.
