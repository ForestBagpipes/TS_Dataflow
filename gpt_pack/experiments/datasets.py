"""ETT dataset loading and window extraction.

The ETT-small CSVs live in ``data/``. Each row is one time step and each
column after the timestamp is one channel, so a window is a contiguous slice of
one channel. Windows containing missing values are dropped here rather than
imputed: the evaluation corpus needs a defect-free base to inject into, so that
"contaminated" means exactly "we put something there".
"""

from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ETT_FILES = {
    "ETTh1": "ETT-small_ETTh1.csv",
    "ETTh2": "ETT-small_ETTh2.csv",
    "ETTm1": "ETT-small_ETTm1.csv",
    "ETTm2": "ETT-small_ETTm2.csv",
}

ETT_FREQ = {"ETTh1": "H", "ETTh2": "H", "ETTm1": "15T", "ETTm2": "15T"}

#: The industrial half of section 4.1.1's corpus. ETTm2 is loadable and is not
#: part of it: the document names three transformer sources, and a fourth from
#: the same two devices adds sampling positions rather than a distinct regime.
INDUSTRIAL = ("ETTh1", "ETTh2", "ETTm1")

#: The financial half, exported from the TIME benchmark by time_export.py. The
#: values are (T, C) matrices in npz files so that reading them needs numpy and
#: nothing else, see that script for why.
TIME_FILES = {
    "Crypto": "time_Crypto.npz",
    "US Term Structure": "time_US_Term_Structure.npz",
    "Oil Price": "time_Oil_Price.npz",
}
FINANCIAL = tuple(TIME_FILES)

MIRRORS = (
    "https://raw.githubusercontent.com/zhouhaoyi/ETDataset/main/ETT-small",
    "https://raw.githubusercontent.com/thuml/Time-Series-Library/main/dataset/ETT-small",
)


def ensure_ett(name: str) -> Path:
    """Path to one ETT CSV, downloading it on first use."""
    dest = DATA_DIR / ETT_FILES[name]
    if dest.exists():
        return dest
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    import urllib.request

    for mirror in MIRRORS:
        try:
            urllib.request.urlretrieve(f"{mirror}/{name}.csv", str(dest))
            return dest
        except Exception:
            continue
    raise FileNotFoundError(f"could not obtain {name}.csv; place it at {dest}")


def load_ett(name: str) -> tuple:
    """Return (values, channel_names) for one ETT file."""
    import pandas as pd

    df = pd.read_csv(ensure_ett(name))
    channels = [c for c in df.columns if c.lower() not in ("date", "unnamed: 0")]
    values = df[channels].to_numpy(dtype=np.float64)
    return values, channels


def sample_ett_windows(
    n_windows: int,
    window_len: int = 512,
    datasets: tuple = INDUSTRIAL,
    seed: int = 42,
    min_std: float = 1e-3,
) -> list:
    """Draw defect-free windows spread across ETT files and channels.

    Returns a list of dicts with ``series``, ``dataset``, ``channel``, ``freq``
    and ``start``. Sampling round-robins over (file, channel) pairs so no single
    channel dominates the corpus.
    """
    rng = np.random.RandomState(seed)
    pools = []
    for name in datasets:
        values, channels = load_ett(name)
        for ci, ch in enumerate(channels):
            pools.append((name, ch, ci, values[:, ci]))

    windows = []
    attempts = 0
    max_attempts = n_windows * 40
    while len(windows) < n_windows and attempts < max_attempts:
        attempts += 1
        name, ch, ci, col = pools[len(windows) % len(pools)]
        T = len(col)
        if T <= window_len:
            continue
        start = int(rng.randint(0, T - window_len))
        seg = col[start : start + window_len]
        if not np.isfinite(seg).all() or float(np.std(seg)) < min_std:
            continue
        windows.append(
            {
                "series": seg.astype(np.float64).copy(),
                "dataset": name,
                "channel": ch,
                "freq": ETT_FREQ[name],
                "start": start,
            }
        )
    if len(windows) < n_windows:
        raise RuntimeError(
            f"only found {len(windows)}/{n_windows} usable ETT windows"
        )
    return windows


