# Handoff — state as of 2026-08-08

Everything is committed. Both machines can be powered off; nothing is left
running that needs to finish.

## Where things live

**Local** `F:\work\Time-research\work2` — git repo, 5 commits, working tree
clean, 67 tests passing.

**GPU box** `ssh -p 53677 root@connect.bjb2.seetacloud.com` — AutoDL container.
Its data disk persists across shutdown, so the deployment survives; only
running processes die. Nothing needs re-installing next time.

```
/root/autodl-tmp/work2          code + data + weights   (work1 is at ../work1)
/root/autodl-tmp/envs/w2        python 3.12.3           (work1 uses ../envs/fc)
/root/autodl-tmp/work2/.cache/hf  model weights         (work1 uses ../.cache/huggingface)
```

Isolation from work1 is by construction: separate tree, separate interpreter,
separate weight cache, and `~/.bashrc` was **not** modified. Activate with:

```bash
source /root/autodl-tmp/work2/scripts/env_autodl.sh
```

Only the pip *download* cache is shared, which affects download speed and
nothing else.

## Next session, first three commands

```bash
source /root/autodl-tmp/work2/scripts/env_autodl.sh
python -c "import torch; print(torch.cuda.is_available())"     # expect True
nvidia-smi --query-gpu=name --format=csv,noheader              # expect RTX 5090
```

## What is verified

Backends, measured against a seasonal-naive reference (lower is better),
`results/gpu/backend_verification.md`:

| backend | forecast | reconstruct | encode |
|---|---|---|---|
| chronos-bolt-small | 0.27x | 0.113 | 6x512 |
| timesfm-2.5-200m | 0.27x | 0.083 | — |
| chronos-bolt-base | 0.29x | 0.103 | 12x768 |
| chronos-t5-small | 0.91x | 0.131 | 6x512 |
| surrogate (offline) | 0.92x | 2.771 | 6x64 |
| MOMENT-1-large | **20.27x** | 0.378 | 24x1024 |

MOMENT's forecasting head ships randomly initialised — the paper's forecasting
numbers come from linear probing. Its reconstruction is genuinely strong. It is
excluded from the default presets because the judge's forecast error dominates
the probe's utility; a `moment-recon` preset exists for the reconstruction
study.

## The open question — read this first next time

Swapping the surrogate for real TSFMs **inverted the repair result**, on the
same corpus, same seed, same code:

| | surrogate | real TSFM (multi-family) |
|---|---|---|
| introact_full repair | **+0.248** | **−0.050** |
| stat_only repair | +0.168 | +0.168 |
| introact_full over-clean | 0.100 | 0.100 |
| introact_full damage | 0.0192 | **0.0121** |

The protection story got *better* — damage 0.0121, seventeen times lower than
`always_clean` at 0.207, and the lowest in the table. But repair went negative
while the statistical baseline stayed at +0.168.

Note what did *not* change: `stat_only` scores +0.168 under both backends,
because it never consults the model. So the inversion is entirely in the
verification signal — the real models' notion of "this edit helped" agrees less
with "this edit moved the data toward the truth" than the surrogate's did.

This is the central claim of the paper (ΔU from a frozen TSFM is a usable proxy
for data quality), so it has to be understood before anything else is built on
top. Three things to check, cheapest first:

1. **Is it the acceptance threshold?** `epsilon=0.005` was calibrated on
   surrogate utilities. Real-model utilities have a different scale and spread;
   print the ΔU distribution per contamination type and recalibrate.
2. **Is it a specific contamination?** Read the per-contamination table in
   `results/gpu/small_ett_multi-family_seed42.md`. Under the surrogate, spike
   repair was +0.667 and carried the average — check whether that survived.
3. **Is the utility rewarding predictability over fidelity?** Real TSFMs are far
   better forecasters (0.27x vs 0.92x naive), so they may prefer edits that
   make a window *easier* rather than *truer*. If so, the structural term is
   doing more work than the utility term, and the weighting in
   `probe.DEFAULT_UTILITY_WEIGHTS` needs revisiting.

Diagnose before tuning. An epsilon fitted to make the number look right would
be exactly the kind of result that does not survive review.

## Also still open

- PatchTST downstream column is untrustworthy at this scale (run-to-run
  variance exceeds the effect; fixing a normalisation bug inverted its
  ranking). Either train it properly or drop the column.
- Downstream transfer barely separates conservative methods even at 67%
  contamination — the benefit of curation reads as avoided damage, not improved
  accuracy. Weaker than the framing in the paper plan assumes.
- Duplicated segments are undetected; level-shift vs legitimate regime switch
  is only partly separable.

## Commits

```
d275176  Fix TSFM adapters against real checkpoints; deploy to GPU box
74079a6  Add downstream transfer: train on curated data, test on pristine data
a6a2296  Add pluggable frozen-backend registry with real TSFM adapters
01ab1b6  Implement IntroAct-TS: intervention-verified, reversible curation agent
```
