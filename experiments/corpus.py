"""Stratified evaluation corpus.

A curation agent that only ever sees corrupted data can look excellent while
being useless: the interesting failures are the false positives. So the corpus
is built in six strata, and only the first is supposed to be repaired.

  contaminated   real windows with a known defect injected; the pristine
                 original is retained as ``clean_series`` so repair quality can
                 be measured against ground truth
  clean          real windows, untouched -- any edit here is over-cleaning
  hard           real windows that are genuinely difficult (low signal-to-noise,
                 weak periodicity) but carry no defect
  rare_valid     a real transient excursion: large, brief, and legitimate
  changepoint    a legitimate regime switch -- the seasonal structure itself
                 changes, as opposed to the corrupted variant where the level
                 is merely displaced
  clean_ood      internally clean series whose shape is unlike the rest of the
                 corpus (random walk, staircase, pulse train)

The distinction between the ``level_shift`` contamination and the
``changepoint`` stratum is the sharpest test in the corpus: both produce a
break, one is an artefact worth resegmenting and the other is the data doing
what the system really did.
"""

from dataclasses import dataclass

import numpy as np

from introact_ts.types import TSWindow

CONTAMINATIONS = (
    "missing_block",
    "missing_scattered",
    "flatline",
    "spike",
    "noise",
    "level_shift",
    "duplicate",
)

STRATA = (
    "contaminated",
    "clean",
    "hard",
    "rare_valid",
    "changepoint",
    "clean_ood",
    "real_ood",
)

#: Which operator is the intended repair for each contamination. Used to score
#: action selection; ``None`` means no operator in the space should fire.
ORACLE_ACTION = {
    "missing_block": "IMPUTE",
    "missing_scattered": "IMPUTE",
    "flatline": "IMPUTE",
    "spike": "DESPIKE",
    "noise": "DENOISE",
    "level_shift": "RESEGMENT",
    "duplicate": "RESEGMENT",
}


def _spread(x: np.ndarray) -> float:
    q75, q25 = np.percentile(x[np.isfinite(x)], [75, 25])
    s = float(q75 - q25)
    return max(s, float(np.std(x)), 1e-6)


# -- contamination operators ------------------------------------------------


