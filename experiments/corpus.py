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

from collections import defaultdict
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

# -- the two noise classes of section 4.1.2 ---------------------------------
#
# Random noise lands on one channel at a time, its position and magnitude drawn
# independently. Systematic noise lands on several channels of the same time
# position at once and the channels share the direction of the offset, because
# what produces it is one event upstream of all of them: a recalibration, a
# feed change, a market wide move.
#
# ``flatline`` sits in the systematic class rather than the random one. It was
# previously routed to IMPUTE, which reads a held value as a gap to fill. On a
# multi channel feed a stuck value is the feed itself stalling, every channel
# holds its last value together, and the repair is to cut the stalled span out
# rather than to interpolate across it. Its oracle operator moves accordingly.
RANDOM_NOISE = ("spike", "missing_scattered", "missing_block", "duplicate")
SYSTEMATIC_NOISE = ("level_shift", "noise", "flatline")

#: Which class each contamination belongs to.
NOISE_CLASS = {
    **{k: "random" for k in RANDOM_NOISE},
    **{k: "systematic" for k in SYSTEMATIC_NOISE},
}

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
    # A stalled feed is a span to cut, not a gap to interpolate. See the noise
    # class note above for why this moved.
    "flatline": "RESEGMENT",
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


def inject_systematic_group(block: np.ndarray, kind: str,
                            rng: np.random.RandomState,
                            share: float = 1.0) -> tuple:
    """Inject one systematic defect across several channels of one position.

    ``block`` is (T, C), the channels of a single time position. The defect is
    placed once and applied to a subset of the channels, all of them at the
    same time index and, where the defect has a direction, with the same sign.
    That shared direction is the whole point: a per channel draw would average
    out across the group and read as random noise, which is the class this one
    is defined against.

    ``share`` is the fraction of channels affected, so a partial event can be
    injected as well as a whole feed failure. Channels are chosen without
    replacement.

    Returns (corrupted block, per channel boolean masks, affected channel
    indices).
    """
    if kind not in SYSTEMATIC_NOISE:
        raise ValueError(f"{kind} is not a systematic defect")
    x = np.asarray(block, dtype=np.float64).copy()
    T, C = x.shape
    masks = np.zeros((T, C), dtype=bool)

    n_hit = max(2, int(round(share * C))) if C >= 2 else C
    hit = np.sort(rng.choice(C, size=min(n_hit, C), replace=False))

    # One draw per event, reused by every affected channel. Sign included.
    sign = float(rng.choice([-1.0, 1.0]))
    if kind == "level_shift":
        lo = int(rng.randint(T // 3, 2 * T // 3))
        size = rng.uniform(2.5, 4.0)
        for ci in hit:
            s_c = _spread(x[:, ci])
            x[lo:, ci] = x[lo:, ci] + sign * size * s_c
            masks[lo:, ci] = True
    elif kind == "noise":
        level = rng.uniform(0.5, 0.9)
        # The disturbance is drawn once and scaled per channel, so the channels
        # move together rather than independently. Independent draws here would
        # be the random class wearing the systematic label.
        shape = rng.randn(T)
        for ci in hit:
            x[:, ci] = x[:, ci] + shape * level * _spread(x[:, ci])
            masks[:, ci] = True
    elif kind == "flatline":
        length = int(rng.randint(max(24, T // 20), max(32, T // 10)))
        lo = int(rng.randint(T // 8, T - length - T // 8))
        for ci in hit:
            x[lo:lo + length, ci] = x[lo, ci]
            masks[lo:lo + length, ci] = True

    return x, masks, hit


# -- special strata ---------------------------------------------------------


# -- selection of the two protected strata ----------------------------------
#
# Criteria and thresholds are fixed in docs/stratum_selection_preregistration.md
# and were committed before this code ran. Nothing here may be widened to make a
# layer fill: a shortfall is reported with its cause instead.
#
# Both layers used to be constructed, a real window plus a synthetic excursion
# or a synthetic tail modulation. Section 4.1.2 claims they are taken from the
# data, and that claim is the one worth having, so the construction went and the
# selection arrived.

#: See the pre registration for the derivation of each of these.
TAIL_PERCENTILE = 99.5
BRIEF_FRAC = 0.05
RETURN_TOL = 0.5
JUMP_D = 2.5
SCALE_RATIO = 1.5
SPLIT_MARGIN = 0.25


def channel_reference(column: np.ndarray) -> tuple:
    """Robust centre, scale and tail threshold of one channel.

    Every criterion is expressed against these rather than against a constant,
    because the corpus now spans quantities three orders of magnitude apart
    inside a single file.
    """
    col = np.asarray(column, dtype=np.float64)
    col = col[np.isfinite(col)]
    if col.size < 8:
        return 0.0, 1.0, np.inf
    m = float(np.median(col))
    q75, q25 = np.percentile(col, [75, 25])
    s = max(float(q75 - q25), 1e-12)
    tail = float(np.percentile(np.abs((col - m) / s), TAIL_PERCENTILE))
    return m, s, tail


def is_rare_valid(series: np.ndarray, ref: tuple) -> tuple:
    """Criterion A. Returns (qualifies, diagnostics)."""
    m, s, tail = ref
    x = np.asarray(series, dtype=np.float64)
    if not np.isfinite(x).all() or not np.isfinite(tail):
        return False, {}
    z = np.abs((x - m) / s)
    peak = float(z.max())
    hits = z >= tail
    share = float(hits.mean())
    q = len(x) // 4
    ends = abs(float(np.median(x[:q])) - float(np.median(x[-q:]))) / s
    ok = bool(peak >= tail and share <= BRIEF_FRAC and ends <= RETURN_TOL)
    return ok, {"peak_z": peak, "tail_z": float(tail),
                "tail_share": share, "end_gap": float(ends)}


def best_split(series: np.ndarray, ref: tuple) -> tuple:
    """Criterion B's statistics at the strongest split in the middle half."""
    m, s, tail = ref
    x = np.asarray(series, dtype=np.float64)
    T = len(x)
    lo, hi = int(SPLIT_MARGIN * T), int((1.0 - SPLIT_MARGIN) * T)
    if hi - lo < 2:
        return 0.0, np.inf, -1
    # Cumulative sums make the scan over all admissible splits exact and cheap.
    cs = np.concatenate([[0.0], np.cumsum(x)])
    idx = np.arange(lo, hi)
    left_mean = cs[idx] / idx
    right_mean = (cs[T] - cs[idx]) / (T - idx)
    d = np.abs(left_mean - right_mean) / s
    k = int(idx[int(np.argmax(d))])
    sl, sr = float(np.std(x[:k])), float(np.std(x[k:]))
    ratio = sl / max(sr, 1e-12)
    return float(d.max()), float(ratio), k


def jump_t(series: np.ndarray, ref: tuple) -> tuple:
    """The rank statistic of the changepoint criterion, and its two gates.

    `t` is the difference of segment means over the pooled within segment
    standard deviation, so it is invariant to rescaling the window and needs no
    reference to the channel or to the injector. See
    `docs/changepoint_criterion_preregistration.md` for why an absolute
    threshold on any unit was abandoned: the financial median sits above the
    industrial ninetieth percentile in every unit measured.
    """
    x = np.asarray(series, dtype=np.float64)
    if not np.isfinite(x).all():
        return -np.inf, {}
    _, ratio, k = best_split(x, ref)
    if not (0 < k < len(x)):
        return -np.inf, {}
    pooled = float(np.sqrt((np.var(x[:k]) + np.var(x[k:])) / 2.0))
    t = abs(float(np.mean(x[:k])) - float(np.mean(x[k:]))) / max(pooled, 1e-12)
    rare, _ = is_rare_valid(x, ref)
    gates = bool((1.0 / SCALE_RATIO) <= ratio <= SCALE_RATIO and not rare)
    return (t if gates else -np.inf), {
        "t": t, "scale_ratio": ratio, "split": k, "also_rare": bool(rare),
        "passes_gates": gates}


def select_changepoints(items, refs, families, n_wanted):
    """Top `t` within each family, quota split in proportion to the pool.

    `items` are (index, series) pairs, `refs` maps index to that window's
    channel reference and `families` maps index to a family label. Returns the
    chosen indices and a per family report including the shortfall, which is
    reported rather than repaired.
    """
    scored = {}
    for idx, series in items:
        t, diag = jump_t(series, refs[idx])
        scored[idx] = (t, diag)

    by_family = defaultdict(list)
    for idx in scored:
        by_family[families[idx]].append(idx)

    total = sum(len(v) for v in by_family.values())
    chosen, report = [], {}
    for fam, idxs in sorted(by_family.items()):
        quota = int(round(n_wanted * len(idxs) / max(total, 1)))
        eligible = sorted((i for i in idxs if np.isfinite(scored[i][0])),
                          key=lambda i: -scored[i][0])
        take = eligible[:quota]
        chosen.extend(take)
        report[fam] = {
            "pool": len(idxs), "quota": quota, "eligible": len(eligible),
            "taken": len(take), "shortfall": max(0, quota - len(take)),
            "t_selected": [round(float(scored[i][0]), 4) for i in take],
        }
    return chosen, report


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


def build_corpus(spec: CorpusSpec = None, source: str = "ett",
                 base: list = None) -> list:
    """Assemble the stratified corpus. Returns a list of ``TSWindow``.

    ``base`` optionally supplies the pool of defect free windows to draw from,
    instead of sampling one here. It exists so a caller can control how the pool
    was drawn, for instance to guarantee that every channel at a position is
    present. Passing None preserves the original behaviour exactly.
    """
    spec = spec or CorpusSpec()
    rng = np.random.RandomState(spec.seed)
    T = spec.window_len

    # Over-draw so the `hard` stratum can be selected by difficulty rather than
    # constructed, which would make it a synthetic artefact.
    n_base = spec.total + spec.n_hard * 4
    if base is not None:
        if len(base) < n_base:
            raise ValueError(f"base has {len(base)} items, need {n_base}")
        base = base[:n_base]
    elif source == "ett":
        from datasets import sample_ett_windows

        base = sample_ett_windows(n_base, window_len=T, seed=spec.seed)
    elif source in ("finance", "mixed"):
        # Section 4.1.1 takes both scene families because peer calibration and
        # abstention assume the corpus is structurally heterogeneous, and one
        # source cannot test that. The halves are interleaved rather than
        # concatenated so that the difficulty ranking which selects the hard
        # stratum sees both, and so a truncated pool is not all one family.
        from datasets import sample_ett_windows, sample_time_windows

        if source == "finance":
            base = sample_time_windows(n_base, window_len=T, seed=spec.seed)
        else:
            n_fin = n_base // 2
            fin = sample_time_windows(n_fin, window_len=T, seed=spec.seed)
            ind = sample_ett_windows(n_base - n_fin, window_len=T,
                                     seed=spec.seed)
            base = [w for pair in zip(ind, fin) for w in pair]
            base += ind[len(fin):] + fin[len(ind):]
            base = base[:n_base]
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


# -- grouped corpus, for the multivariate downstream evaluation --------------


def build_corpus_grouped(spec: CorpusSpec = None, seed: int = None):
    """Assemble a corpus whose windows can be reassembled per channel group.

    Returns ``(windows, group_map)``, where group_map sends a window id to
    (group_id, channel_index). The map is separate from the window because the
    window type is consumed by the curation loop and a downstream evaluation is
    not a reason to change it. The grouping travels through the ``dataset``
    label, which is metadata only and is read nowhere except the trace summary.

    Only strata drawn from the ETT pool can be reassembled. The clean out of
    distribution stratum is generated rather than drawn, so it has no channel
    siblings and is absent from the map by construction. That is correct: those
    windows are synthetic univariate shapes and a multivariate block containing
    them would be a fiction.

    **This changes the corpus composition** relative to the default sampler,
    which draws positions and channels independently. Curation results on a
    grouped corpus are therefore not comparable with results already in this
    repository and must be recomputed.
    """
    spec = spec or CorpusSpec()
    seed = spec.seed if seed is None else seed
    n_base = spec.total + spec.n_hard * 4

    from datasets import sample_ett_window_groups

    n_channels = 7
    n_groups = int(np.ceil(n_base / n_channels)) + 1
    grouped = sample_ett_window_groups(n_groups, window_len=spec.window_len,
                                       seed=seed)
    for g in grouped:
        g["dataset"] = f"{g['dataset']}#g{g['group_id']}c{g['channel_index']}"

    windows = build_corpus(spec, source="ett", base=grouped)

    group_map = {}
    for w in windows:
        label = w.dataset or ""
        if "#g" not in label:
            continue
        tag = label.split("#g", 1)[1]
        gid, _, ci = tag.partition("c")
        try:
            group_map[w.window_id] = (int(gid), int(ci))
        except ValueError:
            continue
    return windows, group_map