def channel_columns(names=None) -> dict:
    """Every channel's full history, keyed by (dataset, channel).

    The stratum selection in corpus.py expresses its criteria against the
    channel a window came from, so it needs the column and not just the window.
    Loading is cheap relative to a curation run and the result is small, both
    halves together are under twenty megabytes.
    """
    out = {}
    for name in (names or INDUSTRIAL):
        if name in TIME_FILES:
            values, channels, _ = load_time(name)
        else:
            values, channels = load_ett(name)
        for ci, ch in enumerate(channels):
            out[(name, ch)] = values[:, ci]
    return out


# -- the financial half of the corpus, from the TIME benchmark --------------
#
# Section 4.1.1 takes two scene families rather than one because peer
# calibration and abstention both assume the corpus is structurally
# heterogeneous, and a single source cannot test that assumption. The three
# sources here carry real cross channel coupling: crypto prices move together,
# the whole forward rate curve shifts at once, and refined products track crude.
# That coupling is what multi channel system noise has to be injected against,
# and it is why these arrive as channel groups rather than loose columns.
#
# Two things differ from ETT and both change how windows are drawn.
#
# **Scale.** Bitcoin sits near 26000 and Litecoin near 81 in the same file, and
# the oil sources mix crude near 75 with refined products near 2.2. An absolute
# spread floor of 1e-3 admits a flat crypto window and rejects nothing, while
# the same floor on a rate curve quoted in percent rejects genuinely varying
# windows. The floor is therefore relative to the channel's own spread, with a
# small absolute term left only to catch numerically degenerate columns.
#
# **Gaps.** Term structure is 95.7 percent finite and oil price 94.9 percent,
# against ETT's complete coverage. Missing entries are left in place by the
# exporter, because dropping them would shift the time axis and break channel
# alignment, so the sampler skips any window that is not finite throughout. The
# corpus needs a defect free base, since contaminated has to mean exactly that
# something was put there.


def load_time(name: str, compact: bool = True):
    """Return (values, channels, freq) for one exported TIME source.

    With ``compact`` the non trading rows are removed. This is not an
    imputation choice dressed up as a loading detail, it is what the data is.
    Term structure is 95.7 percent finite and oil price 94.9 percent, and in
    both the gaps fall on whole rows: 403 of 9326 and 259 of 5035, every channel
    missing together, spaced a median of 22 and 16 rows apart. Those are market
    holidays on a Monday to Friday calendar, roughly ten a year, not sensor
    dropouts. Leaving them in makes a gap free window of 512 steps impossible,
    since the longest uninterrupted run is 74 rows and 62 rows respectively.

    Two alternatives were rejected. Filling the holidays forward would write
    flat segments into a corpus where flatline is one of the injected defects,
    so the base would no longer be defect free. Shortening the window for the
    financial half alone would make the two scene families incomparable.

    Dropping whole rows keeps every channel on the same index, so the cross
    channel coupling that multi channel system noise is injected against is
    preserved exactly.
    """
    path = DATA_DIR / TIME_FILES[name]
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not present. Run experiments/time_export.py in an "
            f"environment that has pyarrow, see that script's docstring.")
    with np.load(path, allow_pickle=True) as z:
        values = z["values"].astype(np.float64)
        channels = [str(c) for c in z["channels"]]
        freq = str(z["freq"])
    if compact:
        keep = np.isfinite(values).all(axis=1)
        partial = int(np.sum(np.isfinite(values).any(axis=1) & ~keep))
        if partial:
            raise RuntimeError(
                f"{name} has {partial} rows missing in some channels but not "
                f"all, which is not the holiday pattern this assumes")
        values = np.ascontiguousarray(values[keep])
    return values, channels, freq


def local_scale(column: np.ndarray, window_len: int, n_probe: int = 40,
                seed: int = 0) -> float:
    """Median spread of same length windows drawn from this channel.

    The comparison a flatness test wants is against what this channel normally
    does over this span, not against the channel's whole history. Prices trend,
    so a column's global spread is mostly the trend: US term structure runs from
    eight percent to near zero across the sample, and every 512 step window
    looks flat beside that. Measured against the local scale instead the median
    window sits at 1.0 by construction and the first percentile at 0.27, so a
    threshold well under one rejects a stuck channel and nothing else.
    """
    col = column[np.isfinite(column)]
    if col.size <= window_len:
        return float(np.std(col)) if col.size > 1 else 0.0
    rng = np.random.RandomState(seed)
    starts = rng.randint(0, col.size - window_len, size=n_probe)
    return float(np.median([np.std(col[s:s + window_len]) for s in starts]))


