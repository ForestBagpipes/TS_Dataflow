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
    datasets: tuple = ("ETTh1", "ETTh2", "ETTm1", "ETTm2"),
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


# -- cross domain sources, used only for the real out of distribution stratum --
#
# The synthetic clean_ood stratum is four generated shapes, and it now carries a
# central finding, so the finding has to be checked against data that was not
# constructed for it. These two are real recordings from domains far from
# electricity transformer temperature: daily exchange rates and ten minute solar
# power. Both files were copied read only from the work1 tree, which had already
# downloaded them, and neither is written back.

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
