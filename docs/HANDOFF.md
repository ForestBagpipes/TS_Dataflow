# Handoff, state as of 2026-08-10, GPU session

Everything is committed. The GPU queue was stopped cleanly, nothing is running.

## What this session produced

Step 0 and step 1 of the GPU queue are done. Steps 2 to 5 are not started.

**Step 0, preflight.** chronos-bolt-base loads in 8.8s with all three
capabilities. GovernanceTrace.summary was verified against a real trace on
disk, not assumed: per step delta_utility, struct_distortion, risk, and
operator parameters are all recorded.

**Step 1, corpus scaled to 2000 windows**, real TSFMs, 37 percent contaminated,
`results/xl/`. The protected strata now hold 210 to 420 windows each, against
ten before.

| method | net | repair | over clean | damage | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|
| stat_only | +0.449 | 0.585 | 0.451 | 0.0931 | 374 | 653 | 36 percent |
| ablate_no_reprobe | +0.345 | 0.388 | 0.196 | 0.0295 | 241 | 295 | 45 percent |
| ablate_no_protection | +0.340 | 0.379 | 0.198 | 0.0268 | 190 | 258 | 42 percent |
| ablate_no_verify | +0.292 | 0.387 | 0.308 | 0.0655 | 314 | 479 | 40 percent |
| **introact_full** | +0.242 | 0.272 | **0.132** | **0.0205** | 141 | **183** | **44 percent** |
| quality_rank | -0.042 | 0.022 | 0.267 | 0.0442 | 70 | 430 | 14 percent |
| always_clean | **-0.216** | 0.078 | 1.000 | 0.2015 | 299 | 1701 | 15 percent |

At scale, unconditional cleaning is now clearly net negative, -0.216, damaging
1701 of 2000 windows. The full agent keeps the lowest over-cleaning and the
lowest damage of any method that edits, and the fewest windows worsened.

Protection by stratum, full agent: rare_valid 0.090 edited with damage 0.0028,
changepoint 0.100 with 0.0132, clean_ood 0.095 with 0.0522, clean 0.138 with
0.0120, hard 0.229 with 0.0309. The hard stratum is the weakest, which is
consistent with everything else: hard windows look defective to a statistical
profile and a strong model is not obviously hurt by them.

## The deferred question is answered, and epsilon is exonerated

Of 184 RESEGMENT candidates judged at this scale, 127 were accepted and 57 were
rejected on utility. Every one of those 57 had a **genuinely negative**
delta_utility, median -0.2830, range -10.39 to -0.0015. **None was merely below
the 0.005 threshold.** Widening epsilon would have changed nothing.

The earlier picture of 0 accepted out of 12 came from a 210 window corpus. At
2000 windows RESEGMENT is accepted 69 percent of the time. That earlier number
was sampling noise, and the audit conclusion built on it, that one operator
accounted for the entire deficit, does not survive the larger corpus. The
mechanism finding from the span check still stands: those refusals are correct
readings of a real absence of utility gain.

## Where the queue stopped

`scripts/_queue.sh` chains the remaining jobs and was killed mid step 2. To
resume, relaunch it. It waits for any xl job then runs the sweep and the
ablations in order.

    source /root/autodl-tmp/work2/scripts/env_autodl.sh
    cd /root/autodl-tmp/work2
    (nohup ./scripts/_queue.sh > logs/queue.log 2>&1 </dev/null &)

Remaining, in order: contamination sweep at 5 10 20 35 50 67 with both rulers,
the eight rung ablation ladder including the two new rungs plus the tau sweep,
downstream fine tuning transfer, and the competitor baselines.

## Two efficiency fixes worth knowing about

Both were found by watching the meter rather than by reading the code.

Perception pinned one core while the GPU sat at 22 percent. The statistical
half is pure numpy and embarrassingly parallel, so it now goes to a process
pool. On 2000 windows it fell from an estimated 1000 seconds to 302.

transfer_metrics issued one forecast per window per model, so scoring a method
that edits nothing cost 567 seconds, and it was paid ten times per run. Batched
by horizon it is 21.7 seconds.

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

## The trade-off the paper has to argue, not hide

Heavy corpus (210 windows, 67% contaminated), real TSFMs, after the scale fix:

| method | net corpus | repair | over-clean | damage | improved | worsened | edit precision |
|---|---|---|---|---|---|---|---|
| stat_only | **+0.731** | 0.766 | 0.500 | 0.0961 | 76 | 68 | 53% |
| ablate_no_reprobe | +0.495 | 0.516 | 0.257 | 0.0583 | 50 | 35 | 59% |
| ablate_no_protection | +0.493 | 0.503 | 0.271 | 0.0297 | 41 | 25 | 62% |
| ablate_no_verify | +0.442 | 0.484 | 0.400 | 0.1181 | 56 | 59 | 49% |
| **introact_full** | +0.311 | 0.320 | **0.200** | **0.0254** | 33 | **20** | **62%** |
| always_clean | -0.032 | 0.042 | 1.000 | 0.2085 | 57 | 153 | 27% |

At this contamination rate the plain statistical baseline more than doubles our
net effect. It is not an artefact: with two thirds of the corpus dirty,
repairing indiscriminately pays, and the windows that pay most are the
`level_shift` ones whose NMSE sits at 4.76 while every other contamination is
below 0.9. One stratum dominates the average.

What IntroAct-TS buys is on the other side of the ledger: it damages 20 windows
where stat_only damages 68, at a 62% edit precision against 53%, with a fifth
of the over-cleaning and a quarter of the damage. It edits 53 windows where
stat_only edits 144 — and that is also the weakness, because plenty of the 91 it
declined were genuinely repairable.

Two honest options, and they are not exclusive:

1. **Argue the operating point.** Verified curation trades recall for precision.
   That is the right trade when data is irreplaceable and a wrong edit is
   expensive, and the wrong one when the corpus is mostly rubbish and anything
   is better than nothing. Report both regimes (`small` at 37% contamination has
   IntroAct-TS ahead on net; `heavy` at 67% does not) and say which the method
   is for.
2. **Recover recall without giving up precision.** 103 of the 153 rollbacks were
   ROLLED_BACK_UTILITY. Before touching `epsilon`, find out how many of those
   were edits that would in fact have moved the window toward the truth --
   the ground truth is available offline, so this is directly measurable.
   If a large share were, the utility term is too strict; if few were, the
   agent is behaving correctly and option 1 is the whole story.

Do the measurement in option 2 first. It costs one run and it decides whether
there is a bug or a position to defend.

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