def inject(series: np.ndarray, kind: str, rng: np.random.RandomState) -> tuple:
    """Apply one contamination. Returns (corrupted, mask of affected points)."""
    x = np.asarray(series, dtype=np.float64).copy()
    T = len(x)
    mask = np.zeros(T, dtype=bool)
    s = _spread(x)

    if kind == "missing_block":
        length = int(rng.randint(max(8, T // 20), max(12, T // 8)))
        lo = int(rng.randint(T // 8, T - length - T // 8))
        x[lo : lo + length] = np.nan
        mask[lo : lo + length] = True

    elif kind == "missing_scattered":
        n = int(rng.randint(max(6, T // 60), max(10, T // 25)))
        idx = rng.choice(np.arange(T // 10, T - T // 10), size=n, replace=False)
        x[idx] = np.nan
        mask[idx] = True

    elif kind == "flatline":
        length = int(rng.randint(max(24, T // 20), max(32, T // 10)))
        lo = int(rng.randint(T // 8, T - length - T // 8))
        x[lo : lo + length] = x[lo]
        mask[lo : lo + length] = True

    elif kind == "spike":
        n = int(rng.randint(3, 9))
        idx = rng.choice(np.arange(T // 12, T - T // 12), size=n, replace=False)
        signs = rng.choice([-1.0, 1.0], size=n)
        x[idx] = x[idx] + signs * rng.uniform(4.0, 8.0, size=n) * s
        mask[idx] = True

    elif kind == "noise":
        level = rng.uniform(0.5, 0.9) * s
        x = x + rng.randn(T) * level
        mask[:] = True

    elif kind == "level_shift":
        lo = int(rng.randint(T // 3, 2 * T // 3))
        x[lo:] = x[lo:] + rng.choice([-1.0, 1.0]) * rng.uniform(2.5, 4.0) * s
        mask[lo:] = True

    elif kind == "duplicate":
        length = int(rng.randint(max(24, T // 12), max(32, T // 6)))
        src = int(rng.randint(0, T - 2 * length))
        dst = int(rng.randint(src + length, T - length))
        x[dst : dst + length] = x[src : src + length]
        mask[dst : dst + length] = True

    else:
        raise ValueError(f"unknown contamination: {kind}")

    return x, mask


# -- special strata ---------------------------------------------------------


def make_rare_valid(series: np.ndarray, rng: np.random.RandomState) -> np.ndarray:
    """A real transient excursion: large, brief, and returning to baseline.

    Structurally this is what an injected spike is not -- it is wide enough to
    be a genuine event and the series comes back from it, which is precisely
    the pattern the agent must learn to leave alone.
    """
    x = np.asarray(series, dtype=np.float64).copy()
    T = len(x)
    s = _spread(x)
    length = int(rng.randint(max(16, T // 24), max(24, T // 12)))
    lo = int(rng.randint(T // 5, T - length - T // 5))
    ramp = np.sin(np.linspace(0.0, np.pi, length)) ** 0.5
    x[lo : lo + length] += rng.choice([-1.0, 1.0]) * rng.uniform(2.5, 4.0) * s * ramp
    return x


def make_changepoint(series: np.ndarray, rng: np.random.RandomState) -> np.ndarray:
    """A legitimate regime switch: the seasonal structure itself changes.

    The level is preserved -- what changes is amplitude and period. That is the
    hard case against ``level_shift``, where the level is displaced and the
    structure is not.
    """
    x = np.asarray(series, dtype=np.float64).copy()
    T = len(x)
    s = _spread(x)
    cut = int(rng.randint(2 * T // 5, 3 * T // 5))
    tail = np.arange(T - cut, dtype=np.float64)
    period = rng.uniform(8.0, 40.0)
    amp = rng.uniform(0.5, 1.2) * s
    modulated = x[cut:] * rng.uniform(0.4, 0.75) + amp * np.sin(
        2.0 * np.pi * tail / period + rng.uniform(0, 2 * np.pi)
    )
    x[cut:] = modulated - np.median(modulated) + np.median(x[cut:])
    return x


def make_clean_ood(kind: str, T: int, rng: np.random.RandomState) -> np.ndarray:
    """Internally clean series with a shape unlike the rest of the corpus."""
    t = np.arange(T, dtype=np.float64)
    if kind == "random_walk":
        return np.cumsum(rng.randn(T)) * rng.uniform(0.5, 2.0)
    if kind == "staircase":
        n_steps = int(rng.randint(4, 10))
        edges = np.sort(rng.choice(np.arange(1, T), size=n_steps, replace=False))
        out = np.zeros(T, dtype=np.float64)
        level = 0.0
        prev = 0
        for e in list(edges) + [T]:
            out[prev:e] = level
            level += rng.randn() * 2.0
            prev = e
        return out + rng.randn(T) * 0.05
    if kind == "pulse_train":
        period = int(rng.randint(20, 60))
        out = np.zeros(T, dtype=np.float64)
        width = max(2, period // 8)
        for start in range(int(rng.randint(0, period)), T, period):
            out[start : start + width] = rng.uniform(3.0, 6.0)
        return out + rng.randn(T) * 0.05
    # sawtooth
    period = rng.uniform(30.0, 90.0)
    return 2.0 * ((t / period) % 1.0) - 1.0 + rng.randn(T) * 0.05


OOD_KINDS = ("random_walk", "staircase", "pulse_train", "sawtooth")


# -- corpus assembly --------------------------------------------------------


@dataclass
class CorpusSpec:
    n_contaminated: int = 140
    n_clean: int = 80
    n_hard: int = 40
    n_rare_valid: int = 40
    n_changepoint: int = 40
    n_clean_ood: int = 40
    #: Real out of distribution windows, drawn from domains unlike the base
    #: corpus rather than generated. Zero by default so existing runs are
    #: unchanged.
    n_real_ood: int = 0
    window_len: int = 512
    seed: int = 42

    @property
    def total(self) -> int:
        return (
            self.n_contaminated + self.n_clean + self.n_hard
            + self.n_rare_valid + self.n_changepoint + self.n_clean_ood
            + self.n_real_ood
        )


def _synthetic_base(n: int, T: int, rng: np.random.RandomState) -> list:
    """Fallback base windows when the ETT files are unavailable."""
    t = np.arange(T, dtype=np.float64)
    out = []
    for _ in range(n):
        trend = rng.uniform(-0.03, 0.03) * t
        signal = np.zeros(T)
        for _ in range(rng.randint(1, 3)):
            period = rng.choice([12.0, 24.0, 48.0, 96.0])
            signal += rng.uniform(1.0, 5.0) * np.sin(
                2 * np.pi * t / period + rng.uniform(0, 2 * np.pi)
            )
        out.append(
            {
                "series": trend + signal + rng.randn(T) * rng.uniform(0.1, 0.4),
                "dataset": "synthetic",
                "channel": "sim",
                "freq": "H",
                "start": 0,
            }
        )
    return out


def _difficulty(series: np.ndarray) -> float:
    """Difficulty proxy: how little exploitable structure a window carries.

    Deliberately *not* the high-frequency energy share. That is the very
    statistic the noise contamination raises, so selecting hard windows by it
    would make the two indistinguishable by construction and the resulting
    "hard" stratum would just be undeclared noise. What makes a window hard is
    the absence of structure to predict from: weak dominant periodicity and
    weak short-range memory.
    """
    x = np.asarray(series, dtype=np.float64)
    x = x - x.mean()
    spec = np.abs(np.fft.rfft(x)) ** 2
    total = spec[1:].sum()
    if total < 1e-12:
        return 1.0
    seasonal = float(spec[1:].max() / total)

    denom = float(np.dot(x, x)) + 1e-12
    acf = [abs(float(np.dot(x[:-k], x[k:]) / denom)) for k in (1, 2, 3)]
    memory = float(np.mean(acf))
    return float(1.0 - 0.5 * (seasonal / 0.3 if seasonal < 0.3 else 1.0) - 0.5 * memory)


def build_corpus(spec: CorpusSpec = None, source: str = "ett") -> list:
    """Assemble the stratified corpus. Returns a list of ``TSWindow``."""
    spec = spec or CorpusSpec()
    rng = np.random.RandomState(spec.seed)
    T = spec.window_len

    # Over-draw so the `hard` stratum can be selected by difficulty rather than
    # constructed, which would make it a synthetic artefact.
    n_base = spec.total + spec.n_hard * 4
    if source == "ett":
        from datasets import sample_ett_windows

        base = sample_ett_windows(n_base, window_len=T, seed=spec.seed)
    else:
        base = _synthetic_base(n_base, T, rng)

    difficulties = np.asarray([_difficulty(b["series"]) for b in base])
    order = np.argsort(-difficulties)
    hard_idx = set(order[: spec.n_hard].tolist())
    rest = [i for i in range(len(base)) if i not in hard_idx]
    rng.shuffle(rest)

    windows = []
    wid = 0
    cursor = 0

    def take():
        nonlocal cursor
        item = base[rest[cursor]]
        cursor += 1
        return item

    # contaminated
    per_kind = max(1, spec.n_contaminated // len(CONTAMINATIONS))
    plan = [k for k in CONTAMINATIONS for _ in range(per_kind)]
    while len(plan) < spec.n_contaminated:
        plan.append(CONTAMINATIONS[len(plan) % len(CONTAMINATIONS)])
    for kind in plan[: spec.n_contaminated]:
        item = take()
        clean = item["series"].copy()
        dirty, mask = inject(clean, kind, rng)
        wid += 1
        windows.append(
            TSWindow(
                window_id=wid, series=dirty, freq=item["freq"],
                dataset=item["dataset"], stratum="contaminated", contamination=kind,
                clean_series=clean, corrupt_mask=mask, seed=spec.seed,
            )
        )

    # clean
    for _ in range(spec.n_clean):
        item = take()
        clean = item["series"].copy()
        wid += 1
        windows.append(
            TSWindow(
                window_id=wid, series=clean.copy(), freq=item["freq"],
                dataset=item["dataset"], stratum="clean", clean_series=clean,
                seed=spec.seed,
            )
        )

    # hard
    for i in sorted(hard_idx):
        item = base[i]
        clean = item["series"].copy()
        wid += 1
        windows.append(
            TSWindow(
                window_id=wid, series=clean.copy(), freq=item["freq"],
                dataset=item["dataset"], stratum="hard", clean_series=clean,
                seed=spec.seed,
            )
        )

    # rare_valid
    for _ in range(spec.n_rare_valid):
        item = take()
        s = make_rare_valid(item["series"], rng)
        wid += 1
        windows.append(
            TSWindow(
                window_id=wid, series=s.copy(), freq=item["freq"],
                dataset=item["dataset"], stratum="rare_valid", clean_series=s.copy(),
                seed=spec.seed,
            )
        )

    # changepoint
    for _ in range(spec.n_changepoint):
        item = take()
        s = make_changepoint(item["series"], rng)
        wid += 1
        windows.append(
            TSWindow(
                window_id=wid, series=s.copy(), freq=item["freq"],
                dataset=item["dataset"], stratum="changepoint", clean_series=s.copy(),
                seed=spec.seed,
            )
        )

    # clean_ood
    for i in range(spec.n_clean_ood):
        kind = OOD_KINDS[i % len(OOD_KINDS)]
        s = make_clean_ood(kind, T, rng)
        wid += 1
        windows.append(
            TSWindow(
                window_id=wid, series=s.copy(), freq="H", dataset=f"ood:{kind}",
                stratum="clean_ood", clean_series=s.copy(), seed=spec.seed,
            )
        )

    # real_ood, drawn from other domains rather than generated
    if spec.n_real_ood:
        from datasets import sample_cross_domain_windows

        for item in sample_cross_domain_windows(
            spec.n_real_ood, window_len=T, seed=spec.seed
        ):
            s = item["series"]
            wid += 1
            windows.append(
                TSWindow(
                    window_id=wid, series=s.copy(), freq=item["freq"],
                    dataset=item["dataset"], stratum="real_ood",
                    clean_series=s.copy(), seed=spec.seed,
                )
            )

    rng.shuffle(windows)
    return windows
