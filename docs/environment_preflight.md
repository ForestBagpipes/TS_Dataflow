# Environment preflight, assert the state before spending the compute

## The rule

Any experiment whose result depends on a specific environment state asserts that
state at startup and aborts if it does not hold. It does not warn and continue.
A run that quietly proceeds under a degraded environment produces a result file
that looks exactly like a valid one, and the defect surfaces later as an
unexplained inconsistency between tables.

The launcher does the assertion, not the experiment script, so the check runs
before any model loads and costs seconds rather than the length of the run.

Pattern in use, from the xl ablation launcher:

```bash
N=$(python -c "
import sys; sys.path.insert(0,'src')
from introact_ts.backends import PRESETS, make_pool
print(len(make_pool(PRESETS['multi-family']['curation'], device='cuda')))
" 2>/dev/null | tail -1)
echo "[xl] curation pool size = $N (must be 3)" >> "$LOG"
if [ "$N" != "3" ]; then
  echo "[xl] ABORT, pool is not 3, results would not be comparable" >> "$LOG"
  exit 1
fi
```

The asserted value goes in the log whether or not it passes, so the log itself
records which environment produced the result.

## Why this was added

On 2026-08-18 an xl scale ablation started with `timesfm` missing from the
environment. `make_pool` is deliberately tolerant, it skips a backend that fails
to load and only raises when no backend loads at all, so the run proceeded on
two backends instead of three. The behavioural probe, peer calibration and every
utility number depend on the pool, so that run could not have been compared
against the 210 window ablation it was meant to extend. It was killed before it
wrote anything.

The tolerance in `make_pool` is correct for its own purpose and is not being
changed. The assertion belongs at the launcher, where the comparability
requirement is known.

## The diagnostic criterion, recorded because the obvious reading is wrong

**A healthy three backend curation pool prints two `Loading weights` blocks, not
three.** `timesfm` loads through a different path and prints no progress bar.

Verified directly:

```
make_pool(PRESETS['multi-family']['curation'], device='cuda')
  -> POOLSIZE 3
  -> "Loading weights:   0%" occurrences in the captured output: 2
```

Consequences for reading old logs:

- Counting `Loading weights` blocks does not tell you how many backends loaded.
- `logs/ablations.log` shows three blocks because `run_ablations.py` also builds
  the transfer pool, whose `chronos-t5-small` prints one block. Two from
  curation plus one from transfer.
- The reliable marker is the `[skip]` line that `make_pool` prints for every
  backend that failed. It has existed since commit `a6a2296` on 2026-08-05, so
  any log written after that date is trustworthy on this point.

Applying the correct criterion across `logs/*.log`, the only file containing a
`[skip]` line is `ablations_xl.log` from the aborted run. **Every previously
committed result was produced with the full three backend pool.** An earlier
suspicion that results after 2026-08-11 were degraded came from counting blocks
and was wrong.

## Repair applied

`pip install timesfm[torch]` in the `fc` environment. A dry run was taken first
and reported `Would install timesfm-2.0.2` with every other requirement already
satisfied, so no existing package was touched. Confirmed after installation:

| package | version |
|---|---|
| torch | 2.11.0+cu128 |
| numpy | 2.4.6 |
| scikit-learn | 1.9.0 |
| cuda available | True |

The version pin matters here. The node is an RTX 5090, which is Blackwell and
needs cu12.8 or later, so any dependency resolution that downgrades torch breaks
the whole environment. Checking the dry run output before installing is part of
the procedure, not an optional caution.

The most likely cause of the loss is a node restart, since the package was
absent while its weights were still in the HF cache under
`/root/autodl-tmp/work2/.cache/hf`. This is not established, only consistent
with the evidence.

## Where else this applies

Any run that depends on state the repository does not carry:

| dependency | assertion |
|---|---|
| backend pool composition | pool size equals the expected count |
| a separate conda environment, for example the valuation family | the interpreter path and the pinned package versions |
| a dataset that is downloaded rather than generated | file count and a checksum of the manifest |
| an external API backend | one probe call that must succeed before the loop starts |