def _usable(seg: np.ndarray, scale: float, min_std_ratio: float,
            abs_floor: float = 1e-9) -> bool:
    """Is this window finite throughout and not flat for its own channel."""
    if not np.isfinite(seg).all():
        return False
    spread = float(np.std(seg))
    if spread < abs_floor:
        return False
    return spread >= min_std_ratio * max(scale, 1e-12)


def sample_time_windows(
    n_windows: int,
    window_len: int = 512,
    sources: tuple = FINANCIAL,
    seed: int = 42,
    min_std_ratio: float = 0.05,
) -> list:
    """Draw defect free windows across the financial sources and channels.

    Round robins over (source, channel) pairs on the same schedule the ETT
    sampler uses, so neither the 40 channel rate curve nor the 4 channel crypto
    file dominates by channel count alone.
    """
    rng = np.random.RandomState(seed)
    pools = []
    for name in sources:
        values, channels, freq = load_time(name)
        for ci, ch in enumerate(channels):
            col = values[:, ci]
            pools.append((name, ch, ci, col, freq,
                          local_scale(col, window_len)))

    windows, attempts = [], 0
    while len(windows) < n_windows and attempts < n_windows * 80:
        attempts += 1
        name, ch, ci, col, freq, scale = pools[len(windows) % len(pools)]
        if len(col) <= window_len:
            continue
        start = int(rng.randint(0, len(col) - window_len))
        seg = col[start:start + window_len]
        if not _usable(seg, scale, min_std_ratio):
            continue
        windows.append({
            "series": seg.astype(np.float64).copy(),
            "dataset": name, "channel": ch, "freq": freq, "start": start,
        })
    if len(windows) < n_windows:
        raise RuntimeError(
            f"only found {len(windows)}/{n_windows} usable financial windows")
    return windows


def sample_time_window_groups(
    n_groups: int,
    window_len: int = 512,
    sources: tuple = FINANCIAL,
    seed: int = 42,
    min_std_ratio: float = 0.05,
) -> list:
    """Draw groups of financial windows sharing a source and a start position.

    The counterpart of `sample_ett_window_groups`. A group is the unit multi
    channel system noise is injected into, so every channel of the position has
    to be present and usable or the group is dropped.
    """
    rng = np.random.RandomState(seed)
    loaded = {n: load_time(n) for n in sources}
    scales = {n: [local_scale(v[:, ci], window_len) for ci in range(v.shape[1])]
              for n, (v, _, _) in loaded.items()}
    order = list(sources)

    out, gid, attempts = [], 0, 0
    while gid < n_groups and attempts < n_groups * 400:
        attempts += 1
        name = order[gid % len(order)]
        values, channels, freq = loaded[name]
        T = values.shape[0]
        if T <= window_len:
            continue
        start = int(rng.randint(0, T - window_len))
        block = values[start:start + window_len, :]
        ok = all(_usable(block[:, ci], scales[name][ci], min_std_ratio)
                 for ci in range(block.shape[1]))
        if not ok:
            continue
        for ci, ch in enumerate(channels):
            out.append({
                "series": block[:, ci].astype(np.float64).copy(),
                "dataset": name, "channel": ch, "freq": freq, "start": start,
                "group_id": gid, "channel_index": ci,
            })
        gid += 1
    if gid < n_groups:
        raise RuntimeError(
            f"only assembled {gid}/{n_groups} financial channel groups")
    return out


# -- cross domain sources, used for the real_ood stratum --
#
# Naming caveat, important. The stratum identifier is real_ood and the code
# keeps that name so existing result files stay comparable, but these windows
# are cross domain, not verifiably out of distribution. Exchange rate and solar
# power are standard public benchmarks that appear in the Monash repository and
# in Time-Series-Library, so they may well sit inside the pretraining corpus of
# the frozen backends. We could not verify membership either way. Everything
# built on this stratum should say cross domain and should not be offered as
# strict out of distribution evidence.
#
# What they still establish is the practical case: real corpora are stitched
# together from many domains, and this measures whether the method misfires on
# that. Daily exchange rates and ten minute solar power are far from electricity
# transformer temperature whatever their pretraining status. Both files were
# copied read only from the work1 tree, which had already downloaded them, and
# neither is written back.

