# IntroAct-TS — code overview

Intervention-verified, reversible data curation for time-series foundation
models. Every curation action is treated as a candidate that must earn its
commit: it is applied to a sandbox copy, the frozen TSFM is re-probed on that
copy, and the edit survives only if model utility improved **and** temporal
structure was preserved **and** the decision risk is acceptable. Otherwise the
agent rolls back, tries another action, or refuses to act.

## Layout

```
src/introact_ts/     pure method layer, zero file IO
  types.py           Action / Verdict / TSWindow / ActionRecord / GovernanceTrace
  backends/          frozen backend registry: base protocol + surrogate,
                     chronos, moment, timesfm adapters
  tsfm.py            backwards-compatible facade over backends/
  probe.py           six families of behavioural signals -> 14-dim vector + utility
  profiling.py       12-dim statistical profile (defines the peer group)
  calibration.py     profile-conditioned peer calibration; re-calibration after an edit
  risk.py            statistical evidence, corpus-adaptive references, hypothesis posterior
  actions.py         the seven operators; each returns a new array and a footprint
  structure.py       bounded structural distortion, local vs global operator profiles
  verify.py          the acceptance rule and the decision-risk term
  policy.py          ordered action proposals from the risk state
  agent.py           the perceive - act - verify - rollback loop

experiments/         thin IO shells
  datasets.py        ETT loading and defect-free window sampling
  corpus.py          the six-stratum evaluation corpus and its contaminations
  baselines.py       no_action / always_clean / stat_only / quality_rank
  metrics.py         detection, action, repair, protection, rollback, transfer
  run_agent.py       main experiment: baselines + ablations, JSON + Markdown output

tests/               67 tests over operators, structure, probe, risk, and the loop
scripts/
  setup_remote.sh    per-family install for a rented GPU box
  verify_backends.py loads each backend and exercises the probe surface
```

## Running

```bash
pip install -r requirements.txt
python experiments/run_agent.py --scale small  --source ett     # ~2 min, 95 windows
python experiments/run_agent.py --scale medium --source ett     # ~6 min, 190 windows
python experiments/run_agent.py --scale full   --source ett     # 380 windows
python -m pytest tests/ -q
```

Results land in `results/<scale>_<source>_seed<n>.{json,md}` plus a
`_traces.json` holding the per-window governance trace. `--source synthetic`
swaps the ETT base for generated series, which is useful when the CSVs are
unavailable.

## Frozen backends

Backends live in `src/introact_ts/backends/` and are named `family:checkpoint`.
Only `forecast_batch` is mandatory; `base.ForecastOnlyMixin` derives backcasting
and masked reconstruction from it, and a backend declares what else it can do
through `capabilities` rather than silently returning zeros. Batching is in the
contract because the probe issues ~30 forward passes per window — served one at
a time that is nearly all launch overhead.

| family | checkpoint | capabilities | notes |
|---|---|---|---|
| `surrogate` | seed | forecast, encode, reconstruct | offline default, 39K params |
| `chronos` | `amazon/chronos-bolt-*`, `amazon/chronos-t5-*` | forecast, reconstruct (+encode on T5) | Bolt exposes no embeddings |
| `moment` | `AutonLab/MOMENT-1-large` | all three | reconstruction is its pretraining task |
| `timesfm` | `google/timesfm-2.5-200m-pytorch` | forecast, reconstruct | no hidden states exposed |

Presets in `backends.PRESETS` pair a curation pool (judge + disagreement) with a
transfer pool that never takes part in curation: `offline`, `chronos-only`,
`multi-family`.

**MOMENT is used through its reconstruction head, not its forecasting head.**
Masked reconstruction is what it was pretrained on and is genuinely zero-shot;
the forecasting head ships randomly initialised and expects fine-tuning, so
calling it zero-shot would measure noise. Forecasts are obtained by masking the
horizon and letting the pretrained head fill it in.

