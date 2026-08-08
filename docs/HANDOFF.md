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

## The open question — RESOLVED

The repair inversion under real TSFMs was a scale bug, not a threshold or a
weighting problem, and it was in the denominator of nearly every indicator in
the method.

`reference_scale` was the interquartile range of the whole window. A
`level_shift` contamination displaces one segment, which inflates that global
IQR **3.0x** (measured: 2.36-3.48 across the stratum; every other contamination
sits at 1.00). Since that quantity divides the forecast error, the
reconstruction error, the jump magnitude and the noise ratio, the contamination
was dividing away its own evidence: level-shifted windows scored *below* the
corpus median on behavioural risk, were filed as clean, and never had a
RESEGMENT proposed. Confirmed in the traces -- of five level_shift windows,
three were left alone outright and two were offered only IMPUTE.

The fix is `actions.robust_scale`: the median of per-block IQRs instead of the
global IQR. A displaced segment corrupts only the block spanning the break, and
the median discards it. Inflation for `level_shift` drops from 3.04x to 1.00x.
The same scale now serves `probe`, `risk` and `structure`, which had each
carried their own copy of the bug.

Effect on the real-TSFM run (small/ETT/multi-family, same corpus and seed):

| | before fix | after fix |
|---|---|---|
| repair | **-0.050** | **+0.367** |
| over-clean | 0.100 | **0.083** |
| damage to protected | 0.0121 | 0.0121 |
| level_shift repair | -0.122 (action acc 0.00) | **+0.466** (acc 0.40) |
| missing_scattered | +0.022 | +0.255 |

The ablations are now much sharper on real models than they ever were on the
surrogate. Removing the structural veto collapses repair from 0.367 to 0.141,
where under the surrogate the same ablation was indistinguishable from the full
method (0.395 vs 0.403). The verification machinery earns its place only when
the judge is a model good enough for its opinion to matter.

Full table, real TSFM after the fix:

| method | repair | over-clean | damage |
|---|---|---|---|
| **introact_full** | **0.367** | **0.083** | **0.0121** |
| ablate_no_reprobe | 0.391 | 0.200 | 0.0268 |
| ablate_no_verify | 0.382 | 0.283 | 0.0568 |
| ablate_no_structure | 0.141 | 0.167 | 0.0222 |
| stat_only | 0.168 | 0.417 | 0.0888 |
| always_clean | -0.027 | 1.000 | 0.2071 |

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