CROSS_DOMAIN = {
    "exchange": "exchange.txt.gz",
    "solar": "solar.txt.gz",
}


def load_cross_domain(name: str):
    """Return the raw matrix of one cross domain source, time by channel."""
    import gzip

    path = DATA_DIR / CROSS_DOMAIN[name]
    if not path.exists():
        raise FileNotFoundError(f"{path} not present, see CROSS_DOMAIN")
    with gzip.open(path, "rt") as fh:
        return np.loadtxt(fh, delimiter=",")


def sample_cross_domain_windows(
    n_windows: int,
    window_len: int = 512,
    sources: tuple = ("exchange", "solar"),
    seed: int = 42,
    min_std_ratio: float = 0.05,
) -> list:
    """Draw defect free windows from domains unlike the base corpus.

    Windows that are nearly constant are skipped. Solar in particular is zero
    every night across many channels, and a flat window would be filtered as a
    stuck sensor rather than recognised as unfamiliar, which is a different
    phenomenon from the one under test.
    """
    rng = np.random.RandomState(seed)
    pools = []
    for name in sources:
        mat = load_cross_domain(name)
        for ci in range(mat.shape[1]):
            pools.append((name, ci, mat[:, ci]))

    out, attempts = [], 0
    while len(out) < n_windows and attempts < n_windows * 200:
        attempts += 1
        name, ci, col = pools[rng.randint(len(pools))]
        if len(col) <= window_len:
            continue
        start = int(rng.randint(0, len(col) - window_len))
        seg = col[start : start + window_len].astype(np.float64)
        if not np.isfinite(seg).all():
            continue
        spread = float(np.std(seg))
        if spread < min_std_ratio * max(float(np.std(col)), 1e-9) or spread < 1e-8:
            continue
        out.append({
            "series": seg.copy(),
            "dataset": f"ood:{name}",
            "channel": str(ci),
            "freq": "D" if name == "exchange" else "10T",
            "start": start,
        })
    if len(out) < n_windows:
        raise RuntimeError(f"only found {len(out)}/{n_windows} cross domain windows")
    return out


# -- channel grouped sampling, for the multivariate downstream evaluation ----
#
# The default sampler round robins over (file, channel) pairs, so the windows in
# a corpus come from unrelated positions in unrelated channels. That is the
# right choice for curation, which operates on one channel at a time, and it
# makes a multivariate downstream evaluation impossible: the seven channels of
# any given timestamp are not all present in the corpus.
#
# This sampler draws a position once and takes every channel at that position,
# so a group can be reassembled into a (T, C) matrix after curation. Curation
# still sees one univariate window at a time and needs no change. The original
# sampler is kept and unmodified, since every result currently in the repository
# was produced with it.


def sample_ett_window_groups(
    n_groups: int,
    window_len: int = 512,
    datasets: tuple = ("ETTh1", "ETTh2", "ETTm1", "ETTm2"),
    seed: int = 42,
    min_std: float = 1e-3,
) -> list:
    """Draw groups of windows that share a file and a start position.

    Returns a flat list of the same dicts `sample_ett_windows` returns, with two
    extra keys, ``group_id`` and ``channel_index``, so the caller can reassemble
    them. A group is emitted only if every channel at that position is finite
    and non degenerate, because a group missing a channel cannot be stacked.
    """
    rng = np.random.RandomState(seed)
    loaded = {name: load_ett(name) for name in datasets}

    out, gid, attempts = [], 0, 0
    max_attempts = n_groups * 40
    while gid < n_groups and attempts < max_attempts:
        attempts += 1
        name = datasets[gid % len(datasets)]
        values, channels = loaded[name]
        T = len(values)
        if T <= window_len:
            continue
        start = int(rng.randint(0, T - window_len))
        block = values[start : start + window_len, :]
        if not np.isfinite(block).all():
            continue
        if float(np.min(np.std(block, axis=0))) < min_std:
            continue
        for ci, ch in enumerate(channels):
            out.append({
                "series": block[:, ci].astype(np.float64).copy(),
                "dataset": name,
                "channel": ch,
                "freq": ETT_FREQ[name],
                "start": start,
                "group_id": gid,
                "channel_index": ci,
            })
        gid += 1
    if gid < n_groups:
        raise RuntimeError(f"only formed {gid}/{n_groups} complete channel groups")
    return out