**The surrogate is not a pretrained foundation model.** A fixed random residual
encoder (37,248 frozen params) with a ridge head (2,080 params) fitted once on a
synthetic corpus (seed 1234, disjoint from every experiment seed). It forecasts
~24x better than last-value on seasonal data and supports every mechanism, which
makes it right for development, tests and offline reproduction — and wrong for
any claim about what real TSFM behaviour looks like.

### Running on a rented GPU

```bash
bash scripts/setup_remote.sh                       # installs each family separately
python scripts/verify_backends.py --device cuda    # run this BEFORE any long job
python experiments/run_agent.py --scale full --source ett \
    --preset multi-family --device cuda
```

`verify_backends.py` exists because the real adapters were written against
published APIs and **have never been executed** — no checkpoint is available in
the development environment. It loads each backend, exercises the full probe
surface, and scores the forecast against a seasonal-naive reference, so a
mis-wired input axis shows up in seconds instead of after an hour of curation.

## Design decisions worth knowing before changing anything

**The probe's reference scale is pinned to the original window.** Errors are
normalised by a spread computed once, not by the spread of whatever series is
being measured. Otherwise the ruler moves with the edit and the sign of ΔU stops
being trustworthy.

**The probe forward-fills NaNs rather than interpolating them.** Interpolating
would have the probe perform the repair itself: IMPUTE would produce a candidate
the model cannot distinguish from the original, ΔU would be exactly zero, and
every fill would be rolled back for failing to help.

**Local and global operators are held to different structural standards.**
IMPUTE / DESPIKE / RESEGMENT declare which points they rewrite and are judged
outside that footprint, plus a check that what they wrote is coherent with its
surroundings. DENOISE rewrites everything, so it is judged on the signal band of
the spectrum, the trend, the periodicity, the memory, and above all the tails.
A global spectral term applied to a local edit vetoes correct repairs: an
injected spike is broadband energy, so removing it shifts the spectrum enormously.

**Cropping is a cost, not a distortion.** RESEGMENT leaves every point it keeps
exactly as it found it. What it discards is charged through R(a).

**Repair quality is measured after centring.** A foundation model
instance-normalises its input, so a segment displaced by a constant is not
degraded data. Scoring raw values reports a correct RESEGMENT as catastrophic.

**Transfer is scored against the pristine continuation, not the curated one.**
Otherwise the metric rewards whichever method smoothed hardest — a flattened
series is trivially easy to predict from itself.

**Evidence thresholds are corpus-adaptive above a floor.** Fixed thresholds
calibrated on synthetic data fail on real ETT windows, which carry natural
flatlines, level changes and high-frequency energy. Adaptation may only raise a
floor and by a bounded factor, so a heavily contaminated corpus cannot talk
itself into treating its contamination as the norm. Level shifts get no
adaptation at all — their indicator is bimodal, so a MAD across the mixture
tracks the contamination rate rather than the corpus.

## Known limitations

- **Duplicated segments are not detected.** A repeated stretch is statistically
  almost invisible; the corpus includes the contamination and the results report
  the miss rather than hiding it.
- **Level shift versus legitimate regime switch is only partly separable.** The
  `shift_purity` term (does the break preserve autocorrelation, variance and
  spectrum?) helps but does not resolve it on real data. The remaining cases are
  caught downstream by rollback rather than by detection.
- **Sensitivity floors are real.** Contamination below `DEFECT_FLOORS` — roughly
  4 spikes or 4 missing points in a 512-point window — is not detected. The
  spike floor was deliberately raised to suppress false positives on
  weakly-structured ETT windows.
- **The real backends are unverified.** Chronos, MOMENT and TimesFM adapters
  were written against published APIs but have never been run: the development
  environment has no `transformers`, no checkpoints and no GPU. Every reported
  number comes from the surrogate. `scripts/verify_backends.py` is the gate that
  must pass before those adapters can be trusted.
- **Representation signals are backend-dependent.** Four of the fourteen probe
  dimensions need hidden states. Backends without `encode` leave them at zero,
  which is harmless within a run — peer calibration is always inside one backend
  — but means the behaviour vector is not comparable across families.
